import pytest

from apps.financas.models import Categoria, ContaFinanceira, RegraCategoria

from .factories import (
    CategoriaFactory,
    ContaFinanceiraFactory,
    RecorrenciaFactory,
    RegraCategoriaFactory,
    TransacaoFactory,
)
from .isolamento import verificar_isolamento

pytestmark = pytest.mark.django_db

CATEGORIAS = "/api/v1/categorias/"
CONTAS = "/api/v1/contas/"
REGRAS = "/api/v1/regras/"


@pytest.mark.parametrize("url", [CATEGORIAS, CONTAS, REGRAS])
def test_exige_autenticacao(api_client, url):
    assert api_client.get(url).status_code == 401


# --- Categorias -----------------------------------------------------------------


def test_cria_categoria_e_subcategoria(cliente_autenticado, usuario):
    pai = cliente_autenticado.post(
        CATEGORIAS, {"nome": "Pets", "icone": "pawprint", "cor": "#00AA00", "tipo": "gasto"}
    )
    assert pai.status_code == 201, pai.json()
    filha = cliente_autenticado.post(
        CATEGORIAS, {"nome": "Ração", "tipo": "gasto", "categoria_pai": pai.json()["id"]}
    )
    assert filha.status_code == 201, filha.json()
    assert Categoria.objects.get(pk=filha.json()["id"]).usuario == usuario


def test_usuario_no_body_e_ignorado(cliente_autenticado, usuario, outro_usuario):
    resposta = cliente_autenticado.post(
        CATEGORIAS, {"nome": "X", "tipo": "gasto", "usuario": str(outro_usuario.pk)}
    )
    assert Categoria.objects.get(pk=resposta.json()["id"]).usuario == usuario


def test_categoria_duplicada_e_terceiro_nivel_sao_rejeitados(cliente_autenticado, usuario):
    pai = CategoriaFactory(usuario=usuario, nome="Casa")
    filha = CategoriaFactory(usuario=usuario, categoria_pai=pai)
    duplicada = cliente_autenticado.post(CATEGORIAS, {"nome": "Casa", "tipo": "gasto"})
    assert duplicada.status_code == 400
    neta = cliente_autenticado.post(
        CATEGORIAS, {"nome": "Neta", "tipo": "gasto", "categoria_pai": str(filha.pk)}
    )
    assert neta.status_code == 400
    assert "categoria_pai" in neta.json()


def test_cor_invalida(cliente_autenticado):
    resposta = cliente_autenticado.post(CATEGORIAS, {"nome": "X", "cor": "red"})
    assert resposta.status_code == 400
    assert "cor" in resposta.json()


def test_nao_aceita_pai_de_outro_usuario(cliente_autenticado, outro_usuario):
    alheia = CategoriaFactory(usuario=outro_usuario)
    resposta = cliente_autenticado.post(
        CATEGORIAS, {"nome": "X", "tipo": "gasto", "categoria_pai": str(alheia.pk)}
    )
    assert resposta.status_code == 400
    assert "categoria_pai" in resposta.json()


def test_filtra_categorias(cliente_autenticado, usuario):
    pai = CategoriaFactory(usuario=usuario, tipo="gasto")
    CategoriaFactory(usuario=usuario, categoria_pai=pai)
    CategoriaFactory(usuario=usuario, tipo="receita")
    assert cliente_autenticado.get(CATEGORIAS, {"tipo": "receita"}).json()["count"] == 1
    assert cliente_autenticado.get(CATEGORIAS, {"raiz": "true"}).json()["count"] == 2
    assert cliente_autenticado.get(CATEGORIAS, {"categoria_pai": pai.pk}).json()["count"] == 1


def test_apagar_categoria_em_uso_por_recorrencia_da_409(cliente_autenticado, usuario):
    rec = RecorrenciaFactory(usuario=usuario)
    assert cliente_autenticado.delete(f"{CATEGORIAS}{rec.categoria_id}/").status_code == 409


def test_apagar_categoria_deixa_transacoes_sem_categoria(cliente_autenticado, usuario):
    categoria = CategoriaFactory(usuario=usuario)
    transacao = TransacaoFactory(usuario=usuario, categoria=categoria)
    assert cliente_autenticado.delete(f"{CATEGORIAS}{categoria.pk}/").status_code == 204
    transacao.refresh_from_db()
    assert transacao.categoria is None


def test_isolamento_categorias(cliente_autenticado, outro_usuario):
    verificar_isolamento(
        cliente_autenticado,
        CATEGORIAS,
        CategoriaFactory(usuario=outro_usuario),
        {"nome": "Roubada", "tipo": "gasto"},
    )


# --- Contas ---------------------------------------------------------------------


def test_crud_de_conta(cliente_autenticado, usuario):
    resposta = cliente_autenticado.post(
        CONTAS,
        {"nome": "Nubank", "tipo": "cartao_credito", "saldo_centavos": 0, "limite_centavos": 5000},
    )
    assert resposta.status_code == 201, resposta.json()
    corpo = resposta.json()
    assert corpo["manual"] is True
    assert corpo["pluggy_account_id"] == ""
    url = f"{CONTAS}{corpo['id']}/"
    assert cliente_autenticado.patch(url, {"ativa": False}).json()["ativa"] is False
    assert cliente_autenticado.get(CONTAS, {"ativa": "true"}).json()["count"] == 0
    assert cliente_autenticado.delete(url).status_code == 204


def test_campos_da_pluggy_sao_somente_leitura(cliente_autenticado):
    resposta = cliente_autenticado.post(
        CONTAS, {"nome": "X", "tipo": "corrente", "pluggy_account_id": "injetado"}
    )
    assert ContaFinanceira.objects.get(pk=resposta.json()["id"]).pluggy_account_id == ""


def test_saldo_de_conta_conectada_nao_e_editavel(cliente_autenticado, usuario):
    conta = ContaFinanceiraFactory(usuario=usuario, pluggy_account_id="conta-pluggy-1")
    resposta = cliente_autenticado.patch(f"{CONTAS}{conta.pk}/", {"saldo_centavos": 1})
    assert resposta.status_code == 400


def test_apagar_conta_com_transacoes_da_409(cliente_autenticado, usuario):
    transacao = TransacaoFactory(usuario=usuario)
    assert cliente_autenticado.delete(f"{CONTAS}{transacao.conta_id}/").status_code == 409


def test_isolamento_contas(cliente_autenticado, outro_usuario):
    verificar_isolamento(
        cliente_autenticado,
        CONTAS,
        ContaFinanceiraFactory(usuario=outro_usuario),
        {"nome": "Roubada", "tipo": "corrente"},
    )


# --- Regras ---------------------------------------------------------------------


def test_cria_regra_e_aplica_em_lote(cliente_autenticado, usuario):
    categoria = CategoriaFactory(usuario=usuario)
    TransacaoFactory(usuario=usuario, descricao="Posto Shell")
    resposta = cliente_autenticado.post(
        REGRAS, {"valor": " posto ", "categoria": str(categoria.pk), "prioridade": 5}
    )
    assert resposta.status_code == 201, resposta.json()
    assert RegraCategoria.objects.get().valor == "posto"
    aplicadas = cliente_autenticado.post(f"{REGRAS}aplicar/")
    assert aplicadas.json() == {"alteradas": 1}


def test_regra_nao_aceita_categoria_de_outro_usuario(cliente_autenticado, outro_usuario):
    alheia = CategoriaFactory(usuario=outro_usuario)
    resposta = cliente_autenticado.post(REGRAS, {"valor": "x", "categoria": str(alheia.pk)})
    assert resposta.status_code == 400
    assert "categoria" in resposta.json()


def test_aplicar_nao_mexe_em_transacoes_de_outro_usuario(cliente_autenticado, outro_usuario):
    regra = RegraCategoriaFactory(usuario=outro_usuario, valor="mercado")
    alheia = TransacaoFactory(usuario=outro_usuario, descricao="Mercado")
    cliente_autenticado.post(f"{REGRAS}aplicar/")
    alheia.refresh_from_db()
    assert alheia.categoria is None
    assert regra.categoria_id is not None


def test_isolamento_regras(cliente_autenticado, usuario, outro_usuario):
    verificar_isolamento(
        cliente_autenticado,
        REGRAS,
        RegraCategoriaFactory(usuario=outro_usuario),
        {"valor": "x", "categoria": str(CategoriaFactory(usuario=usuario).pk)},
    )
