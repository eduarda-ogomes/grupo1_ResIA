# Agente Sintetizador

**Dono:** R5 · **Revisor cruzado:** R4 · **Design:** [`docs/superpowers/specs/2026-10-01-agente-sintetizador-design.md`](../superpowers/specs/2026-10-01-agente-sintetizador-design.md) · **Manual:** §4.5 e §4.5.1

## O que faz

Junta os ramos (Evidências, Texto, Socrático) num dossiê em Markdown, sem veredito. A decisão final é do usuário.

São dois nós em `src/agents/synthesizer.py`:

- **`agente_argumento`** (`argumento_node`) roda depois do Agente de Texto, em paralelo com o Socrático. Escreve as linhas de "Como o texto argumenta" (sem o título) em `state.argument`, com o `qwen2.5-7b`.
- **`sintetizador`** (`sintetizador_node`) só monta o dossiê, sem LLM. Espera Evidências, `agente_argumento` e Socrático (fan-in: roda uma vez só).

```
ingestor ─┬─→ agente_evidencias ──────────────────────┐
          └─→ agente_texto ─┬─→ agente_argumento ─────┼─→ sintetizador → END
                            └─→ agente_socratico ─────┘
```

Seis seções, nesta ordem (pirâmide invertida: o tamanho do problema primeiro, as referências por último). Texto exato, regras de singular/plural e casos degradados: [`docs/superpowers/specs/2026-10-08-dossie-final-design.md`](../superpowers/specs/2026-10-08-dossie-final-design.md).

| # | Seção | Quem escreve | Arquivo |
| --- | --- | --- | --- |
| 1 | `## Resumo` | Código, só contagens | `src/agents/dossie.py` |
| 2 | `## O que as checagens dizem` | Código, com legenda e referências numeradas | `src/agents/dossie.py` |
| 3 | `## Como o texto argumenta` | `agente_argumento` (`qwen2.5-7b`), com fallback em código (o efeito passa por `escapar_markdown` e o trecho por `texto_seguro`, depois dos guardrails); o `sintetizador` põe o título e as linhas de `state.argument` | `src/agents/synthesizer.py` |
| 4 | `## Perguntas para pensar antes de decidir` | Código (copia o Socrático, com Markdown escapado) | `src/agents/dossie.py` |
| 5 | `## Limites desta análise` | Código, sempre presente | `src/agents/dossie.py` |
| 6 | `## Fontes` | Código; só aparece quando há evidência | `src/agents/dossie.py` |

## Contrato

- `argumento_node(state) -> {"argument": list[str]}`, mais `"warnings"` só quando o problema é do próprio nó (modelo fora do ar ou reprovado nos guardrails). Sem `text_report`, ou sem marcadores e sem opinião, não chama o modelo.
- `argumento_fallback(state) -> {"argument": list[str]}`: as linhas do fallback em código, sem LLM. O grafo o usa quando o `agente_argumento` estoura o tempo.
- `sintetizador_node(state) -> {"dossier": str}`: nunca chama o LLM e nunca devolve `dossier = None`. Usa `state.argument` ou, se for `None`, `argumento_fallback`. Só acrescenta `"warnings"` se a rede de segurança das citações remover uma linha.

## Guardrails (`src/guardrails/`)

- **Veredito** (`veredito.py`): `falso/a/os/as`, `verdadeiro/a/os/as`, `fake news`, `mentira(s)`, `desinformação`, sem distinguir maiúsculas nem acentos e respeitando a fronteira de palavra. Vale só para o texto do LLM; o selo `Agência Lupa: Falso` é montado pelo código. Paráfrases ("não procede") passam: é um falso negativo conhecido.
- **Citações** (`citacoes.py`): no texto do LLM, qualquer URL reprova. No dossiê final, a linha com URL fora das evidências é removida, com aviso.

Reprovou: 1 retry, nomeando o problema. Reprovou de novo, ou o LM Studio está fora do ar: fallback com rótulo e trecho literal de cada marcador, mais aviso.

## Avisos próprios

Do `agente_argumento`:

- `sintetizador: falha ao chamar o modelo (o LM Studio está rodando?)`
- `sintetizador: efeito do argumento reprovado nos guardrails após 1 retry`
- `sintetizador: saída inválida após 1 retry` (a saída estruturada do modelo não bateu com o schema)

Do `sintetizador` (montagem):

- `sintetizador: citação removida (URL fora das evidências)`

Ramo anterior que falhou não gera aviso do Sintetizador: o dossiê declara a ausência ("Não foi possível consultar o banco de checagens nesta análise.").

## Como testar

    pytest tests/unit/test_guardrails.py tests/unit/test_dossie.py tests/unit/test_synthesizer.py tests/contract/test_synthesizer_contract.py
    pytest tests/integration/test_sintetizador_lmstudio.py -v -s     # com o LM Studio ligado

## Limitações conhecidas

- O filtro por lista não pega paráfrases de veredito.
- Links que vêm da notícia (frases e trechos de marcador e de checagem) aparecem como `[link]`: nunca viram citação no dossiê nem chegam ao LLM.
- Se o grafo corta o `agente_argumento` por tempo, `argumento_fallback` preenche `state.argument` e o `sintetizador` entrega o dossiê com a seção em fallback (aviso `argumento: timeout`).
- As perguntas socráticas não são reordenadas.
