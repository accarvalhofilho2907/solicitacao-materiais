"""PDF do Relatório Diário de Obra (RDO) — segue o mesmo padrão visual do Relatório de
Carga (pdf_carga.py): paleta oficial Serena (Coral #FF5246, Grafite #4B4B4B, Areia #EDE9E5),
cabeçalho em bloco grafite, seções em faixa areia com filete coral. Não é salvo no banco —
gerado na hora, sob demanda (mesmo padrão do relatório de carga)."""
from io import BytesIO
import requests

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
    o PDF é gerado sem essa foto em vez de quebrar.
    [fix 22/09] Trocado urllib.request por requests — mais robusto com SSL/redirects em
    ambientes containerizados (Render); antes qualquer falha de certificado ou redirect
    do Cloudinary podia derrubar silenciosamente TODAS as fotos do PDF. Log de erro real
    mantido (antes engolia tudo em silêncio, impossível diagnosticar em produção)."""
    if not _TEM_PIL or not url:
        return None
    try:
        if url.startswith("http"):
            resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (SIGA-RDO-PDF)"},
                               allow_redirects=True)
            resp.raise_for_status()
            raw = resp.content
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
    except Exception as e:
        try:
            from flask import current_app
            current_app.logger.warning("RDO PDF: falha ao baixar/processar foto %s — %s: %s", url, type(e).__name__, e)
        except Exception:
            pass  # fora de um contexto de app (ex.: teste isolado) — não quebra por causa do log
        return None


def _ausentes_do_dia_pdf(rdo):
    """[23/09 segunda leva] Mesma lógica de app/facilities.py::_ausentes_do_dia, reimplementada
    aqui pra não criar import circular (pdf_rdo é importado por facilities) — colaboradores das
    atividades do RDO que estão de férias/ausência na data do RDO."""
    from .models import AusenciaColaborador, Colaborador
    from .extensions import db
    colaboradores_ids = {ac.colaborador_id for grupo in rdo.atividades for ac in grupo.colaboradores}
    if not colaboradores_ids:
        return []
    ausentes = []
    for cid in colaboradores_ids:
        aus = (AusenciaColaborador.query.filter_by(colaborador_id=cid)
              .filter(AusenciaColaborador.data_inicio <= rdo.data, AusenciaColaborador.data_retorno > rdo.data)
              .first())
        if aus:
            colab = db.session.get(Colaborador, cid)
            ausentes.append({"nome": colab.nome if colab else "—", "motivo": aus.motivo})
    return ausentes


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

    # [23/09 segunda leva] Mão de obra (Nome, Função, Horários) movida pro CABEÇALHO do PDF —
    # antes ficava só na seção própria mais abaixo (entrega anterior); agora aparece logo no
    # topo também, junto dos dados gerais, pedido do Antonio.
    if rdo.mao_de_obra:
        story.append(_faixa_secao(f"Mão de obra ({len(rdo.mao_de_obra)})"))
        cab_mo = ["Nome", "Função", "Entrada", "Saída"]
        linhas_mo_cab = [cab_mo] + [[m.nome, m.funcao or "—", m.horario_entrada or "—", m.horario_saida or "—"]
                                    for m in rdo.mao_de_obra]
        t_mo_cab = Table(linhas_mo_cab, colWidths=[70 * mm, 60 * mm, 24 * mm, 24 * mm])
        t_mo_cab.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AREIA), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA), ("LINEBELOW", (0, 0), (-1, -2), 0.4, AREIA_ESCURA),
            ("TEXTCOLOR", (0, 1), (-1, -1), GRAFITE),
        ]))
        story.append(t_mo_cab)
        story.append(Spacer(1, 8))
    elif rdo.mao_de_obra_texto:   # [legado] RDOs antigos sem RDOMaoDeObra
        story.append(_faixa_secao("Mão de obra presente"))
        t_mo_cab = Table([[Paragraph(rdo.mao_de_obra_texto.replace("\n", "<br/>"), _OBS)]], colWidths=[178 * mm])
        t_mo_cab.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t_mo_cab)
        story.append(Spacer(1, 8))

    # ---- Dados gerais ----
    # [23/09 reformulacao RDO] Removidos do PDF: Obra, Contratante, Responsável, Prazo
    # contratual/decorrido/a vencer (nunca existiram nesta versão do RDO — o modelo de
    # referência do Antonio tinha esses campos, mas o SIGA não usa essas entidades aqui).
    # Clima agora é Manhã/Tarde (RDOs antigos sem clima_manha/clima_tarde caem no fallback
    # da coluna antiga condicao_climatica, pra não quebrar PDF de relatório já salvo).
    clima_manha = rdo.clima_manha or (rdo.condicao_climatica or "—")
    clima_tarde = rdo.clima_tarde or (rdo.condicao_climatica or "—")
    horario_txt = f"{rdo.horario_inicio or '—'} às {rdo.horario_termino or '—'}"
    if rdo.horario_intervalo_inicio and rdo.horario_intervalo_fim:
        horario_txt += f" (intervalo {rdo.horario_intervalo_inicio}-{rdo.horario_intervalo_fim})"
    story.append(_faixa_secao("Dados gerais"))
    # [23/09 segunda leva] "% média executada" removida do PDF (pedido do Antonio) — o campo/
    # cálculo (percentual_medio / _calcular_media_ponderada_dia) continua existindo no banco.
    story.append(_grade([
        [_campo("Data", rdo.data.strftime("%d/%m/%Y")), _campo("Planta", rdo.planta.nome if rdo.planta else "—")],
        [_campo("Clima — Manhã", clima_manha), _campo("Clima — Tarde", clima_tarde),
         _campo("Horário de trabalho", horario_txt)],
    ]))
    story.append(Spacer(1, 8))

    # [23/09 segunda leva] ausentes/férias do dia — item 4 do pedido
    ausentes = _ausentes_do_dia_pdf(rdo)
    if ausentes:
        story.append(_faixa_secao("Colaboradores ausentes"))
        texto_ausentes = ", ".join(f"{a['nome']} ({a['motivo']})" for a in ausentes)
        t_aus = Table([[Paragraph(texto_ausentes, _OBS)]], colWidths=[178 * mm])
        t_aus.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t_aus)
        story.append(Spacer(1, 8))

    # [23/09 segunda leva] mão de obra já foi exibida no CABEÇALHO (ver acima) — não repete
    # aqui embaixo pra não duplicar a mesma tabela duas vezes no PDF.

    # ---- Equipamentos (caixa SEPARADA da mão de obra — RDOEquipamento) ----
    if rdo.equipamentos:
        story.append(_faixa_secao(f"Equipamentos ({len(rdo.equipamentos)})"))
        linhas_eq = [["Equipamento", "Quantidade"]] + [[e.nome, str(e.quantidade or 1)] for e in rdo.equipamentos]
        t = Table(linhas_eq, colWidths=[138 * mm, 40 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), AREIA), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA), ("LINEBELOW", (0, 0), (-1, -2), 0.4, AREIA_ESCURA),
            ("TEXTCOLOR", (0, 1), (-1, -1), GRAFITE),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))
    elif rdo.equipamentos_texto:   # [legado]
        story.append(_faixa_secao("Equipamentos usados no dia"))
        t = Table([[Paragraph(rdo.equipamentos_texto.replace("\n", "<br/>"), _OBS)]], colWidths=[178 * mm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t)
        story.append(Spacer(1, 8))

    if rdo.ocorrencias:
        story.append(_faixa_secao("Ocorrências"))
        t = Table([[Paragraph(rdo.ocorrencias.replace("\n", "<br/>"), _OBS)]], colWidths=[178 * mm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t)
        story.append(Spacer(1, 8))

    if rdo.comentarios:
        story.append(_faixa_secao("Comentários"))
        t = Table([[Paragraph(rdo.comentarios.replace("\n", "<br/>"), _OBS)]], colWidths=[178 * mm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t)
        story.append(Spacer(1, 8))

    # [23/09 segunda leva] campo "Observações" removido do PDF — Ocorrências e Comentários
    # cobrem o mesmo papel (RelatorioDiarioObra.observacoes continua no banco, sem uso aqui).

    # ---- Maquinário Pesado (22/09) — só os NOMES das máquinas usadas neste dia, conforme
    # pedido explícito do Antonio ("somente virá o nome da máquina mesmo") ----
    nomes_maquinas = sorted({g.maquina_horimetro.nome for g in rdo.atividades
                            if g.tem_horimetro and g.maquina_horimetro})
    if nomes_maquinas:
        story.append(_faixa_secao("Maquinário Pesado"))
        texto_maquinas = ", ".join(nomes_maquinas)
        t = Table([[Paragraph(texto_maquinas, _OBS)]], colWidths=[178 * mm])
        t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("BOX", (0, 0), (-1, -1), 0.6, AREIA_ESCURA)]))
        story.append(t)
        story.append(Spacer(1, 8))

    def _monta_grade_fotos(pares_bytes_url, n_colunas=2):
        """[23/09 reformulacao RDO] Monta uma grade 2xN de fotos clicáveis, preenchendo com
        células vazias (em branco) quando sobrar espaço na última linha — sem quebrar layout.
        pares_bytes_url é uma lista de (bytes, url_original)."""
        if not pares_bytes_url:
            return None
        largura = 84 * mm
        linhas_grade = []
        linha_atual = []
        for fb, url_original in pares_bytes_url:
            img_reader = ImageReader(BytesIO(fb))
            iw, ih = img_reader.getSize()
            altura = min(largura * ih / iw, 60 * mm)
            linha_atual.append(_FotoClicavel(BytesIO(fb), largura, altura, url_original))
            if len(linha_atual) == n_colunas:
                linhas_grade.append(linha_atual)
                linha_atual = []
        if linha_atual:
            while len(linha_atual) < n_colunas:
                linha_atual.append(Paragraph("", _OBS))   # célula vazia em branco
            linhas_grade.append(linha_atual)
        grade = Table(linhas_grade, colWidths=[88 * mm] * n_colunas)
        grade.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                                   ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return grade

    # ---- Atividades do dia: título em cima (com % ou FIXO à direita), descrição, e as fotos
    # EMBAIXO em grade 2x2 (até 4 normal / até 6 com horímetro — 4 da atividade + 2 do painel) ----
    story.append(_faixa_secao(f"Atividades do dia ({len(rdo.atividades)})"))
    story.append(Spacer(1, 4))
    for grupo in rdo.atividades:
        dia_do_grupo = next((d for d in grupo.dias if d.data == rdo.data), None)
        nomes = ", ".join(ac.colaborador.nome for ac in grupo.colaboradores if ac.colaborador)
        # [23/09 reformulacao RDO] % do dia (AtividadeDia.percentual) substitui dias_restantes
        # na exibição do RDO — cada RDO mostra a % daquele DIA específico, não acumulada.
        # FIXA nunca tem %, mostra só "FIXO".
        if grupo.eh_fixa:
            valor_progresso = "FIXO"
        elif dia_do_grupo and dia_do_grupo.percentual is not None:
            valor_progresso = f"{dia_do_grupo.percentual}%"
        else:
            valor_progresso = "—"
        linha_titulo = Table([[Paragraph(grupo.titulo, _ATV_TIT),
                              Paragraph(valor_progresso, _ATV_TIT)]],
                             colWidths=[148 * mm, 30 * mm])
        linha_titulo.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), AREIA),
                                          ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                                          ("LEFTPADDING", (0, 0), (0, 0), 8), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                                          ("RIGHTPADDING", (1, 0), (1, 0), 8)]))
        story.append(linha_titulo)
        detalhes = f"<b>Local:</b> {grupo.predio.nome if grupo.predio else '—'} &nbsp;·&nbsp; <b>Colaboradores:</b> {nomes or '—'}"
        if dia_do_grupo and dia_do_grupo.descricao_execucao:
            detalhes += f"<br/><b>Descrição:</b> {dia_do_grupo.descricao_execucao}"
        story.append(Paragraph(detalhes, _OBS))
        story.append(Spacer(1, 4))

        fotos_painel_urls = []
        # [22/09] Máquina com horímetro: mostra horímetro inicial, final e horas trabalhadas
        # NO DIA (calculado). As fotos do painel entram na MESMA grade das fotos da atividade
        # (até 6 no total — 4 da atividade + 2 do painel).
        if grupo.tem_horimetro and dia_do_grupo:
            registros = {r.tipo: r for r in dia_do_grupo.registros_horimetro}
            if registros:
                partes = [f"<b>🚜 Horímetro ({grupo.maquina_horimetro.nome if grupo.maquina_horimetro else '—'}):</b>"]
                if "INICIO" in registros:
                    partes.append(f"inicial {registros['INICIO'].valor_horimetro}h")
                if "FIM" in registros:
                    partes.append(f"final {registros['FIM'].valor_horimetro}h")
                if "INICIO" in registros and "FIM" in registros:
                    diff = registros["FIM"].valor_horimetro - registros["INICIO"].valor_horimetro
                    partes.append(f"(horas trabalhadas no dia: {round(diff, 1)}h)")
                story.append(Paragraph(" — ".join(partes), _OBS))
                story.append(Spacer(1, 3))
                fotos_painel_urls = [r.foto_painel_url for r in registros.values() if r.foto_painel_url]

        # [item 8] fotos: normal até 4, com horímetro até 6 (4 da atividade + 2 do painel) —
        # grade 2x2 (ou 2x3), CLICÁVEIS (abre a URL original ao clicar).
        max_fotos_atividade = 4
        urls_atividade = []
        if dia_do_grupo and dia_do_grupo.fotos_json:
            try:
                urls_atividade = _json.loads(dia_do_grupo.fotos_json)
            except (ValueError, TypeError):
                urls_atividade = []
        urls_todas = list(urls_atividade[:max_fotos_atividade]) + list(fotos_painel_urls[:2])
        imgs_ok = []
        falhas = []
        for u in urls_todas:
            foto_bytes = _baixar_foto(u)
            if foto_bytes:
                imgs_ok.append((foto_bytes, u))
            else:
                falhas.append(u)
        grade_fotos = _monta_grade_fotos(imgs_ok)
        if grade_fotos:
            story.append(grade_fotos)
            story.append(Paragraph("Clique numa foto para abrir em tamanho grande.", _LABEL))
        if falhas:
            # [fix 22/09] antes uma foto que falhasse ao baixar simplesmente SUMIA do PDF
            # sem nenhum rastro — impossível saber se ela existia ou não. Agora aparece um
            # aviso explícito com o link direto, pra pessoa poder abrir manualmente e o
            # problema fica visível em vez de silencioso.
            aviso = f"⚠️ {len(falhas)} foto(s) não puderam ser incluídas automaticamente neste PDF. Abra o link diretamente: " + \
                    " | ".join(f'<link href="{u}">{u[:50]}...</link>' for u in falhas)
            story.append(Paragraph(aviso, _LABEL))
        story.append(Spacer(1, 10))

    if not rdo.atividades:
        story.append(Paragraph("Nenhuma atividade vinculada.", _OBS))

    # ---- Aprovação (Encarregado E Admin — as duas, quando existirem) ----
    story.append(Spacer(1, 6))
    story.append(_faixa_secao("Aprovação"))
    txt_encarregado = "Pendente"
    if rdo.aprovado_encarregado_em:
        txt_encarregado = f"{rdo.aprovado_encarregado_nome or '—'} em {rdo.aprovado_encarregado_em.strftime('%d/%m/%Y %H:%M')}"
    txt_admin = "Pendente"
    if rdo.aprovado_admin_em:
        txt_admin = f"{rdo.aprovado_admin_nome or '—'} em {rdo.aprovado_admin_em.strftime('%d/%m/%Y %H:%M')}"
    story.append(_grade([[_campo("Encarregado", txt_encarregado), _campo("Admin", txt_admin)]]))

    doc.build(story)
    buf.seek(0)
    return buf
