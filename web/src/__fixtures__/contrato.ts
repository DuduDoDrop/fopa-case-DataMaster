/**
 * As fixtures de CONTRATO: respostas gravadas da fopa-api de verdade por
 * `web/scripts/gerar_fixtures.py` (Postgres efêmero + importador real +
 * login local da demo). Nada aqui é escrito à mão.
 *
 * Cada `corpo` é atribuído ao tipo que o site declara em `api/tipos.ts`. É
 * isso que segura o contrato no BUILD: se o site passar a exigir um campo que
 * a API não manda (o `verificacoes` inventado, o `custo_brl` do resumo...), o
 * `tsc --noEmit` do `npm run build` quebra aqui, antes de qualquer teste.
 *
 * O relógio dos testes é `AGORA_CONTRATO`, o instante em que as fixtures
 * foram geradas: os prazos do cenário são relativos a ele (C1 fecha em 3
 * dias, C2 em 15, C3 fechou há 2, C9 em 60, C4 sem prazo).
 */
import type {
  CatalogoIa,
  ConfiguracaoResposta,
  Custo,
  GastosIa,
  Email,
  ExecucaoDetalhe,
  ExecucaoWorkflow,
  ItemRevisao,
  LicitacaoCompleta,
  Me,
  OrcamentoResposta,
  Pagina,
  Card,
  LicitacoesEmRevisao,
  Questionario,
  ReservaResposta,
  Resumo,
  RevisaoHumana,
  RotuloEscopo,
  RotulosEscopoResposta,
  Saude,
  Termo,
  Usuario,
} from '../api/tipos';
import meta from './contrato/_meta.json';
import jAcaoProcessar from './contrato/acao-processar.json';
import jAcaoVerificar from './contrato/acao-verificar.json';
import jConfig from './contrato/admin-configuracao.json';
import jConfigPut from './contrato/admin-configuracao-put.json';
import jConfigPut409 from './contrato/admin-configuracao-put-409.json';
import jOrcamento from './contrato/admin-orcamento.json';
import jOrcamentoPut from './contrato/admin-orcamento-put.json';
import jReserva from './contrato/admin-reservar-demo.json';
import jTermos from './contrato/admin-termos.json';
import jTermosPut from './contrato/admin-termos-put.json';
import jUsuarios from './contrato/admin-usuarios.json';
import jUsuariosPut from './contrato/admin-usuarios-put.json';
import jCusto from './contrato/custo.json';
import jGastosIa from './contrato/gastos-ia.json';
import jModelosIa from './contrato/modelos-ia.json';
import jEmails from './contrato/emails.json';
import jErroFiltro from './contrato/erro-filtro-sem-extracao.json';
import jErroRevisao from './contrato/erro-revisao-422.json';
import jExecCega from './contrato/execucao-cega.json';
import jExecConcluida from './contrato/execucao-concluida.json';
import jExecEmCurso from './contrato/execucao-em-curso.json';
import jExecucoes from './contrato/execucoes.json';
import jFila from './contrato/fila-revisao.json';
import jFilaLicitacoes from './contrato/fila-revisao-licitacoes.json';
import jFilaLicitacoesBusca from './contrato/fila-revisao-licitacoes-busca.json';
import jFilaControle from './contrato/fila-revisao-controle.json';
import jC1 from './contrato/licitacao-c1.json';
import jC2 from './contrato/licitacao-c2.json';
import jC3 from './contrato/licitacao-c3.json';
import jC4 from './contrato/licitacao-c4.json';
import jLista from './contrato/licitacoes.json';
import jListaEncerradas from './contrato/licitacoes-encerradas.json';
import jListaPagina2 from './contrato/licitacoes-pagina2.json';
import jListaRecorteTodos from './contrato/licitacoes-recorte-todos.json';
import jListaRevisao from './contrato/licitacoes-revisao.json';
import jListaSemExtracao from './contrato/licitacoes-sem_extracao.json';
import jListaUrgentes from './contrato/licitacoes-urgentes.json';
import jErroLeitorProcessar from './contrato/erro-leitor-processar-403.json';
import jMe from './contrato/me.json';
import jMeLeitor from './contrato/me-leitor.json';
import jQuestionario from './contrato/questionario.json';
import jResumo from './contrato/resumo.json';
import jResumoTodos from './contrato/resumo-recorte-todos.json';
import jRevisaoPost from './contrato/revisao-post.json';
import jRotuloPost from './contrato/rotulo-escopo-post.json';
import jRotulos from './contrato/rotulos-escopo.json';
import jSaude from './contrato/saude.json';
import jSaude503 from './contrato/saude-503.json';

export interface Registro<T = unknown> {
  metodo: string;
  caminho: string;
  status: number;
  corpo: T;
}

export const AGORA_CONTRATO = new Date(meta.gerado_em);
export const SLUGS = meta.slugs;

// ---- tipados: o tsc confere o JSON real contra api/tipos.ts
export const me: Me = jMe.corpo;
export const meLeitor: Me = jMeLeitor.corpo;
export const resumo: Resumo = jResumo.corpo;
export const resumoRecorteTodos: Resumo = jResumoTodos.corpo;
/** Padrão da API (ADR-015): só o recorte de 2026. C4 (sem data nenhuma) e C25 (2025) ficam de fora. */
export const lista: Pagina<Card> = jLista.corpo;
/** `?recorte=todos`: as 6 do cenário. */
export const listaRecorteTodos: Pagina<Card> = jListaRecorteTodos.corpo;
/** ADR-003/015: por padrão só o escopo; `?escopo=todos` traz o que a regra recusou. */
export const listaUrgentes: Pagina<Card> = jListaUrgentes.corpo;
export const listaEncerradas: Pagina<Card> = jListaEncerradas.corpo;
export const listaSemExtracao: Pagina<Card> = jListaSemExtracao.corpo;
export const listaRevisao: Pagina<Card> = jListaRevisao.corpo;
export const listaPagina2: Pagina<Card> = jListaPagina2.corpo;
export const licitacaoC1: LicitacaoCompleta = jC1.corpo;
export const licitacaoC2: LicitacaoCompleta = jC2.corpo;
export const licitacaoC3: LicitacaoCompleta = jC3.corpo;
export const licitacaoC4: LicitacaoCompleta = jC4.corpo;
export const execucoes: Pagina<ExecucaoWorkflow> = jExecucoes.corpo;
export const execucaoCega: ExecucaoDetalhe = jExecCega.corpo;
export const execucaoEmCurso: ExecucaoDetalhe = jExecEmCurso.corpo;
export const execucaoConcluida: ExecucaoDetalhe = jExecConcluida.corpo;
export const custo: Custo = jCusto.corpo;
export const gastosIa: GastosIa = jGastosIa.corpo;
export const modelosIa: CatalogoIa = jModelosIa.corpo as CatalogoIa;
export const emails: Pagina<Email> = jEmails.corpo;
export const questionario: Questionario = jQuestionario.corpo;
export const filaRevisao: { itens: ItemRevisao[] } = jFila.corpo;
export const filaRevisaoLicitacoes: LicitacoesEmRevisao = jFilaLicitacoes.corpo;
export const filaRevisaoLicitacoesBusca: LicitacoesEmRevisao = jFilaLicitacoesBusca.corpo;
export const filaRevisaoControle: { itens: ItemRevisao[] } = jFilaControle.corpo;
export const revisaoPost: RevisaoHumana = jRevisaoPost.corpo;
export const rotulosEscopo: RotulosEscopoResposta = jRotulos.corpo;
export const rotuloPost: NonNullable<RotuloEscopo['rotulo']> & { id: number; controle: string } = jRotuloPost.corpo;
export const configuracao: ConfiguracaoResposta = jConfig.corpo;
export const orcamento: OrcamentoResposta = jOrcamento.corpo;
export const termos: { itens: Termo[] } = jTermos.corpo;
export const usuarios: { itens: Usuario[] } = jUsuarios.corpo;
export const reserva: ReservaResposta = jReserva.corpo;
export const saude: Saude = jSaude.corpo;
export const saude503: Saude = jSaude503.corpo;

/** Os cards, por letra do cenário (C1 urgente, C2 aviso + revisão, C3 encerrada...). */
function porSlug(slug: string): Card {
  // O universo do cenário: o recorte inteiro (o que a regra de escopo recusou não chega a tela nenhuma).
  const c = listaRecorteTodos.itens.find((i) => i.slug === slug);
  if (!c) throw new Error(`card ${slug} não está em licitacoes-recorte-todos.json`);
  return c;
}
export const cardC1 = porSlug(SLUGS.c1);
export const cardC2 = porSlug(SLUGS.c2);
export const cardC3 = porSlug(SLUGS.c3);
export const cardC4 = porSlug(SLUGS.c4);

// ---- registros crus (status + corpo), para o fetch falso responder igual à API
export const registros = {
  acaoProcessar: jAcaoProcessar as Registro,
  acaoVerificar: jAcaoVerificar as Registro,
  configPut: jConfigPut as Registro,
  configPut409: jConfigPut409 as Registro,
  orcamentoPut: jOrcamentoPut as Registro,
  termosPut: jTermosPut as Registro,
  usuariosPut: jUsuariosPut as Registro,
  reserva: jReserva as Registro,
  erroFiltro: jErroFiltro as Registro,
  erroRevisao: jErroRevisao as Registro,
  revisaoPost: jRevisaoPost as Registro,
  rotulos: jRotulos as Registro,
  erroLeitorProcessar: jErroLeitorProcessar as Registro,
  rotuloPost: jRotuloPost as Registro,
  saude: jSaude as Registro,
  saude503: jSaude503 as Registro,
  execucaoEmCurso: jExecEmCurso as Registro,
  execucaoConcluida: jExecConcluida as Registro,
};

/** Resposta HTTP com o status e o corpo que a API deu. */
export function responder(r: Registro): () => Response {
  return () => new Response(JSON.stringify(r.corpo), { status: r.status, headers: { 'Content-Type': 'application/json' } });
}

/** As chaves de filtro que a API aceita, lidas da própria recusa 422 dela. */
export function filtrosAceitosPelaApi(): string[] {
  const corpo = jErroFiltro.corpo as { detail: { ctx: { expected: string } }[] };
  return [...corpo.detail[0].ctx.expected.matchAll(/'([^']+)'/g)].map((m) => m[1]);
}

/** Cópia profunda, para um teste derivar um caso sem mexer no original. */
export function copia<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}
