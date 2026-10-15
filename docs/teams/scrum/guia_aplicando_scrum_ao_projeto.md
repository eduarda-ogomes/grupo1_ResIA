# Guia: Aplicando Scrum ao Projeto

**Desafio 1 (Fake News / Desinformação) — práticas de Scrum e papéis sugeridos para o grupo**  
*Felipe Matheus · 10/09/2026 · Revisado: cronograma de 6 sprints combinado em grupo*

---

## 1. Por Que Scrum, e Por Que Adaptado

Scrum é um framework, não uma metodologia fechada — a própria documentação oficial insiste nisso: ele dá só a estrutura mínima necessária (papéis, eventos, artefatos) e espera que cada equipe adapte o resto à sua realidade. Ele se sustenta em três pilares — **transparência** (todo mundo vê o mesmo estado do trabalho), **inspeção** (checagens frequentes do progresso) e **adaptação** (ajustar o processo quando algo não está funcionando). Isso encaixa bem no nosso projeto porque ele tem incerteza real: não sabemos ainda que arquitetura de protótipo vamos construir, nem o resultado do experimento $2018 \rightarrow 2026$ — Scrum é feito exatamente para esse tipo de trabalho, em vez de projetos totalmente previsíveis.

Dito isso, Scrum "de livro" foi desenhado para times profissionais, dedicados em tempo integral. Nosso grupo é o oposto disso: 5 pessoas, *part-time*, com aulas, estágios e outras disciplinas concorrendo pelo tempo. A pesquisa sobre Scrum em equipes de estudantes é consistente nesse ponto: *standups* diários não funcionam bem quando a equipe não está junta todo dia, e ciclos mais curtos com cerimônias flexíveis tendem a funcionar melhor do que tentar replicar o processo de uma empresa de software. O grupo optou por manter sprints como blocos de planejamento — cada um com um foco técnico claro —, mas o escopo de cada sprint é sempre decidido em conversa coletiva, com opinião de todos, nunca fechado por uma pessoa só.

---

## 2. Papéis Sugeridos para o Nosso Grupo

O Scrum define três papéis: **Product Owner** (dono do produto — ajuda a enxergar o que é mais valioso fazer), **Scrum Master** (facilita o processo e remove obstáculos) e **Developers** (quem constrói o incremento). Em times profissionais, esses papéis normalmente não se sobrepõem, e o Product Owner prioriza sozinho. Num grupo de 5 pessoas *part-time* que decidiu planejar tudo em conjunto, isso muda: os papéis abaixo continuam existindo, mas nenhum deles tem poder de decisão individual — a decisão final é sempre do grupo.

| Papel | Quem | O que faz no nosso contexto |
| :--- | :--- | :--- |
| **Product Owner** | Felipe — fixo | Mantém a conexão com a *Essential Question* e o Guia já construído; leva ao grupo uma visão do panorama geral e do que está pendente, para embasar a conversa — mas não decide sozinho: a priorização é sempre discutida e fechada com todos. |
| **Scrum Master** | Rotativo — 1 pessoa diferente a cada sprint | Conduz a *Sprint Planning* e a *Sprint Retrospective*; mantém o *board* atualizado; lembra o grupo de fazer os *check-ins*; identifica bloqueios e ajuda a resolvê-los. Rotacionar garante que todo mundo passe pela experiência de facilitar, e ninguém fica "só" de PM. |
| **Developers** | Todos os 5, inclusive o PO e quem estiver de Scrum Master no sprint | Executam os itens combinados para o sprint — pesquisa, curadoria de dados, construção do protótipo, escrita dos documentos. Autogerenciados: o grupo decide junto quem pega o quê, sem que isso venha imposto de cima. |

Vale registrar a principal diferença em relação ao Scrum "de livro": lá, Product Owner e Scrum Master tipicamente não desenvolvem o incremento, e o Product Owner prioriza sozinho. Aqui, com 5 pessoas, isso deixaria só 3 "mãos" disponíveis para o trabalho de verdade, e concentraria a priorização numa pessoa só — o que o grupo especificamente não quis. Por isso os dois papéis são cumulativos com o de Developer, e toda decisão de prioridade passa pelo grupo.

---

## 3. Cronograma de Sprints do Projeto

O cronograma abaixo cobre o restante do projeto em 6 sprints, combinados em grupo. Cada sprint tem um foco principal e uma lista de itens — a lista é o ponto de partida da *Sprint Planning* de cada sprint, não um escopo fechado de antemão: o grupo confirma e ajusta junto no início de cada uma.

| Sprint | Itens planejados |
| :--- | :--- |
| **Sprint 1** | • Criar/entregar *guiding questions*<br>• Decidir dataset a ser utilizado<br>• Pré-preparação dos dados<br>• Levantamento de requisitos<br>• Pesquisa sobre o modelo a ser construído<br>• Entregar processo investigativo<br>• Estruturação do Scrum do projeto |
| **Sprint 2 — Coleta e preparação dos dados de 2018** | • Consolidar o(s) dataset(s) de 2018 escolhido(s) (ex.: Fake.br Corpus, FakeWhatsApp.Br, FACTCK.BR)<br>• Definir critérios de rotulagem e filtragem para o recorte político<br>• Limpeza e normalização textual (remoção de ruído, tokenização, padronização)<br>• Análise exploratória dos dados (distribuição de classes, tamanho médio dos textos, balanceamento)<br>• Separar dados em treino/validação/teste (*holdout* dentro do próprio período de 2018)<br>• Documentar o pipeline de pré-processamento |
| **Sprint 3 — Modelo baseline** | • Implementar extração de *features* (TF-IDF)<br>• Treinar modelo *baseline* (Regressão Logística e/ou SVM) com os dados de 2018<br>• Validar o *baseline* no *holdout* de 2018 (acurácia, precisão, *recall*, $F_1$)<br>• Ajustar hiperparâmetros do *baseline*<br>• Documentar resultados preliminares |
| **Sprint 4 — Modelo avançado (BERTimbau)** | • Preparar tokenização/*embeddings* compatíveis com o BERTimbau<br>• Realizar *fine-tuning* do BERTimbau com os dados de 2018<br>• Validar o modelo avançado no *holdout* de 2018<br>• Comparar desempenho *baseline* vs. modelo avançado (ainda dentro do período de 2018)<br>• Ajustes finais em ambos os modelos antes do teste de generalização |
| **Sprint 5 — Coleta de dados atuais e teste de generalização temporal** | • Coletar e rotular um conjunto de notícias/desinformação política atual (2026)<br>• Aplicar os dois modelos (treinados em 2018, sem retreinar) sobre os dados atuais<br>• Medir a queda de desempenho de cada modelo (*concept drift*)<br>• Análise de erros: investigar se a queda vem de vocabulário novo, temas/atores políticos novos, ou mudança estrutural na desinformação<br>• Comparar como cada arquitetura (clássica vs. *transformer*) degrada |
| **Sprint 6 — Análise final, documentação e entrega** | • Consolidar resultados e gerar visualizações comparativas (2018 vs. 2026, *baseline* vs. avançado)<br>• Discutir limitações do experimento (tamanho do dataset, critérios de rotulagem, recorte temático)<br>• Redigir o relatório final<br>• Preparar apresentação/slides<br>• Retrospectiva do Scrum e entrega final do projeto |

---

## 4. Cerimônias — Adaptadas à Rotina do Grupo

* **Sprint Planning (início de cada sprint, ~30 min)** — provavelmente na própria reunião de quinta-feira já estabelecida: decidir juntos, com opinião de todos, o que entra no sprint.
* **Check-in assíncrono (2-3x por semana)** — reunião diária não é realista para um grupo *part-time* — a literatura de Scrum em equipes de estudantes confirma isso. Em vez disso, cada um posta uma mensagem curta no grupo (o que fiz, o que vou fazer, algum bloqueio) — leva 2 minutos e mantém todo mundo alinhado sem exigir sincronia.
* **Sprint Review (fim de cada sprint, ~20 min)** — pode acontecer dentro da própria reunião de quinta seguinte: mostrar o que foi de fato entregue (não o que foi "tentado") — a lista de *guiding questions* pronta, o modelo treinado, a versão nova do protótipo.
* **Sprint Retrospective (~10-15 min)** — logo depois da revisão, ainda mais curta: o que funcionou bem, o que atrapalhou, e uma mudança concreta para o próximo sprint. Não precisa de ferramenta especial — três perguntas bastam.

---

## 5. Artefatos — Como Isso Vira o Board Que Vocês Já Usam

O *board* de "A fazer" que o grupo já usa não precisa ser trocado — só precisa ganhar uma estrutura simples por cima dele.

* **Backlog geral** — a lista completa de tudo que o projeto pode precisar. Na prática, é a coluna "A fazer" de vocês, só que olhando o desafio inteiro, não só o sprint atual (ver lista sugerida na Seção 6). O grupo todo ajuda a manter e priorizar essa lista.
* **Sprint Backlog** — o subconjunto do backlog geral combinado em grupo para o sprint atual. Sugestão prática: criar uma etiqueta ou coluna "Sprint Atual" no *board*, e mover só os itens combinados na *Sprint Planning* para lá.
* **Incremento** — o resultado concreto e utilizável ao fim do sprint — não "trabalhamos nisso", mas algo que existe e pode ser mostrado: a lista de *Guiding Questions* consolidada, o modelo treinado e avaliado, a versão do protótipo que roda de ponta a ponta.
* **Definition of Done** — critério mínimo para considerar um item realmente pronto, não só "comecei". Sugestão por tipo de item: uma *Guiding Question* está pronta quando está na lista consolidada com a agência/fonte que a embasa; um dataset está pronto quando catalogado com link verificado; o experimento está pronto quando tem métricas e uma interpretação escrita, não só números soltos.

---

## 6. Backlog Inicial Sugerido

Um ponto de partida para o backlog geral, organizado pelas frentes que já estão em andamento — o grupo prioriza e ajusta junto na primeira *Sprint Planning*.

- [ ] Consolidar as *Guiding Questions* individuais (geral + política) em uma lista única do grupo.
- [ ] Finalizar e revisar o catálogo de datasets (já levantado) com o grupo todo.
- [ ] Preparar os dados de 2018 (FakeWhatsApp.Br + Fake.br Corpus) para treino.
- [ ] Treinar e avaliar o modelo *baseline* (TF-IDF + Regressão Logística/SVM).
- [ ] Curar o conjunto de teste de 2026 (10-30 casos, geral e política, com e sem uso de IA generativa).
- [ ] Rodar a avaliação *cross-temporal* e documentar os resultados.
- [ ] Revisar a *Trust Matrix* à luz do Guia (fonte/conteúdo/propagador, triagem fato/opinião/valor).
- [ ] Decidir a arquitetura do protótipo (padrão andaime) e implementar a interação núcleo.
- [ ] Integrar os achados do experimento ao discurso do protótipo/apresentação.
- [ ] Preparar e ensaiar a apresentação da Semana 6.

---

## 7. O Que Não Vamos Seguir à Risca

Registrar as adaptações explicitamente evita confusão e é, em si, fiel ao espírito do Scrum (que é para ser ajustado, não seguido como dogma):

* **Sprints existem como blocos de planejamento**, mas o escopo de cada um é sempre decidido em conversa coletiva no início do sprint — nunca fechado por uma pessoa só.
* **Sem priorização unilateral** — nem o Product Owner, nem o Scrum Master decidem sozinhos; toda prioridade é combinada com opinião de todos.
* **Sem Daily Scrum diário** — substituído por *check-in* assíncrono 2-3x por semana.
* **Product Owner e Scrum Master também desenvolvem** — não ficam de fora da entrega, diferente do Scrum "de livro".
* **Sem estimativa formal em story points** — dado o volume pequeno de itens, uma estimativa simples em horas ou "P/M/G" já é suficiente.

---

## Referências

1. SCHWABER, K.; SUTHERLAND, J. (2020) *The Scrum Guide*. Disponível em: `scrumguides.org`
2. *Scrum in the Classroom: An Implementation Guide*. Disponível em: `researchgate.net/.../377199429`
3. DAMIANOVA, N.; BERREZUETA-GUZMAN, S. (2026) *The Anatomy of a Successful Student Scrum Team: Motivation, Personalities, and Academic Adaptation*. Disponível em: `arxiv.org/abs/2601.03364`
4. *Adapting SCRUM Ceremonies in Undergraduate Capstone Projects*. Disponível em: `capstonedesigncommunity.org`
5. *Scrum as a Platform to Manage Students in Projects of Technological Development and Scientific Initiation: A Study Case Realized at UNIT/SE*. Disponível em: `researchgate.net/.../316908757`