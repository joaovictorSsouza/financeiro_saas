from django.contrib import admin

from .models import (
    Categoria,
    ContaFinanceira,
    Ocorrencia,
    Orcamento,
    Recorrencia,
    RegraCategoria,
    Transacao,
)
from .services import transacoes as servico_transacoes
from .services.ocorrencias import sincronizar_recorrencia


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


@admin.register(Transacao)
class TransacaoAdmin(AdminDoUsuario):
    """Salvar e apagar passam pelos serviços para manter o saldo das contas manuais."""

    list_display = ("data", "descricao", "valor_centavos", "tipo", "categoria", "conta", "usuario")
    list_filter = ("usuario", "tipo", "origem", "ignorada", "dividida", "conta__tipo")
    search_fields = ("descricao", "descricao_original", "pluggy_transaction_id")
    date_hierarchy = "data"
    list_select_related = ("usuario", "categoria", "conta")
    raw_id_fields = ("conta", "categoria", "transacao_pai")

    def save_model(self, request, obj, form, change):
        dados = {campo: getattr(obj, campo) for campo in form.changed_data}
        if change:
            original = Transacao.objects.get(pk=obj.pk)
            servico_transacoes.atualizar_transacao(original, **dados)
        else:
            campos = {f: getattr(obj, f) for f in form.cleaned_data if f != "usuario"}
            novo = servico_transacoes.criar_transacao(obj.usuario, **campos)
            obj.pk = novo.pk

    def delete_model(self, request, obj):
        servico_transacoes.excluir_transacao(obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            servico_transacoes.excluir_transacao(obj)


@admin.register(RegraCategoria)
class RegraCategoriaAdmin(AdminDoUsuario):
    list_display = ("valor", "operador", "categoria", "prioridade", "usuario")
    list_filter = ("usuario", "operador")
    search_fields = ("valor",)
    list_select_related = ("usuario", "categoria")
    raw_id_fields = ("categoria",)


@admin.register(Recorrencia)
class RecorrenciaAdmin(AdminDoUsuario):
    list_display = ("nome", "tipo", "valor_previsto_centavos", "dia_do_mes", "ativa", "usuario")
    list_filter = ("usuario", "tipo", "ativa")
    search_fields = ("nome",)
    list_select_related = ("usuario", "categoria")
    raw_id_fields = ("categoria", "conta_padrao")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        sincronizar_recorrencia(obj)


@admin.register(Ocorrencia)
class OcorrenciaAdmin(AdminDoUsuario):
    list_display = ("recorrencia", "mes_referencia", "vencimento", "valor_centavos", "status")
    list_filter = ("usuario", "status", "mes_referencia")
    search_fields = ("recorrencia__nome",)
    list_select_related = ("usuario", "recorrencia")
    raw_id_fields = ("recorrencia", "transacao")


@admin.register(Orcamento)
class OrcamentoAdmin(AdminDoUsuario):
    list_display = ("categoria", "mes_referencia", "limite_centavos", "usuario")
    list_filter = ("usuario", "mes_referencia")
    list_select_related = ("usuario", "categoria")
    raw_id_fields = ("categoria",)
