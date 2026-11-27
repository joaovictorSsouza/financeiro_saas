"""Row Level Security em todas as tabelas do schema public (Supabase).

O Supabase expõe o schema public pela Data API (PostgREST) com a chave anon. Com RLS
ligado e nenhuma policy, essa API não lê nem grava nada. O Django conecta com o dono das
tabelas, e o RLS não se aplica ao dono (não usamos FORCE ROW LEVEL SECURITY), então a
aplicação continua funcionando normalmente.

`habilitar_rls` roda no sinal post_migrate (ver CoreConfig), a cada `migrate`, e cobre
qualquer tabela nova automaticamente. Só roda em Postgres.
"""

import logging

from django.core.management import call_command
from django.db import connections

logger = logging.getLogger(__name__)

SQL_TABELAS = """
    SELECT c.relname,
           pg_get_userbyid(c.relowner) AS dono,
           c.relrowsecurity,
           c.relforcerowsecurity,
           pg_has_role(current_user, c.relowner, 'MEMBER') AS pode_alterar
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
     ORDER BY c.relname
"""


def listar_tabelas(conexao) -> list[dict]:
    with conexao.cursor() as cursor:
        cursor.execute(SQL_TABELAS)
        colunas = [c[0] for c in cursor.description]
        return [dict(zip(colunas, linha, strict=True)) for linha in cursor.fetchall()]


def habilitar_rls(conexao) -> list[str]:
    """Liga o RLS (sem policies) nas tabelas do public que ainda não têm. Retorna os nomes."""
    if conexao.vendor != "postgresql":
        return []
    habilitadas = []
    with conexao.cursor() as cursor:
        for tabela in listar_tabelas(conexao):
            if tabela["relrowsecurity"]:
                continue
            if not tabela["pode_alterar"]:
                logger.warning(
                    "RLS: sem permissão para alterar a tabela %s (dono: %s)",
                    tabela["relname"],
                    tabela["dono"],
                )
                continue
            nome = conexao.ops.quote_name(tabela["relname"])
            cursor.execute(f"ALTER TABLE public.{nome} ENABLE ROW LEVEL SECURITY")
            habilitadas.append(tabela["relname"])
    if habilitadas:
        logger.info("RLS habilitado em: %s", ", ".join(habilitadas))
    return habilitadas


def ao_migrar(sender, using="default", **kwargs):
    """post_migrate: garante a tabela do DatabaseCache e liga o RLS em tudo.

    O `createcachetable` vem antes porque o entrypoint e o banco de testes só criam a
    tabela de cache depois do migrate; assim ela já nasce coberta. É idempotente.
    """
    conexao = connections[using]
    if conexao.vendor != "postgresql":
        return
    call_command("createcachetable", database=using, verbosity=0)
    habilitar_rls(conexao)
