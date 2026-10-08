"""Ancoragem no contexto (spec do dossiê final, seção "Guardrails", G3 e G4).

G3: todo trecho entre aspas no texto do LLM precisa existir literalmente em alguma frase da notícia.
G4: nomes próprios, números e doenças no texto do LLM precisam aparecer na notícia.

Só regex e Python puro (reaproveita o vocabulário e a tokenização de src/retrieval/etapa2.py): sem LLM,
sem rede, sem modelo. Quem chama decide o que fazer com a lista devolvida (retry, fallback, descarte).
Limitação conhecida: o G4 compara palavras, não sentido; uma sigla na notícia e o nome por extenso no
texto do LLM ("OMS" x "Organização Mundial da Saúde") é apontada como termo de fora.
"""
import re
from typing import Iterable

from src.retrieval.etapa2 import _SENTENCE_SPLIT, DISEASES, _stem, name_groups, tokenize

# Aspas retas ou curvas; o trecho não atravessa linha, para uma aspa solta não engolir o resto do texto
_TRECHO = re.compile(r'"([^"\n]*)"|“([^”\n]*)”')
_TAMANHO_MINIMO = 3

_ASPAS_CURVAS = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'"})
_RETICENCIAS = re.compile(r"…|\.{3,}")
_MARCADOR_DE_LISTA = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def trechos_citados(texto: str) -> list[str]:
    """Conteúdo de cada trecho entre aspas ("…" ou “…”), na ordem; ignora os de menos de 3 caracteres."""
    trechos = (m.group(1) if m.group(1) is not None else m.group(2) for m in _TRECHO.finditer(texto or ""))
    return [t for t in trechos if len(t.strip()) >= _TAMANHO_MINIMO]


def _normalizar_literal(texto: str) -> str:
    """Minúsculas, aspas unificadas e espaços colapsados: o que sobra é a forma de comparar trechos."""
    return " ".join(texto.translate(_ASPAS_CURVAS).casefold().split())


def _partes(trecho: str) -> list[str]:
    """Pedaços do trecho separados por "…" ou "...", normalizados e sem os vazios."""
    return [p for p in (_normalizar_literal(p) for p in _RETICENCIAS.split(trecho)) if p]


def citacoes_nao_literais(texto: str, fontes: list[str]) -> list[str]:
    """Trechos entre aspas do texto que não aparecem em nenhuma das fontes (G3), no texto original.

    Compara sem diferenciar caixa, espaços nem tipo de aspas. "…" ou "..." dentro do trecho o divide em
    partes, e todas precisam estar na MESMA fonte, em qualquer ordem.
    """
    normalizadas = [_normalizar_literal(f) for f in fontes]
    reprovados = []
    for trecho in trechos_citados(texto):
        partes = _partes(trecho)
        if partes and not any(all(p in fonte for p in partes) for fonte in normalizadas):
            reprovados.append(trecho)
    return reprovados


def _sem_rotulos(texto: str, ignorar: Iterable[str]) -> str:
    for rotulo in ignorar:
        if rotulo.strip():
            texto = re.sub(re.escape(rotulo.strip()), " ", texto, flags=re.IGNORECASE)
    return texto


def termos_fora_do_contexto(texto: str, contexto: str, ignorar: Iterable[str] = ()) -> list[str]:
    """Nomes, números e doenças do texto que a notícia não menciona (G4), sem repetir.

    Ordem da saída: nomes próprios (cada grupo unido por espaço, "ministerio saude"), depois números,
    depois doenças; tudo em minúsculas e sem acento. Um nome ou doença conta como presente se o radical
    de 5 letras de algum de seus termos está entre os do contexto; um número, se o número normalizado
    ("1.800" -> "1800") está no contexto.

    `ignorar`: rótulos fixos do prompt (ex.: "Autoridade sem identificação"), tirados do texto antes da
    extração, sem diferenciar caixa. O texto é lido linha a linha, sem o marcador de lista ("- ", "1. "),
    e cada linha é repartida em frases (depois de ". ", ": " etc.), para que a primeira palavra de cada
    item e de cada frase seja tratada como início de frase, e não como nome próprio.
    """
    radicais = {_stem(t) for t in tokenize(contexto)}
    numeros_do_contexto = {t for t in tokenize(contexto) if t.isdigit()}
    nomes: list[str] = []
    numeros: list[str] = []
    doencas: list[str] = []

    for linha in _sem_rotulos(texto or "", ignorar).splitlines():
        linha = _MARCADOR_DE_LISTA.sub("", linha).strip()
        for frase in _SENTENCE_SPLIT.split(linha):
            for grupo in name_groups(frase):
                if not any(_stem(t) in radicais for t in grupo):
                    nomes.append(" ".join(grupo))
        for token in tokenize(linha):
            if token.isdigit():
                if token not in numeros_do_contexto:
                    numeros.append(token)
            elif token in DISEASES and _stem(token) not in radicais:
                doencas.append(token)

    return list(dict.fromkeys(nomes + numeros + doencas))
