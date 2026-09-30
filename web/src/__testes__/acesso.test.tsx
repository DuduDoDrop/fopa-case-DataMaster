/**
 * Quem vê o quê: quem entra pelo Google vira "usuário" (o leitor) e vê o painel, o histórico, o
 * analytics e — desde 27/09 — a Revisão, onde decide; Execuções, E-mails, Saúde e Admin — e os botões da API — só o
 * admin. O servidor garante com 403; aqui o menu e a página nem aparecem para quem não pode.
 */
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Me } from '../api/tipos';
import { Layout } from '../componentes/Layout';
import { Restrita } from '../componentes/Restrita';
import { nomePapel } from '../componentes/Sessao';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

afterEach(() => vi.unstubAllGlobals());

const USUARIO: Me = { email: 'u@x', papel: 'leitor', nome: null };
const OPERADOR: Me = { email: 'o@x', papel: 'operador', nome: null };
const ADMIN: Me = { email: 'a@x', papel: 'admin', nome: null, supremo: false };
const SUPREMO: Me = { email: 'd@x', papel: 'admin', nome: 'Admin', supremo: true };

async function linksDoMenu(me: Me) {
  fetchFalso({ '/api/me': me });
  render(
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
  await screen.findByText('página');
  const nav = screen.getByRole('navigation', { name: 'Seções' });
  return { links: within(nav).getAllByRole('link').map((a) => a.textContent), nav };
}

describe('quem vê o quê', () => {
  it('o usuário vê o painel, o histórico, o analytics, a Revisão e a Governança', async () => {
    // O Usuário vê a Revisão e decide (ADR-021, emenda); a Governança fica ao lado da Revisão
    const { links, nav } = await linksDoMenu(USUARIO);
    expect(links).toEqual(['Painel', 'Histórico', 'Analytics', 'Revisão', 'Governança']);
    expect(nav.textContent).toContain('u@x · Usuário');
  });

  it('o operador vê o mesmo que o usuário', async () => {
    expect((await linksDoMenu(OPERADOR)).links).toEqual(['Painel', 'Histórico', 'Analytics', 'Revisão', 'Governança']);
  });

  it('o admin vê tudo; o dono aparece como admin supremo', async () => {
    expect((await linksDoMenu(ADMIN)).links).toEqual([
      'Painel', 'Histórico', 'Analytics', 'Revisão', 'Governança', 'Execuções', 'E-mails', 'Saúde', 'Admin',
    ]);
    vi.unstubAllGlobals();
    document.body.innerHTML = '';
    expect((await linksDoMenu(SUPREMO)).nav.textContent).toContain('d@x · Admin Supremo');
  });

  it('o e-mail do cabeçalho vem numa caixa própria, a que o CSS deixa em minúsculas', async () => {
    // Só o e-mail do cabeçalho fica em minúsculas: o papel segue as maiúsculas do
    // menu. A regra está em extra.css (nav.menu .quem .email), conferida em estilo.test.ts.
    const { nav } = await linksDoMenu({ ...USUARIO, email: 'Leitor@Prefeitura.SP.gov.br' });
    const email = within(nav).getByText('Leitor@Prefeitura.SP.gov.br');
    expect(email).toHaveClass('email');
    expect(email.parentElement).toHaveClass('quem');
    expect(email.parentElement?.textContent).toBe('Leitor@Prefeitura.SP.gov.br · Usuário');
  });

  it('e-mail, tema e "Atualizar" formam um grupo só, no fim do menu', async () => {
    // Com a Governança, o menu do admin com e-mail longo não cabe numa linha: o grupo desce inteiro para a direita
    // (regra em extra.css, nav.menu .conta), em vez de o tema e o "Atualizar" caírem soltos à esquerda.
    const { nav } = await linksDoMenu(SUPREMO);
    const conta = nav.lastElementChild as HTMLElement;
    expect(conta).toHaveClass('conta');
    expect([...conta.children].map((c) => c.className)).toEqual(['quem', 'tema', 'atualizar']);
  });

  it('o nome do papel na tela', () => {
    expect([USUARIO, OPERADOR, ADMIN, SUPREMO].map(nomePapel)).toEqual(['Usuário', 'Operador', 'Admin', 'Admin Supremo']);
  });

  it('pelo endereço direto, a página de admin diz "sem acesso" a quem não é admin', () => {
    const { unmount } = renderizar(
      <Restrita minimo="admin">
        <p>conteúdo do admin</p>
      </Restrita>,
      { me: OPERADOR },
    );
    expect(screen.queryByText('conteúdo do admin')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Sem acesso' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Voltar ao painel' })).toHaveAttribute('href', '/');
    unmount();
    renderizar(
      <Restrita minimo="admin">
        <p>conteúdo do admin</p>
      </Restrita>,
      { me: ADMIN },
    );
    expect(screen.getByText('conteúdo do admin')).toBeInTheDocument();
  });
});
