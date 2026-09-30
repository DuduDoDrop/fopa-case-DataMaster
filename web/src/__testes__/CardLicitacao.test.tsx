/**
 * O card do painel no formato de painel.css (README §3), alimentado pelas
 * linhas REAIS de `GET /api/licitacoes` (C1 agente, C2 API legado, C3
 * injeção, C4 sem extração, C9 fora do escopo) e por derivadas delas.
 */
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CardLicitacao } from '../componentes/CardLicitacao';
import { AGORA, aviso, card, custoConhecido, custoLegado, encerradaRecente, longe, urgenteComHora } from '../__fixtures__/cards';
import { AGORA_CONTRATO, cardC1, cardC2, cardC3, cardC4 } from '../__fixtures__/contrato';
import { renderizar } from './ajuda';

function faixaNums(container: HTMLElement) {
  const nums = container.querySelector('.nums');
  if (!nums) throw new Error('card sem .nums');
  return nums as HTMLElement;
}

describe('custo no card', () => {
  it('rodou LOCAL (agente, sem API): custo "local · sem API" — nem R$ 0,00, nem "preço não configurado"', () => {
    // 0 tokens quando a extração rodou local: a flag diz onde rodou; não há preço a configurar.
    const { container } = renderizar(<CardLicitacao card={cardC1} agora={AGORA_CONTRATO} />);
    expect(within(faixaNums(container)).getByText('local · sem API')).toBeInTheDocument();
    expect(container.textContent).not.toContain('R$ 0,00');
    expect(container.textContent).not.toContain('preço não configurado');
  });

  it('rodou na API sem preço na tabela continua "preço não configurado"', () => {
    const c = card({ procedencia: 'api', provedor: 'openai', brl: null, preco_conhecido: false, brl_legado: null });
    const { container } = renderizar(<CardLicitacao card={c} agora={AGORA} />);
    expect(within(faixaNums(container)).getByText('preço não configurado')).toBeInTheDocument();
  });

  it('extração pela API da v2: o custo gravado é o legado, e diz que é legado', () => {
    const { container } = renderizar(<CardLicitacao card={cardC2} agora={AGORA_CONTRATO} />);
    expect(within(faixaNums(container)).getByText('R$ 4,83 (legado)')).toBeInTheDocument();
  });

  it('custo conhecido com separador de milhar', () => {
    const { container } = renderizar(<CardLicitacao card={custoConhecido} agora={AGORA} />);
    expect(within(faixaNums(container)).getByText('R$ 1.234,50')).toBeInTheDocument();
  });

  it('legado com numeric em string', () => {
    const { container } = renderizar(<CardLicitacao card={custoLegado} agora={AGORA} />);
    expect(within(faixaNums(container)).getByText('R$ 3,21 (legado)')).toBeInTheDocument();
  });
});

describe('estrutura do card', () => {
  it('C1 real fecha em 3 dias: borda e prazo com a classe urgente', () => {
    const { container } = renderizar(<CardLicitacao card={cardC1} agora={AGORA_CONTRATO} />);
    const artigo = container.querySelector('article.card')!;
    expect(artigo).toHaveClass('urgente');
    const prazo = artigo.querySelector('.prazo')!;
    expect(prazo).toHaveClass('urgente');
    expect(prazo.querySelector('b')!.textContent).toBe('3 dias');
    expect(prazo.querySelector('span')!.textContent).toBe('até a sessão');
  });

  it('C3 real encerrou há 2 dias: sem borda, "há 2 dia(s)"', () => {
    const { container } = renderizar(<CardLicitacao card={cardC3} agora={AGORA_CONTRATO} />);
    const artigo = container.querySelector('article.card')!;
    expect(artigo).not.toHaveClass('urgente');
    expect(artigo).not.toHaveClass('aviso');
    expect(artigo.querySelector('.prazo span')!.textContent).toBe('há 2 dias');
  });

  it('a barrinha do começo do card: vermelha até 7 dias, amarela até 20, verde depois', () => {
    const cor = (c: typeof longe) => {
      const { container, unmount } = renderizar(<CardLicitacao card={c} agora={AGORA} />);
      const artigo = container.querySelector('article.card')!;
      const classes = ['urgente', 'aviso', 'folga'].filter((k) => artigo.classList.contains(k));
      unmount();
      return classes;
    };
    expect(cor(urgenteComHora)).toEqual(['urgente']);
    expect(cor(aviso)).toEqual(['aviso']);
    expect(cor(longe)).toEqual(['folga']);
    expect(cor(encerradaRecente)).toEqual([]);                 // encerrada: sem barra
  });

  it('encerrada derivada não leva borda vermelha', () => {
    const { container } = renderizar(<CardLicitacao card={encerradaRecente} agora={AGORA} />);
    expect(container.querySelector('article.card')).not.toHaveClass('urgente');
  });

  it('ancoragem N/M: ok só quando N == M > 0', () => {
    const cheio = renderizar(<CardLicitacao card={card({ ancoradas: 15, respondidas: 15 })} agora={AGORA} />);
    expect(within(faixaNums(cheio.container)).getByText('15/15').closest('.num')).toHaveClass('ok');
    cheio.unmount();
    const falta = renderizar(<CardLicitacao card={card({ ancoradas: 14, respondidas: 15 })} agora={AGORA} />);
    expect(within(faixaNums(falta.container)).getByText('14/15').closest('.num')).toHaveClass('al');
  });

  it('procedência é rótulo .marca, nunca cor', () => {
    const { container } = renderizar(<CardLicitacao card={cardC1} agora={AGORA_CONTRATO} />);
    const marca = container.querySelector('.rotulos .marca')!;
    expect(marca.textContent).toBe('local');
    expect(marca.className).toBe('marca');
  });

  it('flag de onde rodou: agente é LOCAL, API da Anthropic e da OpenAI são API (o provedor vai na dica), legado reconstruída', () => {
    const local = renderizar(<CardLicitacao card={cardC1} agora={AGORA_CONTRATO} />);
    expect(local.container.querySelector('.rotulos .marca')!.getAttribute('title')).toMatch(/Extração local, sem serviço pago/);
    local.unmount();
    const a = renderizar(<CardLicitacao card={cardC2} agora={AGORA_CONTRATO} />);
    expect(a.container.querySelector('.rotulos .marca')!.textContent).toBe('api');
    expect(a.container.querySelector('.rotulos .marca')!.getAttribute('title')).toBe('Extração no serviço da Anthropic.');
    a.unmount();
    const o = renderizar(<CardLicitacao card={card({ procedencia: 'api', provedor: 'openai' })} agora={AGORA} />);
    expect(o.container.querySelector('.rotulos .marca')!.textContent).toBe('api');
    expect(o.container.querySelector('.rotulos .marca')!.getAttribute('title')).toBe('Extração no serviço da OpenAI (provedor alternativo).');
    o.unmount();
    const l = renderizar(<CardLicitacao card={custoLegado} agora={AGORA} />);
    expect(l.container.querySelector('.rotulos .marca')!.textContent).toBe('reconstruída');
  });

  it('injeção (C3 real) é a tag forte .tagsusp', () => {
    const { container } = renderizar(<CardLicitacao card={cardC3} agora={AGORA_CONTRATO} />);
    expect(container.querySelector('.tagsusp')!.textContent).toBe('Prompt Injection - Conteúdo Suspeito');
  });

  it('alertas globais reais em p.alerta; no máximo 3, cortados em 300 caracteres', () => {
    const real = renderizar(<CardLicitacao card={cardC1} agora={AGORA_CONTRATO} />);
    expect(real.container.querySelector('p.alerta')!.textContent).toBe(cardC1.alertas_globais[0]);
    real.unmount();
    const longo = 'x'.repeat(400);
    const c = card({ alertas_globais: ['RN-01: a', 'RN-02: b', longo, 'RN-04: d'] });
    const { container } = renderizar(<CardLicitacao card={c} agora={AGORA} />);
    const alertas = container.querySelectorAll('p.alerta');
    expect(alertas).toHaveLength(3);
    expect(alertas[2].textContent).toHaveLength(300);
  });

  it('ações: "Ver as 17 respostas" leva ao detalhe; PNCP abre em nova aba', () => {
    renderizar(<CardLicitacao card={urgenteComHora} agora={AGORA} />);
    const ver = screen.getByRole('link', { name: 'Ver as 17 respostas' });
    expect(ver).toHaveAttribute('href', `/licitacao/${urgenteComHora.slug}`);
    expect(ver).toHaveClass('forte');
    const pncp = screen.getByRole('link', { name: 'Abrir no PNCP' });
    expect(pncp).toHaveAttribute('target', '_blank');
    expect(pncp).toHaveAttribute('rel', 'noopener');
  });

  it('sem extração (C4 real): ação desabilitada com o motivo, e um único "ainda não extraída"', () => {
    const { container } = renderizar(<CardLicitacao card={cardC4} agora={AGORA_CONTRATO} />);
    const morto = screen.getByText('sem extração');
    expect(morto).toHaveAttribute('aria-disabled', 'true');
    expect(morto).toHaveAttribute('title', 'Esta licitação ainda não foi extraída.');
    expect(morto).not.toHaveAttribute('href');
    const nums = faixaNums(container);
    expect(nums.querySelectorAll('.num')).toHaveLength(1);
    expect(nums.textContent).toContain('ainda não extraída');
  });

  it('fora do recorte de 2026 (C4 real, sem data nenhuma) leva o rótulo, e só ele', () => {
    const fora = renderizar(<CardLicitacao card={cardC4} agora={AGORA_CONTRATO} />);
    expect(cardC4.no_recorte).toBe(false);
    expect(within(fora.container).getByText('fora do recorte')).toHaveClass('marca');
    fora.unmount();
    const dentro = renderizar(<CardLicitacao card={cardC1} agora={AGORA_CONTRATO} />);
    expect(within(dentro.container).queryByText('fora do recorte')).toBeNull();
  });

  it('meta = modalidade · controle; objeto cortado em 340', () => {
    const c = card({ objeto: 'o'.repeat(500) });
    const { container } = renderizar(<CardLicitacao card={c} agora={AGORA} />);
    expect(container.querySelector('.meta')!.textContent).toBe(`${cardC1.modalidade} · ${c.controle}`);
    expect(container.querySelector('.obj')!.textContent).toHaveLength(340);
  });
});

describe('flag "sem PDF válido"', () => {
  it('a licitação cujo edital não é PDF que o sistema lê leva a flag, com o formato no title', () => {
    const c = card({ estado: 'formato_nao_suportado', sem_pdf: 'RTF' });
    renderizar(<CardLicitacao card={c} agora={AGORA} />);
    const flag = screen.getByText('sem PDF válido');
    expect(flag.getAttribute('title')).toMatch(/RTF/);
    expect(flag.getAttribute('title')).toMatch(/não processa/);
  });

  it('as outras não levam a flag', () => {
    renderizar(<CardLicitacao card={card({ sem_pdf: null })} agora={AGORA} />);
    expect(screen.queryByText('sem PDF válido')).toBeNull();
  });
});
