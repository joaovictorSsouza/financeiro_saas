from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.financas.datas import parse_mes

from . import serializers, services

MAX_MESES_EVOLUCAO = 24


def _mes(request, parametro="mes"):
    valor = request.query_params.get(parametro)
    if not valor:
        return timezone.localdate().replace(day=1)
    try:
        return parse_mes(valor)
    except ValueError as erro:
        raise drf_serializers.ValidationError({parametro: str(erro)}) from erro


class ResumoView(APIView):
    """Resumo do mês. Valores em centavos. `saldo_previsto_fim_mes` é nulo para meses
    passados; `proximas_contas` é sempre relativo a hoje (próximos 7 dias)."""

    @extend_schema(
        parameters=[OpenApiParameter("mes", str, description="AAAA-MM (padrão: mês atual)")],
        responses=serializers.ResumoSerializer,
        tags=["dashboard"],
    )
    def get(self, request):
        dados = services.resumo(request.user, _mes(request))
        return Response(serializers.ResumoSerializer(dados).data)


class EvolucaoView(APIView):
    """Receitas e despesas dos últimos N meses (do mais antigo ao mais recente)."""

    @extend_schema(
        parameters=[
            OpenApiParameter("meses", int, description=f"1 a {MAX_MESES_EVOLUCAO} (padrão: 6)"),
            OpenApiParameter("ate", str, description="Último mês, AAAA-MM (padrão: atual)"),
        ],
        responses=serializers.EvolucaoMesSerializer(many=True),
        tags=["dashboard"],
    )
    def get(self, request):
        try:
            meses = int(request.query_params.get("meses", 6))
        except ValueError:
            meses = 0
        if not 1 <= meses <= MAX_MESES_EVOLUCAO:
            raise drf_serializers.ValidationError(
                {"meses": f"Informe um número de 1 a {MAX_MESES_EVOLUCAO}."}
            )
        dados = services.evolucao(request.user, _mes(request, "ate"), meses)
        return Response(serializers.EvolucaoMesSerializer(dados, many=True).data)
