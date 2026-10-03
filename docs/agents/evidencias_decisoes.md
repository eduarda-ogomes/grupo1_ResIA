# Agente de Evidências — decisões (ADR)

Dono: R2 (Túlio Celeri) · Atualizado em 01/10/2026 · Status: **proposto, a levar ao grupo**
Como o agente funciona e como rodar: [`evidencias.md`](evidencias.md)

Registra as decisões que divergem do manual ou que o grupo precisa conhecer, com os números que as motivaram. Divergências do manual estão marcadas com ⚠️.

## ADR 1 ⚠️ Stance pelo veredito da agência, depois de confirmar que é a mesma alegação

**Contexto.** A Seção 4.2 define a stance pelo NLI entre o trecho recuperado (premissa) e a frase da notícia (hipótese). Com os modelos reais (26/09), isso errou nos dois riscos que o manual trata como mais graves (Seção 12.1), e com confiança alta:

| Teste (mDeBERTa real) | NLI | Stance pela Seção 4.2 | Correto |
| --- | --- | --- | --- |
| Checagem de dengue × frase sobre chikungunya | contradiction 0,93 | `contradiz` | nenhuma evidência |
| Parágrafo que reproduz o boato × a frase do boato | entailment 0,99 | **`apoia`** | nunca `apoia` |

Nenhum limiar de probabilidade separa esses erros. A similaridade também não: no caso Fachin, a checagem certa ficou em 0,59 e uma checagem sobre outro fato do mesmo ministro em 0,57.

**Decisão.** A stance passa a vir do **veredito da agência**, mas só depois de uma etapa que confirma que a checagem é sobre a **mesma alegação** da frase. A comparação é com o `claim_reviewed` (a alegação que a agência checou, fornecida pela Fact Check Tools API):

1. **Termos-chave.** Se a frase tem um nome próprio, número ou doença que não aparece na checagem, e a alegação tem outro da mesma classe que não aparece na frase, é uma troca ("chikungunya" × "dengue", "Fux" × "Lewandowski", "5 mil" × "50 mil"). A checagem é descartada.
2. **NLI entre alegação e frase.** Antes da comparação, tira-se "Foto/Vídeo/Imagem mostra" da alegação. A checagem segue se o entailment for ≥ 0,8 em **pelo menos uma direção** (0,5 até 01/10; ver a decisão do limiar abaixo). Uma direção basta porque a notícia costuma ser mais específica ou mais genérica que a alegação.
3. **Stance e excerpt.** A stance vem do veredito: falso → `contradiz`, verdadeiro → `apoia`, o resto → `insuficiente`. O `excerpt` é o título da checagem, que é a conclusão escrita pela agência.

O parágrafo que reproduz o boato deixa de ser premissa. Ele passa a só ajudar a busca a achar a checagem certa.

**Experimento** (`data/corpus/experimento_etapa2.py`, NLI real). Os pares são alegações reais do corpus e frases escritas para o teste: paráfrases, trocas de nome ou número, negações e outros fatos.

| Variante | Acertos | **Casou errado** | Paráfrase perdida |
| --- | --- | --- | --- |
| Só NLI | 31/35 | **3** (chikungunya, Fux, R$ 50 mil) | 1 |
| Só termos-chave | 31/35 | 4 (negações, R$ 600) | 0 |
| **NLI + termos-chave + normalização (adotada)** | **35/37** | **0** | 2 (Fachin × Aos Fatos e AFP) |

O NLI e os termos-chave se completam. O NLI deixa passar troca de nome entre frases quase iguais, e os termos-chave pegam isso. Os termos-chave deixam passar negação, e o NLI pega. Nos 37 pares, os limiares 0,5, 0,7 e 0,9 deram o mesmo resultado, porque o NLI responde perto de 0 ou de 1. No conjunto de avaliação não foi assim, e o limiar passou para 0,8 em 01/10 (decisões menores).

**Consequências.**
- ✅ Nenhum "casou errado" nos 37 pares. O erro grave (citar a checagem errada, ou `apoia` para boato) fica barrado.
- ✅ Nenhuma memória extra, porque reaproveita o mDeBERTa. São 2 comparações de NLI por candidata, num único lote por notícia.
- ❌ Frases que **desmentem** o boato ("a foto de Fachin é falsa") não casam com a alegação e ficam sem evidência. Se casassem, a stance sairia invertida.
- ❌ Depende do `claim_reviewed`. Checagens sem ele são ignoradas; hoje todas têm.
- ❌ `apoia` fica raro: das 1.109 checagens analisadas, 924 davam `contradiz`, 180 `insuficiente` e 5 `apoia`. Isso pesa no macro-F1 de stance.
- ⚠️ As regras foram ajustadas nos mesmos pares em que foram medidas. A validação de verdade é o gold set.

**Alternativas consideradas.**

| Alternativa | Por que não |
| --- | --- |
| Seção 4.2 com limiares ajustados | Os erros têm confiança de 93–99% |
| Marcar e filtrar os parágrafos que reproduzem o boato | A heurística marcou 573 parágrafos, e 40% eram conclusões da agência (os melhores trechos). Com o ADR 1, o parágrafo do boato não faz mal. Removido do código. |
| Reranker (`bge-reranker-v2-m3`) | Mede relevância, não "mesma alegação". Custa ~1,1 GB. |
| Termos-chave por palavras raras (IDF) | Reprovava de 5 a 16 paráfrases |
| LLM local como juiz de "mesma alegação" | Muda a arquitetura (o manual diz que o agente não usa LLM). Fica como opção se o gold set mostrar que NLI + termos-chave não basta. |

## ADR 2 ⚠️ Agências do corpus

O manual (Seção 6.1) cita Aos Fatos, Lupa e Comprova.
- **Lupa ficou fora.** A API não devolveu checagens de `agencialupa.org` nem de `lupa.uol.com.br`. As opções para depois são o FACTCK.BR ou a coleta direta do site.
- **Entraram AFP Checamos, Estadão Verifica e UOL Confere**, para chegar aos "alguns milhares" da Seção 6.1. Resultado: 5.826 checagens (UOL 1.732, Estadão 1.479, Aos Fatos 1.192, AFP 1.191, Comprova 232).
- **A AFP recusa o download** (515 de 515 tentativas) e o UOL/BOL passou a recusar depois de ~1.100 downloads. Em 01/10, três dias depois, um teste só com o UOL e 3 s de pausa (`fetch_articles.py --apenas-sites noticias.uol.com.br --limit 5 --delay 3`) falhou em 5 de 5 URLs com "download falhou" (o servidor não devolve a página, não é falha de extração): é bloqueio, e não limite de taxa. O bloqueio **não é contornado**: o download desiste do site depois de 20 falhas seguidas. Toda checagem entra no índice pelo título, mesmo sem o texto. Índice atual: 2.903 checagens com texto e 2.923 só com título, num total de 32.094 trechos.
- O BOL republica o UOL Confere com o mesmo título. As duas contam como uma checagem, e o agente cita o UOL (o original).

## ADR 3 Avaliação: conjunto próprio e definição das métricas

**Contexto.** A Sprint 2 pede "medir Recall@5 e stance" (Seção 10.2), mas o formato do gold set (R3) e o harness comum ainda não existem. A Seção 7.1 nomeia as métricas sem definir os casos de borda que decidem os números: o que conta quando a frase não tem evidência, a mesma alegação checada por várias agências, a frase que desmente o boato.

**Decisão.**

1. **Formato próprio**, só da parte de evidências (`data/gold/evidencias.json`), convertido para o formato do R3 quando ele existir.
2. **Recall@5 por checagem distinta e sem limiar.** Os 30 trechos mais próximos são agrupados por URL; vale o top 5. Mede a busca, não o agente, como pede a Seção 7.1.
3. **Várias URLs aceitas por frase**: espelhos (UOL/BOL) e outras agências que checaram a mesma alegação. Com uma URL só, achar a checagem da AFP no lugar da do Aos Fatos contaria como erro.
4. **Frase sem evidência com URL aceita → stance prevista `insuficiente`** (primeiro sentido da Seção 4.8). Como isso faz uma frase `insuficiente` não encontrada contar como acerto, a **cobertura** e a **stance nas cobertas** (só as frases em que o agente citou uma URL aceita) são reportadas ao lado. A segunda foi acrescentada depois da primeira rodada, em que esse viés apareceu (ev08/s02).
5. **`desmente` com stance esperada `apoia`.** Mede uma limitação conhecida (ADR 1) e baixa o F1 de propósito.
6. **Casamento errado** como quarta métrica, com meta 0: é o erro mais grave (Seção 12) e nenhuma métrica da Seção 7.1 o mede diretamente.
7. **Split por entrada** (metade calibração, metade teste), definido antes de calibrar.
8. **Gold e resultados versionados no Git**: são pequenos e são material do relatório.
9. **Macro-F1 calculado à mão**, sem `scikit-learn`, para não criar dependência no CI. Classe sem exemplo anotado sai da média, com aviso.

**Consequências.**
- ✅ Os números da Sprint 2 saem sem depender do harness; o `avaliar` registra modelos, limiares, índice e commit, então rodadas em máquinas diferentes são comparáveis.
- ✅ O comando serve também para os itens 4 (calibração) e 5 (BGE-M3 × e5).
- ❌ Amostra pequena (~20 frases com checagem): cada frase vale ~5 pontos de Recall. Reportar números absolutos e não tirar conclusões de diferenças pequenas.
- ❌ `apoia` quase não tem exemplos: 36 checagens viram `apoia`, das quais 21 são guias explicativos (o `sortear` as marca). O F1 dessa classe vai ser instável.
- ⚠️ Quem anota conhece as regras do agente. Paráfrases escritas por outra pessoa reduzem o viés.
- ⚠️ A primeira versão do conjunto (01/10) foi escrita pelo Claude, a pedido do R2. Ela só vale para o relatório depois da revisão humana, e o relatório precisa declarar essa origem.

**Primeira rodada (01/10, commit `9eba0f7`).** Números completos no card (seção Avaliação).

| Recall@5 | Cobertura | Macro-F1 | Stance nas cobertas | Inventada | Casamento errado |
| --- | --- | --- | --- | --- | --- |
| 18/19 = 0,95 ✅ | 14/19 = 0,74 | 0,61 ❌ | 14/14 = 1,00 | 0/11 = 0,00 ✅ | 7 ❌ |

Análise dos erros:
- **Stance:** certa em todas as 14 frases em que o agente citou a checagem certa. O F1 abaixo da meta vem das checagens perdidas e das 2 frases `desmente` (0 de 2, limitação conhecida do ADR 1).
- **Checagens perdidas (5 de 19).** Quatro estavam em 1º lugar na busca e caíram na etapa 2:
  - "Aviões…" (F-15) e "Arrependida…" (Cármen Lúcia): a primeira palavra, em maiúscula, conta como nome próprio, e a checagem certa é rejeitada como troca de termo;
  - Janja em Roma: o NLI recusou uma paráfrase boa (entailment 0,00 e 0,10);
  - Arkansas: as duas checagens aceitas foram rejeitadas na etapa 2.

  A quinta (Lula e o socialismo) nem chegou ao top 5: as checagens certas (UOL e AFP) só têm título no índice. É o único erro de Recall@5.
- **Casamentos errados (7):**
  - 2 em `troca_numero`: a alegação checada não tem o número trocado (2024 × 2026) ou o NLI aceitou outra alegação (0,98);
  - 5 em `com_checagem`: o NLI aceitou checagens de outro fato do mesmo tema. Três tinham entailment entre 0,52 e 0,67 (Lula comunista, tarifaço, Lei das Bets) e cairiam com um limiar perto de 0,7; Kamala (0,98) e Bolsonaro na UTI (0,93) não caem com nenhum limiar.
  - Ev01/s02 (Lei das Bets) é provavelmente falha de anotação: a frase afirma que "foi Lula quem assinou a lei", e a checagem citada ("Foi Temer, não Lula, quem permitiu as bets") checa essa parte. Se entrar em `checagens_aceitas`, são 6.
- **"COP30":** vira `cop` nos nomes e `cop30` nos termos, e os dois nunca batem.
- **Abstenção (0/11) otimista:** 10 das 11 frases `sem_checagem` são notícias neutras, que nem parecem boato; só ev06/s03 testa a abstenção num tema próximo de checagens.
- **Ressalva:** a análise olhou frases dos dois splits. Corrigir falhas de regra geral (maiúscula, COP30) é legítimo; os limiares devem ser calibrados só no split `calibracao`.

## Decisões menores

| Decisão | Motivo |
| --- | --- |
| Embedding `BAAI/bge-m3` | Candidato da Seção 5.3. Não exige prefixos (com o e5, esquecer o `query:` piora a busca sem dar erro). A comparação com o e5-large sai do Recall@5. |
| Limiar do NLI na etapa 2 **0,8** (era 0,5) | Calibrado em 01/10 com o `calibrar`, só no split de calibração: com 0,5, 0,6, 0,7 e 0,8 a cobertura ficou em 7/9, e os casamentos errados caíram de 4 para 2 (saem "Lula comunista", NLI 0,52, e "tarifaço", 0,67 no Mac e um pouco acima de 0,7 na CPU do Windows). Medido uma única vez no teste: cobertura igual (8/10), macro-F1 igual (0,69), casamentos errados de 3 para 2 (sai a Lei das Bets, 0,56). O Manual prioriza não citar a checagem errada (Seções 4.7 e 12.1). Custo: checagem certa com nota entre 0,5 e 0,8 deixa de ser citada; no diagnóstico das 36 frases, essa faixa tinha 1 certa (Nikolas Ferreira, 0,51, coberta por outras duas agências) e 3 erradas. Amostra pequena, frases ainda sem revisão do R1: recalibrar quando o conjunto for revisado. Reversível com `EVIDENCE_CLAIM_MATCH_MIN_PROB=0.5` |
| Limiar de similaridade **0,55** (o manual sugere 0,75) | Medido no corpus real: outro assunto ≈ 0,45, outro fato ≈ 0,55–0,57, checagem certa ≈ 0,58–0,68. Com 0,75, nada passaria. O limiar só separa "outro assunto"; "outro fato" é papel do ADR 1. |
| Até 6 candidatas avaliadas, até 3 evidências por frase | O limite de 3 aplicado antes da etapa 2 deixou o Aos Fatos de fora no caso Fachin |
| Vereditos mapeados de forma conservadora | Só rótulos inequívocos (falso, montagem; verdadeiro, comprovado) viram `contradiz`/`apoia`. "Enganoso", "Falta contexto", texto livre e rótulos desconhecidos viram `insuficiente`. |
| `excerpt` é o título, cortado em até 300 caracteres no fim de uma frase | É a conclusão da agência, literal e disponível para todas as checagens. O código nunca reescreve texto. |
| Saída em dicts, não em objetos `Evidence` | O Pydantic v2 rejeita instâncias de outra classe com os mesmos campos |
| Índice ausente = falha (`evidence: None`), e não lista vazia | Sem índice, o sistema não pode afirmar que procurou |
| Stub lê a fixture `02_evidencias_saida.json` e expõe `run` e `evidence_node` | Uma fonte só para a saída da Seção 4.6; os dois nomes atendem o nosso contrato (`run`, Seção 9.4) e o `graph.py` do grupo (`evidence_node`) |
| Primeira palavra da frase só é nome se o corpus a usa como nome (`data/corpus/nomes_proprios.txt`: palavras com maiúscula no meio de alegações e títulos mais vezes do que em minúscula; siglas curtas contam, palavras longas em caixa alta não). Pontuação separa nomes; nomes colados a números ficam inteiros ("COP30") | Na primeira rodada, "Aviões…" e "Arrependida, Cármen Lúcia…" viraram nomes e a checagem certa foi rejeitada como troca, e "COP30" nunca batia. Medido sem os modelos: das 48 URLs aceitas do conjunto, passam 47 (antes, 41); nos 37 pares, as mesmas 18/18 paráfrases passam e as mesmas 11/12 trocas são barradas. Custo: um nome nunca visto no corpus, no início da frase, não conta |
| NLI em fp16 opcional (`EVIDENCE_NLI_FP16`), desligado por padrão | Corta a memória do NLI pela metade, mas o DeBERTa-v3 pode ter overflow em fp16; só liga depois do `medir_recursos.py --comparar-fp16` |
| **Memória e tempo**: medidos só no Windows (CPU), em 01/10 (`eval/resultados/recursos_2026-10-01.json`) | Pesos: BGE-M3 2,12 GB (na CPU fica em fp32) + NLI 0,52 GB = **2,63 GB, acima do orçamento de 2 GB** da Seção 5.2; processo com 2,91 GB. Na GPU (cuda/mps) o código carrega o BGE-M3 em fp16: pela conta (568 milhões de parâmetros × 2 bytes ≈ 1,06 GB), o total ficaria perto de **1,6 GB**. É uma **estimativa**, não uma medida: confirmar na máquina da demo. O NLI ocupa 0,52 GB, cerca de metade do esperado em fp32, o que indica que ele já é carregado em meia precisão (como o arquivo do modelo está salvo); se a máquina da demo mostrar o mesmo, o `EVIDENCE_NLI_FP16` não faz diferença e fica desligado. Tempo na CPU (p50): 4,9 s por notícia de 3 frases e 64 s por notícia de 36; carregar os modelos leva ~13 s. No Mac, a rodada de 01/10 levou de 0,1 a 0,4 s por notícia de 3 frases |
| Coleta dividida em ~38 buscas por palavra-chave | A API dá erro 503 depois de ~500–600 resultados de uma mesma busca |
| Dados brutos e índice fora do Git | Seção 5.5 |

## Pendente (decisões do grupo e próximos passos)

| Item | Depende de |
| --- | --- |
| **Aprovar o ADR 1 e o ADR 2** | Reunião do grupo |
| Revisão das 36 frases de `data/gold/evidencias.json` (escritas pelo Claude), preenchendo `revisor` | R1 |
| Decidir casos de anotação: ev01/s02 (aceitar a checagem do Temer?), ev08/s02 (o "Lula comunista" é outro episódio?), ev11/s01 (F-15: as duas URLs aceitas têm stances diferentes) e trocar frases `sem_checagem` neutras por boatos sem checagem | R2, com a revisão do R1 |
| Recalibrar `CLAIM_MATCH_MIN_PROB` quando o conjunto for revisado ou ampliado | Revisão do R1 |
| **Medir memória e tempo na máquina da demo** (Mac M4, Seção 5.2): `python eval/medir_recursos.py --comparar-fp16 --salvar`, e decidir o `EVIDENCE_NLI_FP16` pela comparação fp32 × fp16. O R2 não tem acesso a um Mac nesta etapa; a medida fica com quem tiver a máquina da demo (o R1 mede a latência nela, Seção 9.3). Ver "Memória e tempo" nas decisões menores | R1 / máquina da demo |
| Converter `data/gold/evidencias.json` para o formato do gold set | R3 |
| Comparar BGE-M3 × e5-large pelo Recall@5 | — |
| Cobrir frases que desmentem o boato | Resultados do gold set |
| Avisar o R5 (erro de sintaxe na linha 11 do `synthesizer.py`) | — |
| Plugar o agente real no `graph.py` e simular busca e NLI no teste do grafo inteiro (o CI não tem torch nem chromadb) | R1 (integração) |

## Histórico

| Data | O que mudou |
| --- | --- |
| 26/09 | Agente reescrito sem LLM, com o contrato `run(state)`. BGE-M3. NLI da Seção 4.2 testado com os modelos reais, com os erros da tabela acima. |
| 27/09 | Stance pelo veredito + etapa "mesma alegação" (ADR 1). Limiar 0,75 → 0,55. Novas agências (ADR 2). Coleta por palavra-chave. |
| 28/09 | Termos-chave (o NLI casou dengue × chikungunya com 0,98), depois relaxados para exigir *troca*. Normalização "Foto mostra". Título indexado e usado como excerpt. Até 6 candidatas. |
| 28/09 | Simplificação. Ficou um único modo: o da Seção 4.2 e a proteção contra o boato citado saíram do código (continuam no histórico do Git, na tag `antes-da-simplificacao`). `src/retrieval/` passou a ter 4 arquivos. No empate UOL/BOL, prevalece o original. |
| 29/09 | Merge da `develop` (Ingestor e `state.py` da Seção 3.3). O agente passa a usar `Segment`/`Evidence` do `src/state.py` e o `evidence_schema.py` temporário foi apagado. Stub unificado. Casos de borda no formato do grupo, incluindo o fato parecido (dengue × chikungunya). |
| 01/10 | Avaliação (ADR 3): `eval/avaliar_evidencias.py` com `sortear`, `validar` e `avaliar`; formato do conjunto em `data/gold/evidencias.json`; testes sem modelos no CI. |
| 01/10 | Comandos `esqueleto` (12 entradas com as checagens sorteadas e as frases em branco) e `completar` (monta o texto das entradas). Filtro de checagens utilizáveis: sem guias, alegações negativas, perguntas, links, textos longos e espelhos (BOL e Acervo Estadão). |
| 01/10 | Conjunto preenchido: 36 frases escritas pelo Claude (rascunho, a revisar), URLs aceitas extras achadas por busca no corpus; `validar` sem erros. |
| 01/10 | Primeira rodada do `avaliar` (Recall@5 0,95; macro-F1 0,61; inventada 0,00; 7 casamentos errados) e análise de erros. Nova métrica "stance nas cobertas" (14/14) e comando `frases`, que gera a entrada do `diagnostico.py`. |
| 01/10 | Sprint 3: termos-chave com vocabulário de nomes do corpus (`nomes_proprios.txt`), pontuação separando nomes e "COP30" inteiro; comando `calibrar`; `eval/medir_recursos.py` e NLI em fp16 opcional; `fetch_articles.py --apenas-sites`. |
| 01/10 | Rodadas com a correção dos termos-chave (cobertura 15/19, macro-F1 0,72). Calibração do NLI no split de calibração e teste: limiar da etapa 2 de 0,5 para **0,8**. Medição de tempo e memória no Windows (CPU). O `avaliar` deixa de contar resultados não commitados como alteração local. |
| 03/10 | UOL: teste de 01/10 confirmou o bloqueio (5/5 falhas com 3 s de pausa); a pendência de terminar o download saiu. Memória e tempo registrados só no Windows (CPU, 2,63 GB); a medida na máquina da demo fica pendente com o R1. |
