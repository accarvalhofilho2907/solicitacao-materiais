"""PDF de etiquetas em folha A4 (item 109, revisado — itens 126/133/137/138/139/144).

Duas etiquetas:
- "Etiqueta de caixas/embalagens": remetente (Delta ou "Outro", com contato editável)
  + destinatário + volume X/Y + Nota Fiscal opcional + selos de manuseio com símbolo.
- "Identificação de Item": texto livre, com moldura e faixa nas cores da Serena.

Recursos:
- Grids de 1/2/4/6/8/10/12/14/16 etiquetas por folha (item 144).
- Orientação Retrato (A4 em pé) ou Paisagem (A4 deitado) (item 144).
- Dados centralizados na etiqueta (item 138).
- Fonte adaptativa: usa o maior tamanho que couber e diminui conforme o texto cresce,
  mantendo quebra de linha (item 139).
- Selos com símbolo desenhado (taça p/ Frágil, chama p/ Explosivo, setas p/ empilhar) (item 137).
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas

CORAL = colors.HexColor("#FF5246")
GRAFITE = colors.HexColor("#4B4B4B")
VERDE = colors.HexColor("#32CAA0")

# Grid (colunas, linhas) por quantidade de etiquetas por folha (item 144).
# Regra confirmada: 2 = uma em cima da outra; 4 = 2x2; e assim por diante.
_GRID = {
    1: (1, 1),
    2: (1, 2),
    4: (2, 2),
    6: (2, 3),
    8: (2, 4),
    10: (2, 5),
    12: (3, 4),
    14: (2, 7),
    16: (4, 4),
}

MARGEM = 10 * mm
GUTTER = 4 * mm


def _pagesize(orientacao):
    return landscape(A4) if orientacao == "paisagem" else A4


def _slots(por_folha, orientacao):
    cols, rows = _GRID[por_folha]
    pw, ph = _pagesize(orientacao)
    largura_util = pw - 2 * MARGEM - (cols - 1) * GUTTER
    altura_util = ph - 2 * MARGEM - (rows - 1) * GUTTER
    larg = largura_util / cols
    alt = altura_util / rows
    posicoes = []
    for r in range(rows):
        for c in range(cols):
            x = MARGEM + c * (larg + GUTTER)
            y = ph - MARGEM - (r + 1) * alt - r * GUTTER
            posicoes.append((x, y, larg, alt))
    return posicoes


def _wrap(c, texto, font, size, max_width):
    """Quebra o texto em linhas que cabem em max_width, dado font/size."""
    palavras = (texto or "").split()
    linhas, atual = [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if c.stringWidth(teste, font, size) <= max_width or not atual:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas or [""]


def _fit_bloco(c, linhas_spec, max_width, max_height, base_scale=1.0):
    """Fonte adaptativa (item 139): encontra o maior tamanho de fonte em que TODAS
    as linhas (com quebra) cabem na largura e a altura total cabe em max_height.

    linhas_spec: lista de (texto, font, tamanho_relativo) — o tamanho relativo é
    multiplicado pela escala calculada. Devolve (escala, altura_total_usada).
    """
    escala = 3.2 * base_scale
    while escala > 0.35:
        total_h = 0
        ok = True
        for texto, font, rel in linhas_spec:
            size = rel * escala
            linhas = _wrap(c, texto, font, size, max_width)
            # se alguma palavra sozinha estourar a largura, reduz
            for ln in linhas:
                if c.stringWidth(ln, font, size) > max_width:
                    ok = False
                    break
            if not ok:
                break
            total_h += len(linhas) * (size + 2.2)
        if ok and total_h <= max_height:
            return escala, total_h
        escala -= 0.12
    return 0.35, max_height


# ---------------- Símbolos dos selos (item 137) ----------------

def _simbolo_selo(c, tipo, cx, cy, s):
    """Desenha um pequeno símbolo (s = tamanho base em pontos) centrado em (cx, cy)."""
    c.saveState()
    c.setStrokeColor(CORAL)
    c.setFillColor(CORAL)
    c.setLineWidth(0.9)
    if tipo == "FRAGIL":
        # taça: base, haste, copo triangular + "trinca"
        c.line(cx - s*0.35, cy - s*0.5, cx + s*0.35, cy - s*0.5)   # base
        c.line(cx, cy - s*0.5, cx, cy - s*0.05)                     # haste
        p = c.beginPath()
        p.moveTo(cx - s*0.4, cy + s*0.5)
        p.lineTo(cx + s*0.4, cy + s*0.5)
        p.lineTo(cx, cy - s*0.05)
        p.close()
        c.drawPath(p, stroke=1, fill=0)
        c.setLineWidth(0.7)
        c.line(cx + s*0.05, cy + s*0.45, cx - s*0.12, cy + s*0.15)  # trinca
    elif tipo == "EXPLOSIVO":
        # explosão: estrela irregular
        import math
        pts = []
        for i in range(12):
            ang = math.radians(i * 30)
            r = s*0.5 if i % 2 == 0 else s*0.22
            pts.append((cx + r*math.cos(ang), cy + r*math.sin(ang)))
        p = c.beginPath()
        p.moveTo(*pts[0])
        for pt in pts[1:]:
            p.lineTo(*pt)
        p.close()
        c.drawPath(p, stroke=1, fill=1)
    elif tipo == "EMPILHAR":
        # duas setas para cima
        for dx in (-s*0.22, s*0.22):
            c.line(cx + dx, cy - s*0.5, cx + dx, cy + s*0.5)
            c.line(cx + dx, cy + s*0.5, cx + dx - s*0.18, cy + s*0.2)
            c.line(cx + dx, cy + s*0.5, cx + dx + s*0.18, cy + s*0.2)
    elif tipo == "NAO_EMPILHAR":
        # seta para cima com X
        c.line(cx, cy - s*0.5, cx, cy + s*0.5)
        c.line(cx, cy + s*0.5, cx - s*0.18, cy + s*0.2)
        c.line(cx, cy + s*0.5, cx + s*0.18, cy + s*0.2)
        c.setStrokeColor(colors.HexColor("#C0392B"))
        c.setLineWidth(1.3)
        c.line(cx - s*0.5, cy - s*0.5, cx + s*0.5, cy + s*0.5)
    c.restoreState()


_SELO_LABEL = {"FRAGIL": "FRÁGIL", "EXPLOSIVO": "EXPLOSIVO",
               "EMPILHAR": "PODE EMPILHAR", "NAO_EMPILHAR": "NÃO EMPILHAR"}


def _desenhar_envio(c, x, y, larg, alt, remetente, destinatario, vol_atual, vol_total,
                    nota_fiscal=None, selos=None):
    pad = min(larg, alt) * 0.07 + 3
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.setDash(2, 2)
    c.rect(x, y, larg, alt)
    c.setDash()

    cx = x + larg / 2   # centro horizontal (item 138 — dados centralizados)
    largura_txt = larg - 2 * pad

    # tag de volume (canto superior direito)
    tag_w, tag_h = min(larg * 0.42, 30 * mm), min(alt * 0.12, 8 * mm)
    c.setFillColor(GRAFITE)
    c.roundRect(x + larg - tag_w - pad, y + alt - tag_h - pad, tag_w, tag_h, 1.2 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    f_tag = min(tag_h * 0.5, 10)
    c.setFont("Helvetica-Bold", f_tag)
    c.drawCentredString(x + larg - tag_w/2 - pad, y + alt - tag_h - pad + tag_h*0.32, f"VOL {vol_atual}/{vol_total}")

    # blocos de texto (remetente + destinatário), centralizados
    contato_dest = " · ".join(filter(None, [destinatario.get("contato", ""), destinatario.get("telefone", "")]))
    linhas_spec = [
        ("REMETENTE", "Helvetica-Bold", 3.0),
        (remetente["nome"], "Helvetica-Bold", 4.2),
        (remetente.get("endereco", ""), "Helvetica", 3.0),
        (f"CNPJ {remetente.get('cnpj','')}" if remetente.get("cnpj") else "", "Helvetica", 3.0),
        (f"Contato: {remetente.get('contato','')}" if remetente.get("contato") else "", "Helvetica", 3.0),
        ("DESTINATÁRIO", "Helvetica-Bold", 3.0),
        (destinatario["nome"], "Helvetica-Bold", 4.2),
        (destinatario.get("endereco", ""), "Helvetica", 3.0),
        (f"CNPJ {destinatario.get('cnpj','')}" if destinatario.get("cnpj") else "", "Helvetica", 3.0),
        (contato_dest, "Helvetica", 3.0),
    ]
    if nota_fiscal:
        linhas_spec.append((f"NF: {nota_fiscal}", "Helvetica-Bold", 3.4))
    linhas_spec = [l for l in linhas_spec if l[0]]

    selos_ativos = [s for s in (selos or []) if s]
    reserva_selo = (min(larg, alt) * 0.16 + 6) if selos_ativos else 0
    area_h = alt - 2 * pad - tag_h - reserva_selo

    escala, _ = _fit_bloco(c, linhas_spec, largura_txt, area_h)

    # calcula altura total real para centralizar verticalmente
    total_h = 0
    for texto, font, rel in linhas_spec:
        size = rel * escala
        total_h += len(_wrap(c, texto, font, size, largura_txt)) * (size + 2.2)

    cursor_y = y + alt - tag_h - pad - (area_h - total_h) / 2
    for texto, font, rel in linhas_spec:
        size = rel * escala
        cor = CORAL if texto in ("REMETENTE", "DESTINATÁRIO") else GRAFITE
        c.setFillColor(cor)
        for ln in _wrap(c, texto, font, size, largura_txt):
            c.setFont(font, size)
            c.drawCentredString(cx, cursor_y - size, ln)
            cursor_y -= (size + 2.2)

    # selos com símbolo (item 137), centralizados na base
    if selos_ativos:
        f_selo = min(reserva_selo * 0.32, 8)
        sim = f_selo * 1.3
        larguras = []
        for s in selos_ativos:
            lab = _SELO_LABEL.get(s, s)
            larguras.append(sim * 1.6 + c.stringWidth(lab, "Helvetica-Bold", f_selo) + 8)
        total_w = sum(larguras) + (len(selos_ativos) - 1) * 6
        sx = cx - total_w / 2
        sy = y + pad + reserva_selo * 0.3
        for i, s in enumerate(selos_ativos):
            lab = _SELO_LABEL.get(s, s)
            w = larguras[i]
            c.setFillColor(colors.HexColor("#FFF1EF"))
            c.roundRect(sx, sy - sim*0.7, w, sim * 1.8, 2, fill=1, stroke=0)
            _simbolo_selo(c, s, sx + sim, sy + sim*0.2, sim)
            c.setFillColor(CORAL)
            c.setFont("Helvetica-Bold", f_selo)
            c.drawString(sx + sim*1.9, sy - f_selo*0.2, lab)
            sx += w + 6


def gerar_pdf_etiquetas_envio(remetente, destinatario, volumes, por_folha,
                              nota_fiscal=None, selos=None, orientacao="retrato"):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=_pagesize(orientacao))
    posicoes = _slots(por_folha, orientacao)
    total_paginas = -(-volumes // por_folha)
    vol = 1
    for _pagina in range(total_paginas):
        for (x, y, larg, alt) in posicoes:
            if vol > volumes:
                break
            _desenhar_envio(c, x, y, larg, alt, remetente, destinatario, vol, volumes,
                            nota_fiscal=nota_fiscal, selos=selos)
            vol += 1
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


def _desenhar_identificacao(c, x, y, larg, alt, texto):
    c.setStrokeColor(CORAL)
    c.setLineWidth(1.4)
    c.rect(x + 1.5*mm, y + 1.5*mm, larg - 3*mm, alt - 3*mm)
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.6)
    c.rect(x + 2.6*mm, y + 2.6*mm, larg - 5.2*mm, alt - 5.2*mm)

    faixa_h = min(alt * 0.14, 8 * mm)
    c.setFillColor(CORAL)
    c.rect(x + 2.6*mm, y + alt - 2.6*mm - faixa_h, larg - 5.2*mm, faixa_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    f_faixa = min(faixa_h * 0.55, 11)
    c.setFont("Helvetica-Bold", f_faixa)
    c.drawCentredString(x + larg/2, y + alt - 2.6*mm - faixa_h + faixa_h*0.3, "SERENA ENERGIA")

    pad = 5 * mm
    largura_txt = larg - 2 * pad
    area_h = alt - faixa_h - 2 * pad
    escala, _ = _fit_bloco(c, [(texto, "Helvetica-Bold", 5.0)], largura_txt, area_h)
    size = 5.0 * escala
    linhas = _wrap(c, texto, "Helvetica-Bold", size, largura_txt)
    total_h = len(linhas) * (size + 3)
    cursor_y = y + (alt - faixa_h)/2 + total_h/2
    c.setFillColor(GRAFITE)
    for ln in linhas:
        c.setFont("Helvetica-Bold", size)
        c.drawCentredString(x + larg/2, cursor_y - size, ln)
        cursor_y -= (size + 3)


def gerar_pdf_etiquetas_identificacao(texto, quantidade, por_folha, orientacao="retrato"):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=_pagesize(orientacao))
    posicoes = _slots(por_folha, orientacao)
    total_paginas = -(-quantidade // por_folha)
    n = 1
    for _pagina in range(total_paginas):
        for (x, y, larg, alt) in posicoes:
            if n > quantidade:
                break
            _desenhar_identificacao(c, x, y, larg, alt, texto)
            n += 1
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()
