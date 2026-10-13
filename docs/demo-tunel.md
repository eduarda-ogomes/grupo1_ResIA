# Demo com túnel: app local acessível por uma URL pública

Para a demo, o sistema roda inteiro na máquina de quem apresenta (LM Studio, modelos e índice), e um túnel gratuito expõe só o Streamlit numa URL pública. O LM Studio não fica exposto: só o app fala com ele, em `localhost:1234`, então a inferência continua local. Sem custo e sem mudar o código.

Pré-requisitos: o ambiente da seção "Como Executar Localmente" do README (venv, índice em `chroma_data/`, LM Studio com o modelo baixado). Todos os comandos rodam na raiz do repositório. São 3 terminais.

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
LLM_MODEL=qwen2.5-vl-7b-instruct streamlit run app/app.py --server.headless true
```

Espere aparecer `Local URL: http://localhost:8501`.

## 3. Terminal 2: túnel

Na rede da instituição, use o [localhost.run](https://localhost.run) (SSH na porta 22, sem conta):

```bash
ssh -o ServerAliveInterval=30 -R 80:localhost:8501 nokey@localhost.run
```

A saída mostra um QR code e a URL pública, no formato `https://xxxxxxxx.lhr.life`. Esse é o link da demo.

Em redes sem bloqueio (em casa, por exemplo), o Cloudflare Quick Tunnel também serve:

```bash
cloudflared tunnel --url http://localhost:8501
```

A rede da instituição bloqueia a porta 7844, a única que o `cloudflared` usa para falar com a Cloudflare (tanto em QUIC quanto com `--protocol http2`). Por isso lá o `cloudflared` não conecta.

## 4. Terminal 3: manter o Mac acordado

```bash
caffeinate -dims
```

Se a máquina dormir, o túnel cai.

## 5. Aquecimento antes de apresentar

1. Abra a URL pública no navegador.
2. Faça uma análise completa com qualquer texto. Na primeira, o Agente de Evidências carrega o BGE-M3 e o mDeBERTa, e a análise pode sair com `evidencias: timeout`. É esperado.
3. Espere um ou dois minutos e rode outra análise; agora deve sair completa.
4. Só então mande o link.

## 6. Encerrar

Ctrl+C nos 3 terminais. O link para de funcionar na hora.

## Problemas comuns

| Sintoma | O que fazer |
| --- | --- |
| "falha ao chamar o modelo" no app | LM Studio desligado ou `LLM_MODEL` com nome errado. Confira com `curl http://localhost:1234/v1/models`. |
| O `ssh` não conecta ou a URL não abre | Rode o `ssh` de novo. A URL muda a cada conexão: mande o link novo. |
| `cloudflared` repete "Failed to dial" e a página dá erro 1033 | A rede bloqueia a porta 7844. Use o localhost.run (passo 3). |
| A página carrega mas fica girando | O túnel caiu. Reinicie o terminal 2. |
| Análises lentas ou com timeout | Uma análise por vez: o LM Studio atende uma requisição de cada vez, e análises simultâneas entram em fila e estouram os limites dos ramos (240 s). |
| Nada funciona | Plano B: abra `http://localhost:8501` na própria máquina e compartilhe a tela. |

## Cuidados

- Quem tiver o link consegue usar o app enquanto o túnel estiver de pé. Mande o link só na hora e encerre o túnel depois da demo.
- Na apresentação, o ideal é só quem apresenta operar o app.
- Use a máquina na tomada e numa rede estável.
