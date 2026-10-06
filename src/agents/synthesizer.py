"""Agente Sintetizador (R5): junta os três ramos num dossiê neutro e citável, sem veredito.

Abordagem híbrida (Manual §4.5.1; design em docs/superpowers/specs/2026-10-01-agente-sintetizador-design.md):
o código escreve tudo o que é fato (src/agents/dossie.py); o qwen2.5-7b escreve só a seção
"Como o texto argumenta", com guardrails (src/guardrails/), 1 retry e fallback em código.

Contrato: sintetizador_node(state) -> {"dossier": str}, mais "warnings" quando o problema
é do próprio Sintetizador. Nunca devolve dossier = None.
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.agents import dossie
from src.guardrails.citacoes import extrair_urls
from src.guardrails.veredito import termos_de_veredito
from src.services.llm import llm_sintetizador
from src.state import PipelineState

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

WARN_MODELO_INDISPONIVEL = "sintetizador: falha ao chamar o modelo (o LM Studio está rodando?)"
WARN_GUARDRAILS = "sintetizador: síntese livre reprovada nos guardrails após 1 retry"
WARN_CITACAO_REMOVIDA = "sintetizador: citação removida (URL fora das evidências)"


class SinteseReprovada(RuntimeError):
    """O texto do modelo continuou reprovado nos guardrails depois do retry."""


class ModeloIndisponivel(RuntimeError):
    """A chamada ao modelo falhou (conexão, timeout, servidor fora do ar)."""


def carregar_prompt_sistema() -> str:
    return (PROMPTS_DIR / "sintetizador_sistema.md").read_text(encoding="utf-8")


def montar_mensagem_usuario(state: PipelineState, ctx: dossie.Contexto) -> str:
    """Frases e marcadores delimitados como dado (§3.5), sem IDs de frase e sem URLs."""
    frases = "\n".join(f"- ({ctx.tipo_por_frase.get(s.id, 'sem rótulo')}) {s.text}" for s in state.segments)
    texto_da_frase = {s.id: s.text for s in state.segments}
    marcadores = "\n".join(
        f'- {dossie.ROTULOS[m.type]} | frase: "{texto_da_frase.get(m.segment_id, "")}" '
        f'| trecho: "{m.excerpt}" | explicação: {m.explanation}'
        for m in state.text_report.markers
    ) or "- (nenhum)"
    return f"<frases>\n{frases}\n</frases>\n\n<marcadores>\n{marcadores}\n</marcadores>"


def montar_mensagens(state: PipelineState, ctx: dossie.Contexto, problema: str | None = None) -> list[tuple[str, str]]:
    usuario = montar_mensagem_usuario(state, ctx)
    if problema:
        usuario += f"\n\nSua resposta anterior foi rejeitada. {problema} Reescreva só os bullets, sem esse problema."
    return [("system", carregar_prompt_sistema()), ("user", usuario)]


def chamar_modelo(mensagens: list[tuple[str, str]]) -> str:
    """Única função que fala com o LM Studio. Os testes a substituem por um modelo falso."""
    return llm_sintetizador.invoke(mensagens).content


def limpar_resposta(bruto: str) -> str:
    """Tira títulos que o modelo às vezes acrescenta ("## Como o texto argumenta")."""
    linhas = [linha for linha in bruto.strip().splitlines() if not linha.lstrip().startswith("#")]
    return "\n".join(linhas).strip()


def problema_da_sintese(texto: str) -> str | None:
    """Guardrails sobre o texto do modelo; devolve o problema nomeado para o retry, ou None."""
    if not texto:
        return "Seu texto veio vazio."
    termos = termos_de_veredito(texto)
    if termos:
        return f"Seu texto usou o termo '{termos[0]}'."
    if extrair_urls(texto):
        return "Seu texto incluiu um link."
    return None


def sintese_livre(state: PipelineState, ctx: dossie.Contexto) -> str:
    problema = None
    for _ in range(2):  # 1 tentativa + 1 retry
        try:
            bruto = chamar_modelo(montar_mensagens(state, ctx, problema))
        except Exception as e:
            raise ModeloIndisponivel(str(e)) from e
        texto = limpar_resposta(bruto)
        problema = problema_da_sintese(texto)
        if problema is None:
            return texto
        logger.warning("Sintetizador: síntese livre rejeitada: %s", problema)
    raise SinteseReprovada(problema)


def secao_argumento(state: PipelineState, ctx: dossie.Contexto) -> tuple[list[str], list[str]]:
    """Linhas da seção "Como o texto argumenta" e os avisos próprios gerados nela."""
    sem_modelo = dossie.argumento_sem_modelo(state, ctx)
    if sem_modelo is not None:
        return [dossie.TITULO_ARGUMENTO, *sem_modelo], []
    try:
        return [dossie.TITULO_ARGUMENTO, sintese_livre(state, ctx)], []
    except ModeloIndisponivel as e:
        logger.warning("Sintetizador: modelo indisponível: %s", e)
        aviso = WARN_MODELO_INDISPONIVEL
    except SinteseReprovada:
        aviso = WARN_GUARDRAILS
    return [dossie.TITULO_ARGUMENTO, *dossie.fallback_argumento(state, ctx)], [aviso]


def sintetizador_node(state: PipelineState) -> dict:
    if not state.segments:
        return {"dossier": dossie.SEM_TEXTO}

    ctx = dossie.preprocessar(state)
    argumento, avisos = secao_argumento(state, ctx)
    texto = dossie.montar(
        dossie.secao_checagens(state, ctx),
        argumento,
        dossie.secao_perguntas(state),
        dossie.secao_limites(state),
    )
    texto, removeu = dossie.remover_citacoes_invalidas(texto, state.evidence or [])
    if removeu:
        avisos.append(WARN_CITACAO_REMOVIDA)
    return {"dossier": texto, "warnings": avisos} if avisos else {"dossier": texto}


# Nomes usados pelo graph.py e pelas convenções do projeto
synthesizer_node = sintetizador_node
run = sintetizador_node
