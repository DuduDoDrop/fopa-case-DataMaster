/**
 * Números, dinheiro e datas no formato do HTML (README §1).
 *
 * Tudo com separador de milhar via Intl pt-BR. O `_brl` do painel v2 trocava
 * ponto por vírgula e pronto, e acima de R$ 1.000 saía "R$ 1234,56".
 */

const FUSO = 'America/Sao_Paulo';

const fmtInteiro = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const fmtDecimal2 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtDecimal1 = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const fmtAte2 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });

/**
 * `numeric` do Postgres chega como string ("6.560") quando o driver
 * serializa Decimal; null/undefined/"" continuam ausentes — nunca zero.
 */
export function numero(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

export function milhar(v: number | string | null | undefined): string {
  const n = numero(v);
  return n === null ? '—' : fmtInteiro.format(n);
}

export function decimal1(v: number | string | null | undefined): string {
  const n = numero(v);
  return n === null ? '—' : fmtDecimal1.format(n);
}

/** "US$ 47,75": o que a fatura das APIs cobra, em dólar (os gastos com IA da home, 26/09). */
export function usd(v: number | string | null | undefined): string {
  const n = numero(v);
  return n === null ? '—' : 'US$ ' + fmtDecimal2.format(n);
}

/** "R$ 1.234,56" com espaço comum, como o `_brl` do HTML. */
export function brl(v: number | string | null | undefined): string {
  const n = numero(v);
  return n === null ? '—' : 'R$ ' + fmtDecimal2.format(n);
}

/**
 * Valor grande encurtado para tile: "R$ 5,66 bi", "R$ 449,0 mi", "R$ 1,80 mi". Abaixo de 1 milhão, `brl`.
 * O tile do Analytics cortava "R$ 5.662.802.496,7…" (24/09 noite); o valor inteiro vai no `title`.
 */
/**
 * O rótulo do eixo de um gráfico: "R$ 1,25 bi", "R$ 500 mi", "R$ 200 mil", "R$ 0" — curto e sem centavos. O eixo do
 * Analytics mostrava "R$ 200.000.000,00", que não cabia na margem e saía comido à esquerda.
 */
export function brlEixo(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1e9) return 'R$ ' + fmtAte2.format(v / 1e9) + ' bi';
  if (abs >= 1e6) return 'R$ ' + fmtAte2.format(v / 1e6) + ' mi';
  if (abs >= 1e3) return 'R$ ' + fmtAte2.format(v / 1e3) + ' mil';
  return 'R$ ' + fmtAte2.format(v);
}

export function brlCompacto(v: number | string | null | undefined): string {
  const n = numero(v);
  if (n === null) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e9) return 'R$ ' + fmtDecimal2.format(n / 1e9) + ' bi';
  if (abs >= 1e6) return 'R$ ' + (abs >= 1e8 ? fmtDecimal1 : fmtDecimal2).format(n / 1e6) + ' mi';
  return brl(n);
}

export const PRECO_NAO_CONFIGURADO = 'preço não configurado';
/** A extração rodou LOCAL (agente, ADR-014): não houve chamada de API — nem R$ 0,00, nem preço a configurar. */
export const SEM_API_LOCAL = 'local · sem API';

/**
 * Custo de uma execução (card, detalhe, tile).
 *
 * - `preco_conhecido=false` ou `brl` NULL: "preço não configurado". Foi assim
 *   que 93 relatórios do agente saíram dizendo "R$ 0,00": a chamada foi
 *   cobrada, só não havia tabela de preço (ADR-012, saida.py:169-173).
 * - legado: o custo como veio da v2, nunca recalculado (plano §9, passo 4), e
 *   dito como legado. Legado zerado é a mesma mentira do "de graça".
 * - rodou local (`procedencia` agente): "local · sem API" — o que a sessão
 *   custou fora daqui não é medido, e dizer R$ 0,00 seria a mesma mentira.
 */
export function custo(c: {
  brl: number | string | null;
  preco_conhecido: boolean | null;
  brl_legado?: number | string | null;
  procedencia?: string | null;
}): string {
  if (c.procedencia === 'agente') return SEM_API_LOCAL;
  const atual = numero(c.brl);
  if (atual !== null && c.preco_conhecido !== false) return brl(atual);
  const legado = numero(c.brl_legado);
  if (legado !== null && legado > 0 && c.preco_conhecido !== false) return `${brl(legado)} (legado)`;
  return PRECO_NAO_CONFIGURADO;
}

/**
 * Custo de uma RODADA (`execucoes_workflow`: /execucoes e o detalhe).
 *
 * A API soma as chamadas ao modelo da rodada; rodada sem chamada leva o valor
 * gravado na linha, e as linhas importadas do `70_extracao_por_agente.py`
 * vêm com 0 — a extração pelo agente, cujo preço nunca foi medido. Mostrar
 * "R$ 0,00" ali é a mentira do "de graça" (README §2.5). Então:
 *
 * - chamada sem preço e nada conhecido: "preço não configurado";
 * - parte conhecida + chamadas sem preço: "R$ X + N sem preço";
 * - nenhuma chamada registrada e valor zerado/ausente: "—" (não foi medido);
 * - o resto: o valor, com milhar. R$ 0,00 só sai quando houve chamada com
 *   preço conhecido e ela custou zero (o provedor simulado).
 */
export function custoRodada(r: {
  custo_brl: number | string | null | undefined;
  chamadas?: number | null;
  sem_preco?: number | null;
}): string {
  const c = numero(r.custo_brl);
  const semPreco = r.sem_preco ?? 0;
  if (semPreco > 0) return c !== null && c > 0 ? `${brl(c)} + ${milhar(semPreco)} sem preço` : PRECO_NAO_CONFIGURADO;
  if (!r.chamadas && (c === null || c === 0)) return '—';
  return brl(c);
}

export const SEM_CHAMADA_REGISTRADA = 'nenhuma chamada ao modelo registrada nesta rodada: o custo não foi medido';

const fmtData = new Intl.DateTimeFormat('pt-BR', { timeZone: FUSO, day: '2-digit', month: '2-digit', year: 'numeric' });
const fmtDataHora = new Intl.DateTimeFormat('pt-BR', {
  timeZone: FUSO,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});
const fmtHora = new Intl.DateTimeFormat('pt-BR', { timeZone: FUSO, hour: '2-digit', minute: '2-digit' });

function comoData(v: string | null | undefined): Date | null {
  if (!v) return null;
  // "AAAA-MM-DD" puro é um DIA, não um instante: sem isto o JS lê como
  // meia-noite UTC e, em Brasília, vira o dia anterior.
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return new Date(`${v}T12:00:00-03:00`);
  // "AAAA-MM-DDThh:mm[:ss]" SEM fuso é hora de Brasília — é assim que o PNCP manda o
  // data_fim_vigencia (e o W01 guarda na lista das novas). Sem isto o navegador lê no fuso
  // DELE: em Tóquio, 09:00 do dia 15 virava dia 14 em Brasília.
  const semFuso = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(v);
  const d = new Date(semFuso ? `${v}-03:00` : v);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** dd/mm/aaaa no fuso de Brasília. */
export function data(v: string | null | undefined): string {
  const d = comoData(v);
  return d ? fmtData.format(d) : '—';
}

/** dd/mm/aaaa hh:mm no fuso de Brasília. */
export function dataHora(v: string | null | undefined): string {
  const d = comoData(v);
  return d ? fmtDataHora.format(d).replace(',', '') : '—';
}

/**
 * Instantes ISO dentro de um texto livre (erro do n8n, mensagem de alerta)
 * em dd/mm/aaaa hh:mm de Brasília: "nova tentativa a partir de
 * 2026-09-24T09:01:01Z" saía cru na tela de e-mails. Só com fuso explícito
 * (Z ou ±hh:mm) — sem fuso o instante é ambíguo e fica como veio.
 */
export function datasNoTexto(texto: string): string {
  return texto.replace(/\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})/g, (iso) => {
    const d = dataHora(iso);
    return d === '—' ? iso : d;
  });
}

export function hora(d: Date): string {
  return fmtHora.format(d);
}

/** "3,2 s", "4 min 05 s". */
export function duracao(segundos: number | string | null | undefined): string {
  const s = numero(segundos);
  if (s === null) return '—';
  if (s < 60) return `${decimal1(s)} s`;
  const min = Math.floor(s / 60);
  const resto = Math.round(s - min * 60);
  return `${min} min ${String(resto).padStart(2, '0')} s`;
}

/** Plural simples no molde do HTML ("1 dia", "2 dias"). */
export function plural(n: number, singular: string, pluralTexto: string): string {
  return `${milhar(n)} ${Math.abs(n) === 1 ? singular : pluralTexto}`;
}
