import django_filters

from .models import Categoria, ContaFinanceira, RegraCategoria


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
