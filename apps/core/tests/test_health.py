from unittest import mock

import pytest
from django.db.utils import OperationalError

URL = "/api/health/"


@pytest.mark.django_db
def test_health_ok(client):
    resposta = client.get(URL)
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "banco": "ok"}


@pytest.mark.django_db
def test_health_retorna_503_quando_banco_cai(client):
    with mock.patch("apps.core.views.connection.cursor", side_effect=OperationalError):
        resposta = client.get(URL)
    assert resposta.status_code == 503
    assert resposta.json()["banco"] == "indisponivel"


def test_health_aceita_apenas_get(client):
    assert client.post(URL).status_code == 405
