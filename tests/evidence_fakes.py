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


NEUTRAL = {"entailment": 0.1, "neutral": 0.8, "contradiction": 0.1}
ENTAILMENT = {"entailment": 0.9, "neutral": 0.08, "contradiction": 0.02}
CONTRADICTION = {"entailment": 0.03, "neutral": 0.12, "contradiction": 0.85}


class FakeClassify:
    """Devolve probabilidades pré-definidas.

    As chaves podem ser o par (premissa, hipótese) ou só a premissa; o par tem
    prioridade. Sem correspondência, devolve `default` (neutro).
    """

    def __init__(self, probs: dict, default=None):
        self.probs = probs
        self.default = default or NEUTRAL
        self.calls: list[list[tuple[str, str]]] = []

    def __call__(self, pairs):
        self.calls.append(list(pairs))
        return [dict(self.probs.get((p, h), self.probs.get(p, self.default))) for p, h in pairs]


def mamao_fakes() -> tuple[SimpleNamespace, FakeSearch, FakeClassify, dict]:
    """Caso da Seção 4.6 com busca e NLI simulados."""
    segments = load_fixture("caso_mamao_dengue/segments.json")["segments"]
    expected = load_fixture("caso_mamao_dengue/evidence.json")
    lupa, aosfatos = expected["evidence"]
    text = {s["id"]: s["text"] for s in segments}

    search = FakeSearch(
        {
            # s01: só um trecho abaixo do limiar -> nenhum objeto (Seção 4.6).
            text["s01"]: [hit("Trecho sobre outro assunto.", 0.40, "https://exemplo.org/outra")],
            # s02: dois trechos da mesma URL (deduplicação) e um sem URL (descartado).
            text["s02"]: [
                hit(lupa["excerpt"], 0.86, lupa["source_url"], lupa["source_name"], "Falso"),
                hit("Outro parágrafo da mesma checagem.", 0.79, lupa["source_url"], lupa["source_name"], "Falso"),
                hit("Trecho sem link de origem.", 0.90, ""),
            ],
            text["s03"]: [hit(aosfatos["excerpt"], 0.81, aosfatos["source_url"], aosfatos["source_name"], "Falso")],
        }
    )
    classify = FakeClassify({lupa["excerpt"]: CONTRADICTION, aosfatos["excerpt"]: CONTRADICTION})
    return make_state(segments), search, classify, expected


# --- Modo "alegacao" ---------------------------------------------------------

FACHIN_URL = "https://exemplo.org/checagem/foto-fachin-moraes-ia"
FACHIN_CLAIM = "Foto mostra Edson Fachin apontando o dedo para Alexandre de Moraes em discussão"
FACHIN_LEAD = (
    "Foi gerada por IA a foto que mostra uma discussão entre dois ministros do STF. "
    "A imagem circula nas redes como se fosse real."
)
FACHIN_CLAIM_NORMALIZADA = "Edson Fachin apontando o dedo para Alexandre de Moraes em discussão"
OUTRA_URL = "https://exemplo.org/checagem/outro-fato-fachin"
OUTRA_CLAIM = "Fachin levou para a Presidência do STF as investigações sobre o INSS"


def claim_mode_fakes():
    """Uma frase, duas checagens candidatas: só a primeira é a mesma alegação.

    Dados sintéticos (agência e URLs fictícias).
    """
    segment = {"id": "s01", "text": "Fachin apontou o dedo para Moraes durante uma discussão no STF."}
    search = FakeSearch(
        {
            segment["text"]: [
                # O parágrafo que repete o boato é o mais parecido com a frase.
                hit("O clima esquentou, enfiou o dedo na cara dele.", 0.60, FACHIN_URL, verdict="falso",
                    claim_reviewed=FACHIN_CLAIM, describes_rumor=True),
                hit("Trecho do meio da checagem sobre a foto.", 0.59, FACHIN_URL, verdict="falso",
                    claim_reviewed=FACHIN_CLAIM, describes_rumor=False),
                hit("No mesmo dia, Fachin levou para a Presidência...", 0.57, OUTRA_URL, verdict="Enganoso",
                    claim_reviewed=OUTRA_CLAIM, describes_rumor=False),
                hit("Trecho de outro assunto.", 0.45, "https://exemplo.org/terceira", claim_reviewed="Outra coisa"),
            ]
        }
    )
    classify = FakeClassify(
        {
            # Mesma alegação: entailment só na direção alegação -> frase
            # (com e sem o "Foto mostra", porque a normalização é ligada por padrão).
            (FACHIN_CLAIM, segment["text"]): ENTAILMENT,
            (segment["text"], FACHIN_CLAIM): NEUTRAL,
            (FACHIN_CLAIM_NORMALIZADA, segment["text"]): ENTAILMENT,
            (segment["text"], FACHIN_CLAIM_NORMALIZADA): NEUTRAL,
            # Outra alegação sobre o mesmo ministro: sem entailment.
            (OUTRA_CLAIM, segment["text"]): NEUTRAL,
            (segment["text"], OUTRA_CLAIM): CONTRADICTION,
        }
    )
    leads = {FACHIN_URL: FACHIN_LEAD}
    return make_state([segment]), search, classify, leads
