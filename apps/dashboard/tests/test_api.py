import datetime

import pytest

from apps.financas.tests.factories import (
    CategoriaFactory,
    ContaFinanceiraFactory,
    OrcamentoFactory,
    RecorrenciaFactory,
    TransacaoFactory,
)

pytestmark = pytest.mark.django_db
RESUMO = "/api/v1/dashboard/resumo/"
EVOLUCAO = "/api/v1/dashboard/evolucao/"


@pytest.mark.parametrize("url", [RESUMO, EVOLUCAO])
def test_exige_autenticacao(api_client, url):
    assert api_client.get(url).status_code == 401


def test_resumo_formato(cliente_autenticado, usuario, hoje):
    conta = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=10_000)
    TransacaoFactory(usuario=usuario, conta=conta, data=hoje, valor_centavos=2_500)
    resposta = cliente_autenticado.get(RESUMO, {"mes": "2026-11"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {
        "mes",
        "saldo_atual",
        "receitas_mes",
        "despesas_mes",
        "comparacao_mes_anterior",
        "contas_a_pagar",
        "receitas_a_receber",
        "fatura_cartao",
        "saldo_previsto_fim_mes",
        "gastos_por_categoria",
        "proximas_contas",
        "orcamentos",
        "maiores_gastos",
        "alertas",
    }
    assert (corpo["mes"], corpo["saldo_atual"], corpo["despesas_mes"]) == (
        "2026-11-01",
        10_000,
        2_500,
    )


def test_resumo_sem_mes_usa_o_atual(cliente_autenticado, hoje):
    assert cliente_autenticado.get(RESUMO).json()["mes"] == "2026-11-01"


@pytest.mark.parametrize("mes", ["2026-13", "nov", "2026-1"])
def test_resumo_mes_invalido(cliente_autenticado, mes):
    assert cliente_autenticado.get(RESUMO, {"mes": mes}).status_code == 400


def test_evolucao(cliente_autenticado, usuario, hoje):
    TransacaoFactory(usuario=usuario, data=datetime.date(2026, 10, 3), valor_centavos=700)
    corpo = cliente_autenticado.get(EVOLUCAO, {"meses": 3}).json()
    assert [m["mes"] for m in corpo] == ["2026-09-01", "2026-10-01", "2026-11-01"]
    assert corpo[1]["despesas"] == 700
    assert len(cliente_autenticado.get(EVOLUCAO).json()) == 6
    ate = cliente_autenticado.get(EVOLUCAO, {"meses": 1, "ate": "2026-10"}).json()
    assert ate == [{"mes": "2026-10-01", "receitas": 0, "despesas": 700, "resultado": -700}]


@pytest.mark.parametrize("params", [{"meses": 0}, {"meses": 25}, {"meses": "x"}, {"ate": "x"}])
def test_evolucao_parametros_invalidos(cliente_autenticado, params):
    assert cliente_autenticado.get(EVOLUCAO, params).status_code == 400


def test_dashboard_nao_mistura_usuarios(cliente_autenticado, usuario, outro_usuario, hoje):
    conta = ContaFinanceiraFactory(usuario=outro_usuario, saldo_centavos=1_000_000)
    categoria = CategoriaFactory(usuario=outro_usuario)
    TransacaoFactory(
        usuario=outro_usuario, conta=conta, data=hoje, valor_centavos=5_000, categoria=categoria
    )
    TransacaoFactory(
        usuario=outro_usuario, conta=conta, data=hoje, tipo="entrada", valor_centavos=9_000
    )
    TransacaoFactory(
        usuario=outro_usuario, conta=conta, data=hoje, descricao="Fatura", valor_centavos=1
    )
    OrcamentoFactory(usuario=outro_usuario, categoria=categoria)
    RecorrenciaFactory(usuario=outro_usuario, dia_do_mes=22)

    resumo = cliente_autenticado.get(RESUMO, {"mes": "2026-11"}).json()
    for campo in (
        "saldo_atual",
        "receitas_mes",
        "despesas_mes",
        "contas_a_pagar",
        "receitas_a_receber",
        "fatura_cartao",
    ):
        assert resumo[campo] == 0, campo
    listas = ("gastos_por_categoria", "proximas_contas", "orcamentos", "maiores_gastos", "alertas")
    for lista in listas:
        assert resumo[lista] == [], lista
    evolucao = cliente_autenticado.get(EVOLUCAO).json()
    assert all(m["receitas"] == m["despesas"] == 0 for m in evolucao)
    # O resumo do usuário não gera ocorrências para o outro.
    assert not outro_usuario.ocorrencias.exists()
