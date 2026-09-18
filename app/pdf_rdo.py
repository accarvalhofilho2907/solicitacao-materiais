"""PDF do Relatório Diário de Obra (RDO) — segue o mesmo padrão visual do Relatório de
Carga (pdf_carga.py): paleta oficial Serena (Coral #FF5246, Grafite #4B4B4B, Areia #EDE9E5),
cabeçalho em bloco grafite, seções em faixa areia com filete coral. Não é salvo no banco —
gerado na hora, sob demanda (mesmo padrão do relatório de carga)."""
from io import BytesIO
import urllib.request

try:
    from reportlab import rl_config as _rl_config
    _rl_config.useA85 = 0
except Exception:
    pass

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                Image, PageBreak)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

try:
    from PIL import Image as PILImage, ImageOps, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    _TEM_PIL = True
except Exception:
    _TEM_PIL = False

_ST = getSampleStyleSheet()

CORAL = colors.HexColor("#FF5246")
VERDE = colors.HexColor("#32CAA0")
GRAFITE = colors.HexColor("#4B4B4B")
AREIA = colors.HexColor("#EDE9E5")
AREIA_ESCURA = colors.HexColor("#DED8D1")
BRANCO = colors.white

_CAB_TIT = ParagraphStyle("ct", parent=_ST["Normal"], textColor=BRANCO, fontSize=17,
                          fontName="Helvetica-Bold", leading=20)
_CAB_SUB = ParagraphStyle("cs", parent=_ST["Normal"], textColor=colors.HexColor("#C9C6C2"),
                          fontSize=8.5, fontName="Helvetica", leading=11)
_STATUS_LABEL = ParagraphStyle("sl", parent=_ST["Normal"], textColor=BRANCO, fontSize=8,
                               fontName="Helvetica", leading=10, alignment=1)
_STATUS_VAL = ParagraphStyle("sv", parent=_ST["Normal"], textColor=BRANCO, fontSize=13,
                             fontName="Helvetica-Bold", leading=15, alignment=1)
_SECAO = ParagraphStyle("s", parent=_ST["Normal"], fontName="Helvetica-Bold",
                        fontSize=9.5, textColor=GRAFITE, leading=12)
_LABEL = ParagraphStyle("l", parent=_ST["Normal"], fontName="Helvetica-Bold",
                        fontSize=7.5, textColor=colors.HexColor("#8A8580"), leading=9)
_VALOR = ParagraphStyle("v", parent=_ST["Normal"], fontName="Helvetica",
                        fontSize=9, textColor=GRAFITE, leading=12)
_OBS = ParagraphStyle("o", parent=_ST["Normal"], fontName="Helvetica", fontSize=9,
                      textColor=GRAFITE, leading=13)
_ATV_TIT = ParagraphStyle("at", parent=_ST["Normal"], fontName="Helvetica-Bold",
                          fontSize=9.5, textColor=GRAFITE, leading=12)


from reportlab.platypus import Flowable


class _FotoClicavel(Flowable):
    """[item 8] Flowable customizado: desenha a imagem no tamanho pedido e sobrepõe uma área
    de link clicável (canvas.linkURL) apontando pra URL original da foto — o reportlab não
    tem link embutido em Image por padrão."""
    def __init__(self, img_data, largura, altura, url):
        Flowable.__init__(self)
        self.img_data = img_data
        self.width = largura
        self.height = altura
        self.url = url

    def draw(self):
        self.canv.drawImage(ImageReader(self.img_data), 0, 0, width=self.width, height=self.height,
                            preserveAspectRatio=True, mask="auto")
        # relative=1: as coordenadas são relativas ao ponto onde ESTE Flowable está sendo
        # desenhado (o framework já posiciona (0,0) certo na página) — usar relative=0 aqui
        # gravava a coordenada errada no PDF final e o link não aparecia de verdade.
        self.canv.linkURL(self.url, (0, 0, self.width, self.height), relative=1, thickness=0)


def _campo(label, valor):
    return [Paragraph(label.upper(), _LABEL), Paragraph(str(valor or "—"), _VALOR)]


def _faixa_secao(titulo):
    t = Table([[Paragraph(titulo.upper(), _SECAO)]], colWidths=[178 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), AREIA),
        ("LINEBEFORE", (0, 0), (0, -1), 3, CORAL),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _grade(linhas):
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
    bloco = Table(blocos, colWidths=[LARG_TOTAL])
    bloco.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
    return bloco


def _baixar_foto(url, max_lado=1400, quality=85):
    """Baixa uma foto (URL do Cloudinary ou caminho relativo /uploads/...) e devolve os
    bytes já normalizados. Se falhar (foto removida, sem internet, etc.), devolve None —
    o PDF é gerado sem essa foto em vez de quebrar."""
    if not _TEM_PIL or not url:
        return None
    try:
        if url.startswith("http"):
            with urllib.request.urlopen(url, timeout=8) as resp:
                raw = resp.read()
        else:
            return None  # caminho local relativo — sem acesso direto ao disco daqui
        im = PILImage.open(BytesIO(raw))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if max(im.size) > max_lado:
            im.thumbnail((max_lado, max_lado))
        out = BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def gerar_pdf_rdo(rdo):
    """Gera o PDF do RDO. `rdo` é uma instância de RelatorioDiarioObra (já com .atividades
    resolvido). Retorna BytesIO pronto para enviar como resposta HTTP."""
    import json as _json

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0, bottomMargin=15 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)
    story = []

    # ---- Cabeçalho (bloco grafite, status do RDO à direita) ----
    status_cor = VERDE if rdo.status == "APROVADO" else colors.HexColor("#E6A700")
    cab_esq = Table([[Paragraph("RELATÓRIO DIÁRIO DE OBRA", _CAB_TIT)],
                     [Paragraph(f"{rdo.planta.nome if rdo.planta else '—'} · {rdo.data.strftime('%d/%m/%Y')}", _CAB_SUB)]],
                    colWidths=[120 * mm])
    cab_esq.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2)]))
    cab_dir = Table([[Paragraph("STATUS", _STATUS_LABEL)], [Paragraph(rdo.status, _STATUS_VAL)]], colWidths=[58 * mm])
    cab_dir.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), status_cor),
                                 ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    cab = Table([[cab_esq, cab_dir]], colWidths=[120 * mm, 58 * mm])
    cab.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), GRAFITE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("TOPPADDING", (0, 0), (-1, -1), 14), ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
                             ("LEFTPADDING", (0, 0), (0, 0), 16)]))
    story.append(cab)
    story.append(Spacer(1, 10))

    # ---- Dados gerais ----
    story.append(_faixa_secao("Dados gerais"))
    story.append(_grade([
        [_campo("Data", rdo.data.strftime("%d/%m/%Y")), _campo("Planta", rdo.planta.nome if rdo.planta else "—"),
         _campo("Condição climática", rdo.condicao_climatica)],
        [_campo("% média executada no dia", f"{rdo.percentual_medio}%" if rdo.percentual_medio is not None else "—"),
         _campo("Aprovado (Encarregado)", "Sim" if rdo.aprovado_encarregado_em else "Não"),
         _campo("Aprovado (Admin)", "Sim" if rdo.aprovado_admin_em else "Não")],
    ]))
    story.append(Spacer(1, 8))

    if rdo.mao_de_obra_texto:
        story.append(_faixa_secao("Mão de obra presente"))
        t = Table([[Paragraph(rdo.mao_de_obra_texto.replace("\n", "<br/>"), _OBS)]], colWidths=[178 * mm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t)
        story.append(Spacer(1, 8))

    if rdo.equipamentos_texto:
        story.append(_faixa_secao("Equipamentos usados no dia"))
        t = Table([[Paragraph(rdo.equipamentos_texto.replace("\n", "<br/>"), _OBS)]], colWidths=[178 * mm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t)
        story.append(Spacer(1, 8))

    if rdo.observacoes:
        story.append(_faixa_secao("Observações gerais"))
        t = Table([[Paragraph(rdo.observacoes.replace("\n", "<br/>"), _OBS)]], colWidths=[178 * mm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t)
        story.append(Spacer(1, 8))

    # ---- Atividades do dia (com colaboradores, observações da equipe, % e fotos) ----
    story.append(_faixa_secao(f"Atividades do dia ({len(rdo.atividades)})"))
    story.append(Spacer(1, 4))
    for grupo in rdo.atividades:
        dia_do_grupo = next((d for d in grupo.dias if d.data == rdo.data), None)
        nomes = ", ".join(ac.colaborador.nome for ac in grupo.colaboradores if ac.colaborador)
        linha_titulo = Table([[Paragraph(grupo.titulo, _ATV_TIT),
                              Paragraph(f"{dia_do_grupo.percentual}%" if dia_do_grupo and dia_do_grupo.percentual is not None else "—", _ATV_TIT)]],
                             colWidths=[148 * mm, 30 * mm])
        linha_titulo.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AREIA),
                                          ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                                          ("LEFTPADDING", (0, 0), (0, 0), 8), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                          ("RIGHTPADDING", (1, 0), (1, 0), 8)]))
        story.append(linha_titulo)
        detalhes = f"<b>Local:</b> {grupo.predio.nome if grupo.predio else '—'} &nbsp;·&nbsp; <b>Colaboradores:</b> {nomes or '—'}"
        if dia_do_grupo and dia_do_grupo.descricao_execucao:
            detalhes += f"<br/><b>Observações da equipe:</b> {dia_do_grupo.descricao_execucao}"
        story.append(Paragraph(detalhes, _OBS))
        story.append(Spacer(1, 4))

        # [item 8] fotos do dia: 4 pequenas lado a lado, CLICÁVEIS (abre a URL original,
        # sem compressão adicional, ao clicar em cima — usa um Flowable customizado porque o
        # reportlab não tem link embutido em Image "de fábrica").
        if dia_do_grupo and dia_do_grupo.fotos_json:
            try:
                urls = _json.loads(dia_do_grupo.fotos_json)
            except (ValueError, TypeError):
                urls = []
            imgs_ok = []
            for u in urls[:4]:
                foto_bytes = _baixar_foto(u)
                if foto_bytes:
                    imgs_ok.append((foto_bytes, u))
            if imgs_ok:
                cel_imgs = []
                for fb, url_original in imgs_ok:
                    img_reader = ImageReader(BytesIO(fb))
                    iw, ih = img_reader.getSize()
                    largura = 42 * mm
                    altura = largura * ih / iw
                    cel_imgs.append(_FotoClicavel(BytesIO(fb), largura, altura, url_original))
                linha_fotos = Table([cel_imgs], colWidths=[44 * mm] * len(cel_imgs))
                linha_fotos.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 2),
                                                 ("RIGHTPADDING", (0, 0), (-1, -1), 2)]))
                story.append(linha_fotos)
                story.append(Paragraph("Clique numa foto para abrir em tamanho grande.", _LABEL))
        story.append(Spacer(1, 10))

    if not rdo.atividades:
        story.append(Paragraph("Nenhuma atividade vinculada.", _OBS))

    doc.build(story)
    buf.seek(0)
    return buf
