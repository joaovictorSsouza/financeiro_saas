from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.managers import normalizar_email
from apps.accounts.models import DIAS_VALIDADE_CONVITE, Convite, Usuario


class Command(BaseCommand):
    help = "Cria um convite de cadastro e imprime o código."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="", help="Restringe o convite a este e-mail.")
        parser.add_argument(
            "--dias",
            type=int,
            default=DIAS_VALIDADE_CONVITE,
            help=f"Dias de validade (padrão: {DIAS_VALIDADE_CONVITE}).",
        )
        parser.add_argument(
            "--criado-por", default="", help="E-mail do usuário que está convidando."
        )

    def handle(self, *args, **opcoes):
        if opcoes["dias"] < 1:
            raise CommandError("--dias deve ser pelo menos 1.")

        criado_por = None
        if opcoes["criado_por"]:
            try:
                criado_por = Usuario.objects.get(email=normalizar_email(opcoes["criado_por"]))
            except Usuario.DoesNotExist as erro:
                raise CommandError(f"Usuário {opcoes['criado_por']} não encontrado.") from erro

        convite = Convite.objects.create(
            email=opcoes["email"],
            criado_por=criado_por,
            expira_em=timezone.now() + timedelta(days=opcoes["dias"]),
        )
        self.stdout.write(self.style.SUCCESS(f"Convite criado: {convite.codigo}"))
        self.stdout.write(f"E-mail: {convite.email or 'qualquer'}")
        self.stdout.write(f"Expira em: {timezone.localtime(convite.expira_em):%d/%m/%Y %H:%M}")
