import datetime

import factory

from apps.accounts.tests.factories import UsuarioFactory
from apps.financas.datas import vencimento_no_mes
from apps.financas.models import (
    Categoria,
    ContaFinanceira,
    Ocorrencia,
    Orcamento,
    Recorrencia,
    RegraCategoria,
    Transacao,
)


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


class RecorrenciaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Recorrencia

    usuario = factory.SubFactory(UsuarioFactory)
    tipo = Recorrencia.Tipo.CONTA
    nome = factory.Sequence(lambda n: f"Conta fixa {n}")
    valor_previsto_centavos = 10_000
    dia_do_mes = 10
    categoria = factory.SubFactory(CategoriaFactory, usuario=factory.SelfAttribute("..usuario"))
    inicio = datetime.date(2026, 1, 1)


class OcorrenciaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ocorrencia

    recorrencia = factory.SubFactory(RecorrenciaFactory)
    usuario = factory.SelfAttribute("recorrencia.usuario")
    mes_referencia = datetime.date(2026, 11, 1)
    vencimento = factory.LazyAttribute(
        lambda o: vencimento_no_mes(o.mes_referencia, o.recorrencia.dia_do_mes)
    )
    valor_centavos = factory.SelfAttribute("recorrencia.valor_previsto_centavos")


class OrcamentoFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Orcamento

    usuario = factory.SubFactory(UsuarioFactory)
    categoria = factory.SubFactory(CategoriaFactory, usuario=factory.SelfAttribute("..usuario"))
    mes_referencia = datetime.date(2026, 11, 1)
    limite_centavos = 50_000
