"""PDF do Relatório de Recebimento / Envio de Materiais (item 111).

Modelo inspirado na foto enviada pelo usuário em 08/07/2026
("Relatório de Carga Almoxarifado Delta MA"): cabeçalho com faixa colorida,
selo de status, dados do fornecedor/destinatário e bloco "Dados da Carga".

Não é salvo no banco — só gera o PDF na hora (decisão do usuário, 08/07/2026).
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

_ST = getSampleStyleSheet()

FAIXA_COR = colors.HexColor("#6E7FE0")   # tom próximo ao do modelo em foto
STATUS_RECEBIDO = colors.HexColor("#32CAA0")
STATUS_ENVIADO = colors.HexColor("#FF5246")
CINZA_CLARO = colors.HexColor("#EDE9E5")
GRAFITE = colors.HexColor("#4B4B4B")

_TITULO = ParagraphStyle("titulo_relatorio", parent=_ST["Title"], textColor=colors.white, fontSize=16)
_SECAO = ParagraphStyle("secao", parent=_ST["Normal"], alignment=1, fontName="Helvetica-Bold", fontSize=10)


def gerar_pdf_relatorio_carga(modo, dados):
    """modo: 'recebimento' ou 'envio'. dados: dict vindo do formulário."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0, bottomMargin=18 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)
    el = []

    titulo_txt = "RELATÓRIO DE CARGA — ALMOXARIFADO DELTA MA"
    status_txt = dados.get("status", "Recebido" if modo == "recebimento" else "Enviado")
    status_cor = STATUS_RECEBIDO if modo == "recebimento" else STATUS_ENVIADO

    cabecalho = Table(
        [[Paragraph(titulo_txt, _TITULO), Paragraph(f'<font color="white"><b>{status_txt}</b></font>', _ST["Normal"])]],
        colWidths=[130 * mm, 40 * mm]
    )
    cabecalho.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), FAIXA_COR),
        ("BACKGROUND", (1, 0), (1, -1), status_cor),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (0, -1), 14),
    ]))
    el.append(cabecalho)
    el.append(Spacer(1, 8 * mm))

    linhas = [
        ["Data", dados.get("data") or "-", "Responsável", dados.get("responsavel") or "-"],
        ["Razão Social", dados.get("razao_social") or "-", "", ""],
        ["CNPJ", dados.get("cnpj") or "-", "Inscrição Estadual", dados.get("ie") or "-"],
        ["Endereço", dados.get("endereco") or "-", "", ""],
    ]
    t1 = Table(linhas, colWidths=[28 * mm, 62 * mm, 32 * mm, 46 * mm])
    t1.setStyle(TableStyle([
        ("SPAN", (1, 1), (3, 1)), ("SPAN", (1, 3), (3, 3)),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#DDDDDD")),
    ]))
    el.append(t1)
    el.append(Spacer(1, 4 * mm))

    sec_carga = Table([[Paragraph("DADOS DA CARGA", _SECAO)]], colWidths=[168 * mm])
    sec_carga.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CINZA_CLARO),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el.append(sec_carga)
    el.append(Spacer(1, 2 * mm))

    linhas2 = [
        ["Nota Fiscal", dados.get("nota_fiscal") or "-", "Série", dados.get("serie") or "-",
         "OC (se informado)", "  " + (dados.get("oc") or "-")],
        ["Valor da NF", f"R$ {dados.get('valor_nf') or '-'}", "Natureza da operação", "  " + (dados.get("natureza_operacao") or "-"), "", ""],
        ["CT-e", dados.get("cte") or "-", "Valor CT-e", f"R$ {dados.get('valor_cte') or '-'}", "", ""],
    ]
    t2 = Table(linhas2, colWidths=[24 * mm, 30 * mm, 32 * mm, 32 * mm, 28 * mm, 22 * mm])
    t2.setStyle(TableStyle([
        ("SPAN", (3, 1), (5, 1)), ("SPAN", (3, 2), (5, 2)),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#DDDDDD")),
    ]))
    el.append(t2)
    el.append(Spacer(1, 4 * mm))

    sec_obs = Table([[Paragraph("OBSERVAÇÕES", _SECAO)]], colWidths=[168 * mm])
    sec_obs.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CINZA_CLARO),
                                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el.append(sec_obs)
    el.append(Spacer(1, 2 * mm))
    el.append(Paragraph(dados.get("observacoes") or "S/ observações", _ST["Normal"]))

    doc.build(el)
    buf.seek(0)
    return buf.getvalue()
