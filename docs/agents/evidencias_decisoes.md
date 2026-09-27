# Agente de Evidências — decisões de projeto

Dono: R2 (Túlio Celeri) · Branch: `AgenteEvidencias` · Última atualização: 26/09/2026

Este documento registra as decisões tomadas na implementação do Agente de Evidências, por que foram tomadas e o que fica em aberto. Complementa a Seção 4.2 do manual; quando algo aqui diverge do manual, a divergência está marcada e justificada.

## 1. Resumo

Para cada frase da notícia (`segments`), o agente busca os trechos mais próximos num índice ChromaDB de checagens publicadas e classifica a relação com um modelo de NLI: `apoia`, `contradiz` ou `insuficiente`. Não usa LLM gerador. Toda evidência sai com o link exato da checagem.

```text
segments ──► busca top-5 por frase ──► limiar + URL obrigatória + 1 trecho por URL (máx. 3)
         ──► NLI em lote (premissa = trecho, hipótese = frase) ──► stance ──► list[Evidence]
```

## 2. Contrato com o grafo

| Decisão | Justificativa |
| --- | --- |
| A função é `run(state) -> dict`, e há um alias `evidencias_node = run` | O manual (Seção 9.4) exige `run`; o alias mantém o `graph.py` atual funcionando até o orquestrador trocar o import. Remover o alias depois. |
| O agente lê **só** `state.segments` | Menor acoplamento possível com o `PipelineState`. Nos testes, basta um objeto com `segments`. |
| Aceita `Segment` de qualquer classe, dicts ou objetos com `id`/`text` | O `Segment` do `state.py` é outra classe Python; o agente normaliza a entrada. |
| As evidências saem como **dicionários** com exatamente os campos de `Evidence` da Seção 3.3 | Testado: o Pydantic v2 rejeita instâncias de outra classe, mesmo com os mesmos campos. Dicts são validados pela classe `Evidence` do `state.py`, qualquer que seja a versão. |
| Schema local temporário em `src/agents/evidence_schema.py` | O `state.py` da `main` ainda não segue a Seção 3.3 e não deve ser alterado nesta branch (risco de conflito de merge). |

### 2.1 Os três resultados possíveis

| Saída | Significado |
| --- | --- |
| `{"evidence": [..]}` com objetos | Encontrou checagens acima do limiar para ao menos uma frase |
| `{"evidence": []}` | Buscou em todas as frases e nada passou do limiar (ou não havia frases) |
| `{"evidence": None, "warnings": ["evidencias: ..."]}` | O agente falhou: índice ausente, modelo que não carrega etc. (degradação graciosa, Seção 3.4) |

Índice ausente é tratado como **falha**, e não como "nenhuma checagem": sem índice, o sistema não pode afirmar que procurou.

### 2.2 Os dois sentidos de "insuficiente" (Seção 4.8, item 1)

- Nenhuma checagem acima do limiar para a frase → **nenhum objeto** `Evidence` para ela.
- Checagem encontrada, mas o NLI não indica apoio nem contradição → `Evidence` com stance `insuficiente` **e** `source_url`.

### 2.3 O que muda quando o `state.py` da Seção 3.3 entrar na `main`

1. Em `src/agents/evidence.py` e `src/stubs/evidence_stub.py`, trocar o import para `from src.state import Evidence, Segment`.
2. Apagar `src/agents/evidence_schema.py`.
3. Rodar `python -m pytest tests/contract/test_evidence_contract.py`. O teste já detecta o `state.py` novo sozinho e passa a validar a saída contra ele também.

Enquanto o `state.py` antigo estiver na `main`, o grafo completo **não** aceita a saída nova (o `Evidence` antigo exige `retrieved_from` e o State antigo não tem `warnings`). O agente roda isolado e pelos testes, como prevê o fluxo de stubs da Seção 9.4.

**Aviso para a interface (R4):** o `app/app.py` atual lê as evidências das atualizações do grafo como objetos (`ev.stance`) e faz `.extend(value)`. Com o contrato novo, essas atualizações chegam como dicts e podem ser `None`; a interface precisa tratar os dois casos.

## 3. Recuperação

| Decisão | Valor padrão | Justificativa |
| --- | --- | --- |
| Modelo de embedding | `BAAI/bge-m3` | Candidato da Seção 5.3. Não usa prefixos (esquecer `query:`/`passage:` no e5 piora a busca sem dar erro) e aceita trechos longos. A escolha final sai do Recall@5 contra o multilingual-e5-large. |
| Embeddings calculados pelo nosso código, não pela `embedding_function` do Chroma | — | Controle de dispositivo, fp16 e prefixos; o mesmo código serve à indexação e à busca. |
| Uma coleção por modelo | `checagens__<modelo>` | Trocar de modelo exige reindexar; coleções separadas permitem comparar modelos sem misturar índices. |
| Distância | cosseno | Similaridade = 1 − distância, fácil de interpretar e de calibrar. |
| Resultados por frase | top-5 | Necessário para medir Recall@5 (Seção 7.1). |
| Limiar de similaridade | 0,75 (**provisório**) | Principal defesa contra "evidência inventada" (meta ≤ 0,10). Calibrar com o gold set: as 15 frases sem checagem definem o piso. |
| Um trecho por URL em cada frase, no máximo 3 por frase | 3 | Evita repetir a mesma checagem no dossiê; o Sintetizador também deduplica por URL. |
| Trecho sem `source_url` é descartado antes do NLI | — | Citação obrigatória (Seção 1.1). |
| Caminho do índice relativo à raiz do repositório | `chroma_data/` | O código antigo dependia da pasta de onde se rodava o programa. |

## 4. Classificação de stance (NLI)

| Decisão | Valor padrão | Justificativa |
| --- | --- | --- |
| Modelo | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | Seção 4.2. |
| Entrada | par `text` = trecho da checagem, `text_pair` = frase da notícia | Premissa e hipótese como no manual. O código antigo mandava uma string única com `[SEP]`, que o pipeline não trata como par. |
| Mapeamento | entailment → `apoia`; contradiction → `contradiz`; neutral → `insuficiente` | Seção 4.2. |
| Probabilidade mínima | 0,5 (**provisório**) | Se o rótulo vencedor tiver menos que isso, vira `insuficiente` ("incerteza honesta"). |
| Todas as frases em um lote | — | Uma chamada de busca e uma de NLI por notícia, em vez de uma por frase. |
| Probabilidades completas registradas em log | logger `src.agents.evidence.nli`, nível DEBUG | O schema não tem campo de confiança. As probabilidades ficam fora do State, disponíveis para análise de erros e para o conformal (Seção 11). |

## 5. Trecho citado (`excerpt`) e veredito da agência

- O `excerpt` é sempre um **prefixo literal** do trecho indexado. Se passar de 300 caracteres, é cortado no fim de uma frase (ou num espaço). O código nunca acrescenta nem reescreve texto, nem reticências.
- `agency_verdict` vem do `textualRating` da Fact Check Tools API, guardado nos metadados de cada trecho. Veredito vazio vira `None`. O agente só repassa o veredito com atribuição; a decisão de exibi-lo como selo fora do texto do LLM é da Seção 4.8, item 2 (Sintetizador e interface).

## 6. Corpus

Pipeline (Seção 6.1), em três scripts independentes que podem ser retomados:

```text
collect_factcheck_api.py ──► data/corpus/raw/factcheck_api.jsonl   (1 linha por URL de checagem)
fetch_articles.py        ──► data/corpus/raw/articles.jsonl        (texto completo via trafilatura)
build_index.py           ──► chroma_data/ (coleção do modelo atual)
```

| Decisão | Justificativa |
| --- | --- |
| API com `languageCode=pt`, filtro por site e paginação; padrão dos últimos 730 dias | Seção 6.1: "priorizando os últimos 24 meses". |
| Sites padrão: `aosfatos.org`, `agencialupa.org`, `lupa.uol.com.br`, `projetocomprova.com.br` | A Lupa já publicou em mais de um domínio; o script informa quantas checagens cada site devolveu, para confirmar quais funcionam. |
| Deduplicação por URL na coleta e no download | Seção 6.1. |
| Dados brutos em `data/corpus/raw/`, fora do Git (`.gitignore`) | "Não versionar dados brutos grandes" (Seção 5.5). |
| Trechos: parágrafos agrupados até 800 caracteres, sobreposição de 1 parágrafo, parágrafos com menos de 40 caracteres descartados | "Chunking por parágrafo com sobreposição" (Seção 6.1). 800 caracteres ficam bem abaixo do limite de 512 tokens do NLI. |
| IDs determinísticos (`sha1(url)` + índice) e `upsert` | Rodar a indexação de novo atualiza em vez de duplicar. |
| Metadados por trecho | `source_url`, `source_name`, `agency_verdict`, `review_date`, `claim_reviewed`, `chunk_index`, `describes_rumor`. O `claim_reviewed` fica guardado para a opção 3 da Seção 7. |
| `seed_db.py` indexa só os dois trechos do exemplo da Seção 4.6 | Permite ver o agente rodando sem chave de API nem internet. Recria a coleção: depois dele, rodar `build_index.py` de novo. |

O loader do FACTCK.BR fica para depois: antes é preciso conferir formato, data de corte e licença.

## 7. Proteção contra o boato citado (opção 1, desligada por padrão)

**Problema.** Checagens costumam começar reproduzindo o boato ("Circula nas redes um vídeo em que um homem afirma que o chá de mamão cura a dengue…"). Esse parágrafo é o mais parecido com a frase da notícia, então é recuperado primeiro. Com ele como premissa, o NLI pode dar neutral (a contradição da checagem some) ou entailment (o sistema marca `apoia` para um boato desmentido).

**Confirmado no teste de fumaça** (ChromaDB real, embeddings simulados): sem a proteção, o parágrafo do boato ficou em 1º lugar e, como só um trecho por URL é mantido, foi ele que virou o `excerpt` da evidência. Mesmo quando o NLI acerta a stance, o usuário veria o boato como citação da agência.

**O que foi implementado (opção 1).** Na indexação, cada parágrafo é classificado por expressões ("circula nas redes", "vídeo afirma", "posts alegam", "segundo a publicação" etc.) e marcado em `describes_rumor`. Um trecho nunca mistura parágrafo do boato com parágrafo de conclusão. Com `EVIDENCE_FILTER_RUMOR=1`, a busca ignora os trechos marcados, que nunca viram premissa nem `excerpt`.

**Por que desligada por padrão.** O padrão segue o manual; a chave permite medir com e sem a proteção no gold set e levar números ao grupo.

**Limitações.** A lista de expressões é inicial e deixa passar textos fora do padrão. Revisar com exemplos reais depois da primeira coleta (o `build_index.py` informa quantos trechos foram marcados).

**Alternativas em aberto, para decisão do grupo (ADR):**

- **Opção 2:** recuperar por qualquer parágrafo (o do boato é o melhor para achar o artigo), mas rodar o NLI e tirar o `excerpt` só dos parágrafos de conclusão daquele mesmo artigo.
- **Opção 3:** usar o NLI para confirmar que a frase é a mesma alegação do `claim_reviewed` e derivar a stance do veredito da agência. Também ataca o risco do "fato parecido, mas diferente", mas muda a técnica da Seção 4.2.

## 8. Dispositivo e memória

- Dispositivo escolhido automaticamente: `cuda` → `mps` → `cpu` (`EVIDENCE_DEVICE` força um valor). O manual assume MacBook com MPS; o mesmo código roda em Windows.
- Embeddings em fp16 quando há GPU, para caber no orçamento de < 2 GB para embeddings + NLI (Seção 5.2). O NLI fica em fp32 por padrão (`EVIDENCE_NLI_FP16=1` para testar fp16). Medir a memória real na máquina da demo.
- Os modelos são carregados uma única vez por processo.

## 9. Configuração

Tudo em `src/retrieval/config.py`, sobrescrevível por variável de ambiente. O `services/llm.py` é do R1 e trata só de LLM, por isso a configuração deste agente fica separada.

| Variável | Padrão | Uso |
| --- | --- | --- |
| `EVIDENCE_EMBEDDING_MODEL` | `BAAI/bge-m3` | Modelo de embedding |
| `EVIDENCE_NLI_MODEL` | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | Modelo de NLI |
| `EVIDENCE_SIM_THRESHOLD` | `0.75` | Limiar de similaridade (provisório) |
| `EVIDENCE_NLI_MIN_PROB` | `0.5` | Probabilidade mínima do rótulo do NLI (provisório) |
| `EVIDENCE_TOP_K` | `5` | Trechos buscados por frase |
| `EVIDENCE_MAX_PER_SEGMENT` | `3` | Evidências por frase |
| `EVIDENCE_EXCERPT_MAX_CHARS` | `300` | Tamanho máximo do `excerpt` |
| `EVIDENCE_FILTER_RUMOR` | `0` | Proteção contra o boato citado |
| `EVIDENCE_CHUNK_MAX_CHARS` / `EVIDENCE_CHUNK_OVERLAP` / `EVIDENCE_MIN_PARAGRAPH_CHARS` | `800` / `1` / `40` | Chunking |
| `EVIDENCE_DEVICE` | automático | `cpu`, `cuda` ou `mps` |
| `EVIDENCE_EMBEDDING_FP16` / `EVIDENCE_NLI_FP16` | `1` / `0` | Precisão na GPU |
| `EVIDENCE_BATCH_SIZE` | `16` | Lote de embeddings e NLI |
| `EVIDENCE_CHROMA_PATH` / `EVIDENCE_RAW_DIR` | `chroma_data/` / `data/corpus/raw/` | Caminhos |
| `FACTCHECK_API_KEY` | — | Chave da Fact Check Tools API |

## 10. Testes

Rodar sempre **a partir da raiz** com `python -m pytest` (assim a raiz entra no `sys.path` e os imports `src.` funcionam). O `pytest` não está no `requirements.txt`; instale com `pip install pytest`.

| Arquivo | O que cobre |
| --- | --- |
| `tests/contract/test_evidence_contract.py` | Stub e agente real: campos exatos da Seção 3.3, stance válida, URL não vazia, `segment_id` existente, só as chaves `evidence`/`warnings`; falha → `None` + aviso |
| `tests/unit/test_evidence_unit.py` | Mapeamento do NLI, `excerpt` literal, limiar, deduplicação, caso do mamão (Seção 4.6), casos de borda da Seção 4.7, compatibilidade com outras classes de `Segment` |
| `tests/unit/test_evidence_chunking.py` | Marcação "descreve o boato", separação boato/conclusão, tamanho máximo e sobreposição |
| `tests/integration/test_evidence_integration.py` | Diagnóstico com o NLI real nos casos "fato parecido" (chikungunya × dengue) e "boato citado"; roda só com `EVIDENCE_INTEGRATION=1` |

Fixtures: `tests/fixtures/caso_mamao_dengue/` (Seção 4.6) e `tests/fixtures/bordas/evidencias_*.json` (Seção 4.7). Nos casos sintéticos, agência e URLs são fictícias (`exemplo.org`); o parágrafo do boato em `evidencias_boato_citado.json` é texto sintético, não citação da checagem real.

## 11. Como rodar

Comandos a partir da raiz do repositório. Variáveis de ambiente no PowerShell (terminal padrão do VS Code no Windows); no macOS/Linux, use `export NOME=valor`.

```powershell
# 1. Teste rápido, sem internet para a API (baixa os modelos na primeira vez)
python data/corpus/seed_db.py
$env:EVIDENCE_INTEGRATION = "1"
python -m pytest tests/integration/test_evidence_integration.py -v -s

# 2. Corpus real
$env:FACTCHECK_API_KEY = "sua-chave"
python data/corpus/collect_factcheck_api.py
python data/corpus/fetch_articles.py
python data/corpus/build_index.py --reset
```

## 12. Pendências e decisões em aberto

| Item | Quando | Depende de |
| --- | --- | --- |
| Calibrar `EVIDENCE_SIM_THRESHOLD` e `EVIDENCE_NLI_MIN_PROB` | Após as 12 entradas do gold set | Gold set (formato do R3) |
| Comparar BGE-M3 × multilingual-e5-large por Recall@5 | Sprint 2 | Corpus indexado + gold set |
| Script de métricas (Recall@5, macro-F1 de stance, taxa de evidência inventada) | Sprint 2 | Harness comum do R3 |
| Medir o efeito da proteção contra o boato; decidir entre opções 1, 2 e 3 | Sprint 3 | Métricas acima; decisão do grupo (ADR) |
| Loader do FACTCK.BR | Sprint 3 | Conferir formato e licença |
| Escolher, dentro do trecho, a frase mais relevante como `excerpt` (hoje é o início do trecho) | Sprint 3 | — |
| Conformal prediction (Seção 11): exigirá campo de conjunto/probabilidades no schema | Só se o macro-F1 de stance estiver estável | ADR de mudança no `state.py` |
| Card do agente em `docs/agents/` | Sprint 4 | — |
