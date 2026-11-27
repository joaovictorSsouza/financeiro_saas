"""Domínio financeiro: categorias, contas, transações, regras, recorrências,
ocorrências e orçamentos.

Todo model pertence a um usuário (FK `usuario`) e todo valor monetário é inteiro em
centavos. As regras de negócio ficam em `services.py`.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import ModeloBase

validar_cor_hex = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use uma cor hexadecimal, ex.: #1A2B3C.")


class Categoria(ModeloBase):
    """Categoria de gasto ou receita. No máximo 2 níveis (pai > subcategoria)."""

    class Tipo(models.TextChoices):
        GASTO = "gasto", "Gasto"
        RECEITA = "receita", "Receita"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categorias"
    )
    nome = models.CharField("nome", max_length=80)
    icone = models.CharField("ícone", max_length=50, blank=True)
    cor = models.CharField("cor", max_length=7, default="#9E9E9E", validators=[validar_cor_hex])
    categoria_pai = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategorias",
        verbose_name="categoria pai",
    )
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices, default=Tipo.GASTO)
    ativa = models.BooleanField("ativa", default=True)

    class Meta(ModeloBase.Meta):
        verbose_name = "categoria"
        verbose_name_plural = "categorias"
        ordering = ["nome"]
        constraints = [
            # nulls_distinct=False: sem isso duas categorias raiz com o mesmo nome passariam,
            # porque no Postgres NULL != NULL numa constraint única.
            models.UniqueConstraint(
                fields=["usuario", "nome", "categoria_pai"],
                nulls_distinct=False,
                name="categoria_unica_por_usuario_nome_pai",
            ),
        ]
        indexes = [models.Index(fields=["usuario", "tipo"], name="categoria_usuario_tipo")]

    def __str__(self):
        return f"{self.categoria_pai.nome} > {self.nome}" if self.categoria_pai_id else self.nome

    @property
    def raiz(self) -> "Categoria":
        return self.categoria_pai if self.categoria_pai_id else self

    def clean(self):
        pai = self.categoria_pai
        if pai is None:
            return
        if pai.usuario_id != self.usuario_id:
            raise ValidationError({"categoria_pai": "Categoria pai inválida."})
        if pai.pk == self.pk:
            raise ValidationError({"categoria_pai": "Uma categoria não pode ser pai dela mesma."})
        if pai.categoria_pai_id is not None:
            raise ValidationError({"categoria_pai": "Só são permitidos 2 níveis de categoria."})
        if self.pk and self.subcategorias.exists():
            raise ValidationError(
                {"categoria_pai": "Uma categoria com subcategorias não pode ter pai."}
            )
        if pai.tipo != self.tipo:
            raise ValidationError({"tipo": "A subcategoria deve ter o mesmo tipo da pai."})


class ContaFinanceira(ModeloBase):
    """Conta corrente, poupança, cartão, carteira... Sem `pluggy_account_id` = conta manual."""

    class Tipo(models.TextChoices):
        CORRENTE = "corrente", "Conta corrente"
        POUPANCA = "poupanca", "Poupança"
        CARTAO_CREDITO = "cartao_credito", "Cartão de crédito"
        CARTEIRA = "carteira", "Carteira"
        OUTRO = "outro", "Outro"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contas_financeiras"
    )
    nome = models.CharField("nome", max_length=80)
    tipo = models.CharField("tipo", max_length=20, choices=Tipo.choices, default=Tipo.CORRENTE)
    instituicao = models.CharField("instituição", max_length=80, blank=True)
    saldo_centavos = models.BigIntegerField("saldo (centavos)", default=0)
    limite_centavos = models.BigIntegerField("limite (centavos)", null=True, blank=True)
    # Integração Pluggy (fase 2, app `bancos`). Os ids da Pluggy são UUIDs; a conexão
    # (item) fica como UUID solto até existir o model de conexão.
    conexao_pluggy_id = models.UUIDField("conexão Pluggy (item)", null=True, blank=True)
    pluggy_account_id = models.UUIDField("conta Pluggy", null=True, blank=True)
    ativa = models.BooleanField("ativa", default=True)

    class Meta(ModeloBase.Meta):
        verbose_name = "conta financeira"
        verbose_name_plural = "contas financeiras"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["pluggy_account_id"],
                condition=models.Q(pluggy_account_id__isnull=False),
                name="conta_pluggy_account_id_unico",
            ),
        ]
        indexes = [models.Index(fields=["usuario", "ativa"], name="conta_usuario_ativa")]

    def __str__(self):
        return self.nome

    @property
    def manual(self) -> bool:
        return self.pluggy_account_id is None
