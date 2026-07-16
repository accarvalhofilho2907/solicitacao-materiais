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
                     TAREFAS_PERFIL, TAREFAS_GRUPOS,
                     InspecaoExtintor, PendenciaEtiqueta, CHECK_EXTINTOR, ITEM_ETIQUETA_EXTINTOR,
                     ProdutoAlmox, MovimentacaoMaterial, LocalAlmox)


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
    {"slug": "materiais",   "nome": "Material (estoque)",              "icone": "📦", "liberado": True, "endpoint": "almox.materiais"},
    {"slug": "mat_mov",     "nome": "Movimentações de material",       "icone": "📊", "liberado": True, "endpoint": "almox.materiais_mov"},
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
    from .models import Usuario as _U
    autor_id = current_user.id if isinstance(current_user, _U) else None
    db.session.add(AlmoxLog(autor_id=autor_id, autor_nome=getattr(current_user, "nome", None),
                            categoria=categoria, detalhe=detalhe))


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
    # Painel: números do dia a dia (usa dados já existentes)
    resumo = {"chaves_em_uso": 0, "ext_irregular": 0, "ext_prox": 0,
              "mat_baixo": 0, "pend_etiqueta": 0}
    try:
        resumo["chaves_em_uso"] = Chave.query.filter_by(ativo=True, status="Em uso").count()
        for e in Extintor.query.filter_by(ativo=True).all():
            k = _situacao_extintor(e)[0]
            if k in ("IRREGULAR", "VENCIDO", "EM_RECARGA"):
                resumo["ext_irregular"] += 1
            elif k == "PROX_VENC":
                resumo["ext_prox"] += 1
        resumo["mat_baixo"] = sum(1 for p in ProdutoAlmox.query.filter_by(ativo=True).all() if p.abaixo_minimo)
        resumo["pend_etiqueta"] = PendenciaEtiqueta.query.filter_by(resolvida=False).count()
    except Exception:
        pass
    return render_template("almox/home.html", topicos=topicos, resumo=resumo)


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


def _resolver_quadro(form):
    """Resolve o quadro pelo id (select) ou, como fallback, pelo nome digitado."""
    qid = form.get("quadro_chave_id") or None
    if qid and str(qid).isdigit():
        return int(qid)
    nome = (form.get("quadro_nome") or form.get("quadro") or "").strip()
    if nome:
        q = QuadroChave.query.filter(db.func.upper(QuadroChave.nome) == nome.upper()).first()
        if q:
            return q.id
    return None


@almox_bp.route("/chaves/nova", methods=["POST"])
@_guard("pode_chaves")
def chave_nova():
    import secrets
    desc = (request.form.get("descricao") or "").strip()
    if not desc:
        flash("Informe a descrição da chave.", "danger")
        return redirect(url_for("almox.chaves"))
    quadro_id = _resolver_quadro(request.form)
    uid = "CH-" + secrets.token_hex(4).upper()
    while Chave.query.filter_by(qr_uid=uid).first():
        uid = "CH-" + secrets.token_hex(4).upper()
    c = Chave(descricao=desc.upper(), quadro_chave_id=quadro_id,
              qr_uid=uid, status="Disponível")
    db.session.add(c)
    _log("Chave", f"Chave cadastrada: {c.descricao}" + (f" (quadro: {c.quadro_nome})" if quadro_id else " (sem quadro)"))
    db.session.commit()
    flash("Chave cadastrada." + ("" if quadro_id else " (Sem quadro — você pode definir depois em Editar.)"), "success")
    return redirect(url_for("almox.chaves"))


@almox_bp.route("/chaves/<int:cid>/editar", methods=["POST"])
@_guard("pode_chaves")
def chave_editar(cid):
    c = db.session.get(Chave, cid) or abort(404)
    mudancas = []
    nova_desc = (request.form.get("descricao") or "").strip().upper()
    if nova_desc and nova_desc != (c.descricao or ""):
        mudancas.append(f"descrição: {c.descricao or '—'} → {nova_desc}")
        c.descricao = nova_desc
    novo_quadro = _resolver_quadro(request.form)
    if novo_quadro != c.quadro_chave_id:
        antigo = c.quadro_nome
        c.quadro_chave_id = novo_quadro
        mudancas.append(f"quadro: {antigo or '—'} → {c.quadro_nome or '—'}")
    if mudancas:
        _log("Chave", f"Chave {c.descricao} editada — " + "; ".join(mudancas))
        db.session.commit()
        flash("Chave atualizada.", "success")
    else:
        flash("Nada a alterar.", "info")
    return redirect(url_for("almox.chaves"))


@almox_bp.route("/chaves/<int:cid>/historico")
@_guard("pode_chaves")
def chave_historico(cid):
    c = db.session.get(Chave, cid) or abort(404)
    movs = (MovimentacaoChave.query.filter_by(chave_id=c.id)
            .order_by(MovimentacaoChave.criado_em.desc()).all())
    return render_template("almox/chave_historico.html", c=c, movs=movs)


def _op_id():
    """id do operador para gravar em operador_id (FK usuarios). None se for colaborador."""
    from .models import Usuario as _U
    return current_user.id if isinstance(current_user, _U) else None


def _resolver_colaborador(termo):
    """Acha o colaborador por QR (COL-...), CPF (só dígitos) ou nome. Devolve Colaborador ou None."""
    t = (termo or "").strip()
    if not t:
        return None
    # QR: 'COLAB:COL-XXXX' ou 'COL-XXXX'
    uid = t.split(":", 1)[1] if ":" in t else t
    c = Colaborador.query.filter_by(qr_uid=uid, ativo=True).first()
    if c:
        return c
    # CPF (só dígitos)
    dig = "".join(ch for ch in t if ch.isdigit())
    if dig:
        for col in Colaborador.query.filter(Colaborador.ativo.is_(True)).all():
            if "".join(ch for ch in (col.cpf or "") if ch.isdigit()) == dig:
                return col
    # Nome (exato, ignorando caixa)
    return Colaborador.query.filter(db.func.upper(Colaborador.nome) == t.upper(),
                                    Colaborador.ativo.is_(True)).first()


@almox_bp.route("/chaves/<int:cid>/toggle", methods=["POST"])
@_guard("pode_chaves")
def chave_toggle(cid):
    c = db.session.get(Chave, cid) or abort(404)
    if c.status == "Disponível":
        termo = request.form.get("com_quem") or ""
        colab = _resolver_colaborador(termo)
        if not colab:
            flash("Informe quem vai retirar (nome, CPF ou bipe o QR de um colaborador cadastrado).", "danger")
            return redirect(url_for("almox.chaves"))
        # Retirada pede a senha do colaborador
        senha = request.form.get("senha") or ""
        if not colab.tem_senha:
            flash(f"{colab.nome} ainda não definiu a senha. Ele define no 1º acesso (login por CPF) ou peça reset.", "warning")
            return redirect(url_for("almox.chaves"))
        if not colab.check_senha(senha):
            flash("Senha do colaborador inválida. Retirada não confirmada.", "danger")
            return redirect(url_for("almox.chaves"))
        c.status = "Em uso"
        c.com_quem = colab.nome
        db.session.add(MovimentacaoChave(
            chave_id=c.id, chave_desc=c.descricao, quadro_nome=c.quadro_nome,
            colaborador_id=colab.id, colaborador_nome=colab.nome,
            acao="retirada", operador_id=_op_id()))
        _log("Chave", f"Chave {c.descricao} retirada por {colab.nome}")
    else:
        retirou = c.com_quem or "—"
        termo = request.form.get("devolvido_por") or ""
        colab = _resolver_colaborador(termo)
        devolvedor = colab.nome if colab else (termo.strip().upper() or retirou)
        db.session.add(MovimentacaoChave(
            chave_id=c.id, chave_desc=c.descricao, quadro_nome=c.quadro_nome,
            colaborador_id=(colab.id if colab else None), colaborador_nome=devolvedor,
            retirado_por=retirou, acao="devolucao",
            operador_id=_op_id()))
        _log("Chave", f"Chave {c.descricao} devolvida por {devolvedor}" +
             (f" (estava com {retirou})" if devolvedor != retirou else ""))
        c.status = "Disponível"
        c.com_quem = None
    db.session.commit()
    return redirect(url_for("almox.chaves"))


# ----- Quadros de Chave (localizador) -----
def _backfill_qr_quadros():
    """Garante que todo quadro tenha um QR próprio (QUAD-...)."""
    import secrets
    faltando = QuadroChave.query.filter((QuadroChave.qr_uid.is_(None)) | (QuadroChave.qr_uid == "")).all()
    for q in faltando:
        uid = "QUAD-" + secrets.token_hex(4).upper()
        while QuadroChave.query.filter_by(qr_uid=uid).first():
            uid = "QUAD-" + secrets.token_hex(4).upper()
        q.qr_uid = uid
    if faltando:
        db.session.commit()


@almox_bp.route("/chaves/quadros")
@_guard("pode_chaves")
def quadros_chave():
    _backfill_qr_quadros()
    quadros = QuadroChave.query.order_by(QuadroChave.nome).all()
    return render_template("almox/quadros_chave.html", quadros=quadros)


@almox_bp.route("/chaves/quadros/novo", methods=["POST"])
@_guard("pode_chaves")
def quadro_novo():
    import secrets
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do Quadro de Chaves.", "danger")
        return redirect(url_for("almox.quadros_chave"))
    if QuadroChave.query.filter(db.func.upper(QuadroChave.nome) == nome.upper()).first():
        flash("Já existe um Quadro de Chaves com esse nome.", "warning")
        return redirect(url_for("almox.quadros_chave"))
    uid = "QUAD-" + secrets.token_hex(4).upper()
    while QuadroChave.query.filter_by(qr_uid=uid).first():
        uid = "QUAD-" + secrets.token_hex(4).upper()
    db.session.add(QuadroChave(nome=nome.upper(), qr_uid=uid))
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


@almox_bp.route("/chaves/quadros/qr")
@_guard("pode_chaves")
def quadros_qr():
    """Página de impressão dos QR dos quadros (uma etiqueta por quadro)."""
    _backfill_qr_quadros()
    ids = request.args.get("ids") or ""
    consulta = QuadroChave.query.filter_by(ativo=True)
    if ids.strip():
        lista_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        if lista_ids:
            consulta = consulta.filter(QuadroChave.id.in_(lista_ids))
    itens = consulta.order_by(QuadroChave.nome).all()
    formato = request.args.get("formato", "a4")
    return render_template("almox/quadros_qr.html", itens=itens, qr_svg=_qr_svg, formato=formato)

# ---------- EXTINTORES (Etapa 3) ----------
import json as _json
from datetime import datetime as _dt

MESES_PT = ["", "JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

SITUACAO_LABEL = {
    "NO_PRAZO": ("No prazo", "success"),
    "PROX_VENC": ("Próximo do vencimento", "warning"),
    "VENCIDO": ("Irregular / Vencido", "danger"),
    "IRREGULAR": ("Irregular / Vencido", "danger"),
    "ATENCAO": ("Atenção (etiqueta)", "info"),
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
    """Ciclo do extintor. Estados operacionais gravados em e.situacao
    (IRREGULAR/ATENCAO/EM_RECARGA/PRONTO_REPO); NO_PRAZO deriva PROX/VENCIDO das datas."""
    s = e.situacao or "NO_PRAZO"
    if s in ("EM_RECARGA", "PRONTO_REPO", "IRREGULAR", "ATENCAO"):
        return (s,) + SITUACAO_LABEL[s]
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
    import json as _json
    e = db.session.get(Extintor, eid) or abort(404)
    k, lbl, cls = _situacao_extintor(e)
    hist_raw = (InspecaoExtintor.query.filter_by(extintor_id=e.id)
                .order_by(InspecaoExtintor.criado_em.desc()).limit(30).all())
    hist = []
    for h in hist_raw:
        try:
            itens = _json.loads(h.itens_json) if h.itens_json else {}
        except Exception:
            itens = {}
        hist.append({"h": h, "itens": itens})
    colab = _colab_sessao() if not current_user.is_authenticated else None
    # itens do checklist de retorno (almox) = sem "Acesso e sinalização"
    check_retorno = [c for c in CHECK_EXTINTOR if not c.lower().startswith("acesso")]
    return render_template("almox/extintor_ficha.html", e=e, sit_k=k, sit_lbl=lbl, sit_cls=cls,
                           check=CHECK_EXTINTOR, check_retorno=check_retorno,
                           item_etiqueta=ITEM_ETIQUETA_EXTINTOR,
                           hist=hist, competencia=_competencia, meses=MESES_PT,
                           anos=_anos_range(), pode_gerir=_pode_gerir_ext(),
                           campo=(not current_user.is_authenticated), ator_colab=colab)


def _coletar_checklist(form):
    """Lê o checklist. Devolve (itens_dict, core_nok, etiqueta_nok).
    O item da etiqueta é separado (regra especial de 'Atenção')."""
    itens = {}
    core_nok = False
    for i, item in enumerate(CHECK_EXTINTOR):
        v = form.get(f"item_{i}")
        if v is None:
            continue                      # item não exibido nesse checklist (ex.: retorno)
        itens[item] = v
        if v == "nok":
            core_nok = True
    et = form.get("item_etiqueta", "na")
    itens[ITEM_ETIQUETA_EXTINTOR] = et
    return itens, core_nok, (et == "nok")


def _quem(form):
    """Quem operou: colaborador de campo (sessão) ou o usuário logado. Não usa mais campo de texto."""
    colab = _colab_sessao()
    if colab and not current_user.is_authenticated:
        return colab.nome, colab.id
    if current_user.is_authenticated:
        return current_user.nome, None
    return ("—", None)


def _aplicar_resultado(e, core_nok, et_nok, nome):
    """Define a situação do extintor conforme o checklist e trata pendências."""
    if core_nok:
        e.situacao = "IRREGULAR"          # regularização pendente até voltar ao local
        return "irregular"
    if et_nok:
        e.situacao = "ATENCAO"            # segue em uso; só pendência de etiqueta
        if not PendenciaEtiqueta.query.filter_by(extintor_id=e.id, resolvida=False).first():
            db.session.add(PendenciaEtiqueta(extintor_id=e.id, extintor_cod=e.codigo,
                           predio=e.predio, local=e.local, aberta_por=nome))
        return "irregular"
    e.situacao = "NO_PRAZO"
    return "conforme"


@almox_bp.route("/extintores/<int:eid>/inspecionar", methods=["POST"])
@_ext_acesso
def extintor_inspecionar(eid):
    import json as _json
    e = db.session.get(Extintor, eid) or abort(404)
    itens, core_nok, et_nok = _coletar_checklist(request.form)
    nome, cid = _quem(request.form)
    resultado = _aplicar_resultado(e, core_nok, et_nok, nome)
    e.inspecao = date.today()
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="inspecao",
                   resultado=resultado, itens_json=_json.dumps(itens, ensure_ascii=False),
                   etiqueta_ok=(not et_nok), obs=(request.form.get("obs") or "").strip(),
                   colaborador_id=cid, colaborador_nome=nome,
                   operador_id=getattr(current_user, "id", None)))
    if core_nok:
        _log("Extintor", f"{e.codigo} ({e.local}): inspeção IRREGULAR por {nome} — notificar ADMIN")
        msg, cat = "Inspeção registrada. Extintor IRREGULAR — leve ao Almox D6.", "warning"
    elif et_nok:
        _log("Extintor", f"{e.codigo}: etiqueta em desacordo por {nome} — pendência aberta (Atenção)")
        msg, cat = "Inspeção registrada. Etiqueta em desacordo: status Atenção + pendência.", "warning"
    else:
        _log("Extintor", f"{e.codigo} ({e.local}): inspeção conforme por {nome}")
        msg, cat = "Inspeção conforme registrada.", "success"
    db.session.commit()
    flash(msg, cat)
    return _redir_ficha(e)


@almox_bp.route("/extintores/<int:eid>/reposicao", methods=["POST"])
@_ext_acesso
def extintor_reposicao(eid):
    """Troca programada: substitui o extintor, faz o checklist do NOVO e lança nova validade/TH."""
    import json as _json
    e = db.session.get(Extintor, eid) or abort(404)
    itens, core_nok, et_nok = _coletar_checklist(request.form)
    nome, cid = _quem(request.form)
    nova_val = _parse_mmaaaa("validade", request.form)
    novo_th = _parse_mmaaaa("th", request.form)
    if nova_val:
        e.validade = nova_val
    if novo_th:
        e.teste_hidrostatico = novo_th
    resultado = _aplicar_resultado(e, core_nok, et_nok, nome)
    e.inspecao = date.today()
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="reposicao",
                   resultado=resultado, itens_json=_json.dumps(itens, ensure_ascii=False),
                   etiqueta_ok=(not et_nok), colaborador_id=cid, colaborador_nome=nome,
                   operador_id=getattr(current_user, "id", None),
                   obs=f"Troca programada. Validade {_competencia(e.validade)}, TH {_competencia(e.teste_hidrostatico)}"))
    _log("Extintor", f"{e.codigo}: reposição/troca por {nome} "
                     f"(validade {_competencia(e.validade)}, TH {_competencia(e.teste_hidrostatico)})")
    db.session.commit()
    flash("Reposição (troca) registrada.", "success")
    return _redir_ficha(e)


@almox_bp.route("/extintores/<int:eid>/regularizar", methods=["POST"])
@_ext_acesso
def extintor_regularizar(eid):
    """Único caminho na ficha Irregular: Levado ao Almox D6 (sem pedir nome)."""
    e = db.session.get(Extintor, eid) or abort(404)
    nome, cid = _quem(request.form)
    e.situacao = "EM_RECARGA"
    e.retirado_por = nome
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="retirada",
                   resultado="irregular", colaborador_id=cid, colaborador_nome=nome,
                   operador_id=getattr(current_user, "id", None)))
    _log("Extintor", f"{e.codigo}: levado ao Almox D6 p/ recarga por {nome}")
    db.session.commit()
    flash("Extintor marcado como Em recarga (levado ao Almox D6).", "info")
    return _redir_ficha(e)


@almox_bp.route("/extintores/<int:eid>/conferir", methods=["POST"])
@_ext_acesso
def extintor_conferir(eid):
    """Conferência do Almoxarifado no retorno (sem 'Acesso', sem nome) → Pronto p/ reposição."""
    import json as _json
    e = db.session.get(Extintor, eid) or abort(404)
    if not _pode_gerir_ext():
        abort(403)
    itens, core_nok, et_nok = _coletar_checklist(request.form)
    nome, cid = _quem(request.form)
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="conferencia",
                   resultado=("irregular" if (core_nok or et_nok) else "conforme"),
                   itens_json=_json.dumps(itens, ensure_ascii=False), etiqueta_ok=(not et_nok),
                   colaborador_id=cid, colaborador_nome=nome,
                   operador_id=getattr(current_user, "id", None)))
    if et_nok and not PendenciaEtiqueta.query.filter_by(extintor_id=e.id, resolvida=False).first():
        db.session.add(PendenciaEtiqueta(extintor_id=e.id, extintor_cod=e.codigo,
                       predio=e.predio, local=e.local, aberta_por=nome))
    e.situacao = "PRONTO_REPO"
    _log("Extintor", f"{e.codigo}: conferido no Almox (pronto p/ reposição) por {nome}")
    db.session.commit()
    flash("Conferência registrada. Extintor Pronto para reposição.", "success")
    return _redir_ficha(e)


@almox_bp.route("/extintores/<int:eid>/repor", methods=["POST"])
@_ext_acesso
def extintor_repor(eid):
    """Reposição final: volta ao local (sem nome), atualiza validade/TH (MMM+AAAA) → No prazo."""
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
    e.situacao = "NO_PRAZO"        # voltou ao local: sai da pendência de regularização
    e.retirado_por = None
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="reposicao",
                   resultado="conforme", colaborador_id=cid, colaborador_nome=nome,
                   operador_id=getattr(current_user, "id", None),
                   obs=f"Reposto no local. Validade {_competencia(e.validade)}, TH {_competencia(e.teste_hidrostatico)}"))
    _log("Extintor", f"{e.codigo}: reposto no local por {nome}")
    db.session.commit()
    flash("Reposição concluída. Extintor No prazo.", "success")
    return _redir_ficha(e)


@almox_bp.route("/extintores/<int:eid>/desativar", methods=["POST"])
@_guard("pode_extintores")
def extintor_desativar(eid):
    e = db.session.get(Extintor, eid) or abort(404)
    e.ativo = False
    _log("Extintor", f"{e.codigo}: extintor desativado por {current_user.nome}")
    db.session.commit()
    flash("Extintor desativado.", "success")
    return redirect(url_for("almox.extintores"))


@almox_bp.route("/extintores/cadastro")
@_guard("pode_extintores")
def extintor_cadastro():
    def distintos(col):
        vals = db.session.query(col).filter(col.isnot(None), col != "").distinct().all()
        return sorted({v[0] for v in vals if v[0]})
    sugestoes = {
        "predio": distintos(Extintor.predio),
        "local": distintos(Extintor.local),
        "tipo": distintos(Extintor.tipo),
        "classe": distintos(Extintor.classe),
    }
    return render_template("almox/extintor_cadastro.html", sugestoes=sugestoes,
                           check=CHECK_EXTINTOR, item_etiqueta=ITEM_ETIQUETA_EXTINTOR,
                           meses=MESES_PT, anos=_anos_range())


@almox_bp.route("/extintores/novo", methods=["POST"])
@_guard("pode_extintores")
def extintor_novo():
    import secrets, json as _json
    predio = (request.form.get("predio") or "").strip().upper()
    local = (request.form.get("local") or "").strip()
    tipo = (request.form.get("tipo") or "").strip().upper()
    classe = (request.form.get("classe") or "").strip().upper()
    if not local:
        flash("Informe ao menos o local do extintor.", "danger")
        return redirect(url_for("almox.extintores"))
    seq = (Extintor.query.count() or 0) + 1
    codigo = f"EXT{seq:04d}"
    while Extintor.query.filter_by(codigo=codigo).first():
        seq += 1
        codigo = f"EXT{seq:04d}"
    uid = "EXT-" + secrets.token_hex(4).upper()
    while Extintor.query.filter_by(qr_uid=uid).first():
        uid = "EXT-" + secrets.token_hex(4).upper()
    e = Extintor(codigo=codigo, predio=predio, local=local, tipo=tipo, classe=classe,
                 validade=_parse_mmaaaa("validade", request.form),
                 teste_hidrostatico=_parse_mmaaaa("th", request.form),
                 situacao="NO_PRAZO", status="No Local", qr_uid=uid, ativo=True)
    db.session.add(e)
    db.session.flush()
    # checklist inicial de conferência
    itens, core_nok, et_nok = _coletar_checklist(request.form)
    nome, cid = _quem(request.form)
    resultado = _aplicar_resultado(e, core_nok, et_nok, nome)
    e.inspecao = date.today()
    db.session.add(InspecaoExtintor(extintor_id=e.id, extintor_cod=e.codigo, tipo="inspecao",
                   resultado=resultado, itens_json=_json.dumps(itens, ensure_ascii=False),
                   etiqueta_ok=(not et_nok), colaborador_id=cid, colaborador_nome=nome,
                   operador_id=getattr(current_user, "id", None), obs="Cadastro / conferência inicial"))
    _log("Extintor", f"Extintor cadastrado: {codigo} ({local}) por {nome}")
    db.session.commit()
    flash(f"Extintor {codigo} cadastrado.", "success")
    return redirect(url_for("almox.extintor_ficha", eid=e.id))


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
    # Se o extintor estava em "Atenção" só pela etiqueta, volta a No prazo
    ext = db.session.get(Extintor, p.extintor_id) if p.extintor_id else None
    if ext and ext.situacao == "ATENCAO":
        ext.situacao = "NO_PRAZO"
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
PAPEIS_COLAB = [("COLABORADOR DIVERSO", "Colaborador diverso"),
                ("SOLICITANTE", "Solicitante"),
                ("ALMOXARIFADO", "Almoxarifado"),
                ("VISUALIZADOR", "Visualizador"),
                ("ADMIN", "Admin")]


@almox_bp.route("/colaboradores")
@_guard("pode_colaboradores")
def colaboradores():
    from .models import Fornecedor
    itens = Colaborador.query.filter_by(ativo=True).order_by(Colaborador.nome).all()
    papeis = PapelColaborador.query.filter_by(ativo=True).order_by(PapelColaborador.nome).all()
    empresas = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome).all()
    return render_template("almox/colaboradores.html", itens=itens, papeis=papeis, empresas=empresas,
                           papeis_colab=PAPEIS_COLAB, pode_papel=current_user.is_admin,
                           is_master=current_user.is_master)


@almox_bp.route("/colaboradores/novo", methods=["POST"])
@_guard("pode_colaboradores")
def colaborador_novo():
    import secrets
    nome = (request.form.get("nome") or "").strip()
    cpf_bruto = (request.form.get("cpf") or "").strip()
    cpf = "".join(ch for ch in cpf_bruto if ch.isdigit())
    email = (request.form.get("email") or "").strip().lower()
    if not nome:
        flash("Informe o nome completo do colaborador.", "danger")
        return redirect(url_for("almox.colaboradores"))
    if not cpf:
        flash("CPF é obrigatório (só números).", "danger")
        return redirect(url_for("almox.colaboradores"))
    for c0 in Colaborador.query.filter(Colaborador.ativo.is_(True)).all():
        if "".join(ch for ch in (c0.cpf or "") if ch.isdigit()) == cpf:
            flash("Já existe um colaborador ativo com esse CPF.", "warning")
            return redirect(url_for("almox.colaboradores"))
    # Perfil de acesso: só Admin escolhe; senão entra sem perfil administrativo.
    papel = "COLABORADOR DIVERSO"
    if current_user.is_admin:
        escolhido = (request.form.get("papel") or "").strip().upper()
        nomes = {p.nome.upper() for p in PapelColaborador.query.all()}
        if escolhido and escolhido in nomes:
            papel = escolhido
    uid = "COL-" + secrets.token_hex(4).upper()
    while Colaborador.query.filter_by(qr_uid=uid).first():
        uid = "COL-" + secrets.token_hex(4).upper()
    c = Colaborador(nome=nome.upper(), cpf=cpf, email=(email or None),
                    empresa=(request.form.get("empresa") or "").strip().upper(),
                    cargo=(request.form.get("cargo") or "").strip().upper(),
                    papel=papel, qr_uid=uid)
    db.session.add(c)
    _log("Colaborador", f"Colaborador cadastrado: {c.nome} (CPF {cpf}, papel {papel})")
    db.session.commit()
    flash("Colaborador cadastrado. Ele define a senha no 1º acesso (CPF).", "success")
    return redirect(url_for("almox.colaboradores"))


@almox_bp.route("/colaboradores/<int:cid>", methods=["GET"])
@_guard("pode_colaboradores")
def colaborador_perfil(cid):
    from .models import Fornecedor, HistoricoColaborador
    c = db.session.get(Colaborador, cid) or abort(404)
    empresas = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome).all()
    hist = (HistoricoColaborador.query.filter_by(colaborador_id=c.id)
            .order_by(HistoricoColaborador.criado_em.desc()).all())
    papeis = PapelColaborador.query.filter_by(ativo=True).order_by(PapelColaborador.nome).all()
    return render_template("almox/colaborador_perfil.html", c=c, empresas=empresas,
                           papeis=papeis, papeis_colab=PAPEIS_COLAB, hist=hist,
                           pode_papel=current_user.is_admin, is_master=current_user.is_master)


@almox_bp.route("/colaboradores/<int:cid>/editar", methods=["POST"])
@_guard("pode_colaboradores")
def colaborador_editar(cid):
    from .models import HistoricoColaborador
    c = db.session.get(Colaborador, cid) or abort(404)
    autor = current_user.nome
    mudancas = []

    def registrar(campo, de, para):
        db.session.add(HistoricoColaborador(colaborador_id=c.id, colaborador_nome=c.nome,
                       campo=campo, de=de or "—", para=para or "—", alterado_por_nome=autor))
        mudancas.append(campo)

    # Cargo e empresa: Admin/Master e Almoxarifado podem
    novo_cargo = (request.form.get("cargo") or "").strip().upper()
    if novo_cargo != (c.cargo or ""):
        registrar("cargo", c.cargo, novo_cargo); c.cargo = novo_cargo
    nova_emp = (request.form.get("empresa") or "").strip().upper()
    if nova_emp != (c.empresa or ""):
        registrar("empresa", c.empresa, nova_emp); c.empresa = nova_emp

    # Perfil de acesso: só Admin
    if current_user.is_admin:
        novo_papel = (request.form.get("papel") or c.papel or "").strip().upper()
        nomes = {p.nome.upper() for p in PapelColaborador.query.all()}
        if novo_papel and novo_papel in nomes and novo_papel != (c.papel or "").upper():
            registrar("papel", c.papel, novo_papel); c.papel = novo_papel
    elif request.form.get("papel") and request.form.get("papel").strip().upper() != (c.papel or "").upper():
        flash("Apenas Admin altera o perfil de acesso. As demais alterações foram salvas.", "warning")

    if mudancas:
        _log("Colaborador", f"{c.nome}: alterado ({', '.join(mudancas)}) por {autor}")
    db.session.commit()
    flash("Alterações salvas." if mudancas else "Nada a alterar.", "success" if mudancas else "info")
    return redirect(url_for("almox.colaborador_perfil", cid=c.id))


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
    return render_template("almox/papeis.html", itens=itens,
                           tarefas_perfil=TAREFAS_PERFIL, grupos=TAREFAS_GRUPOS)


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
    validas = {k for k, _r, _g, fut in TAREFAS_PERFIL if not fut} | {k for k, _ in TAREFAS_COLABORADOR}
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
    validas = {k for k, _r, _g, fut in TAREFAS_PERFIL if not fut} | {k for k, _ in TAREFAS_COLABORADOR}
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
    c = _resolver_colaborador(_uid_limpo(qr_uid)) or _resolver_colaborador(qr_uid)
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
                           operador_id=_op_id()))
            feitas.append(f"Retirou {c.descricao}")
        elif acao == "devolver" and c.status == "Em uso":
            retirou = c.com_quem or "—"
            c.status = "Disponível"
            c.com_quem = None
            db.session.add(MovimentacaoChave(chave_id=c.id, chave_desc=c.descricao,
                           quadro_nome=c.quadro_nome, colaborador_id=colab.id,
                           colaborador_nome=colab.nome, retirado_por=retirou,
                           acao="devolucao", operador_id=_op_id()))
            feitas.append(f"Devolveu {c.descricao}")
    _log("Coletor", f"{colab.nome}: " + "; ".join(feitas) if feitas else f"{colab.nome}: sem ações válidas")
    db.session.commit()
    return jsonify(ok=True, resumo=feitas, colaborador=colab.nome)


# ==================== MATERIAL (estoque com quantidade) ====================
def _num(v, default=0.0):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return default


@almox_bp.route("/materiais")
@_guard("pode_almox_modulo")
def materiais():
    itens = ProdutoAlmox.query.filter_by(ativo=True).order_by(ProdutoAlmox.nome).all()
    n_baixo = sum(1 for p in itens if p.abaixo_minimo)
    locais = LocalAlmox.query.filter_by(ativo=True).order_by(LocalAlmox.nome).all()
    return render_template("almox/materiais.html", itens=itens, n_baixo=n_baixo, locais=locais)


@almox_bp.route("/materiais/novo", methods=["POST"])
@_guard("pode_almox_modulo")
def material_novo():
    import secrets
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do material.", "danger")
        return redirect(url_for("almox.materiais"))
    uid = "MAT-" + secrets.token_hex(4).upper()
    while ProdutoAlmox.query.filter_by(qr_uid=uid).first():
        uid = "MAT-" + secrets.token_hex(4).upper()
    local_id = request.form.get("local_id") or None
    if not local_id:
        temp = LocalAlmox.query.filter_by(temporaria=True).first()
        local_id = temp.id if temp else None
    p = ProdutoAlmox(codigo=(request.form.get("codigo") or "").strip().upper(),
                     nome=nome.upper(), unidade=(request.form.get("unidade") or "UN").strip().upper(),
                     categoria=(request.form.get("categoria") or "").strip().upper(),
                     saldo=_num(request.form.get("saldo_inicial"), 0),
                     saldo_minimo=_num(request.form.get("saldo_minimo"), 0),
                     local_id=int(local_id) if local_id else None, qr_uid=uid)
    db.session.add(p)
    db.session.flush()
    if p.saldo:
        db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="entrada",
                       quantidade=p.saldo, saldo_apos=p.saldo, operador_id=_op_id(),
                       obs="Saldo inicial de cadastro"))
    _log("Material", f"Material cadastrado: {p.nome} (saldo {p.saldo} {p.unidade})")
    db.session.commit()
    flash("Material cadastrado.", "success")
    return redirect(url_for("almox.materiais"))


# ----- Locais de estocagem -----
@almox_bp.route("/materiais/locais")
@_guard("pode_almox_modulo")
def locais():
    itens = LocalAlmox.query.order_by(LocalAlmox.nome).all()
    return render_template("almox/locais.html", itens=itens)


@almox_bp.route("/materiais/locais/novo", methods=["POST"])
@_guard("pode_almox_modulo")
def local_novo():
    nome = (request.form.get("nome") or "").strip()
    if not nome:
        flash("Informe o nome do local.", "danger")
        return redirect(url_for("almox.locais"))
    if LocalAlmox.query.filter(db.func.upper(LocalAlmox.nome) == nome.upper()).first():
        flash("Já existe um local com esse nome.", "warning")
        return redirect(url_for("almox.locais"))
    db.session.add(LocalAlmox(nome=nome.upper()))
    _log("Material", f"Local cadastrado: {nome.upper()}")
    db.session.commit()
    flash("Local cadastrado.", "success")
    return redirect(url_for("almox.locais"))


@almox_bp.route("/materiais/locais/<int:lid>/toggle", methods=["POST"])
@_guard("pode_almox_modulo")
def local_toggle(lid):
    l = db.session.get(LocalAlmox, lid) or abort(404)
    l.ativo = not l.ativo
    db.session.commit()
    return redirect(url_for("almox.locais"))


@almox_bp.route("/materiais/<int:pid>/mover", methods=["POST"])
@_guard("pode_almox_modulo")
def material_mover(pid):
    p = db.session.get(ProdutoAlmox, pid) or abort(404)
    destino_id = request.form.get("local_id")
    destino = db.session.get(LocalAlmox, int(destino_id)) if destino_id and destino_id.isdigit() else None
    if not destino:
        flash("Selecione o local de destino.", "danger")
        return redirect(url_for("almox.materiais"))
    de = p.local_nome
    p.local_id = destino.id
    db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="movimentacao",
                   quantidade=0, saldo_apos=p.saldo, local_de=de, local_para=destino.nome,
                   operador_id=_op_id(), obs=(request.form.get("obs") or "").strip()))
    _log("Material", f"{p.nome}: movido de {de} para {destino.nome}")
    db.session.commit()
    flash(f"{p.nome} movido para {destino.nome}.", "success")
    return redirect(url_for("almox.materiais"))


@almox_bp.route("/materiais/<int:pid>/entrada", methods=["POST"])
@_guard("pode_almox_modulo")
def material_entrada(pid):
    p = db.session.get(ProdutoAlmox, pid) or abort(404)
    qtd = _num(request.form.get("quantidade"))
    if qtd <= 0:
        flash("Quantidade inválida.", "danger")
        return redirect(url_for("almox.materiais"))
    p.saldo = (p.saldo or 0) + qtd
    db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="entrada",
                   quantidade=qtd, saldo_apos=p.saldo, operador_id=_op_id(),
                   obs=(request.form.get("obs") or "").strip()))
    _log("Material", f"Entrada {qtd} {p.unidade} de {p.nome} (saldo {p.saldo})")
    db.session.commit()
    flash(f"Entrada registrada. Saldo de {p.nome}: {p.saldo:g} {p.unidade}.", "success")
    return redirect(url_for("almox.materiais"))


@almox_bp.route("/materiais/<int:pid>/saida", methods=["POST"])
@_guard("pode_almox_modulo")
def material_saida(pid):
    p = db.session.get(ProdutoAlmox, pid) or abort(404)
    qtd = _num(request.form.get("quantidade"))
    if qtd <= 0:
        flash("Quantidade inválida.", "danger")
        return redirect(url_for("almox.materiais"))
    # Prevenção de estoque negativo (item roadmap §9)
    if qtd > (p.saldo or 0):
        flash(f"Saída bloqueada: saldo de {p.nome} é {p.saldo:g} {p.unidade}, "
              f"menor que {qtd:g}. Faça entrada/ajuste antes.", "danger")
        return redirect(url_for("almox.materiais"))
    nome = (request.form.get("colaborador_nome") or "").strip().upper()
    colab = Colaborador.query.filter(db.func.upper(Colaborador.nome) == nome).first() if nome else None
    p.saldo = (p.saldo or 0) - qtd
    db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="saida",
                   quantidade=qtd, saldo_apos=p.saldo, colaborador_id=(colab.id if colab else None),
                   colaborador_nome=(nome or None), operador_id=_op_id(),
                   obs=(request.form.get("obs") or "").strip()))
    _log("Material", f"Saída {qtd} {p.unidade} de {p.nome} p/ {nome or '—'} (saldo {p.saldo})")
    db.session.commit()
    flash(f"Saída registrada. Saldo de {p.nome}: {p.saldo:g} {p.unidade}.", "success")
    return redirect(url_for("almox.materiais"))


@almox_bp.route("/materiais/<int:pid>/ajuste", methods=["POST"])
@_guard("pode_almox_modulo")
def material_ajuste(pid):
    p = db.session.get(ProdutoAlmox, pid) or abort(404)
    novo = _num(request.form.get("saldo"))
    antigo = p.saldo or 0
    p.saldo = novo
    db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="ajuste",
                   quantidade=novo - antigo, saldo_apos=novo, operador_id=_op_id(),
                   obs=(request.form.get("obs") or f"Ajuste de {antigo:g} para {novo:g}").strip()))
    _log("Material", f"Ajuste de saldo {p.nome}: {antigo:g} → {novo:g}")
    db.session.commit()
    flash(f"Saldo de {p.nome} ajustado para {novo:g} {p.unidade}.", "success")
    return redirect(url_for("almox.materiais"))


@almox_bp.route("/materiais/<int:pid>/desativar", methods=["POST"])
@_guard("pode_almox_modulo")
def material_desativar(pid):
    p = db.session.get(ProdutoAlmox, pid) or abort(404)
    p.ativo = False
    _log("Material", f"Material desativado: {p.nome}")
    db.session.commit()
    flash("Material desativado.", "success")
    return redirect(url_for("almox.materiais"))


def _filtra_mov_material():
    from datetime import datetime as _dt
    qy = MovimentacaoMaterial.query
    pid = request.args.get("produto_id") or ""
    tipo = request.args.get("tipo") or ""
    di = request.args.get("data_ini") or ""
    dfim = request.args.get("data_fim") or ""
    if pid.isdigit():
        qy = qy.filter(MovimentacaoMaterial.produto_id == int(pid))
    if tipo in ("entrada", "saida", "ajuste"):
        qy = qy.filter(MovimentacaoMaterial.tipo == tipo)
    if di:
        try: qy = qy.filter(MovimentacaoMaterial.criado_em >= _dt.strptime(di, "%Y-%m-%d"))
        except ValueError: pass
    if dfim:
        try:
            fim = _dt.strptime(dfim, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            qy = qy.filter(MovimentacaoMaterial.criado_em <= fim)
        except ValueError: pass
    movs = qy.order_by(MovimentacaoMaterial.criado_em.desc()).limit(2000).all()
    ctx = dict(produto_id=pid, tipo=tipo, data_ini=di, data_fim=dfim)
    return movs, ctx


@almox_bp.route("/materiais/movimentacoes")
@_guard("pode_almox_modulo")
def materiais_mov():
    movs, ctx = _filtra_mov_material()
    produtos = ProdutoAlmox.query.filter_by(ativo=True).order_by(ProdutoAlmox.nome).all()
    return render_template("almox/materiais_mov.html", movs=movs, produtos=produtos, ctx=ctx)


@almox_bp.route("/materiais/movimentacoes/csv")
@_guard("pode_almox_modulo")
def materiais_mov_csv():
    import csv, io
    from flask import Response
    movs, _ = _filtra_mov_material()
    buf = io.StringIO(); buf.write("\ufeff")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Data/Hora", "Tipo", "Material", "Quantidade", "Saldo após", "Colaborador", "Operador", "Obs"])
    for m in movs:
        w.writerow([m.criado_em.strftime("%d/%m/%Y %H:%M") if m.criado_em else "", m.tipo,
                    m.produto_nome or "", ("%g" % (m.quantidade or 0)), ("%g" % (m.saldo_apos or 0)),
                    m.colaborador_nome or "", (m.operador.nome if m.operador else ""), m.obs or ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=movimentacoes_material.csv"})


@almox_bp.route("/materiais/movimentacoes/pdf")
@_guard("pode_almox_modulo")
def materiais_mov_pdf():
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    import io
    from flask import Response
    movs, ctx = _filtra_mov_material()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), topMargin=12*mm, bottomMargin=12*mm,
                            leftMargin=10*mm, rightMargin=10*mm)
    styles = getSampleStyleSheet()
    elems = [Paragraph("Movimentações de material", styles["Title"]),
             Paragraph(f"Período: {ctx['data_ini'] or 'início'} a {ctx['data_fim'] or 'hoje'}", styles["Normal"]),
             Spacer(1, 6)]
    data = [["Data/Hora", "Tipo", "Material", "Qtd", "Saldo após", "Colaborador", "Operador"]]
    for m in movs:
        data.append([m.criado_em.strftime("%d/%m/%y %H:%M") if m.criado_em else "", m.tipo,
                     m.produto_nome or "", ("%g" % (m.quantidade or 0)), ("%g" % (m.saldo_apos or 0)),
                     m.colaborador_nome or "", (m.operador.nome if m.operador else "")])
    if len(data) == 1:
        data.append(["—"] * 7)
    t = Table(data, repeatRows=1, colWidths=[26*mm, 18*mm, 70*mm, 20*mm, 24*mm, 40*mm, 40*mm])
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
                    headers={"Content-Disposition": "attachment; filename=movimentacoes_material.pdf"})


@almox_bp.route("/materiais/saldo/csv")
@_guard("pode_almox_modulo")
def materiais_saldo_csv():
    import csv, io
    from flask import Response
    itens = ProdutoAlmox.query.filter_by(ativo=True).order_by(ProdutoAlmox.nome).all()
    buf = io.StringIO(); buf.write("\ufeff")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Código", "Material", "Unidade", "Categoria", "Saldo", "Saldo mínimo", "Abaixo do mínimo?"])
    for p in itens:
        w.writerow([p.codigo or "", p.nome, p.unidade, p.categoria or "",
                    ("%g" % (p.saldo or 0)), ("%g" % (p.saldo_minimo or 0)),
                    "SIM" if p.abaixo_minimo else ""])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=saldo_material.csv"})


@almox_bp.route("/materiais/qr")
@_guard("pode_almox_modulo")
def materiais_qr():
    ids = request.args.get("ids") or ""
    consulta = ProdutoAlmox.query.filter_by(ativo=True)
    if ids.strip():
        lista_ids = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        consulta = consulta.filter(ProdutoAlmox.id.in_(lista_ids))
    itens = consulta.order_by(ProdutoAlmox.nome).all()
    formato = request.args.get("formato", "a4")
    return render_template("almox/materiais_qr.html", itens=itens, qr_svg=_qr_svg, formato=formato)


# ----- Coletor: saída de MATERIAL (via QR do colaborador + QR do produto) -----
@almox_bp.route("/coletor/api/produto/<path:qr_uid>")
@modulo_required
def coletor_api_produto(qr_uid):
    uid = _uid_limpo(qr_uid)
    p = ProdutoAlmox.query.filter_by(qr_uid=uid, ativo=True).first()
    if not p:
        return jsonify(ok=False, erro="Material não encontrado."), 404
    return jsonify(ok=True, id=p.id, nome=p.nome, unidade=p.unidade, saldo=p.saldo or 0)


@almox_bp.route("/coletor/api/material-saida", methods=["POST"])
@modulo_required
def coletor_api_material_saida():
    """payload: {colaborador_id, senha, itens:[{produto_id, qtd}]}"""
    data = request.get_json(silent=True) or {}
    colab = db.session.get(Colaborador, data.get("colaborador_id") or 0)
    if not colab or not colab.ativo:
        return jsonify(ok=False, erro="Colaborador inválido."), 400
    senha = data.get("senha") or ""
    if not colab.tem_senha:
        if len(senha) < 4:
            return jsonify(ok=False, erro="Primeiro uso: defina uma senha de ao menos 4 dígitos."), 400
        colab.set_senha(senha)
    elif not colab.check_senha(senha):
        return jsonify(ok=False, erro="Senha do colaborador inválida."), 403
    itens = data.get("itens") or []
    if not itens:
        return jsonify(ok=False, erro="Nenhum material para confirmar."), 400
    # Valida saldo ANTES de aplicar (prevenção de estoque negativo)
    faltas = []
    plano = []
    for it in itens:
        p = db.session.get(ProdutoAlmox, it.get("produto_id") or 0)
        q = _num(it.get("qtd"))
        if not p or q <= 0:
            continue
        if q > (p.saldo or 0):
            faltas.append(f"{p.nome} (saldo {p.saldo:g}, pedido {q:g})")
        else:
            plano.append((p, q))
    if faltas:
        return jsonify(ok=False, erro="Saldo insuficiente: " + "; ".join(faltas)), 400
    feitas = []
    for p, q in plano:
        p.saldo = (p.saldo or 0) - q
        db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="saida",
                       quantidade=q, saldo_apos=p.saldo, colaborador_id=colab.id,
                       colaborador_nome=colab.nome, operador_id=_op_id(), obs="Coletor"))
        feitas.append(f"{q:g} {p.unidade} de {p.nome}")
    _log("Coletor", f"{colab.nome}: saída de material — " + "; ".join(feitas))
    db.session.commit()
    return jsonify(ok=True, resumo=feitas, colaborador=colab.nome)


# ----- Estoque negativo (detecção/resolução — roadmap §9) -----
@almox_bp.route("/materiais/negativos")
@_guard("pode_almox_modulo")
def materiais_negativos():
    negativos = (ProdutoAlmox.query.filter(ProdutoAlmox.ativo == True, ProdutoAlmox.saldo < 0)
                 .order_by(ProdutoAlmox.nome).all())
    return render_template("almox/materiais_negativos.html", negativos=negativos)


# ----- Coletor: MOVIMENTAÇÃO de material entre locais -----
@almox_bp.route("/coletor/api/locais")
@modulo_required
def coletor_api_locais():
    locais = LocalAlmox.query.filter_by(ativo=True).order_by(LocalAlmox.nome).all()
    return jsonify(ok=True, locais=[{"id": l.id, "nome": l.nome} for l in locais])


@almox_bp.route("/coletor/api/mover", methods=["POST"])
@modulo_required
def coletor_api_mover():
    data = request.get_json(silent=True) or {}
    p = db.session.get(ProdutoAlmox, data.get("produto_id") or 0)
    destino = db.session.get(LocalAlmox, data.get("local_id") or 0)
    if not p or not p.ativo:
        return jsonify(ok=False, erro="Material inválido."), 400
    if not destino:
        return jsonify(ok=False, erro="Local de destino inválido."), 400
    de = p.local_nome
    p.local_id = destino.id
    db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="movimentacao",
                   quantidade=0, saldo_apos=p.saldo, local_de=de, local_para=destino.nome,
                   operador_id=_op_id(), obs="Coletor"))
    _log("Coletor", f"{p.nome}: movido de {de} para {destino.nome}")
    db.session.commit()
    return jsonify(ok=True, resumo=[f"{p.nome}: {de} → {destino.nome}"])


# ==================== INVENTÁRIO DE MATERIAL ====================
@almox_bp.route("/materiais/inventario", methods=["GET"])
@_guard("pode_almox_modulo")
def inventario():
    itens = ProdutoAlmox.query.filter_by(ativo=True).order_by(ProdutoAlmox.nome).all()
    return render_template("almox/inventario.html", itens=itens)


@almox_bp.route("/materiais/inventario", methods=["POST"])
@_guard("pode_almox_modulo")
def inventario_salvar():
    itens = ProdutoAlmox.query.filter_by(ativo=True).all()
    ajustados = 0
    for p in itens:
        raw = request.form.get(f"contado_{p.id}")
        if raw is None or str(raw).strip() == "":
            continue                     # item não contado nesta rodada: ignora
        contado = _num(raw)
        if contado != (p.saldo or 0):
            dif = contado - (p.saldo or 0)
            p.saldo = contado
            db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="inventario",
                           quantidade=dif, saldo_apos=contado, operador_id=_op_id(),
                           obs="Inventário (conferência)"))
            ajustados += 1
    _log("Material", f"Inventário aplicado: {ajustados} item(ns) ajustado(s)")
    db.session.commit()
    flash(f"Inventário concluído. {ajustados} item(ns) ajustado(s).", "success")
    return redirect(url_for("almox.materiais"))


@almox_bp.route("/coletor/api/inventario", methods=["POST"])
@modulo_required
def coletor_api_inventario():
    """payload: {produto_id, contado}"""
    data = request.get_json(silent=True) or {}
    p = db.session.get(ProdutoAlmox, data.get("produto_id") or 0)
    if not p or not p.ativo:
        return jsonify(ok=False, erro="Material inválido."), 400
    contado = _num(data.get("contado"), None if data.get("contado") in (None, "") else 0)
    if contado is None:
        return jsonify(ok=False, erro="Quantidade contada inválida."), 400
    antigo = p.saldo or 0
    dif = contado - antigo
    p.saldo = contado
    db.session.add(MovimentacaoMaterial(produto_id=p.id, produto_nome=p.nome, tipo="inventario",
                   quantidade=dif, saldo_apos=contado, operador_id=_op_id(), obs="Inventário (coletor)"))
    _log("Coletor", f"Inventário {p.nome}: {antigo:g} → {contado:g}")
    db.session.commit()
    return jsonify(ok=True, resumo=[f"{p.nome}: {antigo:g} → {contado:g}"], nome=p.nome,
                   antigo=antigo, novo=contado)


# ==================== HIERARQUIA FÍSICA: PLANTA / ARMAZÉM / LOCALIZADOR ====================

@almox_bp.route("/plantas", methods=["GET", "POST"])
@_guard("pode_almox_modulo")
def plantas():
    from .models import Planta
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip().upper()
        if not nome:
            flash("Informe o nome da planta.", "danger")
        elif Planta.query.filter(db.func.upper(Planta.nome) == nome).first():
            flash("Já existe uma planta com esse nome.", "warning")
        else:
            db.session.add(Planta(nome=nome))
            _log("Planta", f"Planta cadastrada: {nome}")
            db.session.commit()
            flash("Planta cadastrada.", "success")
        return redirect(url_for("almox.plantas"))
    itens = Planta.query.order_by(Planta.nome).all()
    return render_template("almox/plantas.html", itens=itens)


@almox_bp.route("/plantas/<int:pid>", methods=["POST"])
@_guard("pode_almox_modulo")
def planta_editar(pid):
    from .models import Planta
    p = db.session.get(Planta, pid) or abort(404)
    p.nome = (request.form.get("nome") or p.nome).strip().upper()
    p.ativo = request.form.get("ativo") == "1"
    db.session.commit()
    flash("Planta atualizada.", "success")
    return redirect(url_for("almox.plantas"))


@almox_bp.route("/armazens", methods=["GET", "POST"])
@_guard("pode_almox_modulo")
def armazens():
    from .models import Armazem, Planta
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip().upper()
        planta_id = request.form.get("planta_id") or None
        if not nome or not planta_id:
            flash("Informe o nome do armazém e a planta.", "danger")
        else:
            db.session.add(Armazem(nome=nome, planta_id=int(planta_id)))
            _log("Armazém", f"Armazém cadastrado: {nome}")
            db.session.commit()
            flash("Armazém cadastrado.", "success")
        return redirect(url_for("almox.armazens"))
    itens = Armazem.query.order_by(Armazem.nome).all()
    plantas_l = Planta.query.filter_by(ativo=True).order_by(Planta.nome).all()
    return render_template("almox/armazens.html", itens=itens, plantas=plantas_l)


@almox_bp.route("/armazens/<int:aid>", methods=["POST"])
@_guard("pode_almox_modulo")
def armazem_editar(aid):
    from .models import Armazem
    a = db.session.get(Armazem, aid) or abort(404)
    a.nome = (request.form.get("nome") or a.nome).strip().upper()
    if request.form.get("planta_id"):
        a.planta_id = int(request.form.get("planta_id"))
    a.ativo = request.form.get("ativo") == "1"
    db.session.commit()
    flash("Armazém atualizado.", "success")
    return redirect(url_for("almox.armazens"))


@almox_bp.route("/localizadores", methods=["GET", "POST"])
@_guard("pode_almox_modulo")
def localizadores():
    import secrets
    from .models import Armazem, Localizador
    if request.method == "POST":
        armazem_id = request.form.get("armazem_id") or None
        fila = (request.form.get("fila") or "").strip().upper()[:1]
        estante = request.form.get("estante")
        nivel = request.form.get("nivel")
        if not (armazem_id and fila.isalpha() and (estante or "").isdigit() and (nivel or "").isdigit()):
            flash("Preencha armazém, fila (1 letra), estante e nível (números).", "danger")
            return redirect(url_for("almox.localizadores"))
        existe = Localizador.query.filter_by(armazem_id=int(armazem_id), fila=fila,
                                             estante=int(estante), nivel=int(nivel)).first()
        if existe:
            flash("Esse localizador já existe.", "warning")
            return redirect(url_for("almox.localizadores"))
        uid = "LOC-" + secrets.token_hex(4).upper()
        db.session.add(Localizador(armazem_id=int(armazem_id), fila=fila,
                                   estante=int(estante), nivel=int(nivel), qr_uid=uid))
        _log("Localizador", f"Localizador {fila}*{estante}*{nivel} cadastrado")
        db.session.commit()
        flash("Localizador cadastrado.", "success")
        return redirect(url_for("almox.localizadores"))
    itens = Localizador.query.order_by(Localizador.armazem_id, Localizador.fila,
                                       Localizador.estante, Localizador.nivel).all()
    armazens_l = Armazem.query.filter_by(ativo=True).order_by(Armazem.nome).all()
    return render_template("almox/localizadores.html", itens=itens, armazens=armazens_l)


@almox_bp.route("/localizadores/<int:lid>/toggle", methods=["POST"])
@_guard("pode_almox_modulo")
def localizador_toggle(lid):
    from .models import Localizador
    l = db.session.get(Localizador, lid) or abort(404)
    l.ativo = not l.ativo
    db.session.commit()
    flash("Localizador atualizado.", "success")
    return redirect(url_for("almox.localizadores"))


@almox_bp.route("/localizadores/gerar", methods=["GET", "POST"])
@_guard("pode_almox_modulo")
def localizadores_gerar():
    import secrets
    from .models import Armazem, Localizador
    if request.method == "POST":
        armazem_id = request.form.get("armazem_id") or None
        f_ini = (request.form.get("fila_ini") or "").strip().upper()[:1]
        f_fim = (request.form.get("fila_fim") or "").strip().upper()[:1]
        try:
            e_ini = int(request.form.get("estante_ini")); e_fim = int(request.form.get("estante_fim"))
            n_ini = int(request.form.get("nivel_ini")); n_fim = int(request.form.get("nivel_fim"))
        except (TypeError, ValueError):
            flash("Estante e nível devem ser números.", "danger")
            return redirect(url_for("almox.localizadores_gerar"))
        if not (armazem_id and f_ini.isalpha() and f_fim.isalpha() and f_ini <= f_fim
                and e_ini <= e_fim and n_ini <= n_fim):
            flash("Confira os intervalos (fila A→Z, estante e nível crescentes).", "danger")
            return redirect(url_for("almox.localizadores_gerar"))
        criados, pulados = 0, 0
        existentes = {(l.fila, l.estante, l.nivel) for l in
                      Localizador.query.filter_by(armazem_id=int(armazem_id)).all()}
        for cod in range(ord(f_ini), ord(f_fim) + 1):
            fila = chr(cod)
            for est in range(e_ini, e_fim + 1):
                for niv in range(n_ini, n_fim + 1):
                    if (fila, est, niv) in existentes:
                        pulados += 1
                        continue
                    uid = "LOC-" + secrets.token_hex(4).upper()
                    db.session.add(Localizador(armazem_id=int(armazem_id), fila=fila,
                                               estante=est, nivel=niv, qr_uid=uid))
                    criados += 1
        _log("Localizador", f"Gerados {criados} localizadores em massa (pulados {pulados})")
        db.session.commit()
        flash(f"{criados} localizador(es) gerado(s). {pulados} já existiam.", "success")
        return redirect(url_for("almox.localizadores"))
    armazens_l = Armazem.query.filter_by(ativo=True).order_by(Armazem.nome).all()
    return render_template("almox/localizadores_gerar.html", armazens=armazens_l)


@almox_bp.route("/relatorios")
@_guard("pode_almox_modulo")
def relatorios_central():
    """Central de relatórios: reúne num lugar só todos os relatórios e exportações."""
    return render_template("almox/relatorios_central.html")
