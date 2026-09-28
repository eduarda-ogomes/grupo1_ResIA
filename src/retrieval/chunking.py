"""Divisão das checagens em trechos (chunks) para o índice.

Regras:
- Cada parágrafo é classificado como "descreve o boato" ou não (heurística por
  expressões, usada pela proteção da opção 1).
- Parágrafos consecutivos com a mesma classificação são agrupados até
  CHUNK_MAX_CHARS, com sobreposição de CHUNK_OVERLAP_PARAGRAPHS parágrafos.
- Um trecho nunca mistura parágrafo que descreve o boato com parágrafo de
  conclusão; assim a marcação vale para o trecho inteiro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.retrieval import config

# Expressões típicas de parágrafos que reproduzem a alegação checada.
# Lista inicial, a revisar com exemplos reais do corpus.
_RUMOR_PATTERNS = [
    # "Circula nas redes...", "circulam no WhatsApp...", "circula um vídeo..."
    r"\bcircula(?:m|ndo)?\s+(?:nas?\s+redes|no\s+(?:whatsapp|facebook|instagram|tiktok|telegram|kwai|youtube|x)\b"
    r"|pelas?\s+redes|em\s+grupos|um\s+v[íi]deo|uma\s+(?:mensagem|publica[çc][ãa]o|imagem|corrente)"
    r"|um\s+(?:texto|[áa]udio|post))",
    r"\bviraliz(?:ou|aram|a|am|ando)\b",
    # "Um vídeo afirma...", "posts alegam...", "a publicação diz..."
    r"\b(?:post|posts|postagem|postagens|publica[çc][ãa]o|publica[çc][õo]es|v[íi]deo|v[íi]deos"
    r"|mensagem|mensagens|corrente|correntes|[áa]udio|[áa]udios|tu[íi]te|tu[íi]tes)\b"
    r"[^.!?]{0,80}?\b(?:afirma|afirmam|diz|dizem|alega|alegam|garante|garantem|sugere|sugerem"
    r"|mostra|mostram|sustenta|sustentam|defende|defendem)\b",
    r"\bsegundo\s+(?:o|a|os|as)\s+(?:post|postagem|publica[çc][ãa]o|v[íi]deo|mensagem|corrente)",
    r"\bcompartilhad[oa]s?\s+(?:nas|pelas)\s+redes",
]
_RUMOR_RE = re.compile("|".join(_RUMOR_PATTERNS), re.IGNORECASE)

# Marcadores de conclusão da agência. Um parágrafo com um destes marcadores é
# conclusão, mesmo que também mencione o post ("É falso que um vídeo mostra...").
# Adicionado em 27/09 depois de medir o corpus real: 230 dos 573 parágrafos
# marcados pela versão anterior eram conclusões.
_DEBUNK_PATTERNS = [
    r"\b(?:é|são|foi|foram|está|estão)\s+(?:falso|falsa|falsos|falsas|enganos[oa]s?|mentiros[oa]s?"
    r"|montage[mn]s?|editad[oa]s?|manipulad[oa]s?|adulterad[oa]s?|antig[oa]s?|descontextualizad[oa]s?"
    r"|gerad[oa]s?\s+(?:por|com)\s+(?:ia\b|intelig))",
    r"\bnão\s+(?:é|são)\s+(?:verdade|real|reais|verdadeir[oa]s?|autêntic[oa]s?)\b",
    r"\bnão\s+procede\b",
    r"\bnão\s+(?:é|são)\s+(?:atua(?:l|is)|recentes?)\b",
    r"\bnão\s+(?:foi|foram)\s+(?:gravad[oa]s?|feit[oa]s?|registrad[oa]s?|dit[oa]s?|publicad[oa]s?)\b",
    r"\bnão\s+há\s+(?:registro|registros|provas?|evidências?|indícios?)\b",
    r"\b(?:mentem|mente|engana|enganam|distorce|distorcem|distorceu)\b",
    r"\bna\s+(?:verdade|realidade)\b",
    r"\bnão\s+tem\s+(?:qualquer\s+|nenhuma\s+)?relação\b",
    r"\bcomo\s+se\s+(?:fosse|fossem|tratasse)\s+(?:de\s+)?(?:(?:um|uma|uns|umas)\s+)?(?:\w+\s+)?"
    r"(?:atua(?:l|is)|recentes?|rea(?:l|is)|verdadeir[oa]s?|autêntic[oa]s?)\b",
    r"\b(?:é|são|foi|foram)\s+(?:de|gravad[oa]s?\s+em|feit[oa]s?\s+em|registrad[oa]s?\s+em)\s+(?:\d{4}|\d{1,2}\s+de)\b",
    r"\b(?:tirad[oa]s?|fora)\s+de\s+contexto\b",
    r"\bdesinforma(?:ção|ções|m|tiv[oa]s?)?\b",
]
_DEBUNK_RE = re.compile("|".join(_DEBUNK_PATTERNS), re.IGNORECASE)


def is_conclusion(paragraph: str) -> bool:
    """True se o parágrafo traz um marcador de conclusão da agência."""
    return bool(_DEBUNK_RE.search(paragraph))


def describes_rumor(paragraph: str) -> bool:
    """True se o parágrafo parece reproduzir o boato em vez de concluir a checagem.

    Limitação conhecida: o texto do post colado sem introdução (como o Aos Fatos
    costuma fazer no 3º parágrafo) não tem marcador e não é detectado.
    """
    return bool(_RUMOR_RE.search(paragraph)) and not is_conclusion(paragraph)


@dataclass
class Chunk:
    text: str
    describes_rumor: bool


def split_paragraphs(text: str, min_chars: int | None = None) -> list[str]:
    min_chars = config.MIN_PARAGRAPH_CHARS if min_chars is None else min_chars
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n+", text or "")]
    return [p for p in paragraphs if len(p) >= min_chars]


def build_chunks(
    text: str,
    max_chars: int | None = None,
    overlap: int | None = None,
    min_chars: int | None = None,
) -> list[Chunk]:
    max_chars = config.CHUNK_MAX_CHARS if max_chars is None else max_chars
    overlap = config.CHUNK_OVERLAP_PARAGRAPHS if overlap is None else overlap

    chunks: list[Chunk] = []
    current: list[str] = []
    current_flag: bool | None = None
    new_since_flush = False  # evita emitir um trecho feito só de sobreposição

    def flush():
        nonlocal new_since_flush
        if current and new_since_flush:
            chunks.append(Chunk("\n".join(current), bool(current_flag)))
        new_since_flush = False

    for paragraph in split_paragraphs(text, min_chars):
        flag = describes_rumor(paragraph)
        too_long = len("\n".join(current + [paragraph])) > max_chars
        if current and (flag != current_flag or too_long):
            flush()
            # Sobreposição só dentro de uma sequência com a mesma marcação.
            carry = current[-overlap:] if (overlap and flag == current_flag) else []
            if carry and len("\n".join(carry + [paragraph])) > max_chars:
                carry = []
            current = list(carry)
        if not current:
            current_flag = flag
        current.append(paragraph)
        new_since_flush = True
    flush()
    return chunks
