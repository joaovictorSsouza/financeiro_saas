import datetime

import pytest
from django.urls import reverse

from apps.accounts.tests.factories import UsuarioFactory
from apps.financas.services.transacoes import criar_transacao

from .factories import (
    ContaFinanceiraFactory,
    OcorrenciaFactory,
    OrcamentoFactory,
    RegraCategoriaFactory,
    TransacaoFactory,
)

pytestmark = pytest.mark.django_db

MODELOS = [
    "categoria",
    "contafinanceira",
    "transacao",
    "regracategoria",
    "recorrencia",
    "ocorrencia",
    "orcamento",
]


@pytest.fixture
def admin_client(client):
    client.force_login(UsuarioFactory(is_staff=True, is_superuser=True))
    return client


@pytest.mark.parametrize("modelo", MODELOS)
def test_admin_lista_e_formulario(admin_client, usuario, modelo):
    TransacaoFactory(usuario=usuario)
    RegraCategoriaFactory(usuario=usuario)
    OcorrenciaFactory(recorrencia__usuario=usuario)
    OrcamentoFactory(usuario=usuario)
    lista = admin_client.get(reverse(f"admin:financas_{modelo}_changelist"))
    assert lista.status_code == 200
    filtrada = admin_client.get(
        reverse(f"admin:financas_{modelo}_changelist"), {"usuario__id__exact": usuario.pk}
    )
    assert filtrada.status_code == 200
    assert admin_client.get(reverse(f"admin:financas_{modelo}_add")).status_code == 200


def test_admin_apagar_transacao_ajusta_saldo(admin_client, usuario):
    conta = ContaFinanceiraFactory(usuario=usuario, saldo_centavos=0)
    t = criar_transacao(
        usuario,
        conta=conta,
        data=datetime.date(2026, 11, 1),
        descricao="X",
        valor_centavos=500,
        tipo="saida",
    )
    url = reverse("admin:financas_transacao_delete", args=[t.pk])
    assert admin_client.post(url, {"post": "yes"}).status_code == 302
    conta.refresh_from_db()
    assert conta.saldo_centavos == 0
