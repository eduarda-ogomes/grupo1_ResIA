# Agente de Evidências — decisões de projeto

Dono: R2 (Túlio Celeri) · Branch: `AgenteEvidencias` · Última atualização: 28/09/2026

> **Simplificação de 28/09 (etapa 1).** O código passou a ter um único modo (o `alegacao`): o modo `trecho`, a heurística e a proteção contra o boato citado, o `seed_db.py` e as chaves `EVIDENCE_STANCE_MODE`, `EVIDENCE_KEY_TERM_CHECK`, `EVIDENCE_CLAIM_NORMALIZE`, `EVIDENCE_FILTER_RUMOR`, `EVIDENCE_NLI_MIN_PROB`, `EVIDENCE_TOP_K` e as de chunking/precisão foram removidos (termos-chave e normalização ficam sempre ligados). Checagens sem `claim_reviewed` passam a ser ignoradas. O comportamento do modo padrão não mudou. As seções abaixo que falam desses itens descrevem o histórico; este documento será reescrito como card do agente + ADR na etapa 2.

Este documento registra as decisões tomadas na implementação do Agente de Evidências, por que foram tomadas e o que fica em aberto. Complementa a Seção 4.2 do manual. **Onde há divergência do manual, ela está marcada com ⚠️ e justificada.** O histórico datado das decisões está na Seção 15.

## 1. Resumo

Para cada frase da notícia (`segments`), o agente busca trechos de checagens publicadas num índice ChromaDB e devolve evidências com o link exato da checagem. Não usa LLM gerador. Há dois modos de decidir a stance; o padrão é o modo `alegacao`.

```text
Modo "alegacao" (PADRÃO)                                    Modo "trecho" (Seção 4.2 do manual)
────────────────────────                                    ───────────────────────────────────
frase ─► busca 10 trechos (similaridade ≥ 0,55)             frase ─► busca 10 trechos (similaridade ≥ 0,55)
      ─► agrupa por checagem (até 6 candidatas;                   ─► 1 trecho por checagem (máx. 3)
         mesma checagem em 2 endereços conta 1)                   ─► NLI(trecho → frase)
      ─► ETAPA 2: é a mesma alegação?                             ─► stance = rótulo do NLI
           a) termos-chave: há TROCA de nome, número              ─► excerpt = trecho recuperado
              ou doença entre frase e alegação?
           b) NLI(alegação sem "Foto mostra" ↔ frase),
              2 direções, entailment ≥ 0,5 em alguma?
      ─► no máximo 3 checagens por frase
      ─► stance = veredito da agência
      ─► excerpt = título da checagem (conclusão da agência)
```

## 2. Contrato com o grafo

| Decisão | Justificativa |
| --- | --- |
| A função é `run(state) -> dict`, e há um alias `evidencias_node = run` | O manual (Seção 9.4) exige `run`; o alias mantém o `graph.py` atual funcionando até o orquestrador trocar o import. Remover o alias depois. |
| O agente lê **só** `state.segments` | Menor acoplamento possível com o `PipelineState`. Nos testes, basta um objeto com `segments`. |
| Aceita `Segment` de qualquer classe, dicts ou objetos com `id`/`text` | O `Segment` do `state.py` é outra classe Python; o agente normaliza a entrada. |
| As evidências saem como **dicionários** com exatamente os campos de `Evidence` da Seção 3.3 | Testado: o Pydantic v2 rejeita instâncias de outra classe, mesmo com os mesmos campos. Dicts são validados pela classe `Evidence` do `state.py`, qualquer que seja a versão. |
| Schema local temporário em `src/agents/evidence_schema.py` | O `state.py` da `main` ainda não segue a Seção 3.3 e não deve ser alterado nesta branch (risco de conflito de merge). |
| Nenhuma mudança de schema foi necessária para o modo `alegacao` | O `Evidence` da Seção 3.3 já tem tudo o que o modo usa. |

### 2.1 Os três resultados possíveis

| Saída | Significado |
| --- | --- |
| `{"evidence": [..]}` com objetos | Encontrou checagens para ao menos uma frase |
| `{"evidence": []}` | Buscou em todas as frases e nada passou dos filtros (ou não havia frases) |
| `{"evidence": None, "warnings": ["evidencias: ..."]}` | O agente falhou: índice ausente, modelo que não carrega, modo inválido etc. (degradação graciosa, Seção 3.4) |

Índice ausente é tratado como **falha**, e não como "nenhuma checagem": sem índice, o sistema não pode afirmar que procurou.

### 2.2 Os dois sentidos de "insuficiente" (Seção 4.8, item 1)

- Nenhuma checagem passou dos filtros para a frase → **nenhum objeto** `Evidence` para ela. No modo `alegacao`, uma checagem que não é a mesma alegação também cai aqui.
- Checagem encontrada, mas sem conclusão clara → `Evidence` com stance `insuficiente` **e** `source_url`. No modo `alegacao`, isso acontece quando o veredito da agência não é "falso" nem "verdadeiro" (ex.: "Enganoso", "Falta contexto").

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
| Trechos buscados por frase | 10 (`SEARCH_K`) | Como os trechos são agrupados por checagem, 10 trechos garantem candidatos suficientes. O Recall@5 da avaliação usa os 5 primeiros (`TOP_K`). |
| Limiar de similaridade | **0,55** (provisório; era 0,75) | Medido em 27/09 com o BGE-M3 no corpus real (Seção 13): outro assunto ≈ 0,45; mesmo assunto, outro fato ≈ 0,55–0,57; a checagem certa ≈ 0,58–0,59. Com 0,75 o agente nunca emitiria nada. O limiar só separa "outro assunto"; distinguir "outro fato" é papel da etapa 2 (Seção 4). |
| Até 3 checagens por frase | 3 | Evita repetir checagens no dossiê; o Sintetizador também deduplica por URL. |
| Trecho sem `source_url` é descartado | — | Citação obrigatória (Seção 1.1). |
| Caminho do índice relativo à raiz do repositório | `chroma_data/` | O código antigo dependia da pasta de onde se rodava o programa. |

## 4. Decisão de stance

### 4.1 ⚠️ Modo `alegacao` como padrão (diverge da Seção 4.2)

**Status:** adotado na branch em 27/09/2026 por decisão do dono do agente (R2). **Precisa ser levado ao grupo e registrado como ADR**, porque muda a técnica descrita na Seção 4.2. O modo do manual continua disponível (`EVIDENCE_STANCE_MODE=trecho`).

**Contexto.** A Seção 4.2 define a stance pelo NLI entre o trecho recuperado (premissa) e a frase da notícia (hipótese). Os testes com os modelos reais mostraram que isso falha nos dois riscos que o manual trata como mais graves (Seção 12.1):

| Teste (26/09, mDeBERTa real) | NLI | Stance no modo `trecho` | O que devia sair |
| --- | --- | --- | --- |
| Checagem de dengue × frase sobre chikungunya ("fato parecido") | contradiction 0,93 | `contradiz` | no máximo `insuficiente` |
| Parágrafo que reproduz o boato × a frase do boato | entailment 0,99 | `apoia` | nunca `apoia` |

O modelo errou com 93% e 99% de confiança; subir a probabilidade mínima do NLI não resolve. E a similaridade também não separa "a mesma alegação" de "um fato parecido": no caso Fachin (27/09), a checagem certa ficou em 0,59 e uma checagem sobre outro fato do mesmo ministro em 0,57.

**Decisão.** Uma etapa extra decide se a checagem trata da **mesma alegação** que a frase, comparando a frase com o `claim_reviewed` (a alegação que a agência checou, vinda da Fact Check Tools API):

1. Os trechos recuperados acima do limiar são agrupados por checagem (URL).
2. **Termos-chave** (`KEY_TERM_CHECK`, ligada; Seção 4.1.1): se um nome próprio, número ou nome de doença da frase não aparece na checagem (alegação, título e texto) **e** a alegação tem um termo da mesma classe que a frase não tem, é uma troca ("chikungunya" × "dengue") e a checagem é descartada antes do NLI.
3. **NLI**: compara `claim_reviewed → frase` e `frase → claim_reviewed`, com a alegação sem o "Foto/Vídeo/Imagem mostra" (`CLAIM_NORMALIZE`, ligada desde 28/09). A checagem segue se o entailment for ≥ 0,5 (`CLAIM_MATCH_MIN_PROB`) **em pelo menos uma direção**. Uma direção basta porque a notícia costuma ser mais específica ou mais genérica que a alegação checada ("o chá cura a dengue em três dias" implica "o chá cura a dengue", não o contrário).
   São avaliadas até 6 checagens por frase (`CLAIM_CANDIDATES`); a mesma checagem publicada em dois endereços (mesmo título, ex.: UOL e BOL) conta uma vez; a saída é limitada a 3 por frase **depois** da etapa 2.
4. Checagem que não é a mesma alegação é descartada: não gera objeto.
5. A stance vem do **veredito da agência** (Seção 5): falso → `contradiz`, verdadeiro → `apoia`, o resto → `insuficiente`.
6. O `excerpt` é o **título da checagem**, que é a conclusão da agência escrita por ela (Seção 6).
7. Checagens sem `claim_reviewed` (o seed, ou o FACTCK.BR no futuro) seguem o método da Seção 4.2 para aquela checagem.

**Por que o NLI entre alegações ajuda.** A tendência do NLI de marcar como equivalentes frases com muitas palavras em comum — o que causou o `apoia` do boato citado — é útil para reconhecer paráfrases da mesma alegação. O parágrafo do boato deixa de ser premissa: ele só ajuda a busca a achar a checagem certa.

**Custos.** Nenhuma memória extra (usa o mDeBERTa já carregado). A checagem de termos-chave é uma consulta ao índice por checagem candidata; o NLI faz duas comparações por candidata, num único lote por notícia: alguns segundos na CPU.

#### 4.1.1 O que os testes com o modelo real mostraram (27/09) e a checagem de termos-chave

A previsão de 27/09 de que o NLI entre alegações também rejeitaria "dengue × chikungunya" **estava errada**. Com o mDeBERTa real, em 6 pares de teste:

| Par | Entailment (alegação→frase / frase→alegação) | Etapa 2 só com NLI | Certo? |
| --- | --- | --- | --- |
| Paráfrase do caso Fachin ("Foto mostra Edson Fachin apontando o dedo…") | 0,000 / 0,008 | rejeitou | ❌ checagem certa perdida |
| Fachin × outro fato | 0,003 / 0,001 | rejeitou | ✅ |
| Paráfrase do caso mamão | 0,994 / 0,998 | casou | ✅ |
| **Mamão: dengue × chikungunya** | **0,987 / 0,969** | **casou** | ❌ **erro grave** |
| Paráfrase do Bolsa Família | 0,999 / 0,999 | casou | ✅ |
| Bolsa Família: R$ 600 × R$ 1.800 | 0,007 / 0,002 | rejeitou | ✅ |

Duas conclusões: (1) o NLI percebe troca de **número**, mas não troca de **nome** entre frases quase idênticas; (2) alegações escritas como "Foto/Vídeo mostra X" não são tratadas como equivalentes a "X" (cerca de 10% das alegações do corpus começam assim).

**Termos-chave (ligada por padrão; versão inicial, ajustada na Seção 4.1.2).** Para o erro (1), a checagem exige que os **nomes próprios, números e nomes de doenças** da frase apareçam no texto da checagem. Detalhes:

- nome próprio = palavra com maiúscula fora do início da frase; a primeira palavra só conta se a seguinte também tiver maiúscula ("Eduardo Bolsonaro…");
- números normalizados ("R$ 5 mil" = "R$ 5.000" = 5000);
- lista curta de doenças, que em minúscula funcionam como nomes (dengue, zika, chikungunya, covid…);
- comparação por prefixo de 5 letras, para tolerar variações ("Paraguai"/"paraguaio").

Calibração em 28/09, sem o NLI, nos 35 pares de `data/corpus/pares_etapa2.json` (alegações reais do corpus, frases escritas para o teste): **aceitou as 16 paráfrases e rejeitou as 8 trocas de nome**; errou em 4 casos que são do NLI (duas negações, "R$ 600" presente no texto da checagem, outro fato sobre o Pix). Uma versão por palavras raras (IDF) foi testada e descartada: reprovava de 5 a 16 paráfrases, porque paráfrases trazem palavras novas.

Ressalvas: a regra foi calibrada nos mesmos pares em que foi medida, e a lista de doenças foi motivada pelo caso da chikungunya; o número é otimista, e a validação de verdade é o gold set. Ela está ligada por padrão, antes do experimento com o NLI, porque só torna o agente **mais conservador** (pode perder evidência, nunca inventar) e barra o erro mais grave conhecido. Para desligar: `EVIDENCE_KEY_TERM_CHECK=0`.

**Normalização (desligada inicialmente; ligada em 28/09, Seção 4.1.2).** Para o erro (2), `CLAIM_NORMALIZE` tira "Foto mostra", "Vídeo mostra que", "Em áudio," etc. do início da alegação antes do NLI (altera 596 das 5.826 alegações). Não se sabe ainda se o NLI casa "Edson Fachin apontando o dedo…" (sintagma sem verbo) com a paráfrase; fica desligada até o experimento medir. Limitação: em "Imagem de Lula mostra presidente…", o nome sai junto com o prefixo.

#### 4.1.2 Resultado do experimento (28/09) e ajustes

`python data/corpus/experimento_etapa2.py`, NLI real, 35 pares:

| Variante | Acertos | **Casou errado** | Paráfrase perdida |
| --- | --- | --- | --- |
| A — só NLI | 31/35 | **3** (chikungunya, Fux, R$ 50 mil) | 1 |
| B — NLI + normalização | 31/35 | **3** | 1 |
| **C — NLI + termos-chave** | **34/35** | **0** | 1 (Fachin) |
| **D — C + normalização** | **34/35** | **0** | 1 (Fachin) |
| E — só termos-chave | 31/35 | 4 (negações, R$ 600) | 0 |

- O NLI e os termos-chave se completam: o NLI erra troca de nome, que os termos pegam; os termos erram negação, que o NLI pega.
- Os limiares 0,5, 0,7 e 0,9 deram resultados idênticos: o NLI responde perto de 0 ou de 1. **Mantido 0,5.**

O diagnóstico com o índice real (frase do Fachin) mostrou três problemas que o experimento não pegava, corrigidos em 28/09:

1. **Termos-chave estritos demais em checagens só com título.** "STF" estava na frase e não no título da AFP e do UOL, e as duas checagens certas foram rejeitadas. **Correção:** um termo ausente só reprova se a alegação tiver um termo da mesma classe ausente da frase (a assinatura de uma troca). Nomes compostos viram um grupo ("Alexandre de Moraes"); a primeira palavra da frase passa a contar como nome, exceto palavras comuns de início ("Governo", "Vídeo", "Presidente"…); "Covid-19" não gera o número 19.
2. **A normalização ajuda em casos reais.** Alegação do UOL "Imagem mostra Fachin apontando o dedo para Moraes": entailment 0,09 → **0,99** sem o "Imagem mostra". No experimento ela não criou casamento errado. **`CLAIM_NORMALIZE` ligada.**
3. **O limite de 3 vinha antes da etapa 2.** As 3 vagas foram de AFP, UOL e BOL (o mesmo texto do UOL em outro endereço), e o Aos Fatos nem foi avaliado. **Correção:** até 6 candidatas na etapa 2, mesma checagem em dois endereços conta uma vez, limite de 3 aplicado no fim.

Resultado com as correções (37 pares: os 35 + Fachin × AFP e Fachin × UOL, checagens só com título), usando as probabilidades do NLI já medidas: **35/37, 0 casou errado**, 2 perdidos (Fachin × Aos Fatos e Fachin × AFP: mesmo normalizada, "Imagem mostra Edson Fachin com dedo em riste…" tem entailment 0,07). Antes das correções: 34/37, 0 casou errado, 3 perdidos.

Ressalvas: (a) as regras foram ajustadas nos mesmos pares em que foram medidas; a validação é o gold set. (b) A regra de termos-chave ficou mais tolerante: **sozinha**, sem o NLI, agora casa errado em 7 dos 37 pares (antes, 4). As duas verificações precisam andar juntas. (c) A lista de palavras comuns de início de frase é curta e feita à mão. Para confirmar com o NLI real, rodar de novo `experimento_etapa2.py` (37 pares).

**Limitações conhecidas.**

- Depende da qualidade do `claim_reviewed` (preenchido em todas as checagens coletadas; mediana de 68 caracteres). Algumas alegações são o texto cru do post ("ÚLTIMOS MOMENTOS DE RICK ANTES DO ACIDENTE"), difíceis de comparar.
- **Frases que desmentem o boato** ("a foto de Fachin é falsa") não têm entailment com a alegação e ficam sem evidência. É conservador, mas é uma perda de cobertura. Se casassem, a stance sairia errada (o veredito "Falso" se refere ao boato, não à frase que o desmente).
- A checagem de termos-chave depende de maiúsculas corretas no texto de entrada, e uma troca entre termos de classes diferentes (nome × doença) não é detectada por ela.
- Stance do tipo `apoia` fica rara, porque o corpus quase não tem vereditos "verdadeiro" (Seção 5).
- Frases compostas continuam difíceis para o NLI (risco residual da Seção 2.1 do manual).

**Alternativas consideradas.**

| Alternativa | Por que não agora |
| --- | --- |
| Manter o modo `trecho` e só ajustar limiares | Os erros dos testes têm confiança de 93–99%; nenhum limiar os separa. |
| Reranker (ex.: `bge-reranker-v2-m3`), citado na Camada 3 do manual | Mede relevância, não "mesma alegação"; provavelmente deixaria passar o outro fato de Fachin. Custa ~1,1 GB e latência. Pode entrar depois como complemento. |
| Checagem de termos-chave sozinha, sem NLI | Adotada como reforço do NLI em 28/09 (Seção 4.1.1). Sozinha, não pega negações nem "outro fato" com os mesmos nomes. |
| LLM local (8B) como juiz de "mesma alegação", uma chamada por notícia | Provavelmente mais preciso em trocas de nome e negações, mas muda a arquitetura (o manual diz que este agente não usa LLM gerador) e acrescenta uma chamada de LLM por notícia. Fica como opção se o experimento e o gold set mostrarem que NLI + termos-chave não basta; decisão do grupo. |

**Como comparar os dois modos.** Rodar a avaliação do gold set com `EVIDENCE_STANCE_MODE=alegacao` e `=trecho` e comparar Recall@5, macro-F1 de stance e taxa de evidência inventada. É material para o relatório final, na linha do experimento de controle da Seção 7.3.

**Por que já é o padrão, antes da decisão do grupo.** O modo do manual produziu `apoia` para um boato desmentido nos testes. Um padrão que sabidamente erra desse jeito é arriscado se alguém integrar o agente antes da discussão.

### 4.2 Modo `trecho` (Seção 4.2 do manual)

| Decisão | Valor padrão | Justificativa |
| --- | --- | --- |
| Modelo | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | Seção 4.2. Usado também na etapa 2 do modo `alegacao`. |
| Entrada | par `text` = trecho da checagem, `text_pair` = frase da notícia | Premissa e hipótese como no manual. O código antigo mandava uma string única com `[SEP]`, que o pipeline não trata como par. |
| Mapeamento | entailment → `apoia`; contradiction → `contradiz`; neutral → `insuficiente` | Seção 4.2. |
| Probabilidade mínima | 0,5 (provisório) | Se o rótulo vencedor tiver menos que isso, vira `insuficiente`. |
| Todas as frases em um lote | — | Uma chamada de busca e uma de NLI por notícia. |

Nos dois modos, as probabilidades completas do NLI vão para o log `src.agents.evidence.nli` (nível DEBUG), fora do State, para análise de erros e para o conformal (Seção 11 do manual).

## 5. Veredito da agência

A Fact Check Tools API devolve o veredito (`textualRating`) em formatos variados. No corpus de 27/09:

| Formato | Exemplo | Tratamento |
| --- | --- | --- |
| Rótulo simples | `falso`, `Enganoso`, `Falta contexto`, `Sátira` | Comparado sem maiúsculas nem acentos |
| Rótulo com sublinhados (Aos Fatos) | `não_é_bem_assim` | Sublinhados viram espaços |
| Rótulo + explicação (Comprova) | `Falso: Na verdade, uma empresa...` | Rótulo = parte antes de `:` (se curta) |
| Texto livre, sem rótulo | `É mentirosa a afirmação de que...` | `insuficiente` (conservador) |

Mapeamento (`src/retrieval/verdicts.py`), deliberadamente conservador: só rótulos inequívocos viram `contradiz` (falso, falsa, fake, montagem, mentira…) ou `apoia` (verdadeiro, comprovado, correto…). Todo o resto — "Enganoso", "Não é bem assim", "Falta contexto", "Contextualizando", "Sátira", "verdadeiro, mas…", texto livre e rótulos desconhecidos — vira `insuficiente`.

Distribuição nas 1.109 checagens coletadas: **924 `contradiz`**, 180 `insuficiente`, **5 `apoia`**. Corpora de checagem desmentem muito mais do que confirmam; o gold set terá poucos casos de `apoia`, o que pesa no macro-F1 de stance. Vale considerar isso na anotação.

O `agency_verdict` da evidência sai com o rótulo como publicado, sem sublinhados e sem a explicação ("Falso", "Não é bem assim"), pronto para o selo com atribuição da Seção 4.8, item 2. Para revisar o mapeamento: `python data/corpus/diagnostico.py --vereditos`.

## 6. Trecho citado (`excerpt`)

- **Modo `alegacao`:** o **título da checagem** (desde 28/09). O título é a conclusão da agência, escrita por ela, curta e literal ("Foto de briga entre Fachin e Moraes não é real, mas produzida por IA"; "É falso que presidente do Paraguai agradeceu a Lula na ONU…"), e vem da API para todas as checagens, inclusive as que não puderam ser baixadas. Sem título, usa o parágrafo de abertura (em 78% das checagens do Aos Fatos ele tem marcador explícito de conclusão); sem abertura indexada, o trecho recuperado mais similar que não esteja marcado como boato.
- **Modo `trecho`:** o próprio trecho recuperado.
- Nos dois modos, o `excerpt` é sempre um **prefixo literal** do texto indexado. Se passar de 300 caracteres, é cortado no fim de uma frase (ou num espaço). O código nunca acrescenta nem reescreve texto.
- Limitação: artigos que checam várias falas de uma vez (ex.: "checamos Nunes e Boulos") têm abertura genérica.

## 7. Corpus

Pipeline (Seção 6.1), em três scripts independentes que podem ser retomados:

```text
collect_factcheck_api.py ──► data/corpus/raw/factcheck_api.jsonl   (1 linha por URL de checagem)
fetch_articles.py        ──► data/corpus/raw/articles.jsonl        (texto completo via trafilatura)
build_index.py           ──► chroma_data/ (coleção do modelo atual)
```

### 7.1 ⚠️ Agências (diverge da Seção 6.1)

O manual cita Aos Fatos, Lupa e Comprova.

- **Lupa:** a API não devolveu nenhuma checagem com `agencialupa.org` (domínio atual da agência) nem com `lupa.uol.com.br`, e a Lupa não apareceu entre os publishers de uma busca aberta em 27/09. Por ora, a Lupa fica fora do corpus. Alternativas: FACTCK.BR (checagens mais antigas) ou coleta direta do site, que dá mais trabalho.
- **Incluídas em 27/09**, por decisão do dono do agente, para chegar ao volume da Seção 6.1 ("alguns milhares"): **AFP Checamos** (`checamos.afp.com`), **Estadão Verifica** (`estadao.com.br`) e **UOL Confere** (`noticias.uol.com.br`). O Observador (Portugal) ficou fora por ser português europeu. Vale comunicar ao grupo.

### 7.2 Coleta

| Decisão | Justificativa |
| --- | --- |
| `languageCode=pt`, filtro por site; padrão dos últimos 730 dias | Seção 6.1: "priorizando os últimos 24 meses". Para ampliar: `--max-age-days 0`. |
| Coleta dividida em buscas por palavra-chave (uma sem palavra-chave + ~38 temas) | A API devolve erro 503 depois de ~500–600 resultados de uma mesma busca (Aos Fatos: 602 e 502; Comprova: 200), e rodar de novo só repete as primeiras páginas. Buscas menores não chegam ao limite. Uma busca com erro não interrompe as outras. |
| Deduplicação por URL na coleta e no download | Seção 6.1. |
| Dados brutos em `data/corpus/raw/`, fora do Git (`.gitignore`) | "Não versionar dados brutos grandes" (Seção 5.5). |

Situação em 28/09: **5.826 checagens** coletadas (UOL 1.732, Estadão 1.479, Aos Fatos 1.192, AFP 1.191, Comprova 232), acima da meta de "alguns milhares" da Seção 6.1. 1.424 textos baixados até a interrupção; faltam os do Estadão e do UOL.

**AFP Checamos recusa o download** (515 de 515 tentativas falharam em 27/09). O bloqueio não é contornado (é uma recusa explícita do site). Em vez disso: o `fetch_articles.py` desiste de um site depois de 20 falhas seguidas (`--max-falhas-seguidas`, ou `--pular-sites checamos.afp.com`), e o índice inclui o título de toda checagem (Seção 7.3). Assim a AFP entra no corpus pelo título e pela alegação, sem o texto completo.

### 7.3 Trechos e metadados

| Decisão | Justificativa |
| --- | --- |
| Parágrafos agrupados até 800 caracteres, sobreposição de 1 parágrafo, parágrafos com menos de 40 caracteres descartados | "Chunking por parágrafo com sobreposição" (Seção 6.1). 800 caracteres ficam abaixo do limite de 512 tokens do NLI. |
| Um trecho nunca mistura parágrafo marcado como boato com parágrafo não marcado | A marcação vale para o trecho inteiro. |
| **Toda checagem ganha um trecho com o título** (`chunk_kind = "titulo"`, `chunk_index = -1`), mesmo sem texto baixado | O título é a conclusão da agência e bom material de busca; é o `excerpt` do modo `alegacao`; faz a AFP entrar no índice. (28/09) |
| IDs determinísticos (`sha1(url)` + índice) e `upsert` | Rodar a indexação de novo atualiza em vez de duplicar. |
| Metadados por trecho | `source_url`, `source_name`, `agency_verdict`, `review_date`, `claim_reviewed`, `review_title`, `chunk_index`, `chunk_kind`, `describes_rumor`. |
| `seed_db.py` indexa os dois trechos do exemplo da Seção 4.6 | Teste rápido sem chave de API. O `claim_reviewed` dessas duas checagens foi reconstruído a partir do endereço (slug) da URL. Recria a coleção: depois dele, rodar `build_index.py --reset`. |

## 8. Proteção contra o boato citado

**Problema.** Checagens reproduzem o boato que desmentem. No modo `trecho`, esse parágrafo vira premissa do NLI e pode gerar `apoia` (confirmado: 0,99). A proteção (opção 1) marca na indexação os parágrafos que descrevem o boato (`describes_rumor`) e, com `EVIDENCE_FILTER_RUMOR=1`, a busca os ignora.

**Medição no corpus real (27/09).** A heurística original marcava 573 de 8.623 parágrafos, e **230 deles (40%) eram conclusões da agência** ("É falso que um vídeo mostra…", "São enganosas as publicações que afirmam…"), justamente os melhores trechos. Ao mesmo tempo, não detectava o texto do post colado sem introdução (padrão do Aos Fatos no 3º parágrafo). Correção: um parágrafo com marcador de conclusão ("é falso", "não é verdade", "engana", "na verdade", "foi gravado em 2022"…) nunca é marcado como boato. Resultado: 260 parágrafos marcados nas 552 checagens de 27/09; em 28/09, com 1.424 checagens, 784 de 21.911 parágrafos (3,6%). A amostra ainda tem alguns falsos positivos (parágrafos que descrevem a apuração: "Aos Fatos realizou busca reversa do vídeo compartilhado nas redes…").

**⚠️ Mudança em relação ao plano de 27/09.** O plano aprovado previa ligar a proteção por padrão. Com os dados acima, ela **continua desligada**:

- no modo `alegacao` (padrão), o parágrafo do boato não é premissa de nada e **ajuda** a busca a achar a checagem certa; filtrá-lo pioraria a recuperação;
- com a heurística ainda marcando algumas conclusões, ligar a proteção esconderia parte dos melhores trechos.

A proteção continua útil para quem rodar o modo `trecho` (`EVIDENCE_FILTER_RUMOR=1`). Para revisar a marcação: `python data/corpus/diagnostico.py --amostra-boato 20`. Depois de mudar a heurística, é preciso reindexar (`build_index.py --reset`).

## 9. Dispositivo e memória

- Dispositivo escolhido automaticamente: `cuda` → `mps` → `cpu` (`EVIDENCE_DEVICE` força um valor). O manual assume MacBook com MPS; o mesmo código roda em Windows.
- Embeddings em fp16 quando há GPU, para caber no orçamento de < 2 GB para embeddings + NLI (Seção 5.2). O NLI fica em fp32 por padrão (`EVIDENCE_NLI_FP16=1` para testar fp16). Medir a memória real na máquina da demo.
- Os modelos são carregados uma única vez por processo.
- Observado em 26/09 no Windows com Python 3.14: o PyTorch avisa que o 3.14 ainda não tem suporte completo. Vale alinhar a versão do Python com o grupo.

## 10. Configuração

Tudo em `src/retrieval/config.py`, sobrescrevível por variável de ambiente. O `services/llm.py` é do R1 e trata só de LLM, por isso a configuração deste agente fica separada.

| Variável | Padrão | Uso |
| --- | --- | --- |
| `EVIDENCE_STANCE_MODE` | **`alegacao`** | `alegacao` (etapa 2 + veredito) ou `trecho` (Seção 4.2) |
| `EVIDENCE_SIM_THRESHOLD` | `0.55` | Limiar de similaridade (provisório) |
| `EVIDENCE_CLAIM_MATCH_MIN_PROB` | `0.5` | Entailment mínimo da etapa 2 (provisório) |
| `EVIDENCE_KEY_TERM_CHECK` | **`1`** | Termos-chave na etapa 2 (Seções 4.1.1 e 4.1.2) |
| `EVIDENCE_CLAIM_NORMALIZE` | **`1`** | Tira "Foto/Vídeo/Imagem mostra" da alegação antes do NLI (ligada desde 28/09) |
| `EVIDENCE_CLAIM_CANDIDATES` | `6` | Checagens avaliadas na etapa 2 por frase, antes do limite de saída |
| `EVIDENCE_NLI_MIN_PROB` | `0.5` | Probabilidade mínima do rótulo do NLI no modo `trecho` (provisório) |
| `EVIDENCE_SEARCH_K` | `10` | Trechos buscados por frase pelo agente |
| `EVIDENCE_TOP_K` | `5` | k do Recall@k na avaliação |
| `EVIDENCE_MAX_PER_SEGMENT` | `3` | Checagens por frase |
| `EVIDENCE_EXCERPT_MAX_CHARS` | `300` | Tamanho máximo do `excerpt` |
| `EVIDENCE_FILTER_RUMOR` | `0` | Proteção contra o boato citado (Seção 8) |
| `EVIDENCE_EMBEDDING_MODEL` | `BAAI/bge-m3` | Modelo de embedding |
| `EVIDENCE_NLI_MODEL` | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | Modelo de NLI |
| `EVIDENCE_CHUNK_MAX_CHARS` / `EVIDENCE_CHUNK_OVERLAP` / `EVIDENCE_MIN_PARAGRAPH_CHARS` | `800` / `1` / `40` | Chunking |
| `EVIDENCE_DEVICE` | automático | `cpu`, `cuda` ou `mps` |
| `EVIDENCE_EMBEDDING_FP16` / `EVIDENCE_NLI_FP16` | `1` / `0` | Precisão na GPU |
| `EVIDENCE_BATCH_SIZE` | `16` | Lote de embeddings e NLI |
| `EVIDENCE_CHROMA_PATH` / `EVIDENCE_RAW_DIR` | `chroma_data/` / `data/corpus/raw/` | Caminhos |
| `FACTCHECK_API_KEY` | — | Chave da Fact Check Tools API |

## 11. Testes

Rodar sempre **a partir da raiz** com `python -m pytest` (assim a raiz entra no `sys.path` e os imports `src.` funcionam). O `pytest` não está no `requirements.txt`; instale com `pip install pytest`.

| Arquivo | O que cobre |
| --- | --- |
| `tests/contract/test_evidence_contract.py` | Stub e agente real nos dois modos: campos exatos da Seção 3.3, stance válida, URL não vazia, `segment_id` existente, só as chaves `evidence`/`warnings`; falha → `None` + aviso |
| `tests/unit/test_evidence_alegacao.py` | Modo `alegacao`: só a mesma alegação vira evidência, NLI nas duas direções em um lote, stance pelo veredito, título/abertura como `excerpt`, termos-chave barrando troca de nome, normalização, até 6 candidatas com saída limitada a 3, mesma checagem em dois endereços, checagem sem `claim_reviewed`, modo `trecho` e modo inválido |
| `tests/unit/test_evidence_unit.py` | Mapeamento do NLI, `excerpt` literal, limiar, deduplicação, caso do mamão (Seção 4.6), casos de borda da Seção 4.7 |
| `tests/unit/test_evidence_verdicts.py` | Normalização dos vereditos com os formatos reais do corpus |
| `tests/unit/test_evidence_claim_match.py` | Normalização da alegação, nomes compostos, primeira palavra, termos-chave e a regra de troca (dengue/chikungunya, Lewandowski/Fux, 5.000/50 mil, "STF" como contexto) |
| `tests/unit/test_evidence_corpus_scripts.py` | Trecho de título no índice, download que desiste do site que recusa, lógica do experimento e validade dos pares |
| `tests/unit/test_evidence_chunking.py` | Marcação de boato (inclusive conclusões reais que a versão anterior marcava), separação boato/conclusão, tamanho e sobreposição |
| `tests/integration/test_evidence_integration.py` | Com os modelos reais (`EVIDENCE_INTEGRATION=1`): etapa 2 em 6 pares (paráfrases × fatos parecidos), falhas conhecidas do modo `trecho` (marcadas como `xfail`) e o índice do seed |

Fixtures: `tests/fixtures/caso_mamao_dengue/` (Seção 4.6) e `tests/fixtures/bordas/evidencias_*.json` (Seção 4.7). Nos casos sintéticos, agência e URLs são fictícias (`exemplo.org`).

## 12. Como rodar

Comandos a partir da raiz do repositório. Variáveis de ambiente no PowerShell (terminal padrão do VS Code no Windows); no macOS/Linux, use `export NOME=valor`.

```powershell
# 1. Testes (sem modelos)
python -m pytest tests

# 2. Testes com os modelos reais
python data/corpus/seed_db.py
$env:EVIDENCE_INTEGRATION = "1"
python -m pytest tests/integration -v -s

# 3. Corpus real (coleta retomável; só acrescenta o que é novo)
$env:FACTCHECK_API_KEY = "sua-chave"
python data/corpus/collect_factcheck_api.py
python data/corpus/fetch_articles.py
python data/corpus/build_index.py --reset

# 4. Experimento da etapa 2 (NLI real nos 35 pares; não precisa do índice)
python data/corpus/experimento_etapa2.py

# 5. Diagnóstico
python data/corpus/diagnostico.py --vereditos
python data/corpus/diagnostico.py --amostra-boato 20
python data/corpus/diagnostico.py --frases "Fachin apontou o dedo para Moraes durante uma discussão no STF."
```

## 13. Resultados observados

| Data | Experimento | Resultado |
| --- | --- | --- |
| 26/09 | NLI real, modo `trecho`: dengue × chikungunya | contradiction 0,93 → `contradiz` (erro) |
| 26/09 | NLI real, modo `trecho`: parágrafo do boato × boato | entailment 0,99 → `apoia` (erro grave) |
| 26/09 | Coleta, 1ª rodada | Só Aos Fatos (552 checagens); Lupa com 0 resultados; 503 nos demais |
| 26/09 | Busca "chá de mamão cura dengue" no corpus real | Checagem não está no corpus (é de fev/2024, fora da janela de 24 meses); trechos de outro assunto com similaridade 0,41–0,45; nada emitido (correto) |
| 27/09 | Busca com paráfrase do caso Fachin | Checagem certa: 0,594 e 0,579; parágrafo do boato: 0,567; outro fato sobre Fachin: 0,566; outro fato do STF: 0,544 |
| 27/09 | Coleta, 2ª rodada | 1.109 checagens (Aos Fatos + Comprova); 503 recorrente depois de ~500 resultados por busca |
| 27/09 | Vereditos do corpus | 125 formas distintas; 924 `contradiz`, 180 `insuficiente`, 5 `apoia` |
| 27/09 | Abertura das checagens | 78% com marcador explícito de conclusão |
| 27/09 | Heurística de boato | 573 marcados, 40% eram conclusões → corrigida para 260 |
| 27/09 | NLI real na etapa 2 (6 pares) | 4/6 certos; **casou dengue × chikungunya (0,98)**; rejeitou a paráfrase do Fachin (0,00) por causa do "Foto mostra" |
| 27/09 | Coleta, 3ª rodada (5 agências, 39 buscas cada) | 5.826 checagens; 1 busca com 503 (Aos Fatos, sem palavra-chave) |
| 27/09 | Download | AFP Checamos: 515/515 falhas; Aos Fatos e Comprova: 0 falhas |
| 28/09 | Termos-chave, sem NLI (35 pares) | 31/35: 16/16 paráfrases aceitas, 8/8 trocas de nome rejeitadas; versão por IDF descartada (reprovava 5–16 paráfrases) |
| 28/09 | Normalização da alegação | Altera 596 de 5.826 alegações (10%) |
| 28/09 | Experimento da etapa 2, NLI real (35 pares) | NLI + termos-chave: 34/35, 0 casou errado; só NLI: 3 casou errado; limiares 0,5/0,7/0,9 idênticos |
| 28/09 | Download, 2ª rodada | +1.479 textos (Estadão, restante do UOL até o bloqueio); UOL e BOL passaram a recusar depois de ~1.100 downloads; AFP pulada |
| 28/09 | Índice | 5.826 checagens (2.903 com texto, 2.923 só com título) → 32.094 trechos |
| 28/09 | Diagnóstico Fachin (índice real) | Achou AFP, UOL, BOL e Aos Fatos como `Falso`; etapa 2 rejeitou todas (STF ausente dos títulos; "Imagem mostra"); limite de 3 cortou o Aos Fatos |
| 28/09 | Diagnóstico chikungunya | Nenhuma checagem acima do limiar (não há checagem sobre o tema no corpus); nada emitido (correto) |
| 28/09 | Correções da etapa 2 (37 pares) | 35/37, 0 casou errado, 2 perdidos |

## 14. Pendências e decisões em aberto

| Item | Quando | Depende de |
| --- | --- | --- |
| **Levar o modo `alegacao` ao grupo e registrar ADR** | Próxima reunião | — |
| **Comunicar ao grupo a troca de agências (sem Lupa; + AFP, Estadão, UOL)** | Próxima reunião | — |
| Rodar de novo `experimento_etapa2.py` (37 pares) e o diagnóstico do Fachin para confirmar as correções de 28/09 com o NLI real | Agora | — |
| Terminar o download do UOL/BOL (recusaram depois de ~1.100; tentar com `--delay 3`) e reindexar | Sprint 2 | — |
| Validar a checagem de termos-chave no gold set com exemplos novos (a regra foi calibrada nos mesmos pares em que foi medida) | Sprint 2 | Gold set |
| Se NLI + termos-chave não bastar: LLM local como juiz de "mesma alegação" | Sprint 3 | Decisão do grupo (muda a arquitetura) |
| Calibrar `SIM_THRESHOLD`, `CLAIM_MATCH_MIN_PROB` e `NLI_MIN_PROB` | Após as 12 entradas do gold set | Gold set (formato do R3) |
| Comparar os modos `alegacao` × `trecho` e BGE-M3 × e5-large no gold set | Sprint 2 | Corpus + gold set + harness |
| Script de métricas (Recall@5, macro-F1 de stance, taxa de evidência inventada) | Sprint 2 | Harness comum do R3 |
| Cobrir frases que desmentem o boato (contradição com o `claim_reviewed`) | Sprint 3 | Resultados do gold set |
| Lupa: FACTCK.BR ou coleta direta | Sprint 3 | Conferir formato e licença do FACTCK.BR |
| Conformal prediction (Seção 11): exigirá campo de conjunto/probabilidades no schema | Só se o macro-F1 de stance estiver estável | ADR de mudança no `state.py` |
| Card do agente em `docs/agents/` | Sprint 4 | — |

## 15. Histórico de decisões

| Data | Decisão | Quem |
| --- | --- | --- |
| 26/09/2026 | Agente reescrito sem LLM, contrato `run(state)`, schema local temporário, saída em dicts | R2 |
| 26/09/2026 | BGE-M3 como embedding padrão; limiar provisório 0,75; NLI com par `text`/`text_pair` | R2 |
| 26/09/2026 | Proteção contra o boato citado implementada (opção 1), desligada por padrão | R2 |
| 26/09/2026 | Dados brutos fora do Git (`data/corpus/raw/` no `.gitignore`) | R2 |
| 27/09/2026 | **Modo `alegacao` (etapa "mesma alegação" + veredito da agência) como padrão; modo `trecho` mantido como opção** | R2 — a levar ao grupo (ADR) |
| 27/09/2026 | Limiar de similaridade 0,75 → 0,55, com base nas medições do corpus real | R2 |
| 27/09/2026 | Agências: incluídas AFP Checamos, Estadão Verifica e UOL Confere; Lupa sem cobertura na API | R2 — a comunicar ao grupo |
| 27/09/2026 | Coleta dividida em buscas por palavra-chave para contornar o 503 | R2 |
| 27/09/2026 | Normalização dos vereditos (mapeamento conservador) | R2 |
| 27/09/2026 | Heurística de boato corrigida; proteção continua desligada (contrariando o plano inicial, pelos dados da Seção 8) | R2 |
| 28/09/2026 | **Checagem de termos-chave na etapa 2, ligada por padrão** (o NLI casou dengue × chikungunya) | R2 |
| 28/09/2026 | Normalização "Foto/Vídeo mostra" implementada, desligada até o experimento | R2 |
| 28/09/2026 | Título de toda checagem indexado; título como `excerpt` no modo `alegacao` | R2 |
| 28/09/2026 | Download desiste de um site após 20 falhas seguidas (AFP recusa o download; bloqueio não é contornado) | R2 |
| 28/09/2026 | Experimento da etapa 2: NLI + termos-chave adotado; limiar da etapa 2 mantido em 0,5 | R2 |
| 28/09/2026 | Termos-chave passam a exigir **troca** (termo da mesma classe sobrando na alegação); nomes compostos; primeira palavra conta como nome | R2 |
| 28/09/2026 | **Normalização da alegação ligada por padrão** | R2 |
| 28/09/2026 | Etapa 2 avalia até 6 checagens por frase e junta a mesma checagem em dois endereços; limite de 3 aplicado depois | R2 |
