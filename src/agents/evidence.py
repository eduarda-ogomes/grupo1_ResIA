"""Agente de Evidências.

Para cada frase da notícia (state.segments), procura checagens publicadas sobre
a MESMA alegação e devolve o que a agência concluiu, com o link. Não usa LLM.

Fluxo, por frase:
  1. Busca: os trechos de checagem mais parecidos com a frase (similaridade
     >= SIM_THRESHOLD), agrupados por checagem; até CLAIM_CANDIDATES checagens.
     A mesma checagem publicada em dois endereços (mesmo título) conta uma vez.
  2. Termos-chave: se a frase troca um nome próprio, número ou doença da
     alegação checada ("chikungunya" no lugar de "dengue"), a checagem é
     descartada. O NLI sozinho não percebe esse tipo de troca.
  3. NLI: a frase e a alegação checada (sem "Foto/Vídeo mostra") precisam se
     implicar em pelo menos uma direção (entailment >= CLAIM_MATCH_MIN_PROB).
  4. Evidência: stance = veredito da agência (falso -> contradiz,
     verdadeiro -> apoia, o resto -> insuficiente); excerpt = título da
     checagem. No máximo MAX_EVIDENCE_PER_SEGMENT por frase.

Isso diverge da Seção 4.2 do manual (NLI entre o trecho e a frase); o motivo e
os números estão em docs/agents/evidencias_decisoes.md.

Contrato: run(state) -> dict
  {"evidence": [..]}                     busca concluída (a lista pode ser vazia)
  {"evidence": None, "warnings": [..]}   o agente falhou (índice, modelo etc.)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

from src.retrieval import config
from src.retrieval.etapa2 import (display_verdict, key_terms_present, normalize_claim, normalize_text,
                                  stance_from_verdict)
from src.retrieval.indice import Hit, get_checagem_texts, get_lead_text, search
from src.retrieval.nli import classify
from src.observabilidade import span
from src.state import Evidence, Segment

logger = logging.getLogger(__name__)


# --- Passo 1: busca e agrupamento ---------------------------------------------

def group_hits_by_url(hits: Iterable[Hit], threshold: float | None = None,
                      max_urls: int | None = None) -> list[list[Hit]]:
    """Trechos acima do limiar e com link, agrupados por checagem, da mais para a menos similar."""
    threshold = config.SIM_THRESHOLD if threshold is None else threshold
    max_urls = config.CLAIM_CANDIDATES if max_urls is None else max_urls
    groups: dict[str, list[Hit]] = {}
    for hit in hits:
        url = str(hit.metadata.get("source_url") or "").strip()
        if url and hit.similarity >= threshold:
            groups.setdefault(url, []).append(hit)
    ranked = [sorted(g, key=lambda h: h.similarity, reverse=True) for g in groups.values()]
    ranked.sort(key=lambda g: g[0].similarity, reverse=True)
    return ranked[:max_urls]


def _meta(group: list[Hit], key: str) -> str:
    """Primeiro valor não vazio de um metadado entre os trechos da checagem."""
    return next((str(h.metadata.get(key) or "").strip() for h in group if h.metadata.get(key)), "")


# Sites que republicam checagens de outro (o BOL republica o UOL Confere).
# Com o mesmo título nos dois, fica o link do site original.
MIRROR_DOMAINS = ("bol.uol.com.br",)


def _is_mirror(group: list[Hit]) -> bool:
    return any(domain in _meta(group, "source_url") for domain in MIRROR_DOMAINS)


def _candidates(hits: list[Hit]) -> list[list[Hit]]:
    """Checagens candidatas de uma frase, sem repetir o mesmo título e só com alegação checada."""
    position: dict[str, int] = {}  # título -> posição em result
    result = []
    for group in group_hits_by_url(hits):
        if not _meta(group, "claim_reviewed"):
            continue  # sem a alegação checada não há como saber se é a mesma alegação
        title = " ".join(normalize_text(_meta(group, "review_title")).split())
        key = title or _meta(group, "source_url")
        if key not in position:
            position[key] = len(result)
            result.append(group)
        elif _is_mirror(result[position[key]]) and not _is_mirror(group):
            result[position[key]] = group  # troca o espelho pelo original, na mesma posição
    return result


# --- Passo 3: NLI -----------------------------------------------------------------

def claim_match_score(forward: dict[str, float], backward: dict[str, float]) -> float:
    """Maior entailment entre as duas direções; basta uma, porque a notícia costuma
    ser mais específica ou mais genérica que a alegação checada."""
    return max(forward.get("entailment", 0.0), backward.get("entailment", 0.0))


# --- Passo 4: evidência --------------------------------------------------------------

_SENTENCE_END = re.compile(r"[.!?…](?=\s|$)")


def make_excerpt(text: str, max_chars: int | None = None) -> str:
    """Prefixo literal do texto, cortado no fim de uma frase (ou num espaço) se for longo."""
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


def _build_evidence(segment: Segment, group: list[Hit]) -> dict:
    url = _meta(group, "source_url")
    excerpt = _meta(group, "review_title") or get_lead_text(url) or group[0].text
    verdict = _meta(group, "agency_verdict")
    return Evidence(
        segment_id=segment.id,
        stance=stance_from_verdict(verdict),
        excerpt=make_excerpt(excerpt),
        source_url=url,
        source_name=_meta(group, "source_name"),
        agency_verdict=display_verdict(verdict),
    ).model_dump()


# --- Nó do grafo -------------------------------------------------------------------

def _to_segment(item: Any) -> Segment:
    """Aceita o Segment de qualquer versão do state.py, dicts ou objetos com id/text."""
    if isinstance(item, dict):
        return Segment.model_validate(item)
    return Segment(id=getattr(item, "id"), text=getattr(item, "text"))


def run(state) -> dict:
    try:
        segments = [_to_segment(s) for s in (getattr(state, "segments", None) or [])]
        segments = [s for s in segments if s.text.strip()]
        if not segments:
            return {"evidence": []}

        # Passos 1 e 2: candidatas de cada frase que passam nos termos-chave.
        with span("evidencias.busca", tipo="RETRIEVER", frases=len(segments), k=config.SEARCH_K):
            hits_per_segment = search([s.text for s in segments], k=config.SEARCH_K)
        with span("evidencias.termos_chave") as s:
            jobs: list[tuple[Segment, list[Hit]]] = []
            candidatas = 0
            for segment, hits in zip(segments, hits_per_segment):
                for group in _candidates(hits):
                    candidatas += 1
                    claim = _meta(group, "claim_reviewed")
                    texts = [claim, _meta(group, "review_title"), *get_checagem_texts(_meta(group, "source_url"))]
                    if key_terms_present(segment.text, texts, claim).ok:
                        jobs.append((segment, group))
            s.set_attribute("pipeline.candidatas", candidatas)
            s.set_attribute("pipeline.aprovadas", len(jobs))
        if not jobs:
            return {"evidence": []}

        with span("evidencias.nli") as s:
            # Passo 3: um único lote de NLI para a notícia inteira (2 direções por candidata).
            pairs = []
            for segment, group in jobs:
                claim = normalize_claim(_meta(group, "claim_reviewed"))
                pairs += [(claim, segment.text), (segment.text, claim)]
            probs = classify(pairs)

            # Passo 4: evidências, no máximo MAX_EVIDENCE_PER_SEGMENT por frase.
            evidence, per_segment = [], {}
            for i, (segment, group) in enumerate(jobs):
                score = claim_match_score(probs[2 * i], probs[2 * i + 1])
                logger.debug(json.dumps({"segment_id": segment.id, "source_url": _meta(group, "source_url"),
                                         "match_score": round(score, 4)}, ensure_ascii=False))
                if score < config.CLAIM_MATCH_MIN_PROB or per_segment.get(segment.id, 0) >= config.MAX_EVIDENCE_PER_SEGMENT:
                    continue
                evidence.append(_build_evidence(segment, group))
                per_segment[segment.id] = per_segment.get(segment.id, 0) + 1
            s.set_attribute("pipeline.pares", len(pairs))
            s.set_attribute("pipeline.evidencias", len(evidence))
        return {"evidence": evidence}

    except Exception as exc:  # degradação graciosa (Seção 3.4)
        logger.exception("Agente de Evidências falhou")
        return {"evidence": None, "warnings": [f"evidencias: {type(exc).__name__}: {exc}"]}


# Alias para o graph.py atual, que ainda importa `evidencias_node`.
evidencias_node = run
