/**
 * Plural de verdade nos textos montados em pedaços (docs/textos-do-site.md; plano de textos, Review Focus): "1 alerta",
 * "2 alertas" — nunca "alerta(s)". Os três que sobraram depois da revisão por área: os alertas de cada resposta, os
 * documentos das condições da execução e as buscas que falharam numa execução.
 */
import { screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Condicoes } from '../componentes/Condicoes';
import { TabelaRespostas } from '../componentes/TabelaRespostas';
import { mesclarRespostas } from '../lib/respostas';
import { Execucoes } from '../paginas/Execucoes';
import { custo, execucoes, licitacaoC1 } from '../__fixtures__/contrato';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

afterEach(() => vi.unstubAllGlobals());

const L = licitacaoC1.licitacao;

describe('plural de verdade', () => {
  it('os alertas da verificação de cada resposta: "1 alerta" e "2 alertas"', () => {
    const [a, b, ...resto] = mesclarRespostas(licitacaoC1.respostas, licitacaoC1.verificacao_respostas);
    const respostas = [{ ...a, alertas: ['um'] }, { ...b, alertas: ['um', 'dois'] }, ...resto.map((r) => ({ ...r, alertas: [] }))];
    const { container } = renderizar(<TabelaRespostas slug={L.slug} respostas={respostas} q13={L.q13_estruturada} />);
    const linha = (id: string) => container.querySelector(`tr[data-pergunta="${id}"]`) as HTMLElement;
    expect(within(linha(a.pergunta_id)).getByText('1 alerta da verificação')).toBeInTheDocument();
    expect(within(linha(b.pergunta_id)).getByText('2 alertas da verificação')).toBeInTheDocument();
  });

  it('os documentos das condições da execução concordam com o total: "1 de 1 documento", "2 de 3 documentos"', () => {
    const um = renderizar(<Condicoes c={{ ...L.condicoes!, documentos: { obtidos: 1, esperados: 1 } }} />);
    expect(um.container.textContent).toContain('1 de 1 documento ·');
    um.unmount();
    const tres = renderizar(<Condicoes c={{ ...L.condicoes!, documentos: { obtidos: 2, esperados: 3 } }} />);
    expect(tres.container.textContent).toContain('2 de 3 documentos ·');
  });

  it('a execução com uma busca que falhou diz "1 busca falhou"', async () => {
    fetchFalso({ '/api/execucoes': execucoes, '/api/custo': custo });
    const { container } = renderizar(<Execucoes />);
    expect(await screen.findByText(/1 busca falhou/)).toBeInTheDocument();
    expect(container.textContent).not.toContain('busca(s)');
  });
});
