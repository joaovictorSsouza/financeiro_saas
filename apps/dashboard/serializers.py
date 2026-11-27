"""Serializers só de saída: documentam no OpenAPI o formato das respostas."""

from rest_framework import serializers


class ComparacaoSerializer(serializers.Serializer):
    anterior = serializers.IntegerField()
    diferenca = serializers.IntegerField()
    percentual = serializers.FloatField(allow_null=True)


class ComparacaoMesAnteriorSerializer(serializers.Serializer):
    receitas = ComparacaoSerializer()
    despesas = ComparacaoSerializer()


class GastoCategoriaSerializer(serializers.Serializer):
    categoria = serializers.UUIDField(allow_null=True)
    nome = serializers.CharField()
    icone = serializers.CharField()
    cor = serializers.CharField()
    total_centavos = serializers.IntegerField()
    percentual = serializers.FloatField(allow_null=True)


class ProximaContaSerializer(serializers.Serializer):
    ocorrencia = serializers.UUIDField()
    nome = serializers.CharField()
    vencimento = serializers.DateField()
    valor_centavos = serializers.IntegerField()
    categoria = serializers.UUIDField()


class OrcamentoResumoSerializer(serializers.Serializer):
    orcamento = serializers.UUIDField()
    categoria = serializers.UUIDField()
    nome = serializers.CharField()
    gasto_centavos = serializers.IntegerField()
    limite_centavos = serializers.IntegerField()
    restante_centavos = serializers.IntegerField()
    percentual = serializers.FloatField()


class MaiorGastoSerializer(serializers.Serializer):
    transacao = serializers.UUIDField()
    data = serializers.DateField()
    descricao = serializers.CharField()
    valor_centavos = serializers.IntegerField()
    categoria = serializers.UUIDField(allow_null=True)
    categoria_nome = serializers.CharField(allow_null=True)
    conta = serializers.UUIDField()


class AlertaSerializer(serializers.Serializer):
    tipo = serializers.CharField()
    mensagem = serializers.CharField()
    transacao = serializers.UUIDField(allow_null=True)


class ResumoSerializer(serializers.Serializer):
    mes = serializers.DateField()
    saldo_atual = serializers.IntegerField()
    receitas_mes = serializers.IntegerField()
    despesas_mes = serializers.IntegerField()
    comparacao_mes_anterior = ComparacaoMesAnteriorSerializer()
    contas_a_pagar = serializers.IntegerField()
    receitas_a_receber = serializers.IntegerField()
    fatura_cartao = serializers.IntegerField()
    saldo_previsto_fim_mes = serializers.IntegerField(allow_null=True)
    gastos_por_categoria = GastoCategoriaSerializer(many=True)
    proximas_contas = ProximaContaSerializer(many=True)
    orcamentos = OrcamentoResumoSerializer(many=True)
    maiores_gastos = MaiorGastoSerializer(many=True)
    alertas = AlertaSerializer(many=True)


class EvolucaoMesSerializer(serializers.Serializer):
    mes = serializers.DateField()
    receitas = serializers.IntegerField()
    despesas = serializers.IntegerField()
    resultado = serializers.IntegerField()
