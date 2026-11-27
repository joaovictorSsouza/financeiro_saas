"""Categorização automática de transações por regras do usuário."""

import re
from collections.abc import Iterable

from apps.financas.models import Categoria, RegraCategoria, Transacao

from .texto import normalizar

# Números, datas e símbolos que variam a cada compra (ex.: "UBER *TRIP 12/03 4521").
_RUIDO = re.compile(r"[\d*#/\\.,:;\-_]+")


def _textos(transacao: Transacao) -> list[str]:
    textos = [transacao.descricao_original, transacao.descricao]
    return [normalizar(t) for t in textos if t]


def regra_casa(regra: RegraCategoria, transacao: Transacao) -> bool:
    valor = normalizar(regra.valor)
    if not valor:
        return False
    for texto in _textos(transacao):
        if regra.operador == RegraCategoria.Operador.CONTEM and valor in texto:
            return True
        if regra.operador == RegraCategoria.Operador.COMECA_COM and texto.startswith(valor):
            return True
        if regra.operador == RegraCategoria.Operador.IGUAL and texto == valor:
            return True
    return False


def _compativel(regra: RegraCategoria, transacao: Transacao) -> bool:
    # Saída com categoria de receita é inválida; entrada com categoria de gasto é estorno.
    return not (
        transacao.tipo == Transacao.Tipo.SAIDA and regra.categoria.tipo == Categoria.Tipo.RECEITA
    )


def regras_do_usuario(usuario) -> list[RegraCategoria]:
    return list(
        RegraCategoria.objects.filter(usuario=usuario, categoria__ativa=True)
        .select_related("categoria")
        .order_by("-prioridade", "criado_em")
    )


def aplicar_regras(
    transacao: Transacao, regras: Iterable[RegraCategoria] | None = None, salvar: bool = True
) -> RegraCategoria | None:
    """Aplica a regra de maior prioridade que casar. Nunca mexe em categoria manual.

    `regras` permite reaproveitar a lista ao aplicar em lote. Retorna a regra aplicada.
    """
    if transacao.categoria_definida_manualmente:
        return None
    if regras is None:
        regras = regras_do_usuario(transacao.usuario_id)
    for regra in regras:
        if _compativel(regra, transacao) and regra_casa(regra, transacao):
            if transacao.categoria_id != regra.categoria_id:
                transacao.categoria = regra.categoria
                if salvar and transacao.pk:
                    transacao.save(update_fields=["categoria", "atualizado_em"])
            return regra
    return None


def aplicar_regras_em_lote(usuario) -> int:
    """Reaplica as regras em todas as transações sem categoria manual. Retorna quantas mudaram."""
    regras = regras_do_usuario(usuario)
    alteradas = 0
    transacoes = Transacao.objects.filter(
        usuario=usuario, categoria_definida_manualmente=False, dividida=False
    )
    for transacao in transacoes.iterator():
        anterior = transacao.categoria_id
        aplicar_regras(transacao, regras=regras)
        alteradas += transacao.categoria_id != anterior
    return alteradas


def sugerir_regra(transacao: Transacao) -> dict | None:
    """Sugestão de regra após o usuário corrigir a categoria. Não cria nada.

    Retorna None se a transação não tem categoria, se a descrição não tem texto útil ou
    se já existe uma regra que casa com ela e aponta para a mesma categoria.
    """
    if transacao.categoria_id is None:
        return None
    base = transacao.descricao_original or transacao.descricao
    valor = " ".join(_RUIDO.sub(" ", normalizar(base)).split())[:60].strip()
    if len(valor) < 3:
        return None
    for regra in regras_do_usuario(transacao.usuario_id):
        if regra.categoria_id == transacao.categoria_id and regra_casa(regra, transacao):
            return None
    return {
        "campo": RegraCategoria.Campo.DESCRICAO,
        "operador": RegraCategoria.Operador.CONTEM,
        "valor": valor,
        "categoria": str(transacao.categoria_id),
    }
