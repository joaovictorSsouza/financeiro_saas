from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Núcleo"

    def ready(self):
        from .rls import ao_migrar

        # sender=self: roda uma vez por `migrate`, depois de todas as migrations.
        post_migrate.connect(ao_migrar, sender=self, dispatch_uid="core_habilitar_rls")
