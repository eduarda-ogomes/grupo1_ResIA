from langchain_core.prompts import ChatPromptTemplate
from src.state import PipelineState, Evidence
from src.services.llm import llm
from src.retrieval.chroma_client import get_chroma_collection, get_nli_pipeline

def evidencias_node(state: PipelineState) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extraia até 3 frases principais do texto que contenham afirmações factuais verificáveis. Retorne apenas as frases, uma por linha, sem numeração ou formatação."),
        ("user", "{text}")
    ])
    chain = prompt | llm
    try:
        response = chain.invoke({"text": state.clean_text})
        claims = [c.strip() for c in response.content.split('\n') if c.strip()][:3]
    except Exception:
        claims = []

    if not claims:
        return {"evidence": [Evidence(stance="insuficiente", excerpt="Nenhuma afirmação clara extraída.", source_url="", source_name="", retrieved_from="corpus")]}

    collection = get_chroma_collection()
    nli = get_nli_pipeline()
    evidencias_finais = []
    
    for claim in claims:
        results = collection.query(query_texts=[claim], n_results=1)
        if not results['documents'][0]:
            continue
            
        retrieved_fact = results['documents'][0][0]
        metadata = results['metadatas'][0][0]
        
        nli_result = nli(f"{retrieved_fact} [SEP] {claim}")[0]
        label = nli_result['label'].lower()
        score = nli_result['score']
        
        if label == "entailment" and score > 0.5:
            stance = "apoia"
        elif label == "contradiction" and score > 0.5:
            stance = "contradiz"
        else:
            stance = "insuficiente"
            
        evidencias_finais.append(Evidence(
            stance=stance,
            excerpt=f"Afirmação na notícia: '{claim}' | Fato do DB: '{retrieved_fact}' (Confiança NLI: {score:.2f})",
            source_url=metadata['source_url'],
            source_name=metadata['source_name'],
            retrieved_from="corpus"
        ))

    if not evidencias_finais:
        evidencias_finais.append(Evidence(stance="insuficiente", excerpt="Nenhum fato correlato encontrado na base de RAG.", source_url="", source_name="", retrieved_from="corpus"))
        
    return {"evidence": evidencias_finais}
