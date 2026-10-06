"""Agente de Texto (R3): mostra como o texto argumenta, sem julgar se é verdadeiro.

Entrada: state.segments. Saída: {"text_report": TextReport | None, "warnings"?: [...]}.
Manual: §4.3 (especificação), §4.7 (falha após 1 retry), §3.5 (notícia é dado, não instrução).
"""
import json
import logging
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


class LoteInvalido(ValueError):
    """O JSON é válido, mas não classifica cada frase do lote exatamente uma vez."""


class SaidaInvalida(RuntimeError):
    """O lote continuou inválido depois do retry."""


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
    """Checagem determinística (sem LLM) da resposta de um lote."""
    textos = {s.id: s.text for s in alvo}
    ordem = {s.id: i for i, s in enumerate(alvo)}

    statements = [st for st in relatorio.statements if st.segment_id in textos]
    classificados = [st.segment_id for st in statements]
    faltando = [sid for sid in textos if sid not in classificados]
    repetidos = sorted({sid for sid in classificados if classificados.count(sid) > 1})
    if faltando or repetidos:
        raise LoteInvalido(f"frases sem classificação: {faltando}; classificadas mais de uma vez: {repetidos}")
    statements.sort(key=lambda st: ordem[st.segment_id])

    markers = [
        m for m in relatorio.markers
        if m.segment_id in textos and m.excerpt.strip() and m.excerpt in textos[m.segment_id]
    ]
    return TextReport(statements=statements, markers=markers)


def analisar_lote(contexto: list[Segment], alvo: list[Segment]) -> TextReport:
    erro = None
    for _ in range(2):  # 1 tentativa + 1 retry
        try:
            bruto = chamar_modelo(montar_mensagens(contexto, alvo, erro))
        except Exception as e:
            raise ModeloIndisponivel(str(e)) from e
        try:
            return validar_lote(alvo, TextReport.model_validate_json(remover_cercas(bruto)))
        except (ValidationError, LoteInvalido) as e:
            erro = str(e)[:500]
            logger.warning("Agente de Texto: resposta rejeitada: %s", erro)
    raise SaidaInvalida(erro)


def texto_node(state: PipelineState) -> dict:
    if not state.segments:
        return {"text_report": None}

<<<<<<< Updated upstream
    statements, markers = [], []
    try:
        for contexto, alvo in dividir_em_lotes(state.segments):
            parcial = analisar_lote(contexto, alvo)
            statements += parcial.statements
            markers += parcial.markers
    except SaidaInvalida:
        return {"text_report": None, "warnings": [WARN_SAIDA_INVALIDA]}
    except ModeloIndisponivel as e:
        logger.warning("Agente de Texto: modelo indisponível: %s", e)
        return {"text_report": None, "warnings": [WARN_MODELO_INDISPONIVEL]}
=======
    import concurrent.futures

    statements, markers, sem_classificacao, avisos = [], [], [], []
    lotes = dividir_em_lotes(state.segments)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futuros = []
        for contexto, alvo in lotes:
            futuros.append(executor.submit(analisar_lote, contexto, alvo))
            
        modelo_caiu = False
        for i, (futuro, (contexto, alvo)) in enumerate(zip(futuros, lotes)):
            if modelo_caiu:
                sem_classificacao += alvo
                continue

            try:
                parcial, faltando = futuro.result()
                statements += parcial.statements
                markers += parcial.markers
                sem_classificacao += [s for s in alvo if s.id in faltando]
            except ModeloIndisponivel as e:
                logger.warning("Agente de Texto: modelo indisponível: %s", e)
                avisos.append(WARN_MODELO_INDISPONIVEL)
                sem_classificacao += alvo
                modelo_caiu = True
                # Cancela os próximos que ainda não começaram
                for f in futuros[i+1:]:
                    f.cancel()
>>>>>>> Stashed changes

    return {"text_report": TextReport(statements=statements, markers=markers)}
