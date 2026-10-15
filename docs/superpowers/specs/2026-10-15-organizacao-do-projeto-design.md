# Organização do projeto: design

Data: 15/10/2026. Branch: `refactor/organizacao`, a partir da `develop` (34a5eeb).

## Objetivo

Arrumar a estrutura de pastas para que cada pacote tenha uma responsabilidade clara, sem mudar comportamento. Sucesso: mesma suíte de testes passando, o app rodando como antes e nenhum import apontando para caminho antigo.

Fora do escopo: renomear módulos dos agentes, mudar código além de imports e caminhos, mexer em `app/app.py` como ponto de entrada (os deploys apontam para ele).

## Problemas atuais

- A infraestrutura do pipeline (`graph.py`, `protecao.py`, `medicao.py`, `progresso.py`, `observabilidade.py`) fica solta na raiz de `src/`, ao lado do contrato `state.py`.
- O Sintetizador está dividido em dois arquivos irmãos de todos os outros agentes (`agents/synthesizer.py` e `agents/dossie.py`).
- `src/stubs/` faz parte do pacote da aplicação, mas só os testes de contrato a usam.
- Arquivos avulsos na raiz: `patch_tests.py` (script único que reescreveu um teste, já aplicado) e `test_news.py` (script manual de exemplos, não é teste do pytest).

## Estrutura nova

```
src/
  state.py                      contrato, fica
  pipeline/                     orquestração
    graph.py  protecao.py  medicao.py  progresso.py
  services/
    llm.py
    observabilidade.py          de src/
  agents/
    ingestor.py  evidence.py  text_analysis.py  socratic.py
    synthesizer/
      agent.py                  de agents/synthesizer.py
      dossie.py                 de agents/dossie.py
  retrieval/  guardrails/  prompts/   ficam
tests/stubs/                    de src/stubs/
scripts/rodar_exemplos.py       de test_news.py
patch_tests.py                  removido
```

## Decisões

1. **`retrieval/` fica em `src/`.** É compartilhada pelo Agente de Evidências, pelos guardrails (`ancoragem.py` usa a tokenização da `etapa2`), por 7 scripts de `data/corpus/`, 2 de `eval/` e 7 arquivos de teste. Dentro do agente, todos passariam a depender do miolo dele.
2. **`observabilidade.py` vai para `services/`.** Os agentes usam `span()`. Em `pipeline/`, os agentes importariam o pacote que importa os agentes.
3. **Sem `__init__.py` nos pacotes novos.** O projeto inteiro usa pacotes de namespace (não há `__init__.py` em `src/` nem nos subpacotes); `pipeline/` e `agents/synthesizer/` seguem o mesmo padrão.
4. **Todo mundo importa o módulo do Sintetizador pelo caminho completo**, `src.agents.synthesizer.agent`. Os testes usam `from src.agents.synthesizer import agent as synthesizer`, então os `monkeypatch.setattr(synthesizer, "chamar_modelo", ...)` continuam acertando o módulo que chama o LLM. Uma reexportação num `__init__.py` faria o patch cair no pacote e desligaria, sem aviso, a trava do `tests/conftest.py` que impede os testes de falar com o LM Studio; o `tests/unit/test_isolamento.py` confirma que a trava segue valendo.
5. **Sem módulos de compatibilidade nos caminhos antigos.** Duas formas de importar a mesma coisa confundem quem chega; os renames feitos com `git mv` deixam o merge das branches abertas resolver a maior parte.
6. **Caminhos relativos ao arquivo.** `agents/synthesizer/agent.py` fica um nível mais fundo: o `PROMPTS_DIR` passa de `parents[1]` para `parents[2]`. `scripts/rodar_exemplos.py` ganha o mesmo `sys.path.insert` da raiz que os scripts de `eval/` usam, para rodar com `python scripts/rodar_exemplos.py`.
7. **Documentação:** atualizar README, `docs/agents/*.md` e comentários com caminhos. Specs, planos e relatórios antigos em `docs/` ficam como registro do que era verdade na data.

## Impacto

- Branches abertas que mexem em `src/agents/synthesizer.py` ou `src/services/llm.py` (`setup_mlops_deployment`, `test/deploy`): o git detecta o rename; os conflitos esperados são nas linhas de import.
- O Dockerfile do Hugging Face e o Streamlit Cloud usam `app/app.py`, que não muda.

## Verificação

- `pytest` completo: o mesmo resultado de antes da mudança (599 passed, 2 skipped na `develop` em 34a5eeb), incluindo `tests/unit/test_isolamento.py`.
- `grep` sem ocorrências de `src.graph`, `src.protecao`, `src.medicao`, `src.progresso`, `src.observabilidade`, `src.stubs`, `src.agents.dossie` e do módulo antigo do Sintetizador em código e docs atuais.
- O app sobe e uma análise de URL real termina sem exceção (o mesmo roteiro com `AppTest` usado no PR #28).
