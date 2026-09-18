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
from .storage import salvar_imagem
from .models import (ModeloChecklist, ItemChecklist, ProdutoAlmox, ExecucaoChecklist,
                     ItemFalhaAberta, Planta, Colaborador, Fornecedor, Predio, Feriado,
                     AtividadeGrupo, AtividadeColaborador, AtividadeDia, RegistroPreenchimento,
                     EncarregadoEmpresa, RelatorioDiarioObra,
                     UNIDADES_DURACAO_DIAS_UTEIS, OPCOES_RECORRENCIA)

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


def _logado_required(f):
    """[fix] Para as telas de PREENCHER: não exige nenhuma tarefa de perfil — qualquer
    Colaborador (mesmo "Colaborador Diverso" sem tarefas de Facilities atribuídas) que esteja
    de fato participando de uma atividade pode preencher a própria %. A rota em si já filtra
    pelo colaborador certo; aqui só barra quem não está logado de jeito nenhum."""
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if current_user.is_authenticated or _colab_sessao():
            return f(*a, **k)
        return redirect(url_for("auth.login"))
    return w


def _tem_acesso_facilities(prop_generica):
    """[fix] Checa a permissão tanto para quem está logado NORMALMENTE (current_user — que
    pode ser Usuario OU Colaborador, já que Colaborador também é UserMixin e pode logar pelo
    site, não só via QR de campo) quanto para quem está numa sessão de campo via QR
    (_colab_sessao()). Antes só a segunda era checada, deixando qualquer Encarregado/
    Colaborador logado pelo site normal sempre barrado, mesmo com a tarefa certa.
    Admin e Master sempre têm acesso a tudo em Facilities."""
    from .almox import _colab_sessao
    if current_user.is_authenticated:
        if getattr(current_user, "is_admin", False) or getattr(current_user, "is_master", False):
            return True
        if getattr(current_user, prop_generica, False):
            return True
    colab = _colab_sessao()
    if colab and getattr(colab, prop_generica, False):
        return True
    return False


def _gerir_required(f):
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if _tem_acesso_facilities("pode_facilities_gerir"):
            return f(*a, **k)
        if not current_user.is_authenticated and not _colab_sessao():
            return redirect(url_for("auth.login"))
        abort(403)
    return w


def _ver_required(f):
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if _tem_acesso_facilities("pode_facilities"):
            return f(*a, **k)
        if not current_user.is_authenticated and not _colab_sessao():
            return redirect(url_for("auth.login"))
        abort(403)
    return w


def _ver_programacao_required(f):
    """[fix] A tela de PROGRAMAÇÃO GERAL (calendário/lista de TODAS as atividades) é uma
    visão de GESTÃO — não é o mesmo que "preencher a minha atividade". Um Colaborador comum
    não deveria enxergar a agenda inteira da empresa, só a própria (via /preencher). Só
    Admin/Master/Encarregado de Campo ou quem tiver a tarefa fac_ver_programacao acessam aqui."""
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if _tem_acesso_facilities("pode_ver_programacao"):
            return f(*a, **k)
        if not current_user.is_authenticated and not _colab_sessao():
            return redirect(url_for("auth.login"))
        abort(403)
    return w


def _inspecionar_required(f):
    @wraps(f)
    def w(*a, **k):
        from .almox import _colab_sessao
        if _tem_acesso_facilities("pode_facilities_inspecionar"):
            return f(*a, **k)
        if not current_user.is_authenticated and not _colab_sessao():
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
    fotos = _salvar_fotos("fotos", maximo=4)
    execucao = ExecucaoChecklist(produto_id=produto.id, modelo_id=modelo.id,
                                 planta_id=produto.planta_id,
                                 executado_por_usuario_id=usuario_id,
                                 executado_por_colaborador_id=colaborador_id,
                                 resultado_geral=resultado,
                                 respostas_json=json.dumps(respostas),
                                 cabecalho_json=json.dumps(cabecalho) if cabecalho else None,
                                 fotos_json=json.dumps(fotos) if fotos else None,
                                 observacoes=(request.form.get("observacoes") or "").strip())
    db.session.add(execucao)
    db.session.commit()
    flash("Checklist registrado.", "success")
    return redirect(url_for("facilities.inspecionar"))


def _dia_util(d):
    """True se d (date) não é sábado, domingo, nem feriado cadastrado ativo."""
    if d.weekday() >= 5:
        return False
    return Feriado.query.filter_by(data=d, ativo=True).first() is None


def _gerar_dias_uteis(data_inicio, quantidade):
    """[v3] Gera `quantidade` datas úteis a partir de data_inicio (inclusive), pulando
    sábado/domingo/feriados. Retorna lista de date, em ordem."""
    datas = []
    d = data_inicio
    while len(datas) < quantidade:
        if _dia_util(d):
            datas.append(d)
        d = d + timedelta(days=1)
    return datas


def _checar_conflito_colaborador(colaborador_id, data_inicio, datas_novas, ignorar_grupo_id=None):
    """[v3] Verifica se o colaborador já tem AtividadeDia em qualquer uma das datas da
    atividade nova (overlap por range). Retorna lista de (grupo, dias_conflitantes)."""
    ids_dia = {d for d in datas_novas}
    q = (AtividadeDia.query
         .join(AtividadeColaborador, AtividadeColaborador.grupo_id == AtividadeDia.grupo_id)
         .filter(AtividadeColaborador.colaborador_id == colaborador_id,
                 AtividadeDia.data.in_(ids_dia)))
    if ignorar_grupo_id:
        q = q.filter(AtividadeDia.grupo_id != ignorar_grupo_id)
    dias = q.all()
    if not dias:
        return None
    grupo = dias[0].grupo
    return {"grupo": grupo, "dias": [d.data for d in dias]}


def _remover_particulas_sobrenome(nome_completo):
    """[v3] Formata "Nome Sobrenome" para o resumo diário: pega o primeiro nome + o
    restante, ignorando que partículas soltas (de/da/do/dos/das) NÃO contam como o
    "corte" do sobrenome — ex.: "João da Costa Filho" -> "João da Costa" (3 palavras,
    a partícula "da" fica junto do sobrenome seguinte, não corta ali)."""
    partes = (nome_completo or "").strip().split()
    if len(partes) <= 2:
        return nome_completo
    particulas = {"de", "da", "do", "das", "dos"}
    saida = [partes[0]]
    i = 1
    while i < len(partes) and len(saida) < 3:
        saida.append(partes[i])
        if partes[i].lower() not in particulas:
            break
        i += 1
    return " ".join(saida)


def _colaboradores_disp_por_empresa(fornecedor_id):
    q = Colaborador.query.filter_by(ativo=True)
    if fornecedor_id:
        forn = db.session.get(Fornecedor, int(fornecedor_id))
        if forn:
            q = q.filter(db.func.upper(Colaborador.empresa) == (forn.nome or "").upper())
    return q.order_by(Colaborador.nome).all()


def _salvar_fotos(campo_form, maximo=4):
    """[v3] Salva até `maximo` fotos enviadas no campo `campo_form` do request (usa o mesmo
    salvar_imagem() já usado pelo resto do sistema — Cloudinary se CLOUDINARY_URL estiver
    configurado, senão cai no disco local do Render, que é volátil). Devolve uma lista de
    URLs (para gravar como JSON em fotos_json / fotos_antes_json)."""
    arquivos = request.files.getlist(campo_form)[:maximo]
    urls = []
    for arq in arquivos:
        if not arq or not arq.filename:
            continue
        url = salvar_imagem(arq)
        if url:
            urls.append(url)
    return urls


def _quem_preencheu():
    from .almox import _colab_sessao
    if current_user.is_authenticated:
        return None, current_user.id
    colab = _colab_sessao()
    return (colab.id if colab else None), None


# ============================================================================
# PRÉDIO (cadastro novo — Cadastro > Plantas, Armazéns e Localizadores)
# ============================================================================

@facilities_bp.route("/predios", methods=["GET", "POST"])
@_gerir_required
def predios():
    plantas_disp, ids_permitidas = _plantas_ctx()
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        planta_id = request.form.get("planta_id") or None
        if not nome:
            flash("Informe o nome do prédio.", "danger")
        else:
            db.session.add(Predio(nome=nome, planta_id=int(planta_id) if planta_id else None))
            db.session.commit()
            flash("Prédio cadastrado.", "success")
        return redirect(url_for("facilities.predios"))
    itens = Predio.query.filter_by(ativo=True).order_by(Predio.nome).all()
    return render_template("facilities/predios.html", itens=itens, plantas_disp=plantas_disp)


# ============================================================================
# PROGRAMAÇÃO DE ATIVIDADES v3
# ============================================================================

@facilities_bp.route("/programacao", methods=["GET"])
@_ver_programacao_required
def programacao():
    _promover_falhas_vencidas()
    plantas_disp, ids_permitidas = _plantas_ctx()

    # [fix] datas selecionadas: agora aceita MULTIPLAS (?datas=2026-09-17&datas=2026-09-18),
    # acumulando ao clicar em vez de substituir a selecao anterior.
    datas_sel_str = request.args.getlist("datas") or [request.args.get("data") or date.today().strftime("%Y-%m-%d")]
    datas_sel = []
    for s in datas_sel_str:
        try:
            datas_sel.append(datetime.strptime(s, "%Y-%m-%d").date())
        except ValueError:
            continue
    if not datas_sel:
        datas_sel = [date.today()]

    # [fix] navegação de semana INDEPENDENTE da data selecionada — offset explícito (?semana=N),
    # não mais calculado a partir do dia clicado (senão clicar num dia "pulava" a janela do calendário).
    try:
        offset_semanas = int(request.args.get("semana") or 0)
    except ValueError:
        offset_semanas = 0
    hoje = date.today()
    inicio_janela = hoje - timedelta(days=hoje.weekday()) + timedelta(weeks=offset_semanas)

    q = AtividadeDia.query.filter(AtividadeDia.data.in_(datas_sel))
    if ids_permitidas:
        q = q.join(AtividadeGrupo).filter(db.or_(AtividadeGrupo.planta_id.in_(ids_permitidas),
                                                  AtividadeGrupo.planta_id.is_(None)))
    dias = q.order_by(AtividadeDia.data, AtividadeDia.ordem).all()

    n_incompletas = AtividadeGrupo.query.filter_by(status_cadastro="INCOMPLETO").count()

    # contagem + TÍTULOS de atividades por dia, pra tooltip customizado (14 dias a partir da janela)
    contagem = {}
    for i in range(14):
        d = inicio_janela + timedelta(days=i)
        qc = AtividadeDia.query.filter_by(data=d)
        if ids_permitidas:
            qc = qc.join(AtividadeGrupo).filter(db.or_(AtividadeGrupo.planta_id.in_(ids_permitidas),
                                                        AtividadeGrupo.planta_id.is_(None)))
        titulos = [x.grupo.titulo for x in qc.all()]
        contagem[d.isoformat()] = titulos

    return render_template("facilities/programacao.html", dias=dias,
                           datas_sel=[d.isoformat() for d in datas_sel],
                           offset_semanas=offset_semanas, inicio_janela=inicio_janela,
                           fim_janela=inicio_janela + timedelta(days=13),
                           n_incompletas=n_incompletas, contagem_json=json.dumps(contagem),
                           hoje=date.today())


@facilities_bp.route("/programacao/nova", methods=["GET", "POST"])
@_ver_required
def programacao_nova():
    from .almox import _colab_sessao
    pode_criar = getattr(current_user, "is_admin", False) or getattr(_colab_sessao(), "pode_criar_atividade", False)
    if not pode_criar:
        abort(403)
    plantas_disp, ids_permitidas = _plantas_ctx()

    if request.method == "GET":
        materiais = ProdutoAlmox.query.filter_by(ativo=True).order_by(ProdutoAlmox.nome).all()
        predios_disp = Predio.query.filter_by(ativo=True).order_by(Predio.nome).all()
        empresas_disp = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome).all()
        return render_template("facilities/programacao_nova.html", plantas_disp=plantas_disp,
                               materiais=materiais, predios_disp=predios_disp, empresas_disp=empresas_disp,
                               opcoes_recorrencia=OPCOES_RECORRENCIA)

    titulo = (request.form.get("titulo") or "").strip()
    data_inicio_str = request.form.get("data_inicio")
    unidade = request.form.get("unidade_duracao") or "dias"
    if not titulo or not data_inicio_str:
        flash("Informe ao menos título e data de início (pode completar o restante depois).", "warning")
    try:
        data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%d").date() if data_inicio_str else date.today()
    except ValueError:
        data_inicio = date.today()

    duracao = UNIDADES_DURACAO_DIAS_UTEIS.get(unidade)
    if duracao is None:  # "dias" manual
        try:
            duracao = max(1, int(request.form.get("duracao_dias_uteis") or 1))
        except ValueError:
            duracao = 1

    recorrencia = request.form.get("recorrencia_dias") or None
    recorrencia = int(recorrencia) if recorrencia and recorrencia.isdigit() else None
    if recorrencia is not None and recorrencia < duracao:
        recorrencia = None  # trava de segurança: nunca aceita recorrência menor que a duração

    planta_id = request.form.get("planta_id") or None
    if planta_id:
        ids_ok = {p.id for p in plantas_disp}
        if int(planta_id) not in ids_ok:
            planta_id = None
    predio_id = request.form.get("predio_id") or None
    produto_id = request.form.get("produto_id") or None

    faltando_campo = not (titulo and data_inicio_str and planta_id and predio_id)
    fotos_antes = _salvar_fotos("fotos_antes", maximo=4)

    grupo = AtividadeGrupo(titulo=titulo or "(sem título)", descricao=(request.form.get("descricao") or "").strip(),
                           data_inicio=data_inicio, unidade_duracao=unidade, duracao_dias_uteis=duracao,
                           recorrencia_dias=recorrencia, planta_id=int(planta_id) if planta_id else None,
                           predio_id=int(predio_id) if predio_id else None,
                           produto_id=int(produto_id) if produto_id else None,
                           fotos_antes_json=json.dumps(fotos_antes) if fotos_antes else None,
                           status_cadastro="INCOMPLETO" if faltando_campo else "COMPLETO",
                           criado_por=current_user.id if current_user.is_authenticated else None)
    db.session.add(grupo)
    db.session.commit()

    # colaboradores: o PRIMEIRO da lista = responsável
    colaboradores_ids = request.form.getlist("colaborador_id")
    conflitos = []
    for i, cid in enumerate(colaboradores_ids):
        if not cid:
            continue
        cid = int(cid)
        datas_novas = _gerar_dias_uteis(data_inicio, duracao)
        conflito = _checar_conflito_colaborador(cid, data_inicio, datas_novas, ignorar_grupo_id=grupo.id)
        if conflito:
            conflitos.append({"colaborador_id": cid, "grupo_titulo": conflito["grupo"].titulo,
                              "grupo_id": conflito["grupo"].id, "dias": [d.isoformat() for d in conflito["dias"]]})
        db.session.add(AtividadeColaborador(grupo_id=grupo.id, colaborador_id=cid, eh_responsavel=(i == 0)))
    db.session.commit()

    # gera as linhas (AtividadeDia)
    datas = _gerar_dias_uteis(data_inicio, duracao)
    for i, d in enumerate(datas, start=1):
        meta = round(i / duracao * 100)
        db.session.add(AtividadeDia(grupo_id=grupo.id, data=d, ordem=i, meta_percentual=meta, status="PENDENTE"))
    db.session.commit()

    if conflitos:
        flash(f"Atividade criada, mas {len(conflitos)} colaborador(es) já têm outra atividade nesse período — "
              f"revise na tela de detalhes.", "warning")
    else:
        flash("Atividade programada e dividida em {} dia(s).".format(duracao), "success")
    return redirect(url_for("facilities.programacao"))


@facilities_bp.route("/atividade/<int:grupo_id>", methods=["GET", "POST"])
@_ver_required
def atividade_detalhe(grupo_id):
    """Tela de detalhe de uma AtividadeGrupo — Admin/Master/Encarregado de Campo veem tudo e
    podem editar QUALQUER campo (não só quando incompleta) e gerenciar colaboradores. Um
    Colaborador comum participante só vê os próprios dias e o botão de preencher a %."""
    from .almox import _colab_sessao
    grupo = db.session.get(AtividadeGrupo, grupo_id) or abort(404)
    colab = _colab_sessao()
    eh_gestor = (
        (current_user.is_authenticated and (getattr(current_user, "is_admin", False)
            or getattr(current_user, "is_master", False)
            or getattr(current_user, "eh_encarregado_campo", False)))
        or getattr(colab, "eh_encarregado_campo", False)
    )
    colab_atual_id = colab.id if colab else (current_user.id if (current_user.is_authenticated and isinstance(current_user, Colaborador)) else None)
    eh_participante = colab_atual_id and any(ac.colaborador_id == colab_atual_id for ac in grupo.colaboradores)
    if not eh_gestor and not eh_participante:
        abort(403)

    if request.method == "POST":
        if not eh_gestor:
            abort(403)
        acao = request.form.get("acao", "salvar")

        if acao == "cancelar":
            motivo = (request.form.get("motivo_cancelamento") or "").strip()
            if not motivo:
                flash("Informe o motivo do cancelamento.", "danger")
                return redirect(url_for("facilities.atividade_detalhe", grupo_id=grupo.id))
            for d in grupo.dias:
                if d.status not in ("APROVADA",):
                    d.status = "CANCELADA"
            grupo.motivo_cancelamento = motivo
            grupo.status_cadastro = grupo.status_cadastro  # mantém, só os dias mudam de status
            db.session.commit()
            flash("Atividade cancelada.", "success")
            return redirect(url_for("facilities.programacao"))

        if acao == "adicionar_colaborador":
            colaborador_id = request.form.get("novo_colaborador_id")
            if colaborador_id:
                ja_existe = any(ac.colaborador_id == int(colaborador_id) for ac in grupo.colaboradores)
                if not ja_existe:
                    db.session.add(AtividadeColaborador(grupo_id=grupo.id, colaborador_id=int(colaborador_id),
                                                        eh_responsavel=not grupo.colaboradores))
                    db.session.commit()
                    flash("Colaborador adicionado.", "success")
            return redirect(url_for("facilities.atividade_detalhe", grupo_id=grupo.id))

        if acao == "remover_colaborador":
            ac_id = request.form.get("ac_id")
            if ac_id:
                AtividadeColaborador.query.filter_by(id=int(ac_id), grupo_id=grupo.id).delete()
                db.session.commit()
                flash("Colaborador removido.", "success")
            return redirect(url_for("facilities.atividade_detalhe", grupo_id=grupo.id))

        # acao == "salvar" (completar/editar os campos principais) — [fix] agora disponível
        # SEMPRE para o gestor, não só quando o cadastro está incompleto.
        plantas_disp, ids_permitidas = _plantas_ctx()
        planta_id = request.form.get("planta_id") or None
        if planta_id:
            ids_ok = {p.id for p in plantas_disp}
            if int(planta_id) not in ids_ok:
                planta_id = None
        grupo.titulo = (request.form.get("titulo") or grupo.titulo).strip()
        grupo.descricao = (request.form.get("descricao") or grupo.descricao or "").strip()
        grupo.planta_id = int(planta_id) if planta_id else None
        predio_id = request.form.get("predio_id") or None
        grupo.predio_id = int(predio_id) if predio_id else None
        # completo só se os campos essenciais estiverem todos preenchidos agora
        grupo.status_cadastro = "COMPLETO" if (grupo.titulo and grupo.planta_id and grupo.predio_id) else "INCOMPLETO"
        db.session.commit()
        flash("Atividade atualizada." + ("" if grupo.status_cadastro == "COMPLETO" else " Ainda falta completar algum campo."), "success")
        return redirect(url_for("facilities.atividade_detalhe", grupo_id=grupo.id))

    dias = sorted(grupo.dias, key=lambda d: d.ordem)
    plantas_disp = predios_disp = colaboradores_disp = None
    if eh_gestor:
        plantas_disp, _ids = _plantas_ctx()
        predios_disp = Predio.query.filter_by(ativo=True).order_by(Predio.nome).all()
        ja_na_atividade = {ac.colaborador_id for ac in grupo.colaboradores}
        colaboradores_disp = (Colaborador.query.filter_by(ativo=True)
                              .filter(~Colaborador.id.in_(ja_na_atividade) if ja_na_atividade else True)
                              .order_by(Colaborador.nome).all())
    return render_template("facilities/atividade_detalhe.html", grupo=grupo, dias=dias,
                           eh_gestor=eh_gestor, colab_atual=colab, hoje=date.today(),
                           plantas_disp=plantas_disp, predios_disp=predios_disp,
                           colaboradores_disp=colaboradores_disp)


@facilities_bp.route("/programacao/conflito/<int:grupo_antigo_id>/resolver", methods=["POST"])
@_ver_required
def resolver_conflito(grupo_antigo_id):
    """Aplica a decisão do usuário sobre um conflito de agenda: manter nas duas (nada a
    fazer), retirar da anterior, ou reprogramar a anterior para outra data (com motivo)."""
    acao = request.form.get("acao")
    colaborador_id = int(request.form.get("colaborador_id"))
    if acao == "retirar_anterior":
        AtividadeColaborador.query.filter_by(grupo_id=grupo_antigo_id, colaborador_id=colaborador_id).delete()
        db.session.commit()
        flash("Colaborador removido da atividade anterior.", "success")
    elif acao == "reprogramar_anterior":
        nova_data = request.form.get("nova_data")
        motivo = (request.form.get("motivo") or "").strip()
        if not nova_data or not motivo:
            flash("Informe a nova data e o motivo da reprogramação.", "danger")
            return redirect(url_for("facilities.programacao"))
        grupo = db.session.get(AtividadeGrupo, grupo_antigo_id) or abort(404)
        nova_data_d = datetime.strptime(nova_data, "%Y-%m-%d").date()
        novas_datas = _gerar_dias_uteis(nova_data_d, grupo.duracao_dias_uteis)
        for dia, nova_d in zip(grupo.dias, novas_datas):
            dia.reprogramado_de = dia.data
            dia.motivo_reprogramacao = motivo
            dia.data = nova_d
        grupo.data_inicio = nova_data_d
        db.session.commit()
        flash("Atividade reprogramada.", "success")
    else:
        flash("Mantido nas duas atividades.", "success")
    return redirect(url_for("facilities.programacao"))


@facilities_bp.route("/programacao/colaboradores-por-empresa/<int:fornecedor_id>")
@_ver_required
def colaboradores_por_empresa(fornecedor_id):
    from flask import jsonify
    itens = _colaboradores_disp_por_empresa(fornecedor_id)
    return jsonify(colaboradores=[{"id": c.id, "nome": c.nome} for c in itens])


# ============================================================================
# PREENCHIMENTO (colaborador) — fluxo obrigatório: escolher HOJE ou OUTRO DIA primeiro
# ============================================================================

@facilities_bp.route("/preencher")
@_logado_required
def preencher_escolher():
    """Tela 1: escolhe HOJE ou um dos dias em que o colaborador tem atividade."""
    from .almox import _colab_sessao
    colab_id, usuario_id = _quem_preencheu()
    q = AtividadeDia.query.join(AtividadeColaborador, AtividadeColaborador.grupo_id == AtividadeDia.grupo_id)
    if colab_id:
        q = q.filter(AtividadeColaborador.colaborador_id == colab_id)
    dias_disponiveis = sorted({d.data for d in q.all() if d.data <= date.today()}, reverse=True)
    return render_template("facilities/preencher_escolher.html", dias_disponiveis=dias_disponiveis, hoje=date.today())


@facilities_bp.route("/preencher/<data_str>", methods=["GET", "POST"])
@_logado_required
def preencher_dia(data_str):
    """Tela 2: mostra (e processa) só as atividades do colaborador NAQUELE dia."""
    try:
        data_d = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        abort(404)
    colab_id, usuario_id = _quem_preencheu()

    q = AtividadeDia.query.join(AtividadeColaborador, AtividadeColaborador.grupo_id == AtividadeDia.grupo_id)
    q = q.filter(AtividadeDia.data == data_d)
    if colab_id:
        q = q.filter(AtividadeColaborador.colaborador_id == colab_id)
    minhas_atividades = q.all()
    # [item 4 fix] % do dia anterior de cada atividade — usado no template pra so' mostrar a
    # caixa de justificativa quando a nova % REALMENTE for menor (antes o JS mostrava sempre).
    pct_anterior_por_dia = {}
    for at in minhas_atividades:
        anterior = (AtividadeDia.query.filter(AtividadeDia.grupo_id == at.grupo_id,
                    AtividadeDia.ordem < at.ordem).order_by(AtividadeDia.ordem.desc()).first())
        pct_anterior_por_dia[at.id] = anterior.percentual if anterior else None

    if request.method == "POST":
        dia_id = int(request.form.get("dia_id"))
        dia = db.session.get(AtividadeDia, dia_id) or abort(404)
        # [fix CRÍTICO] antes o POST processava qualquer dia_id enviado, sem checar se o dia
        # pertence a uma atividade do colaborador logado — a tela só ESCONDIA os outros dias,
        # mas a rota aceitava preencher qualquer um. Agora valida de verdade: só quem participa
        # da atividade (ou Admin/Master) pode preencher aquele dia.
        eh_participante = colab_id and any(ac.colaborador_id == colab_id for ac in dia.grupo.colaboradores)
        eh_gestor = current_user.is_authenticated and (getattr(current_user, "is_admin", False)
                    or getattr(current_user, "is_master", False))
        if not eh_participante and not eh_gestor:
            abort(403)
        nova_pct = int(request.form.get("percentual") or 0)

        dia_anterior = (AtividadeDia.query.filter(AtividadeDia.grupo_id == dia.grupo_id,
                        AtividadeDia.ordem < dia.ordem).order_by(AtividadeDia.ordem.desc()).first())
        justificativa = (request.form.get("justificativa") or "").strip()
        # [fix] só exige justificativa se o dia anterior REALMENTE tem uma % registrada (not None
        # e diferente de vazio) — antes de qualquer preenchimento, dia_anterior.percentual é None,
        # e comparar "nova_pct < None" nunca deveria disparar o aviso.
        if (dia_anterior and dia_anterior.percentual is not None
                and nova_pct < dia_anterior.percentual and not justificativa):
            flash("A % é menor que a do dia anterior — informe uma justificativa.", "danger")
            return redirect(url_for("facilities.preencher_dia", data_str=data_str))

        dia.percentual = nova_pct
        dia.descricao_execucao = (request.form.get("descricao") or "").strip()
        dia.justificativa_queda = justificativa or None
        dia.status = "AGUARDANDO_APROVACAO"
        fotos = _salvar_fotos("fotos", maximo=4)
        if fotos:
            dia.fotos_json = json.dumps(fotos)
        db.session.add(RegistroPreenchimento(dia_id=dia.id, colaborador_id=colab_id, usuario_id=usuario_id,
                                             percentual=nova_pct))
        db.session.commit()
        flash("Preenchido — aguardando aprovação do Encarregado de Campo.", "success")
        return redirect(url_for("facilities.preencher_dia", data_str=data_str, compartilhar=dia.id))

    return render_template("facilities/preencher_dia.html", data_d=data_d, atividades=minhas_atividades,
                           pct_anterior_por_dia=pct_anterior_por_dia,
                           compartilhar_id=request.args.get("compartilhar"))


# ============================================================================
# APROVAÇÃO (Encarregado de Campo) — só Aprovar ou Retificar (sem reprovar)
# ============================================================================

@facilities_bp.route("/aprovacao")
@_ver_required
def aprovacao():
    from .almox import _colab_sessao
    colab = _colab_sessao()
    # [fix] mesma checagem: Encarregado pode estar logado NORMALMENTE (current_user é o
    # próprio Colaborador) ou via sessão de campo (colab) — antes só a segunda era vista.
    is_encarregado = (
        (current_user.is_authenticated and (getattr(current_user, "is_admin", False)
            or getattr(current_user, "is_master", False)
            or getattr(current_user, "eh_encarregado_campo", False)))
        or getattr(colab, "eh_encarregado_campo", False)
    )
    if not is_encarregado:
        abort(403)
    colab_atual = colab if colab else (current_user if (current_user.is_authenticated and isinstance(current_user, Colaborador)) else None)
    q = AtividadeDia.query.filter_by(status="AGUARDANDO_APROVACAO")
    if colab_atual and not (getattr(current_user, "is_admin", False) or getattr(current_user, "is_master", False)):
        empresas_ids = {e.id for e in colab_atual.empresas_encarregado}
        if empresas_ids:
            nomes_empresas = {db.session.get(Fornecedor, eid).nome_fantasia or db.session.get(Fornecedor, eid).razao_social
                              for eid in empresas_ids}
            q = (q.join(AtividadeGrupo)
                 .join(AtividadeColaborador, AtividadeColaborador.grupo_id == AtividadeGrupo.id)
                 .join(Colaborador, Colaborador.id == AtividadeColaborador.colaborador_id)
                 .filter(Colaborador.empresa.in_(nomes_empresas)))
    pendentes = q.order_by(AtividadeDia.data.desc()).all()
    return render_template("facilities/aprovacao.html", pendentes=pendentes)


@facilities_bp.route("/aprovacao/<int:dia_id>/aprovar", methods=["POST"])
@_ver_required
def aprovar_dia(dia_id):
    dia = db.session.get(AtividadeDia, dia_id) or abort(404)
    dia.status = "APROVADA"
    dia.aprovado_em = datetime.utcnow()
    dia.aprovado_por = current_user.id if current_user.is_authenticated else None
    db.session.commit()
    flash("Aprovado.", "success")
    return redirect(url_for("facilities.aprovacao"))


@facilities_bp.route("/aprovacao/<int:dia_id>/retificar", methods=["POST"])
@_ver_required
def retificar_dia(dia_id):
    """[v3] Não existe mais "reprovar": o Encarregado edita direto e já sai aprovado."""
    dia = db.session.get(AtividadeDia, dia_id) or abort(404)
    dia.percentual = int(request.form.get("percentual") or dia.percentual or 0)
    dia.descricao_execucao = (request.form.get("descricao") or dia.descricao_execucao)
    dia.retificado = True
    dia.status = "APROVADA"
    dia.aprovado_em = datetime.utcnow()
    dia.aprovado_por = current_user.id if current_user.is_authenticated else None
    db.session.commit()
    flash("Retificado e aprovado.", "success")
    return redirect(url_for("facilities.aprovacao"))


@facilities_bp.route("/aprovacao/<int:dia_id>/reprogramar", methods=["POST"])
@_ver_required
def reprogramar_dia(dia_id):
    """[item 10] Reprograma um dia de atividade. Duas opções:
    - "somente_esta": só o dia clicado muda de data; os demais dias pendentes (se houver)
      continuam nas datas originais.
    - "todas_restantes": TODOS os dias ainda não aprovados a partir deste (inclusive) são
      recalculados a partir da nova data informada, pulando fim de semana/feriados (mesma
      lógica de _gerar_dias_uteis usada na criação da atividade) — preserva a ordem/sequência
      entre eles, só desloca o "início" da parte que falta.
    Em ambos os casos, exige motivo (histórico de por que foi reprogramado)."""
    dia = db.session.get(AtividadeDia, dia_id) or abort(404)
    nova_data = request.form.get("nova_data")
    motivo = (request.form.get("motivo") or "").strip()
    escopo = request.form.get("escopo", "somente_esta")
    if not nova_data or not motivo:
        flash("Informe a nova data e o motivo.", "danger")
        return redirect(request.referrer or url_for("facilities.aprovacao"))
    nova_data_d = datetime.strptime(nova_data, "%Y-%m-%d").date()

    if escopo == "todas_restantes":
        # todos os dias do MESMO grupo, a partir deste (por ordem), que ainda não foram
        # aprovados — os já aprovados ficam intocados, o histórico deles não deve mudar.
        restantes = (AtividadeDia.query.filter(AtividadeDia.grupo_id == dia.grupo_id,
                     AtividadeDia.ordem >= dia.ordem, AtividadeDia.status != "APROVADA")
                     .order_by(AtividadeDia.ordem).all())
        novas_datas = _gerar_dias_uteis(nova_data_d, len(restantes))
        for d, nova_d in zip(restantes, novas_datas):
            d.reprogramado_de = d.data
            d.data = nova_d
            d.motivo_reprogramacao = motivo
        db.session.commit()
        flash(f"{len(restantes)} dia(s) reprogramado(s) a partir de {nova_data_d.strftime('%d/%m/%Y')}.", "success")
    else:
        dia.reprogramado_de = dia.data
        dia.data = nova_data_d
        dia.motivo_reprogramacao = motivo
        db.session.commit()
        flash("Dia reprogramado.", "success")
    return redirect(request.referrer or url_for("facilities.aprovacao"))


# ============================================================================
# RESUMO DIÁRIO (imagem/PDF) — início/fim, por empresa
# ============================================================================

@facilities_bp.route("/resumo-diario")
@_ver_programacao_required
def resumo_diario():
    data_str = request.args.get("data") or date.today().strftime("%Y-%m-%d")
    data_d = datetime.strptime(data_str, "%Y-%m-%d").date()
    tipo = request.args.get("tipo", "inicio")

    agora = datetime.now()
    fim_liberado = data_d < date.today() or (data_d == date.today() and agora.hour >= 14)
    if tipo == "fim" and not fim_liberado:
        flash("O resumo de FIM só fica disponível após as 14h (ou em dias anteriores).", "warning")
        return redirect(url_for("facilities.programacao", data=data_str))

    dias = AtividadeDia.query.filter_by(data=data_d).all()
    # [fix] atividades com cadastro incompleto (falta planta/prédio/data) NÃO entram no resumo —
    # o resumo é um documento formal pra empresa, não faz sentido sair com dado faltando.
    dias_completos = [d for d in dias if d.grupo.status_cadastro != "INCOMPLETO"]
    n_incompletas_no_dia = len(dias) - len(dias_completos)
    dias = dias_completos

    empresas_ids = set()
    for d in dias:
        for ac in d.grupo.colaboradores:
            if ac.colaborador and ac.colaborador.empresa:
                empresas_ids.add(ac.colaborador.empresa)

    fornecedor_sel = request.args.get("empresa")
    linhas = []
    if fornecedor_sel:
        for d in dias:
            colaboradores_da_empresa = [ac.colaborador.nome for ac in d.grupo.colaboradores
                                        if ac.colaborador and ac.colaborador.empresa == fornecedor_sel]
            if not colaboradores_da_empresa:
                continue
            nomes_fmt = ", ".join(_remover_particulas_sobrenome(n) for n in colaboradores_da_empresa)
            linhas.append({"local": d.grupo.predio.nome if d.grupo.predio else "—",
                          "titulo": d.grupo.titulo, "colaboradores": nomes_fmt})

    return render_template("facilities/resumo_diario.html", data_d=data_d, tipo=tipo,
                           fim_liberado=fim_liberado, empresas=sorted(empresas_ids),
                           empresa_sel=fornecedor_sel, linhas=linhas,
                           n_incompletas_no_dia=n_incompletas_no_dia)


# ============================================================================
# RELATÓRIO DIÁRIO DE OBRA (RDO)
# ============================================================================

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
    atividades_hoje_ids = {d.grupo_id for d in AtividadeDia.query.filter(AtividadeDia.data == hoje).all()}
    atividades_hoje = AtividadeGrupo.query.filter(AtividadeGrupo.id.in_(atividades_hoje_ids)).all() if atividades_hoje_ids else []
    if ids_permitidas:
        atividades_hoje = [a for a in atividades_hoje if a.planta_id in ids_permitidas or a.planta_id is None]
    return render_template("facilities/rdo.html", itens=itens, plantas_disp=plantas_disp,
                           atividades_hoje=atividades_hoje, hoje=hoje)
