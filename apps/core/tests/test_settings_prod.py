import importlib
import sys

import pytest

CHAVES = ["DJANGO_SESSION_COOKIE_SECURE", "DJANGO_CSRF_COOKIE_SECURE", "DJANGO_SECURE_SSL_REDIRECT"]


def carregar_prod(monkeypatch, **env):
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "api.exemplo.com")
    for chave in CHAVES:
        monkeypatch.delenv(chave, raising=False)
    for chave, valor in env.items():
        monkeypatch.setenv(chave, valor)
    sys.modules.pop("config.settings.prod", None)
    return importlib.import_module("config.settings.prod")


@pytest.fixture(autouse=True)
def _descarta_modulo():
    yield
    sys.modules.pop("config.settings.prod", None)


def test_prod_e_seguro_por_padrao(monkeypatch):
    prod = carregar_prod(monkeypatch)
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.DEBUG is False


def test_prod_permite_desligar_para_uso_local(monkeypatch):
    prod = carregar_prod(monkeypatch, **dict.fromkeys(CHAVES, "False"))
    assert prod.SESSION_COOKIE_SECURE is False
    assert prod.CSRF_COOKIE_SECURE is False
    assert prod.SECURE_SSL_REDIRECT is False
