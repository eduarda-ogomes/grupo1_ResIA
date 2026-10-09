"""Agente Sintetizador (R5): junta os ramos num dossiê neutro e citável, sem veredito.

Abordagem híbrida (Manual §4.5.1; design em docs/superpowers/specs/2026-10-01-agente-sintetizador-design.md):
o código escreve tudo o que é fato (src/agents/dossie.py); o qwen2.5-7b escreve só a seção
"Como o texto argumenta", com guardrails (src/guardrails/), 1 retry e fallback em código.
Ordem das seções: Resumo, Checagens, Argumento, Perguntas, Limites, Fontes
(docs/superpowers/specs/2026-10-08-dossie-final-design.md).

Dois nós (docs/superpowers/specs/2026-10-09-desempenho-agentes-design.md):
- argumento_node(state) -> {"argument": list[str]}: o `agente_argumento`, depois do Agente de Texto,
  em paralelo com o Socrático; "warnings" só quando o problema é dele.
- sintetizador_node(state) -> {"dossier": str}: só monta, sem LLM; "warnings" só se a rede de
  segurança das citações remover algo. Nunca devolve dossier = None.
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.agents import dossie
from src.guardrails.ancoragem import citacoes_nao_literais, termos_fora_do_contexto
from src.guardrails.citacoes import extrair_urls, neutralizar_urls
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
    frases = "\n".join(
        f"- ({ctx.tipo_por_frase.get(s.id, 'sem rótulo')}) {neutralizar_urls(s.text)}" for s in state.segments
    )
    texto_da_frase = {s.id: neutralizar_urls(s.text) for s in state.segments}
    marcadores = "\n".join(
        f'- {dossie.ROTULOS[m.type]} | frase: "{texto_da_frase.get(m.segment_id, "")}" '
        f'| trecho: "{neutralizar_urls(m.excerpt)}" | explicação: {neutralizar_urls(m.explanation)}'
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


def problema_da_sintese(texto: str, frases: list[str]) -> str | None:
    """Guardrails sobre o texto do modelo; devolve o problema nomeado para o retry, ou None.

    `frases` são os textos dos segmentos já passados por neutralizar_urls, os mesmos que o modelo recebeu:
    G3 exige que todo trecho entre aspas esteja literalmente numa delas; G4, que nomes, números e doenças
    apareçam nelas. Os rótulos fixos do prompt (dossie.ROTULOS, "Juízo de valor") não contam como termos.
    """
    if not texto:
        return "Seu texto veio vazio."
    termos = termos_de_veredito(texto)
    if termos:
        return f"Seu texto usou o termo '{termos[0]}'."
    if extrair_urls(texto):
        return "Seu texto incluiu um link."
    trechos = citacoes_nao_literais(texto, frases)
    if trechos:
        return f'Seu texto citou "{trechos[0]}", que não está em nenhuma frase da notícia.'
    ignorar = list(dossie.ROTULOS.values()) + ["Juízo de valor"]
    fora = termos_fora_do_contexto(texto, " ".join(frases), ignorar)
    if fora:
        return f"Seu texto mencionou '{fora[0]}', que não aparece na notícia."
    return None


def sintese_livre(state: PipelineState, ctx: dossie.Contexto) -> str:
    frases = [neutralizar_urls(s.text) for s in state.segments]
    problema = None
    for _ in range(2):  # 1 tentativa + 1 retry
        try:
            bruto = chamar_modelo(montar_mensagens(state, ctx, problema))
        except Exception as e:
            raise ModeloIndisponivel(str(e)) from e
        texto = limpar_resposta(bruto)
        problema = problema_da_sintese(texto, frases)
        if problema is None:
            return texto
        logger.warning("Sintetizador: síntese livre rejeitada: %s", problema)
    raise SinteseReprovada(problema)


def linhas_argumento(state: PipelineState, ctx: dossie.Contexto) -> tuple[list[str], list[str]]:
    """Linhas da seção "Como o texto argumenta" (sem o título) e os avisos próprios gerados nela."""
    sem_modelo = dossie.argumento_sem_modelo(state, ctx)
    if sem_modelo is not None:
        return sem_modelo, []
    try:
        # Escapa depois dos guardrails, que conferem o texto como o modelo o escreveu
        return [dossie.escapar_cifrao(sintese_livre(state, ctx))], []
    except ModeloIndisponivel as e:
        logger.warning("Argumento: modelo indisponível: %s", e)
        aviso = WARN_MODELO_INDISPONIVEL
    except SinteseReprovada:
        aviso = WARN_GUARDRAILS
    return dossie.fallback_argumento(state, ctx), [aviso]


def argumento_node(state: PipelineState) -> dict:
    """Nó `agente_argumento`: escreve as linhas de "Como o texto argumenta" em `argument`.

    Chama o LLM só quando há o que descrever; modelo fora do ar ou reprovado nos guardrails
    cai no fallback em código e avisa. Devolve "warnings" só quando o problema é dele.
    """
    linhas, avisos = linhas_argumento(state, dossie.preprocessar(state))
    return {"argument": linhas, "warnings": avisos} if avisos else {"argument": linhas}


def argumento_fallback(state: PipelineState) -> dict:
    """As linhas do argumento sem chamar o LLM.

    O grafo usa quando o `agente_argumento` estoura o tempo (src/graph.py) e o Sintetizador
    quando `argument` não chegou: o usuário recebe a seção em fallback, não um dossiê vazio.
    """
    ctx = dossie.preprocessar(state)
    sem_modelo = dossie.argumento_sem_modelo(state, ctx)
    return {"argument": sem_modelo if sem_modelo is not None else dossie.fallback_argumento(state, ctx)}


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
