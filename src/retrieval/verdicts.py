"""Normalização dos vereditos das agências (campo textualRating da Fact Check Tools API).

Formatos encontrados no corpus (27/09/2026):
  - rótulo simples: "falso", "Falso", "Enganoso", "Falta contexto", "verdadeiro",
    "Comprovado", "Sátira", "não_é_bem_assim" (Aos Fatos, com sublinhados);
  - rótulo + explicação (Comprova): "Falso: Na verdade, uma empresa...";
  - texto livre sem rótulo: "É mentirosa a afirmação de que...".

Regra conservadora: só rótulos inequívocos viram "contradiz" ou "apoia"; todo o
resto (inclusive rótulos desconhecidos e texto livre) vira "insuficiente".
Para revisar o mapeamento com os dados atuais:
    python data/corpus/diagnostico.py --vereditos
"""

from __future__ import annotations

import re
import unicodedata

CONTRADIZ = {"falso", "falsa", "fake", "montagem", "mentira", "mentiroso", "e falso", "inventado", "fabricado"}
APOIA = {"verdadeiro", "verdadeira", "verdade", "e verdade", "comprovado", "correto"}

# Rótulo = parte antes de ":" quando essa parte é curta (formato do Comprova).
_MAX_LABEL_CHARS = 40


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def _label(raw: str | None) -> str:
    """Rótulo como publicado: sem sublinhados e sem a explicação após ':'."""
    text = re.sub(r"\s+", " ", (raw or "").replace("_", " ")).strip()
    head, sep, _ = text.partition(":")
    if sep and 0 < len(head.strip()) <= _MAX_LABEL_CHARS:
        return head.strip()
    return text


def normalize_label(raw: str | None) -> str:
    """Rótulo em minúsculas, sem acentos e sem pontuação final (para comparação)."""
    return _strip_accents(_label(raw)).lower().strip(" .!;,")


def stance_from_verdict(raw: str | None) -> str:
    label = normalize_label(raw)
    if label in CONTRADIZ:
        return "contradiz"
    if label in APOIA:
        return "apoia"
    return "insuficiente"


def display_verdict(raw: str | None) -> str | None:
    """Veredito para exibição com atribuição ("Aos Fatos: Falso").

    Mantém o texto da agência, só troca sublinhados por espaços, tira a
    explicação após ':' e põe a primeira letra em maiúscula.
    """
    label = _label(raw)
    if not label:
        return None
    return label[0].upper() + label[1:]
