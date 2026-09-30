/**
 * Moldura das páginas logadas: confirma a sessão em `GET /api/me` antes de
 * mostrar qualquer dado (401 → /entrar, pelo cliente) e põe o papel no
 * contexto para os botões nascerem habilitados ou não.
 *
 * O HTML da v2 não tinha menu (era um arquivo só); o menu aqui é o mínimo,
 * em mono e na cor da tinta, para não competir com o conteúdo.
 */
import '../../design/painel.css';
import type { ReactNode } from 'react';
import { useIsFetching, useQueryClient } from '@tanstack/react-query';
import { NavLink, Outlet } from 'react-router-dom';
import { ErroApi } from '../api/cliente';
import { useMe } from '../api/consultas';
import { escolherTema, useTema } from '../lib/tema';
import { nomePapel, permitido, type Minimo } from './Sessao';
import { Carregando, Falha } from './Estado';
import { SessaoContexto } from './Sessao';

// `minimo`: o papel que vê o link (Execuções,
// E-mails, Saúde e Admin são só do admin). A mesma regra guarda a rota (App.tsx, componentes/Restrita).
const LINKS: { para: string; rotulo: string; fim?: boolean; minimo?: Minimo }[] = [
  { para: '/', rotulo: 'Painel', fim: true },
  { para: '/historico', rotulo: 'Histórico' },
  // As duas páginas do Analytics (Mercado e Histórico FOPA) trocam pelos botões no topo delas; aqui, um item só, marcado
  // nas duas.
  { para: '/analytics', rotulo: 'Analytics' },
  // a Revisão é de todo usuário logado desde 27/09 (ADR-021, emenda)
  { para: '/revisao', rotulo: 'Revisão' },
  // a Governança, ao lado da Revisão e de todo usuário logado
  { para: '/governanca', rotulo: 'Governança' },
  { para: '/execucoes', rotulo: 'Execuções', minimo: 'admin' },
  { para: '/emails', rotulo: 'E-mails', minimo: 'admin' },
  { para: '/saude', rotulo: 'Saúde', minimo: 'admin' },
  { para: '/admin', rotulo: 'Admin', minimo: 'admin' },
];

/**
 * "Atualizar" no canto superior direito de todas as páginas.
 * Invalida as consultas: a página busca de novo o que mostra, sem recarregar o site.
 */
function Atualizar() {
  const qc = useQueryClient();
  const buscando = useIsFetching();
  return (
    <button type="button" className="atualizar" title="Recarrega os dados desta página" onClick={() => qc.invalidateQueries()}>
      ↻ {buscando > 0 ? 'Atualizando…' : 'Atualizar'}
    </button>
  );
}

/**
 * O tema (nomes de 28/09): um botão ao lado do "Atualizar" que diz para onde vai — "Modo Escuro" no
 * fundo claro, "Modo Claro" no escuro (antes eram
 * "Dark Mode" e "Bright Mode"). O ícone é a lua ou o sol do destino: a bolinha ●/○ de antes parecia marcador de lista.
 */
function BotaoTema() {
  const escuro = useTema() === 'escuro';
  return (
    <button
      type="button"
      className="tema"
      title={escuro ? 'Alterna para o tema claro' : 'Alterna para o tema escuro'}
      onClick={() => escolherTema(escuro ? 'claro' : 'escuro')}
    >
      <span aria-hidden="true" className="tema-icone">{escuro ? '☀' : '☾'}</span> {escuro ? 'Modo Claro' : 'Modo Escuro'}
    </button>
  );
}

function Moldura({ children }: { children: ReactNode }) {
  return (
    <div className="pg-painel">
      <div className="wrap">{children}</div>
    </div>
  );
}

export function Layout() {
  const me = useMe();
  if (me.isError) {
    if (me.error instanceof ErroApi && me.error.status === 401)
      return (
        <Moldura>
          <Carregando texto="Redirecionando para o login…" />
        </Moldura>
      );
    return (
      <Moldura>
        <Falha erro={me.error} oque="a sessão" />
      </Moldura>
    );
  }
  if (!me.data)
    return (
      <Moldura>
        <Carregando texto="Verificando a sessão…" />
      </Moldura>
    );
  return (
    <SessaoContexto.Provider value={me.data}>
      <nav className="menu" aria-label="Seções">
        <span className="marcafopa">FOPA</span>
        {LINKS.filter((l) => !l.minimo || permitido(me.data, l.minimo)).map((l) => (
          <NavLink key={l.para} to={l.para} end={l.fim}>
            {l.rotulo}
          </NavLink>
        ))}
        {/* e-mail, tema e "Atualizar" num grupo só: quando o menu não cabe numa linha (o do admin com e-mail longo),
            descem juntos para a direita */}
        <span className="conta">
          <span className="quem" title={`papel: ${nomePapel(me.data)}`}>
            <span className="email">{me.data.email}</span> · {nomePapel(me.data)}
          </span>
          <BotaoTema />
          <Atualizar />
        </span>
      </nav>
      <Outlet />
    </SessaoContexto.Provider>
  );
}
