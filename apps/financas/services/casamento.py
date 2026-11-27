"""Casamento de ocorrências previstas com transações (pagamento detectado)."""

import datetime

from django.db import transaction
from django.utils import timezone

from apps.financas.datas import primeiro_dia
from apps.financas.models import Ocorrencia, Recorrencia, Transacao

from .ocorrencias import gerar_ocorrencias

TOLERANCIA_VALOR = 0.10  # ±10% do valor previsto
TOLERANCIA_DIAS = 5  # até 5 dias antes ou depois do vencimento


def _tipo_transacao(ocorrencia: Ocorrencia) -> str:
    if ocorrencia.recorrencia.tipo == Recorrencia.Tipo.CONTA:
        return Transacao.Tipo.SAIDA
    return Transacao.Tipo.ENTRADA


def _candidata(ocorrencia: Ocorrencia, t: Transacao) -> bool:
    previsto = ocorrencia.valor_centavos
    return (
        t.tipo == _tipo_transacao(ocorrencia)
        and abs(t.valor_centavos - previsto) <= previsto * TOLERANCIA_VALOR
        and abs((t.data - ocorrencia.vencimento).days) <= TOLERANCIA_DIAS
    )


def _pontuacao(ocorrencia: Ocorrencia, t: Transacao):
    """Menor é melhor: mesma conta padrão, menor diferença de valor, menor de dias."""
    conta_padrao = ocorrencia.recorrencia.conta_padrao_id
    return (
        0 if conta_padrao and t.conta_id == conta_padrao else 1,
        abs(t.valor_centavos - ocorrencia.valor_centavos),
        abs((t.data - ocorrencia.vencimento).days),
        t.data,
    )


@transaction.atomic
def casar_ocorrencias(usuario, mes: datetime.date) -> int:
    """Marca como pagas as ocorrências previstas do mês que têm transação compatível.

    Considera só transações "de extrato" (não partes de divisão), não ignoradas e ainda
    não vinculadas: uma transação nunca quita duas ocorrências (OneToOne no banco).
    Ocorrências desmarcadas pelo usuário (`casamento_automatico=False`) ficam de fora.
    Retorna quantas foram casadas.
    """
    ocorrencias = list(
        Ocorrencia.objects.select_for_update(of=("self",))
        .filter(
            usuario=usuario,
            mes_referencia=primeiro_dia(mes),
            status=Ocorrencia.Status.PREVISTA,
            casamento_automatico=True,
        )
        .select_related("recorrencia")
        .order_by("vencimento", "criado_em")
    )
    if not ocorrencias:
        return 0

    folga = datetime.timedelta(days=TOLERANCIA_DIAS)
    candidatas = list(
        Transacao.objects.select_for_update(of=("self",)).filter(
            usuario=usuario,
            transacao_pai__isnull=True,
            ignorada=False,
            ocorrencia__isnull=True,
            data__gte=min(o.vencimento for o in ocorrencias) - folga,
            data__lte=max(o.vencimento for o in ocorrencias) + folga,
        )
    )

    casadas = 0
    for ocorrencia in ocorrencias:
        compativeis = [t for t in candidatas if _candidata(ocorrencia, t)]
        if not compativeis:
            continue
        escolhida = min(compativeis, key=lambda t: _pontuacao(ocorrencia, t))
        candidatas.remove(escolhida)
        _quitar(ocorrencia, escolhida, escolhida.data)
        casadas += 1
    return casadas


def _quitar(ocorrencia: Ocorrencia, transacao_: Transacao | None, paga_em: datetime.date):
    ocorrencia.status = Ocorrencia.Status.PAGA
    ocorrencia.transacao = transacao_
    ocorrencia.paga_em = paga_em
    ocorrencia.casamento_automatico = True
    ocorrencia.save(
        update_fields=["status", "transacao", "paga_em", "casamento_automatico", "atualizado_em"]
    )


@transaction.atomic
def marcar_paga(
    ocorrencia: Ocorrencia,
    transacao_: Transacao | None = None,
    paga_em: datetime.date | None = None,
) -> Ocorrencia:
    """Marca manualmente como paga, opcionalmente vinculando uma transação."""
    if paga_em is None:
        paga_em = transacao_.data if transacao_ else timezone.localdate()
    _quitar(ocorrencia, transacao_, paga_em)
    casar_ocorrencias(ocorrencia.usuario_id, ocorrencia.mes_referencia)
    return ocorrencia


@transaction.atomic
def desmarcar(ocorrencia: Ocorrencia) -> Ocorrencia:
    """Volta para prevista e desliga o casamento automático desta ocorrência, para que a
    mesma transação não seja vinculada de novo sozinha."""
    ocorrencia.status = Ocorrencia.Status.PREVISTA
    ocorrencia.transacao = None
    ocorrencia.paga_em = None
    ocorrencia.casamento_automatico = False
    ocorrencia.save(
        update_fields=["status", "transacao", "paga_em", "casamento_automatico", "atualizado_em"]
    )
    casar_ocorrencias(ocorrencia.usuario_id, ocorrencia.mes_referencia)
    return ocorrencia


def casar_perto_de(usuario, data: datetime.date) -> int:
    """Casa os meses que podem ter vencimento a até 5 dias da data (o próprio e vizinhos)."""
    folga = datetime.timedelta(days=TOLERANCIA_DIAS)
    meses = {primeiro_dia(data - folga), primeiro_dia(data), primeiro_dia(data + folga)}
    return sum(casar_ocorrencias(usuario, m) for m in sorted(meses))


def preparar_mes(usuario, mes: datetime.date) -> None:
    """Chamado ao consultar um mês: gera sempre (idempotente) e, se o mês ainda não tinha
    ocorrências, roda o casamento."""
    mes = primeiro_dia(mes)
    tinha = Ocorrencia.objects.filter(usuario=usuario, mes_referencia=mes).exists()
    gerar_ocorrencias(usuario, mes)
    if not tinha:
        casar_ocorrencias(usuario, mes)
