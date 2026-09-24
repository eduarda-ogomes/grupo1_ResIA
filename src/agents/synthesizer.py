from langchain_core.prompts import ChatPromptTemplate
from src.state import PipelineState, Dossier
from src.services.llm import llm

def sintetizador_node(state: PipelineState) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Você é o Compilador Final do Dossiê. Sua função é estritamente descritiva.
REGRAS ABSOLUTAS:
1. NUNCA use as palavras "Falso", "Verdadeiro", "Fake News", "Mentira" ou "Desinformação".
2. Não emita o seu próprio veredito sobre a notícia.
3. Estruture os fatos cruzando os dados usando expressões neutras como "As evidências apontam que..." ou "Não foram encontrados dados na base que corroborem...""""),
        ("user", "Texto: {text}\nPerguntas: {questions}\nEvidências: {evidence}\nMarcadores: {framing}")
    ])
    chain = prompt | llm.with_structured_output(Dossier)
    try:
        dossie = chain.invoke({
            "text": state.clean_text,
            "questions": state.socratic_questions,
            "evidence": state.evidence,
            "framing": state.framing
        })
        return {"dossier": dossie}
    except Exception as e:
        print(f"Erro no Agente Sintetizador: {e}")
        return {"dossier": Dossier(content_summary=f"Erro na síntese: {str(e)}", framing_summary="Falha na execução do LLM via LMStudio.")}
