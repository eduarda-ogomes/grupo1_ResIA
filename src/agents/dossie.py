"""Partes do dossiê que o código escreve, sem LLM: tudo o que é fato.

Design: docs/superpowers/specs/2026-10-01-agente-sintetizador-design.md ("Como funciona" e
"Casos degradados"); Manual §4.5.1. O synthesizer.py junta estas seções com a síntese
livre do LLM ("Como o texto argumenta").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.agents.ingestor import is_url
from src.guardrails.citacoes import neutralizar_urls, urls_invalidas
from src.state import Evidence, PipelineState, Segment

TITULO_CHECAGENS = "## O que as checagens dizem"
TITULO_ARGUMENTO = "## Como o texto argumenta"
TITULO_PERGUNTAS = "## Perguntas para pensar antes de decidir"
TITULO_LIMITES = "## Limites desta análise"
TITULO_FONTES = "## Fontes"

# Cópia exata do spec do dossiê final ("2. O que as checagens dizem"); sem os termos do filtro de veredito
LEGENDA_CHECAGENS = (
    "_Comparamos cada afirmação factual com checagens já publicadas por agências. "
    "**Contradiz**: a agência checou uma alegação igual e concluiu que ela não se sustenta. "
    "**Apoia**: concluiu que ela se sustenta. "
    "**Não conclusiva**: deu um veredito intermediário (como \"enganoso\" ou \"sem contexto\") "
    "ou não chegou a uma conclusão. "
    "O selo ao lado é o veredito da própria agência; o número leva à fonte._"
)
ROTULOS_STANCE = {"contradiz": "Contradiz", "apoia": "Apoia", "insuficiente": "Não conclusiva"}

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

_ESCAPAR = re.compile(r"([\\`*_\[\]<>~$])")


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


# --- Texto da notícia dentro do Markdown ------------------------------------------

def escapar_markdown(texto: str) -> str:
    """Escapa com `\\` os caracteres que o Markdown do app interpretaria: \\ ` * _ [ ] < > ~ $.

    O `$` entra porque o Streamlit renderiza `$...$` como LaTeX ("R$ 10 e R$ 20").
    """
    return _ESCAPAR.sub(r"\\\1", texto)


def texto_seguro(texto: str) -> str:
    """Frase ou trecho da notícia/corpus pronto para o dossiê: escapa primeiro e só depois troca as URLs
    por [link], para que o próprio "[link]" não seja escapado."""
    return neutralizar_urls(escapar_markdown(texto))


def encurtar(texto: str, limite: int = 80) -> str:
    """Corta em `limite` caracteres no máximo, terminando em "…" quando cortou."""
    if len(texto) <= limite:
        return texto
    return texto[:limite - 1].rstrip() + "…"


# --- 3. Montagem: "O que as checagens dizem" e "Fontes" ------------------------------

def _por_frase(ctx: Contexto) -> dict[str, list[Evidence]]:
    por_frase: dict[str, list[Evidence]] = {}
    for ev in ctx.evidencias:
        por_frase.setdefault(ev.segment_id, []).append(ev)
    return por_frase


def numerar_fontes(state: PipelineState, ctx: Contexto) -> dict[str, int]:
    """URL -> número da fonte, na ordem das frases e depois das evidências de cada frase.

    Só numera o que aparece no corpo (evidência de frase que não está em segments não aparece);
    a mesma URL em duas frases fica com o primeiro número.
    """
    por_frase = _por_frase(ctx)
    fontes: dict[str, int] = {}
    for segment in state.segments:
        for ev in por_frase.get(segment.id, []):
            fontes.setdefault(ev.source_url, len(fontes) + 1)
    return fontes


def _selo(ev: Evidence) -> str:
    return f"{ev.source_name}: {ev.agency_verdict}" if ev.agency_verdict else ev.source_name


def _linha_checagem(ev: Evidence, fontes: dict[str, int]) -> str:
    return f"  - {ROTULOS_STANCE[ev.stance]} · {_selo(ev)} [↗ {fontes[ev.source_url]}](<{ev.source_url}>)"


def linha_sem_checagem(frases: list[Segment]) -> str:
    """Uma linha com teto de tamanho: até 2 frases (cortadas em 80 caracteres) e a contagem do resto.

    `frases` não pode ser vazia; a lista completa fica no expander do app.
    """
    n = len(frases)
    citadas = [f'"{texto_seguro(encurtar(s.text))}"' for s in frases[:2]]
    if n == 1:
        lista, frase = f"1 afirmação factual, {citadas[0]}", "essa frase"
    elif n == 2:
        lista, frase = f"2 afirmações factuais, {citadas[0]} e {citadas[1]}", "essas frases"
    else:
        lista, frase = f"{n} afirmações factuais, como {citadas[0]}, {citadas[1]} e mais {n - 2}", "essas frases"
    return f"- Sem checagem no nosso banco: {lista}. Isso não confirma nem descarta {frase}."


def secao_checagens(state: PipelineState, ctx: Contexto, fontes: dict[str, int]) -> list[str]:
    linhas = [TITULO_CHECAGENS]
    if state.evidence is None:
        return linhas + [SEM_BANCO]

    por_frase = _por_frase(ctx)

    # Na ordem das frases; evidência de frase que não está em segments não aparece (e o ID nunca aparece)
    corpo: list[str] = []
    for segment in state.segments:
        evs = por_frase.get(segment.id)
        if evs:
            corpo.append(f'- "{texto_seguro(segment.text)}"')
            corpo += [_linha_checagem(ev, fontes) for ev in evs]

    if not corpo:
        return linhas + [SEM_CHECAGEM]
    linhas += [LEGENDA_CHECAGENS, *corpo]
    if ctx.factuais_sem_checagem:
        linhas.append(linha_sem_checagem(ctx.factuais_sem_checagem))
    return linhas


def secao_fontes(ctx: Contexto, fontes: dict[str, int]) -> list[str]:
    """Uma linha por fonte numerada: veredito da agência, trecho da checagem e link. [] sem fontes."""
    if not fontes:
        return []
    primeira: dict[str, Evidence] = {}
    for ev in ctx.evidencias:
        if ev.source_url in fontes:
            primeira.setdefault(ev.source_url, ev)
    return [TITULO_FONTES] + [
        f'{n}. {_selo(primeira[url])} — "{texto_seguro(primeira[url].excerpt)}" · [abrir ↗](<{url}>)'
        for url, n in sorted(fontes.items(), key=lambda item: item[1]) if url in primeira
    ]


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
    linhas = [f'- {ROTULOS[m.type]}: "{texto_seguro(m.excerpt)}"' for m in state.text_report.markers]
    linhas += [f'- Juízo de valor: "{texto_seguro(s.text)}" é uma opinião e não foi checada.' for s in ctx.frases_valor]
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
    else:
        classificadas = {st.segment_id for st in state.text_report.statements}
        sem_classificacao = [s for s in state.segments if s.id not in classificadas]
        if sem_classificacao:
            frases = ", ".join(f'"{texto_seguro(s.text)}"' for s in sem_classificacao)
            linhas.append(f"- Estas frases não puderam ser classificadas como fato ou opinião: {frases}.")
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
