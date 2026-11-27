import re
import unicodedata

_ESPACOS = re.compile(r"\s+")


def normalizar(texto: str) -> str:
    """Minúsculas, sem acentos e com espaços colapsados (para comparar descrições)."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acentos = "".join(c for c in decomposto if not unicodedata.combining(c))
    return _ESPACOS.sub(" ", sem_acentos.casefold()).strip()
