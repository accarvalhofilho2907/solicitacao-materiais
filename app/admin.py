from functools import wraps
from datetime import datetime, date
from urllib.parse import quote

from flask import (
    Blueprint, render_template, redirect, url_for, request, flash, abort, current_app, jsonify
)
from flask_login import login_required, current_user

from .extensions import db, csrf
from .models import (
    Usuario, TipoMaterial, Fornecedor, Solicitacao, Comentario, PedidoCompra, Orcamento,
    Cidade, Transportadora, Empresa, Sugestao, Atividade, Notinha, LogSolicitacao,
    HistoricoPapel, Colaborador,
    STATUS, STATUS_PADRAO,
)
from .storage import salvar_imagem
from .emails import enviar_email


def _mail_solic(s, assunto, corpo, **kw):
    """Envia e-mail ao solicitante SÓ se houver endereço (usuario ou colaborador).
    Solicitacoes feitas por colaborador tem s.solicitante (Usuario) = None."""
    dest = None
    if getattr(s, "solicitante", None) is not None and getattr(s.solicitante, "email", None):
        dest = s.solicitante.email
    elif getattr(s, "solicitante_colab_id", None):
        try:
            from .models import Colaborador
            cb = db.session.get(Colaborador, s.solicitante_colab_id)
            dest = getattr(cb, "email", None) if cb else None
        except Exception:
            dest = None
    if dest:
        enviar_email(dest, assunto, corpo, **kw)
from .pdf import gerar_pdf_pedido, gerar_pdf_pedido_lote
from .pdf_orcamento import extrair_itens, _parse_valor
from .util import (normalizar_telefone_br, somar_dias_uteis, contem_busca, sem_acentos,
                   formatar_cnpj, cnpj_valido, formatar_ie, so_digitos)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
NOTA_WHATS = ("(Esta solicitação de cotação também foi enviada por e-mail; estamos "
              "encaminhando por aqui também. Pode responder por e-mail ou por aqui.)")


def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*a, **k):
        if not current_user.is_admin:
            abort(403)
        return f(*a, **k)
    return wrapper


# Dados fixos do comprador para o e-mail de cotação (item 73). (SPE, Endereço, CNPJ, I.E.)
SPES_COTACAO = [
    ("Delta 3 I Energia S.A.", "Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000", "23.598.517/0002-00", "124895123"),
    ("Delta 3 II Energia S.A.", "Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000", "23.598.858/0002-86", "124897193"),
    ("Delta 3 III Energia S.A.", "Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000", "23.598.847/0002-04", "124897070"),
    ("Delta 3 IV Energia S.A.", "Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000", "23.598.842/0002-73", "124897029"),
    ("Delta 3 V Energia S.A.", "Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000", "23.598.829/0002-14", "124897134"),
    ("Delta 3 VI Energia S.A.", "Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000", "23.598.831/0002-93", "124896995"),
    ("Delta 3 VII Energia S.A.", "Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000", "23.598.844/0002-62", "124897100"),
    ("Delta 3 VIII Energia S.A.", "Rua Rio Novo, 47 - Centro - Paulino Neves/MA - 65585-000", "15.190.472/0002-02", "12.512653-0"),
    ("Delta 5 I Energia S.A.", "Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 5, Zona Rural - Paulino Neves/MA - 65585-000", "29.296.171/0002-72", "12.556889-4"),
    ("Delta 5 II Energia S.A.", "Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 5, Zona Rural - Paulino Neves/MA - 65585-000", "29.303.897/0002-95", "12.556898-3"),
    ("Delta 6 I Energia S.A.", "Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 6, Zona Rural - Paulino Neves/MA - 65585-000", "29.296.141/0002-66", "12.556908-4"),
    ("Delta 6 II Energia S.A.", "Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 6, Zona Rural - Paulino Neves/MA - 65585-000", "29.296.975/0002-71", "12.556887-8"),
    ("Delta 7 I Energia S.A", "Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 7, Zona Rural - Paulino Neves/MA - 65585-000", "30.866.542/0002-93", "12.583428-4"),
    ("Delta 7 II Energia S.A", "Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 7, Zona Rural - Paulino Neves/MA - 65585-000", "30.905.225/0002-39", "12.583447-0"),
    ("Delta 8 I Energia S.A.", "Rodovia MA-315, s/n, Vias Internas do Complexo Eólico Delta 8, Zona Rural - Paulino Neves/MA - 65585-000", "30.866.547/0002-16", "12.583436-5"),
]
ASSINATURA_COTACAO = ("Antonio Carlos Carvalho\n"
                      "Analista Administrativo Jr de O&M – Cluster Delta MA\n"
                      "+55 (86) 99939-9872\n"
                      "srna.co")


def _mai(v):
    """Padroniza texto de cadastro em MAIÚSCULAS (item 88)."""
    return (v or "").strip().upper()


def _prazo_cotacao():
    d = somar_dias_uteis(5)
    return d, d.strftime("%d/%m/%Y")


def _log(s, evento):
    """Registra um evento na linha do tempo da solicitação (e no log do sistema)."""
    db.session.add(LogSolicitacao(solicitacao_id=s.id, evento=evento,
                                  autor_id=current_user.id if current_user.is_authenticated else None))
    try:
        from .logsys import registrar as _logsys
        _logsys("Solicitação", f"#{s.id}: {evento}")
    except Exception:
        pass


def _link_curto(s):
    """Link curto interno (item 71): detecta o endereço de onde o sistema é acessado."""
    if not s.link_similar:
        return ""
    try:
        base = request.url_root.rstrip("/")
    except Exception:
        base = current_app.config.get("BASE_URL", "").rstrip("/")
    return f"{base}/r/{s.id}"


def _proximo_num_cotacao(ano=None):
    ano = ano or date.today().year
    prefixo = f"COT-{ano}-"
    maxn = 0
    for (c,) in db.session.query(PedidoCompra.cotacao_seq).filter(PedidoCompra.cotacao_seq.like(prefixo + "%")).all():
        try:
            maxn = max(maxn, int(c.rsplit("-", 1)[-1]))
        except (ValueError, AttributeError):
            pass
    return maxn + 1


def _seq_str(n, ano=None):
    return f"COT-{ano or date.today().year}-{n:03d}"


def _assunto_cotacao(fornecedor, seq):
    return f"SRNA | {fornecedor.nome}: Cotação de material #{seq}"


def _tabela_texto(cabecalhos, linhas, larguras):
    """Tabela em texto puro com colunas alinhadas (item 77). Última coluna fica livre."""
    def fmt(vals):
        n = len(vals)
        return "  ".join(str(v) if i == n - 1 else str(v).ljust(larguras[i]) for i, v in enumerate(vals))
    sep = "  ".join("-" * w for w in larguras)
    return "\n".join([fmt(cabecalhos), sep] + [fmt(l) for l in linhas])


def _corpo_cotacao(fornecedor, itens, incluir_spe=True, spe_escolhida=None):
    """Corpo padrão do e-mail/WhatsApp/texto de cotação (itens 73/75/77/91/117/120).

    incluir_spe=True  -> e-mail (com o quadro 'Dados para Cotação' / SPEs)
    incluir_spe=False -> WhatsApp / Texto pronto (sem o quadro de CNPJs).
    spe_escolhida=nome da Delta selecionada no pop-up (item 120); se informado,
    mostra só essa SPE na tabela em vez das 15.
    """
    _, prazo = _prazo_cotacao()
    contato = (fornecedor.contato_nome or "").strip()
    saud = f"Olá, {contato}, tudo bem?" if contato else "Olá, tudo bem?"
    L = [saud, "",
         "Poderia enviar a cotação do material abaixo considerando:",
         "i. Frete CIF",
         "ii. Pagamento 30 DDL",
         "iii. Material com finalidade de Uso e Consumo", ""]
    if incluir_spe:
        L.append("Dados para Cotação:")
        fonte_spes = SPES_COTACAO
        if spe_escolhida:
            fonte_spes = [d for d in SPES_COTACAO if d[0] == spe_escolhida] or SPES_COTACAO
        spe_linhas = [(spe, cnpj, ie, end) for (spe, end, cnpj, ie) in fonte_spes]
        L.append(_tabela_texto(["SPE", "CNPJ", "I.E.", "Endereço"], spe_linhas, [26, 20, 13, 60]))
        L.append("")
    L += ["Produtos:"]
    prod = [[f"#{s.id}#", (s.material or "") + (f" ({s.unidade_medida})" if s.unidade_medida else ""),
             (s.fabricante or "N/D"), s.quantidade, _link_curto(s) or "-"]
            for s in itens]
    L.append(_tabela_texto(["Nº", "Produto", "Fabricante/Marca", "Qtd", "Link"], prod, [7, 30, 20, 5, 40]))
    L += ["", f"Prazo para retorno: 5 dias úteis (Até {prazo}).", "",
          "Qualquer dúvida, estou à disposição.", "", ASSINATURA_COTACAO]
    return "\n".join(L)


def _wa_link(f, texto):
    return f"https://wa.me/{f.telefone_e164}?text={quote(texto)}" if f.telefone_e164 else None


def _mailto(fornecedor, itens, seq, spe_escolhida=None):
    if not fornecedor.email:
        return None
    assunto = _assunto_cotacao(fornecedor, seq)
    corpo = _corpo_cotacao(fornecedor, itens, spe_escolhida=spe_escolhida)
    return f"mailto:{fornecedor.email}?subject={quote(assunto)}&body={quote(corpo)}"


# ---------------- Painel ----------------
@admin_bp.route("/")
@admin_required
def dashboard():
    q = Solicitacao.query
    f_status = request.args.getlist("status")
    f_sol = request.args.getlist("solicitante")
    f_tipo = request.args.get("tipo")
    f_busca = (request.args.get("q") or "").strip()
    f_forn = request.args.getlist("fornecedor")
    f_de = request.args.get("de")
    f_ate = request.args.get("ate")
    f_vencidos = request.args.get("vencidos")
    f_atrasadas = request.args.get("atrasadas")
    aplicou = bool(request.args)
    if not f_status and not aplicou:
        f_status = STATUS_PADRAO[:]  # padrão: tudo menos Concluído/Cancelada
    if f_vencidos:
        q = q.filter(Solicitacao.status == "AGUARDANDO_RECEBIMENTO_COTACAO",
                     Solicitacao.prazo_cotacao.isnot(None), Solicitacao.prazo_cotacao < date.today())
    elif f_atrasadas:
        q = q.filter(Solicitacao.status == "AGUARDANDO_CHEGADA",
                     Solicitacao.prazo_recebimento.isnot(None), Solicitacao.prazo_recebimento < date.today())
    elif f_status:
        q = q.filter(Solicitacao.status.in_(f_status))
    if f_sol:
        q = q.filter(Solicitacao.solicitante_id.in_([int(x) for x in f_sol]))
    if f_forn:
        ids = [int(x) for x in f_forn]
        sub = db.session.query(Orcamento.solicitacao_id).filter(Orcamento.fornecedor_id.in_(ids))
        q = q.filter(db.or_(Solicitacao.fornecedor_definido_id.in_(ids), Solicitacao.id.in_(sub)))
    if f_tipo:
        q = q.filter_by(tipo_material_id=int(f_tipo))
    if f_de:
        q = q.filter(Solicitacao.criado_em >= datetime.strptime(f_de, "%Y-%m-%d"))
    if f_ate:
        q = q.filter(Solicitacao.criado_em <= datetime.strptime(f_ate, "%Y-%m-%d").replace(hour=23, minute=59))
    pedidos = q.order_by(Solicitacao.atualizado_em.desc()).all()
    if f_busca:  # busca ignora acentos (item 150)
        pedidos = [s for s in pedidos if contem_busca(s.material, f_busca)]

    # Resumo de notinhas (mês corrente) + filtro de atividade
    f_ativ = request.args.get("ativ_resumo")
    ini = date.today().replace(day=1)
    nq = Notinha.query.filter(Notinha.data >= ini)
    if f_ativ:
        nq = nq.filter_by(atividade_id=int(f_ativ))
    total_notinhas_mes = sum(float(n.valor) for n in nq.all())

    return render_template("admin/dashboard.html", pedidos=pedidos,
        tipos=TipoMaterial.query.order_by(TipoMaterial.nome).all(),
        solicitantes=Usuario.query.filter(Usuario.papel.in_(["solicitante", "almoxarifado"])).order_by(Usuario.nome).all(),
        fornecedores=Fornecedor.query.order_by(Fornecedor.nome_fantasia).all(),
        atividades=Atividade.query.filter_by(ativo=True).order_by(Atividade.nome).all(),
        total_notinhas_mes=total_notinhas_mes, f_ativ=f_ativ,
        pendentes=Solicitacao.query.filter_by(status="AGUARDANDO_APROVACAO").count(),
        n_envio=Solicitacao.query.filter_by(status="AGUARDANDO_ENVIO_COTACAO").count(),
        n_chegada=Solicitacao.query.filter_by(status="AGUARDANDO_CHEGADA").count(),
        n_vencidos=Solicitacao.query.filter(Solicitacao.status == "AGUARDANDO_RECEBIMENTO_COTACAO",
            Solicitacao.prazo_cotacao.isnot(None), Solicitacao.prazo_cotacao < date.today()).count(),
        n_atrasadas=Solicitacao.query.filter(Solicitacao.status == "AGUARDANDO_CHEGADA",
            Solicitacao.prazo_recebimento.isnot(None), Solicitacao.prazo_recebimento < date.today()).count(),
        f_vencidos=f_vencidos,
        f_status=f_status, f_tipo=f_tipo, f_sol=[int(x) for x in f_sol],
        f_forn=[int(x) for x in f_forn], f_busca=f_busca, f_de=f_de, f_ate=f_ate)


@admin_bp.route("/aprovacoes")
@admin_required
def aprovacoes():
    pedidos = Solicitacao.query.filter_by(status="AGUARDANDO_APROVACAO").order_by(Solicitacao.criado_em).all()
    return render_template("admin/aprovacoes.html", pedidos=pedidos)


def _aprovar(s):
    if s.status == "AGUARDANDO_APROVACAO":
        s.status = "AGUARDANDO_ENVIO_COTACAO"
        _log(s, "Aprovada (liberada para cotação)")
        _mail_solic(s, f"Solicitação Nº {s.id} aprovada", f"Sua solicitação Nº {s.id} foi aprovada.")
        return True
    return False


@admin_bp.route("/solicitacao/<int:sid>/aprovar", methods=["POST"])
@admin_required
def aprovar(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    if _aprovar(s):
        db.session.commit()
        flash(f"Solicitação Nº {s.id} aprovada.", "success")
    return redirect(request.referrer or url_for("admin.aprovacoes"))


@admin_bp.route("/aprovacoes/aprovar-lote", methods=["POST"])
@admin_required
def aprovar_lote():
    n = 0
    for sid in request.form.getlist("ids"):
        s = db.session.get(Solicitacao, int(sid))
        if s and _aprovar(s):
            n += 1
    db.session.commit()
    flash(f"{n} solicitação(ões) aprovada(s) em lote.", "success")
    return redirect(url_for("admin.aprovacoes"))


@admin_bp.route("/aprovacoes/exportar", methods=["POST"])
@admin_required
def aprovacoes_exportar():
    from flask import Response
    from .pdf import gerar_pdf_fichas
    itens = Solicitacao.query.filter(Solicitacao.id.in_(request.form.getlist("ids"))).order_by(Solicitacao.id).all()
    if not itens:
        flash("Marque ao menos uma solicitação para exportar.", "warning")
        return redirect(url_for("admin.aprovacoes"))
    pdf = gerar_pdf_fichas(itens)
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment; filename=fichas_solicitacoes.pdf"})


@admin_bp.route("/solicitacao/<int:sid>")
@admin_required
def solicitacao(sid):
    s = db.session.get(Solicitacao, sid)
    if not s:
        abort(404)
    excluidos = list(s.fornecedores_excluidos)
    excluidos_ids = {f.id for f in excluidos}
    fornecedores = [f for f in s.tipo.fornecedores if f.ativo and f.aprovado and f.id not in excluidos_ids] if s.tipo else []
    orcamentos = sorted(s.orcamentos, key=lambda o: o.valor_total)
    base = _proximo_num_cotacao()
    seqs = {f.id: _seq_str(base + i) for i, f in enumerate(fornecedores)}
    wa = {f.id: _wa_link(f, _corpo_cotacao(f, [s], incluir_spe=False)) for f in fornecedores} if fornecedores else None
    mail = {f.id: _mailto(f, [s], seqs[f.id]) for f in fornecedores} if fornecedores else None
    txt = {f.id: _corpo_cotacao(f, [s], incluir_spe=False) for f in fornecedores} if fornecedores else None
    # Histórico de preços do mesmo tipo de material (item 100)
    historico_precos = []
    if s.tipo_material_id:
        historico_precos = (Orcamento.query.join(Solicitacao, Orcamento.solicitacao_id == Solicitacao.id)
            .filter(Solicitacao.tipo_material_id == s.tipo_material_id, Orcamento.solicitacao_id != s.id)
            .order_by(Orcamento.recebido_em.desc()).limit(8).all())
    voltar = request.args.get("voltar", "")
    voltar_url = url_for("admin.dashboard") + (("?" + voltar) if voltar else "")
    return render_template("admin/solicitacao.html", s=s, fornecedores=fornecedores, orcamentos=orcamentos,
        menor_valor=orcamentos[0].valor_total if orcamentos else None, wa=wa, mail=mail, txt=txt, seqs=seqs,
        excluidos=excluidos, historico_precos=historico_precos,
        hoje=date.today().isoformat(), voltar_url=voltar_url,
        tipos=TipoMaterial.query.filter_by(ativo=True).order_by(TipoMaterial.nome).all(),
        transportadoras=Transportadora.query.filter_by(ativo=True)
            .filter((Transportadora.aprovacao == "aprovado") | (Transportadora.aprovacao.is_(None)))
            .order_by(Transportadora.nome).all(),
        cidades=Cidade.query.filter_by(ativo=True).order_by(Cidade.nome).all())


@admin_bp.route("/solicitacao/<int:sid>/status", methods=["POST"])
@admin_required
def mudar_status(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    novo = request.form.get("status")
    if novo in STATUS:
        s.status = novo
        _log(s, f"Status alterado para: {s.status_label}")
        db.session.commit()
        _mail_solic(s, f"Solicitação Nº {s.id} — status atualizado", f"Status: {s.status_label}.")
        flash("Status atualizado.", "success")
    return redirect(url_for("admin.solicitacao", sid=s.id))


@admin_bp.route("/solicitacao/<int:sid>/comentar", methods=["POST"])
@admin_required
def comentar(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    texto = request.form.get("texto", "").strip()
    if texto:
        db.session.add(Comentario(solicitacao_id=s.id, autor_id=current_user.id, texto=texto))
        db.session.commit()
        _mail_solic(s, f"Solicitação Nº {s.id} — nova mensagem",
                     f"{texto}\n\n{current_app.config['BASE_URL']}/solicitante/solicitacao/{s.id}")
        flash("Mensagem enviada.", "success")
    return redirect(url_for("admin.solicitacao", sid=s.id))


@admin_bp.route("/solicitacao/<int:sid>/enviar-cotacao", methods=["POST"])
@admin_required
def enviar_pedido(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    _excl = {f.id for f in s.fornecedores_excluidos}
    fornecedores = [f for f in s.tipo.fornecedores if f.ativo and f.aprovado and f.usa_email and f.email and f.id not in _excl] if s.tipo else []
    if not fornecedores:
        flash("Nenhum fornecedor ativo com e-mail para este tipo (verifique o 'usa e-mail').", "warning")
        return redirect(url_for("admin.solicitacao", sid=s.id))
    _, prazo = _prazo_cotacao()
    corpo = request.form.get("corpo", "").strip() or (
        f"Prezados, segue solicitação de cotação (Nº {s.id}) em anexo. Por favor, retornem com "
        f"valor, prazo e condições de pagamento em até 5 dias úteis (até {prazo}).")
    pdf = gerar_pdf_pedido(s)
    emails = [f.email for f in fornecedores]
    enviar_email(emails, f"Solicitação de Cotação Nº {s.id}", corpo, anexo_bytes=pdf, anexo_nome=f"cotacao_{s.id}.pdf")
    db.session.add(PedidoCompra(solicitacao_id=s.id, enviado_por=current_user.id, destinatarios=", ".join(emails)))
    s.status = "AGUARDANDO_RECEBIMENTO_COTACAO"
    s.prazo_cotacao = _prazo_cotacao()[0]
    _log(s, f"Cotação enviada por e-mail ({len(emails)} fornecedor(es))")
    db.session.commit()
    flash(f"Cotação enviada por e-mail para {len(emails)} fornecedor(es).", "success")
    return redirect(url_for("admin.solicitacao", sid=s.id))


def _agrupar(status, expandir=False, busca=None, excluir_fornecedores=None):
    """Agrupa solicitações por fornecedor para a tela de Enviar Cotação.
    expandir=True -> considera qualquer status (exceto Concluído/Cancelada), não só o status pedido (item 122).
    busca -> filtra por nome de empresa(fornecedor)/tipo de material/produto (item 122).
    excluir_fornecedores -> ids de fornecedor para pular nesta tela (item 123, sessão/temporário)."""
    query = Solicitacao.query.filter(Solicitacao.tipo_material_id.isnot(None))
    if expandir:
        query = query.filter(Solicitacao.status.notin_(["CONCLUIDO", "CANCELADA"]))
    else:
        query = query.filter_by(status=status)
    itens = query.order_by(Solicitacao.id).all()

    if busca:
        def _bate(s):
            campos = [s.material or "", s.tipo.nome if s.tipo else "",
                     " ".join(f.nome for f in s.tipo.fornecedores) if s.tipo else ""]
            return any(contem_busca(c, busca) for c in campos)
        itens = [s for s in itens if _bate(s)]

    excluir_fornecedores = excluir_fornecedores or set()
    grupos = {}
    for s in itens:
        excluidos = {f.id for f in s.fornecedores_excluidos} | excluir_fornecedores
        for f in s.tipo.fornecedores:
            if f.ativo and f.aprovado and f.id not in excluidos:
                grupos.setdefault(f.id, {"fornecedor": f, "itens": []})["itens"].append(s)
    return itens, grupos


@admin_bp.route("/enviar-lote")
@admin_required
def enviar_lote():
    expandir = request.args.get("expandir") == "1"
    busca = request.args.get("q", "").strip()
    excl_raw = request.args.get("excluir_fornecedores", "")
    excluir_fornecedores = {int(x) for x in excl_raw.split(",") if x.isdigit()}
    itens, grupos = _agrupar("AGUARDANDO_ENVIO_COTACAO", expandir=expandir, busca=busca or None,
                             excluir_fornecedores=excluir_fornecedores)
    base = _proximo_num_cotacao()
    lista = []
    for i, g in enumerate(grupos.values()):
        f = g["fornecedor"]
        seq = _seq_str(base + i)
        texto = _corpo_cotacao(f, g["itens"], incluir_spe=False)   # WhatsApp/Texto sem o quadro de CNPJs (item 91)
        lista.append({"fornecedor": f, "itens": g["itens"], "seq": seq, "wa": _wa_link(f, texto),
                      "assunto": _assunto_cotacao(f, seq), "texto": texto})
    return render_template("admin/enviar_lote.html", itens=itens, grupos=lista, expandir=expandir,
                           busca=busca, spes=SPES_COTACAO, excluir_fornecedores=excl_raw,
                           todos_fornecedores=Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome_fantasia).all())


@admin_bp.route("/enviar-lote/email", methods=["POST"])
@admin_required
def enviar_lote_email():
    """Prepara o link mailto: para 1 fornecedor, com a SPE escolhida no pop-up (item 120).
    CORRIGIDO (item 141): antes chamava enviar_email() (SMTP simulado do servidor, que não
    abre nada na tela do usuário). Agora devolve JSON com o link mailto: e o front-end abre
    o e-mail do próprio usuário — mesmo padrão do resto do sistema. Retorna JSON (não redirect)
    porque um redirect 302 do servidor para mailto: não é seguido de forma confiável."""
    fid = int(request.form.get("fornecedor_id"))
    spe = request.form.get("spe_nome") or None
    ids = request.form.getlist("ids")
    f = db.session.get(Fornecedor, fid) or abort(404)
    itens = [db.session.get(Solicitacao, int(i)) for i in ids]
    itens = [s for s in itens if s]
    if not itens or not (f.usa_email and f.email):
        return jsonify({"ok": False, "erro": "Fornecedor sem e-mail ou nenhum item selecionado."})
    seq = _seq_str(_proximo_num_cotacao())
    prazo_d, _ = _prazo_cotacao()
    for s in itens:
        db.session.add(PedidoCompra(solicitacao_id=s.id, enviado_por=current_user.id,
                                    destinatarios=f.email, cotacao_seq=seq))
        s.status = "AGUARDANDO_RECEBIMENTO_COTACAO"
        s.prazo_cotacao = prazo_d
        spe_txt = f" (SPE: {spe})" if spe else ""
        _log(s, f"Cotação {seq} — e-mail preparado (mailto) para {f.nome}{spe_txt}")
    db.session.commit()
    return jsonify({"ok": True, "mailto": _mailto(f, itens, seq, spe_escolhida=spe)})


@admin_bp.route("/enviar-lote/confirmar", methods=["POST"])
@admin_required
def enviar_lote_confirmar():
    corpo_base = request.form.get("corpo", "").strip()
    _, grupos = _agrupar("AGUARDANDO_ENVIO_COTACAO")
    if not grupos:
        flash("Não há solicitações para enviar cotação.", "warning")
        return redirect(url_for("admin.enviar_lote"))
    enviadas = {}
    seqs = {}
    ano = date.today().year
    n = _proximo_num_cotacao(ano)
    for g in grupos.values():
        f = g["fornecedor"]
        if not (f.usa_email and f.email):
            continue  # fornecedor sem e-mail: contato por WhatsApp/outro meio
        seq = _seq_str(n, ano); n += 1
        corpo = corpo_base or _corpo_cotacao(f, g["itens"])
        enviar_email(f.email, _assunto_cotacao(f, seq), corpo)
        for s in g["itens"]:
            enviadas.setdefault(s.id, set()).add(f.email)
            seqs.setdefault(s.id, seq)
    prazo_d, _ = _prazo_cotacao()
    for sid, emails in enviadas.items():
        s = db.session.get(Solicitacao, sid)
        db.session.add(PedidoCompra(solicitacao_id=sid, enviado_por=current_user.id,
                                    destinatarios=", ".join(sorted(emails)), cotacao_seq=seqs.get(sid)))
        s.status = "AGUARDANDO_RECEBIMENTO_COTACAO"
        s.prazo_cotacao = prazo_d
        _log(s, f"Cotação {seqs.get(sid)} enviada por e-mail (lote)")
    db.session.commit()
    flash(f"Cotação enviada: {len(grupos)} fornecedor(es), {len(enviadas)} solicitação(ões).", "success")
    return redirect(url_for("admin.dashboard"))


def _apos_orcamento(s):
    if s.status in ("AGUARDANDO_RECEBIMENTO_COTACAO", "AGUARDANDO_ENVIO_COTACAO"):
        s.status = "AGUARDANDO_DEFINICAO_FORNECEDOR"


@admin_bp.route("/solicitacao/<int:sid>/orcamento", methods=["POST"])
@admin_required
def lancar_orcamento(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    try:
        valor = float(request.form.get("valor_total", "0").replace(".", "").replace(",", "."))
    except ValueError:
        flash("Valor inválido.", "danger")
        return redirect(url_for("admin.solicitacao", sid=s.id))
    item = request.form.get("item_fornecedor", "").strip()
    if not item:
        flash("Informe o nome do item como o fornecedor descreveu (obrigatório).", "danger")
        return redirect(url_for("admin.solicitacao", sid=s.id))
    anexo = salvar_imagem(request.files.get("anexo")) if request.files.get("anexo") else None
    db.session.add(Orcamento(solicitacao_id=s.id, fornecedor_id=int(request.form["fornecedor_id"]), valor_total=valor,
        prazo_entrega=request.form.get("prazo_entrega", "").strip(), item_fornecedor=item,
        observacoes=request.form.get("observacoes", "").strip(), anexo_url=anexo, registrado_por=current_user.id))
    _apos_orcamento(s)
    _log(s, f"Orçamento lançado: {item} — R$ {valor:.2f}")
    db.session.commit()
    flash("Orçamento lançado.", "success")
    return redirect(url_for("admin.solicitacao", sid=s.id))


@admin_bp.route("/solicitacao/<int:sid>/definir", methods=["POST"])
@admin_required
def definir_fornecedor(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    oid = request.form.get("orcamento_id")
    o = db.session.get(Orcamento, int(oid)) if oid else None
    if not o or o.solicitacao_id != s.id:
        flash("Escolha um orçamento válido.", "danger")
        return redirect(url_for("admin.solicitacao", sid=s.id))
    ft = request.form.get("frete_tipo")
    if ft not in ("CIF", "FOB"):
        flash("Informe o tipo de frete (CIF ou FOB).", "danger")
        return redirect(url_for("admin.solicitacao", sid=s.id))
    modalidade = transp = cidade = None
    if ft == "FOB":
        modalidade = request.form.get("frete_modalidade")
        if modalidade == "TRANSPORTADORA":
            transp = request.form.get("transportadora_id") or None
            if not transp:
                flash("Indique a transportadora.", "danger")
                return redirect(url_for("admin.solicitacao", sid=s.id))
        elif modalidade == "COLABORADOR":
            cidade = request.form.get("cidade_retirada_id") or None
            if not cidade:
                flash("Indique a cidade de retirada.", "danger")
                return redirect(url_for("admin.solicitacao", sid=s.id))
        else:
            flash("No FOB, escolha Transportadora ou Colaborador do parque.", "danger")
            return redirect(url_for("admin.solicitacao", sid=s.id))
    prazo = request.form.get("prazo_recebimento")
    if not prazo:
        flash("Informe o prazo de recebimento (obrigatório).", "danger")
        return redirect(url_for("admin.solicitacao", sid=s.id))
    for outro in s.orcamentos:
        outro.escolhido = (outro.id == o.id)
    s.fornecedor_definido_id = o.fornecedor_id
    s.frete_tipo = ft
    s.frete_modalidade = modalidade
    s.transportadora_id = int(transp) if transp else None
    s.cidade_retirada_id = int(cidade) if cidade else None
    s.prazo_recebimento = datetime.strptime(prazo, "%Y-%m-%d").date()
    s.status = "AGUARDANDO_CHEGADA"
    _log(s, f"Fornecedor definido: {o.fornecedor.nome} (R$ {float(o.valor_total):.2f}) · frete {ft} · OC enviada")
    pdf = gerar_pdf_pedido(s)
    enviar_email(o.fornecedor.email, f"Ordem de Compra Nº {s.id}",
                 f"Prezados, confirmamos a compra do item da solicitação Nº {s.id}. Segue OC em anexo.",
                 anexo_bytes=pdf, anexo_nome=f"OC_{s.id}.pdf")
    db.session.commit()
    flash("Fornecedor definido e Ordem de Compra enviada. Status: Aguardando chegada.", "success")
    return redirect(url_for("admin.solicitacao", sid=s.id))


@admin_bp.route("/solicitacao/<int:sid>/remover-fornecedor/<int:fid>", methods=["POST"])
@admin_required
def remover_fornecedor(sid, fid):
    """Fornecedor não tem o item: remove-o da cotação desta solicitação (item 90)."""
    s = db.session.get(Solicitacao, sid) or abort(404)
    f = db.session.get(Fornecedor, fid) or abort(404)
    if f not in s.fornecedores_excluidos:
        s.fornecedores_excluidos.append(f)
        _log(s, f"Fornecedor {f.nome} removido da cotação (sem o item)")
        db.session.commit()
        flash(f"{f.nome} removido desta solicitação.", "success")
    return redirect(url_for("admin.solicitacao", sid=sid))


@admin_bp.route("/solicitacao/<int:sid>/restaurar-fornecedor/<int:fid>", methods=["POST"])
@admin_required
def restaurar_fornecedor(sid, fid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    f = db.session.get(Fornecedor, fid) or abort(404)
    if f in s.fornecedores_excluidos:
        s.fornecedores_excluidos.remove(f)
        _log(s, f"Fornecedor {f.nome} devolvido à cotação")
        db.session.commit()
        flash(f"{f.nome} devolvido à solicitação.", "success")
    return redirect(url_for("admin.solicitacao", sid=sid))


@admin_bp.route("/solicitacao/<int:sid>/reenviar-cotacao", methods=["POST"])
@admin_required
def reenviar_cotacao(sid):
    """Reenvio de cotação: renova o prazo e registra (item 99)."""
    s = db.session.get(Solicitacao, sid) or abort(404)
    s.prazo_cotacao = _prazo_cotacao()[0]
    if s.status == "AGUARDANDO_ENVIO_COTACAO":
        s.status = "AGUARDANDO_RECEBIMENTO_COTACAO"
    _log(s, "Cotação reenviada (prazo renovado)")
    db.session.commit()
    flash("Cotação marcada como reenviada e prazo renovado (5 dias úteis).", "success")
    return redirect(url_for("admin.solicitacao", sid=sid))


@admin_bp.route("/solicitacao/<int:sid>/duplicar", methods=["POST"])
@admin_required
def duplicar(sid):
    """Cria uma nova solicitação copiando os dados (item 106)."""
    s = db.session.get(Solicitacao, sid) or abort(404)
    nova = Solicitacao(solicitante_id=current_user.id, tipo_material_id=s.tipo_material_id,
                       material=s.material, quantidade=s.quantidade, fabricante=s.fabricante,
                       link_similar=s.link_similar, local_servico=s.local_servico,
                       status="AGUARDANDO_APROVACAO")
    db.session.add(nova)
    db.session.flush()
    _log(nova, f"Solicitação criada (duplicada da Nº {s.id})")
    db.session.commit()
    flash(f"Solicitação duplicada — nova Nº {nova.id} (aguardando aprovação).", "success")
    return redirect(url_for("admin.solicitacao", sid=nova.id))


@admin_bp.route("/pendencias")
@admin_required
def pendencias():
    """O que precisa de mim hoje (item 98)."""
    aprovar = Solicitacao.query.filter_by(status="AGUARDANDO_APROVACAO").order_by(Solicitacao.criado_em).all()
    vencidas = (Solicitacao.query.filter(Solicitacao.status == "AGUARDANDO_RECEBIMENTO_COTACAO",
                Solicitacao.prazo_cotacao.isnot(None), Solicitacao.prazo_cotacao < date.today())
                .order_by(Solicitacao.prazo_cotacao).all())
    atrasadas = (Solicitacao.query.filter(Solicitacao.status == "AGUARDANDO_CHEGADA",
                 Solicitacao.prazo_recebimento.isnot(None), Solicitacao.prazo_recebimento < date.today())
                 .order_by(Solicitacao.prazo_recebimento).all())
    return render_template("admin/pendencias.html", aprovar=aprovar, vencidas=vencidas, atrasadas=atrasadas)


@admin_bp.route("/precos")
@admin_required
def precos():
    """Histórico de preços por fornecedor (item 107)."""
    fid = request.args.get("fornecedor")
    q = Orcamento.query
    if fid:
        q = q.filter_by(fornecedor_id=int(fid))
    orcs = q.order_by(Orcamento.recebido_em.desc()).limit(300).all()
    grupos = {}
    for o in orcs:
        g = grupos.setdefault(o.fornecedor_id, {"fornecedor": o.fornecedor, "itens": []})
        g["itens"].append(o)
    return render_template("admin/precos.html",
        grupos=sorted(grupos.values(), key=lambda g: ((g["fornecedor"].nome or "") if g["fornecedor"] else "")),
        fornecedores=Fornecedor.query.order_by(Fornecedor.nome_fantasia).all(), f_forn=fid)


@admin_bp.route("/solicitacao/<int:sid>/quantidade", methods=["POST"])
@admin_required
def alterar_quantidade(sid):
    s = db.session.get(Solicitacao, sid) or abort(404)
    try:
        nova = int(request.form.get("quantidade"))
    except (TypeError, ValueError):
        flash("Quantidade inválida.", "danger")
        return redirect(url_for("admin.solicitacao", sid=s.id))
    if nova <= 0:
        flash("A quantidade deve ser maior que zero.", "danger")
    elif nova != s.quantidade:
        if s.quantidade_original is None:
            s.quantidade_original = s.quantidade
        anterior = s.quantidade
        s.quantidade = nova
        s.quantidade_alterada_por = current_user.id
        s.quantidade_alterada_em = datetime.utcnow()
        _log(s, f"Quantidade alterada de {anterior} para {nova}")
        db.session.commit()
        _mail_solic(s, f"Solicitação Nº {s.id} — quantidade ajustada",
                     f"A quantidade foi ajustada para {nova} pelo administrador.")
        flash("Quantidade atualizada.", "success")
    return redirect(request.referrer or url_for("admin.solicitacao", sid=s.id))


@admin_bp.route("/solicitacao/<int:sid>/editar-campos", methods=["POST"])
@admin_required
def editar_campos(sid):
    """Editar Tipo, Local/frente e Fabricante da solicitação (item 84)."""
    s = db.session.get(Solicitacao, sid) or abort(404)
    mudou = []
    novo_tipo = request.form.get("tipo_material_id") or None
    novo_tipo = int(novo_tipo) if novo_tipo else None
    if novo_tipo != s.tipo_material_id:
        ant = s.tipo.nome if s.tipo else "-"
        s.tipo_material_id = novo_tipo
        nt = db.session.get(TipoMaterial, novo_tipo) if novo_tipo else None
        mudou.append(f"Tipo: {ant} -> {nt.nome if nt else '-'}")
    local = (request.form.get("local_servico") or "").strip()
    if local != (s.local_servico or ""):
        mudou.append(f"Local/frente: {s.local_servico or '-'} -> {local or '-'}")
        s.local_servico = local
    fab = (request.form.get("fabricante") or "").strip()
    if fab != (s.fabricante or ""):
        mudou.append(f"Fabricante: {s.fabricante or '-'} -> {fab or '-'}")
        s.fabricante = fab
    if mudou:
        _log(s, "Edição — " + "; ".join(mudou))
        db.session.commit()
        flash("Solicitação atualizada.", "success")
    else:
        flash("Nada a alterar.", "info")
    return redirect(url_for("admin.solicitacao", sid=s.id))


@admin_bp.route("/cotacao/marcar-enviada/<int:fid>", methods=["POST"])
@admin_required
def marcar_cotacao_enviada(fid):
    """Marca a cotação como enviada para um fornecedor (item 72), com o novo fluxo
    de pop-up (item 119): 'finalizar=1' muda o status; 'finalizar=0' só grava no
    histórico da solicitação e mantém a tela aberta para continuar marcando outros
    fornecedores antes de fechar o processo."""
    f = db.session.get(Fornecedor, fid) or abort(404)
    base = (Solicitacao.query.filter_by(status="AGUARDANDO_ENVIO_COTACAO")
            .filter(Solicitacao.tipo_material_id.isnot(None)).all())
    itens = [s for s in base if s.tipo and any(t.id == fid for t in s.tipo.fornecedores)]
    ids = request.form.getlist("ids")
    if ids:
        alvo = {int(x) for x in ids}
        itens = [s for s in itens if s.id in alvo]
    if not itens:
        flash("Nenhuma solicitação pendente de cotação para este fornecedor.", "warning")
        return redirect(request.referrer or url_for("admin.enviar_lote"))

    finalizar = request.form.get("finalizar") == "1"
    seq = _seq_str(_proximo_num_cotacao())
    prazo_d, _ = _prazo_cotacao()
    for s in itens:
        db.session.add(PedidoCompra(solicitacao_id=s.id, enviado_por=current_user.id,
                                    destinatarios=(f.email or f.nome), cotacao_seq=seq))
        if finalizar:
            s.status = "AGUARDANDO_RECEBIMENTO_COTACAO"
            s.prazo_cotacao = prazo_d
            _log(s, f"Cotação {seq} marcada como enviada para {f.nome} (processo finalizado)")
        else:
            _log(s, f"Cotação {seq} marcada como enviada para {f.nome} (aguardando enviar a mais fornecedores)")
    db.session.commit()
    if finalizar:
        flash(f"Cotação {seq} enviada para {f.nome} e status atualizado ({len(itens)} item(ns)).", "success")
    else:
        flash(f"Registrado no histórico: cotação {seq} enviada para {f.nome}. Continue marcando outros fornecedores.", "success")
    return redirect(request.referrer or url_for("admin.enviar_lote"))


@admin_bp.route("/importar-orcamento", methods=["GET", "POST"])
@admin_required
def importar_orcamento():
    fornecedores = Fornecedor.query.order_by(Fornecedor.nome_fantasia).all()
    if request.method == "POST":
        fid = request.form.get("fornecedor_id")
        arq = request.files.get("pdf")
        if not fid or not arq or not arq.filename:
            flash("Selecione o fornecedor e o arquivo PDF.", "warning")
            return render_template("admin/importar_orcamento.html", fornecedores=fornecedores)
        try:
            itens = extrair_itens(arq)
        except Exception:
            itens = []
        if not itens:
            flash("Não consegui ler itens com valores nesse PDF.", "warning")
            return render_template("admin/importar_orcamento.html", fornecedores=fornecedores)
        abertas = (Solicitacao.query.filter(Solicitacao.status.in_(
            ["AGUARDANDO_RECEBIMENTO_COTACAO", "AGUARDANDO_DEFINICAO_FORNECEDOR", "AGUARDANDO_ENVIO_COTACAO"]))
            .order_by(Solicitacao.id).all())
        return render_template("admin/mapear_orcamento.html", itens=itens, abertas=abertas,
                               fornecedor=db.session.get(Fornecedor, int(fid)))
    return render_template("admin/importar_orcamento.html", fornecedores=fornecedores)


@admin_bp.route("/importar-orcamento/confirmar", methods=["POST"])
@admin_required
def confirmar_orcamento_pdf():
    fid = int(request.form["fornecedor_id"])
    n = int(request.form.get("n", 0))
    criados = 0
    for i in range(n):
        sid = request.form.get(f"sol_{i}")
        val = request.form.get(f"val_{i}")
        if not sid or not val:
            continue
        valor = _parse_valor(val)
        if valor is None:
            continue
        desc = (request.form.get(f"desc_{i}", "") or "").strip()
        db.session.add(Orcamento(solicitacao_id=int(sid), fornecedor_id=fid, valor_total=valor,
            item_fornecedor=desc[:300], observacoes=desc[:200], registrado_por=current_user.id))
        s = db.session.get(Solicitacao, int(sid))
        if s:
            _apos_orcamento(s)
        criados += 1
    db.session.commit()
    flash(f"{criados} orçamento(s) importado(s) do PDF.", "success")
    return redirect(url_for("admin.dashboard"))


# ---------------- Cadastros ----------------
@admin_bp.route("/backup")
@admin_required
def backup():
    """Baixar backup (item 108) — gera um dump .sql lógico (INSERT statements)
    a partir das tabelas do banco atual (SQLite local ou Postgres/Neon em produção).
    Não depende de pg_dump/binários externos."""
    from io import BytesIO
    from datetime import datetime as _dt
    from sqlalchemy import inspect as _inspect, text as _text

    insp = _inspect(db.engine)
    linhas = [f"-- Backup gerado em {_dt.now():%d/%m/%Y %H:%M:%S}",
              "-- Sistema de Solicitação de Materiais / Almoxarifado — Cluster Delta MA",
              "-- Dump lógico (INSERT statements), gerado pela própria aplicação.", ""]

    for table in db.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        colunas = [c["name"] for c in insp.get_columns(table.name)]
        linhas.append(f"-- Tabela: {table.name}")
        resultado = db.session.execute(_text(f'SELECT {", ".join(colunas)} FROM "{table.name}"'))
        for row in resultado:
            valores = []
            for v in row:
                if v is None:
                    valores.append("NULL")
                elif isinstance(v, (int, float)):
                    valores.append(str(v))
                else:
                    escapado = str(v).replace("'", "''")
                    valores.append(f"'{escapado}'")
            cols_sql = ", ".join(colunas)
            vals_sql = ", ".join(valores)
            linhas.append(f'INSERT INTO "{table.name}" ({cols_sql}) VALUES ({vals_sql});')
        linhas.append("")

    conteudo = "\n".join(linhas)
    buf = BytesIO(conteudo.encode("utf-8"))
    nome_arquivo = f"backup_{_dt.now():%Y%m%d_%H%M}.sql"
    return current_app.response_class(
        buf.getvalue(), mimetype="application/sql",
        headers={"Content-Disposition": f"attachment; filename={nome_arquivo}"})


@admin_bp.route("/log-sistema")
@admin_required
def log_sistema():
    from .models import AlmoxLog
    cat = (request.args.get("categoria") or "").strip()
    q = (request.args.get("q") or "").strip()
    di = request.args.get("data_ini") or ""
    dfim = request.args.get("data_fim") or ""
    qy = AlmoxLog.query
    if cat:
        qy = qy.filter(AlmoxLog.categoria == cat)
    if di:
        try: qy = qy.filter(AlmoxLog.criado_em >= datetime.strptime(di, "%Y-%m-%d"))
        except ValueError: pass
    if dfim:
        try:
            fim = datetime.strptime(dfim, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            qy = qy.filter(AlmoxLog.criado_em <= fim)
        except ValueError: pass
    logs = qy.order_by(AlmoxLog.criado_em.desc()).limit(2000 if q else 1000).all()
    if q:
        logs = [l for l in logs
                if contem_busca((l.detalhe or "") + " " + (l.autor_nome or ""), q)][:1000]
    categorias = sorted({l[0] for l in db.session.query(AlmoxLog.categoria).distinct().all() if l[0]})
    ctx = dict(categoria=cat, q=q, data_ini=di, data_fim=dfim)
    return render_template("admin/log_sistema.html", logs=logs, categorias=categorias, ctx=ctx)


@admin_bp.route("/cadastros")
@admin_required
def cadastros():
    n_forn_pend = Fornecedor.query.filter_by(aprovacao="pendente").count()
    n_transp_pend = Transportadora.query.filter_by(aprovacao="pendente").count()
    return render_template("admin/cadastros.html",
                           n_pendentes=(n_forn_pend + n_transp_pend))


@admin_bp.route("/cadastros-pendentes")
@admin_required
def cadastros_pendentes():
    """Tela de aprovação dos cadastros criados automaticamente pelo Relatório de
    Carga ao detectar um CNPJ novo (item 145)."""
    fornecedores = (Fornecedor.query.filter_by(aprovacao="pendente")
                    .order_by(Fornecedor.razao_social).all())
    transportadoras = (Transportadora.query.filter_by(aprovacao="pendente")
                       .order_by(Transportadora.nome).all())
    return render_template("admin/cadastros_pendentes.html",
                           fornecedores=fornecedores, transportadoras=transportadoras)


@admin_bp.route("/cadastros-pendentes/fornecedor/<int:fid>", methods=["POST"])
@admin_required
def pendente_fornecedor_acao(fid):
    f = db.session.get(Fornecedor, fid) or abort(404)
    acao = request.form.get("acao")
    if acao == "aprovar":
        f.aprovacao = "aprovado"
        db.session.commit()
        flash(f"Fornecedor {f.nome} aprovado.", "success")
    elif acao == "rejeitar":
        db.session.delete(f)
        db.session.commit()
        flash("Cadastro de fornecedor rejeitado e removido.", "success")
    return redirect(url_for("admin.cadastros_pendentes"))


@admin_bp.route("/cadastros-pendentes/transportadora/<int:tid>", methods=["POST"])
@admin_required
def pendente_transportadora_acao(tid):
    t = db.session.get(Transportadora, tid) or abort(404)
    acao = request.form.get("acao")
    if acao == "aprovar":
        t.aprovacao = "aprovado"
        db.session.commit()
        flash(f"Transportadora {t.nome} aprovada.", "success")
    elif acao == "rejeitar":
        db.session.delete(t)
        db.session.commit()
        flash("Cadastro de transportadora rejeitado e removido.", "success")
    return redirect(url_for("admin.cadastros_pendentes"))


def _registrar_papel(usuario, novo_papel, autor):
    """Fecha o período do papel anterior e abre o novo no histórico."""
    aberto = (HistoricoPapel.query
              .filter_by(usuario_id=usuario.id, fim=None)
              .order_by(HistoricoPapel.inicio.desc()).first())
    if aberto and aberto.papel == novo_papel:
        return
    if aberto:
        aberto.fim = datetime.utcnow()
    db.session.add(HistoricoPapel(usuario_id=usuario.id, pessoa_nome=usuario.nome,
                                  papel=novo_papel, alterado_por=autor.id))


@admin_bp.route("/usuarios", methods=["GET", "POST"])
@admin_required
def usuarios():
    if not current_user.is_master:
        flash("A tela de Usuários - Antigo é acessível apenas ao Admin Master.", "warning")
        return redirect(url_for("admin.cadastros"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        papel = request.form.get("papel", "solicitante")
        if papel == "admin" and not current_user.is_master:
            flash("Apenas o Admin Master pode criar administradores.", "danger")
            return redirect(url_for("admin.usuarios"))
        if Usuario.query.filter_by(email=email).first():
            flash("Já existe usuário com esse e-mail.", "warning")
        else:
            u = Usuario(nome=_mai(request.form.get("nome")), email=email,
                        papel=papel, empresa_id=request.form.get("empresa_id") or None,
                        senha_temporaria=True)
            u.set_senha(request.form.get("senha", ""))
            db.session.add(u)
            db.session.flush()
            _registrar_papel(u, papel, current_user)
            db.session.commit()
            flash("Usuário criado. Ele trocará a senha no primeiro acesso.", "success")
        return redirect(url_for("admin.usuarios"))
    colabs = Colaborador.query.filter_by(ativo=True).order_by(Colaborador.nome).all()
    return render_template("admin/usuarios.html",
                           lista=Usuario.query.order_by(Usuario.nome).all(),
                           empresas=Empresa.query.filter_by(ativo=True).order_by(Empresa.nome).all(),
                           colaboradores=colabs)


@admin_bp.route("/usuarios/<int:uid>", methods=["POST"])
@admin_required
def usuario_editar(uid):
    u = db.session.get(Usuario, uid) or abort(404)
    if not current_user.pode_gerir(u):
        flash("Você não tem permissão para editar este usuário.", "danger")
        return redirect(url_for("admin.usuarios"))
    novo_email = request.form.get("email", "").strip().lower()
    if novo_email and novo_email != u.email:
        if Usuario.query.filter(Usuario.email == novo_email, Usuario.id != u.id).first():
            flash("Já existe usuário com esse e-mail.", "warning")
            return redirect(url_for("admin.usuarios"))
        u.email = novo_email
    u.nome = _mai(request.form.get("nome")) or u.nome
    novo_papel = request.form.get("papel", u.papel)
    if u.is_master:
        novo_papel = "admin"   # master é sempre admin; não pode ser rebaixado
    if novo_papel == "admin" and u.papel != "admin" and not current_user.is_master:
        flash("Apenas o Admin Master pode promover a administrador.", "danger")
        return redirect(url_for("admin.usuarios"))
    if novo_papel != u.papel:
        u.papel = novo_papel
        _registrar_papel(u, novo_papel, current_user)
    u.empresa_id = request.form.get("empresa_id") or None
    if u.is_master:
        u.ativo = True         # master nunca é desativado
    else:
        u.ativo = request.form.get("ativo") == "1"
    nova = request.form.get("nova_senha", "").strip()
    if nova:
        u.set_senha(nova)
        u.senha_temporaria = True
        flash(f"Senha de {u.nome} redefinida (ele troca no próximo acesso).", "success")
    db.session.commit()
    flash("Usuário atualizado.", "success")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/usuarios/promover-colaborador", methods=["POST"])
@admin_required
def promover_colaborador():
    """Transforma um colaborador de campo em usuário que loga (Etapa 2.5)."""
    cid = request.form.get("colaborador_id")
    colab = db.session.get(Colaborador, int(cid)) if cid and cid.isdigit() else None
    if not colab:
        flash("Selecione um colaborador válido.", "danger")
        return redirect(url_for("admin.usuarios"))
    email = request.form.get("email", "").strip().lower()
    papel = request.form.get("papel", "solicitante")
    if papel == "admin" and not current_user.is_master:
        flash("Apenas o Admin Master pode promover a administrador.", "danger")
        return redirect(url_for("admin.usuarios"))
    if not email:
        flash("Informe o e-mail de acesso do novo usuário.", "danger")
        return redirect(url_for("admin.usuarios"))
    if Usuario.query.filter_by(email=email).first():
        flash("Já existe usuário com esse e-mail.", "warning")
        return redirect(url_for("admin.usuarios"))
    u = Usuario(nome=colab.nome, email=email, papel=papel, senha_temporaria=True)
    u.set_senha(request.form.get("senha", "") or "Trocar@123")
    db.session.add(u)
    db.session.flush()
    _registrar_papel(u, papel, current_user)
    db.session.commit()
    flash(f"{colab.nome} agora acessa o sistema como {papel}. Senha provisória definida.", "success")
    return redirect(url_for("admin.usuarios"))


@admin_bp.route("/usuarios/<int:uid>/historico")
@admin_required
def usuario_historico(uid):
    u = db.session.get(Usuario, uid) or abort(404)
    hist = (HistoricoPapel.query.filter_by(usuario_id=u.id)
            .order_by(HistoricoPapel.inicio.desc()).all())
    return render_template("admin/usuario_historico.html", u=u, hist=hist)


def _cad_simples(model, template, label, extra=None):
    """Cria/lista um cadastro simples (nome [+ extra])."""
    if request.method == "POST":
        nome = _mai(request.form.get("nome"))
        if nome:
            obj = model(nome=nome)
            if extra:
                extra(obj)
            db.session.add(obj)
            db.session.commit()
            flash(f"{label} cadastrado(a).", "success")
        return redirect(request.path)
    return render_template(template, lista=model.query.order_by(model.nome).all())


@admin_bp.route("/tipos", methods=["GET", "POST"])
@admin_required
def tipos():
    if request.method == "POST":
        nome = _mai(request.form.get("nome"))
        if nome and not TipoMaterial.query.filter_by(nome=nome).first():
            db.session.add(TipoMaterial(nome=nome, ativo=True))
            db.session.commit()
            flash("Tipo cadastrado.", "success")
        return redirect(url_for("admin.tipos"))
    return render_template("admin/tipos.html", lista=TipoMaterial.query.order_by(TipoMaterial.nome).all(),
                           fornecedores=Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.nome_fantasia).all())


@admin_bp.route("/tipos/<int:tid>", methods=["POST"])
@admin_required
def tipo_editar(tid):
    t = db.session.get(TipoMaterial, tid) or abort(404)
    ids_fornecedores = {int(x) for x in request.form.getlist("fornecedores")}
    novo_nome = _mai(request.form.get("nome")) or t.nome
    novo_ativo = request.form.get("ativo") == "1"
    with db.session.no_autoflush:
        novos_fornecedores = Fornecedor.query.filter(Fornecedor.id.in_(ids_fornecedores)).all() if ids_fornecedores else []
        t.fornecedores = novos_fornecedores
    t.nome = novo_nome
    t.ativo = novo_ativo
    db.session.commit()
    flash("Tipo atualizado.", "success")
    return redirect(url_for("admin.tipos"))


@admin_bp.route("/cidades", methods=["GET", "POST"])
@admin_required
def cidades():
    if request.method == "POST":
        nome = _mai(request.form.get("nome"))
        if nome:
            db.session.add(Cidade(nome=nome, uf=(request.form.get("uf", "").strip().upper()[:2] or None)))
            db.session.commit()
            flash("Cidade cadastrada.", "success")
        return redirect(url_for("admin.cidades"))
    return render_template("admin/cidades.html", lista=Cidade.query.order_by(Cidade.nome).all())


@admin_bp.route("/cidades/<int:cid>", methods=["POST"])
@admin_required
def cidade_editar(cid):
    c = db.session.get(Cidade, cid) or abort(404)
    c.nome = _mai(request.form.get("nome")) or c.nome
    c.uf = request.form.get("uf", "").strip().upper()[:2] or None
    c.ativo = request.form.get("ativo") == "1"
    db.session.commit()
    flash("Cidade atualizada.", "success")
    return redirect(url_for("admin.cidades"))


@admin_bp.route("/transportadoras", methods=["GET", "POST"])
@admin_required
def transportadoras():
    return _cad_simples(Transportadora, "admin/transportadoras.html", "Transportadora")


@admin_bp.route("/transportadoras/<int:tid>", methods=["POST"])
@admin_required
def transportadora_editar(tid):
    t = db.session.get(Transportadora, tid) or abort(404)
    t.nome = _mai(request.form.get("nome")) or t.nome
    t.ativo = request.form.get("ativo") == "1"
    db.session.commit()
    flash("Transportadora atualizada.", "success")
    return redirect(url_for("admin.transportadoras"))


@admin_bp.route("/empresas", methods=["GET", "POST"])
@admin_required
def empresas():
    return _cad_simples(Empresa, "admin/empresas.html", "Empresa")


@admin_bp.route("/empresas/<int:eid>", methods=["POST"])
@admin_required
def empresa_editar(eid):
    e = db.session.get(Empresa, eid) or abort(404)
    e.nome = _mai(request.form.get("nome")) or e.nome
    e.ativo = request.form.get("ativo") == "1"
    db.session.commit()
    flash("Empresa atualizada.", "success")
    return redirect(url_for("admin.empresas"))


def _aplicar_fornecedor(f):
    f.razao_social = _mai(request.form.get("razao_social"))
    f.nome_fantasia = _mai(request.form.get("nome_fantasia"))
    f.email = request.form.get("email", "").strip()
    f.usa_email = request.form.get("usa_email") == "1"
    f.contato_nome = _mai(request.form.get("contato_nome"))
    e164, exib = normalizar_telefone_br(request.form.get("telefone", "").strip())
    f.telefone = exib or request.form.get("telefone", "").strip()
    f.telefone_e164 = e164
    f.tipos = TipoMaterial.query.filter(TipoMaterial.id.in_(request.form.getlist("tipos"))).all()
    # item 150 — CNPJ, IE e endereço estruturado
    cnpj_raw = request.form.get("cnpj", "").strip()
    f.cnpj = formatar_cnpj(cnpj_raw) if cnpj_valido(cnpj_raw) else (cnpj_raw or None)
    f.inscricao_estadual = formatar_ie(request.form.get("inscricao_estadual", "").strip())
    f.cep = request.form.get("cep", "").strip() or None
    f.logradouro = _mai(request.form.get("logradouro"))
    f.numero = request.form.get("numero", "").strip() or None
    f.bairro = _mai(request.form.get("bairro"))
    f.complemento = _mai(request.form.get("complemento"))
    f.cidade = _mai(request.form.get("cidade"))
    f.estado = (request.form.get("estado", "").strip().upper() or None)
    # papéis (item 150) — pode ser fornecedor, empresa interna, ou ambos
    f.is_fornecedor = request.form.get("is_fornecedor") == "1"
    f.is_empresa_interna = request.form.get("is_empresa_interna") == "1"
    # se não marcou nenhum, assume fornecedor (não deixa cadastro "órfão")
    if not f.is_fornecedor and not f.is_empresa_interna:
        f.is_fornecedor = True


@admin_bp.route("/fornecedores", methods=["GET", "POST"])
@admin_required
def fornecedores():
    tipos = TipoMaterial.query.filter_by(ativo=True).order_by(TipoMaterial.nome).all()
    if request.method == "POST":
        # CNPJ obrigatório e válido nos cadastros novos (item 150)
        cnpj_raw = request.form.get("cnpj", "").strip()
        if not cnpj_valido(cnpj_raw):
            flash("Informe um CNPJ válido — ele é obrigatório em novos cadastros.", "warning")
            return redirect(url_for("admin.fornecedores"))
        f = Fornecedor(email="")
        _aplicar_fornecedor(f)
        f.ativo = True
        db.session.add(f)
        db.session.commit()
        flash("Cadastro salvo.", "success")
        return redirect(url_for("admin.fornecedores"))

    # Lista unificada (fornecedores + empresas internas). Filtros: busca e incompletos.
    busca = (request.args.get("q") or "").strip()
    so_incompletos = request.args.get("incompletos") == "1"
    lista = Fornecedor.query.order_by(Fornecedor.nome_fantasia, Fornecedor.razao_social).all()
    if so_incompletos:
        lista = [f for f in lista if f.cadastro_incompleto and f.ativo]
    if busca:
        bsa = sem_acentos(busca)
        # a busca reconhece palavras-chave de PAPEL, além de nome/CNPJ/cidade.
        quer_empresa = any(p in bsa for p in ("empresa", "interna", "empresa interna"))
        quer_fornecedor = "fornecedor" in bsa
        quer_sem_cnpj = any(p in bsa for p in ("sem cnpj", "incompleto", "sem cadastro"))

        def _bate(f):
            # palavra-chave de papel casa direto
            if quer_empresa and f.is_empresa_interna:
                return True
            if quer_fornecedor and f.is_fornecedor:
                return True
            if quer_sem_cnpj and f.cadastro_incompleto:
                return True
            # texto do cadastro (inclui o papel por extenso, para busca natural)
            papel_txt = " ".join(["empresa interna" if f.is_empresa_interna else "",
                                  "fornecedor" if f.is_fornecedor else ""])
            campos = " ".join([f.nome or "", f.cnpj or "", f.cidade or "", papel_txt])
            return contem_busca(campos, busca)

        lista = [f for f in lista if _bate(f)]
    return render_template("admin/fornecedores.html", lista=lista, tipos=tipos,
                           busca=busca, so_incompletos=so_incompletos)


@admin_bp.route("/fornecedores/<int:fid>/editar", methods=["GET", "POST"])
@admin_required
def fornecedor_editar(fid):
    f = db.session.get(Fornecedor, fid) or abort(404)
    tipos = TipoMaterial.query.filter_by(ativo=True).order_by(TipoMaterial.nome).all()
    if request.method == "POST":
        _aplicar_fornecedor(f)
        f.ativo = request.form.get("ativo") == "1"
        db.session.commit()
        flash("Fornecedor atualizado.", "success")
        return redirect(url_for("admin.fornecedores"))
    return render_template("admin/fornecedor_editar.html", f=f, tipos=tipos, tipos_ids={t.id for t in f.tipos})


@admin_bp.route("/fornecedores/<int:fid>/toggle-ativo", methods=["POST"])
@admin_required
def fornecedor_toggle_ativo(fid):
    """Ativar/desativar fornecedor com 1 clique na listagem (item 124)."""
    f = db.session.get(Fornecedor, fid) or abort(404)
    f.ativo = not f.ativo
    db.session.commit()
    flash(f"{f.nome} {'ativado' if f.ativo else 'desativado'}.", "success")
    return redirect(url_for("admin.fornecedores"))


@admin_bp.route("/coletas-proprias")
@admin_required
def coletas_proprias():
    """Solicitações com frete FOB/retirada por colaborador (item 125), agrupadas por
    cidade e, dentro de cada cidade, por fornecedor (item 142) — com o contato do
    fornecedor (nome/e-mail/telefone) ao lado, e texto pronto para o motorista."""
    itens = (Solicitacao.query
             .filter_by(frete_tipo="FOB", frete_modalidade="COLABORADOR")
             .filter(Solicitacao.status.notin_(["CONCLUIDO", "CANCELADA"]))
             .order_by(Solicitacao.cidade_retirada_id, Solicitacao.id).all())

    # estrutura: { cidade: { "fornecedores": { fid: {"fornecedor": f, "itens": [...] } } } }
    grupos = {}
    for s in itens:
        cidade = s.cidade_retirada.rotulo if s.cidade_retirada else "Sem cidade definida"
        f = s.fornecedor_definido
        chave_f = f.id if f else 0
        cid = grupos.setdefault(cidade, {})
        bloco = cid.setdefault(chave_f, {"fornecedor": f, "itens": []})
        bloco["itens"].append(s)

    # ordena fornecedores por nome dentro de cada cidade
    grupos_ord = {}
    for cidade, fdict in grupos.items():
        grupos_ord[cidade] = sorted(
            fdict.values(),
            key=lambda b: ((b["fornecedor"].nome or "").lower() if b["fornecedor"] else "zzz"))

    # texto pronto por cidade (agrupado por fornecedor)
    textos = {}
    for cidade, blocos in grupos_ord.items():
        linhas = [f"🚚 Coleta em {cidade}", ""]
        for b in blocos:
            f = b["fornecedor"]
            if f:
                cab = f.nome
                contato = " · ".join(x for x in [f.contato_nome, f.telefone, f.email] if x)
                linhas.append(f"▶ {cab}" + (f"  ({contato})" if contato else ""))
            else:
                linhas.append("▶ Fornecedor não definido")
            for s in b["itens"]:
                linhas.append(f"   #{s.id} — {s.material} (x{s.quantidade})")
            linhas.append("")
        textos[cidade] = "\n".join(linhas).strip()

    return render_template("admin/coletas_proprias.html", grupos=grupos_ord, textos=textos)


@admin_bp.route("/sugestoes")
@admin_required
def sugestoes():
    return render_template("admin/sugestoes.html",
                           lista=Sugestao.query.order_by(Sugestao.criado_em.desc()).all())


def _melhor_por_fornecedor(s):
    """Menor orçamento de cada fornecedor para a solicitação s."""
    por_forn = {}
    for o in s.orcamentos:
        atual = por_forn.get(o.fornecedor_id)
        if atual is None or o.valor_total < atual.valor_total:
            por_forn[o.fornecedor_id] = o
    return sorted(por_forn.values(), key=lambda o: o.valor_total)


@admin_bp.route("/comparativo")
@admin_required
def comparativo():
    """Compras aguardando definição de fornecedor. Visão por produto ou por fornecedor."""
    modo = request.args.get("modo", "produto")
    sols = (Solicitacao.query.filter_by(status="AGUARDANDO_DEFINICAO_FORNECEDOR")
            .order_by(Solicitacao.id).all())
    if modo == "fornecedor":
        # Agrupa por fornecedor as solicitações em que ele é o MAIS BARATO
        grupos = {}
        for s in sols:
            melhores = _melhor_por_fornecedor(s)
            if not melhores:
                continue
            vencedor = melhores[0]
            g = grupos.setdefault(vencedor.fornecedor_id, {"fornecedor": vencedor.fornecedor, "itens": [], "total": 0.0})
            g["itens"].append({"s": s, "orc": vencedor})
            g["total"] += float(vencedor.valor_total)
        return render_template("admin/comparativo.html", modo=modo, grupos=sorted(grupos.values(), key=lambda g: g["fornecedor"].nome))
    dados = [{"s": s, "melhores": _melhor_por_fornecedor(s)} for s in sols]
    return render_template("admin/comparativo.html", modo="produto", dados=dados)


@admin_bp.route("/aprovar-fornecedor", methods=["POST"])
@admin_required
def aprovar_fornecedor():
    """Define um fornecedor como vencedor em TODAS as compras em que ele é o mais barato."""
    fid = int(request.form["fornecedor_id"])
    prazo = request.form.get("prazo_recebimento")
    if not prazo:
        flash("Informe o prazo de recebimento para aprovar em lote.", "danger")
        return redirect(url_for("admin.comparativo", modo="fornecedor"))
    ft = request.form.get("frete_tipo") or "CIF"
    prazo_d = datetime.strptime(prazo, "%Y-%m-%d").date()
    sols = Solicitacao.query.filter_by(status="AGUARDANDO_DEFINICAO_FORNECEDOR").all()
    n = 0
    for s in sols:
        melhores = _melhor_por_fornecedor(s)
        if not melhores or melhores[0].fornecedor_id != fid:
            continue
        o = melhores[0]
        for outro in s.orcamentos:
            outro.escolhido = (outro.id == o.id)
        s.fornecedor_definido_id = fid
        s.frete_tipo = ft
        s.prazo_recebimento = prazo_d
        s.status = "AGUARDANDO_CHEGADA"
        _log(s, f"Fornecedor definido em lote: {o.fornecedor.nome} (R$ {float(o.valor_total):.2f}) · OC enviada")
        pdf = gerar_pdf_pedido(s)
        enviar_email(o.fornecedor.email, f"Ordem de Compra Nº {s.id}",
                     f"Prezados, confirmamos a compra do item da solicitação Nº {s.id}. Segue OC em anexo.",
                     anexo_bytes=pdf, anexo_nome=f"OC_{s.id}.pdf")
        n += 1
    db.session.commit()
    flash(f"{n} compra(s) aprovada(s) para o fornecedor de uma vez.", "success")
    return redirect(url_for("admin.comparativo", modo="fornecedor"))


@admin_bp.route("/tipos/ativar-todos", methods=["POST"])
@admin_required
def tipos_ativar_todos():
    TipoMaterial.query.update({TipoMaterial.ativo: True})
    db.session.commit()
    flash("Todos os tipos de material foram ativados.", "success")
    return redirect(url_for("admin.tipos"))


@admin_bp.route("/atividades", methods=["GET", "POST"])
@admin_required
def atividades():
    return _cad_simples(Atividade, "admin/atividades.html", "Atividade")


@admin_bp.route("/atividades/<int:aid>", methods=["POST"])
@admin_required
def atividade_editar(aid):
    a = db.session.get(Atividade, aid) or abort(404)
    a.nome = _mai(request.form.get("nome")) or a.nome
    a.ativo = request.form.get("ativo") == "1"
    db.session.commit()
    flash("Atividade atualizada.", "success")
    return redirect(url_for("admin.atividades"))


# ---------------- Cadastro rápido (inline / JSON) ----------------
@admin_bp.route("/api/criar/<entidade>", methods=["POST"])
@admin_required
@csrf.exempt
def api_criar(entidade):
    nome = ((request.json or {}).get("nome", "") if request.is_json else request.form.get("nome", "")).strip().upper()
    if not nome:
        return jsonify(ok=False, erro="nome vazio"), 400
    mapa = {"tipo": TipoMaterial, "cidade": Cidade, "transportadora": Transportadora,
            "empresa": Empresa, "atividade": Atividade}
    model = mapa.get(entidade)
    if not model:
        return jsonify(ok=False, erro="entidade inválida"), 400
    obj = model(nome=nome)
    if entidade == "cidade":
        uf = ((request.json or {}).get("uf") if request.is_json else request.form.get("uf")) or ""
        obj.uf = uf.strip().upper()[:2] or None
    db.session.add(obj)
    db.session.commit()
    rotulo = obj.rotulo if entidade == "cidade" else obj.nome
    return jsonify(ok=True, id=obj.id, nome=rotulo)
