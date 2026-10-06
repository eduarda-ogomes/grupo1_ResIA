"""Configuração do Agente de Evidências.

Só o que alguém realmente vai ajustar pode ser sobrescrito por variável de
ambiente (limiares, quantidades, modelos, caminhos). O resto é constante.
Os valores e o motivo de cada um estão em docs/agents/evidencias_decisoes.md.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Ajustáveis por variável de ambiente ------------------------------------
EMBEDDING_MODEL = os.getenv("EVIDENCE_EMBEDDING_MODEL", "BAAI/bge-m3")
NLI_MODEL = os.getenv("EVIDENCE_NLI_MODEL", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
DEVICE = os.getenv("EVIDENCE_DEVICE", "")            # "cpu", "cuda", "mps"; vazio = automático
CHROMA_PATH = Path(os.getenv("EVIDENCE_CHROMA_PATH", str(REPO_ROOT / "chroma_data")))
RAW_DIR = Path(os.getenv("EVIDENCE_RAW_DIR", str(REPO_ROOT / "data" / "corpus" / "raw")))

# Limiares. O do NLI foi calibrado em 01/10 (eval/avaliar_evidencias.py calibrar, split de
# calibração) e confirmado no split de teste; ver o ADR em docs/agents/evidencias_decisoes.md.
SIM_THRESHOLD = float(os.getenv("EVIDENCE_SIM_THRESHOLD", 0.55))              # similaridade mínima na busca
CLAIM_MATCH_MIN_PROB = float(os.getenv("EVIDENCE_CLAIM_MATCH_MIN_PROB", 0.8))  # entailment mínimo na etapa 2

SEARCH_K = int(os.getenv("EVIDENCE_SEARCH_K", 10))                   # trechos buscados por frase
CLAIM_CANDIDATES = int(os.getenv("EVIDENCE_CLAIM_CANDIDATES", 6))    # checagens avaliadas na etapa 2
MAX_EVIDENCE_PER_SEGMENT = int(os.getenv("EVIDENCE_MAX_PER_SEGMENT", 3))

# --- Constantes -------------------------------------------------------------
COLLECTION_PREFIX = "checagens"
BATCH_SIZE = 16
EMBEDDING_FP16 = True        # embeddings em fp16 quando houver GPU (orçamento de memória, Seção 5.2)
# NLI em fp16 na GPU (cuda/mps): metade da memória. Desligado até o eval/medir_recursos.py
# confirmar que as decisões do NLI não mudam (o DeBERTa-v3 pode ter overflow em fp16).
NLI_FP16 = os.getenv("EVIDENCE_NLI_FP16", "0") == "1"
EXCERPT_MAX_CHARS = 300
CHUNK_MAX_CHARS = 800        # trechos do índice: parágrafos agrupados até este tamanho
CHUNK_OVERLAP_PARAGRAPHS = 1
MIN_PARAGRAPH_CHARS = 40


def collection_name(model_name: str | None = None) -> str:
    """Uma coleção por modelo de embedding, para comparar modelos sem misturar índices."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (model_name or EMBEDDING_MODEL)).strip("-").lower()
    return f"{COLLECTION_PREFIX}__{slug}"[:63].rstrip("-_")   # o Chroma aceita até 63 caracteres


def pick_device() -> str:
    """cuda -> mps -> cpu, a menos que EVIDENCE_DEVICE force um valor."""
    if DEVICE:
        return DEVICE
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"
