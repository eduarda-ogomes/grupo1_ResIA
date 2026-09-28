"""Apoio à etapa "mesma alegação" do modo alegacao.

Duas variantes, medidas pelo experimento data/corpus/experimento_etapa2.py
antes de virarem padrão:

(b) normalize_claim: tira o enquadramento de mídia da alegação checada.
    "Foto mostra Edson Fachin apontando o dedo..." -> "Edson Fachin apontando o dedo...".
    Motivo (27/09): para o NLI, "uma foto mostra X" não implica "X", e a
    paráfrase do caso Fachin teve entailment 0,000. ~8% das alegações do corpus
    começam assim.

(c) key_terms_present: checagem determinística de termos-chave. O NLI marcou
    "cura a dengue" x "cura a chikungunya" como a mesma alegação (0,98); ele
    percebe troca de número, mas não de nome. Um NOME PRÓPRIO, NÚMERO ou NOME DE
    DOENÇA da frase ausente da checagem reprova a checagem quando a alegação
    checada tem um termo da mesma classe ausente da frase (uma troca).

    Calibrada em 28/09 nos 35 pares de data/corpus/pares_etapa2.json (sem o
    NLI): aceitou as 16 paráfrases e rejeitou 6 das 8 trocas de nome. Uma
    versão por palavras raras (IDF) foi testada e descartada: reprovava de 5 a
    16 paráfrases, porque paráfrases trazem palavras novas.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable, NamedTuple

# --- (b) enquadramento de mídia ---------------------------------------------

_MEDIA_NOUN = (
    r"(?:v[íi]deos?|fotos?|fotografias?|imag(?:em|ens)|[áa]udios?|montage(?:m|ns)|prints?|reportage(?:m|ns)"
    r"|posts?|postage(?:m|ns)|publica[çc](?:[ãa]o|[õo]es)|grava[çc](?:[ãa]o|[õo]es)|registros?)"
)
# "Foto mostra X", "Vídeo publicado no TikTok mostra que X", "Imagem de Lula mostra X"
_MEDIA_PREFIX = re.compile(
    r"^\s*" + _MEDIA_NOUN + r"\b[^,.;:]{0,50}?\s*,?\s*"
    r"(?:mostra(?:m)?|registra(?:m)?|flagra(?:m)?|exibe(?:m)?|revela(?:m)?|comprova(?:m)?|prova(?:m)?)\s+(?:que\s+)?",
    re.IGNORECASE,
)
# "Em vídeo, X", "Num áudio, X"
_MEDIA_LEAD = re.compile(r"^\s*(?:em|no|na|num|numa)\s+" + _MEDIA_NOUN + r"\s*,\s*", re.IGNORECASE)


def normalize_claim(claim: str) -> str:
    """Tira "Foto mostra", "Vídeo mostra que", "Em vídeo," etc. do início da alegação."""
    claim = (claim or "").strip()
    stripped = _MEDIA_LEAD.sub("", _MEDIA_PREFIX.sub("", claim, count=1), count=1).strip()
    if not stripped or stripped == claim:
        return claim
    return stripped[0].upper() + stripped[1:]


# --- (c) termos-chave ----------------------------------------------------------

_STOPWORDS = set(
    """
    a ao aos as ate com como da das de dele dela deles delas depois do dos e ela elas ele eles em entre era
    essa esse esta este eu foi foram ha isso isto ja la mais mas me mesmo muito na nao nas nem no nos num numa
    o os ou para pela pelas pelo pelos por porque qual quando que quem se sem ser seu seus sua suas so sobre
    tambem te tem ter todo todos toda todas um uma umas uns vai vao voce apos ainda assim antes agora onde
    sao seja sera estao esta estava estavam teria teriam sido sendo tinha foram fosse fossem pode podem apenas
    diz disse dizem afirma afirmam mostra mostram segundo contra desde durante
    """.split()
)

# Nomes de doenças: em minúscula, mas funcionam como nomes próprios (dengue x chikungunya).
DISEASES = set(
    """
    dengue zika chikungunya covid coronavirus sarampo gripe influenza h1n1 malaria febre amarela mpox variola
    poliomielite polio tuberculose hiv aids hepatite sifilis meningite caxumba rubeola catapora coqueluche
    hpv cancer diabetes alzheimer parkinson autismo raiva leptospirose oropouche
    """.split()
)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def normalize_text(text: str) -> str:
    """Minúsculas, sem acentos; números sem separador de milhar; "5 mil" -> "5000"."""
    text = _strip_accents((text or "").lower())
    text = re.sub(r"\bcovid[\s-]?19\b", "covid", text)                    # o 19 não é um número da alegação
    text = re.sub(r"(?<=\d)[.\s](?=\d{3}\b)", "", text)                  # 1.800 -> 1800
    text = re.sub(r"\b(\d+)(?:,(\d+))?\s*mil\b",                          # 5 mil -> 5000; 1,5 mil -> 1500
                  lambda m: str(int(float(f"{m.group(1)}.{m.group(2) or 0}") * 1000)), text)
    return text


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", normalize_text(text))
    return [t for t in tokens if (t.isdigit() or len(t) >= 3) and t not in _STOPWORDS]


def _stem(token: str) -> str:
    """Prefixo de 5 letras: tolera variações (Paraguai/paraguaio, vacina/vacinou, cerebral/cérebro)."""
    return token if token.isdigit() else token[:5]


# Palavras que costumam abrir frases e não são nomes próprios. Usadas só para
# decidir se a PRIMEIRA palavra da frase conta como nome (a maiúscula ali não
# indica nada). Lista curta e feita à mão (28/09).
_COMMON_STARTERS = set(
    """
    governo presidente presidenta ministro ministra video videos foto fotos imagem imagens audio audios
    post posts postagem postagens publicacao publicacoes reportagem texto textos mensagem mensagens estudo
    estudos pesquisa pesquisas lei projeto decreto empresa empresas brasileiros brasileiras homem homens mulher
    mulheres crianca criancas pessoas medico medicos cientistas hackers policia justica senado camara congresso
    prefeito prefeita vereador deputado deputada senador senadora jornal site perfil grupo moradores
    """.split()
)
# Ligam partes de um mesmo nome: "Alexandre de Moraes".
_NAME_CONNECTORS = {"de", "da", "do", "dos", "das"}


class KeyTermResult(NamedTuple):
    ok: bool                 # a checagem pode ser a mesma alegação?
    missing: list[str]       # termos-chave da frase ausentes da checagem
    substitutes: list[str]   # termos da alegação, da mesma classe, ausentes da frase


def name_groups(sentence: str) -> list[list[str]]:
    """Nomes próprios da frase, agrupados ("Alexandre de Moraes" -> ["alexandre", "moraes"]).

    Nome = palavra com maiúscula. A primeira palavra só conta se não for uma
    palavra comum de início de frase ("Governo", "Vídeo", "O"...).
    """
    words = re.findall(r"[^\W\d_]+", sentence or "")
    groups: list[list[str]] = []
    current: list[str] = []
    for i, word in enumerate(words):
        plain = _strip_accents(word.lower())
        is_name = word[0].isupper() and plain not in _STOPWORDS
        if i == 0:
            is_name = is_name and plain not in _COMMON_STARTERS
        tokens = [t for t in tokenize(word) if not t.isdigit() and t not in DISEASES]  # doença tem classe própria
        if is_name and tokens:
            current += tokens
        elif current and plain in _NAME_CONNECTORS:
            continue  # "de" entre duas partes de um nome
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return [g for g in groups if g]


def _classes(sentence: str) -> dict[str, list]:
    tokens = tokenize(sentence)                      # números normalizados na frase inteira
    return {
        "nomes": name_groups(sentence),
        "numeros": [t for t in dict.fromkeys(tokens) if t.isdigit()],
        "doencas": [t for t in dict.fromkeys(tokens) if t in DISEASES],
    }


def key_terms(sentence: str) -> list[str]:
    """Nomes próprios, números e doenças da frase."""
    c = _classes(sentence)
    names = [t for group in c["nomes"] for t in group]
    return list(dict.fromkeys(names + c["numeros"] + c["doencas"]))


def key_terms_present(sentence: str, checagem_texts: Iterable[str], claim: str | None = None) -> KeyTermResult:
    """A checagem pode tratar da mesma alegação que a frase?

    1. Termos-chave da frase (nomes, números, doenças) que não aparecem no texto
       da checagem são "ausentes".
    2. Sem a alegação (claim=None), qualquer ausente reprova (regra estrita).
    3. Com a alegação, um ausente só reprova se a alegação tiver um termo da
       MESMA classe que a frase não tem: é a assinatura de uma troca
       (chikungunya ausente + dengue sobrando; Fux ausente + Lewandowski
       sobrando). Um ausente sem par é contexto a mais na frase ("no STF") e
       não reprova. Mudança de 28/09: a regra estrita rejeitava checagens que
       só têm título.
    """
    available = {_stem(t) for text in checagem_texts for t in tokenize(text)}
    mine = _classes(sentence)
    missing = {
        "nomes": [t for group in mine["nomes"] for t in group if _stem(t) not in available],
        "numeros": [t for t in mine["numeros"] if t not in available],
        "doencas": [t for t in mine["doencas"] if _stem(t) not in available],
    }
    all_missing = list(dict.fromkeys(t for terms in missing.values() for t in terms))
    if not all_missing:
        return KeyTermResult(True, [], [])
    if claim is None:
        return KeyTermResult(False, all_missing, [])

    sentence_stems = {_stem(t) for t in tokenize(sentence)}
    theirs = _classes(normalize_claim(claim))
    substitutes: list[str] = []
    if missing["nomes"]:
        substitutes += [" ".join(g) for g in theirs["nomes"] if not any(_stem(t) in sentence_stems for t in g)]
    if missing["numeros"]:
        substitutes += [t for t in theirs["numeros"] if t not in sentence_stems]
    if missing["doencas"]:
        substitutes += [t for t in theirs["doencas"] if _stem(t) not in sentence_stems]
    return KeyTermResult(not substitutes, all_missing, substitutes)
