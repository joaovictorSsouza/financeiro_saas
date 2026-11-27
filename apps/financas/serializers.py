from rest_framework import serializers

from apps.core.api import CampoDoUsuario, validar_com_clean

from .models import Categoria, ContaFinanceira, RegraCategoria

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
