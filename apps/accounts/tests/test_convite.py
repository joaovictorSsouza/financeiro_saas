from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.accounts.models import Convite

from .factories import ConviteFactory, UsuarioFactory

pytestmark = pytest.mark.django_db


def test_convite_novo_esta_disponivel_por_7_dias():
    convite = ConviteFactory()
    assert len(convite.codigo) >= 20
    assert convite.disponivel
    assert timedelta(days=6) < convite.expira_em - timezone.now() <= timedelta(days=7)


def test_codigos_sao_unicos():
    assert ConviteFactory().codigo != ConviteFactory().codigo


def test_convite_expirado_e_usado_nao_estao_disponiveis():
    expirado = ConviteFactory(expira_em=timezone.now() - timedelta(minutes=1))
    usado = ConviteFactory()
    usado.marcar_como_usado(UsuarioFactory())
    disponivel = ConviteFactory()

    assert not expirado.disponivel
    assert not usado.disponivel
    assert list(Convite.objects.disponiveis()) == [disponivel]


def test_convite_com_email_aceita_apenas_esse_email():
    convite = ConviteFactory(email="Convidado@Exemplo.com")
    assert convite.email == "convidado@exemplo.com"
    assert convite.aceita_email("CONVIDADO@exemplo.com")
    assert not convite.aceita_email("outro@exemplo.com")


def test_convite_sem_email_aceita_qualquer_email():
    assert ConviteFactory(email="").aceita_email("qualquer@exemplo.com")


def test_comando_criar_convite():
    criador = UsuarioFactory(email="admin@exemplo.com")
    saida = StringIO()
    call_command(
        "criar_convite",
        "--email=amigo@exemplo.com",
        "--dias=3",
        "--criado-por=admin@exemplo.com",
        stdout=saida,
    )

    convite = Convite.objects.get()
    assert convite.codigo in saida.getvalue()
    assert convite.email == "amigo@exemplo.com"
    assert convite.criado_por == criador
    assert timedelta(days=2) < convite.expira_em - timezone.now() <= timedelta(days=3)


def test_comando_criar_convite_sem_argumentos():
    call_command("criar_convite", stdout=StringIO())
    convite = Convite.objects.get()
    assert convite.email == ""
    assert convite.criado_por is None


def test_comando_criar_convite_com_criador_inexistente():
    with pytest.raises(CommandError, match="não encontrado"):
        call_command("criar_convite", "--criado-por=ninguem@exemplo.com", stdout=StringIO())


def test_comando_criar_convite_rejeita_dias_invalidos():
    with pytest.raises(CommandError):
        call_command("criar_convite", "--dias=0", stdout=StringIO())


def test_admin_lista_convites_e_define_criador(client):
    admin = UsuarioFactory(is_staff=True, is_superuser=True)
    client.force_login(admin)
    ConviteFactory()
    assert client.get("/admin/accounts/convite/").status_code == 200

    resposta = client.post(
        "/admin/accounts/convite/add/",
        {"email": "", "expira_em_0": "01/01/2099", "expira_em_1": "10:00:00"},
    )
    assert resposta.status_code == 302, resposta.content
    assert Convite.objects.filter(criado_por=admin).exists()
