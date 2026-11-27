import pytest

from apps.financas.models import RegraCategoria, Transacao
from apps.financas.services.regras import (
    aplicar_regras,
    aplicar_regras_em_lote,
    sugerir_regra,
)
from apps.financas.services.texto import normalizar

from .factories import CategoriaFactory, RegraCategoriaFactory, TransacaoFactory

pytestmark = pytest.mark.django_db


def test_normalizar_remove_acentos_caixa_e_espacos():
    assert normalizar("  PÃO   de Açúcar ") == "pao de acucar"


@pytest.mark.parametrize(
    ("operador", "valor", "descricao", "casa"),
    [
        ("contem", "acucar", "Supermercado PÃO DE AÇÚCAR", True),
        ("contem", "Açúcar", "pao de acucar", True),
        ("comeca_com", "uber", "UBER *TRIP", True),
        ("comeca_com", "trip", "UBER *TRIP", False),
        ("igual", "netflix.com", "NETFLIX.COM", True),
        ("igual", "netflix", "NETFLIX.COM", False),
    ],
)
def test_operadores(usuario, operador, valor, descricao, casa):
    regra = RegraCategoriaFactory(usuario=usuario, operador=operador, valor=valor)
    transacao = TransacaoFactory(usuario=usuario, descricao=descricao)
    assert (aplicar_regras(transacao) == regra) is casa
    transacao.refresh_from_db()
    assert (transacao.categoria_id == regra.categoria_id) is casa


def test_usa_tambem_a_descricao_original(usuario):
    regra = RegraCategoriaFactory(usuario=usuario, valor="ifood")
    transacao = TransacaoFactory(
        usuario=usuario, descricao="Jantar", descricao_original="IFD*IFOOD.COM AGENCIA"
    )
    assert aplicar_regras(transacao) == regra


def test_aplica_a_de_maior_prioridade(usuario):
    RegraCategoriaFactory(usuario=usuario, valor="uber", prioridade=1)
    alta = RegraCategoriaFactory(usuario=usuario, valor="uber eats", prioridade=10)
    transacao = TransacaoFactory(usuario=usuario, descricao="UBER EATS")
    assert aplicar_regras(transacao) == alta


def test_nunca_sobrescreve_categoria_manual(usuario):
    manual = CategoriaFactory(usuario=usuario)
    RegraCategoriaFactory(usuario=usuario, valor="mercado")
    transacao = TransacaoFactory(
        usuario=usuario, descricao="Mercado", categoria=manual, categoria_definida_manualmente=True
    )
    assert aplicar_regras(transacao) is None
    transacao.refresh_from_db()
    assert transacao.categoria == manual


def test_ignora_regras_de_outro_usuario(usuario, outro_usuario):
    RegraCategoriaFactory(usuario=outro_usuario, valor="mercado")
    transacao = TransacaoFactory(usuario=usuario, descricao="Mercado")
    assert aplicar_regras(transacao) is None


def test_saida_nao_recebe_categoria_de_receita(usuario):
    receita = CategoriaFactory(usuario=usuario, tipo="receita")
    RegraCategoriaFactory(usuario=usuario, valor="pix", categoria=receita)
    saida = TransacaoFactory(usuario=usuario, descricao="PIX enviado", tipo="saida")
    entrada = TransacaoFactory(usuario=usuario, descricao="PIX recebido", tipo="entrada")
    assert aplicar_regras(saida) is None
    assert aplicar_regras(entrada) is not None


def test_entrada_pode_receber_categoria_de_gasto_estorno(usuario):
    compras = CategoriaFactory(usuario=usuario, tipo="gasto")
    RegraCategoriaFactory(usuario=usuario, valor="amazon", categoria=compras)
    estorno = TransacaoFactory(usuario=usuario, descricao="Estorno AMAZON", tipo="entrada")
    aplicar_regras(estorno)
    assert estorno.categoria == compras
    assert estorno.estorno


def test_aplicar_em_lote(usuario):
    RegraCategoriaFactory(usuario=usuario, valor="mercado")
    TransacaoFactory.create_batch(3, usuario=usuario, descricao="Mercado X")
    TransacaoFactory(usuario=usuario, descricao="Outra coisa")
    assert aplicar_regras_em_lote(usuario) == 3
    assert aplicar_regras_em_lote(usuario) == 0


def test_sugestao_de_regra_limpa_numeros(usuario):
    categoria = CategoriaFactory(usuario=usuario)
    transacao = TransacaoFactory(
        usuario=usuario, descricao="UBER *TRIP 12/03 4521", categoria=categoria
    )
    assert sugerir_regra(transacao) == {
        "campo": "descricao",
        "operador": "contem",
        "valor": "uber trip",
        "categoria": str(categoria.id),
    }


def test_sem_sugestao_quando_ja_existe_regra(usuario):
    regra = RegraCategoriaFactory(usuario=usuario, valor="uber")
    transacao = TransacaoFactory(usuario=usuario, descricao="UBER", categoria=regra.categoria)
    assert sugerir_regra(transacao) is None


def test_sem_sugestao_sem_categoria(usuario):
    assert sugerir_regra(TransacaoFactory(usuario=usuario)) is None


def test_regra_vazia_nao_casa(usuario):
    RegraCategoriaFactory(usuario=usuario, valor="  ")
    assert aplicar_regras(TransacaoFactory(usuario=usuario)) is None
    assert RegraCategoria.objects.count() == 1
    assert Transacao.objects.count() == 1
