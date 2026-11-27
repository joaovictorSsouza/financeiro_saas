from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import Convite, Usuario


class UsuarioCreationForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ("email", "nome")


class UsuarioChangeForm(UserChangeForm):
    class Meta:
        model = Usuario
        fields = "__all__"


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    form = UsuarioChangeForm
    add_form = UsuarioCreationForm
    ordering = ("email",)
    list_display = ("email", "nome", "is_active", "is_staff", "criado_em")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("email", "nome")
    readonly_fields = ("id", "criado_em", "atualizado_em", "last_login")
    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        ("Dados pessoais", {"fields": ("nome",)}),
        (
            "Permissões",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Datas", {"fields": ("last_login", "criado_em", "atualizado_em")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "nome", "password1", "password2"),
            },
        ),
    )


@admin.register(Convite)
class ConviteAdmin(admin.ModelAdmin):
    list_display = ("codigo", "email", "situacao", "expira_em", "criado_por", "usado_por")
    list_filter = ("expira_em", "usado_em")
    search_fields = ("codigo", "email", "usado_por__email")
    readonly_fields = ("id", "codigo", "criado_por", "usado_por", "usado_em", "criado_em")
    fields = ("id", "codigo", "email", "expira_em", "criado_por", "usado_por", "usado_em")

    @admin.display(description="situação")
    def situacao(self, obj: Convite) -> str:
        if obj.usado:
            return "usado"
        if obj.expirado:
            return "expirado"
        return "disponível"

    def save_model(self, request, obj, form, change):
        if not change and obj.criado_por_id is None:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)
