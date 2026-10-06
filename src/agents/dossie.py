"""Partes do dossiê que o código escreve, sem LLM: tudo o que é fato.

Design: docs/superpowers/specs/2026-10-01-agente-sintetizador-design.md ("Como funciona" e
"Casos degradados"); Manual §4.5.1. O synthesizer.py junta estas seções com a síntese
livre do LLM ("Como o texto argumenta").
"""
from __future__ import annotations

from dataclasses import dataclass

from src.agents.ingestor import is_url
from src.guardrails.citacoes import urls_invalidas
from src.state import Evidence, PipelineState, Segment

TITULO_CHECAGENS = "## O que as checagens dizem"
TITULO_ARGUMENTO = "## Como o texto argumenta"
TITULO_PERGUNTAS = "## Perguntas para pensar antes de decidir"
TITULO_LIMITES = "## Limites desta análise"

ROTULOS = {
    "adjetivacao_extrema": "Adjetivação extrema",
    "urgencia_artificial": "Urgência",
    "apelo_autoridade": "Autoridade sem identificação",
    "falsa_dicotomia": "Falsa dicotomia",
    "generalizacao": "Generalização",
}

SEM_TEXTO = (f"{TITULO_LIMITES}\n- A página não pôde ser analisada: nenhum texto foi extraído. "
             "Cole o texto da matéria no campo de entrada para analisar.")
SEM_BANCO = "- Não foi possível consultar o banco de checagens nesta análise."
SEM_CHECAGEM = ("- Nenhuma checagem encontrada no nosso banco para as frases factuais. "
                "Isso não confirma nem descarta essas frases.")
SEM_ESTRUTURA = "- Não foi possível analisar a estrutura do texto."
SEM_PADROES = "- Nenhum padrão de viés ou falácia foi apontado neste texto."
SEM_PERGUNTAS = "- As perguntas não puderam ser geradas nesta análise."
NENHUMA_PERGUNTA = "- Nenhuma pergunta foi gerada para este texto."
LIMITE_COLETA = "- O banco de checagens pode não conter checagens mais recentes que a última coleta."

_NUMERAIS = {1: "uma", 2: "duas", 3: "três", 4: "quatro", 5: "cinco", 6: "seis"}


@dataclass
class Contexto:
    evidencias: list[Evidence]            # deduplicadas e sem as de frases de valor
    tipo_por_frase: dict[str, str]        # segment_id -> "factual" | "valor"; vazio sem text_report
    factuais_sem_checagem: list[Segment]
    frases_valor: list[Segment]


# --- 1. Pré-processamento --------------------------------------------------------

def preprocessar(state: PipelineState) -> Contexto:
    tipo = {st.segment_id: st.kind for st in state.text_report.statements} if state.text_report else {}

    vistas, evidencias = set(), []
    for ev in state.evidence or []:
        chave = (ev.segment_id, ev.source_url)
        # Opinião não é checada (§3.5); sem text_report não há como saber, e a evidência fica (§4.7)
        if chave in vistas or tipo.get(ev.segment_id) == "valor":
            continue
        vistas.add(chave)
        evidencias.append(ev)

    com_evidencia = {ev.segment_id for ev in evidencias}
    return Contexto(
        evidencias=evidencias,
        tipo_por_frase=tipo,
        factuais_sem_checagem=[s for s in state.segments if tipo.get(s.id) == "factual" and s.id not in com_evidencia],
        frases_valor=[s for s in state.segments if tipo.get(s.id) == "valor"],
    )


# --- 3. Montagem: "O que as checagens dizem" -------------------------------------

def _numeral(n: int) -> str:
    return _NUMERAIS.get(n, str(n))


def _checagens(n: int) -> str:
    return f"{_numeral(n)} {'checagem' if n == 1 else 'checagens'}"


def resumo_por_stance(stances: list[str]) -> str:
    """Resumo por extenso, na ordem contradiz -> apoia -> insuficiente."""
    n = {s: stances.count(s) for s in ("contradiz", "apoia", "insuficiente")}
    partes = []
    for stance, singular, plural in (("contradiz", "contradiz", "contradizem"), ("apoia", "apoia", "apoiam")):
        if n[stance]:
            # o substantivo só vai no primeiro: "duas checagens contradizem e uma apoia"
            sujeito = _checagens(n[stance]) if not partes else _numeral(n[stance])
            partes.append(f"{sujeito} {singular if n[stance] == 1 else plural}")
    if not n["insuficiente"]:
        return f"{' e '.join(partes)} esta frase"
    conclusiva = "não é conclusiva" if n["insuficiente"] == 1 else "não são conclusivas"
    if not partes:
        return f"{_checagens(n['insuficiente'])} {conclusiva} sobre esta frase"
    return f"{' e '.join(partes)} esta frase, e {_numeral(n['insuficiente'])} {conclusiva}"


def _sublinha(ev: Evidence) -> str:
    selo = f"{ev.source_name}: {ev.agency_verdict}" if ev.agency_verdict else ev.source_name
    return f'  - {selo} — "{ev.excerpt}" ({ev.source_url})'


def secao_checagens(state: PipelineState, ctx: Contexto) -> list[str]:
    linhas = [TITULO_CHECAGENS]
    if state.evidence is None:
        return linhas + [SEM_BANCO]

    por_frase: dict[str, list[Evidence]] = {}
    for ev in ctx.evidencias:
        por_frase.setdefault(ev.segment_id, []).append(ev)

    # Na ordem das frases; evidência de frase que não está em segments não aparece (e o ID nunca aparece)
    for segment in state.segments:
        evs = por_frase.get(segment.id)
        if evs:
            linhas.append(f'- "{segment.text}" — {resumo_por_stance([e.stance for e in evs])}.')
            linhas += [_sublinha(ev) for ev in evs]

    if len(linhas) == 1:
        return linhas + [SEM_CHECAGEM]
    if ctx.factuais_sem_checagem:
        frases = ", ".join(f'"{s.text}"' for s in ctx.factuais_sem_checagem)
        linhas.append(f"- Nenhuma checagem encontrada no nosso banco para: {frases}. "
                      "Isso não confirma nem descarta essas frases.")
    return linhas


# --- "Como o texto argumenta" sem LLM ---------------------------------------------

def argumento_sem_modelo(state: PipelineState, ctx: Contexto) -> list[str] | None:
    """Bullets da seção quando não há o que o LLM descrever; None quando a seção precisa do LLM."""
    if state.text_report is None:
        return [SEM_ESTRUTURA]
    if not state.text_report.markers and not ctx.frases_valor:
        return [SEM_PADROES]
    return None


def fallback_argumento(state: PipelineState, ctx: Contexto) -> list[str]:
    """Rótulo + trecho literal por marcador e uma linha por frase de valor.

    Não copia o `explanation` do Agente de Texto: também é texto de LLM e furaria o filtro de veredito.
    """
    linhas = [f'- {ROTULOS[m.type]}: "{m.excerpt}"' for m in state.text_report.markers]
    linhas += [f'- Juízo de valor: "{s.text}" é uma opinião e não foi checada.' for s in ctx.frases_valor]
    return linhas


# --- Perguntas e limites -----------------------------------------------------------

def secao_perguntas(state: PipelineState) -> list[str]:
    if state.socratic_questions is None:
        return [TITULO_PERGUNTAS, SEM_PERGUNTAS]
    if not state.socratic_questions:
        return [TITULO_PERGUNTAS, NENHUMA_PERGUNTA]
    return [TITULO_PERGUNTAS] + [f"{i}. {q}" for i, q in enumerate(state.socratic_questions, start=1)]


def secao_limites(state: PipelineState) -> list[str]:
    linhas = [TITULO_LIMITES]
    if state.truncated:
        linhas.append("- Só o início do texto foi analisado (o texto ultrapassou o limite).")
    if state.published_at is None:
        linhas.append("- O texto não tem data de publicação.")
    if not is_url(state.raw_input.strip()):
        linhas.append("- O texto não tem link de origem.")
    if state.evidence is None:
        linhas.append("- O banco de checagens não pôde ser consultado.")
    if state.text_report is None:
        linhas.append("- A estrutura do texto não pôde ser analisada.")
    if state.socratic_questions is None:
        linhas.append("- As perguntas reflexivas não puderam ser geradas.")
    return linhas + [LIMITE_COLETA]


# --- 3 e 4. Montagem e checagem final ----------------------------------------------

def montar(*secoes: list[str]) -> str:
    return "\n\n".join("\n".join(secao) for secao in secoes)


def remover_citacoes_invalidas(dossie: str, evidencias) -> tuple[str, bool]:
    """Rede de segurança: tira as linhas com URL fora das evidências; diz se tirou alguma."""
    linhas = dossie.split("\n")
    validas = [linha for linha in linhas if not urls_invalidas(linha, evidencias)]
    return "\n".join(validas), len(validas) < len(linhas)
