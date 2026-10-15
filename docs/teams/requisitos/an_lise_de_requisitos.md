# Análise de Requisitos

## 1. Objetivo do Sistema

O sistema consiste em um bot integrado ao Telegram para auxiliar usuários na análise de conteúdos potencialmente relacionados à desinformação.

A proposta não é fornecer apenas uma classificação binária de "verdadeiro" ou "falso", mas apresentar uma análise contextualizada que permita ao usuário compreender os fatores considerados pelo sistema e desenvolver uma postura mais crítica diante da informação recebida.

A resposta do sistema será organizada em três componentes principais:

1. **Análise do conteúdo:** identificação e avaliação de características relevantes da notícia ou mensagem recebida;
2. **Estímulo ao pensamento crítico:** apresentação de uma pergunta reflexiva relacionada ao conteúdo analisado;
3. **Explicabilidade e rastreabilidade:** apresentação das evidências, fontes e principais fatores utilizados pelos agentes de IA para construir a análise.

---

## 2. Usuário do Sistema

O usuário principal será uma pessoa que recebe uma notícia ou mensagem pelo Telegram e deseja obter informações adicionais que auxiliem na avaliação de sua confiabilidade.

O sistema deverá ser desenvolvido considerando usuários sem conhecimento técnico sobre inteligência artificial, portanto as respostas deverão ser apresentadas em linguagem clara e acessível.

---

## 3. Requisitos Funcionais

### 3.1 Recebimento e análise do conteúdo

* **RF01 - Recebimento da notícia:** O sistema deve permitir que o usuário envie uma notícia ou mensagem textual ao bot por meio do Telegram.
* **RF02 - Processamento do conteúdo:** O sistema deve processar o conteúdo recebido e identificar as informações relevantes para sua análise.
* **RF03 - Identificação de alegações:** O sistema deve identificar as principais alegações factuais presentes no conteúdo enviado pelo usuário.
* **RF04 - Análise textual:** O sistema deve analisar características linguísticas e estruturais do conteúdo que possam estar relacionadas à desinformação, considerando elementos como linguagem emocional, alarmismo, senso de urgência e ausência de fontes.
* **RF05 - Avaliação do conteúdo:** O sistema deve utilizar o modelo de inteligência artificial desenvolvido para realizar uma avaliação do conteúdo analisado.
* **RF06 - Apresentação do resultado:** O sistema deve apresentar ao usuário o resultado da análise de forma contextualizada, evitando limitar a resposta a uma classificação binária de "verdadeiro" ou "falso".

### 3.2 Estímulo ao pensamento crítico

* **RF07 - Geração de pergunta reflexiva:** O sistema deve apresentar ao usuário uma pergunta relacionada ao conteúdo analisado com o objetivo de estimular o pensamento crítico.
* **RF08 - Contextualização da pergunta:** A pergunta reflexiva deve considerar os aspectos identificados durante a análise do conteúdo.
* **RF09 - Incentivo à verificação:** O sistema deve estimular o usuário a questionar a procedência, as evidências, as fontes e o contexto da informação antes de formar sua própria conclusão ou compartilhá-la.

### 3.3 Explicabilidade e rastreabilidade

* **RF10 - Apresentação das evidências:** O sistema deve apresentar as principais evidências utilizadas durante a análise do conteúdo.
* **RF11 - Apresentação das fontes:** O sistema deve apresentar as fontes utilizadas pelos agentes durante a análise, quando essas fontes estiverem disponíveis.
* **RF12 - Justificativa da análise:** O sistema deve apresentar os principais fatores que contribuíram para o resultado apresentado ao usuário.
* **RF13 - Rastreabilidade das informações:** O sistema deve permitir identificar a origem das informações utilizadas para fundamentar a análise.
* **RF14 - Apresentação da atuação dos agentes:** O sistema deve apresentar, de forma compreensível ao usuário, quais informações foram utilizadas pelos agentes e como elas contribuíram para a construção da resposta final.

---

## 4. Requisitos Não Funcionais

* **RNF01 - Usabilidade:** O sistema deve apresentar as informações em linguagem clara e acessível para usuários sem conhecimento técnico sobre inteligência artificial.
* **RNF02 - Transparência:** O sistema deve deixar claro que sua análise é baseada nas informações e evidências disponíveis, não devendo apresentar a avaliação como uma verdade absoluta.
* **RNF03 - Rastreabilidade:** As informações utilizadas para fundamentar a resposta devem possuir origem identificável, quando disponível.
* **RNF04 - Desempenho:** O sistema deve processar uma solicitação em tempo adequado para uma interação conversacional no Telegram.
* **RNF05 - Consistência:** O sistema deve utilizar critérios de análise definidos de forma consistente para diferentes conteúdos submetidos pelos usuários.

---

## 5. Regras de Negócio

* **RN01 - Análise não binária:** O resultado apresentado pelo sistema não deve se limitar exclusivamente às categorias "verdadeiro" ou "falso".
* **RN02 - Separação entre análise e reflexão:** A conclusão gerada pelo sistema deve ser apresentada separadamente da pergunta destinada ao estímulo do pensamento crítico.
* **RN03 - Fundamentação da resposta:** Sempre que possível, as informações apresentadas pelo sistema devem estar associadas às evidências e fontes utilizadas durante a análise.
* **RN04 - Transparência da análise:** O sistema deve apresentar ao usuário os principais elementos que contribuíram para o resultado, evitando que a resposta seja apresentada como uma conclusão sem justificativa.
* **RN05 - Estímulo à autonomia:** A resposta deve fornecer informações suficientes para que o usuário possa realizar sua própria avaliação sobre o conteúdo, evitando a dependência exclusiva da classificação fornecida pela inteligência artificial.

---

## 6. Fluxo Principal

O funcionamento esperado do sistema pode ser representado pelo seguinte fluxo:

1. **Usuário envia notícia** $\downarrow$
2. **Sistema recebe e processa o conteúdo** $\downarrow$
3. **Agentes realizam a análise** $\downarrow$
4. **Identificação das alegações e características do conteúdo** $\downarrow$
5. **Busca e análise das evidências disponíveis** $\downarrow$
6. **Construção da resposta:**
   * **1. Análise do conteúdo:** Apresentação dos principais aspectos identificados.
   * **2. Pensamento crítico:** Apresentação de uma pergunta reflexiva relacionada à análise.
   * **3. Explicabilidade:** Apresentação das evidências, fontes e fatores utilizados pelos agentes. $\downarrow$
7. **Resposta enviada ao usuário pelo Telegram**

---

## 7. Critérios de Aceitação

O sistema será considerado funcional quando:

- [ ] O usuário conseguir enviar uma notícia ou mensagem pelo Telegram;
- [ ] O conteúdo enviado for processado pelo sistema;
- [ ] O sistema realizar a análise utilizando o modelo desenvolvido;
- [ ] A resposta apresentar uma análise contextualizada do conteúdo;
- [ ] O sistema apresentar uma pergunta destinada ao estímulo do pensamento crítico;
- [ ] O sistema apresentar as principais evidências utilizadas na análise;
- [ ] As fontes utilizadas forem apresentadas quando disponíveis;
- [ ] O usuário conseguir compreender os principais fatores que levaram à resposta;
- [ ] A resposta não depender exclusivamente de um rótulo de "verdadeiro" ou "falso".