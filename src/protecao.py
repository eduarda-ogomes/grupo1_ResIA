"""Proteção dos nós do grafo: timeout por nó, e exceção vira aviso (Manual §3.4).

Cada agente já trata as próprias falhas e grava o próprio aviso. Esta camada cobre
o que escapa (um modelo travado, um bug), para que o grafo sempre chegue ao
Sintetizador e o dossiê sempre saia.

Limitação: o Python não interrompe uma thread. Quando um nó estoura o tempo, o grafo
segue sem ele, mas a chamada continua em segundo plano até terminar sozinha; o
timeout dos clientes de LLM (src/services/llm.py) limita quanto isso dura.
"""
from __future__ import annotations

import copy
import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout  # no Python 3.10 não é o TimeoutError embutido
from typing import Any, Callable

logger = logging.getLogger(__name__)


def ler_timeout(variavel: str, padrao: float) -> float:
    """Segundos lidos da variável de ambiente; ausente, inválido, infinito ou <= 0 usa o padrão."""
    try:
        valor = float(os.environ[variavel])
    except (KeyError, ValueError):
        return padrao
    return valor if math.isfinite(valor) and valor > 0 else padrao


# Lidos ao importar o grafo: defina as variáveis antes de subir o Streamlit.
TIMEOUT_INGESTOR_S = ler_timeout("GRAFO_TIMEOUT_INGESTOR", 60)
TIMEOUT_RAMO_S = ler_timeout("GRAFO_TIMEOUT_RAMO", 240)
TIMEOUT_SINTETIZADOR_S = ler_timeout("GRAFO_TIMEOUT_SINTETIZADOR", 180)

FALHA_INGESTOR = {"clean_text": "", "title": None, "published_at": None, "truncated": False, "segments": []}
DOSSIE_INDISPONIVEL = "Não foi possível montar o dossiê nesta análise. Os avisos indicam o que falhou."


def proteger(nome: str, fn: Callable[[Any], dict], timeout_s: float, em_falha: dict) -> Callable[[Any], dict]:
    """Envolve `fn(state)`: devolve a saída dela ou, se ela estourar `timeout_s` segundos
    ou levantar exceção, uma cópia de `em_falha` com o aviso "<nome>: <motivo>"."""

    def no(state):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=nome)
        futuro = executor.submit(fn, state)
        try:
            return futuro.result(timeout=timeout_s)
        except FuturesTimeout:
            logger.warning("%s: estourou o limite de %s s", nome, timeout_s)
            motivo = "timeout"
        except Exception as exc:
            logger.exception("%s falhou", nome)
            motivo = f"{type(exc).__name__}: {exc}"
        finally:
            # wait=False: não espera a thread travada (um `with` esperaria e anularia o timeout)
            executor.shutdown(wait=False, cancel_futures=True)
        return {**copy.deepcopy(em_falha), "warnings": [f"{nome}: {motivo}"]}

    no.__name__ = f"{nome}_protegido"
    return no
