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
            ["Solicitante", s.solicitante.nome],
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
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    el = [Paragraph("Notinhas", _ST["Title"]),
          Paragraph(f"Exportado em {datetime.now():%d/%m/%Y %H:%M}", _ST["Normal"]), Spacer(1, 6 * mm)]
    linhas = [["Data", "Competência", "Fornecedor", "Atividade", "Valor (R$)"]]
    total = 0.0
    for n in notas:
        total += float(n.valor)
        linhas.append([n.data.strftime("%d/%m/%Y"), n.competencia or "-", n.fornecedor.nome,
                       n.atividade.nome if n.atividade else "-", f"{float(n.valor):.2f}"])
    linhas.append(["", "", "", "Total", f"{total:.2f}"])
    t = Table(linhas, colWidths=[24 * mm, 26 * mm, 55 * mm, 38 * mm, 27 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"), ("PADDING", (0, 0), (-1, -1), 4)]))
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
