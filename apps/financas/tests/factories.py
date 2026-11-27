import factory

from apps.accounts.tests.factories import UsuarioFactory
from apps.financas.models import Categoria, ContaFinanceira


class CategoriaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Categoria

    usuario = factory.SubFactory(UsuarioFactory)
    nome = factory.Sequence(lambda n: f"Categoria {n}")
    icone = "tag"
    cor = "#336699"
    tipo = Categoria.Tipo.GASTO


class ContaFinanceiraFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContaFinanceira

    usuario = factory.SubFactory(UsuarioFactory)
    nome = factory.Sequence(lambda n: f"Conta {n}")
    tipo = ContaFinanceira.Tipo.CORRENTE
    instituicao = "Banco Exemplo"
    saldo_centavos = 0
