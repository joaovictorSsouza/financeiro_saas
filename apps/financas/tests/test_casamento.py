import datetime

import pytest

from apps.financas.models import Ocorrencia
from apps.financas.services.casamento import (
    casar_ocorrencias,
    desmarcar,
    marcar_paga,
    preparar_mes,
)
from apps.financas.services.transacoes import criar_transacao, excluir_transacao

from .factories import (
    ContaFinanceiraFactory,
    OcorrenciaFactory,
    RecorrenciaFactory,
    TransacaoFactory,
)

pytestmark = pytest.mark.django_db
d = datetime.date
NOV = d(2026, 11, 1)


@pytest.fixture
def conta_luz(usuario):
    """Conta de R$ 100,00 que vence em 10/11."""
    rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=10, valor_previsto_centavos=10_000)
    return OcorrenciaFactory(recorrencia=rec, mes_referencia=NOV)


def saida(usuario, valor, data, **extra):
    return TransacaoFactory(usuario=usuario, valor_centavos=valor, data=data, **extra)


@pytest.mark.parametrize(
    ("valor", "data", "casa"),
    [
        (10_000, d(2026, 11, 10), True),
        (11_000, d(2026, 11, 10), True),  # +10%
        (9_000, d(2026, 11, 10), True),  # -10%
        (11_001, d(2026, 11, 10), False),
        (8_999, d(2026, 11, 10), False),
        (10_000, d(2026, 11, 5), True),  # 5 dias antes
        (10_000, d(2026, 11, 15), True),  # 5 dias depois
        (10_000, d(2026, 11, 4), False),
        (10_000, d(2026, 11, 16), False),
    ],
)
def test_limites_de_valor_e_data(usuario, conta_luz, valor, data, casa):
    t = saida(usuario, valor, data)
    assert casar_ocorrencias(usuario, NOV) == int(casa)
    conta_luz.refresh_from_db()
    assert (conta_luz.status == "paga") is casa
    if casa:
        assert conta_luz.transacao == t
        assert conta_luz.paga_em == data


def test_conta_casa_so_com_saida_e_receita_so_com_entrada(usuario, conta_luz):
    saida(usuario, 10_000, d(2026, 11, 10), tipo="entrada")
    assert casar_ocorrencias(usuario, NOV) == 0
    salario = RecorrenciaFactory(
        usuario=usuario, tipo="receita", dia_do_mes=5, valor_previsto_centavos=500_000
    )
    oc = OcorrenciaFactory(recorrencia=salario, mes_referencia=NOV)
    saida(usuario, 500_000, d(2026, 11, 5), tipo="entrada")
    assert casar_ocorrencias(usuario, NOV) == 1
    oc.refresh_from_db()
    assert oc.status == "paga"


def test_ignora_ignoradas_partes_e_de_outro_usuario(usuario, outro_usuario, conta_luz):
    saida(usuario, 10_000, d(2026, 11, 10), ignorada=True)
    pai = saida(usuario, 20_000, d(2026, 11, 1), dividida=True)
    saida(usuario, 10_000, d(2026, 11, 10), transacao_pai=pai)
    saida(outro_usuario, 10_000, d(2026, 11, 10))
    assert casar_ocorrencias(usuario, NOV) == 0


def test_nunca_vincula_a_mesma_transacao_duas_vezes(usuario):
    rec_a = RecorrenciaFactory(usuario=usuario, dia_do_mes=10, valor_previsto_centavos=10_000)
    rec_b = RecorrenciaFactory(usuario=usuario, dia_do_mes=10, valor_previsto_centavos=10_000)
    a = OcorrenciaFactory(recorrencia=rec_a, mes_referencia=NOV)
    b = OcorrenciaFactory(recorrencia=rec_b, mes_referencia=NOV)
    saida(usuario, 10_000, d(2026, 11, 10))
    assert casar_ocorrencias(usuario, NOV) == 1
    assert casar_ocorrencias(usuario, NOV) == 0
    a.refresh_from_db()
    b.refresh_from_db()
    assert sorted([a.status, b.status]) == ["paga", "prevista"]


def test_transacao_ja_vinculada_nao_e_reusada(usuario, conta_luz):
    t = saida(usuario, 10_000, d(2026, 11, 10))
    outra_rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=10, valor_previsto_centavos=10_000)
    OcorrenciaFactory(recorrencia=outra_rec, mes_referencia=d(2026, 10, 1), transacao=t)
    assert casar_ocorrencias(usuario, NOV) == 0


def test_prefere_conta_padrao_e_valor_mais_proximo(usuario):
    conta = ContaFinanceiraFactory(usuario=usuario)
    rec = RecorrenciaFactory(
        usuario=usuario, dia_do_mes=10, valor_previsto_centavos=10_000, conta_padrao=conta
    )
    oc = OcorrenciaFactory(recorrencia=rec, mes_referencia=NOV)
    saida(usuario, 10_000, d(2026, 11, 10))
    certa = saida(usuario, 10_500, d(2026, 11, 11), conta=conta)
    casar_ocorrencias(usuario, NOV)
    oc.refresh_from_db()
    assert oc.transacao == certa


def test_desmarcar_nao_casa_de_novo_e_marcar_volta_a_casar(usuario, conta_luz):
    t = saida(usuario, 10_000, d(2026, 11, 10))
    casar_ocorrencias(usuario, NOV)
    desmarcar(Ocorrencia.objects.get(pk=conta_luz.pk))
    conta_luz.refresh_from_db()
    assert (conta_luz.status, conta_luz.transacao, conta_luz.paga_em) == ("prevista", None, None)
    assert not conta_luz.casamento_automatico
    assert casar_ocorrencias(usuario, NOV) == 0

    marcar_paga(conta_luz, transacao_=t)
    conta_luz.refresh_from_db()
    assert (conta_luz.status, conta_luz.transacao, conta_luz.paga_em) == ("paga", t, t.data)
    assert conta_luz.casamento_automatico


def test_marcar_paga_sem_transacao_usa_hoje(usuario, conta_luz):
    marcar_paga(conta_luz, paga_em=d(2026, 11, 3))
    conta_luz.refresh_from_db()
    assert (conta_luz.status, conta_luz.paga_em, conta_luz.transacao) == (
        "paga",
        d(2026, 11, 3),
        None,
    )


def test_criar_transacao_casa_automaticamente_inclusive_no_mes_vizinho(usuario):
    rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=31, valor_previsto_centavos=10_000)
    oc = OcorrenciaFactory(recorrencia=rec, mes_referencia=NOV)  # vence 30/11
    conta = ContaFinanceiraFactory(usuario=usuario)
    t = criar_transacao(
        usuario,
        conta=conta,
        data=d(2026, 12, 2),
        descricao="Luz",
        valor_centavos=10_000,
        tipo="saida",
    )
    oc.refresh_from_db()
    assert oc.transacao == t

    excluir_transacao(t)
    oc.refresh_from_db()
    assert (oc.status, oc.transacao) == ("prevista", None)


def test_preparar_mes_gera_sempre_e_casa_so_na_primeira_vez(usuario):
    RecorrenciaFactory(usuario=usuario, dia_do_mes=10, valor_previsto_centavos=10_000)
    saida(usuario, 10_000, d(2026, 11, 10))
    preparar_mes(usuario, NOV)
    assert Ocorrencia.objects.get().status == "paga"

    nova = RecorrenciaFactory(usuario=usuario, dia_do_mes=12, valor_previsto_centavos=5_000)
    saida(usuario, 5_000, d(2026, 11, 12))
    preparar_mes(usuario, NOV)
    oc = Ocorrencia.objects.get(recorrencia=nova)
    assert oc.status == "prevista"  # gerou, mas o mês já tinha ocorrências: não casa aqui
