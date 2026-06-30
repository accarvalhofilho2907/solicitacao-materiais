"""Leitor de PDF de orçamento do fornecedor.

Estratégia:
1) Lê o texto com pdfplumber (preserva o layout em linhas).
2) Reconhece o padrão estruturado "código · descrição · unidade · qtde · preço · subtotal"
   (ex.: orçamentos REALSYS / DELTA). Quando reconhece, usa só esses itens.
3) Para layouts desconhecidos, cai num método heurístico (último valor da linha).

Cada item devolvido: {descricao, valor (preço unitário), quantidade, unidade, subtotal, codigo}.
"""
import re

# Unidades comuns em orçamentos (token isolado antes dos números)
UNIDADES = r"(?:UN|JG|KIT|CT|PC|PCS|PCT|MT|ML|M|CX|PA|PAR|KG|LT|L|RL|RO|BD|GL|FR|SC|CJ|CD|TB)"

ITEM_RE = re.compile(
    r"^\s*(\d{6,})\s+(.+?)\s+(" + UNIDADES + r")\s+"
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"      # quantidade
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+"      # preço unitário
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*$"     # subtotal
)

_MONEY = re.compile(
    r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}|\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})"
)


def _parse_valor(s):
    if s is None:
        return None
    s = s.strip().replace("R$", "").strip()
    if "," in s and "." in s:
        # BR: 1.234,56  |  US: 1,234.56
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
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
            linhas += [l.strip() for l in texto.split("\n") if l.strip()]
    return linhas


def extrair_itens(file_storage):
    """Recebe um PDF e devolve a lista de itens do orçamento."""
    linhas = _linhas(file_storage)

    # 1) Padrão estruturado
    estruturados = []
    for ln in linhas:
        m = ITEM_RE.match(ln)
        if m:
            cod, desc, und, qtd, preco, sub = m.groups()
            estruturados.append({
                "descricao": desc.strip(),
                "unidade": und,
                "quantidade": _parse_valor(qtd),
                "valor": _parse_valor(preco),     # preço unitário
                "subtotal": _parse_valor(sub),
                "codigo": cod,
            })
    if estruturados:
        return estruturados

    # 2) Fallback heurístico (layouts desconhecidos): último valor da linha
    out = []
    for ln in linhas:
        matches = list(_MONEY.finditer(ln))
        if not matches:
            continue
        ultimo = matches[-1]
        valor = _parse_valor(ultimo.group(1))
        descricao = ln[: ultimo.start()].strip(" .:-\t")
        if valor is not None and descricao and len(descricao) > 1 and not descricao[0].isdigit():
            out.append({
                "descricao": descricao, "unidade": None, "quantidade": None,
                "valor": valor, "subtotal": None, "codigo": None,
            })
    return out
