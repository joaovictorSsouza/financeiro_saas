import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.financas.models import Categoria, ContaFinanceira

from .factories import CategoriaFactory, ContaFinanceiraFactory

pytestmark = pytest.mark.django_db


def test_categoria_raiz_com_mesmo_nome_e_unica(usuario):
    CategoriaFactory(usuario=usuario, nome="Lazer")
    with pytest.raises(IntegrityError):
        CategoriaFactory(usuario=usuario, nome="Lazer")


def test_mesmo_nome_em_pais_diferentes_e_permitido(usuario):
    a = CategoriaFactory(usuario=usuario, nome="A")
    b = CategoriaFactory(usuario=usuario, nome="B")
    CategoriaFactory(usuario=usuario, nome="Outros", categoria_pai=a)
    CategoriaFactory(usuario=usuario, nome="Outros", categoria_pai=b)
    CategoriaFactory(usuario=usuario, nome="Outros")


def test_mesmo_nome_em_usuarios_diferentes(usuario, outro_usuario):
    CategoriaFactory(usuario=usuario, nome="Lazer")
    CategoriaFactory(usuario=outro_usuario, nome="Lazer")


def test_categoria_no_maximo_dois_niveis(usuario):
    pai = CategoriaFactory(usuario=usuario)
    filha = CategoriaFactory(usuario=usuario, categoria_pai=pai)
    neta = Categoria(usuario=usuario, nome="Neta", categoria_pai=filha)
    with pytest.raises(ValidationError):
        neta.full_clean()


def test_subcategoria_com_tipo_diferente_da_pai(usuario):
    pai = CategoriaFactory(usuario=usuario, tipo="gasto")
    filha = Categoria(usuario=usuario, nome="X", categoria_pai=pai, tipo="receita")
    with pytest.raises(ValidationError):
        filha.full_clean()


def test_cor_invalida(usuario):
    with pytest.raises(ValidationError):
        Categoria(usuario=usuario, nome="X", cor="azul").full_clean()


def test_raiz_da_categoria(usuario):
    pai = CategoriaFactory(usuario=usuario)
    filha = CategoriaFactory(usuario=usuario, categoria_pai=pai)
    assert filha.raiz == pai
    assert pai.raiz == pai


def test_pluggy_account_id_unico_quando_preenchido(usuario):
    ContaFinanceiraFactory(usuario=usuario)
    ContaFinanceiraFactory(usuario=usuario)  # dois nulos convivem
    pluggy_id = uuid.uuid4()
    ContaFinanceiraFactory(usuario=usuario, pluggy_account_id=pluggy_id)
    with pytest.raises(IntegrityError):
        ContaFinanceiraFactory(usuario=usuario, pluggy_account_id=pluggy_id)


def test_conta_manual(usuario):
    assert ContaFinanceiraFactory(usuario=usuario).manual
    assert not ContaFinanceira(pluggy_account_id=uuid.uuid4()).manual
