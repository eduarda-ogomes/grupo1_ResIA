"""Argumento: o efeito de cada marcador em "Como o texto argumenta", passo final do Agente de Texto.

O `texto_node` (src/agents/text_analysis.py) classifica as frases e, quando há classificação, chama
`argumento_node` com o estado já classificado; o Sintetizador só monta o dossiê com o `argument` pronto.
O código escreve o rótulo, o trecho literal e o juízo de valor (src/agents/synthesizer/dossie.py); o LLM
escreve só o efeito de cada marcador, em JSON, com guardrails (src/guardrails/), 1 retry e linha sem efeito
quando o efeito não passa. Design: docs/superpowers/specs/2026-10-09-desempenho-agentes-design.md e
docs/superpowers/specs/2026-10-15-agentes-em-paralelo-design.md.

O cliente `llm_sintetizador`, o prompt `sintetizador_sistema.md` e o prefixo "sintetizador:" dos avisos
mantêm o nome de quando este passo era do Sintetizador.

argumento_node(state) -> {"argument": list[str]}; "warnings" só quando o problema é dele.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from src.agents.synthesizer import dossie
from src.guardrails.ancoragem import citacoes_nao_literais, termos_fora_do_contexto
from src.guardrails.citacoes import extrair_urls, neutralizar_urls
from src.guardrails.veredito import termos_de_veredito
from src.services.llm import llm_sintetizador
from src.state import PipelineState, TextMarker

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

WARN_MODELO_INDISPONIVEL = "sintetizador: falha ao chamar o modelo (o LM Studio está rodando?)"
WARN_GUARDRAILS = "sintetizador: efeito do argumento reprovado nos guardrails após 1 retry"
WARN_SAIDA_INVALIDA = "sintetizador: saída inválida após 1 retry"
WARN_ERRO_INESPERADO = "sintetizador: erro inesperado no efeito dos marcadores; seção sem efeito"

# Última linha da mensagem de retry quando a resposta não pôde ser lida
PROBLEMA_ILEGIVEL = "Sua resposta não era um JSON no formato pedido."


class Efeito(BaseModel):
    marcador: int   # posição do marcador na lista enviada, a partir de 1
    efeito: str     # o que o trecho faz com quem lê, em até 15 palavras


class RespostaArgumento(BaseModel):
    """O JSON que o modelo devolve (`response_format` estrito)."""
    efeitos: list[Efeito]


class ModeloIndisponivel(RuntimeError):
    """A chamada ao modelo falhou (conexão, timeout, servidor fora do ar)."""


def carregar_prompt_sistema() -> str:
    return (PROMPTS_DIR / "sintetizador_sistema.md").read_text(encoding="utf-8")


def montar_mensagem_usuario(state: PipelineState, marcadores: list[TextMarker]) -> str:
    """Os marcadores numerados, delimitados como dado (§3.5), sem IDs de frase e sem URLs."""
    texto_da_frase = {s.id: neutralizar_urls(s.text) for s in state.segments}
    linhas = "\n".join(
        f'[{i}] {dossie.ROTULOS[m.type]} | frase: "{texto_da_frase.get(m.segment_id, "")}" '
        f'| trecho: "{neutralizar_urls(m.excerpt)}" | explicação: {neutralizar_urls(m.explanation)}'
        for i, m in enumerate(marcadores, start=1)
    )
    return f"<marcadores>\n{linhas}\n</marcadores>"


def montar_mensagens(state: PipelineState, marcadores: list[TextMarker], problema: str | None = None) -> list[tuple[str, str]]:
    """`problema` é a frase pronta de `_frase_do_problema` ("O efeito do marcador 1 foi rejeitado. ..."), sempre no fim."""
    usuario = montar_mensagem_usuario(state, marcadores)
    if problema:
        usuario += f"\n\nResponda de novo, só com o JSON, com um efeito para cada marcador.\n{problema}"
    return [("system", carregar_prompt_sistema()), ("user", usuario)]


def chamar_modelo(mensagens: list[tuple[str, str]]) -> str:
    """Única função que fala com o LM Studio. Os testes a substituem por um modelo falso."""
    formato = {
        "type": "json_schema",
        "json_schema": {"name": "efeitos_argumento", "strict": True, "schema": RespostaArgumento.model_json_schema()},
    }
    return llm_sintetizador.bind(response_format=formato).invoke(mensagens).content


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


def avaliar_efeitos(resposta: RespostaArgumento, n_marcadores: int, frases: list[str]) -> tuple[dict[int, str], dict[int, str]]:
    """(aprovados, reprovados): índice do marcador (a partir de 1) -> efeito aprovado / problema nomeado.

    Índice fora de 1..n_marcadores ou repetido (vale o primeiro) é ignorado: não aprova nem reprova.
    Só o efeito que chegou aos guardrails (vazio, veredito, link, G3, G4) e caiu conta como reprovado.
    """
    aprovados: dict[int, str] = {}
    reprovados: dict[int, str] = {}
    vistos: set[int] = set()
    for e in resposta.efeitos:
        if not 1 <= e.marcador <= n_marcadores or e.marcador in vistos:
            continue
        vistos.add(e.marcador)
        efeito = e.efeito.strip()
        problema = problema_da_sintese(efeito, frases)
        if problema is None:
            aprovados[e.marcador] = efeito
        else:
            reprovados[e.marcador] = problema
    return aprovados, reprovados


def _frase_do_problema(marcador: int, problema: str) -> str:
    return f"O efeito do marcador {marcador} foi rejeitado. {problema}"


def remover_cercas(bruto: str) -> str:
    """Tira a cerca ```json ... ``` que modelos pequenos às vezes colocam em volta do JSON."""
    texto = bruto.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1] if "\n" in texto else ""
        texto = texto.rsplit("```", 1)[0]
    return texto.strip()


def _pedir_efeitos(state: PipelineState, marcadores: list[TextMarker], problema: str | None) -> RespostaArgumento | None:
    """Uma chamada ao modelo. Falha de chamada vira ModeloIndisponivel; resposta que não é o JSON
    esperado (mesmo sem a cerca) devolve None."""
    try:
        bruto = chamar_modelo(montar_mensagens(state, marcadores, problema))
    except Exception as e:
        raise ModeloIndisponivel(str(e)) from e
    try:
        return RespostaArgumento.model_validate_json(remover_cercas(bruto))
    except ValidationError as e:
        logger.warning("Argumento: resposta fora do formato: %s", e.errors()[:1])
        return None


def _tentar(state: PipelineState, marcadores: list[TextMarker], frases: list[str],
            problema: str | None) -> tuple[dict[int, str], dict[int, str], bool]:
    """(aprovados, reprovados, legível) de uma tentativa; ModeloIndisponivel sobe para quem chamou."""
    resposta = _pedir_efeitos(state, marcadores, problema)
    if resposta is None:
        return {}, {}, False
    aprovados, reprovados = avaliar_efeitos(resposta, len(marcadores), frases)
    return aprovados, reprovados, True


def efeitos_do_modelo(state: PipelineState) -> tuple[dict[int, str], list[str]]:
    """Os efeitos aprovados por marcador e os avisos próprios gerados aqui.

    Retry só quando algum efeito foi reprovado ou a resposta não pôde ser lida; depois dele vale o melhor
    efeito de cada marcador entre as duas tentativas. Avisos: guardrails se algum efeito reprovado continua
    sem efeito aprovado; saída inválida se a resposta do retry continua ilegível.
    """
    marcadores = dossie.selecionar_marcadores(state.text_report.markers)
    frases = [neutralizar_urls(s.text) for s in state.segments]
    try:
        aprovados, reprovados, legivel = _tentar(state, marcadores, frases, None)
    except ModeloIndisponivel as e:
        logger.warning("Argumento: modelo indisponível: %s", e)
        return {}, [WARN_MODELO_INDISPONIVEL]
    if legivel and not reprovados:
        return aprovados, []

    if reprovados:
        problema = _frase_do_problema(*next(iter(reprovados.items())))
        logger.warning("Argumento: efeito rejeitado: %s", reprovados)
    else:
        problema = PROBLEMA_ILEGIVEL
        logger.warning("Argumento: resposta ilegível, nova tentativa")
    indisponivel = False
    try:
        aprovados2, reprovados2, legivel2 = _tentar(state, marcadores, frases, problema)
    except ModeloIndisponivel as e:
        logger.warning("Argumento: modelo indisponível no retry: %s", e)
        aprovados2, reprovados2, legivel2, indisponivel = {}, {}, True, True
    aprovados = {**aprovados2, **aprovados}   # empate: vale a primeira tentativa, já aprovada
    avisos = []
    if (set(reprovados) | set(reprovados2)) - set(aprovados):
        avisos.append(WARN_GUARDRAILS)
    if not legivel2:
        avisos.append(WARN_SAIDA_INVALIDA)
    elif indisponivel and not legivel:
        avisos.append(WARN_MODELO_INDISPONIVEL)
    return aprovados, avisos


def argumento_node(state: PipelineState) -> dict:
    """Passo final do Agente de Texto: escreve as linhas de "Como o texto argumenta" em `argument`.

    Chama o LLM só quando há marcador a descrever (e só para o efeito dele); modelo fora do ar ou efeito
    reprovado nos guardrails deixa o marcador sem efeito e avisa. Devolve "warnings" só quando o problema é dele.
    """
    sem_modelo = dossie.argumento_sem_modelo(state, dossie.preprocessar(state))
    if sem_modelo is not None:
        return {"argument": sem_modelo}
    if not state.text_report.markers:   # só opiniões: a linha de juízo de valor é código puro
        return {"argument": dossie.linhas_argumento(state, {})}
    efeitos, avisos = efeitos_do_modelo(state)
    linhas = dossie.linhas_argumento(state, efeitos)
    return {"argument": linhas, "warnings": avisos} if avisos else {"argument": linhas}


def argumento_sem_derrubar_o_texto(state: PipelineState) -> dict:
    """`argumento_node` que nunca levanta: um erro inesperado (ex.: um bug nos guardrails) vira o fallback
    em código com aviso, para não levar junto a classificação do Agente de Texto, que roda no mesmo nó."""
    try:
        return argumento_node(state)
    except Exception:
        logger.exception("Argumento: erro inesperado; seção em fallback")
        return {"argument": dossie.linhas_argumento(state, {}), "warnings": [WARN_ERRO_INESPERADO]}
