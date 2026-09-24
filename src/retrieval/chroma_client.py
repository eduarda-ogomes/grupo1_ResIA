import chromadb
from transformers import pipeline

nli_pipeline = None
chroma_client = None

def get_nli_pipeline():
    global nli_pipeline
    if nli_pipeline is None:
        print("Carregando modelo NLI (mDeBERTa-v3)...")
        nli_pipeline = pipeline("text-classification", model="MoritzLaurer/mDeBERTa-v3-base-mnli-xnli")
    return nli_pipeline

def get_chroma_collection():
    global chroma_client
    if chroma_client is None:
        chroma_client = chromadb.PersistentClient(path="./chroma_data")
    return chroma_client.get_collection(name="fact_checks")
