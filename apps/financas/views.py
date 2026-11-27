from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import serializers as drf_serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import Conflito, DoUsuarioViewSet

from . import filtros, serializers
from .models import Categoria, ContaFinanceira, RegraCategoria, Transacao
from .services import transacoes as servico_transacoes
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


class TransacaoViewSet(DoUsuarioViewSet):
    """Transações. Por padrão a lista mostra as partes de uma divisão no lugar da
    original (use `?incluir_divididas=true` para ver as originais também)."""

    model = Transacao
    serializer_class = serializers.TransacaoSerializer
    filterset_class = filtros.TransacaoFiltro

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("categoria")
            .prefetch_related(Prefetch("partes", queryset=Transacao.objects.order_by("criado_em")))
        )

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        # Só na listagem: o detalhe da original dividida continua acessível.
        incluir = self.request.query_params.get("incluir_divididas", "").lower()
        if self.action == "list" and incluir not in ("true", "1"):
            queryset = queryset.filter(dividida=False)
        return queryset

    def perform_destroy(self, instance):
        if instance.transacao_pai_id:
            raise Conflito("Para apagar uma parte, desfaça a divisão da transação original.")
        servico_transacoes.excluir_transacao(instance)

    @extend_schema(
        request=serializers.DividirSerializer,
        responses={200: serializers.TransacaoSerializer},
        methods=["POST"],
    )
    @extend_schema(
        request=None, responses={200: serializers.TransacaoSerializer}, methods=["DELETE"]
    )
    @action(detail=True, methods=["post", "delete"])
    def dividir(self, request, pk=None):
        """POST divide a transação em partes com categorias diferentes (a soma deve dar o
        valor da original). DELETE desfaz a divisão."""
        transacao = self.get_object()
        if request.method == "DELETE":
            servico_transacoes.desfazer_divisao(transacao)
        else:
            entrada = serializers.DividirSerializer(
                data=request.data, context={**self.get_serializer_context(), "transacao": transacao}
            )
            entrada.is_valid(raise_exception=True)
            try:
                servico_transacoes.dividir_transacao(transacao, entrada.validated_data["itens"])
            except servico_transacoes.DivisaoInvalida as erro:
                raise drf_serializers.ValidationError({"itens": str(erro)}) from erro
        return Response(self.get_serializer(self.get_queryset().get(pk=transacao.pk)).data)
