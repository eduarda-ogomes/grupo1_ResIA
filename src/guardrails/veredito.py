"""Filtro de veredito (Manual §3.5): termos que dariam um veredito ao texto escrito pelo LLM.

Ignora maiúsculas e acentos e respeita a fronteira de palavra ("falsificação" passa).
Aplica-se só ao texto do LLM; o selo da agência ("Agência Lupa: Falso") fica fora.
Nomes de falácia que contêm um termo da lista ("Falsa dicotomia", rótulo de
src/agents/dossie.py) não são veredito e não reprovam o texto.
Limitação conhecida: paráfrases ("não procede", "é enganoso") passam.
"""
import re
import unicodedata

TERMOS = (
    "falso", "falsa", "falsos", "falsas",
    "verdadeiro", "verdadeira", "verdadeiros", "verdadeiras",
    "fake news", "mentira", "mentiras", "desinformação",
)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


# Mais longos primeiro; espaço do termo aceita qualquer sequência de espaços ("fake   news")
_ALTERNATIVAS = [re.escape(_sem_acento(t)).replace(r"\ ", r"\s+") for t in sorted(TERMOS, key=len, reverse=True)]
_PADRAO = re.compile(r"\b(" + "|".join(_ALTERNATIVAS) + r")\b", re.IGNORECASE)

NOMES_DE_FALACIA = ("falsa dicotomia",)
_FALACIAS = re.compile(
    r"\b(" + "|".join(re.escape(n).replace(r"\ ", r"\s+") for n in NOMES_DE_FALACIA) + r")\b", re.IGNORECASE
)


def termos_de_veredito(texto: str) -> list[str]:
    """Termos proibidos encontrados (minúsculos, sem acento), na ordem em que aparecem, sem repetir."""
    achados: list[str] = []
    for m in _PADRAO.finditer(_FALACIAS.sub(" ", _sem_acento(texto))):
        termo = " ".join(m.group(1).lower().split())
        if termo not in achados:
            achados.append(termo)
    return achados
