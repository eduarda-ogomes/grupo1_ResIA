import re
import logging
from typing import Set
from langchain_core.prompts import ChatPromptTemplate
from src.services.llm import get_llm
from src.state import PipelineState

logger = logging.getLogger(__name__)

# Configurações do Guardrail
TERMOS_PROIBIDOS = [
    r"\bfalso\b", r"\bverdadeiro\b", r"\bfake news\b", r"\bmentira\b", 
    r"\bboato\b", r"\bconfirmado\b", r"\binventado\b"
]

SYSTEM_PROMPT = """Você é o Agente Sintetizador do sistema scaffolding.
Sua missão é compilar as informações dos outros agentes em um dossiê analítico.
Você NUNCA deve dar um veredito de 'Verdadeiro' ou 'Falso'. 
Você NUNCA deve usar termos como 'Fake News', 'Mentira' ou 'Boato'.
Você deve ajudar o leitor a pensar criticamente.

Estruture a resposta OBRIGATORIAMENTE em Markdown com os seguintes cabeçalhos exatos:
## O que as checagens dizem
## Análise de Retórica
## Perguntas para Reflexão
## Conclusão Neutra
"""

USER_TEMPLATE = """Baseando-se nos dados abaixo, gere o dossiê:

Notícia Original: {texto_original}

EVIDÊNCIAS COLETADAS:
{bloco_evidencias}

ANÁLISE DE RETÓRICA:
{bloco_retorica}

PERGUNTAS REFLEXIVAS:
{bloco_perguntas}
"""

def verificar_filtro_veredito(texto: str) -> bool:
    texto_lower = texto.lower()
    for termo in TERMOS_PROIBIDOS:
        if re.search(termo, texto_lower):
            logger.warning(f"Guardrail acionado: Uso do termo proibido '{termo}' detectado.")
            return False
    return True

def verificar_citacoes(texto: str, urls_conhecidas: Set[str]) -> bool:
    urls_geradas = set(re.findall(r'https?://[^\s)]+', texto))
    urls_falsas = urls_geradas - urls_conhecidas
    if urls_falsas:
        logger.warning(f"Guardrail acionado: O LLM alucinou as URLs: {urls_falsas}")
        return False
    return True

def preparar_dados_contexto(state: PipelineState) -> dict:
    urls_conhecidas = set()
    evidencias_filtradas = []
    
    # Pre-processamento: Deduplicação e filtragem de 'valor'
    for ev in state.evidences:
        if ev.url in urls_conhecidas:
            continue
            
        segmento_relacionado = next((s for s in state.segments if s.id == ev.segment_id), None)
        if segmento_relacionado and segmento_relacionado.statement_type == "valor":
            continue
            
        evidencias_filtradas.append(ev)
        urls_conhecidas.add(ev.url)
        
    return {
        "urls": urls_conhecidas,
        "evidencias": evidencias_filtradas
    }

def run(state: PipelineState) -> dict:
    try:
        dados = preparar_dados_contexto(state)
        
        # Formatando bloco de evidências
        if dados["evidencias"]:
            bloco_evidencias = "\n".join([f"- Alegação [{e.segment_id}]: {e.stance} pela {e.source}. Trecho: {e.quote}" for e in dados["evidencias"]])
        else:
            bloco_evidencias = "Nenhuma evidência factual encontrada."
            
        # Formatando bloco de retórica
        if state.text_analysis.markers:
            bloco_retorica = "\n".join([f"- {m.type}: {m.description}" for m in state.text_analysis.markers])
        else:
            bloco_retorica = "Nenhum marcador retórico relevante detectado."
            
        # Formatando bloco de perguntas
        if state.socratic_questions:
            bloco_perguntas = "\n".join([f"- {q}" for q in state.socratic_questions])
        else:
            bloco_perguntas = "Nenhuma pergunta socrática gerada."
            
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("user", USER_TEMPLATE)
        ])
        
        llm = get_llm()
        chain = prompt | llm
        
        resposta = chain.invoke({
            "texto_original": state.raw_input,
            "bloco_evidencias": bloco_evidencias,
            "bloco_retorica": bloco_retorica,
            "bloco_perguntas": bloco_perguntas
        })
        
        conteudo_dossie = resposta.content
        
        # Aplica Guardrails
        if not verificar_filtro_veredito(conteudo_dossie):
            # Segunda chance (re-prompting com aviso)
            prompt_reforcado = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT + "\nATENÇÃO: Na tentativa anterior você usou termos proibidos como 'falso' ou 'fake news'. NÃO USE ESSES TERMOS."),
                ("user", USER_TEMPLATE)
            ])
            resposta = (prompt_reforcado | llm).invoke({
                "texto_original": state.raw_input,
                "bloco_evidencias": bloco_evidencias,
                "bloco_retorica": bloco_retorica,
                "bloco_perguntas": bloco_perguntas
            })
            conteudo_dossie = resposta.content
            
        verificar_citacoes(conteudo_dossie, dados["urls"])
        
        return {"dossier": conteudo_dossie}
        
    except Exception as e:
        logger.error(f"Erro no Agente Sintetizador: {e}")
        return {"dossier": "Não foi possível sintetizar a análise devido a um erro interno."}

synthesizer_node = run
