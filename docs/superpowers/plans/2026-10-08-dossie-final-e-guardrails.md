# Dossiê final e guardrails de contexto — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar o dossiê numa estrutura final coesa (Resumo → Checagens → Argumento → Perguntas → Limites → Fontes), resolver os 5 itens de `Testes e Possíveis Melhorias.md` e impedir que dados de fora da notícia entrem no dossiê (guardrails G1–G4).

**Architecture:** O dossiê continua sendo uma string Markdown montada em `src/agents/dossie.py` (partes de fato, sem LLM) e `src/agents/synthesizer.py` (síntese do LLM + guardrails). Os guardrails novos são funções puras e determinísticas: G1 no Ingestor, G2 no Agente de Evidências (antes do NLI) e G3/G4 em `src/guardrails/ancoragem.py`, usados pelo Sintetizador e pelo Socrático. O `app/app.py` da `develop` passa a mostrar só o dossiê, mais dois expanders.

**Tech Stack:** Python 3.10, LangGraph, Pydantic, Streamlit (`AppTest`), pytest, trafilatura/spaCy (Ingestor), BGE-M3 + ChromaDB + mDeBERTa (Evidências), qwen2.5-7b no LM Studio.

**Spec:** `docs/superpowers/specs/2026-10-08-dossie-final-design.md`

## Global Constraints

- Branch a partir da `develop`; o PR vai para a `develop`.
- Nenhuma dependência nova; tem que rodar no Python 3.10 (CI).
- O `PipelineState` não muda: `dossier` continua `str` e nenhum campo é criado.
- Testes unitários e de contrato nunca falam com o LM Studio, o ChromaDB, o BGE-M3 ou o NLI (`tests/conftest.py`).
- Guardrails são determinísticos: nenhum guardrail chama LLM.
- Todo texto visível ao leitor é em pt-BR, sem nomes técnicos (`adjetivacao_extrema`, `s03`) e sem os termos de `src/guardrails/veredito.py::TERMOS` nas partes escritas pelo código.
- Os textos fixos (cabeçalhos, legenda, linhas do Resumo, Fontes) são cópia exata do spec.
- Mensagens de commit no padrão do repositório (`feat:`, `fix:`, `test:`, `docs:`), em português.
- Suíte rápida: `venv/bin/python -m pytest tests/unit tests/contract -q` tem que ficar verde ao fim de cada tarefa.

## Review Focus

1. **Notícia com `$`, `*`, `_` ou `[`** ("R$ 10 e R$ 20", "*exclusivo*"): o dossiê mostra os caracteres literalmente, sem LaTeX nem itálico. O teste fica na Task 6.
2. **A mesma checagem (URL) ligada a duas frases:** um único número em "Fontes", repetido nas duas referências. O teste fica na Task 6.
3. **URL de checagem com parênteses** (`https://x.org/a_(b)`): o link `[↗ n](<url>)` funciona e `remover_citacoes_invalidas` não apaga a linha. O teste fica na Task 6.
4. **LLM cita com aspas curvas, caixa diferente ou "…" no meio do trecho:** G3 aceita quando as partes estão na notícia, sem falso positivo. O teste fica na Task 3.
5. **Nome com acento ou caixa diferente entre a notícia e o texto do LLM** ("Saúde" × "saude", "CENIPA" × "Cenipa"): G4 não reprova. O teste fica na Task 3.

---

### Task 1: G1, filtro de boilerplate no Ingestor

**Files:**
- Modify: `src/agents/ingestor.py` (constante nova + função nova; chamada dentro de `ingestor_node`, só no ramo de URL, antes de `truncate_words`)
- Test: `tests/unit/test_ingestor.py`

**Interfaces:**
- Produces: `PADROES_BOILERPLATE: tuple[re.Pattern, ...]` e `remover_boilerplate(texto: str) -> str` em `src/agents/ingestor.py`

- [ ] **Step 1: Write the failing tests**

```python
from src.agents.ingestor import remover_boilerplate

def test_remove_aviso_de_opiniao_e_chamadas_da_pagina():
    texto = ("O fogo atingiu 3 mil hectares.\n"
             "Os artigos de opinião assinados não refletem necessariamente o ponto de vista da Folha.\n"
             "Leia também: Incêndios no Pantanal batem recorde\n"
             "Receba as notícias no seu e-mail\n"
             "© 2024 Globo. Todos os direitos reservados.\n"
             "A Defesa Civil monitora a região.")
    assert remover_boilerplate(texto) == "O fogo atingiu 3 mil hectares.\nA Defesa Civil monitora a região."

def test_paragrafo_comum_que_cita_leia_no_meio_fica():
    texto = "O ministro pediu que a população leia também as orientações oficiais."
    assert remover_boilerplate(texto) == texto

def test_texto_colado_nao_passa_pelo_filtro(monkeypatch):
    # entrada sem URL: o usuário escolheu o texto, nada é removido
    estado = PipelineState(**initial_state("Leia também: a cura natural da dengue."))
    saida = ingestor_node(estado)
    assert saida["clean_text"] == "Leia também: a cura natural da dengue."
```

Adicione também um teste com `extract_text`/`fetch_page` substituídos por monkeypatch (como os testes de URL existentes no arquivo) e garanta que a URL que devolve um parágrafo de boilerplate não gera esse parágrafo em `segments`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `venv/bin/python -m pytest tests/unit/test_ingestor.py -q`
Expected: FAIL com `ImportError: cannot import name 'remover_boilerplate'`

- [ ] **Step 3: Implementar `remover_boilerplate`**

Remove as linhas (o trafilatura separa parágrafos por `\n`) que batem com algum padrão depois de passar por minúsculas e tirar acentos. Padrões, que são valores do spec:

```python
PADROES_BOILERPLATE = tuple(re.compile(p) for p in (
    r"^(leia|veja) (tambem|mais)\b",
    r"nao refletem necessariamente",
    r"todos os direitos reservados",
    r"^(receba|assine)\b.*\b(newsletter|noticias|e-?mail)\b",
    r"^siga\b.*\b(instagram|twitter|facebook|tiktok|youtube|redes sociais)\b",
    r"^clique aqui\b",
    r"^publicidade$",
))
```

Linhas vazias que sobrarem são colapsadas.

- [ ] **Step 4: Rodar e ver passar**

Run: `venv/bin/python -m pytest tests/unit/test_ingestor.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/ingestor.py tests/unit/test_ingestor.py
git commit -m "feat: Ingestor remove avisos e chamadas da página antes de segmentar (G1)"
```

---

### Task 2: G2, ancoragem lexical entre a frase e a alegação checada

**Files:**
- Modify: `src/retrieval/etapa2.py` (função nova na seção "2. Termos-chave")
- Modify: `src/retrieval/config.py` (limiar novo, ajustável por variável de ambiente)
- Modify: `src/agents/evidence.py` (`run`: filtro logo depois de `key_terms_present`, no span `evidencias.termos_chave`)
- Modify: `docs/agents/evidencias_decisoes.md` (ADR curto com os números antes e depois)
- Test: `tests/unit/test_evidence_etapa2.py`, `tests/unit/test_evidence_agente.py`

**Interfaces:**
- Produces: `content_overlap(sentence: str, texts: Iterable[str]) -> int` (quantidade de radicais `_stem(tokenize(...))` da frase presentes em `texts`) e `config.MIN_CONTENT_OVERLAP: int = int(os.getenv("EVIDENCE_MIN_CONTENT_OVERLAP", 1))`
- `run` compara a frase com `[normalize_claim(claim), review_title]`. Não usa o texto inteiro da checagem, que fala de muita coisa.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_evidence_etapa2.py
def test_frase_e_alegacao_sem_palavra_em_comum_tem_sobreposicao_zero():
    frase = "Isso resultou em acúmulo de material combustível."
    titulo = "Vídeo de aeronave tomada por névoa foi gravado na China, não na Amazônia"
    assert content_overlap(frase, [titulo]) == 0

def test_sobreposicao_tolera_flexao_e_acento():
    assert content_overlap("O chá da folha de mamão cura a dengue.", ["Chá de folhas de mamão não cura dengue"]) == 5
```

```python
# tests/unit/test_evidence_agente.py
def test_checagem_de_outro_assunto_e_descartada_mesmo_com_nli_alto(monkeypatch):
    frase = "Isso resultou em acúmulo de material combustível."
    hits = [hit("t", 0.9, "https://aosfatos.org/aeronave", claim_reviewed="Vídeo mostra aeronave tomada por névoa na Amazônia",
                review_title="Vídeo de aeronave tomada por névoa foi gravado na China, não na Amazônia")]
    output, classify = _run_one(monkeypatch, frase, hits, default=ENTAILMENT)
    assert output["evidence"] == []
    assert classify.calls == []          # descartada antes do NLI

def test_padrao_do_limiar_de_sobreposicao():
    assert config.MIN_CONTENT_OVERLAP == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `venv/bin/python -m pytest tests/unit/test_evidence_etapa2.py tests/unit/test_evidence_agente.py -q`
Expected: FAIL (`content_overlap` não existe)

- [ ] **Step 3: Implementar `content_overlap`, o limiar e o filtro em `run`**

Registre no span `evidencias.termos_chave` o atributo `pipeline.sem_ancoragem` com quantas candidatas caíram nesse filtro.

- [ ] **Step 4: Rodar a suíte do Evidências e ajustar os testes sintéticos**

Run: `venv/bin/python -m pytest tests/unit -q -k evidence`
Expected: os testes novos passam. Os testes antigos que usam frase e alegação sem nenhuma palavra em comum ("a frase da notícia." × "a alegação 3") passam a falhar. Corrija o **dado de teste**, fazendo a alegação sintética compartilhar uma palavra com a frase (ex.: "a alegação 3 da notícia"). Não desligue o guardrail nos testes.

- [ ] **Step 5: Calibrar no gold set (precisa de `chroma_data/` e dos modelos locais)**

Run, antes e depois da mudança e na mesma máquina: `venv/bin/python eval/avaliar_evidencias.py avaliar --split todos --salvar`
Expected: `casamento_errado.evidencias` ≤ 4 (o valor de 03/10) e `cobertura.acertos` igual ao da rodada anterior à mudança.
- Se a cobertura cair, rode de novo comparando também com `get_checagem_texts(url)`.
- Se ainda cair, deixe o padrão em `0` (guardrail desligado) e registre isso no ADR.
- Registre os dois resultados no ADR de `docs/agents/evidencias_decisoes.md`.

- [ ] **Step 6: Commit**

```bash
git add src/retrieval/etapa2.py src/retrieval/config.py src/agents/evidence.py tests/unit/test_evidence_*.py docs/agents/evidencias_decisoes.md eval/resultados/evidencias_*.json
git commit -m "feat: Evidências descarta checagem sem palavra em comum com a frase (G2)"
```

---

### Task 3: G3 e G4, módulo de ancoragem no contexto

**Files:**
- Create: `src/guardrails/ancoragem.py`
- Test: `tests/unit/test_guardrails.py`

**Interfaces:**
- Consumes: `name_groups`, `tokenize`, `_stem`, `DISEASES` de `src/retrieval/etapa2.py` (só regex e Python puro, sem dependência pesada)
- Produces:
  - `trechos_citados(texto: str) -> list[str]`: conteúdo entre `"…"` ou `“…”`, com 3 ou mais caracteres, na ordem.
  - `citacoes_nao_literais(texto: str, fontes: list[str]) -> list[str]`: trechos citados que não estão em nenhuma fonte. Compara depois de passar para minúsculas, colapsar espaços e unificar aspas; "…" ou "..." dentro do trecho o divide em partes, e cada parte precisa estar na mesma fonte.
  - `termos_fora_do_contexto(texto: str, contexto: str, ignorar: Iterable[str] = ()) -> list[str]`: nomes próprios (grupo de `name_groups`, unido por espaço), números e doenças do texto que não aparecem no contexto (radical de 5 letras, sem acento). Grupos de nome contam como presentes se algum token estiver no contexto. As strings de `ignorar` são removidas do texto antes da extração (sem diferenciar maiúsculas). O texto é avaliado linha a linha, sem o marcador de lista `- `.

- [ ] **Step 1: Write the failing tests**

```python
FRASES = ["Segundo o Corpo de Bombeiros, a aeronave ficou totalmente destruída.",
          "As causas serão investigadas pelo Cenipa em 2022."]

def test_trecho_literal_passa_com_aspas_curvas_e_caixa_diferente():
    assert citacoes_nao_literais('- Urgência: “TOTALMENTE destruída” reforça o dano.', FRASES) == []

def test_trecho_com_reticencias_passa_quando_as_partes_estao_na_mesma_frase():
    assert citacoes_nao_literais('- "Segundo o Corpo de Bombeiros… totalmente destruída"', FRASES) == []

def test_trecho_parafraseado_e_reprovado():
    assert citacoes_nao_literais('- "o avião foi completamente destruído"', FRASES) == ["o avião foi completamente destruído"]

def test_nome_numero_e_doenca_de_fora_sao_apontados():
    texto = "- Generalização: a OMS registrou 15 casos de dengue."
    assert termos_fora_do_contexto(texto, " ".join(FRASES)) == ["oms", "15", "dengue"]

def test_caixa_e_acento_diferentes_nao_reprovam():
    assert termos_fora_do_contexto("- O CENIPA vai investigar o caso de 2022.", " ".join(FRASES)) == []

def test_rotulos_ignorados_nao_viram_nome():
    texto = '- Autoridade sem identificação: "Corpo de Bombeiros" é citado sem nome.'
    assert termos_fora_do_contexto(texto, " ".join(FRASES), ignorar=["Autoridade sem identificação"]) == []
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `venv/bin/python -m pytest tests/unit/test_guardrails.py -q`
Expected: FAIL (`ModuleNotFoundError: src.guardrails.ancoragem`)

- [ ] **Step 3: Implementar as três funções em `src/guardrails/ancoragem.py`**

A docstring do módulo cita o spec, seção "Guardrails", G3 e G4.

- [ ] **Step 4: Rodar e ver passar**

Run: `venv/bin/python -m pytest tests/unit/test_guardrails.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/guardrails/ancoragem.py tests/unit/test_guardrails.py
git commit -m "feat: Guardrails de citação literal e de termos fora da notícia (G3, G4)"
```

---

### Task 4: Sintetizador aplica G3 e G4

**Files:**
- Modify: `src/agents/synthesizer.py` (`problema_da_sintese`, `sintese_livre`)
- Test: `tests/unit/test_synthesizer.py` (use `SintetizadorFalso` de `tests/modelos_falsos.py`)

**Interfaces:**
- Consumes: `citacoes_nao_literais`, `termos_fora_do_contexto` (Task 3)
- Produces: `problema_da_sintese(texto: str, frases: list[str]) -> str | None`. `frases` são os textos dos segmentos já passados por `neutralizar_urls`, os mesmos que o LLM recebeu. `ignorar` = `list(dossie.ROTULOS.values()) + ["Juízo de valor"]`.
- Ordem das checagens: vazio → veredito → link → G3 → G4. Mensagens (cópia exata):
  - G3: `f'Seu texto citou "{trecho}", que não está em nenhuma frase da notícia.'`
  - G4: `f"Seu texto mencionou '{termo}', que não aparece na notícia."`

- [ ] **Step 1: Write the failing tests**

```python
def test_trecho_inventado_dispara_retry_com_o_trecho_nomeado(monkeypatch):
    falso = SintetizadorFalso('- Urgência: "corra antes que seja tarde" pede pressa.',
                              '- Urgência: "URGENTE" pede ação imediata.').instalar(monkeypatch)
    resultado = sintetizador_node(estado_mamao())
    assert '"URGENTE" pede ação imediata' in resultado["dossier"]
    assert 'Seu texto citou "corra antes que seja tarde"' in falso.mensagens[1][-1][1]

def test_entidade_de_fora_reprovada_duas_vezes_cai_no_fallback(monkeypatch):
    SintetizadorFalso("- Generalização: a OMS discorda.", "- Generalização: a OMS discorda.").instalar(monkeypatch)
    resultado = sintetizador_node(estado_mamao())
    assert resultado["warnings"] == [WARN_GUARDRAILS]
    assert "OMS" not in resultado["dossier"]
```

Ajuste os nomes dos helpers (`estado_mamao`, atributo das mensagens recebidas) aos que já existem em `tests/unit/test_synthesizer.py` e `tests/modelos_falsos.py`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `venv/bin/python -m pytest tests/unit/test_synthesizer.py -q`
Expected: os 2 testes novos falham.

- [ ] **Step 3: Implementar.** Se alguma resposta enlatada de teste antigo citar trecho não literal, corrija a resposta, não o guardrail.

- [ ] **Step 4: Rodar a suíte rápida**

Run: `venv/bin/python -m pytest tests/unit tests/contract -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/synthesizer.py tests/unit/test_synthesizer.py
git commit -m "feat: Sintetizador reprova trecho não literal e termo fora da notícia"
```

---

### Task 5: Socrático aplica G4 por pergunta

**Files:**
- Modify: `src/agents/socratic.py` (`validar_perguntas`, `extrair_e_validar`, `analisar_texto`)
- Test: `tests/unit/test_socratic.py`

**Interfaces:**
- Consumes: `termos_fora_do_contexto` (Task 3)
- Produces: `validar_perguntas(perguntas: list[str], clean_text: str) -> list[str]` e `extrair_e_validar(bruto: str, clean_text: str) -> list[str]`. Ordem: limpar → descartar as perguntas com termo fora do contexto (log de warning) → exigir ≥ 2 → cortar em 3 → regras já existentes.
- Quando sobram menos de 2 perguntas: `PerguntaInvalida(f"Pergunta menciona '{termo}', que não aparece na notícia: '{pergunta}'")`, com a primeira descartada.

- [ ] **Step 1: Write the failing tests**

```python
MAMAO = "O chá da folha de mamão cura a dengue em apenas três dias. Um especialista garante que salva vidas."

def test_pergunta_com_entidade_de_fora_e_descartada():
    perguntas = ["Quem é o especialista citado e onde ele publicou seus estudos?",
                 "O que diz a OMS sobre o chá de mamão?",
                 "Quais estudos sustentam a cura da dengue em três dias?"]
    assert validar_perguntas(perguntas, MAMAO) == [perguntas[0], perguntas[2]]

def test_sobra_menos_de_duas_perguntas_dispara_retry():
    with pytest.raises(PerguntaInvalida, match="'oms'"):
        validar_perguntas(["O que diz a OMS sobre isso?", "E o Ministério da Saúde, o que diz?",
                           "Quem é o especialista citado na notícia?"], MAMAO)
```

- [ ] **Step 2: Rodar e ver falhar** — `venv/bin/python -m pytest tests/unit/test_socratic.py -q` → FAIL (`TypeError`: argumento a mais)

- [ ] **Step 3: Implementar e atualizar as chamadas.** Os exemplos few-shot (`src/prompts/socratico_exemplos.json`) também precisam passar no G4 com a própria `entrada` deles. Acrescente esse teste e corrija o exemplo que reprovar.

- [ ] **Step 4: Rodar a suíte rápida** — `venv/bin/python -m pytest tests/unit tests/contract -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/socratic.py src/prompts/socratico_exemplos.json tests/unit/test_socratic.py
git commit -m "feat: Socrático descarta pergunta com nome ou número que a notícia não traz"
```

---

### Task 6: Dossiê, checagens compactas com legenda e Fontes numeradas (itens 2, 3 e 5)

**Files:**
- Modify: `src/agents/dossie.py`
- Test: `tests/unit/test_dossie.py`

**Interfaces:**
- Produces, em `src/agents/dossie.py`:
  - `TITULO_FONTES = "## Fontes"`, `LEGENDA_CHECAGENS` (cópia exata do spec) e `ROTULOS_STANCE = {"contradiz": "Contradiz", "apoia": "Apoia", "insuficiente": "Não conclusiva"}`
  - `escapar_markdown(texto: str) -> str`: escapa `\ ` * _ [ ] < > ~ $` com `\`
  - `texto_seguro(texto: str) -> str` = `neutralizar_urls(escapar_markdown(texto))`. Substitui as chamadas atuais a `neutralizar_urls` sobre frases e trechos no `dossie.py`.
  - `encurtar(texto: str, limite: int = 80) -> str`: corta com "…"
  - `numerar_fontes(state: PipelineState, ctx: Contexto) -> dict[str, int]`: URL → número, na ordem das frases e depois das evidências
  - `secao_checagens(state: PipelineState, ctx: Contexto, fontes: dict[str, int]) -> list[str]`: assinatura nova
  - `linha_sem_checagem(frases: list[Segment]) -> str`
  - `secao_fontes(ctx: Contexto, fontes: dict[str, int]) -> list[str]`: devolve `[]` quando `fontes` está vazio
- `SEM_CHECAGEM` e `SEM_BANCO` continuam iguais.

- [ ] **Step 1: Reescrever `test_secao_checagens_do_mamao` e acrescentar os testes novos**

```python
def test_secao_checagens_do_mamao():
    state = estado_mamao(); ctx = dossie.preprocessar(state)
    linhas = dossie.secao_checagens(state, ctx, dossie.numerar_fontes(state, ctx))
    assert linhas == [
        dossie.TITULO_CHECAGENS, dossie.LEGENDA_CHECAGENS,
        '- "O chá da folha de mamão cura a dengue em apenas três dias."',
        f'  - Contradiz · Agência Lupa: Falso [↗ 1](<{URL_LUPA}>)',
        '- "Ele estimula a medula óssea a produzir mais plaquetas e evita a dengue hemorrágica."',
        f'  - Contradiz · Aos Fatos: Falso [↗ 2](<{URL_AOSFATOS}>)',
        '- Sem checagem no nosso banco: 2 afirmações factuais, "URGENTE: os médicos estão escondendo a cura natural da dengue!" '
        'e "Um especialista em plantas medicinais garante que a folha de mamão salva vidas.". '
        'Isso não confirma nem descarta essas frases.',
    ]

def test_fontes_do_mamao():
    state = estado_mamao(); ctx = dossie.preprocessar(state)
    assert dossie.secao_fontes(ctx, dossie.numerar_fontes(state, ctx)) == [
        dossie.TITULO_FONTES,
        f'1. Agência Lupa: Falso — "Não existe um tratamento específico para a dengue e as formas graves da doença." · [abrir ↗](<{URL_LUPA}>)',
        f'2. Aos Fatos: Falso — "não comprovam que o tratamento seja eficaz em humanos" · [abrir ↗](<{URL_AOSFATOS}>)',
    ]

def test_sem_checagem_com_muitas_frases_mostra_duas_e_conta_o_resto():
    frases = [Segment(id=f"s{i:02d}", text=f"Frase factual número {i} " + "x" * 90) for i in range(1, 31)]
    linha = dossie.linha_sem_checagem(frases)
    assert linha.startswith('- Sem checagem no nosso banco: 30 afirmações factuais, como "Frase factual número 1 ')
    assert linha.endswith(' e mais 28. Isso não confirma nem descarta essas frases.')
    assert len(linha) < 300

def test_uma_frase_sem_checagem_usa_singular():
    assert dossie.linha_sem_checagem([Segment(id="s01", text="A ponte caiu.")]) == (
        '- Sem checagem no nosso banco: 1 afirmação factual, "A ponte caiu.". Isso não confirma nem descarta essa frase.')

def test_mesma_url_em_duas_frases_tem_um_numero_so():          # Review Focus 2
    url = "https://a.org/1"
    state = estado_mamao(evidence=[evidencia("s02", url), evidencia("s03", url)]); ctx = dossie.preprocessar(state)
    fontes = dossie.numerar_fontes(state, ctx)
    assert fontes == {url: 1}
    assert len(dossie.secao_fontes(ctx, fontes)) == 2

def test_url_com_parenteses_continua_valida():                # Review Focus 3
    url = "https://x.org/a_(b)"
    state = estado_mamao(evidence=[evidencia("s02", url)]); ctx = dossie.preprocessar(state)
    texto = dossie.montar(dossie.secao_checagens(state, ctx, dossie.numerar_fontes(state, ctx)))
    assert f"[↗ 1](<{url}>)" in texto
    assert dossie.remover_citacoes_invalidas(texto, state.evidence)[1] is False

def test_cifrao_asterisco_e_colchete_da_noticia_sao_escapados():   # Review Focus 1
    assert dossie.texto_seguro("Custa R$ 10 e R$ 20, *exclusivo* [veja]") == r"Custa R\$ 10 e R\$ 20, \*exclusivo\* \[veja\]"
    assert dossie.texto_seguro("veja https://a.org/x_y.") == "veja [link]."
```

Atualize os demais testes de `secao_checagens` (sem selo, frase desconhecida, frase com link etc.) para a nova assinatura e o novo formato de linha.

- [ ] **Step 2: Rodar e ver falhar** — `venv/bin/python -m pytest tests/unit/test_dossie.py -q` → FAIL

- [ ] **Step 3: Implementar.** `resumo_por_stance` deixa de ser usado; remova a função e o `test_resumo_por_stance`. A Task 7 cria `contagem_por_stance` para o Resumo.

- [ ] **Step 4: Rodar e ver passar** — `venv/bin/python -m pytest tests/unit/test_dossie.py -q` → PASS (o `test_synthesizer.py` ainda pode falhar até a Task 7)

- [ ] **Step 5: Commit**

```bash
git add src/agents/dossie.py tests/unit/test_dossie.py
git commit -m "feat: Checagens com legenda, referências numeradas e seção Fontes no dossiê"
```

---

### Task 7: Dossiê, seção Resumo e ordem final

**Files:**
- Modify: `src/agents/dossie.py` (`TITULO_RESUMO`, `secao_resumo`)
- Modify: `src/agents/synthesizer.py` (`_montar_dossie`: ordem Resumo, Checagens, Argumento, Perguntas, Limites, Fontes)
- Modify: `tests/unit/test_dossie.py`, `tests/unit/test_synthesizer.py` (`TITULOS`), `tests/unit/test_graph.py:165`, `tests/integration/test_sintetizador_lmstudio.py:40`
- Modify: `tests/fixtures/caso_mamao_dengue/05_sintetizador_saida.json` (dossiê de referência no formato novo), `docs/agents/sintetizador.md` (seção sobre a estrutura do dossiê, apontando para o spec)

**Interfaces:**
- Consumes: `numerar_fontes`, `secao_checagens`, `secao_fontes` (Task 6)
- Produces: `TITULO_RESUMO = "## Resumo"` e `secao_resumo(state: PipelineState, ctx: Contexto) -> list[str]`, com as linhas exatas do spec, incluindo os casos degradados.

- [ ] **Step 1: Write the failing tests**

```python
def test_resumo_do_mamao():
    state = estado_mamao()
    assert dossie.secao_resumo(state, dossie.preprocessar(state)) == [
        dossie.TITULO_RESUMO,
        "- 6 frases analisadas: 4 afirmações factuais e 2 opiniões.",
        "- 2 das 4 afirmações factuais têm checagem publicada (2 contradizem).",
        "- 6 padrões de argumentação apontados.",
        "- O dossiê não dá veredito: mostra o que já foi checado, como o texto argumenta e o que perguntar antes de decidir.",
    ]

@pytest.mark.parametrize("sobrescritas, segunda, terceira", [
    ({"evidence": None}, "- O banco de checagens não pôde ser consultado.", "- 6 padrões de argumentação apontados."),
    ({"evidence": []}, "- Nenhuma das 4 afirmações factuais tem checagem no nosso banco.", "- 6 padrões de argumentação apontados."),
])
def test_resumo_degradado(sobrescritas, segunda, terceira):
    state = estado_mamao(**sobrescritas)
    linhas = dossie.secao_resumo(state, dossie.preprocessar(state))
    assert linhas[2:4] == [segunda, terceira]

def test_resumo_sem_text_report():
    state = estado_mamao(text_report=None)
    assert dossie.secao_resumo(state, dossie.preprocessar(state))[1:3] == [
        "- 6 frases analisadas.", "- 2 frases têm checagem publicada (2 contradizem)."]

def test_resumo_mistura_stances_no_singular_e_plural():
    assert dossie.contagem_por_stance(["contradiz", "contradiz", "apoia", "insuficiente"]) == "2 contradizem, 1 apoia, 1 não conclusiva"
```

Em `tests/unit/test_synthesizer.py`: `TITULOS = [TITULO_RESUMO, TITULO_CHECAGENS, TITULO_ARGUMENTO, TITULO_PERGUNTAS, TITULO_LIMITES, TITULO_FONTES]`. Acrescente um teste para quando não há evidência: os títulos ficam sem `TITULO_FONTES`.

- [ ] **Step 2: Rodar e ver falhar** — `venv/bin/python -m pytest tests/unit -q` → FAIL

- [ ] **Step 3: Implementar** `secao_resumo` e `contagem_por_stance(stances: list[str]) -> str` (no `dossie.py`) e a nova ordem em `_montar_dossie`. `remover_citacoes_invalidas` continua rodando sobre o texto final.

- [ ] **Step 4: Rodar a suíte rápida** — `venv/bin/python -m pytest tests/unit tests/contract -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add src/agents/dossie.py src/agents/synthesizer.py tests docs/agents/sintetizador.md
git commit -m "feat: Dossiê final com Resumo no topo e Fontes no fim"
```

---

### Task 8: App mostra só o dossiê (item 4) e as frases num expander

**Files:**
- Modify: `app/app.py:57-115`
- Modify: `src/agents/dossie.py` (tabela das frases, pura e testável)
- Test: `tests/unit/test_app.py`, `tests/unit/test_dossie.py`

**Interfaces:**
- Produces: `tabela_frases(state: PipelineState) -> dict[str, list]` com as chaves `"frase"`, `"tipo"` ("Fato" | "Opinião" | "Sem classificação") e `"checagens"` (int, contado sobre `preprocessar(state).evidencias`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_dossie.py
def test_tabela_frases_do_mamao():
    tabela = dossie.tabela_frases(estado_mamao())
    assert tabela["tipo"] == ["Fato", "Fato", "Fato", "Fato", "Opinião", "Opinião"]
    assert tabela["checagens"] == [0, 1, 1, 0, 0, 0]

# tests/unit/test_app.py
def test_app_mostra_so_o_dossie_e_os_expanders():
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")
    assert not at.exception
    assert [s.value for s in at.subheader] == []                 # sem "Evidências Analisadas" nem "Marcadores"
    rotulos = [e.label for e in at.expander]
    assert any(r.startswith("Todas as frases analisadas (") for r in rotulos)
    assert "Detalhes técnicos" in rotulos
```

Troque `"Frases segmentadas"` por `"Todas as frases analisadas"` em `test_app_analisa_texto_sem_excecao`.

- [ ] **Step 2: Rodar e ver falhar** — `venv/bin/python -m pytest tests/unit/test_app.py tests/unit/test_dossie.py -q` → FAIL

- [ ] **Step 3: Implementar o layout do spec ("App")**
  - Uma coluna e `st.markdown(dossier)`.
  - "Publicado em {data}" só quando há data; sai a linha "**Fonte/Ingestão**".
  - O expander de frases usa `tabela_frases`.
  - Tempos e trace vão para "Detalhes técnicos".
  - Saem as colunas `col1`/`col2`.

- [ ] **Step 4: Rodar a suíte rápida** — `venv/bin/python -m pytest tests/unit tests/contract -q` → PASS

- [ ] **Step 5: Ver o app rodando** (skill `run` ou `streamlit run app/app.py`). Analise o texto do mamão e confira:
  - a ordem das seções;
  - que o `[↗ n]` abre o link;
  - que "R$ 10" aparece literal.

- [ ] **Step 6: Commit**

```bash
git add app/app.py src/agents/dossie.py tests/unit/test_app.py tests/unit/test_dossie.py
git commit -m "feat: App mostra só o dossiê, com frases e detalhes técnicos em expanders"
```

---

### Task 9: Agente de Texto, notícia de desastre e falas citadas (item 1)

**Files:**
- Modify: `src/prompts/texto_sistema.md` (seção "Regras": duas regras novas)
- Modify: `src/prompts/texto_exemplos.json` (terceiro exemplo)
- Create: `tests/fixtures/bordas/texto_noticia_desastre.json`
- Test: `tests/unit/test_text_analysis.py`, `tests/integration/test_texto_lmstudio.py`

**Interfaces:** nenhuma de código. Regras (cópia exata, acrescentadas depois de "Dados estatísticos neutros..."):

```
- Palavras que descrevem um fato concreto e grave (mortes, destruição, ferimentos, número de vítimas) não são adjetivação extrema, mesmo que sejam fortes: "carbonizados", "totalmente destruído" e "morreram" descrevem o que aconteceu.
- Linguagem emocional dentro de falas, notas ou declarações citadas e atribuídas a alguém identificado é da pessoa citada, não do texto, e não é marcador.
```

Exemplo few-shot (cópia exata):

```json
{"entrada": [
  {"id": "s01", "text": "O avião caiu em uma área de mata e ficou totalmente destruído, segundo os bombeiros."},
  {"id": "s02", "text": "Dois corpos foram encontrados carbonizados."},
  {"id": "s03", "text": "Em nota, a empresa disse: \"Com profundo pesar recebemos a notícia do falecimento dos tripulantes.\""}],
 "saida": {"statements": [{"segment_id": "s01", "kind": "factual"}, {"segment_id": "s02", "kind": "factual"},
                          {"segment_id": "s03", "kind": "factual"}], "markers": []}}
```

A fixture de integração usa frases **diferentes** do exemplo, para medir generalização e não cópia:
- s01: "Um avião de pequeno porte que havia desaparecido na quinta-feira foi localizado neste sábado em uma área de mata."
- s02: "Segundo o Corpo de Bombeiros, a aeronave ficou totalmente destruída e os dois ocupantes morreram carbonizados."
- s03: "Em nota, a família de um dos ocupantes afirmou: \"É com profundo pesar que recebemos hoje a notícia do falecimento do nosso filho.\""
- s04: "As causas do acidente serão investigadas pelo Cenipa."

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_text_analysis.py
def test_prompt_tem_as_regras_de_desastre_e_fala_citada():
    prompt = carregar_prompt_sistema()
    assert "não são adjetivação extrema" in prompt
    assert "falas, notas ou declarações citadas" in prompt

def test_ha_exemplo_de_desastre_sem_marcadores():
    exemplos = [e for e in carregar_exemplos() if any("carbonizados" in s["text"] for s in e["entrada"])]
    assert len(exemplos) == 1 and exemplos[0]["saida"]["markers"] == []
```

```python
# tests/integration/test_texto_lmstudio.py (pulado sem o LM Studio, como os demais do arquivo)
def test_noticia_de_desastre_nao_vira_adjetivacao_nem_urgencia():
    ...  # carrega tests/fixtures/bordas/texto_noticia_desastre.json, roda texto_node
    proibidos = ("carbonizad", "destruíd", "pesar")
    assert not [m for m in relatorio.markers
                if m.type in ("adjetivacao_extrema", "urgencia_artificial") and any(p in m.excerpt for p in proibidos)]
```

- [ ] **Step 2: Rodar e ver falhar** — `venv/bin/python -m pytest tests/unit/test_text_analysis.py -q` → FAIL

- [ ] **Step 3: Editar o prompt, o exemplo e a fixture**

- [ ] **Step 4: Rodar a unitária e a integração**

Run: `venv/bin/python -m pytest tests/unit/test_text_analysis.py -q` → PASS
Run, com o LM Studio no ar: `venv/bin/python -m pytest tests/integration/test_texto_lmstudio.py -q`. Expected: PASS, e o `test_caso_mamao_com_modelo_real` continua passando, ou seja, as regras novas não apagaram os marcadores do mamão.

- [ ] **Step 5: Commit**

```bash
git add src/prompts/texto_sistema.md src/prompts/texto_exemplos.json tests/fixtures/bordas/texto_noticia_desastre.json tests/unit/test_text_analysis.py tests/integration/test_texto_lmstudio.py
git commit -m "fix: Agente de Texto não marca descrição de desastre nem fala citada como retórica"
```

---

## Fechamento

- [ ] `venv/bin/python -m pytest tests/unit tests/contract -q` verde; com o LM Studio, `venv/bin/python -m pytest tests/integration -q` verde.
- [ ] Rodar o app nos três casos do `Testes e Possíveis Melhorias.md` (G1 avião da FAB, texto dos incêndios, mamão) e anotar no PR o que mudou em cada item 1–5.
- [ ] PR para a `develop`.
