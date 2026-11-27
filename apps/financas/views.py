from django.db.models import Case, CharField, F, Prefetch, Value, When
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers as drf_serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api import Conflito, DoUsuarioSomenteLeituraViewSet, DoUsuarioViewSet

from . import filtros, serializers
from .datas import parse_mes
from .models import (
    Categoria,
    ContaFinanceira,
    Ocorrencia,
    Orcamento,
    Recorrencia,
    RegraCategoria,
    Transacao,
)
from .services import casamento
from .services import transacoes as servico_transacoes
from .services.ocorrencias import sincronizar_recorrencia
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


def mes_da_query(request):
    """`?mes=AAAA-MM` → date do dia 1 (padrão: mês atual). Inválido → 400."""
    valor = request.query_params.get("mes")
    if not valor:
        return timezone.localdate().replace(day=1)
    try:
        return parse_mes(valor)
    except ValueError as erro:
        raise drf_serializers.ValidationError({"mes": str(erro)}) from erro


class RecorrenciaViewSet(DoUsuarioViewSet):
    """Contas e receitas fixas. Criar gera a ocorrência do mês atual; editar atualiza as
    previstas do mês atual em diante; desativar ou definir fim apaga as previstas futuras."""

    model = Recorrencia
    serializer_class = serializers.RecorrenciaSerializer
    filterset_class = filtros.RecorrenciaFiltro

    def perform_create(self, serializer):
        super().perform_create(serializer)
        sincronizar_recorrencia(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        sincronizar_recorrencia(serializer.instance)

    def perform_destroy(self, instance):
        if instance.ocorrencias.filter(status=Ocorrencia.Status.PAGA).exists():
            raise Conflito("A recorrência tem ocorrências pagas: desative-a em vez de apagar.")
        instance.delete()


class OcorrenciaViewSet(DoUsuarioSomenteLeituraViewSet):
    """Ocorrências do mês (`?mes=AAAA-MM`, padrão: o atual). A listagem sempre gera as
    ocorrências que faltam no mês (idempotente). O status "atrasada" é calculado."""

    model = Ocorrencia
    serializer_class = serializers.OcorrenciaSerializer
    filterset_class = filtros.OcorrenciaFiltro

    def get_queryset(self):
        hoje = timezone.localdate()
        return (
            super()
            .get_queryset()
            .select_related("recorrencia")
            .annotate(
                status_atual=Case(
                    When(
                        status=Ocorrencia.Status.PREVISTA,
                        vencimento__lt=hoje,
                        then=Value(Ocorrencia.Status.ATRASADA),
                    ),
                    default=F("status"),
                    output_field=CharField(),
                )
            )
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "hoje": timezone.localdate()}

    @extend_schema(
        parameters=[
            OpenApiParameter("mes", str, description="Mês no formato AAAA-MM (padrão: atual)")
        ]
    )
    def list(self, request, *args, **kwargs):
        mes = mes_da_query(request)
        casamento.preparar_mes(request.user, mes)
        self.mes = mes
        return super().list(request, *args, **kwargs)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.action == "list":
            queryset = queryset.filter(mes_referencia=self.mes)
        return queryset

    def _resposta(self, ocorrencia):
        return Response(self.get_serializer(self.get_queryset().get(pk=ocorrencia.pk)).data)

    @extend_schema(
        request=serializers.MarcarPagaSerializer, responses=serializers.OcorrenciaSerializer
    )
    @action(detail=True, methods=["post"], url_path="marcar-paga")
    def marcar_paga(self, request, pk=None):
        """Marca como paga (ou recebida). Opcional: `transacao` que quitou e `paga_em`."""
        ocorrencia = self.get_object()
        entrada = serializers.MarcarPagaSerializer(
            data=request.data, context={**self.get_serializer_context(), "ocorrencia": ocorrencia}
        )
        entrada.is_valid(raise_exception=True)
        casamento.marcar_paga(
            ocorrencia,
            transacao_=entrada.validated_data.get("transacao"),
            paga_em=entrada.validated_data.get("paga_em"),
        )
        return self._resposta(ocorrencia)

    @extend_schema(request=None, responses=serializers.OcorrenciaSerializer)
    @action(detail=True, methods=["post"])
    def desmarcar(self, request, pk=None):
        """Volta para prevista. Essa ocorrência deixa de ser casada automaticamente."""
        ocorrencia = self.get_object()
        casamento.desmarcar(ocorrencia)
        return self._resposta(ocorrencia)


class OrcamentoViewSet(DoUsuarioViewSet):
    model = Orcamento
    serializer_class = serializers.OrcamentoSerializer
    filterset_class = filtros.OrcamentoFiltro

    def get_queryset(self):
        return super().get_queryset().select_related("categoria")
