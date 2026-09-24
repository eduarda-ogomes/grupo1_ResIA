from langchain_core.prompts import ChatPromptTemplate
from src.state import PipelineState, FramingReport, FramingMarker
from src.services.llm import llm

def texto_node(state: PipelineState) -> dict:
    prompt = ChatPromptTemplate.from_messages([
        ("system", """Você é um especialista em Análise do Discurso e Linguística. 
Mapeie marcadores de viés e tom emocional no texto. 
Regra Absoluta: Fatos estatísticos puros NÃO são marcadores emocionais, mesmo que o tema seja grave."""),
        ("user", "Texto: 'A taxa de desemprego atingiu 12% no último trimestre.'"),
        ("assistant", '{{"markers": [], "emotional_tone": {{"neutro": 1.0}}}}'),
        ("user", "Texto: 'É o fim! O desemprego disparou de forma aterrorizante por conta da burrice do governo, jogando as famílias nas ruas.'"),
        ("assistant", '{{"markers": [{{"type": "Adjetivação Extrema", "exact_excerpt": "aterrorizante", "short_explanation": "Intensificador de pânico injustificado"}}, {{"type": "Ataque Ad Hominem", "exact_excerpt": "burrice", "short_explanation": "Ataque direto à inteligência"}}], "emotional_tone": {{"panico": 0.8, "indignacao": 0.9}}}}'),
        ("user", "Texto: {text}")
    ])
    chain = prompt | llm.with_structured_output(FramingReport)
    try:
        report = chain.invoke({"text": state.clean_text})
        return {"framing": report}
    except Exception as e:
        print(f"Erro no Agente de Texto: {e}")
        return {"framing": FramingReport(markers=[FramingMarker(type="Erro", exact_excerpt="", short_explanation=str(e))], emotional_tone={"erro": 1.0})}
