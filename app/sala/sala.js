// Sala dos agentes: a redação onde os cinco agentes do Dossiê trabalham durante a análise.
//
// Pixel art em SVG gerado aqui mesmo, a partir de grades de texto: cada letra é uma cor
// da paleta do personagem e "." é transparente. A técnica vem do AiOperationsRoom
// (github.com/mewsdev/AiOperationsRoom, licença MIT); personagens e cenário são deste projeto.
//
// O Python (src/progresso.py) manda o estado de cada agente a cada nó que termina. Aqui a
// sala anima as passagens: o Ingestor distribui a matéria, cada ramo leva a sua parte até
// a mesa do Sintetizador e o dossiê se fecha no fim. Cada fase dura um mínimo na tela,
// senão os agentes rápidos (Ingestor, Evidências) passariam sem ninguém ver.

const SVG = 'http://www.w3.org/2000/svg';
const LARGURA = 240;
const ALTURA = 116;
const TRABALHO_MINIMO_MS = 1600;
const VELOCIDADE = 46; // unidades da cena por segundo
const VOO_MS = 850;
const RAMOS = ['agente_evidencias', 'agente_texto', 'agente_socratico'];

const salas = new Map(); // id da análise -> Sala: sobrevive aos redesenhos do Streamlit

export default function (componente) {
  let dados = componente.data;
  if (typeof dados === 'string') dados = JSON.parse(dados);
  if (!dados || !dados.analise) return;

  let sala = salas.get(dados.analise);
  if (!sala) {
    sala = new Sala();
    salas.set(dados.analise, sala);
    for (const antiga of [...salas.keys()].slice(0, -3)) salas.delete(antiga);
  }
  const pai = componente.parentElement;
  for (const outra of pai.querySelectorAll(':scope > .sala')) if (outra !== sala.raiz) outra.remove();
  if (sala.raiz.parentNode !== pai) pai.appendChild(sala.raiz);
  sala.atualizar(dados);
}

// ---------------------------------------------------------------- desenho

function el(nome, atributos = {}, classe) {
  const e = document.createElementNS(SVG, nome);
  for (const [k, v] of Object.entries(atributos)) e.setAttribute(k, v);
  if (classe) e.setAttribute('class', classe);
  return e;
}

function html(nome, classe, texto) {
  const e = document.createElement(nome);
  if (classe) e.className = classe;
  if (texto !== undefined) e.textContent = texto;
  return e;
}

// Uma grade de texto vira um <path> por cor, com as sequências da mesma cor juntas.
function pixels(linhas, paleta, dx = 0, dy = 0, classe) {
  const g = el('g', {}, classe);
  const porCor = new Map();
  linhas.forEach((linha, y) => {
    let x = 0;
    while (x < linha.length) {
      const cor = paleta[linha[x]];
      if (!cor) { x++; continue; }
      let fim = x;
      while (fim < linha.length && paleta[linha[fim]] === cor) fim++;
      porCor.set(cor, (porCor.get(cor) || '') + `M${x + dx} ${y + dy}h${fim - x}v1h${x - fim}z`);
      x = fim;
    }
  });
  for (const [cor, d] of porCor) g.appendChild(el('path', { d, fill: cor }));
  return g;
}

function bloco(g, x, y, w, h, cor) {
  g.appendChild(el('rect', { x, y, width: w, height: h, fill: cor }));
}

// Sobrepõe linhas: "." mantém o que já estava.
function compor(base, ...camadas) {
  const linhas = [...base];
  for (const camada of camadas) {
    for (const [i, linha] of Object.entries(camada)) {
      const antes = linhas[i];
      linhas[i] = [...linha].map((c, x) => (c === '.' ? antes[x] : c)).join('');
    }
  }
  return linhas;
}

// ---------------------------------------------------------------- personagens

const CONTORNO = '#2B2024';

// 12 x 20; as duas primeiras linhas ficam para chapéus e penteados.
const CORPO = [
  '............',
  '............',
  '...kkkkkk...',
  '..khhhhhhk..',
  '..khsssshk..',
  '..ksessesk..',
  '..kssssssk..',
  '..ksssmssk..',
  '...kssssk...',
  '..kccwwcck..',
  '.kcccccccck.',
  'kccCccccCcck',
  'kccCccccCcck',
  'kscCccccCcsk',
  '.kkppppppkk.',
  '..kppkkppk..',
  '..kppkkppk..',
  '..kppkkppk..',
  '.kbbbkkbbbk.',
  '.kkkk..kkkk.',
];
const DIGITAR_A = { 13: 'kccsccccscck' };
const DIGITAR_B = { 12: 'kcsCccccCsck', 13: 'kccCccccCcck' };
const PASSO = { 16: '.kppk..kppk.', 17: '.kppk..kppk.', 18: 'kbbbk..kbbbk', 19: 'kkkk....kkkk' };
const OLHOS_FECHADOS = { 5: '....s..s....' };

const PERSONAGENS = {
  ingestor: {
    nome: 'Ingestor', papel: 'Recorta a matéria', cor: '#C9A86A',
    paleta: { h: '#4A3426', s: '#E8B98E', c: '#C9A86A', C: '#A68548', w: '#F4EFE6', p: '#4D4F5C', b: '#2E2A2B', a: '#5B4A3D', r: '#7C2128' },
    extras: { 0: '....kkkk....', 1: '...kaaaak...', 2: '...krrwak...', 3: '.kkaaaaaakk.' },
    icone: ['ggggggg', '.......', 'gggg.gg', '.......', 'ggggg..'],
  },
  agente_evidencias: {
    nome: 'Evidências', papel: 'Consulta as checagens', cor: '#7A6249',
    paleta: { h: '#2F2523', s: '#C98E64', c: '#7A6249', C: '#5E4A36', w: '#EDE6DA', p: '#3B3A40', b: '#241F20', a: '#8B7355', A: '#6B5640' },
    extras: { 1: '....kkkk....', 2: '...kaAaAk...', 3: '..kaaaaaak..', 4: '..kA....Ak..' },
    icone: ['.kkk...', 'k...k..', '.kkk...', '....k..', '.....k.'],
  },
  agente_texto: {
    nome: 'Texto', papel: 'Lê como o texto argumenta', cor: '#B0303A',
    paleta: { h: '#1F1A1C', s: '#8D5A3B', c: '#F2EFEA', C: '#D8D1C6', w: '#FFFFFF', p: '#2F3A4A', b: '#2B2024', g: '#7C2128', r: '#B0303A' },
    extras: {
      3: '.khhhhhhhhk.', 4: '.kh......hk.', 5: '.khgeggeghk.', 6: '.kh......hk.', 7: '.kh......hk.',
      8: '.khk....khk.', 10: '.....rr.....', 11: '.....rr.....', 12: '.....rr.....',
    },
    icone: ['ggggggg', '.......', 'ggrrrgg', '.......', 'gggg...'],
  },
  agente_socratico: {
    nome: 'Socrático', papel: 'Formula perguntas', cor: '#6E8B4E',
    paleta: { h: '#E4DFD6', s: '#C68B5E', c: '#F4F1EA', C: '#D9D1C2', w: '#F4F1EA', p: '#F4F1EA', b: '#8B6A4A', W: '#ECE8E1', g: '#6E8B4E', r: '#7C2128' },
    extras: {
      3: '..kggggggk..', 6: '..kWssssWk..', 7: '..kWWmmWWk..', 8: '...kWWWWk...', 9: '...kWWWWk...',
      10: '....kWWkr...', 11: '.......r....', 12: '......r.....',
      15: '..kcCccCck..', 16: '..kcCccCck..', 17: '..kcccccck..',
    },
    icone: ['..kkk..', '.....k.', '...kk..', '.......', '...k...'],
  },
  sintetizador: {
    nome: 'Sintetizador', papel: 'Monta o dossiê', cor: '#7C2128',
    paleta: { h: '#7A3E2A', s: '#F2C9A0', c: '#7C2128', C: '#5A161C', w: '#F4EFE6', p: '#3A3238', b: '#1F1A1C', y: '#D9B45A' },
    extras: { 0: '.....kk.....', 1: '....khhk....', 11: '.....y......' },
    icone: ['.kk....', 'kkkkkkk', 'kyyyyyk', 'kyyyyyk', 'kkkkkkk'],
  },
};

const COMUM = { k: CONTORNO, e: CONTORNO, m: '#B5574B' };

function quadros(def) {
  const paleta = { ...COMUM, ...def.paleta };
  const vestir = (...poses) => compor(CORPO, ...poses, def.extras);
  return {
    parado: pixels(vestir(), paleta, 0, 0, 'q q-parado'),
    digitarA: pixels(vestir(DIGITAR_A), paleta, 0, 0, 'q q-digitarA'),
    digitarB: pixels(vestir(DIGITAR_B), paleta, 0, 0, 'q q-digitarB'),
    andar: pixels(vestir(PASSO), paleta, 0, 0, 'q q-andar'),
    piscar: pixels(compor(vestir(), OLHOS_FECHADOS).map((l, i) => (i === 5 ? l : '')), paleta, 0, 0, 'piscar'),
  };
}

// ---------------------------------------------------------------- objetos da cena

const MADEIRA = { k: '#4A3426', t: '#C79A66', T: '#A97B4B', f: '#8E6440', D: '#6B4A2E' };
const BRANCO = { k: CONTORNO, w: '#FFFDF8', g: '#C9C2B8', r: '#B0303A', y: '#D9B45A', a: '#E2C98F', A: '#C9AE70' };

function mesa(w) {
  const linhas = ['k'.repeat(w), 'k' + 't'.repeat(w - 2) + 'k', 'k' + 'T'.repeat(w - 2) + 'k'];
  for (let i = 3; i < 8; i++) {
    const meio = Math.floor((w - 2) / 2) - 1;
    const puxador = i === 5 ? 'f'.repeat(meio) + 'DD' + 'f'.repeat(w - 4 - meio) : 'f'.repeat(w - 2);
    linhas.push('k' + puxador + 'k');
  }
  linhas.push('k'.repeat(w));
  return linhas;
}

const PULPITO = [
  'kkkkkkkkkkkkkk',
  'kttttttttttttk',
  'kTTTTTTTTTTTTk',
  '...kffffffk...',
  '...kfDDDDfk...',
  '...kffffffk...',
  '...kffffffk...',
  '...kffffffk...',
  '..kffffffffk..',
  '.kkkkkkkkkkkk.',
];

const PAPEL = ['kkkkk', 'kwwwk', 'kgggk', 'kwwwk', 'kgggk', 'kkkkk'];
const PASTA_ABERTA = ['kkkkkkkkkkkkkk', 'kaaaaaakaaaaak', 'kAAAAAAkAAAAAk'];
const PASTA_FECHADA = ['.kkkkkkkkkkkk.', 'krrrrrrrrrrrrk', 'krrrwwwwwwrrrk', 'krrrrrryrrrrrk', 'kkkkkkkkkkkkkk'];
const BALAO = ['.kkkkkkkkk.', 'kwwwwwwwwwk', 'kwwwwwwwwwk', 'kwwwwwwwwwk', 'kwwwwwwwwwk', 'kwwwwwwwwwk', '.kkwkkkkkk.', '..kk.......'];
const SELO_OK = ['.kkkkk.', 'kgggggk', 'kggggwk', 'kwggwgk', 'kgwwggk', 'kgggggk', '.kkkkk.'];
const SELO_ALERTA = ['.kkkkk.', 'kaawaak', 'kaawaak', 'kaawaak', 'kaaaaak', 'kaawaak', '.kkkkk.'];

// Onde cada agente fica; `mesa` é o tampo, e as mãos do personagem ficam na altura dele.
const CENA = {
  ingestor: { x: 16, y: 83, mesa: { x: 8, y: 96, w: 28 } },
  agente_evidencias: { x: 68, y: 63, mesa: { x: 60, y: 76, w: 28 }, saida: 90, chegada: { x: 163, y: 83 } },
  agente_texto: { x: 112, y: 63, mesa: { x: 104, y: 76, w: 28 }, saida: 134, chegada: { x: 166, y: 85 } },
  agente_socratico: { x: 151, y: 63, pulpito: { x: 150, y: 76 }, saida: 166, chegada: { x: 169, y: 84 } },
  sintetizador: { x: 201, y: 83, mesa: { x: 182, y: 96, w: 40 } },
};
const PASTA = { x: 186, y: 93 };
const CORREDOR = 84;

// ---------------------------------------------------------------- a sala

class Sala {
  constructor() {
    this.reduzido = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.agentes = {};
    this.voos = [];
    this.paginas = 0;
    this.primeira = true;
    this.situacao = '';
    this.montar();
  }

  montar() {
    this.raiz = html('div', 'sala');
    this.raiz.setAttribute('role', 'group');
    this.raiz.setAttribute('aria-label', 'Sala dos agentes: acompanhamento da análise');

    const topo = html('div', 'sala-topo');
    topo.append(html('span', 'sala-titulo', 'SALA DOS AGENTES'));
    this.textoSituacao = html('span', 'sala-situacao', 'Análise em andamento');
    topo.append(this.textoSituacao);

    const cena = html('div', 'sala-cena');
    this.svg = el('svg', { viewBox: `0 0 ${LARGURA} ${ALTURA}`, 'aria-hidden': 'true', focusable: 'false' });
    cena.append(this.svg);

    // Balão de fala do Sintetizador no fim. Em HTML, e não em pixels, para o texto continuar
    // legível no celular; a posição é a da cabeça dele, em % da cena (o CSS usa as variáveis).
    const fala = html('div', 'fala-sintetizador', 'Análise concluída');
    fala.setAttribute('aria-hidden', 'true'); // o topo da sala já anuncia "Dossiê pronto"
    fala.style.setProperty('--x', `${((CENA.sintetizador.x + 6) / LARGURA) * 100}%`);
    fala.style.setProperty('--y', `${((ALTURA - CENA.sintetizador.y + 2) / ALTURA) * 100}%`);
    cena.append(fala);

    this.legenda = html('ol', 'sala-legenda');
    this.anuncio = html('p', 'sala-anuncio');
    this.anuncio.setAttribute('aria-live', 'polite');

    this.raiz.append(topo, cena, this.legenda, this.anuncio);

    this.fundo();
    this.camada = el('g');      // objetos ordenados pela profundidade (pé mais baixo na frente)
    this.ceu = el('g');         // papéis voando, sempre por cima
    this.svg.append(this.camada, this.ceu);
    this.objetos = [];
    this.moveis();
    for (const id of Object.keys(PERSONAGENS)) this.criarAgente(id);
    this.ordenar(true);
  }

  fundo() {
    const g = el('g');
    bloco(g, 0, 0, LARGURA, 60, '#F3ECE2');                    // parede
    bloco(g, 0, 0, LARGURA, 2, '#E6DACB');
    bloco(g, 0, 44, LARGURA, 14, '#ECE2D4');                   // lambri
    for (let x = 6; x < LARGURA; x += 24) bloco(g, x, 46, 18, 10, '#E4D8C7');
    bloco(g, 0, 58, LARGURA, 3, '#B89F82');                    // rodapé
    bloco(g, 0, 61, LARGURA, ALTURA - 61, '#E8D9C3');           // assoalho
    for (let y = 67, i = 0; y < ALTURA; y += 7, i++) {
      bloco(g, 0, y, LARGURA, 1, '#DCC9AE');
      for (let x = (i % 2) * 19; x < LARGURA; x += 38) bloco(g, x, y - 6, 1, 6, '#DFCDB3');
    }

    // janela
    bloco(g, 12, 8, 34, 28, '#B89F82');
    bloco(g, 14, 10, 30, 24, '#DCE8EF');
    bloco(g, 14, 26, 30, 8, '#E9F0F3');
    bloco(g, 18, 14, 8, 2, '#FFFFFF'); bloco(g, 16, 16, 12, 2, '#FFFFFF');
    bloco(g, 28, 10, 2, 24, '#B89F82'); bloco(g, 14, 21, 30, 2, '#B89F82');
    bloco(g, 10, 36, 38, 2, '#A68A6C');

    // quadro de investigação: notas presas e o fio vermelho
    bloco(g, 88, 6, 62, 34, '#8E6440');
    bloco(g, 90, 8, 58, 30, '#C99C6A');
    const notas = [[94, 11, '#FFFDF8'], [110, 20, '#F2E3A0'], [124, 10, '#F3C7C2'], [138, 22, '#FFFDF8'], [100, 27, '#F3C7C2']];
    const fio = el('polyline', {
      points: notas.map(([x, y]) => `${x + 4},${y + 1}`).join(' '),
      fill: 'none', stroke: '#7C2128', 'stroke-width': 0.6,
    });
    g.append(fio);
    for (const [x, y, cor] of notas) {
      bloco(g, x, y, 8, 7, cor);
      bloco(g, x + 1, y + 3, 6, 1, '#C9C2B8'); bloco(g, x + 1, y + 5, 4, 1, '#C9C2B8');
      bloco(g, x + 3, y, 2, 2, '#7C2128');
    }

    // relógio
    g.append(pixels(['..kkkk..', '.kwwwwk.', 'kwwkwwwk', 'kwwkwwwk', 'kwwkkkwk', 'kwwwwwwk', '.kwwwwk.', '..kkkk..'],
      { k: '#6B4A2E', w: '#FFFDF8' }, 166, 14));

    // estante
    bloco(g, 202, 8, 32, 52, '#8E6440');
    const cores = ['#7C2128', '#3F5E7A', '#C99A3B', '#4E6E58', '#B5574B', '#5B4A3D', '#E2C98F'];
    for (let p = 0, y = 10; p < 4; p++, y += 12) {
      bloco(g, 204, y, 28, 10, '#6B4A2E');
      for (let x = 205, i = p; x < 230; i++) {
        const largura = 2 + (i % 3 === 0 ? 1 : 0);
        const altura = 6 + ((i * 7) % 4);
        bloco(g, x, y + 10 - altura, largura, altura, cores[i % cores.length]);
        x += largura + (i % 5 === 0 ? 2 : 0);
      }
      bloco(g, 202, y + 10, 32, 2, '#A97B4B');
    }
    this.svg.append(g);
  }

  adicionar(g, profundidade) {
    const obj = { g, profundidade: () => profundidade };
    this.objetos.push(obj);
    return obj;
  }

  moveis() {
    // arquivo de fichas atrás do Agente de Evidências (o ChromaDB)
    const arquivo = el('g');
    bloco(arquivo, 44, 50, 14, 26, '#4A3426');
    bloco(arquivo, 45, 51, 12, 24, '#8A9A8E');
    for (let y = 53; y < 74; y += 7) {
      bloco(arquivo, 46, y, 10, 6, '#7A8A7E');
      bloco(arquivo, 49, y + 1, 4, 2, '#FFFDF8');
      bloco(arquivo, 50, y + 4, 2, 1, '#4A3426');
    }
    this.adicionar(arquivo, 76);

    for (const [id, pos] of Object.entries(CENA)) {
      const g = el('g');
      if (pos.mesa) g.append(pixels(mesa(pos.mesa.w), MADEIRA, pos.mesa.x, pos.mesa.y));
      if (pos.pulpito) {
        g.append(pixels(PULPITO, MADEIRA, pos.pulpito.x, pos.pulpito.y));
        g.append(pixels(['ywwwwwwy'], BRANCO, pos.pulpito.x + 3, pos.pulpito.y - 1));
      }
      const { x, y } = pos.mesa || pos.pulpito;
      if (id === 'ingestor') {
        g.append(pixels(['kkkkkkkk', 'kwgwggwk', 'kkkkkkkk', 'kwwgwgwk'], BRANCO, x + 2, y - 4));
        g.append(pixels(['kkkk..', 'krrkkk', 'krrk.k', 'krrkkk', 'kkkk..'], BRANCO, x + 21, y - 5)); // caneca
      }
      if (id === 'agente_evidencias') {
        g.append(pixels(['kkkkkk', 'kwwwgk', 'kgwwwk'], { ...BRANCO, g: '#8A9A8E' }, x + 20, y - 3));
      }
      if (id === 'agente_texto') {
        g.append(pixels(['wwwwwww', 'wrrwwgw'], BRANCO, x + 2, y - 1));
        g.append(pixels(['....r', '...r.', '..k..'], BRANCO, x + 21, y - 3));
      }
      if (id === 'sintetizador') {
        this.pastaAberta = pixels(PASTA_ABERTA, BRANCO, PASTA.x, PASTA.y, 'pasta-aberta');
        this.pilha = el('g', {}, 'pilha');
        this.pastaFechada = pixels(PASTA_FECHADA, { ...BRANCO, r: '#7C2128' }, PASTA.x, PASTA.y - 2, 'pasta-fechada');
        this.brilhos = el('g', {}, 'brilhos');
        for (const [bx, by, atraso] of [[183, 86, 0], [201, 84, 0.5], [195, 90, 1]]) {
          const b = pixels(['.w.', 'www', '.w.'], { w: '#D9B45A' }, bx, by, 'brilho');
          b.style.animationDelay = `${atraso}s`;
          this.brilhos.append(b);
        }
        g.append(this.pastaAberta, this.pilha, this.pastaFechada, this.brilhos);
        g.append(pixels(['kkkkkk', 'kwwwwk', 'kkkkkk'], BRANCO, x + 33, y - 3)); // bandeja
      }
      this.adicionar(g, y + 9);
    }

    // vaso no canto
    this.adicionar(pixels(
      ['..g.g...', '.gggg.g.', 'gGggGgg.', '.gGggG..', '..gggg..', '.kkkkkk.', '.kttttk.', '..kttk..', '..kkkk..'],
      { g: '#5E8C5A', G: '#4A7348', k: '#6B3B2E', t: '#B5574B' }, 228, 100), 109);
  }

  criarAgente(id) {
    const def = PERSONAGENS[id];
    const pos = CENA[id];
    const g = el('g', { 'data-id': id }, 'pessoa');
    const corpo = el('g', {}, 'corpo');
    const q = quadros(def);
    corpo.append(pixels(['..kkkkkkkk..'], { k: 'rgba(43,32,36,.16)' }, 0, 20, 'sombra'),
      q.parado, q.digitarA, q.digitarB, q.andar, q.piscar);
    q.piscar.style.animationDelay = `${(Object.keys(this.agentes).length * 1.3) % 4}s`;
    const papel = pixels(PAPEL, BRANCO, 9, 11, 'papel-na-mao');
    corpo.append(papel);

    const balao = el('g', {}, 'balao');
    balao.append(pixels(BALAO, BRANCO, 7, -9), pixels(def.icone, { ...BRANCO, k: CONTORNO, g: '#8C8279', y: '#E2C98F' }, 9, -8));
    const seloOk = pixels(SELO_OK, { k: CONTORNO, g: '#3F7D4E', w: '#FFFDF8' }, 9, -6, 'selo selo-ok');
    const seloAviso = pixels(SELO_ALERTA, { k: CONTORNO, a: '#C98A1B', w: '#FFFDF8' }, 9, -6, 'selo selo-aviso');
    const seloErro = pixels(SELO_ALERTA, { k: CONTORNO, a: '#7C2128', w: '#FFFDF8' }, 9, -6, 'selo selo-erro');
    g.append(corpo, balao, seloOk, seloAviso, seloErro);

    const item = html('li', 'agente');
    const nome = html('span', 'agente-nome');
    const cor = html('span', 'agente-cor');
    cor.style.background = def.cor;
    nome.append(cor, document.createTextNode(def.nome));
    const estado = html('span', 'agente-estado');
    const rotulo = html('span', 'agente-rotulo');
    const tempo = html('span', 'agente-tempo');
    tempo.setAttribute('aria-hidden', 'true');
    estado.append(rotulo, tempo);
    item.append(nome, html('span', 'agente-papel', def.papel), estado);
    this.legenda.append(item);

    const ag = {
      id, def, g, corpo, item, rotulo, tempo,
      x: pos.x, y: pos.y, olhandoEsquerda: false,
      fase: 'aguardando', desde: 0, alvo: 'aguardando', segundos: null, avisos: [],
      recebeu: false, entregou: false, rota: null,
    };
    this.agentes[id] = ag;
    this.objetos.push({ g, profundidade: () => ag.y + 19 });
    this.posicionar(ag);
    this.pose(ag, 'parado');
    this.mostrarFase(ag);
  }

  // ------------------------------------------------------------ dados vindos do Python

  atualizar(dados) {
    for (const a of dados.agentes) {
      const ag = this.agentes[a.id];
      if (!ag) continue;
      ag.alvo = a.estado;
      ag.segundos = a.segundos;
      ag.avisos = a.avisos || [];
    }
    this.interrompida = !!dados.interrompida;
    if (this.primeira) {
      this.primeira = false;
      // Montada depois que a análise acabou (página recarregada): mostra o fim, sem replay.
      if (dados.concluida) this.pularParaOFim();
    }
    for (const ag of Object.values(this.agentes)) this.mostrarFase(ag);
    this.acordar();
  }

  pularParaOFim() {
    for (const ag of Object.values(this.agentes)) {
      ag.fase = 'concluido';
      ag.recebeu = ag.entregou = true;
    }
    this.paginas = RAMOS.length;
    this.desenharPilha();
    this.raiz.dataset.dossie = 'fechado';
  }

  acordar() {
    if (this.raf || this.espera) return;
    this.raf = requestAnimationFrame((t) => this.quadro(t));
  }

  quadro(agora) {
    this.raf = null;
    this.espera = null;
    if (!this.raiz.isConnected) return; // saiu da página; volta no próximo `atualizar`
    const dt = this.ultimo ? Math.min(agora - this.ultimo, 100) : 0;
    this.ultimo = agora;

    this.avancar(agora);
    const mexeu = this.mover(agora, dt);
    this.atualizarLegenda(agora);

    const pendente = Object.values(this.agentes).some((ag) => ['trabalhando', 'entregando'].includes(ag.fase) || ag.rota)
      || Object.values(this.agentes).some((ag) => ag.fase === 'aguardando' && ag.alvo !== 'aguardando');
    if (mexeu || this.voos.length) {
      this.raf = requestAnimationFrame((t) => this.quadro(t));
    } else if (pendente) {
      this.ultimo = null;
      this.espera = setTimeout(() => { this.espera = null; this.acordar(); }, 200);
    } else {
      this.ultimo = null;
    }
  }

  // ------------------------------------------------------------ regras das fases

  avancar(agora) {
    const A = this.agentes;
    const ing = A.ingestor;
    const sin = A.sintetizador;
    const ramos = RAMOS.map((id) => A[id]);
    const cumpriu = (ag) => agora - ag.desde >= TRABALHO_MINIMO_MS;

    if (ing.fase === 'aguardando') this.mudar(ing, 'trabalhando', agora);
    if (ing.fase === 'trabalhando') {
      if (ing.alvo === 'concluido' && cumpriu(ing)) {
        this.mudar(ing, 'entregando', agora);
        this.distribuir(agora);
      } else if (ing.alvo === 'interrompido') {
        this.mudar(ing, 'interrompido', agora);
      }
    }

    for (const r of ramos) {
      if (r.fase === 'aguardando' && r.recebeu && r.alvo !== 'aguardando') this.mudar(r, 'trabalhando', agora);
      if (r.fase === 'trabalhando') {
        if (r.alvo === 'concluido' && cumpriu(r)) {
          this.mudar(r, 'entregando', agora);
          this.levar(r);
        } else if (r.alvo === 'interrompido') {
          this.mudar(r, 'interrompido', agora);
        }
      }
    }

    if (sin.fase === 'aguardando' && sin.alvo !== 'aguardando' && ramos.every((r) => r.entregou)) {
      this.mudar(sin, 'trabalhando', agora);
    }
    if (sin.fase === 'trabalhando') {
      if (sin.alvo === 'concluido' && cumpriu(sin)) {
        this.mudar(sin, 'concluido', agora);
        this.raiz.dataset.dossie = 'fechado';
      } else if (sin.alvo === 'interrompido') {
        this.mudar(sin, 'interrompido', agora);
      }
    }
  }

  mudar(ag, fase, agora) {
    ag.fase = fase;
    ag.desde = agora;
    if (fase === 'trabalhando') this.pose(ag, 'digitando');
    else if (!ag.rota) this.pose(ag, 'parado');
    this.mostrarFase(ag);
    const [rotulo] = this.rotulo(ag, agora);
    this.anuncio.textContent = `${ag.def.nome}: ${rotulo.toLowerCase()}.`;
  }

  // O Ingestor manda uma cópia da matéria para cada ramo.
  distribuir(agora) {
    const ing = this.agentes.ingestor;
    const de = { x: CENA.ingestor.mesa.x + 10, y: CENA.ingestor.mesa.y - 6 };
    let faltam = RAMOS.length;
    RAMOS.forEach((id, i) => {
      const pos = CENA[id];
      const alvo = pos.mesa || pos.pulpito;
      this.voar(de, { x: alvo.x + 6, y: alvo.y - 5 }, agora + i * 160, () => {
        this.agentes[id].recebeu = true;
        if (--faltam === 0) this.mudar(ing, 'concluido', performance.now());
      });
    });
  }

  // O ramo leva a sua parte até a mesa do Sintetizador, entrega e volta.
  levar(ag) {
    const pos = CENA[ag.id];
    const ida = [
      { x: pos.saida, y: pos.y },
      { x: pos.saida, y: CORREDOR },
      { x: pos.chegada.x, y: CORREDOR },
      pos.chegada,
    ];
    const volta = [...ida].reverse().slice(1).concat([{ x: pos.x, y: pos.y }]);
    ag.corpo.classList.add('carregando');
    this.andar(ag, ida, () => {
      ag.corpo.classList.remove('carregando');
      ag.olhandoEsquerda = false;
      this.posicionar(ag);
      const agora = performance.now();
      this.voar({ x: ag.x + 9, y: ag.y + 11 }, { x: PASTA.x + 8, y: PASTA.y - 5 }, agora, () => {
        this.paginas += 1;
        this.desenharPilha();
      });
      ag.entregou = true;
      this.mudar(ag, 'concluido', agora);
      this.andar(ag, volta, () => { ag.olhandoEsquerda = false; this.posicionar(ag); });
    });
  }

  desenharPilha() {
    this.pilha.replaceChildren();
    for (let i = 0; i < Math.min(this.paginas, 3); i++) {
      this.pilha.append(pixels(['kkkkk', 'kwwwk'], BRANCO, PASTA.x + 8, PASTA.y - 2 - i * 2));
    }
  }

  // ------------------------------------------------------------ movimento

  andar(ag, pontos, aoChegar) {
    if (this.reduzido) {
      const fim = pontos[pontos.length - 1];
      ag.x = fim.x; ag.y = fim.y;
      ag.rota = null;
      this.posicionar(ag);
      this.ordenar();
      aoChegar();
      return;
    }
    ag.rota = { pontos: [...pontos], aoChegar };
    this.pose(ag, 'andando');
  }

  voar(de, para, inicio, aoPousar) {
    const g = pixels(PAPEL, BRANCO, 0, 0, 'papel-voando');
    g.style.display = 'none';
    this.ceu.append(g);
    this.voos.push({ g, de, para, inicio, duracao: this.reduzido ? 0 : VOO_MS, aoPousar });
  }

  mover(agora, dt) {
    let mexeu = false;
    for (const ag of Object.values(this.agentes)) {
      if (!ag.rota) continue;
      mexeu = true;
      let passo = (VELOCIDADE * dt) / 1000;
      while (passo > 0 && ag.rota.pontos.length) {
        const alvo = ag.rota.pontos[0];
        const dx = alvo.x - ag.x;
        const dy = alvo.y - ag.y;
        const dist = Math.hypot(dx, dy);
        if (dx !== 0) ag.olhandoEsquerda = dx < 0;
        if (dist <= passo) {
          ag.x = alvo.x; ag.y = alvo.y;
          passo -= dist;
          ag.rota.pontos.shift();
        } else {
          ag.x += (dx / dist) * passo;
          ag.y += (dy / dist) * passo;
          passo = 0;
        }
      }
      this.posicionar(ag);
      if (!ag.rota.pontos.length) {
        const { aoChegar } = ag.rota;
        ag.rota = null;
        this.pose(ag, ag.fase === 'trabalhando' ? 'digitando' : 'parado');
        aoChegar();
      }
    }
    if (mexeu) this.ordenar();

    this.voos = this.voos.filter((v) => {
      if (agora < v.inicio) return true;
      const t = v.duracao ? Math.min((agora - v.inicio) / v.duracao, 1) : 1;
      const x = v.de.x + (v.para.x - v.de.x) * t;
      const y = v.de.y + (v.para.y - v.de.y) * t - Math.sin(Math.PI * t) * 14;
      v.g.style.display = '';
      v.g.setAttribute('transform', `translate(${Math.round(x)} ${Math.round(y)})`);
      if (t < 1) return true;
      v.g.remove();
      v.aoPousar();
      return false;
    });
    return mexeu;
  }

  posicionar(ag) {
    ag.g.setAttribute('transform', `translate(${Math.round(ag.x)} ${Math.round(ag.y)})`);
    ag.corpo.setAttribute('transform', ag.olhandoEsquerda ? 'matrix(-1 0 0 1 12 0)' : '');
  }

  pose(ag, pose) {
    ag.g.dataset.pose = pose;
  }

  ordenar(forcar = false) {
    const ordem = [...this.objetos].sort((a, b) => a.profundidade() - b.profundidade());
    const atual = [...this.camada.children];
    if (!forcar && ordem.every((o, i) => o.g === atual[i])) return;
    for (const o of ordem) this.camada.append(o.g);
  }

  // ------------------------------------------------------------ legenda e selos

  mostrarFase(ag) {
    ag.g.dataset.fase = ag.fase;
    ag.item.dataset.fase = ag.fase;
    const comAviso = ag.avisos.length > 0;
    ag.item.classList.toggle('com-aviso', comAviso);
    if (comAviso) ag.item.title = ag.avisos.join('\n');
    else ag.item.removeAttribute('title');
    ag.g.dataset.selo = ag.fase === 'interrompido' ? 'erro'
      : ag.fase === 'concluido' ? (comAviso ? 'aviso' : 'ok') : '';
  }

  rotulo(ag, agora) {
    switch (ag.fase) {
      case 'trabalhando':
        return ['Trabalhando', ` · ${Math.floor((agora - ag.desde) / 1000)} s`];
      case 'entregando':
        return [ag.id === 'ingestor' ? 'Distribuindo a matéria' : 'Levando ao Sintetizador', ''];
      case 'concluido': {
        const tempo = ag.segundos == null ? ''
          : ag.segundos < 0.05 ? ' · < 0,1 s' : ` · ${ag.segundos.toFixed(1).replace('.', ',')} s`;
        if (ag.id === 'sintetizador') return ['Dossiê pronto', tempo];
        return [ag.avisos.length ? 'Concluído com aviso' : 'Concluído', tempo];
      }
      case 'interrompido':
        return ['Interrompido', ''];
      default:
        return ['Aguardando', ''];
    }
  }

  atualizarLegenda(agora) {
    for (const ag of Object.values(this.agentes)) {
      const [rotulo, tempo] = this.rotulo(ag, agora);
      if (ag.rotulo.textContent !== rotulo) ag.rotulo.textContent = rotulo;
      if (ag.tempo.textContent !== tempo) ag.tempo.textContent = tempo;
    }
    const situacao = this.agentes.sintetizador.fase === 'concluido' ? 'pronta'
      : this.interrompida ? 'interrompida' : 'andamento';
    if (situacao !== this.situacao) {
      this.situacao = situacao;
      this.raiz.dataset.situacao = situacao;
      this.textoSituacao.textContent = {
        pronta: 'Dossiê pronto', interrompida: 'Análise interrompida', andamento: 'Análise em andamento',
      }[situacao];
    }
  }
}
