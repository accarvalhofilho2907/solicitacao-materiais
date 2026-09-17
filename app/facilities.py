"""SIGA / Facilities — motor genérico de checklist e inspeção.

[M2] O checklist roda sobre itens de MATERIAL (ProdutoAlmox) já existentes no sistema,
de forma genérica por tipo (sem diferenciar unidade física). Não há vínculo fixo entre
um item de material e um modelo de checklist: na hora de executar, a pessoa escolhe
livremente QUAL material está inspecionando e QUAL modelo de checklist usar. O próprio
modelo comporta um "cabeçalho" de dados livres (marca, nº de série, etc.), guardado em
ExecucaoChecklist.cabecalho_json, sem travar nada no cadastro do material.

Só o Admin/Master (ou quem tiver a tarefa fac_gerir_modelos) cria e edita MODELOS de
checklist. A regra de bloqueio (Impeditivo / Atenção / Temporário com promoção automática
por prazo) está descrita em detalhe nos comentários de app/models.py, junto aos modelos.
"""
import json
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user

from .extensions import db
from .models import (ModeloChecklist, ItemChecklist, ProdutoAlmox, ExecucaoChecklist,
                     ItemFalhaAberta, Planta, Colaborador, AtividadeProgramada,
                     RelatorioAtividade, RelatorioDiarioObra)

facilities_bp = Blueprint("facilities", __name__, url_prefix="/facilities")


def _promover_falhas_vencidas():
    try:
        vencidas = (ItemFalhaAberta.query
                   .filter(ItemFalhaAberta.status == "ATENCAO",
                          ItemFalhaAberta.prazo_final.isnot(None),
                          ItemFalhaAberta.prazo_final < date.today())
                   .all())
        for f in vencidas:
            f.status = "IMPEDITIVO"
            f.promovido_em = datetime.utcnow()
        if vencidas:
            db.session.commit()
    except Exception:
        db.session.rollback()


def _gerir_required(f):
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if current_user.is_authenticated and getattr(current_user, "is_admin", False):
            return f(*a, **k)
        colab = _colab_sessao()
        if colab and getattr(colab, "pode_facilities_gerir", False):
            return f(*a, **k)
        if not current_user.is_authenticated and not colab:
            return redirect(url_for("auth.login"))
        abort(403)
    return w


def _ver_required(f):
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if current_user.is_authenticated and getattr(current_user, "is_admin", False):
            return f(*a, **k)
        colab = _colab_sessao()
        if colab and getattr(colab, "pode_facilities", False):
            return f(*a, **k)
        if not current_user.is_authenticated and not colab:
            return redirect(url_for("auth.login"))
        abort(403)
    return w


def _inspecionar_required(f):
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if current_user.is_authenticated and getattr(current_user, "is_admin", False):
            return f(*a, **k)
        colab = _colab_sessao()
        if colab and getattr(colab, "pode_facilities_inspecionar", False):
            return f(*a, **k)
        if not current_user.is_authenticated and not colab:
            return redirect(url_for("auth.login"))
        abort(403)
    return w


def _quem_executou():
    from .almox import _colab_sessao
    if current_user.is_authenticated:
        return current_user.id, None
    colab = _colab_sessao()
    return None, (colab.id if colab else None)


def _plantas_ctx():
    from .almox import _plantas_para_cadastro, _plantas_permitidas_ids
    return _plantas_para_cadastro(), _plantas_permitidas_ids()


def _materiais_disp(ids_permitidas):
    q = ProdutoAlmox.query.filter_by(ativo=True)
    if ids_permitidas:
        q = q.filter(db.or_(ProdutoAlmox.planta_id.in_(ids_permitidas), ProdutoAlmox.planta_id.is_(None)))
    return q.order_by(ProdutoAlmox.nome).all()


@facilities_bp.route("/modelos")
@_gerir_required
def modelos():
    itens = ModeloChecklist.query.order_by(ModeloChecklist.nome).all()
    return render_template("facilities/modelos.html", itens=itens)


@facilities_bp.route("/modelos/novo", methods=["GET", "POST"])
@_gerir_required
def modelo_novo():
    if request.method == "GET":
        return render_template("facilities/modelo_form.html", modelo=None)
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do modelo.", "danger")
        return redirect(url_for("facilities.modelo_novo"))
    modelo = ModeloChecklist(nome=nome, descricao=(request.form.get("descricao") or "").strip(),
                             criado_por=current_user.id if current_user.is_authenticated else None)
    db.session.add(modelo)
    db.session.commit()
    _salvar_itens_do_form(modelo, request.form)
    flash("Modelo de checklist criado.", "success")
    return redirect(url_for("facilities.modelos"))


@facilities_bp.route("/modelos/<int:mid>/editar", methods=["GET", "POST"])
@_gerir_required
def modelo_editar(mid):
    modelo = db.session.get(ModeloChecklist, mid) or abort(404)
    if request.method == "GET":
        return render_template("facilities/modelo_form.html", modelo=modelo)
    modelo.nome = (request.form.get("nome") or modelo.nome).strip()
    modelo.descricao = (request.form.get("descricao") or "").strip()
    _salvar_itens_do_form(modelo, request.form, substituir=True)
    db.session.commit()
    flash("Modelo atualizado.", "success")
    return redirect(url_for("facilities.modelos"))


def _salvar_itens_do_form(modelo, form, substituir=False):
    if substituir:
        ItemChecklist.query.filter_by(modelo_id=modelo.id).delete()
    textos = request.form.getlist("item_texto")
    tipos = request.form.getlist("item_tipo")
    prazos = request.form.getlist("item_prazo")
    for i, texto in enumerate(textos):
        texto = (texto or "").strip()
        if not texto:
            continue
        tipo = tipos[i] if i < len(tipos) else "ATENCAO"
        if tipo not in ("IMPEDITIVO", "ATENCAO", "TEMPORARIO"):
            tipo = "ATENCAO"
        prazo = None
        if tipo == "TEMPORARIO":
            try:
                prazo = int(prazos[i]) if i < len(prazos) and prazos[i] else None
            except (ValueError, IndexError):
                prazo = None
            if not prazo or prazo < 1:
                prazo = 7
        db.session.add(ItemChecklist(modelo_id=modelo.id, texto=texto, tipo=tipo,
                                     prazo_dias=prazo, ordem=i))
    db.session.commit()


@facilities_bp.route("/inspecionar", methods=["GET", "POST"])
@_inspecionar_required
def inspecionar():
    _promover_falhas_vencidas()
    plantas_disp, ids_permitidas = _plantas_ctx()

    if request.method == "GET":
        produto_id = request.args.get("produto_id")
        modelo_id = request.args.get("modelo_id")
        if not produto_id or not modelo_id:
            materiais = _materiais_disp(ids_permitidas)
            modelos_disp = ModeloChecklist.query.filter_by(ativo=True).order_by(ModeloChecklist.nome).all()
            return render_template("facilities/inspecionar_escolher.html",
                                   materiais=materiais, modelos_disp=modelos_disp)
        produto = db.session.get(ProdutoAlmox, int(produto_id)) or abort(404)
        modelo = db.session.get(ModeloChecklist, int(modelo_id)) or abort(404)
        falhas_abertas = {f.item_checklist_id: f for f in
                          ItemFalhaAberta.query.filter_by(produto_id=produto.id)
                          .filter(ItemFalhaAberta.status.in_(["ATENCAO", "IMPEDITIVO"])).all()}
        return render_template("facilities/inspecionar.html", produto=produto, modelo=modelo,
                               falhas_abertas=falhas_abertas, hoje=date.today())

    produto_id = int(request.form.get("produto_id"))
    modelo_id = int(request.form.get("modelo_id"))
    produto = db.session.get(ProdutoAlmox, produto_id) or abort(404)
    modelo = db.session.get(ModeloChecklist, modelo_id) or abort(404)

    falhas_abertas = {f.item_checklist_id: f for f in
                      ItemFalhaAberta.query.filter_by(produto_id=produto.id)
                      .filter(ItemFalhaAberta.status.in_(["ATENCAO", "IMPEDITIVO"])).all()}

    usuario_id, colaborador_id = _quem_executou()
    tem_impeditivo_bloqueando = False
    respostas = {}
    for item in modelo.itens:
        resp = request.form.get(f"resposta_{item.id}")
        respostas[item.id] = resp
        falha_existente = falhas_abertas.get(item.id)

        if resp == "falha":
            if item.tipo == "IMPEDITIVO":
                tem_impeditivo_bloqueando = True
            elif item.tipo == "TEMPORARIO":
                if not falha_existente:
                    prazo_final = date.today() + timedelta(days=item.prazo_dias or 7)
                    db.session.add(ItemFalhaAberta(produto_id=produto.id, item_checklist_id=item.id,
                                                   prazo_final=prazo_final, status="ATENCAO"))
                elif falha_existente.status == "IMPEDITIVO":
                    tem_impeditivo_bloqueando = True
        else:
            if falha_existente and falha_existente.status in ("ATENCAO", "IMPEDITIVO"):
                falha_existente.status = "RESOLVIDO"
                falha_existente.resolvido_em = datetime.utcnow()

    if tem_impeditivo_bloqueando:
        db.session.rollback()
        flash("Checklist NÃO gerado: há item(ns) impeditivo(s) reprovado(s). Resolva antes de continuar.", "danger")
        return redirect(url_for("facilities.inspecionar", produto_id=produto_id, modelo_id=modelo_id))

    cabecalho = {k[len("cab_"):]: v for k, v in request.form.items() if k.startswith("cab_") and v}
    resultado = "OK"
    if any(v == "falha" for v in respostas.values()):
        resultado = "ATENCAO"
    execucao = ExecucaoChecklist(produto_id=produto.id, modelo_id=modelo.id,
                                 planta_id=produto.planta_id,
                                 executado_por_usuario_id=usuario_id,
                                 executado_por_colaborador_id=colaborador_id,
                                 resultado_geral=resultado,
                                 respostas_json=json.dumps(respostas),
                                 cabecalho_json=json.dumps(cabecalho) if cabecalho else None,
                                 observacoes=(request.form.get("observacoes") or "").strip())
    db.session.add(execucao)
    db.session.commit()
    flash("Checklist registrado.", "success")
    return redirect(url_for("facilities.inspecionar"))


@facilities_bp.route("/programacao", methods=["GET", "POST"])
@_ver_required
def programacao():
    plantas_disp, ids_permitidas = _plantas_ctx()
    if request.method == "POST":
        from .almox import _colab_sessao
        pode_criar = getattr(current_user, "is_admin", False) or getattr(_colab_sessao(), "pode_facilities_inspecionar", False)
        if not pode_criar:
            abort(403)
        titulo = (request.form.get("titulo") or "").strip()
        data_prevista = request.form.get("data_prevista")
        if not titulo or not data_prevista:
            flash("Informe título e data prevista.", "danger")
            return redirect(url_for("facilities.programacao"))
        try:
            data_d = datetime.strptime(data_prevista, "%Y-%m-%d").date()
        except ValueError:
            flash("Data inválida.", "danger")
            return redirect(url_for("facilities.programacao"))
        planta_id = request.form.get("planta_id") or None
        if planta_id:
            ids_ok = {p.id for p in plantas_disp}
            if int(planta_id) not in ids_ok:
                planta_id = None
        produto_id = request.form.get("produto_id") or None
        responsavel_texto = (request.form.get("responsavel_texto") or "").strip()
        db.session.add(AtividadeProgramada(
            titulo=titulo, descricao=(request.form.get("descricao") or "").strip(),
            data_prevista=data_d, planta_id=int(planta_id) if planta_id else None,
            produto_id=int(produto_id) if produto_id else None,
            responsavel_texto=responsavel_texto or None,
            criado_por=current_user.id if current_user.is_authenticated else None))
        db.session.commit()
        flash("Atividade programada.", "success")
        return redirect(url_for("facilities.programacao"))

    q = AtividadeProgramada.query.filter(AtividadeProgramada.status == "PENDENTE")
    if ids_permitidas:
        q = q.filter(db.or_(AtividadeProgramada.planta_id.in_(ids_permitidas), AtividadeProgramada.planta_id.is_(None)))
    itens = q.order_by(AtividadeProgramada.data_prevista).all()
    materiais_disp = _materiais_disp(ids_permitidas)
    return render_template("facilities/programacao.html", itens=itens, plantas_disp=plantas_disp,
                           materiais_disp=materiais_disp, hoje=date.today())


@facilities_bp.route("/programacao/<int:aid>/concluir", methods=["POST"])
@_inspecionar_required
def programacao_concluir(aid):
    a = db.session.get(AtividadeProgramada, aid) or abort(404)
    a.status = "CONCLUIDA"
    db.session.commit()
    flash("Atividade marcada como concluída.", "success")
    return redirect(url_for("facilities.programacao"))


@facilities_bp.route("/programacao/<int:aid>/cancelar", methods=["POST"])
@_gerir_required
def programacao_cancelar(aid):
    a = db.session.get(AtividadeProgramada, aid) or abort(404)
    a.status = "CANCELADA"
    db.session.commit()
    flash("Atividade cancelada.", "success")
    return redirect(url_for("facilities.programacao"))


@facilities_bp.route("/relatorio-atividades", methods=["GET", "POST"])
@_ver_required
def relatorio_atividades():
    plantas_disp, ids_permitidas = _plantas_ctx()
    if request.method == "POST":
        from .almox import _colab_sessao
        pode_criar = getattr(current_user, "is_admin", False) or getattr(_colab_sessao(), "pode_facilities_inspecionar", False)
        if not pode_criar:
            abort(403)
        titulo = (request.form.get("titulo") or "").strip()
        if not titulo:
            flash("Informe um título para o relatório.", "danger")
            return redirect(url_for("facilities.relatorio_atividades"))
        planta_id = request.form.get("planta_id") or None
        if planta_id:
            ids_ok = {p.id for p in plantas_disp}
            if int(planta_id) not in ids_ok:
                planta_id = None
        produto_id = request.form.get("produto_id") or None
        atividade_id = request.form.get("atividade_programada_id") or None
        usuario_id, colaborador_id = _quem_executou()
        rel = RelatorioAtividade(
            titulo=titulo, descricao=(request.form.get("descricao") or "").strip(),
            planta_id=int(planta_id) if planta_id else None,
            produto_id=int(produto_id) if produto_id else None,
            atividade_programada_id=int(atividade_id) if atividade_id else None,
            executado_por_usuario_id=usuario_id, executado_por_colaborador_id=colaborador_id)
        db.session.add(rel)
        if atividade_id:
            ap = db.session.get(AtividadeProgramada, int(atividade_id))
            if ap and ap.status == "PENDENTE":
                ap.status = "CONCLUIDA"
        db.session.commit()
        flash("Relatório de atividade registrado.", "success")
        return redirect(url_for("facilities.relatorio_atividades"))

    q = RelatorioAtividade.query
    if ids_permitidas:
        q = q.filter(db.or_(RelatorioAtividade.planta_id.in_(ids_permitidas), RelatorioAtividade.planta_id.is_(None)))
    itens = q.order_by(RelatorioAtividade.executado_em.desc()).limit(100).all()
    materiais_disp = _materiais_disp(ids_permitidas)
    pendentes_disp = (AtividadeProgramada.query.filter_by(status="PENDENTE")
                      .order_by(AtividadeProgramada.data_prevista).all())
    return render_template("facilities/relatorio_atividades.html", itens=itens, plantas_disp=plantas_disp,
                           materiais_disp=materiais_disp, pendentes_disp=pendentes_disp)


@facilities_bp.route("/rdo", methods=["GET", "POST"])
@_ver_required
def rdo():
    plantas_disp, ids_permitidas = _plantas_ctx()
    if request.method == "POST":
        from .almox import _colab_sessao
        pode_criar = getattr(current_user, "is_admin", False) or getattr(_colab_sessao(), "pode_facilities_inspecionar", False)
        if not pode_criar:
            abort(403)
        data_str = request.form.get("data")
        if not data_str:
            flash("Informe a data do RDO.", "danger")
            return redirect(url_for("facilities.rdo"))
        try:
            data_d = datetime.strptime(data_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Data inválida.", "danger")
            return redirect(url_for("facilities.rdo"))
        planta_id = request.form.get("planta_id") or None
        if planta_id:
            ids_ok = {p.id for p in plantas_disp}
            if int(planta_id) not in ids_ok:
                planta_id = None
        atividades_ids = request.form.getlist("atividades_ids")
        db.session.add(RelatorioDiarioObra(
            data=data_d, planta_id=int(planta_id) if planta_id else None,
            condicao_climatica=(request.form.get("condicao_climatica") or "").strip(),
            mao_de_obra_texto=(request.form.get("mao_de_obra_texto") or "").strip(),
            equipamentos_texto=(request.form.get("equipamentos_texto") or "").strip(),
            atividades_ids_json=json.dumps([int(x) for x in atividades_ids if x.isdigit()]),
            observacoes=(request.form.get("observacoes") or "").strip(),
            criado_por=current_user.id if current_user.is_authenticated else None))
        db.session.commit()
        flash("RDO registrado.", "success")
        return redirect(url_for("facilities.rdo"))

    q = RelatorioDiarioObra.query
    if ids_permitidas:
        q = q.filter(db.or_(RelatorioDiarioObra.planta_id.in_(ids_permitidas), RelatorioDiarioObra.planta_id.is_(None)))
    itens = q.order_by(RelatorioDiarioObra.data.desc()).limit(60).all()

    hoje = date.today()
    atividades_hoje = AtividadeProgramada.query.filter(AtividadeProgramada.data_prevista == hoje).all()
    if ids_permitidas:
        atividades_hoje = [a for a in atividades_hoje
                           if a.planta_id in ids_permitidas or a.planta_id is None]
    return render_template("facilities/rdo.html", itens=itens, plantas_disp=plantas_disp,
                           atividades_hoje=atividades_hoje, hoje=hoje)
