import datetime

import factory

from apps.accounts.tests.factories import UsuarioFactory
from apps.financas.models import Categoria, ContaFinanceira, RegraCategoria, Transacao


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


class TransacaoFactory(factory.django.DjangoModelFactory):
    """Grava direto no banco (não passa pelo serviço, então não mexe no saldo)."""

    class Meta:
        model = Transacao

    usuario = factory.SubFactory(UsuarioFactory)
    conta = factory.SubFactory(ContaFinanceiraFactory, usuario=factory.SelfAttribute("..usuario"))
    data = factory.LazyFunction(datetime.date.today)
    descricao = factory.Sequence(lambda n: f"Compra {n}")
    valor_centavos = 1000
    tipo = Transacao.Tipo.SAIDA


class RegraCategoriaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RegraCategoria

    usuario = factory.SubFactory(UsuarioFactory)
    valor = "mercado"
    operador = RegraCategoria.Operador.CONTEM
    categoria = factory.SubFactory(CategoriaFactory, usuario=factory.SelfAttribute("..usuario"))
    prioridade = 0
