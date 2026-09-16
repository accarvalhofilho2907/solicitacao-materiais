import os
from io import BytesIO
from datetime import datetime

from flask import current_app
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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
             ["Link de similar", s.link_similar or "-"],
             ["Solicitante", (s.solicitante.nome if s.solicitante else (getattr(s, "solicitante_nome", None) or "-"))]]
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


def gerar_pdf_fichas(solicitacoes):
    """Uma ficha completa por solicitação (uma por página)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    el = []
    for idx, s in enumerate(solicitacoes):
        if idx:
            el.append(PageBreak())
        el.append(Paragraph(f"Ficha da Solicitação Nº {s.id}", _ST["Title"]))
        el.append(Paragraph(f"Status: {s.status_label}", _ST["Normal"]))
        el.append(Spacer(1, 6 * mm))
        linhas = [
            ["Material", s.material or "-"],
            ["Quantidade", str(s.quantidade) + (f" (original: {s.quantidade_original})" if s.quantidade_original else "")],
            ["Fabricante", s.fabricante or "-"],
            ["Tipo de material", s.tipo.nome if s.tipo else "-"],
            ["Local / frente de serviço", s.local_servico or "-"],
            ["Link de similar", s.link_similar or "-"],
            ["Solicitante", (s.solicitante.nome if s.solicitante else (getattr(s, "solicitante_nome", None) or "-"))],
            ["Criada em", s.criado_em.strftime("%d/%m/%Y %H:%M") if s.criado_em else "-"],
            ["Fornecedor definido", s.fornecedor_definido.nome if s.fornecedor_definido else "-"],
            ["Frete", (s.frete_tipo or "-")],
            ["Prazo de recebimento", s.prazo_recebimento.strftime("%d/%m/%Y") if s.prazo_recebimento else "-"],
        ]
        t = Table(linhas, colWidths=[55 * mm, 110 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("PADDING", (0, 0), (-1, -1), 5)]))
        el.append(t)
        if s.imagens:
            el.append(Spacer(1, 5 * mm))
            el.append(Paragraph("Fotos:", _ST["Heading4"]))
            el += _img_flowables(s, larg=60 * mm)
    doc.build(el)
    buf.seek(0)
    return buf.getvalue()


def gerar_pdf_notinhas(notas):
    # [118] Layout com a identidade Serena (coral/grafite/areia) e texto contido nas células
    CORAL = colors.HexColor("#FF5246")
    GRAFITE = colors.HexColor("#4B4B4B")
    AREIA = colors.HexColor("#EDE9E5")
    BRANCO = colors.white

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)
    titulo_style = ParagraphStyle("NotinhasTitulo", parent=_ST["Title"], textColor=GRAFITE, fontSize=18)
    sub_style = ParagraphStyle("NotinhasSub", parent=_ST["Normal"], textColor=colors.HexColor("#6f6f6f"), fontSize=9)
    cel_style = ParagraphStyle("NotinhasCel", parent=_ST["Normal"], fontSize=8, textColor=GRAFITE, leading=10)

    el = [Paragraph("Notinhas", titulo_style),
          Paragraph(f"Exportado em {datetime.now():%d/%m/%Y %H:%M}", sub_style), Spacer(1, 6 * mm)]

    linhas = [["Data", "Competência", "Fornecedor", "Atividade", "Valor (R$)"]]
    total = 0.0
    for n in notas:
        total += float(n.valor)
        linhas.append([n.data.strftime("%d/%m/%Y"), n.competencia or "-",
                       Paragraph(n.fornecedor.nome, cel_style),
                       Paragraph(n.atividade.nome if n.atividade else "-", cel_style),
                       f"{float(n.valor):.2f}"])
    linhas.append(["", "", "", "Total", f"{total:.2f}"])

    t = Table(linhas, colWidths=[22 * mm, 24 * mm, 62 * mm, 40 * mm, 24 * mm], repeatRows=1)
    ultima = len(linhas) - 1
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, AREIA),
        ("BACKGROUND", (0, 0), (-1, 0), CORAL), ("TEXTCOLOR", (0, 0), (-1, 0), BRANCO),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, ultima - 1), [BRANCO, AREIA]),
        ("BACKGROUND", (0, ultima), (-1, ultima), GRAFITE), ("TEXTCOLOR", (0, ultima), (-1, ultima), BRANCO),
        ("FONTNAME", (0, ultima), (-1, ultima), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 8), ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("PADDING", (0, 0), (-1, -1), 5)]))
    el.append(t)
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
