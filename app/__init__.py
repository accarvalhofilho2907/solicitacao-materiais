import os

from flask import Flask, send_from_directory
from sqlalchemy import inspect, text

from .extensions import db, login_manager, csrf, migrate
from .models import Usuario, TipoMaterial
from .seed_data import TIPOS_PADRAO


def _light_migrate():
    """Adiciona colunas novas que ainda não existem (não apaga dados)."""
    insp = inspect(db.engine)
    for table in db.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existentes = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existentes:
                tipo = col.type.compile(dialect=db.engine.dialect)
                db.session.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {tipo}'))
    db.session.commit()
    # Colunas "ativo" recém-criadas ficam NULL nas linhas antigas; tratar como ativas.
    for table in db.metadata.sorted_tables:
        if insp.has_table(table.name) and "ativo" in {c["name"] for c in insp.get_columns(table.name)}:
            db.session.execute(text(f'UPDATE "{table.name}" SET ativo = TRUE WHERE ativo IS NULL'))
    db.session.commit()
    # Coluna "aprovacao" recém-criada (item 145): registros antigos = 'aprovado' (não somem das listas).
    for tabela in ("fornecedores", "transportadoras"):
        if insp.has_table(tabela) and "aprovacao" in {c["name"] for c in insp.get_columns(tabela)}:
            db.session.execute(text(f"UPDATE \"{tabela}\" SET aprovacao = 'aprovado' WHERE aprovacao IS NULL"))
    db.session.commit()
    # Garante que o link aceite URLs longas (ex.: Mercado Livre) no PostgreSQL.
    if db.engine.dialect.name == "postgresql":
        try:
            db.session.execute(text('ALTER TABLE solicitacoes ALTER COLUMN link_similar TYPE TEXT'))
            db.session.commit()
        except Exception:
            db.session.rollback()
        # O email do fornecedor passou a ser opcional (item 145: cadastro pendente vindo do
        # relatório de carga não tem e-mail). A tabela antiga foi criada com NOT NULL —
        # remove essa restrição para não quebrar o INSERT do cadastro pendente.
        try:
            db.session.execute(text('ALTER TABLE fornecedores ALTER COLUMN email DROP NOT NULL'))
            db.session.commit()
        except Exception:
            db.session.rollback()
    # Backfill: todos os cadastros em MAIÚSCULAS (item 88). Idempotente.
    _maiusculas_cadastros(insp)
    # Unificação Fornecedores/Empresas (item 150). Aditiva e idempotente.
    _unificar_empresas_fornecedores(insp)


def _unificar_empresas_fornecedores(insp):
    """Item 150 — unifica Empresas dentro de Fornecedores, de forma ADITIVA e sem risco:
    - fornecedores existentes viram is_fornecedor=True (backfill dos NULL);
    - cada Empresa vira um Fornecedor com is_empresa_interna=True (se ainda não migrada);
    - Usuario.empresa_fornecedor_id é populado a partir do empresa_id antigo.
    Nada é apagado nem renumerado — os vínculos antigos continuam existindo.
    Em qualquer falha, faz rollback e não aplica (deixa como estava)."""
    from .models import Empresa, Fornecedor, Usuario
    try:
        cols_forn = {c["name"] for c in insp.get_columns("fornecedores")}
        if "is_fornecedor" not in cols_forn or "is_empresa_interna" not in cols_forn:
            return  # colunas ainda não existem neste boot; próximo boot aplica

        # 1) fornecedores sem papel definido = fornecedores de verdade
        db.session.execute(text(
            "UPDATE fornecedores SET is_fornecedor = TRUE WHERE is_fornecedor IS NULL"))
        db.session.execute(text(
            "UPDATE fornecedores SET is_empresa_interna = FALSE WHERE is_empresa_interna IS NULL"))
        db.session.commit()

        if not insp.has_table("empresas"):
            return

        # 2) cada Empresa vira um Fornecedor-empresa-interna (se ainda não existe um com esse nome)
        mapa = {}   # empresa_id -> fornecedor_id
        for emp in Empresa.query.all():
            nome = (emp.nome or "").strip()
            if not nome:
                continue
            # já migrada? procura fornecedor com mesmo nome marcado como empresa interna
            existente = (Fornecedor.query
                         .filter(Fornecedor.is_empresa_interna.is_(True))
                         .filter((Fornecedor.razao_social == nome) | (Fornecedor.nome_fantasia == nome))
                         .first())
            if existente:
                mapa[emp.id] = existente.id
                continue
            novo = Fornecedor(razao_social=nome, nome_fantasia=nome,
                              is_fornecedor=False, is_empresa_interna=True,
                              aprovacao="aprovado", ativo=bool(getattr(emp, "ativo", True)),
                              usa_email=False)
            db.session.add(novo)
            db.session.flush()   # garante o id sem fechar a transação
            mapa[emp.id] = novo.id
        db.session.commit()

        # 3) popula Usuario.empresa_fornecedor_id a partir do empresa_id antigo
        cols_user = {c["name"] for c in insp.get_columns("usuarios")}
        if "empresa_fornecedor_id" in cols_user:
            for u in Usuario.query.filter(Usuario.empresa_id.isnot(None)).all():
                if u.empresa_fornecedor_id is None and u.empresa_id in mapa:
                    u.empresa_fornecedor_id = mapa[u.empresa_id]
            db.session.commit()
    except Exception:
        db.session.rollback()
        import logging
        logging.getLogger(__name__).exception("Falha na unificação Empresas/Fornecedores (item 150) — mantido estado anterior")


def _maiusculas_cadastros(insp):
    """Converte para maiúsculas os cadastros já existentes (só altera o que precisa)."""
    alvos = [
        ("empresas", ["nome"]),
        ("usuarios", ["nome"]),
        ("tipos_material", ["nome"]),
        ("atividades", ["nome"]),
        ("cidades", ["nome", "uf"]),
        ("transportadoras", ["nome"]),
        ("fornecedores", ["razao_social", "nome_fantasia", "contato_nome"]),
    ]
    for tabela, colunas in alvos:
        if not insp.has_table(tabela):
            continue
        existentes = {c["name"] for c in insp.get_columns(tabela)}
        for col in colunas:
            if col not in existentes:
                continue
            try:
                db.session.execute(text(
                    f'UPDATE "{tabela}" SET "{col}" = UPPER("{col}") '
                    f'WHERE "{col}" IS NOT NULL AND "{col}" <> UPPER("{col}")'))
                db.session.commit()
            except Exception:
                db.session.rollback()


def _seed_tipos():
    """Cria os tipos de material padrão se ainda não existirem (idempotente)."""
    existentes = {t.nome for t in TipoMaterial.query.all()}
    novos = [TipoMaterial(nome=n) for n in TIPOS_PADRAO if n not in existentes]
    if novos:
        db.session.add_all(novos)
        db.session.commit()


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    login_manager.login_view = "auth.login"
    login_manager.login_message = "Faça login para continuar."

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(Usuario, int(uid))

    from .auth import auth_bp
    from .solicitante import sol_bp
    from .admin import admin_bp
    from .almox import almox_bp
    from .geral import geral_bp
    from .notinhas import notinhas_bp
    from .relatorios import relatorios_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(sol_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(almox_bp)
    app.register_blueprint(geral_bp)
    app.register_blueprint(notinhas_bp)
    app.register_blueprint(relatorios_bp)

    @app.route("/uploads/<path:nome>")
    def uploads(nome):
        return send_from_directory(app.config["UPLOAD_FOLDER"], nome)

    from flask import redirect, abort
    from .models import STATUS, STATUS_LABEL, Solicitacao

    @app.errorhandler(413)
    def _upload_grande(e):
        # Substitui a tela crua "Request Entity Too Large" por um aviso claro.
        from flask import request, redirect, flash, url_for
        limite_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        flash(f"Os arquivos enviados passaram do limite de {limite_mb} MB por envio. "
              f"Envie menos fotos de uma vez (ou fotos menores) e tente novamente.", "warning")
        # volta para a tela de onde veio, se der; senão para o início
        destino = request.referrer or url_for("auth.index")
        return redirect(destino), 303

    @app.route("/r/<int:sid>")
    def link_curto(sid):
        s = db.session.get(Solicitacao, sid)
        if not s or not s.link_similar:
            abort(404)
        return redirect(s.link_similar)

    @app.context_processor
    def inject_status():
        ctx = {"STATUS": STATUS, "STATUS_LABEL": STATUS_LABEL}
        from flask_login import current_user
        if current_user.is_authenticated and current_user.is_admin:
            ctx["n_aprovacoes"] = Solicitacao.query.filter_by(status="AGUARDANDO_APROVACAO").count()
            ctx["n_cotacao"] = Solicitacao.query.filter_by(status="AGUARDANDO_ENVIO_COTACAO").count()
            # item 150: cadastros (fornecedores/empresas) ativos sem CNPJ = precisam ser completados
            from .models import Fornecedor
            try:
                ctx["n_cadastros_incompletos"] = (Fornecedor.query
                    .filter(Fornecedor.ativo.is_(True))
                    .filter((Fornecedor.cnpj.is_(None)) | (Fornecedor.cnpj == ""))
                    .count())
            except Exception:
                ctx["n_cadastros_incompletos"] = 0
        return ctx

    with app.app_context():
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        db.create_all()
        _light_migrate()
        _seed_tipos()

    return app
