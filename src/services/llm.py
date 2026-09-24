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
