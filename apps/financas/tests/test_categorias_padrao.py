import pytest
from django.core.management import CommandError, call_command

from apps.accounts.tests.factories import ConviteFactory
from apps.financas.models import Categoria
from apps.financas.services.categorias import criar_categorias_padrao

pytestmark = pytest.mark.django_db

TOTAL_PADRAO = 14  # 9 gastos + 3 subcategorias de Alimentação + 2 receitas


def test_cria_categorias_padrao(usuario):
    assert criar_categorias_padrao(usuario) == TOTAL_PADRAO
    alimentacao = Categoria.objects.get(usuario=usuario, nome="Alimentação")
    assert set(alimentacao.subcategorias.values_list("nome", flat=True)) == {
        "Mercado",
        "Restaurante",
        "Delivery",
    }
    assert Categoria.objects.get(usuario=usuario, nome="Salário").tipo == "receita"
    assert Categoria.objects.get(usuario=usuario, nome="Outras receitas").tipo == "receita"
    assert Categoria.objects.get(usuario=usuario, nome="Outros").tipo == "gasto"


def test_criar_categorias_padrao_e_idempotente(usuario):
    criar_categorias_padrao(usuario)
    assert criar_categorias_padrao(usuario) == 0
    assert Categoria.objects.filter(usuario=usuario).count() == TOTAL_PADRAO


def test_registro_por_convite_cria_categorias_padrao(api_client):
    convite = ConviteFactory()
    resposta = api_client.post(
        "/api/v1/auth/registro/",
        {"codigo": convite.codigo, "email": "novo@exemplo.com", "senha": "uma-senha-bem-forte-9"},
    )
    assert resposta.status_code == 201
    assert Categoria.objects.filter(usuario__email="novo@exemplo.com").count() == TOTAL_PADRAO


def test_comando_criar_categorias_padrao(usuario, capsys):
    call_command("criar_categorias_padrao", usuario.email.upper())
    assert f"{TOTAL_PADRAO} categoria(s) criada(s)" in capsys.readouterr().out
    call_command("criar_categorias_padrao", usuario.email)
    assert "0 categoria(s) criada(s)" in capsys.readouterr().out


def test_comando_com_usuario_inexistente():
    with pytest.raises(CommandError):
        call_command("criar_categorias_padrao", "ninguem@exemplo.com")
