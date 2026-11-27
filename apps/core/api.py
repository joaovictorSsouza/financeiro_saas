"""Bases para as APIs de domínio: tudo filtrado pelo usuário autenticado."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError, RestrictedError
from rest_framework import serializers, status, viewsets
from rest_framework.exceptions import APIException


class Conflito(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "O recurso está em uso."
    default_code = "conflito"


class DoUsuarioMixin:
    """Queryset sempre do `request.user` e `usuario` gravado no servidor.
    Recurso de outro usuário → 404. Defina `model` e `serializer_class`."""

    model = None
    mensagem_protegido = "Este registro está em uso e não pode ser apagado."

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # geração do schema OpenAPI
            return self.model.objects.none()
        return self.model.objects.filter(usuario=self.request.user)

    def perform_create(self, serializer):
        serializer.save(usuario=self.request.user)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except (ProtectedError, RestrictedError) as erro:
            raise Conflito(self.mensagem_protegido) from erro


class DoUsuarioViewSet(DoUsuarioMixin, viewsets.ModelViewSet):
    pass


class DoUsuarioSomenteLeituraViewSet(DoUsuarioMixin, viewsets.ReadOnlyModelViewSet):
    pass


class CampoDoUsuario(serializers.PrimaryKeyRelatedField):
    """FK que só aceita objetos do usuário autenticado; id alheio → 400 (objeto não existe)."""

    def __init__(self, model, **kwargs):
        self.model = model
        kwargs.setdefault("queryset", model.objects.none())
        super().__init__(**kwargs)

    def get_queryset(self):
        request = self.context.get("request")
        if request is None or not request.user.is_authenticated:
            return self.model.objects.none()
        return self.model.objects.filter(usuario=request.user)


def validar_com_clean(serializer, attrs, model):
    """Roda o `clean()` do model com os dados do serializer (validações de domínio)."""
    instancia = model(**{**_valores_atuais(serializer.instance), **attrs})
    instancia.pk = serializer.instance.pk if serializer.instance else None
    instancia.usuario = serializer.context["request"].user
    try:
        instancia.clean()
    except DjangoValidationError as erro:
        raise serializers.ValidationError(erro.message_dict) from erro


def _valores_atuais(instancia) -> dict:
    if instancia is None:
        return {}
    return {
        f.name: getattr(instancia, f.name)
        for f in instancia._meta.concrete_fields
        if not f.primary_key and f.name != "usuario"
    }
