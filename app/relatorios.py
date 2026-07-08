"""Relatórios e Impressões — Geração de Etiquetas (item 109) e
Relatório de Recebimento/Envio de Materiais (item 111).

Regras confirmadas com o usuário (08/07/2026):
- Etiquetas: tipos "Envio de Material" e "Identificação de Item" (campo livre + logo/moldura Serena).
  Tipo "Devolução" foi descartado.
- Relatório de Recebimento e Relatório de Envio são DUAS telas distintas.
- Por enquanto nenhum dos dois relatórios de carga é salvo no banco — só gera o PDF na hora.
"""
from functools import wraps
from datetime import date

from flask import Blueprint, render_template, request, abort, send_file
from flask_login import login_required, current_user

from .models import Fornecedor
from .admin import SPES_COTACAO
from .pdf_etiquetas import gerar_pdf_etiquetas_envio, gerar_pdf_etiquetas_identificacao
from .pdf_carga import gerar_pdf_relatorio_carga

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")

REMETENTE_FIXO = {
    "nome": "Antonio Carlos Carvalho",
    "telefone": "(86) 99939-9872",
    "email": "antonio.carvalho@srna.co",
}


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
                           fornecedores=fornecedores, remetente_fixo=REMETENTE_FIXO)


@relatorios_bp.route("/etiquetas/envio/gerar", methods=["POST"])
@relatorios_required
def etiquetas_envio_gerar():
    f = request.form
    delta_nome = f.get("delta_nome", "")
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

    pdf = gerar_pdf_etiquetas_envio(remetente, destinatario, volumes, por_folha)
    from io import BytesIO
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="etiquetas_envio_material.pdf")


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
    from io import BytesIO
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name="etiquetas_identificacao_item.pdf")


@relatorios_bp.route("/carga/<modo>", methods=["GET"])
@relatorios_required
def carga(modo):
    if modo not in ("recebimento", "envio"):
        abort(404)
    return render_template("relatorios/carga.html", modo=modo, hoje=date.today().strftime("%Y-%m-%d"),
                           nome_usuario=current_user.nome)


@relatorios_bp.route("/carga/<modo>/gerar", methods=["POST"])
@relatorios_required
def carga_gerar(modo):
    if modo not in ("recebimento", "envio"):
        abort(404)
    f = request.form
    dados = {
        "data": f.get("data", ""),
        "responsavel": f.get("responsavel", ""),
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
        "status": "Recebido" if modo == "recebimento" else "Enviado",
    }
    pdf = gerar_pdf_relatorio_carga(modo, dados)
    from io import BytesIO
    nome_arquivo = f"relatorio_{modo}_materiais.pdf"
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name=nome_arquivo)
