# Agentes em paralelo: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingestor → {Evidências, Texto (com o argumento), Socrático} em paralelo → Sintetizador, com o dossiê igual ao de hoje.

**Architecture:** Mover o passo do argumento para `src/agents/argumento.py`, chamado pelo `texto_node`; tirar o nó `agente_argumento` do grafo; simplificar o resumo do Socrático e o progresso da sala.

**Tech Stack:** Python, LangGraph, pytest, LM Studio (integração).

**Spec:** `docs/superpowers/specs/2026-10-15-agentes-em-paralelo-design.md`

## Global Constraints

- Nomes mantidos: `llm_sintetizador`, `src/prompts/sintetizador_sistema.md`, avisos `sintetizador: ...`.
- Saída de falha do nó do Texto: `{"text_report": None, "argument": None}`.
- `ORDEM_NOS = ("ingestor", "agente_evidencias", "agente_texto", "agente_socratico", "sintetizador")`.
- Suíte verde ao fim de cada tarefa; LM Studio em `localhost:1234` com `LLM_MODEL=qwen/qwen2.5-vl-7b` para a integração.

## Review Focus

- Trava dos testes contra o LLM: `tests/conftest.py` passa a trocar `chamar_modelo` em `src.agents.argumento` (o Sintetizador não tem mais LLM); `test_isolamento.py` cobre.
- Texto sem nenhuma frase classificada: `argument` não preenchido e o dossiê com "Não foi possível analisar a estrutura do texto."
- Modelo fora do ar no argumento: classificação mantida, marcadores sem efeito e aviso `sintetizador: falha ao chamar o modelo`.
- Timeout do nó do Texto: `text_report` e `argument` `None`, aviso `texto: timeout`, dossiê sai.
- Socrático com `text_report` ausente: resumo com título e primeiras frases.

---

### Task 1: Argumento dentro do Agente de Texto

**Files:** Create `src/agents/argumento.py` (o código de LLM de `src/agents/synthesizer/agent.py`); Modify `src/agents/synthesizer/agent.py` (fica `sintetizador_node`, `argumento_fallback` e aliases), `src/agents/text_analysis.py` (`texto_node` chama `argumento.argumento_node`); Tests: `tests/unit/test_synthesizer.py` (partes do argumento passam a importar `src.agents.argumento`), `tests/unit/test_text_analysis.py`, `tests/conftest.py`, `tests/modelos_falsos.py`, `tests/unit/test_isolamento.py`, contrato do Sintetizador.

**Interfaces:**
- Produces: `src.agents.argumento.argumento_node(state: PipelineState) -> dict` (`{"argument": list[str]}` + `"warnings"` opcional), `chamar_modelo`, `WARN_*` do argumento; `texto_node(state) -> {"text_report", "argument"?, "warnings"?}`.

- [ ] **Step 1:** Teste `test_texto_node_tambem_escreve_o_argumento`: com o modelo falso respondendo a classificação e o efeito, `texto_node` devolve `text_report` e `argument` igual a `argumento_node` aplicado ao estado classificado. Teste `test_sem_classificacao_nao_ha_argumento`: modelo falso que não classifica nada → sem chave `argument`. Rodar: FAIL.
- [ ] **Step 2:** Mover o código; `texto_node` chama `argumento_node(state.model_copy(update={"text_report": relatorio}))` e soma os avisos depois dos do Texto.
- [ ] **Step 3:** `venv/bin/python -m pytest -q` → verde.

### Task 2: Grafo, Socrático, progresso e sala

**Files:** `src/pipeline/graph.py`, `src/agents/socratic.py` (`resumo_para_socratico`), `src/pipeline/progresso.py`, `app/sala/sala.js`; Tests: `tests/unit/test_graph.py`, `tests/unit/test_socratic.py`, `tests/unit/test_progresso.py`, `tests/unit/test_app.py`, `tests/unit/test_medicao.py`.

- [ ] **Step 1:** Atualizar os testes: arestas `ingestor→{evidencias,texto,socratico}`, `[ev,texto,soc]→sintetizador`, sem `agente_argumento`; `ORDEM_NOS` nova; timeout do Texto devolve `argument=None` e o dossiê sai com o fallback; Socrático começa junto com Texto e Evidências na sala; resumo do Socrático sem seleção de factuais. Rodar: FAIL.
- [ ] **Step 2:** Implementar.
- [ ] **Step 3:** `venv/bin/python -m pytest -q` → verde.

### Task 3: Integração, latência e documentação

- [ ] **Step 1:** `LLM_MODEL=qwen/qwen2.5-vl-7b venv/bin/python -m pytest -q tests/integration` → passa (sem skip do LM Studio).
- [ ] **Step 2:** `eval/medir_latencia.py --repeticoes 2 --aquecimento 1 --saida eval/resultados/latencia_2026-10-15_depois.json`; comparar com `latencia_2026-10-15_antes.json`.
- [ ] **Step 3:** Docs: README, `docs/agents/desempenho.md` (barreira e resultado), `sintetizador.md`, `socratico.md`, `texto.md`; `grep -rn "agente_argumento"` em código e docs atuais só onde for histórico.
- [ ] **Step 4:** Commit.
