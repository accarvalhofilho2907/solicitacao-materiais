"""SIGA / Facilities — motor genérico de checklist e inspeção (02 · Facilities).

Só o Admin/Master cria e edita MODELOS de checklist (o "desenho" do formulário).
Qualquer pessoa com acesso pode EXECUTAR um checklist num equipamento (a resposta).
A regra de bloqueio (Impeditivo / Atenção / Temporário com promoção automática por
prazo) está descrita em detalhe nos comentários de app/models.py, junto aos modelos.
"""
import json
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user

from .extensions import db
from .models import (ModeloChecklist, ItemChecklist, TipoEquipamento, Equipamento,
                     ExecucaoChecklist, ItemFalhaAberta, Planta, Colaborador,
                     AtividadeProgramada, RelatorioAtividade)

facilities_bp = Blueprint("facilities", __name__, url_prefix="/facilities")


def _promover_falhas_vencidas():
    """[Regra de negócio definida por Antonio] Varre ItemFalhaAberta com status='ATENCAO' cujo
    prazo_final já passou (tempo corrido, independente de nova inspeção) e promove para
    status='IMPEDITIVO'. Chamada no início das rotas que listam/exibem equipamentos e checklist,
    como uma verificação "preguiçosa" (lazy) — não depende de um cron job configurado no Render,
    que o plano atual não tem. Idempotente e barata (só grava o que de fato mudou)."""
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
    """Criar/editar MODELOS e TIPOS: Admin sempre pode; um Colaborador só se tiver a tarefa
    fac_gerir_modelos explicitamente liberada no papel (delegação pontual, granular)."""
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
    """Ver a lista de equipamentos: Admin sempre pode; Colaborador precisa de fac_ver
    (ou qualquer tarefa do grupo Facilities, que já implica acesso de leitura)."""
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
    """Executar (responder) um checklist: Admin sempre pode; Colaborador precisa da tarefa
    granular fac_inspecionar especificamente (ver a lista não implica poder inspecionar)."""
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


def _cadastrar_equip_required(f):
    """Cadastrar um Equipamento novo: Admin sempre pode; Colaborador precisa da tarefa
    fac_cadastrar_equipamento."""
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if current_user.is_authenticated and getattr(current_user, "is_admin", False):
            return f(*a, **k)
        colab = _colab_sessao()
        if colab and getattr(colab, "pode_facilities_cadastrar", False):
            return f(*a, **k)
        if not current_user.is_authenticated and not colab:
            return redirect(url_for("auth.login"))
        abort(403)
    return w


def _quem_executou():
    """(usuario_id, colaborador_id) — só um dos dois preenchido, conforme quem está agindo."""
    from .almox import _colab_sessao
    if current_user.is_authenticated:
        return current_user.id, None
    colab = _colab_sessao()
    return None, (colab.id if colab else None)


def _plantas_ctx():
    from .almox import _plantas_para_cadastro, _plantas_permitidas_ids
    return _plantas_para_cadastro(), _plantas_permitidas_ids()


# ============================================================================
# MODELOS DE CHECKLIST (Admin/Master)
# ============================================================================

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
                             criado_por=current_user.id)
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
    """Lê os itens enviados pelo form (arrays paralelos: item_texto[], item_tipo[],
    item_prazo[]) e grava como ItemChecklist. Se substituir=True, apaga os itens
    antigos antes (edição completa do modelo)."""
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
                prazo = 7  # default de segurança se o admin esquecer de preencher
        db.session.add(ItemChecklist(modelo_id=modelo.id, texto=texto, tipo=tipo,
                                     prazo_dias=prazo, ordem=i))
    db.session.commit()


# ============================================================================
# TIPOS DE EQUIPAMENTO (Admin/Master)
# ============================================================================

@facilities_bp.route("/tipos", methods=["GET", "POST"])
@_gerir_required
def tipos():
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        modelo_id = request.form.get("modelo_checklist_id") or None
        if not nome:
            flash("Informe o nome do tipo.", "danger")
        elif TipoEquipamento.query.filter(db.func.upper(TipoEquipamento.nome) == nome.upper()).first():
            flash("Já existe um tipo de equipamento com esse nome.", "warning")
        else:
            db.session.add(TipoEquipamento(nome=nome, modelo_checklist_id=int(modelo_id) if modelo_id else None))
            db.session.commit()
            flash("Tipo de equipamento cadastrado.", "success")
        return redirect(url_for("facilities.tipos"))
    itens = TipoEquipamento.query.order_by(TipoEquipamento.nome).all()
    modelos_disp = ModeloChecklist.query.filter_by(ativo=True).order_by(ModeloChecklist.nome).all()
    return render_template("facilities/tipos.html", itens=itens, modelos_disp=modelos_disp)


# ============================================================================
# EQUIPAMENTOS
# ============================================================================

@facilities_bp.route("/equipamentos", methods=["GET", "POST"])
@_ver_required
def equipamentos():
    _promover_falhas_vencidas()
    plantas_disp, ids_permitidas = _plantas_ctx()
    if request.method == "POST":
        from .almox import _colab_sessao
        pode_cadastrar = getattr(current_user, "is_admin", False) or getattr(_colab_sessao(), "pode_facilities_cadastrar", False)
        if not pode_cadastrar:
            abort(403)
        nome = (request.form.get("nome") or "").strip()
        tipo_id = request.form.get("tipo_id")
        planta_id = request.form.get("planta_id") or None
        if not nome or not tipo_id:
            flash("Informe nome e tipo do equipamento.", "danger")
        else:
            if planta_id:
                ids_ok = {p.id for p in plantas_disp}
                if int(planta_id) not in ids_ok:
                    planta_id = None
            import secrets
            uid = "EQ-" + secrets.token_hex(4).upper()
            while Equipamento.query.filter_by(qr_uid=uid).first():
                uid = "EQ-" + secrets.token_hex(4).upper()
            db.session.add(Equipamento(nome=nome, codigo=(request.form.get("codigo") or "").strip(),
                                       tipo_id=int(tipo_id), planta_id=int(planta_id) if planta_id else None,
                                       local=(request.form.get("local") or "").strip(), qr_uid=uid))
            db.session.commit()
            flash("Equipamento cadastrado.", "success")
        return redirect(url_for("facilities.equipamentos"))

    q = Equipamento.query.filter_by(ativo=True)
    if ids_permitidas:
        q = q.filter(db.or_(Equipamento.planta_id.in_(ids_permitidas), Equipamento.planta_id.is_(None)))
    itens = q.order_by(Equipamento.nome).all()
    tipos_disp = TipoEquipamento.query.filter_by(ativo=True).order_by(TipoEquipamento.nome).all()
    return render_template("facilities/equipamentos.html", itens=itens, tipos_disp=tipos_disp,
                           plantas_disp=plantas_disp)


# ============================================================================
# EXECUÇÃO DO CHECKLIST
# ============================================================================

@facilities_bp.route("/equipamentos/<int:eid>/inspecionar", methods=["GET", "POST"])
@_inspecionar_required
def inspecionar(eid):
    _promover_falhas_vencidas()
    equipamento = db.session.get(Equipamento, eid) or abort(404)
    modelo = equipamento.modelo_checklist
    if not modelo:
        flash("Este equipamento não tem um modelo de checklist vinculado.", "danger")
        return redirect(url_for("facilities.equipamentos"))

    # Falhas TEMPORARIO já abertas para este equipamento, indexadas por item — usado tanto
    # para exibir "há X dias em aberto" quanto para decidir se já virou IMPEDITIVO.
    falhas_abertas = {f.item_checklist_id: f for f in
                      ItemFalhaAberta.query.filter_by(equipamento_id=equipamento.id)
                      .filter(ItemFalhaAberta.status.in_(["ATENCAO", "IMPEDITIVO"])).all()}

    if request.method == "GET":
        return render_template("facilities/inspecionar.html", equipamento=equipamento, modelo=modelo,
                               falhas_abertas=falhas_abertas, hoje=date.today())

    # POST: processa as respostas. Convenção do form: resposta_<item_id> = 'ok' | 'falha'
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
                    db.session.add(ItemFalhaAberta(equipamento_id=equipamento.id, item_checklist_id=item.id,
                                                   prazo_final=prazo_final, status="ATENCAO"))
                # se já existia e já foi promovida a IMPEDITIVO (prazo vencido), bloqueia agora
                elif falha_existente.status == "IMPEDITIVO":
                    tem_impeditivo_bloqueando = True
            # ATENCAO comum: não bloqueia, não abre "relógio" (não tem prazo a vencer)
        else:
            # resp == 'ok': se havia uma falha aberta (TEMPORARIO) para este item, resolve
            if falha_existente and falha_existente.status in ("ATENCAO", "IMPEDITIVO"):
                falha_existente.status = "RESOLVIDO"
                falha_existente.resolvido_em = datetime.utcnow()

    if tem_impeditivo_bloqueando:
        db.session.rollback()
        flash("Checklist NÃO gerado: há item(ns) impeditivo(s) reprovado(s). Resolva antes de continuar.", "danger")
        return redirect(url_for("facilities.inspecionar", eid=eid))

    resultado = "OK"
    if any(v == "falha" for v in respostas.values()):
        resultado = "ATENCAO"
    execucao = ExecucaoChecklist(equipamento_id=equipamento.id, modelo_id=modelo.id,
                                 executado_por_usuario_id=usuario_id,
                                 executado_por_colaborador_id=colaborador_id,
                                 resultado_geral=resultado,
                                 respostas_json=json.dumps(respostas),
                                 observacoes=(request.form.get("observacoes") or "").strip())
    db.session.add(execucao)
    db.session.commit()
    flash("Checklist registrado.", "success")
    return redirect(url_for("facilities.equipamentos"))


# ============================================================================
# PROGRAMAÇÃO DE ATIVIDADES ("Rotina" — agenda simples, sem recorrência por ora)
# ============================================================================

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
        equipamento_id = request.form.get("equipamento_id") or None
        responsavel_texto = (request.form.get("responsavel_texto") or "").strip()
        db.session.add(AtividadeProgramada(
            titulo=titulo, descricao=(request.form.get("descricao") or "").strip(),
            data_prevista=data_d, planta_id=int(planta_id) if planta_id else None,
            equipamento_id=int(equipamento_id) if equipamento_id else None,
            responsavel_texto=responsavel_texto or None,
            criado_por=current_user.id if current_user.is_authenticated else None))
        db.session.commit()
        flash("Atividade programada.", "success")
        return redirect(url_for("facilities.programacao"))

    q = AtividadeProgramada.query.filter(AtividadeProgramada.status == "PENDENTE")
    if ids_permitidas:
        q = q.filter(db.or_(AtividadeProgramada.planta_id.in_(ids_permitidas), AtividadeProgramada.planta_id.is_(None)))
    itens = q.order_by(AtividadeProgramada.data_prevista).all()
    equipamentos_disp = Equipamento.query.filter_by(ativo=True).order_by(Equipamento.nome).all()
    return render_template("facilities/programacao.html", itens=itens, plantas_disp=plantas_disp,
                           equipamentos_disp=equipamentos_disp, hoje=date.today())


@facilities_bp.route("/programacao/<int:aid>/concluir", methods=["POST"])
@_inspecionar_required
def programacao_concluir(aid):
    """Marca a atividade programada como concluída, sem exigir um Relatório de Atividade
    junto (a pessoa pode preferir só registrar o relatório separadamente, ou os dois)."""
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


# ============================================================================
# RELATÓRIO DE ATIVIDADES (execução — o que de fato aconteceu)
# ============================================================================

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
        equipamento_id = request.form.get("equipamento_id") or None
        atividade_id = request.form.get("atividade_programada_id") or None
        usuario_id, colaborador_id = _quem_executou()
        rel = RelatorioAtividade(
            titulo=titulo, descricao=(request.form.get("descricao") or "").strip(),
            planta_id=int(planta_id) if planta_id else None,
            equipamento_id=int(equipamento_id) if equipamento_id else None,
            atividade_programada_id=int(atividade_id) if atividade_id else None,
            executado_por_usuario_id=usuario_id, executado_por_colaborador_id=colaborador_id)
        db.session.add(rel)
        # se veio de uma atividade programada, fecha o ciclo (marca como concluída também)
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
    equipamentos_disp = Equipamento.query.filter_by(ativo=True).order_by(Equipamento.nome).all()
    pendentes_disp = (AtividadeProgramada.query.filter_by(status="PENDENTE")
                      .order_by(AtividadeProgramada.data_prevista).all())
    return render_template("facilities/relatorio_atividades.html", itens=itens, plantas_disp=plantas_disp,
                           equipamentos_disp=equipamentos_disp, pendentes_disp=pendentes_disp)
