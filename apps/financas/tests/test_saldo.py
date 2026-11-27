import datetime
import uuid

import pytest

from apps.financas.models import Transacao
from apps.financas.services.transacoes import (
    atualizar_transacao,
    criar_transacao,
    excluir_transacao,
)

from .factories import CategoriaFactory, ContaFinanceiraFactory, RegraCategoriaFactory

pytestmark = pytest.mark.django_db
HOJE = datetime.date(2026, 11, 10)


def nova(usuario, conta, **extra):
    dados = {"conta": conta, "data": HOJE, "descricao": "X", "valor_centavos": 1000}
    dados["tipo"] = "saida"
    return criar_transacao(usuario, **(dados | extra))


def saldo(conta):
    conta.refresh_from_db()
    return conta.saldo_centavos


def test_criar_editar_e_excluir_ajustam_saldo_da_conta_manual(usuario):
    conta = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=10_000)
    t = nova(usuario, conta)
    assert saldo(conta) == 9_000
    atualizar_transacao(t, valor_centavos=2_500)
    assert saldo(conta) == 7_500
    atualizar_transacao(t, tipo="entrada")
    assert saldo(conta) == 12_500
    excluir_transacao(t)
    assert saldo(conta) == 10_000


def test_trocar_de_conta_move_o_saldo(usuario):
    a = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=0)
    b = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=0)
    t = nova(usuario, a)
    atualizar_transacao(t, conta=b)
    assert (saldo(a), saldo(b)) == (0, -1000)


def test_ignorada_tambem_mexe_no_saldo(usuario):
    conta = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=0)
    nova(usuario, conta, ignorada=True)
    assert saldo(conta) == -1000


def test_conta_pluggy_nao_e_alterada(usuario):
    conta = ContaFinanceiraFactory(
        usuario=usuario, saldo_centavos=500, pluggy_account_id=uuid.uuid4()
    )
    nova(usuario, conta)
    assert saldo(conta) == 500


def test_categoria_informada_na_criacao_e_manual(usuario):
    conta = ContaFinanceiraFactory(usuario=usuario)
    t = nova(usuario, conta, categoria=CategoriaFactory(usuario=usuario))
    assert t.categoria_definida_manualmente


def test_criacao_sem_categoria_aplica_regras(usuario):
    regra = RegraCategoriaFactory(usuario=usuario, valor="padaria")
    t = nova(usuario, ContaFinanceiraFactory(usuario=usuario), descricao="Padaria Real")
    assert t.categoria == regra.categoria
    assert not t.categoria_definida_manualmente


def test_editar_categoria_marca_como_manual(usuario):
    t = nova(usuario, ContaFinanceiraFactory(usuario=usuario))
    atualizar_transacao(t, categoria=CategoriaFactory(usuario=usuario))
    assert Transacao.objects.get(pk=t.pk).categoria_definida_manualmente
