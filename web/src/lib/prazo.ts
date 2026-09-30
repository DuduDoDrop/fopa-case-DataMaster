/**
 * A regra do prazo — o campo que ordena a lista (web/design/README.md §4).
 *
 * `dias = fim_prazo − hoje`, contado em DIAS DE CALENDÁRIO de Brasília e
 * calculado AQUI, no navegador, a cada renderização. No painel v2 o número
 * era congelado na geração do HTML (painel.py:318) e o card dizia "3 dias"
 * uma semana depois; `v_card` deixa `dias` de fora exatamente por isso.
 *
 * `fim_prazo_tem_hora` importa num caso só: a sessão é HOJE e a hora já
 * passou. Sem a hora, "0 dias" é urgente até o fim do dia; com a hora, a
 * licitação já fechou e não pode aparecer em "urgentes" (o filtro da v2
 * incluía encerradas: defeito que não volta).
 */
import type { Card, RespostaDetalhe } from '../api/tipos';
import { hora } from './formato';

const FUSO = 'America/Sao_Paulo';
const fmtDia = new Intl.DateTimeFormat('en-CA', { timeZone: FUSO, year: 'numeric', month: '2-digit', day: '2-digit' });

/** O dia de calendário em Brasília, "AAAA-MM-DD". */
export function diaEmSaoPaulo(d: Date): string {
  return fmtDia.format(d);
}

function diaParaUtc(dia: string): number {
  const [a, m, d] = dia.split('-').map(Number);
  return Date.UTC(a, m - 1, d);
}

function diferencaEmDias(de: string, ate: string): number {
  return Math.round((diaParaUtc(ate) - diaParaUtc(de)) / 86_400_000);
}

function ddmmaaaa(dia: string): string {
  return dia.split('-').reverse().join('/');
}

/** A barrinha do começo do card: vermelha até 7 dias, amarela até 20, verde depois. */
export type ClassePrazo = '' | 'urgente' | 'aviso' | 'folga';

export interface Prazo {
  /** null = prazo desconhecido. */
  dias: number | null;
  encerrada: boolean;
  classe: ClassePrazo;
  /** o `<b>` do `.prazo` */
  titulo: string;
  /** o `<span>` do `.prazo` */
  detalhe: string;
  /** texto completo para o `title` (data e hora de Brasília) */
  dica: string;
}

type ComPrazo = Pick<Card, 'fim_prazo' | 'fim_prazo_tem_hora'> & {
  sessao_q1?: string | null;
  fim_prazo_pncp_invalido?: string | null;
};

export function calcularPrazo(c: ComPrazo, agora: Date = new Date()): Prazo {
  const hoje = diaEmSaoPaulo(agora);
  const instante = c.fim_prazo ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(c.fim_prazo) ? `${c.fim_prazo}T00:00:00-03:00` : c.fim_prazo) : null;

  if (!instante || Number.isNaN(instante.getTime())) {
    // O inventário não trouxe prazo — mas a extração pode ter a data, e só
    // vale se a Q1 foi APROVADA (quem entrega `sessao_q1` já filtrou).
    // Paulo Bento/RS mostrava "prazo não informado" com a data ancorada no
    // edital (painel.py:_data_da_q1).
    if (c.sessao_q1 && /^\d{4}-\d{2}-\d{2}$/.test(c.sessao_q1)) {
      const passou = c.sessao_q1 < hoje;
      return {
        dias: null,
        encerrada: false,
        classe: '',
        titulo: passou ? 'sessão encerrada' : 'sessão',
        detalhe: `em ${ddmmaaaa(c.sessao_q1)} (conforme a Q1)`,
        dica: 'Data obtida na resposta aprovada da Q1; o PNCP não informou o prazo final.',
      };
    }
    // Data de sessão absurda no PNCP (mais de 2 anos depois da publicação — db/047): o servidor já a tirou do
    // `fim_prazo`; aqui ela aparece como inválida, em vez de "3522 dias até a sessão" (Brasília/DF).
    const absurda = c.fim_prazo_pncp_invalido ? new Date(c.fim_prazo_pncp_invalido) : null;
    if (absurda && !Number.isNaN(absurda.getTime())) {
      return {
        dias: null,
        encerrada: false,
        classe: '',
        titulo: 'data inválida',
        detalhe: `no PNCP: ${ddmmaaaa(diaEmSaoPaulo(absurda))}`,
        dica: 'O PNCP informa a sessão mais de 2 anos após a publicação, provável erro de digitação. A licitação é tratada como sem data.',
      };
    }
    return { dias: null, encerrada: false, classe: '', titulo: '—', detalhe: 'prazo não informado', dica: '' };
  }

  const dia = diaEmSaoPaulo(instante);
  const dias = diferencaEmDias(hoje, dia);
  const dica = c.fim_prazo_tem_hora ? `fim do prazo: ${ddmmaaaa(dia)} às ${hora(instante)}` : `fim do prazo: ${ddmmaaaa(dia)}`;

  if (dias < 0) {
    return { dias, encerrada: true, classe: '', titulo: 'encerrado', detalhe: dias === 0 ? 'hoje' : `há ${-dias} ${dias === -1 ? 'dia' : 'dias'}`, dica };
  }
  if (dias === 0 && c.fim_prazo_tem_hora && instante.getTime() <= agora.getTime()) {
    // A tabela §4 tem uma linha para encerrada: "há N dia(s)". A hora de
    // hoje que já passou continua no `title` (dica), não inventa um formato.
    return { dias, encerrada: true, classe: '', titulo: 'encerrado', detalhe: dias === 0 ? 'hoje' : `há ${-dias} ${dias === -1 ? 'dia' : 'dias'}`, dica };
  }
  const titulo = `${dias} dia${dias === 1 ? '' : 's'}`;
  const classe: ClassePrazo = dias <= 7 ? 'urgente' : dias <= 20 ? 'aviso' : 'folga';
  return { dias, encerrada: false, classe, titulo, detalhe: 'até a sessão', dica };
}

/** Urgente = ABERTA e 0 ≤ dias ≤ 7. Nunca encerrada. */
export function ehUrgente(p: Prazo): boolean {
  return !p.encerrada && p.dias !== null && p.dias >= 0 && p.dias <= 7;
}

const RE_DATA_Q1 = /(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})/;

/**
 * A data da sessão que a extração encontrou (AAAA-MM-DD), só com a Q1
 * APROVADA: data não verificada não vale para decidir nada (painel.py).
 */
export function dataDaQ1(respostas: Pick<RespostaDetalhe, 'pergunta_id' | 'veredito' | 'resposta'>[]): string | null {
  const q1 = respostas.find((r) => r.pergunta_id === 'Q1');
  if (!q1 || q1.veredito !== 'APROVADO') return null;
  const m = RE_DATA_Q1.exec(q1.resposta ?? '');
  if (!m) return null;
  return `${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
}

/**
 * Abertas por `dias` crescente → encerradas → sem prazo; o nome desempata.
 * A lista serve para decidir onde entrar, e o que já fechou não é mais
 * decisão (painel.py:coletar).
 */
export function ordenarPorPrazo<T extends ComPrazo & { local: string }>(cards: T[], agora: Date = new Date()): T[] {
  const chave = (c: T): [number, number] => {
    const p = calcularPrazo(c, agora);
    if (p.dias === null) return [2, 0];
    if (p.encerrada) return [1, p.dias];
    return [0, p.dias];
  };
  return [...cards]
    .map((c) => ({ c, k: chave(c) }))
    .sort((a, b) => a.k[0] - b.k[0] || a.k[1] - b.k[1] || a.c.local.localeCompare(b.c.local, 'pt-BR'))
    .map((x) => x.c);
}
