from django.db import transaction

from apps.financas.models import Categoria

# (nome, ícone, cor, subcategorias). Ícones são nomes de SF Symbols, usados pelo PWA.
CATEGORIAS_PADRAO_GASTO = [
    ("Moradia", "house", "#8D6E63", []),
    (
        "Alimentação",
        "fork.knife",
        "#EF6C00",
        [
            ("Mercado", "cart", "#F57C00"),
            ("Restaurante", "fork.knife", "#FB8C00"),
            ("Delivery", "bag", "#FFA726"),
        ],
    ),
    ("Transporte", "car", "#1E88E5", []),
    ("Saúde", "cross.case", "#E53935", []),
    ("Lazer", "gamecontroller", "#8E24AA", []),
    ("Compras", "bag", "#D81B60", []),
    ("Assinaturas", "repeat", "#5E35B1", []),
    ("Educação", "book", "#3949AB", []),
    ("Outros", "ellipsis.circle", "#757575", []),
]
CATEGORIAS_PADRAO_RECEITA = [
    ("Salário", "banknote", "#43A047", []),
    # "Outros" já existe como gasto e a unicidade é por (usuario, nome, categoria_pai).
    ("Outras receitas", "ellipsis.circle", "#7CB342", []),
]


@transaction.atomic
def criar_categorias_padrao(usuario) -> int:
    """Cria as categorias padrão que faltam para o usuário. Idempotente: não mexe nas
    que já existem (nem nas que o usuário renomeou). Retorna quantas foram criadas."""
    criadas = 0
    for tipo, lista in (
        (Categoria.Tipo.GASTO, CATEGORIAS_PADRAO_GASTO),
        (Categoria.Tipo.RECEITA, CATEGORIAS_PADRAO_RECEITA),
    ):
        for nome, icone, cor, filhas in lista:
            pai, nova = _obter_ou_criar(usuario, nome, tipo, icone, cor, None)
            criadas += nova
            for nome_f, icone_f, cor_f in filhas:
                criadas += _obter_ou_criar(usuario, nome_f, tipo, icone_f, cor_f, pai)[1]
    return criadas


def _obter_ou_criar(usuario, nome, tipo, icone, cor, pai):
    return Categoria.objects.get_or_create(
        usuario=usuario,
        nome=nome,
        categoria_pai=pai,
        defaults={"tipo": tipo, "icone": icone, "cor": cor},
    )
