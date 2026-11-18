import re
import unicodedata


def normalize(text: str) -> str:
    """Minúsculas e sem acentos: "Horário" e "horario" viram o mesmo termo."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def terms(query: str, min_len: int = 3) -> list[str]:
    return [t for t in dict.fromkeys(re.findall(r"[a-z0-9]+", normalize(query))) if len(t) >= min_len]
