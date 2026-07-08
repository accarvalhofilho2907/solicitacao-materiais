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

from flask import Blueprint, render_template, request, abort, send_file
from flask_login import login_required, current_user

from .models import Fornecedor, Usuario
from .admin import SPES_COTACAO
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
    fornecedores = Fornecedor.query.filter_by(ativo=True).order_by(Fornecedor.razao_social).all()
    return render_template("relatorios/etiquetas.html", deltas=SPES_COTACAO,
                           fornecedores=fornecedores, remetente_fixo=REMETENTE_FIXO,
                           selos=SELOS_CARGA)


def _gerar_pdf_envio_a_partir_do_form(f):
    delta_nome = f.get("delta_nome", "")
    if delta_nome == "OUTRO":
        remetente = {
            "nome": f.get("outro_nome", "").strip() or "Remetente não informado",
            "endereco": f.get("outro_endereco", "").strip(),
            "cnpj": f.get("outro_cnpj", "").strip(),
            "contato": REMETENTE_FIXO["nome"], "telefone": REMETENTE_FIXO["telefone"],
            "email": REMETENTE_FIXO["email"],
        }
    else:
        delta = next((d for d in SPES_COTACAO if d[0] == delta_nome), None)
        if not delta:
            abort(400, "Delta (remetente) inválida.")
        remetente = {
            "nome": delta[0], "endereco": delta[1], "cnpj": delta[2],
            "contato": REMETENTE_FIXO["nome"], "telefone": REMETENTE_FIXO["telefone"],
            "email": REMETENTE_FIXO["email"],
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
    if por_folha not in (2, 4, 6, 8):
        por_folha = 4
    nota_fiscal = f.get("nota_fiscal", "").strip() or None
    selos = f.getlist("selos")

    return gerar_pdf_etiquetas_envio(remetente, destinatario, volumes, por_folha,
                                     nota_fiscal=nota_fiscal, selos=selos)


@relatorios_bp.route("/etiquetas/envio/gerar", methods=["POST"])
@relatorios_required
def etiquetas_envio_gerar():
    pdf = _gerar_pdf_envio_a_partir_do_form(request.form)
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="etiquetas_caixas_embalagens.pdf")


@relatorios_bp.route("/etiquetas/envio/gerar-para-email", methods=["POST"])
@relatorios_required
def etiquetas_envio_gerar_email():
    """Gera o mesmo PDF, mas com nome de arquivo e resposta pensados para o
    usuário baixar e anexar manualmente ao e-mail (item 133). Navegadores não
    permitem anexar arquivo automaticamente via link mailto, então a melhor
    abordagem possível é: baixar o PDF pronto + abrir o e-mail padrão já com
    assunto/corpo preenchidos, pedindo para anexar o arquivo baixado."""
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
    if por_folha not in (2, 4, 6, 8):
        por_folha = 4

    pdf = gerar_pdf_etiquetas_identificacao(texto, quantidade, por_folha)
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="etiquetas_identificacao_item.pdf")


@relatorios_bp.route("/carga", methods=["GET"])
@relatorios_required
def carga():
    """Tela única de Relatório de Carga (item 128) — o campo Status decide se é
    Recebimento ou Envio, em vez de serem duas rotas/telas separadas."""
    usuarios = Usuario.query.filter_by(ativo=True).order_by(Usuario.nome).all()
    return render_template("relatorios/carga.html", hoje=date.today().strftime("%Y-%m-%d"),
                           usuario_atual_id=current_user.id, usuarios=usuarios)


@relatorios_bp.route("/carga/gerar", methods=["POST"])
@relatorios_required
def carga_gerar():
    f = request.form
    status = f.get("status", "Recebido")
    modo = "recebimento" if status == "Recebido" else "envio"
    responsavel_id = f.get("responsavel_id")
    responsavel_nome = ""
    if responsavel_id:
        u = Usuario.query.get(int(responsavel_id))
        responsavel_nome = u.nome if u else ""
    avarias = f.getlist("foto_avariada")   # marcações "Avariado?" das fotos anexadas (item 128)
    obs_avarias = [v.strip() for v in f.getlist("obs_avaria") if v.strip()]
    dados = {
        "data": f.get("data", ""),
        "responsavel": responsavel_nome,
        "razao_social": f.get("razao_social", ""),
        "cnpj": f.get("cnpj", ""),
        "ie": f.get("ie", ""),
        "endereco": f.get("endereco", ""),
        "nota_fiscal": f.get("nota_fiscal", ""),
        "serie": f.get("serie", ""),
        "oc": f.get("oc", ""),
        "valor_nf": f.get("valor_nf", ""),
        "natureza_operacao": f.get("natureza_operacao", ""),
        "cte": f.get("cte", ""),
        "valor_cte": f.get("valor_cte", ""),
        "observacoes": f.get("observacoes", "").strip() or "S/ observações",
        "status": status,
        "tem_avaria": bool(avarias),
        "obs_avarias": obs_avarias,
    }
    pdf = gerar_pdf_relatorio_carga(modo, dados)
    nome_arquivo = f"relatorio_{modo}_materiais.pdf"
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name=nome_arquivo)
