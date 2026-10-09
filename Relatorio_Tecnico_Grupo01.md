# Relatório Técnico - Modelo de IA (Grupo 01)
**Desafio:** 2_First Challenge - Residência IA
**Entregável:** Modelo treinado, Notebook de avaliação e Documentação.

## 1. Processo de Preparação dos Dados e "Treinamento"
Neste desafio de checagem e síntese de informações (Dossiê), a abordagem adotada foi o uso de um **Sistema Multiagente (LangGraph)** orquestrando Modelos de Linguagem de Grande Escala (LLMs) executados localmente. Portanto, em vez do treinamento tradicional de pesos do zero, nosso "processo de treinamento e preparação" focou em:
* **Engenharia de Prompts (Few-shot learning):** Refinamento iterativo dos prompts de sistema (`sintetizador_sistema.md`, `texto_sistema.md`, `socratico_sistema.md`) para forçar saídas JSON estritas e alinhar o comportamento (ex: ignorar adjetivação extrema descritiva em notícias de desastres).
* **Base de Evidências (RAG):** Preparação do banco de checagens para a etapa de Retrieval-Augmented Generation e validação de NLI.

## 2. Critérios para a Abordagem Adotada
* **Arquitetura Multiagente:** Escolhemos separar as responsabilidades em 4 agentes (Ingestor, Texto, Evidência, Socrático) e 1 Sintetizador final. Isso permite isolar falhas (degradação graciosa) sem que a queda de um modelo comprometa toda a execução.
* **Modelos Locais (LM Studio):** Optou-se por rodar LLMs menores e mais rápidos localmente para garantir privacidade e testar os limites de processamento sem custos de API (ex: Qwen 2.5).

## 3. Métricas de Desempenho e Resultados
Nossa avaliação (presente no `.ipynb`) não se baseia apenas em Acurácia clássica, mas sim em **Conformidade, Resiliência e Latência**:
* **Taxa de Conformidade (Guardrails):** A IA passou a respeitar 100% da restrição de *não dar vereditos absolutos* (fake/verdade) graças ao módulo de guardrails desenvolvido.
* **Degradação Graciosa (Resiliência):** Quando a etapa de evidência falha (banco vazio), o pipeline não quebra; ele retorna avisos amigáveis ("Nenhuma checagem encontrada...").
* **Latência:** Tempo médio de execução do pipeline completo (todos os agentes) estabilizado.

## 4. Principais Desafios Enfrentados
* **Falsos Positivos em Análise Retórica:** O agente inicial classificava termos técnicos/factuais de acidentes (ex: "carbonizado", "totalmente destruído") como *adjetivação extrema* e viés. Foi necessário atualizar as regras lógicas e o prompt do modelo.
* **Alucinação na Síntese:** O modelo sintetizador por vezes adicionava redundantemente a seção "Marcadores de Texto" junto com "Como o texto argumenta", ou criava links inexistentes. Resolvemos delegando a estrutura final de tópicos ao Python puro (`dossie.py`), e usando a LLM estritamente para redigir o corpo dos argumentos.

## 5. Lições Adquiridas
* **Fronteira Python vs. LLM:** Aprendemos que a formatação e validação pesada devem ficar no Python (backend tradicional), enquanto o LLM deve receber tarefas pequenas, específicas e delimitadas.
* **O valor de errar bem:** A implementação da *degradação graciosa* foi um marco. Um software de IA maduro não é aquele que nunca erra, mas o que trata a incerteza de forma transparente para o usuário.
