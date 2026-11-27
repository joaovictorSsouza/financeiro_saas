from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.api import CampoDoUsuario, validar_com_clean

from .models import (
    Categoria,
    ContaFinanceira,
    Ocorrencia,
    Orcamento,
    Recorrencia,
    RegraCategoria,
    Transacao,
)
from .services import transacoes as servico
from .services.regras import sugerir_regra

CAMPOS_BASE = ("id", "criado_em", "atualizado_em")


class CategoriaSerializer(serializers.ModelSerializer):
    categoria_pai = CampoDoUsuario(Categoria, allow_null=True, required=False)

    class Meta:
        model = Categoria
        fields = (*CAMPOS_BASE, "nome", "icone", "cor", "categoria_pai", "tipo", "ativa")
        read_only_fields = CAMPOS_BASE
        # A unicidade (usuario, nome, pai) é verificada em validate(), com usuario do servidor.
        validators = []

    def validate(self, attrs):
        validar_com_clean(self, attrs, Categoria)
        usuario = self.context["request"].user
        nome = attrs.get("nome", getattr(self.instance, "nome", None))
        pai = attrs.get("categoria_pai", getattr(self.instance, "categoria_pai", None))
        repetida = Categoria.objects.filter(usuario=usuario, nome=nome, categoria_pai=pai)
        if self.instance:
            repetida = repetida.exclude(pk=self.instance.pk)
        if repetida.exists():
            raise serializers.ValidationError({"nome": "Já existe uma categoria com este nome."})
        return attrs


class ContaFinanceiraSerializer(serializers.ModelSerializer):
    manual = serializers.BooleanField(read_only=True)

    class Meta:
        model = ContaFinanceira
        fields = (
            *CAMPOS_BASE,
            "nome",
            "tipo",
            "instituicao",
            "saldo_centavos",
            "limite_centavos",
            "ativa",
            "manual",
            "conexao_pluggy_id",
            "pluggy_account_id",
        )
        # Os campos da Pluggy só são preenchidos pela integração (fase 2).
        read_only_fields = (*CAMPOS_BASE, "conexao_pluggy_id", "pluggy_account_id")

    def validate_saldo_centavos(self, valor):
        if self.instance and not self.instance.manual and valor != self.instance.saldo_centavos:
            raise serializers.ValidationError("O saldo de uma conta conectada vem do banco.")
        return valor

    def validate_limite_centavos(self, valor):
        if valor is not None and valor < 0:
            raise serializers.ValidationError("O limite não pode ser negativo.")
        return valor


class RegraCategoriaSerializer(serializers.ModelSerializer):
    categoria = CampoDoUsuario(Categoria)

    class Meta:
        model = RegraCategoria
        fields = (*CAMPOS_BASE, "campo", "operador", "valor", "categoria", "prioridade")
        read_only_fields = CAMPOS_BASE

    def validate_valor(self, valor):
        if not valor.strip():
            raise serializers.ValidationError("Informe o texto da regra.")
        return valor.strip()


class ResultadoAplicarRegrasSerializer(serializers.Serializer):
    alteradas = serializers.IntegerField()


def validar_categoria_para_tipo(categoria, tipo):
    """Saída com categoria de receita é inválida. Entrada com categoria de gasto é estorno."""
    if categoria and tipo == Transacao.Tipo.SAIDA and categoria.tipo == Categoria.Tipo.RECEITA:
        raise serializers.ValidationError(
            {"categoria": "Uma saída não pode ter categoria de receita."}
        )


class SugestaoRegraSerializer(serializers.Serializer):
    campo = serializers.CharField()
    operador = serializers.CharField()
    valor = serializers.CharField()
    categoria = serializers.UUIDField()


class ParteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transacao
        fields = ("id", "descricao", "valor_centavos", "categoria", "observacao")
        read_only_fields = fields


# Numa parte de divisão só dá para mudar estes campos (o resto vem da original).
CAMPOS_EDITAVEIS_NA_PARTE = {"categoria", "descricao", "observacao"}
# Numa transação dividida, estes campos ficam travados até desfazer a divisão.
CAMPOS_TRAVADOS_NA_DIVIDIDA = {"conta", "data", "valor_centavos", "tipo", "categoria"}


class TransacaoSerializer(serializers.ModelSerializer):
    conta = CampoDoUsuario(ContaFinanceira)
    categoria = CampoDoUsuario(Categoria, allow_null=True, required=False)
    estorno = serializers.BooleanField(read_only=True)
    partes = ParteSerializer(many=True, read_only=True)
    sugestao_regra = serializers.SerializerMethodField()

    class Meta:
        model = Transacao
        fields = (
            *CAMPOS_BASE,
            "conta",
            "data",
            "descricao",
            "descricao_original",
            "valor_centavos",
            "tipo",
            "categoria",
            "categoria_definida_manualmente",
            "origem",
            "pluggy_transaction_id",
            "parcela_atual",
            "total_parcelas",
            "ignorada",
            "observacao",
            "estorno",
            "transacao_pai",
            "dividida",
            "partes",
            "sugestao_regra",
        )
        read_only_fields = (
            *CAMPOS_BASE,
            "descricao_original",
            "categoria_definida_manualmente",
            "origem",
            "pluggy_transaction_id",
            "transacao_pai",
            "dividida",
        )

    @extend_schema_field(SugestaoRegraSerializer(allow_null=True))
    def get_sugestao_regra(self, obj):
        """Só vem preenchida na resposta da edição que trocou a categoria."""
        return getattr(self, "_sugestao", None) if obj is self.instance else None

    def validate_valor_centavos(self, valor):
        if valor <= 0:
            raise serializers.ValidationError("O valor deve ser positivo (o sentido vai em tipo).")
        return valor

    def validate(self, attrs):
        atual = self.instance
        if atual and atual.transacao_pai_id and set(attrs) - CAMPOS_EDITAVEIS_NA_PARTE:
            raise serializers.ValidationError(
                "Numa parte de divisão só dá para mudar categoria, descrição e observação."
            )
        if atual and atual.dividida:
            travados = {
                c for c in CAMPOS_TRAVADOS_NA_DIVIDIDA & set(attrs) if attrs[c] != getattr(atual, c)
            }
            if travados:
                raise serializers.ValidationError(
                    f"Desfaça a divisão para alterar: {', '.join(sorted(travados))}."
                )

        def valor(campo):
            return attrs.get(campo, getattr(atual, campo, None))

        validar_categoria_para_tipo(valor("categoria"), valor("tipo"))
        parcela, total = valor("parcela_atual"), valor("total_parcelas")
        if parcela is not None and total is not None and not 1 <= parcela <= total:
            raise serializers.ValidationError(
                {"parcela_atual": "Deve estar entre 1 e o total de parcelas."}
            )
        return attrs

    def create(self, validated_data):
        return servico.criar_transacao(**validated_data)

    def update(self, instance, validated_data):
        categoria_anterior = instance.categoria_id
        instance = servico.atualizar_transacao(instance, **validated_data)
        if "categoria" in validated_data and instance.categoria_id != categoria_anterior:
            self._sugestao = sugerir_regra(instance)
        return instance


class ItemDivisaoSerializer(serializers.Serializer):
    categoria = CampoDoUsuario(Categoria)
    valor_centavos = serializers.IntegerField(min_value=1)
    descricao = serializers.CharField(max_length=255, required=False, allow_blank=True)
    observacao = serializers.CharField(required=False, allow_blank=True)


class DividirSerializer(serializers.Serializer):
    itens = ItemDivisaoSerializer(many=True)

    def validate(self, attrs):
        transacao = self.context["transacao"]
        for item in attrs["itens"]:
            validar_categoria_para_tipo(item["categoria"], transacao.tipo)
        return attrs


class RecorrenciaSerializer(serializers.ModelSerializer):
    categoria = CampoDoUsuario(Categoria)
    conta_padrao = CampoDoUsuario(ContaFinanceira, allow_null=True, required=False)

    class Meta:
        model = Recorrencia
        fields = (
            *CAMPOS_BASE,
            "tipo",
            "nome",
            "valor_previsto_centavos",
            "dia_do_mes",
            "categoria",
            "conta_padrao",
            "inicio",
            "fim",
            "total_parcelas",
            "ativa",
        )
        read_only_fields = CAMPOS_BASE
        extra_kwargs = {
            "valor_previsto_centavos": {"min_value": 1},
            "dia_do_mes": {"min_value": 1, "max_value": 31},
            "total_parcelas": {"min_value": 1},
        }

    def validate(self, attrs):
        def valor(campo):
            return attrs.get(campo, getattr(self.instance, campo, None))

        inicio, fim = valor("inicio"), valor("fim")
        if fim and inicio and fim < inicio:
            raise serializers.ValidationError({"fim": "O fim deve ser depois do início."})
        conta = valor("tipo") == Recorrencia.Tipo.CONTA
        esperado = Categoria.Tipo.GASTO if conta else Categoria.Tipo.RECEITA
        if valor("categoria").tipo != esperado:
            raise serializers.ValidationError(
                {"categoria": f"Use uma categoria de {Categoria.Tipo(esperado).label.lower()}."}
            )
        return attrs


class OcorrenciaSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="recorrencia.nome", read_only=True)
    tipo = serializers.CharField(source="recorrencia.tipo", read_only=True)
    categoria = serializers.UUIDField(source="recorrencia.categoria_id", read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Ocorrencia
        fields = (
            *CAMPOS_BASE,
            "recorrencia",
            "nome",
            "tipo",
            "categoria",
            "mes_referencia",
            "vencimento",
            "valor_centavos",
            "status",
            "transacao",
            "paga_em",
            "casamento_automatico",
        )
        read_only_fields = fields

    @extend_schema_field(serializers.ChoiceField(choices=Ocorrencia.Status.choices))
    def get_status(self, obj) -> str:
        return getattr(obj, "status_atual", None) or obj.status_em(self.context["hoje"])


class MarcarPagaSerializer(serializers.Serializer):
    transacao = CampoDoUsuario(Transacao, allow_null=True, required=False)
    paga_em = serializers.DateField(required=False)

    def validate_transacao(self, transacao):
        if transacao is None:
            return None
        ocorrencia = self.context["ocorrencia"]
        if transacao.transacao_pai_id:
            raise serializers.ValidationError("Use a transação original, não uma parte.")
        vinculada = Ocorrencia.objects.filter(transacao=transacao).exclude(pk=ocorrencia.pk)
        if vinculada.exists():
            raise serializers.ValidationError("Esta transação já quitou outra ocorrência.")
        esperado = (
            Transacao.Tipo.SAIDA
            if ocorrencia.recorrencia.tipo == Recorrencia.Tipo.CONTA
            else Transacao.Tipo.ENTRADA
        )
        if transacao.tipo != esperado:
            raise serializers.ValidationError(f"A transação deve ser uma {esperado}.")
        return transacao


class OrcamentoSerializer(serializers.ModelSerializer):
    categoria = CampoDoUsuario(Categoria)
    mes_referencia = serializers.DateField(help_text="Qualquer dia do mês; é gravado como o dia 1.")

    class Meta:
        model = Orcamento
        fields = (*CAMPOS_BASE, "categoria", "mes_referencia", "limite_centavos")
        read_only_fields = CAMPOS_BASE
        extra_kwargs = {"limite_centavos": {"min_value": 1}}

    def validate_mes_referencia(self, valor):
        return valor.replace(day=1)

    def validate_categoria(self, categoria):
        if categoria.tipo != Categoria.Tipo.GASTO:
            raise serializers.ValidationError("Orçamento só para categorias de gasto.")
        return categoria

    def validate(self, attrs):
        categoria = attrs.get("categoria", getattr(self.instance, "categoria", None))
        mes = attrs.get("mes_referencia", getattr(self.instance, "mes_referencia", None))
        repetido = Orcamento.objects.filter(
            usuario=self.context["request"].user, categoria=categoria, mes_referencia=mes
        )
        if self.instance:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise serializers.ValidationError(
                {"categoria": "Já existe orçamento para esta categoria neste mês."}
            )
        return attrs
