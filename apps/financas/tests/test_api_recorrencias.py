import datetime

import pytest

from apps.financas.models import Ocorrencia, Orcamento, Recorrencia

from .factories import (
    CategoriaFactory,
    ContaFinanceiraFactory,
    OcorrenciaFactory,
    OrcamentoFactory,
    RecorrenciaFactory,
    TransacaoFactory,
)
from .isolamento import verificar_isolamento

pytestmark = pytest.mark.django_db
d = datetime.date

RECORRENCIAS = "/api/v1/recorrencias/"
OCORRENCIAS = "/api/v1/ocorrencias/"
ORCAMENTOS = "/api/v1/orcamentos/"


@pytest.mark.parametrize("url", [RECORRENCIAS, OCORRENCIAS, ORCAMENTOS])
def test_exige_autenticacao(api_client, url):
    assert api_client.get(url).status_code == 401


# --- Recorrências ---------------------------------------------------------------


def dados_recorrencia(categoria, **extra):
    base = {
        "tipo": "conta",
        "nome": "Aluguel",
        "valor_previsto_centavos": 200_000,
        "dia_do_mes": 31,
        "categoria": str(categoria.pk),
        "inicio": "2026-01-01",
    }
    return base | extra


def test_criar_recorrencia_gera_ocorrencia_do_mes_atual(cliente_autenticado, usuario, hoje):
    categoria = CategoriaFactory(usuario=usuario)
    resposta = cliente_autenticado.post(RECORRENCIAS, dados_recorrencia(categoria))
    assert resposta.status_code == 201, resposta.json()
    ocorrencia = Ocorrencia.objects.get()
    assert (ocorrencia.mes_referencia, ocorrencia.vencimento) == (d(2026, 11, 1), d(2026, 11, 30))
    assert ocorrencia.usuario == usuario


def test_editar_recorrencia_atualiza_previstas(cliente_autenticado, usuario, hoje):
    categoria = CategoriaFactory(usuario=usuario)
    rec_id = cliente_autenticado.post(RECORRENCIAS, dados_recorrencia(categoria)).json()["id"]
    cliente_autenticado.patch(f"{RECORRENCIAS}{rec_id}/", {"valor_previsto_centavos": 210_000})
    assert Ocorrencia.objects.get().valor_centavos == 210_000


def test_desativar_recorrencia_apaga_previstas_futuras(cliente_autenticado, usuario, hoje):
    rec = RecorrenciaFactory(usuario=usuario, dia_do_mes=25)
    OcorrenciaFactory(recorrencia=rec, mes_referencia=d(2026, 11, 1))
    cliente_autenticado.patch(f"{RECORRENCIAS}{rec.pk}/", {"ativa": False})
    assert not rec.ocorrencias.exists()


@pytest.mark.parametrize(
    "extra",
    [
        {"dia_do_mes": 0},
        {"dia_do_mes": 32},
        {"valor_previsto_centavos": 0},
        {"fim": "2025-12-31"},
        {"total_parcelas": 0},
    ],
)
def test_validacoes_da_recorrencia(cliente_autenticado, usuario, extra):
    categoria = CategoriaFactory(usuario=usuario)
    resposta = cliente_autenticado.post(RECORRENCIAS, dados_recorrencia(categoria, **extra))
    assert resposta.status_code == 400


def test_tipo_da_categoria_deve_combinar(cliente_autenticado, usuario):
    receita = CategoriaFactory(usuario=usuario, tipo="receita")
    gasto = CategoriaFactory(usuario=usuario, tipo="gasto")
    assert cliente_autenticado.post(RECORRENCIAS, dados_recorrencia(receita)).status_code == 400
    salario = dados_recorrencia(gasto, tipo="receita")
    assert cliente_autenticado.post(RECORRENCIAS, salario).status_code == 400


def test_nao_aceita_categoria_ou_conta_alheia(cliente_autenticado, usuario, outro_usuario):
    alheia = CategoriaFactory(usuario=outro_usuario)
    assert cliente_autenticado.post(RECORRENCIAS, dados_recorrencia(alheia)).status_code == 400
    conta_alheia = ContaFinanceiraFactory(usuario=outro_usuario)
    minha = CategoriaFactory(usuario=usuario)
    resposta = cliente_autenticado.post(
        RECORRENCIAS, dados_recorrencia(minha, conta_padrao=str(conta_alheia.pk))
    )
    assert resposta.status_code == 400
    assert "conta_padrao" in resposta.json()


def test_apagar_recorrencia_com_ocorrencia_paga_da_409(cliente_autenticado, usuario):
    rec = RecorrenciaFactory(usuario=usuario)
    OcorrenciaFactory(recorrencia=rec, status="paga")
    assert cliente_autenticado.delete(f"{RECORRENCIAS}{rec.pk}/").status_code == 409
    sem_paga = RecorrenciaFactory(usuario=usuario)
    OcorrenciaFactory(recorrencia=sem_paga)
    assert cliente_autenticado.delete(f"{RECORRENCIAS}{sem_paga.pk}/").status_code == 204


def test_isolamento_recorrencias(cliente_autenticado, usuario, outro_usuario):
    verificar_isolamento(
        cliente_autenticado,
        RECORRENCIAS,
        RecorrenciaFactory(usuario=outro_usuario),
        dados_recorrencia(CategoriaFactory(usuario=usuario)),
    )


# --- Ocorrências ----------------------------------------------------------------


def test_listar_gera_sempre_e_calcula_atrasada(cliente_autenticado, usuario, hoje):
    RecorrenciaFactory(usuario=usuario, dia_do_mes=10, nome="Luz")
    resposta = cliente_autenticado.get(OCORRENCIAS, {"mes": "2026-11"})
    assert resposta.status_code == 200
    [luz] = resposta.json()["results"]
    assert (luz["nome"], luz["status"], luz["vencimento"]) == ("Luz", "atrasada", "2026-11-10")

    # Gera sempre: uma recorrência nova aparece mesmo com o mês já tendo ocorrências.
    RecorrenciaFactory(usuario=usuario, dia_do_mes=25, inicio=d(2026, 12, 1))
    RecorrenciaFactory(usuario=usuario, dia_do_mes=25)
    corpo = cliente_autenticado.get(OCORRENCIAS, {"mes": "2026-11"}).json()
    assert corpo["count"] == 2
    assert cliente_autenticado.get(OCORRENCIAS, {"status": "atrasada"}).json()["count"] == 1
    assert cliente_autenticado.get(OCORRENCIAS, {"status": "prevista"}).json()["count"] == 1


def test_sem_mes_usa_o_atual_e_mes_invalido_da_400(cliente_autenticado, usuario, hoje):
    RecorrenciaFactory(usuario=usuario)
    [ocorrencia] = cliente_autenticado.get(OCORRENCIAS).json()["results"]
    assert ocorrencia["mes_referencia"] == "2026-11-01"
    assert cliente_autenticado.get(OCORRENCIAS, {"mes": "2026-13"}).status_code == 400


def test_consultar_mes_novo_casa_transacoes(cliente_autenticado, usuario, hoje):
    RecorrenciaFactory(usuario=usuario, dia_do_mes=5, valor_previsto_centavos=10_000)
    t = TransacaoFactory(usuario=usuario, data=d(2026, 10, 6), valor_centavos=10_000)
    [ocorrencia] = cliente_autenticado.get(OCORRENCIAS, {"mes": "2026-10"}).json()["results"]
    assert (ocorrencia["status"], ocorrencia["transacao"]) == ("paga", str(t.pk))


def test_marcar_paga_e_desmarcar(cliente_autenticado, usuario, hoje):
    oc = OcorrenciaFactory(recorrencia__usuario=usuario)
    t = TransacaoFactory(usuario=usuario, valor_centavos=1)
    url = f"{OCORRENCIAS}{oc.pk}/"
    resposta = cliente_autenticado.post(f"{url}marcar-paga/", {"transacao": str(t.pk)})
    assert resposta.status_code == 200, resposta.json()
    assert resposta.json()["status"] == "paga"
    assert resposta.json()["transacao"] == str(t.pk)

    resposta = cliente_autenticado.post(f"{url}desmarcar/")
    assert resposta.json()["status"] == "atrasada"  # vence 10/11 e hoje é 20/11
    assert resposta.json()["casamento_automatico"] is False

    sem_transacao = cliente_autenticado.post(f"{url}marcar-paga/", {"paga_em": "2026-11-11"})
    assert (sem_transacao.json()["paga_em"], sem_transacao.json()["transacao"]) == (
        "2026-11-11",
        None,
    )


def test_marcar_paga_valida_transacao(cliente_autenticado, usuario, outro_usuario):
    oc = OcorrenciaFactory(recorrencia__usuario=usuario)
    url = f"{OCORRENCIAS}{oc.pk}/marcar-paga/"
    alheia = TransacaoFactory(usuario=outro_usuario)
    entrada = TransacaoFactory(usuario=usuario, tipo="entrada")
    ja_usada = TransacaoFactory(usuario=usuario)
    OcorrenciaFactory(recorrencia__usuario=usuario, transacao=ja_usada, status="paga")
    for t in (alheia, entrada, ja_usada):
        resposta = cliente_autenticado.post(url, {"transacao": str(t.pk)})
        assert resposta.status_code == 400, t
        assert "transacao" in resposta.json()


def test_isolamento_ocorrencias(cliente_autenticado, outro_usuario):
    alheia = OcorrenciaFactory(recorrencia__usuario=outro_usuario)
    url = f"{OCORRENCIAS}{alheia.pk}/"
    assert cliente_autenticado.get(OCORRENCIAS, {"mes": "2026-11"}).json()["count"] == 0
    assert cliente_autenticado.get(url).status_code == 404
    assert cliente_autenticado.post(f"{url}marcar-paga/").status_code == 404
    assert cliente_autenticado.post(f"{url}desmarcar/").status_code == 404
    assert cliente_autenticado.delete(url).status_code == 405  # somente leitura
    alheia.refresh_from_db()
    assert alheia.status == "prevista"


# --- Orçamentos -----------------------------------------------------------------


def test_crud_orcamento_normaliza_mes(cliente_autenticado, usuario):
    categoria = CategoriaFactory(usuario=usuario)
    resposta = cliente_autenticado.post(
        ORCAMENTOS,
        {"categoria": str(categoria.pk), "mes_referencia": "2026-11-17", "limite_centavos": 100},
    )
    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["mes_referencia"] == "2026-11-01"
    assert Orcamento.objects.get().usuario == usuario
    assert cliente_autenticado.get(ORCAMENTOS, {"mes": "2026-11"}).json()["count"] == 1
    assert cliente_autenticado.get(ORCAMENTOS, {"mes": "2026-12"}).json()["count"] == 0


def test_orcamento_duplicado_receita_e_limite_invalido(cliente_autenticado, usuario):
    orcamento = OrcamentoFactory(usuario=usuario)
    base = {"mes_referencia": "2026-11-01", "limite_centavos": 100}
    duplicado = base | {"categoria": str(orcamento.categoria_id)}
    assert cliente_autenticado.post(ORCAMENTOS, duplicado).status_code == 400
    receita = CategoriaFactory(usuario=usuario, tipo="receita")
    de_receita = base | {"categoria": str(receita.pk)}
    assert cliente_autenticado.post(ORCAMENTOS, de_receita).status_code == 400
    gasto = CategoriaFactory(usuario=usuario)
    zero = base | {"categoria": str(gasto.pk), "limite_centavos": 0}
    assert cliente_autenticado.post(ORCAMENTOS, zero).status_code == 400


def test_orcamento_com_categoria_alheia(cliente_autenticado, outro_usuario):
    alheia = CategoriaFactory(usuario=outro_usuario)
    dados = {"categoria": str(alheia.pk), "mes_referencia": "2026-11-01", "limite_centavos": 1}
    assert cliente_autenticado.post(ORCAMENTOS, dados).status_code == 400


def test_isolamento_orcamentos(cliente_autenticado, usuario, outro_usuario):
    verificar_isolamento(
        cliente_autenticado,
        ORCAMENTOS,
        OrcamentoFactory(usuario=outro_usuario),
        {
            "categoria": str(CategoriaFactory(usuario=usuario).pk),
            "mes_referencia": "2026-11-01",
            "limite_centavos": 1,
        },
    )
    assert Recorrencia.objects.count() == 0
