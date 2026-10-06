from langchain_openai import ChatOpenAI

LOCAL_MODEL = "qwen2.5-7b"
BASE_URL = "http://localhost:1234/v1"

# Todos os clientes: timeout de 120 s e sem retry do cliente HTTP. Os agentes fazem o
# próprio retry quando a saída vem inválida (Manual §4.7), e o grafo limita o tempo de
# cada nó (src/protecao.py); sem timeout aqui, uma chamada abandonada pelo grafo
# continuaria ocupando o LM Studio indefinidamente.
TIMEOUT_S = 120


def _cliente(temperatura: float) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=BASE_URL,
        api_key="lm-studio",
        model=LOCAL_MODEL,
        temperature=temperatura,
        timeout=TIMEOUT_S,
        max_retries=0,
    )


llm = _cliente(0)               # Sintetizador
llm_socratico = _cliente(0.7)   # Agente Socrático
llm_texto = _cliente(0)         # Agente de Texto
