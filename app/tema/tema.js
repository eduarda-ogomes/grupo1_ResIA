// Alternador de tema claro/escuro. O botão (.botao-tema) é desenhado pelo app.py na navbar;
// aqui só se aplica o tema no <html> e se liga o clique. A escolha fica no localStorage e vale
// entre páginas e recargas; sem escolha salva, segue o tema do sistema operacional.

const CHAVE = 'dossie-tema';
const sistema = window.matchMedia('(prefers-color-scheme: dark)');

function salvo() {
  try {
    return localStorage.getItem(CHAVE);
  } catch {
    return null;
  }
}

function salvar(tema) {
  try {
    localStorage.setItem(CHAVE, tema);
  } catch {
    // sem armazenamento (aba anônima, cookies bloqueados): o tema vale só até a próxima página
  }
}

function preferido() {
  return salvo() ?? (sistema.matches ? 'escuro' : 'claro');
}

function aplicar(tema) {
  document.documentElement.dataset.tema = tema;
  const escuro = tema === 'escuro';
  for (const botao of document.querySelectorAll('.botao-tema')) {
    botao.setAttribute('aria-pressed', String(escuro));
    botao.title = escuro ? 'Mudar para o modo claro' : 'Mudar para o modo escuro';
  }
}

// O Streamlit chama esta função a cada rerun; os ouvintes só são ligados na primeira vez
export default function () {
  aplicar(preferido());
  if (window.__dossieTemaLigado) return;
  window.__dossieTemaLigado = true;

  document.addEventListener('click', (evento) => {
    if (!evento.target.closest?.('.botao-tema')) return;
    const novo = document.documentElement.dataset.tema === 'escuro' ? 'claro' : 'escuro';
    salvar(novo);
    aplicar(novo);
  });

  sistema.addEventListener('change', () => {
    if (!salvo()) aplicar(preferido());
  });
}
