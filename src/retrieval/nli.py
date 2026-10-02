"""Classificação NLI com o mDeBERTa: premissa -> hipótese."""

from __future__ import annotations

from typing import Sequence

from src.retrieval import config

LABELS = ("entailment", "neutral", "contradiction")

_pipeline = None


def make_nli_pipeline(fp16: bool | None = None):
    """Cria o pipeline do NLI; fp16 só vale na GPU (cuda/mps). Padrão: config.NLI_FP16."""
    from transformers import pipeline

    fp16 = config.NLI_FP16 if fp16 is None else fp16
    device = config.pick_device()
    extra = {}
    if fp16 and device in {"cuda", "mps"}:
        import torch

        extra["torch_dtype"] = torch.float16
    return pipeline(
        "text-classification",
        model=config.NLI_MODEL,
        device=device,
        top_k=None,  # devolve as três probabilidades, não só o rótulo vencedor
        **extra,
    )


def get_nli():
    """Carrega o modelo uma única vez por processo."""
    global _pipeline
    if _pipeline is None:
        _pipeline = make_nli_pipeline()
    return _pipeline


def classify(pairs: Sequence[tuple[str, str]], pipe=None) -> list[dict[str, float]]:
    """Recebe pares (premissa, hipótese) e devolve {rótulo: probabilidade} para cada par.

    Os pares vão como text/text_pair, que é como o modelo foi treinado. `pipe` permite
    usar outro pipeline (ex.: comparar fp32 e fp16); padrão: o do agente.
    """
    if not pairs:
        return []
    inputs = [{"text": premise, "text_pair": hypothesis} for premise, hypothesis in pairs]
    outputs = (pipe or get_nli())(inputs, batch_size=config.BATCH_SIZE, truncation=True)
    if outputs and isinstance(outputs[0], dict):  # algumas versões tiram o nível externo com 1 entrada
        outputs = [outputs]
    results = []
    for scores in outputs:
        probs = {label: 0.0 for label in LABELS}
        for item in scores:
            probs[item["label"].strip().lower()] = float(item["score"])
        results.append(probs)
    return results
