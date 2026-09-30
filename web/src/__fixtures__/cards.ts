/**
 * Cards DERIVADOS de um card real (`contrato/licitacoes.json`, o C1 do
 * cenário), mudando só o campo que o caso exercita. A forma do objeto é a da
 * API; o valor trocado é o do caso — nenhum campo daqui existe só no front.
 *
 * O relógio destes casos é AGORA = 24/09/2026 12:00 em Brasília. Cada card
 * cobre uma linha da tabela da regra do prazo (web/design/README.md §4) ou um
 * dos três formatos de custo. `fim_prazo` vem como o importador grava
 * (migracao/regras.py:fim_prazo): ISO com o fuso de Brasília.
 */
import type { Card } from '../api/tipos';
import { cardC1, copia } from './contrato';

export const AGORA = new Date('2026-09-24T12:00:00-03:00');

/** `sessao_q1` não vem da API: o detalhe calcula da Q1 aprovada (lib/prazo.ts:dataDaQ1). */
export type CardComQ1 = Card & { sessao_q1?: string | null };

let seq = 0;

export function card(parcial: Partial<CardComQ1> = {}): CardComQ1 {
  seq += 1;
  const controle = parcial.controle ?? `12345678000190-1-${String(seq).padStart(6, '0')}/2026`;
  return { ...copia(cardC1), controle, slug: controle.replace('/', '-'), ...parcial };
}

// ---- prazo (README §4), relativos a AGORA
export const urgenteComHora = card({
  local: 'Adrianópolis/PR',
  fim_prazo: '2026-09-28T09:00:00-03:00',
  fim_prazo_tem_hora: true,
});
export const umDia = card({ local: 'Um Dia/MG', fim_prazo: '2026-09-25T00:00:00-03:00', fim_prazo_tem_hora: false });
export const encerradaRecente = card({
  local: 'Encerrada/RS',
  fim_prazo: '2026-09-21T00:00:00-03:00',
  fim_prazo_tem_hora: false,
});
export const encerradaHojeCedo = card({
  local: 'Hoje Cedo/SP',
  fim_prazo: '2026-09-24T10:00:00-03:00',
  fim_prazo_tem_hora: true,
});
export const aviso = card({ local: 'Aviso/BA', fim_prazo: '2026-10-09T00:00:00-03:00', fim_prazo_tem_hora: false });
export const longe = card({ local: 'Longe/PE', fim_prazo: '2026-11-30T00:00:00-03:00', fim_prazo_tem_hora: false });
export const semPrazo = card({ local: 'Sem Prazo/GO', fim_prazo: null, fim_prazo_tem_hora: null });
export const q1Passou = card({ local: 'Paulo Bento/RS', fim_prazo: null, fim_prazo_tem_hora: null, sessao_q1: '2026-09-10' });
export const q1Futura = card({ local: 'Q1 Futura/RS', fim_prazo: null, fim_prazo_tem_hora: null, sessao_q1: '2026-10-02' });
/** 01:00 UTC do dia 25 = 22:00 do dia 24 em Brasília: é HOJE, não amanhã. */
export const viradaUtc = card({ local: 'Virada/AM', fim_prazo: '2026-09-25T01:00:00Z', fim_prazo_tem_hora: true });

// ---- custo. O C1 real rodou LOCAL (agente, sem API): "local · sem API". O desconhecido é o que rodou NA API
// sem preço na tabela (um modelo novo da OpenAI, por exemplo): esse sim é "preço não configurado" (ADR-012).
export const custoDesconhecido = card({
  local: 'Sem preço/MG',
  procedencia: 'api',
  provedor: 'openai',
  brl: null,
  preco_conhecido: false,
  brl_legado: null,
});
export const custoConhecido = card({
  local: 'Caro/SP',
  procedencia: 'api',
  provedor: 'claude',
  modelo: 'claude-opus-5',
  brl: 1234.5,
  preco_conhecido: true,
});
export const custoLegado = card({
  local: 'Legado/PR',
  procedencia: 'legado',
  brl: null,
  brl_legado: '3.210',
  preco_conhecido: true,
});
