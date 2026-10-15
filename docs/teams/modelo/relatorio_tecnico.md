# Relatório técnico: modelo de IA do Sistema Multiagente de Avaliação de Confiabilidade

**Grupo 1 (ResIA)** · Outubro de 2026

**Artefatos desta entrega** (pasta `entrega/`):

| Artefato | Arquivo |
| --- | --- |
| Notebook | `notebook_modelo.ipynb` |
| Modelo | `modelo/modelo_evidencias.pkl` |
| Ajuste | `treinar_modelo.py` |
| Números citados | `resultados/treino_2026-10-09.json` e `resultados/avaliacao_notebook.json` |

---

## Sumário

1. [Contexto e escopo da entrega](#1-contexto-e-escopo-da-entrega)
2. [Preparação dos dados](#2-preparação-dos-dados)
3. [Treinamento e ajuste do modelo](#3-treinamento-e-ajuste-do-modelo)
4. [Critérios de seleção da abordagem](#4-critérios-de-seleção-da-abordagem)
5. [Métricas de desempenho e análise dos resultados](#5-métricas-de-desempenho-e-análise-dos-resultados)
6. [Principais desafios](#6-principais-desafios)
7. [Aprendizados e lições](#7-aprendizados-e-lições)
8. [Limitações e próximos passos](#8-limitações-e-próximos-passos)
9. [Reprodutibilidade](#9-reprodutibilidade)

---

## 1. Contexto e escopo da entrega

O sistema recebe o texto ou a URL de uma notícia e devolve um **dossiê de evidências**, sem nunca dar um veredito de "verdadeiro" ou "falso" (o "padrão andaime" do Manual §1.1): mostra o que as agências de checagem já publicaram sobre as alegações do texto, como o texto argumenta e que perguntas o leitor deveria fazer. Cinco agentes, orquestrados em LangGraph:

```
Entrada ─ Ingestor ─┬─ Evidências  (RAG + NLI, sem LLM)   ─┐
                    ├─ Texto       (LLM local, few-shot)  ─┼─ Sintetizador (código + LLM) ─ Dossiê
                    └─ Socrático   (LLM local)            ─┘
```

**O modelo entregue é o do Agente de Evidências.** É o único componente com uma tarefa de previsão bem definida, um conjunto rotulado e métricas quantitativas medidas. Para cada frase da notícia, ele decide:

1. se existe no corpus uma checagem sobre a **mesma alegação**;
2. qual é a **stance** dessa checagem em relação à frase: `apoia`, `contradiz` ou `insuficiente`.

Os outros agentes usam um LLM pré-treinado (Qwen 2.5 7B Instruct, local) por *prompting*, sem treino. Eles aparecem neste relatório e no notebook (seção 8) quando ajudam a entender o modelo no sistema: latência ponta a ponta e guardrails de citação e veredito. A interface, a API e os demais componentes de aplicação ficam fora desta entrega, como pedido.

---

## 2. Preparação dos dados

São dois conjuntos de dados com papéis diferentes: o **corpus de checagens**, que é a base de conhecimento consultada pelo modelo, e o **gold set**, o conjunto rotulado usado para calibrar e avaliar.

### 2.1 Corpus de checagens

**Coleta.**

| Fonte | Como foi coletada | Agências |
| --- | --- | --- |
| Google Fact Check Tools API (ClaimReview) | Script `data/corpus/collect_factcheck_api.py` | Aos Fatos, UOL Confere, AFP Checamos, Estadão Verifica, Projeto Comprova, Agência Pública/Truco, Fato ou Fake (O Globo), Correio Braziliense e Estado de Minas |
| Dataset acadêmico FACTCK.BR (licença MIT, WebMedia '19) | Importado com `import_factckbr.py` | Agência Lupa e Aos Fatos, de 2018 e 2019. A Lupa não aparece na API |

Cada registro traz a URL, a agência, o **veredito** da agência, a **alegação checada** (`claim_reviewed`), o título e a data. O texto completo de cada checagem foi baixado com `fetch_articles.py` (trafilatura).

A API corta uma mesma busca com erro 503 depois de cerca de 500 resultados. Por isso a coleta foi dividida em buscas por palavra-chave:

- 83 palavras-chave temáticas;
- depois, mais 69 temáticas;
- por fim, 1.300 nomes próprios e as 900 palavras mais frequentes do próprio corpus.

**Limpeza e filtragem.** Cada regra abaixo foi motivada por um problema observado:

| Regra | Motivo |
| --- | --- |
| Exclusão do `bol.uol.com.br` | Republica o UOL Confere: 525 das 531 checagens do BOL tinham o original no UOL. As cópias ocupavam vagas do top 5 da busca e empurravam checagens relevantes para fora |
| Deduplicação por título | A mesma checagem publicada em dois endereços conta uma vez, e fica o site original |
| FACTCK.BR: só páginas com uma alegação | 91 páginas reuniam várias alegações (até 27), 61 delas com vereditos diferentes. O modelo supõe uma alegação por URL |
| FACTCK.BR: descarte de 4 checagens "verdadeiro" com título que desmente | O rótulo da coleta original estava trocado ("É falso que…" com veredito *verdadeiro*). Como a stance vem do veredito, o modelo daria `apoia` a um boato desmentido, que é o erro mais grave do sistema |
| FACTCK.BR: títulos corrigidos | Saem as marcas "#Verificamos:" e " \| Aos Fatos". Em 198 títulos da Lupa, o "É" inicial perdido é restaurado. É a única correção de texto, e só nesse padrão |
| Ano no nome da fonte para checagens anteriores a 2024 | "Aos Fatos (2019)": o contrato `Evidence` não tem data, e uma checagem antiga não pode parecer atual |
| Respeito a recusas de download | A AFP recusou 515 de 515 downloads, e o UOL passou a recusar depois de ~1.100. O bloqueio **não foi contornado**: essas checagens entram no índice só pelo título, que é a conclusão da agência |

**Resultado** (índice usado na entrega):

- **18.179 checagens**, de 2015 a 2026;
- 9.718 com texto completo, e as demais só com o título;
- **114.337 trechos** indexados.

**Divisão em trechos e indexação** (`data/corpus/build_index.py`):

- Os parágrafos são agrupados até 800 caracteres, com sobreposição de 1 parágrafo. Parágrafos com menos de 40 caracteres (menus, legendas) saem.
- Cada checagem ganha também um trecho com o **título**, inclusive as que não têm texto.
- Os embeddings são calculados com `BAAI/bge-m3` (normalizados, em fp16 na GPU) e gravados no ChromaDB com distância de cosseno.
- Os IDs são determinísticos, então reindexar atualiza em vez de duplicar.

**Vocabulário de nomes próprios.** O mesmo script extrai do corpus as palavras que aparecem com maiúscula **no meio** de alegações e títulos mais vezes do que em minúscula, com siglas curtas incluídas (`STF`, `COP30`). O resultado são 4.150 palavras, em `data/corpus/nomes_proprios.txt`. O vocabulário resolve uma ambiguidade da etapa de termos-chave: a primeira palavra de uma frase sempre tem maiúscula, e só o corpus diz se "Lula" é nome e "Aviões" não é.

### 2.2 Gold set (conjunto de avaliação)

`data/gold/evidencias.json` tem **14 entradas (notícias) e 42 frases**, cada uma anotada com:

- o tipo da frase;
- as **URLs aceitas**, incluindo outras agências que checaram a mesma alegação;
- a stance esperada.

| Tipo | Frases | O que testa |
| --- | ---: | --- |
| `com_checagem` | 23 | Recuperação e stance |
| `sem_checagem` | 12 | Abstenção: o modelo não deve inventar evidência |
| `fato_parecido` | 3 | Mesmo tema, outro fato (ex.: chikungunya × dengue): não citar |
| `troca_numero` | 2 | Mesmo fato com número trocado: não citar |
| `desmente` | 2 | Frase que nega o boato (limitação conhecida, medida de propósito) |

Cuidados na construção:

- **Paráfrase obrigatória:** as frases nunca copiam o título da checagem. O comando `validar` avisa quando mais de 60% das palavras de uma frase aparecem no título ou na alegação ("possível vazamento"), para que ela seja reescrita. Sem isso, a busca acharia a checagem trivialmente e o Recall@5 ficaria inflado (Manual §6.2).
- **Seleção sem viés de escolha:** as checagens que viraram frases foram sorteadas do corpus com semente fixa (`eval/avaliar_evidencias.py sortear` e `esqueleto`), com vagas por veredito (falso, enganoso, verdadeiro), para checagens da AFP (só título) e para alegações com número ou nome. Guias explicativos, alegações negativas e espelhos ficaram fora do sorteio.
- **Divisão por entrada**, decidida **antes** de calibrar: 7 entradas (21 frases) para **calibração** e 7 entradas (21 frases) para **teste**. Frases da mesma notícia nunca ficam em splits diferentes.
- **Origem declarada:** 36 frases foram redigidas com ajuda de um assistente de IA (Claude) e revisadas pelo responsável pelo agente; 6 foram escritas por ele. A revisão por um segundo integrante está pendente.

O experimento da etapa "mesma alegação" usa um conjunto à parte, `data/corpus/pares_etapa2.json`: **37 pares** rotulados de alegações reais × frases escritas para o teste (paráfrases, paráfrases de mídia, trocas de nome, trocas de número, outro fato, negação).

---

## 3. Treinamento e ajuste do modelo

### 3.1 Por que não houve treino de pesos

Os dois componentes neurais são **pré-treinados e usados como estão**:

| Componente | Modelo | Parâmetros | Papel |
| --- | --- | --- | --- |
| Embeddings | `BAAI/bge-m3` | 568 M | Busca densa multilíngue |
| NLI | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | 279 M | "A frase e a alegação checada dizem a mesma coisa?" (entailment) |

Ajustar esses pesos (*fine-tuning*) exigiria milhares de pares rotulados em português. O gold set tem 42 frases, que bastam para **calibrar** poucos parâmetros de decisão, mas não para treinar uma rede sem sobreajuste. Além disso, a tarefa não pede que o modelo *aprenda* o que é verdade: as agências já publicaram o veredito, e o problema é **encontrar a checagem certa** e **confirmar que é a mesma alegação**. O "conhecimento" do modelo é o índice, e não os pesos (seção 4).

### 3.2 O que foi ajustado com dados

O treino deste modelo é o **ajuste dos parâmetros de decisão** do pipeline. Fica tudo em `modelo_evidencias.pkl`:

| Parâmetro | Valor | Como foi definido |
| --- | --- | --- |
| Similaridade mínima na busca (`SIM_THRESHOLD`) | 0,55 | Medido no corpus real: outro assunto ≈ 0,45; outro fato do mesmo tema ≈ 0,55–0,57; checagem certa ≈ 0,58–0,68. Os 0,75 sugeridos no manual não deixariam passar nada |
| Entailment mínimo (`CLAIM_MATCH_MIN_PROB`) | **0,8** | **Busca em grade no split de calibração** (abaixo) |
| Ancoragem lexical mínima (`MIN_CONTENT_OVERLAP`) | 1 radical | Filtro contra checagem de outro assunto. Os valores 2 e 3 reduziam casamentos errados no gold set, mas foram rejeitados por risco de sobreajuste: as frases do gold set são paráfrases e têm sobreposição artificialmente alta |
| Trechos buscados / candidatas / evidências por frase | 10 / 6 / 3 | Com 3 candidatas, a checagem do Aos Fatos no caso Fachin ficava de fora |
| Vocabulário de nomes próprios | 4.150 palavras | Extraído do corpus (2.1) |
| Mapa veredito → stance | Conservador | Só rótulos inequívocos viram `contradiz` (falso, montagem…) ou `apoia` (verdadeiro, comprovado…). "Enganoso", "falta contexto" e rótulos livres viram `insuficiente` |

### 3.3 Calibração do limiar de entailment

O processo, implementado em `treinar_modelo.py`:

1. Rodar o pipeline completo no **split de calibração** para cada limiar em {0,5; 0,6; 0,7; 0,8; 0,9}.
2. Escolher pelo critério, em ordem:
   1. **menos casamentos errados**, isto é, citar a checagem de outra alegação, o erro mais grave (Manual §12.1);
   2. **mais cobertura**;
   3. no empate, o **centro do platô** de limiares empatados.
3. Medir o limiar escolhido **uma única vez** no split de teste.

| NLI ≥ | Cobertura | Macro-F1 | Evidência inventada | Casamentos errados |
| ---: | ---: | ---: | ---: | ---: |
| 0,5 | 9/11 | 0,73 | 0/7 | 6 |
| 0,6 | 10/11 | 0,80 | 0/7 | 5 |
| 0,7 | 10/11 | 0,80 | 0/7 | 4 |
| **0,8** | **10/11** | **0,80** | **0/7** | **4** |
| 0,9 | 10/11 | 0,80 | 0/7 | 4 |

*Split de calibração, 21 frases, índice de 114.337 trechos.*

Leitura da tabela:

- **Por que a cobertura cai em 0,5.** Com o limiar baixo, entram mais candidatas erradas. Como o modelo emite no máximo 3 evidências por frase, ordenadas pela similaridade, uma candidata errada pode tomar a vaga da certa.
- **Por que 0,8.** Os limiares 0,7, 0,8 e 0,9 empatam. O desempate original do script de avaliação ("o limiar mais baixo") escolheria 0,7. Preferimos o **centro do platô**: na primeira calibração (01/10, índice de 32 mil trechos), 0,7 ainda casava errado onde 0,8 não, ou seja, a borda inferior do platô é a primeira a piorar quando o corpus cresce. 0,8 também é o valor que o sistema já usava desde 01/10, então o modelo da entrega e o da aplicação são o mesmo.

---

## 4. Critérios de seleção da abordagem

Seis critérios do Manual guiaram as escolhas, em ordem de prioridade:

1. **Nunca emitir veredito.** O sistema mostra evidências, e a conclusão é do usuário.
2. **Citação obrigatória e literal.** Toda evidência traz o link exato da checagem de origem.
3. **Errar por omissão, e não por comissão.** Citar a checagem errada é pior do que não citar nenhuma.
4. **Inferência 100% local**, por privacidade: nada da notícia sai da máquina.
5. **Hardware de uma máquina** (Mac M4 com 24 GB) e cerca de 2 GB de memória para o agente.
6. **Prazo de 6 semanas** e um grupo de 5 pessoas.

### 4.1 Por que não um classificador supervisionado de "fake news"

| Opção | Avaliação |
| --- | --- |
| Classificador binário verdadeiro/falso treinado em notícias rotuladas | Violaria o princípio 1. Também generaliza mal para alegações novas: aprende o estilo do texto, e não o fato. E não há dados rotulados em português na granularidade de frase |
| **Recuperar o veredito de quem já checou (RAG) e confirmar que é a mesma alegação (adotada)** | O rótulo vem de especialistas (as agências), com o link para o leitor conferir. O sistema só precisa acertar *qual* checagem citar |

### 4.2 Por que a stance vem do veredito, e não do NLI direto

O desenho inicial do Manual (§4.2) comparava, por NLI, o trecho recuperado com a frase. Com os modelos reais, isso errou **com confiança alta** nos dois piores casos:

| Teste (mDeBERTa real) | NLI | Stance pelo desenho inicial | Correto |
| --- | --- | --- | --- |
| Checagem de dengue × frase sobre chikungunya | contradiction 0,93 | `contradiz` | nenhuma evidência |
| Parágrafo que **reproduz o boato** × a frase do boato | entailment 0,99 | **`apoia`** | nunca `apoia` |

Nenhum limiar de probabilidade separa esses erros. A solução foi trocar a pergunta feita ao NLI:

- **antes:** "o trecho apoia a frase?";
- **depois:** "a frase e a **alegação checada** são a mesma afirmação?". A stance passa a vir do veredito da agência.

O trecho que reproduz o boato continua ajudando a busca, mas deixou de ser premissa.

### 4.3 Por que NLI e termos-chave juntos

Experimento com os 37 pares rotulados, medido com o modelo da entrega (entailment ≥ 0,8; notebook, seção 6). "Casar" é decidir que é a mesma alegação:

| Variante da decisão "mesma alegação" | Acertos | Precisão (casar) | Revocação (casar) | Casou errado | Paráfrase perdida |
| --- | ---: | ---: | ---: | ---: | ---: |
| A. Só NLI | 31/37 | 0,83 | 0,83 | 3 | 3 |
| B. NLI + normalização | 32/37 | 0,84 | 0,89 | 3 | 2 |
| C. NLI + termos-chave | 34/37 | 1,00 | 0,83 | 0 | 3 |
| **D. NLI + normalização + termos-chave (adotada)** | **35/37** | **1,00** | **0,89** | **0** | 2 |
| E. Só termos-chave | 30/37 | 0,72 | 1,00 | 7 | 0 |

As duas peças erram em situações opostas:

- o NLI aceita **troca de nome** entre frases quase iguais ("chá cura a dengue" × "chá cura a chikungunya": entailment 0,98);
- os termos-chave aceitam **negação**, porque a frase nega o que a alegação afirma usando os mesmos nomes.

A normalização ("Foto mostra X" → "X") recuperou paráfrases de checagens de mídia: no caso Fachin, o entailment foi de 0,09 para 0,99.

### 4.4 Escolha dos modelos pré-treinados

| Escolha | Alternativa | Critério e evidência |
| --- | --- | --- |
| **BGE-M3** (embeddings) | `multilingual-e5-large` | Comparação de igual para igual (42 frases, mesmo índice): **Recall@5 0,96 × 0,74**, cobertura 0,83 × 0,61 e macro-F1 0,77 × 0,56. O BGE-M3 também não exige prefixos (com o e5, esquecer o `query:` piora a busca sem dar erro) |
| **mDeBERTa-v3 XNLI** (NLI) | Reranker `bge-reranker-v2-m3` | O reranker mede *relevância*, e não "mesma alegação", e custaria ~1,1 GB a mais. O mDeBERTa é multilíngue, foi treinado em XNLI (com português) e cabe no orçamento: 0,52 GB |
| **Sem LLM no Agente de Evidências** | LLM local como juiz de "mesma alegação" | O resultado é reproduzível e determinístico, e o modelo não inventa texto: tudo o que devolve foi escrito pela agência. Uma notícia leva menos de 1 s. O LLM fica registrado como opção se NLI + termos-chave não bastarem |
| **Qwen 2.5 7B Instruct** (agentes de LLM) | Llama 3.x 8B | Critérios do Manual §5.3: validade do JSON estruturado, português, velocidade no M4. Roda local no LM Studio, com saída restrita por JSON Schema |

### 4.5 Arquitetura do sistema

A versão anterior tinha 10 nós (decomposição de alegações, agente de fonte, verificador de *grounding*). Ela foi reduzida a **5 nós com topologia fixa** e os três ramos em paralelo:

- passa de 6 a 9 chamadas de LLM por notícia para cerca de 3;
- simplifica os contratos entre os integrantes do grupo.

O verificador de *grounding* foi absorvido pela etapa "mesma alegação" e pela checagem determinística de URLs no Sintetizador. No Sintetizador, **o código escreve fatos e citações**, e o LLM só escreve a seção sobre como o texto argumenta. Assim, a validade de citação é 1,00 por construção.

---

## 5. Métricas de desempenho e análise dos resultados

### 5.1 Métricas consideradas

As métricas seguem o Manual §7.1. As definições dos casos de borda estão no ADR 3 (`docs/agents/evidencias_decisoes.md`).

| Métrica | O que mede | Meta |
| --- | --- | --- |
| **Recall@5** | A busca: alguma URL aceita está entre as 5 primeiras checagens distintas, sem limiar? | ≥ 0,70 |
| **Cobertura** | O modelo inteiro: emitiu uma URL aceita para a frase `com_checagem`? | — |
| **Macro-F1 de stance** | Média do F1 de `apoia`, `contradiz` e `insuficiente`. Sem evidência aceita, a stance prevista é `insuficiente` (Manual §4.8) | ≥ 0,65 |
| **Stance nas cobertas** | A stance, só onde o modelo citou a checagem certa. Separa o erro de stance do erro de cobertura | — |
| **Evidência inventada** | Fração das frases `sem_checagem` em que o modelo emitiu alguma evidência | ≤ 0,10 |
| **Casamento errado** | Número de evidências com URL não aceita para a frase | **0** |

Por que essas métricas:

- **Recall@5 e cobertura** separam a falha da busca da falha da decisão.
- **O macro-F1** dá o mesmo peso às três classes, apesar do desbalanceamento: `apoia` é rara no corpus (5 de 1.109 checagens analisadas em 27/09).
- **O casamento errado** foi criado pelo grupo. Nenhuma métrica do Manual media diretamente o erro mais grave, e a precisão agregada o diluiria.

### 5.2 Resultado no split de teste

| Métrica | Meta | Teste (21 frases) | Calibração (21) | Todos (42) |
| --- | --- | ---: | ---: | ---: |
| Recall@5 | ≥ 0,70 | **1,00** (12/12) ✅ | 1,00 (11/11) | 1,00 (23/23) |
| Cobertura | — | **0,83** (10/12) | 0,91 (10/11) | 0,87 (20/23) |
| Macro-F1 de stance | ≥ 0,65 | **0,74** ✅ | 0,80 | 0,77 |
| Stance nas cobertas | — | **1,00** (10/10) | 1,00 (10/10) | 1,00 (20/20) |
| Evidência inventada | ≤ 0,10 | **0,00** (0/5) ✅ | 0,00 (0/7) | 0,00 (0/12) |
| Casamentos errados | 0 | **2** ❌ | 4 | 6 (em 5 frases) |

**Stance por classe (teste):**

| Classe | Precisão | Revocação | F1 | Suporte |
| --- | ---: | ---: | ---: | ---: |
| `apoia` | 1,00 | 0,67 | 0,80 | 3 |
| `contradiz` | 1,00 | 0,75 | 0,86 | 8 |
| `insuficiente` | 0,40 | 1,00 | 0,57 | 2 |
| **macro** | 0,80 | 0,81 | **0,74** | 13 |

**Matriz de confusão (teste; linhas = esperada, colunas = prevista):**

| | `apoia` | `contradiz` | `insuficiente` |
| --- | ---: | ---: | ---: |
| `apoia` | 2 | 0 | 1 |
| `contradiz` | 0 | 6 | 2 |
| `insuficiente` | 0 | 0 | 2 |

O macro-F1 foi conferido com o `scikit-learn` no notebook (seção 5.2): os dois cálculos dão o mesmo valor.

### 5.3 Análise dos resultados

1. **A busca não é o gargalo.** O Recall@5 é 1,00 em todos os splits: a checagem certa sempre aparece entre as 5 primeiras. As perdas acontecem depois, na decisão "mesma alegação".
2. **Quando o modelo afirma, ele acerta a stance.** A precisão de `apoia` e de `contradiz` é 1,00, e a stance nas frases cobertas é 10/10. Todos os erros de stance caem em `insuficiente`, que é a abstenção. É o comportamento desejado pelo critério 3 (errar por omissão), e o custo aparece no F1 de `insuficiente` (0,57).
3. **A abstenção funciona:** 0 evidências inventadas em 12 frases sem checagem, nos dois splits.
4. **O erro grave não foi zerado.** Há 2 casamentos errados no teste e 6 no total. Todos têm o mesmo padrão: **mesmo personagem ou tema, outro episódio**. Exemplos:
   - urnas no Arkansas × uma checagem sobre Kamala Harris;
   - Silvio Almeida × um vídeo de outra eleição;
   - Bolsonaro no hospital × uma cirurgia de 2025.

   O NLI dá entailment de 0,93 a 0,98 para esses pares, e nenhum limiar os separa. As 6 evidências erradas estão em 5 frases. Em duas delas (Flávio Bolsonaro e Carrefour, 3 das 6 evidências, todas no split de calibração), o modelo cita uma checagem *da mesma alegação* com a mesma conclusão, que o gabarito não listava: são **lacunas do gabarito**, e não do modelo.
5. **Perdas de cobertura (2 no teste):**
   - Arkansas: o NLI recusou uma paráfrase boa;
   - Cármen Lúcia: a etapa "mesma alegação" recusou a checagem certa, que estava em 1º na busca.

   As duas são o custo de privilegiar a precisão.
6. **A frase que desmente o boato fica sem evidência** (ev03/s01, "Lula não virou réu…"). É uma limitação conhecida, medida de propósito no gold set (tipo `desmente`): se a frase casasse com a alegação, a stance sairia invertida.
7. **O modelo é estável com o crescimento do corpus.** Entre 01/10 e 09/10, o índice passou de 32 mil para 114 mil trechos, e o Recall@5 foi de 0,95 para 1,00. O macro-F1 ficou estável em 0,77 desde 03/10, quando o conjunto chegou a 42 frases. Um corpus 3,5 vezes maior não trouxe mais ruído para o top 5 (notebook, seção 7).
8. **O split de calibração ficou um pouco melhor que o de teste** (macro-F1 0,80 × 0,74). É o esperado de um limiar ajustado na calibração, e a diferença equivale a uma frase. Com 21 frases por split, **cada frase vale ~5 a 8 pontos percentuais**. Os números devem ser lidos como contagens absolutas, e diferenças pequenas não sustentam conclusões.

### 5.4 Experimento "mesma alegação" (37 pares)

A decisão "mesma alegação" é a peça central do modelo. Isolada nos 37 pares (tabela da seção 4.3), a variante adotada tem:

- acurácia de **35/37**;
- **precisão de 1,00** e revocação de 0,89 ao decidir "é a mesma alegação";
- nenhum par casado por engano, contra 3 do NLI sozinho e 7 dos termos-chave sozinhos.

Os 2 erros são paráfrases perdidas: a frase sobre Fachin, que não casou com as checagens do Aos Fatos e da AFP. Esse resultado é coerente com o comportamento no gold set: alta precisão e perdas de cobertura no lugar de erros graves.

**Ressalva:** as regras foram desenvolvidas olhando esses mesmos pares. A validação independente é o split de teste do gold set (seção 5.2), em que a mesma decisão errou 2 vezes, sempre do tipo "mesmo personagem, outro episódio", que não aparece nos 37 pares.

### 5.5 O modelo dentro do sistema completo

Execução do grafo inteiro com o LLM local (notebook, seção 8):

| | Mamão e dengue | Corrente do Carrefour |
| --- | ---: | ---: |
| Frases | 6 | 7 |
| Evidências encontradas pelo modelo | 3 | 2 |
| Tempo do modelo de evidências | 0,7 s | 2,0 s |
| Agente de Texto (LLM) | 17,9 s | 25,1 s |
| Agente Socrático (LLM) | 8,2 s | 9,0 s |
| Sintetizador | 7,8 s | 15,1 s |
| **Total ponta a ponta** | **25,8 s** | **40,3 s** |
| URLs no dossiê / inválidas | 0 / 0 | 4 / 0 |
| Termos de veredito no texto do LLM | 0 | 0 |
| Frases marcadas como factuais pelo Agente de Texto | **0 de 6** | 1 de 7 |
| Evidências escondidas (frase marcada como opinião) | **3** | 0 |

*Qwen 2.5 VL 7B Instruct no LM Studio, Mac com Apple Silicon. Os tempos variam cerca de 10% entre execuções.*

**Metas do sistema:**

| Métrica | Meta | Resultado |
| --- | --- | --- |
| Latência | p50 < 180 s | Mediana de 33 s ✅ |
| Validade de citação | 1,00 | 1,00 ✅ |
| Vazamento de veredito | 0 | 0 dossiês ✅. O filtro é por lista e não pega paráfrases |

O modelo de evidências responde por 3% a 5% do tempo total. O gargalo são os agentes de LLM, e o Agente de Texto sozinho representa cerca de 70% do tempo.

**Achado da integração.** No caso do mamão, o modelo de evidências encontrou as checagens corretas: Comprova, Aos Fatos e UOL, as três com veredito "Falso", para "O chá da folha de mamão cura a dengue em três dias" (notebook, seção 4). Mesmo assim, o dossiê diz "Nenhuma afirmação factual para checar". O motivo é que o Agente de Texto (LLM) classificou as 6 frases como **opinião**, e o Sintetizador só mostra a stance de frases factuais (Manual §4.8).

O comportamento se repetiu nas três execuções desta entrega. O card do Agente de Texto registrava 6/6 classificações corretas nesse caso em 01/10, o que sugere uma regressão posterior. A consequência é que **o desempenho que o usuário percebe é limitado pela classificação fato/valor, e não pelo modelo de evidências**. Essa classificação ainda não foi medida num gold set (seção 8).

---

## 6. Principais desafios

1. **O desenho inicial falhou com confiança alta.** O NLI entre o trecho e a frase deu `apoia` para o parágrafo que reproduz o boato (0,99) e `contradiz` para dengue × chikungunya (0,93). O problema não era o limiar, e sim a pergunta feita ao modelo. Redesenhar a etapa (seção 4.2) foi a decisão mais importante do projeto, e só apareceu ao testar com os modelos reais.
2. **Dados: coleta limitada e rótulos sujos.**
   - A API do Google devolve no máximo ~500 resultados por busca, o que levou à coleta por milhares de palavras-chave, com retorno decrescente: o último lote de 400 nomes trouxe só 61 checagens novas.
   - Duas agências recusam o download do texto, e a decisão foi **não contornar**.
   - O dataset acadêmico tinha rótulos invertidos e páginas com várias alegações.
   - Espelhos do UOL ocupavam o top 5 da busca.
3. **Detecção de nomes próprios em português.** A primeira palavra da frase tem maiúscula. "Aviões de caça…" e "Arrependida, Cármen Lúcia…" viravam nomes e faziam a checagem certa ser descartada como troca, e "COP30" nunca casava. A solução foi o vocabulário extraído do corpus, medido sem os modelos: 47 de 48 URLs aceitas passam, contra 41 antes.
4. **Avaliar com poucos dados sem se enganar.**
   - O gold set é pequeno (42 frases).
   - A calibração foi separada do teste antes de olhar os resultados.
   - Foi preciso inventar uma métrica (casamento errado) para o erro que importa.
   - Quem anota conhece as regras do modelo, o que é um risco de viés.
   - A abstenção é testada principalmente com notícias neutras, o que torna esse número otimista.
5. **LLM de 7B com saída estruturada** (agentes de Texto e Socrático):
   - pulou frases em lotes de 15;
   - classificou exclamações ("Justiça feita!") como fato;
   - copiou o rótulo "Falsa dicotomia", que esbarrava no filtro de veredito.

   Cada problema virou uma correção com teste, mas a qualidade desses agentes continua sendo o principal risco do produto. Na execução desta entrega, o Agente de Texto marcou como opinião a alegação central do caso do mamão e escondeu do dossiê as checagens que o modelo de evidências tinha acertado (seção 5.5).
6. **Recursos de uma máquina só.**
   - Na CPU, BGE-M3 + mDeBERTa somam 2,63 GB, acima do orçamento de 2 GB. Na GPU, em fp16, ficam em 1,58 GB.
   - A primeira análise carrega os modelos e pode estourar o tempo limite do ramo; por isso o grafo tem timeouts e degradação graciosa.
   - Texto e Socrático disputam o mesmo LLM no LM Studio.
7. **Reprodutibilidade.**
   - O índice (~1 GB) e os dados brutos ficam fora do Git e vêm do Google Drive.
   - Máquinas diferentes tinham índices de tamanhos diferentes, o que exigiu registrar a configuração em toda rodada: modelos, limiares, número de trechos e commit.

---

## 7. Aprendizados e lições

1. **Teste com os modelos reais o quanto antes.** Os testes com dublês passavam, mas quatro bugs (rótulo de falácia, segmentação, nome do modelo, lote que pulava frases) e o problema central do NLI só apareceram com os modelos de verdade.
2. **Quando os erros têm custos diferentes, a métrica precisa refletir isso.** Citar a checagem errada é muito pior do que não citar nenhuma. Tornar o casamento errado uma métrica com meta zero mudou as decisões, como a calibração do limiar e o desempate pelo centro do platô.
3. **Componentes simples e determinísticos complementam os neurais.** Uma regra de termos-chave de poucas linhas cobre exatamente o ponto cego do NLI (trocas de nome e número), e vice-versa. O conjunto teve zero casamentos errados nos pares de teste.
4. **Pergunte ao modelo a coisa certa.** O mesmo mDeBERTa que errava com 0,99 de confiança acerta quando a pergunta muda de "o trecho apoia a frase?" para "são a mesma alegação?".
5. **Deixe fatos e citações com o código.** O LLM escreve prosa; links e vereditos vêm de dados. Isso dá validade de citação 1,00 por construção e um dossiê que sai mesmo quando o LLM falha.
6. **Qualidade de dados vale mais que quantidade.** Tirar 535 espelhos do BOL e 4 rótulos invertidos teve mais efeito no comportamento do modelo do que milhares de checagens novas, que trouxeram retorno decrescente.
7. **Separe calibração e teste, e meça o teste uma vez.** Com amostras pequenas, reporte contagens absolutas e não tire conclusões de diferenças de uma frase.
8. **Registre cada decisão com o número que a motivou.** Os ADRs (`docs/agents/evidencias_decisoes.md`) permitiram rever decisões quando os dados mudaram, por exemplo o limiar de 0,5 para 0,8 e o BOL fora do corpus, e escrever este relatório sem reconstruir a história de memória.
9. **Ética da coleta.** Respeitar a recusa explícita de um site custou cobertura de texto (AFP e UOL entram só pelo título), mas é a regra certa. O título, que é a conclusão da agência, se mostrou suficiente para a busca na maioria dos casos.

---

## 8. Limitações e próximos passos

**Limitações:**

- **Casamento errado acima da meta (2 no teste).** O modelo não distingue "mesmo personagem, outro episódio". Próximo passo: uma regra que compare o episódio (data, local, ação) ou um LLM como juiz só nos casos de NLI alto.
- **O valor entregue ao usuário depende do Agente de Texto.** O dossiê só exibe a stance de frases classificadas como factuais. Nesta entrega, o LLM classificou como opinião a alegação central do caso do mamão, e o dossiê escondeu as 3 checagens corretas que o modelo encontrou (seção 5.5). Medir o macro-F1 fato/valor (Manual §7.1) é a próxima prioridade. Uma alternativa de desenho é exibir a checagem mesmo para frases marcadas como opinião, com um aviso.
- **Frases que desmentem o boato ficam sem evidência.**
- **O gold set é pequeno e ainda não tem a revisão cruzada.** Falta também trocar parte das frases `sem_checagem` neutras por boatos sem checagem no corpus, para testar a abstenção num tema próximo.
- **As métricas dos agentes de LLM do Manual §7.1 ainda não foram medidas num gold set:** macro-F1 fato/valor do Agente de Texto e rubrica do Socrático.
- **O corpus fica desatualizado para fatos muito recentes:** a frase fica sem evidência.

**Próximos passos:**

1. Revisão cruzada do gold set e recalibração com o conjunto ampliado.
2. Medir o vazamento de veredito com paráfrases (o filtro atual é por lista).
3. Comparar com o *baseline* de chamada única (Manual §7.3).

---

## 9. Reprodutibilidade

| O quê | Comando ou arquivo |
| --- | --- |
| Ajustar o modelo e gerar o `.pkl` | `python entrega/treinar_modelo.py` |
| Carregar, executar e avaliar | `entrega/notebook_modelo.ipynb` |
| Avaliação pela linha de comando | `python eval/avaliar_evidencias.py avaliar --split teste` |
| Experimento "mesma alegação" | `python data/corpus/experimento_etapa2.py` |
| Testes (sem modelos) | `pytest` (contrato e unidade, rodam no CI) |
| Decisões e números | `docs/agents/evidencias_decisoes.md` (ADRs) e `docs/agents/evidencias.md` |

**Ambiente da execução desta entrega:**

| Item | Valor |
| --- | --- |
| Máquina | macOS (Apple Silicon, `mps`), Python 3.14 |
| Bibliotecas | torch 2.14, transformers 5.17, sentence-transformers 6.1, chromadb 1.5.9 |
| Índice | `checagens__baai-bge-m3`, 114.337 trechos |
| Pesos | revisões fixadas no `.pkl`: BGE-M3 `5617a9f`, mDeBERTa `8adb042` |
