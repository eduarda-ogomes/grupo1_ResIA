"""Proteção dos nós do grafo: timeout por nó, e exceção vira aviso (Manual §3.4).

Cada agente já trata as próprias falhas e grava o próprio aviso. Esta camada cobre
o que escapa (um modelo travado, um bug), para que o grafo sempre chegue ao
Sintetizador e o dossiê sempre saia.

Limitação: o Python não interrompe uma thread. Quando um nó estoura o tempo, o grafo
segue sem ele, mas o agente continua em segundo plano até terminar sozinho. O timeout
dos clientes de LLM (src/services/llm.py) limita cada chamada, não o agente inteiro:
o Agente de Texto, por exemplo, segue processando os lotes restantes e ocupando o
LM Studio, o que pode atrasar a análise seguinte.
"""
from __future__ import annotations

import copy
import logging
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout  # no Python 3.10 não é o TimeoutError embutido
from typing import Any, Callable

logger = logging.getLogger(__name__)


def ler_timeout(variavel: str, padrao: float) -> float:
    """Segundos lidos da variável de ambiente; ausente, inválido, infinito ou <= 0 usa o padrão.

    Valores enormes ("1e10", para "desligar" o timeout) são limitados ao máximo que a
    plataforma aceita: acima dele, esperar pela thread levanta OverflowError.
    """
    try:
        valor = float(os.environ[variavel])
    except (KeyError, ValueError):
        return padrao
    if not math.isfinite(valor) or valor <= 0:
        return padrao
    return min(valor, threading.TIMEOUT_MAX)


# Lidos ao importar o grafo: defina as variáveis antes de subir o Streamlit.
TIMEOUT_INGESTOR_S = ler_timeout("GRAFO_TIMEOUT_INGESTOR", 60)
TIMEOUT_RAMO_S = ler_timeout("GRAFO_TIMEOUT_RAMO", 240)
TIMEOUT_SINTETIZADOR_S = ler_timeout("GRAFO_TIMEOUT_SINTETIZADOR", 180)

FALHA_INGESTOR = {"clean_text": "", "title": None, "published_at": None, "truncated": False, "segments": []}
DOSSIE_INDISPONIVEL = "Não foi possível montar o dossiê nesta análise. Os avisos indicam o que falhou."


def proteger(
    nome: str,
    fn: Callable[[Any], dict],
    timeout_s: float,
    em_falha: dict,
    recuperar: Callable[[Any], dict] | None = None,
) -> Callable[[Any], dict]:
    """Envolve `fn(state)`: devolve a saída dela ou, se ela estourar `timeout_s` segundos
    ou levantar exceção, a saída de falha com o aviso "<nome>: <motivo>" na frente.

    A saída de falha é `recuperar(state)`, quando dado (ex.: o dossiê montado sem o LLM),
    ou uma cópia de `em_falha`, que também cobre um `recuperar` que falhe.
    """

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
        saida = _saida_de_falha(nome, state, em_falha, recuperar)
        return {**saida, "warnings": [f"{nome}: {motivo}", *saida.get("warnings", [])]}

    no.__name__ = f"{nome}_protegido"
    return no


def _saida_de_falha(nome: str, state: Any, em_falha: dict, recuperar: Callable[[Any], dict] | None) -> dict:
    if recuperar is not None:
        try:
            return recuperar(state)
        except Exception:
            logger.exception("%s: a recuperação também falhou", nome)
    return copy.deepcopy(em_falha)
