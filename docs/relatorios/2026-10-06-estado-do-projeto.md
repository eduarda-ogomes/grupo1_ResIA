# Relatório de estado do projeto — 06/10/2026

Sistema multiagente de avaliação de confiabilidade da informação (Grupo 1, ResIA). Este relatório descreve o que existe hoje no código, quanto tempo cada agente leva, o que já foi medido de qualidade, o que aprendemos rodando com os modelos reais e o que falta.

**Fontes dos números:**
- `eval/resultados/latencia_2026-10-06.json`: latência medida hoje.
- `eval/resultados/evidencias_2026-10-03_4.json`: gold set do Agente de Evidências.
- `eval/resultados/recursos_2026-10-03.json`: memória e tempo do Agente de Evidências.
- Execuções reais feitas hoje com o LM Studio e o índice completo.

---

## 1. Resumo

- **O pipeline completo funciona de ponta a ponta com os cinco agentes reais.** Ingestor → (Evidências | Texto | Socrático, em paralelo) → Sintetizador. Na `main` atual só o Ingestor é real; os outros quatro são stubs. A `develop` traz a primeira versão realmente orquestrada.
- **Latência dentro da meta:** p50 de **31,2 s** e p95 de **41,2 s** ponta a ponta. A meta do Manual §7.1 é p50 abaixo de 3 min.
- **O Agente de Texto é o gargalo:** responde por cerca de 70% do tempo total (p50 de 22,3 s).
- **O Agente de Evidências bate as metas de recuperação e de abstenção** no gold set: Recall@5 0,96, nenhuma evidência inventada e macro-F1 de stance 0,77. A única ressalva são 4 casamentos com a alegação errada.
- **Robustez:** cada nó tem timeout e degradação graciosa. Se o Sintetizador estourar o tempo, o dossiê sai montado sem o LLM. Uma análise nunca termina sem dossiê.
- **Observabilidade:** cada análise vira um trace no Phoenix local. O Streamlit mostra os tempos por etapa, e um script mede p50/p95.
- **Testes:** 367 testes unitários e de contrato, rodando sem modelos, e 5 de integração com os modelos reais, todos passando hoje.
- **Pontos fracos:**
  - qualidade do Agente de Texto, que classifica exclamações como "fato" e pula frases em lotes grandes;
  - qualidade do Agente Socrático, que às vezes gera perguntas sem sentido;
  - teste feito só com a variante de visão do Qwen 2.5 7B (`qwen2.5-vl-7b`);
  - métricas de qualidade ainda não medidas para Texto, Socrático e Sintetizador.

---

## 2. Estado do repositório

| Branch | Situação |
| --- | --- |
| `main` | Grafo com stubs; só o Ingestor é real (último merge: PR #2) |
| `origin/develop` | Os cinco agentes reais orquestrados (`aa9045e`). PR `develop → main` preparado com a descrição da primeira versão orquestrada |
| `develop` (local) | 2 commits à frente da `origin/develop`, sem push: perguntas socráticas aparecem uma vez só no app; correção de data no card do Agente de Texto |
| `feat/observabilidade` | Observabilidade (Phoenix, tempos, latência) e este relatório, sobre a `develop` local. Ainda não integrada |

Histórico das entregas desta etapa, na ordem:

1. **Orquestração:** grafo com os agentes reais, timeout por nó e proteção contra exceções (`src/graph.py`, `src/protecao.py`).
2. **Reescrita do Sintetizador** conforme a spec: abordagem híbrida e guardrails. A versão anterior lia campos inexistentes do estado e sempre devolvia a mensagem de erro.
3. **Correções achadas com os modelos reais:**
   - o filtro de veredito barrava o rótulo "Falsa dicotomia";
   - pontuação solta virava frase no Ingestor;
   - links da notícia passavam a ser tratados como citação;
   - os modelos do Evidências podiam ser carregados duas vezes;
   - nome do modelo do LM Studio configurável (`LLM_MODEL`);
   - falha por lote no Agente de Texto.
4. **Observabilidade** com Phoenix local, tempos no Streamlit e relatório de latência.

---

## 3. Arquitetura atual

```
Entrada (texto ou URL)
  └─ Ingestor ─────────── limpa, trunca (5.000 palavras), segmenta em frases s01, s02…
       ├─ Evidências ──── BGE-M3 + ChromaDB (36.071 trechos) → termos-chave → NLI (mDeBERTa)
       ├─ Texto ───────── qwen2.5-7b: fato/valor por frase + marcadores de retórica (lotes de 15)
       └─ Socrático ───── qwen2.5-7b: 2–3 perguntas reflexivas, sem perguntas indutivas
            └─ Sintetizador ─ dossiê em 4 seções; o 7B escreve só "Como o texto argumenta"
```

- **Estado compartilhado:** `src/state.py` (Manual §3.3), estrito e sem valores padrão; a entrada é sempre criada por `initial_state(...)`.
- **Proteção dos nós** (`src/protecao.py`), com estes limites:

| Nó | Limite | Variável de ambiente |
| --- | --- | --- |
| Ingestor | 60 s | `GRAFO_TIMEOUT_INGESTOR` |
| Cada ramo (Evidências, Texto, Socrático) | 240 s | `GRAFO_TIMEOUT_RAMO` |
| Sintetizador | 180 s | `GRAFO_TIMEOUT_SINTETIZADOR` |

  - Timeout ou exceção num nó vira aviso em `warnings`, e o grafo segue.
  - O contexto do trace é copiado para a thread de cada nó.
- **Clientes de LLM** (`src/services/llm.py`): timeout de 120 s, sem retry do cliente; o nome do modelo vem de `LLM_MODEL`.
- **Guardrails do Sintetizador** (`src/guardrails/`):
  - **filtro de veredito:** barra termos como falso, verdadeiro, fake news, mentira e desinformação, sem distinguir maiúsculas e acentos;
  - **checagem de citações:** toda URL do dossiê precisa estar entre as evidências recebidas;
  - **links da notícia:** são neutralizados como `[link]`.
- **Observabilidade** (`src/observabilidade.py`, `src/medicao.py`): desligada por padrão; com `PHOENIX_TRACING=1`, cada análise vira um trace no projeto `grupo1-resia` do Phoenix.

---

## 4. Estado de cada agente

| Agente | Técnica | Estado | Pontos de atenção |
| --- | --- | --- | --- |
| **Ingestor** | trafilatura + BeautifulSoup, truncamento e spaCy `pt_core_news_sm` | Real e estável | Junta pontuação solta à frase anterior ("URGENTE!!!" era cortado em dois). Paywall e páginas que dependem de JavaScript viram aviso |
| **Evidências** | RAG: BGE-M3, ChromaDB 1.5.9, termos-chave, NLI mDeBERTa e veredito da agência | Real, avaliado no gold set | Não usa LLM. A primeira análise carrega cerca de 2 GB de modelos. Índice e dados brutos vêm do Google Drive, fora do git |
| **Texto** | qwen2.5-7b, few-shot e JSON Schema, lotes de 15 frases com 2 de contexto, 1 retry | Real; falha por lote desde hoje | É o gargalo de tempo. Pula frases em lotes grandes. Marca exclamações e chamadas ("Justiça feita!") como `factual` |
| **Socrático** | qwen2.5-7b, temperatura 0,7, rejeita perguntas indutivas e com veredito | Real | Às vezes gera pergunta sem sentido ou com erro de português |
| **Sintetizador** | Híbrido: o código monta checagens, perguntas e limites; o 7B escreve o argumento; guardrails, 1 retry e fallback | Real, reescrito conforme a spec | Prompt conflitante: pede "2 a 6 bullets" e também "um bullet por frase de opinião"; com muitos marcadores, as frases de opinião somem da seção |

---

## 5. Tempos

### 5.1 Medição de hoje (Manual §7.1)

`python eval/medir_latencia.py --repeticoes 3`

- **Modelo:** LM Studio com `qwen/qwen2.5-vl-7b`.
- **Máquina:** macOS 27, arm64.
- **Índice:** real, com 36.071 trechos.
- **Rodadas:** 1 análise de aquecimento descartada, mais 2 entradas × 3 repetições.
- **Avisos:** nenhuma das 6 execuções gerou aviso.

| Nó | p50 (s) | p95 (s) | Participação no p50 total |
| --- | ---: | ---: | ---: |
| Ingestor | 0,0 | 0,0 | ~0% |
| Evidências | 0,7 | 2,0 | (em paralelo) |
| **Texto** | **22,3** | **29,5** | **~71%** |
| Socrático | 9,6 | 11,7 | (em paralelo) |
| Sintetizador | 8,9 | 13,0 | ~29% |
| **Total** | **31,2** | **41,2** | meta: p50 < 180 s ✅ |

Como os três ramos rodam em paralelo, o tempo total é aproximadamente **Ingestor + o ramo mais lento (sempre o Texto) + Sintetizador**. O Evidências e o Socrático terminam antes do Texto e não pesam no total.

### 5.2 Por entrada (médias das 3 repetições)

| Entrada | Frases | Total (s) | Evidências | Texto | Socrático | Sintetizador |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Mamão e dengue (Manual §4.6) | 6 | 29,1 | 0,7 | 20,3 | 9,2 | 8,8 |
| Corrente do Carrefour (Osasco) | 7 | 40,1 | 1,1 | 28,2 | 10,6 | 11,9 |

No Carrefour, uma frase a mais e trechos de retórica mais longos somam cerca de 8 s no Texto e 3 s no Sintetizador: o custo cresce com o volume de texto que o modelo precisa ler e escrever.

### 5.3 Outras medições do dia

| Cenário | Resultado |
| --- | --- |
| Grafo com o caso do mamão (teste de integração) | 28 s a 34 s no total |
| Corrente do Carrefour pelo grafo, com o trace no Phoenix | 24,5 s, 19 spans num único trace |
| Agente de Texto sozinho, numa checagem de 30 frases do corpus (2 lotes) | 37,9 s, as 30 frases classificadas |
| Agente de Evidências quente, notícia de 3 frases (03/10, GPU) | p50 0,11 s |
| Agente de Evidências quente, notícia de 36 frases (03/10, GPU) | p50 0,79 s |
| Primeira análise após subir o processo | Soma o carregamento do BGE-M3 e do mDeBERTa, e o download na primeira vez da máquina. Pode passar do limite de 240 s do ramo e gerar `evidencias: timeout` |

### 5.4 Memória (Agente de Evidências, 03/10)

- Processo com os dois modelos carregados: **2,34 GB de RAM**.
- Na GPU: 2,59 GB (BGE-M3 em fp16).
- Somando o 7B do LM Studio (cerca de 5 GB mais o KV cache), a demo cabe no orçamento de cerca de 16 GB do Manual §5.2. Falta medir no M4.

---

## 6. Qualidade medida

### 6.1 Contra as metas do Manual §7.1

| Componente | Métrica | Meta | Atual | Situação |
| --- | --- | --- | --- | --- |
| Evidências: recuperação | Recall@5 | ≥ 0,70 | **0,96** (42 frases, BGE-M3) | ✅ |
| Evidências: stance | Macro-F1 apoia/contradiz/insuficiente | ≥ 0,65 | **0,77** | ✅ |
| Evidências: abstenção | Taxa de evidência inventada | ≤ 0,10 | **0,00** (0 de 12 frases sem checagem) | ✅ |
| Sintetizador: citações | Validade de citação | 1,00 | **1,00 por construção** (o código monta as citações a partir das evidências; links da notícia são neutralizados) | ✅ |
| Sintetizador: veredito | Vazamento de veredito | 0 | Filtro determinístico ativo; paráfrases ("não procede") passam e não foram medidas | ⚠️ não medido |
| Texto | Macro-F1 fato/valor | ≥ 0,75 | Só o caso do mamão (6/6); falta o gold set | ⚠️ não medido |
| Texto | Marcadores pertinentes | ≥ 0,70 | 3/6 no caso do mamão (01/10) | ⚠️ amostra mínima |
| Socrático | Qualidade das perguntas (rubrica 1–3) | ≥ 2,5 | Não medido; houve pergunta sem sentido no cenário do Carrefour | ⚠️ não medido |
| Sistema | Latência p50 | < 180 s | **31,2 s** | ✅ |

### 6.2 Detalhes do Agente de Evidências (gold set de 42 frases, 03/10)

| Medida | Valor |
| --- | --- |
| Cobertura (frase com checagem que recebeu a evidência certa) | 0,83 |
| Stance correta quando a checagem certa foi encontrada | 1,00 |
| Casamentos com a alegação errada | 4 evidências (registrados como limitação conhecida no ADR do agente) |

**Comparação de modelos de embedding no mesmo gold set:**

| Modelo | Recall@5 | Macro-F1 |
| --- | ---: | ---: |
| BGE-M3 (em uso) | 0,96 | 0,77 |
| multilingual-e5-large | 0,74 | 0,56 |

O ganho justificou manter o BGE-M3.

---

## 7. Testes e verificação

| Conjunto | Quantidade | Roda no CI? | Situação |
| --- | ---: | --- | --- |
| Contrato + unitários (`tests/contract`, `tests/unit`) | 367 | Sim, Python 3.10 | Verde localmente; independente da ordem e de `PHOENIX_TRACING` |
| Integração com modelos reais (`tests/integration`, `EVIDENCE_INTEGRATION=1`) | 5 | Não | 5/5 hoje, com o LM Studio e o índice real |

Garantias que os testes cobrem:

- Nenhum teste unitário ou de contrato fala com o LM Studio, o ChromaDB, o BGE-M3 ou o NLI (`tests/conftest.py`).
- Timeout e exceção em cada ramo, URL atrás de paywall, Sintetizador travado e o caso do mamão de ponta a ponta (`tests/unit/test_graph.py`).
- Guardrails com as fixtures de borda do Manual §4.7.
- Spans: a hierarquia do trace, o resultado de cada nó e as etapas do Ingestor e do Evidências.

---

## 8. Principais insights

1. **O tempo está no Agente de Texto, não no RAG.** O Evidências leva menos de 1 s quente; o Texto leva 20–30 s porque gera JSON estruturado para cada frase, em lotes. Reduzir o tempo total passa pelo Texto: lotes menores em paralelo, menos tokens de saída ou um modelo mais rápido.
2. **O paralelismo ajuda pouco numa máquina só.** Texto e Socrático disputam o mesmo modelo no LM Studio, como o Manual §5.1 previa. O total é cerca de Texto + Sintetizador, e o Socrático "se esconde" dentro do tempo do Texto.
3. **Um 7B segue mal instruções longas de saída estruturada.** Achados com o modelo real:
   - pulou frases em lotes de 15;
   - classificou chamadas e exclamações como fato;
   - copiou o rótulo "Falsa dicotomia", que esbarrava no filtro de veredito.
   
   Cada um virou correção com teste, mas a qualidade do Texto ainda é o principal risco do produto.
4. **Deixar fatos e citações com o código funcionou.** No Sintetizador híbrido, o LLM nunca escreve URLs nem o selo da agência. Com isso, a validade de citação é 1,00 por construção, e uma falha do LLM não impede a entrega do dossiê.
5. **A primeira análise é a mais perigosa.** O carregamento dos modelos pode estourar o timeout do ramo de Evidências. O README recomenda uma análise de aquecimento antes da demo.
6. **A configuração varia de máquina para máquina.** O LM Studio recusa nomes de modelo desconhecidos quando há mais de um carregado; por isso o `LLM_MODEL` passou a ser obrigatório na prática. O índice (`chroma_data/`) e os dados brutos precisam ser baixados do Google Drive.
7. **Testar com os modelos reais pagou.** Quatro bugs só apareceram fora dos testes com dublês: o rótulo da falácia, a segmentação, o nome do modelo e o lote que pulava frases.
8. **A observabilidade confirma o desenho.** Um trace por análise (19 spans no cenário real) mostra cada nó, cada chamada ao LLM com tokens e as etapas do RAG. Isso já permite investigar uma análise lenta ou degradada sem reproduzi-la.

---

## 9. Riscos e limitações conhecidas

| Risco | Impacto | Mitigação atual |
| --- | --- | --- |
| Qualidade do Agente de Texto (fato/valor, frases puladas) | Dossiê com classificação errada ou parcial | Falha por lote com aviso; frases sem classificação listadas no dossiê |
| Teste feito só com `qwen2.5-vl-7b` | Resultados podem mudar com o Qwen 2.5 7B não-VL | `LLM_MODEL` configurável; repetir a medição com o modelo final |
| Nó abandonado por timeout continua rodando em segundo plano | A análise seguinte pode ficar mais lenta | Documentado; o timeout de 120 s por chamada limita cada chamada, não o agente inteiro |
| Paráfrases de veredito passam pelo filtro | Veredito implícito no texto do LLM | Falso negativo conhecido, fixado em teste; precisa entrar no gold set |
| Casamentos com a alegação errada no Evidências (4 no gold set) | Checagem de outro fato exibida como evidência | Termos-chave + NLI; limitação registrada no ADR |
| Índice e dados fora do git | Ambiente difícil de reproduzir | Download pelo Google Drive documentado no card do agente |

---

## 10. Pendências e próximos passos

**Prioridade alta (antes da demo):**
1. Integrar a `develop` na `main` (PR com a primeira versão orquestrada) e decidir a integração da observabilidade.
2. Repetir `eval/medir_latencia.py` e os testes de integração com o **Qwen 2.5 7B** final, na máquina da demo.
3. Ajustar o prompt do Sintetizador (conflito "2 a 6 bullets" × frases de opinião) e do Agente de Texto (exclamações e chamadas como `valor`).

**Prioridade média (métricas do Manual §7.1 ainda abertas):**
4. Medir o macro-F1 fato/valor e os marcadores pertinentes do Agente de Texto no gold set.
5. Aplicar a rubrica 1–3 às perguntas do Socrático.
6. Medir o vazamento de veredito, incluindo paráfrases, nos dossiês do gold set.
7. Rodar o baseline de chamada única (Manual §7.3) para comparar com o multiagente.

**Melhorias adiadas da revisão de observabilidade:**
8. O link "Ver o trace no Phoenix" abre a página inicial, não o trace.
9. Validar os argumentos de `eval/medir_latencia.py` (arquivo de entradas vazio, `--repeticoes 0`).
10. Alinhar os nomes `no.texto` (trace) e `agente_texto` (tabela do app e JSON de latência).
11. Mover a seção de observabilidade do README para antes do rodapé e listar os arquivos novos na estrutura do repositório.
12. Proteger o wrapper dos nós contra um nó que devolva `None`, e chamar `ligar_tracing()` depois de `st.set_page_config`.

**Avisos para o grupo:**
- O Sintetizador do PR #11 foi substituído pela versão da spec.
- O contrato de falha do Agente de Texto mudou de "tudo ou nada" para "por lote" (Manual §4.7).
- Cada máquina precisa definir `LLM_MODEL` com o nome do modelo no LM Studio local.

---

## Apêndice: como reproduzir

```bash
source venv/bin/activate
pytest tests/contract tests/unit -q                                   # 367 testes, sem modelos

# LM Studio em localhost:1234; chroma_data/ e data/corpus/raw/ do Google Drive
LLM_MODEL=qwen/qwen2.5-vl-7b EVIDENCE_INTEGRATION=1 pytest tests/integration -v -s
LLM_MODEL=qwen/qwen2.5-vl-7b python eval/medir_latencia.py --repeticoes 3

# Observabilidade
phoenix serve                                                         # http://localhost:6006
PHOENIX_TRACING=1 LLM_MODEL=qwen/qwen2.5-vl-7b streamlit run app/app.py
```
