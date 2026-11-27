from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Convite, Usuario

from .factories import SENHA_PADRAO, ConviteFactory, UsuarioFactory

pytestmark = pytest.mark.django_db

REGISTRO = "/api/v1/auth/registro/"
LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
LOGOUT = "/api/v1/auth/logout/"
SENHA_NOVA = "Uma-senha-bem-forte-42"


def dados_registro(codigo, **extra):
    return {"codigo": codigo, "email": "novo@exemplo.com", "senha": SENHA_NOVA, **extra}


# --- Registro -------------------------------------------------------------------


def test_registro_com_convite_valido(api_client):
    convite = ConviteFactory()
    resposta = api_client.post(
        REGISTRO, dados_registro(convite.codigo, nome="Fulano", email="Novo@Exemplo.com")
    )

    assert resposta.status_code == 201, resposta.json()
    corpo = resposta.json()
    assert corpo["usuario"]["email"] == "novo@exemplo.com"
    assert corpo["usuario"]["nome"] == "Fulano"
    assert {"access", "refresh"} <= corpo.keys()
    assert "senha" not in corpo["usuario"]

    usuario = Usuario.objects.get(email="novo@exemplo.com")
    assert usuario.check_password(SENHA_NOVA)
    convite.refresh_from_db()
    assert convite.usado_por == usuario
    assert convite.usado_em is not None


def test_registro_sem_codigo_falha(api_client):
    resposta = api_client.post(REGISTRO, {"email": "a@exemplo.com", "senha": SENHA_NOVA})
    assert resposta.status_code == 400
    assert "codigo" in resposta.json()
    assert not Usuario.objects.exists()


@pytest.mark.parametrize(
    "preparar",
    [
        pytest.param(lambda: "codigo-que-nao-existe", id="inexistente"),
        pytest.param(
            lambda: ConviteFactory(expira_em=timezone.now() - timedelta(seconds=1)).codigo,
            id="expirado",
        ),
        pytest.param(
            lambda: ConviteFactory(usado_em=timezone.now(), usado_por=UsuarioFactory()).codigo,
            id="usado",
        ),
        pytest.param(lambda: ConviteFactory(email="outra@exemplo.com").codigo, id="outro-email"),
    ],
)
def test_registro_com_convite_invalido(api_client, preparar):
    codigo = preparar()
    resposta = api_client.post(REGISTRO, dados_registro(codigo))
    assert resposta.status_code == 400
    assert "codigo" in resposta.json()
    assert not Usuario.objects.filter(email="novo@exemplo.com").exists()


def test_registro_com_convite_restrito_ao_mesmo_email(api_client):
    convite = ConviteFactory(email="novo@exemplo.com")
    resposta = api_client.post(REGISTRO, dados_registro(convite.codigo))
    assert resposta.status_code == 201


def test_convite_nao_pode_ser_usado_duas_vezes(api_client):
    convite = ConviteFactory()
    assert api_client.post(REGISTRO, dados_registro(convite.codigo)).status_code == 201
    segunda = api_client.post(REGISTRO, dados_registro(convite.codigo, email="segundo@exemplo.com"))
    assert segunda.status_code == 400
    assert Usuario.objects.filter(email="segundo@exemplo.com").count() == 0


def test_registro_com_email_existente_nao_consome_convite(api_client):
    UsuarioFactory(email="novo@exemplo.com")
    convite = ConviteFactory()
    resposta = api_client.post(REGISTRO, dados_registro(convite.codigo, email="NOVO@exemplo.com"))
    assert resposta.status_code == 400
    assert "email" in resposta.json()
    convite.refresh_from_db()
    assert convite.disponivel


def test_registro_rejeita_senha_fraca_sem_consumir_convite(api_client):
    convite = ConviteFactory()
    resposta = api_client.post(REGISTRO, dados_registro(convite.codigo, senha="123"))
    assert resposta.status_code == 400
    assert "senha" in resposta.json()
    assert Convite.objects.disponiveis().filter(pk=convite.pk).exists()


def test_registro_ignora_campos_privilegiados(api_client):
    convite = ConviteFactory()
    dados = dados_registro(convite.codigo, is_staff=True, is_superuser=True)
    assert api_client.post(REGISTRO, dados, format="json").status_code == 201
    usuario = Usuario.objects.get(email="novo@exemplo.com")
    assert not usuario.is_staff
    assert not usuario.is_superuser


# --- Login ----------------------------------------------------------------------


def test_login_devolve_tokens(api_client):
    usuario = UsuarioFactory(email="login@exemplo.com")
    resposta = api_client.post(LOGIN, {"email": "LOGIN@exemplo.com", "senha": SENHA_PADRAO})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert {"access", "refresh"} == corpo.keys()
    assert RefreshToken(corpo["refresh"])["user_id"] == str(usuario.pk)
    usuario.refresh_from_db()
    assert usuario.last_login is not None


def test_login_com_senha_errada(api_client):
    UsuarioFactory(email="login@exemplo.com")
    resposta = api_client.post(LOGIN, {"email": "login@exemplo.com", "senha": "errada"})
    assert resposta.status_code == 401


def test_login_de_usuario_inativo(api_client):
    UsuarioFactory(email="inativo@exemplo.com", is_active=False)
    resposta = api_client.post(LOGIN, {"email": "inativo@exemplo.com", "senha": SENHA_PADRAO})
    assert resposta.status_code == 401


def test_access_token_autentica_requisicoes(api_client):
    usuario = UsuarioFactory()
    access = str(RefreshToken.for_user(usuario).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    resposta = api_client.post(LOGOUT, {"refresh": str(RefreshToken.for_user(usuario))})
    assert resposta.status_code == 204


# --- Refresh --------------------------------------------------------------------


def test_refresh_rotaciona_e_invalida_o_antigo(api_client):
    usuario = UsuarioFactory()
    refresh_antigo = str(RefreshToken.for_user(usuario))

    resposta = api_client.post(REFRESH, {"refresh": refresh_antigo})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["refresh"] != refresh_antigo
    assert "access" in corpo

    reuso = api_client.post(REFRESH, {"refresh": refresh_antigo})
    assert reuso.status_code == 401


def test_refresh_de_usuario_desativado_falha(api_client):
    usuario = UsuarioFactory()
    refresh = str(RefreshToken.for_user(usuario))
    usuario.is_active = False
    usuario.save()
    assert api_client.post(REFRESH, {"refresh": refresh}).status_code == 401


# --- Logout ---------------------------------------------------------------------


def test_logout_invalida_o_refresh(cliente_autenticado, usuario):
    refresh = str(RefreshToken.for_user(usuario))
    assert cliente_autenticado.post(LOGOUT, {"refresh": refresh}).status_code == 204
    assert BlacklistedToken.objects.count() == 1
    assert cliente_autenticado.post(REFRESH, {"refresh": refresh}).status_code == 401


def test_logout_exige_autenticacao(api_client, usuario):
    resposta = api_client.post(LOGOUT, {"refresh": str(RefreshToken.for_user(usuario))})
    assert resposta.status_code == 401


def test_logout_nao_invalida_token_de_outro_usuario(cliente_autenticado, outro_usuario):
    refresh_alheio = str(RefreshToken.for_user(outro_usuario))
    resposta = cliente_autenticado.post(LOGOUT, {"refresh": refresh_alheio})
    assert resposta.status_code == 400
    assert not BlacklistedToken.objects.exists()


def test_logout_com_token_invalido(cliente_autenticado):
    assert cliente_autenticado.post(LOGOUT, {"refresh": "lixo"}).status_code == 400


def test_login_ignora_bearer_invalido_no_header(api_client):
    UsuarioFactory(email="login@exemplo.com")
    api_client.credentials(HTTP_AUTHORIZATION="Bearer token-vencido")
    resposta = api_client.post(LOGIN, {"email": "login@exemplo.com", "senha": SENHA_PADRAO})
    assert resposta.status_code == 200
