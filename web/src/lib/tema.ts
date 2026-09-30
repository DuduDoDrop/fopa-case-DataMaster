/**
 * Tema claro ou escuro. A escolha fica neste navegador (`fopa-tema`); sem escolha guardada, vale
 * a do sistema. O tema mora em `<html data-tema>`, que o CSS lê — o `index.html` aplica o mesmo antes da primeira
 * pintura, para a página não piscar branca.
 */
import { useSyncExternalStore } from 'react';

export type Tema = 'claro' | 'escuro';

const CHAVE = 'fopa-tema';

function guardado(): Tema | null {
  try {
    const v = localStorage.getItem(CHAVE);
    return v === 'claro' || v === 'escuro' ? v : null;
  } catch {
    return null;
  }
}

/** A escolha guardada; senão, a preferência do sistema. */
export function temaInicial(): Tema {
  const g = guardado();
  if (g) return g;
  try {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro';
  } catch {
    return 'claro';
  }
}

export function aplicarTema(t: Tema) {
  document.documentElement.dataset.tema = t;
}

const ouvintes = new Set<() => void>();

/** Aplica, guarda e avisa quem desenha com o tema (o botão, os gráficos); sem armazenamento, vale até recarregar. */
export function escolherTema(t: Tema) {
  aplicarTema(t);
  try {
    localStorage.setItem(CHAVE, t);
  } catch {
    /* sem armazenamento */
  }
  ouvintes.forEach((avisar) => avisar());
}

/** O tema em uso — o que está no `<html>` —, e a página redesenha quando ele muda. */
export function useTema(): Tema {
  return useSyncExternalStore(
    (avisar) => {
      ouvintes.add(avisar);
      return () => {
        ouvintes.delete(avisar);
      };
    },
    () => (document.documentElement.dataset.tema === 'escuro' ? 'escuro' : 'claro'),
    () => 'claro',
  );
}

/** Luminância relativa (WCAG) de uma cor `#RRGGBB`: 0 é preto, 1 é branco. */
export function luminancia(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [n >> 16, (n >> 8) & 255, n & 255].map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

const MINIMA_NO_ESCURO = 0.2; // ~4:1 sobre o fundo escuro dos cartões

/**
 * A cor de uma série no tema em uso. No escuro, a cor de marca escura (a Caixa, o BRB, o azul da tinta) some no fundo:
 * ela clareia, misturada com branco, só até ler. As claras não mudam, e no tema claro nada muda.
 */
export function corNoTema(cor: string, tema: Tema): string {
  if (tema !== 'escuro' || !/^#[0-9a-f]{6}$/i.test(cor) || luminancia(cor) >= MINIMA_NO_ESCURO) return cor;
  const n = parseInt(cor.slice(1), 16);
  const rgb = [n >> 16, (n >> 8) & 255, n & 255];
  for (let t = 0.05; t < 1; t += 0.05) {
    const mistura = rgb.map((c) => Math.round(c + (255 - c) * t));
    const hex = `#${mistura.map((c) => c.toString(16).padStart(2, '0')).join('').toUpperCase()}`;
    if (luminancia(hex) >= MINIMA_NO_ESCURO) return hex;
  }
  return '#FFFFFF';
}
