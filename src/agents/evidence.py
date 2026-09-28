"""Agente de Evidências (Seção 4.2 do manual, com a etapa "mesma alegação").

Para cada frase da notícia (state.segments), busca trechos de checagens
anteriores no índice vetorial. Não usa LLM gerador. Dois modos
(config.STANCE_MODE, variável EVIDENCE_STANCE_MODE):

  "alegacao" (PADRÃO desde 27/09/2026; diverge da Seção 4.2)
      1. Agrupa os trechos recuperados por checagem (URL).
      2. Etapa "mesma alegação":
         a. termos-chave (KEY_TERM_CHECK, ligada): um nome próprio, número ou
            doença da frase ausente da checagem reprova quando a alegação tem
            um termo da mesma classe ausente da frase (troca);
         b. NLI entre a frase e a alegação checada (claim_reviewed), nas duas
            direções; segue se o entailment passar de CLAIM_MATCH_MIN_PROB em
            pelo menos uma. Com CLAIM_NORMALIZE (ligada), a alegação perde o
            "Foto/Vídeo/Imagem mostra" antes do NLI.
         Avalia até CLAIM_CANDIDATES checagens por frase (a mesma checagem em
         dois endereços conta uma vez) e só depois limita a saída a
         MAX_EVIDENCE_PER_SEGMENT.
      3. Stance = veredito da agência (falso -> contradiz, verdadeiro -> apoia,
         o resto -> insuficiente).
      4. excerpt = título da checagem (a conclusão da agência); na falta dele,
         o parágrafo de abertura.
      Checagens sem claim_reviewed seguem o modo "trecho".

  "trecho" (método da Seção 4.2)
      NLI com o trecho recuperado como premissa e a frase como hipótese:
      entailment -> "apoia", contradiction -> "contradiz", neutral -> "insuficiente".

Por que o padrão mudou: nos testes com o modelo real, o NLI sobre o trecho deu
"apoia" (0,99) para um parágrafo que só reproduzia o boato e "contradiz" (0,93)
para uma checagem de dengue diante de uma frase sobre chikungunya. E o NLI entre
alegações também não distingue troca de nome (dengue x chikungunya: 0,98), daí
a checagem de termos-chave. Detalhes em docs/agents/evidencias_decisoes.md.

Contrato: run(state) -> dict, devolvendo só os campos deste agente.
  {"evidence": [..]}                     busca concluída (lista pode ser vazia)
  {"evidence": None, "warnings": [..]}   o agente falhou (índice, modelo etc.)
As evidências saem como dicionários com exatamente os campos de Evidence da
Seção 3.3; o PipelineState as valida na sua própria classe Evidence.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# TEMPORÁRIO: trocar por `from src.state import Evidence, Segment` quando o
# state.py da Seção 3.3 estiver na main (ver evidence_schema.py).
from src.agents.evidence_schema import Evidence, Segment
from src.retrieval import config
from src.retrieval.nli import classify
from src.retrieval.claim_match import key_terms_present, normalize_claim, normalize_text
from src.retrieval.search import Hit, get_checagem_texts, get_lead_text, search
from src.retrieval.verdicts import display_verdict, stance_from_verdict

logger = logging.getLogger(__name__)
# Log separado com as probabilidades do NLI, para análise de erros e calibração.
nli_logger = logging.getLogger(__name__ + ".nli")

STANCE_BY_LABEL = {
    "entailment": "apoia",
    "contradiction": "contradiz",
    "neutral": "insuficiente",
}


# --- Funções puras ----------------------------------------------------------

def stance_from_probs(probs: dict[str, float], min_prob: float | None = None) -> str:
    """Rótulo mais provável do NLI; abaixo de min_prob vira "insuficiente"."""
    min_prob = config.NLI_MIN_PROB if min_prob is None else min_prob
    if not probs:
        return "insuficiente"
    label = max(probs, key=probs.get)
    if probs[label] < min_prob:
        return "insuficiente"
    return STANCE_BY_LABEL.get(label, "insuficiente")


def claim_match_score(forward: dict[str, float], backward: dict[str, float]) -> float:
    """Maior entailment entre as duas direções (alegação -> frase, frase -> alegação).

    A notícia costuma ser mais específica ou mais genérica que a alegação
    checada, então basta uma direção.
    """
    return max(forward.get("entailment", 0.0), backward.get("entailment", 0.0))


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


def group_hits_by_url(
    hits: Iterable[Hit],
    threshold: float | None = None,
    max_urls: int | None = None,
) -> list[list[Hit]]:
    """Filtra os trechos de uma frase (limiar e URL obrigatória) e agrupa por checagem.

    Devolve até max_urls grupos, do mais para o menos similar; dentro de cada
    grupo, os trechos também vêm do mais para o menos similar.
    """
    threshold = config.SIM_THRESHOLD if threshold is None else threshold
    max_urls = config.MAX_EVIDENCE_PER_SEGMENT if max_urls is None else max_urls

    groups: dict[str, list[Hit]] = {}
    for hit in hits:
        url = str(hit.metadata.get("source_url") or "").strip()
        if not url or hit.similarity < threshold:
            continue
        groups.setdefault(url, []).append(hit)
    ranked = [sorted(g, key=lambda h: h.similarity, reverse=True) for g in groups.values()]
    ranked.sort(key=lambda g: g[0].similarity, reverse=True)
    return ranked[:max_urls]


def select_candidates(
    hits: Iterable[Hit],
    threshold: float | None = None,
    max_per_segment: int | None = None,
) -> list[Hit]:
    """Modo trecho: o trecho mais similar de cada checagem acima do limiar."""
    return [group[0] for group in group_hits_by_url(hits, threshold, max_per_segment)]


def _best_non_rumor(group: list[Hit]) -> Hit:
    for hit in group:
        if not hit.metadata.get("describes_rumor"):
            return hit
    return group[0]


def _to_segment(item: Any) -> Segment:
    """Aceita o Segment de qualquer versão do state.py, dicts ou objetos com id/text."""
    if isinstance(item, Segment):
        return item
    if hasattr(item, "model_dump"):
        item = item.model_dump()
    elif not isinstance(item, dict):
        item = {"id": getattr(item, "id"), "text": getattr(item, "text")}
    return Segment.model_validate(item)


def _build_evidence(segment: Segment, metadata: dict, excerpt_source: str, stance: str) -> dict:
    evidence = Evidence(
        segment_id=segment.id,
        stance=stance,
        excerpt=make_excerpt(excerpt_source),
        source_url=str(metadata["source_url"]).strip(),
        source_name=str(metadata.get("source_name") or "").strip(),
        agency_verdict=display_verdict(metadata.get("agency_verdict")),
    )
    return evidence.model_dump()


def _log(**fields) -> None:
    if nli_logger.isEnabledFor(logging.DEBUG):
        nli_logger.debug(json.dumps(fields, ensure_ascii=False, default=str))


def _rounded(probs: dict[str, float]) -> dict[str, float]:
    return {k: round(v, 4) for k, v in probs.items()}


# --- Modo "trecho" (Seção 4.2) ------------------------------------------------

def _run_trecho(segments: list[Segment], hits_per_segment: list[list[Hit]]) -> list[dict]:
    candidates: list[tuple[Segment, Hit]] = []
    for segment, hits in zip(segments, hits_per_segment):
        for hit in select_candidates(hits):
            candidates.append((segment, hit))
    if not candidates:
        return []

    probs_list = classify([(hit.text, segment.text) for segment, hit in candidates])
    evidence = []
    for (segment, hit), probs in zip(candidates, probs_list):
        stance = stance_from_probs(probs)
        _log(mode="trecho", segment_id=segment.id, source_url=hit.metadata.get("source_url"),
             similarity=round(hit.similarity, 4), probs=_rounded(probs), stance=stance)
        evidence.append(_build_evidence(segment, hit.metadata, hit.text, stance))
    return evidence


# --- Modo "alegacao" (padrão) ------------------------------------------------

@dataclass
class _Job:
    segment: Segment
    group: list[Hit]
    claim: str
    pair_indexes: list[int] = field(default_factory=list)
    rejected_by_terms: bool = False

    @property
    def metadata(self) -> dict:
        return self.group[0].metadata

    @property
    def url(self) -> str:
        return str(self.metadata.get("source_url"))


def _first_meta(group: list[Hit], key: str) -> str:
    return next((str(h.metadata.get(key) or "").strip() for h in group
                 if str(h.metadata.get(key) or "").strip()), "")


def _same_article_key(group: list[Hit]) -> str:
    """Mesma checagem publicada em dois endereços (ex.: UOL e BOL) tem o mesmo título."""
    title = _first_meta(group, "review_title")
    return " ".join(normalize_text(title).split()) if title else str(group[0].metadata.get("source_url"))


def _run_alegacao(segments: list[Segment], hits_per_segment: list[list[Hit]]) -> list[dict]:
    jobs: list[_Job] = []
    for segment, hits in zip(segments, hits_per_segment):
        seen: set[str] = set()
        # Avalia até CLAIM_CANDIDATES checagens; o limite de saída vem depois da etapa 2.
        for group in group_hits_by_url(hits, max_urls=config.CLAIM_CANDIDATES):
            key = _same_article_key(group)
            if key in seen:
                continue
            seen.add(key)
            jobs.append(_Job(segment, group, _first_meta(group, "claim_reviewed")))
    if not jobs:
        return []

    # Termos-chave (nomes próprios, números, doenças) antes do NLI: barata e
    # rejeita trocas de nome que o NLI deixa passar.
    if config.KEY_TERM_CHECK:
        for job in jobs:
            if not job.claim:
                continue
            texts = [job.claim, _first_meta(job.group, "review_title"), *get_checagem_texts(job.url)]
            result = key_terms_present(job.segment.text, texts, job.claim)
            job.rejected_by_terms = not result.ok
            if job.rejected_by_terms:
                _log(mode="alegacao", segment_id=job.segment.id, source_url=job.url, claim=job.claim,
                     matched=False, reason="troca de termo-chave", missing=result.missing,
                     substitutes=result.substitutes)
        jobs = [job for job in jobs if not job.rejected_by_terms]
        if not jobs:
            return []

    # Um único lote de NLI para a notícia inteira.
    pairs: list[tuple[str, str]] = []
    for job in jobs:
        if job.claim:
            # Variante (b): sem "Foto/Vídeo mostra" no início da alegação.
            claim = normalize_claim(job.claim) if config.CLAIM_NORMALIZE else job.claim
            job.pair_indexes = [len(pairs), len(pairs) + 1]
            pairs += [(claim, job.segment.text), (job.segment.text, claim)]
        else:  # sem alegação checada: cai no método da Seção 4.2 para esta checagem
            job.pair_indexes = [len(pairs)]
            pairs.append((_best_non_rumor(job.group).text, job.segment.text))
    probs_list = classify(pairs)

    evidence = []
    per_segment: dict[str, int] = {}
    for job in jobs:
        if per_segment.get(job.segment.id, 0) >= config.MAX_EVIDENCE_PER_SEGMENT:
            continue
        best = job.group[0]
        if job.claim:
            forward, backward = (probs_list[i] for i in job.pair_indexes)
            score = claim_match_score(forward, backward)
            matched = score >= config.CLAIM_MATCH_MIN_PROB
            stance = stance_from_verdict(job.metadata.get("agency_verdict")) if matched else None
            _log(mode="alegacao", segment_id=job.segment.id, source_url=job.url,
                 similarity=round(best.similarity, 4), claim=job.claim,
                 claim_nli=pairs[job.pair_indexes[0]][0],
                 forward=_rounded(forward), backward=_rounded(backward),
                 match_score=round(score, 4), matched=matched, stance=stance)
            if not matched:
                continue  # outra alegação: tratada como "nenhuma checagem"
            # excerpt: título da checagem (conclusão da agência, literal) -> abertura -> melhor trecho.
            excerpt_source = (_first_meta(job.group, "review_title") or get_lead_text(job.url)
                              or _best_non_rumor(job.group).text)
        else:
            probs = probs_list[job.pair_indexes[0]]
            stance = stance_from_probs(probs)
            excerpt_source = pairs[job.pair_indexes[0]][0]
            _log(mode="alegacao/sem_claim", segment_id=job.segment.id, source_url=job.url,
                 similarity=round(best.similarity, 4), probs=_rounded(probs), stance=stance)
        evidence.append(_build_evidence(job.segment, job.metadata, excerpt_source, stance))
        per_segment[job.segment.id] = per_segment.get(job.segment.id, 0) + 1
    return evidence


# --- Nó do grafo ---------------------------------------------------------------

def run(state) -> dict:
    try:
        mode = config.STANCE_MODE
        if mode not in config.STANCE_MODES:
            raise ValueError(f"EVIDENCE_STANCE_MODE inválido: {mode!r} (use {config.STANCE_MODES})")

        segments = [_to_segment(s) for s in (getattr(state, "segments", None) or [])]
        segments = [s for s in segments if s.text.strip()]
        if not segments:
            return {"evidence": []}

        hits_per_segment = search([s.text for s in segments], k=config.SEARCH_K)
        if mode == "trecho":
            evidence = _run_trecho(segments, hits_per_segment)
        else:
            evidence = _run_alegacao(segments, hits_per_segment)
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
