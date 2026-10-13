# Desempenho dos agentes com LLM

Medições de 09/10/2026 com `qwen/qwen2.5-vl-7b` (Q4_K_M, LM Studio local, contexto 8192, 4 previsões em paralelo), 2 repetições por entrada, via `eval/medir_latencia.py`. Com n=2, p50 e p95 são interpolados entre as duas execuções (o p50 é a média das duas); trate diferenças de 1 a 2 s como ruído. Arquivos: `eval/resultados/latencia_2026-10-09_{base,final,rascunho}.json`.

- **base:** código antes das mudanças.
- **final:** código otimizado, sem decodificação especulativa.
- **rascunho:** código otimizado + `qwen2.5-0.5b-instruct` (GGUF Q8_0) como modelo rascunho.

## Tempo ponta a ponta, em segundos

| entrada | base p50 | base p95 | final p50 | final p95 | rascunho p50 | rascunho p95 |
| --- | --- | --- | --- | --- | --- | --- |
| mamao_dengue | 26,9 | 26,9 | 26,3 | 26,4 | 29,8 | 30,1 |
| carrefour_osasco | 42,5 | 43,6 | 36,6 | 37,7 | 37,4 | 38,3 |
| noticia_longa | 173,8 | 180,8 | 134,1 | 136,6 | 148,6 | 153,4 |

Avisos (`execucoes_com_aviso`): 0 nas três medições. O p50 do conjunto passou de 41,4 s (base) para 35,3 s (final), e o p95 de 181,5 s para 136,8 s; a meta do Manual (p50 abaixo de 3 min) é cumprida em todas as entradas.

## Por nó, p50 em segundos (base, final, rascunho)

| nó | mamao_dengue | carrefour_osasco | noticia_longa |
| --- | --- | --- | --- |
| ingestor | 0,0 / 0,0 / 0,0 | 0,0 / 0,0 / 0,0 | 0,1 / 0,1 / 0,1 |
| agente_evidencias | 0,5 / 0,3 / 0,4 | 1,1 / 0,6 / 0,6 | 5,6 / 7,0 / 5,9 |
| agente_texto | 19,6 / 17,6 / 15,1 | 27,9 / 25,1 / 21,3 | 142,9 / 112,2 / 122,2 |
| agente_argumento (novo) | - / 8,6 / 12,2 | - / 11,5 / 16,2 | - / 21,8 / 26,4 |
| agente_socratico | 7,0 / 7,6 / 14,7 | 9,7 / 8,7 / 16,2 | 16,0 / 15,0 / 20,0 |
| sintetizador | 7,3 / 0,0 / 0,0 | 14,6 / 0,0 / 0,0 | 30,9 / 0,0 / 0,0 |

O `sintetizador` agora é só código (marca ~0 s). O trabalho de LLM que ele fazia passou para o nó `agente_argumento`, então a linha `sintetizador` da base não é comparável com a da medição final: compare a base `sintetizador` com `agente_argumento` e o total.

## O que mudou e por quê

O tempo era dominado pelos tokens gerados, e o LM Studio local dá ~19 tokens/s; duas chamadas simultâneas ficam ~45% mais lentas cada. Spec e decisões: `docs/superpowers/specs/2026-10-09-desempenho-agentes-design.md`. Em resumo:

- **Argumento com saída estruturada.** O modelo devolve só JSON `{marcador, efeito}`; o rótulo e o trecho literal são escritos pelo código. Menos tokens gerados, e a saída deixa de ser texto livre (os guardrails seguem valendo). O nó novo `agente_argumento` faz essa chamada.
- **Sintetizador só código.** Monta o dossiê a partir de `state.argument` e dos outros campos; se o argumento não chegar, usa o fallback em código.
- **Agente de Texto em lotes paralelos, com explicações curtas** (`TEXTO_PARALELISMO`). Foi o maior ganho em notícia longa (142,9 s para 112,2 s).
- **Novo grafo:** Ingestor, depois Evidências e Texto em paralelo; depois do Texto, `agente_argumento` e Socrático em paralelo (o Socrático recebe um resumo da notícia); o Sintetizador espera Evidências, Argumento e Socrático.
- **Correções de robustez medidas junto:** vocabulário de nomes carrega uma só vez com threads em paralelo; o Argumento tira a cerca de JSON e trata resposta ilegível com retry e aviso.

## Decodificação especulativa

- O LM Studio recusa `draft_model` na requisição: `Engine protocol speculativeDecoding capability gap: Engine protocol speculative decoding must be configured at load time, not prediction time.` Por isso a variável `LLM_DRAFT_MODEL`, que mandava `draft_model` em cada chamada, foi removida do código: com ela definida, toda chamada ao LLM falhava.
- Para medir, o rascunho foi configurado ao carregar o modelo (`lms load qwen/qwen2.5-vl-7b --identifier qwen-vl-7b-draft --speculative-draft-simple --speculative-draft-model qwen2.5-0.5b-instruct -c 8192 --parallel 4`) e `LLM_MODEL=qwen-vl-7b-draft` foi usado. O LM Studio aceitou o par (vocabulário compatível, ambos GGUF) e devolveu `draft_model` na resposta.
- Resultado: **sem ganho no total** (mamao_dengue +3,5 s, carrefour_osasco +0,8 s, noticia_longa +14,5 s sobre o final). O Agente de Texto, que roda sozinho no LM Studio, ficou mais rápido (-2,5 s, -3,8 s) em duas entradas e mais lento na longa (+10 s); o Argumento e o Socrático, que rodam ao mesmo tempo, ficaram mais lentos (ex.: Socrático 7,6 s para 14,7 s). Com chamadas concorrentes, o rascunho disputa a mesma memória e o ganho some.
- Ressalvas: n=2; a medição com rascunho usou uma segunda instância do modelo carregada ao lado da primeira (24 GB de RAM), o que pode ter pesado. Os testes de integração passam igual com o rascunho (4 passed, 2 skipped), como esperado: o resultado da geração gulosa não muda.

## Recomendação para quem roda localmente

- **Modelo rascunho: não use.** Não ajudou o pipeline, que roda chamadas em paralelo, e só funciona configurado no carregamento do modelo (a variável `LLM_DRAFT_MODEL` foi removida). Se quiser testar na sua máquina, carregue o modelo com o rascunho (comando acima), aponte `LLM_MODEL` para o identificador dele e meça com `eval/medir_latencia.py`.
- **`TEXTO_PARALELISMO`: mantenha o padrão (2).** Todas as medições "final" e "rascunho" usaram 2. Não foi medido outro valor; valores maiores só ajudam se o LM Studio estiver com previsões em paralelo suficientes (`--parallel`), e a geração concorrente deixa cada chamada mais lenta, então 2 é o ponto de partida seguro.

## O que ainda domina

O Agente de Texto em notícia longa: 112,2 s de 134,1 s (84%) no `noticia_longa`, no caminho crítico, sozinho. Próximas alavancas, em ordem: reduzir tokens gerados por lote (o JSON de saída), lotes menores ou maiores conforme o tamanho da notícia, e um modelo mais rápido ou quantização menor para esse agente. A medição de `TEXTO_PARALELISMO` entre 1 e 4 na notícia longa ainda está por fazer.
