from django.conf import settings
from rest_framework.permissions import BasePermission


class AutenticadoOuDebug(BasePermission):
    """Libera em DEBUG; fora dele, exige usuário autenticado."""

    def has_permission(self, request, view) -> bool:
        return bool(settings.DEBUG or (request.user and request.user.is_authenticated))
