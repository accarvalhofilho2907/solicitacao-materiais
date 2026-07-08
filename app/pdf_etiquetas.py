"""PDF de etiquetas em folha A4 (item 109, revisado 08/07/2026 — itens 126, 127, 133).

Duas etiquetas:
- "Etiqueta de caixas/embalagens" (era "Envio de Material" — renomeado no item 133):
  remetente (Delta ou "Outro") + destinatário (fornecedor) + volume X/Y + Nota Fiscal
  opcional + selos de manuseio (Frágil / Explosivo / Pode empilhar).
- Identificação de Item: texto livre, com moldura e faixa nas cores da Serena.

Fonte proporcional ao tamanho do slot (item 126) — quanto menos etiquetas por
folha, maior a fonte, sempre pensada para ser lida numa caixa física.
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas

CORAL = colors.HexColor("#FF5246")
GRAFITE = colors.HexColor("#4B4B4B")
VERDE = colors.HexColor("#32CAA0")

_GRID = {
    2: (1, 2),
    4: (2, 2),
    6: (2, 3),
    8: (2, 4),
}

# Escala de fonte por layout (item 126) — quanto menos etiquetas por folha, maior a fonte.
_ESCALA_FONTE = {2: 1.55, 4: 1.25, 6: 1.0, 8: 0.85}

MARGEM = 10 * mm
GUTTER = 4 * mm


def _slots(por_folha):
    cols, rows = _GRID[por_folha]
    largura_util = A4[0] - 2 * MARGEM - (cols - 1) * GUTTER
    altura_util = A4[1] - 2 * MARGEM - (rows - 1) * GUTTER
    larg = largura_util / cols
    alt = altura_util / rows
    posicoes = []
    for r in range(rows):
        for c in range(cols):
            x = MARGEM + c * (larg + GUTTER)
            y = A4[1] - MARGEM - (r + 1) * alt - r * GUTTER
            posicoes.append((x, y, larg, alt))
    return posicoes


def _wrap_text(c, texto, font, size, max_width):
    c.setFont(font, size)
    palavras = texto.split()
    linhas, atual = [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if c.stringWidth(teste, font, size) <= max_width:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def _desenhar_envio(c, x, y, larg, alt, remetente, destinatario, vol_atual, vol_total,
                    por_folha, nota_fiscal=None, selos=None):
    escala = _ESCALA_FONTE.get(por_folha, 1.0)
    pad = 5 * mm
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.setDash(2, 2)
    c.rect(x, y, larg, alt)
    c.setDash()

    # tag de volume
    f_tag = 9 * escala
    tag_w, tag_h = 24 * mm * min(escala, 1.3), 7 * mm * min(escala, 1.3)
    c.setFillColor(GRAFITE)
    c.roundRect(x + larg - tag_w - pad, y + alt - tag_h - pad, tag_w, tag_h, 1.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", f_tag)
    c.drawCentredString(x + larg - tag_w / 2 - pad, y + alt - tag_h - pad + tag_h * 0.3, f"VOL {vol_atual}/{vol_total}")

    largura_txt = larg - 2 * pad
    f_titulo = 8.5 * escala
    f_nome = 12 * escala
    f_corpo = 9 * escala

    def altura_bloco(linhas_txt):
        h = (f_titulo + 2) 
        for txt, font, size in linhas_txt:
            n_linhas = max(1, len(_wrap_text(c, txt, font, size, largura_txt))) if txt else 1
            h += n_linhas * (size + 3)
        return h

    linhas_rem = [
        (remetente["nome"], "Helvetica-Bold", f_nome),
        (remetente.get("endereco", ""), "Helvetica", f_corpo),
        (f"CNPJ {remetente.get('cnpj', '')}" if remetente.get("cnpj") else "", "Helvetica", f_corpo),
    ]
    contato_dest = " · ".join(filter(None, [destinatario.get("contato", ""), destinatario.get("telefone", "")]))
    linhas_dest = [
        (destinatario["nome"], "Helvetica-Bold", f_nome),
        (destinatario.get("endereco", ""), "Helvetica", f_corpo),
        (f"CNPJ {destinatario.get('cnpj', '')}" if destinatario.get("cnpj") else "", "Helvetica", f_corpo),
        (contato_dest, "Helvetica", f_corpo),
    ]
    extra_linhas = []
    if nota_fiscal:
        extra_linhas.append((f"NF: {nota_fiscal}", "Helvetica-Bold", f_corpo))

    total_h = altura_bloco(linhas_rem) + 6 * mm + altura_bloco(linhas_dest) + (altura_bloco(extra_linhas) if extra_linhas else 0)
    selos_ativos = [s for s in (selos or []) if s]
    selo_h = (10 * escala + 6) if selos_ativos else 0
    total_h += selo_h
    cursor_y = y + alt / 2 + total_h / 2 - 4

    def bloco(titulo, linhas_txt):
        nonlocal cursor_y
        c.setFillColor(CORAL)
        c.setFont("Helvetica-Bold", f_titulo)
        c.drawString(x + pad, cursor_y, titulo.upper())
        cursor_y -= (f_titulo + 3)
        c.setFillColor(GRAFITE)
        for txt, font, size in linhas_txt:
            if not txt:
                continue
            for linha in _wrap_text(c, txt, font, size, largura_txt):
                c.setFont(font, size)
                c.drawString(x + pad, cursor_y, linha)
                cursor_y -= (size + 3)

    bloco("Remetente", linhas_rem)
    cursor_y -= 3 * mm
    c.setStrokeColor(colors.HexColor("#DDDDDD"))
    c.line(x + pad, cursor_y, x + larg - pad, cursor_y)
    cursor_y -= 5 * mm

    bloco("Destinatário", linhas_dest)

    if nota_fiscal:
        cursor_y -= 2 * mm
        c.setFillColor(GRAFITE)
        c.setFont("Helvetica-Bold", f_corpo)
        c.drawString(x + pad, cursor_y, f"NF: {nota_fiscal}")
        cursor_y -= (f_corpo + 3)

    if selos_ativos:
        cursor_y -= 2 * mm
        selo_x = x + pad
        f_selo = 8 * escala
        icone = {"FRAGIL": "⚠ FRÁGIL", "EXPLOSIVO": "☢ EXPLOSIVO", "EMPILHAR": "▲ PODE EMPILHAR",
                "NAO_EMPILHAR": "✕ NÃO EMPILHAR"}
        for s in selos_ativos:
            txt = icone.get(s, s)
            w = c.stringWidth(txt, "Helvetica-Bold", f_selo) + 6
            c.setFillColor(colors.HexColor("#FFF1EF"))
            c.roundRect(selo_x, cursor_y - 2, w, f_selo + 5, 1.5, fill=1, stroke=0)
            c.setFillColor(CORAL)
            c.setFont("Helvetica-Bold", f_selo)
            c.drawString(selo_x + 3, cursor_y + 1, txt)
            selo_x += w + 4


def gerar_pdf_etiquetas_envio(remetente, destinatario, volumes, por_folha, nota_fiscal=None, selos=None):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    posicoes = _slots(por_folha)
    total_paginas = -(-volumes // por_folha)

    vol = 1
    for pagina in range(total_paginas):
        for (x, y, larg, alt) in posicoes:
            if vol > volumes:
                break
            _desenhar_envio(c, x, y, larg, alt, remetente, destinatario, vol, volumes,
                           por_folha, nota_fiscal=nota_fiscal, selos=selos)
            vol += 1
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


def _desenhar_identificacao(c, x, y, larg, alt, texto, por_folha):
    escala = _ESCALA_FONTE.get(por_folha, 1.0)
    pad = 4 * mm
    c.setStrokeColor(CORAL)
    c.setLineWidth(1.4)
    c.rect(x + 1.5 * mm, y + 1.5 * mm, larg - 3 * mm, alt - 3 * mm)
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.6)
    c.rect(x + 2.6 * mm, y + 2.6 * mm, larg - 5.2 * mm, alt - 5.2 * mm)

    faixa_h = 7 * mm * min(escala, 1.3)
    c.setFillColor(CORAL)
    c.rect(x + 2.6 * mm, y + alt - 2.6 * mm - faixa_h, larg - 5.2 * mm, faixa_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9 * escala)
    c.drawCentredString(x + larg / 2, y + alt - 2.6 * mm - faixa_h + faixa_h * 0.3, "SERENA ENERGIA")

    largura_txt = larg - 2 * pad
    f_texto = 14 * escala
    c.setFillColor(GRAFITE)
    linhas = _wrap_text(c, texto, "Helvetica-Bold", f_texto, largura_txt)
    altura_bloco = len(linhas) * (f_texto + 4)
    cursor_y = y + alt / 2 + altura_bloco / 2 - f_texto * 0.7
    for linha in linhas:
        c.setFont("Helvetica-Bold", f_texto)
        c.drawCentredString(x + larg / 2, cursor_y, linha)
        cursor_y -= (f_texto + 4)


def gerar_pdf_etiquetas_identificacao(texto, quantidade, por_folha):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    posicoes = _slots(por_folha)
    total_paginas = -(-quantidade // por_folha)

    n = 1
    for pagina in range(total_paginas):
        for (x, y, larg, alt) in posicoes:
            if n > quantidade:
                break
            _desenhar_identificacao(c, x, y, larg, alt, texto, por_folha)
            n += 1
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()
