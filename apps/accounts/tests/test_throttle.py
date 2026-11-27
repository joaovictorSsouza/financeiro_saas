import pytest

from .factories import ConviteFactory, UsuarioFactory

pytestmark = pytest.mark.django_db


def test_login_e_limitado_por_ip(api_client):
    UsuarioFactory(email="alvo@exemplo.com")
    dados = {"email": "alvo@exemplo.com", "senha": "errada"}
    respostas = [api_client.post("/api/v1/auth/login/", dados).status_code for _ in range(6)]
    assert respostas[:5] == [401] * 5
    assert respostas[5] == 429


def test_registro_e_limitado_por_ip(api_client):
    dados = {"codigo": "x", "email": "a@exemplo.com", "senha": "Senha-forte-123"}
    respostas = [api_client.post("/api/v1/auth/registro/", dados).status_code for _ in range(11)]
    assert respostas[:10] == [400] * 10
    assert respostas[10] == 429
    # mesmo com convite válido, continua bloqueado
    dados["codigo"] = ConviteFactory().codigo
    assert api_client.post("/api/v1/auth/registro/", dados).status_code == 429
