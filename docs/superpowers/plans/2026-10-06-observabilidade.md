# Observabilidade (tracing com Phoenix local e latência) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cada análise vira um trace no Arize Phoenix local (raiz, nós do grafo, chamadas de LLM e etapas do Ingestor e do Evidências), o Streamlit mostra quanto cada nó levou, e um script em `eval/` mede p50/p95 por nó e ponta a ponta.

**Architecture:** OpenTelemetry é a base. `src/observabilidade.py` liga o Phoenix (`phoenix.otel.register` + `LangChainInstrumentor`), mas só quando `PHOENIX_TRACING=1`; sem isso, todo span é no-op. `src/protecao.py` passa a rodar cada nó com `contextvars.copy_context()`, para que spans e chamadas de LLM feitos dentro da thread do nó fiquem pendurados no trace certo, e abre um span por nó com o resultado (ok, timeout ou erro). `src/medicao.py` executa o grafo por `stream`, junta o estado, calcula a duração de cada nó e abre o span raiz `analise`; o app e o script de latência usam essa mesma função.

**Tech Stack:** Python 3.10 (CI) / 3.14 (venv), LangGraph 1.2, `opentelemetry-sdk` 1.44 (já no venv), `arize-phoenix` + `arize-phoenix-otel` + `openinference-instrumentation-langchain` (novos; instalação conferida no venv em 06/10), Streamlit `AppTest`, pytest.

**Spec:** não há spec própria. O plano implementa o Manual (`docs/Manual do Sistema Multiagente — Avaliação de Confiabilidade da Informação.md`) §5.4, linha "Observabilidade: Arize Phoenix (local) ou LangSmith (cota gratuita) — Trace por nó: entrada, saída, latência, tokens"; §7.1, "Latência: p50 e p95 ponta a ponta, por entrada — p50 < 3 min"; §10.5, "Execução aparece no tracing com latência registrada"; e §9.3 (tracing é entregável do R1). Decisões tomadas com o usuário em 06/10: **Phoenix local** (não LangSmith); escopo = tracing por nó + **relatório p50/p95** + **tempos no Streamlit** + **spans do Ingestor e do Evidências**.

## Global Constraints

- Tracing **desligado por padrão**. Liga só com `PHOENIX_TRACING=1`. O endereço do coletor vem de `PHOENIX_COLLECTOR_ENDPOINT` (padrão do próprio Phoenix: `http://localhost:6006`). O projeto no Phoenix se chama `grupo1-resia`.
- Observabilidade **nunca derruba uma análise**: pacote ausente, Phoenix fora do ar ou atributo estranho viram, no máximo, um `logger.warning`.
- Os dados ficam na máquina: nada é enviado para fora de `localhost`.
- CI: `requirements-ci.txt` ganha só `opentelemetry-sdk`. Phoenix e OpenInference entram só em `requirements.txt` e são importados de forma preguiçosa, dentro de `configurar_tracing()`.
- Nenhum teste de `tests/unit` ou `tests/contract` abre servidor ou faz rede. Os testes de span usam `InMemorySpanExporter`.
- O `PipelineState` não muda, e os agentes continuam sem importar LangGraph. Spans manuais usam só `src.observabilidade.span`.
- Atributos próprios usam o prefixo `pipeline.`. Todo span manual tem `openinference.span.kind`: `CHAIN`, ou `RETRIEVER` na busca do Evidências, para o Phoenix exibir o tipo.
- CI em Python 3.10: sem sintaxe nova, e `contextvars.copy_context()` está disponível.
- Branch `feat/observabilidade` a partir da `develop` local; PR para a `develop`. Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Phoenix fora do ar com `PHOENIX_TRACING=1`:** a análise roda normal e o problema vira log, não exceção. Teste: `test_register_que_falha_nao_derruba_e_devolve_false` (Task 1).
2. **Thread abandonada por timeout que cria span depois que o nó já devolveu:** não quebra, e o span fica filho do span do nó. Teste: `test_span_da_thread_abandonada_continua_no_trace` (Task 2).
3. **Atributo de tipo estranho** (`None`, dict, `Segment`, lista mista): é descartado ou vira texto, sem exceção. Teste: `test_atributos_estranhos_nao_quebram` (Task 1).
4. **App com tracing desligado:** os tempos por nó aparecem, mas não aparece link nem ID de trace. Teste: `test_app_mostra_tempos_sem_trace_quando_tracing_desligado` (Task 5).
5. **Relatório com uma única execução, ou sem execução:** p50 = p95 = o próprio valor; lista vazia dá `ValueError` com mensagem clara, e não `IndexError`. Teste: `test_percentil_com_um_valor` e `test_percentil_sem_valores` (Task 6).

## Mapa de arquivos

| Arquivo | Ação | Responsabilidade |
| --- | --- | --- |
| `src/observabilidade.py` | Criar | `configurar_tracing()` e `span(...)` |
| `tests/conftest.py` | Modificar | Fixture `spans` (provider em memória) |
| `tests/unit/test_observabilidade.py` | Criar | Ligar e desligar, falhas, atributos |
| `src/protecao.py` | Modificar | `copy_context` + span por nó |
| `tests/unit/test_protecao.py` | Modificar | Hierarquia de spans, resultado do nó |
| `src/agents/ingestor.py`, `src/agents/evidence.py` | Modificar | Spans das etapas |
| `tests/unit/test_ingestor.py`, `tests/unit/test_evidence_agente.py` | Modificar | Spans e atributos |
| `src/medicao.py` | Criar | `executar(...)`, `Execucao`, span raiz |
| `tests/unit/test_medicao.py` | Criar | Junção do estado, durações, span raiz |
| `app/app.py`, `tests/unit/test_app.py` | Modificar | Usa `executar`, mostra tempos e trace |
| `eval/medir_latencia.py`, `eval/entradas_latencia.json` | Criar | p50/p95 por nó e total |
| `tests/unit/test_medir_latencia.py` | Criar | Percentil, resumo, aquecimento |
| `requirements.txt`, `requirements-ci.txt`, `README.md`, Manual §5.4 | Modificar | Dependências e como usar |

---

### Task 1: Base de observabilidade

**Files:**
- Create: `src/observabilidade.py`
- Modify: `tests/conftest.py`, `requirements.txt`, `requirements-ci.txt`
- Test: `tests/unit/test_observabilidade.py`

**Interfaces:**
- Produces:
  - `configurar_tracing() -> bool`. Devolve `True` quando o tracing ficou ligado. É idempotente: na segunda chamada não registra de novo, só devolve o estado. Nunca levanta exceção.
  - `span(nome: str, tipo: str = "CHAIN", **atributos) -> ContextManager[opentelemetry.trace.Span]`. Abre `tracer.start_as_current_span(nome)`, grava `openinference.span.kind = tipo` e cada atributo como `pipeline.<chave>`, e registra a exceção no span se o bloco levantar (e a repassa).
  - Fixture `spans` em `tests/conftest.py`: devolve o `InMemorySpanExporter` limpo. O `TracerProvider` com `SimpleSpanProcessor(exporter)` é registrado como global uma única vez por sessão.

- [ ] **Step 0:** `git switch -c feat/observabilidade develop`; `venv/bin/pip install arize-phoenix arize-phoenix-otel openinference-instrumentation-langchain`; `pytest tests/contract tests/unit -q` verde (linha de base: 338).

- [ ] **Step 1: Testes que falham** (`tests/unit/test_observabilidade.py`), com módulos falsos via `monkeypatch.setitem(sys.modules, "phoenix.otel", ...)` e `"openinference.instrumentation.langchain"`. Antes de cada teste, `monkeypatch.setattr(observabilidade, "_configurado", None)`.

```python
def test_desligado_por_padrao_nao_importa_phoenix(monkeypatch):
    monkeypatch.delenv("PHOENIX_TRACING", raising=False)
    monkeypatch.setitem(sys.modules, "phoenix.otel", None)  # importar levantaria ImportError
    assert observabilidade.configurar_tracing() is False

def test_ligado_registra_o_projeto_e_instrumenta_o_langchain_uma_vez(monkeypatch):
    # register falso guarda os kwargs e devolve um provider sentinela; o instrumentador falso guarda tracer_provider
    ...
    assert observabilidade.configurar_tracing() is True
    assert observabilidade.configurar_tracing() is True
    assert chamadas_register == [{"project_name": "grupo1-resia", "batch": True}]
    assert instrumentado_com == [provider]

def test_pacote_ausente_devolve_false_e_avisa(monkeypatch, caplog):
    monkeypatch.setenv("PHOENIX_TRACING", "1")
    monkeypatch.setitem(sys.modules, "phoenix.otel", None)
    assert observabilidade.configurar_tracing() is False
    assert "pip install arize-phoenix-otel" in caplog.text

def test_register_que_falha_nao_derruba_e_devolve_false(monkeypatch):
    # register falso levanta ConnectionError("Phoenix fora do ar")
    assert observabilidade.configurar_tracing() is False

def test_span_grava_tipo_e_atributos_com_prefixo(spans):
    with observabilidade.span("ingestor.segmentar", frases=3, truncado=False):
        pass
    [s] = spans.get_finished_spans()
    assert s.name == "ingestor.segmentar"
    assert s.attributes["openinference.span.kind"] == "CHAIN"
    assert s.attributes["pipeline.frases"] == 3 and s.attributes["pipeline.truncado"] is False

def test_atributos_estranhos_nao_quebram(spans):
    with observabilidade.span("x", nada=None, dicionario={"a": 1}, lista=["a", 2], objeto=object()):
        pass
    attrs = spans.get_finished_spans()[0].attributes
    assert "pipeline.nada" not in attrs
    assert attrs["pipeline.dicionario"] == "{'a': 1}" and attrs["pipeline.lista"] == ("a", "2")
    assert isinstance(attrs["pipeline.objeto"], str)

def test_excecao_no_bloco_fica_no_span_e_e_repassada(spans):
    with pytest.raises(ValueError):
        with observabilidade.span("x"):
            raise ValueError("bug")
    s = spans.get_finished_spans()[0]
    assert s.status.status_code.name == "ERROR" and s.events[0].name == "exception"
```

- [ ] **Step 2:** `pytest tests/unit/test_observabilidade.py -v` deve falhar com `ImportError: cannot import name 'observabilidade'`.

- [ ] **Step 3: Implementar `src/observabilidade.py`.**
  - `configurar_tracing()` lê `PHOENIX_TRACING == "1"`. Importa `phoenix.otel.register` e `openinference.instrumentation.langchain.LangChainInstrumentor` dentro de `try` e chama `register(project_name="grupo1-resia", batch=True)`; o endpoint vem do próprio `PHOENIX_COLLECTOR_ENDPOINT`. Depois chama `LangChainInstrumentor().instrument(tracer_provider=provider)` e guarda o resultado em `_configurado`.
  - Normalização em `span`: `None` é descartado; `str`, `bool`, `int` e `float` passam como estão; lista ou tupla viram tupla de `str`; qualquer outro valor vira `str(valor)`.
  - Usar `trace.get_tracer("grupo1_resia")` na hora da chamada, não no import, para respeitar o provider definido depois.
  - Fixture `spans` em `tests/conftest.py`, como descrito em Interfaces; chamar `exporter.clear()` antes de devolver.
  - `requirements.txt`: `arize-phoenix`, `arize-phoenix-otel`, `openinference-instrumentation-langchain`. `requirements-ci.txt`: `opentelemetry-sdk`.

- [ ] **Step 4:** `pytest tests/unit/test_observabilidade.py -v` passa; `pytest tests/contract tests/unit -q` verde.

- [ ] **Step 5:** commit `feat: Base de observabilidade: Phoenix local opcional e spans com atributos pipeline.*`.

---

### Task 2: Contexto e span por nó na proteção

**Files:**
- Modify: `src/protecao.py`
- Test: `tests/unit/test_protecao.py`

**Interfaces:**
- Consumes: `observabilidade.span` (Task 1).
- Produces: cada nó protegido gera um span `no.<nome>` (por exemplo `no.texto`) com `pipeline.no`, `pipeline.resultado` (`"ok"`, `"timeout"` ou `"erro"`) e `pipeline.avisos` (os `warnings` da saída devolvida, que pode estar vazia). A função do nó roda dentro de `contextvars.copy_context()`, capturado **dentro** do span, então tudo o que a thread criar fica filho de `no.<nome>`. A assinatura de `proteger` não muda.

- [ ] **Step 1: Testes que falham**

```python
def test_span_criado_dentro_do_no_fica_debaixo_do_no_e_de_quem_chamou(spans):
    tracer = trace.get_tracer("teste")
    def fn(state):
        with tracer.start_as_current_span("dentro"):
            return {"text_report": None}
    no = protecao.proteger("texto", fn, 1, {"text_report": None})
    with tracer.start_as_current_span("fora"):
        no(None)
    por_nome = {s.name: s for s in spans.get_finished_spans()}
    assert por_nome["dentro"].parent.span_id == por_nome["no.texto"].context.span_id
    assert por_nome["no.texto"].parent.span_id == por_nome["fora"].context.span_id

@pytest.mark.parametrize("fn, resultado", [
    (lambda s: {"evidence": []}, "ok"),
    (quebra, "erro"),          # levanta RuntimeError
])
def test_span_do_no_registra_o_resultado(spans, fn, resultado): ...
    # atributos: pipeline.no == "evidencias", pipeline.resultado == resultado

def test_span_do_no_registra_timeout_e_avisos(spans):
    # fn travada em Event, timeout 0.1 → pipeline.resultado == "timeout",
    # pipeline.avisos == ("socratico: timeout",)

def test_span_da_thread_abandonada_continua_no_trace(spans):
    # fn: espera o Event, depois abre span "tarde"; o teste libera o Event depois do timeout
    # e espera a thread terminar (Event "terminou"); "tarde" existe e é filho de no.socratico
```

- [ ] **Step 2:** os testes falham (não há span `no.*`, e o span `dentro` sai como raiz).

- [ ] **Step 3:** em `proteger.no(state)`, envolver tudo em `observabilidade.span(f"no.{nome}", no=nome)`; dentro dele, `ctx = contextvars.copy_context()` e `executor.submit(ctx.run, fn, state)`. Antes de devolver, gravar `pipeline.resultado` e `pipeline.avisos` no span. O caminho do `recuperar` não muda.

- [ ] **Step 4:** `pytest tests/unit/test_protecao.py tests/unit/test_graph.py -v` passa; suíte inteira verde.

- [ ] **Step 5:** commit `feat: Nós protegidos propagam o contexto do trace e registram o resultado num span`.

---

### Task 3: Spans das etapas do Ingestor e do Evidências

**Files:**
- Modify: `src/agents/ingestor.py` (`ingestor_node`), `src/agents/evidence.py` (`run`)
- Test: `tests/unit/test_ingestor.py`, `tests/unit/test_evidence_agente.py`

**Interfaces:**
- Consumes: `observabilidade.span` (Task 1).
- Produces (nomes e atributos que o Phoenix e o README citam):
  - `ingestor.baixar` (só quando a entrada é URL): `url`, `ok` (bool; `False` em paywall, timeout ou página vazia).
  - `ingestor.segmentar`: `frases` (int), `truncado` (bool).
  - `evidencias.busca` (`tipo="RETRIEVER"`): `frases`, `k`.
  - `evidencias.termos_chave`: `candidatas`, `aprovadas`.
  - `evidencias.nli`: `pares`, `evidencias`. Só existe quando há candidata aprovada.

- [ ] **Step 1: Testes que falham**

```python
# test_ingestor.py
def test_spans_do_ingestor_com_texto(spans):
    run_node("Primeira frase. Segunda frase.")
    por_nome = {s.name: s for s in spans.get_finished_spans()}
    assert "ingestor.baixar" not in por_nome
    assert por_nome["ingestor.segmentar"].attributes["pipeline.frases"] == 2

def test_span_de_download_marca_paywall(spans, monkeypatch):
    monkeypatch.setattr(ingestor, "fetch_page", lambda url: None)
    run_node("https://exemplo-jornal.com.br/materia-fechada")
    baixar = next(s for s in spans.get_finished_spans() if s.name == "ingestor.baixar")
    assert baixar.attributes["pipeline.ok"] is False

# test_evidence_agente.py — caso do mamão com os dublês (mamao_fakes + patch_agent)
def test_spans_do_evidencias_no_caso_do_mamao(spans, monkeypatch):
    ...
    attrs = {s.name: s.attributes for s in spans.get_finished_spans()}
    assert attrs["evidencias.busca"]["pipeline.frases"] == 6
    assert attrs["evidencias.busca"]["openinference.span.kind"] == "RETRIEVER"
    assert attrs["evidencias.termos_chave"]["pipeline.candidatas"] == 2
    assert attrs["evidencias.termos_chave"]["pipeline.aprovadas"] == 2
    assert attrs["evidencias.nli"]["pipeline.pares"] == 4
    assert attrs["evidencias.nli"]["pipeline.evidencias"] == 2
```

- [ ] **Step 2:** falham (sem spans).

- [ ] **Step 3:** envolver os trechos existentes com `with span(...) as s:` e gravar os atributos que só se conhecem no fim com `s.set_attribute("pipeline.<chave>", valor)`. Sem mudar nenhum retorno nem tratamento de erro dos agentes.

- [ ] **Step 4:** `pytest tests/unit/test_ingestor.py tests/unit/test_evidence_agente.py -v` passa; suíte verde.

- [ ] **Step 5:** commit `feat: Spans das etapas do Ingestor e do Agente de Evidências`.

---

### Task 4: Execução medida do grafo

**Files:**
- Create: `src/medicao.py`
- Test: `tests/unit/test_medicao.py`

**Interfaces:**
- Consumes: `observabilidade.span`; `graph.RAMOS`; `PipelineState`.
- Produces:
  - `@dataclass Execucao`, com os campos `estado: PipelineState`, `fim_por_no: dict[str, float]` (segundos desde o início até o nó terminar), `duracao_por_no: dict[str, float]`, `total: float` e `trace_id: str | None` (32 hex; `None` quando o tracing está desligado, ou seja, quando o contexto do span é inválido).
  - `executar(grafo, estado_inicial: dict, relogio: Callable[[], float] = time.monotonic, ao_terminar_no: Callable[[str, float], None] | None = None) -> Execucao`. Itera `grafo.stream(estado_inicial)`, junta as atualizações (os `warnings` são somados, os demais campos sobrescritos) e chama `ao_terminar_no(no, fim)` a cada evento. No fim, valida com `PipelineState.model_validate`. Tudo roda dentro do span raiz `analise`, com os atributos `entrada` (`"url"` ou `"texto"`), `frases`, `avisos` e `total_s`.
  - `trace_id_de(contexto: SpanContext) -> str | None`: devolve 32 hex, ou `None` se `not contexto.is_valid`. O app (Task 5) troca essa função nos testes.
  - O relógio é lido uma vez no início e uma vez a cada evento do stream; `total` = fim do último nó.
  - Regra das durações (as etapas são sequenciais e os ramos, paralelos): `ingestor` = fim do ingestor; cada ramo = seu fim − fim do ingestor; `sintetizador` = seu fim − o maior fim entre os ramos. Um nó que não apareceu no stream fica fora dos dicionários.

- [ ] **Step 1: Testes que falham**, com um grafo falso (classe com `stream(estado)` que devolve eventos fixos) e um relógio falso (iterador de tempos):

```python
def test_junta_o_estado_e_soma_os_avisos(): ...
    # eventos: ingestor (segments, warnings ["ingestor: x"]), agente_texto (warnings ["texto: y"]), ...
    # execucao.estado.warnings == ["ingestor: x", "texto: y"]

def test_duracoes_respeitam_o_paralelismo():
    # relógio: início 0; ingestor termina em 1; socratico 4, evidencias 6, texto 9; sintetizador 12
    assert e.duracao_por_no == {"ingestor": 1, "agente_socratico": 3, "agente_evidencias": 5,
                                "agente_texto": 8, "sintetizador": 3}
    assert e.total == 12

def test_avisa_cada_no_que_termina(): ...  # ao_terminar_no recebe ("ingestor", 1.0), ... na ordem

def test_span_raiz_analise_com_atributos(spans):
    # executar com o grafo real e os modelos falsos (tests/modelos_falsos.ligar_falsos)
    raiz = next(s for s in spans.get_finished_spans() if s.name == "analise")
    assert raiz.parent is None and raiz.attributes["pipeline.entrada"] == "texto"
    assert e.trace_id == format(raiz.context.trace_id, "032x")
    assert all(s.context.trace_id == raiz.context.trace_id
               for s in spans.get_finished_spans() if s.name.startswith("no."))

def test_trace_id_de_contexto_invalido_e_none():
    # tracing desligado = contexto inválido; testado na função pura, porque o provider de testes é global
    assert medicao.trace_id_de(trace.INVALID_SPAN_CONTEXT) is None
```

- [ ] **Step 2:** falham (`ImportError`).

- [ ] **Step 3:** implementar `src/medicao.py`, incluindo `trace_id_de(contexto) -> str | None`.

- [ ] **Step 4:** `pytest tests/unit/test_medicao.py -v` passa; suíte verde.

- [ ] **Step 5:** commit `feat: Execução medida do grafo: estado, duração por nó e span raiz da análise`.

---

### Task 5: Tempos e trace no Streamlit

**Files:**
- Modify: `app/app.py`
- Test: `tests/unit/test_app.py`

**Interfaces:**
- Consumes: `medicao.executar`, `Execucao` (Task 4); `observabilidade.configurar_tracing` (Task 1).
- Produces (o que a tela mostra):
  - Durante a análise, dentro do `st.status`: `Nó concluído: **<nó>** (<s> s)`, uma linha por nó.
  - Depois, um `st.expander("Tempos por etapa")` com `st.table` nas colunas `nó`, `segundos` e uma linha `total`.
  - Com `trace_id`: `st.caption` com o ID e o link `http://localhost:6006` (ou o valor de `PHOENIX_COLLECTOR_ENDPOINT`), texto "Ver o trace no Phoenix". Sem `trace_id`: nada.
  - `configurar_tracing()` é chamado uma vez por processo, via função decorada com `@st.cache_resource`.

- [ ] **Step 1: Testes que falham** (com `falsos.ligar_falsos(monkeypatch)`):

```python
def test_app_mostra_tempos_por_etapa(monkeypatch):
    at = analisar(falsos.TEXTO_LIVRE)
    assert any(e.label == "Tempos por etapa" for e in at.expander)
    tabela = at.table[-1].value
    assert list(tabela["nó"]) == ["ingestor", "agente_evidencias", "agente_texto",
                                  "agente_socratico", "sintetizador", "total"]

def test_app_mostra_tempos_sem_trace_quando_tracing_desligado(monkeypatch):
    monkeypatch.delenv("PHOENIX_TRACING", raising=False)
    at = analisar(falsos.TEXTO_LIVRE)
    assert not any("Phoenix" in c.value for c in at.caption)

def test_app_mostra_o_trace_quando_ha_trace_id(monkeypatch):
    # monkeypatch medicao.trace_id_de → "0af7651916cd43dd8448eb211c80319c"
    assert any("0af7651916cd43dd8448eb211c80319c" in c.value and "Phoenix" in c.value for c in at.caption)
```

A ordem da tabela segue a ordem da topologia (`ingestor`, `graph.RAMOS`, `sintetizador`), não a ordem de término.

- [ ] **Step 2:** falham.

- [ ] **Step 3:** trocar o laço manual de `stream` do `app.py` por `medicao.executar(sistema_multiagente, estado_inicial, ao_terminar_no=...)` e usar `execucao.estado` no lugar do `final_state` montado à mão. Manter todo o resto da tela.

- [ ] **Step 4:** `pytest tests/unit/test_app.py -v` passa; suíte verde.

- [ ] **Step 5: Verificação manual com o Phoenix real.** Abra três terminais.
  - No primeiro, `phoenix serve` e espere `http://localhost:6006`.
  - No segundo, `PHOENIX_TRACING=1 LLM_MODEL=<id> streamlit run app/app.py` e analise o caso do Carrefour.
  - No Phoenix, projeto `grupo1-resia`, o trace precisa ter a raiz `analise`, os 5 spans `no.*`, as chamadas `ChatOpenAI` debaixo de `no.texto`, `no.socratico` e `no.sintetizador`, e os spans `ingestor.*` e `evidencias.*`, com tokens e latência.
  - Anote o resultado no PR.

- [ ] **Step 6:** commit `feat: Streamlit mostra os tempos por etapa e o trace da análise no Phoenix`.

---

### Task 6: Relatório de latência p50/p95

**Files:**
- Create: `eval/medir_latencia.py`, `eval/entradas_latencia.json`
- Test: `tests/unit/test_medir_latencia.py`

**Interfaces:**
- Consumes: `medicao.executar`, `Execucao`; `graph.sistema_multiagente`; `initial_state`; `observabilidade.configurar_tracing`.
- Produces:
  - `percentil(valores: list[float], p: float) -> float`, pelo método do posto mais próximo (nearest-rank): ordena, posto = `ceil(p/100 · n)`, devolve `valores[posto − 1]`. Levanta `ValueError("percentil de uma lista vazia")`.
  - `resumir(execucoes: list[Execucao]) -> dict`, no formato `{"total": {"p50", "p95", "n"}, "por_no": {nó: {"p50", "p95", "n"}}}`.
  - `medir(grafo, entradas: list[dict], repeticoes: int, aquecimento: int) -> list[Execucao]`. Cada entrada tem `nome` e `texto`. Antes de medir, roda `aquecimento` análises descartadas com a primeira entrada; depois, `repeticoes` vezes cada entrada.
  - CLI: `python eval/medir_latencia.py [--entradas eval/entradas_latencia.json] [--repeticoes 3] [--aquecimento 1] [--saida eval/resultados/latencia_<AAAA-MM-DD>.json]`. Grava `{"data", "modelo": LOCAL_MODEL, "maquina": platform.platform(), "resumo", "execucoes": [{"entrada", "total", "duracao_por_no", "avisos"}]}`, imprime p50/p95 por nó e total e marca se o p50 total cumpre a meta de 180 s.
  - `eval/entradas_latencia.json`: o caso do mamão (`tests/fixtures/caso_mamao_dengue/00_entrada.json`) e o cenário do Carrefour (o texto de corrente usado no teste real de 06/10).

- [ ] **Step 1: Testes que falham**

```python
def test_percentil_posto_mais_proximo():
    assert percentil([5, 1, 3, 2, 4], 50) == 3
    assert percentil(list(range(1, 21)), 95) == 19

def test_percentil_com_um_valor():
    assert percentil([42.0], 50) == percentil([42.0], 95) == 42.0

def test_percentil_sem_valores():
    with pytest.raises(ValueError, match="lista vazia"):
        percentil([], 50)

def test_resumir_por_no_e_total(): ...  # duas Execucao montadas à mão → p50, p95 e n por nó e total

def test_aquecimento_nao_entra_na_medicao(): ...
    # grafo falso que conta chamadas de stream: medir(..., entradas=2, repeticoes=2, aquecimento=1)
    # → 5 chamadas ao grafo, 4 Execucao devolvidas
```

- [ ] **Step 2:** falham.

- [ ] **Step 3:** implementar. `main()` chama `configurar_tracing()`, para que a rodada também apareça no Phoenix quando ele estiver ligado.

- [ ] **Step 4:** `pytest tests/unit/test_medir_latencia.py -v` passa; suíte verde. Com o LM Studio e o índice disponíveis, rodar `LLM_MODEL=<id> python eval/medir_latencia.py --repeticoes 3` e conferir o JSON em `eval/resultados/`.

- [ ] **Step 5: Documentação.**
  - No `README.md`, uma seção "Observabilidade": instalar, `phoenix serve`, `PHOENIX_TRACING=1`, o que aparece no trace (raiz, nós, LLM, etapas) e o script de latência.
  - No Manual §5.4, linha Observabilidade, acrescentar "Implementado com Phoenix local: `src/observabilidade.py`; latência p50/p95 em `eval/medir_latencia.py`".
  - Commit `feat: Relatório de latência p50/p95 por nó e ponta a ponta; documentação de observabilidade`.
