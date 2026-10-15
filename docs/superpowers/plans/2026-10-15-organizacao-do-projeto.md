# Organização do projeto: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar as pastas conforme o spec, sem mudar comportamento, num único commit.

**Architecture:** Só movimentação de arquivos com `git mv`, atualização de imports e caminhos, e documentação. Nenhuma lógica muda, exceto o `PROMPTS_DIR` do Sintetizador (um nível a mais) e o `sys.path` do script de exemplos.

**Tech Stack:** Python 3, pytest, pacotes de namespace (sem `__init__.py`).

**Spec:** `docs/superpowers/specs/2026-10-15-organizacao-do-projeto-design.md`

## Global Constraints

- Base: `develop` em 34a5eeb; branch `refactor/organizacao`.
- Resultado da suíte igual ao de antes: 599 passed, 2 skipped.
- Sem `__init__.py` novos; sem módulos de compatibilidade nos caminhos antigos.
- `app/app.py` continua sendo o ponto de entrada.
- Um único commit com a reorganização, o spec e este plano (pedido do usuário).

## Review Focus

- Trava dos testes contra o LM Studio: `tests/conftest.py` precisa continuar trocando `chamar_modelo` no módulo `src.agents.synthesizer.agent`; `tests/unit/test_isolamento.py` cobre.
- Prompts do Sintetizador achados no novo caminho: `tests/unit/test_synthesizer.py` carrega o prompt de sistema; se o `PROMPTS_DIR` estiver errado, falha com `FileNotFoundError`.
- Strings de caminho de módulo em testes (`"src.graph..."` em `monkeypatch.setattr` com string): conferir com `grep` depois da troca.
- App importando os novos caminhos: rodar a análise de URL real com `AppTest`.
- Scripts fora do pytest (`eval/`, `data/corpus/`, `scripts/`): conferir que importam (`python -c` / `--help`).

---

### Task 1: Mover pipeline, observabilidade e Sintetizador

**Files:**
- `git mv src/graph.py src/protecao.py src/medicao.py src/progresso.py src/pipeline/`
- `git mv src/observabilidade.py src/services/observabilidade.py`
- `git mv src/agents/synthesizer.py src/agents/synthesizer/agent.py`
- `git mv src/agents/dossie.py src/agents/synthesizer/dossie.py`
- Modify: todo `.py` em `src/`, `app/`, `tests/`, `eval/`, `data/corpus/` que importe os módulos acima.

**Interfaces:**
- Produces: `src.pipeline.graph` (`sistema_multiagente`, `construir_grafo`, `ORDEM_NOS`, `PREDECESSORES`), `src.pipeline.protecao`, `src.pipeline.medicao`, `src.pipeline.progresso`, `src.services.observabilidade` (`span`, `configurar_tracing`), `src.agents.synthesizer.agent` (`argumento_node`, `argumento_fallback`, `sintetizador_node`, `chamar_modelo`…), `src.agents.synthesizer.dossie`.

- [ ] **Step 1:** Fazer os `git mv` acima.
- [ ] **Step 2:** Trocar imports: `src.graph`→`src.pipeline.graph`, `src.protecao`→`src.pipeline.protecao`, `src.medicao`→`src.pipeline.medicao`, `src.progresso`→`src.pipeline.progresso`, `src.observabilidade`→`src.services.observabilidade`, `from src import protecao|medicao|observabilidade`→ caminho novo, `from src.agents import dossie`→`from src.agents.synthesizer import dossie`, `src.agents.dossie`→`src.agents.synthesizer.dossie`, `from src.agents.synthesizer import X`→`from src.agents.synthesizer.agent import X`, e `from src.agents import ..., synthesizer, ...` → separar em `from src.agents.synthesizer import agent as synthesizer`.
- [ ] **Step 3:** Em `src/agents/synthesizer/agent.py`, `PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"`.
- [ ] **Step 4:** `grep -rnE "src\.(graph|protecao|medicao|progresso|observabilidade)\b|src\.agents\.dossie|from src import (protecao|medicao|observabilidade|progresso)" --include='*.py' src app tests eval data scripts` → nenhuma saída.
- [ ] **Step 5:** `venv/bin/python -m pytest -q` → 599 passed, 2 skipped.

### Task 2: Stubs para os testes e limpeza da raiz

**Files:**
- `git mv src/stubs tests/stubs`; Modify: `tests/contract/*.py` (`src.stubs`→`tests.stubs`).
- `git mv test_news.py scripts/rodar_exemplos.py`; adicionar no topo `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` antes dos imports de `src`, como em `eval/medir_latencia.py`, e trocar `src.graph` pelo caminho novo.
- `git rm patch_tests.py`.

- [ ] **Step 1:** Mover e editar como acima.
- [ ] **Step 2:** `grep -rn "src.stubs" --include='*.py' .` (fora de `venv/`) → nenhuma saída.
- [ ] **Step 3:** `venv/bin/python -c "import ast,sys; ast.parse(open('scripts/rodar_exemplos.py').read())"` e `venv/bin/python -m pytest -q tests/contract` → passa.

### Task 3: Documentação

**Files:** `README.md` (árvore do repositório e caminhos citados), `docs/agents/*.md`, comentários e docstrings em `src/` e `app/` que citam os caminhos antigos.

- [ ] **Step 1:** `grep -rnE "src/(graph|protecao|medicao|progresso|observabilidade)\.py|agents/(dossie|synthesizer)\.py|src/stubs|test_news" README.md docs/agents src app tests` e atualizar cada ocorrência para o caminho novo. Specs, planos e relatórios antigos ficam como estão.
- [ ] **Step 2:** Rodar o mesmo `grep` → nenhuma saída.

### Task 4: Verificação final e commit

- [ ] **Step 1:** `venv/bin/python -m pytest -q` → 599 passed, 2 skipped.
- [ ] **Step 2:** `venv/bin/python eval/medir_latencia.py --help` e `venv/bin/python data/corpus/diagnostico.py --help` → mostram a ajuda sem `ImportError`.
- [ ] **Step 3:** Rodar o app com `AppTest` (página `analisar`, URL real da Agência Brasil) → análise termina sem exceção e o Ingestor conclui.
- [ ] **Step 4:** `git status` mostra os renames (`R`) e nada fora do escopo; commit único:

```bash
git add -A src app tests eval data scripts docs README.md patch_tests.py test_news.py
git commit -m "refactor: organiza o projeto em pacotes por responsabilidade"
```
