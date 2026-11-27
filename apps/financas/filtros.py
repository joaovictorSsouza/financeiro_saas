import re

import django_filters
from django.db.models import Q
from rest_framework.exceptions import ValidationError

from .datas import parse_mes, ultimo_dia
from .models import Categoria, ContaFinanceira, RegraCategoria, Transacao


class CategoriaFiltro(django_filters.FilterSet):
    raiz = django_filters.BooleanFilter(
        field_name="categoria_pai", lookup_expr="isnull", label="Só categorias raiz"
    )

    class Meta:
        model = Categoria
        fields = ("tipo", "ativa", "categoria_pai")


class ContaFinanceiraFiltro(django_filters.FilterSet):
    class Meta:
        model = ContaFinanceira
        fields = ("tipo", "ativa")


class RegraCategoriaFiltro(django_filters.FilterSet):
    class Meta:
        model = RegraCategoria
        fields = ("categoria", "operador")


_VALOR = re.compile(r"^\d+([.,]\d{1,2})?$")


def valor_em_centavos(texto: str) -> int | None:
    """'45' → 4500, '45,9' → 4590, '45.90' → 4590; texto não numérico → None."""
    texto = texto.strip()
    if not _VALOR.match(texto):
        return None
    reais, _, centavos = texto.replace(",", ".").partition(".")
    return int(reais) * 100 + int(centavos.ljust(2, "0") or 0)


class TransacaoFiltro(django_filters.FilterSet):
    mes = django_filters.CharFilter(method="filtrar_mes", label="Mês (AAAA-MM)")
    categoria = django_filters.UUIDFilter(
        method="filtrar_categoria", label="Categoria (inclui subcategorias)"
    )
    sem_categoria = django_filters.BooleanFilter(field_name="categoria", lookup_expr="isnull")
    busca = django_filters.CharFilter(method="filtrar_busca", label="Descrição ou valor")
    incluir_divididas = django_filters.BooleanFilter(
        method="filtrar_divididas",
        label="Incluir as originais divididas (por padrão só aparecem as partes)",
    )

    class Meta:
        model = Transacao
        fields = ("conta", "tipo", "ignorada", "origem", "transacao_pai")

    def filtrar_divididas(self, queryset, nome, valor):
        return queryset  # aplicado na listagem pela view (TransacaoViewSet.filter_queryset)

    def filtrar_mes(self, queryset, nome, valor):
        try:
            mes = parse_mes(valor)
        except ValueError as erro:
            raise ValidationError({"mes": str(erro)}) from erro
        return queryset.filter(data__gte=mes, data__lte=ultimo_dia(mes))

    def filtrar_categoria(self, queryset, nome, valor):
        return queryset.filter(Q(categoria=valor) | Q(categoria__categoria_pai=valor))

    def filtrar_busca(self, queryset, nome, valor):
        condicao = Q(descricao__icontains=valor) | Q(descricao_original__icontains=valor)
        centavos = valor_em_centavos(valor)
        if centavos is not None:
            condicao |= Q(valor_centavos=centavos)
        return queryset.filter(condicao)
