from langchain_core.prompts import ChatPromptTemplate
from src.state import PipelineState
from src.services.llm import llm_socratico
from pydantic import BaseModel
from typing import List


class QuestionList(BaseModel):
    perguntas: List[str]


def socratico_node(state: PipelineState) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """Você é um filósofo socrático analisando a validade lógica de argumentos jornalísticos.

Sua tarefa é analisar o texto jornalístico e formular de 2 a 3 perguntas socráticas incisivas.

Antes de formular as perguntas, identifique mentalmente:
- premissas ocultas;
- relações de causa e efeito que podem não estar demonstradas;
- generalizações;
- ausência de evidências;
- possíveis explicações alternativas;
- informações importantes que o texto não apresenta.

As perguntas devem ajudar o leitor a perceber essas lacunas e pensar criticamente sobre a afirmação apresentada.

Não responda se a notícia é verdadeira ou falsa.
Não dê um veredito.
Faça perguntas que estimulem o próprio leitor a avaliar o argumento."""
        ),

        (
            "user",
            """Exemplo de análise:

Texto:
"O prefeito comprou novos carros para a polícia, logo a criminalidade vai cair."
"""
        ),

        (
            "assistant",
            """{{"perguntas": [
                "A correlação entre a compra de novos veículos para a polícia e a queda da criminalidade é baseada em quais dados ou evidências?",
                "O texto considera outros fatores que podem influenciar a criminalidade ou assume que a melhoria da frota policial será suficiente para causar essa redução?"
            ]}}"""
        ),

        (
            "user",
            """Agora analise o seguinte texto jornalístico:

{text}"""
        )
    ])

    chain = prompt | llm_socratico.with_structured_output(QuestionList)

    try:
        resultado = chain.invoke({
            "text": state.clean_text
        })

        return {
            "socratic_questions": resultado.perguntas
        }

    except Exception as e:
        print(f"Erro no Agente Socrático: {e}")

        return {
            "socratic_questions": [
                f"Erro na chamada do modelo: {e}"
            ]
        }