"""Agente de Texto (R3): mostra como o texto argumenta, sem julgar se é verdadeiro.

Entrada: state.segments. Saída: {"text_report": TextReport | None, "warnings"?: [...]}.
Manual: §4.3 (especificação), §4.7 (falha por lote após 1 retry), §3.5 (notícia é dado, não instrução).

Falha por lote, não do texto inteiro: o que o modelo classificou fica, e as frases que
continuaram sem classificação depois do retry são listadas num aviso. `text_report` só
é None quando nenhuma frase foi classificada.
"""
import json
import logging
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from src.services.llm import llm_texto
from src.state import PipelineState, Segment, TextReport

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
TAMANHO_LOTE = 15
FRASES_DE_CONTEXTO = 2

WARN_SAIDA_INVALIDA = "texto: saída inválida após 1 retry"
WARN_MODELO_INDISPONIVEL = "texto: falha ao chamar o modelo (o LM Studio está rodando?)"


def aviso_frases_sem_classificacao(ids: list[str]) -> str:
    n = len(ids)
    return f"texto: {n} {'frase' if n == 1 else 'frases'} sem classificação ({', '.join(ids)}); as demais foram analisadas"


class LoteInvalido(ValueError):
    """O JSON é válido, mas não classifica cada frase do lote exatamente uma vez.

    Leva a parte aproveitável da resposta (`parcial`) e as frases que faltaram (`faltando`).
    """

    def __init__(self, mensagem: str, parcial: TextReport, faltando: list[str]):
        super().__init__(mensagem)
        self.parcial = parcial
        self.faltando = faltando


class ModeloIndisponivel(RuntimeError):
    """A chamada ao modelo falhou (conexão, timeout, servidor fora do ar)."""


def carregar_prompt_sistema() -> str:
    return (PROMPTS_DIR / "texto_sistema.md").read_text(encoding="utf-8")


def carregar_exemplos() -> list[dict]:
    return json.loads((PROMPTS_DIR / "texto_exemplos.json").read_text(encoding="utf-8"))


def dividir_em_lotes(
    segments: list[Segment], tamanho: int = TAMANHO_LOTE, contexto: int = FRASES_DE_CONTEXTO
) -> list[tuple[list[Segment], list[Segment]]]:
    """Devolve pares (frases de contexto, frases a classificar)."""
    lotes = []
    for inicio in range(0, len(segments), tamanho):
        anteriores = segments[max(0, inicio - contexto):inicio]
        lotes.append((anteriores, segments[inicio:inicio + tamanho]))
    return lotes


def _formatar(segments: list[Segment]) -> str:
    return "\n".join(f"[{s.id}] {s.text}" for s in segments)


def montar_mensagem_usuario(contexto: list[Segment], alvo: list[Segment]) -> str:
    partes = []
    if contexto:
        partes.append(f"<contexto>\n{_formatar(contexto)}\n</contexto>")
    partes.append(f"<frases_para_analisar>\n{_formatar(alvo)}\n</frases_para_analisar>")
    return "\n\n".join(partes)


def montar_mensagens(
    contexto: list[Segment], alvo: list[Segment], erro_anterior: str | None = None
) -> list[tuple[str, str]]:
    mensagens = [("system", carregar_prompt_sistema())]
    for exemplo in carregar_exemplos():
        entrada = [Segment(**s) for s in exemplo["entrada"]]
        mensagens.append(("user", montar_mensagem_usuario([], entrada)))
        mensagens.append(("assistant", json.dumps(exemplo["saida"], ensure_ascii=False)))
    usuario = montar_mensagem_usuario(contexto, alvo)
    if erro_anterior:
        usuario += (
            f"\n\nSua resposta anterior foi rejeitada: {erro_anterior}\n"
            "Responda de novo, só com o JSON, classificando todas as frases de <frases_para_analisar>."
        )
    mensagens.append(("user", usuario))
    return mensagens


def chamar_modelo(mensagens: list[tuple[str, str]]) -> str:
    """Única função que fala com o LM Studio. Os testes a substituem por um modelo falso."""
    formato = {
        "type": "json_schema",
        "json_schema": {"name": "text_report", "strict": True, "schema": TextReport.model_json_schema()},
    }
    return llm_texto.bind(response_format=formato).invoke(mensagens).content


def remover_cercas(bruto: str) -> str:
    """Tira a cerca ```json ... ``` que modelos pequenos às vezes colocam em volta do JSON."""
    texto = bruto.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1] if "\n" in texto else ""
        texto = texto.rsplit("```", 1)[0]
    return texto.strip()


def validar_lote(alvo: list[Segment], relatorio: TextReport) -> TextReport:
    """Checagem determinística (sem LLM) da resposta de um lote.

    Cada frase do lote precisa ser classificada exatamente uma vez; senão levanta
    LoteInvalido com a parte aproveitável: as frases classificadas uma vez só e os
    marcadores com trecho literal.
    """
    textos = {s.id: s.text for s in alvo}
    ordem = {s.id: i for i, s in enumerate(alvo)}

    statements = [st for st in relatorio.statements if st.segment_id in textos]
    vezes = Counter(st.segment_id for st in statements)
    unicos = sorted((st for st in statements if vezes[st.segment_id] == 1), key=lambda st: ordem[st.segment_id])
    markers = [
        m for m in relatorio.markers
        if m.segment_id in textos and m.excerpt.strip() and m.excerpt in textos[m.segment_id]
    ]
    parcial = TextReport(statements=unicos, markers=markers)

    faltando = [sid for sid in textos if vezes[sid] == 0]
    repetidos = [sid for sid in textos if vezes[sid] > 1]
    if faltando or repetidos:
        raise LoteInvalido(
            f"frases sem classificação: {faltando}; classificadas mais de uma vez: {repetidos}",
            parcial,
            [sid for sid in textos if vezes[sid] != 1],
        )
    return parcial


def analisar_lote(contexto: list[Segment], alvo: list[Segment]) -> tuple[TextReport, list[str]]:
    """Relatório do lote e as frases que ficaram sem classificação depois do retry.

    Lote completo: lista vazia. Senão, fica a tentativa que classificou mais frases; uma
    resposta que nem valida no schema não aproveita nada. Levanta ModeloIndisponivel.
    """
    erro = None
    melhor = TextReport(statements=[], markers=[]), [s.id for s in alvo]
    for _ in range(2):  # 1 tentativa + 1 retry
        try:
            bruto = chamar_modelo(montar_mensagens(contexto, alvo, erro))
        except Exception as e:
            raise ModeloIndisponivel(str(e)) from e
        try:
            return validar_lote(alvo, TextReport.model_validate_json(remover_cercas(bruto))), []
        except LoteInvalido as e:
            erro = str(e)[:500]
            if len(e.faltando) < len(melhor[1]):
                melhor = e.parcial, e.faltando
        except ValidationError as e:
            erro = str(e)[:500]
        logger.warning("Agente de Texto: resposta rejeitada: %s", erro)
    return melhor


def texto_node(state: PipelineState) -> dict:
    if not state.segments:
        return {"text_report": None}

    statements, markers, sem_classificacao, avisos = [], [], [], []
    lotes = dividir_em_lotes(state.segments)
    for i, (contexto, alvo) in enumerate(lotes):
        try:
            parcial, faltando = analisar_lote(contexto, alvo)
        except ModeloIndisponivel as e:
            # Servidor fora: não adianta tentar os lotes seguintes (cada um esperaria o timeout)
            logger.warning("Agente de Texto: modelo indisponível: %s", e)
            avisos.append(WARN_MODELO_INDISPONIVEL)
            sem_classificacao += [s.id for _, restante in lotes[i:] for s in restante]
            break
        statements += parcial.statements
        markers += parcial.markers
        sem_classificacao += faltando

    if not statements:
        return {"text_report": None, "warnings": avisos or [WARN_SAIDA_INVALIDA]}
    if sem_classificacao:
        avisos.append(aviso_frases_sem_classificacao(sem_classificacao))
    resultado = {"text_report": TextReport(statements=statements, markers=markers)}
    if avisos:
        resultado["warnings"] = avisos
    return resultado
