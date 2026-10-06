# 🕵️‍♂️ Sistema Multiagente de Avaliação de Confiabilidade

> Projeto desenvolvido pelo **Grupo 1 (ResIA)** para avaliar a confiabilidade de informações e notícias utilizando Inteligência Artificial, sem substituir o pensamento crítico humano.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-Multiagente-orange)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)
![LMStudio](https://img.shields.io/badge/LLM-Local_Inference-lightgrey)

## 📖 Sobre o Projeto

O sistema recebe um texto suspeito ou a URL de uma notícia e devolve um **dossiê de evidências** montado por agentes especializados trabalhando em paralelo. 

**Princípio Fundamental:** O sistema opera no "padrão andaime". Ele **nunca** emite um veredito binário ("falso" ou "verdadeiro"). Em vez disso, ele fornece o contexto factual, expõe as falhas lógicas e aponta os viéses do texto, capacitando o usuário a tomar sua própria decisão.

---

## 🧠 Arquitetura dos Agentes

O projeto utiliza **LangGraph** para orquestrar 5 agentes em um grafo de estados com processamento paralelo:

1. 📥 **Agente Ingestor:** Realiza *scraping* (via Trafilatura) da URL, limpa ruídos do HTML, trunca textos muito longos por segurança e extrai a matéria bruta.
2. 🔍 **Agente de Evidências:** Faz buscas em um banco de dados vetorial local (**ChromaDB**) usando RAG. Compara as afirmações da notícia com as checagens do banco utilizando um modelo matemático de linguagem (**mDeBERTa-v3** / NLI) para definir se a evidência *Apoia*, *Contradiz* ou é *Insuficiente*.
3. 📝 **Agente de Texto:** Utiliza um LLM local configurado com *Contrastive Few-Shot Prompting* para analisar o discurso, identificando marcadores de viés, apelos emocionais e falácias lógicas na estrutura do argumento.
4. 🤔 **Agente Socrático:** Baseado no método da maiêutica, atua como um filósofo. Lê a notícia e formula perguntas incisivas que expõem lacunas lógicas para instigar o pensamento crítico do usuário.
5. 📊 **Agente Sintetizador:** O compilador final. Aguarda os três agentes analíticos terminarem e junta os fatos, estrutura e reflexões em um Dossiê organizado. Possui *Guardrails* arquiteturais para não usar palavras deterministas como "Fake News".

---

## 📂 Estrutura do Repositório

```text
grupo1_ResIA/
├── app/
│   └── app.py                  # Interface gráfica web (Streamlit)
├── data/
│   ├── corpus/
│   │   └── seed_db.py          # Script de inserção no banco de dados vetorial
│   └── gold/                   # Dataset de avaliação (gold set)
├── docs/
│   └── Manual...md             # Documentação oficial e princípios de design
├── src/
│   ├── agents/                 # Lógica individual de cada agente
│   │   ├── evidence.py
│   │   ├── ingestor.py
│   │   ├── socratic.py
│   │   ├── synthesizer.py
│   │   └── text_analysis.py
│   ├── retrieval/              # Configuração do ChromaDB e mDeBERTa
│   ├── services/               # Clientes LLM (Conexão com LMStudio via OpenAI API)
│   ├── graph.py                # Orquestração do grafo LangGraph
│   └── state.py                # Contratos de tipagem (Pydantic schemas)
└── README.md
```

---

## 🚀 Como Executar Localmente

### 1. Pré-requisitos
- Python 3.10 ou superior.
- [LMStudio](https://lmstudio.ai/) instalado para rodar os LLMs localmente (Recomendação: `Qwen 2.5 7B Instruct GGUF`).

### 2. Preparando o Ambiente
Clone o repositório e instale as dependências:
```bash
git clone https://github.com/eduarda-ogomes/grupo1_ResIA.git
cd grupo1_ResIA
python -m venv venv
source venv/bin/activate  # No Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Subindo o Motor de IA
1. Abra o **LMStudio** (ou use a CLI `lms`).
2. Carregue o modelo desejado (ex: Qwen 2.5) garantindo que o limite de contexto (`Context Length`) seja de pelo menos **16384 tokens**.
3. Inicie o "Local Server" na porta padrão `1234`.

### 4. Iniciando a Interface
Com o servidor do LMStudio rodando no fundo, execute o Streamlit **a partir da raiz do repositório** (com o `venv` ativado). Os stubs e o ChromaDB usam caminhos relativos à raiz:
```bash
streamlit run app/app.py
```
Acesse `http://localhost:8501` no seu navegador e comece a analisar!

Para rodar os testes (também da raiz, sem precisar definir `PYTHONPATH`):
```bash
pytest
```

### 5. Orquestração: timeouts e avisos

O grafo (`src/graph.py`) roda o Ingestor, depois Evidências, Texto e Socrático em paralelo, e por fim o Sintetizador. Cada nó tem um limite de tempo (`src/protecao.py`). Se um nó estoura o tempo ou quebra, o grafo segue sem ele, a interface mostra o aviso (por exemplo, `socratico: timeout`) e o dossiê sai assim mesmo.

| Nó | Padrão | Variável de ambiente |
| --- | --- | --- |
| Ingestor | 60 s | `GRAFO_TIMEOUT_INGESTOR` |
| Evidências, Texto, Socrático (cada um) | 240 s | `GRAFO_TIMEOUT_RAMO` |
| Sintetizador | 180 s | `GRAFO_TIMEOUT_SINTETIZADOR` |

Defina as variáveis antes de subir o Streamlit (ex.: `GRAFO_TIMEOUT_RAMO=400 streamlit run app/app.py`).

O nome do modelo no LM Studio vem de `LLM_MODEL` (padrão `qwen2.5-7b`). Use o identificador que aparece em `curl http://localhost:1234/v1/models`, por exemplo `LLM_MODEL=qwen/qwen2.5-7b-instruct streamlit run app/app.py`; com um nome desconhecido, o LM Studio recusa a chamada e os agentes de LLM avisam "falha ao chamar o modelo".

Na primeira execução, o Agente de Evidências baixa e carrega o BGE-M3 e o mDeBERTa, o que pode passar do limite e gerar `evidencias: timeout`. O carregamento continua em segundo plano (uma única vez, mesmo que outra análise comece no meio): espere um ou dois minutos antes de analisar de novo. Na demo, faça uma análise de aquecimento antes de apresentar.

Um nó que estoura o tempo não é interrompido: ele segue rodando em segundo plano até terminar (o Agente de Texto, por exemplo, continua chamando o LM Studio para os lotes restantes), o que pode deixar a análise seguinte mais lenta. Se o Sintetizador estourar o tempo, o dossiê sai assim mesmo, montado sem o modelo.

Para rodar o grafo inteiro com os modelos reais e ver o tempo de cada nó (fora do CI):
```bash
pytest tests/integration/test_grafo_lmstudio.py -v -s
```

---
*Este projeto foi arquitetado focado em escalabilidade, transparência explicável (XAI) e privacidade (inferência 100% local).*