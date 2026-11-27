import datetime

import pytest
from django.core.cache import cache
from django.utils import timezone
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


@pytest.fixture(autouse=True)
def _limpa_cache():
    """O throttling guarda contadores no cache; cada teste começa do zero."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def hoje(monkeypatch):
    """Fixa o "hoje" (timezone.localdate) em 20/11/2026 para testes com datas."""
    data = datetime.date(2026, 11, 20)
    original = timezone.localdate

    def localdate(value=None, timezone=None):
        if value is None and timezone is None:
            return data
        return original(value, timezone)

    monkeypatch.setattr("django.utils.timezone.localdate", localdate)
    return data
