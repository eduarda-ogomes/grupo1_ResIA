# Dossiê final e guardrails de contexto — design

Data: 08/10/2026. Origem: `Testes e Possíveis Melhorias.md` (5 itens de teste manual com capturas) e decisões do grupo em 08/10.

## Decisões tomadas

| Pergunta | Decisão |
| --- | --- |
| Interface | `app/app.py` atual da `develop`; o redesign da `feat/interface-web` fica para depois |
| Seções redundantes (item 4) | Fica **"Como o texto argumenta"** (passa pelos guardrails). A coluna crua "Marcadores de Texto (Viés/Falácia)" sai do app |
| Coluna "Evidências Analisadas" (item 2) | Sai do app: repete "O que as checagens dizem" sem dizer a qual frase cada checagem se refere. A legenda pedida no item 2 entra na seção de checagens |
| Fontes (item 5) | Referência numerada `[↗ n]` no fim de cada linha de checagem; seção **"Fontes"** no fim com o título da checagem e o link |
| Guardrails | Implementar os de maior retorno (abaixo); as demais ideias ficam registradas como visão |

## Estrutura final do dossiê

O dossiê continua sendo uma string Markdown em `state.dossier` (o `PipelineState` não muda). Ordem das seções e o motivo:

| # | Seção | Quem escreve | Por que nesta posição |
| --- | --- | --- | --- |
| 1 | `## Resumo` | código | Pirâmide invertida: o leitor vê o tamanho do problema antes dos detalhes |
| 2 | `## O que as checagens dizem` | código | É o fato mais forte (veredito de agências, com atribuição) |
| 3 | `## Como o texto argumenta` | LLM + guardrails (fallback em código) | Depois dos fatos, como o texto tenta convencer |
| 4 | `## Perguntas para pensar antes de decidir` | Agente Socrático | Fecha o raciocínio com a ação do leitor |
| 5 | `## Limites desta análise` | código | O que a análise não cobre |
| 6 | `## Fontes` | código | Referências; só aparece quando há evidência |

### 1. Resumo (cópia exata)

```
## Resumo
- {N} frases analisadas: {F} afirmações factuais e {V} opiniões.
- {K} das {F} afirmações factuais têm checagem publicada ({contagem por stance}).
- {M} padrões de argumentação apontados.
- O dossiê não dá veredito: mostra o que já foi checado, como o texto argumenta e o que perguntar antes de decidir.
```

- Singular: "1 frase analisada", "1 afirmação factual", "1 opinião", "1 padrão de argumentação apontado".
- Contagem por stance, na ordem contradiz → apoia → insuficiente, separada por vírgula: "2 contradizem, 1 apoia, 1 não conclusiva" (singular "contradiz", "apoia", "não conclusiva"; plural "contradizem", "apoiam", "não conclusivas").
- Casos degradados:
  - Sem `text_report`: a 1ª linha vira "- {N} frases analisadas.", a 2ª vira "- {K} frases têm checagem publicada (...)." e a 3ª some.
  - `evidence is None`: a 2ª linha vira "- O banco de checagens não pôde ser consultado."
  - Nenhuma checagem: "- Nenhuma das {F} afirmações factuais tem checagem no nosso banco." (sem `text_report`: "- Nenhuma frase tem checagem no nosso banco.").
  - `M == 0`: "- Nenhum padrão de argumentação apontado."

### 2. O que as checagens dizem (cópia exata)

```
## O que as checagens dizem
_Comparamos cada afirmação factual com checagens já publicadas por agências. **Contradiz**: a agência checou uma alegação igual e concluiu que ela não se sustenta. **Apoia**: concluiu que ela se sustenta. **Não conclusiva**: deu um veredito intermediário (como "enganoso" ou "sem contexto") ou não chegou a uma conclusão. O selo ao lado é o veredito da própria agência; o número leva à fonte._
- "{frase}"
  - {Stance} · {source_name}: {agency_verdict} [↗ {n}](<{source_url}>)
- Sem checagem no nosso banco: {resumo}. Isso não confirma nem descarta {essa frase|essas frases}.
```

- A legenda não usa os termos do filtro de veredito.
- `{Stance}`: contradiz → "Contradiz", apoia → "Apoia", insuficiente → "Não conclusiva". Sem `agency_verdict`: `{Stance} · {source_name} [↗ n](<url>)`.
- O título da checagem (`excerpt`) não aparece no corpo, só em "Fontes" (preview escolhido pelo grupo).
- A linha "Sem checagem" (item 3) é limitada: 1 frase → `1 afirmação factual, "A"`; 2 → `2 afirmações factuais, "A" e "B"`; 3 ou mais → `{n} afirmações factuais, como "A", "B" e mais {n-2}`. Cada frase é cortada em 80 caracteres com "…". A lista completa fica no expander do app.
- Frases e trechos vindos da notícia ou do corpus passam por `escapar_markdown` e depois por `neutralizar_urls`, nessa ordem, para que o `[link]` não seja escapado. Caracteres escapados: `\ ` * _ [ ] < > ~ $`. O `$` é necessário porque o Streamlit renderiza `$...$` como LaTeX ("R$ 10 e R$ 20").

### 6. Fontes (cópia exata)

```
## Fontes
1. {source_name}: {agency_verdict} — "{excerpt}" · [abrir ↗](<{source_url}>)
```

- A numeração segue a ordem da primeira citação no corpo; a mesma URL tem sempre o mesmo número.
- A seção é omitida quando não há evidência.

### Regras de UX e de lógica do dossiê

1. Nenhum veredito sobre a notícia; o veredito de uma agência só aparece atribuído a ela (selo).
2. Toda afirmação do dossiê tem uma origem rastreável: frase da notícia, checagem com número de fonte ou "Limites".
3. Progressão: resumo → fatos → retórica → perguntas → limites → referências.
4. Tamanho limitado: nenhuma seção escrita pelo código cresce sem limite com o tamanho da notícia (a linha "Sem checagem" tem teto; a lista completa fica no app).
5. Cor nunca é o único sinal: stance sempre por extenso.
6. Ausência ≠ negação: "sem checagem" sempre vem com "não confirma nem descarta".
7. Nomes técnicos (`adjetivacao_extrema`, `s03`) nunca aparecem para o leitor.

### App (`app/app.py`)

- Uma coluna: título da notícia, linha "Publicado em {data}" (só quando há data), avisos, dossiê (`st.markdown`).
- Expander **"Todas as frases analisadas ({N})"**: tabela com as colunas frase / tipo ("Fato", "Opinião", "Sem classificação") / checagens (número).
- Expander **"Detalhes técnicos"**: tempos por etapa e o link do trace no Phoenix.
- Saem as colunas "Evidências Analisadas" e "Marcadores de Texto (Viés/Falácia)".

## Agente de Texto: notícia de desastre e falas citadas (item 1)

O modelo marcou "carbonizados" e "totalmente destruído" (descrição factual de um acidente) e uma nota de pesar citada ("Com profundo pesar...") como adjetivação/urgência. Novas regras no prompt e um exemplo few-shot sem marcadores:

- Palavras que descrevem um fato concreto e grave (mortes, destruição, ferimentos, números de vítimas) não são adjetivação extrema, mesmo que fortes.
- Linguagem emocional dentro de falas, notas ou declarações citadas e atribuídas a alguém identificado é da pessoa citada, não do texto, e não é marcador.

## Guardrails: impedir dados fora do contexto da notícia

### Onde dado de fora entra hoje

| Porta | Exemplo observado | Camada |
| --- | --- | --- |
| Página: texto que não é da matéria | "Os artigos de opinião assinados não refletem necessariamente o ponto de vista da..." virou frase checada (captura 5) | Ingestor |
| Busca: checagem de outro assunto | "Vídeo de aeronave tomada por névoa foi gravado na China" ligado a "Isso resultou em acúmulo de material combustível" (captura 5) | Evidências |
| LLM: trecho citado que não está na notícia | paráfrase entre aspas na seção "Como o texto argumenta" | Sintetizador |
| LLM: nome, número ou doença que a notícia não menciona | pergunta socrática ou bullet trazendo entidade externa | Sintetizador, Socrático |

### Implementados neste ciclo (todos determinísticos, sem LLM)

| ID | Guardrail | Regra | Ação ao falhar |
| --- | --- | --- | --- |
| G1 | Filtro de boilerplate | Parágrafo extraído de URL que bate com um padrão de rodapé/aviso/chamada é removido antes da segmentação | Remove o parágrafo |
| G2 | Ancoragem lexical da evidência | A frase e a alegação checada (ou o título da checagem) precisam ter ≥ `EVIDENCE_MIN_CONTENT_OVERLAP` (padrão 1) radicais de conteúdo em comum | Descarta a candidata antes do NLI |
| G3 | Citação literal | Todo trecho entre aspas no texto do Sintetizador precisa existir em alguma frase da notícia (ignorando caixa, espaços e tipo de aspas; "…" ou "..." separa partes) | Retry nomeando o trecho → fallback em código |
| G4 | Termos fora do contexto | Nomes próprios, números e doenças no texto do LLM precisam aparecer na notícia (radical de 5 letras, sem acento) | Sintetizador: retry → fallback. Socrático: descarta a pergunta; < 2 perguntas → retry |

### Visão (não implementado; ordem sugerida)

1. **Saída estruturada no Sintetizador.** O LLM devolve JSON `{segment_id, marcador, efeito}` e o código escreve o trecho literal. G3 deixa de ser necessário e o LLM não consegue mais citar texto de fora. É a mudança de maior retorno; custo: prompt novo e reavaliação.
2. **Coerência temática no nível da notícia.** Descartar a checagem cuja similaridade (BGE-M3, já carregado) com o título ou o centróide da notícia fica abaixo de um limiar calibrado no gold set. Pega checagem de outro assunto que compartilha uma palavra genérica (que G2 deixa passar).
3. **Resolução de anáfora antes da busca.** Frases como "Isso resultou em..." buscam com a frase anterior concatenada; a evidência continua presa à frase original.
4. **Coerência temporal.** Com `published_at`, sinalizar ou descartar checagens muito anteriores à notícia (hoje só o ano aparece no nome da fonte).
5. **NLI de fidelidade no texto do LLM.** Cada bullet precisa ser implicado (mDeBERTa) pela frase que cita. Custo: latência extra por bullet.
6. **`favor_precision=True` no trafilatura.** Menos boilerplate na origem; precisa de checagem manual em páginas reais para não cortar texto da matéria.
7. **Feedback do leitor.** Botão "esta checagem não tem a ver" grava o par (frase, URL) para ampliar o gold set de casamentos errados.
8. **LLM-juiz.** Descartado por ora: dobra a latência e herda os mesmos vieses do modelo de 7B.
