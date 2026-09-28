# Agente de Evidências — decisões (ADR)

Dono: R2 (Túlio Celeri) · Atualizado em 28/09/2026 · Status: **proposto, a levar ao grupo**
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
2. **NLI entre alegação e frase.** Antes da comparação, tira-se "Foto/Vídeo/Imagem mostra" da alegação. A checagem segue se o entailment for ≥ 0,5 em **pelo menos uma direção**. Uma direção basta porque a notícia costuma ser mais específica ou mais genérica que a alegação.
3. **Stance e excerpt.** A stance vem do veredito: falso → `contradiz`, verdadeiro → `apoia`, o resto → `insuficiente`. O `excerpt` é o título da checagem, que é a conclusão escrita pela agência.

O parágrafo que reproduz o boato deixa de ser premissa. Ele passa a só ajudar a busca a achar a checagem certa.

**Experimento** (`data/corpus/experimento_etapa2.py`, NLI real). Os pares são alegações reais do corpus e frases escritas para o teste: paráfrases, trocas de nome ou número, negações e outros fatos.

| Variante | Acertos | **Casou errado** | Paráfrase perdida |
| --- | --- | --- | --- |
| Só NLI | 31/35 | **3** (chikungunya, Fux, R$ 50 mil) | 1 |
| Só termos-chave | 31/35 | 4 (negações, R$ 600) | 0 |
| **NLI + termos-chave + normalização (adotada)** | **35/37** | **0** | 2 (Fachin × Aos Fatos e AFP) |

O NLI e os termos-chave se completam. O NLI deixa passar troca de nome entre frases quase iguais, e os termos-chave pegam isso. Os termos-chave deixam passar negação, e o NLI pega. Os limiares 0,5, 0,7 e 0,9 deram o mesmo resultado, porque o NLI responde perto de 0 ou de 1.

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
- **A AFP recusa o download** (515 de 515 tentativas) e o UOL/BOL passou a recusar depois de ~1.100 downloads. O bloqueio **não é contornado**: o download desiste do site depois de 20 falhas seguidas. Toda checagem entra no índice pelo título, mesmo sem o texto. Índice atual: 2.903 checagens com texto e 2.923 só com título, num total de 32.094 trechos.
- O BOL republica o UOL Confere com o mesmo título. As duas contam como uma checagem, e o agente cita o UOL (o original).

## Decisões menores

| Decisão | Motivo |
| --- | --- |
| Embedding `BAAI/bge-m3` | Candidato da Seção 5.3. Não exige prefixos (com o e5, esquecer o `query:` piora a busca sem dar erro). A comparação com o e5-large sai do Recall@5. |
| Limiar de similaridade **0,55** (o manual sugere 0,75) | Medido no corpus real: outro assunto ≈ 0,45, outro fato ≈ 0,55–0,57, checagem certa ≈ 0,58–0,68. Com 0,75, nada passaria. O limiar só separa "outro assunto"; "outro fato" é papel do ADR 1. |
| Até 6 candidatas avaliadas, até 3 evidências por frase | O limite de 3 aplicado antes da etapa 2 deixou o Aos Fatos de fora no caso Fachin |
| Vereditos mapeados de forma conservadora | Só rótulos inequívocos (falso, montagem; verdadeiro, comprovado) viram `contradiz`/`apoia`. "Enganoso", "Falta contexto", texto livre e rótulos desconhecidos viram `insuficiente`. |
| `excerpt` é o título, cortado em até 300 caracteres no fim de uma frase | É a conclusão da agência, literal e disponível para todas as checagens. O código nunca reescreve texto. |
| Saída em dicts, não em objetos `Evidence` | O Pydantic v2 rejeita instâncias de outra classe com os mesmos campos |
| Índice ausente = falha (`evidence: None`), e não lista vazia | Sem índice, o sistema não pode afirmar que procurou |
| Schema local temporário (`evidence_schema.py`) | O `state.py` da `main` ainda não segue a Seção 3.3 e não será alterado nesta branch (risco de conflito) |
| Coleta dividida em ~38 buscas por palavra-chave | A API dá erro 503 depois de ~500–600 resultados de uma mesma busca |
| Dados brutos e índice fora do Git | Seção 5.5 |

## Pendente (decisões do grupo e próximos passos)

| Item | Depende de |
| --- | --- |
| **Aprovar o ADR 1 e o ADR 2** | Reunião do grupo |
| Formato do gold set; anotar as 12 entradas | R3 |
| Script de métricas (Recall@5, macro-F1 de stance, taxa de evidência inventada) | Harness do R3 |
| Calibrar `SIM_THRESHOLD` e `CLAIM_MATCH_MIN_PROB`; comparar BGE-M3 × e5-large | Gold set |
| Medir latência e memória na máquina da demo (orçamento < 2 GB, Seção 5.2) | — |
| Terminar o download do UOL (`--delay 3`) e reindexar | — |
| Cobrir frases que desmentem o boato | Resultados do gold set |
| Avisar o R4 (`app.py` lê as evidências como objetos) e o R5 (erro de sintaxe na linha 11 do `synthesizer.py`) | — |

## Histórico

| Data | O que mudou |
| --- | --- |
| 26/09 | Agente reescrito sem LLM, com o contrato `run(state)`. BGE-M3. NLI da Seção 4.2 testado com os modelos reais, com os erros da tabela acima. |
| 27/09 | Stance pelo veredito + etapa "mesma alegação" (ADR 1). Limiar 0,75 → 0,55. Novas agências (ADR 2). Coleta por palavra-chave. |
| 28/09 | Termos-chave (o NLI casou dengue × chikungunya com 0,98), depois relaxados para exigir *troca*. Normalização "Foto mostra". Título indexado e usado como excerpt. Até 6 candidatas. |
| 28/09 | Simplificação. Ficou um único modo: o da Seção 4.2 e a proteção contra o boato citado saíram do código (continuam no histórico do Git, na tag `antes-da-simplificacao`). `src/retrieval/` passou a ter 4 arquivos. No empate UOL/BOL, prevalece o original. |
