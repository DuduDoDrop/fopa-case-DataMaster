/**
 * A opinião da IA (Jev) sobre ser compra de folha, em palavras. A tela mostra a chance de SER folha, não a de "o
 * filtro estar certo".
 */
import { describe, expect, it } from 'vitest';
import { AVISO_IA_FOLHA, opiniaoIa } from '../lib/respostas';

describe('opiniaoIa', () => {
  it.each([
    [0.93, 'IA: é folha (93%)', 'jev-sim'],
    [0.75, 'IA: é folha (75%)', 'jev-sim'],
    [0.62, 'IA: provavelmente é folha (62%)', 'jev-provavel'],
    [0.5, 'IA: provavelmente é folha (50%)', 'jev-provavel'],
    [0.4, 'IA: provavelmente não é folha (40%)', 'jev-duvida'],
    [0.25, 'IA: não é folha (25%)', 'jev-nao'],
    [0.05, 'IA: não é folha (5%)', 'jev-nao'],
  ])('%s -> %s', (p, texto, classe) => {
    expect(opiniaoIa(p)).toEqual({ texto, classe });
  });

  it('sem nota não há opinião; o número vem como texto do Postgres às vezes', () => {
    expect(opiniaoIa(null)).toBeNull();
    expect(opiniaoIa(undefined)).toBeNull();
    expect(opiniaoIa('0.81')).toEqual({ texto: 'IA: é folha (81%)', classe: 'jev-sim' });
  });

  it('o aviso diz o que o número é e que ele não decide', () => {
    expect(AVISO_IA_FOLHA).toMatch(/probabilidade de ser compra de folha/i);
    expect(AVISO_IA_FOLHA).toMatch(/não altera o escopo/i);
  });
});
