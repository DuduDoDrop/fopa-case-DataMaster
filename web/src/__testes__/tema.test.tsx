/**
 * Modo escuro: um botão no menu alterna e guarda a escolha; sem escolha
 * guardada, vale a do sistema.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Layout } from '../componentes/Layout';
import { corNoTema, luminancia, temaInicial } from '../lib/tema';
import { me } from '../__fixtures__/contrato';
import { fetchFalso } from './falso';

function montar() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<p>página</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.tema;
});
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
  delete document.documentElement.dataset.tema;
});

describe('modo escuro', () => {
  it('o botão do menu alterna entre claro e escuro e guarda a escolha', async () => {
    fetchFalso({ '/api/me': me });
    montar();
    // o nome diz para onde vai, em português: "Modo Escuro" no claro, "Modo Claro" no escuro
    const botao = await screen.findByRole('button', { name: 'Modo Escuro' });
    const usuario = userEvent.setup();
    await usuario.click(botao);
    expect(document.documentElement.dataset.tema).toBe('escuro');
    expect(localStorage.getItem('fopa-tema')).toBe('escuro');
    expect(botao).toHaveAccessibleName('Modo Claro');
    await usuario.click(botao);
    expect(document.documentElement.dataset.tema).toBe('claro');
    expect(localStorage.getItem('fopa-tema')).toBe('claro');
    // o "atualizar" continua sendo o último do menu (canto superior direito): o último do grupo da conta, que fecha o
    // menu desde 28/09
    expect(screen.getByRole('navigation', { name: 'Seções' }).lastElementChild?.lastElementChild).toBe(
      screen.getByRole('button', { name: /Atualizar/ }),
    );
  });

  it('sem escolha guardada vale a do sistema; com escolha, a escolha', () => {
    vi.stubGlobal('matchMedia', (q: string) => ({ matches: q.includes('dark'), media: q }));
    expect(temaInicial()).toBe('escuro');
    localStorage.setItem('fopa-tema', 'claro');
    expect(temaInicial()).toBe('claro');
    localStorage.setItem('fopa-tema', 'qualquer');
    expect(temaInicial()).toBe('escuro');
  });

  it('no escuro, a cor escura de um banco clareia até ler no fundo; as claras e o tema claro ficam como estão', () => {
    for (const escura of ['#11243D', '#1B3D6D', '#8C1D40', '#6D2077', '#005CA9']) {
      const c = corNoTema(escura, 'escuro');
      expect(c).not.toBe(escura);
      expect(luminancia(c)).toBeGreaterThanOrEqual(0.2);
    }
    expect(corNoTema('#E5B800', 'escuro')).toBe('#E5B800');
    expect(corNoTema('#EC7000', 'escuro')).toBe('#EC7000');
    expect(corNoTema('#11243D', 'claro')).toBe('#11243D');
    expect(corNoTema('var(--teal)', 'escuro')).toBe('var(--teal)');
  });
});
