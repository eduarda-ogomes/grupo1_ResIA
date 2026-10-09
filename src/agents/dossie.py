"""Partes do dossiê que o código escreve, sem LLM: tudo o que é fato.

Design: docs/superpowers/specs/2026-10-01-agente-sintetizador-design.md ("Como funciona" e
"Casos degradados"); Manual §4.5.1. O synthesizer.py junta estas seções com a síntese
livre do LLM ("Como o texto argumenta").
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from src.agents.ingestor import is_url
from src.guardrails.citacoes import neutralizar_urls, urls_invalidas
from src.state import Evidence, PipelineState, Segment

TITULO_RESUMO = "## Resumo"
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
# Contagem por stance do Resumo, na ordem contradiz -> apoia -> insuficiente: (stance, singular, plural)
FORMAS_STANCE = (
    ("contradiz", "contradiz", "contradizem"),
    ("apoia", "apoia", "apoiam"),
    ("insuficiente", "não conclusiva", "não conclusivas"),
)
# Cópia exata do spec do dossiê final ("1. Resumo")
RESUMO_SEM_VEREDITO = ("- O dossiê não dá veredito: mostra o que já foi checado, como o texto argumenta "
                       "e o que perguntar antes de decidir.")
RESUMO_SEM_BANCO = "- O banco de checagens não pôde ser consultado."

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
_CIFRAO = re.compile(r"(?<!\\)\$")


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


def escapar_cifrao(texto: str) -> str:
    """Escapa só o `$` (para `\\$`), sem tocar no resto do Markdown nem escapar de novo um `\\$` que já veio escapado.

    É o escape do texto livre do LLM ("Como o texto argumenta"): ele escreve bullets e ênfase de propósito,
    mas o Streamlit renderizaria `$...$` como LaTeX.
    """
    return _CIFRAO.sub(r"\\$", texto)


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


def _evidencias_no_corpo(state: PipelineState, ctx: Contexto) -> Iterator[Evidence]:
    """As evidências na ordem em que aparecem no corpo: frase por frase de `state.segments` e, em cada uma,
    na ordem de `ctx.evidencias`. Evidência de frase que não está em segments não aparece (e o ID nunca aparece)."""
    por_frase = _por_frase(ctx)
    for segment in state.segments:
        yield from por_frase.get(segment.id, [])


def numerar_fontes(state: PipelineState, ctx: Contexto) -> dict[str, int]:
    """URL -> número da fonte, na ordem em que a URL aparece no corpo (frases e depois evidências de cada frase).

    Só numera o que aparece no corpo; a mesma URL em duas frases fica com o primeiro número.
    """
    fontes: dict[str, int] = {}
    for ev in _evidencias_no_corpo(state, ctx):
        fontes.setdefault(ev.source_url, len(fontes) + 1)
    return fontes


def _selo(ev: Evidence) -> str:
    nome = escapar_markdown(ev.source_name)
    return f"{nome}: {escapar_markdown(ev.agency_verdict)}" if ev.agency_verdict else nome


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


def secao_fontes(state: PipelineState, ctx: Contexto, fontes: dict[str, int]) -> list[str]:
    """Uma linha por fonte numerada: veredito da agência, trecho da checagem e link. [] sem fontes.

    O selo e o trecho vêm da primeira evidência da URL na ordem do corpo (a mesma da numeração),
    não de uma evidência de frase que ficou fora do corpo.
    """
    if not fontes:
        return []
    primeira: dict[str, Evidence] = {}
    for ev in _evidencias_no_corpo(state, ctx):
        primeira.setdefault(ev.source_url, ev)
    return [TITULO_FONTES] + [
        f'{n}. {_selo(primeira[url])} — "{texto_seguro(primeira[url].excerpt)}" · [abrir ↗](<{url}>)'
        for url, n in sorted(fontes.items(), key=lambda item: item[1]) if url in primeira
    ]


# --- Resumo ---------------------------------------------------------------------------

def contagem_por_stance(stances: list[str]) -> str:
    """"2 contradizem, 1 apoia, 1 não conclusiva": na ordem contradiz -> apoia -> insuficiente, sem os zeros."""
    partes = []
    for stance, singular, plural in FORMAS_STANCE:
        n = stances.count(stance)
        if n:
            partes.append(f"{n} {singular if n == 1 else plural}")
    return ", ".join(partes)


def _quantos(n: int, singular: str, plural: str, nenhum: str) -> str:
    if n == 0:
        return nenhum
    return f"1 {singular}" if n == 1 else f"{n} {plural}"


def _linha_checagens_do_resumo(f: int, k: int, contagem: str) -> str:
    """Segunda linha do Resumo com text_report (f = afirmações factuais, k = as que têm checagem)."""
    if f == 0:
        return "- Nenhuma afirmação factual para checar."
    if k == 0:
        return "- A única afirmação factual não tem checagem no nosso banco." if f == 1 \
            else f"- Nenhuma das {f} afirmações factuais tem checagem no nosso banco."
    if f == 1:
        return f"- A única afirmação factual tem checagem publicada ({contagem})."
    if k == 1:
        return f"- 1 das {f} afirmações factuais tem checagem publicada ({contagem})."
    return f"- {k} das {f} afirmações factuais têm checagem publicada ({contagem})."


def _linha_checagens_do_resumo_sem_relatorio(k: int, contagem: str) -> str:
    if k == 0:
        return "- Nenhuma frase tem checagem no nosso banco."
    if k == 1:
        return f"- 1 frase tem checagem publicada ({contagem})."
    return f"- {k} frases têm checagem publicada ({contagem})."


def _linha_padroes(m: int) -> str:
    if m == 0:
        return "- Nenhum padrão de argumentação apontado."
    return "- 1 padrão de argumentação apontado." if m == 1 else f"- {m} padrões de argumentação apontados."


def secao_resumo(state: PipelineState, ctx: Contexto) -> list[str]:
    """Tamanho do problema em quatro linhas (spec do dossiê final, "1. Resumo"), só com contagens.

    As checagens contadas são as que aparecem no corpo; com `text_report`, só as das afirmações factuais.
    A contagem por stance é de checagens publicadas (cada linha de checagem do corpo), não de frases.
    """
    n = len(state.segments)
    frases = "1 frase analisada" if n == 1 else f"{n} frases analisadas"
    tem_relatorio = state.text_report is not None

    checagens = [ev for ev in _evidencias_no_corpo(state, ctx)
                 if not tem_relatorio or ctx.tipo_por_frase.get(ev.segment_id) == "factual"]
    k = len({ev.segment_id for ev in checagens})
    contagem = contagem_por_stance([ev.stance for ev in checagens])

    if tem_relatorio:
        tipos = [ctx.tipo_por_frase.get(s.id) for s in state.segments]
        f, v = tipos.count("factual"), tipos.count("valor")
        factuais = _quantos(f, "afirmação factual", "afirmações factuais", "nenhuma afirmação factual")
        opinioes = _quantos(v, "opinião", "opiniões", "nenhuma opinião")
        primeira = f"- {frases}: {factuais} e {opinioes}."
        padroes = [_linha_padroes(len(state.text_report.markers))]
        checagens_linha = _linha_checagens_do_resumo(f, k, contagem)
    else:
        primeira, padroes = f"- {frases}.", []
        checagens_linha = _linha_checagens_do_resumo_sem_relatorio(k, contagem)

    if state.evidence is None:
        checagens_linha = RESUMO_SEM_BANCO
    return [TITULO_RESUMO, primeira, checagens_linha, *padroes, RESUMO_SEM_VEREDITO]


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
    return [TITULO_PERGUNTAS] + [f"{i}. {escapar_markdown(q)}" for i, q in enumerate(state.socratic_questions, start=1)]


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
    """Junta as seções com uma linha em branco entre elas; seção vazia (como Fontes sem evidência) é pulada."""
    return "\n\n".join("\n".join(secao) for secao in secoes if secao)


def remover_citacoes_invalidas(dossie: str, evidencias) -> tuple[str, bool]:
    """Rede de segurança: tira as linhas com URL fora das evidências; diz se tirou alguma."""
    linhas = dossie.split("\n")
    validas = [linha for linha in linhas if not urls_invalidas(linha, evidencias)]
    return "\n".join(validas), len(validas) < len(linhas)
