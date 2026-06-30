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
    # Garante que o link aceite URLs longas (ex.: Mercado Livre) no PostgreSQL.
    if db.engine.dialect.name == "postgresql":
        try:
            db.session.execute(text('ALTER TABLE solicitacoes ALTER COLUMN link_similar TYPE TEXT'))
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

    app.register_blueprint(auth_bp)
    app.register_blueprint(sol_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(almox_bp)
    app.register_blueprint(geral_bp)
    app.register_blueprint(notinhas_bp)

    @app.route("/uploads/<path:nome>")
    def uploads(nome):
        return send_from_directory(app.config["UPLOAD_FOLDER"], nome)

    from flask import redirect, abort
    from .models import STATUS, STATUS_LABEL, Solicitacao

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
        return ctx

    with app.app_context():
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        db.create_all()
        _light_migrate()
        _seed_tipos()

    return app
