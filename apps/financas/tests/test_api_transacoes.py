import datetime

import pytest

from apps.financas.filtros import valor_em_centavos
from apps.financas.models import Transacao
from apps.financas.services.ocorrencias import gerar_ocorrencias

from .factories import (
    CategoriaFactory,
    ContaFinanceiraFactory,
    RecorrenciaFactory,
    RegraCategoriaFactory,
    TransacaoFactory,
)
from .isolamento import verificar_isolamento

pytestmark = pytest.mark.django_db
URL = "/api/v1/transacoes/"
d = datetime.date


def dados(conta, **extra):
    base = {
        "conta": str(conta.pk),
        "data": "2026-11-10",
        "descricao": "Padaria",
        "valor_centavos": 1500,
        "tipo": "saida",
    }
    return base | extra


def test_exige_autenticacao(api_client):
    assert api_client.get(URL).status_code == 401


def test_cria_transacao_ajusta_saldo_e_aplica_regra(cliente_autenticado, usuario):
    conta = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=10_000)
    regra = RegraCategoriaFactory(usuario=usuario, valor="padaria")
    resposta = cliente_autenticado.post(URL, dados(conta))
    assert resposta.status_code == 201, resposta.json()
    corpo = resposta.json()
    assert corpo["categoria"] == str(regra.categoria_id)
    assert corpo["categoria_definida_manualmente"] is False
    assert corpo["origem"] == "manual"
    assert corpo["sugestao_regra"] is None
    conta.refresh_from_db()
    assert conta.saldo_centavos == 8_500


@pytest.mark.parametrize("valor", [0, -100])
def test_valor_deve_ser_positivo(cliente_autenticado, usuario, valor):
    conta = ContaFinanceiraFactory(usuario=usuario)
    resposta = cliente_autenticado.post(URL, dados(conta, valor_centavos=valor))
    assert resposta.status_code == 400


def test_saida_com_categoria_de_receita_e_invalida(cliente_autenticado, usuario):
    conta = ContaFinanceiraFactory(usuario=usuario)
    receita = CategoriaFactory(usuario=usuario, tipo="receita")
    resposta = cliente_autenticado.post(URL, dados(conta, categoria=str(receita.pk)))
    assert resposta.status_code == 400
    assert "categoria" in resposta.json()


def test_entrada_com_categoria_de_gasto_e_estorno(cliente_autenticado, usuario):
    conta = ContaFinanceiraFactory(usuario=usuario)
    compras = CategoriaFactory(usuario=usuario, tipo="gasto")
    resposta = cliente_autenticado.post(
        URL, dados(conta, tipo="entrada", categoria=str(compras.pk), descricao="Estorno")
    )
    assert resposta.status_code == 201, resposta.json()
    assert resposta.json()["estorno"] is True


def test_parcela_invalida(cliente_autenticado, usuario):
    conta = ContaFinanceiraFactory(usuario=usuario)
    resposta = cliente_autenticado.post(URL, dados(conta, parcela_atual=4, total_parcelas=3))
    assert resposta.status_code == 400


def test_nao_aceita_conta_ou_categoria_alheia(cliente_autenticado, usuario, outro_usuario):
    conta_alheia = ContaFinanceiraFactory(usuario=outro_usuario)
    assert cliente_autenticado.post(URL, dados(conta_alheia)).status_code == 400
    conta = ContaFinanceiraFactory(usuario=usuario)
    categoria_alheia = CategoriaFactory(usuario=outro_usuario)
    resposta = cliente_autenticado.post(URL, dados(conta, categoria=str(categoria_alheia.pk)))
    assert resposta.status_code == 400
    assert "categoria" in resposta.json()


def test_corrigir_categoria_marca_manual_e_sugere_regra(cliente_autenticado, usuario):
    t = TransacaoFactory(usuario=usuario, descricao="UBER *TRIP 1234")
    categoria = CategoriaFactory(usuario=usuario)
    resposta = cliente_autenticado.patch(f"{URL}{t.pk}/", {"categoria": str(categoria.pk)})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["categoria_definida_manualmente"] is True
    assert corpo["sugestao_regra"] == {
        "campo": "descricao",
        "operador": "contem",
        "valor": "uber trip",
        "categoria": str(categoria.pk),
    }
    # Nada foi criado automaticamente, e a sugestão só aparece na edição.
    assert not usuario.regras_categoria.exists()
    assert cliente_autenticado.get(f"{URL}{t.pk}/").json()["sugestao_regra"] is None


def test_editar_outro_campo_nao_sugere_regra(cliente_autenticado, usuario):
    t = TransacaoFactory(usuario=usuario, categoria=CategoriaFactory(usuario=usuario))
    resposta = cliente_autenticado.patch(f"{URL}{t.pk}/", {"observacao": "ok"})
    assert resposta.json()["sugestao_regra"] is None


def test_apagar_ajusta_saldo(cliente_autenticado, usuario):
    conta = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=0)
    criada = cliente_autenticado.post(URL, dados(conta)).json()
    assert cliente_autenticado.delete(f"{URL}{criada['id']}/").status_code == 204
    conta.refresh_from_db()
    assert conta.saldo_centavos == 0


def test_criar_transacao_casa_ocorrencia(cliente_autenticado, usuario):
    RecorrenciaFactory(usuario=usuario, dia_do_mes=10, valor_previsto_centavos=1500)
    gerar_ocorrencias(usuario, d(2026, 11, 1))
    conta = ContaFinanceiraFactory(usuario=usuario)
    criada = cliente_autenticado.post(URL, dados(conta)).json()
    assert usuario.ocorrencias.get().transacao_id is not None
    assert str(usuario.ocorrencias.get().transacao_id) == criada["id"]


# --- filtros --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("45", 4500), ("45,9", 4590), ("45.90", 4590), ("0,05", 5), ("abc", None), ("4,567", None)],
)
def test_valor_em_centavos(texto, esperado):
    assert valor_em_centavos(texto) == esperado


def test_filtros(cliente_autenticado, usuario):
    conta = ContaFinanceiraFactory(usuario=usuario)
    outra_conta = ContaFinanceiraFactory(usuario=usuario)
    pai = CategoriaFactory(usuario=usuario)
    filha = CategoriaFactory(usuario=usuario, categoria_pai=pai)
    TransacaoFactory(usuario=usuario, conta=conta, data=d(2026, 11, 1), categoria=pai)
    TransacaoFactory(usuario=usuario, conta=conta, data=d(2026, 11, 30), categoria=filha)
    TransacaoFactory(
        usuario=usuario,
        conta=outra_conta,
        data=d(2026, 12, 1),
        tipo="entrada",
        descricao="Pix da Maria",
        valor_centavos=4590,
    )

    def contar(**params):
        resposta = cliente_autenticado.get(URL, params)
        assert resposta.status_code == 200, resposta.json()
        return resposta.json()["count"]

    assert contar() == 3
    assert contar(mes="2026-11") == 2
    assert contar(mes="2026-12") == 1
    assert contar(conta=conta.pk) == 2
    assert contar(categoria=pai.pk) == 2
    assert contar(categoria=filha.pk) == 1
    assert contar(sem_categoria="true") == 1
    assert contar(tipo="entrada") == 1
    assert contar(busca="maria") == 1
    assert contar(busca="45,90") == 1
    assert contar(busca="10") == 2  # valor da factory: R$ 10,00


def test_mes_invalido_da_400(cliente_autenticado):
    assert cliente_autenticado.get(URL, {"mes": "11/2026"}).status_code == 400


def test_paginacao(cliente_autenticado, usuario):
    TransacaoFactory.create_batch(3, usuario=usuario)
    corpo = cliente_autenticado.get(URL, {"page_size": 2}).json()
    assert corpo["count"] == 3
    assert len(corpo["results"]) == 2
    assert corpo["next"]


def test_isolamento(cliente_autenticado, usuario, outro_usuario):
    verificar_isolamento(
        cliente_autenticado,
        URL,
        TransacaoFactory(usuario=outro_usuario),
        dados(ContaFinanceiraFactory(usuario=usuario)),
    )


# --- divisão --------------------------------------------------------------------


@pytest.fixture
def compra(usuario):
    conta = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=0)
    return TransacaoFactory(usuario=usuario, conta=conta, valor_centavos=10_000)


def dividir(cliente, transacao, *partes):
    itens = [{"categoria": str(c.pk), "valor_centavos": v} for c, v in partes]
    return cliente.post(f"{URL}{transacao.pk}/dividir/", {"itens": itens})


def test_dividir_cria_partes_e_lista_so_as_partes(cliente_autenticado, usuario, compra):
    mercado, farmacia = CategoriaFactory(usuario=usuario), CategoriaFactory(usuario=usuario)
    resposta = dividir(cliente_autenticado, compra, (mercado, 7_000), (farmacia, 3_000))
    assert resposta.status_code == 200, resposta.json()
    corpo = resposta.json()
    assert corpo["dividida"] is True
    assert sorted(p["valor_centavos"] for p in corpo["partes"]) == [3_000, 7_000]

    partes = Transacao.objects.filter(transacao_pai=compra)
    assert all(p.conta_id == compra.conta_id and p.data == compra.data for p in partes)
    assert all(p.categoria_definida_manualmente for p in partes)
    lista = cliente_autenticado.get(URL).json()
    assert lista["count"] == 2
    assert cliente_autenticado.get(URL, {"incluir_divididas": "true"}).json()["count"] == 3
    compra.conta.refresh_from_db()
    assert compra.conta.saldo_centavos == 0  # divisão não mexe no saldo


def test_dividir_de_novo_substitui_e_delete_desfaz(cliente_autenticado, usuario, compra):
    a, b, c = (CategoriaFactory(usuario=usuario) for _ in range(3))
    dividir(cliente_autenticado, compra, (a, 5_000), (b, 5_000))
    dividir(cliente_autenticado, compra, (a, 2_000), (b, 3_000), (c, 5_000))
    assert compra.partes.count() == 3
    resposta = cliente_autenticado.delete(f"{URL}{compra.pk}/dividir/")
    assert resposta.status_code == 200
    assert resposta.json()["dividida"] is False
    assert not compra.partes.exists()


@pytest.mark.parametrize("valores", [[5_000, 4_000], [10_000]])
def test_dividir_exige_soma_igual_e_duas_partes(cliente_autenticado, usuario, compra, valores):
    categorias = [CategoriaFactory(usuario=usuario) for _ in valores]
    resposta = dividir(cliente_autenticado, compra, *zip(categorias, valores, strict=True))
    assert resposta.status_code == 400
    assert "itens" in resposta.json()


def test_dividir_valida_categoria(cliente_autenticado, usuario, outro_usuario, compra):
    alheia = CategoriaFactory(usuario=outro_usuario)
    receita = CategoriaFactory(usuario=usuario, tipo="receita")
    ok = CategoriaFactory(usuario=usuario)
    assert dividir(cliente_autenticado, compra, (alheia, 5_000), (ok, 5_000)).status_code == 400
    assert dividir(cliente_autenticado, compra, (receita, 5_000), (ok, 5_000)).status_code == 400


def test_parte_e_dividida_tem_campos_travados(cliente_autenticado, usuario, compra):
    a, b = CategoriaFactory(usuario=usuario), CategoriaFactory(usuario=usuario)
    dividir(cliente_autenticado, compra, (a, 5_000), (b, 5_000))
    parte = compra.partes.first()
    url_parte = f"{URL}{parte.pk}/"
    assert cliente_autenticado.patch(url_parte, {"valor_centavos": 1}).status_code == 400
    assert cliente_autenticado.patch(url_parte, {"categoria": str(b.pk)}).status_code == 200
    assert cliente_autenticado.post(f"{URL}{parte.pk}/dividir/", {"itens": []}).status_code == 400
    assert cliente_autenticado.delete(url_parte).status_code == 409
    url_compra = f"{URL}{compra.pk}/"
    assert cliente_autenticado.patch(url_compra, {"valor_centavos": 1}).status_code == 400
    assert cliente_autenticado.patch(url_compra, {"ignorada": True}).status_code == 200
    assert all(compra.partes.values_list("ignorada", flat=True))


def test_dividir_transacao_de_outro_usuario_da_404(cliente_autenticado, outro_usuario):
    alheia = TransacaoFactory(usuario=outro_usuario)
    assert cliente_autenticado.post(f"{URL}{alheia.pk}/dividir/", {"itens": []}).status_code == 404
    assert cliente_autenticado.delete(f"{URL}{alheia.pk}/dividir/").status_code == 404
