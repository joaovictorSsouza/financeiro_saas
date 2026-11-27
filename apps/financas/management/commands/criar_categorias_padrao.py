from django.core.management.base import BaseCommand, CommandError

from apps.accounts.managers import normalizar_email
from apps.accounts.models import Usuario
from apps.financas.services.categorias import criar_categorias_padrao


class Command(BaseCommand):
    help = "Cria as categorias padrão que faltam para um usuário existente (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("email", help="E-mail do usuário.")

    def handle(self, *args, **opcoes):
        try:
            usuario = Usuario.objects.get(email=normalizar_email(opcoes["email"]))
        except Usuario.DoesNotExist as erro:
            raise CommandError(f"Usuário {opcoes['email']} não encontrado.") from erro
        criadas = criar_categorias_padrao(usuario)
        self.stdout.write(self.style.SUCCESS(f"{criadas} categoria(s) criada(s)."))
