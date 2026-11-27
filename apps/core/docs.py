from django.contrib.auth.views import redirect_to_login
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.exceptions import NotAuthenticated, PermissionDenied


class SwaggerView(SpectacularSwaggerView):
    """Swagger UI que, sem login, manda para o login do admin em vez de responder 403."""

    def handle_exception(self, exc):
        if isinstance(exc, NotAuthenticated | PermissionDenied):
            return redirect_to_login(self.request.get_full_path(), login_url="admin:login")
        return super().handle_exception(exc)
