"""Configuração do Agente de Evidências e do índice de checagens.

Todos os valores podem ser sobrescritos por variáveis de ambiente, para que
nenhum modelo, limiar ou caminho fique fixo no código do agente. As decisões
por trás de cada valor padrão estão em docs/agents/evidencias_decisoes.md.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "sim", "yes", "on"}


# Raiz do repositório (src/retrieval/config.py -> dois níveis acima de src/).
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Modelos ---------------------------------------------------------------
EMBEDDING_MODEL = os.getenv("EVIDENCE_EMBEDDING_MODEL", "BAAI/bge-m3")
NLI_MODEL = os.getenv("EVIDENCE_NLI_MODEL", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
# Embeddings em fp16 quando houver GPU (cuda/mps), para caber no orçamento de
# memória da Seção 5.2. O NLI fica em fp32 por padrão.
EMBEDDING_FP16 = _env_bool("EVIDENCE_EMBEDDING_FP16", True)
NLI_FP16 = _env_bool("EVIDENCE_NLI_FP16", False)
# Força um dispositivo ("cpu", "cuda", "mps"). Vazio = escolha automática.
DEVICE = os.getenv("EVIDENCE_DEVICE", "")
BATCH_SIZE = _env_int("EVIDENCE_BATCH_SIZE", 16)

# --- Índice ----------------------------------------------------------------
CHROMA_PATH = Path(os.getenv("EVIDENCE_CHROMA_PATH", str(REPO_ROOT / "chroma_data")))
COLLECTION_PREFIX = "checagens"

# --- Modo de stance --------------------------------------------------------
# "alegacao" (padrão desde 27/09): a checagem só é usada se o NLI indicar que a
#   frase é a mesma alegação do claim_reviewed; a stance vem do veredito da
#   agência. Diverge da Seção 4.2 do manual; ver docs/agents/evidencias_decisoes.md.
# "trecho": o método da Seção 4.2 (NLI entre o trecho da checagem e a frase).
STANCE_MODE = os.getenv("EVIDENCE_STANCE_MODE", "alegacao").strip().lower()
STANCE_MODES = ("alegacao", "trecho")

# --- Busca e stance (valores provisórios, a calibrar com o gold set) -------
TOP_K = _env_int("EVIDENCE_TOP_K", 5)             # k do Recall@k na avaliação
SEARCH_K = _env_int("EVIDENCE_SEARCH_K", 10)      # trechos buscados por frase pelo agente
SIM_THRESHOLD = _env_float("EVIDENCE_SIM_THRESHOLD", 0.55)
NLI_MIN_PROB = _env_float("EVIDENCE_NLI_MIN_PROB", 0.5)
CLAIM_MATCH_MIN_PROB = _env_float("EVIDENCE_CLAIM_MATCH_MIN_PROB", 0.5)
# Variantes da etapa "mesma alegação" (ver src/retrieval/claim_match.py e o
# experimento data/corpus/experimento_etapa2.py):
# - termos-chave: um nome próprio, número ou doença da frase ausente da checagem
#   reprova quando a alegação tem um termo da mesma classe ausente da frase (troca).
#   LIGADA: barra o erro "dengue x chikungunya" que o NLI deixa passar.
# - normalização: tira "Foto/Vídeo/Imagem mostra" da alegação antes do NLI.
#   LIGADA desde 28/09 (caso real UOL/Fachin: entailment 0,09 -> 0,99; nenhum
#   casamento errado novo no experimento).
KEY_TERM_CHECK = _env_bool("EVIDENCE_KEY_TERM_CHECK", True)
CLAIM_NORMALIZE = _env_bool("EVIDENCE_CLAIM_NORMALIZE", True)
# Checagens avaliadas na etapa 2 por frase; o resultado ainda é limitado a
# MAX_EVIDENCE_PER_SEGMENT. Antes de 28/09 o limite de 3 vinha antes da etapa 2 e
# cortava checagens certas (caso Fachin: o Aos Fatos ficou de fora).
CLAIM_CANDIDATES = _env_int("EVIDENCE_CLAIM_CANDIDATES", 6)
MAX_EVIDENCE_PER_SEGMENT = _env_int("EVIDENCE_MAX_PER_SEGMENT", 3)
EXCERPT_MAX_CHARS = _env_int("EVIDENCE_EXCERPT_MAX_CHARS", 300)

# --- Proteção contra o boato citado (opção 1; desligada por padrão) --------
# Quando ligada, trechos marcados como "descreve o boato" na indexação não são
# recuperados. Continua desligada: no modo "alegacao" o parágrafo do boato
# ajuda a achar a checagem certa, e a heurística ainda marca algumas
# conclusões por engano (ver documento de decisões, seção 7).
FILTER_RUMOR_CHUNKS = _env_bool("EVIDENCE_FILTER_RUMOR", False)

# --- Chunking --------------------------------------------------------------
CHUNK_MAX_CHARS = _env_int("EVIDENCE_CHUNK_MAX_CHARS", 800)
CHUNK_OVERLAP_PARAGRAPHS = _env_int("EVIDENCE_CHUNK_OVERLAP", 1)
MIN_PARAGRAPH_CHARS = _env_int("EVIDENCE_MIN_PARAGRAPH_CHARS", 40)

# --- Corpus bruto (fora do Git) -------------------------------------------
RAW_DIR = Path(os.getenv("EVIDENCE_RAW_DIR", str(REPO_ROOT / "data" / "corpus" / "raw")))


def collection_name(model_name: str | None = None) -> str:
    """Uma coleção por modelo de embedding, para comparar modelos sem misturar índices."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (model_name or EMBEDDING_MODEL)).strip("-").lower()
    # O Chroma aceita nomes de 3 a 63 caracteres.
    return f"{COLLECTION_PREFIX}__{slug}"[:63].rstrip("-_")


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
