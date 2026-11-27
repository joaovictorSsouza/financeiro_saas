"""Cálculos do dashboard (só leitura agregada; o app não tem models).

Convenções:
- Entram nas somas só transações não ignoradas e não divididas (as partes de uma
  divisão entram no lugar da original).
- Receita = entrada sem categoria ou com categoria de receita.
- Estorno = entrada com categoria de gasto: abate o gasto da categoria e as despesas.
- Despesas = saídas - estornos.
"""

import datetime
from collections import defaultdict

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.financas.datas import primeiro_dia, somar_meses, ultimo_dia, ultimos_meses
from apps.financas.models import (
    Categoria,
    ContaFinanceira,
    Ocorrencia,
    Orcamento,
    Recorrencia,
    Transacao,
)
from apps.financas.services.casamento import preparar_mes
from apps.financas.services.ocorrencias import gerar_ocorrencias
from apps.financas.services.texto import normalizar

DIAS_PROXIMAS_CONTAS = 7
TOP_MAIORES_GASTOS = 5
PALAVRAS_FATURA = ("fatura", "cartao")

Q_RECEITA = Q(tipo=Transacao.Tipo.ENTRADA) & (
    Q(categoria__isnull=True) | Q(categoria__tipo=Categoria.Tipo.RECEITA)
)
Q_ESTORNO = Q(tipo=Transacao.Tipo.ENTRADA, categoria__tipo=Categoria.Tipo.GASTO)
Q_SAIDA = Q(tipo=Transacao.Tipo.SAIDA)


def _soma(campo="valor_centavos", **filtro):
    return Coalesce(Sum(campo, **filtro), 0)


def transacoes_contabeis(usuario):
    return Transacao.objects.filter(usuario=usuario, ignorada=False, dividida=False)


def transacoes_do_mes(usuario, mes: datetime.date):
    return transacoes_contabeis(usuario).filter(data__gte=mes, data__lte=ultimo_dia(mes))


def totais(queryset) -> dict:
    t = queryset.aggregate(
        receitas=_soma(filter=Q_RECEITA),
        saidas=_soma(filter=Q_SAIDA),
        estornos=_soma(filter=Q_ESTORNO),
    )
    return {"receitas": t["receitas"], "despesas": t["saidas"] - t["estornos"]}


def percentual(parte: int, total: int) -> float | None:
    return round(parte * 100 / total, 1) if total else None


def _comparacao(atual: int, anterior: int) -> dict:
    diferenca = atual - anterior
    return {
        "anterior": anterior,
        "diferenca": diferenca,
        "percentual": percentual(diferenca, anterior),
    }


def _gasto_liquido_por_categoria(queryset) -> dict:
    """{categoria_id ou None: saídas - estornos}, por categoria exata."""
    linhas = (
        queryset.filter(Q_SAIDA | Q_ESTORNO)
        .values("categoria", "tipo")
        .annotate(total=Sum("valor_centavos"))
    )
    gastos = defaultdict(int)
    for linha in linhas:
        sinal = 1 if linha["tipo"] == Transacao.Tipo.SAIDA else -1
        gastos[linha["categoria"]] += sinal * linha["total"]
    return gastos


def gastos_por_categoria(usuario, queryset, despesas: int) -> list[dict]:
    """Agrupado pela categoria pai (subcategorias somam na pai)."""
    gastos = _gasto_liquido_por_categoria(queryset)
    categorias = Categoria.objects.filter(usuario=usuario, pk__in=[c for c in gastos if c])
    raiz_de = {c.pk: c.categoria_pai_id or c.pk for c in categorias}
    por_raiz = defaultdict(int)
    for categoria_id, total in gastos.items():
        por_raiz[raiz_de.get(categoria_id)] += total

    raizes = Categoria.objects.in_bulk([r for r in por_raiz if r])
    itens = []
    for raiz_id, total in por_raiz.items():
        if total == 0:
            continue
        raiz = raizes.get(raiz_id)
        itens.append(
            {
                "categoria": raiz_id,
                "nome": raiz.nome if raiz else "Sem categoria",
                "icone": raiz.icone if raiz else "",
                "cor": raiz.cor if raiz else "#9E9E9E",
                "total_centavos": total,
                "percentual": percentual(total, despesas),
            }
        )
    return sorted(itens, key=lambda i: i["total_centavos"], reverse=True)


def orcamentos(usuario, queryset, mes) -> list[dict]:
    """Gasto x limite. Orçamento de categoria pai inclui as subcategorias."""
    gastos = _gasto_liquido_por_categoria(queryset)
    filhas = defaultdict(list)
    subcategorias = Categoria.objects.filter(usuario=usuario, categoria_pai__isnull=False)
    for pk, pai in subcategorias.values_list("pk", "categoria_pai"):
        filhas[pai].append(pk)

    itens = []
    for orc in Orcamento.objects.filter(usuario=usuario, mes_referencia=mes).select_related(
        "categoria"
    ):
        ids = [orc.categoria_id, *filhas.get(orc.categoria_id, [])]
        gasto = sum(gastos.get(i, 0) for i in ids)
        itens.append(
            {
                "orcamento": orc.pk,
                "categoria": orc.categoria_id,
                "nome": orc.categoria.nome,
                "gasto_centavos": gasto,
                "limite_centavos": orc.limite_centavos,
                "restante_centavos": orc.limite_centavos - gasto,
                "percentual": percentual(gasto, orc.limite_centavos),
            }
        )
    return sorted(itens, key=lambda i: i["percentual"], reverse=True)


def _ocorrencias_nao_pagas(usuario, mes, tipo):
    return Ocorrencia.objects.filter(
        usuario=usuario,
        mes_referencia=mes,
        recorrencia__tipo=tipo,
        status=Ocorrencia.Status.PREVISTA,
    ).aggregate(total=_soma())["total"]


def proximas_contas(usuario, hoje: datetime.date) -> list[dict]:
    limite = hoje + datetime.timedelta(days=DIAS_PROXIMAS_CONTAS)
    # Independe do mês consultado; a janela pode entrar no mês seguinte.
    for mes in {primeiro_dia(hoje), primeiro_dia(limite)}:
        gerar_ocorrencias(usuario, mes)
    ocorrencias = (
        Ocorrencia.objects.filter(
            usuario=usuario,
            recorrencia__tipo=Recorrencia.Tipo.CONTA,
            status=Ocorrencia.Status.PREVISTA,
            vencimento__gte=hoje,
            vencimento__lte=limite,
        )
        .select_related("recorrencia")
        .order_by("vencimento")
    )
    return [
        {
            "ocorrencia": o.pk,
            "nome": o.recorrencia.nome,
            "vencimento": o.vencimento,
            "valor_centavos": o.valor_centavos,
            "categoria": o.recorrencia.categoria_id,
        }
        for o in ocorrencias
    ]


def maiores_gastos(queryset) -> list[dict]:
    return [
        {
            "transacao": t.pk,
            "data": t.data,
            "descricao": t.descricao,
            "valor_centavos": t.valor_centavos,
            "categoria": t.categoria_id,
            "categoria_nome": t.categoria.nome if t.categoria else None,
            "conta": t.conta_id,
        }
        for t in queryset.filter(Q_SAIDA)
        .select_related("categoria")
        .order_by("-valor_centavos", "-data")[:TOP_MAIORES_GASTOS]
    ]


def alertas(usuario, mes) -> list[dict]:
    """Por enquanto: possível pagamento de fatura na conta corrente sem `ignorada`, que
    contaria a despesa duas vezes (no cartão e na corrente). Na fase 2 vira automático."""
    suspeitas = Transacao.objects.filter(
        usuario=usuario,
        conta__tipo=ContaFinanceira.Tipo.CORRENTE,
        tipo=Transacao.Tipo.SAIDA,
        ignorada=False,
        transacao_pai__isnull=True,
        data__gte=mes,
        data__lte=ultimo_dia(mes),
    ).order_by("data")
    itens = []
    for t in suspeitas:
        texto = normalizar(f"{t.descricao} {t.descricao_original}")
        if any(palavra in texto for palavra in PALAVRAS_FATURA):
            itens.append(
                {
                    "tipo": "fatura_nao_ignorada",
                    "mensagem": (
                        f"“{t.descricao}” parece o pagamento da fatura do cartão. "
                        "Marque como ignorada para não contar a despesa duas vezes."
                    ),
                    "transacao": t.pk,
                }
            )
    return itens


def resumo(usuario, mes: datetime.date, hoje: datetime.date | None = None) -> dict:
    hoje = hoje or timezone.localdate()
    mes = primeiro_dia(mes)
    preparar_mes(usuario, mes)

    do_mes = transacoes_do_mes(usuario, mes)
    atual = totais(do_mes)
    anterior = totais(transacoes_do_mes(usuario, somar_meses(mes, -1)))

    contas_ativas = ContaFinanceira.objects.filter(usuario=usuario, ativa=True)
    saldo_atual = contas_ativas.exclude(tipo=ContaFinanceira.Tipo.CARTAO_CREDITO).aggregate(
        total=_soma("saldo_centavos")
    )["total"]
    contas_a_pagar = _ocorrencias_nao_pagas(usuario, mes, Recorrencia.Tipo.CONTA)
    receitas_a_receber = _ocorrencias_nao_pagas(usuario, mes, Recorrencia.Tipo.RECEITA)
    fatura_cartao = do_mes.filter(
        Q_SAIDA, conta__tipo=ContaFinanceira.Tipo.CARTAO_CREDITO
    ).aggregate(total=_soma())["total"]

    # Para meses passados o saldo de hoje não diz nada sobre o fim daquele mês.
    saldo_previsto = (
        saldo_atual + receitas_a_receber - contas_a_pagar - fatura_cartao
        if mes >= primeiro_dia(hoje)
        else None
    )

    return {
        "mes": mes,
        "saldo_atual": saldo_atual,
        "receitas_mes": atual["receitas"],
        "despesas_mes": atual["despesas"],
        "comparacao_mes_anterior": {
            "receitas": _comparacao(atual["receitas"], anterior["receitas"]),
            "despesas": _comparacao(atual["despesas"], anterior["despesas"]),
        },
        "contas_a_pagar": contas_a_pagar,
        "receitas_a_receber": receitas_a_receber,
        "fatura_cartao": fatura_cartao,
        "saldo_previsto_fim_mes": saldo_previsto,
        "gastos_por_categoria": gastos_por_categoria(usuario, do_mes, atual["despesas"]),
        "proximas_contas": proximas_contas(usuario, hoje),
        "orcamentos": orcamentos(usuario, do_mes, mes),
        "maiores_gastos": maiores_gastos(do_mes),
        "alertas": alertas(usuario, mes),
    }


def evolucao(usuario, ate: datetime.date, meses: int) -> list[dict]:
    lista = ultimos_meses(ate, meses)
    linhas = (
        transacoes_contabeis(usuario)
        .filter(data__gte=lista[0], data__lte=ultimo_dia(lista[-1]))
        .annotate(mes=TruncMonth("data"))
        .values("mes")
        .annotate(
            receitas=_soma(filter=Q_RECEITA),
            saidas=_soma(filter=Q_SAIDA),
            estornos=_soma(filter=Q_ESTORNO),
        )
    )
    por_mes = {linha["mes"]: linha for linha in linhas}
    resultado = []
    for mes in lista:
        linha = por_mes.get(mes, {"receitas": 0, "saidas": 0, "estornos": 0})
        despesas = linha["saidas"] - linha["estornos"]
        resultado.append(
            {
                "mes": mes,
                "receitas": linha["receitas"],
                "despesas": despesas,
                "resultado": linha["receitas"] - despesas,
            }
        )
    return resultado
