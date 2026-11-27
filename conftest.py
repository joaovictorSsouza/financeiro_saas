import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UsuarioFactory


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def usuario(db):
    return UsuarioFactory()


@pytest.fixture
def outro_usuario(db):
    return UsuarioFactory()


@pytest.fixture
def cliente_autenticado(api_client, usuario):
    api_client.force_authenticate(usuario)
    return api_client
