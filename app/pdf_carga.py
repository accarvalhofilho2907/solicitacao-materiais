"""PDF do Relatório de Recebimento / Envio de Materiais (itens 111/128/135/145/147).

Redesenhado (item 135) com a paleta oficial Serena e layout profissional:
- Coral (#FF5246) nas faixas/destaques, Grafite (#4B4B4B) nos textos,
  Verde (#32CAA0) no status de Recebimento, Areia (#EDE9E5) nos fundos de seção.
- Seções: Cabeçalho, Remetente, Destinatário, Transportadora, Dados da Carga,
  Observações (avarias entram junto aqui — item 145), e Fotos.
- Fotos embutidas de verdade, UMA POR PÁGINA, em boa resolução (item 135).

Não é salvo no banco — só gera o PDF na hora (decisão do usuário, 08/07/2026).
"""
from io import BytesIO
import os
import tempfile

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                Image, PageBreak)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

try:
    from PIL import Image as PILImage, ImageOps
    _TEM_PIL = True
except Exception:
    _TEM_PIL = False


def _normalizar_imagem(raw, max_lado=2400, quality=90):
    """Converte foto (JPEG/PNG/EXIF/RGBA) em JPEG RGB limpo. 'raw' pode ser bytes OU
    um caminho de arquivo no disco (streaming, uma foto por vez). 2400px q90."""
    if not _TEM_PIL:
        return raw if isinstance(raw, (bytes, bytearray)) else None
    im = None
    try:
        fonte = BytesIO(raw) if isinstance(raw, (bytes, bytearray)) else raw
        im = PILImage.open(fonte)
        im = ImageOps.exif_transpose(im)   # corrige rotação vinda do celular
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if max(im.size) > max_lado:
            im.thumbnail((max_lado, max_lado))
        out = BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None
    finally:
        # libera o bitmap da memória assim que termina (importante com muitas fotos)
        try:
            if im is not None:
                im.close()
        except Exception:
            pass

_ST = getSampleStyleSheet()

CORAL = colors.HexColor("#FF5246")
VERDE = colors.HexColor("#32CAA0")
GRAFITE = colors.HexColor("#4B4B4B")
AREIA = colors.HexColor("#EDE9E5")
AREIA_ESCURA = colors.HexColor("#DED8D1")
BRANCO = colors.white

_TITULO = ParagraphStyle("t", parent=_ST["Normal"], textColor=BRANCO, fontSize=15,
                         fontName="Helvetica-Bold", leading=18)
_SUBTIT = ParagraphStyle("st", parent=_ST["Normal"], textColor=BRANCO, fontSize=8.5,
                         fontName="Helvetica", leading=11)
_SECAO = ParagraphStyle("s", parent=_ST["Normal"], fontName="Helvetica-Bold",
                        fontSize=9.5, textColor=GRAFITE, leading=12)
_LABEL = ParagraphStyle("l", parent=_ST["Normal"], fontName="Helvetica-Bold",
                        fontSize=7.5, textColor=colors.HexColor("#8A8580"), leading=9)
_VALOR = ParagraphStyle("v", parent=_ST["Normal"], fontName="Helvetica",
                        fontSize=9, textColor=GRAFITE, leading=12)
_OBS = ParagraphStyle("o", parent=_ST["Normal"], fontName="Helvetica", fontSize=9,
                      textColor=GRAFITE, leading=13)

# Estilos do cabeçalho (Opção 3 — bloco grafite com status integrado)
_MARCA_S = ParagraphStyle("ms", parent=_ST["Normal"], textColor=BRANCO, fontSize=20,
                          fontName="Helvetica-Bold", leading=20, alignment=1)
_CAB_TIT = ParagraphStyle("ct", parent=_ST["Normal"], textColor=BRANCO, fontSize=17,
                          fontName="Helvetica-Bold", leading=20)
_CAB_SUB = ParagraphStyle("cs", parent=_ST["Normal"], textColor=colors.HexColor("#C9C6C2"),
                          fontSize=8.5, fontName="Helvetica", leading=11)
_STATUS_LABEL = ParagraphStyle("sl", parent=_ST["Normal"], textColor=BRANCO, fontSize=8,
                               fontName="Helvetica", leading=10, alignment=1)
_STATUS_VAL = ParagraphStyle("sv", parent=_ST["Normal"], textColor=BRANCO, fontSize=13,
                             fontName="Helvetica-Bold", leading=15, alignment=1)


def _campo(label, valor):
    """Uma célula com rótulo pequeno em cima e valor embaixo."""
    return [Paragraph(label.upper(), _LABEL), Paragraph(str(valor or "—"), _VALOR)]


def _faixa_secao(titulo):
    """Barra de título de seção, fundo areia com um filete coral à esquerda."""
    t = Table([[Paragraph(titulo.upper(), _SECAO)]], colWidths=[178 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AREIA),
        ("LINEBEFORE", (0, 0), (0, -1), 3, CORAL),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _grade(linhas):
    """Monta uma grade de campos. linhas: lista de listas de células;
    cada célula é [Paragraph_label, Paragraph_valor]. Cada linha é renderizada
    como sua própria mini-tabela ocupando a largura total, dividida igualmente
    pelo nº de colunas daquela linha (2 ou 3). Assim nada estoura a margem."""
    LARG_TOTAL = 178 * mm
    PAD_LAT = 8
    blocos = []
    for idx, linha in enumerate(linhas):
        n = len(linha)
        col_width = LARG_TOTAL / n
        larg_interna = col_width - (PAD_LAT * 2)
        cells = []
        for cel in linha:
            sub = Table([[cel[0]], [cel[1]]], colWidths=[larg_interna])
            sub.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 1),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
            cells.append(sub)
        row_tab = Table([cells], colWidths=[col_width] * n)
        estilo = [
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), PAD_LAT), ("RIGHTPADDING", (0, 0), (-1, -1), PAD_LAT),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        if idx < len(linhas) - 1:
            estilo.append(("LINEBELOW", (0, 0), (-1, -1), 0.4, AREIA_ESCURA))
        row_tab.setStyle(TableStyle(estilo))
        blocos.append([row_tab])
    # empilha as linhas numa tabela única de 1 coluna
    t = Table(blocos, colWidths=[LARG_TOTAL])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def gerar_pdf_relatorio_carga(modo, dados, fotos=None):
    """modo: 'recebimento' ou 'envio'. dados: dict do formulário. fotos: lista de dicts
    {bytes, legenda, avaria(bool), obs} — embutidas uma por página no fim (item 135)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0, bottomMargin=15 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)
    el = []
    _temp_fotos = []   # arquivos temporários das fotos (limpos após build)

    is_receb = (modo == "recebimento")
    status_txt = "RECEBIMENTO" if is_receb else "ENVIO"
    status_cor = VERDE if is_receb else CORAL

    # ---------- Cabeçalho (faixa grafite única, status como tag dentro dela) ----------
    ALT_CAB = 26 * mm
    # marca "S" num quadrado coral
    marca = Table([[Paragraph("S", _MARCA_S)]], colWidths=[13 * mm], rowHeights=[13 * mm])
    marca.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CORAL),
                               ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    # tag de status (pílula colorida) — fica DENTRO da faixa grafite, à direita
    tag_status = Table([[Paragraph(status_txt, _STATUS_VAL)]], colWidths=[42 * mm], rowHeights=[13 * mm])
    tag_status.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), status_cor),
                                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                                    ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    # conteúdo da faixa: marca S | título | (espaço) | tag de status — tudo sobre grafite
    conteudo = Table(
        [[marca,
          [Paragraph("RELATÓRIO DE CARGA", _CAB_TIT),
           Paragraph("Serena Energia · Almoxarifado Cluster Delta MA", _CAB_SUB)],
          tag_status]],
        colWidths=[13 * mm, 116 * mm, 42 * mm])
    conteudo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                  ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 14),
                                  ("LEFTPADDING", (1, 0), (1, 0), 0),
                                  ("LEFTPADDING", (2, 0), (2, 0), 0), ("RIGHTPADDING", (2, 0), (2, 0), 0),
                                  ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    # faixa: barrinha coral fina à esquerda + faixa grafite ocupando o resto (largura total)
    cab = Table([["", conteudo]], colWidths=[2.5 * mm, 175.5 * mm], rowHeights=[ALT_CAB])
    cab.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), CORAL),
        ("BACKGROUND", (1, 0), (1, 0), GRAFITE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 12), ("RIGHTPADDING", (1, 0), (1, 0), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    el.append(cab)

    # aviso de avaria (se houver)
    tem_avaria = dados.get("tem_avaria")
    if tem_avaria:
        aviso = Table([[Paragraph('<font color="white"><b>⚠ ATENÇÃO: carga com item(ns) avariado(s) — ver Observações Gerais</b></font>', _ST["Normal"])]],
                      colWidths=[178 * mm])
        aviso.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#C0392B")),
                                   ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        el.append(aviso)
    el.append(Spacer(1, 6 * mm))

    # ---------- Cabeçalho: Data / Responsável ----------
    el.append(_faixa_secao("Cabeçalho"))
    el.append(_grade([[_campo("Data", dados.get("data")), _campo("Responsável", dados.get("responsavel")),
                       _campo("Status", status_txt.capitalize())]]))
    el.append(Spacer(1, 4 * mm))

    # ---------- Remetente ----------
    el.append(_faixa_secao("Remetente"))
    el.append(_grade([
        [_campo("Razão Social / Nome", dados.get("rem_nome")), _campo("CNPJ", dados.get("rem_cnpj"))],
        [_campo("Inscrição Estadual", dados.get("rem_ie")), _campo("Endereço", dados.get("rem_endereco"))],
    ]))
    el.append(Spacer(1, 4 * mm))

    # ---------- Destinatário ----------
    el.append(_faixa_secao("Destinatário"))
    el.append(_grade([
        [_campo("Razão Social / Nome", dados.get("dest_nome")), _campo("CNPJ", dados.get("dest_cnpj"))],
        [_campo("Inscrição Estadual", dados.get("dest_ie")), _campo("Endereço", dados.get("dest_endereco"))],
    ]))
    el.append(Spacer(1, 4 * mm))

    # ---------- Transportadora (sem IE) ----------
    el.append(_faixa_secao("Transportadora"))
    el.append(_grade([
        [_campo("Razão Social / Nome", dados.get("transp_nome")), _campo("CNPJ", dados.get("transp_cnpj"))],
        [_campo("Endereço", dados.get("transp_endereco"))],
    ]))
    el.append(Spacer(1, 4 * mm))

    # ---------- Dados da Carga ----------
    el.append(_faixa_secao("Dados da Carga"))
    el.append(_grade([
        [_campo("Nº Nota Fiscal", dados.get("nota_fiscal")), _campo("Série", dados.get("serie")),
         _campo("OC", dados.get("oc"))],
        [_campo("Qtd. Volumes", dados.get("qtd_volumes")), _campo("Tipo de Volume", dados.get("tipo_volume")),
         _campo("Valor da NF", dados.get("valor_nf"))],
        [_campo("Natureza da Operação", dados.get("natureza_operacao")), _campo("Nº CT-e", dados.get("cte")),
         _campo("Valor do CT-e", dados.get("valor_cte"))],
        [_campo("Tomador do CT-e", dados.get("tomador_cte")), _campo("Descrição da Carga", dados.get("descricao_carga"))],
    ]))
    el.append(Spacer(1, 4 * mm))

    # ---------- Observações Gerais (avarias entram aqui — item 145) ----------
    el.append(_faixa_secao("Observações Gerais"))
    obs_txt = (dados.get("observacoes") or "S/ observações").strip()
    corpo_obs = [Paragraph(obs_txt, _OBS)]
    obs_avarias = dados.get("obs_avarias") or []
    if obs_avarias:
        corpo_obs.append(Spacer(1, 2 * mm))
        corpo_obs.append(Paragraph('<font color="#C0392B"><b>Avarias registradas nas fotos:</b></font>', _OBS))
        for i, o in enumerate(obs_avarias, 1):
            corpo_obs.append(Paragraph(f"{i}. {o}", _OBS))
    box = Table([[corpo_obs]], colWidths=[178 * mm])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, AREIA_ESCURA),
                             ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                             ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    el.append(box)

    # ---------- Fotos (uma por página, alta resolução — item 135) ----------
    # Memória controlada por streaming: cada foto é normalizada, escrita e liberada
    # antes da próxima (o pico é de UMA foto por vez, não de todas somadas).
    fotos = fotos or []
    if fotos:
        for foto in fotos:
            legenda = foto.get("legenda") or "Foto da carga"
            if foto.get("avaria"):
                legenda += "  —  ⚠ AVARIADO"
            img_bytes = _normalizar_imagem(foto.get("bytes") or foto.get("path"))
            foto["bytes"] = None  # libera a foto original (pesada) da memória assim que normaliza
            if not img_bytes:
                # não conseguiu processar a imagem: registra aviso mas NÃO derruba o PDF
                el.append(PageBreak())
                el.append(_faixa_secao(legenda))
                el.append(Spacer(1, 4 * mm))
                el.append(Paragraph("(não foi possível processar esta imagem — formato não suportado)", _OBS))
                continue
            try:
                img_reader = ImageReader(BytesIO(img_bytes))
                iw, ih = img_reader.getSize()
                max_w, max_h = 178 * mm, 205 * mm
                ratio = min(max_w / iw, max_h / ih)
                # Grava em arquivo temporário e usa Image por caminho com lazy=2:
                # o ReportLab abre a imagem só na hora de desenhar e libera depois,
                # mantendo o pico de memória em ~uma foto por vez (não todas juntas).
                tf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                tf.write(img_bytes); tf.close()
                _temp_fotos.append(tf.name)
                img_bytes = None  # libera a versão em memória
                img = Image(tf.name, width=iw * ratio, height=ih * ratio, lazy=2)
                img.hAlign = "CENTER"
                el.append(PageBreak())
                el.append(_faixa_secao(legenda))
                el.append(Spacer(1, 4 * mm))
                el.append(img)
                if foto.get("avaria") and foto.get("obs"):
                    el.append(Spacer(1, 3 * mm))
                    el.append(Paragraph(f'<font color="#C0392B"><b>Avaria:</b></font> {foto["obs"]}', _OBS))
            except Exception:
                el.append(PageBreak())
                el.append(_faixa_secao(legenda))
                el.append(Spacer(1, 4 * mm))
                el.append(Paragraph("(não foi possível carregar esta imagem)", _OBS))

    def _rodape(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#8A8580"))
        canvas.drawCentredString(A4[0] / 2, 8 * mm,
                                 "Serena Energia · Almoxarifado Cluster Delta MA · documento gerado pelo sistema")
        canvas.restoreState()

    doc.build(el, onFirstPage=_rodape, onLaterPages=_rodape)
    # remove os arquivos temporários das fotos
    for _p in _temp_fotos:
        try:
            os.unlink(_p)
        except Exception:
            pass
    buf.seek(0)
    return buf.getvalue()
