import os
from io import BytesIO
from datetime import datetime

from flask import current_app
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)
from reportlab.lib.styles import getSampleStyleSheet

_ST = getSampleStyleSheet()


def _img_flowables(solicitacao, larg=70 * mm):
    """Tenta embutir as imagens locais; sempre lista as URLs."""
    out = []
    pasta = current_app.config.get("UPLOAD_FOLDER", "")
    for img in solicitacao.imagens:
        url = img.url or ""
        if url.startswith("/uploads/"):
            caminho = os.path.join(pasta, os.path.basename(url))
            if os.path.exists(caminho):
                try:
                    im = Image(caminho)
                    ratio = im.imageHeight / float(im.imageWidth or 1)
                    im.drawWidth = larg
                    im.drawHeight = larg * ratio
                    out.append(im)
                    out.append(Spacer(1, 3 * mm))
                    continue
                except Exception:
                    pass
        out.append(Paragraph(f"Imagem: {url}", _ST["Normal"]))
    return out


def gerar_pdf_pedido(s):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    el = [Paragraph("Pedido de Compra", _ST["Title"]),
          Paragraph(f"Solicitação Nº {s.id} — {datetime.now():%d/%m/%Y %H:%M}", _ST["Normal"]),
          Spacer(1, 8 * mm)]
    dados = [["Material", s.material or "-"], ["Quantidade", str(s.quantidade)],
             ["Fabricante", s.fabricante or "-"], ["Tipo", s.tipo.nome if s.tipo else "-"],
             ["Local / frente de serviço", s.local_servico or "-"],
             ["Link de similar", s.link_similar or "-"], ["Solicitante", s.solicitante.nome]]
    t = Table(dados, colWidths=[50 * mm, 115 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 6)]))
    el.append(t)
    if s.imagens:
        el.append(Spacer(1, 6 * mm))
        el.append(Paragraph("Fotos do item:", _ST["Heading4"]))
        el += _img_flowables(s)
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph("Por favor, responder com valor, prazo e condições de pagamento.", _ST["Italic"]))
    doc.build(el)
    buf.seek(0)
    return buf.getvalue()


def gerar_pdf_pedido_lote(fornecedor_nome, solicitacoes):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    el = [Paragraph("Pedido de Compra", _ST["Title"]),
          Paragraph(f"Fornecedor: {fornecedor_nome} — {datetime.now():%d/%m/%Y %H:%M}", _ST["Normal"]),
          Spacer(1, 6 * mm)]
    linhas = [["Nº", "Material", "Qtd", "Fabricante", "Link"]]
    for s in solicitacoes:
        linhas.append([str(s.id), s.material or "-", str(s.quantidade), s.fabricante or "-", s.link_similar or "-"])
    t = Table(linhas, colWidths=[12 * mm, 70 * mm, 14 * mm, 32 * mm, 42 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 4)]))
    el.append(t)
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph("Por favor, responder com valor, prazo e condições de pagamento de cada item.", _ST["Italic"]))
    doc.build(el)
    buf.seek(0)
    return buf.getvalue()


def gerar_pdf_lista(solicitacoes):
    """Exportação de várias solicitações para o usuário guardar."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    el = [Paragraph("Minhas Solicitações", _ST["Title"]),
          Paragraph(f"Exportado em {datetime.now():%d/%m/%Y %H:%M}", _ST["Normal"]), Spacer(1, 6 * mm)]
    linhas = [["Nº", "Material", "Qtd", "Status", "Local"]]
    for s in solicitacoes:
        linhas.append([str(s.id), s.material or "-", str(s.quantidade), s.status_label, s.local_servico or "-"])
    t = Table(linhas, colWidths=[12 * mm, 72 * mm, 14 * mm, 45 * mm, 35 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("PADDING", (0, 0), (-1, -1), 5)]))
    el.append(t)
    doc.build(el)
    buf.seek(0)
    return buf.getvalue()
