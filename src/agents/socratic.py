"""Agente Socrático (R4): gera de 2 a 3 perguntas reflexivas sobre o argumento da notícia.

Entrada: um resumo da notícia (título e primeiras frases), validado contra state.clean_text. Roda em paralelo com o Agente de Texto, logo depois do Ingestor. Saída: {"socratic_questions": list[str] | None, "warnings"?: [...]}.
Manual: §4.4 (especificação), §4.7 (rejeição de indutivas, degradação graciosa).
"""
import json
import logging
import re
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field, ValidationError

from src.agents.ingestor import TITULO_TEXTO_COLADO
from src.guardrails.ancoragem import termos_fora_do_contexto
from src.services.llm import llm_socratico
from src.state import PipelineState, Segment

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

WARN_SAIDA_INVALIDA = "socrático: saída inválida após 1 retry"
WARN_MODELO_INDISPONIVEL = "socrático: falha ao chamar o modelo (o servidor de LLM está rodando?)"

LIMITE_PALAVRAS_SOCRATICO = 400

# Padrões compilados para validação rápida e limpa
RE_INDUTIVO = re.compile(
    r"\b(você\s+não\s+acha|não\s+acha\s+que|"
    r"não\s+é\s+(?:verdade|fato|óbvio|claro|evidente|suspeito)|"
    r"não\s+seria\s+(?:suspeito|melhor|óbvio|evidente)|"
    r"será\s+que\s+não|você\s+concorda|concorda\s+que)\b",
    re.IGNORECASE,
)

RE_VEREDITO = re.compile(
    r"\b(fake\s*news|é\s+falso|é\s+verdadeiro|é\s+mentira)\b",
    re.IGNORECASE,
)


class SocraticReport(BaseModel):
    socratic_questions: List[str] = Field(
        description="Lista contendo de 2 a 3 perguntas socráticas reflexivas."
    )


class PerguntaInvalida(ValueError):
    """Pergunta socrática inválida (indutiva, com veredito proibido ou fora das regras)."""


class SaidaInvalida(RuntimeError):
    """A resposta continuou inválida após 1 retry."""


class ModeloIndisponivel(RuntimeError):
    """Falha de conexão com o modelo de linguagem."""


def carregar_prompt_sistema() -> str:
    return (PROMPTS_DIR / "socratico_sistema.md").read_text(encoding="utf-8")


def carregar_exemplos() -> list[dict]:
    caminho = PROMPTS_DIR / "socratico_exemplos.json"
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else []


def validar_perguntas(perguntas: list[str], clean_text: str) -> list[str]:
    """Valida quantidade e qualidade reflexiva das perguntas geradas.

    Ordem: limpar, descartar a pergunta com nome, número ou doença que a notícia não traz (G4, com aviso
    no log), exigir no mínimo 2, cortar em 3 e aplicar as regras de tamanho, indução e veredito.
    """
    if not isinstance(perguntas, list):
        raise PerguntaInvalida("A saída deve ser uma lista de perguntas.")

    limpas = [p.strip() for p in perguntas if isinstance(p, str) and p.strip()]

    mantidas: list[str] = []
    descartadas: list[tuple[str, str]] = []  # (pergunta, primeiro termo de fora)
    for p in limpas:
        fora = termos_fora_do_contexto(p, clean_text)
        if fora:
            logger.warning("Agente Socrático: pergunta descartada, menciona '%s' (fora da notícia): %s", fora[0], p)
            descartadas.append((p, fora[0]))
        else:
            mantidas.append(p)

    if len(mantidas) < 2:
        if descartadas:
            pergunta, termo = descartadas[0]
            raise PerguntaInvalida(f"Pergunta menciona '{termo}', que não aparece na notícia: '{pergunta}'")
        raise PerguntaInvalida(f"Esperado no mínimo 2 perguntas, obtido {len(mantidas)}")

    mantidas = mantidas[:3]  # O contrato aceita no máximo 3 perguntas
    for p in mantidas:
        if len(p) < 10:
            raise PerguntaInvalida(f"Pergunta excessivamente curta: '{p}'")
        if RE_INDUTIVO.search(p):
            raise PerguntaInvalida(f"Pergunta indutiva detectada: '{p}'")
        if RE_VEREDITO.search(p):
            raise PerguntaInvalida(f"Pergunta contém veredito proibido: '{p}'")

    return mantidas


def resumo_para_socratico(state: PipelineState) -> str:
    """Resume a notícia para o modelo: título e as frases em ordem, em até 400 palavras.

    O título entra numa linha própria, exceto o título padrão de texto colado. Depois vêm as frases, na
    ordem do texto, unidas por espaço. O corte é em fim de frase e o título conta no limite. O Socrático
    roda em paralelo com o Agente de Texto, então não usa a classificação das frases.
    """
    escolhidas = state.segments or ([Segment(id="s01", text=state.clean_text.strip())] if state.clean_text.strip() else [])

    titulo = (state.title or "").strip()
    if titulo == TITULO_TEXTO_COLADO:
        titulo = ""

    usadas = len(titulo.split())
    textos: list[str] = []
    for frase in escolhidas:
        palavras = frase.text.split()
        if usadas + len(palavras) > LIMITE_PALAVRAS_SOCRATICO:
            if not textos:  # frase única maior que o limite: corta por palavras
                textos.append(" ".join(palavras[: max(LIMITE_PALAVRAS_SOCRATICO - usadas, 0)]))
            break
        textos.append(frase.text)
        usadas += len(palavras)

    corpo = " ".join(t for t in textos if t)
    return f"{titulo}\n{corpo}" if titulo and corpo else (titulo or corpo)


def montar_mensagens(clean_text: str, erro_anterior: str | None = None) -> list[tuple[str, str]]:
    mensagens = [("system", carregar_prompt_sistema())]
    for ex in carregar_exemplos():
        mensagens.append(("user", f"<noticia>\n{ex['entrada']}\n</noticia>"))
        mensagens.append(("assistant", json.dumps(ex["saida"], ensure_ascii=False)))

    usuario = f"<noticia>\n{clean_text}\n</noticia>"
    if erro_anterior:
        usuario += (
            f"\n\nSua resposta anterior foi rejeitada: {erro_anterior}\n"
            "Responda estritamente com o objeto JSON contendo de 2 a 3 perguntas NÃO indutivas."
        )
    mensagens.append(("user", usuario))
    return mensagens


def remover_cercas(bruto: str) -> str:
    texto = bruto.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1] if "\n" in texto else ""
        texto = texto.rsplit("```", 1)[0]
    return texto.strip()


def chamar_modelo(mensagens: list[tuple[str, str]]) -> str:
    """Único ponto de chamada ao LLM (facilmente mockável em testes)."""
    formato = {
        "type": "json_schema",
        "json_schema": {"name": "socratic_report", "strict": True, "schema": SocraticReport.model_json_schema()},
    }
    try:
        return llm_socratico.bind(response_format=formato).invoke(mensagens).content
    except Exception:
        return llm_socratico.invoke(mensagens).content


def extrair_e_validar(bruto: str, clean_text: str) -> list[str]:
    """Decodifica e valida o JSON, tolerando variações de chave ('perguntas' ou 'socratic_questions').

    `clean_text` é a notícia contra a qual cada pergunta é checada (G4)."""
    dados = json.loads(remover_cercas(bruto))
    if not isinstance(dados, dict):
        raise PerguntaInvalida("A saída não é um objeto JSON.")

    if "perguntas" in dados and "socratic_questions" not in dados:
        dados["socratic_questions"] = dados["perguntas"]

    relatorio = SocraticReport.model_validate(dados)
    return validar_perguntas(relatorio.socratic_questions, clean_text)


def analisar_texto(entrada: str, contexto: str) -> list[str]:
    """Pede as perguntas ao modelo (1 tentativa + 1 retry).

    `entrada` é o que o modelo lê (o resumo); `contexto` é a notícia inteira, contra a qual o G4 valida."""
    erro = None
    for _ in range(2):  # 1 tentativa inicial + 1 retry
        try:
            bruto = chamar_modelo(montar_mensagens(entrada, erro))
        except Exception as e:
            raise ModeloIndisponivel(str(e)) from e

        try:
            return extrair_e_validar(bruto, contexto)
        except (ValidationError, PerguntaInvalida, json.JSONDecodeError) as e:
            erro = str(e)[:500]
            logger.warning("Agente Socrático: resposta rejeitada: %s", erro)

    raise SaidaInvalida(erro)


def socratic_node(state: PipelineState) -> dict:
    if not state.clean_text or not state.clean_text.strip():
        return {"socratic_questions": []}

    try:
        titulo = (state.title or "").strip()
        # O modelo lê o título no resumo, então o G4 também o aceita como contexto.
        contexto = state.clean_text if not titulo or titulo == TITULO_TEXTO_COLADO else f"{titulo}\n{state.clean_text}"
        perguntas = analisar_texto(resumo_para_socratico(state), contexto)
        return {"socratic_questions": perguntas}
    except SaidaInvalida:
        return {"socratic_questions": None, "warnings": [WARN_SAIDA_INVALIDA]}
    except ModeloIndisponivel as e:
        logger.warning("Agente Socrático: modelo indisponível: %s", e)
        return {"socratic_questions": None, "warnings": [WARN_MODELO_INDISPONIVEL]}


# Aliases para conformidade com o grafo e convenções do projeto
socratico_node = socratic_node
run = socratic_node
