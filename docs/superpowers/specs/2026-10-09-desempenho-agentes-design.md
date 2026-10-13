# Desempenho e correção dos agentes com LLM — design

Data: 09/10/2026. Escopo: Agente de Texto, Sintetizador e Agente Socrático. Base: branch `feat/dossie-final`.

## Onde o tempo vai hoje

| Medida | Valor | Fonte |
| --- | --- | --- |
| Ponta a ponta, p50 (entradas curtas, ~440 caracteres) | 31,2 s | `eval/resultados/latencia_2026-10-06.json` |
| Agente de Texto, p50 | 22,3 s (caminho crítico) | idem |
| Sintetizador, p50 | 8,9 s (caminho crítico) | idem |
| Agente Socrático, p50 | 9,6 s (em paralelo com o Texto) | idem |
| Geração do `qwen/qwen2.5-vl-7b` nesta máquina | ~19 tokens/s | sonda de 09/10 |
| 2 chamadas simultâneas ao LM Studio | 15,5 s na parede (21,2 s em fila); cada uma ~45% mais lenta | sonda de 09/10 |

Conclusões:
- O tempo é dominado pelos tokens **gerados**.
- O Socrático, rodando junto com o Texto, deixa o Texto mais lento: o Texto está no caminho crítico e o Socrático não.
- Numa notícia real (40 frases ou mais), os lotes de 15 frases do Texto rodam em fila.

## Decisões do grupo (09/10)

| Pergunta | Decisão |
| --- | --- |
| Sintetizador | LLM com **saída estruturada**: o modelo devolve só JSON `{marcador, efeito}` e o código escreve rótulo e trecho literal |
| LM Studio | Código **e** configuração: decodificação especulativa com modelo rascunho, medida e documentada |
| Qualidade | **Sem gold set**: a correção vem de garantias estruturais (guardrails, saída estruturada) e dos testes |
| Socrático | Recebe um **resumo da notícia** e passa a rodar **depois do Agente de Texto**, em paralelo com a síntese do argumento |

## Novo grafo

```
START → ingestor ─┬─→ agente_evidencias ───────────────────────────┐
                  └─→ agente_texto ─┬─→ agente_argumento (LLM) ─────┼─→ sintetizador (só código) → END
                                    └─→ agente_socratico (LLM) ─────┘
```

- `sintetizador` espera os três predecessores (fan-in com `add_edge([...], "sintetizador")`) e não chama LLM.
- `agente_argumento` escreve as linhas de "Como o texto argumenta" num campo novo do estado: `argument: list[str] | None`, com as linhas da seção sem o título; `None` significa ainda não produzido.
- Caminho crítico esperado: Texto (sozinho no LM Studio) + max(Argumento, Socrático) + montagem.

## Clientes do LLM (`src/services/llm.py`)

| Cliente | temperatura | max_tokens |
| --- | --- | --- |
| `llm_texto` | 0 | 1000 |
| `llm_sintetizador` (argumento) | 0 | 400 |
| `llm_socratico` | 0.2 (era 0.7) | 300 |

- `LLM_DRAFT_MODEL` (variável de ambiente, vazia por padrão): quando definida, toda chamada leva `draft_model=<nome>` no corpo da requisição. É o parâmetro de decodificação especulativa do LM Studio. Vazia, nada é enviado.

## Agente de Texto

- Lotes em paralelo: `TEXTO_PARALELISMO` (variável de ambiente, inteiro ≥ 1, padrão 2). A ordem do resultado é sempre a ordem dos lotes.
- `explanation` com no máximo 10 palavras (regra no prompt; os exemplos few-shot obedecem).

## Argumento estruturado (`agente_argumento`)

- **Entrada do modelo:** até 8 marcadores numerados (`[1] Rótulo | frase: "…" | trecho: "…" | explicação: …`), delimitados como dado.
- **Seleção dos marcadores** (`MAX_MARCADORES_ARGUMENTO = 8`): primeiro um marcador por tipo, na ordem em que cada tipo aparece no texto; depois o restante, na ordem do texto, até completar 8. A exibição segue a ordem do texto.
- **Saída:** JSON `{"efeitos": [{"marcador": <int>, "efeito": "<texto>"}]}`, com `json_schema` estrito. O efeito descreve o efeito do trecho em até 15 palavras e não repete o trecho.
- **Validação por marcador:**
  - índice inexistente ou repetido: ignorado;
  - efeito vazio: reprovado;
  - efeito reprovado no veredito, em link, no G3 ou no G4 (contexto = frases da notícia; `ignorar` = rótulos): reprovado.
- **Retry:** 1, só quando algum efeito foi reprovado (índice inexistente, repetido ou ausente não conta), nomeando o primeiro problema. Depois dele, vale o melhor efeito válido de cada marcador entre as duas tentativas. Marcador sem efeito válido sai sem efeito, e há aviso `WARN_GUARDRAILS` se algum foi reprovado. Falha de chamada: todos saem sem efeito, com `WARN_MODELO_INDISPONIVEL`.
- **Linhas (cópia exata):**
  - Marcador com efeito: `- {Rótulo}: "{trecho}" {efeito}`. Sem efeito: `- {Rótulo}: "{trecho}"`.
  - Trecho por `texto_seguro`; efeito por `escapar_markdown`.
  - Marcadores omitidos: 1 → `- Outro trecho repete esses padrões e não foi listado.`; n ≥ 2 → `- Outros {n} trechos repetem esses padrões e não foram listados.`
  - Juízo de valor (código, sem LLM), uma linha só:
    - 1 → `- Juízo de valor: "A" é uma opinião e não foi checada.`
    - 2 → `- Juízo de valor: "A" e "B" são opiniões e não foram checadas.`
    - n ≥ 3 → `- Juízo de valor: {n} frases são opiniões e não foram checadas, como "A", "B" e mais {n-2}.`
    - Cada frase passa por `encurtar(…, 80)` e depois por `texto_seguro`.
- **Ordem na seção:** linhas dos marcadores, linha de omitidos (se houver), linha de juízo de valor (se houver).
- **Sem `text_report`:** `SEM_ESTRUTURA`. Sem marcadores e sem opinião: `SEM_PADROES`. Nos dois casos, sem chamar o modelo.

## Socrático

- Entrada do modelo (`resumo_para_socratico`):
  - o título, exceto o título padrão de texto colado (`Texto Inserido Manualmente`);
  - as 3 primeiras frases;
  - as frases classificadas como factuais;
  - tudo na ordem do texto, sem repetir, até 400 palavras, cortando em fim de frase.
  - Sem `text_report`, as frases em ordem até o limite.
- Validação G4 das perguntas continua contra a notícia inteira (`clean_text`).

## Correção diante do contexto (sem gold set)

- O trecho citado no argumento é sempre literal: o código escreve, e o modelo só escreve o efeito.
- Todo texto de LLM que vai para o leitor passa por veredito, link, G3 e G4 antes de entrar no dossiê.
- Temperatura baixa nos três agentes.
- `max_tokens` limita o pior caso.

## Medição e aceitação

- `eval/entradas_latencia.json` ganha `noticia_longa`: as entradas `mamao_dengue` e `carrefour_osasco` e as 4 frases de `tests/fixtures/bordas/texto_noticia_desastre.json`, nessa ordem, unidas por espaço; o bloco é repetido 3 vezes (≈ 48 frases).
- `eval/medir_latencia.py` passa a resumir os avisos: execuções com aviso e contagem por prefixo (texto antes do primeiro `:`).
- Linha de base: medida antes de qualquer mudança. Aceitação final, na mesma máquina e com o mesmo modelo:
  - p50 ponta a ponta menor que a linha de base em todas as entradas;
  - `execucoes_com_aviso` não maior que na linha de base.

## Fora do escopo

Gold set e métricas de qualidade, troca do modelo principal, interface web nova.
