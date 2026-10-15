# Challenge 1: Fake News / Desinformação
## Processo Investigativo + Guiding Questions

**Instituição:** Instituto Eldorado — *Inspiração pelo Novo*  
**Programa:** Residência de IA — Grupo 01  

**Integrantes:**
* Ana Beatriz de Oliveira Marques
* Túlio Augusto Celeri
* Maria Carolina Martins Frota
* Maria Eduarda de Oliveira Gomes
* Felipe Matheus Ribeiro Lopes

---

## 1. Questionamentos Levantados pelo Grupo

1. Onde informações são obtidas?
2. Que tipo de pessoa é alvo?
3. Que tipo de sistema de IA poderíamos criar sobre esse tema de desinformação?
4. Qual a motivação por trás da desinformação?
   * **a.** Poder político
   * **b.** Lucro financeiro
   * **c.** Manipulação da opinião pública
5. A desinformação pode ser boa?
6. Quais fatores influenciam na hora de analisar uma notícia?
7. Confiança é algo metrificável? Se sim, como podemos medi-la?
8. Como medir se uma informação é confiável?
   * $\rightarrow$ *Jornalismo é imparcial, a motivação de uma notícia é propagar uma informação sem viés.*

### Palavras-chave elencadas pelo grupo sobre o tema:
> Poder, manipulação, crença, dados falsos, controle, influência, viés, polêmica, engajamento, emocional, atenção.

### Conceitos que se relacionam com desinformação:
* **Pós-verdade:** As pessoas aceitam uma informação porque ela confirma o que já sentem ou acreditam.
* **Pensamento Crítico:** Habilidade de questionar diante do contexto que se tem, com informações já conhecidas.
* **Possível Inspiração:** Existe um site gringo chamado *AllSides* que classifica veículos de notícia com base em como o público relata suas próprias inclinações políticas, usando um sistema patenteado de classificação de viés que envolve *crowdsourcing*, pesquisas, análise interna e fontes de terceiros como a Wikipedia. Classifica-se em categorias tipo *Left*, *Lean Left*, *Center*, *Lean Right*, *Right*.

### Tipos de Desinformação:
* **Desinformação deliberada (*Disinformation*):** Conteúdo comprovadamente falso criado e compartilhado com intenção explícita de enganar, lucrar ou prejudicar alguém (indivíduo, grupo, instituição ou processo democrático).
* **Informação incorreta (*Misinformation*):** Conteúdo falso ou equivocado compartilhado sem intenção deliberada de prejudicar — geralmente por pessoas que realmente acreditam naquilo e repassam em grupos familiares ou redes sociais.
* **Informação maliciosa (*Malinformation*):** Informações verdadeiras, vazamentos ou dados reais retirados de contexto e divulgados propositalmente para difamar, expor privacidade ou causar dano direto.

---

## 2. Ideias de Produto que Surgiram

### Ideia 1: Verificador de Desinformação em Falas Políticas
Esta aplicação tem como objetivo analisar declarações públicas de políticos, sejam discursos, entrevistas ou publicações em redes sociais, e verificar automaticamente se contêm desinformação. O sistema identificaria afirmações factualmente verificáveis dentro da fala (separando-as de opiniões subjetivas) e as classificaria com base em graus de veracidade, indo além do simples "verdadeiro ou falso" para capturar nuances como afirmações parcialmente corretas ou descontextualizadas. A validação seria feita cruzando as informações com fontes confiáveis, como bancos de dados oficiais e agências de *fact-checking* já estabelecidas. O principal desafio técnico está em garantir imparcialidade na análise, aplicando o mesmo rigor a políticos de diferentes espectros ideológicos, e em lidar com a ambiguidade natural da linguagem política.

### Ideia 2: Classificador de Viés Político em Notícias
Esta aplicação permite que o usuário anexe uma notícia e receba, em troca, uma classificação percentual indicando se o conteúdo tende para a esquerda, o centro ou a direita do espectro político. Diferente da primeira ideia, o foco aqui não é a veracidade da informação, mas o enquadramento (*framing*) e o viés editorial presentes no texto, como escolha de vocabulário, seleção de fontes citadas e ênfase dada a determinados aspectos da notícia. O maior desafio conceitual é que, ao contrário da verificação de fatos, não existe um "gabarito" objetivo para classificar viés político, o que exige uma metodologia transparente de rotulagem (por exemplo, avaliação por múltiplos anotadores humanos com espectros políticos diferentes). O projeto também precisa lidar com a distinção entre viés do veículo como um todo e viés de uma matéria específica.

### Ideia 3: Teste de Generalização Temporal — Modelo Treinado em 2018 vs. Notícias Atuais *(Ideia escolhida pelo grupo)*
Esta ideia parte de uma pergunta diferente das duas anteriores: em vez de criar uma nova aplicação de classificação, o foco é investigar quão bem um modelo de detecção de desinformação (ou de viés) generaliza ao longo do tempo. A proposta é treinar um classificador usando um conjunto de notícias e desinformações da eleição presidencial de 2018 — período com bastante material documentado por *fact-checkers* e pesquisadores, já que foi um marco na discussão sobre desinformação política no Brasil — e depois testar esse mesmo modelo em notícias políticas atuais (2026), sem retreiná-lo. O objetivo é medir se há queda de desempenho (um fenômeno conhecido como *concept drift*, ou desvio de conceito), o que aconteceria porque os temas, vocabulário, atores políticos e estratégias de desinformação mudam com o tempo — um modelo treinado para reconhecer boatos sobre um determinado candidato ou pauta de 2018 pode não reconhecer padrões novos ligados a eventos, plataformas ou figuras políticas que não existiam ou não tinham relevância na época. O principal desafio técnico está em conseguir dados rotulados de ambos os períodos de forma comparável, e o principal valor do projeto está menos em construir uma ferramenta de uso prático e mais em gerar uma análise crítica sobre a durabilidade e os limites reais de modelos de IA aplicados a um problema que é, por natureza, mutável ao longo do tempo.

### Ideia 4: Bot de WhatsApp para Avaliação de Confiabilidade e Estímulo ao Pensamento Crítico
Esta aplicação propõe a criação de um assistente conversacional integrado diretamente ao WhatsApp — canal prioritário de disseminação orgânica de boatos e correntes no Brasil — cujo papel não é atuar como um árbitro autoritário da verdade, mas como um tutor de letramento midiático e checagem auxiliada por IA. Em vez de apenas devolver um veredito binário ("verdadeiro" ou "falso") que incentive a automação do julgamento, o sistema decompõe a mensagem encaminhada pelo usuário em evidências transparentes: realiza a extração e busca da alegação em bases de agências de checagem parceiras, identifica técnicas de manipulação discursiva (como apelo emocional excessivo, alarmismo, senso artificial de urgência ou ausência de fontes citadas) e sugere perguntas reflexivas para que o próprio usuário aprenda a questionar a procedência daquele conteúdo.

O principal desafio técnico reside em construir um pipeline eficiente de recuperação e explicabilidade (XAI) em linguagem natural e acessível, capaz de lidar com a diversidade de formatos típicos do ecossistema do aplicativo (textos repletos de emojis, mensagens truncadas, áudios transcritos e imagens fora de contexto). Do ponto de vista conceitual e ético, o desafio é calibrar a resposta para evitar o "efeito oráculo" — assegurando que o modelo forneça contexto, rastreabilidade e fontes verificáveis sem gerar dependência cognitiva ou criar atrito ideológico que faça o usuário rejeitar a ferramenta por percepção de viés.

---

## 3. Guiding Questions

### Gerais
* Como se define desinformação, e qual a diferença entre desinformação, misinformação e malinformação?
* Quais características textuais, linguísticas ou estruturais costumam distinguir conteúdo enganoso de conteúdo factual?
* Quais são as limitações e riscos de sistemas automatizados de detecção (falsos positivos, viés do modelo, dependência da qualidade dos dados de treino)?
* Como a desinformação se relaciona com fenômenos como câmaras de eco e polarização?
* Quem lucra com a desinformação? Existe uma "indústria" da desinformação?
* Quais são os grupos mais vulneráveis a cada um desses tipos de informação, e por quê (ex: idosos e pessoas com menor acesso à educação digital)?
* Que fatores psicológicos e sociais tornam as pessoas mais propensas a acreditar e compartilhar desinformação (ex: viés de confirmação, heurísticas de familiaridade)?
* Quem deveria ser responsabilizado quando desinformação causa dano real: o criador, quem compartilha, ou a plataforma que amplifica?
* De que maneira um algoritmo pode operacionalizar a separação entre informação incorreta, desinformação e má informação, considerando que a intenção por trás do compartilhamento não consta no próprio texto?
* Quais elementos combinados (procedência do veículo, estrutura textual e métricas de engajamento) são determinantes para orientar a avaliação imediata do usuário sobre a confiabilidade do conteúdo?
* Quais contradições emergem ao utilizar modelos de inteligência artificial na contenção de um fenômeno impulsionado pela própria IA, e quais restrições isso estabelece ao projeto?
* Que indicadores revelam que a ferramenta passou a gerar automação do julgamento individual em vez de estimular a reflexão crítica?

### Política
* Como a desinformação política se diferencia de outros tipos (ex: saúde, ciência)?
* De que maneira o nosso pipeline lidará com meias-verdades?
* Como avaliar a performance do classificador (precisão, recall, comparação com *fact-checkers* humanos)?
* Até que ponto o Estado consegue regular o discurso online para combater a desinformação intencional sem acabar punindo também a informação incorreta (compartilhada de boa-fé) ou restringindo a liberdade de expressão legítima?
* Como evitar que nosso sistema seja percebido como politicamente enviesado, já que pesquisa recente mostra que usuários enxergam inclinação ideológica em modelos de IA populares, mesmo sem prova de viés real?
* Que diferença de tratamento nosso sistema precisa dar a uma alegação factual com carga política (ex.: um dado eleitoral) versus uma alegação de valor (ex.: uma proposta de política pública) e como ele identificaria essa diferença antes de tentar avaliar algo?
* Será que um classificador ajustado exclusivamente com dados das eleições de 2018 preserva sua capacidade de identificar fraudes em 2026, ou o fenômeno da desinformação sofreu uma mudança de conceito tão profunda que torna essa investigação irrelevante?
* Que parte de uma eventual queda de desempenho em 2026 viria de mudança na linguagem da desinformação, e que parte viria simplesmente de temas políticos novos (candidatos, escândalos) que o modelo nunca viu?
* Ao combinar `FakeWhatsApp.Br` (estritamente eleitoral) com `Fake.br Corpus` (desinformação geral), o modelo aprende a reconhecer desinformação política especificamente, ou desinformação em geral? Isso muda como devemos avaliar os resultados em 2026?
* Como escolher e apresentar os casos de teste políticos de 2026 de um jeito que não pareça, mesmo sem intenção, favorecer um lado político?

---

## 4. Possíveis Datasets

### Detecção de fake news / desinformação (português)
* **Fake.Br Corpus** $\rightarrow$ [GitHub](https://github.com/roneysco/Fake.br-Corpus)
* **Fake.Br Corpus (versão Hugging Face)** $\rightarrow$ [Hugging Face](https://huggingface.co/datasets/fake-news-UFG/fakebr)
* **FACTCK.BR** $\rightarrow$ [GitHub](https://github.com/jghm-f/FACTCK.BR)
* **FACTCK.BR (versão Hugging Face)** $\rightarrow$ [Hugging Face](https://huggingface.co/datasets/factckbr/factckbr)
* **FactChecks.br** *(coleção de benchmarks de fact-checking em português)* $\rightarrow$ [GitHub](https://github.com/fake-news-UFG/FactChecks.br)
* **Lista Portuguese-NLP** *(catálogo com FakeRecogna, FakeTweetBr, FakeWhatsApp.Br, FactNews, etc.)* $\rightarrow$ [GitHub](https://github.com/ajdavidl/Portuguese-NLP)
* **FakeRecogna** $\rightarrow$ [GitHub](https://github.com/Gabriel-Lino-Garcia/FakeRecogna)
* **FakeRecogna (Hugging Face)** $\rightarrow$ [Hugging Face](https://huggingface.co/datasets/recogna-nlp/FakeRecogna)
* **FakeWhatsApp.Br** $\rightarrow$ [GitHub](https://github.com/cabrau/FakeWhatsApp.Br)
* **FakeTweetBr** $\rightarrow$ [Hugging Face](https://huggingface.co/datasets/ju-resplande/FakeTweetBr)
* **FactNews** *(fatualidade em nível de frase)* $\rightarrow$ [GitHub](https://github.com/franciellevargas/FactNews)
* **FakeNewsSet** $\rightarrow$ [GitHub](https://github.com/kamplus/FakeNewsSetGen)
* **Fakepedia-Corpus** $\rightarrow$ [GitHub](https://github.com/andersoncordeiro/Fakepedia-Corpus)
* **FKTC (Fake news Text Collections)** $\rightarrow$ [GitHub](https://github.com/GoloMarcos/FKTC)
* **Central de Fatos (Hugging Face)** $\rightarrow$ [Hugging Face](https://huggingface.co/datasets/fake-news-UFG/central_de_fatos)
* **Portuguese Fact-Checking (Hugging Face)** $\rightarrow$ [Hugging Face](https://huggingface.co/datasets/ju-resplande/portuguese-fact-checking)

### Referências internacionais *(inglês, úteis como benchmark/metodologia)*
* **Q_bias - AllSides Balanced News Dataset** *(viés esquerda/centro/direita)* $\rightarrow$ [GitHub](https://github.com/irgroup/Qbias)

### Melhores Datasets após análise
*Esses datasets foram escolhidos por terem o atributo data, possibilitando assim o filtro de notícias de 2018:*
* **Fake.Br Corpus** $\rightarrow$ https://github.com/roneysco/Fake.br-Corpus
* **FakeWhatsApp.Br** $\rightarrow$ https://github.com/cabrau/FakeWhatsApp.Br

---

## 5. Modelo de Machine Learning e Sprints Planejadas

### Sprint 1
* [ ] Criar/entregar *guiding questions*
* [ ] Decidir dataset a ser utilizado
* [ ] Pré-preparação dos dados
* [ ] Levantamento de requisitos
* [ ] Pesquisa sobre o modelo a ser construído
* [ ] Entregar processo investigativo
* [ ] Estruturação do Scrum do projeto

### Sprint 2 — Coleta e preparação dos dados de 2018
* [ ] Consolidar o(s) dataset(s) de 2018 escolhido(s) (ex: `Fake.Br Corpus`, `FakeWhatsApp.Br`, `FACTCK.BR`)
* [ ] Definir critérios de rotulagem e filtragem para o recorte político
* [ ] Limpeza e normalização textual (remoção de ruído, tokenização, padronização)
* [ ] Análise exploratória dos dados (distribuição de classes, tamanho médio dos textos, balanceamento)
* [ ] Separar dados em treino/validação/teste (*holdout* dentro do próprio período de 2018)
* [ ] Documentar o pipeline de pré-processamento

### Sprint 3 — Modelo baseline
* [ ] Implementar extração de *features* (TF-IDF)
* [ ] Treinar modelo *baseline* (Regressão Logística e/ou SVM) com os dados de 2018
* [ ] Validar o *baseline* no *holdout* de 2018 (acurácia, precisão, recall, $F_1$)
* [ ] Ajustar hiperparâmetros do *baseline*
* [ ] Documentar resultados preliminares

### Sprint 4 — Modelo avançado (BERTimbau)
* [ ] Preparar tokenização/embeddings compatíveis com o BERTimbau
* [ ] Realizar *fine-tuning* do BERTimbau com os dados de 2018
* [ ] Validar o modelo avançado no *holdout* de 2018
* [ ] Comparar desempenho *baseline* vs. modelo avançado (ainda dentro do período de 2018)
* [ ] Ajustes finais em ambos os modelos antes do teste de generalização

### Sprint 5 — Coleta de dados atuais e teste de generalização temporal
* [ ] Coletar e rotular um conjunto de notícias/desinformação política atual (2026)
* [ ] Aplicar os dois modelos (treinados em 2018, sem retreinar) sobre os dados atuais
* [ ] Medir a queda de desempenho de cada modelo (*concept drift*)
* [ ] Análise de erros: investigar se a queda vem de vocabulário novo, temas/atores políticos novos, ou mudança estrutural na desinformação
* [ ] Comparar como cada arquitetura (clássica vs. *transformer*) degrada

### Sprint 6 — Análise final, documentação e entrega
* [ ] Consolidar resultados e gerar visualizações comparativas (2018 vs. 2026, *baseline* vs. avançado)
* [ ] Discutir limitações do experimento (tamanho do dataset, critérios de rotulagem, recorte temático)
* [ ] Redigir o relatório final
* [ ] Preparar apresentação/slides
* [ ] Retrospectiva do Scrum e entrega final do projeto

---

## Referências
* [TCC UFC — Repositório Institucional](https://repositorio.ufc.br/bitstream/riufc/79291/1/2024_tcc_fisilvajunior.pdf)