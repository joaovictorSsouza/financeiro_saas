import uuid

import pytest
from django.db import IntegrityError

from apps.accounts.models import Usuario

pytestmark = pytest.mark.django_db


def test_cria_usuario_com_email_normalizado():
    usuario = Usuario.objects.create_user(email="  Fulano@Exemplo.COM ", password="x-senha-123")
    assert usuario.email == "fulano@exemplo.com"
    assert isinstance(usuario.id, uuid.UUID)
    assert usuario.check_password("x-senha-123")
    assert not usuario.is_staff
    assert not usuario.is_superuser


def test_email_e_obrigatorio():
    with pytest.raises(ValueError, match="e-mail"):
        Usuario.objects.create_user(email="", password="x")


def test_email_unico_sem_diferenciar_maiusculas():
    Usuario.objects.create_user(email="a@exemplo.com", password="x")
    with pytest.raises(IntegrityError):
        Usuario.objects.create_user(email="A@EXEMPLO.com", password="x")


def test_cria_superusuario():
    admin = Usuario.objects.create_superuser(email="admin@exemplo.com", password="x")
    assert admin.is_staff
    assert admin.is_superuser


def test_superusuario_exige_flags():
    with pytest.raises(ValueError):
        Usuario.objects.create_superuser(email="a@exemplo.com", password="x", is_staff=False)


def test_login_por_email_sem_diferenciar_maiusculas(client):
    Usuario.objects.create_user(email="b@exemplo.com", password="x-senha-123")
    assert client.login(email="B@Exemplo.com", password="x-senha-123")


def test_nao_tem_username():
    assert not hasattr(Usuario, "username")
    assert Usuario.USERNAME_FIELD == "email"
