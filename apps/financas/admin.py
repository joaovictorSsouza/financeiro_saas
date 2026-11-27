from django.contrib import admin

from .models import Categoria, ContaFinanceira


class AdminDoUsuario(admin.ModelAdmin):
    """Base: filtro por usuário e campos de auditoria somente leitura."""

    list_filter = ("usuario",)
    list_select_related = ("usuario",)
    readonly_fields = ("id", "criado_em", "atualizado_em")
    autocomplete_fields = ("usuario",)


@admin.register(Categoria)
class CategoriaAdmin(AdminDoUsuario):
    list_display = ("nome", "categoria_pai", "tipo", "ativa", "usuario")
    list_filter = ("usuario", "tipo", "ativa")
    search_fields = ("nome",)
    list_select_related = ("usuario", "categoria_pai")
    raw_id_fields = ("categoria_pai",)


@admin.register(ContaFinanceira)
class ContaFinanceiraAdmin(AdminDoUsuario):
    list_display = ("nome", "tipo", "instituicao", "saldo_centavos", "ativa", "usuario")
    list_filter = ("usuario", "tipo", "ativa")
    search_fields = ("nome", "instituicao", "pluggy_account_id")
