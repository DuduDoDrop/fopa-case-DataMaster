/**
 * Regra do prazo — web/design/README.md §4.
 *
 * `dias` é calculado no navegador em America/Sao_Paulo. No HTML da v2 ele era
 * congelado na geração (painel.py:318) e o card dizia "3 dias" uma semana
 * depois: o defeito que não volta. O processo de teste roda em Asia/Tokyo
 * (vite.config.ts) para provar que o fuso da máquina não entra na conta.
 */
import { describe, expect, it } from 'vitest';
import { calcularPrazo, dataDaQ1, diaEmSaoPaulo, ordenarPorPrazo } from '../lib/prazo';
import {
  AGORA,
  aviso,
  encerradaHojeCedo,
  encerradaRecente,
  longe,
  q1Futura,
  q1Passou,
  semPrazo,
  umDia,
  urgenteComHora,
  viradaUtc,
} from '../__fixtures__/cards';
import { licitacaoC1 } from '../__fixtures__/contrato';
import { mesclarRespostas } from '../lib/respostas';

// Derivada do C1 real: a Q1 do cenário diz "resposta Q1"; aqui ela traz a data.
const RESPOSTAS = mesclarRespostas(licitacaoC1.respostas, licitacaoC1.verificacao_respostas).map((r) =>
  r.pergunta_id === 'Q1' ? { ...r, resposta: '28/09/2026 às 09h00' } : r,
);

describe('tabela da regra do prazo (README §4)', () => {
  it.each([
    ['Q1 aprovada com data já passada', q1Passou, '', 'sessão encerrada', 'em 10/09/2026 (conforme a Q1)'],
    ['Q1 aprovada com data futura', q1Futura, '', 'sessão', 'em 02/10/2026 (conforme a Q1)'],
    ['dias desconhecido', semPrazo, '', '—', 'prazo não informado'],
    ['dias < 0', encerradaRecente, '', 'encerrado', 'há 3 dias'],
    ['0 ≤ dias ≤ 7, com hora', urgenteComHora, 'urgente', '4 dias', 'até a sessão'],
    ['1 dia, singular', umDia, 'urgente', '1 dia', 'até a sessão'],
    ['8 ≤ dias ≤ 20', aviso, 'aviso', '15 dias', 'até a sessão'],
    ['dias > 20: folga (a barrinha verde)', longe, 'folga', '67 dias', 'até a sessão'],
  ])('%s', (_nome, c, classe, titulo, detalheTexto) => {
    const p = calcularPrazo(c, AGORA);
    expect(p.classe).toBe(classe);
    expect(p.titulo).toBe(titulo);
    expect(p.detalhe).toBe(detalheTexto);
  });

  it('data de sessão absurda no PNCP: diz que é inválida, com a data, e não conta dias (db/047)', () => {
    // Brasília/DF: publicada em 18/05/2026, sessão em 19/05/2036 no PNCP — o card dizia "3522 dias até a sessão"
    const p = calcularPrazo({ ...semPrazo, fim_prazo_pncp_invalido: '2036-05-19T13:00:00+00:00' }, AGORA);
    expect(p.dias).toBeNull();
    expect(p.encerrada).toBe(false);
    expect(p.classe).toBe('');
    expect(p.titulo).toBe('data inválida');
    expect(p.detalhe).toBe('no PNCP: 19/05/2036');
    expect(p.dica).toMatch(/mais de 2 anos após a publicação/);
    // a Q1 aprovada, quando há, vale mais que a data absurda do PNCP
    expect(calcularPrazo({ ...q1Futura, fim_prazo_pncp_invalido: '2036-05-19T13:00:00+00:00' }, AGORA).titulo).toBe('sessão');
  });

  it('usa o dia de Brasília, não o de UTC nem o da máquina', () => {
    // 01:00Z do dia 25 = 22:00 do dia 24 em Brasília: fecha HOJE.
    const p = calcularPrazo(viradaUtc, AGORA);
    expect(p.dias).toBe(0);
    expect(p.encerrada).toBe(false);
    expect(p.classe).toBe('urgente');
    expect(p.titulo).toBe('0 dias');
    expect(diaEmSaoPaulo(new Date('2026-09-25T01:00:00Z'))).toBe('2026-09-24');
  });

  it('com hora declarada, a sessão de hoje que já passou é encerrada (tabela §4: "há N dia(s)")', () => {
    const p = calcularPrazo(encerradaHojeCedo, AGORA);
    expect(p.dias).toBe(0);
    expect(p.encerrada).toBe(true);
    expect(p.classe).toBe('');
    expect(p.titulo).toBe('encerrado');
    expect(p.detalhe).toBe('hoje');
    // a hora continua disponível, no title
    expect(p.dica).toBe('fim do prazo: 24/09/2026 às 10:00');
  });

  it('o número anda com o relógio (não é congelado)', () => {
    const amanha = new Date(AGORA.getTime() + 24 * 3600 * 1000);
    expect(calcularPrazo(urgenteComHora, AGORA).dias).toBe(4);
    expect(calcularPrazo(urgenteComHora, amanha).dias).toBe(3);
  });

  it('a Q1 real do cenário não tem data: nada de "sessão" inventada', () => {
    expect(dataDaQ1(mesclarRespostas(licitacaoC1.respostas, licitacaoC1.verificacao_respostas))).toBeNull();
  });

  it('data da Q1 só vale com veredito APROVADO', () => {
    expect(dataDaQ1(RESPOSTAS)).toBe('2026-09-28');
    const revisar = RESPOSTAS.map((r) => (r.pergunta_id === 'Q1' ? { ...r, veredito: 'REVISAR' as const } : r));
    expect(dataDaQ1(revisar)).toBeNull();
  });

  it('ordena abertas por dias, depois encerradas, depois sem prazo; nome desempata', () => {
    const ordem = ordenarPorPrazo([semPrazo, longe, encerradaRecente, aviso, urgenteComHora, umDia], AGORA).map(
      (c) => c.local,
    );
    expect(ordem).toEqual(['Um Dia/MG', 'Adrianópolis/PR', 'Aviso/BA', 'Longe/PE', 'Encerrada/RS', 'Sem Prazo/GO']);
  });
});
