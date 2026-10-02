# Agente de Evidências

Dono: R2 (Túlio Celeri) · Branch: `AgenteEvidencias` · Atualizado em 01/10/2026
Decisões e números: [`evidencias_decisoes.md`](evidencias_decisoes.md)

## O que faz

Para cada frase da notícia, procura **checagens já publicadas sobre a mesma alegação** e devolve o que a agência concluiu, com o link. Não usa LLM: busca por embeddings num índice ChromaDB e um modelo de NLI.

## Entrada e saída

Lê só `state.segments`. Devolve um dict com os campos de `Evidence` da Seção 3.3:

```python
run(state) -> {"evidence": [
    {"segment_id": "s01", "stance": "contradiz",
     "excerpt": "Imagem de Fachin apontando dedo para Moraes é falsa e criada por IA",
     "source_url": "https://noticias.uol.com.br/...", "source_name": "UOL Notícias",
     "agency_verdict": "Falso"}]}
```

| Saída | Significado |
| --- | --- |
| `{"evidence": [..]}` | Busca feita; a lista pode ser vazia (nenhuma checagem sobre aquelas frases) |
| `{"evidence": None, "warnings": ["evidencias: ..."]}` | O agente falhou (índice ausente, modelo que não carrega); degradação graciosa, Seção 3.4 |

`stance`: `contradiz` (agência disse falso), `apoia` (verdadeiro) ou `insuficiente` (enganoso, falta contexto etc.). Frase sem checagem não gera objeto.

## Fluxo, por frase

```text
frase ─► 1. busca: 10 trechos mais parecidos (similaridade ≥ 0,55), agrupados por checagem;
            até 6 checagens; mesma checagem em 2 sites conta 1 (fica o original, não o espelho do BOL)
      ─► 2. termos-chave: a frase troca um nome, número ou doença da alegação checada? → descarta
      ─► 3. NLI: frase e alegação (sem "Foto/Vídeo mostra") se implicam em alguma direção (≥ 0,5)?
      ─► 4. evidência: stance = veredito da agência; excerpt = título da checagem; até 3 por frase
```

## Arquivos

| Arquivo | O que tem |
| --- | --- |
| `src/agents/evidence.py` | O agente: os 4 passos acima e `run(state)` |
| `src/retrieval/config.py` | Limiares, modelos e caminhos (variáveis de ambiente) |
| `src/retrieval/indice.py` | ChromaDB e embeddings: coleção, busca, trechos de uma checagem |
| `src/retrieval/nli.py` | Modelo de NLI (mDeBERTa) |
| `src/retrieval/etapa2.py` | "Mesma alegação": normalização da alegação, termos-chave, veredito → stance |
| `src/stubs/evidence_stub.py` | Stub para os outros agentes testarem sem modelos: devolve a fixture `02_evidencias_saida.json` (Seção 4.6) |
| `data/corpus/` | Coleta (`collect_factcheck_api.py`), download (`fetch_articles.py`), índice (`build_index.py`), diagnóstico e experimento |
| `eval/avaliar_evidencias.py` | Avaliação: `sortear`, `validar` e `avaliar` (Recall@5, stance, evidência inventada); ver [Avaliação](#avaliação) |
| `data/gold/evidencias.json` | Conjunto de avaliação (parte de evidências do gold set) |
| `eval/resultados/` | Resultado de cada rodada do `avaliar --salvar`, versionado para o relatório |
| `tests/` | Unitários (sem modelos), contrato e integração (modelos reais) |

## Como rodar

Sempre a partir da raiz do repositório, com o ambiente virtual ativado. Os comandos `python` são iguais nos dois sistemas; muda só a ativação do ambiente e a forma de definir variáveis de ambiente.

**Windows (PowerShell)**

```powershell
venv\Scripts\Activate.ps1                                # ativa o ambiente virtual

python -m pytest tests                                   # testes rápidos, sem modelos

$env:FACTCHECK_API_KEY = "sua-chave"                     # corpus (retomável)
python data/corpus/collect_factcheck_api.py
python data/corpus/fetch_articles.py
python data/corpus/build_index.py --reset

python data/corpus/diagnostico.py --frases "Fachin apontou o dedo para Moraes no STF."
python data/corpus/experimento_etapa2.py                 # etapa 2 nos 37 pares (NLI real)

$env:EVIDENCE_INTEGRATION = "1"                          # testes com os modelos reais
python -m pytest tests/integration -v -s
```

**macOS (Terminal, zsh)**

```bash
source venv/bin/activate                                 # ativa o ambiente virtual

python -m pytest tests                                   # testes rápidos, sem modelos

export FACTCHECK_API_KEY="sua-chave"                     # corpus (retomável)
python data/corpus/collect_factcheck_api.py
python data/corpus/fetch_articles.py
python data/corpus/build_index.py --reset

python data/corpus/diagnostico.py --frases "Fachin apontou o dedo para Moraes no STF."
python data/corpus/experimento_etapa2.py                 # etapa 2 nos 37 pares (NLI real)

export EVIDENCE_INTEGRATION=1                            # testes com os modelos reais
python -m pytest tests/integration -v -s
```

**Avaliação** (os comandos são iguais nos dois sistemas)

```bash
python eval/avaliar_evidencias.py sortear --n 30                        # checagens para parafrasear
python eval/avaliar_evidencias.py sortear --n 10 --veredito verdadeiro
python eval/avaliar_evidencias.py sortear --n 5 --agencia AFP
python eval/avaliar_evidencias.py esqueleto                             # 12 entradas com as checagens e as frases em branco
python eval/avaliar_evidencias.py completar                             # monta o texto das entradas a partir das frases
python eval/avaliar_evidencias.py validar                               # confere data/gold/evidencias.json
python eval/avaliar_evidencias.py avaliar --split todos --salvar        # índice e modelos reais
```

A variável vale só para a janela do terminal em que foi definida. Fora do ambiente virtual, no macOS, use `python3` no lugar de `python`. No Mac com Apple Silicon, o agente usa a GPU (`mps`) automaticamente.

## Configuração

| Variável | Padrão | Uso |
| --- | --- | --- |
| `EVIDENCE_SIM_THRESHOLD` | `0.55` | Similaridade mínima na busca (provisório) |
| `EVIDENCE_CLAIM_MATCH_MIN_PROB` | `0.5` | Entailment mínimo da etapa 2 (provisório) |
| `EVIDENCE_SEARCH_K` / `EVIDENCE_CLAIM_CANDIDATES` / `EVIDENCE_MAX_PER_SEGMENT` | `10` / `6` / `3` | Trechos buscados / checagens avaliadas / evidências por frase |
| `EVIDENCE_EMBEDDING_MODEL` / `EVIDENCE_NLI_MODEL` | `BAAI/bge-m3` / `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` | Modelos |
| `EVIDENCE_DEVICE` | automático | `cuda` → `mps` → `cpu` |
| `EVIDENCE_CHROMA_PATH` / `EVIDENCE_RAW_DIR` | `chroma_data/` / `data/corpus/raw/` | Caminhos (fora do Git) |

## Limitações conhecidas

- Só acha o que está no corpus (5.826 checagens de 24 meses; sem Lupa). Checagens da AFP entram só pelo título.
- Frases que **desmentem** o boato ("a foto é falsa") ficam sem evidência.
- Paráfrases muito diferentes da alegação podem ser perdidas (ex.: "com dedo em riste", NLI 0,07). O agente prefere perder a citar a checagem errada.
- `apoia` é raro: das 5.826 checagens, 36 viram `apoia`, e 21 delas são guias do Comprova ("Como funciona o golpe do SMS"), não alegações. Uma ("Não é Moraes no avião de Vorcaro", Comprovado) daria a stance invertida, porque o comprovado é que a imagem é real.
- Termos-chave dependem de maiúsculas corretas; limiares ainda não calibrados no gold set.

## Avaliação

Mede as três métricas da Seção 7.1 sem esperar o harness do R3. Definições e motivos no ADR 3 de [`evidencias_decisoes.md`](evidencias_decisoes.md).

### Conjunto: `data/gold/evidencias.json`

12 entradas (~36 frases). Cada entrada é um texto curto de notícia; cada frase tem tipo, URLs aceitas e stance esperada. Quando o R3 definir o formato do gold set, um conversor leva os dados para lá.

```json
{"versao": 1, "entradas": [{
  "id": "ev01", "split": "teste", "anotador": "R2", "revisor": null,
  "texto": "Texto completo da notícia, como o Ingestor receberia.",
  "frases": [
    {"id": "s01", "texto": "Frase parafraseada que afirma o boato.", "tipo": "com_checagem",
     "checagens_aceitas": ["https://www.aosfatos.org/noticias/...", "https://checamos.afp.com/..."],
     "stance_esperada": "contradiz", "alegacao_original": "claim_reviewed de onde veio a paráfrase", "obs": ""},
    {"id": "s02", "texto": "Frase sobre um fato que não foi checado.", "tipo": "sem_checagem",
     "checagens_aceitas": [], "stance_esperada": null}]}]}
```

| Tipo | Frases | `checagens_aceitas` | `stance_esperada` |
| --- | --- | --- | --- |
| `com_checagem` | ~20 (≈12 falso, ≈4 enganoso etc., ≥ 2 verdadeiro, ≈2 da AFP) | Todas as URLs da mesma alegação (espelho UOL/BOL, outras agências) | Pelo veredito: falso → `contradiz`, verdadeiro → `apoia`, o resto → `insuficiente` |
| `sem_checagem` | ~10 | vazia | `null` |
| `fato_parecido` / `troca_numero` | ~4 | vazia (qualquer evidência é casamento errado) | `null` |
| `desmente` ("a foto é falsa") | ~2 | a checagem do boato | `apoia` (a checagem apoia a frase) |

**Como preencher.** O comando `esqueleto` já distribuiu as checagens pelas 12 entradas, seguindo a tabela acima e alternando os splits. Ele preencheu, em cada frase, o tipo, as URLs (com os espelhos BOL/Acervo), a stance pelo veredito e a `alegacao_original`. Também deixou, como apoio, o veredito da agência (`_veredito`), a checagem de origem das trocas (`_base`) e uma instrução (`_instrucao`). Só usa checagens que são alegações concretas: descarta guias explicativos, alegações negativas, perguntas, links, textos longos, espelhos e as checagens dos 37 pares. Para cada frase:

1. Escreva o `texto` seguindo a `_instrucao` (lendo só a `alegacao_original`, sem abrir o título).
2. Junte todas as frases num arquivo e rode o `diagnostico.py --arquivo` uma vez; acrescente em `checagens_aceitas` as outras URLs da mesma alegação e confirme que as `sem_checagem` não têm checagem.
3. Se uma checagem sorteada não servir, troque-a à mão por outra do `sortear` (URL, `alegacao_original`, `stance_esperada`, `_veredito`).
4. Rode `completar` (monta o `texto` de cada entrada e apaga as `_instrucao` das frases escritas) e depois `validar`.

Os campos que começam com `_` são só de apoio: o `avaliar` e o `validar` os ignoram. O `esqueleto` não sobrescreve um arquivo que já tem entradas, a menos que receba `--forcar`.

Regras de anotação:

1. **Parafrasear, nunca copiar** (Seção 6.2). Mantenha nomes, números e lugares; mude palavras e ordem.
2. **Não usar as checagens dos 37 pares** (`data/corpus/pares_etapa2.json`): as regras foram ajustadas neles. O `sortear` já as exclui.
3. **`sem_checagem`**: frases plausíveis e do mesmo universo de temas (saúde, política, STF). Confirme com `diagnostico.py --frases` que nada no corpus checa aquilo.
4. **`fato_parecido`**: uma checagem real com um termo trocado (doença, nome, número); preencha `alegacao_original`. O caso do mamão (Lupa) não serve: não há checagem de mamão/dengue no corpus.
5. **URLs aceitas**: rode `diagnostico.py --frases "<paráfrase>"` e inclua as checagens da mesma alegação. A decisão é de quem anota, não da similaridade.
6. **Quem anota**: uma pessoa; as paráfrases não são geradas por LLM. Quem conhece as regras do agente deve escrever como alguém que nunca viu o código. O campo `revisor` é do revisor cruzado (R1).
7. **Split por entrada**: metade `calibracao`, metade `teste`. Os limiares (item 4 da Sprint 3) são ajustados só na calibração.

O `validar` confere tudo isso que é verificável: JSON e ids, tipo × URLs × stance, URL existente no corpus, URL nos 37 pares, veredito × stance, frase presente no texto da entrada, vazamento (mais de 60% das palavras da frase no título ou na alegação), revisor, split e composição. Erros impedem o `avaliar`; avisos não.

### Métricas

| Métrica | Frases | Definição | Meta |
| --- | --- | --- | --- |
| Recall@5 (busca) | `com_checagem` | Alguma URL aceita entre as 5 primeiras checagens distintas da busca (`search(k=30)` + `group_hits_by_url` sem limiar). Sem limiar e sem etapa 2: mede a recuperação. | ≥ 0,70 |
| Cobertura (agente) | `com_checagem` | O agente emitiu evidência com URL aceita. Mostra quanto o limiar e a etapa 2 cortam. | — |
| Macro-F1 de stance | `com_checagem`, `desmente` | Prevista = stance da primeira evidência com URL aceita; sem ela, `insuficiente` (Seção 4.8). Média nas classes com exemplo anotado. | ≥ 0,65 |
| Stance nas cobertas | `com_checagem`, `desmente` em que o agente citou uma URL aceita | % com a stance certa. Separa erro de stance de checagem perdida: no macro-F1, uma frase `insuficiente` cuja checagem o agente perdeu conta como acerto. | — |
| Evidência inventada | `sem_checagem` | % de frases com qualquer evidência | ≤ 0,10 |
| Casamento errado | todas | Evidências com URL fora das aceitas (inclui `fato_parecido`) | 0 |

O relatório mostra números absolutos ao lado de cada taxa, a matriz de confusão e cada erro com a frase. Com `--salvar`, grava `eval/resultados/evidencias_<data>.json` com métricas, detalhe por frase, tempos, configuração (modelos, limiares, coleção, trechos no índice, versão do `chromadb`) e o commit.

Para comparar modelos de embedding (item 5): defina `EVIDENCE_EMBEDDING_MODEL`, rode `build_index.py --reset` e depois `avaliar`. Compare o Recall@5, que não depende do limiar.

### Resultados

| Data | Split | Recall@5 | Cobertura | Macro-F1 | Stance nas cobertas | Inventada | Casamento errado | Arquivo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01/10 | todos | 18/19 = **0,95** | 14/19 = 0,74 | **0,61** | 14/14 = 1,00 | 0/11 = **0,00** | **7** | `eval/resultados/evidencias_2026-10-01.json` |
| 01/10 | teste | 10/10 | 7/10 | 0,44 | 7/7 | 0/5 | 3 | (mesmo arquivo) |
| 01/10 | calibração | 8/9 | 7/9 | 0,75 | 7/7 | 0/6 | 4 | (mesmo arquivo) |

Configuração: BGE-M3, mDeBERTa, `SIM_THRESHOLD` 0,55, `CLAIM_MATCH_MIN_PROB` 0,5, índice com 32.094 trechos, Mac (`mps`), commit `9eba0f7`. A "stance nas cobertas" foi criada depois da rodada e calculada a partir do detalhe por frase salvo no arquivo; as próximas rodadas já a gravam.

Leitura:
- **Quando o agente acha a checagem certa, a stance sai certa (14/14).** O macro-F1 abaixo da meta vem de checagens perdidas (5 de 19) e das 2 frases que desmentem o boato, não de erro de stance.
- A revocação de `insuficiente` (1,00) está inflada: em ev08/s02 o agente perdeu a checagem e citou outra, e a frase contou como acerto. A "stance nas cobertas" existe para isso.
- A análise dos erros e os próximos passos estão no ADR 3.

Estado do conjunto (01/10): 12 entradas e 36 frases, `validar` sem erros, URLs aceitas conferidas com o `diagnostico.py` (que acrescentou mais duas; saída em `eval/resultados/diagnostico_gold.txt`). **As frases foram escritas pelo Claude**, a pedido do R2, o que contraria a regra 6 acima. Antes de os números entrarem no relatório:
- o R1 revisa as frases e preenche `revisor`;
- o relatório declara a origem das paráfrases.

### Como reproduzir

macOS:

```bash
source venv/bin/activate
python eval/avaliar_evidencias.py validar
python eval/avaliar_evidencias.py frases          # grava eval/resultados/frases_gold.txt
python data/corpus/diagnostico.py --arquivo eval/resultados/frases_gold.txt > eval/resultados/diagnostico_gold.txt
python eval/avaliar_evidencias.py avaliar --salvar
```

Windows (PowerShell): os mesmos comandos, ativando o ambiente com `venv\Scripts\Activate.ps1`. Antes, rode `$env:PYTHONUTF8 = "1"`: sem isso, o Python grava a saída redirecionada na codificação do Windows e quebra nos caracteres "✓" e "…" do diagnóstico. Para gravar o diagnóstico em UTF-8, use `| Out-File -Encoding utf8 eval/resultados/diagnostico_gold.txt` no lugar do `>`.

## Integração

- `Segment` e `Evidence` vêm do `src/state.py` (Seção 3.3, na `develop` desde 29/09). O teste de contrato também valida a saída dentro do `PipelineState` estrito.
- O `graph.py` ainda usa o **stub** (`evidence_node`). Para plugar o agente real (integração do R1): `from src.agents.evidence import run as evidencias_node`. Nesse momento, o `tests/unit/test_state.py`, que roda o grafo inteiro, vai precisar simular a busca e o NLI, porque o CI não tem torch nem chromadb.
- Os casos de borda em `tests/fixtures/bordas/evidencias_*.json` seguem o formato do grupo, com uma chave a mais, `hits` (busca simulada para o teste unitário).
