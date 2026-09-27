"""Classificação NLI (premissa = trecho da checagem, hipótese = frase da notícia)."""

from __future__ import annotations

from typing import Sequence

from src.retrieval import config

LABELS = ("entailment", "neutral", "contradiction")

_pipeline = None


def get_nli():
    """Carrega o mDeBERTa uma única vez por processo."""
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline

        device = config.pick_device()
        kwargs = {}
        if config.NLI_FP16 and device in {"cuda", "mps"}:
            import torch

            kwargs["torch_dtype"] = torch.float16
        _pipeline = pipeline(
            "text-classification",
            model=config.NLI_MODEL,
            device=device,
            top_k=None,  # devolve as três probabilidades, não só o rótulo vencedor
            **kwargs,
        )
    return _pipeline


def _normalize(scores: list[dict]) -> dict[str, float]:
    probs = {label: 0.0 for label in LABELS}
    for item in scores:
        probs[item["label"].strip().lower()] = float(item["score"])
    return probs


def classify(pairs: Sequence[tuple[str, str]]) -> list[dict[str, float]]:
    """Recebe pares (premissa, hipótese) e devolve as probabilidades de cada rótulo.

    Os pares vão como text/text_pair, que é como o modelo foi treinado; uma
    string única com "[SEP]" no meio não é tratada como par.
    """
    if not pairs:
        return []
    inputs = [{"text": premise, "text_pair": hypothesis} for premise, hypothesis in pairs]
    outputs = get_nli()(inputs, batch_size=config.BATCH_SIZE, truncation=True)
    # Com uma única entrada, algumas versões devolvem a lista sem o nível externo.
    if outputs and isinstance(outputs[0], dict):
        outputs = [outputs]
    return [_normalize(scores) for scores in outputs]
