"""Utilitários: normalização de telefone BR e cálculo de dias úteis."""
import re
from datetime import date, timedelta


def normalizar_telefone_br(raw):
    """Recebe um telefone em qualquer formato e devolve (digits_e164, exibicao).

    Entende DDD e o dígito 9 do celular. Ex.: "11 98888-7777" -> ("5511988887777", "+55 (11) 98888-7777").
    Devolve (None, None) se não conseguir interpretar.
    """
    if not raw:
        return None, None
    d = re.sub(r"\D", "", raw)
    if not d:
        return None, None

    # Remove zeros de operadora/DDD na frente (ex.: 011)
    if d.startswith("0"):
        d = d.lstrip("0")

    # Já com DDI 55
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]

    # Agora d deve ser DDD (2) + número (8 ou 9)
    if len(d) == 11:            # DDD + 9 dígitos (celular já com 9)
        nacional = d
    elif len(d) == 10:          # DDD + 8 dígitos -> insere o 9 (celular)
        nacional = d[:2] + "9" + d[2:]
    elif len(d) in (8, 9):      # sem DDD: não dá para garantir; mantém sem DDD
        nacional = d
    else:
        nacional = d            # melhor esforço

    e164 = "55" + nacional
    if len(nacional) == 11:
        exib = f"+55 ({nacional[:2]}) {nacional[2:7]}-{nacional[7:]}"
    elif len(nacional) == 10:
        exib = f"+55 ({nacional[:2]}) {nacional[2:6]}-{nacional[6:]}"
    else:
        exib = "+55 " + nacional
    return e164, exib


def somar_dias_uteis(n, inicio=None):
    """Soma n dias úteis (pula sábado e domingo)."""
    d = inicio or date.today()
    add = 0
    while add < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # 0-4 = seg a sex
            add += 1
    return d
