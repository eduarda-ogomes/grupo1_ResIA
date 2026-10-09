"""Clientes do LLM local (LM Studio, API compatível com OpenAI).

Variáveis de ambiente:
- LLM_MODEL: nome do modelo no LM Studio (lido ao importar).
- LLM_DRAFT_MODEL: modelo rascunho opcional para decodificação especulativa. Lido a cada
  criação de cliente; quando definido, toda requisição leva `draft_model=<nome>` no corpo.
  Vazio ou ausente: nada extra é enviado.
"""
import os

from langchain_openai import ChatOpenAI


def modelo_local() -> str:
    """Nome do modelo no LM Studio. LLM_MODEL sobrescreve, porque cada máquina baixa o
    modelo com um nome (ex.: "qwen/qwen2.5-7b-instruct"); o LM Studio recusa nome desconhecido."""
    return os.getenv("LLM_MODEL", "").strip() or "qwen2.5-7b"


LOCAL_MODEL = modelo_local()  # lido ao importar: defina LLM_MODEL antes de subir o Streamlit
BASE_URL = "http://localhost:1234/v1"

# Todos os clientes: timeout de 120 s e sem retry do cliente HTTP. Os agentes fazem o
# próprio retry quando a saída vem inválida (Manual §4.7), e o grafo limita o tempo de
# cada nó (src/protecao.py); sem timeout aqui, uma chamada abandonada pelo grafo
# continuaria ocupando o LM Studio indefinidamente.
TIMEOUT_S = 120


def modelo_rascunho() -> str | None:
    """Modelo rascunho da decodificação especulativa (LLM_DRAFT_MODEL), lido na hora da
    chamada. Vazio ou só espaços vale como não definido."""
    return os.getenv("LLM_DRAFT_MODEL", "").strip() or None


def _cliente(temperatura: float, max_tokens: int) -> ChatOpenAI:
    """Cliente com teto de tokens gerados; se houver modelo rascunho, envia `draft_model`
    no corpo de cada requisição (também depois de `.bind(...)`, pois é campo do construtor)."""
    rascunho = modelo_rascunho()
    return ChatOpenAI(
        base_url=BASE_URL,
        api_key="lm-studio",
        model=LOCAL_MODEL,
        temperature=temperatura,
        max_tokens=max_tokens,
        timeout=TIMEOUT_S,
        max_retries=0,
        extra_body={"draft_model": rascunho} if rascunho else None,
    )


llm_sintetizador = _cliente(0, 400)    # Sintetizador
llm_socratico = _cliente(0.2, 300)     # Agente Socrático
llm_texto = _cliente(0, 1000)          # Agente de Texto
