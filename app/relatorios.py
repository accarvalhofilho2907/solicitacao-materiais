"""Relatórios e Impressões — Geração de Etiquetas (item 109, revisado 133) e
Relatório de Recebimento/Envio de Materiais (item 111, unificado no item 128).

Regras confirmadas com o usuário (08/07/2026):
- Etiquetas: "Etiqueta de caixas/embalagens" (era "Envio de Material") e "Identificação
  de Item" (campo livre + moldura Serena). Tipo "Devolução" foi descartado.
  Remetente aceita "Outro" (texto livre) além das 15 Deltas (item 133).
- Relatório de Recebimento/Envio: UMA tela só; o campo Status decide se é
  Recebimento ou Envio (item 128). Responsável é dropdown de Usuários.
- Fotos (NF, CT-e, avarias) são temporárias — só para montar o PDF gerado na
  hora; não ficam salvas no sistema (confirmado 08/07/2026).
- Nenhum dos dois relatórios de carga é salvo no banco — só gera o PDF na hora.
"""
from functools import wraps
from datetime import date
from io import BytesIO
import re

from flask import Blueprint, render_template, request, abort, send_file, flash, redirect, url_for, current_app, Response
from flask_login import login_required, current_user

from .extensions import db
from .models import (Fornecedor, Usuario, Transportadora,
                     TIPOS_VOLUME, NATUREZAS_OPERACAO)
from .admin import SPES_COTACAO
from .util import so_digitos, cnpj_valido, formatar_cnpj, formatar_ie
from .pdf_etiquetas import gerar_pdf_etiquetas_envio, gerar_pdf_etiquetas_identificacao
from .pdf_carga import gerar_pdf_relatorio_carga

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")

REMETENTE_FIXO = {
    "nome": "Antonio Carlos Carvalho",
    "telefone": "(86) 99939-9872",
    "email": "antonio.carvalho@srna.co",
}

SELOS_CARGA = [
    ("FRAGIL", "Frágil"),
    ("EXPLOSIVO", "Explosivo"),
    ("EMPILHAR", "Pode empilhar"),
    ("NAO_EMPILHAR", "Não empilhar"),
]

GRIDS_VALIDOS = (1, 2, 4, 6, 8, 10, 12, 14, 16)


def relatorios_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not (current_user.is_almox or current_user.is_admin):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@relatorios_bp.route("/etiquetas", methods=["GET"])
@relatorios_required
def etiquetas():
    fornecedores = (Fornecedor.query.filter_by(ativo=True)
                    .filter((Fornecedor.aprovacao == "aprovado") | (Fornecedor.aprovacao.is_(None)))
                    .order_by(Fornecedor.razao_social).all())
    return render_template("relatorios/etiquetas.html", deltas=SPES_COTACAO,
                           fornecedores=fornecedores, remetente_fixo=REMETENTE_FIXO,
                           selos=SELOS_CARGA, grids=GRIDS_VALIDOS)




def _gerar_pdf_envio_a_partir_do_form(f):
    delta_nome = f.get("delta_nome", "")
    # Contato do remetente: padrão Antonio Carlos Carvalho, mas editável (item 144)
    contato_nome = f.get("rem_contato", "").strip() or REMETENTE_FIXO["nome"]
    contato_tel = f.get("rem_telefone", "").strip() or REMETENTE_FIXO["telefone"]
    if delta_nome == "OUTRO":
        remetente = {
            "nome": f.get("outro_nome", "").strip() or "Remetente não informado",
            "endereco": f.get("outro_endereco", "").strip(),
            "cnpj": f.get("outro_cnpj", "").strip(),
            "contato": contato_nome, "telefone": contato_tel,
        }
    else:
        delta = next((d for d in SPES_COTACAO if d[0] == delta_nome), None)
        if not delta:
            abort(400, "Delta (remetente) inválida.")
        remetente = {
            "nome": delta[0], "endereco": delta[1], "cnpj": delta[2],
            "contato": contato_nome, "telefone": contato_tel,
        }
    destinatario = {
        "nome": f.get("dest_nome", ""), "endereco": f.get("dest_endereco", ""),
        "cnpj": f.get("dest_cnpj", ""), "contato": f.get("dest_contato", ""),
        "telefone": f.get("dest_telefone", ""), "email": f.get("dest_email", ""),
    }
    try:
        volumes = max(1, int(f.get("volumes", 1)))
    except ValueError:
        volumes = 1
    try:
        por_folha = int(f.get("por_folha", 4))
    except ValueError:
        por_folha = 4
    if por_folha not in GRIDS_VALIDOS:
        por_folha = 4
    orientacao = f.get("orientacao", "retrato")
    if orientacao not in ("retrato", "paisagem"):
        orientacao = "retrato"
    nota_fiscal = f.get("nota_fiscal", "").strip() or None
    selos = f.getlist("selos")

    return gerar_pdf_etiquetas_envio(remetente, destinatario, volumes, por_folha,
                                     nota_fiscal=nota_fiscal, selos=selos, orientacao=orientacao)


@relatorios_bp.route("/etiquetas/envio/gerar", methods=["POST"])
@relatorios_required
def etiquetas_envio_gerar():
    pdf = _gerar_pdf_envio_a_partir_do_form(request.form)
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="etiquetas_caixas_embalagens.pdf")


@relatorios_bp.route("/etiquetas/envio/gerar-para-email", methods=["POST"])
@relatorios_required
def etiquetas_envio_gerar_email():
    """Gera o mesmo PDF, com nome de arquivo pensado para o usuário baixar e anexar
    manualmente ao e-mail (itens 133/148). Navegadores não permitem anexar arquivo
    automaticamente via mailto, então o botão combinado (item 148) baixa este PDF e
    abre o e-mail em seguida, cabendo ao usuário arrastar o arquivo para o e-mail."""
    pdf = _gerar_pdf_envio_a_partir_do_form(request.form)
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="etiquetas_para_anexar_email.pdf")


@relatorios_bp.route("/etiquetas/identificacao/gerar", methods=["POST"])
@relatorios_required
def etiquetas_identificacao_gerar():
    f = request.form
    texto = f.get("texto_livre", "").strip()
    if not texto:
        abort(400, "Informe o texto da etiqueta.")
    try:
        quantidade = max(1, int(f.get("quantidade", 1)))
    except ValueError:
        quantidade = 1
    try:
        por_folha = int(f.get("por_folha", 4))
    except ValueError:
        por_folha = 4
    if por_folha not in GRIDS_VALIDOS:
        por_folha = 4
    orientacao = f.get("orientacao", "retrato")
    if orientacao not in ("retrato", "paisagem"):
        orientacao = "retrato"

    pdf = gerar_pdf_etiquetas_identificacao(texto, quantidade, por_folha, orientacao=orientacao)
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="etiquetas_identificacao_item.pdf")


@relatorios_bp.route("/carga", methods=["GET"])
@relatorios_required
def carga():
    """Tela única de Relatório de Carga (itens 128/145/150) — o campo Status decide se é
    Recebimento ou Envio. Passa Usuários, tipos de volume, naturezas, e os CNPJs já
    cadastrados (com endereço estruturado) para autopreenchimento."""
    usuarios = Usuario.query.filter_by(ativo=True).order_by(Usuario.nome).all()

    def _dados_endereco(obj):
        return {"cep": obj.cep or "", "logradouro": obj.logradouro or "", "numero": obj.numero or "",
                "bairro": obj.bairro or "", "complemento": obj.complemento or "",
                "cidade": obj.cidade or "", "estado": obj.estado or "",
                "endereco": obj.endereco_completo or obj.endereco or ""}

    # Cadastro unificado (item 150): fornecedores E empresas internas entram no autopreenchimento.
    fornecedores = {}
    for fo in Fornecedor.query.filter(Fornecedor.cnpj.isnot(None)).all():
        d = so_digitos(fo.cnpj)
        if d:
            dados = {"nome": fo.razao_social or fo.nome or "", "ie": fo.inscricao_estadual or ""}
            dados.update(_dados_endereco(fo))
            fornecedores[d] = dados
    # Transportadoras seguem na sua própria tabela
    transportadoras = {}
    for tr in Transportadora.query.filter(Transportadora.cnpj.isnot(None)).all():
        d = so_digitos(tr.cnpj)
        if d:
            transportadoras[d] = {"nome": tr.nome or "", "endereco": tr.endereco or "",
                                  "cep": "", "logradouro": "", "numero": "", "bairro": "",
                                  "complemento": "", "cidade": "", "estado": ""}
    return render_template("relatorios/carga.html", hoje=date.today().strftime("%Y-%m-%d"),
                           usuario_atual_id=current_user.id, usuarios=usuarios,
                           tipos_volume=TIPOS_VOLUME, naturezas=NATUREZAS_OPERACAO,
                           mapa_fornecedores=fornecedores, mapa_transportadoras=transportadoras)


def _garantir_fornecedor_pendente(nome, cnpj_raw, ie, endereco, end_estrut=None):
    """Se o CNPJ é válido e ainda não existe em Fornecedor, cria um cadastro
    PENDENTE de aprovação (item 145/150). Devolve (criado: bool)."""
    if not cnpj_valido(cnpj_raw):
        return False
    cnpj_fmt = formatar_cnpj(cnpj_raw)
    d = so_digitos(cnpj_raw)
    for fo in Fornecedor.query.filter(Fornecedor.cnpj.isnot(None)).all():
        if so_digitos(fo.cnpj) == d:
            return False
    e = end_estrut or {}
    f = Fornecedor(razao_social=(nome or "").strip().upper() or "SEM NOME",
                   cnpj=cnpj_fmt, inscricao_estadual=(ie or "").strip(),
                   endereco=(endereco or "").strip(), aprovacao="pendente",
                   ativo=True, usa_email=False, is_fornecedor=True, is_empresa_interna=False,
                   cep=e.get("cep") or None, logradouro=e.get("logradouro") or None,
                   numero=e.get("numero") or None, bairro=e.get("bairro") or None,
                   complemento=e.get("complemento") or None, cidade=e.get("cidade") or None,
                   estado=(e.get("estado") or "").upper() or None)
    db.session.add(f)
    return True


def _garantir_transportadora_pendente(nome, cnpj_raw, endereco):
    """Idem, mas para a tabela de Transportadoras (item 145)."""
    if not cnpj_valido(cnpj_raw):
        return False
    cnpj_fmt = formatar_cnpj(cnpj_raw)
    d = so_digitos(cnpj_raw)
    existe = None
    for tr in Transportadora.query.filter(Transportadora.cnpj.isnot(None)).all():
        if so_digitos(tr.cnpj) == d:
            existe = tr
            break
    if existe:
        return False
    nome_final = (nome or "").strip().upper() or f"TRANSPORTADORA {cnpj_fmt}"
    # nome é único na tabela; se colidir, acrescenta o CNPJ
    if Transportadora.query.filter_by(nome=nome_final).first():
        nome_final = f"{nome_final} ({cnpj_fmt})"
    t = Transportadora(nome=nome_final, cnpj=cnpj_fmt,
                       endereco=(endereco or "").strip(), aprovacao="pendente", ativo=True)
    db.session.add(t)
    return True


def _nome_arquivo_carga(modo, dados):
    """Nome automático do arquivo (item 147):
    Envio <Destinatário> <NF se houver> <Data DD MM AAAA>
    Recebimento <Remetente> <NF se houver> <Data DD MM AAAA>. Só espaços, sem especiais."""
    if modo == "envio":
        prefixo, empresa = "Envio", dados.get("dest_nome", "")
    else:
        prefixo, empresa = "Recebimento", dados.get("rem_nome", "")
    partes = [prefixo, empresa]
    if dados.get("nota_fiscal"):
        partes.append(dados["nota_fiscal"])
    # data: aceita AAAA-MM-DD (input date) -> DD MM AAAA
    data_raw = dados.get("data", "")
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", data_raw or "")
    if m:
        partes.append(f"{m.group(3)} {m.group(2)} {m.group(1)}")
    elif data_raw:
        partes.append(re.sub(r"[^\d ]", " ", data_raw))
    nome = " ".join(str(p).strip() for p in partes if str(p).strip())
    nome = re.sub(r"[^\w \-]", "", nome, flags=re.UNICODE)  # remove especiais, mantém espaço e hífen
    nome = re.sub(r"\s+", " ", nome).strip()
    return (nome or "Relatorio de Carga") + ".pdf"


@relatorios_bp.route("/carga/gerar", methods=["POST"])
@relatorios_required
def carga_gerar():
    f = request.form
    status = f.get("status", "")
    if status not in ("Recebido", "Enviado"):
        flash("Escolha o Status (Recebimento ou Envio) antes de gerar o relatório.", "warning")
        return abort(400, "Status não selecionado.")
    modo = "recebimento" if status == "Recebido" else "envio"

    responsavel_id = f.get("responsavel_id")
    responsavel_nome = ""
    if responsavel_id:
        u = db.session.get(Usuario, int(responsavel_id))
        responsavel_nome = u.nome if u else ""

    # avarias marcadas + observações
    avarias_ids = set(f.getlist("foto_avariada"))
    obs_avarias = [v.strip() for v in f.getlist("obs_avaria") if v.strip()]

    def _endereco_estruturado(prefixo):
        """Monta o endereço em texto a partir dos campos separados do formulário (item 150)."""
        cep = f.get(f"{prefixo}_cep", "").strip()
        logr = f.get(f"{prefixo}_logradouro", "").strip()
        num = f.get(f"{prefixo}_numero", "").strip()
        bairro = f.get(f"{prefixo}_bairro", "").strip()
        compl = f.get(f"{prefixo}_complemento", "").strip()
        cidade = f.get(f"{prefixo}_cidade", "").strip()
        uf = f.get(f"{prefixo}_estado", "").strip().upper()
        partes = []
        if logr:
            partes.append(logr + (f", {num}" if num else ""))
        if bairro:
            partes.append(bairro)
        if compl:
            partes.append(compl)
        cid_uf = " - ".join(x for x in [cidade, uf] if x)
        if cid_uf:
            partes.append(cid_uf)
        if cep:
            partes.append(f"CEP {cep}")
        # se não preencheu nada estruturado, cai no campo antigo (compatibilidade)
        return ", ".join(partes) if partes else f.get(f"{prefixo}_endereco", "").strip()

    rem_endereco = _endereco_estruturado("rem")
    dest_endereco = _endereco_estruturado("dest")
    transp_endereco = _endereco_estruturado("transp")

    dados = {
        "data": f.get("data", ""),
        "responsavel": responsavel_nome,
        "rem_nome": f.get("rem_nome", ""), "rem_cnpj": formatar_cnpj(f.get("rem_cnpj", "")) or f.get("rem_cnpj", ""),
        "rem_ie": formatar_ie(f.get("rem_ie", "")), "rem_endereco": rem_endereco,
        "dest_nome": f.get("dest_nome", ""), "dest_cnpj": formatar_cnpj(f.get("dest_cnpj", "")) or f.get("dest_cnpj", ""),
        "dest_ie": formatar_ie(f.get("dest_ie", "")), "dest_endereco": dest_endereco,
        "transp_nome": f.get("transp_nome", ""), "transp_cnpj": formatar_cnpj(f.get("transp_cnpj", "")) or f.get("transp_cnpj", ""),
        "transp_endereco": transp_endereco,
        "nota_fiscal": f.get("nota_fiscal", ""), "serie": f.get("serie", ""), "oc": f.get("oc", ""),
        "qtd_volumes": f.get("qtd_volumes", ""),
        "tipo_volume": f.get("tipo_volume_outro", "").strip() if f.get("tipo_volume") == "__OUTRO__" else f.get("tipo_volume", ""),
        "valor_nf": f.get("valor_nf", ""),
        "natureza_operacao": f.get("natureza_outro", "").strip() if f.get("natureza_operacao") == "__OUTRO__" else f.get("natureza_operacao", ""),
        "cte": f.get("cte", ""), "valor_cte": f.get("valor_cte", ""),
        "tomador_cte": f.get("tomador_cte", ""),
        "descricao_carga": f.get("descricao_carga", ""),
        "observacoes": f.get("observacoes", "").strip() or "S/ observações",
        "status": status,
        "tem_avaria": bool(avarias_ids),
        "obs_avarias": obs_avarias,
    }

    # Cadastro pendente por CNPJ novo (item 145)
    # Cadastro pendente por CNPJ novo (item 145). Protegido: se falhar no banco,
    # faz rollback e segue gerando o PDF — o relatório é a prioridade, o cadastro
    # pendente é um bônus e nunca deve derrubar a geração do documento.
    try:
        criados = 0
        criados += 1 if _garantir_fornecedor_pendente(dados["rem_nome"], f.get("rem_cnpj", ""),
                                                       f.get("rem_ie", ""), dados["rem_endereco"],
                                                       {k: f.get("rem_" + k, "") for k in ["cep","logradouro","numero","bairro","complemento","cidade","estado"]}) else 0
        criados += 1 if _garantir_fornecedor_pendente(dados["dest_nome"], f.get("dest_cnpj", ""),
                                                       f.get("dest_ie", ""), dados["dest_endereco"],
                                                       {k: f.get("dest_" + k, "") for k in ["cep","logradouro","numero","bairro","complemento","cidade","estado"]}) else 0
        criados += 1 if _garantir_transportadora_pendente(dados["transp_nome"], f.get("transp_cnpj", ""),
                                                           dados["transp_endereco"]) else 0
        if criados:
            db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Falha ao criar cadastro pendente no relatório de carga (ignorado)")

    # Fotos enviadas (item 135) — salvas em arquivo TEMPORARIO no disco (streaming, uma por vez),
    # para NAO acumular 25-50 fotos na memoria (evita OOM no Render). Guardamos so o caminho.
    import tempfile as _tmp, shutil as _sh, os as _os
    fotos = []
    temp_uploads = []

    def _salvar_foto_temp(fs):
        try:
            fs.stream.seek(0)
        except Exception:
            pass
        tf = _tmp.NamedTemporaryFile(suffix=".img", delete=False)
        _sh.copyfileobj(fs.stream, tf, length=1024 * 256)
        tf.close()
        if _os.path.getsize(tf.name) <= 0:
            try:
                _os.unlink(tf.name)
            except Exception:
                pass
            return None
        temp_uploads.append(tf.name)
        return tf.name

    foto_nf = request.files.get("foto_nf")
    if foto_nf and foto_nf.filename:
        p = _salvar_foto_temp(foto_nf)
        if p:
            fotos.append({"path": p, "legenda": f"Nota Fiscal {dados.get('nota_fiscal','')}".strip(),
                          "avaria": False, "obs": ""})
    foto_cte = request.files.get("foto_cte")
    if foto_cte and foto_cte.filename:
        p = _salvar_foto_temp(foto_cte)
        if p:
            fotos.append({"path": p, "legenda": f"CT-e {dados.get('cte','')}".strip(),
                          "avaria": False, "obs": ""})

    idx = 0
    for arquivo in request.files.getlist("fotos"):
        if not arquivo or not arquivo.filename:
            continue
        idx += 1
        p = _salvar_foto_temp(arquivo)
        if not p:
            continue
        foto_id = f"foto_{idx}"
        avaria = foto_id in avarias_ids
        obs = ""
        if avaria:
            obs_lista = f.getlist(f"obs_{foto_id}")
            obs = obs_lista[0].strip() if obs_lista else ""
        fotos.append({"path": p, "legenda": arquivo.filename, "avaria": avaria, "obs": obs})

    try:
        pdf = gerar_pdf_relatorio_carga(modo, dados, fotos=fotos)
    except Exception:
        current_app.logger.exception("Falha ao gerar PDF do relatório de carga")
        flash("Não foi possível gerar o PDF (verifique as fotos anexadas e tente novamente). "
              "Se persistir, gere sem as fotos e anexe-as separadamente.", "danger")
        return redirect(url_for("relatorios.carga"))
    finally:
        for _p in temp_uploads:
            try:
                _os.unlink(_p)
            except Exception:
                pass

    nome = _nome_arquivo_carga(modo, dados)
    # ASCII-safe para o header (evita erro de encoding no header sob Gunicorn);
    # o nome com acentos vai no filename* (RFC 5987), tratado pelo Werkzeug.
    resp = Response(pdf, mimetype="application/pdf")
    try:
        resp.headers.set("Content-Disposition", "attachment", filename=nome)
    except Exception:
        resp.headers["Content-Disposition"] = 'attachment; filename="relatorio_carga.pdf"'
    return resp
