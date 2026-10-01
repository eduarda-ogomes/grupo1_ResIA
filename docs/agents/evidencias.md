# Agente de Evidências

Dono: R2 (Túlio Celeri) · Branch: `AgenteEvidencias` · Atualizado em 28/09/2026
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
- `apoia` é raro: o corpus quase só tem vereditos "falso".
- Termos-chave dependem de maiúsculas corretas; limiares ainda não calibrados no gold set.

## Integração

- `Segment` e `Evidence` vêm do `src/state.py` (Seção 3.3, na `develop` desde 29/09). O teste de contrato também valida a saída dentro do `PipelineState` estrito.
- O `graph.py` ainda usa o **stub** (`evidence_node`). Para plugar o agente real (integração do R1): `from src.agents.evidence import run as evidencias_node`. Nesse momento, o `tests/unit/test_state.py`, que roda o grafo inteiro, vai precisar simular a busca e o NLI, porque o CI não tem torch nem chromadb.
- Os casos de borda em `tests/fixtures/bordas/evidencias_*.json` seguem o formato do grupo, com uma chave a mais, `hits` (busca simulada para o teste unitário).
