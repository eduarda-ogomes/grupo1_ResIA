# Card — Agente de Texto

**Dono:** R3 · **Revisor cruzado:** R2 · **Código:** `src/agents/text_analysis.py` · **Prompts:** `src/prompts/texto_*`

## O que faz
Classifica cada frase como `factual` ou `valor` e aponta trechos com padrões de viés, emoção ou falácia (`adjetivacao_extrema`, `urgencia_artificial`, `apelo_autoridade`, `falsa_dicotomia`, `generalizacao`). Não julga se o texto é verdadeiro.

## Entrada e saída
- Entrada: `state.segments`.
- Saída: `{"text_report": TextReport}`; em falha, `{"text_report": None, "warnings": [...]}`.

## Modelo
`qwen2.5-7b` (LM Studio, `localhost:1234`), temperatura 0, JSON Schema do `TextReport`, lotes de 15 frases com 2 de contexto, 1 retry por lote.

## Resultados (caso do mamão, 2026-10-01)
- `kind` igual à anotação: 6/6
- Marcadores pertinentes: 3/6
- Tempo do agente: 25.00s

## Limitações conhecidas
- Ironia e sátira não são tratadas.
- Pode confundir estilo editorial legítimo com manipulação: os marcadores são padrões para observar, não acusações.
- Frases imperativas são classificadas como `valor` (Manual §4.8).
- Se qualquer lote falhar após o retry, o relatório inteiro é descartado (tudo ou nada).
- Métricas medidas em um único caso; o macro-F1 oficial depende do gold set (Manual §6.2).
