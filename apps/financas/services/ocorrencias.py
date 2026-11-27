"""Geração das ocorrências mensais a partir das recorrências."""

import datetime

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.financas.datas import primeiro_dia, ultimo_dia, vencimento_no_mes
from apps.financas.models import Ocorrencia, Recorrencia


def _nova_ocorrencia(recorrencia: Recorrencia, mes: datetime.date) -> Ocorrencia:
    return Ocorrencia(
        usuario_id=recorrencia.usuario_id,
        recorrencia=recorrencia,
        mes_referencia=mes,
        vencimento=vencimento_no_mes(mes, recorrencia.dia_do_mes),
        valor_centavos=recorrencia.valor_previsto_centavos,
    )


def gerar_ocorrencias(usuario, mes: datetime.date, recorrencias=None) -> int:
    """Cria as ocorrências do mês que ainda não existem. Idempotente.

    Nunca altera ocorrências existentes (a unicidade por recorrência+mês descarta as
    repetidas). Retorna quantas foram criadas.
    """
    mes = primeiro_dia(mes)
    if recorrencias is None:
        recorrencias = Recorrencia.objects.filter(
            usuario=usuario, ativa=True, inicio__lte=ultimo_dia(mes)
        ).filter(Q(fim__isnull=True) | Q(fim__gte=mes))
    novas = [_nova_ocorrencia(r, mes) for r in recorrencias if r.ativa and r.vale_para(mes)]
    if not novas:
        return 0
    existentes = Ocorrencia.objects.filter(
        recorrencia__in=[o.recorrencia_id for o in novas], mes_referencia=mes
    ).count()
    Ocorrencia.objects.bulk_create(novas, ignore_conflicts=True)
    return len(novas) - existentes


@transaction.atomic
def sincronizar_recorrencia(recorrencia: Recorrencia, hoje: datetime.date | None = None) -> None:
    """Aplica uma recorrência criada ou editada às ocorrências. Pagas nunca mudam.

    - inativa: apaga as previstas que ainda não venceram;
    - com fim: apaga as previstas que vencem depois do fim;
    - previstas do mês atual em diante: recebem o valor e o vencimento novos (ou são
      apagadas se a recorrência não vale mais para aquele mês, ex.: menos parcelas);
    - gera a ocorrência do mês atual, se couber.
    """
    hoje = hoje or timezone.localdate()
    previstas = recorrencia.ocorrencias.filter(status=Ocorrencia.Status.PREVISTA)
    if not recorrencia.ativa:
        previstas.filter(vencimento__gte=hoje).delete()
        return
    if recorrencia.fim:
        previstas.filter(vencimento__gt=recorrencia.fim).delete()

    for ocorrencia in previstas.filter(mes_referencia__gte=primeiro_dia(hoje)):
        if not recorrencia.vale_para(ocorrencia.mes_referencia):
            ocorrencia.delete()
            continue
        ocorrencia.valor_centavos = recorrencia.valor_previsto_centavos
        ocorrencia.vencimento = vencimento_no_mes(ocorrencia.mes_referencia, recorrencia.dia_do_mes)
        ocorrencia.save(update_fields=["valor_centavos", "vencimento", "atualizado_em"])

    gerar_ocorrencias(recorrencia.usuario_id, hoje, recorrencias=[recorrencia])
