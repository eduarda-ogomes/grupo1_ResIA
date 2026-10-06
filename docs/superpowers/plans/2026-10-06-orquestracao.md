# Orquestração dos agentes reais — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o grafo LangGraph roda os cinco agentes reais (sem stubs), com timeout por nó e degradação graciosa, e o dossiê sempre chega ao usuário, mesmo quando um ramo trava ou quebra.

**Architecture:** `src/graph.py` passa a montar o grafo numa função `construir_grafo(...)`. Cada nó real é envolvido por `proteger(...)` (`src/protecao.py`), que roda o agente numa thread com timeout e converte timeout ou exceção em aviso em `warnings` mais a saída de falha do nó. Os testes nunca falam com modelos: um `tests/conftest.py` na raiz bloqueia os quatro pontos de acesso (LM Studio de Texto, Socrático e Sintetizador; busca do Evidências), e `tests/modelos_falsos.py` oferece respostas falsas para os testes de ponta a ponta. O Sintetizador recebe só uma correção mínima de nomes de campo para funcionar com o `state.py` atual.

**Tech Stack:** Python 3.10 (CI) / 3.14 (venv local), LangGraph 1.2, Pydantic 2, langchain-openai (cliente do LM Studio), pytest, Streamlit `AppTest`.

**Spec:** não há spec própria. O plano implementa o Manual (`docs/Manual do Sistema Multiagente — Avaliação de Confiabilidade da Informação.md`): §3.1 (grafo), §3.4 (fluxo de controle e falhas), §4.7 (linha "Sistema: timeout no Socrático" e fixture `tests/fixtures/bordas/sistema_timeout_ramo.json`), §9.3 R1 e §9.4 (regras de integração), §10.2/§10.3 R1 (timeouts, `warnings`, integração completa).

## Estado de partida (develop em 06/10/2026, commit `3966628`)

- `src/graph.py` já tem a topologia do §3.1, mas importa `src.stubs.evidence_stub` e `src.stubs.socratic_stub`. Os agentes reais (`src/agents/evidence.py`, `src/agents/socratic.py`) já estão prontos e testados.
- Nenhum nó tem timeout. `llm` (Sintetizador) e `llm_socratico` em `src/services/llm.py` não têm timeout, e o cliente faz 2 retries por padrão.
- `src/agents/synthesizer.py` (PR #11) lê campos que não existem no `state.py` (`state.evidences`, `ev.url`, `segment.statement_type`, `state.text_analysis`, `e.source`, `e.quote`, `m.description`). Por isso sempre cai no `except` e devolve "Não foi possível sintetizar…". O teste de contrato passa mesmo assim, porque só confere se volta uma string.
- `tests/unit/conftest.py` só bloqueia o LLM do Agente de Texto. `tests/unit/test_app.py` e `tests/unit/test_state.py` rodam o grafo real.

## Global Constraints

- O CI roda **Python 3.10**. No 3.10, `concurrent.futures.TimeoutError` **não** é o `TimeoutError` embutido (eles só se unificaram no 3.11): importe `from concurrent.futures import TimeoutError as FuturesTimeout`.
- Contrato de agente (§9.4, regra 1): `run(state: PipelineState) -> dict` devolve só os próprios campos (mais `warnings`), e os agentes não importam LangGraph. A proteção fica no orquestrador, não nos agentes.
- O `PipelineState` (`src/state.py`) **não muda**. O estado de entrada é sempre criado com `initial_state(...)`.
- Nenhum teste em `tests/unit/` ou `tests/contract/` chama o LM Studio, o ChromaDB, o BGE-M3 ou o NLI. Testes com modelos reais ficam em `tests/integration/` (fora do CI).
- `requirements-ci.txt` continua sem torch, chromadb e transformers.
- Os avisos seguem o formato `"<agente>: <motivo>"`. Para timeout, o texto é exatamente o da fixture: `"socratico: timeout"`, `"evidencias: timeout"`, `"texto: timeout"`, `"sintetizador: timeout"`, `"ingestor: timeout"`.
- O dossiê nunca é `None` (Manual §4.5.1, linha "Contrato").
- Os nomes dos nós não mudam: `ingestor`, `agente_evidencias`, `agente_texto`, `agente_socratico`, `sintetizador`.
- A branch é `feat/orquestracao`, criada a partir da `origin/develop`. O PR vai para a `develop`.
- Todo commit termina com a linha `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

Os cinco casos mais prováveis de aparecer na demo, cada um com o teste que o fixa:

1. **Primeira execução do Agente de Evidências.** Carregar o BGE-M3 e o mDeBERTa (e baixá-los, na primeira vez) pode passar do timeout do ramo. O esperado é o aviso `evidencias: timeout`, com o dossiê saindo assim mesmo. Teste: `test_ramo_que_estoura_o_tempo_vira_aviso_e_o_dossie_sai[evidencias]` (Task 4).
2. **Exceção não prevista dentro de um agente** (um bug, não uma falha do modelo). O esperado é um aviso com o tipo e a mensagem do erro, sem derrubar o grafo. Teste: `test_excecao_nao_prevista_num_agente_vira_aviso` (Task 4) e `test_excecao_vira_aviso` (Task 3).
3. **URL atrás de paywall passando pelo grafo inteiro.** O esperado é só o aviso do Ingestor, com evidências e perguntas vazias e o dossiê entregue. Teste: `test_url_com_paywall_passa_pelo_grafo_inteiro` (Task 4).
4. **Sintetizador travado ou fora do ar.** O dossiê nunca sai `None`: vem o texto de indisponibilidade mais o aviso. Teste: `test_sintetizador_travado_ainda_entrega_um_dossie` (Task 4).
5. **Variável de ambiente de timeout inválida** (`"abc"`, `"0"`, `"inf"`). O esperado é usar o valor padrão, sem quebrar a importação do grafo. Teste: `test_timeout_invalido_usa_o_padrao` (Task 3).

## Fora deste plano

- A reescrita do Sintetizador conforme a spec (`docs/superpowers/specs/2026-10-01-agente-sintetizador-design.md`, §4.5.1 do Manual: abordagem híbrida, `src/guardrails/`). Aqui só os nomes de campo são corrigidos. A deduplicação por URL (e não por `(segment_id, source_url)`) e o resultado ignorado de `verificar_citacoes` continuam como estão.
- O prefixo dos avisos do Socrático. O agente usa `"socrático: ..."`, com acento, e a fixture de timeout usa `"socratico: timeout"`, sem. Fica registrado, sem mudança no código do agente.
- Tracing (Phoenix/LangSmith) e medição formal de p50/p95. O teste de integração só imprime o tempo de cada nó.
- Interromper de fato uma thread que estourou o timeout. O Python não permite: a chamada termina em segundo plano, limitada pelo timeout de 120 s do cliente de LLM.

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
| --- | --- | --- |
| `tests/conftest.py` | Criar | Bloqueia os quatro modelos em todos os testes |
| `tests/integration/conftest.py` | Criar | Desliga esse bloqueio nos testes de integração |
| `tests/unit/conftest.py` | Remover | Substituído por `tests/conftest.py` |
| `tests/unit/test_isolamento.py` | Criar | Prova que o bloqueio vale |
| `tests/modelos_falsos.py` | Criar (Task 2), estender (Task 4) | Respostas falsas de Sintetizador, Texto, Socrático e busca |
| `src/agents/synthesizer.py` | Modificar | Correção mínima dos nomes de campo, constante `DOSSIE_FALHA` e aviso próprio |
| `tests/unit/test_synthesizer.py` | Criar | Sintetizador com o LLM falso |
| `tests/contract/test_synthesizer_contract.py` | Modificar | Contrato com `PipelineState` de verdade |
| `src/services/llm.py` | Modificar | Timeout de 120 s e sem retry em todos os clientes |
| `tests/unit/test_services_llm.py` | Criar | Configuração dos clientes |
| `src/protecao.py` | Criar | `proteger`, `ler_timeout`, timeouts padrão e saídas de falha |
| `tests/unit/test_protecao.py` | Criar | Timeout, exceção e variável de ambiente |
| `src/graph.py` | Modificar | `construir_grafo(...)` com os agentes reais protegidos |
| `tests/unit/test_graph.py` | Criar | Topologia, falhas por ramo, paywall e caso do mamão de ponta a ponta |
| `tests/unit/test_state.py` | Modificar | Tira os dois testes de grafo, que vão para `test_graph.py` |
| `app/app.py` | Modificar | Texto do LM Studio no lugar do Ollama |
| `tests/unit/test_app.py` | Modificar | Avisos de todos os ramos e o texto novo |
| `tests/integration/test_grafo_lmstudio.py` | Criar | Grafo inteiro com os modelos reais, com o tempo de cada nó |
| `README.md`, Manual §3.4 | Modificar | Como os timeouts funcionam e como ajustá-los |

---

### Task 1: Os testes nunca chamam um modelo

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/integration/conftest.py`
- Create: `tests/unit/test_isolamento.py`
- Delete: `tests/unit/conftest.py`

**Interfaces:**
- Consumes: `src.agents.text_analysis.chamar_modelo(mensagens) -> str`, `src.agents.socratic.chamar_modelo(mensagens) -> str`, `src.agents.synthesizer.llm` (Runnable usado em `prompt | llm`), `src.agents.evidence.search(textos, k=...) -> list[list[Hit]]`.
- Produces: fixture autouse `sem_modelos` em `tests/conftest.py`. Com ela, as quatro funções levantam `ConnectionError("modelos desligados nos testes (tests/conftest.py)")`. Os testes que precisam de resposta fazem `monkeypatch.setattr` por cima. Em `tests/integration/`, a fixture de mesmo nome não faz nada.

- [ ] **Step 0: Preparar o ambiente**

```bash
cd /Users/aluno2/Documents/CBL-01
git switch feat/orquestracao          # já criada a partir da origin/develop
source venv/bin/activate
pytest tests/contract tests/unit -q
```

Esperado: tudo verde (linha de base). Se algo falhar aqui, pare e reporte: o problema é anterior a este plano.

- [ ] **Step 1: Escrever o teste que falha**

`tests/unit/test_isolamento.py`:

```python
"""O tests/conftest.py desliga todos os modelos: nenhum teste unitário fala com o LM Studio ou com o índice."""
import pytest

from src.agents import evidence, socratic, synthesizer, text_analysis


def test_agente_de_texto_nao_alcanca_o_modelo():
    with pytest.raises(ConnectionError, match="modelos desligados"):
        text_analysis.chamar_modelo([("user", "oi")])


def test_agente_socratico_nao_alcanca_o_modelo():
    with pytest.raises(ConnectionError, match="modelos desligados"):
        socratic.chamar_modelo([("user", "oi")])


def test_sintetizador_nao_alcanca_o_modelo():
    with pytest.raises(ConnectionError, match="modelos desligados"):
        synthesizer.llm.invoke("oi")


def test_evidencias_nao_alcanca_o_indice():
    with pytest.raises(ConnectionError, match="modelos desligados"):
        evidence.search(["uma frase"], k=1)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/unit/test_isolamento.py -v -k "not evidencias"`

O `-k` evita carregar o BGE-M3 neste passo. Esperado: FAIL nos três testes. O de texto falha porque a mensagem do conftest antigo é outra; os de socrático e sintetizador falham porque tentam o LM Studio de verdade, ou com erro de conexão (que não é `ConnectionError`) ou com uma resposta.

- [ ] **Step 3: Implementar o bloqueio**

`tests/conftest.py`:

```python
"""Nenhum teste de tests/unit ou tests/contract fala com um modelo de verdade.

Bloqueia os quatro pontos de acesso: o LM Studio (Agentes de Texto, Socrático e
Sintetizador) e a busca no índice do Agente de Evidências, que carregaria o
ChromaDB e o BGE-M3. Quem precisa de uma resposta substitui a função no próprio
teste (ver tests/modelos_falsos.py). O tests/integration/conftest.py desliga este bloqueio.
"""
import pytest
from langchain_core.runnables import RunnableLambda

from src.agents import evidence, socratic, synthesizer, text_analysis

MOTIVO = "modelos desligados nos testes (tests/conftest.py)"


def _recusa(*args, **kwargs):
    raise ConnectionError(MOTIVO)


@pytest.fixture(autouse=True)
def sem_modelos(monkeypatch):
    monkeypatch.setattr(text_analysis, "chamar_modelo", _recusa)
    monkeypatch.setattr(socratic, "chamar_modelo", _recusa)
    monkeypatch.setattr(synthesizer, "llm", RunnableLambda(lambda entrada: _recusa()))
    monkeypatch.setattr(evidence, "search", _recusa)
```

`tests/integration/conftest.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def sem_modelos():
    """Os testes de integração usam os modelos reais: anula o bloqueio de tests/conftest.py."""
    yield
```

Remover o conftest antigo:

```bash
git rm tests/unit/conftest.py
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/unit/test_isolamento.py -v && pytest tests/contract tests/unit -q`

Esperado: os 4 testes de isolamento passam e a suíte inteira continua verde. `test_app_mostra_aviso_quando_o_agente_de_texto_falha` passa porque o aviso vem de `text_analysis.WARN_MODELO_INDISPONIVEL`, não da mensagem do conftest.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/integration/conftest.py tests/unit/test_isolamento.py
git commit -m "test: Bloqueia os quatro modelos em todos os testes, não só o do Agente de Texto" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Correção mínima do Sintetizador

**Files:**
- Create: `tests/modelos_falsos.py`
- Create: `tests/unit/test_synthesizer.py`
- Modify: `src/agents/synthesizer.py` (`preparar_dados_contexto`, `run` e a nova constante `DOSSIE_FALHA`)
- Modify: `tests/contract/test_synthesizer_contract.py`

**Interfaces:**
- Consumes: `PipelineState` com `evidence: list[Evidence] | None` (campos `segment_id`, `stance`, `excerpt`, `source_url`, `source_name`, `agency_verdict`), `text_report: TextReport | None` (`statements[].segment_id/kind`, `markers[].type/excerpt/explanation`), `socratic_questions: list[str] | None`, `clean_text: str`.
- Produces:
  - `synthesizer.run(state) -> {"dossier": str}`. Em caso de erro, `{"dossier": DOSSIE_FALHA, "warnings": ["sintetizador: <Tipo>: <mensagem>"]}`. O alias `synthesizer_node = run` continua.
  - `synthesizer.DOSSIE_FALHA: str`.
  - `tests/modelos_falsos.py`: `RESPOSTA_SINTETIZADOR: str`, `carregar_mamao(nome: str) -> dict` e `SintetizadorFalso(*respostas)`, com `.prompts: list[str]` e `.instalar(monkeypatch) -> SintetizadorFalso`. Uma resposta pode ser `Exception`, e nesse caso é levantada. A última resposta da lista se repete.

- [ ] **Step 1: Escrever os dublês e os testes que falham**

`tests/modelos_falsos.py`:

```python
"""Modelos falsos para rodar os agentes e o grafo sem LM Studio, índice nem NLI."""
import json
from pathlib import Path

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.agents import synthesizer

FIXTURES_MAMAO = Path(__file__).resolve().parent / "fixtures" / "caso_mamao_dengue"

RESPOSTA_SINTETIZADOR = "## O que as checagens dizem\n- Dossiê escrito pelo modelo falso."


def carregar_mamao(nome: str) -> dict:
    return json.loads((FIXTURES_MAMAO / nome).read_text(encoding="utf-8"))


class SintetizadorFalso:
    """Substitui synthesizer.llm: devolve as respostas na ordem (a última se repete)
    e guarda o texto de cada prompt recebido. Uma resposta Exception é levantada."""

    def __init__(self, *respostas):
        self.respostas = list(respostas) or [RESPOSTA_SINTETIZADOR]
        self.prompts: list[str] = []

    def __call__(self, valor_prompt):
        self.prompts.append(valor_prompt.to_string())
        resposta = self.respostas[min(len(self.prompts), len(self.respostas)) - 1]
        if isinstance(resposta, BaseException):
            raise resposta
        return AIMessage(content=resposta)

    def instalar(self, monkeypatch) -> "SintetizadorFalso":
        monkeypatch.setattr(synthesizer, "llm", RunnableLambda(lambda valor: self(valor)))
        return self
```

`tests/unit/test_synthesizer.py`:

```python
"""Sintetizador com o LLM falso: lê os campos do state.py da Seção 3.3 e nunca devolve dossiê vazio."""
from src.agents import synthesizer
from src.state import PipelineState
from tests import modelos_falsos as falsos


def estado_mamao(**sobrescritas) -> PipelineState:
    dados = falsos.carregar_mamao("05_sintetizador_entrada.json")
    dados.update(sobrescritas)
    return PipelineState(**dados)


def test_dossie_vem_do_modelo_no_caso_do_mamao(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)

    assert synthesizer.run(estado_mamao()) == {"dossier": falsos.RESPOSTA_SINTETIZADOR}


def test_prompt_leva_evidencias_marcadores_perguntas_e_o_texto_limpo(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)
    state = estado_mamao()

    synthesizer.run(state)

    prompt = modelo.prompts[0]
    assert "Agência Lupa" in prompt and "Aos Fatos" in prompt
    assert "Não existe um tratamento específico para a dengue" in prompt
    assert "Cita uma autoridade sem nome, formação ou fonte verificável." in prompt
    assert state.socratic_questions[0] in prompt
    assert state.clean_text in prompt


def test_evidencia_de_frase_de_valor_nao_vai_para_o_prompt(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)
    base = estado_mamao()
    opiniao = {
        "segment_id": "s05",  # marcada como "valor" pelo Agente de Texto
        "stance": "contradiz",
        "excerpt": "Trecho de checagem sobre a natureza.",
        "source_url": "https://exemplo.org/checagem-natureza",
        "source_name": "Agência Exemplo",
        "agency_verdict": "Falso",
    }

    synthesizer.run(estado_mamao(evidence=[*[e.model_dump() for e in base.evidence], opiniao]))

    assert "Trecho de checagem sobre a natureza." not in modelo.prompts[0]
    assert "Agência Lupa" in modelo.prompts[0]


def test_sem_text_report_mostra_todas_as_evidencias(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.run(estado_mamao(text_report=None))

    assert resultado == {"dossier": falsos.RESPOSTA_SINTETIZADOR}
    assert "Nenhum marcador retórico relevante detectado." in modelo.prompts[0]
    assert "Agência Lupa" in modelo.prompts[0]


def test_sem_evidencias_e_sem_perguntas(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.run(estado_mamao(evidence=None, socratic_questions=None))

    assert resultado == {"dossier": falsos.RESPOSTA_SINTETIZADOR}
    assert "Nenhuma evidência factual encontrada." in modelo.prompts[0]
    assert "Nenhuma pergunta socrática gerada." in modelo.prompts[0]


def test_entrada_por_url_manda_o_texto_extraido_e_nao_a_url(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    synthesizer.run(estado_mamao(raw_input="https://exemplo.org/materia", clean_text="Texto extraído da página."))

    assert "Texto extraído da página." in modelo.prompts[0]
    assert "https://exemplo.org/materia" not in modelo.prompts[0]


def test_termo_proibido_gera_uma_nova_tentativa(monkeypatch):
    modelo = falsos.SintetizadorFalso("Isto é fake news.", falsos.RESPOSTA_SINTETIZADOR).instalar(monkeypatch)

    resultado = synthesizer.run(estado_mamao())

    assert resultado == {"dossier": falsos.RESPOSTA_SINTETIZADOR}
    assert len(modelo.prompts) == 2
    assert "NÃO USE ESSES TERMOS" in modelo.prompts[1]


def test_modelo_fora_do_ar_devolve_dossie_de_falha_e_aviso(monkeypatch):
    falsos.SintetizadorFalso(ConnectionError("LM Studio fora do ar")).instalar(monkeypatch)

    resultado = synthesizer.run(estado_mamao())

    assert resultado == {
        "dossier": synthesizer.DOSSIE_FALHA,
        "warnings": ["sintetizador: ConnectionError: LM Studio fora do ar"],
    }
```

`tests/contract/test_synthesizer_contract.py` (substituir o arquivo inteiro):

```python
from src.agents.synthesizer import run
from src.state import PipelineState, initial_state


def test_synthesizer_contract():
    # O tests/conftest.py desliga o modelo: o contrato vale também no caminho de falha
    state = PipelineState(**initial_state("O suco de limão cura tudo"))

    resultado = run(state)

    assert isinstance(resultado, dict), "O agente deve retornar um dicionário"
    assert isinstance(resultado["dossier"], str) and resultado["dossier"], "O dossier deve ser uma string não vazia"
    assert set(resultado) <= {"dossier", "warnings"}, "O Sintetizador só escreve os próprios campos"
    PipelineState(**{**state.model_dump(), **resultado})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/unit/test_synthesizer.py tests/contract/test_synthesizer_contract.py -v`

Esperado: FAIL nos 8 testes de `test_synthesizer.py`. `state.evidences` levanta `AttributeError` antes de chamar o modelo, então o dossiê vem como "Não foi possível sintetizar…", `modelo.prompts` fica vazio (`IndexError`) e `synthesizer.DOSSIE_FALHA` ainda não existe. O teste de contrato passa: o caminho de falha já devolvia string.

- [ ] **Step 3: Implementar a correção mínima**

Em `src/agents/synthesizer.py`, mudar só o que segue e manter o resto como está (`TERMOS_PROIBIDOS`, `SYSTEM_PROMPT`, `USER_TEMPLATE`, `verificar_filtro_veredito`, `verificar_citacoes` e a lógica de retry).

Logo depois de `logger = logging.getLogger(__name__)`:

```python
DOSSIE_FALHA = "Não foi possível sintetizar a análise devido a um erro interno."
```

Substituir `preparar_dados_contexto` inteira:

```python
def preparar_dados_contexto(state: PipelineState) -> dict:
    urls_conhecidas = set()
    evidencias_filtradas = []
    tipo_por_frase = (
        {st.segment_id: st.kind for st in state.text_report.statements} if state.text_report else {}
    )

    # Pre-processamento: Deduplicação e filtragem de 'valor'
    # Sem text_report não há como saber o que é opinião: a evidência fica (Manual §4.7)
    for ev in state.evidence or []:
        if ev.source_url in urls_conhecidas:
            continue
        if tipo_por_frase.get(ev.segment_id) == "valor":
            continue

        evidencias_filtradas.append(ev)
        urls_conhecidas.add(ev.source_url)

    return {
        "urls": urls_conhecidas,
        "evidencias": evidencias_filtradas
    }
```

Em `run`, trocar os dois blocos de formatação:

```python
        # Formatando bloco de evidências
        if dados["evidencias"]:
            bloco_evidencias = "\n".join([f"- Alegação [{e.segment_id}]: {e.stance} pela {e.source_name}. Trecho: {e.excerpt}" for e in dados["evidencias"]])
        else:
            bloco_evidencias = "Nenhuma evidência factual encontrada."

        # Formatando bloco de retórica
        markers = state.text_report.markers if state.text_report else []
        if markers:
            bloco_retorica = "\n".join([f"- {m.type}: {m.explanation}" for m in markers])
        else:
            bloco_retorica = "Nenhum marcador retórico relevante detectado."
```

Nas **duas** chamadas `.invoke({...})` de `run`, trocar `"texto_original": state.raw_input,` por:

```python
            "texto_original": state.clean_text or state.raw_input,
```

Substituir o `except` final:

```python
    except Exception as e:
        logger.error(f"Erro no Agente Sintetizador: {e}")
        return {"dossier": DOSSIE_FALHA, "warnings": [f"sintetizador: {type(e).__name__}: {e}"]}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/unit/test_synthesizer.py tests/contract/test_synthesizer_contract.py -v && pytest tests/contract tests/unit -q`

Esperado: os 8 testes do Sintetizador e o de contrato passam. **Atenção:** `tests/unit/test_state.py::test_grafo_roda_ponta_a_ponta_com_texto_livre` e `::test_grafo_segue_quando_o_agente_de_texto_falha` agora falham, porque o Sintetizador passou a gravar o próprio aviso. Isso é esperado: os dois testes saem desse arquivo na Task 4. Marque-os como pulados até lá:

```python
import pytest
# ... em cima de cada um dos dois testes:
@pytest.mark.skip(reason="substituído por tests/unit/test_graph.py na Task 4 do plano de orquestração")
```

Rode de novo: `pytest tests/contract tests/unit -q` → verde, com 2 testes pulados.

- [ ] **Step 5: Commit**

```bash
git add tests/modelos_falsos.py tests/unit/test_synthesizer.py tests/contract/test_synthesizer_contract.py src/agents/synthesizer.py tests/unit/test_state.py
git commit -m "fix: Sintetizador lê os campos do state.py da Seção 3.3 e grava aviso quando falha" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Proteção dos nós (timeout e exceção viram aviso)

**Files:**
- Create: `src/protecao.py`
- Create: `tests/unit/test_protecao.py`
- Modify: `src/services/llm.py` (arquivo inteiro)
- Create: `tests/unit/test_services_llm.py`

**Interfaces:**
- Consumes: nada de tarefas anteriores.
- Produces (`src/protecao.py`):
  - `ler_timeout(variavel: str, padrao: float) -> float`
  - `TIMEOUT_INGESTOR_S: float` (env `GRAFO_TIMEOUT_INGESTOR`, padrão 60), `TIMEOUT_RAMO_S: float` (env `GRAFO_TIMEOUT_RAMO`, padrão 240), `TIMEOUT_SINTETIZADOR_S: float` (env `GRAFO_TIMEOUT_SINTETIZADOR`, padrão 180)
  - `FALHA_INGESTOR: dict` (`clean_text=""`, `title=None`, `published_at=None`, `truncated=False`, `segments=[]`)
  - `DOSSIE_INDISPONIVEL: str`
  - `proteger(nome: str, fn: Callable[[Any], dict], timeout_s: float, em_falha: dict) -> Callable[[Any], dict]`: devolve a saída de `fn(state)`; em timeout ou exceção, devolve `{**deepcopy(em_falha), "warnings": [f"{nome}: timeout"]}` ou `[f"{nome}: {Tipo}: {mensagem}"]`.
- Produces (`src/services/llm.py`): `llm`, `llm_socratico` e `llm_texto`, todos com `request_timeout == 120` e `max_retries == 0`. A temperatura continua 0, 0,7 e 0.

- [ ] **Step 1: Escrever os testes que falham**

`tests/unit/test_protecao.py`:

```python
"""Timeout por nó e degradação graciosa (Manual §3.4 e §4.7, linha "Sistema")."""
import json
import threading
import time
from pathlib import Path

import pytest

from src import protecao

FIXTURE_TIMEOUT = Path(__file__).resolve().parents[1] / "fixtures" / "bordas" / "sistema_timeout_ramo.json"


def test_saida_do_agente_passa_sem_mudanca():
    saida = {"text_report": None, "warnings": ["texto: saída inválida após 1 retry"]}
    no = protecao.proteger("texto", lambda state: saida, 1, {"text_report": None})

    assert no(object()) == saida


def test_timeout_devolve_a_saida_da_fixture_sem_esperar_o_agente():
    liberar = threading.Event()

    def socratico_travado(state):
        liberar.wait(5)
        return {"socratic_questions": ["nunca chega a tempo"]}

    no = protecao.proteger("socratico", socratico_travado, 0.1, {"socratic_questions": None})
    inicio = time.monotonic()
    try:
        saida = no(object())
    finally:
        liberar.set()

    assert time.monotonic() - inicio < 1, "o nó não pode esperar a thread travada"
    assert saida == json.loads(FIXTURE_TIMEOUT.read_text(encoding="utf-8"))["saida_esperada"]


def test_excecao_vira_aviso():
    def quebra(state):
        raise ValueError("índice corrompido")

    no = protecao.proteger("evidencias", quebra, 1, {"evidence": None})

    assert no(object()) == {"evidence": None, "warnings": ["evidencias: ValueError: índice corrompido"]}


def test_saida_de_falha_e_uma_copia_nova_a_cada_chamada():
    def quebra(state):
        raise RuntimeError("x")

    no = protecao.proteger("ingestor", quebra, 1, protecao.FALHA_INGESTOR)
    primeira = no(object())
    primeira["segments"].append("lixo")

    assert no(object())["segments"] == []
    assert protecao.FALHA_INGESTOR["segments"] == []


def test_timeout_lido_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("GRAFO_TIMEOUT_RAMO", "12.5")
    assert protecao.ler_timeout("GRAFO_TIMEOUT_RAMO", 240) == 12.5

    monkeypatch.delenv("GRAFO_TIMEOUT_RAMO")
    assert protecao.ler_timeout("GRAFO_TIMEOUT_RAMO", 240) == 240


@pytest.mark.parametrize("valor", ["abc", "", "0", "-5", "inf", "nan"])
def test_timeout_invalido_usa_o_padrao(monkeypatch, valor):
    monkeypatch.setenv("GRAFO_TIMEOUT_RAMO", valor)

    assert protecao.ler_timeout("GRAFO_TIMEOUT_RAMO", 240) == 240


def test_timeouts_padrao():
    assert (protecao.TIMEOUT_INGESTOR_S, protecao.TIMEOUT_RAMO_S, protecao.TIMEOUT_SINTETIZADOR_S) == (60, 240, 180)
```

`tests/unit/test_services_llm.py`:

```python
import pytest

from src.services import llm as servicos


@pytest.mark.parametrize("nome", ["llm", "llm_socratico", "llm_texto"])
def test_clientes_tem_timeout_e_nao_repetem_a_chamada(nome):
    # Sem timeout, uma chamada abandonada pelo grafo (src/protecao.py) ocuparia o LM Studio indefinidamente
    cliente = getattr(servicos, nome)

    assert cliente.request_timeout == 120
    assert cliente.max_retries == 0


def test_temperaturas():
    assert (servicos.llm.temperature, servicos.llm_socratico.temperature, servicos.llm_texto.temperature) == (0, 0.7, 0)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/unit/test_protecao.py tests/unit/test_services_llm.py -v`

Esperado: `test_protecao.py` falha na coleta com `ModuleNotFoundError: No module named 'src.protecao'`. Em `test_services_llm.py`, os testes de `llm` e `llm_socratico` falham (`request_timeout` é `None` e `max_retries` é 2), e os de `llm_texto` e de temperatura passam.

- [ ] **Step 3: Implementar**

`src/protecao.py`:

```python
"""Proteção dos nós do grafo: timeout por nó, e exceção vira aviso (Manual §3.4).

Cada agente já trata as próprias falhas e grava o próprio aviso. Esta camada cobre
o que escapa (um modelo travado, um bug), para que o grafo sempre chegue ao
Sintetizador e o dossiê sempre saia.

Limitação: o Python não interrompe uma thread. Quando um nó estoura o tempo, o grafo
segue sem ele, mas a chamada continua em segundo plano até terminar sozinha; o
timeout dos clientes de LLM (src/services/llm.py) limita quanto isso dura.
"""
from __future__ import annotations

import copy
import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout  # no Python 3.10 não é o TimeoutError embutido
from typing import Any, Callable

logger = logging.getLogger(__name__)


def ler_timeout(variavel: str, padrao: float) -> float:
    """Segundos lidos da variável de ambiente; ausente, inválido, infinito ou <= 0 usa o padrão."""
    try:
        valor = float(os.environ[variavel])
    except (KeyError, ValueError):
        return padrao
    return valor if math.isfinite(valor) and valor > 0 else padrao


# Lidos ao importar o grafo: defina as variáveis antes de subir o Streamlit.
TIMEOUT_INGESTOR_S = ler_timeout("GRAFO_TIMEOUT_INGESTOR", 60)
TIMEOUT_RAMO_S = ler_timeout("GRAFO_TIMEOUT_RAMO", 240)
TIMEOUT_SINTETIZADOR_S = ler_timeout("GRAFO_TIMEOUT_SINTETIZADOR", 180)

FALHA_INGESTOR = {"clean_text": "", "title": None, "published_at": None, "truncated": False, "segments": []}
DOSSIE_INDISPONIVEL = "Não foi possível montar o dossiê nesta análise. Os avisos indicam o que falhou."


def proteger(nome: str, fn: Callable[[Any], dict], timeout_s: float, em_falha: dict) -> Callable[[Any], dict]:
    """Envolve `fn(state)`: devolve a saída dela ou, se ela estourar `timeout_s` segundos
    ou levantar exceção, uma cópia de `em_falha` com o aviso "<nome>: <motivo>"."""

    def no(state):
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=nome)
        futuro = executor.submit(fn, state)
        try:
            return futuro.result(timeout=timeout_s)
        except FuturesTimeout:
            logger.warning("%s: estourou o limite de %s s", nome, timeout_s)
            motivo = "timeout"
        except Exception as exc:
            logger.exception("%s falhou", nome)
            motivo = f"{type(exc).__name__}: {exc}"
        finally:
            # wait=False: não espera a thread travada (um `with` esperaria e anularia o timeout)
            executor.shutdown(wait=False, cancel_futures=True)
        return {**copy.deepcopy(em_falha), "warnings": [f"{nome}: {motivo}"]}

    no.__name__ = f"{nome}_protegido"
    return no
```

`src/services/llm.py` (substituir o arquivo inteiro):

```python
from langchain_openai import ChatOpenAI

LOCAL_MODEL = "qwen2.5-7b"
BASE_URL = "http://localhost:1234/v1"

# Todos os clientes: timeout de 120 s e sem retry do cliente HTTP. Os agentes fazem o
# próprio retry quando a saída vem inválida (Manual §4.7), e o grafo limita o tempo de
# cada nó (src/protecao.py); sem timeout aqui, uma chamada abandonada pelo grafo
# continuaria ocupando o LM Studio indefinidamente.
TIMEOUT_S = 120


def _cliente(temperatura: float) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=BASE_URL,
        api_key="lm-studio",
        model=LOCAL_MODEL,
        temperature=temperatura,
        timeout=TIMEOUT_S,
        max_retries=0,
    )


llm = _cliente(0)               # Sintetizador
llm_socratico = _cliente(0.7)   # Agente Socrático
llm_texto = _cliente(0)         # Agente de Texto
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/unit/test_protecao.py tests/unit/test_services_llm.py -v && pytest tests/contract tests/unit -q`

Esperado: todos passam e a suíte continua verde (com os 2 pulados da Task 2).

- [ ] **Step 5: Commit**

```bash
git add src/protecao.py tests/unit/test_protecao.py src/services/llm.py tests/unit/test_services_llm.py
git commit -m "feat: Timeout por nó e exceção como aviso; timeout de 120 s em todos os clientes de LLM" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Grafo com os cinco agentes reais, protegidos

**Files:**
- Modify: `src/graph.py` (arquivo inteiro)
- Modify: `tests/modelos_falsos.py` (acrescentar no fim)
- Create: `tests/unit/test_graph.py`
- Modify: `tests/unit/test_state.py` (remover os dois testes de grafo)

**Interfaces:**
- Consumes:
  - Task 3: `protecao.proteger`, `protecao.TIMEOUT_*_S`, `protecao.FALHA_INGESTOR`, `protecao.DOSSIE_INDISPONIVEL`.
  - Task 2: `synthesizer.synthesizer_node`, `synthesizer.DOSSIE_FALHA` e `modelos_falsos.SintetizadorFalso/RESPOSTA_SINTETIZADOR/carregar_mamao`.
  - Agentes: `ingestor.ingestor_node`, `ingestor.fetch_page`, `ingestor.WARN_PAYWALL`, `evidence.run`, `text_analysis.texto_node`, `text_analysis.dividir_em_lotes`, `socratic.socratic_node`.
  - `tests/evidence_fakes.py`: `mamao_fakes() -> (state, FakeSearch, FakeClassify, esperado)` e `patch_agent(monkeypatch, agent, search, classify)`.
- Produces:
  - `graph.construir_grafo(timeout_ingestor: float = TIMEOUT_INGESTOR_S, timeout_ramo: float = TIMEOUT_RAMO_S, timeout_sintetizador: float = TIMEOUT_SINTETIZADOR_S)`, que devolve o grafo compilado.
  - `graph.sistema_multiagente = construir_grafo()`, com o mesmo nome de hoje (o `app/app.py` usa).
  - `modelos_falsos.texto_falso(relatorio: dict)`, `modelos_falsos.socratico_falso(perguntas: list[str])`, `modelos_falsos.ligar_falsos(monkeypatch, relatorio=..., perguntas=...) -> SintetizadorFalso`, `TEXTO_LIVRE`, `RELATORIO_TEXTO_LIVRE`, `PERGUNTAS_TEXTO_LIVRE`.

- [ ] **Step 1: Estender os dublês**

Acrescentar no fim de `tests/modelos_falsos.py` (e juntar os imports novos aos do topo):

```python
# imports a acrescentar no topo do arquivo:
# from src.agents import evidence, socratic, synthesizer, text_analysis

# Duas frases para o ingestor real (spaCy): s01 e s02.
TEXTO_LIVRE = "O suco de mamão cura a dengue. Isso não tem comprovação."
RELATORIO_TEXTO_LIVRE = {
    "statements": [{"segment_id": "s01", "kind": "factual"}, {"segment_id": "s02", "kind": "factual"}],
    "markers": [],
}
PERGUNTAS_TEXTO_LIVRE = [
    "Quais estudos sustentam que o suco de mamão cura a dengue?",
    "Quem afirma que isso não tem comprovação, e com base em quê?",
]


def texto_falso(relatorio: dict):
    """Substitui text_analysis.chamar_modelo: sempre o mesmo relatório em JSON."""
    resposta = json.dumps(relatorio, ensure_ascii=False)
    return lambda mensagens: resposta


def socratico_falso(perguntas: list[str]):
    """Substitui socratic.chamar_modelo: sempre as mesmas perguntas em JSON."""
    resposta = json.dumps({"socratic_questions": perguntas}, ensure_ascii=False)
    return lambda mensagens: resposta


def busca_vazia(textos, k=None):
    """Substitui evidence.search: nenhuma checagem para nenhuma frase."""
    return [[] for _ in textos]


def ligar_falsos(monkeypatch, relatorio=RELATORIO_TEXTO_LIVRE, perguntas=PERGUNTAS_TEXTO_LIVRE) -> SintetizadorFalso:
    """Liga os quatro modelos falsos com respostas válidas; devolve o Sintetizador falso."""
    monkeypatch.setattr(text_analysis, "chamar_modelo", texto_falso(relatorio))
    monkeypatch.setattr(socratic, "chamar_modelo", socratico_falso(perguntas))
    monkeypatch.setattr(evidence, "search", busca_vazia)
    return SintetizadorFalso().instalar(monkeypatch)
```

O import do topo passa a ser `from src.agents import evidence, socratic, synthesizer, text_analysis`.

- [ ] **Step 2: Escrever os testes que falham**

`tests/unit/test_graph.py`:

```python
"""O grafo do Manual §3.1 com os cinco agentes reais e a proteção do §3.4."""
import threading

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src import graph, protecao
from src.agents import evidence, ingestor, socratic, synthesizer, text_analysis
from src.state import initial_state
from tests import modelos_falsos as falsos
from tests.evidence_fakes import mamao_fakes, patch_agent

TIMEOUT_CURTO = 1.0


def test_topologia_do_manual():
    arestas = {(a.source, a.target) for a in graph.sistema_multiagente.get_graph().edges}

    assert arestas == {
        ("__start__", "ingestor"),
        ("ingestor", "agente_evidencias"),
        ("ingestor", "agente_texto"),
        ("ingestor", "agente_socratico"),
        ("agente_evidencias", "sintetizador"),
        ("agente_texto", "sintetizador"),
        ("agente_socratico", "sintetizador"),
        ("sintetizador", "__end__"),
    }


def test_grafo_usa_os_agentes_reais_e_termina_com_todos_os_modelos_desligados():
    # o tests/conftest.py desliga os quatro modelos: cada agente real grava o próprio aviso
    out = graph.sistema_multiagente.invoke(initial_state(falsos.TEXTO_LIVRE))

    assert out["segments"]
    assert out["evidence"] is None
    assert out["text_report"] is None
    assert out["socratic_questions"] is None
    assert out["dossier"] == synthesizer.DOSSIE_FALHA
    assert sorted(w.split(":")[0] for w in out["warnings"]) == ["evidencias", "sintetizador", "socrático", "texto"]


def test_grafo_com_modelos_falsos_termina_sem_avisos(monkeypatch):
    falsos.ligar_falsos(monkeypatch)

    out = graph.sistema_multiagente.invoke(initial_state(falsos.TEXTO_LIVRE))

    assert out["warnings"] == []
    assert out["evidence"] == []
    assert out["text_report"].statements[0].kind == "factual"
    assert out["socratic_questions"] == falsos.PERGUNTAS_TEXTO_LIVRE
    assert out["dossier"] == falsos.RESPOSTA_SINTETIZADOR


def test_caso_do_mamao_de_ponta_a_ponta(monkeypatch):
    perguntas = falsos.carregar_mamao("04_socratico_saida.json")["socratic_questions"]
    sintetizador = falsos.ligar_falsos(
        monkeypatch,
        relatorio=falsos.carregar_mamao("03_texto_saida.json")["text_report"],
        perguntas=perguntas,
    )
    _, search, classify, esperado = mamao_fakes()
    patch_agent(monkeypatch, evidence, search, classify)

    out = graph.sistema_multiagente.invoke(initial_state(falsos.carregar_mamao("00_entrada.json")["raw_input"]))

    assert out["warnings"] == []
    assert [s.model_dump() for s in out["segments"]] == falsos.carregar_mamao("01_ingestor_saida.json")["segments"]
    assert [e.model_dump() for e in out["evidence"]] == esperado["evidence"]
    assert len(out["text_report"].markers) == 6
    assert out["socratic_questions"] == perguntas
    assert out["dossier"] == falsos.RESPOSTA_SINTETIZADOR
    prompt = sintetizador.prompts[0]
    for ev in esperado["evidence"]:
        assert ev["source_name"] in prompt and ev["excerpt"] in prompt
    for pergunta in perguntas:
        assert pergunta in prompt


def test_url_com_paywall_passa_pelo_grafo_inteiro(monkeypatch):
    falsos.ligar_falsos(monkeypatch)
    monkeypatch.setattr(ingestor, "fetch_page", lambda url: None)

    out = graph.sistema_multiagente.invoke(initial_state("https://exemplo-jornal.com.br/materia-fechada"))

    assert out["segments"] == []
    assert out["warnings"] == [ingestor.WARN_PAYWALL]
    assert out["evidence"] == []
    assert out["text_report"] is None
    assert out["socratic_questions"] == []
    assert out["dossier"] == falsos.RESPOSTA_SINTETIZADOR


# Cada ramo trava até o teste liberar; depois devolve uma resposta válida, para a
# thread abandonada terminar sem chamar mais nada.
CASOS_TIMEOUT = {
    "evidencias": (evidence, "search", falsos.busca_vazia, "evidence"),
    "texto": (text_analysis, "chamar_modelo", falsos.texto_falso(falsos.RELATORIO_TEXTO_LIVRE), "text_report"),
    "socratico": (socratic, "chamar_modelo", falsos.socratico_falso(falsos.PERGUNTAS_TEXTO_LIVRE), "socratic_questions"),
}


@pytest.mark.parametrize("ramo", sorted(CASOS_TIMEOUT))
def test_ramo_que_estoura_o_tempo_vira_aviso_e_o_dossie_sai(monkeypatch, ramo):
    falsos.ligar_falsos(monkeypatch)
    modulo, atributo, resposta, campo = CASOS_TIMEOUT[ramo]
    liberar = threading.Event()

    def travado(*args, **kwargs):
        liberar.wait(5)
        return resposta(*args, **kwargs)

    monkeypatch.setattr(modulo, atributo, travado)
    grafo = graph.construir_grafo(timeout_ramo=TIMEOUT_CURTO)
    try:
        out = grafo.invoke(initial_state(falsos.TEXTO_LIVRE))
    finally:
        liberar.set()

    assert out[campo] is None
    assert out["warnings"] == [f"{ramo}: timeout"]
    assert out["dossier"] == falsos.RESPOSTA_SINTETIZADOR


def test_excecao_nao_prevista_num_agente_vira_aviso(monkeypatch):
    sintetizador = falsos.ligar_falsos(monkeypatch)

    def quebra(*args, **kwargs):
        raise ValueError("bug no lote")

    # o texto_node só trata SaidaInvalida e ModeloIndisponivel: um ValueError escaparia
    monkeypatch.setattr(text_analysis, "dividir_em_lotes", quebra)

    out = graph.sistema_multiagente.invoke(initial_state(falsos.TEXTO_LIVRE))

    assert out["text_report"] is None
    assert out["warnings"] == ["texto: ValueError: bug no lote"]
    assert out["dossier"] == falsos.RESPOSTA_SINTETIZADOR
    assert "Nenhum marcador retórico relevante detectado." in sintetizador.prompts[0]


def test_sintetizador_travado_ainda_entrega_um_dossie(monkeypatch):
    falsos.ligar_falsos(monkeypatch)
    liberar = threading.Event()

    def travado(valor_prompt):
        liberar.wait(5)
        return AIMessage(content=falsos.RESPOSTA_SINTETIZADOR)

    monkeypatch.setattr(synthesizer, "llm", RunnableLambda(travado))
    grafo = graph.construir_grafo(timeout_sintetizador=TIMEOUT_CURTO)
    try:
        out = grafo.invoke(initial_state(falsos.TEXTO_LIVRE))
    finally:
        liberar.set()

    assert out["dossier"] == protecao.DOSSIE_INDISPONIVEL
    assert out["warnings"] == ["sintetizador: timeout"]
```

Em `tests/unit/test_state.py`, apagar os dois testes pulados na Task 2 (`test_grafo_roda_ponta_a_ponta_com_texto_livre` e `test_grafo_segue_quando_o_agente_de_texto_falha`) e os imports que só eles usavam. O arquivo fica assim:

```python
from src.state import PipelineState, initial_state


def test_initial_state_valida_no_schema_estrito():
    state = PipelineState(**initial_state("uma noticia"))

    assert state.raw_input == "uma noticia"
    assert state.segments == []
    assert state.warnings == []
    assert state.evidence is None
    assert state.dossier is None


def test_initial_state_aceita_sobrescritas():
    state = PipelineState(**initial_state("x", clean_text="texto", truncated=True))

    assert state.clean_text == "texto"
    assert state.truncated is True


def test_initial_state_cobre_exatamente_os_campos_do_schema():
    # Falha se alguém mudar o PipelineState sem atualizar initial_state (ver aviso em src/state.py)
    assert set(initial_state("x")) == set(PipelineState.model_fields)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `pytest tests/unit/test_graph.py -v`

Esperado: `test_topologia_do_manual` já passa, porque a topologia não muda. Os testes de timeout falham com `AttributeError: module 'src.graph' has no attribute 'construir_grafo'`. Os demais falham porque o grafo ainda usa os stubs de Evidências e Socrático: aparecem evidências e perguntas fixas, faltam os avisos, e o `ValueError` derruba o `invoke`.

- [ ] **Step 4: Implementar**

`src/graph.py` (substituir o arquivo inteiro):

```python
"""Orquestrador: o grafo do Manual §3.1 com os cinco agentes reais.

Cada nó passa por `proteger` (src/protecao.py): estourar o tempo ou levantar exceção
vira aviso em `warnings` e a saída de falha do nó, e o grafo sempre chega ao
Sintetizador (Manual §3.4).

ATENÇÃO: o PipelineState é estrito (sem valores padrão). Quem chamar o grafo
deve passar o estado completo criado por `initial_state(...)` (src/state.py):
    sistema_multiagente.invoke(initial_state("texto ou URL"))
Passar só {"raw_input": ...} levanta ValidationError. Ver o aviso no topo de src/state.py.
"""
from langgraph.graph import END, START, StateGraph

from src import protecao
from src.agents.evidence import run as evidencias_node
from src.agents.ingestor import ingestor_node
from src.agents.socratic import socratic_node as socratico_node
from src.agents.synthesizer import synthesizer_node as sintetizador_node
from src.agents.text_analysis import texto_node
from src.state import PipelineState

RAMOS = ("agente_evidencias", "agente_texto", "agente_socratico")


def construir_grafo(
    timeout_ingestor: float = protecao.TIMEOUT_INGESTOR_S,
    timeout_ramo: float = protecao.TIMEOUT_RAMO_S,
    timeout_sintetizador: float = protecao.TIMEOUT_SINTETIZADOR_S,
):
    """Monta e compila o grafo; os timeouts (em segundos) existem como parâmetro para os testes."""
    builder = StateGraph(PipelineState)

    builder.add_node("ingestor", protecao.proteger("ingestor", ingestor_node, timeout_ingestor, protecao.FALHA_INGESTOR))
    builder.add_node("agente_evidencias", protecao.proteger("evidencias", evidencias_node, timeout_ramo, {"evidence": None}))
    builder.add_node("agente_texto", protecao.proteger("texto", texto_node, timeout_ramo, {"text_report": None}))
    builder.add_node("agente_socratico", protecao.proteger("socratico", socratico_node, timeout_ramo, {"socratic_questions": None}))
    builder.add_node(
        "sintetizador",
        protecao.proteger("sintetizador", sintetizador_node, timeout_sintetizador, {"dossier": protecao.DOSSIE_INDISPONIVEL}),
    )

    builder.add_edge(START, "ingestor")
    for ramo in RAMOS:
        builder.add_edge("ingestor", ramo)
        builder.add_edge(ramo, "sintetizador")
    builder.add_edge("sintetizador", END)

    return builder.compile()


sistema_multiagente = construir_grafo()
```

- [ ] **Step 5: Rodar e ver passar**

Run: `pytest tests/unit/test_graph.py -v && pytest tests/contract tests/unit -q`

Esperado: os 10 testes do grafo passam (os de timeout levam cerca de 1 s cada) e a suíte inteira fica verde, sem testes pulados. `tests/contract/test_state_contracts.py` continua usando os stubs, e é assim que deve ser: ele valida os stubs, não o grafo.

Se `test_caso_do_mamao_de_ponta_a_ponta` falhar só na comparação de `segments`, rode `python -c "from src.agents.ingestor import segment_text; print(segment_text(open('tests/fixtures/caso_mamao_dengue/00_entrada.json').read()))"` e compare com `01_ingestor_saida.json`. Em 06/10, com o `pt_core_news_sm` local, as 6 frases batem.

- [ ] **Step 6: Commit**

```bash
git add src/graph.py tests/modelos_falsos.py tests/unit/test_graph.py tests/unit/test_state.py
git commit -m "feat: Grafo com os cinco agentes reais, cada nó com timeout e degradação graciosa" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Interface, rodada com modelos reais e documentação

**Files:**
- Modify: `app/app.py` (duas strings)
- Modify: `tests/unit/test_app.py` (acrescentar dois testes)
- Create: `tests/integration/test_grafo_lmstudio.py`
- Modify: `README.md` (nova subseção depois de "Para rodar os testes")
- Modify: `docs/Manual do Sistema Multiagente — Avaliação de Confiabilidade da Informação.md` (§3.4, bullet "Timeout por nó")

**Interfaces:**
- Consumes: `graph.sistema_multiagente` (Task 4), as variáveis `GRAFO_TIMEOUT_INGESTOR`, `GRAFO_TIMEOUT_RAMO` e `GRAFO_TIMEOUT_SINTETIZADOR` (Task 3) e a fixture `sem_modelos` anulada em `tests/integration/conftest.py` (Task 1).
- Produces: nenhuma interface de código nova.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar no fim de `tests/unit/test_app.py`:

```python
def test_app_mostra_o_aviso_de_cada_ramo_que_falhou():
    # o tests/conftest.py desliga os quatro modelos
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    assert not at.exception
    avisos = " ".join(w.value for w in at.warning)
    for prefixo in ("evidencias:", "texto:", "socrático:", "sintetizador:"):
        assert prefixo in avisos


def test_app_cita_o_lm_studio_e_nao_o_ollama():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()

    textos = " ".join(m.value for m in at.markdown)
    assert "LM Studio" in textos
    assert "Ollama" not in textos
```

`tests/integration/test_grafo_lmstudio.py`:

```python
"""Roda o grafo inteiro com os modelos reais e imprime o tempo de cada nó.

Não roda no CI. Rode da raiz, com o LM Studio ligado (qwen2.5-7b em localhost:1234):
    pytest tests/integration/test_grafo_lmstudio.py -v -s
O Agente de Evidências usa o índice em chroma_data/. Sem ele, ou na primeira carga dos
modelos (que pode passar do timeout do ramo), o teste aceita o aviso de evidências.
"""
import json
import time
from pathlib import Path

import pytest
import requests

from src.graph import sistema_multiagente
from src.state import initial_state

ENTRADA = Path(__file__).resolve().parents[1] / "fixtures" / "caso_mamao_dengue" / "00_entrada.json"


def lm_studio_no_ar():
    try:
        return requests.get("http://localhost:1234/v1/models", timeout=2).ok
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not lm_studio_no_ar(), reason="LM Studio não está rodando em localhost:1234")


def test_caso_do_mamao_com_os_modelos_reais():
    estado = initial_state(json.loads(ENTRADA.read_text(encoding="utf-8"))["raw_input"])
    final, tempos = dict(estado), {}
    inicio = time.monotonic()

    for evento in sistema_multiagente.stream(estado):
        for no, atualizacao in evento.items():
            tempos[no] = round(time.monotonic() - inicio, 1)
            for chave, valor in atualizacao.items():
                final[chave] = final["warnings"] + valor if chave == "warnings" else valor

    print("\nsegundos desde o início, quando cada nó terminou:", tempos)
    print("avisos:", final["warnings"])
    print(final["dossier"])

    assert final["dossier"]
    assert final["text_report"] is not None
    assert final["socratic_questions"]
    assert not [w for w in final["warnings"] if w.startswith(("ingestor", "texto", "socr", "sintetizador"))]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest tests/unit/test_app.py -v`

Esperado: `test_app_cita_o_lm_studio_e_nao_o_ollama` falha (o texto ainda diz "Ollama (`llama3.2`)"). `test_app_mostra_o_aviso_de_cada_ramo_que_falhou` já passa desde a Task 4: ele fica como guarda de regressão da interface.

- [ ] **Step 3: Implementar**

Em `app/app.py`, trocar:

```python
st.markdown("Executa análise paralela com LangGraph e modelos locais via Ollama (`llama3.2`).")
```

por:

```python
st.markdown("Executa a análise em paralelo com LangGraph e modelos locais no LM Studio (`qwen2.5-7b`).")
```

e trocar:

```python
                st.info("Dica: Verifique se o Ollama está rodando e se o modelo 'llama3.2' está instalado.")
```

por:

```python
                st.info("Dica: verifique se o LM Studio está rodando em localhost:1234 com o qwen2.5-7b carregado.")
```

Em `README.md`, logo depois do bloco

````text
Para rodar os testes (também da raiz, sem precisar definir `PYTHONPATH`):
```bash
pytest
```
````

acrescentar:

````markdown
### 5. Orquestração: timeouts e avisos

O grafo (`src/graph.py`) roda o Ingestor, depois Evidências, Texto e Socrático em paralelo, e por fim o Sintetizador. Cada nó tem um limite de tempo (`src/protecao.py`). Se um nó estoura o tempo ou quebra, o grafo segue sem ele, a interface mostra o aviso (por exemplo, `socratico: timeout`) e o dossiê sai assim mesmo.

| Nó | Padrão | Variável de ambiente |
| --- | --- | --- |
| Ingestor | 60 s | `GRAFO_TIMEOUT_INGESTOR` |
| Evidências, Texto, Socrático (cada um) | 240 s | `GRAFO_TIMEOUT_RAMO` |
| Sintetizador | 180 s | `GRAFO_TIMEOUT_SINTETIZADOR` |

Defina as variáveis antes de subir o Streamlit (ex.: `GRAFO_TIMEOUT_RAMO=400 streamlit run app/app.py`).

Na primeira execução, o Agente de Evidências baixa e carrega o BGE-M3 e o mDeBERTa, o que pode passar do limite e gerar `evidencias: timeout`. O carregamento continua em segundo plano, e a análise seguinte já encontra os modelos na memória. Na demo, faça uma análise de aquecimento antes de apresentar.

Para rodar o grafo inteiro com os modelos reais e ver o tempo de cada nó (fora do CI):
```bash
pytest tests/integration/test_grafo_lmstudio.py -v -s
```
````

No Manual, §3.4, trocar o bullet:

```markdown
- **Timeout por nó:** um ramo que estoura o tempo grava um aviso em `warnings` e devolve `None`; os outros seguem.
```

por:

```markdown
- **Timeout por nó:** um ramo que estoura o tempo grava um aviso em `warnings` e devolve `None`; os outros seguem. Implementado em `src/protecao.py`: 60 s no Ingestor, 240 s em cada ramo e 180 s no Sintetizador, ajustáveis por `GRAFO_TIMEOUT_INGESTOR`, `GRAFO_TIMEOUT_RAMO` e `GRAFO_TIMEOUT_SINTETIZADOR`. A mesma camada transforma uma exceção não tratada de qualquer nó em aviso, e o Sintetizador protegido nunca devolve `dossier = None`.
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest tests/contract tests/unit -q`

Esperado: tudo verde.

Run: `pytest tests/integration/test_grafo_lmstudio.py -v -s`

Esperado: `SKIPPED` se o LM Studio estiver desligado. Com ele ligado, `PASSED`, com o tempo de cada nó impresso. Anote os tempos para o PR (meta do Manual: p50 < 3 min).

Run (com o LM Studio ligado): `streamlit run app/app.py`. Cole o texto de `tests/fixtures/caso_mamao_dengue/00_entrada.json` e confira que aparecem as frases, as evidências (se o índice existir), os marcadores, as perguntas e o dossiê.

- [ ] **Step 5: Commit**

```bash
git add app/app.py tests/unit/test_app.py tests/integration/test_grafo_lmstudio.py README.md "docs/Manual do Sistema Multiagente — Avaliação de Confiabilidade da Informação.md"
git commit -m "docs: Timeouts do grafo no README e no Manual; teste do grafo com os modelos reais; interface cita o LM Studio" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Entrega

- [ ] `pytest tests/contract tests/unit -q` verde, rodado da raiz.
- [ ] `git push -u origin feat/orquestracao` (a branch foi criada rastreando a `origin/develop`, e o `-u` corrige o upstream).
- [ ] PR para a **develop**, com: o que mudou por task; o aviso de que o `synthesizer.py` recebeu só a correção de campos e a reescrita da spec §4.5.1 continua pendente; os tempos por nó medidos no Step 4 da Task 5; e a inconsistência `socrático:`/`socratico:` nos prefixos de aviso, para o dono do Agente Socrático decidir.
