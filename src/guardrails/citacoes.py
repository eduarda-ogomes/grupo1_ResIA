"""Checagem de citações (Manual §3.5): toda URL do dossiê precisa estar entre as evidências recebidas."""
import re
from typing import Iterable

from src.state import Evidence

_URL = re.compile(r"https?://[^\s<>\"']+")
_PONTUACAO_FINAL = ".,;:!?)]}"


def _normalizar(url: str) -> str:
    return url.rstrip(_PONTUACAO_FINAL)


def extrair_urls(texto: str) -> list[str]:
    """URLs http(s) do texto, na ordem, sem a pontuação final que costuma colar nelas."""
    return [_normalizar(m.group(0)) for m in _URL.finditer(texto)]


def urls_invalidas(texto: str, evidencias: Iterable[Evidence]) -> list[str]:
    """URLs do texto que não estão entre as source_url das evidências, sem repetir."""
    conhecidas = {_normalizar(e.source_url) for e in evidencias}
    invalidas: list[str] = []
    for url in extrair_urls(texto):
        if url not in conhecidas and url not in invalidas:
            invalidas.append(url)
    return invalidas
