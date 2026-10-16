# Card — Agente de Texto

**Dono:** R3 · **Revisor cruzado:** R2 · **Código:** `src/agents/text_analysis.py`, `src/agents/argumento.py` · **Prompts:** `src/prompts/texto_*`

## O que faz
Classifica cada frase como `factual` ou `valor` e aponta trechos com padrões de viés, emoção ou falácia (`adjetivacao_extrema`, `urgencia_artificial`, `apelo_autoridade`, `falsa_dicotomia`, `generalizacao`). Não julga se o texto é verdadeiro.

Depois de classificar, escreve o efeito de cada marcador para a seção "Como o texto argumenta" do dossiê (`argumento_node`, em `src/agents/argumento.py`; guardrails, retry e fallback em [`sintetizador.md`](sintetizador.md)). Até 15/10 esse passo era um nó próprio do grafo, o `agente_argumento`. Roda em paralelo com Evidências e Socrático, logo depois do Ingestor.

Em notícias de desastres e acidentes, a intensidade que descreve o evento ("temporal violento", "a maior cheia já registrada") não é marcador; o adjetivo que julga pessoas ou instituições ("prefeito irresponsável") é. Isso vem do exemplo few-shot de desastre (15/10), não de uma regra no prompt: três redações de regra apagaram marcadores de texto alarmista.

## Entrada e saída
- Entrada: `state.segments`.
- Saída: `{"text_report": TextReport, "argument": list[str]}`. Se algumas frases ficarem sem classificação depois do retry, o relatório traz o que foi classificado e um aviso com o ID e o começo de cada frase que ficou de fora (`texto: 2 frases sem classificação (as demais foram analisadas): s22 "…"; s24 "…"`); o dossiê lista essas frases por extenso em "Limites desta análise". Só quando nenhuma frase é classificada: `{"text_report": None, "warnings": [...]}`, sem `argument` (o Sintetizador usa o fallback). Os avisos do argumento vêm depois dos da classificação.

## Modelo
`qwen2.5-7b` (LM Studio, `localhost:1234`), temperatura 0, JSON Schema do `TextReport`, lotes de 15 frases com 2 de contexto, 1 retry por lote.

## Resultados (caso do mamão, 2026-10-01)
- `kind` igual à anotação: 6/6
- Marcadores pertinentes: 3/6
- Tempo do agente: 25.00s

## Desastres (2026-10-15, `qwen2.5-vl-7b`)
- 10 frases de desastres e acidentes sem repetir expressões do prompt (`tests/fixtures/bordas/texto_desastres_variados.json`): frases de contexto com marcador caíram de 8 para 1 ("terremoto brutal").
- "As autoridades incompetentes não fizeram nada…" sai como adjetivação ou generalização, conforme a sessão do LM Studio; antes saía como urgência artificial.
- Texto alarmista do mamão: os 4 marcadores de antes continuam (`test_texto_alarmista_mantem_os_marcadores`).

## Limitações conhecidas
- Ironia e sátira não são tratadas.
- Pode confundir estilo editorial legítimo com manipulação: os marcadores são padrões para observar, não acusações.
- Frases imperativas são classificadas como `valor` (Manual §4.8).
- Falha por lote (decisão do grupo em 06/10, depois de testes com o 7B real, que pula frases em lotes grandes): fica a tentativa que classificou mais frases, e as que faltaram aparecem no aviso. Uma frase sem classificação não entra em "factuais sem checagem" nem tem a stance descartada como opinião.
- Métricas medidas em um único caso; o macro-F1 oficial depende do gold set (Manual §6.2).
