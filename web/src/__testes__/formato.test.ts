/**
 * Números com separador de milhar e custo (README §1 e §2.5).
 *
 * O `_brl` do painel v2 trocava ponto por vírgula e pronto: acima de mil
 * saía "R$ 1234,56". E custo `null` virou "R$ 0,00" em 93 relatórios do
 * agente. Nenhum dos dois volta.
 */
import { describe, expect, it } from 'vitest';
import { brl, custo, custoRodada, data, dataHora, datasNoTexto, milhar, brlCompacto } from '../lib/formato';
import { custoConhecido, custoDesconhecido, custoLegado } from '../__fixtures__/cards';

describe('milhar', () => {
  it.each([
    [0, '0'],
    [999, '999'],
    [1925, '1.925'],
    [1234567, '1.234.567'],
    ['412345', '412.345'],
  ])('%s -> %s', (v, esperado) => {
    expect(milhar(v)).toBe(esperado);
  });

  it('sem número é travessão, não zero', () => {
    expect(milhar(null)).toBe('—');
    expect(milhar(undefined)).toBe('—');
  });
});

describe('brl', () => {
  it.each([
    [0, 'R$ 0,00'],
    [3.4, 'R$ 3,40'],
    [1234.56, 'R$ 1.234,56'],
    [1234567.8, 'R$ 1.234.567,80'],
    ['6.560', 'R$ 6,56'],
  ])('%s -> %s', (v, esperado) => {
    expect(brl(v)).toBe(esperado);
  });

  it('usa espaço comum depois do R$, como o HTML', () => {
    expect(brl(1)).not.toContain(' ');
  });

  it('null não vira R$ 0,00', () => {
    expect(brl(null)).toBe('—');
  });
});

describe('custo da execução', () => {
  it('rodou LOCAL (agente): "local · sem API" — não há chamada paga nem preço a configurar', () => {
    expect(custo({ brl: null, preco_conhecido: false, brl_legado: null, procedencia: 'agente' })).toBe('local · sem API');
    expect(custo({ brl: null, preco_conhecido: false, brl_legado: null, procedencia: 'api' })).toBe('preço não configurado');
  });

  it('preço desconhecido = "preço não configurado", nunca R$ 0,00', () => {
    expect(custo(custoDesconhecido)).toBe('preço não configurado');
  });

  it('brl NULL com preco_conhecido NULL também é desconhecido', () => {
    expect(custo({ brl: null, preco_conhecido: null, brl_legado: null })).toBe('preço não configurado');
  });

  it('preco_conhecido=false vence um brl que venha preenchido', () => {
    expect(custo({ brl: 0, preco_conhecido: false, brl_legado: null })).toBe('preço não configurado');
  });

  it('custo conhecido com milhar', () => {
    expect(custo(custoConhecido)).toBe('R$ 1.234,50');
  });

  it('legado diz que é legado', () => {
    expect(custo(custoLegado)).toBe('R$ 3,21 (legado)');
  });

  it('legado zerado era a mentira do "de graça": vira preço não configurado', () => {
    expect(custo({ brl: null, preco_conhecido: true, brl_legado: 0 })).toBe('preço não configurado');
  });
});

describe('custo de uma rodada (execucoes_workflow)', () => {
  it('rodada importada do agente, sem chamada registrada e gravada com 0: não é "R$ 0,00"', () => {
    // 119 linhas do 70_extracao_por_agente.py saíam "R$ 0,00" em /execucoes (QA 24/09)
    expect(custoRodada({ custo_brl: 0, chamadas: 0, sem_preco: 0 })).toBe('—');
    expect(custoRodada({ custo_brl: null, chamadas: 0, sem_preco: 0 })).toBe('—');
  });

  it('só chamadas sem preço: "preço não configurado", nunca "R$ 0,00 + N sem preço"', () => {
    expect(custoRodada({ custo_brl: 0, chamadas: 3, sem_preco: 3 })).toBe('preço não configurado');
    expect(custoRodada({ custo_brl: null, chamadas: 2, sem_preco: 2 })).toBe('preço não configurado');
  });

  it('parte conhecida + chamadas sem preço', () => {
    expect(custoRodada({ custo_brl: 1234.5, chamadas: 4, sem_preco: 1 })).toBe('R$ 1.234,50 + 1 sem preço');
  });

  it('chamada com preço conhecido que custou zero (simulado) continua R$ 0,00', () => {
    expect(custoRodada({ custo_brl: 0, chamadas: 3, sem_preco: 0 })).toBe('R$ 0,00');
  });

  it('valor gravado pela v2 numa rodada sem chamada registrada aparece', () => {
    expect(custoRodada({ custo_brl: '4.83', chamadas: 0, sem_preco: 0 })).toBe('R$ 4,83');
  });
});

describe('datas dentro de texto livre', () => {
  it('instante ISO com fuso vira dd/mm/aaaa hh:mm de Brasília', () => {
    expect(datasNoTexto('tentativa 1/5 falhou; nova tentativa a partir de 2026-09-24T09:01:01Z: SMTP não configurado')).toBe(
      'tentativa 1/5 falhou; nova tentativa a partir de 24/09/2026 06:01: SMTP não configurado',
    );
    expect(datasNoTexto('em 2026-09-24T06:49:27.566660+00:00')).toBe('em 24/09/2026 03:49');
  });

  it('sem fuso, só data ou identificador com data: fica como veio', () => {
    for (const t of ['snapshot 2026-09-24_0150', 'dia 2026-09-24', 'às 2026-09-24T09:01:01 local', 'sem data']) {
      expect(datasNoTexto(t)).toBe(t);
    }
  });
});

describe('instante sem fuso é hora de Brasília (PNCP)', () => {
  it('data e dataHora não trocam de dia nem de hora com o fuso do navegador (os testes rodam em Tóquio)', () => {
    expect(data('2026-10-15T09:00:00')).toBe('15/10/2026');
    expect(dataHora('2026-10-15T09:00:00')).toBe('15/10/2026 09:00');
    expect(dataHora('2026-10-15T09:00')).toBe('15/10/2026 09:00');
    // com fuso explícito continua valendo o que veio
    expect(dataHora('2026-10-15T12:00:00Z')).toBe('15/10/2026 09:00');
  });
});

describe('brlCompacto', () => {
  it('bilhão e milhão encurtam (o tile do Analytics cortava "R$ 5.662.802.496,7…"); o resto fica em reais', () => {
    expect(brlCompacto(5662802496.78)).toBe('R$ 5,66 bi');
    expect(brlCompacto(449020485.2)).toBe('R$ 449,0 mi');
    expect(brlCompacto(1800000)).toBe('R$ 1,80 mi');
    expect(brlCompacto(250000)).toBe(brl(250000));
    expect(brlCompacto(null)).toBe('—');
  });
});
