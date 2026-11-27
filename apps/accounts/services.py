"""Regras de negócio de contas, independentes da camada HTTP.

`gerar_tokens` é o ponto único de emissão de JWT: o login por senha usa hoje e o
login por passkey (WebAuthn, fase futura) vai usar o mesmo, sem duplicar lógica.
"""

from django.contrib.auth.models import update_last_login
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from .managers import normalizar_email
from .models import Convite, Usuario
from .signals import usuario_registrado


class ConviteInvalido(Exception):
    """Código inexistente, expirado, já usado ou de outro e-mail."""


class EmailJaCadastrado(Exception):
    pass


def gerar_tokens(usuario: Usuario) -> dict[str, str]:
    refresh = RefreshToken.for_user(usuario)
    update_last_login(None, usuario)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


@transaction.atomic
def registrar_com_convite(*, codigo: str, email: str, senha: str, nome: str = "") -> Usuario:
    """Cria o usuário e consome o convite na mesma transação.

    `select_for_update` impede que duas requisições simultâneas usem o mesmo convite.
    Qualquer erro desfaz tudo, então o convite só é consumido se o usuário for criado.
    """
    email = normalizar_email(email)
    convite = Convite.objects.select_for_update().filter(codigo=codigo).first()
    if convite is None or not convite.disponivel or not convite.aceita_email(email):
        raise ConviteInvalido

    if Usuario.objects.filter(email=email).exists():
        raise EmailJaCadastrado

    usuario = Usuario.objects.create_user(email=email, password=senha, nome=nome)
    convite.marcar_como_usado(usuario)
    usuario_registrado.send(sender=Usuario, usuario=usuario)
    return usuario
