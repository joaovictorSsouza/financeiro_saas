import pytest
from django.core.management import call_command
from django.db import connection

from apps.core.rls import ao_migrar, habilitar_rls, listar_tabelas
from apps.financas.tests.factories import TransacaoFactory

pytestmark = pytest.mark.django_db


def test_todas_as_tabelas_do_public_tem_rls():
    tabelas = listar_tabelas(connection)
    nomes = {t["relname"] for t in tabelas}
    # Tabelas do Django e de terceiros também precisam estar cobertas.
    esperadas = {
        "accounts_usuario",
        "auth_group",
        "django_admin_log",
        "django_content_type",
        "django_session",
        "django_migrations",
        "token_blacklist_outstandingtoken",
        "token_blacklist_blacklistedtoken",
        "financas_transacao",
    }
    assert esperadas <= nomes
    sem_rls = sorted(t["relname"] for t in tabelas if not t["relrowsecurity"])
    assert sem_rls == [], f"Tabelas sem RLS: {sem_rls}"
    com_force = sorted(t["relname"] for t in tabelas if t["relforcerowsecurity"])
    assert com_force == [], "FORCE bloquearia o próprio Django"


def test_django_e_dono_das_tabelas():
    assert all(t["pode_alterar"] for t in listar_tabelas(connection))


def test_habilitar_rls_cobre_tabela_nova_e_e_idempotente():
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE public.teste_rls_nova (id int)")
    assert habilitar_rls(connection) == ["teste_rls_nova"]
    assert habilitar_rls(connection) == []


def test_sinal_post_migrate_cria_tabela_de_cache_com_rls(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
        }
    }
    ao_migrar(sender=None, using="default")
    cache = {t["relname"]: t for t in listar_tabelas(connection)}["django_cache"]
    assert cache["relrowsecurity"]


def _pode_criar_papel() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user"
        )
        return cursor.fetchone()[0]


def test_papel_sem_policy_nao_le_nada_mas_o_dono_le(usuario):
    """Simula o `anon` do Supabase: tem GRANT de SELECT, mas o RLS sem policy bloqueia."""
    if not _pode_criar_papel():
        pytest.skip("o usuário do banco de testes não pode criar papéis")
    TransacaoFactory(usuario=usuario)
    with connection.cursor() as cursor:
        cursor.execute("CREATE ROLE teste_anon_rls NOLOGIN")
        cursor.execute("GRANT USAGE ON SCHEMA public TO teste_anon_rls")
        cursor.execute("GRANT SELECT ON financas_transacao, accounts_usuario TO teste_anon_rls")
        cursor.execute("SET LOCAL ROLE teste_anon_rls")
        cursor.execute("SELECT count(*) FROM financas_transacao")
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT count(*) FROM accounts_usuario")
        assert cursor.fetchone()[0] == 0
        cursor.execute("RESET ROLE")
        cursor.execute("SELECT count(*) FROM financas_transacao")
        assert cursor.fetchone()[0] == 1


def test_comando_verificar_rls(capsys):
    call_command("verificar_rls")
    saida = capsys.readouterr().out
    assert "Usuário do banco:" in saida
    assert "financas_transacao" in saida
    assert "Todas as tabelas do public têm RLS." in saida
