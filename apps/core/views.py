import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def health(request):
    """Verifica se a API está de pé e consegue falar com o banco.

    `versao` é o commit em execução; o job de deploy do CI espera esse valor mudar.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check: falha ao conectar no banco")
        return JsonResponse(
            {"status": "erro", "banco": "indisponivel", "versao": settings.VERSAO}, status=503
        )
    return JsonResponse({"status": "ok", "banco": "ok", "versao": settings.VERSAO})
