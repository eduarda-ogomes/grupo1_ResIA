"""Dublês da busca e do NLI para testar o Agente de Evidências sem modelos nem índice."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.retrieval.search import Hit

FIXTURES = Path(__file__).resolve().parent / "fixtures"

EVIDENCE_FIELDS = {"segment_id", "stance", "excerpt", "source_url", "source_name", "agency_verdict"}


def load_fixture(relative: str) -> dict:
    with (FIXTURES / relative).open(encoding="utf-8") as f:
        return json.load(f)


def make_state(segments: list[dict]) -> SimpleNamespace:
    """O agente só lê state.segments; não precisa do PipelineState completo."""
    return SimpleNamespace(segments=segments)


def hit(text: str, similarity: float, url: str, name: str = "Agência Exemplo",
        verdict: str = "Falso", chunk_id: str | None = None, **extra) -> Hit:
    return Hit(
        chunk_id=chunk_id or f"{abs(hash((url, text))) % 10**8:08d}-000",
        text=text,
        similarity=similarity,
        metadata={"source_url": url, "source_name": name, "agency_verdict": verdict, **extra},
    )


class FakeSearch:
    """Devolve hits pré-definidos por texto da frase e registra as chamadas."""

    def __init__(self, hits_by_text: dict[str, list[Hit]]):
        self.hits_by_text = hits_by_text
        self.calls: list[list[str]] = []

    def __call__(self, texts, k=None):
        self.calls.append(list(texts))
        return [list(self.hits_by_text.get(t, []))[: k or 5] for t in texts]


class FakeClassify:
    """Devolve probabilidades pré-definidas por premissa (texto do trecho)."""

    def __init__(self, probs_by_premise: dict[str, dict[str, float]], default=None):
        self.probs_by_premise = probs_by_premise
        self.default = default or {"entailment": 0.1, "neutral": 0.8, "contradiction": 0.1}
        self.calls: list[list[tuple[str, str]]] = []

    def __call__(self, pairs):
        self.calls.append(list(pairs))
        return [dict(self.probs_by_premise.get(p, self.default)) for p, _ in pairs]


def mamao_fakes() -> tuple[SimpleNamespace, FakeSearch, FakeClassify, dict]:
    """Caso da Seção 4.6 com busca e NLI simulados."""
    segments = load_fixture("caso_mamao_dengue/segments.json")["segments"]
    expected = load_fixture("caso_mamao_dengue/evidence.json")
    lupa, aosfatos = expected["evidence"]
    text = {s["id"]: s["text"] for s in segments}

    search = FakeSearch(
        {
            # s01: só um trecho abaixo do limiar -> nenhum objeto (Seção 4.6).
            text["s01"]: [hit("Trecho sobre outro assunto.", 0.55, "https://exemplo.org/outra")],
            # s02: dois trechos da mesma URL (deduplicação) e um sem URL (descartado).
            text["s02"]: [
                hit(lupa["excerpt"], 0.86, lupa["source_url"], lupa["source_name"], "Falso"),
                hit("Outro parágrafo da mesma checagem.", 0.79, lupa["source_url"], lupa["source_name"], "Falso"),
                hit("Trecho sem link de origem.", 0.90, ""),
            ],
            text["s03"]: [hit(aosfatos["excerpt"], 0.81, aosfatos["source_url"], aosfatos["source_name"], "Falso")],
        }
    )
    contradiction = {"entailment": 0.03, "neutral": 0.12, "contradiction": 0.85}
    classify = FakeClassify({lupa["excerpt"]: contradiction, aosfatos["excerpt"]: contradiction})
    return make_state(segments), search, classify, expected
