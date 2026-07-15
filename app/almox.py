from functools import wraps
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, abort, flash, current_app, request, session
from flask_login import login_required, current_user, login_user

from .extensions import db
from .models import Solicitacao, LogSolicitacao
from .emails import enviar_email

almox_bp = Blueprint("almox", __name__, url_prefix="/almoxarifado")


def almox_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not (current_user.is_almox or current_user.is_admin):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@almox_bp.route("/chegadas")
@almox_required
def index():
    pendentes = (Solicitacao.query.filter_by(status="AGUARDANDO_CHEGADA")
                 .order_by(Solicitacao.prazo_recebimento).all())
    recentes = (Solicitacao.query.filter_by(status="CONCLUIDO")
                .order_by(Solicitacao.chegada_em.desc()).limit(10).all())
    return render_template("almox/index.html", pendentes=pendentes, recentes=recentes)


@almox_bp.route("/chegada/<int:sid>/editar-data", methods=["POST"])
@almox_required
def editar_data_chegada(sid):
    """Corrige a data de uma chegada já confirmada (item 129)."""
    s = db.session.get(Solicitacao, sid) or abort(404)
    nova_data = request.form.get("nova_data")
    if not nova_data or not s.chegada_em:
        flash("Informe uma data válida.", "danger")
        return redirect(url_for("almox.index"))
    try:
        d = datetime.strptime(nova_data, "%Y-%m-%d")
        s.chegada_em = d.replace(hour=s.chegada_em.hour, minute=s.chegada_em.minute, second=s.chegada_em.second)
        db.session.add(LogSolicitacao(solicitacao_id=s.id, autor_id=current_user.id,
                                      evento=f"Data de chegada corrigida para {d:%d/%m/%Y}"))
        db.session.commit()
        flash("Data de chegada atualizada.", "success")
    except ValueError:
        flash("Data inválida.", "danger")
    return redirect(url_for("almox.index"))


@almox_bp.route("/chegada/<int:sid>", methods=["POST"])
@almox_required
def marcar_chegada(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    if s.status != "AGUARDANDO_CHEGADA":
        flash("Esta solicitação não está aguardando chegada.", "warning")
        return redirect(url_for("almox.index"))
    ja = s.quantidade_recebida or 0
    restante = max(s.quantidade - ja, 0)
    # quantidade informada nesta confirmação (padrão = restante)
    try:
        qtd = int(request.form.get("qtd_recebida") or restante)
    except ValueError:
        qtd = restante
    if qtd <= 0:
        flash("Informe uma quantidade recebida maior que zero.", "danger")
        return redirect(url_for("almox.index"))
    qtd = min(qtd, restante)
    total = ja + qtd
    s.quantidade_recebida = total

    # item 129 — permitir registrar com data diferente de hoje (ex.: chegada com atraso no registro)
    data_chegada_str = request.form.get("data_chegada")
    momento_chegada = datetime.utcnow()
    if data_chegada_str:
        try:
            data_escolhida = datetime.strptime(data_chegada_str, "%Y-%m-%d")
            momento_chegada = data_escolhida.replace(
                hour=momento_chegada.hour, minute=momento_chegada.minute, second=momento_chegada.second)
        except ValueError:
            pass

    if total >= s.quantidade:
        s.status = "CONCLUIDO"
        s.chegada_confirmada_por = current_user.id
        s.chegada_em = momento_chegada
        evento = f"Chegada confirmada — recebido {total} de {s.quantidade} (Concluído) — data: {momento_chegada:%d/%m/%Y}"
        assunto = f"Solicitação Nº {s.id} — material recebido (completo)"
        msg = f"Chegada completa: {total} de {s.quantidade} ({s.material})."
        flash(f"Chegada total confirmada. Solicitação Nº {s.id} concluída.", "success")
    else:
        evento = f"Chegada parcial — recebido {qtd} (acumulado {total} de {s.quantidade}) — data: {momento_chegada:%d/%m/%Y}"
        assunto = f"Solicitação Nº {s.id} — chegada parcial"
        msg = f"Chegada parcial: recebido {total} de {s.quantidade} ({s.material})."
        flash(f"Chegada parcial registrada: {total} de {s.quantidade}.", "success")
    db.session.add(LogSolicitacao(solicitacao_id=s.id, autor_id=current_user.id, evento=evento))
    db.session.commit()
    enviar_email([s.solicitante.email, current_app.config.get("ADMIN_EMAIL")], assunto,
                 f"A confirmação de chegada da solicitação Nº {s.id} foi registrada. {msg}")
    return redirect(url_for("almox.index"))


# ==================== MÓDULO ALMOXARIFADO (Chaves / Extintores / Colaboradores) ====================
from datetime import date
from .models import (Chave, Extintor, Colaborador, AlmoxLog, QuadroChave,
                     PapelColaborador, MovimentacaoChave, TAREFAS_COLABORADOR, TAREFAS_DICT,
                     InspecaoExtintor, PendenciaEtiqueta, CHECK_EXTINTOR, ITEM_ETIQUETA_EXTINTOR)


def _qr_svg(texto, box=8, border=2):
    """Gera um QR Code como string SVG (sem dependência de imagem/Pillow).
    Usado para impressão de etiquetas de chaves/colaboradores/extintores."""
    try:
        import qrcode
        import qrcode.image.svg as _svg
        import io
        img = qrcode.make(texto, image_factory=_svg.SvgPathImage, box_size=box, border=border)
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf-8")
    except Exception:
        # Fallback: caixa com o texto, caso a lib não esteja disponível
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120">'
                f'<rect width="120" height="120" fill="#eee" stroke="#999"/>'
                f'<text x="60" y="64" font-size="10" text-anchor="middle">{texto}</text></svg>')

# Tópicos do módulo. liberado=True abre a tela; senão mostra "Em construção".
TOPICOS = [
    {"slug": "painel",      "nome": "Painel",                          "icone": "📊", "liberado": False},
    {"slug": "entrada",     "nome": "Entrada de material",             "icone": "⤵",  "liberado": False},
    {"slug": "devolucao",   "nome": "Devolução forçada",               "icone": "⏎",  "liberado": False},
    {"slug": "inventario",  "nome": "Inventário",                      "icone": "✓",  "liberado": False},
    {"slug": "ajuste",      "nome": "Ajuste de item",                  "icone": "✎",  "liberado": False},
    {"slug": "produto",     "nome": "Produto (Item/Classe/Atributo)",  "icone": "⬡",  "liberado": False},
    {"slug": "unidades",    "nome": "Unidades / validade / calibração","icone": "⌗",  "liberado": False},
    {"slug": "kit",         "nome": "Controle por Kit",                "icone": "◫",  "liberado": False},
    {"slug": "consulta",    "nome": "Consulta de estoque",             "icone": "🔎", "liberado": False},
    {"slug": "movimentacoes","nome": "Movimentações",                  "icone": "⇄",  "liberado": False},
    {"slug": "etiquetas",   "nome": "Etiquetas",                       "icone": "🏷", "liberado": False},
    {"slug": "qr",          "nome": "QR de colaboradores",             "icone": "▨",  "liberado": False},
    {"slug": "log",         "nome": "Log de ações",                    "icone": "📜", "liberado": False},
    {"slug": "coletor",     "nome": "Coletor",                         "icone": "📲", "liberado": True, "endpoint": "almox.coletor"},
    {"slug": "chaves",      "nome": "Chaves",                          "icone": "🔑", "liberado": True, "endpoint": "almox.chaves"},
    {"slug": "relatorio_chaves","nome": "Relatório de chaves",         "icone": "📈", "liberado": True, "endpoint": "almox.relatorio_chaves"},
    {"slug": "extintores",  "nome": "Extintores",                      "icone": "🧯", "liberado": True, "endpoint": "almox.extintores"},
    {"slug": "pend_etiqueta","nome": "Pendências de etiqueta",          "icone": "🏷", "liberado": True, "endpoint": "almox.pendencias_etiqueta"},
    {"slug": "colaboradores","nome": "Colaboradores",                  "icone": "👤", "liberado": True, "endpoint": "almox.colaboradores", "somente_colab": True},
    {"slug": "papeis",      "nome": "Papéis de colaborador",           "icone": "🎭", "liberado": True, "endpoint": "almox.papeis", "somente_admin": True},
]


def modulo_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.pode_almox_modulo:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def _guard(prop):
    def deco(f):
        @wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if not getattr(current_user, prop, False):
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return deco


def _log(categoria, detalhe):
    db.session.add(AlmoxLog(autor_id=getattr(current_user, "id", None), categoria=categoria, detalhe=detalhe))


def _venc_info(validade):
    """Retorna (rotulo, cor_bootstrap) a partir da data de validade."""
    if not validade:
        return ("—", "secondary")
    dias = (validade - date.today()).days
    if dias < 0:
        return ("Vencido", "danger")
    if dias <= 30:
        return (f"Vence em {dias}d", "danger")
    if dias <= 90:
        return (f"Vence em {dias}d", "warning")
    return ("No prazo", "success")


@almox_bp.route("/")
@modulo_required
def home():
    topicos = [t for t in TOPICOS
               if not (t.get("somente_colab") and not current_user.pode_colaboradores)
               and not (t.get("somente_admin") and not current_user.is_admin)]
    return render_template("almox/home.html", topicos=topicos)


@almox_bp.route("/em-construcao/<slug>")
@modulo_required
def em_construcao(slug):
    topico = next((t for t in TOPICOS if t["slug"] == slug), None)
    if not topico:
        abort(404)
    return render_template("almox/em_construcao.html", topico=topico)


# ---------- CHAVES ----------
@almox_bp.route("/chaves")
@_guard("pode_chaves")
def chaves():
    q = (request.args.get("q") or "").strip()
    consulta = Chave.query.filter_by(ativo=True)
    itens = [c for c in consulta.order_by(Chave.descricao).all()
             if not q or q.lower() in " ".join([c.descricao or "", c.quadro_nome or "", c.status or "", c.com_quem or ""]).lower()]
    quadros = QuadroChave.query.filter_by(ativo=True).order_by(QuadroChave.nome).all()
    colabs = Colaborador.query.filter_by(ativo=True).order_by(Colaborador.nome).all()
    return render_template("almox/chaves.html", itens=itens, q=q, quadros=quadros, colabs=colabs)


@almox_bp.route("/chaves/nova", methods=["POST"])
@_guard("pode_chaves")
def chave_nova():
    import secrets
    desc = (request.form.get("descricao") or "").strip()
    if not desc:
        flash("Informe a descrição da chave.", "danger")
        return redirect(url_for("almox.chaves"))
    quadro_id = request.form.get("quadro_chave_id") or None
    uid = "CH-" + secrets.token_hex(4).upper()
    while Chave.query.filter_by(qr_uid=uid).first():
        uid = "CH-" + secrets.token_hex(4).upper()
    c = Chave(descricao=desc.upper(), quadro_chave_id=int(quadro_id) if quadro_id else None,
              qr_uid=uid, status="Disponível")
    db.session.add(c)
    _log("Chave", f"Chave cadastrada: {c.descricao}")
    db.session.commit()
    flash("Chave cadastrada.", "success")
    return redirect(url_for("almox.chaves"))


@almox_bp.route("/chaves/<int:cid>/toggle", methods=["POST"])
@_guard("pode_chaves")
def chave_toggle(cid):
    c = db.session.get(Chave, cid) or abort(404)
    if c.status == "Disponível":
        nome = (request.form.get("com_quem") or "").strip().upper() or "—"
        c.status = "Em uso"
        c.com_quem = nome
        colab = Colaborador.query.filter(db.func.upper(Colaborador.nome) == nome).first()
        db.session.add(MovimentacaoChave(
            chave_id=c.id, chave_desc=c.descricao, quadro_nome=c.quadro_nome,
            colaborador_id=(colab.id if colab else None), colaborador_nome=nome,
            acao="retirada", operador_id=current_user.id))
        _log("Chave", f"Chave {c.descricao} retirada por {nome}")
    else:
        retirou = c.com_quem or "—"
        devolvedor = (request.form.get("devolvido_por") or "").strip().upper() or retirou
        colab = Colaborador.query.filter(db.func.upper(Colaborador.nome) == devolvedor).first()
        db.session.add(MovimentacaoChave(
            chave_id=c.id, chave_desc=c.descricao, quadro_nome=c.quadro_nome,
            colaborador_id=(colab.id if colab else None), colaborador_nome=devolvedor,
            retirado_por=retirou, acao="devolucao", operador_id=current_user.id))
        _log("Chave", f"Chave {c.descricao} devolvida por {devolvedor}" +
             (f" (estava com {retirou})" if devolvedor != retirou else ""))
        c.status = "Disponível"
        c.com_quem = None
    db.session.commit()
    return redirect(url_for("almox.chaves"))


# ----- Quadros de Chave (localizador) -----
@almox_bp.route("/chaves/quadros")
@_guard("pode_chaves")
def quadros_chave():
    quadros = QuadroChave.query.order_by(QuadroChave.nome).all()
    return render_template("almox/quadros_chave.html", quadros=quadros)


@almox_bp.route("/chaves/quadros/novo", methods=["POST"])
@_guard("pode_chaves")
def quadro_novo():
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do Quadro de Chaves.", "danger")
        return redirect(url_for("almox.quadros_chave"))
    if QuadroChave.query.filter(db.func.upper(QuadroChave.nome) == nome.upper()).first():
        flash("Já existe um Quadro de Chaves com esse nome.", "warning")
        return redirect(url_for("almox.quadros_chave"))
    db.session.add(QuadroChave(nome=nome.upper()))
    _log("Chave", f"Quadro de Chaves cadastrado: {nome.upper()}")
    db.session.commit()
    flash("Quadro de Chaves cadastrado.", "success")
    return redirect(url_for("almox.quadros_chave"))


@almox_bp.route("/chaves/quadros/<int:qid>/toggle", methods=["POST"])
@_guard("pode_chaves")
def quadro_toggle(qid):
    quadro = db.session.get(QuadroChave, qid) or abort(404)
    quadro.ativo = not quadro.ativo
    db.session.commit()
    return redirect(url_for("almox.quadros_chave"))


# ----- QR individual da chave (impressão) -----
@almox_bp.route("/chaves/qr")
@_guard("pode_chaves")
def chaves_qr():
    """Página de impressão dos QR das chaves (uma etiqueta por chave)."""
    ids = request.args.get("ids") or ""
    consulta = Chave.query.filter_by(ativo=True)
    if ids.strip():
        try:
            lista_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
            consulta = consulta.filter(Chave.id.in_(lista_ids))
        except ValueError:
            pass
    itens = consulta.order_by(Chave.descricao).all()
    formato = request.args.get("formato", "a4")   # 'a4' | 'termica' | 'dobravel'
    return render_template("almox/chaves_qr.html", itens=itens, qr_svg=_qr_svg, formato=formato)

# ---------- EXTINTORES (Etapa 3) ----------
import json as _json
from datetime import datetime as _dt

MESES_PT = ["", "JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

SITUACAO_LABEL = {
    "NO_PRAZO": ("No prazo", "success"),
    "PROX_VENC": ("Próximo do vencimento", "warning"),
    "VENCIDO": ("Irregular / Vencido", "danger"),
    "IRREGULAR": ("Irregular", "danger"),
    "EM_RECARGA": ("Em recarga", "info"),
    "PRONTO_REPO": ("Pronto p/ reposição", "primary"),
}


def _competencia(d):
    """Rótulo MMM/AAAA de uma data (competência)."""
    return f"{MESES_PT[d.month]}/{d.year}" if d else "—"


def _meses_ate(d):
    if not d:
        return None
    hoje = date.today()
    return (d.year - hoje.year) * 12 + (d.month - hoje.month)


def _situacao_extintor(e):
    """Espelha o ciclo do protótipo. Estados operacionais (IRREGULAR/EM_RECARGA/
    PRONTO_REPO) vêm gravados em e.situacao; NO_PRAZO deriva PROX/VENCIDO das datas
    (carga E teste hidrostático). Próximo do vencimento = na competência anterior."""
    s = e.situacao or "NO_PRAZO"
    if s in ("EM_RECARGA", "PRONTO_REPO", "IRREGULAR"):
        return (s,) + SITUACAO_LABEL[s]
    # NO_PRAZO: checa validade da carga e do teste hidrostático
    piores = []
    for d in (e.validade, e.teste_hidrostatico):
        m = _meses_ate(d)
        if m is None:
            continue
        if m < 0:
            piores.append("VENCIDO")
        elif m <= 1:
            piores.append("PROX_VENC")
        else:
            piores.append("NO_PRAZO")
    if "VENCIDO" in piores:
        k = "VENCIDO"
    elif "PROX_VENC" in piores:
        k = "PROX_VENC"
    else:
        k = "NO_PRAZO"
    return (k,) + SITUACAO_LABEL[k]


def _parse_mmaaaa(prefixo, form):
    """Lê dois selects (mes_<prefixo>, ano_<prefixo>) e devolve date no dia 01, ou None."""
    mes = form.get(f"mes_{prefixo}") or ""
    ano = form.get(f"ano_{prefixo}") or ""
    if mes.isdigit() and ano.isdigit():
        try:
            return date(int(ano), int(mes), 1)
        except ValueError:
            return None
    return None


def _anos_range():
    a = date.today().year
    return list(range(a - 6, a + 8))


def _colab_sessao():
    """Colaborador autenticado no fluxo de campo (via QR), guardado na sessão."""
    cid = session.get("colab_ext_id")
    return db.session.get(Colaborador, cid) if cid else None


def _pode_gerir_ext():
    """True se o ator atual pode fazer as ações de gestão (regularizar/conferir/repor)."""
    return bool(current_user.is_authenticated and getattr(current_user, "pode_extintores", False))


def _ext_acesso(f):
    """Libera a rota para: usuário logado com acesso a extintores OU colaborador de campo (sessão)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated and getattr(current_user, "pode_extintores", False):
            return f(*args, **kwargs)
        if _colab_sessao():
            return f(*args, **kwargs)
        eid = kwargs.get("eid")
        e = db.session.get(Extintor, eid) if eid else None
        if e and e.qr_uid:
            return redirect(url_for("almox.extintor_campo", qr_uid=e.qr_uid))
        return redirect(url_for("auth.login"))
    return wrapper


def _redir_ficha(e):
    """Volta para a ficha certa conforme o ator (desktop logado x campo/colaborador)."""
    if current_user.is_authenticated:
        return redirect(url_for("almox.extintor_ficha", eid=e.id))
    return redirect(url_for("almox.extintor_campo", qr_uid=e.qr_uid))



@almox_bp.route("/extintores")
@_guard("pode_extintores")
def extintores():
    from .seed_extintores import PREDIO_LABEL
    predio = request.args.get("predio") or ""
    local = (request.args.get("local") or "").strip()
    tipo = (request.args.get("tipo") or "").strip()
    situacao = request.args.get("situacao") or ""
    consulta = Extintor.query.filter_by(ativo=True)
    if predio:
        consulta = consulta.filter_by(predio=predio)
    linhas = []
    todos = consulta.order_by(Extintor.predio, Extintor.local, Extintor.codigo).all()
    for e in todos:
        if local and local.lower() not in (e.local or "").lower():
            continue
        if tipo and tipo.lower() not in (e.tipo or "").lower():
            continue
        k, lbl, cls = _situacao_extintor(e)
        if situacao and situacao != k:
            continue
        linhas.append((e, k, lbl, cls))
    predios = sorted({e.predio for e in Extintor.query.filter_by(ativo=True).all() if e.predio})
    tipos = sorted({e.tipo for e in Extintor.query.filter_by(ativo=True).all() if e.tipo})
    n_pend = PendenciaEtiqueta.query.filter_by(resolvida=False).count()
    return render_template("almox/extintores.html", linhas=linhas, predio=predio, local=local,
                           tipo=tipo, situacao=situacao, predios=predios, tipos=tipos,
                           predio_label=PREDIO_LABEL, situacao_label=SITUACAO_LABEL,
                           competencia=_competencia, n_pend=n_pend)


@almox_bp.route("/extintores/<int:eid>")
@_ext_acesso
def extintor_ficha(eid):
    e = db.session.get(Extintor, eid) or abort(404)
    k, lbl, cls = _situacao_extintor(e)
    hist = (InspecaoExtintor.query.filter_by(extintor_id=e.id)
            .order_by(InspecaoExtintor.criado_em.desc()).limit(20).all())
    colab = _colab_sessao() if not current_user.is_authenticated else None
    return render_template("almox/extintor_ficha.html", e=e, sit_k=k, sit_lbl=lbl, sit_cls=cls,
                           check=CHECK_EXTINTOR, item_etiqueta=ITEM_ETIQUETA_EXTINTOR,
                           hist=hist, competencia=_competencia, meses=MESES_PT,
                           anos=_anos_range(), pode_gerir=_pode_gerir_ext(),
                           campo=False, ator_colab=colab)


def _coletar_checklist(form):
    """Lê o checklist do formulário. Devolve (itens_dict, tudo_conforme)."""
    itens = {}
    tudo_ok = True
    for i, item in enumerate(CHECK_EXTINTOR):
        v = form.get(f"item_{i}", "na")   # ok | nok | na
        itens[item] = v
        if v == "nok":
            tudo_ok = False
    return itens, tudo_ok



def _quem(form):
    """Nome de quem operou. Prioridade: colaborador de campo (sessão) > nome informado > usuário logado."""
    colab = _colab_sessao()
    if colab and not current_user.is_authenticated:
        return colab.nome, colab.id
    nome = (form.get("colaborador_nome") or "").strip().upper()
    if nome:
        c = Colaborador.query.filter(db.func.upper(Colaborador.nome) == nome).first()
        return nome, (c.id if c else None)
    if current_user.is_authenticated:
        return current_user.nome, None
    return ("—", None)


@almox_bp.route("/extintores/<int:eid>/inspecionar", methods=["POST"])
@_ext_acesso
def extintor_inspecionar(eid):
    e = db.session.get(Extintor, eid) or abort(404)
    itens, tudo_ok = _coletar_checklist(request.form)
    obs = (request.form.get("obs") or "").strip()
    nome, cid = _quem(request.form)
    resultado = "conforme" if tudo_ok else "irregular"
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="inspecao",
                                    resultado=resultado, itens_json=_json.dumps(itens, ensure_ascii=False),
                                    obs=obs, colaborador_id=cid, colaborador_nome=nome,
                                    operador_id=getattr(current_user, "id", None)))
    e.inspecao = date.today()
    if not tudo_ok:
        e.situacao = "IRREGULAR"
        _log("Extintor", f"{e.codigo} ({e.local}): inspeção IRREGULAR por {nome} — notificar ADMIN")
    else:
        # inspeção conforme não muda estado operacional (mantém NO_PRAZO/derivados)
        if e.situacao in ("IRREGULAR",):
            e.situacao = "NO_PRAZO"
        _log("Extintor", f"{e.codigo} ({e.local}): inspeção conforme por {nome}")
    db.session.commit()
    flash("Inspeção registrada." + ("" if tudo_ok else " Extintor marcado como IRREGULAR."),
          "success" if tudo_ok else "warning")
    return _redir_ficha(e)


@almox_bp.route("/extintores/<int:eid>/regularizar", methods=["POST"])
@_ext_acesso
def extintor_regularizar(eid):
    e = db.session.get(Extintor, eid) or abort(404)
    acao = request.form.get("acao")   # levado_d6 | reposto_local
    nome, cid = _quem(request.form)
    if acao == "levado_d6":
        e.situacao = "EM_RECARGA"
        e.retirado_por = nome
        db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="retirada",
                                        resultado="irregular", colaborador_id=cid, colaborador_nome=nome,
                                        operador_id=getattr(current_user, "id", None)))
        _log("Extintor", f"{e.codigo}: levado ao Almox D6 p/ recarga por {nome}")
        flash("Extintor marcado como Em recarga (levado ao Almox D6).", "info")
    elif acao == "reposto_local":
        itens, tudo_ok = _coletar_checklist(request.form)
        etiqueta = request.form.get("etiqueta_ok")   # sim | nao
        etiqueta_ok = (etiqueta == "sim")
        db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="reposto_local",
                                        resultado="conforme" if tudo_ok else "irregular",
                                        itens_json=_json.dumps(itens, ensure_ascii=False),
                                        etiqueta_ok=etiqueta_ok, colaborador_id=cid, colaborador_nome=nome,
                                        operador_id=getattr(current_user, "id", None)))
        if not etiqueta_ok:
            db.session.add(PendenciaEtiqueta(extintor_id=e.id, extintor_cod=e.codigo,
                                             predio=e.predio, local=e.local, aberta_por=nome))
        e.situacao = "NO_PRAZO" if tudo_ok else "IRREGULAR"
        _log("Extintor", f"{e.codigo}: reposto no local por {nome} "
                          f"({'OK' if tudo_ok else 'ainda irregular'}"
                          f"{'' if etiqueta_ok else '; etiqueta pendente'})")
        flash("Reposição registrada." + ("" if etiqueta_ok else " Pendência de etiqueta aberta."),
              "success")
    db.session.commit()
    return _redir_ficha(e)


@almox_bp.route("/extintores/<int:eid>/conferir", methods=["POST"])
@_ext_acesso
def extintor_conferir(eid):
    """Conferência do Almoxarifado (inclui item da etiqueta) → Pronto p/ reposição."""
    e = db.session.get(Extintor, eid) or abort(404)
    if not _pode_gerir_ext():
        abort(403)
    itens, tudo_ok = _coletar_checklist(request.form)
    etiqueta_ok = (request.form.get("etiqueta_ok") == "sim")
    nome, cid = _quem(request.form)
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="conferencia",
                                    resultado="conforme" if tudo_ok else "irregular",
                                    itens_json=_json.dumps(itens, ensure_ascii=False),
                                    etiqueta_ok=etiqueta_ok, colaborador_id=cid, colaborador_nome=nome,
                                    operador_id=getattr(current_user, "id", None)))
    if not etiqueta_ok:
        db.session.add(PendenciaEtiqueta(extintor_id=e.id, extintor_cod=e.codigo,
                                         predio=e.predio, local=e.local, aberta_por=nome))
    e.situacao = "PRONTO_REPO"
    _log("Extintor", f"{e.codigo}: conferido no Almox (pronto p/ reposição) por {nome}"
                     f"{'' if etiqueta_ok else '; etiqueta pendente'}")
    db.session.commit()
    flash("Conferência registrada. Extintor Pronto para reposição." +
          ("" if etiqueta_ok else " Pendência de etiqueta aberta."), "success")
    return _redir_ficha(e)


@almox_bp.route("/extintores/<int:eid>/repor", methods=["POST"])
@_ext_acesso
def extintor_repor(eid):
    """Reposição final: volta ao local, atualiza validade da carga e/ou TH (MMM+AAAA)."""
    e = db.session.get(Extintor, eid) or abort(404)
    if not _pode_gerir_ext():
        abort(403)
    nome, cid = _quem(request.form)
    nova_val = _parse_mmaaaa("validade", request.form)
    novo_th = _parse_mmaaaa("th", request.form)
    if nova_val:
        e.validade = nova_val
    if novo_th:
        e.teste_hidrostatico = novo_th
    e.situacao = "NO_PRAZO"
    e.retirado_por = None
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="reposicao",
                                    resultado="conforme", colaborador_id=cid, colaborador_nome=nome,
                                    operador_id=getattr(current_user, "id", None),
                                    obs=f"validade={_competencia(e.validade)}; TH={_competencia(e.teste_hidrostatico)}"))
    _log("Extintor", f"{e.codigo}: reposto no local por {nome} "
                     f"(validade {_competencia(e.validade)}, TH {_competencia(e.teste_hidrostatico)})")
    db.session.commit()
    flash("Reposição concluída. Extintor No prazo.", "success")
    return _redir_ficha(e)


# ----- Acesso pelo QR no campo (login único: CPF ou e-mail) -----
@almox_bp.route("/e/<qr_uid>")
def extintor_campo(qr_uid):
    e = Extintor.query.filter_by(qr_uid=qr_uid, ativo=True).first() or abort(404)
    # Já logado como usuário do sistema com acesso → ficha completa
    if current_user.is_authenticated and getattr(current_user, "pode_extintores", False):
        return _ficha_campo(e, pode_gerir=True, colab=None)
    # Colaborador de campo já autenticado nesta sessão → ficha de inspeção
    colab = _colab_sessao()
    if colab:
        return _ficha_campo(e, pode_gerir=False, colab=colab)
    # Senão, tela de login única
    return render_template("almox/extintor_login.html", e=e, etapa="login")


def _ficha_campo(e, pode_gerir, colab):
    k, lbl, cls = _situacao_extintor(e)
    hist = (InspecaoExtintor.query.filter_by(extintor_id=e.id)
            .order_by(InspecaoExtintor.criado_em.desc()).limit(20).all())
    return render_template("almox/extintor_ficha.html", e=e, sit_k=k, sit_lbl=lbl, sit_cls=cls,
                           check=CHECK_EXTINTOR, item_etiqueta=ITEM_ETIQUETA_EXTINTOR,
                           hist=hist, competencia=_competencia, meses=MESES_PT,
                           anos=_anos_range(), pode_gerir=pode_gerir, campo=True, ator_colab=colab)


@almox_bp.route("/e/<qr_uid>/entrar", methods=["POST"])
def extintor_campo_entrar(qr_uid):
    from .models import Usuario
    e = Extintor.query.filter_by(qr_uid=qr_uid, ativo=True).first() or abort(404)
    ident = (request.form.get("ident") or "").strip()
    senha = request.form.get("senha") or ""
    if "@" in ident:
        # login de usuário do sistema
        u = Usuario.query.filter_by(email=ident.lower()).first()
        if u and u.ativo and u.check_senha(senha):
            login_user(u)
            return redirect(url_for("almox.extintor_campo", qr_uid=qr_uid))
        flash("E-mail ou senha inválidos.", "danger")
        return render_template("almox/extintor_login.html", e=e, etapa="login")
    # senão, trata como CPF de colaborador
    cpf = "".join(c for c in ident if c.isdigit())
    colab = Colaborador.query.filter_by(ativo=True).filter(
        db.func.replace(db.func.replace(db.func.replace(Colaborador.cpf, ".", ""), "-", ""), " ", "") == cpf).first()
    if not colab:
        # fallback: compara só dígitos em Python (bases pequenas)
        colab = next((c for c in Colaborador.query.filter_by(ativo=True).all()
                      if "".join(ch for ch in (c.cpf or "") if ch.isdigit()) == cpf and cpf), None)
    if not colab:
        flash("CPF não encontrado no cadastro de colaboradores.", "danger")
        return render_template("almox/extintor_login.html", e=e, etapa="login")
    if not colab.tem_senha:
        # primeiro acesso: define a senha
        conf = request.form.get("confirma") or ""
        if not senha or len(senha) < 4:
            flash("Primeiro acesso: defina uma senha de ao menos 4 dígitos.", "warning")
            return render_template("almox/extintor_login.html", e=e, etapa="definir", colab_nome=colab.nome)
        if senha != conf:
            flash("As senhas não coincidem.", "danger")
            return render_template("almox/extintor_login.html", e=e, etapa="definir", colab_nome=colab.nome)
        colab.set_senha(senha)
        db.session.commit()
        session["colab_ext_id"] = colab.id
        flash("Senha definida. Bem-vindo!", "success")
        return redirect(url_for("almox.extintor_campo", qr_uid=qr_uid))
    if colab.check_senha(senha):
        session["colab_ext_id"] = colab.id
        return redirect(url_for("almox.extintor_campo", qr_uid=qr_uid))
    flash("Senha inválida.", "danger")
    return render_template("almox/extintor_login.html", e=e, etapa="login")


@almox_bp.route("/e/<qr_uid>/sair")
def extintor_campo_sair(qr_uid):
    session.pop("colab_ext_id", None)
    return redirect(url_for("almox.extintor_campo", qr_uid=qr_uid))


@almox_bp.route("/extintores/pendencias")
@_guard("pode_extintores")
def pendencias_etiqueta():
    abertas = (PendenciaEtiqueta.query.filter_by(resolvida=False)
               .order_by(PendenciaEtiqueta.aberta_em.desc()).all())
    resolvidas = (PendenciaEtiqueta.query.filter_by(resolvida=True)
                  .order_by(PendenciaEtiqueta.resolvida_em.desc()).limit(30).all())
    return render_template("almox/pendencias_etiqueta.html", abertas=abertas, resolvidas=resolvidas)


@almox_bp.route("/extintores/pendencias/<int:pid>/baixar", methods=["POST"])
@_guard("pode_extintores")
def pendencia_baixar(pid):
    p = db.session.get(PendenciaEtiqueta, pid) or abort(404)
    p.resolvida = True
    p.resolvida_em = _dt.utcnow()
    p.resolvida_por = current_user.nome
    _log("Extintor", f"Pendência de etiqueta baixada: {p.extintor_cod} ({p.local})")
    db.session.commit()
    flash("Pendência de etiqueta resolvida.", "success")
    return redirect(url_for("almox.pendencias_etiqueta"))


@almox_bp.route("/extintores/qr")
@_guard("pode_extintores")
def extintores_qr():
    ids = request.args.get("ids") or ""
    consulta = Extintor.query.filter_by(ativo=True)
    if ids.strip():
        lista_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        consulta = consulta.filter(Extintor.id.in_(lista_ids))
    itens = consulta.order_by(Extintor.predio, Extintor.local).all()
    formato = request.args.get("formato", "a4")
    return render_template("almox/extintores_qr.html", itens=itens, qr_svg=_qr_svg, formato=formato)


@almox_bp.route("/extintores/pdf")
@_guard("pode_extintores")
def extintores_pdf():
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    import io
    from flask import Response
    predio = request.args.get("predio") or ""
    consulta = Extintor.query.filter_by(ativo=True)
    if predio:
        consulta = consulta.filter_by(predio=predio)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=12 * mm, bottomMargin=12 * mm,
                            leftMargin=10 * mm, rightMargin=10 * mm)
    styles = getSampleStyleSheet()
    elems = [Paragraph("Extintores — " + (predio or "Todos os prédios"), styles["Title"]), Spacer(1, 6)]
    data = [["Código", "Prédio", "Local", "Tipo/Carga", "Classe", "Validade", "TH", "Situação"]]
    for e in consulta.order_by(Extintor.predio, Extintor.local, Extintor.codigo).all():
        k, lbl, _ = _situacao_extintor(e)
        data.append([e.codigo or "", e.predio or "", e.local or "", e.tipo or "", e.classe or "",
                     _competencia(e.validade), _competencia(e.teste_hidrostatico), lbl])
    if len(data) == 1:
        data.append(["—"] * 8)
    t = Table(data, repeatRows=1,
              colWidths=[24 * mm, 22 * mm, 60 * mm, 34 * mm, 16 * mm, 24 * mm, 24 * mm, 40 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF5246")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f4")]),
    ]))
    elems.append(t)
    doc.build(elems)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=extintores.pdf"})



# ---------- COLABORADORES ----------
@almox_bp.route("/colaboradores")
@_guard("pode_colaboradores")
def colaboradores():
    itens = Colaborador.query.filter_by(ativo=True).order_by(Colaborador.nome).all()
    papeis = PapelColaborador.query.filter_by(ativo=True).order_by(PapelColaborador.nome).all()
    return render_template("almox/colaboradores.html", itens=itens, papeis=papeis)


@almox_bp.route("/colaboradores/novo", methods=["POST"])
@_guard("pode_colaboradores")
def colaborador_novo():
    import secrets
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome completo do colaborador.", "danger")
        return redirect(url_for("almox.colaboradores"))
    papel = "COLABORADOR DIVERSO"   # Etapa 2.5 — cadastro pelo módulo é sempre diverso
    uid = "COL-" + secrets.token_hex(4).upper()
    while Colaborador.query.filter_by(qr_uid=uid).first():
        uid = "COL-" + secrets.token_hex(4).upper()
    c = Colaborador(nome=nome.upper(), cpf=(request.form.get("cpf") or "").strip(),
                    empresa=(request.form.get("empresa") or "").strip().upper(),
                    cargo=(request.form.get("cargo") or "").strip().upper(),
                    papel=papel, qr_uid=uid)
    db.session.add(c)
    _log("Colaborador", f"Colaborador cadastrado: {c.nome} ({papel})")
    db.session.commit()
    flash("Colaborador cadastrado. Imprima o QR na coluna de ações.", "success")
    return redirect(url_for("almox.colaboradores"))


@almox_bp.route("/colaboradores/<int:cid>/desativar", methods=["POST"])
@_guard("pode_colaboradores")
def colaborador_desativar(cid):
    c = db.session.get(Colaborador, cid) or abort(404)
    c.ativo = False
    _log("Colaborador", f"Colaborador desativado: {c.nome}")
    db.session.commit()
    flash("Colaborador desativado.", "success")
    return redirect(url_for("almox.colaboradores"))


@almox_bp.route("/colaboradores/<int:cid>/reset-senha", methods=["POST"])
@_guard("pode_colaboradores")
def colaborador_reset_senha(cid):
    c = db.session.get(Colaborador, cid) or abort(404)
    c.senha_hash = None
    _log("Colaborador", f"Senha resetada: {c.nome}")
    db.session.commit()
    flash(f"Senha de {c.nome} resetada. No próximo uso ele define uma nova.", "success")
    return redirect(url_for("almox.colaboradores"))


@almox_bp.route("/colaboradores/qr")
@_guard("pode_colaboradores")
def colaboradores_qr():
    ids = request.args.get("ids") or ""
    consulta = Colaborador.query.filter_by(ativo=True)
    if ids.strip():
        lista_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        consulta = consulta.filter(Colaborador.id.in_(lista_ids))
    itens = consulta.order_by(Colaborador.nome).all()
    formato = request.args.get("formato", "foto")   # 'foto' | 'termica'
    return render_template("almox/colaboradores_qr.html", itens=itens, qr_svg=_qr_svg, formato=formato)


def _admin_only(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ---------- PAPÉIS DE COLABORADOR (somente ADMIN) ----------
@almox_bp.route("/papeis")
@_admin_only
def papeis():
    itens = PapelColaborador.query.order_by(PapelColaborador.nome).all()
    return render_template("almox/papeis.html", itens=itens, tarefas=TAREFAS_COLABORADOR)


@almox_bp.route("/papeis/novo", methods=["POST"])
@_admin_only
def papel_novo():
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do papel.", "danger")
        return redirect(url_for("almox.papeis"))
    if PapelColaborador.query.filter(db.func.upper(PapelColaborador.nome) == nome.upper()).first():
        flash("Já existe um papel com esse nome.", "warning")
        return redirect(url_for("almox.papeis"))
    validas = {k for k, _ in TAREFAS_COLABORADOR}
    escolhidas = [t for t in request.form.getlist("tarefas") if t in validas]
    db.session.add(PapelColaborador(nome=nome.upper(), tarefas=",".join(escolhidas)))
    _log("Papel", f"Papel cadastrado: {nome.upper()}")
    db.session.commit()
    flash("Papel cadastrado.", "success")
    return redirect(url_for("almox.papeis"))


@almox_bp.route("/papeis/<int:pid>/editar", methods=["POST"])
@_admin_only
def papel_editar(pid):
    p = db.session.get(PapelColaborador, pid) or abort(404)
    validas = {k for k, _ in TAREFAS_COLABORADOR}
    p.tarefas = ",".join(t for t in request.form.getlist("tarefas") if t in validas)
    _log("Papel", f"Papel editado: {p.nome}")
    db.session.commit()
    flash("Papel atualizado.", "success")
    return redirect(url_for("almox.papeis"))


@almox_bp.route("/papeis/<int:pid>/toggle", methods=["POST"])
@_admin_only
def papel_toggle(pid):
    p = db.session.get(PapelColaborador, pid) or abort(404)
    p.ativo = not p.ativo
    db.session.commit()
    return redirect(url_for("almox.papeis"))


# ---------- RELATÓRIO DE CHAVES ----------
def _filtra_movimentacoes():
    """Aplica os filtros da querystring e devolve (lista, contexto_filtros)."""
    from datetime import datetime as _dt
    qy = MovimentacaoChave.query
    di = request.args.get("data_ini") or ""
    dfim = request.args.get("data_fim") or ""
    chave_id = request.args.get("chave_id") or ""
    colaborador = (request.args.get("colaborador") or "").strip()
    quadro = (request.args.get("quadro") or "").strip()
    acao = request.args.get("acao") or ""
    if di:
        try: qy = qy.filter(MovimentacaoChave.criado_em >= _dt.strptime(di, "%Y-%m-%d"))
        except ValueError: pass
    if dfim:
        try:
            fim = _dt.strptime(dfim, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            qy = qy.filter(MovimentacaoChave.criado_em <= fim)
        except ValueError: pass
    if chave_id.isdigit():
        qy = qy.filter(MovimentacaoChave.chave_id == int(chave_id))
    if colaborador:
        qy = qy.filter(db.func.upper(MovimentacaoChave.colaborador_nome).like(f"%{colaborador.upper()}%"))
    if quadro:
        qy = qy.filter(db.func.upper(MovimentacaoChave.quadro_nome).like(f"%{quadro.upper()}%"))
    if acao in ("retirada", "devolucao"):
        qy = qy.filter(MovimentacaoChave.acao == acao)
    movs = qy.order_by(MovimentacaoChave.criado_em.desc()).all()
    ctx = dict(data_ini=di, data_fim=dfim, chave_id=chave_id, colaborador=colaborador,
               quadro=quadro, acao=acao)
    return movs, ctx


@almox_bp.route("/chaves/relatorio")
@_guard("pode_chaves")
def relatorio_chaves():
    movs, ctx = _filtra_movimentacoes()
    # Resumos
    retiradas = [m for m in movs if m.acao == "retirada"]
    total_retiradas = len(retiradas)
    colabs_distintos = len({(m.colaborador_nome or "").upper() for m in retiradas})
    # ranking chaves e colaboradores (por retiradas)
    from collections import Counter
    rk_chaves = Counter((m.chave_desc or "—") for m in retiradas).most_common(10)
    rk_colabs = Counter((m.colaborador_nome or "—") for m in retiradas).most_common(10)
    # situação atual: chaves em uso
    em_uso = Chave.query.filter_by(ativo=True, status="Em uso").order_by(Chave.descricao).all()
    chaves = Chave.query.filter_by(ativo=True).order_by(Chave.descricao).all()
    return render_template("almox/relatorio_chaves.html", movs=movs, ctx=ctx,
                           total_retiradas=total_retiradas, colabs_distintos=colabs_distintos,
                           rk_chaves=rk_chaves, rk_colabs=rk_colabs, em_uso=em_uso, chaves=chaves)


@almox_bp.route("/chaves/relatorio/csv")
@_guard("pode_chaves")
def relatorio_chaves_csv():
    import csv, io
    movs, _ = _filtra_movimentacoes()
    buf = io.StringIO()
    buf.write("\ufeff")   # BOM p/ Excel abrir acentos certo
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Data/Hora", "Ação", "Chave", "Quadro", "Colaborador", "Estava com (devolução)", "Operador"])
    for m in movs:
        w.writerow([m.criado_em.strftime("%d/%m/%Y %H:%M") if m.criado_em else "",
                    m.acao, m.chave_desc or "", m.quadro_nome or "",
                    m.colaborador_nome or "",
                    (m.retirado_por or "") if m.acao == "devolucao" else "",
                    (m.operador.nome if m.operador else "")])
    from flask import Response
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=relatorio_chaves.csv"})


@almox_bp.route("/chaves/relatorio/pdf")
@_guard("pode_chaves")
def relatorio_chaves_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    import io
    from flask import Response
    movs, ctx = _filtra_movimentacoes()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=12*mm, rightMargin=12*mm)
    styles = getSampleStyleSheet()
    elems = [Paragraph("Relatório de Movimentações de Chaves", styles["Title"])]
    periodo = f"Período: {ctx['data_ini'] or 'início'} a {ctx['data_fim'] or 'hoje'}"
    elems.append(Paragraph(periodo, styles["Normal"]))
    elems.append(Spacer(1, 6))
    data = [["Data/Hora", "Ação", "Chave", "Quadro", "Colaborador", "Estava com", "Operador"]]
    for m in movs:
        data.append([m.criado_em.strftime("%d/%m/%y %H:%M") if m.criado_em else "",
                     m.acao, m.chave_desc or "", m.quadro_nome or "",
                     m.colaborador_nome or "",
                     (m.retirado_por or "") if m.acao == "devolucao" else "",
                     (m.operador.nome if m.operador else "")])
    if len(data) == 1:
        data.append(["—", "—", "—", "—", "—", "—", "—"])
    t = Table(data, repeatRows=1, colWidths=[22*mm, 17*mm, 33*mm, 33*mm, 30*mm, 30*mm, 22*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FF5246")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f4")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elems.append(t)
    doc.build(elems)
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=relatorio_chaves.pdf"})


# ==================== COLETOR (online — fase 1) ====================
# Aparelho dedicado do almoxarifado (logado como ALMOXARIFADO). Lê QR pela câmera.
# Identifica o colaborador por QR + senha e movimenta CHAVES. Material entra depois.
from flask import jsonify


@almox_bp.route("/coletor")
@modulo_required
def coletor():
    return render_template("almox/coletor.html")


def _uid_limpo(qr_uid):
    """Aceita tanto 'CHAVE:CH-XXXX' / 'COLAB:COL-XXXX' quanto só o uid."""
    s = (qr_uid or "").strip()
    if ":" in s:
        s = s.split(":", 1)[1]
    return s


@almox_bp.route("/coletor/api/colaborador/<path:qr_uid>")
@modulo_required
def coletor_api_colaborador(qr_uid):
    uid = _uid_limpo(qr_uid)
    c = Colaborador.query.filter_by(qr_uid=uid, ativo=True).first()
    if not c:
        return jsonify(ok=False, erro="Colaborador não encontrado."), 404
    return jsonify(ok=True, id=c.id, nome=c.nome, tem_senha=c.tem_senha)


@almox_bp.route("/coletor/api/chave/<path:qr_uid>")
@modulo_required
def coletor_api_chave(qr_uid):
    uid = _uid_limpo(qr_uid)
    c = Chave.query.filter_by(qr_uid=uid, ativo=True).first()
    if not c:
        return jsonify(ok=False, erro="Chave não encontrada."), 404
    return jsonify(ok=True, id=c.id, descricao=c.descricao, quadro=c.quadro_nome,
                   status=c.status, com_quem=c.com_quem)


@almox_bp.route("/coletor/api/confirmar", methods=["POST"])
@modulo_required
def coletor_api_confirmar():
    """Aplica as ações de chave confirmadas pela senha do colaborador.
    payload: {colaborador_id, senha, acoes:[{chave_id, acao: 'retirar'|'devolver'}]}"""
    data = request.get_json(silent=True) or {}
    colab = db.session.get(Colaborador, data.get("colaborador_id") or 0)
    if not colab or not colab.ativo:
        return jsonify(ok=False, erro="Colaborador inválido."), 400
    senha = data.get("senha") or ""
    # Primeiro uso define a senha; depois valida.
    if not colab.tem_senha:
        if len(senha) < 4:
            return jsonify(ok=False, erro="Primeiro uso: defina uma senha de ao menos 4 dígitos."), 400
        colab.set_senha(senha)
    elif not colab.check_senha(senha):
        return jsonify(ok=False, erro="Senha do colaborador inválida."), 403

    acoes = data.get("acoes") or []
    if not acoes:
        return jsonify(ok=False, erro="Nenhuma chave para confirmar."), 400
    feitas = []
    for a in acoes:
        c = db.session.get(Chave, a.get("chave_id") or 0)
        if not c or not c.ativo:
            continue
        acao = a.get("acao")
        if acao == "retirar" and c.status == "Disponível":
            c.status = "Em uso"
            c.com_quem = colab.nome
            db.session.add(MovimentacaoChave(chave_id=c.id, chave_desc=c.descricao,
                           quadro_nome=c.quadro_nome, colaborador_id=colab.id,
                           colaborador_nome=colab.nome, acao="retirada",
                           operador_id=current_user.id))
            feitas.append(f"Retirou {c.descricao}")
        elif acao == "devolver" and c.status == "Em uso":
            retirou = c.com_quem or "—"
            c.status = "Disponível"
            c.com_quem = None
            db.session.add(MovimentacaoChave(chave_id=c.id, chave_desc=c.descricao,
                           quadro_nome=c.quadro_nome, colaborador_id=colab.id,
                           colaborador_nome=colab.nome, retirado_por=retirou,
                           acao="devolucao", operador_id=current_user.id))
            feitas.append(f"Devolveu {c.descricao}")
    _log("Coletor", f"{colab.nome}: " + "; ".join(feitas) if feitas else f"{colab.nome}: sem ações válidas")
    db.session.commit()
    return jsonify(ok=True, resumo=feitas, colaborador=colab.nome)
