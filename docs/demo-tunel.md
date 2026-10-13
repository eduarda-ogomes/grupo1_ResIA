# Demo: app local acessível por outras pessoas

Para a demo, o sistema roda inteiro na máquina de quem apresenta (LM Studio, modelos e índice). Só o Streamlit fica acessível para os outros, pelo IP da rede local ou por um túnel gratuito. O LM Studio não fica exposto: só o app fala com ele, em `localhost:1234`, então a inferência continua local. Sem custo e sem mudar o código.

## Qual caminho usar

| Situação | Caminho | Seção |
| --- | --- | --- |
| Apresentação para uma sala | Compartilhar a tela, com o app em `http://localhost:8501` | 3a |
| Plateia no mesmo Wi-Fi | IP da máquina na rede local, sem túnel | 3b |
| Acesso de fora, com a máquina numa rede sua (casa, hotspot do celular) | Cloudflare Quick Tunnel | 3c |
| Acesso de fora, com a máquina na rede da instituição | localhost.run, que funciona mas é lento | 3d |

A rede da instituição restringe túneis: a porta 7844 (Cloudflare) está bloqueada, o firewall só aceita HTTPS na porta 443 (o SSH do Pinggy trava) e o serveo.net cai numa página "Violação de Política". O localhost.run passa, mas o plano gratuito limita a banda. Não tente driblar o bloqueio com outros serviços: é uma regra da rede. Se a banca precisar acessar de fora, peça a liberação à TI ou use uma rede sua.

Pré-requisitos: o ambiente da seção "Como Executar Localmente" do README (venv, índice em `chroma_data/`, LM Studio com o modelo baixado). Todos os comandos rodam na raiz do repositório.

## 1. LM Studio

Abra o LM Studio, carregue o modelo e inicie o servidor local na porta 1234. Pelo terminal:

```bash
~/.lmstudio/bin/lms server start
~/.lmstudio/bin/lms load qwen2.5-vl-7b-instruct
```

Confira se o modelo está carregado, com contexto de pelo menos 16384:

```bash
curl http://localhost:1234/v1/models
~/.lmstudio/bin/lms ps
```

O nome que aparece aqui é o valor de `LLM_MODEL` no passo seguinte.

## 2. Terminal 1: Streamlit

```bash
source venv/bin/activate
LLM_MODEL=qwen2.5-vl-7b-instruct streamlit run app/app.py --server.headless true --server.port 8501
```

Espere aparecer `Local URL: http://localhost:8501`. A porta fixa importa: sem `--server.port`, se a 8501 estiver ocupada (outro Streamlit esquecido aberto), o Streamlit sobe calado na 8502 e o túnel continua apontando para a 8501. Com ela, o Streamlit acusa a porta ocupada; nesse caso, ache e feche o processo antigo com `lsof -nP -iTCP:8501 -sTCP:LISTEN`.

Em outro terminal, mantenha o Mac acordado durante a demo (se ele dormir, o app e o túnel caem):

```bash
caffeinate -dims
```

## 3. Dar acesso

### 3a. Compartilhar a tela

Abra `http://localhost:8501` e projete. É o caminho mais confiável: não depende da rede.

### 3b. IP na rede local

Quem estiver no mesmo Wi-Fi abre o "Network URL" que o Streamlit mostra ao subir, por exemplo `http://192.168.0.250:8501`. Para descobrir o IP:

```bash
ipconfig getifaddr en0
```

Teste antes com o celular no mesmo Wi-Fi: algumas redes isolam os aparelhos entre si, e aí o endereço não abre.

### 3c. Cloudflare Quick Tunnel (fora da rede da instituição)

```bash
cloudflared tunnel --url http://localhost:8501
```

Em alguns segundos aparece uma URL `https://palavras-aleatorias.trycloudflare.com`, que é o link da demo. Ela muda a cada execução.

### 3d. localhost.run (na rede da instituição)

```bash
ssh -o ServerAliveInterval=30 -R 80:localhost:8501 nokey@localhost.run
```

A saída mostra um QR code e, logo abaixo, uma linha como `xxxxxxxx.lhr.life tunneled with tls termination, https://xxxxxxxx.lhr.life`. A URL dessa linha é o link da demo. Os outros links da saída (`admin.localhost.run`, documentação) não são o app. Se o localhost.run trocar o endereço durante a sessão, ele imprime uma linha nova: use sempre a última.

No plano gratuito a banda fica em torno de 40 KB/s (medido em 13/10/2026: 11 s para o JavaScript principal do Streamlit, de 443 KB). Na prática:

- o primeiro acesso leva de 1 a 2 minutos. Espere a página carregar; recarregar recomeça o download e gasta mais da cota;
- quando a cota estoura, o terminal mostra "your connection has been slowed by N seconds" e o app trava até a banda voltar;
- cada pessoa a mais abrindo o link piora para todos.

## 4. Aquecimento antes de apresentar

1. Abra o app pelo caminho que vai usar na demo.
2. Faça uma análise completa com qualquer texto. Na primeira, o Agente de Evidências carrega o BGE-M3 e o mDeBERTa, e a análise pode sair com `evidencias: timeout`. É esperado.
3. Espere um ou dois minutos e rode outra análise; agora deve sair completa.
4. Só então mande o link.

## 5. Encerrar

Ctrl+C no Streamlit, no túnel e no `caffeinate`. O link para de funcionar na hora.

## Problemas comuns

| Sintoma | O que fazer |
| --- | --- |
| "falha ao chamar o modelo" no app | LM Studio desligado ou `LLM_MODEL` com nome errado. Confira com `curl http://localhost:1234/v1/models`. |
| `cloudflared` repete "Failed to dial" e a página dá erro 1033 | A rede bloqueia a porta 7844. Use outra rede (3c) ou um dos outros caminhos. |
| "your connection has been slowed by N seconds" no terminal do localhost.run | É o limite de banda do plano gratuito. Espere a banda voltar, evite recarregar a página e limite quem abre o link. Para a demo, prefira 3a ou 3b. |
| Página "no tunnel here" do localhost.run | A URL não corresponde a um túnel ativo: é de uma sessão anterior, ou o `ssh` caiu. Pegue a última URL na saída do `ssh` (linha "tunneled with tls termination") ou rode o `ssh` de novo. |
| O `ssh` não conecta ou a URL não abre | Rode o `ssh` de novo. A URL muda a cada conexão: mande o link novo. |
| A página carrega mas fica girando | O túnel caiu ou a banda foi limitada. Veja a saída do `ssh` e reinicie o túnel se preciso. |
| O IP local não abre no celular | A rede isola os aparelhos. Compartilhe a tela (3a). |
| Análises lentas ou com timeout | Uma análise por vez: o LM Studio atende uma requisição de cada vez, e análises simultâneas entram em fila e estouram os limites dos ramos (240 s). |

## Cuidados

- Quem tiver o link do túnel consegue usar o app enquanto ele estiver de pé. Mande o link só na hora e encerre o túnel depois da demo.
- Na apresentação, o ideal é só quem apresenta operar o app.
- Use a máquina na tomada e numa rede estável.
