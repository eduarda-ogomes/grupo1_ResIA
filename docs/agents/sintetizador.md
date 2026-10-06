# Agente Sintetizador

**Dono:** R5 · **Revisor cruzado:** R4 · **Design:** [`docs/superpowers/specs/2026-10-01-agente-sintetizador-design.md`](../superpowers/specs/2026-10-01-agente-sintetizador-design.md) · **Manual:** §4.5 e §4.5.1

## O que faz

Junta os três ramos (Evidências, Texto, Socrático) num dossiê em Markdown, sem veredito. A decisão final é do usuário.

| Seção | Quem escreve | Arquivo |
| --- | --- | --- |
| `## O que as checagens dizem` | Código | `src/agents/dossie.py` |
| `## Como o texto argumenta` | `qwen2.5-7b`, com fallback em código | `src/agents/synthesizer.py` |
| `## Perguntas para pensar antes de decidir` | Código (copia o Socrático) | `src/agents/dossie.py` |
| `## Limites desta análise` | Código, sempre presente | `src/agents/dossie.py` |

## Contrato

`sintetizador_node(state) -> {"dossier": str}`, mais `"warnings"` só quando o problema é do próprio Sintetizador. Nunca devolve `dossier = None`.

## Guardrails (`src/guardrails/`)

- **Veredito** (`veredito.py`): `falso/a/os/as`, `verdadeiro/a/os/as`, `fake news`, `mentira(s)`, `desinformação`, sem distinguir maiúsculas nem acentos e respeitando a fronteira de palavra. Vale só para o texto do LLM; o selo `Agência Lupa: Falso` é montado pelo código. Paráfrases ("não procede") passam: é um falso negativo conhecido.
- **Citações** (`citacoes.py`): no texto do LLM, qualquer URL reprova. No dossiê final, a linha com URL fora das evidências é removida, com aviso.

Reprovou: 1 retry, nomeando o problema. Reprovou de novo, ou o LM Studio está fora do ar: fallback com rótulo e trecho literal de cada marcador, mais aviso.

## Avisos próprios

- `sintetizador: falha ao chamar o modelo (o LM Studio está rodando?)`
- `sintetizador: síntese livre reprovada nos guardrails após 1 retry`
- `sintetizador: citação removida (URL fora das evidências)`

Ramo anterior que falhou não gera aviso do Sintetizador: o dossiê declara a ausência ("Não foi possível consultar o banco de checagens nesta análise.").

## Como testar

    pytest tests/unit/test_guardrails.py tests/unit/test_dossie.py tests/unit/test_synthesizer.py tests/contract/test_synthesizer_contract.py
    pytest tests/integration/test_sintetizador_lmstudio.py -v -s     # com o LM Studio ligado

## Limitações conhecidas

- O filtro por lista não pega paráfrases de veredito.
- Links que vêm da notícia (frases e trechos de marcador e de checagem) aparecem como `[link]`: nunca viram citação no dossiê nem chegam ao LLM.
- Se o grafo corta o Sintetizador por tempo, `dossie_sem_modelo` entrega o dossiê com a seção do argumento em fallback (aviso `sintetizador: timeout`).
- As perguntas socráticas não são reordenadas.
