/**
 * Tabela das 17 (README §5, pagina.py:340-470) com o detalhe REAL da API:
 * `respostas` (crua, do modelo) e `verificacao_respostas` (do verificador)
 * chegam em listas separadas e o site junta por pergunta. Barra de status,
 * crítica como rótulo, evidência SEMPRE presente com os três estados de
 * ausência, e o link de origem por id numérico com #page=N.
 */
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { TentativasMelhorDeN } from '../api/tipos';
import { TabelaRespostas } from '../componentes/TabelaRespostas';
import { mesclarRespostas } from '../lib/respostas';
import { licitacaoC1 } from '../__fixtures__/contrato';
import { renderizar } from './ajuda';

const L = licitacaoC1.licitacao;
const SLUG = L.slug;
const RESPOSTAS = mesclarRespostas(licitacaoC1.respostas, licitacaoC1.verificacao_respostas);
const vr = (id: string) => licitacaoC1.verificacao_respostas.find((v) => v.pergunta_id === id)!;

function linha(container: HTMLElement, id: string): HTMLTableRowElement {
  const tr = container.querySelector(`tr[data-pergunta="${id}"]`);
  if (!tr) throw new Error(`linha ${id} não encontrada`);
  return tr as HTMLTableRowElement;
}

function renderTabela() {
  return renderizar(<TabelaRespostas slug={SLUG} respostas={RESPOSTAS} q13={L.q13_estruturada} />);
}

describe('junção respostas × verificacao_respostas', () => {
  it('as 17 linhas levam o veredito e o arquivo_id do verificador', () => {
    expect(RESPOSTAS).toHaveLength(17);
    for (const r of RESPOSTAS) {
      expect(r.veredito).toBe(vr(r.pergunta_id).veredito);
      expect(r.arquivo_id).toBe(vr(r.pergunta_id).arquivo_id);
    }
  });
});

describe('evidência', () => {
  it('as 17 linhas têm bloco de evidência, mesmo sem trecho', () => {
    const { container } = renderTabela();
    const linhas = container.querySelectorAll('tbody > tr[data-pergunta]');
    expect(linhas).toHaveLength(17);
    for (const tr of linhas) expect(tr.querySelector('blockquote')).not.toBeNull();
  });

  it('os três estados de ausência vêm de verificacao_respostas.ausencia', () => {
    const { container } = renderTabela();
    expect(vr('Q4').ausencia).toBe('nao_se_aplica');
    const naoAplica = linha(container, 'Q4').querySelector('blockquote')!;
    expect(naoAplica).toHaveClass('naoaplica');
    expect(naoAplica.textContent).toContain('Não se aplica a esta modalidade.');
    expect(naoAplica.textContent).toContain('credenciamento não tem tipo de pregão');

    const semEv = linha(container, 'Q6').querySelector('blockquote')!;
    expect(semEv).toHaveClass('semev');
    expect(semEv.textContent).toContain('não consta dos documentos');

    const faltaEv = linha(container, 'Q12').querySelector('blockquote')!;
    expect(faltaEv).toHaveClass('faltaev');
    expect(faltaEv.textContent).toContain('Evidência não encontrada.');
    expect(faltaEv.closest('details')).toHaveAttribute('open');
  });

  it('com trecho, o blockquote é o próprio trecho, sem classe de ausência', () => {
    const { container } = renderTabela();
    const bq = linha(container, 'Q2').querySelector('blockquote')!;
    expect(bq.className).toBe('');
    expect(bq.textContent).toBe('trecho Q2');
  });
});

describe('barra de status', () => {
  it('st-ok aprovado, st-rev revisar, st-nl não localizado (vence o veredito)', () => {
    const { container } = renderTabela();
    expect(linha(container, 'Q2')).toHaveClass('st-ok');
    expect(linha(container, 'Q9')).toHaveClass('st-rev');
    expect(linha(container, 'Q4')).toHaveClass('st-nl');
    expect(linha(container, 'Q6')).toHaveClass('st-nl');
  });

  it('crítica é rótulo .marca, e a linha crítica aprovada continua st-ok', () => {
    const { container } = renderTabela();
    const q1 = linha(container, 'Q1');
    expect(q1).toHaveClass('st-ok');
    expect(within(q1).getByText('crítica')).toHaveClass('marca');
    expect(within(linha(container, 'Q2')).queryByText('crítica')).toBeNull();
  });

  it('veredito em pílula .v com a classe do veredito', () => {
    const { container } = renderTabela();
    expect(linha(container, 'Q9').querySelector('.v')).toHaveClass('REVISAR');
    expect(linha(container, 'Q1').querySelector('.v')).toHaveClass('APROVADO');
  });
});

describe('origem', () => {
  it('link "arquivo — p. N" pelo arquivo_id do verificador, com #page=N', () => {
    const { container } = renderTabela();
    const a = within(linha(container, 'Q1')).getByRole('link', { name: '01 - Edital.pdf — p. 1' });
    expect(a).toHaveAttribute('href', `/api/pdf/${SLUG}/${vr('Q1').arquivo_id}#page=1`);
  });

  it('página corrigida: o link vai para a página final e o title diz a citada', () => {
    const { container } = renderTabela();
    expect(vr('Q10').pagina_final).toBe(1);
    const a = within(linha(container, 'Q10')).getByRole('link');
    expect(a.textContent).toBe('01 - Edital.pdf — p. 1');
    expect(a).toHaveAttribute('href', `/api/pdf/${SLUG}/${vr('Q10').arquivo_id}#page=1`);
    expect(a.getAttribute('title')).toContain('citou a p. 2');
  });

  it('nunca monta link pelo nome cru do arquivo; toda resposta ancorada tem link', () => {
    const { container } = renderTabela();
    const links = container.querySelectorAll('td.info a');
    const ancoradas = licitacaoC1.verificacao_respostas.filter((v) => v.arquivo_id !== null);
    expect(links).toHaveLength(ancoradas.length);
    for (const a of links) expect(a.getAttribute('href')).toMatch(new RegExp(`^/api/pdf/${SLUG}/\\d+#page=\\d+$`));
  });

  it('não localizado aparece como .nl, sem link', () => {
    const { container } = renderTabela();
    const origem = linha(container, 'Q6').querySelector('td.info')!;
    expect(origem.querySelector('a')).toBeNull();
    expect(origem.querySelector('.nl')!.textContent).toBe('não localizado');
  });
});

describe('Q13 estruturada (q13_estruturada da v_detalhe)', () => {
  it('table.dist com milhar, barra proporcional e total que confere', () => {
    const { container } = renderTabela();
    const dist = linha(container, 'Q13').querySelector('table.dist')!;
    const qtds = [...dist.querySelectorAll('td.dq')].map((td) => td.textContent);
    expect(qtds).toEqual(['800', '400', '50', '1.250']);
    expect((dist.querySelector('td.db span') as HTMLElement).style.width).toBe('100%');
    expect(dist.querySelector('.dok')!.textContent).toBe('confere com o total impresso');
    expect(screen.getByText(/distribuição estruturada \(3 linhas\)/)).toBeInTheDocument();
  });
});

describe('Best-of-N (v3.1): a nota discreta na linha da pergunta', () => {
  // Best-of-N: a resposta que falha no verificador ganha até 2 tentativas extras.
  const AVISO = 'Best-of-N: a resposta não passou no verificador e o modelo tentou novamente; prevalece a tentativa que a evidência sustenta.';
  const MELHOR_DE_N: Record<string, TentativasMelhorDeN> = {
    Q7: { tentativas: 3, escolhida: 1, pontos: [[-1, 0.41], [0, 0], [-1, 0.3]] },
    Q9: { tentativas: 3, escolhida: 2, pontos: [[-1, 0.2], [-1, 0.35], [1, 0.97]] },
    Q12: { tentativas: 3, escolhida: 0, pontos: [[0, 0], [-1, 0.2], [-1, 0.1]] },
  };
  const nota = (container: HTMLElement, id: string) => linha(container, id).querySelector('[title^="Best-of-N"]');

  it('sem registro, nenhuma linha muda (o prop é opcional)', () => {
    const { container } = renderTabela();
    expect(container.querySelector('[title^="Best-of-N"]')).toBeNull();
    expect(container.textContent).not.toMatch(/tentativas/);
  });

  it('a pergunta refeita ganha, na célula da verificação, qual tentativa ficou — com o porquê no title', () => {
    const { container } = renderizar(
      <TabelaRespostas slug={SLUG} respostas={RESPOSTAS} q13={L.q13_estruturada} melhorDeN={MELHOR_DE_N} />,
    );
    expect(nota(container, 'Q7')!.textContent).toBe('escolhida a 2ª de 3 tentativas');
    expect(nota(container, 'Q9')!.textContent).toBe('escolhida a 3ª de 3 tentativas');
    expect(nota(container, 'Q12')!.textContent).toBe('3 tentativas; prevaleceu a primeira');
    for (const id of Object.keys(MELHOR_DE_N)) {
      const n = nota(container, id)!;
      expect(n).toHaveAttribute('title', AVISO);
      expect(n).toHaveClass('perg');                                  // a nota pequena e apagada que a página já usa
      expect(n.closest('td')).toBe(linha(container, id).lastElementChild);
    }
    // o veredito continua o do verificador, e quem não teve tentativa extra não ganha nota
    expect(linha(container, 'Q9').querySelector('.v')).toHaveClass('REVISAR');
    expect(container.querySelectorAll('[title^="Best-of-N"]')).toHaveLength(3);
  });
});
