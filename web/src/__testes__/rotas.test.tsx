/**
 * Entrada, relatório e a moldura com sessão.
 *
 * `/login` é do SERVIDOR (api/site.py): no modo local da demo ele já entra
 * como o admin semeado; no Google redireciona ao fluxo OAuth. O front nunca
 * aponta direto para `/auth/google/login` — quem decide o modo é a API. A
 * página do front é `/entrar`, para onde o 401 manda, e o botão dela vai
 * para `/login` numa navegação de página inteira.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Layout } from '../componentes/Layout';
import { nomePapel, useSessao } from '../componentes/Sessao';
import { Login } from '../paginas/Login';
import { Relatorio } from '../paginas/Relatorio';
import { copia, me, registros, responder, saude } from '../__fixtures__/contrato';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

afterEach(() => vi.unstubAllGlobals());

describe('entrar', () => {
  it('o botão vai para /login do servidor (modo local da demo, pela /api/saude)', async () => {
    fetchFalso({ '/api/saude': saude });
    renderizar(<Login />, { rota: '/entrar' });
    const botao = await screen.findByRole('link', { name: 'Entrar (demonstração local)' });
    expect(botao).toHaveAttribute('href', '/login');
  });

  it('com auth_mode google o botão diz Google — e continua indo para /login', async () => {
    fetchFalso({ '/api/saude': { ...copia(saude), auth_mode: 'google' } });
    renderizar(<Login />, { rota: '/entrar' });
    const botao = await screen.findByRole('link', { name: 'Entrar com Google' });
    expect(botao).toHaveAttribute('href', '/login');
  });

  it('com a saúde em 503 o corpo ainda diz o modo, e o botão funciona', async () => {
    fetchFalso({ '/api/saude': responder(registros.saude503) });
    renderizar(<Login />, { rota: '/entrar' });
    expect(await screen.findByRole('link', { name: 'Entrar (demonstração local)' })).toHaveAttribute('href', '/login');
  });

  it('nunca aponta direto para o OAuth', async () => {
    fetchFalso({ '/api/saude': saude });
    const { container } = renderizar(<Login />, { rota: '/entrar' });
    await screen.findByRole('link', { name: /Entrar/ });
    expect(container.innerHTML).not.toContain('/auth/google');
  });
});

describe('relatório', () => {
  it('abre /api/licitacoes/{slug}/relatorio', () => {
    const navegar = vi.fn();
    renderizar(
      <Routes>
        <Route path="/licitacao/:slug/relatorio" element={<Relatorio navegar={navegar} />} />
      </Routes>,
      { rota: '/licitacao/12345678000101-1-000001-2026/relatorio' },
    );
    expect(navegar).toHaveBeenCalledWith('/api/licitacoes/12345678000101-1-000001-2026/relatorio');
  });
});

describe('moldura com sessão', () => {
  function Papel() {
    return <p>papel: {useSessao()?.papel}</p>;
  }

  it('só mostra a página depois do /api/me real, com o papel no contexto', async () => {
    fetchFalso({ '/api/me': me });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Papel />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText('Verificando a sessão…')).toBeInTheDocument();
    expect(await screen.findByText(`papel: ${me.papel}`)).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Seções' });
    expect(nav.textContent).toContain(`${me.email} · ${nomePapel(me)}`);
    expect(nav.textContent).toContain('Revisão');
    // o Analytics virou duas páginas, trocadas pelos botões no topo delas; no menu fica só "Analytics", sem caixa no
    // mouse
    expect(within(nav).getByRole('link', { name: 'Analytics' })).toHaveAttribute('href', '/analytics');
    expect(within(nav).queryByRole('link', { name: 'Analytics de Mercado' })).toBeNull();
    expect(within(nav).queryByRole('link', { name: 'Analytics Histórico FOPA' })).toBeNull();
    expect(nav.querySelector('.submenu')).toBeNull();
    // A página do questionário saiu do site.
    expect(nav.textContent).not.toContain('Questionário');
  });

  it('"Analytics" no menu fica marcado nas duas páginas do Analytics', async () => {
    fetchFalso({ '/api/me': me });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/analytics/historico-fopa']}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="*" element={<Papel />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText('papel: ' + me.papel);
    const nav = screen.getByRole('navigation', { name: 'Seções' });
    expect(within(nav).getByRole('link', { name: 'Analytics' })).toHaveAttribute('aria-current', 'page');
  });

  it('"atualizar" no canto superior direito busca de novo os dados da página', async () => {
    const { chamadas } = fetchFalso({ '/api/me': me });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Papel />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText(`papel: ${me.papel}`);
    const antes = chamadas.filter((c) => c.url.pathname === '/api/me').length;
    const nav = screen.getByRole('navigation', { name: 'Seções' });
    const botao = screen.getByRole('button', { name: /Atualizar/ });
    expect(nav.lastElementChild?.lastElementChild).toBe(botao);   // o último do grupo da conta, que fecha o menu: canto superior direito
    await userEvent.setup().click(botao);
    await waitFor(() => expect(chamadas.filter((c) => c.url.pathname === '/api/me').length).toBeGreaterThan(antes));
  });
});
