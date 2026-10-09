# Agente de Evidências — decisões (ADR)

Dono: R2 (Túlio Celeri) · Atualizado em 03/10/2026 · Status: **proposto, a levar ao grupo**
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
- **Lupa: só pelo FACTCK.BR.** A API não devolveu checagens de `agencialupa.org` nem de `lupa.uol.com.br`. Em 03/10 entraram as checagens da Lupa (e mais do Aos Fatos) do FACTCK.BR; ver abaixo.
- **Entraram AFP Checamos, Estadão Verifica e UOL Confere**, para chegar aos "alguns milhares" da Seção 6.1. Resultado: 5.826 checagens (UOL 1.732, Estadão 1.479, Aos Fatos 1.192, AFP 1.191, Comprova 232).
- **Coleta sem limite de idade (07/10).** Com `--max-age-days 0` e a lista de palavras-chave ampliada para 83, a API passou a 15.423 checagens, de 2015 a 2026 (Aos Fatos 3.960, UOL 3.778, AFP 3.359, Estadão 2.618, Comprova 1.220). O download, sem AFP e UOL, trouxe o texto de 4.896 das 4.897 páginas novas. Índice: 15.938 checagens (8.314 com texto) e 99.464 trechos. Checagens anteriores a 2024 levam o ano no `source_name`, como no FACTCK.BR (decisões menores). Avaliação (07/10, GPU, `evidencias_2026-10-07.json`): Recall@5 22/23, cobertura 19/23, macro-F1 0,77, stance nas cobertas 19/19 e inventada 0/12, iguais às de 03/10. Casamentos errados: 5. O novo (ev12/s03) cita checagens de 2022 sobre a mesma montagem de Flávio Bolsonaro, com a mesma conclusão; é lacuna do gabarito, a corrigir na revisão. O ganho ainda não foi medido: o conjunto não tem frases sobre checagens de 2015–2023.
- **A AFP recusa o download** (515 de 515 tentativas) e o UOL/BOL passou a recusar depois de ~1.100 downloads. Em 01/10, três dias depois, um teste só com o UOL e 3 s de pausa (`fetch_articles.py --apenas-sites noticias.uol.com.br --limit 5 --delay 3`) falhou em 5 de 5 URLs com "download falhou" (o servidor não devolve a página, não é falha de extração): é bloqueio, e não limite de taxa. O bloqueio **não é contornado**: o download desiste do site depois de 20 falhas seguidas. Toda checagem entra no índice pelo título, mesmo sem o texto. Índice da API: 2.903 checagens com texto e 2.923 só com título, num total de 32.094 trechos; com o FACTCK.BR, 36.071 (03/10, depois do descarte abaixo).
- O BOL republica o UOL Confere com o mesmo título. As duas contam como uma checagem, e o agente cita o UOL (o original).
- **Sites novos e BOL fora do índice (08/10).** Uma sondagem de ~40 domínios na API achou quatro com checagens em pt-BR: Fato ou Fake (`oglobo.globo.com`), Truco (`apublica.org`), Correio Braziliense e Estado de Minas. Ficaram fora `nexojornal.com.br` (resumos com várias alegações por página) e as checagens de Portugal. Com mais 69 palavras-chave, a coleta sem limite de idade trouxe 1.658 checagens novas (17.089 URLs). Na avaliação seguinte, o ev12/s03 saiu do top 5: uma cópia no BOL da checagem de 2022 sobre a montagem de Flávio Bolsonaro somou-se às da AFP e do UOL e empurrou as de 2026 para fora. O BOL chega pela busca de `noticias.uol.com.br`, e 525 das 531 checagens dele tinham o original no UOL. **Decisão: `bol.uol.com.br` sai do corpus** (`config.DOMINIOS_EXCLUIDOS`). A coleta descarta essas URLs, e o `build_index.py` as ignora e apaga do índice os trechos que já estavam lá (535). Perda: 6 títulos sem par no UOL. As duas URLs do BOL no gabarito (ev02/s01 e ev12/s03) foram retiradas; as duas frases continuam com outras URLs aceitas. Índice: 17.013 checagens e 108.072 trechos. Avaliação (08/10, GPU, `evidencias_2026-10-08_2.json`): Recall@5 23/23, cobertura 20/23, macro-F1 0,77, stance nas cobertas 20/20, inventada 0/12 e 6 casamentos errados. O casamento novo (ev13/s01) é uma checagem da AFP de 2018 sobre o mesmo boato de Osasco, com rótulo "Sem evidências": lacuna do gabarito, como a de 07/10.
- **Coleta da noite de 08 para 09/10.** Palavras-chave tiradas do próprio corpus, nos 5 sites grandes (os 4 novos rendem pouco por busca): 1.300 nomes de `nomes_proprios.txt` (100 de piloto e 1.200 na noite, sorteados com semente 1; nomes com menos de 4 letras ficaram fora) e as 900 palavras mais frequentes nas alegações e títulos (presentes em pelo menos 15 checagens, sem as palavras funcionais nem as já usadas). Resultado: +1.233 checagens na API (18.322 URLs) e índice com 18.179 checagens (9.718 com texto) e 114.337 trechos (+6.265). O retorno caiu rápido: os lotes de 400 nomes trouxeram 339, 312 e 61 checagens; os lotes de 150 palavras, de 148 a 15. O Comprova não trouxe quase nada (1). A busca sem palavra-chave, repetida a cada lote, ainda acha checagens: a API a corta com erro 503 depois de ~1.400–1.900 resultados, e a ordem varia entre execuções. Leitura: para estas agências a API está perto do esgotamento; crescer de novo pede outra fonte. Os 2.201 nomes não usados não foram rodados. Avaliação depois de cada etapa (09/10, GPU, `evidencias_2026-10-09.json` e `_2.json`): igual à de 08/10, com os mesmos erros. O conjunto não tem frases sobre os temas novos, então o ganho não foi medido.

**FACTCK.BR (03/10).** O dataset FACTCK.BR (https://github.com/jghm-f/FACTCK.BR, licença MIT; os autores pedem a citação do artigo do WebMedia '19, https://doi.org/10.1145/3323503.3361698) tem 1.312 checagens de 2016 a 2019 da Lupa, do Aos Fatos e do Truco, e nenhuma URL em comum com o corpus da API. O R2 tratou o dataset e baixou o texto de 982 das 983 páginas (notebook `AnaliseFACTCKbr`, arquivo `factckbr_com_texto.csv`, fora do Git em `data/corpus/raw/`). O `data/corpus/import_factckbr.py` converte o CSV para o formato do corpus:

- **Entram 727 checagens**: Lupa 379 e Aos Fatos 348 (677 viram `contradiz`, 42 `insuficiente`, 8 `apoia`).
- **Truco fica para depois** (414 linhas): checa falas de políticos, que envelhecem rápido ("Haddad é réu por improbidade…", Verdadeiro em 2018), e os títulos dele não trazem a conclusão ("3 frases que mostram o poder de Cunha").
- **Só páginas com uma alegação.** 91 páginas reúnem várias alegações (até 27), e 61 delas com rótulos diferentes; o índice e o agente supõem uma alegação por URL, e o veredito sairia trocado. Saem também 10 linhas sem alegação e 13 com mais de 60 palavras (texto da matéria colado no campo).
- **Fora: veredito "verdadeiro" com título que desmente.** Em 4 das 12 checagens com veredito verdadeiro, o título diz o contrário: "É falso que Freixo recebe auxílio-moradia…", "É falso que aliado de Bolsonaro acaba de ser preso", "Papa Francisco não enviou terço a Lula; Vaticano desmente boato" e "Imagem que mostra personagens se beijando não é de novo filme da Disney". O rótulo da coleta original está trocado. Como a stance vem do veredito (ADR 1), o agente daria `apoia` a um boato desmentido, o erro mais grave da Seção 12.1. A regra (veredito que vira `apoia` e título com "falso/falsa", "não", "desmente" ou "boato") pega exatamente essas 4 e mantém as outras 8. O caso inverso (veredito falso e título "É verdade que…") não aparece. Achado em 03/10, ao escolher checagens para o conjunto de avaliação.
- **Ano no `source_name`** ("Agência Lupa (2019)", "Aos Fatos (2018)"): o `Evidence` não tem campo de data, e uma checagem de 2018 não pode parecer atual no dossiê. O contrato não muda.
- **Títulos** (são o `excerpt`): sai a marca "#Verificamos:" e o " | Aos Fatos" do fim. Em 198 títulos da Lupa a coleta original perdeu o "É" inicial ("#Verificamos:  falso que…", com dois espaços); ele é restaurado, como está hoje na página da Lupa ("É falso que imagem antiga mostre Miriam Leitão…"). É a única correção feita no texto, e só nesse padrão. O parágrafo de abertura não serve como alternativa: na Lupa ele descreve o boato ("Circula pelas redes sociais…").
- **URLs da Lupa** passam do domínio antigo (`piaui.folha.uol.com.br/lupa/…`) para o atual (`www.agencialupa.org/jornalismo/…`), que é o link citado; a original fica em `url_original`. Conferido em duas checagens.
- ⚠️ **Os textos da Lupa foram baixados com um User-Agent de navegador**, porque o site devolvia 403 ao cliente padrão. Decisão do R2 (03/10): usar. Por que não é o mesmo caso da AFP e do UOL: o `robots.txt` da Lupa permite o acesso aos artigos a qualquer cliente e só barra crawlers de IA e scrapers conhecidos, pelo nome. O 403 é um filtro automático de robôs, e não uma recusa do site ao acesso. Na AFP e no UOL, o servidor recusa todas as tentativas. A regra continua: não contornamos recusa explícita. **A levar ao grupo** junto com o ADR 2.
- O metadado `corpus` ("factcheck_api" ou "factckbr") registra a fonte de cada trecho, e o `build_index.py --apenas-novos` indexa só o que falta, sem recalcular os 32 mil trechos.
- **Rodada com o FACTCK.BR** (03/10, CPU, `eval/resultados/evidencias_2026-10-03_2.json`, 36.099 trechos, antes do descarte acima): Recall@5 18/19, cobertura 15/19, macro-F1 0,72, stance nas cobertas 15/15 e inventada 0/11, iguais às de 01/10. As checagens de 2018–2019 não tomaram o lugar das certas. Casamentos errados: 4 no conjunto todo (primeira rodada do conjunto todo com o NLI em 0,8: Kamala, Bolsonaro na UTI, Silvio Almeida e Marçal); no teste, os mesmos 2 de 01/10. O conjunto não tinha frases sobre checagens do FACTCK.BR.
- **Ganho do FACTCK.BR** (03/10, CPU, `evidencias_2026-10-03_4.json`, 36.071 trechos, depois do descarte): com as entradas ev13 e ev14 (6 frases escritas pelo R2 a partir de checagens do FACTCK.BR), o conjunto passa a 42 frases. Resultado: Recall@5 22/23, cobertura 19/23, macro-F1 0,77, stance nas cobertas 19/19, inventada 0/12 e os mesmos 4 casamentos errados. As 4 checagens do FACTCK.BR vieram em 1º lugar na busca e foram citadas com a stance certa (2 `contradiz` e 2 `apoia`). O fato parecido (Moro × Cunha no lugar de Moro × Dallagnol) foi barrado na etapa 2, embora a checagem-base estivesse em 2º na busca. A frase sem checagem não recebeu evidência.

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
  - Ev01/s02 (Lei das Bets) parecia falha de anotação, mas não é (decisão de 04/10): a checagem citada ("Foi Temer, não Lula, quem permitiu as bets") desmente que a lei de Lula *permitiu* as bets, e a frase só diz que Lula assinou a lei, o que é verdade (ele sancionou a regulamentação de 2023). Com o NLI em 0,8, o agente deixou de citá-la.
- **"COP30":** vira `cop` nos nomes e `cop30` nos termos, e os dois nunca batem.
- **Abstenção (0/11) otimista:** 10 das 11 frases `sem_checagem` são notícias neutras, que nem parecem boato; só ev06/s03 testa a abstenção num tema próximo de checagens.
- **Ressalva:** a análise olhou frases dos dois splits. Corrigir falhas de regra geral (maiúscula, COP30) é legítimo; os limiares devem ser calibrados só no split `calibracao`.

## Decisões menores

| Decisão | Motivo |
| --- | --- |
| Embedding `BAAI/bge-m3` (comparado com o e5-large em 03/10) | Candidato da Seção 5.3. Não exige prefixos (com o e5, esquecer o `query:` piora a busca sem dar erro). Na comparação de igual para igual (42 frases, mesmo índice de 36.071 trechos, avaliação na CPU; `evidencias_2026-10-03_4.json` × `_5.json`), o BGE-M3 acha mais: Recall@5 22/23 × 17/23, cobertura 19/23 × 14/23 e macro-F1 0,77 × 0,56 (o do e5 fica abaixo da meta). O e5 não pôs entre as 5 primeiras nenhuma das 4 checagens do FACTCK.BR do conjunto. Ele cita menos checagens erradas (1 × 4), mas porque acha menos em geral; os 4 erros do BGE-M3 se resolvem na etapa 2 (ver Pendente). Na primeira comparação (36 frases, índice anterior ao descarte, e5 avaliado na GPU), a diferença era menor: Recall@5 18 × 16 e cobertura 15 × 13 |
| Limiar do NLI na etapa 2 **0,8** (era 0,5) | Calibrado em 01/10 com o `calibrar`, só no split de calibração: com 0,5, 0,6, 0,7 e 0,8 a cobertura ficou em 7/9, e os casamentos errados caíram de 4 para 2 (saem "Lula comunista", NLI 0,52, e "tarifaço", 0,67 no Mac e um pouco acima de 0,7 na CPU do Windows). Medido uma única vez no teste: cobertura igual (8/10), macro-F1 igual (0,69), casamentos errados de 3 para 2 (sai a Lei das Bets, 0,56). O Manual prioriza não citar a checagem errada (Seções 4.7 e 12.1). Custo: checagem certa com nota entre 0,5 e 0,8 deixa de ser citada; no diagnóstico das 36 frases, essa faixa tinha 1 certa (Nikolas Ferreira, 0,51, coberta por outras duas agências) e 3 erradas. Amostra pequena, frases ainda sem revisão do R1: recalibrar quando o conjunto for revisado. Reversível com `EVIDENCE_CLAIM_MATCH_MIN_PROB=0.5` |
| Limiar de similaridade **0,55** (o manual sugere 0,75) | Medido no corpus real: outro assunto ≈ 0,45, outro fato ≈ 0,55–0,57, checagem certa ≈ 0,58–0,68. Com 0,75, nada passaria. O limiar só separa "outro assunto"; "outro fato" é papel do ADR 1. |
| Até 6 candidatas avaliadas, até 3 evidências por frase | O limite de 3 aplicado antes da etapa 2 deixou o Aos Fatos de fora no caso Fachin |
| Vereditos mapeados de forma conservadora | Só rótulos inequívocos (falso, montagem; verdadeiro, comprovado) viram `contradiz`/`apoia`. "Enganoso", "Falta contexto", texto livre e rótulos desconhecidos viram `insuficiente`. |
| `excerpt` é o título, cortado em até 300 caracteres no fim de uma frase | É a conclusão da agência, literal e disponível para todas as checagens. O código nunca reescreve texto. |
| Saída em dicts, não em objetos `Evidence` | O Pydantic v2 rejeita instâncias de outra classe com os mesmos campos |
| Índice ausente = falha (`evidence: None`), e não lista vazia | Sem índice, o sistema não pode afirmar que procurou |
| Stub lê a fixture `02_evidencias_saida.json` e expõe `run` e `evidence_node` | Uma fonte só para a saída da Seção 4.6; os dois nomes atendem o nosso contrato (`run`, Seção 9.4) e o `graph.py` do grupo (`evidence_node`) |
| Primeira palavra da frase só é nome se o corpus a usa como nome (`data/corpus/nomes_proprios.txt`: palavras com maiúscula no meio de alegações e títulos mais vezes do que em minúscula; siglas curtas contam, palavras longas em caixa alta não). Pontuação separa nomes; nomes colados a números ficam inteiros ("COP30") | Na primeira rodada, "Aviões…" e "Arrependida, Cármen Lúcia…" viraram nomes e a checagem certa foi rejeitada como troca, e "COP30" nunca batia. Medido sem os modelos: das 48 URLs aceitas do conjunto, passam 47 (antes, 41); nos 37 pares, as mesmas 18/18 paráfrases passam e as mesmas 11/12 trocas são barradas. Custo: um nome nunca visto no corpus, no início da frase, não conta |
| NLI em fp16 opcional (`EVIDENCE_NLI_FP16`), desligado por padrão | Corta a memória do NLI pela metade, mas o DeBERTa-v3 pode ter overflow em fp16; só liga depois do `medir_recursos.py --comparar-fp16`. Comparação de 03/10 na GPU: diferença 0 nas 74 comparações. O modelo já é carregado em meia precisão, como o arquivo está salvo (0,52 GB de pesos na CPU e na GPU), então a variável não muda nada. Fica desligada e pode sair do código |
| **Memória e tempo**: medidos no Windows, na CPU (01/10, `eval/resultados/recursos_2026-10-01.json`) e numa GPU NVIDIA (03/10, `recursos_2026-10-03.json`) | **CPU:** BGE-M3 2,12 GB (na CPU fica em fp32) + NLI 0,52 GB = **2,63 GB, acima do orçamento de 2 GB** da Seção 5.2; processo com 2,91 GB. Tempo (p50): 4,9 s por notícia de 3 frases e 64 s por notícia de 36; carregar os modelos leva ~13 s. **GPU:** o BGE-M3 vai em fp16: 1,06 GB + NLI 0,52 GB = **1,58 GB, dentro do orçamento** (a conta de 01/10 previa ~1,6 GB). O pico alocado na GPU foi 2,59 GB, porque soma às ativações dos lotes; o processo usou 2,67 GB de RAM. Tempo (p50): 0,11 s por notícia de 3 frases e 0,79 s por notícia de 36; carregar leva ~14 s. No Mac, a rodada de 01/10 levou de 0,1 a 0,4 s por notícia de 3 frases |
| Coleta dividida em buscas por palavra-chave (~38 até 07/10; 84 desde então, com a lista `QUERIES` ampliada) | A API dá erro 503 depois de ~500–600 resultados de uma mesma busca. Cada palavra nova abre outro lote de até ~500 resultados |
| Checagem anterior a 2024 leva o ano no `source_name` ("Aos Fatos (2019)"; `SOURCE_YEAR_BEFORE` em `config.py`, aplicado no `build_index.py`) | Mesmo motivo do FACTCK.BR (ADR 2): o `Evidence` não tem campo de data. Prepara a coleta sem limite de idade (`--max-age-days 0`). Checagens sem data e nomes que já trazem o ano ficam como estão |
| Dados brutos e índice fora do Git | Seção 5.5 |

## Pendente (decisões do grupo e próximos passos)

| Item | Depende de |
| --- | --- |
| **Aprovar o ADR 1 e o ADR 2** | Reunião do grupo |
| Revisão das 42 frases de `data/gold/evidencias.json` (36 escritas pelo Claude; as 6 de ev13 e ev14, pelo R2), preenchendo `revisor` | R1 |
| Trocar parte das frases `sem_checagem` neutras por boatos sem checagem no corpus (sugestão: 6 de 12, 3 por split), para a "evidência inventada" testar a abstenção num tema próximo de checagens. Fica para depois do PR, se der tempo | R2, com a revisão do R1 |
| Recalibrar `CLAIM_MATCH_MIN_PROB` quando o conjunto for revisado ou ampliado | Revisão do R1 |
| **Medir memória e tempo na máquina da demo** (Mac M4, Seção 5.2): `python eval/medir_recursos.py --comparar-fp16 --salvar`, e decidir o `EVIDENCE_NLI_FP16` pela comparação fp32 × fp16. O R2 não tem acesso a um Mac nesta etapa e mediu no Windows, na CPU e numa GPU NVIDIA (1,58 GB de pesos); a medida no Mac fica com quem tiver a máquina da demo (o R1 mede a latência nela, Seção 9.3). Ver "Memória e tempo" nas decisões menores | R1 / máquina da demo |
| Converter `data/gold/evidencias.json` para o formato do gold set | R3 |
| Casamentos errados que sobram (Kamala, Bolsonaro na UTI, Silvio Almeida e Marçal; NLI de 0,93 a 0,98 nos dois primeiros): registrados em 04/10 como limitação conhecida no card. Uma regra na etapa 2 que compare o episódio, e não só os termos, fica para depois do PR | Depois |
| FACTCK.BR: Truco e páginas com várias alegações (exige uma chave por alegação, e não por URL) | Depois |
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
| 03/10 | FACTCK.BR: 731 checagens da Lupa e do Aos Fatos (2018–2019), com ano no `source_name`, títulos limpos e URLs da Lupa no domínio atual; Truco e páginas com várias alegações ficam para depois. Textos da Lupa baixados com User-Agent de navegador: usados (ADR 2). `build_index.py --apenas-novos`. |
| 03/10 | Índice reconstruído com o FACTCK.BR (36.099 trechos): métricas iguais às de 01/10. Primeira comparação BGE-M3 × e5-large (36 frases). Memória e tempo numa GPU NVIDIA: 1,58 GB de pesos, e o fp16 do NLI não muda nada. |
| 03/10 | FACTCK.BR: descartadas as 4 checagens "verdadeiro" com título que desmente (ficam 727). O filtro `--agencia` do `sortear` passa a olhar só o nome e o domínio da agência. Entradas ev13 e ev14 no conjunto, com as frases a escrever pelo R2. |
| 03/10 | Reindexação depois do descarte (36.071 trechos) e conjunto com 42 frases: Recall@5 22/23, macro-F1 0,77, as 4 checagens do FACTCK.BR citadas com a stance certa. BGE-M3 × e5-large de igual para igual: **fica o BGE-M3** (e5: Recall@5 17/23, macro-F1 0,56). |
| 04/10 | Casos de anotação decididos, sem mudar URLs nem stances: ev01/s02 não aceita a checagem do Temer (outra alegação), ev08/s02 não aceita "Lula comunista" (outro episódio) e ev11/s01 mantém `apoia` com as duas URLs. Motivos no `obs` de cada frase. Índice e dados brutos no Google Drive; `chromadb` fixado em 1.5.9. Os 4 casamentos errados que sobram ficam como limitação conhecida (meta 0 não atingida). |
| 07/10 | Coleta da API sem limite de idade e com 83 palavras-chave: 15.423 checagens (2015–2026); índice com 99.464 trechos. Ano no `source_name` das checagens anteriores a 2024. Avaliação: métricas iguais às de 03/10, com 1 casamento errado a mais que é lacuna do gabarito (ev12/s03). Índice novo enviado ao Drive. |
| 08/10 | Quatro sites novos (Fato ou Fake, Truco, Correio Braziliense, Estado de Minas) e mais 69 palavras-chave: +1.658 checagens. `bol.uol.com.br` sai do corpus e do gabarito (republica o UOL e ocupava vagas do top 5). Índice com 108.072 trechos. Avaliação: Recall@5 23/23, cobertura 20/23, macro-F1 0,77; 6 casamentos errados, o novo é lacuna do gabarito (ev13/s01). |
| 09/10 | Coleta noturna com nomes próprios e palavras frequentes do corpus como palavras-chave: +1.233 checagens, índice com 114.337 trechos. Retorno decrescente: a API está perto do esgotamento para as agências atuais. Avaliação igual à de 08/10. |
