from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.core.rls import listar_tabelas


class Command(BaseCommand):
    help = (
        "Mostra o usuário do banco e, por tabela do schema public, o dono e se o RLS está "
        "ligado. Falha se alguma tabela estiver sem RLS, com FORCE ou com outro dono."
    )

    def handle(self, *args, **opcoes):
        if connection.vendor != "postgresql":
            raise CommandError("Só faz sentido em Postgres.")
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
            usuario, superusuario, bypass = cursor.fetchone()
        self.stdout.write(
            f"Usuário do banco: {usuario} (superusuário: {superusuario}, BYPASSRLS: {bypass})"
        )

        problemas = []
        for t in listar_tabelas(connection):
            situacao = "RLS ok" if t["relrowsecurity"] else "SEM RLS"
            if t["relforcerowsecurity"]:
                situacao += " + FORCE"
            self.stdout.write(f"  {t['relname']:<45} dono={t['dono']:<20} {situacao}")
            if not t["relrowsecurity"]:
                problemas.append(f"{t['relname']}: sem RLS")
            if t["relforcerowsecurity"]:
                problemas.append(f"{t['relname']}: FORCE ligado (bloquearia o Django)")
            if not t["pode_alterar"]:
                problemas.append(f"{t['relname']}: o dono não é {usuario}")

        if problemas:
            raise CommandError("Problemas encontrados:\n" + "\n".join(problemas))
        self.stdout.write(self.style.SUCCESS("Todas as tabelas do public têm RLS."))
