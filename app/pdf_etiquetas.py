"""PDF de etiquetas em folha A4 (item 109).

Duas etiquetas:
- Envio de Material: remetente (Delta) + destinatário (fornecedor) + volume X/Y.
- Identificação de Item: texto livre, com moldura e faixa nas cores da Serena
  (não tem logo de imagem embutida — usa o símbolo textual "SERENA" estilizado,
  já que não há arquivo de logo disponível neste ambiente de geração).

Layout: grid fixo de 1, 2 ou 4 colunas conforme a quantidade por folha (2/4/6/8),
usando toda a folha A4 com margem de segurança para impressão doméstica.
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
    2: (1, 2),   # 1 coluna x 2 linhas
    4: (2, 2),
    6: (2, 3),
    8: (2, 4),
}

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


def _desenhar_envio(c, x, y, larg, alt, remetente, destinatario, vol_atual, vol_total):
    pad = 5 * mm
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.setDash(2, 2)
    c.rect(x, y, larg, alt)
    c.setDash()

    # tag de volume
    tag_w, tag_h = 24 * mm, 7 * mm
    c.setFillColor(GRAFITE)
    c.roundRect(x + larg - tag_w - pad, y + alt - tag_h - pad, tag_w, tag_h, 1.5 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x + larg - tag_w / 2 - pad, y + alt - tag_h - pad + 2.4, f"VOL {vol_atual}/{vol_total}")

    largura_txt = larg - 2 * pad

    # pré-calcula altura total do conteúdo para centralizar verticalmente
    def altura_bloco(linhas_txt):
        h = 3.8 * mm  # título
        for txt, font, size in linhas_txt:
            n_linhas = max(1, len(_wrap_text(c, txt, font, size, largura_txt))) if txt else 1
            h += n_linhas * (size + 2.4)
        return h

    linhas_rem = [
        (remetente["nome"], "Helvetica-Bold", 10),
        (remetente.get("endereco", ""), "Helvetica", 7.5),
        (f"CNPJ {remetente.get('cnpj', '')}", "Helvetica", 7.5),
    ]
    contato_dest = " · ".join(filter(None, [destinatario.get("contato", ""), destinatario.get("telefone", "")]))
    linhas_dest = [
        (destinatario["nome"], "Helvetica-Bold", 10),
        (destinatario.get("endereco", ""), "Helvetica", 7.5),
        (f"CNPJ {destinatario.get('cnpj', '')}" if destinatario.get("cnpj") else "", "Helvetica", 7.5),
        (contato_dest, "Helvetica", 7.5),
    ]

    total_h = altura_bloco(linhas_rem) + 6 * mm + altura_bloco(linhas_dest)
    cursor_y = y + alt / 2 + total_h / 2 - 4

    def bloco(titulo, linhas_txt):
        nonlocal cursor_y
        c.setFillColor(CORAL)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(x + pad, cursor_y, titulo.upper())
        cursor_y -= 4 * mm
        c.setFillColor(GRAFITE)
        for txt, font, size in linhas_txt:
            if not txt:
                continue
            for linha in _wrap_text(c, txt, font, size, largura_txt):
                c.setFont(font, size)
                c.drawString(x + pad, cursor_y, linha)
                cursor_y -= (size + 2.4)

    bloco("Remetente", linhas_rem)
    cursor_y -= 3 * mm
    c.setStrokeColor(colors.HexColor("#DDDDDD"))
    c.line(x + pad, cursor_y, x + larg - pad, cursor_y)
    cursor_y -= 5 * mm

    bloco("Destinatário", linhas_dest)


def gerar_pdf_etiquetas_envio(remetente, destinatario, volumes, por_folha):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    posicoes = _slots(por_folha)
    total_paginas = -(-volumes // por_folha)  # ceil

    vol = 1
    for pagina in range(total_paginas):
        for (x, y, larg, alt) in posicoes:
            if vol > volumes:
                break
            _desenhar_envio(c, x, y, larg, alt, remetente, destinatario, vol, volumes)
            vol += 1
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


def _desenhar_identificacao(c, x, y, larg, alt, texto):
    pad = 4 * mm
    # moldura dupla nas cores da Serena
    c.setStrokeColor(CORAL)
    c.setLineWidth(1.4)
    c.rect(x + 1.5 * mm, y + 1.5 * mm, larg - 3 * mm, alt - 3 * mm)
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.6)
    c.rect(x + 2.6 * mm, y + 2.6 * mm, larg - 5.2 * mm, alt - 5.2 * mm)

    # faixa superior com "logo" textual (sem arquivo de imagem disponível)
    faixa_h = 6 * mm
    c.setFillColor(CORAL)
    c.rect(x + 2.6 * mm, y + alt - 2.6 * mm - faixa_h, larg - 5.2 * mm, faixa_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x + larg / 2, y + alt - 2.6 * mm - faixa_h + 2, "SERENA ENERGIA")

    # texto livre centralizado
    largura_txt = larg - 2 * pad
    c.setFillColor(GRAFITE)
    linhas = _wrap_text(c, texto, "Helvetica-Bold", 11, largura_txt)
    altura_bloco = len(linhas) * 13
    cursor_y = y + alt / 2 + altura_bloco / 2 - 10
    for linha in linhas:
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(x + larg / 2, cursor_y, linha)
        cursor_y -= 13


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
            _desenhar_identificacao(c, x, y, larg, alt, texto)
            n += 1
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()
