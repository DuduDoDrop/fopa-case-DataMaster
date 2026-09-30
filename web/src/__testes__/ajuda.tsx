/**
 * Renderiza um componente com o que o app real põe em volta: roteador,
 * TanStack Query (sem retentativa, para o teste não esperar) e a sessão.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import type { Me } from '../api/tipos';
import { SessaoContexto } from '../componentes/Sessao';

export function renderizar(ui: ReactElement, opcoes: { me?: Me; rota?: string } = {}) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const me = opcoes.me ?? { email: 'leitor@exemplo.gov.br', papel: 'leitor', nome: null };
  return render(
    <QueryClientProvider client={cliente}>
      <SessaoContexto.Provider value={me}>
        <MemoryRouter initialEntries={[opcoes.rota ?? '/']}>{ui}</MemoryRouter>
      </SessaoContexto.Provider>
    </QueryClientProvider>,
  );
}
