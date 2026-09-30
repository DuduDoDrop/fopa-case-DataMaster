import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import { ErroApi } from './api/cliente';
import { Layout } from './componentes/Layout';
import { Restrita } from './componentes/Restrita';
import { Admin } from './paginas/Admin';
import { Detalhe } from './paginas/Detalhe';
import { Emails } from './paginas/Emails';
import { Execucoes } from './paginas/Execucoes';
import { Governanca } from './paginas/Governanca';
import { Login } from './paginas/Login';
import { Analytics } from './paginas/Analytics';
import { AnalyticsHistorico } from './paginas/AnalyticsHistorico';
import { Painel } from './paginas/Painel';
import { Relatorio } from './paginas/Relatorio';
import { Revisao } from './paginas/Revisao';
import { Saude } from './paginas/Saude';

// 401/403/404 não melhoram tentando de novo; erro de rede às vezes melhora.
const cliente = new QueryClient({
  queryCache: new QueryCache(),
  defaultOptions: {
    queries: {
      retry: (n, erro) => !(erro instanceof ErroApi && [401, 403, 404, 422].includes(erro.status)) && n < 2,
      refetchOnWindowFocus: false,
      staleTime: 15_000,
    },
  },
});

function NaoEncontrada() {
  return (
    <div className="pg-painel">
      <div className="wrap">
        <p className="vazio">
          Página não encontrada. <Link to="/">Voltar ao painel</Link>
        </p>
      </div>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={cliente}>
      <BrowserRouter>
        <Routes>
          {/* `/login` é do servidor (modo local ou Google); a página do front é /entrar */}
          <Route path="/entrar" element={<Login />} />
          <Route element={<Layout />}>
            <Route path="/" element={<Painel />} />
            <Route path="/historico" element={<Painel situacao="historico" />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/analytics/historico-fopa" element={<AnalyticsHistorico />} />
            <Route path="/licitacao/:slug" element={<Detalhe />} />
            <Route path="/licitacao/:slug/relatorio" element={<Relatorio />} />
            <Route path="/revisao" element={<Revisao />} />
            <Route path="/governanca" element={<Governanca />} />
            <Route path="/execucoes" element={<Restrita minimo="admin"><Execucoes /></Restrita>} />
            <Route path="/emails" element={<Restrita minimo="admin"><Emails /></Restrita>} />
            <Route path="/saude" element={<Restrita minimo="admin"><Saude /></Restrita>} />
            <Route path="/admin" element={<Restrita minimo="admin"><Admin /></Restrita>} />
            <Route path="*" element={<NaoEncontrada />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
