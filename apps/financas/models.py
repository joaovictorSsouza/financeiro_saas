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

from .datas import meses_entre, primeiro_dia, somar_meses, vencimento_no_mes

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


class Transacao(ModeloBase):
    """Movimento numa conta. `valor_centavos` é sempre positivo; o sentido está em `tipo`.

    Uma entrada com categoria de gasto é um estorno (abate o gasto da categoria).
    Divisão: a original fica com `dividida=True` (sai das somas) e cada parte vira uma
    transação filha (`transacao_pai`), com a própria categoria.
    """

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SAIDA = "saida", "Saída"

    class Origem(models.TextChoices):
        MANUAL = "manual", "Manual"
        BANCO = "banco", "Banco"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transacoes"
    )
    conta = models.ForeignKey(
        ContaFinanceira, on_delete=models.PROTECT, related_name="transacoes", verbose_name="conta"
    )
    data = models.DateField("data")
    descricao = models.CharField("descrição", max_length=255)
    descricao_original = models.TextField("descrição original (banco)", blank=True)
    valor_centavos = models.BigIntegerField("valor (centavos)")
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices)
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transacoes",
        verbose_name="categoria",
    )
    categoria_definida_manualmente = models.BooleanField(
        "categoria definida manualmente", default=False
    )
    origem = models.CharField("origem", max_length=10, choices=Origem.choices, default="manual")
    pluggy_transaction_id = models.UUIDField("transação Pluggy", null=True, blank=True)
    parcela_atual = models.PositiveSmallIntegerField("parcela atual", null=True, blank=True)
    total_parcelas = models.PositiveSmallIntegerField("total de parcelas", null=True, blank=True)
    ignorada = models.BooleanField(
        "ignorada",
        default=False,
        help_text="Fica fora de receitas e despesas (ex.: transferência entre contas próprias, "
        "pagamento da fatura do cartão).",
    )
    observacao = models.TextField("observação", blank=True)
    transacao_pai = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="partes",
        verbose_name="transação original (divisão)",
    )
    dividida = models.BooleanField("dividida", default=False)

    class Meta(ModeloBase.Meta):
        verbose_name = "transação"
        verbose_name_plural = "transações"
        ordering = ["-data", "-criado_em"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valor_centavos__gt=0), name="transacao_valor_positivo"
            ),
            models.CheckConstraint(
                condition=models.Q(parcela_atual__isnull=True)
                | models.Q(total_parcelas__isnull=True)
                | models.Q(parcela_atual__gte=1, parcela_atual__lte=models.F("total_parcelas")),
                name="transacao_parcela_valida",
            ),
            models.UniqueConstraint(
                fields=["pluggy_transaction_id"],
                condition=models.Q(pluggy_transaction_id__isnull=False),
                name="transacao_pluggy_transaction_id_unico",
            ),
        ]
        indexes = [
            models.Index(fields=["usuario", "data"], name="transacao_usuario_data"),
            models.Index(fields=["usuario", "categoria"], name="transacao_usuario_categoria"),
        ]

    def __str__(self):
        return f"{self.data:%d/%m/%Y} {self.descricao} ({self.valor_centavos})"

    @property
    def efeito_no_saldo(self) -> int:
        """Quanto esta transação soma ao saldo da conta (negativo para saídas)."""
        return self.valor_centavos if self.tipo == self.Tipo.ENTRADA else -self.valor_centavos

    @property
    def estorno(self) -> bool:
        return (
            self.tipo == self.Tipo.ENTRADA
            and self.categoria is not None
            and self.categoria.tipo == Categoria.Tipo.GASTO
        )


class RegraCategoria(ModeloBase):
    """Regra que categoriza transações pela descrição (sem acentos e sem caixa)."""

    class Campo(models.TextChoices):
        DESCRICAO = "descricao", "Descrição"

    class Operador(models.TextChoices):
        CONTEM = "contem", "Contém"
        COMECA_COM = "comeca_com", "Começa com"
        IGUAL = "igual", "Igual a"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="regras_categoria"
    )
    campo = models.CharField("campo", max_length=20, choices=Campo.choices, default="descricao")
    operador = models.CharField(
        "operador", max_length=20, choices=Operador.choices, default=Operador.CONTEM
    )
    valor = models.CharField("valor", max_length=255)
    categoria = models.ForeignKey(
        Categoria, on_delete=models.CASCADE, related_name="regras", verbose_name="categoria"
    )
    prioridade = models.IntegerField(
        "prioridade", default=0, help_text="Maior número = aplicada primeiro."
    )

    class Meta(ModeloBase.Meta):
        verbose_name = "regra de categoria"
        verbose_name_plural = "regras de categoria"
        ordering = ["-prioridade", "criado_em"]
        indexes = [models.Index(fields=["usuario", "prioridade"], name="regra_usuario_prioridade")]

    def __str__(self):
        return f"{self.get_operador_display()} '{self.valor}' → {self.categoria}"


class Recorrencia(ModeloBase):
    """Molde de uma conta fixa ou receita fixa (ou parcelado, com `total_parcelas`)."""

    class Tipo(models.TextChoices):
        CONTA = "conta", "Conta a pagar"
        RECEITA = "receita", "Receita"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recorrencias"
    )
    tipo = models.CharField("tipo", max_length=10, choices=Tipo.choices, default=Tipo.CONTA)
    nome = models.CharField("nome", max_length=120)
    valor_previsto_centavos = models.BigIntegerField("valor previsto (centavos)")
    dia_do_mes = models.PositiveSmallIntegerField(
        "dia do mês", help_text="1 a 31; em meses mais curtos, vence no último dia."
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="recorrencias", verbose_name="categoria"
    )
    conta_padrao = models.ForeignKey(
        ContaFinanceira,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorrencias",
        verbose_name="conta padrão",
    )
    inicio = models.DateField("início")
    fim = models.DateField("fim", null=True, blank=True)
    total_parcelas = models.PositiveSmallIntegerField("total de parcelas", null=True, blank=True)
    ativa = models.BooleanField("ativa", default=True)

    class Meta(ModeloBase.Meta):
        verbose_name = "recorrência"
        verbose_name_plural = "recorrências"
        ordering = ["dia_do_mes", "nome"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(dia_do_mes__gte=1, dia_do_mes__lte=31),
                name="recorrencia_dia_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_previsto_centavos__gt=0),
                name="recorrencia_valor_positivo",
            ),
            models.CheckConstraint(
                condition=models.Q(fim__isnull=True) | models.Q(fim__gte=models.F("inicio")),
                name="recorrencia_fim_depois_do_inicio",
            ),
            models.CheckConstraint(
                condition=models.Q(total_parcelas__isnull=True) | models.Q(total_parcelas__gte=1),
                name="recorrencia_parcelas_validas",
            ),
        ]
        indexes = [models.Index(fields=["usuario", "ativa"], name="recorrencia_usuario_ativa")]

    def __str__(self):
        return self.nome

    def primeiro_mes(self):
        """Mês da primeira ocorrência: o do início, ou o seguinte se o vencimento daquele mês
        cai antes do início (ex.: início 15/11 com dia 5 → primeira em dezembro)."""
        mes = primeiro_dia(self.inicio)
        if vencimento_no_mes(mes, self.dia_do_mes) < self.inicio:
            mes = somar_meses(mes, 1)
        return mes

    def vale_para(self, mes) -> bool:
        """Se existe ocorrência neste mês (ignora `ativa`)."""
        primeiro = self.primeiro_mes()
        if mes < primeiro:
            return False
        if self.fim and vencimento_no_mes(mes, self.dia_do_mes) > self.fim:
            return False
        return not (self.total_parcelas and meses_entre(primeiro, mes) >= self.total_parcelas)


class Ocorrencia(ModeloBase):
    """Uma conta ou receita de um mês, gerada a partir de uma recorrência.

    No banco o status é só `prevista` ou `paga`; "atrasada" é calculado na leitura
    (prevista com vencimento antes de hoje).
    """

    class Status(models.TextChoices):
        PREVISTA = "prevista", "Prevista"
        PAGA = "paga", "Paga"
        ATRASADA = "atrasada", "Atrasada"  # nunca gravado, só exibido

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ocorrencias"
    )
    recorrencia = models.ForeignKey(
        Recorrencia, on_delete=models.CASCADE, related_name="ocorrencias"
    )
    mes_referencia = models.DateField("mês de referência")
    vencimento = models.DateField("vencimento")
    valor_centavos = models.BigIntegerField("valor (centavos)")
    status = models.CharField(
        "status",
        max_length=10,
        choices=[(Status.PREVISTA, "Prevista"), (Status.PAGA, "Paga")],
        default=Status.PREVISTA,
    )
    # OneToOne: o banco garante que uma transação quita no máximo uma ocorrência.
    transacao = models.OneToOneField(
        Transacao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ocorrencia",
        verbose_name="transação que quitou",
    )
    paga_em = models.DateField("paga em", null=True, blank=True)
    casamento_automatico = models.BooleanField(
        "casamento automático",
        default=True,
        help_text="Desligado quando o usuário desmarca, para não vincular de novo sozinho.",
    )

    class Meta(ModeloBase.Meta):
        verbose_name = "ocorrência"
        verbose_name_plural = "ocorrências"
        ordering = ["vencimento"]
        constraints = [
            models.UniqueConstraint(
                fields=["recorrencia", "mes_referencia"], name="ocorrencia_unica_por_mes"
            ),
            models.CheckConstraint(
                condition=models.Q(mes_referencia__day=1), name="ocorrencia_mes_no_dia_1"
            ),
        ]
        indexes = [
            models.Index(fields=["usuario", "mes_referencia"], name="ocorrencia_usuario_mes"),
            models.Index(fields=["usuario", "vencimento"], name="ocorrencia_usuario_venc"),
        ]

    def __str__(self):
        return f"{self.recorrencia} {self.mes_referencia:%m/%Y}"

    def status_em(self, hoje) -> str:
        if self.status == self.Status.PREVISTA and self.vencimento < hoje:
            return self.Status.ATRASADA
        return self.status


class Orcamento(ModeloBase):
    """Limite de gasto de uma categoria num mês (inclui as subcategorias)."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orcamentos"
    )
    categoria = models.ForeignKey(
        Categoria, on_delete=models.CASCADE, related_name="orcamentos", verbose_name="categoria"
    )
    mes_referencia = models.DateField("mês de referência")
    limite_centavos = models.BigIntegerField("limite (centavos)")

    class Meta(ModeloBase.Meta):
        verbose_name = "orçamento"
        verbose_name_plural = "orçamentos"
        ordering = ["-mes_referencia"]
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "categoria", "mes_referencia"], name="orcamento_unico_por_mes"
            ),
            models.CheckConstraint(
                condition=models.Q(mes_referencia__day=1), name="orcamento_mes_no_dia_1"
            ),
            models.CheckConstraint(
                condition=models.Q(limite_centavos__gt=0), name="orcamento_limite_positivo"
            ),
        ]
        indexes = [models.Index(fields=["usuario", "mes_referencia"], name="orcamento_usuario_mes")]

    def __str__(self):
        return f"{self.categoria} {self.mes_referencia:%m/%Y}"
