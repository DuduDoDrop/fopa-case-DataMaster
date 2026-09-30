/**
 * As consultas do site (TanStack Query), uma por rota de api/site.py. As
 * chaves são o próprio caminho: invalidar ['/api/licitacoes'] depois de uma
 * ação derruba todas as páginas da lista de uma vez.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, enviar, ErroApi } from './cliente';
import type {
  Analytics,
  ComprasPorBanco,
  Card,
  CatalogoIa,
  ConfiguracaoResposta,
  Custo,
  Email,
  ExecucaoDetalhe,
  GastosIa,
  ExecucaoWorkflow,
  ItemRevisao,
  LicitacoesEmRevisao,
  LicitacaoCompleta,
  Me,
  OrcamentoResposta,
  Pagina,
  Resumo,
  RotulosEscopoResposta,
  Saude,
  Termo,
  Usuario,
} from './tipos';

export function useMe() {
  return useQuery({ queryKey: ['/api/me'], queryFn: () => api<Me>('/api/me'), staleTime: 60_000 });
}

/** Os tiles contam o mesmo universo da lista: o recorte pedido vai também aqui (e só folha, sempre). */
/**
 * Home × histórico: a sessão que já aconteceu vira legado e sai da grade de trabalho —
 * sem apagar nada. A API devolve `todas` se ninguém pedir; o site sempre pede uma das duas.
 */
export type Situacao = 'ativas' | 'historico';

/** O filtro de datas pela publicação (AAAA-MM-DD, pontas inclusas); nenhuma = todo o histórico. */
export interface Datas {
  de?: string | null;
  ate?: string | null;
}

function comDatas(busca: URLSearchParams, d: Datas | undefined) {
  if (d?.de) busca.set('de', d.de);
  if (d?.ate) busca.set('ate', d.ate);
}

/**
 * "apenas FOPA (a IA confirma)" (db/034): a API esconde o que a IA (Jev) estima que não é folha — nota
 * abaixo de 0,5. Sem nota, fica; o rótulo humano "dentro" manda. Só no histórico e no analytics: do painel, a trava
 * (nota <= 0,25) já tira.
 */
function comFopaIa(busca: URLSearchParams, soFopaIa: boolean | undefined) {
  if (soFopaIa) busca.set('so_fopa_ia', 'true');
}

export function useResumo(recorteTodos = false, situacao?: Situacao, datas?: Datas, soFopaIa = false) {
  const busca = new URLSearchParams();
  if (recorteTodos) busca.set('recorte', 'todos');
  if (situacao) busca.set('situacao', situacao);
  comDatas(busca, datas);
  comFopaIa(busca, soFopaIa);
  const s = busca.toString();
  return useQuery({
    queryKey: ['/api/resumo', recorteTodos, situacao, datas?.de ?? null, datas?.ate ?? null, soFopaIa],
    queryFn: () => api<Resumo>('/api/resumo' + (s ? `?${s}` : '')),
  });
}

export interface ParametrosLista {
  q: string;
  /** chaves de api/consultas.py:FILTROS; várias somam-se com E (vazio ou só 'todas' = todas) */
  filtros: string[];
  /** "vence em até N dias" (7, 15, 30, 45 ou 60); null ou ausente = qualquer prazo */
  venceEm?: number | null;
  page: number;
  /** quantos por página (a API aceita 1 a 200); sem isto ela usa 50 */
  porPagina?: number;
  /** ADR-015: sem isto a API lista só o recorte de 2026 */
  recorteTodos: boolean;
  /** home (`ativas`) ou histórico; sem isto a API devolve `todas` */
  situacao?: Situacao;
  /** filtro de datas pela publicação (o histórico) */
  de?: string | null;
  ate?: string | null;
  /** "apenas FOPA (a IA confirma)" — o histórico */
  soFopaIa?: boolean;
}

export function caminhoLista(p: ParametrosLista): string {
  const busca = new URLSearchParams();
  if (p.q) busca.set('q', p.q);
  for (const f of p.filtros) if (f !== 'todas') busca.append('filtro', f);
  if (p.venceEm) busca.set('vence_em', String(p.venceEm));
  if (p.page > 1) busca.set('page', String(p.page));
  if (p.porPagina) busca.set('por_pagina', String(p.porPagina));
  if (p.recorteTodos) busca.set('recorte', 'todos');
  if (p.situacao) busca.set('situacao', p.situacao);
  comDatas(busca, p);
  comFopaIa(busca, p.soFopaIa);
  const s = busca.toString();
  return '/api/licitacoes' + (s ? `?${s}` : '');
}

export function useLicitacoes(p: ParametrosLista) {
  return useQuery({
    queryKey: ['/api/licitacoes', p],
    queryFn: () => api<Pagina<Card>>(caminhoLista(p)),
    // Trocar de página ou de filtro mantém a lista anterior na tela até a
    // nova chegar, em vez de piscar "carregando" no meio da leitura.
    placeholderData: keepPreviousData,
  });
}

/** `intervalo`: acompanhar o processamento depois de uma ação (lib/acompanhar.ts); false = não repergunta. */
export function useLicitacao(slug: string | undefined, habilitado = true, intervalo: number | false = false) {
  return useQuery({
    queryKey: ['/api/licitacoes', slug],
    queryFn: () => api<LicitacaoCompleta>(`/api/licitacoes/${encodeURIComponent(slug ?? '')}`),
    enabled: !!slug && habilitado,
    refetchInterval: intervalo,
  });
}

/**
 * A API pagina de 50 em 50. A chave leva `{page}` num objeto: um número solto
 * colidiria com `useExecucao(id)` (['/api/execucoes', 1] seria as duas).
 */
export function useExecucoes(page = 1) {
  return useQuery({
    queryKey: ['/api/execucoes', { page }],
    queryFn: () => api<Pagina<ExecucaoWorkflow>>('/api/execucoes' + (page > 1 ? `?page=${page}` : '')),
    placeholderData: keepPreviousData,
  });
}

/**
 * As últimas rodadas do W01, as do "Verificar agora" e as da agenda das 6h. O Admin mostra a primeira (saindo da
 * página, a tela voltava ao estado de antes do clique) e tira das outras o tempo de costume.
 */
export function useUltimasVerificacoes() {
  return useQuery({
    queryKey: ['/api/execucoes', { workflow: 'W01' }],
    queryFn: () => api<Pagina<ExecucaoWorkflow>>('/api/execucoes?workflow=W01&por_pagina=20'),
  });
}

/** Acompanha uma execução até ela sair de "em curso" (Verificar agora). */
export function useExecucao(id: number | null) {
  return useQuery({
    queryKey: ['/api/execucoes', id],
    queryFn: () => api<ExecucaoDetalhe>(`/api/execucoes/${id}`),
    enabled: id !== null,
    refetchInterval: (q) => (execucaoTerminou(q.state.data) ? false : 2000),
  });
}

const EM_CURSO = new Set(['em_curso', 'rodando', 'running', 'queued', 'iniciada', 'pendente']);

/** O status de uma execução, da lista ou do detalhe, ainda é de quem está rodando. */
export function statusEmCurso(status: string | null | undefined): boolean {
  return !!status && EM_CURSO.has(status);
}

/** `GET /api/execucoes/{id}` devolve `{execucao: {status}, buscas}`: o status é o da execução. */
export function execucaoTerminou(d: ExecucaoDetalhe | undefined): boolean {
  const status = d?.execucao?.status;
  return !!status && !EM_CURSO.has(status);
}

export function useCusto() {
  return useQuery({ queryKey: ['/api/custo'], queryFn: () => api<Custo>('/api/custo') });
}

/** Os gastos com IA (fatura + Jev), só na home: mudam devagar, um minuto de validade basta. */
export function useGastosIa(ativo = true) {
  return useQuery({
    queryKey: ['/api/gastos-ia'],
    queryFn: () => api<GastosIa>('/api/gastos-ia'),
    staleTime: 60_000,
    enabled: ativo,
  });
}

export function useEmails() {
  return useQuery({ queryKey: ['/api/emails'], queryFn: () => api<Pagina<Email>>('/api/emails') });
}

/**
 * A saúde é pública e responde 503 quando uma peça cai — com o corpo dizendo
 * qual. 503 aqui é o DADO da tela, não falha de carregamento.
 */
export function useSaude(intervalo: number | false = 30_000) {
  return useQuery({
    queryKey: ['/api/saude'],
    queryFn: () => api<Saude>('/api/saude', {}, () => undefined, [503]),
    refetchInterval: intervalo,
  });
}

// ------------------------------------------------------------------ revisão humana
/** `q`: a busca por licitação (a mesma do painel); vazio = a fila inteira. */
/**
 * Os campos pendentes de UMA licitação (`?controle=`). A fila inteira (5.323 em 25/09) travava a página: ela não é
 * mais pedida — sem licitação escolhida, esta consulta nem sai.
 */
export function useFilaRevisao(controle: string) {
  return useQuery({
    queryKey: ['/api/fila-revisao', 'controle', controle],
    queryFn: () => api<{ itens: ItemRevisao[] }>(`/api/fila-revisao?${new URLSearchParams({ controle })}`),
    enabled: !!controle,
  });
}

/** A lista leve da revisão: os totais sempre e, com a busca, as licitações com campos pendentes (até 50). */
export function useLicitacoesEmRevisao(q = '') {
  const s = q.trim();
  return useQuery({
    queryKey: ['/api/fila-revisao', 'licitacoes', s],
    queryFn: () => api<LicitacoesEmRevisao>('/api/fila-revisao/licitacoes' + (s ? `?${new URLSearchParams({ q: s })}` : '')),
    // Digitar mantém a lista anterior na tela até a nova chegar, como no painel.
    placeholderData: keepPreviousData,
  });
}

/**
 * Aba "escopo" da revisão: candidatas do Jev sem rótulo + as rotuladas
 * (`{itens, pendentes, rotuladas}`). Exige papel operador (403 para leitor).
 * 404/405 = API anterior à rota: `disponivel: false`, e a aba diz isso em vez
 * de quebrar.
 */
export function useRotulosEscopo(habilitado = true) {
  return useQuery({
    queryKey: ['/api/rotulos-escopo'],
    enabled: habilitado,
    queryFn: async (): Promise<RotulosEscopoResposta & { disponivel: boolean }> => {
      try {
        const r = await api<RotulosEscopoResposta>('/api/rotulos-escopo');
        return { disponivel: true, itens: r.itens, pendentes: r.pendentes, rotuladas: r.rotuladas };
      } catch (e) {
        if (e instanceof ErroApi && (e.status === 404 || e.status === 405)) {
          return { disponivel: false, itens: [], pendentes: 0, rotuladas: 0 };
        }
        throw e;
      }
    },
  });
}

// ------------------------------------------------------------------ admin (/api/admin/*)
export function useConfiguracao() {
  return useQuery({
    queryKey: ['/api/admin/configuracao'],
    queryFn: () => api<ConfiguracaoResposta>('/api/admin/configuracao'),
  });
}

export function useOrcamento() {
  return useQuery({ queryKey: ['/api/admin/orcamento'], queryFn: () => api<OrcamentoResposta>('/api/admin/orcamento') });
}

export function useTermos() {
  return useQuery({ queryKey: ['/api/admin/termos'], queryFn: () => api<{ itens: Termo[] }>('/api/admin/termos') });
}

export function useUsuarios() {
  return useQuery({ queryKey: ['/api/admin/usuarios'], queryFn: () => api<{ itens: Usuario[] }>('/api/admin/usuarios') });
}

/** Mutação genérica que invalida as chaves afetadas quando dá certo. */
export function useEnviar<TCorpo, TResp = unknown>(
  montar: (corpo: TCorpo) => { caminho: string; metodo: 'POST' | 'PUT' | 'PATCH' | 'DELETE'; corpo?: unknown },
  invalida: string[] = [],
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (corpo: TCorpo) => {
      const m = montar(corpo);
      return enviar<TResp>(m.caminho, m.metodo, m.corpo);
    },
    onSuccess: () => {
      for (const k of invalida) qc.invalidateQueries({ queryKey: [k] });
    },
  });
}

/**
 * Analytics do histórico de compra e venda (GET /api/analytics): aqui, e só aqui, o que está fora do
 * escopo de folha pode entrar ("mostrar fora do escopo"); `ano` é o da publicação.
 */
export function caminhoAnalytics(p: { escopoTodos: boolean; soFopaIa?: boolean } & Datas): string {
  const busca = new URLSearchParams();
  if (p.escopoTodos) busca.set('escopo', 'todos');
  comDatas(busca, p);
  comFopaIa(busca, p.soFopaIa);
  const s = busca.toString();
  return '/api/analytics' + (s ? `?${s}` : '');
}

export function useAnalytics(p: { escopoTodos: boolean; soFopaIa?: boolean } & Datas) {
  return useQuery({
    queryKey: ['/api/analytics', p.escopoTodos, p.de ?? null, p.ate ?? null, !!p.soFopaIa],
    queryFn: () => api<Analytics>(caminhoAnalytics(p)),
    placeholderData: keepPreviousData,
  });
}

/**
 * O que cada instituição financeira comprou (GET /api/analytics/compras): a lista do filtro pesquisável e,
 * com `banco`, as compras dele. O período (`de`, `ate`) é o da DATA DA COMPRA, e o escopo segue a caixa da página.
 */
export function caminhoComprasPorBanco(p: { escopoTodos: boolean; soFopaIa?: boolean; banco: string | null } & Datas): string {
  const busca = new URLSearchParams();
  if (p.escopoTodos) busca.set('escopo', 'todos');
  if (p.banco) busca.set('banco', p.banco);
  comDatas(busca, p);
  comFopaIa(busca, p.soFopaIa);
  const s = busca.toString();
  return '/api/analytics/compras' + (s ? `?${s}` : '');
}

export function useComprasPorBanco(p: { escopoTodos: boolean; soFopaIa?: boolean; banco: string | null } & Datas) {
  const caminho = caminhoComprasPorBanco(p);
  return useQuery({
    queryKey: ['/api/analytics/compras', caminho],
    queryFn: () => api<ComprasPorBanco>(caminho),
    placeholderData: keepPreviousData,
  });
}

/** O catálogo do botão "Extrair com IA": provedores, modelos, esforços e o padrão de cada empresa (api/modelos_ia.py). */
export function useModelosIa() {
  return useQuery({
    queryKey: ['/api/modelos-ia'],
    queryFn: () => api<CatalogoIa>('/api/modelos-ia'),
    staleTime: Infinity,
  });
}
