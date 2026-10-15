"""Agente Sintetizador (R5): junta os ramos num dossiê neutro e citável, sem veredito. Só código, sem LLM.

O código escreve tudo o que é fato (src/agents/synthesizer/dossie.py). As linhas de "Como o texto
argumenta" chegam prontas em `state.argument`, escritas pelo Agente de Texto (src/agents/argumento.py);
se não chegaram, saem do fallback em código. Ordem das seções: Resumo, Checagens, Argumento, Perguntas,
Limites, Fontes (docs/superpowers/specs/2026-10-08-dossie-final-design.md).

sintetizador_node(state) -> {"dossier": str}: "warnings" só se a rede de segurança das citações remover
algo. Nunca devolve dossier = None.
"""
from __future__ import annotations

from src.agents.synthesizer import dossie
from src.state import PipelineState

WARN_CITACAO_REMOVIDA = "sintetizador: citação removida (URL fora das evidências)"


def argumento_fallback(state: PipelineState) -> dict:
    """As linhas do argumento sem chamar o LLM.

    O Sintetizador usa quando `argument` não chegou (o Agente de Texto falhou ou estourou o tempo):
    o usuário recebe a seção em fallback, não um dossiê vazio.
    """
    return {"argument": dossie.linhas_argumento(state, {})}


def sintetizador_node(state: PipelineState) -> dict:
    """Nó `sintetizador`: só monta o dossiê; nunca chama o LLM.

    O argumento vem pronto de `state.argument` (ou do fallback em código, se não chegou).
    A rede de segurança das citações roda aqui e, se remover algo, também avisa.
    """
    if not state.segments:
        return {"dossier": dossie.SEM_TEXTO}

    ctx = dossie.preprocessar(state)
    fontes = dossie.numerar_fontes(state, ctx)
    argumento = state.argument if state.argument is not None else argumento_fallback(state)["argument"]
    # Ordem: pirâmide invertida (spec do dossiê final); Fontes some quando não há evidência
    texto = dossie.montar(
        dossie.secao_resumo(state, ctx),
        dossie.secao_checagens(state, ctx, fontes),
        [dossie.TITULO_ARGUMENTO, *argumento],
        dossie.secao_perguntas(state),
        dossie.secao_limites(state),
        dossie.secao_fontes(state, ctx, fontes),
    )
    texto, removeu = dossie.remover_citacoes_invalidas(texto, state.evidence or [])
    return {"dossier": texto, "warnings": [WARN_CITACAO_REMOVIDA]} if removeu else {"dossier": texto}


# Nomes usados pelo graph.py e pelas convenções do projeto
synthesizer_node = sintetizador_node
run = sintetizador_node
