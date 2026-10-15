# Agentes em paralelo: design

Data: 15/10/2026. Branch: `feat/texto-desastres-e-paralelismo`, a partir da `develop` (5208a2b).

## Objetivo

Voltar ao grafo do Manual (§1.2): depois do Ingestor, Evidências, Texto e Socrático rodam em paralelo e o Sintetizador junta os três. O Socrático não espera mais o Texto. O nó `agente_argumento`, criado em 09/10 (`docs/superpowers/specs/2026-10-09-desempenho-agentes-design.md`), é mesclado ao Agente de Texto. O dossiê sai igual ao de hoje.

## Grafo

```
START → ingestor ─┬→ agente_evidencias ─┐
                  ├→ agente_texto ──────┼→ sintetizador → END
                  └→ agente_socratico ──┘
```

- `ORDEM_NOS = ("ingestor", "agente_evidencias", "agente_texto", "agente_socratico", "sintetizador")`.
- `PREDECESSORES`: os três ramos dependem do `ingestor`; o `sintetizador`, dos três ramos.
- Os três ramos usam `GRAFO_TIMEOUT_RAMO` (240 s); o Sintetizador, `GRAFO_TIMEOUT_SINTETIZADOR` (180 s). Os três ramos estão no mesmo superstep: a "barreira do superstep" de `docs/agents/desempenho.md` deixa de existir.

## Agente de Texto com o argumento

- O código do efeito dos marcadores sai de `src/agents/synthesizer/agent.py` para `src/agents/argumento.py`: montagem das mensagens, chamada ao LLM, guardrails, retry e `argumento_node(state) -> {"argument": list[str], "warnings"?: [...]}`. Continua usando `llm_sintetizador` e `src/prompts/sintetizador_sistema.md` (nomes mantidos para não conflitar com as branches de deploy, que mexem em `src/services/llm.py`); os avisos continuam com o prefixo `sintetizador:`.
- `texto_node(state)` classifica as frases como hoje e, quando há `text_report`, chama `argumento_node` com o estado já classificado. Devolve `text_report`, `argument` e os avisos dos dois passos, nessa ordem.
- Sem `text_report` (nenhuma frase classificada), `argument` não é preenchido; o Sintetizador usa o fallback em código, que escreve "Não foi possível analisar a estrutura do texto."
- Saída de falha do nó `agente_texto` no `proteger`: `{"text_report": None, "argument": None}`.
- O Sintetizador fica só código: `sintetizador_node` e `argumento_fallback` ficam em `synthesizer/agent.py`; nenhum import de LLM sobra nele.

## Socrático

Recebe o estado logo depois do Ingestor, então `text_report` é sempre `None` quando ele roda. `resumo_para_socratico` passa a ser: título (exceto o título padrão de texto colado) e as frases em ordem até 400 palavras, com o mesmo corte de hoje. O ramo que escolhia as frases factuais sai.

## Interface e medição

- `src/pipeline/progresso.py`: um nó por personagem; `NOS_DO_AGENTE` some.
- `app/sala/sala.js`: o Ingestor entrega a matéria aos três ramos; some a passagem do Texto para o Socrático.
- `src/pipeline/medicao.py` não muda: deriva tudo de `ORDEM_NOS` e `PREDECESSORES`.

## Trade-off aceito

Antes, um timeout só do argumento caía no fallback e a classificação sobrevivia. Agora, se o nó do Texto inteiro estoura os 240 s, `text_report` e `argument` ficam `None`. Medido em 09/10, a notícia longa leva ~112 s no Texto e ~22 s no argumento, dentro do limite.

## Verificação

- Suíte completa; testes de integração do Texto, do Sintetizador e do grafo com o LM Studio.
- Latência com `eval/medir_latencia.py --repeticoes 2 --aquecimento 1` antes e depois, nas 3 entradas de `eval/entradas_latencia.json`.
- Documentação: README, `docs/agents/{desempenho,sintetizador,socratico,texto}.md`, docstrings do grafo e do progresso.
