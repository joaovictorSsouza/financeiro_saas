"""Utilitários de mês de referência (sempre o dia 1) e vencimentos."""

import calendar
import datetime
import re

_MES = re.compile(r"^(\d{4})-(\d{2})$")


def primeiro_dia(data: datetime.date) -> datetime.date:
    return data.replace(day=1)


def ultimo_dia(data: datetime.date) -> datetime.date:
    return data.replace(day=calendar.monthrange(data.year, data.month)[1])


def somar_meses(data: datetime.date, meses: int) -> datetime.date:
    """Soma meses a um mês de referência (retorna sempre o dia 1)."""
    total = data.year * 12 + (data.month - 1) + meses
    return datetime.date(total // 12, total % 12 + 1, 1)


def meses_entre(inicio: datetime.date, fim: datetime.date) -> int:
    return (fim.year - inicio.year) * 12 + (fim.month - inicio.month)


def vencimento_no_mes(mes: datetime.date, dia: int) -> datetime.date:
    """Dia `dia` do mês; em meses mais curtos, o último dia (31 → 30/04, 28 ou 29/02)."""
    return mes.replace(day=min(dia, calendar.monthrange(mes.year, mes.month)[1]))


def parse_mes(valor: str) -> datetime.date:
    """'AAAA-MM' → date no dia 1. Levanta ValueError se inválido."""
    casamento = _MES.match(valor or "")
    if not casamento:
        raise ValueError("Use o formato AAAA-MM.")
    return datetime.date(int(casamento[1]), int(casamento[2]), 1)


def ultimos_meses(ate: datetime.date, quantidade: int) -> list[datetime.date]:
    """Os `quantidade` meses terminando em `ate`, do mais antigo ao mais recente."""
    return [somar_meses(primeiro_dia(ate), -i) for i in range(quantidade - 1, -1, -1)]
