/**
 * /governanca — governança e compliance: página estática para todo usuário logado, com o termo em inglês acima do
 * título em português, as normas numa tabela e os links para a Revisão e a Política de Privacidade.
 */
import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { Governanca } from '../paginas/Governanca';
import { meLeitor } from '../__fixtures__/contrato';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.pushState({}, '', '/');
});

// o termo em inglês é o rótulo acima do título em português
const BLOCOS = [
  ['Human-in-the-loop', 'Supervisão humana'],
  ['Accountability', 'Rastreabilidade e prestação de contas'],
  ['Legal & regulatory compliance', 'Fundamentos legais e regulatórios'],
  ['Privacy by design · LGPD', 'Proteção de dados pessoais'],
  ['Open data', 'Dados públicos e coleta responsável'],
  ['Least privilege', 'Segurança da informação e gestão de acessos'],
  ['Business continuity · Risk management', 'Continuidade e gestão de riscos'],
  ['Shared responsibility', 'Responsabilidade compartilhada'],
];

describe('Governança e compliance', () => {
  it('o título e os oito blocos, cada um com o termo em inglês acima do título em português', () => {
    renderizar(<Governanca />, { me: meLeitor });
    expect(screen.getByRole('heading', { level: 1, name: 'Governança e compliance' })).toBeInTheDocument();
    const blocos = screen.getAllByRole('region');
    expect(
      blocos.map((b) => [b.querySelector('.governanca-termo')?.textContent, within(b).getByRole('heading', { level: 2 }).textContent]),
    ).toEqual(BLOCOS);
  });

  it('as normas numa tabela, com o dispositivo de cada uma', () => {
    renderizar(<Governanca />, { me: meLeitor });
    const tabela = within(screen.getByRole('region', { name: 'Fundamentos legais e regulatórios' })).getByRole('table');
    const normas = within(tabela)
      .getAllByRole('row')
      .slice(1)
      .map((l) => l.firstElementChild?.textContent);
    expect(normas).toEqual([
      'Lei nº 14.133/2021, arts. 54 e 174',
      'Lei nº 12.527/2011 (LAI), art. 8º, § 3º, III',
      'Lei nº 13.709/2018 (LGPD), arts. 6º e 7º, IX',
      'Lei nº 13.303/2016',
      'TCU, Acórdãos 3.042/2008 e 1.940/2015, e tribunais de contas estaduais',
      'Resolução CMN nº 5.058/2022 e Lei nº 15.252/2025',
      'Lei nº 14.509/2022',
    ]);
  });

  it('leva à Revisão e à Política de Privacidade, e avisa que não é parecer jurídico', () => {
    renderizar(<Governanca />, { me: meLeitor });
    expect(screen.getByRole('link', { name: 'Revisão' })).toHaveAttribute('href', '/revisao');
    expect(screen.getByRole('link', { name: 'Política de privacidade' })).toHaveAttribute('href', '/privacidade');
    expect(screen.getByText(/Não constitui parecer jurídico\./)).toBeInTheDocument();
  });

  it('o endereço /governanca abre a página para o usuário, com o item do menu marcado', async () => {
    fetchFalso({ '/api/me': meLeitor });
    window.history.pushState({}, '', '/governanca');
    render(<App />);
    expect(await screen.findByRole('heading', { level: 1, name: 'Governança e compliance' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Seções' });
    expect(within(nav).getByRole('link', { name: 'Governança' })).toHaveClass('active');
  });
});
