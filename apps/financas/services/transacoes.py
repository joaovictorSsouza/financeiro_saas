"""Criação, edição e exclusão de transações mantendo o saldo das contas manuais.

O saldo de uma conta manual acompanha as transações (inclusive as ignoradas, porque uma
transferência move dinheiro de verdade). Contas da Pluggy recebem o saldo do banco.
Partes de uma divisão não mexem no saldo: a original já contou.
"""

from django.db import transaction
from django.db.models import F

from apps.financas.models import ContaFinanceira, Ocorrencia, Transacao

from .casamento import casar_perto_de
from .regras import aplicar_regras


def _ajustar_saldo(conta_id, delta: int) -> None:
    if delta:
        ContaFinanceira.objects.filter(pk=conta_id, pluggy_account_id="").update(
            saldo_centavos=F("saldo_centavos") + delta
        )


def _efeito(t: Transacao) -> int:
    return 0 if t.transacao_pai_id else t.efeito_no_saldo


@transaction.atomic
def criar_transacao(usuario, **dados) -> Transacao:
    """Informar a categoria na criação conta como escolha manual; sem categoria, aplica as
    regras do usuário."""
    t = Transacao(usuario=usuario, **dados)
    if t.categoria_id is not None and "categoria_definida_manualmente" not in dados:
        t.categoria_definida_manualmente = True
    if t.categoria_id is None:
        aplicar_regras(t, salvar=False)
    t.save()
    _ajustar_saldo(t.conta_id, _efeito(t))
    _casar(t)
    return t


def _casar(t: Transacao) -> None:
    if t.transacao_pai_id is None:
        casar_perto_de(t.usuario_id, t.data)


def _liberar_ocorrencia(t: Transacao) -> None:
    """Se a transação quitava uma ocorrência, ela volta a prevista."""
    Ocorrencia.objects.filter(transacao=t).update(
        status=Ocorrencia.Status.PREVISTA, transacao=None, paga_em=None
    )


@transaction.atomic
def atualizar_transacao(t: Transacao, **dados) -> Transacao:
    """Mudar a categoria pela edição marca a categoria como manual."""
    conta_anterior, efeito_anterior = t.conta_id, _efeito(t)
    categoria_anterior = t.categoria_id
    tipo_e_ignorada_anteriores = (t.tipo, t.ignorada)
    for campo, valor in dados.items():
        setattr(t, campo, valor)
    if "categoria" in dados and t.categoria_id != categoria_anterior:
        t.categoria_definida_manualmente = t.categoria_id is not None
    t.save()
    _ajustar_saldo(conta_anterior, -efeito_anterior)
    _ajustar_saldo(t.conta_id, _efeito(t))
    if (t.tipo, t.ignorada) != tipo_e_ignorada_anteriores:
        _liberar_ocorrencia(t)
        t.partes.update(ignorada=t.ignorada)
    _casar(t)
    return t


@transaction.atomic
def excluir_transacao(t: Transacao) -> None:
    _ajustar_saldo(t.conta_id, -_efeito(t))
    _liberar_ocorrencia(t)
    t.delete()


class DivisaoInvalida(Exception):
    pass


@transaction.atomic
def dividir_transacao(t: Transacao, itens: list[dict]) -> Transacao:
    """Divide a transação em partes (cada uma com categoria e valor). A original fica com
    `dividida=True` e sai das somas; as partes entram no lugar dela. Dividir de novo
    substitui a divisão anterior. Não mexe no saldo (a original já contou)."""
    if t.transacao_pai_id:
        raise DivisaoInvalida("Não é possível dividir uma parte de outra divisão.")
    if len(itens) < 2:
        raise DivisaoInvalida("Informe pelo menos 2 partes.")
    if sum(item["valor_centavos"] for item in itens) != t.valor_centavos:
        raise DivisaoInvalida("A soma das partes deve ser igual ao valor da transação.")

    t.partes.all().delete()
    Transacao.objects.bulk_create(
        Transacao(
            usuario_id=t.usuario_id,
            conta_id=t.conta_id,
            data=t.data,
            tipo=t.tipo,
            origem=t.origem,
            ignorada=t.ignorada,
            descricao=item.get("descricao") or t.descricao,
            descricao_original=t.descricao_original,
            observacao=item.get("observacao", ""),
            valor_centavos=item["valor_centavos"],
            categoria=item["categoria"],
            categoria_definida_manualmente=True,
            transacao_pai=t,
        )
        for item in itens
    )
    t.dividida = True
    t.save(update_fields=["dividida", "atualizado_em"])
    return t


@transaction.atomic
def desfazer_divisao(t: Transacao) -> Transacao:
    t.partes.all().delete()
    t.dividida = False
    t.save(update_fields=["dividida", "atualizado_em"])
    return t
