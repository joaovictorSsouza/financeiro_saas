import datetime

import pytest

from apps.dashboard import services
from apps.financas.tests.factories import (
    CategoriaFactory,
    ContaFinanceiraFactory,
    OcorrenciaFactory,
    OrcamentoFactory,
    RecorrenciaFactory,
    TransacaoFactory,
)

pytestmark = pytest.mark.django_db
d = datetime.date
NOV = d(2026, 11, 1)
HOJE = d(2026, 11, 20)


@pytest.fixture
def cenario(usuario):
    """Corrente com R$ 1.000, poupança R$ 500, cartão (fora do saldo) e uma conta inativa."""
    c = type("Cenario", (), {})()
    c.corrente = ContaFinanceiraFactory(usuario=usuario, tipo="corrente", saldo_centavos=100_000)
    ContaFinanceiraFactory(usuario=usuario, tipo="poupanca", saldo_centavos=50_000)
    c.cartao = ContaFinanceiraFactory(
        usuario=usuario, tipo="cartao_credito", saldo_centavos=-30_000
    )
    ContaFinanceiraFactory(usuario=usuario, saldo_centavos=999_999, ativa=False)
    c.alimentacao = CategoriaFactory(usuario=usuario, nome="Alimentação")
    c.mercado = CategoriaFactory(usuario=usuario, nome="Mercado", categoria_pai=c.alimentacao)
    c.lazer = CategoriaFactory(usuario=usuario, nome="Lazer")
    c.salario = CategoriaFactory(usuario=usuario, nome="Salário", tipo="receita")
    return c


def t(usuario, conta, valor, data, tipo="saida", **extra):
    return TransacaoFactory(
        usuario=usuario, conta=conta, valor_centavos=valor, data=data, tipo=tipo, **extra
    )


def test_saldo_atual_exclui_cartao_e_inativas(usuario, cenario):
    assert services.resumo(usuario, NOV, hoje=HOJE)["saldo_atual"] == 150_000


def test_receitas_despesas_e_estornos(usuario, cenario):
    c = cenario
    t(usuario, c.corrente, 500_000, d(2026, 11, 5), "entrada", categoria=c.salario)
    t(usuario, c.corrente, 1_000, d(2026, 11, 6), "entrada")  # entrada sem categoria = receita
    t(usuario, c.corrente, 20_000, d(2026, 11, 7), categoria=c.mercado)
    t(usuario, c.cartao, 10_000, d(2026, 11, 8), categoria=c.lazer)
    t(usuario, c.cartao, 4_000, d(2026, 11, 9), "entrada", categoria=c.lazer)  # estorno
    t(usuario, c.corrente, 99_999, d(2026, 11, 10), ignorada=True)
    t(usuario, c.corrente, 77_777, d(2026, 12, 1))  # outro mês

    r = services.resumo(usuario, NOV, hoje=HOJE)
    assert r["receitas_mes"] == 501_000  # estorno não entra em receitas
    assert r["despesas_mes"] == 20_000 + 10_000 - 4_000
    assert r["fatura_cartao"] == 10_000  # por ora: soma das saídas do cartão


def test_gastos_por_categoria_agrupa_na_pai_e_abate_estorno(usuario, cenario):
    c = cenario
    t(usuario, c.corrente, 6_000, d(2026, 11, 1), categoria=c.mercado)
    t(usuario, c.corrente, 2_000, d(2026, 11, 2), categoria=c.alimentacao)
    t(usuario, c.corrente, 3_000, d(2026, 11, 3), categoria=c.lazer)
    t(usuario, c.corrente, 1_000, d(2026, 11, 4), "entrada", categoria=c.lazer)
    t(usuario, c.corrente, 2_000, d(2026, 11, 5))  # sem categoria

    itens = services.resumo(usuario, NOV, hoje=HOJE)["gastos_por_categoria"]
    resumido = [(i["nome"], i["total_centavos"], i["percentual"]) for i in itens]
    assert resumido == [
        ("Alimentação", 8_000, 66.7),
        ("Lazer", 2_000, 16.7),
        ("Sem categoria", 2_000, 16.7),
    ]


def test_divisao_conta_as_partes_e_nao_a_original(usuario, cenario):
    c = cenario
    original = t(usuario, c.corrente, 10_000, d(2026, 11, 3), dividida=True)
    t(usuario, c.corrente, 7_000, d(2026, 11, 3), categoria=c.mercado, transacao_pai=original)
    t(usuario, c.corrente, 3_000, d(2026, 11, 3), categoria=c.lazer, transacao_pai=original)
    r = services.resumo(usuario, NOV, hoje=HOJE)
    assert r["despesas_mes"] == 10_000
    assert {i["nome"]: i["total_centavos"] for i in r["gastos_por_categoria"]} == {
        "Alimentação": 7_000,
        "Lazer": 3_000,
    }
    assert [g["valor_centavos"] for g in r["maiores_gastos"]] == [7_000, 3_000]


def test_comparacao_com_mes_anterior(usuario, cenario):
    c = cenario
    t(usuario, c.corrente, 10_000, d(2026, 10, 31))
    t(usuario, c.corrente, 15_000, d(2026, 11, 1))
    t(usuario, c.corrente, 50_000, d(2026, 11, 5), "entrada")
    comp = services.resumo(usuario, NOV, hoje=HOJE)["comparacao_mes_anterior"]
    assert comp["despesas"] == {"anterior": 10_000, "diferenca": 5_000, "percentual": 50.0}
    assert comp["receitas"] == {"anterior": 0, "diferenca": 50_000, "percentual": None}


def test_contas_a_pagar_receber_e_saldo_previsto(usuario, cenario):
    c = cenario
    aluguel = RecorrenciaFactory(usuario=usuario, valor_previsto_centavos=40_000, dia_do_mes=5)
    luz = RecorrenciaFactory(usuario=usuario, valor_previsto_centavos=10_000, dia_do_mes=25)
    salario = RecorrenciaFactory(
        usuario=usuario, tipo="receita", categoria=c.salario, valor_previsto_centavos=300_000
    )
    OcorrenciaFactory(recorrencia=aluguel, mes_referencia=NOV, status="paga")
    OcorrenciaFactory(recorrencia=luz, mes_referencia=NOV)
    OcorrenciaFactory(recorrencia=salario, mes_referencia=NOV)
    t(usuario, c.cartao, 20_000, d(2026, 11, 2))

    r = services.resumo(usuario, NOV, hoje=HOJE)
    assert r["contas_a_pagar"] == 10_000
    assert r["receitas_a_receber"] == 300_000
    assert r["saldo_previsto_fim_mes"] == 150_000 + 300_000 - 10_000 - 20_000

    assert services.resumo(usuario, d(2026, 10, 1), hoje=HOJE)["saldo_previsto_fim_mes"] is None


def test_resumo_gera_ocorrencias_do_mes(usuario, cenario):
    RecorrenciaFactory(usuario=usuario, valor_previsto_centavos=10_000, dia_do_mes=28)
    assert services.resumo(usuario, NOV, hoje=HOJE)["contas_a_pagar"] == 10_000


def test_proximas_contas_atravessa_o_fim_do_mes(usuario):
    hoje = d(2026, 11, 27)
    RecorrenciaFactory(usuario=usuario, nome="Venceu", dia_do_mes=26)
    RecorrenciaFactory(usuario=usuario, nome="Fim do mês", dia_do_mes=31)  # 30/11
    RecorrenciaFactory(usuario=usuario, nome="Dezembro", dia_do_mes=3)
    RecorrenciaFactory(usuario=usuario, nome="Longe", dia_do_mes=15)
    receita = CategoriaFactory(usuario=usuario, tipo="receita")
    RecorrenciaFactory(usuario=usuario, tipo="receita", categoria=receita, dia_do_mes=28)

    proximas = services.resumo(usuario, NOV, hoje=hoje)["proximas_contas"]
    assert [(p["nome"], p["vencimento"]) for p in proximas] == [
        ("Fim do mês", d(2026, 11, 30)),
        ("Dezembro", d(2026, 12, 3)),
    ]


def test_proximas_contas_em_fevereiro(usuario):
    RecorrenciaFactory(usuario=usuario, nome="Dia 31", dia_do_mes=31)
    RecorrenciaFactory(usuario=usuario, nome="Dia 2", dia_do_mes=2)
    proximas = services.proximas_contas(usuario, d(2027, 2, 25))
    assert [(p["nome"], p["vencimento"]) for p in proximas] == [
        ("Dia 31", d(2027, 2, 28)),
        ("Dia 2", d(2027, 3, 2)),
    ]


def test_orcamentos_incluem_subcategorias_abatem_estornos_e_ordenam(usuario, cenario):
    c = cenario
    OrcamentoFactory(usuario=usuario, categoria=c.alimentacao, limite_centavos=10_000)
    OrcamentoFactory(usuario=usuario, categoria=c.lazer, limite_centavos=10_000)
    OrcamentoFactory(usuario=usuario, categoria=c.mercado, limite_centavos=1_000)
    OrcamentoFactory(
        usuario=usuario, categoria=c.lazer, limite_centavos=1, mes_referencia=d(2026, 12, 1)
    )
    t(usuario, c.corrente, 6_000, d(2026, 11, 1), categoria=c.mercado)
    t(usuario, c.corrente, 3_000, d(2026, 11, 1), categoria=c.alimentacao)
    t(usuario, c.corrente, 5_000, d(2026, 11, 1), categoria=c.lazer)
    t(usuario, c.corrente, 2_000, d(2026, 11, 2), "entrada", categoria=c.lazer)

    orcs = services.resumo(usuario, NOV, hoje=HOJE)["orcamentos"]
    assert [(o["nome"], o["gasto_centavos"], o["percentual"]) for o in orcs] == [
        ("Mercado", 6_000, 600.0),
        ("Alimentação", 9_000, 90.0),
        ("Lazer", 3_000, 30.0),
    ]
    assert orcs[1]["restante_centavos"] == 1_000


def test_maiores_gastos_top_5(usuario, cenario):
    for valor in (100, 900, 500, 700, 300, 800, 50):
        t(usuario, cenario.corrente, valor, d(2026, 11, 3))
    t(usuario, cenario.corrente, 5_000, d(2026, 11, 3), "entrada")
    gastos = services.resumo(usuario, NOV, hoje=HOJE)["maiores_gastos"]
    assert [g["valor_centavos"] for g in gastos] == [900, 800, 700, 500, 300]


def test_alerta_de_fatura_na_corrente_nao_ignorada(usuario, cenario):
    c = cenario
    suspeita = t(usuario, c.corrente, 30_000, d(2026, 11, 10), descricao="PAGTO FATURA NUBANK")
    t(usuario, c.corrente, 1_000, d(2026, 11, 11), descricao="Pagamento Cartão", ignorada=True)
    t(usuario, c.corrente, 1_000, d(2026, 11, 12), descricao="Padaria")
    t(usuario, c.cartao, 1_000, d(2026, 11, 13), descricao="Anuidade cartao")
    t(usuario, c.corrente, 1_000, d(2026, 11, 14), descricao="X", descricao_original="CARTÃO")
    alertas = services.resumo(usuario, NOV, hoje=HOJE)["alertas"]
    assert [a["tipo"] for a in alertas] == ["fatura_nao_ignorada"] * 2
    assert alertas[0]["transacao"] == suspeita.pk


def test_evolucao(usuario, cenario):
    c = cenario
    t(usuario, c.corrente, 100_000, d(2026, 9, 5), "entrada")
    t(usuario, c.corrente, 30_000, d(2026, 9, 30))
    t(usuario, c.corrente, 20_000, d(2026, 11, 1), categoria=c.lazer)
    t(usuario, c.corrente, 5_000, d(2026, 11, 2), "entrada", categoria=c.lazer)
    t(usuario, c.corrente, 1, d(2026, 6, 30))  # fora da janela
    resultado = services.evolucao(usuario, NOV, 4)
    assert resultado == [
        {"mes": d(2026, 8, 1), "receitas": 0, "despesas": 0, "resultado": 0},
        {"mes": d(2026, 9, 1), "receitas": 100_000, "despesas": 30_000, "resultado": 70_000},
        {"mes": d(2026, 10, 1), "receitas": 0, "despesas": 0, "resultado": 0},
        {"mes": d(2026, 11, 1), "receitas": 0, "despesas": 15_000, "resultado": -15_000},
    ]


def test_evolucao_atravessa_fevereiro_e_virada_de_ano(usuario, cenario):
    t(usuario, cenario.corrente, 100, d(2027, 2, 28))
    t(usuario, cenario.corrente, 200, d(2026, 12, 31))
    resultado = services.evolucao(usuario, d(2027, 3, 1), 4)
    assert [(r["mes"], r["despesas"]) for r in resultado] == [
        (d(2026, 12, 1), 200),
        (d(2027, 1, 1), 0),
        (d(2027, 2, 1), 100),
        (d(2027, 3, 1), 0),
    ]
