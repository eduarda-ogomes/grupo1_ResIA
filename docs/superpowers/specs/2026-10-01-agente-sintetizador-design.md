# Agente Sintetizador — Design

**Data:** 01/10/2026 · **Dono:** R5 · **Revisor cruzado:** R4 · **Sprint:** 2–3 (termina 09/10/2026)
**Manual:** §1.1 (princípios), §3.3 (State), §3.4 (falhas), §3.5 (guardrails), §4.5 (especificação), §4.6 (caso do mamão), §4.7 (casos de borda), §4.8 (decisões de contrato), §7.1 (métricas), §9.3 (objetivos do R5), §10.5 (Definition of Done)

## Objetivo

Juntar os três ramos (Evidências, Texto, Socrático) num **dossiê neutro e citável**, sem veredito. O dossiê mostra o que as checagens dizem, como o texto argumenta, perguntas para o usuário pensar e os limites da análise. A decisão final é do usuário.

## Abordagem: híbrida

O código escreve tudo o que é fato; o LLM escreve só a análise do argumento.

| Seção do dossiê | Quem escreve |
| --- | --- |
| `## O que as checagens dizem` | Código |
| `## Como o texto argumenta` | `qwen2.5-7b` (com fallback em código) |
| `## Perguntas para pensar antes de decidir` | Código (copia as perguntas do Socrático) |
| `## Limites desta análise` | Código |

**Por quê.** Um modelo de 7B copia mal URLs e citações literais. Se o código monta a seção de checagens a partir de `evidence`, a validade de citação (§7.1, meta 1,00) é garantida por construção, o filtro de veredito só precisa olhar o texto que o LLM escreveu, e uma falha do LLM não impede a entrega do dossiê.

Alternativas descartadas: o LLM escrever o dossiê inteiro (com um 7B, URLs quebradas e "citações" parafraseadas seriam frequentes e o caminho de regeneração viraria a regra); template 100% sem LLM (contraria §3.2 e esvazia o experimento da §7.3).

## Contrato

- **Função:** `sintetizador_node(state: PipelineState) -> dict`, em `src/agents/synthesizer.py`. É o nome que o `src/graph.py` registra.
- **Entrada:** `segments`, `evidence`, `text_report`, `socratic_questions`, além de `raw_input`, `truncated` e `published_at` para a seção de limites.
- **Saída:** sempre `{"dossier": str}`. O Sintetizador **nunca devolve `dossier = None`**. Quando o problema é dele mesmo, acrescenta `"warnings": [...]`.
- **Schema:** o `src/state.py` **não muda**. O `src/agents/synthesizer.py` atual (que usa `Dossier` e `state.framing`, inexistentes no schema) é reescrito do zero.

## Decisões

| Tema | Decisão | Por quê |
| --- | --- | --- |
| Modelo | `qwen2.5-7b` no LM Studio (`localhost:1234`), temperatura 0, timeout de 120 s, sem retry do cliente | Mesmo modelo do Agente de Texto: custo zero, sem chave de API no CI e um único modelo carregado na demo (§5.2). Trocar por API depois muda só `src/services/llm.py` |
| Abordagem | Híbrida (tabela acima) | Citação e veredito sob controle do código |
| Saída do LLM | Markdown simples (bullets), sem JSON | Não há estrutura para validar; os guardrails olham o texto |
| Retry | 1, com o problema nomeado na nova mensagem | Manual §3.5 e §4.7 |
| Falha do LLM | Fallback determinístico na seção do argumento + aviso | O dossiê sempre sai (fixture `sintetizador_veredito_vazado`: "entregue sem a seção de síntese livre e com aviso") |
| Veredito da agência | Selo com atribuição montado pelo código (`Agência Lupa: Falso`), fora do texto do LLM | Manual §4.8, item 2 |
| Perguntas socráticas | Copiadas na ordem recebida, sem reordenar | YAGNI; o Manual permite reordenar, não exige |
| IDs de frase | Nunca aparecem no dossiê; a frase é sempre citada pelo texto | O usuário não conhece `s01` |
| Prompt | `src/prompts/sintetizador_sistema.md` | Manual §5.5: prompts versionados em arquivo |

## Como funciona

```text
State ─► 1. Pré-processamento (código, sem LLM)
           - deduplica evidências por (segment_id, source_url)
           - descarta stance de frases que o Agente de Texto marcou como "valor"
           - lista as frases factuais sem nenhuma evidência
        ─► 2. "Como o texto argumenta" (qwen2.5-7b)
           - entrada: frases com a classificação fato/valor + marcadores, delimitados como dado
           - saída: bullets em Markdown
           - guardrails sobre esse texto: filtro de veredito + qualquer URL é inválida
           - reprovou → 1 retry nomeando o problema; reprovou de novo → fallback
        ─► 3. Montagem (código): as 4 seções, na ordem da tabela
        ─► 4. Checagem final de citações sobre o dossiê inteiro
        ─► {"dossier": str, ["warnings": [...]]}
```

### 1. Pré-processamento

- **Deduplicação:** duas evidências com o mesmo `segment_id` e a mesma `source_url` viram uma (fica a primeira).
- **Opinião não é checada (§3.5):** se o Agente de Texto marcou a frase como `valor`, as evidências dela não entram na seção de checagens. Se `text_report is None`, não há como saber, e todas as evidências são exibidas (§4.7).
- **Factuais sem checagem:** frases com `kind == "factual"` sem nenhuma evidência. Só é calculado quando `text_report` existe.

### 2. Seção "Como o texto argumenta"

- O LLM recebe as frases dentro de `<frases>` (com o rótulo `factual` ou `valor`) e os marcadores dentro de `<marcadores>` (tipo, frase, trecho, explicação). O conteúdo da notícia é **dado, nunca instrução** (§3.5, injeção de prompt).
- O LLM **não procura padrões novos**: descreve os que o Agente de Texto já apontou, em 2 a 6 bullets no formato `- Rótulo: "trecho literal" ...`, e menciona as frases de valor como "juízo de valor, não foi checado".
- **Sem chamada ao LLM** quando `text_report is None` ou quando não há marcadores nem frases de valor (ver tabela de casos degradados).

### 3. Montagem

**`## O que as checagens dizem`**, uma linha por frase com evidência:

```text
- "<frase>" — <resumo por stance>.
  <source_name>: <agency_verdict> — "<excerpt>" (<source_url>)      ← uma sublinha por evidência
```

- **Resumo por stance**, por extenso e na ordem contradiz → apoia → insuficiente: "uma checagem contradiz esta frase"; "duas checagens contradizem e uma apoia esta frase"; "uma checagem não é conclusiva sobre esta frase".
- Se `agency_verdict is None`, a sublinha fica sem selo: `<source_name> — "<excerpt>" (<source_url>)`.

Depois, uma linha com as frases factuais sem checagem: "Nenhuma checagem encontrada no nosso banco para: ... Isso não confirma nem descarta essas frases."

**`## Perguntas para pensar antes de decidir`**: lista numerada de `socratic_questions`.

**`## Limites desta análise`**, sempre presente, montada a partir do State:

- "Só o início do texto foi analisado (o texto ultrapassou o limite)." quando `truncated`
- "O texto não tem data de publicação." quando `published_at is None`
- "O texto não tem link de origem." quando `raw_input` não é URL
- uma linha para cada ramo que não rodou (checagens, estrutura, perguntas)
- sempre: "O banco de checagens pode não conter checagens mais recentes que a última coleta."

### 4. Guardrails

**Filtro de veredito** (`src/guardrails/veredito.py`, `termos_de_veredito(texto) -> list[str]`):
- Termos: `falso`, `falsa`, `falsos`, `falsas`, `verdadeiro`, `verdadeira`, `verdadeiros`, `verdadeiras`, `fake news`, `mentira`, `mentiras`, `desinformação`.
- Ignora maiúsculas e acentos (`FALSA` e `desinformacao` são pegos) e respeita a fronteira de palavra (`falsificação` não é pego).
- Aplica-se **só ao texto escrito pelo LLM**. O selo da agência fica fora (§4.8, item 2).
- Limitação conhecida: paráfrases ("não procede", "é enganoso") passam. Há um teste que fixa esse falso negativo (fixture `sintetizador_parafrase`).

**Checagem de citações** (`src/guardrails/citacoes.py`, `urls_invalidas(texto, evidencias) -> list[str]`):
- Extrai as URLs do texto (desconsiderando pontuação final como `)`, `.` e `,`) e devolve as que não estão em `source_url` das evidências recebidas.
- Sobre o texto do LLM: qualquer URL reprova (o LLM não recebe URLs).
- Sobre o dossiê final: rede de segurança contra bug na montagem; a linha com URL inválida é removida (fixture `sintetizador_citacao_inventada`).

## Casos degradados e avisos

Regra geral: **o Sintetizador só grava aviso próprio quando o problema é dele.** Quando um ramo anterior falhou, o aviso já foi gravado por quem falhou; o dossiê declara a ausência em linguagem natural (§3.4: ausência declarada, nunca silêncio).

| Situação no State | Chama o 7B? | O que o dossiê diz | Aviso próprio |
| --- | --- | --- | --- |
| `segments` vazio (paywall, timeout, página JS) | Não | Só a seção "Limites": a página não pôde ser analisada; sugere colar o texto | — |
| `evidence is None` | Normal | Checagens: "Não foi possível consultar o banco de checagens nesta análise." | — |
| `evidence == []` | Normal | Checagens: "Nenhuma checagem encontrada no nosso banco para as frases factuais. Isso não confirma nem descarta essas frases." | — |
| `text_report is None` | Não | Argumento: "Não foi possível analisar a estrutura do texto." Stance exibida para todas as evidências; sem a lista de factuais sem checagem | — |
| `text_report` sem marcadores e sem frases de valor | Não | Argumento: "Nenhum padrão de viés ou falácia foi apontado neste texto." | — |
| `socratic_questions is None` | Normal | Perguntas: "As perguntas não puderam ser geradas nesta análise." | — |
| LM Studio fora do ar ou timeout (120 s) | Sim, sem retry | Fallback determinístico no argumento | `sintetizador: falha ao chamar o modelo (o LM Studio está rodando?)` |
| Texto do 7B reprovado nos guardrails duas vezes | Sim, 1 retry | Fallback determinístico no argumento | `sintetizador: síntese livre reprovada nos guardrails após 1 retry` |
| Checagem final encontra URL fora das evidências | — | A linha com a URL é removida | `sintetizador: citação removida (URL fora das evidências)` |

**Fallback determinístico:** um bullet por marcador, com rótulo do tipo e trecho literal (`- Urgência: "URGENTE"`), mais "Juízo de valor: "<frase>" é uma opinião e não foi checada." para cada frase `valor`. **Não** copia o campo `explanation` do Agente de Texto: ele também é texto de LLM e furaria o filtro de veredito.

Rótulos dos tipos: `adjetivacao_extrema` → Adjetivação extrema; `urgencia_artificial` → Urgência; `apelo_autoridade` → Autoridade sem identificação; `falsa_dicotomia` → Falsa dicotomia; `generalizacao` → Generalização.

## Regras de conteúdo do prompt

- Marcadores são "padrões para observar", nunca acusação.
- Proibido usar os termos do filtro de veredito (a lista vai escrita no prompt).
- Proibido incluir links.
- Sem atribuir intenção, lado político ou beneficiários.
- Saída: só os bullets, sem título nem introdução.
- Um exemplo few-shot no próprio arquivo, com um caso inventado. O caso do mamão **não** entra como exemplo: é o caso de teste.
- Mensagem de retry: nomeia o problema ("Seu texto usou o termo 'falso'." / "Seu texto incluiu um link.") e pede para reescrever.

## Testes

| Onde | O que | Roda no CI? |
| --- | --- | --- |
| `tests/unit/test_guardrails.py` | Filtro (termos, acentos, fronteira de palavra, paráfrase passando); URLs (fixture `citacao_inventada`, pontuação final) | Sim |
| `tests/unit/test_synthesizer.py` | 7B falso que conta chamadas: caso do mamão → 4 seções, 2 URLs, selos, sem IDs; cada linha da tabela de casos degradados; retry; fallback; modelo fora do ar | Sim |
| `tests/contract/` | Nó real com o 7B falso; saída mesclada e validada no `PipelineState` | Sim |
| `tests/integration/test_sintetizador_lmstudio.py` | Caso do mamão no 7B real: passa nos dois guardrails e tem as 4 seções (sem comparar texto exato) | Não; pulado com o LM Studio desligado |

O `tests/unit/conftest.py`, que impede testes unitários de chamarem o LM Studio, também é criado pelo plano do Agente de Texto. Quem chegar primeiro cria; o outro reaproveita.

## Fora do escopo

Sintetizador via API ou 14B local (§4.5, §5.2); reordenar as perguntas socráticas; LLM-as-judge e medição de vazamento de veredito no gold set (§7); timeout por nó no grafo (orquestrador); mudanças na interface Streamlit (`st.write(dossier)` já renderiza Markdown).
