from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.managers import normalizar_email
from apps.accounts.models import Usuario
from apps.financas.datas import parse_mes
from apps.financas.services.ocorrencias import gerar_ocorrencias


class Command(BaseCommand):
    help = "Gera as ocorrências do mês a partir das recorrências ativas (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("--mes", help="Mês no formato AAAA-MM (padrão: mês atual).")
        parser.add_argument("--email", help="Só para este usuário (padrão: todos os ativos).")

    def handle(self, *args, **opcoes):
        try:
            mes = parse_mes(opcoes["mes"]) if opcoes["mes"] else timezone.localdate()
        except ValueError as erro:
            raise CommandError(f"--mes inválido: {erro}") from erro

        usuarios = Usuario.objects.filter(is_active=True)
        if opcoes["email"]:
            usuarios = usuarios.filter(email=normalizar_email(opcoes["email"]))
            if not usuarios.exists():
                raise CommandError(f"Usuário {opcoes['email']} não encontrado.")

        total = sum(gerar_ocorrencias(u, mes) for u in usuarios)
        self.stdout.write(self.style.SUCCESS(f"{total} ocorrência(s) criada(s) em {mes:%m/%Y}."))
