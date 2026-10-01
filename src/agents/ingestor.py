from typing import List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from src.state import PipelineState
from src.services.llm import llm_socratico


class QuestionList(BaseModel):
    perguntas: List[str]


def socratico_node(state: PipelineState) -> dict:
    """
    Agente Socrático.

    Recebe o texto já processado pelo Ingestor através de
    state.clean_text e gera de 2 a 3 perguntas socráticas
    que estimulem o pensamento crítico do usuário.
    """

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
Você é um filósofo socrático especializado em análise crítica
de textos jornalísticos.

Sua tarefa é analisar o texto recebido e formular de 2 a 3
perguntas socráticas incisivas que ajudem o leitor a questionar
as afirmações apresentadas.

Antes de formular as perguntas, analise mentalmente:

- quais são as principais afirmações do texto;
- quais premissas estão implícitas;
- se existem relações de causa e efeito que não foram demonstradas;
- se existem generalizações;
- quais evidências seriam necessárias para sustentar as afirmações;
- quais informações importantes podem estar ausentes;
- quais explicações alternativas poderiam existir;
- se há alguma conclusão que parece ir além das informações apresentadas.

As perguntas devem estimular o leitor a pensar e investigar por
conta própria.

IMPORTANTE:
- Não diga se a notícia é verdadeira ou falsa.
- Não dê um veredito sobre a notícia.
- Não responda às próprias perguntas.
- Não invente informações que não estejam no texto.
- Faça perguntas específicas relacionadas ao conteúdo analisado.
- Gere entre 2 e 3 perguntas.
"""
        ),

        (
            "user",
            """
Exemplo:

Texto:
"O prefeito comprou novos carros para a polícia, logo a
criminalidade vai cair."
"""
        ),

        (
            "assistant",
            """
{{"perguntas": [
    "A correlação entre a compra de novos veículos para a polícia e a queda da criminalidade é baseada em quais dados ou evidências?",
    "O texto considera outros fatores que podem influenciar a criminalidade ou assume que a melhoria da frota policial será suficiente para causar essa redução?"
]}}
"""
        ),

        (
            "user",
            """
Agora analise o seguinte texto jornalístico:

{text}
"""
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