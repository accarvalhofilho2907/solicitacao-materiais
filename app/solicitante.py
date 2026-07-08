from flask import (
    Blueprint, render_template, redirect, url_for, request, flash, abort, current_app, Response
)
from flask_login import login_required, current_user

from .extensions import db
from datetime import datetime
from .models import (Solicitacao, TipoMaterial, Imagem, Comentario, LogSolicitacao,
                    Usuario, Fornecedor, Orcamento, UNIDADES_MEDIDA)
from .storage import salvar_imagem
from .emails import enviar_email
from .pdf import gerar_pdf_lista

sol_bp = Blueprint("solicitante", __name__, url_prefix="/solicitante")


@sol_bp.route("/")
@login_required
def index():
    # Painel de visualização livre: todos veem todas (filtros avançados como o admin)
    q = Solicitacao.query
    f_status = request.args.getlist("status")
    f_sol = request.args.getlist("solicitante")
    f_forn = request.args.getlist("fornecedor")
    f_tipo = request.args.get("tipo")
    f_busca = (request.args.get("q") or "").strip()
    f_de = request.args.get("de")
    f_ate = request.args.get("ate")
    if f_status:
        q = q.filter(Solicitacao.status.in_(f_status))
    if f_sol:
        q = q.filter(Solicitacao.solicitante_id.in_([int(x) for x in f_sol]))
    if f_forn:
        ids = [int(x) for x in f_forn]
        sub = db.session.query(Orcamento.solicitacao_id).filter(Orcamento.fornecedor_id.in_(ids))
        q = q.filter(db.or_(Solicitacao.fornecedor_definido_id.in_(ids), Solicitacao.id.in_(sub)))
    if f_tipo:
        q = q.filter_by(tipo_material_id=int(f_tipo))
    if f_busca:
        q = q.filter(Solicitacao.material.ilike(f"%{f_busca}%"))
    if f_de:
        q = q.filter(Solicitacao.criado_em >= datetime.strptime(f_de, "%Y-%m-%d"))
    if f_ate:
        q = q.filter(Solicitacao.criado_em <= datetime.strptime(f_ate, "%Y-%m-%d").replace(hour=23, minute=59))
    pedidos = q.order_by(Solicitacao.atualizado_em.desc()).all()
    pode_criar = current_user.is_admin or current_user.pode_solicitar
    return render_template("solicitante/index.html", pedidos=pedidos,
        tipos=TipoMaterial.query.filter_by(ativo=True).order_by(TipoMaterial.nome).all(),
        solicitantes=Usuario.query.filter(Usuario.papel.in_(["solicitante", "almoxarifado"])).order_by(Usuario.nome).all(),
        fornecedores=Fornecedor.query.order_by(Fornecedor.nome_fantasia).all(),
        f_status=f_status, f_sol=[int(x) for x in f_sol], f_forn=[int(x) for x in f_forn],
        f_tipo=f_tipo, f_busca=f_busca, f_de=f_de, f_ate=f_ate, pode_criar=pode_criar)


@sol_bp.route("/nova", methods=["GET", "POST"])
@login_required
def nova():
    if not (current_user.is_admin or current_user.pode_solicitar):
        abort(403)
    tipos = TipoMaterial.query.filter_by(ativo=True).order_by(TipoMaterial.nome).all()
    if request.method == "POST":
        s = Solicitacao(
            solicitante_id=current_user.id,
            tipo_material_id=request.form.get("tipo_material_id") or None,
            material=request.form.get("material", "").strip(),
            quantidade=int(request.form.get("quantidade") or 1),
            unidade_medida=request.form.get("unidade_medida") or None,
            fabricante=request.form.get("fabricante", "").strip(),
            link_similar=request.form.get("link_similar", "").strip(),
            local_servico=request.form.get("local_servico", "").strip(),
            status="AGUARDANDO_APROVACAO",
        )
        if not s.material:
            flash("Informe o material.", "danger")
            return render_template("solicitante/nova.html", tipos=tipos, unidades=UNIDADES_MEDIDA)
        db.session.add(s)
        db.session.flush()
        for f in request.files.getlist("imagens"):
            url = salvar_imagem(f)
            if url:
                db.session.add(Imagem(solicitacao_id=s.id, url=url))
        db.session.add(LogSolicitacao(solicitacao_id=s.id, autor_id=current_user.id,
                                      evento="Solicitação criada (aguardando aprovação)"))
        db.session.commit()
        enviar_email(current_app.config.get("ADMIN_EMAIL"),
                     f"Nova solicitação Nº {s.id} (aguardando aprovação)",
                     f"{current_user.nome} abriu a solicitação Nº {s.id}: {s.material} (qtd {s.quantidade}).")
        flash("Solicitação enviada. Ficará 'Aguardando aprovação' até o administrador aprovar.", "success")
        return redirect(url_for("solicitante.detalhe", sid=s.id))
    return render_template("solicitante/nova.html", tipos=tipos, unidades=UNIDADES_MEDIDA)


@sol_bp.route("/solicitacao/<int:sid>", methods=["GET", "POST"])
@login_required
def detalhe(sid):
    s = db.session.get(Solicitacao, sid)
    if not s:
        abort(404)
    pode_comentar = current_user.is_admin or current_user.pode_solicitar
    if request.method == "POST":
        if not pode_comentar:
            abort(403)
        texto = request.form.get("texto", "").strip()
        if texto:
            db.session.add(Comentario(solicitacao_id=s.id, autor_id=current_user.id, texto=texto))
            db.session.commit()
            enviar_email(current_app.config.get("ADMIN_EMAIL"),
                         f"Resposta na solicitação Nº {s.id}",
                         f"{current_user.nome} respondeu na solicitação Nº {s.id}.\n{texto}")
            flash("Comentário enviado.", "success")
        return redirect(url_for("solicitante.detalhe", sid=s.id))
    pode_criar = current_user.is_admin or current_user.pode_solicitar
    voltar = request.args.get("voltar", "")
    voltar_url = url_for("solicitante.index") + (("?" + voltar) if voltar else "")
    return render_template("solicitante/detalhe.html", s=s, leitura=not pode_comentar,
                           pode_criar=pode_criar, voltar_url=voltar_url)


@sol_bp.route("/exportar", methods=["POST"])
@login_required
def exportar():
    ids = request.form.getlist("ids")
    itens = Solicitacao.query.filter(Solicitacao.id.in_(ids)).order_by(Solicitacao.id).all()
    if not itens:
        flash("Selecione ao menos uma solicitação para exportar.", "warning")
        return redirect(request.referrer or url_for("solicitante.index"))
    pdf = gerar_pdf_lista(itens)
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=solicitacoes.pdf"})
