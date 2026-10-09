# Desempenho e correção dos agentes com LLM — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduzir o tempo do Agente de Texto, do Sintetizador e do Agente Socrático, garantindo que o texto que eles produzem fique preso ao conteúdo da notícia.

**Architecture:** O Sintetizador se divide em dois nós:
- `agente_argumento`: LLM com saída JSON estruturada, que escreve só o "efeito" de cada marcador;
- `sintetizador`: só código, que monta o dossiê.

O Socrático passa a rodar depois do Agente de Texto, em paralelo com o `agente_argumento`, recebendo um resumo da notícia. O Agente de Texto ganha lotes em paralelo e explicações curtas. Os clientes do LLM ganham `max_tokens`, temperatura baixa e decodificação especulativa opcional (`LLM_DRAFT_MODEL`). Cada mudança é medida contra uma linha de base com `eval/medir_latencia.py`.

**Tech Stack:** Python 3.10, LangGraph, langchain-openai (`ChatOpenAI` → LM Studio em `localhost:1234`), Pydantic, Streamlit, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-desempenho-agentes-design.md`

## Global Constraints

- Branch `feat/desempenho-agentes`, criada a partir da `feat/dossie-final`. O PR vai para a `develop` depois que o PR do dossiê final for mesclado.
- Nenhuma dependência nova; tem que rodar no Python 3.10 (CI).
- O `PipelineState` ganha exatamente um campo, `argument: list[str] | None`. O `initial_state` muda no mesmo commit (regra do topo de `src/state.py`).
- Testes unitários e de contrato nunca falam com o LM Studio, o ChromaDB, o BGE-M3 ou o NLI.
- Textos visíveis ao leitor em pt-BR e copiados exatamente do spec (linhas do argumento, de omitidos e de juízo de valor).
- Medições sempre na mesma máquina e com o mesmo modelo: `LLM_MODEL=qwen/qwen2.5-vl-7b` nesta máquina.
- Suíte rápida `venv/bin/python -m pytest tests/unit tests/contract -q` verde ao fim de cada tarefa.
- Commits no padrão do repositório (`feat:`, `fix:`, `perf:`, `test:`, `docs:`), em português.

## Review Focus

1. **Notícia longa (≈ 48 frases, dezenas de marcadores):** "Como o texto argumenta" mostra no máximo 8 marcadores, mais uma linha de omitidos e uma única linha de juízo de valor. O teste fica na Task 5.
2. **Agente de Texto falhou (`text_report` None):**
   - o argumento sai `SEM_ESTRUTURA` sem chamar o modelo;
   - o Socrático usa as frases em ordem;
   - o dossiê é montado.
   Os testes ficam nas Tasks 3 e 4.
3. **Modelo devolve índice inexistente, índice repetido ou lista vazia:** é ignorado, e os marcadores ficam sem efeito, sem quebrar. O teste fica na Task 5.
4. **Texto colado:** o título `Texto Inserido Manualmente` nunca entra no resumo do Socrático. O teste fica na Task 4.
5. **`LLM_DRAFT_MODEL` vazio:** nenhuma chave extra vai na requisição. Definido, vai `draft_model`. O teste fica na Task 2.

---

### Task 1: Linha de base — notícia longa e avisos na medição

**Files:**
- Modify: `eval/entradas_latencia.json` (nova entrada `noticia_longa`)
- Modify: `eval/medir_latencia.py` (`resumir` passa a contar avisos)
- Create: `eval/resultados/latencia_2026-10-09_base.json` (gerado pela medição)
- Test: `tests/unit/test_medir_latencia.py`

**Interfaces:**
- Produces: `resumir(execucoes) -> dict` com a chave nova `"avisos": {"execucoes_com_aviso": int, "por_prefixo": dict[str, int]}`. O prefixo é o texto antes do primeiro `:` de cada aviso em `e.estado.warnings`.

- [ ] **Step 1: Teste que falha**

```python
def test_resumir_conta_avisos_por_prefixo():
    execs = [execucao(avisos=["texto: saída inválida após 1 retry", "sintetizador: síntese livre reprovada"]),
             execucao(avisos=[]), execucao(avisos=["texto: timeout"])]
    assert resumir(execs)["avisos"] == {"execucoes_com_aviso": 2, "por_prefixo": {"texto": 2, "sintetizador": 1}}
```

Monte o helper `execucao(avisos=...)` com o `Execucao` de `src/medicao.py` e um `PipelineState` de `initial_state(...)`, seguindo o padrão do arquivo.

- [ ] **Step 2: Rodar e ver falhar** — `venv/bin/python -m pytest tests/unit/test_medir_latencia.py -q` → FAIL (`KeyError: 'avisos'`)
- [ ] **Step 3: Implementar a contagem em `resumir` e criar a entrada `noticia_longa`.** O texto da entrada segue o spec ("Medição e aceitação"): gere-o uma vez com um script descartável e grave o texto literal no JSON.
- [ ] **Step 4: Rodar e ver passar** — o mesmo comando → PASS
- [ ] **Step 5: Medir a linha de base, com o LM Studio no ar e antes de qualquer outra tarefa**

Run: `LLM_MODEL=qwen/qwen2.5-vl-7b venv/bin/python eval/medir_latencia.py --repeticoes 2 --saida eval/resultados/latencia_2026-10-09_base.json`
Expected: o arquivo existe, com `resumo.total`, `resumo.por_no` e `resumo.avisos` para as três entradas.

- [ ] **Step 6: Commit**

```bash
git add eval/entradas_latencia.json eval/medir_latencia.py eval/resultados/latencia_2026-10-09_base.json tests/unit/test_medir_latencia.py
git commit -m "test: Linha de base de latência com notícia longa e contagem de avisos"
```

---

### Task 2: Clientes do LLM — `max_tokens`, temperatura e modelo rascunho

**Files:**
- Modify: `src/services/llm.py`
- Test: `tests/unit/test_services_llm.py`

**Interfaces:**
- Produces:
  - `modelo_rascunho() -> str | None`: lê `LLM_DRAFT_MODEL` na hora da chamada; vazio ou só espaços dá `None`.
  - `_cliente(temperatura: float, max_tokens: int) -> ChatOpenAI`: com rascunho, `extra_body={"draft_model": <nome>}`; sem rascunho, `extra_body` fica no padrão.
  - Os clientes `llm_texto` (0, 1000), `llm_sintetizador` (0, 400) e `llm_socratico` (0.2, 300) usam os valores do spec.

- [ ] **Step 1: Testes que falham**

```python
def test_valores_dos_clientes():
    assert (llm.llm_texto.temperature, llm.llm_texto.max_tokens) == (0, 1000)
    assert (llm.llm_sintetizador.temperature, llm.llm_sintetizador.max_tokens) == (0, 400)
    assert (llm.llm_socratico.temperature, llm.llm_socratico.max_tokens) == (0.2, 300)

def test_sem_rascunho_nao_envia_draft_model(monkeypatch):
    monkeypatch.delenv("LLM_DRAFT_MODEL", raising=False)
    assert not (llm._cliente(0, 100).extra_body or {}).get("draft_model")

def test_com_rascunho_envia_draft_model(monkeypatch):
    monkeypatch.setenv("LLM_DRAFT_MODEL", " qwen2.5-0.5b-instruct ")
    assert llm._cliente(0, 100).extra_body == {"draft_model": "qwen2.5-0.5b-instruct"}
```

- [ ] **Step 2: Rodar e ver falhar** — `venv/bin/python -m pytest tests/unit/test_services_llm.py -q` → FAIL
- [ ] **Step 3: Implementar.** Atualize o comentário de `TIMEOUT_S` se ele mencionar valores que mudaram, e documente `LLM_DRAFT_MODEL` no docstring do módulo.
- [ ] **Step 4: Suíte rápida** — `venv/bin/python -m pytest tests/unit tests/contract -q` → PASS
- [ ] **Step 5: Commit** — `perf: Limite de tokens, temperatura baixa no Socrático e modelo rascunho opcional`

---

### Task 3: Grafo novo — nó `agente_argumento`, Sintetizador só monta, Socrático depois do Texto

**Files:**
- Modify: `src/state.py` (campo `argument` + `initial_state`)
- Modify: `src/agents/synthesizer.py` (separa geração e montagem)
- Modify: `src/graph.py` (topologia, `ORDEM_NOS`, `PREDECESSORES`; sai `RAMOS`)
- Modify: `src/medicao.py` (`duracoes` por predecessores)
- Modify: `app/app.py` (tabela de tempos usa `ORDEM_NOS`)
- Modify: `docs/agents/sintetizador.md` e a seção 3.3 do Manual (campo novo e nó novo)
- Test: `tests/unit/test_graph.py`, `tests/unit/test_medicao.py`, `tests/unit/test_synthesizer.py`, `tests/contract/test_synthesizer_contract.py`, `tests/unit/test_state.py`

**Interfaces:**
- Produces:
  - `PipelineState.argument: list[str] | None`: linhas da seção, sem o título.
  - Em `src/agents/synthesizer.py`:
    - `argumento_node(state) -> dict`: devolve `{"argument": list[str]}`, mais `"warnings"` quando há problema próprio.
    - `argumento_fallback(state) -> dict`: `{"argument": <linhas do fallback em código>}`.
    - `sintetizador_node(state) -> dict`: devolve `{"dossier": str}` e nunca chama LLM. Usa `state.argument` ou, se for `None`, `argumento_fallback(state)["argument"]`.
    - `dossie_sem_modelo` deixa de existir.
  - Em `src/graph.py`:
    - `ORDEM_NOS = ("ingestor", "agente_evidencias", "agente_texto", "agente_argumento", "agente_socratico", "sintetizador")`
    - `PREDECESSORES: dict[str, tuple[str, ...]]`, conforme o grafo do spec.
  - `medicao.duracoes(fim_por_no)`: duração de um nó = seu fim − o maior fim entre os predecessores presentes (0 sem predecessor).
- Nesta tarefa, o `agente_argumento` usa a síntese livre que já existe: `secao_argumento` sem o título, com os mesmos guardrails. A Task 5 troca pela saída estruturada.
- Nós:
  - `agente_argumento`: `proteger("argumento", argumento_node, TIMEOUT_SINTETIZADOR_S, {"argument": None}, recuperar=argumento_fallback)`.
  - `sintetizador`: `proteger("sintetizador", sintetizador_node, TIMEOUT_SINTETIZADOR_S, {"dossier": DOSSIE_INDISPONIVEL})`.
  - Fan-in: `add_edge(["agente_evidencias", "agente_argumento", "agente_socratico"], "sintetizador")`.

- [ ] **Step 1: Testes que falham**

```python
# tests/unit/test_graph.py
def test_topologia_socratico_e_argumento_depois_do_texto():
    arestas = {(a.source, a.target) for a in sistema_multiagente.get_graph().edges}
    assert {("agente_texto", "agente_argumento"), ("agente_texto", "agente_socratico"),
            ("ingestor", "agente_texto"), ("ingestor", "agente_evidencias")} <= arestas
    assert ("ingestor", "agente_socratico") not in arestas

def test_sintetizador_roda_uma_vez_com_tudo_pronto(...):   # use os falsos de ligar_falsos e conte as chamadas
    ...
    assert chamadas_sintetizador == 1
    assert out["dossier"].startswith(dossie.TITULO_RESUMO) and out["argument"]

def test_argumento_estourado_vira_fallback_e_o_dossie_sai():   # timeout pequeno via construir_grafo(timeout_sintetizador=...)
    ...
    assert "argumento: timeout" in out["warnings"] and dossie.TITULO_ARGUMENTO in out["dossier"]

# tests/unit/test_medicao.py
def test_duracoes_seguem_os_predecessores():
    fim = {"ingestor": 1.0, "agente_evidencias": 2.0, "agente_texto": 10.0,
           "agente_argumento": 15.0, "agente_socratico": 14.0, "sintetizador": 15.1}
    assert duracoes(fim) == pytest.approx({"ingestor": 1.0, "agente_evidencias": 1.0, "agente_texto": 9.0,
                                           "agente_argumento": 5.0, "agente_socratico": 4.0, "sintetizador": 0.1})

# tests/unit/test_synthesizer.py
def test_sem_text_report_argumento_nao_chama_o_modelo(monkeypatch):     # Review Focus 2
    falso = falsos.SintetizadorFalso().instalar(monkeypatch)
    assert synthesizer.argumento_node(estado_mamao(text_report=None)) == {"argument": [dossie.SEM_ESTRUTURA]}
    assert falso.prompts == []
```

Contrato:
- `sintetizador_node` devolve exatamente `{"dossier"}`;
- `argumento_node` com o modelo desligado devolve `{"argument", "warnings"}`, com `warnings == [WARN_MODELO_INDISPONIVEL]`.

- [ ] **Step 2: Rodar e ver falhar** — `venv/bin/python -m pytest tests/unit tests/contract -q` → FAIL nos testes novos
- [ ] **Step 3: Implementar.** Ajuste os testes antigos que dependem de `RAMOS`, de `dossie_sem_modelo` ou dos avisos vindos do `sintetizador_node`, e mantenha a intenção de cada um.
- [ ] **Step 4: Suíte rápida** → PASS
- [ ] **Step 5: Commit** — `perf: Socrático e síntese do argumento rodam em paralelo depois do Agente de Texto`

---

### Task 4: Socrático recebe um resumo da notícia

**Files:**
- Modify: `src/agents/ingestor.py` (constante `TITULO_TEXTO_COLADO = "Texto Inserido Manualmente"`, usada no lugar da string literal)
- Modify: `src/agents/socratic.py`
- Test: `tests/unit/test_socratic.py`

**Interfaces:**
- Produces:
  - `resumo_para_socratico(state: PipelineState) -> str`, com `LIMITE_PALAVRAS_SOCRATICO = 400` e `FRASES_INICIAIS_SOCRATICO = 3`, conforme o spec.
  - `socratic_node(state)`: monta a mensagem com o resumo (`analisar_texto(resumo, clean_text)`, em que o primeiro é a entrada do modelo e o segundo o contexto do G4) e valida o G4 contra `state.clean_text`.

- [ ] **Step 1: Testes que falham**

```python
def test_resumo_titulo_inicio_e_factuais(): ...
    # estado com título "Chá cura dengue", 8 frases (s01..s08), s07 factual e as demais valor
    # → "Chá cura dengue\n" + s01 s02 s03 s07 (unidas por espaço, na ordem)

def test_resumo_sem_titulo_de_texto_colado(): ...            # Review Focus 4
    assert not resumo_para_socratico(estado(title="Texto Inserido Manualmente")).startswith("Texto Inserido")

def test_resumo_sem_text_report_usa_frases_em_ordem_ate_o_limite(): ...
    # 60 frases de 10 palavras → 40 frases (400 palavras), cortado em fim de frase

def test_g4_valida_contra_a_noticia_inteira(monkeypatch): ...
    # pergunta com nome que está só no fim da notícia (fora do resumo) → aceita
```

- [ ] **Step 2: Rodar e ver falhar** → FAIL
- [ ] **Step 3: Implementar.** Ajuste os testes que chamam `analisar_texto` com um argumento só.
- [ ] **Step 4: Suíte rápida** → PASS
- [ ] **Step 5: Commit** — `perf: Socrático lê título, abertura e frases factuais em vez da notícia inteira`

---

### Task 5: Argumento com saída estruturada

**Files:**
- Modify: `src/agents/dossie.py` (seleção de marcadores e linhas do spec)
- Modify: `src/agents/synthesizer.py` (`argumento_node` com JSON)
- Rewrite: `src/prompts/sintetizador_sistema.md`
- Test: `tests/unit/test_dossie.py`, `tests/unit/test_synthesizer.py`, `tests/modelos_falsos.py` (`RESPOSTA_SINTETIZADOR` vira JSON)

**Interfaces:**
- Consumes: `problema_da_sintese(texto, frases)` (já existe; aplicado a cada efeito), `texto_seguro`, `escapar_markdown`, `encurtar`.
- Produces:
  - Em `src/agents/dossie.py`:
    - `MAX_MARCADORES_ARGUMENTO = 8`
    - `selecionar_marcadores(markers: list[TextMarker], limite: int = MAX_MARCADORES_ARGUMENTO) -> list[TextMarker]`
    - `linha_marcador(m: TextMarker, efeito: str | None) -> str`
    - `linha_marcadores_omitidos(n: int) -> str`
    - `linha_juizo_valor(frases: list[Segment]) -> str | None`
    - `linhas_argumento(state: PipelineState, efeitos: dict[int, str]) -> list[str]`: monta a seção. Os índices de `efeitos` são as posições, a partir de 1, em `selecionar_marcadores(...)`. É também o fallback, com `efeitos={}`.
  - Em `src/agents/synthesizer.py`:
    - `class Efeito(BaseModel): marcador: int; efeito: str`
    - `class RespostaArgumento(BaseModel): efeitos: list[Efeito]`
    - `efeitos_validos(resposta: RespostaArgumento, n_marcadores: int, frases: list[str]) -> tuple[dict[int, str], str | None]`: devolve os efeitos aprovados e o primeiro problema.
  - O prompt de sistema exige JSON no formato do spec. A mensagem de retry, cópia exata: `f"O efeito do marcador {i} foi rejeitado. {problema}"`.

- [ ] **Step 1: Testes que falham**

```python
# tests/unit/test_dossie.py
def test_selecao_garante_um_por_tipo_e_mantem_a_ordem_do_texto():
    tipos = ["urgencia_artificial"] * 9 + ["generalizacao", "apelo_autoridade"]
    markers = [marcador(t, f"s{i:02d}") for i, t in enumerate(tipos, start=1)]
    escolhidos = dossie.selecionar_marcadores(markers)
    assert len(escolhidos) == 8 and {"generalizacao", "apelo_autoridade"} <= {m.type for m in escolhidos}
    assert [m.segment_id for m in escolhidos] == sorted(m.segment_id for m in escolhidos)

def test_linhas_do_spec():
    assert dossie.linha_marcadores_omitidos(1) == "- Outro trecho repete esses padrões e não foi listado."
    assert dossie.linha_marcadores_omitidos(3) == "- Outros 3 trechos repetem esses padrões e não foram listados."
    assert dossie.linha_juizo_valor(frases(["A.", "B."])) == '- Juízo de valor: "A." e "B." são opiniões e não foram checadas.'
    assert dossie.linha_juizo_valor(frases(["A.", "B.", "C.", "D."])) == (
        '- Juízo de valor: 4 frases são opiniões e não foram checadas, como "A.", "B." e mais 2.')

def test_noticia_longa_tem_no_maximo_8_marcadores_e_uma_linha_de_juizo():   # Review Focus 1
    linhas = dossie.linhas_argumento(estado_com(n_marcadores=20, n_opinioes=12), efeitos={})
    assert len(linhas) == 8 + 1 + 1 and linhas[-2].startswith("- Outros 12 trechos") and linhas[-1].startswith("- Juízo de valor: 12 frases")

# tests/unit/test_synthesizer.py
def test_mamao_com_efeitos_estruturados(monkeypatch):
    resposta = {"efeitos": [{"marcador": i, "efeito": "pede atenção imediata."} for i in range(1, 7)]}
    falsos.SintetizadorFalso(json.dumps(resposta)).instalar(monkeypatch)
    linhas = synthesizer.argumento_node(estado_mamao())["argument"]
    assert linhas[0] == '- Urgência: "URGENTE" pede atenção imediata.'
    assert linhas[-1] == ('- Juízo de valor: "Não existe nada melhor do que a natureza para cuidar da nossa saúde." e '
                          '"Compartilhe com todos antes que apaguem este vídeo!" são opiniões e não foram checadas.')

def test_indice_invalido_ou_repetido_e_ignorado_sem_retry(monkeypatch):     # Review Focus 3
    ruins = {"efeitos": [{"marcador": 99, "efeito": "x x x"}, {"marcador": 1, "efeito": "a."}, {"marcador": 1, "efeito": "b."}]}
    falso = falsos.SintetizadorFalso(json.dumps(ruins)).instalar(monkeypatch)
    saida = synthesizer.argumento_node(estado_mamao())
    assert saida["argument"][0] == '- Urgência: "URGENTE" a.' and saida["argument"][1] == '- Generalização: "os médicos estão escondendo"'
    assert "warnings" not in saida and len(falso.prompts) == 1

def test_lista_vazia_deixa_todos_sem_efeito_sem_retry(monkeypatch):
    falso = falsos.SintetizadorFalso(json.dumps({"efeitos": []})).instalar(monkeypatch)
    saida = synthesizer.argumento_node(estado_mamao())
    assert saida["argument"][0] == '- Urgência: "URGENTE"' and len(falso.prompts) == 1

def test_efeito_com_termo_de_fora_vai_ao_retry_e_cai_sem_efeito(monkeypatch):
    ruim = {"efeitos": [{"marcador": 1, "efeito": "segundo a OMS, exagera."}]}
    falso = falsos.SintetizadorFalso(json.dumps(ruim), json.dumps(ruim)).instalar(monkeypatch)
    saida = synthesizer.argumento_node(estado_mamao())
    assert saida["argument"][0] == '- Urgência: "URGENTE"' and saida["warnings"] == [synthesizer.WARN_GUARDRAILS]
    assert falso.prompts[1].endswith("O efeito do marcador 1 foi rejeitado. Seu texto mencionou 'oms', que não aparece na notícia.")

def test_efeito_com_cifrao_e_escapado(monkeypatch): ...
    # efeito "custa R$ 10." → a linha termina com "custa R\\$ 10."
```

Só efeito **reprovado** (vazio, veredito, link, G3, G4) provoca a nova tentativa. Índice inexistente ou repetido é ignorado; marcador sem efeito fica sem efeito, sem nova tentativa e sem aviso. No teste do índice repetido, vale o primeiro efeito válido (`a.`). Confirme a frase de cada marcador do mamão no `05_sintetizador_entrada.json`.

- [ ] **Step 2: Rodar e ver falhar** → FAIL
- [ ] **Step 3: Implementar.** A chamada do modelo usa `response_format` `json_schema` estrito, como o Agente de Texto. O código antigo da síntese livre sai: `limpar_resposta`, a montagem de bullets livres e a regra 3 do prompt (juízo de valor agora é código). Ajuste os testes que dependiam dele.
- [ ] **Step 4: Suíte rápida** → PASS
- [ ] **Step 5: Commit** — `perf: Argumento com saída estruturada; trecho literal escrito pelo código`

---

### Task 6: Agente de Texto — lotes em paralelo e explicação curta

**Files:**
- Modify: `src/agents/text_analysis.py`
- Modify: `src/prompts/texto_sistema.md` (regra de `explanation`), `src/prompts/texto_exemplos.json` (explicações com ≤ 10 palavras)
- Test: `tests/unit/test_text_analysis.py`

**Interfaces:**
- Produces: `paralelismo() -> int`: lê `TEXTO_PARALELISMO` a cada chamada; valor inválido ou < 1 dá 2. O `texto_node` usa `ThreadPoolExecutor(max_workers=paralelismo())`. A regra de parar quando o modelo cai continua igual.
- Regra no prompt (cópia exata, substituindo a atual): `` - `explanation` tem no máximo 10 palavras e descreve um padrão para o leitor observar, nunca uma acusação.``

- [ ] **Step 1: Testes que falham**

```python
def test_lotes_rodam_em_paralelo_e_mantem_a_ordem(monkeypatch):
    monkeypatch.setenv("TEXTO_PARALELISMO", "2")
    # 45 frases → 3 lotes; o falso dorme 0,05 s e registra o pico de chamadas simultâneas
    ...
    assert pico == 2
    assert [st.segment_id for st in out["text_report"].statements] == [f"s{i:02d}" for i in range(1, 46)]

@pytest.mark.parametrize("valor, esperado", [("1", 1), ("3", 3), ("0", 2), ("x", 2), ("", 2)])
def test_paralelismo(monkeypatch, valor, esperado):
    monkeypatch.setenv("TEXTO_PARALELISMO", valor)
    assert paralelismo() == esperado

def test_explicacoes_dos_exemplos_tem_no_maximo_10_palavras():
    assert all(len(m["explanation"].split()) <= 10 for e in carregar_exemplos() for m in e["saida"]["markers"])
```

- [ ] **Step 2: Rodar e ver falhar** → FAIL
- [ ] **Step 3: Implementar.** Os testes de "modelo cai no meio" e "um lote ruim não descarta os outros" continuam passando; com 2 workers, o lote seguinte pode já estar em andamento quando o modelo cai.
- [ ] **Step 4: Suíte rápida** → PASS
- [ ] **Step 5: Commit** — `perf: Agente de Texto roda lotes em paralelo e escreve explicações curtas`

---

### Task 7: Medição final, decodificação especulativa e documentação

**Files:**
- Create: `eval/resultados/latencia_2026-10-09_final.json`, `eval/resultados/latencia_2026-10-09_rascunho.json`
- Create: `docs/agents/desempenho.md`
- Modify: `README.md` (variáveis `LLM_DRAFT_MODEL` e `TEXTO_PARALELISMO`)

- [ ] **Step 1: Medição final sem rascunho**

Run: `LLM_MODEL=qwen/qwen2.5-vl-7b venv/bin/python eval/medir_latencia.py --repeticoes 2 --saida eval/resultados/latencia_2026-10-09_final.json`
Expected:
- p50 ponta a ponta menor que em `latencia_2026-10-09_base.json` em todas as entradas;
- `avisos.execucoes_com_aviso` não maior que na linha de base.
Se alguma entrada piorar, pare e registre qual nó piorou antes de seguir.

- [ ] **Step 2: Baixar o modelo rascunho no LM Studio.** Busque `qwen2.5-0.5b-instruct` na interface ou use `lms get qwen2.5-0.5b-instruct`. Ação do usuário: confirme com ele antes de baixar.
- [ ] **Step 3: Medição com rascunho** — `LLM_DRAFT_MODEL=<id do rascunho no LM Studio>`, no mesmo comando, com `--saida eval/resultados/latencia_2026-10-09_rascunho.json`. Se o LM Studio recusar o par (vocabulário incompatível com o `qwen2.5-vl-7b`), registre a mensagem e não use rascunho.
- [ ] **Step 4: Rodar a integração com o LM Studio** — `LLM_MODEL=qwen/qwen2.5-vl-7b venv/bin/python -m pytest tests/integration -q`. Os testes do Sintetizador e do grafo sem aviso precisam passar.
- [ ] **Step 5: Escrever `docs/agents/desempenho.md`.** O documento tem três partes:
  - a tabela base × final × rascunho (p50 e p95 ponta a ponta e por nó, avisos);
  - o que mudou e por quê, apontando para o spec;
  - a recomendação sobre `LLM_DRAFT_MODEL` e `TEXTO_PARALELISMO` para quem roda localmente.
  Acrescente as duas variáveis ao README.
- [ ] **Step 6: Commit** — `docs: Medição final de desempenho dos agentes e decodificação especulativa`
