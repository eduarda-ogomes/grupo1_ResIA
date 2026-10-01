"""Classificação NLI com o mDeBERTa: premissa -> hipótese."""

from __future__ import annotations

from typing import Sequence

from src.retrieval import config

LABELS = ("entailment", "neutral", "contradiction")

_pipeline = None


def get_nli():
    """Carrega o modelo uma única vez por processo."""
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline

        _pipeline = pipeline(
            "text-classification",
            model=config.NLI_MODEL,
            device=config.pick_device(),
            top_k=None,  # devolve as três probabilidades, não só o rótulo vencedor
        )
    return _pipeline


def classify(pairs: Sequence[tuple[str, str]]) -> list[dict[str, float]]:
    """Recebe pares (premissa, hipótese) e devolve {rótulo: probabilidade} para cada par.

    Os pares vão como text/text_pair, que é como o modelo foi treinado.
    """
    if not pairs:
        return []
    inputs = [{"text": premise, "text_pair": hypothesis} for premise, hypothesis in pairs]
    outputs = get_nli()(inputs, batch_size=config.BATCH_SIZE, truncation=True)
    if outputs and isinstance(outputs[0], dict):  # algumas versões tiram o nível externo com 1 entrada
        outputs = [outputs]
    results = []
    for scores in outputs:
        probs = {label: 0.0 for label in LABELS}
        for item in scores:
            probs[item["label"].strip().lower()] = float(item["score"])
        results.append(probs)
    return results
