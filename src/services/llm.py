from langchain_openai import ChatOpenAI

LOCAL_MODEL = "qwen2.5-7b"
llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    model=LOCAL_MODEL,
    temperature=0
)

llm_socratico = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    model=LOCAL_MODEL,
    temperature=0.7
)

# Agente de Texto: determinístico e sem retry do cliente HTTP.
# O próprio agente faz 1 retry quando o JSON vem inválido (Manual §4.7).
llm_texto = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    model=LOCAL_MODEL,
    temperature=0,
    timeout=120,
    max_retries=0,
)
