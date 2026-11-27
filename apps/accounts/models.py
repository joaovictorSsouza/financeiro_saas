import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.core.models import ModeloBase

from .managers import UsuarioManager, normalizar_email

DIAS_VALIDADE_CONVITE = 7


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


def gerar_codigo_convite() -> str:
    return secrets.token_urlsafe(16)


def expiracao_padrao_convite():
    return timezone.now() + timedelta(days=DIAS_VALIDADE_CONVITE)


class ConviteQuerySet(models.QuerySet):
    def disponiveis(self):
        """Convites ainda não usados e não expirados."""
        return self.filter(usado_em__isnull=True, expira_em__gt=timezone.now())


class Convite(ModeloBase):
    """Convite de cadastro. O registro só é aceito com um código válido e não usado."""

    codigo = models.CharField(
        "código", max_length=64, unique=True, default=gerar_codigo_convite, editable=False
    )
    email = models.EmailField(
        "e-mail",
        blank=True,
        help_text="Opcional. Se preenchido, só este e-mail pode usar o convite.",
    )
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="criado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="convites_criados",
    )
    usado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="convites_usados",
    )
    expira_em = models.DateTimeField("expira em", default=expiracao_padrao_convite)
    usado_em = models.DateTimeField("usado em", null=True, blank=True)

    objects = ConviteQuerySet.as_manager()

    class Meta(ModeloBase.Meta):
        verbose_name = "convite"
        verbose_name_plural = "convites"

    def __str__(self) -> str:
        return f"{self.codigo} ({self.email or 'qualquer e-mail'})"

    def save(self, *args, **kwargs):
        self.email = normalizar_email(self.email)
        super().save(*args, **kwargs)

    @property
    def usado(self) -> bool:
        return self.usado_em is not None

    @property
    def expirado(self) -> bool:
        return self.expira_em <= timezone.now()

    @property
    def disponivel(self) -> bool:
        return not self.usado and not self.expirado

    def aceita_email(self, email: str) -> bool:
        return not self.email or self.email == normalizar_email(email)

    def marcar_como_usado(self, usuario) -> None:
        self.usado_por = usuario
        self.usado_em = timezone.now()
        self.save(update_fields=["usado_por", "usado_em", "atualizado_em"])
