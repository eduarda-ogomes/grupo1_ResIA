# 🕵️‍♂️ Sistema Multiagente de Avaliação de Confiabilidade

> Projeto desenvolvido pelo **Grupo 1 (ResIA)** para avaliar a confiabilidade de informações e notícias utilizando Inteligência Artificial, sem substituir o pensamento crítico humano.

[![CI de Testes e Contratos](https://github.com/eduarda-ogomes/grupo1_ResIA/actions/workflows/ci.yml/badge.svg)](https://github.com/eduarda-ogomes/grupo1_ResIA/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Multiagente-orange)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)
![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-purple)
![LMStudio](https://img.shields.io/badge/LLM-Local_Inference-lightgrey)

## 📖 Sobre o Projeto

O sistema recebe um texto suspeito ou a URL de uma notícia e devolve um **dossiê de evidências** montado por agentes especializados, parte deles trabalhando em paralelo.

**Princípio fundamental:** o sistema opera no "padrão andaime". Ele **nunca** emite um veredito binário ("falso" ou "verdadeiro"). Em vez disso, mostra o que as agências de checagem já publicaram, expõe como o texto argumenta e faz perguntas que ajudam o usuário a tomar a própria decisão.

Outros princípios que guiam o código:

- **A notícia é dado, não instrução:** o texto analisado entra delimitado nos prompts e nunca é tratado como comando.
- **Toda afirmação é rastreável:** cada trecho do dossiê aponta para a frase da notícia (`s01`, `s02`…) ou para a checagem que o sustenta, com link.
- **Inferência 100% local:** os LLMs rodam no LM Studio e os modelos de embeddings/NLI na própria máquina; a notícia não sai do computador.
- **Degradação graciosa:** se um agente falha ou estoura o tempo, a análise continua e o dossiê sai assim mesmo, declarando o que ficou de fora.

A especificação completa está no [Manual do Sistema Multiagente](docs/Manual%20do%20Sistema%20Multiagente%20—%20Avaliação%20de%20Confiabilidade%20da%20Informação.md).

---

## 🧠 Arquitetura

O grafo é orquestrado com **LangGraph** (`src/pipeline/graph.py`) e tem cinco nós, um por agente. O Ingestor abre três ramos que rodam em paralelo (Evidências, Texto e Socrático); o Sintetizador espera os três e monta o dossiê.

```text
Entrada (texto ou URL)
  └─ ingestor ─┬─→ agente_evidencias ─┐
               ├─→ agente_texto ──────┼─→ sintetizador → dossiê
               └─→ agente_socratico ──┘
```

| Nó | O que faz | Técnica / modelo | Código |
| --- | --- | --- | --- |
| 📥 **Ingestor** | Baixa a página (Trafilatura), remove ruído (avisos, rodapé, "publicidade"), trunca em 5.000 palavras e divide o texto em frases numeradas (`s01`, `s02`…). | spaCy `pt_core_news_sm`, sem LLM | `src/agents/ingestor.py` |
| 🔍 **Evidências** | Para cada frase, procura checagens já publicadas sobre a **mesma alegação** e devolve o que a agência concluiu (*apoia*, *contradiz* ou *insuficiente*), com título e link. | RAG: BGE-M3 + ChromaDB → termos-chave → NLI (mDeBERTa-v3), sem LLM | `src/agents/evidence.py`, `src/retrieval/` |
| 📝 **Texto** | Classifica cada frase como `factual` ou `valor` e aponta marcadores de retórica: adjetivação extrema, urgência artificial, apelo à autoridade, falsa dicotomia e generalização. Em notícias de desastre, a intensidade que descreve o evento não é marcador. Por fim, escreve o efeito de cada marcador para "Como o texto argumenta" (o rótulo e o trecho literal vêm do código). | `qwen2.5-7b` com *few-shot* contrastivo e JSON Schema, lotes de 15 frases em paralelo; efeito com guardrails | `src/agents/text_analysis.py`, `src/agents/argumento.py` |
| 🤔 **Socrático** | Formula de 2 a 3 perguntas reflexivas e não indutivas (maiêutica) a partir do título e das primeiras frases da notícia. | `qwen2.5-7b` + validação de ancoragem | `src/agents/socratic.py` |
| 📊 **Sintetizador** | Junta tudo num dossiê em Markdown, sem veredito. Não chama LLM e nunca devolve dossiê vazio. | Só código | `src/agents/synthesizer/agent.py`, `src/agents/synthesizer/dossie.py` |

O estado compartilhado (`src/state.py`) é estrito: a entrada é sempre criada com `initial_state("texto ou URL")`. O `segment_id` de cada frase é o contrato que permite ao Sintetizador cruzar "esta frase é factual" (Texto) com "esta frase tem checagem que a contradiz" (Evidências).

### O dossiê

Seis seções, em pirâmide invertida (o tamanho do problema primeiro, as referências por último):

1. **Resumo** — contagens de frases, checagens e marcadores.
2. **O que as checagens dizem** — selo da agência, título da checagem e referência numerada.
3. **Como o texto argumenta** — marcadores de retórica com o trecho literal da notícia.
4. **Perguntas para pensar antes de decidir** — as perguntas do Agente Socrático.
5. **Limites desta análise** — sempre presente: o que não foi analisado e por quê.
6. **Fontes** — links das checagens citadas.

### Guardrails (`src/guardrails/`)

- **Filtro de veredito:** barra "falso", "verdadeiro", "fake news", "mentira", "desinformação" no texto gerado pelo LLM (o selo da agência fica de fora).
- **Checagem de citações:** toda URL do dossiê precisa estar entre as evidências recebidas; uma linha com URL inventada é removida.
- **Ancoragem:** trechos entre aspas precisam existir literalmente na notícia, e nomes, números e doenças citados pelo LLM precisam aparecer no texto.

Reprovou: 1 retry, nomeando o problema; reprovou de novo, entra o *fallback* em código com aviso.

### Interface

A interface em **Streamlit** (`app/app.py`) recebe o texto ou a URL e mostra a **sala dos agentes** (`app/sala/`), uma animação em pixel art que acompanha o progresso de cada agente em tempo real. Ao final exibe o dossiê, as frases analisadas, os avisos e os tempos de cada etapa.

---

## 📂 Estrutura do Repositório

```text
grupo1_ResIA/
├── app/
│   ├── app.py                  # Interface web (Streamlit): ponto de entrada
│   └── sala/                   # Sala dos agentes: animação pixel art da análise (st.components.v2)
├── data/
│   ├── corpus/                 # Coleta, importação e indexação das checagens (API do Google, FACTCK.BR, Lupa)
│   └── gold/                   # Gold set de avaliação do Agente de Evidências
├── docs/
│   ├── Manual ... .md          # Manual do sistema: princípios, arquitetura, contratos e sprints
│   ├── agents/                 # Card de cada agente, ADRs e medições de desempenho
│   ├── relatorios/             # Relatórios de estado do projeto
│   └── superpowers/            # Specs de design e planos de implementação
├── eval/                       # Scripts de avaliação (evidências, latência, recursos) e resultados
├── scripts/
│   └── rodar_exemplos.py       # Roda o grafo em notícias de exemplo (fora do pytest)
├── src/
│   ├── state.py                # Contrato compartilhado (PipelineState, Pydantic)
│   ├── pipeline/               # Orquestração
│   │   ├── graph.py            # Grafo LangGraph: nós, arestas e timeouts
│   │   ├── protecao.py         # Timeout por nó; falha vira aviso
│   │   ├── medicao.py          # Execução medida do grafo (tempo por nó, trace)
│   │   └── progresso.py        # Progresso da análise para a sala dos agentes
│   ├── agents/                 # Um módulo por agente
│   │   ├── ingestor.py
│   │   ├── evidence.py
│   │   ├── text_analysis.py
│   │   ├── argumento.py        # Efeito dos marcadores (passo final do Texto)
│   │   ├── socratic.py
│   │   └── synthesizer/
│   │       ├── agent.py        # Nó sintetizador (só código)
│   │       └── dossie.py       # Seções do dossiê escritas pelo código
│   ├── retrieval/              # Índice ChromaDB, embeddings, NLI e etapa "mesma alegação" (compartilhado)
│   ├── guardrails/             # Veredito, citações e ancoragem
│   ├── prompts/                # Prompts de sistema e exemplos few-shot (Texto, Socrático, Sintetizador)
│   └── services/
│       ├── llm.py              # Clientes do LM Studio (API compatível com OpenAI)
│       └── observabilidade.py  # Traces no Arize Phoenix (OpenTelemetry)
├── tests/
│   ├── unit/                   # Testes unitários (rodam sem modelos)
│   ├── contract/               # Testes de contrato do estado e dos agentes
│   ├── integration/            # Testes com os modelos reais (fora do CI)
│   ├── fixtures/               # Caso de ponta a ponta (mamão × dengue) e casos de borda
│   └── stubs/                  # Agentes falsos dos testes de contrato
├── requirements.txt            # Dependências completas
└── requirements-ci.txt         # Dependências mínimas para o CI (sem torch/chromadb)
```

---

## 🚀 Como Executar Localmente

### 1. Pré-requisitos

- Python 3.10 ou superior.
- [LM Studio](https://lmstudio.ai/) para rodar o LLM localmente (recomendado: **Qwen 2.5 7B Instruct**, GGUF Q4_K_M).
- O índice de checagens (`chroma_data/`), que fica fora do Git (ver o passo 3).

### 2. Preparando o ambiente

```bash
git clone https://github.com/eduarda-ogomes/grupo1_ResIA.git
cd grupo1_ResIA
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
pip install -r requirements.txt
```

O `requirements.txt` já instala o modelo de português do spaCy (`pt_core_news_sm`); o Ingestor nunca o baixa durante a análise. Sem ele, as frases são separadas só pela pontuação e a interface mostra um aviso.

### 3. Índice de checagens

O Agente de Evidências consulta um índice ChromaDB com **cerca de 18 mil checagens e 114 mil trechos** (Google Fact Check Tools API 2015–2026 + FACTCK.BR). O índice e os dados brutos ficam fora do Git, porque trazem o texto integral das checagens das agências, que não é nosso para redistribuir.

- **Índice pronto:** baixe o `chroma_data.zip` (índice) e, se for rodar a avaliação, o `raw.zip` (dados brutos) da [pasta do Google Drive](https://drive.google.com/drive/folders/1FrQBt0Q34wez1ZnvsIkLEvClwSNjQuGQ?usp=sharing) e extraia na raiz do repositório:

  ```bash
  unzip chroma_data.zip -d .          # cria ./chroma_data
  unzip raw.zip -d data/corpus        # cria data/corpus/raw
  ```

  Instruções para Windows e como conferir o índice em [`docs/agents/evidencias.md` → Como rodar](docs/agents/evidencias.md#como-rodar).
- **Para refazer o índice do zero:** são necessários uma chave da Fact Check Tools API (`FACTCHECK_API_KEY`) e os scripts de `data/corpus/`:

  ```bash
  python data/corpus/collect_factcheck_api.py
  python data/corpus/fetch_articles.py
  python data/corpus/build_index.py --reset
  ```

  Para trazer só as checagens novas depois: `python data/corpus/atualizar.py --max-age-days 30`.

O `chromadb` está fixado em 1.5.9: um índice criado numa versão pode não abrir em outra. Os modelos BGE-M3 e mDeBERTa são baixados do Hugging Face na primeira execução.

### 4. Subindo o motor de IA

1. Abra o **LM Studio** (ou use a CLI `lms`).
2. Carregue o modelo com `Context Length` de pelo menos **8192 tokens** (o valor usado nas medições).
3. Inicie o *Local Server* na porta padrão `1234`.
4. Confira o identificador do modelo com `curl http://localhost:1234/v1/models` e passe-o em `LLM_MODEL` (padrão `qwen2.5-7b`). Com um nome desconhecido, o LM Studio recusa a chamada e os agentes avisam "falha ao chamar o modelo".

### 5. Iniciando a interface

Com o servidor do LM Studio rodando, execute o Streamlit **a partir da raiz do repositório** (com o `venv` ativado):

```bash
LLM_MODEL=qwen/qwen2.5-7b-instruct streamlit run app/app.py
```

Acesse `http://localhost:8501` e cole um texto ou a URL de uma notícia.

> Na primeira análise, o Agente de Evidências carrega o BGE-M3 e o mDeBERTa, o que pode passar do limite e gerar `evidencias: timeout`. O carregamento continua em segundo plano: espere um ou dois minutos e analise de novo. Na demo, faça uma análise de aquecimento antes de apresentar.

### 6. Testes

```bash
pytest                        # tudo; os de integração são pulados sem o LM Studio no ar
pytest tests/unit tests/contract
EVIDENCE_INTEGRATION=1 pytest tests/integration/test_evidence_integration.py -v   # Evidências com os modelos reais
```

São cerca de 600 testes; os unitários e de contrato rodam sem modelos e são os mesmos do CI (GitHub Actions, em `main` e `develop`). Para rodar o grafo inteiro com os modelos reais e ver o tempo de cada nó:

```bash
pytest tests/integration/test_grafo_lmstudio.py -v -s
```

---

## ⚙️ Configuração

### Timeouts e avisos

Cada nó tem um limite de tempo (`src/pipeline/protecao.py`). Se um nó estoura o tempo ou quebra, o grafo segue sem ele, a interface mostra o aviso (por exemplo, `socratico: timeout`) e o dossiê sai assim mesmo.

| Nó | Padrão | Variável de ambiente |
| --- | --- | --- |
| Ingestor | 60 s | `GRAFO_TIMEOUT_INGESTOR` |
| Evidências, Texto, Socrático (cada um) | 240 s | `GRAFO_TIMEOUT_RAMO` |
| Sintetizador | 180 s | `GRAFO_TIMEOUT_SINTETIZADOR` |

Um nó que estoura o tempo não é interrompido: ele segue rodando em segundo plano até terminar, o que pode deixar a análise seguinte mais lenta. O tempo do Texto inclui o efeito dos marcadores; se ele estourar, o dossiê sai sem "Como o texto argumenta" ("Não foi possível analisar a estrutura do texto.").

### Variáveis de ambiente

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `LLM_MODEL` | `qwen2.5-7b` | Identificador do modelo no LM Studio |
| `TEXTO_PARALELISMO` | `2` | Lotes que o Agente de Texto manda ao LM Studio ao mesmo tempo. Só ganha se o modelo estiver carregado com "Max Concurrent Predictions" ≥ o valor |
| `PHOENIX_TRACING` | desligado | `1` liga os traces no Phoenix |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006` | Endereço do Phoenix |
| `EVIDENCE_CHROMA_PATH` | `chroma_data/` | Pasta do índice |
| `EVIDENCE_DEVICE` | automático | `cpu`, `cuda` ou `mps` para os modelos do Agente de Evidências |
| `EVIDENCE_SIM_THRESHOLD` | `0.55` | Similaridade mínima na busca |
| `EVIDENCE_CLAIM_MATCH_MIN_PROB` | `0.8` | *Entailment* mínimo para aceitar que a checagem trata da mesma alegação |
| `FACTCHECK_API_KEY` | — | Chave da Google Fact Check Tools API (só para coletar o corpus) |

As demais variáveis do Agente de Evidências estão em `src/retrieval/config.py`, com o motivo de cada valor em [`docs/agents/evidencias_decisoes.md`](docs/agents/evidencias_decisoes.md).

---

## 🔭 Observabilidade (Phoenix local)

Cada análise pode virar um *trace* no [Arize Phoenix](https://github.com/Arize-ai/phoenix), rodando na sua máquina (os dados não saem dela). O tracing é desligado por padrão.

```bash
phoenix serve                            # em outro terminal; interface em http://localhost:6006
PHOENIX_TRACING=1 LLM_MODEL=<id> streamlit run app/app.py
```

No projeto `grupo1-resia` do Phoenix, cada análise aparece como um trace com:

- `analise` (raiz): tipo de entrada, número de frases, avisos e tempo total;
- um span por nó (`no.ingestor`, `no.evidencias`, `no.texto`, `no.argumento`, `no.socratico`, `no.sintetizador`) com o resultado (`ok`, `timeout` ou `erro`) e os avisos;
- as chamadas ao LLM (`ChatOpenAI`) com prompt, resposta, tokens e tempo;
- as etapas do Ingestor (`ingestor.baixar`, `ingestor.segmentar`) e do Evidências (`evidencias.busca`, `evidencias.termos_chave`, `evidencias.nli`) com as contagens.

O Streamlit mostra os tempos de cada etapa e, com o tracing ligado, o ID do trace. Se o Phoenix estiver fora do ar, a análise segue normalmente.

---

## 📈 Avaliação e Resultados

| Métrica | Resultado | Meta | Fonte |
| --- | --- | --- | --- |
| Latência ponta a ponta (p50 / p95) | **35,3 s / 136,8 s** | p50 < 3 min | `eval/resultados/latencia_2026-10-09_final.json` |
| Evidências: Recall@5 da busca | **1,00** (23/23) | ≥ 0,70 | `eval/resultados/evidencias_2026-10-09_5.json` |
| Evidências: macro-F1 de stance | **0,77** | ≥ 0,65 | idem |
| Evidências: evidência inventada | **0/12** | ≤ 10% | idem |
| Evidências: casamento com a alegação errada | **6** | 0 | idem |

Medições de 09/10/2026, com `qwen2.5-7b` (Q4_K_M) no LM Studio, o índice de 114 mil trechos e o gold set de 42 frases. Detalhes e análise de erros em [`docs/agents/desempenho.md`](docs/agents/desempenho.md) e [`docs/agents/evidencias.md`](docs/agents/evidencias.md#avaliação).

Para reproduzir:

```bash
LLM_MODEL=<id> python eval/medir_latencia.py --repeticoes 3      # resultado em eval/resultados/latencia_<data>.json
python eval/avaliar_evidencias.py avaliar --split todos --salvar  # precisa do índice e de data/corpus/raw/
```

### Limitações conhecidas

- O Agente de Evidências só encontra o que está no corpus; checagens da AFP e da maior parte do UOL entram só pelo título, porque os sites recusam o download.
- Ainda há casos de "casamento errado": uma checagem do mesmo personagem e tema, mas de outro episódio.
- O Agente de Texto não trata ironia nem sátira, e pode confundir estilo editorial legítimo com manipulação: os marcadores são padrões para observar, não acusações.
- O filtro de veredito não pega paráfrases ("não procede", "é enganoso").

---

## 📚 Documentação

| Documento | Conteúdo |
| --- | --- |
| [Manual do sistema](docs/Manual%20do%20Sistema%20Multiagente%20—%20Avaliação%20de%20Confiabilidade%20da%20Informação.md) | Princípios, arquitetura, contratos, métricas, papéis e sprints |
| [`docs/agents/evidencias.md`](docs/agents/evidencias.md) | Agente de Evidências: fluxo, corpus, índice, avaliação |
| [`docs/agents/evidencias_decisoes.md`](docs/agents/evidencias_decisoes.md) | ADRs do Agente de Evidências |
| [`docs/agents/texto.md`](docs/agents/texto.md) | Agente de Texto |
| [`docs/agents/socratico.md`](docs/agents/socratico.md) | Agente Socrático |
| [`docs/agents/sintetizador.md`](docs/agents/sintetizador.md) | Sintetizador, dossiê e guardrails |
| [`docs/agents/desempenho.md`](docs/agents/desempenho.md) | Medições de latência e otimizações |
| [`docs/relatorios/`](docs/relatorios/) | Relatórios de estado do projeto |

---

## 👥 Colaboradores

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/TulioCeleri">
        <img src="https://github.com/TulioCeleri.png?size=120" width="100" height="100" alt="Foto de Túlio Celeri" /><br />
        <sub><b>Túlio Celeri</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/eduarda-ogomes">
        <img src="https://github.com/eduarda-ogomes.png?size=120" width="100" height="100" alt="Foto de Maria Eduarda" /><br />
        <sub><b>Maria Eduarda</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/mcznh">
        <img src="https://github.com/mcznh.png?size=120" width="100" height="100" alt="Foto de Maria Carolina Frota" /><br />
        <sub><b>Maria Carolina Frota</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/AnaMarques37">
        <img src="https://github.com/AnaMarques37.png?size=120" width="100" height="100" alt="Foto de Ana Marques" /><br />
        <sub><b>Ana Marques</b></sub>
      </a>
    </td>
    <td align="center">
      <a href="https://github.com/femathrl0">
        <img src="https://github.com/femathrl0.png?size=120" width="100" height="100" alt="Foto de femathrl0" /><br />
        <sub><b>femathrl0</b></sub>
      </a>
    </td>
  </tr>
</table>

*Este projeto foi construído com foco em transparência explicável (XAI), privacidade (inferência 100% local) e no pensamento crítico de quem lê.*
