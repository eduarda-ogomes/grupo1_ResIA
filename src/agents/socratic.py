from langchain_core.prompts import ChatPromptTemplate
from src.state import PipelineState
from src.services.llm import llm_socratico
from pydantic import BaseModel
from typing import List

def socratico_node(state: PipelineState) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Você é um filósofo socrático analisando a validade lógica de argumentos jornalísticos. 
Primeiro, identifique premissas ocultas ou falácias lógicas no texto. Depois, gere 2 ou 3 perguntas incisivas que exponham essas lacunas."""),
        ("user", "Texto: 'O prefeito comprou novos carros para a polícia, logo a criminalidade vai cair.'"),
        ("assistant", '{{"perguntas": ["A correlação entre frota veicular e queda de crimes é baseada em quais dados históricos?", "O texto isola outros fatores sociais que impactam a criminalidade, ou assume uma relação simples de causa e efeito?"]}}'),
        ("user", "Texto: {text}")
    ])
    class QuestionList(BaseModel):
        perguntas: List[str]
        
    chain = prompt | llm_socratico.with_structured_output(QuestionList)
    try:
        resultado = chain.invoke({"text": state.clean_text})
        return {"socratic_questions": resultado.perguntas}
    except Exception as e:
        print(f"Erro no Agente Socrático: {e}")
        return {"socratic_questions": [f"Erro na chamada do modelo: {e}"]}
