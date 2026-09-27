"""Agente de Evidências (Seção 4.2 do manual).

Para cada frase da notícia (state.segments), busca trechos de checagens
anteriores no índice vetorial e classifica a relação com um modelo de NLI:
entailment -> "apoia", contradiction -> "contradiz", neutral -> "insuficiente".
Não usa LLM gerador.

Contrato: run(state) -> dict, devolvendo só os campos deste agente.
  {"evidence": [..]}                     busca concluída (lista pode ser vazia)
  {"evidence": None, "warnings": [..]}   o agente falhou (índice, modelo etc.)

As evidências saem como dicionários com exatamente os campos de Evidence da
Seção 3.3; o PipelineState as valida na sua própria classe Evidence.
Decisões de projeto: docs/agents/evidencias_decisoes.md.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

# TEMPORÁRIO: trocar por `from src.state import Evidence, Segment` quando o
# state.py da Seção 3.3 estiver na main (ver evidence_schema.py).
from src.agents.evidence_schema import Evidence, Segment
from src.retrieval import config
from src.retrieval.nli import classify
from src.retrieval.search import Hit, search

logger = logging.getLogger(__name__)
# Log separado com as probabilidades do NLI, para calibração/conformal futura.
nli_logger = logging.getLogger(__name__ + ".nli")

STANCE_BY_LABEL = {
    "entailment": "apoia",
    "contradiction": "contradiz",
    "neutral": "insuficiente",
}


def stance_from_probs(probs: dict[str, float], min_prob: float | None = None) -> str:
    """Rótulo mais provável do NLI; abaixo de min_prob vira "insuficiente"."""
    min_prob = config.NLI_MIN_PROB if min_prob is None else min_prob
    if not probs:
        return "insuficiente"
    label = max(probs, key=probs.get)
    if probs[label] < min_prob:
        return "insuficiente"
    return STANCE_BY_LABEL.get(label, "insuficiente")


_SENTENCE_END = re.compile(r"[.!?…](?=\s|$)")


def make_excerpt(text: str, max_chars: int | None = None) -> str:
    """Trecho literal da checagem, cortado no fim de uma frase se for longo.

    Nunca acrescenta nem reescreve texto: o resultado é sempre um prefixo
    literal do trecho indexado.
    """
    max_chars = config.EXCERPT_MAX_CHARS if max_chars is None else max_chars
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    window = text[:max_chars]
    ends = [m.end() for m in _SENTENCE_END.finditer(window)]
    if ends and ends[-1] >= max_chars // 3:
        return window[: ends[-1]].strip()
    cut = window.rfind(" ")
    return (window[:cut] if cut > 0 else window).strip()


def select_candidates(
    hits: Iterable[Hit],
    threshold: float | None = None,
    max_per_segment: int | None = None,
) -> list[Hit]:
    """Filtra os trechos de uma frase: limiar, URL obrigatória e um trecho por URL."""
    threshold = config.SIM_THRESHOLD if threshold is None else threshold
    max_per_segment = config.MAX_EVIDENCE_PER_SEGMENT if max_per_segment is None else max_per_segment

    best_by_url: dict[str, Hit] = {}
    for hit in hits:
        url = str(hit.metadata.get("source_url") or "").strip()
        if not url or hit.similarity < threshold:
            continue
        if url not in best_by_url or hit.similarity > best_by_url[url].similarity:
            best_by_url[url] = hit
    ranked = sorted(best_by_url.values(), key=lambda h: h.similarity, reverse=True)
    return ranked[:max_per_segment]


def _to_segment(item: Any) -> Segment:
    """Aceita o Segment de qualquer versão do state.py, dicts ou objetos com id/text."""
    if isinstance(item, Segment):
        return item
    if hasattr(item, "model_dump"):
        item = item.model_dump()
    elif not isinstance(item, dict):
        item = {"id": getattr(item, "id"), "text": getattr(item, "text")}
    return Segment.model_validate(item)


def _build_evidence(segment: Segment, hit: Hit, stance: str) -> dict:
    meta = hit.metadata
    verdict = str(meta.get("agency_verdict") or "").strip() or None
    evidence = Evidence(
        segment_id=segment.id,
        stance=stance,
        excerpt=make_excerpt(hit.text),
        source_url=str(meta["source_url"]).strip(),
        source_name=str(meta.get("source_name") or "").strip(),
        agency_verdict=verdict,
    )
    return evidence.model_dump()


def run(state) -> dict:
    try:
        segments = [_to_segment(s) for s in (getattr(state, "segments", None) or [])]
        segments = [s for s in segments if s.text.strip()]
        if not segments:
            return {"evidence": []}

        hits_per_segment = search([s.text for s in segments], k=config.TOP_K)

        candidates: list[tuple[Segment, Hit]] = []
        for segment, hits in zip(segments, hits_per_segment):
            for hit in select_candidates(hits):
                candidates.append((segment, hit))
        if not candidates:
            return {"evidence": []}

        probs_list = classify([(hit.text, segment.text) for segment, hit in candidates])

        evidence = []
        for (segment, hit), probs in zip(candidates, probs_list):
            stance = stance_from_probs(probs)
            nli_logger.debug(
                json.dumps(
                    {
                        "segment_id": segment.id,
                        "chunk_id": hit.chunk_id,
                        "source_url": hit.metadata.get("source_url"),
                        "similarity": round(hit.similarity, 4),
                        "probs": {k: round(v, 4) for k, v in probs.items()},
                        "stance": stance,
                    },
                    ensure_ascii=False,
                )
            )
            evidence.append(_build_evidence(segment, hit, stance))
        return {"evidence": evidence}

    except Exception as exc:  # degradação graciosa (Seção 3.4)
        logger.exception("Agente de Evidências falhou")
        return {
            "evidence": None,
            "warnings": [f"evidencias: {type(exc).__name__}: {exc}"],
        }


# Alias para o graph.py atual, que ainda importa `evidencias_node`.
# Remover quando o orquestrador passar a registrar `evidence.run`.
evidencias_node = run
