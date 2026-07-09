"""Leitor de PDF de orçamento do fornecedor (item 114).

Estratégia (calibrada com 4 modelos reais em 09/07/2026):
1) Lê o texto com pdfplumber, preservando as linhas.
2) Detecta o fornecedor pelo CNPJ que aparece no topo do PDF e aplica o
   parser específico daquele layout (Cofermeta, FBM, Ferramentech, Lojão/Tucano).
3) Se não reconhecer o fornecedor, cai num parser genérico mais tolerante.

Cada item devolvido: {descricao, valor (preço unitário), quantidade, unidade, subtotal, codigo}.

Cada fornecedor tem um layout bem diferente (ordem das colunas, colunas extras
como NCM/CST/ICMS, e até separador decimal). Por isso a detecção por CNPJ:
- Cofermeta  17.281.973/0008-15 — descrição na linha ACIMA do código; BR (vírgula)
- FBM        28.933.967/0001-45 — código no meio, marca/prazo em texto; BR
- Ferramentech 19.544.638/0001-11 — separador decimal AMERICANO (1,063.47)
- Lojão/Tucano 40.217.808/0001-40 — quantidade primeiro; descrição pode quebrar em 2 linhas; BR
"""
import re


def _so_digitos(s):
    return re.sub(r"\D", "", s or "")


def _val_br(s):
    """Converte '1.498,00' -> 1498.0 (formato brasileiro)."""
    if s is None:
        return None
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _val_us(s):
    """Converte '1,063.47' -> 1063.47 (formato americano)."""
    if s is None:
        return None
    s = s.strip().replace(",", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _parse_valor(s):
    """Interpreta um valor digitado pelo usuário (no de-para), aceitando BR ou US.
    Ex.: '1.498,00' -> 1498.0 ; '1,063.47' -> 1063.47 ; '30.19' -> 30.19."""
    if s is None:
        return None
    s = str(s).strip().replace("R$", "").strip()
    if not s:
        return None
    if "," in s and "." in s:
        # o último separador manda: se vírgula vem depois, é BR; senão US
        return _val_br(s) if s.rfind(",") > s.rfind(".") else _val_us(s)
    if "," in s:
        return _val_br(s)
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _linhas(file_storage):
    import pdfplumber
    linhas = []
    with pdfplumber.open(file_storage) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            linhas += [l.rstrip() for l in texto.split("\n")]
    return linhas


# ---------------- Parsers específicos por fornecedor ----------------

# Cofermeta: linha do item = Nº Código UN ... Qtde NCM CST %ICMS VrUnit VrTotal PRAZO 0,00
# A DESCRIÇÃO fica na linha imediatamente ACIMA do código.
_COFERMETA_ITEM = re.compile(
    r"^\s*(\d+)\s+(\d{3,})\s+([A-Z]{1,3})\s+.*?\s+"
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"       # qtde
    r"\d+\s+\d+\s+\d{1,3},\d{2}\s+"          # NCM CST %ICMS
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"        # Vr Unit c/ ICMS
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"        # Vr Total c/ ICMS
    r"\w+")                                   # prazo (IMEDIATO)


def _parse_cofermeta(linhas):
    itens = []
    for i, ln in enumerate(linhas):
        m = _COFERMETA_ITEM.match(ln)
        if not m:
            continue
        num, cod, und, qtd, unit, total = m.groups()
        # descrição: linha anterior não-vazia (que não seja cabeçalho de coluna)
        desc = ""
        j = i - 1
        while j >= 0:
            cand = linhas[j].strip()
            if cand and not cand.startswith("N°") and "Descrição" not in cand and "Incluso" not in cand:
                desc = cand
                break
            j -= 1
        itens.append({"descricao": desc or f"Item {num}", "unidade": und,
                      "quantidade": _val_br(qtd), "valor": _val_br(unit),
                      "subtotal": _val_br(total), "codigo": cod})
    return itens


# FBM: Item Qtde Código descrição MARCA prazo PrecoUnit PrecoTotal
_FBM_ITEM = re.compile(
    r"^\s*(\d+)\s+(\d{1,4})\s+(.+?)\s+"      # item, qtde, resto(codigo+desc+marca+prazo)
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"        # preço unit
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*$")      # preço total


def _parse_fbm(linhas):
    itens = []
    dentro = False
    for ln in linhas:
        if "Detalhamento do Orçamento" in ln or ln.strip().startswith("Item Qtde"):
            dentro = True
            continue
        if not dentro:
            continue
        if "APROVAÇÃO" in ln or "Observações" in ln:
            break
        m = _FBM_ITEM.match(ln)
        if not m:
            continue
        item, qtd, meio, unit, total = m.groups()
        # meio = "6203 ZZ - ROL. RIGIDO DE ESFERAS SKF 1 A 2 DIAS" -> tira prazo e marca do fim
        meio_limpo = re.sub(r"\s+\d+\s+A\s+\d+\s+DIAS\s*$", "", meio)  # remove "1 A 2 DIAS"
        itens.append({"descricao": meio_limpo.strip(), "unidade": None,
                      "quantidade": _val_br(qtd), "valor": _val_br(unit),
                      "subtotal": _val_br(total), "codigo": None})
    return itens


# Ferramentech: Item Código descrição NCM ... Qtd P.Unit Valor prazo  (decimais AMERICANOS)
_FERRA_ITEM = re.compile(
    r"^\s*(\d+)\s+(\w+)\s+(.+?)\s+"          # item, código, descrição+marca
    r"(\d{8})\s+"                            # NCM (8 dígitos)
    r"(\d+)\s+"                              # Qtd
    r"(\d{1,3}(?:,\d{3})*\.\d{2})\s+"        # P.Unitário (US)
    r"(\d{1,3}(?:,\d{3})*\.\d{2})\s+")       # Valor (US)


def _parse_ferramentech(linhas):
    itens = []
    for ln in linhas:
        m = _FERRA_ITEM.match(ln)
        if not m:
            continue
        item, cod, desc, ncm, qtd, unit, valor = m.groups()
        itens.append({"descricao": desc.strip(), "unidade": None,
                      "quantidade": _val_br(qtd), "valor": _val_us(unit),
                      "subtotal": _val_us(valor), "codigo": cod})
    return itens


# Lojão/Tucano: QTDE UNID0 CODIGO [REF] descrição PRECO TOTAL ; descrição pode quebrar em 2 linhas
_LOJAO_ITEM = re.compile(
    r"^\s*(\d{1,3},\d{2})\s+UNID\S*\s+(\w+)\s+(.+?)\s+"   # qtde, unid, código, resto
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"                      # preço
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*$")                    # total


def _parse_lojao(linhas):
    itens = []
    dentro = False
    for ln in linhas:
        if ln.strip().startswith("QTDE"):
            dentro = True
            continue
        if not dentro:
            continue
        if ln.strip().startswith("Itens:") or "SUBTOTAL" in ln or "TOTAL:" in ln:
            break
        m = _LOJAO_ITEM.match(ln)
        if m:
            qtd, cod, resto, preco, total = m.groups()
            # resto pode começar com uma REFERENCIA (código alfanumérico) — a descrição é o principal
            itens.append({"descricao": resto.strip(), "unidade": "UN",
                          "quantidade": _val_br(qtd), "valor": _val_br(preco),
                          "subtotal": _val_br(total), "codigo": cod})
        else:
            # linha de continuação da descrição anterior (ex.: "MAGNETICO", "COR", "S/V")
            if itens and ln.strip() and not re.search(r"\d", ln) and len(ln.strip()) <= 20:
                itens[-1]["descricao"] += " " + ln.strip()
    return itens


# CNPJ (só dígitos) -> parser
_FORNECEDORES = [
    ("17281973000815", _parse_cofermeta),
    ("28933967000145", _parse_fbm),
    ("19544638000111", _parse_ferramentech),
    ("40217808000140", _parse_lojao),
]


def _detectar_fornecedor(linhas):
    """Procura o CNPJ do FORNECEDOR no topo do PDF (primeiras ~8 linhas)."""
    topo = " ".join(linhas[:8])
    digitos_topo = _so_digitos(topo)
    for cnpj, parser in _FORNECEDORES:
        if cnpj in digitos_topo:
            return parser
    return None


# ---------------- Parser genérico (fallback) ----------------
_MONEY = re.compile(r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}|\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})")


def _parse_generico(linhas):
    """Fallback tolerante: linhas que começam com nº de item e têm 2+ valores no fim.
    Evita cabeçalho/endereço exigindo estrutura de linha de item."""
    out = []
    for ln in linhas:
        # precisa começar com um número de item e ter pelo menos 2 valores monetários
        if not re.match(r"^\s*\d+\s+", ln):
            continue
        vals = _MONEY.findall(ln)
        if len(vals) < 2:
            continue
        # descrição = do início até o primeiro valor monetário
        m = _MONEY.search(ln)
        desc = ln[:m.start()].strip()
        desc = re.sub(r"^\s*\d+\s+", "", desc)  # tira o nº do item
        if not desc or len(desc) < 2:
            continue
        # heurística de decimal: se tem vírgula como decimal usa BR, senão US
        unit = _val_br(vals[-2]) if "," in vals[-2] and vals[-2].rfind(",") > vals[-2].rfind(".") else _val_us(vals[-2])
        total = _val_br(vals[-1]) if "," in vals[-1] and vals[-1].rfind(",") > vals[-1].rfind(".") else _val_us(vals[-1])
        out.append({"descricao": desc, "unidade": None, "quantidade": None,
                    "valor": unit, "subtotal": total, "codigo": None})
    return out


def extrair_itens(file_storage):
    """Recebe um PDF e devolve a lista de itens do orçamento (item 114)."""
    linhas = _linhas(file_storage)
    parser = _detectar_fornecedor(linhas)
    if parser:
        itens = parser(linhas)
        if itens:
            return itens
    # fornecedor não reconhecido ou parser específico não achou nada
    return _parse_generico(linhas)
