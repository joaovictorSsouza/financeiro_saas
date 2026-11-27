import pytest
from django.core.management import call_command

from apps.accounts.tests.factories import UsuarioFactory

pytestmark = pytest.mark.django_db


def test_docs_sem_login_redireciona_para_admin(client):
    resposta = client.get("/api/docs/")
    assert resposta.status_code == 302
    assert resposta["Location"].startswith("/admin/login/")


def test_schema_sem_login_e_negado(client):
    assert client.get("/api/schema/").status_code in (401, 403)


def test_docs_com_sessao_do_admin(client):
    client.force_login(UsuarioFactory())
    assert client.get("/api/docs/").status_code == 200
    assert client.get("/api/schema/").status_code == 200


def test_docs_liberados_em_debug(client, settings):
    settings.DEBUG = True
    assert client.get("/api/docs/").status_code == 200


def test_schema_openapi_valido_sem_avisos(tmp_path):
    call_command(
        "spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "schema.yml")
    )


def test_cors_libera_apenas_origens_configuradas(client, settings):
    settings.CORS_ALLOWED_ORIGINS = ["https://app.exemplo.com"]
    ok = client.get("/api/health/", HTTP_ORIGIN="https://app.exemplo.com")
    assert ok["Access-Control-Allow-Origin"] == "https://app.exemplo.com"
    negado = client.get("/api/health/", HTTP_ORIGIN="https://malicioso.com")
    assert "Access-Control-Allow-Origin" not in negado
