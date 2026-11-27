from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from apps.core.models import ModeloBase

from .managers import UsuarioManager, normalizar_email


class Usuario(ModeloBase, AbstractBaseUser, PermissionsMixin):
    """Usuário do sistema. Login por e-mail, sem username.

    Passkeys/WebAuthn (fase futura) entrarão como um model separado
    (`CredencialPasskey`, FK para Usuario), sem alterar este model.
    """

    email = models.EmailField("e-mail", unique=True)
    nome = models.CharField("nome", max_length=150, blank=True)
    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField(
        "membro da equipe",
        default=False,
        help_text="Pode acessar o admin do Django.",
    )

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta(ModeloBase.Meta):
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self) -> str:
        return self.email

    def clean(self):
        super().clean()
        self.email = normalizar_email(self.email)

    def save(self, *args, **kwargs):
        self.email = normalizar_email(self.email)
        super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        return self.nome or self.email

    def get_short_name(self) -> str:
        return (self.nome.split() or [self.email])[0]
