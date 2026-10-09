# Entrega: modelo de IA

Grupo 1 (ResIA). Sistema Multiagente de Avaliação de Confiabilidade da Informação.

Esta pasta reúne **só o modelo de IA**: como carregá-lo, executá-lo e avaliá-lo, e a documentação do processo. A interface (Streamlit), a sala dos agentes e os demais componentes de aplicação não fazem parte da entrega.

## Conteúdo

| Arquivo | O que é |
| --- | --- |
| [`notebook_modelo.ipynb`](notebook_modelo.ipynb) | Notebook que carrega o modelo, executa-o em notícias de exemplo e o avalia no gold set (Recall@5, cobertura, macro-F1 de stance, precisão/revocação por classe, matriz de confusão, evidência inventada, casamento errado), mais o experimento "mesma alegação", o histórico das rodadas e o pipeline completo com latência e guardrails. Salvo **com as saídas** da execução |
| [`modelo/modelo_evidencias.pkl`](modelo/modelo_evidencias.pkl) | Modelo ajustado (objeto `ModeloEvidencias`, pickle) |
| [`modelo/modelo_evidencias.json`](modelo/modelo_evidencias.json) | O mesmo conteúdo do `.pkl` em formato legível |
| [`relatorio_tecnico.md`](relatorio_tecnico.md) | Relatório técnico: dados, ajuste do modelo, critérios de escolha, métricas e resultados, desafios e aprendizados |
| [`modelo_evidencias.py`](modelo_evidencias.py) | Classe do modelo: `carregar`, `prever`, `buscar`, `avaliar`, `verificar_ambiente` |
| [`treinar_modelo.py`](treinar_modelo.py) | Script que ajusta o modelo (calibração dos limiares) e gera o `.pkl` |
| [`resultados/`](resultados/) | Saídas do ajuste (`treino_<data>.json`: grade de calibração e métricas por frase) e do notebook (`avaliacao_notebook.json`) |
| [`requirements-entrega.txt`](requirements-entrega.txt) | Dependências extras do notebook (Jupyter, matplotlib, scikit-learn) |

## O que está no `.pkl`

O modelo é o **Agente de Evidências**: busca densa (BGE-M3 + ChromaDB), etapa "mesma alegação" (termos-chave + NLI com mDeBERTa-v3) e stance pelo veredito da agência. Os pesos neurais são pré-treinados e públicos, e **não foram re-treinados** (motivo no relatório, seção 3). O `.pkl` guarda o que foi ajustado com dados:

- os **limiares de decisão** (similaridade ≥ 0,55; entailment ≥ 0,8; ancoragem ≥ 1 palavra), calibrados no split de calibração do gold set;
- o **vocabulário de nomes próprios** (4.150 palavras), extraído do corpus;
- o **mapeamento veredito → stance**;
- a **identificação exata** dos pesos (repositório e commit no Hugging Face) e do índice (coleção e número de trechos);
- a **grade de calibração** e as **métricas** medidas no ajuste.

Os pesos (~2,6 GB) e o índice vetorial (~1 GB) são grandes demais para o Git. O Hugging Face baixa os pesos na primeira execução, e o índice vem do Google Drive do grupo (ver `docs/agents/evidencias.md`, "Corpus e índice"). O notebook confere se as revisões e o índice disponíveis na máquina são os mesmos do modelo.

## Como executar

A partir da raiz do repositório:

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r entrega/requirements-entrega.txt
python -m spacy download pt_core_news_sm      # usado pelo Ingestor para segmentar as frases

# índice: chroma_data/ na raiz do repositório (ou EVIDENCE_CHROMA_PATH=/caminho/chroma_data)
jupyter lab entrega/notebook_modelo.ipynb
```

- **Sem o LM Studio:** o notebook roda inteiro e só pula a seção 8 (pipeline completo com o LLM).
- **Com o LM Studio** (`localhost:1234`, Qwen 2.5 7B Instruct carregado): o notebook detecta o modelo e roda também o grafo completo.

Para refazer o ajuste e regravar o `.pkl` (alguns minutos com os modelos em cache):

```bash
python entrega/treinar_modelo.py
```

## Resultado principal (split de teste, 21 frases)

| Métrica | Meta (Manual §7.1) | Obtido |
| --- | --- | --- |
| Recall@5 | ≥ 0,70 | **1,00** (12/12) |
| Macro-F1 de stance | ≥ 0,65 | **0,74** |
| Evidência inventada | ≤ 0,10 | **0,00** (0/5) |
| Casamentos errados | 0 | **2** ❌ |
| Cobertura | — | 0,83 (10/12) |
| Stance nas frases cobertas | — | 1,00 (10/10) |

A análise completa, incluindo os erros, está no notebook (seção 5) e no relatório (seção 5).
