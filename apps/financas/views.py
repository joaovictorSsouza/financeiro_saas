from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import DoUsuarioViewSet

from . import filtros, serializers
from .models import Categoria, ContaFinanceira, RegraCategoria
from .services.regras import aplicar_regras_em_lote


class CategoriaViewSet(DoUsuarioViewSet):
    model = Categoria
    serializer_class = serializers.CategoriaSerializer
    filterset_class = filtros.CategoriaFiltro
    mensagem_protegido = "Categoria usada em recorrências: troque a categoria ou desative-a."

    def get_queryset(self):
        return super().get_queryset().select_related("categoria_pai")


class ContaFinanceiraViewSet(DoUsuarioViewSet):
    model = ContaFinanceira
    serializer_class = serializers.ContaFinanceiraSerializer
    filterset_class = filtros.ContaFinanceiraFiltro
    mensagem_protegido = "A conta tem transações: desative-a em vez de apagar."


class RegraCategoriaViewSet(DoUsuarioViewSet):
    model = RegraCategoria
    serializer_class = serializers.RegraCategoriaSerializer
    filterset_class = filtros.RegraCategoriaFiltro

    def get_queryset(self):
        return super().get_queryset().select_related("categoria")

    @extend_schema(request=None, responses=serializers.ResultadoAplicarRegrasSerializer)
    @action(detail=False, methods=["post"])
    def aplicar(self, request):
        """Reaplica as regras em todas as transações sem categoria manual."""
        return Response({"alteradas": aplicar_regras_em_lote(request.user)})
