/**
 * Analytics Histórico FOPA: os editais de folha sem comprador que
 * voltaram a ser publicados, com filtro de período (último mês … 4 anos), busca e número de tentativas — e as duas
 * páginas do Analytics em abas.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Analytics as TipoAnalytics, CadeiaRepublicacao, ResultadoTentativa } from '../api/tipos';
import { AnalyticsHistorico, inicioDoPeriodo, linkPncp } from '../paginas/AnalyticsHistorico';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

function cadeia(cnpj: string, municipio: string, uf: string, orgao: string, datas: string[], comprada = false): CadeiaRepublicacao {
  const historico = datas.map((d, i) => ({
    publicacao: i + 1,
    controles: [`${cnpj}-1-${String(100 + i).padStart(6, '0')}/${d.slice(0, 4)}`],
    publicado_em: `${d}T11:00:00+00:00`,
    resultado: (i < datas.length - 1 ? 'deserta' : comprada ? 'comprada' : 'aberta') as ResultadoTentativa,
    valor_estimado: 1000000,
  }));
  const ultima = historico[historico.length - 1];
  return {
    orgao_cnpj: cnpj, orgao, municipio, uf, tentativas: datas.length, historico,
    situacao_atual: ultima.resultado, sem_comprador: !comprada, ultima_publicacao: ultima.publicado_em,
  };
}

// hoje = 26/09/2026 (fixado no beforeEach)
const BENTO: CadeiaRepublicacao = {
  orgao_cnpj: '44444444000101', orgao: 'Prefeitura de Bento', municipio: 'Bento', uf: 'RS', tentativas: 3,
  situacao_atual: 'aberta', sem_comprador: true, ultima_publicacao: '2026-05-13T11:00:00+00:00',
  historico: [
    { publicacao: 1, controles: ['44444444000101-1-000650/2025'], publicado_em: '2025-11-10T11:00:00+00:00', resultado: 'deserta', valor_estimado: 8805657.81 },
    { publicacao: 2, controles: ['44444444000101-1-000738/2025', '44444444000101-1-000739/2025'], publicado_em: '2026-01-06T11:00:00+00:00', resultado: 'deserta', valor_estimado: 8858147.76 },
    { publicacao: 3, controles: ['44444444000101-1-000317/2026'], publicado_em: '2026-05-13T11:00:00+00:00', resultado: 'aberta', valor_estimado: 9058141.48 },
  ],
};
const SAO_JOSE = cadeia('55555555000101', 'São José dos Campos', 'SP', 'Prefeitura de São José dos Campos', ['2026-07-01', '2026-09-10'], true);
const MARINGA = cadeia('66666666000101', 'Maringá', 'PR', 'Câmara de Maringá', ['2022-03-01', '2022-06-01', '2022-10-01', '2023-02-01']);
const NATAL = cadeia('77777777000101', 'Natal', 'RN', 'Prefeitura de Natal', ['2023-01-10', '2023-05-10', '2023-09-10', '2024-01-10', '2024-06-10', '2024-12-01']);

const DADOS: TipoAnalytics = {
  filtro: { escopo: 'dentro', ano: null, de: null, ate: null },
  resumo: {
    compras: 30, com_vencedor: 5, bancos: 2, valor_homologado: 1, valor_estimado: 1, desertas: 12, republicadas: 4,
    coletadas_em: '2026-09-24T23:50:00+00:00',
  },
  bancos: [],
  mensal: { meses: [], series: [] },
  republicadas: [NATAL, MARINGA, BENTO, SAO_JOSE],
};

const TODAS = ['Natal/RN', 'Maringá/PR', 'Bento/RS', 'São José dos Campos/SP'];

// 15 cadeias de 2 publicações: passa das 10 que a tabela mostra por vez
const MUITAS = Array.from({ length: 15 }, (_, i) =>
  cadeia(String(10000000000100 + i), 'Cidade ' + String(i + 1).padStart(2, '0'), 'MG', 'Prefeitura ' + (i + 1), ['2025-01-10', '2025-06-10']),
);

const nomes = (container: HTMLElement) =>
  Array.from(container.querySelectorAll('table.republicadas tbody tr td:first-child b')).map((b) => b.textContent);

// As duas barras de página, em cima e embaixo da tabela, com nomes diferentes para o leitor de tela.
const navCima = () => screen.getByRole('navigation', { name: 'Paginação, acima da lista' });
const navBaixo = () => screen.getByRole('navigation', { name: 'Paginação, abaixo da lista' });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-09-26T12:00:00-03:00'));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('Analytics Histórico FOPA', () => {
  it('as cadeias do histórico inteiro, só folha (a IA confirma), com tiles, tentativas e o link do PNCP', async () => {
    const { chamadas } = fetchFalso({ '/api/analytics': DADOS });
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    expect(await screen.findByRole('heading', { name: 'Analytics Histórico FOPA' })).toBeInTheDocument();
    await screen.findByText('Bento/RS');
    // o histórico inteiro, sempre só folha: nenhuma data nem "fora do escopo" vai para a API
    const doAnalytics = chamadas.filter((c) => c.url.pathname === '/api/analytics');
    expect(doAnalytics.length).toBeGreaterThan(0);
    for (const c of doAnalytics) {
      expect(c.url.searchParams.get('so_fopa_ia')).toBe('true');
      expect(['de', 'ate', 'escopo'].some((k) => c.url.searchParams.has(k))).toBe(false);
    }
    expect(screen.queryByRole('checkbox')).toBeNull();
    const resumo = screen.getByRole('region', { name: 'resumo' });
    expect(within(resumo).getByText('publicados novamente').previousSibling).toHaveTextContent('4');
    expect(within(resumo).getByText('ainda sem comprador').previousSibling).toHaveTextContent('3');
    expect(within(resumo).getByText('comprados após republicação').previousSibling).toHaveTextContent('1');
    expect(nomes(container)).toEqual(TODAS);
    // a cadeia: 3ª publicação, sem comprador, o cadastro duplicado aparece e o link vai ao PNCP
    const bento = screen.getByText('Bento/RS').closest('tr')!;
    expect(within(bento).getByText('3ª publicação')).toBeInTheDocument();
    expect(within(bento).getByText('sem comprador')).toBeInTheDocument();
    expect(within(bento).getByText(/cadastro duplicado/)).toBeInTheDocument();
    expect(within(bento).getAllByRole('link')[0]).toHaveAttribute('href', 'https://pncp.gov.br/app/editais/44444444000101/2025/650');
    expect(within(screen.getByText('São José dos Campos/SP').closest('tr')!).getByText('comprada na 2ª')).toBeInTheDocument();
  });

  it('as duas páginas do Analytics em abas, com esta marcada', async () => {
    fetchFalso({ '/api/analytics': DADOS });
    renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    const abas = await screen.findByRole('navigation', { name: 'Páginas do Analytics' });
    const mercado = within(abas).getByRole('link', { name: 'Analytics de Mercado' });
    const historico = within(abas).getByRole('link', { name: 'Analytics Histórico FOPA' });
    expect(mercado).toHaveAttribute('href', '/analytics');
    expect(mercado).not.toHaveAttribute('aria-current');
    expect(historico).toHaveAttribute('href', '/analytics/historico-fopa');
    expect(historico).toHaveAttribute('aria-current', 'page');
  });

  it('período pela última publicação: último mês, 3 e 6 meses, 1, 2 e 4 anos — sem ir de novo à API', async () => {
    const { chamadas } = fetchFalso({ '/api/analytics': DADOS });
    const usuario = userEvent.setup();
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    await screen.findByText('Bento/RS');
    const antes = chamadas.length;
    // os grupos de botões viraram listas
    const periodo = screen.getByRole('combobox', { name: 'Período' });
    const esperado: [string, string[]][] = [
      ['Último mês', ['São José dos Campos/SP']],
      ['3 meses', ['São José dos Campos/SP']],
      ['6 meses', ['Bento/RS', 'São José dos Campos/SP']],
      ['1 ano', ['Bento/RS', 'São José dos Campos/SP']],
      ['2 anos', ['Natal/RN', 'Bento/RS', 'São José dos Campos/SP']],
      ['4 anos', TODAS],
      ['Todo o histórico', TODAS],
    ];
    for (const [opcao, lista] of esperado) {
      await usuario.selectOptions(periodo, opcao);
      expect((periodo as HTMLSelectElement).selectedOptions[0].text).toBe(opcao);
      expect(nomes(container)).toEqual(lista);
    }
    // os tiles contam o que a lista mostra
    await usuario.selectOptions(periodo, '6 meses');
    const resumo = screen.getByRole('region', { name: 'resumo' });
    expect(within(resumo).getByText('publicados novamente').previousSibling).toHaveTextContent('2');
    expect(within(resumo).getByText('ainda sem comprador').previousSibling).toHaveTextContent('1');
    // a tentativa de antes do período continua contando: Bento segue na 3ª publicação
    expect(within(screen.getByText('Bento/RS').closest('tr')!).getByText('3ª publicação')).toBeInTheDocument();
    expect(chamadas.length).toBe(antes);
  });

  it('filtro por quantas tentativas o edital já teve: 2, 3, 4 ou mais', async () => {
    fetchFalso({ '/api/analytics': DADOS });
    const usuario = userEvent.setup();
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    await screen.findByText('Bento/RS');
    const tentativas = screen.getByRole('combobox', { name: 'Tentativas' });
    await usuario.selectOptions(tentativas, '2');
    expect(nomes(container)).toEqual(['São José dos Campos/SP']);
    await usuario.selectOptions(tentativas, '3');
    expect(nomes(container)).toEqual(['Bento/RS']);
    await usuario.selectOptions(tentativas, '4 ou mais');
    expect(nomes(container)).toEqual(['Natal/RN', 'Maringá/PR']);
    // combina com o período: 4 ou mais nos últimos 2 anos = só Natal
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Período' }), '2 anos');
    expect(nomes(container)).toEqual(['Natal/RN']);
    await usuario.selectOptions(tentativas, 'Todas');
    expect(nomes(container)).toEqual(['Natal/RN', 'Bento/RS', 'São José dos Campos/SP']);
  });

  it('busca como no painel: município, UF, órgão ou controle, sem acento; nada achado diz que está vazio', async () => {
    fetchFalso({ '/api/analytics': DADOS });
    const usuario = userEvent.setup();
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    await screen.findByText('Bento/RS');
    const busca = screen.getByRole('searchbox', { name: /Buscar/ });
    await usuario.type(busca, 'sao jose');
    expect(nomes(container)).toEqual(['São José dos Campos/SP']);
    await usuario.clear(busca);
    await usuario.type(busca, 'bento/rs');
    expect(nomes(container)).toEqual(['Bento/RS']);
    await usuario.clear(busca);
    await usuario.type(busca, '000317');                      // um controle da cadeia
    expect(nomes(container)).toEqual(['Bento/RS']);
    await usuario.clear(busca);
    await usuario.type(busca, 'câmara');
    expect(nomes(container)).toEqual(['Maringá/PR']);
    await usuario.type(busca, ' natal');
    expect(nomes(container)).toEqual([]);
    expect(screen.getByText('Nenhum edital republicado encontrado para os filtros selecionados.')).toBeInTheDocument();
    await usuario.clear(busca);
    await waitFor(() => expect(nomes(container)).toEqual(TODAS));
  });

  it('os filtros moram na URL: o link abre com eles', async () => {
    fetchFalso({ '/api/analytics': DADOS });
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa?periodo=2a&tentativas=4%2B&q=natal' });
    await screen.findByText('Natal/RN');
    expect(nomes(container)).toEqual(['Natal/RN']);
    expect(screen.getByRole('searchbox', { name: /Buscar/ })).toHaveValue('natal');
    expect(screen.getByRole('combobox', { name: 'Período' })).toHaveValue('2a');
    expect(screen.getByRole('combobox', { name: 'Tentativas' })).toHaveValue('4+');
  });

  it('a tabela mostra 10 por vez, com a opção de 50, 100 ou todos', async () => {
    fetchFalso({ '/api/analytics': { ...DADOS, republicadas: MUITAS } });
    const usuario = userEvent.setup();
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    await screen.findByText('Cidade 01/MG');
    expect(nomes(container)).toHaveLength(10);
    expect(nomes(container)[9]).toBe('Cidade 10/MG');
    expect(screen.getByText('mostrando 1–10 de 15')).toBeInTheDocument();
    const itens = screen.getByRole('combobox', { name: 'Mostrar' });
    expect(itens).toHaveValue('10');
    expect([...(itens as HTMLSelectElement).options].map((o) => o.text)).toEqual(
      ['10 por página', '50 por página', '100 por página', 'Todos']);
    await usuario.selectOptions(itens, '50');
    expect(nomes(container)).toHaveLength(15);
    expect(screen.getByText('mostrando 1–15 de 15')).toBeInTheDocument();
    await usuario.selectOptions(itens, '10');
    expect(nomes(container)).toHaveLength(10);
    await usuario.selectOptions(itens, 'todos');
    expect(nomes(container)).toHaveLength(15);
    // os tiles contam a lista inteira, não só o que está na tela
    await usuario.selectOptions(itens, '10');
    expect(within(screen.getByRole('region', { name: 'resumo' })).getByText('publicados novamente').previousSibling).toHaveTextContent('15');
  });

  it('passa de página com Anterior/Próxima', async () => {
    const { chamadas } = fetchFalso({ '/api/analytics': { ...DADOS, republicadas: MUITAS } });
    const usuario = userEvent.setup();
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    await screen.findByText('Cidade 01/MG');
    const antes = chamadas.length;
    expect(within(navBaixo()).getByText('página 1 de 2')).toBeInTheDocument();
    const anterior = within(navBaixo()).getByRole('button', { name: /Anterior/ });
    expect(anterior).toBeDisabled();
    await usuario.click(within(navBaixo()).getByRole('button', { name: /Próxima/ }));
    expect(nomes(container)).toEqual(['Cidade 11/MG', 'Cidade 12/MG', 'Cidade 13/MG', 'Cidade 14/MG', 'Cidade 15/MG']);
    expect(within(navBaixo()).getByText('página 2 de 2')).toBeInTheDocument();
    expect(screen.getByText('mostrando 11–15 de 15')).toBeInTheDocument();
    expect(within(navBaixo()).getByRole('button', { name: /Próxima/ })).toBeDisabled();
    // os tiles seguem contando a lista inteira; a paginação é no navegador, sem ir de novo à API
    expect(within(screen.getByRole('region', { name: 'resumo' })).getByText('publicados novamente').previousSibling).toHaveTextContent('15');
    expect(chamadas.length).toBe(antes);
    await usuario.click(within(navBaixo()).getByRole('button', { name: /Anterior/ }));
    expect(nomes(container)[0]).toBe('Cidade 01/MG');
  });

  it('mudar filtro ou quantidade volta à primeira página; com "todos" não há paginação', async () => {
    fetchFalso({ '/api/analytics': { ...DADOS, republicadas: MUITAS } });
    const usuario = userEvent.setup();
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa?pagina=2' });
    await screen.findByText('Cidade 11/MG');
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Tentativas' }), '2');
    expect(nomes(container)[0]).toBe('Cidade 01/MG');
    await usuario.click(within(navBaixo()).getByRole('button', { name: /Próxima/ }));
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Mostrar' }), 'todos');
    expect(nomes(container)).toHaveLength(15);
    // nem a barra de cima nem a de baixo
    expect(screen.queryAllByRole('navigation', { name: /^Paginação/ })).toHaveLength(0);
  });

  it('passar de página ou trocar a quantidade leva ao alto da tabela; mudar filtro não', async () => {
    const alvos: Element[] = [];
    const rolar = vi.fn(function (this: Element) {
      alvos.push(this);
    });
    Element.prototype.scrollIntoView = rolar;
    fetchFalso({ '/api/analytics': { ...DADOS, republicadas: MUITAS } });
    const usuario = userEvent.setup();
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    await screen.findByText('Cidade 01/MG');
    // o alvo é o alto da tabela: a barra de cima quando ela existe (da página 2 em diante), senão a própria tabela
    const grade = container.querySelector('.grade-lista')!;
    expect(grade.firstElementChild!.querySelector('table.republicadas')).not.toBeNull();       // página 1: a tabela
    await usuario.click(within(navBaixo()).getByRole('button', { name: /Próxima/ }));
    expect(alvos).toEqual([grade]);
    expect(grade.firstElementChild).toBe(navCima());                                           // página 2: a barra
    await usuario.click(within(navCima()).getByRole('button', { name: /Anterior/ }));           // os de cima também
    expect(alvos).toEqual([grade, grade]);
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Mostrar' }), '50');
    expect(alvos).toEqual([grade, grade, grade]);
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Tentativas' }), '2');
    expect(rolar).toHaveBeenCalledTimes(3);
  });

  it('a barra de páginas de cima só aparece da página 2 em diante, logo acima da tabela', async () => {
    // Na primeira página, a barra de cima não faz sentido
    fetchFalso({ '/api/analytics': { ...DADOS, republicadas: MUITAS } });
    const usuario = userEvent.setup();
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    await screen.findByText('Cidade 01/MG');
    expect(screen.queryByRole('navigation', { name: 'Paginação, acima da lista' })).toBeNull();     // página 1: só embaixo
    expect(navBaixo().previousElementSibling!.querySelector('table.republicadas')).not.toBeNull();
    await usuario.click(within(navBaixo()).getByRole('button', { name: /Próxima/ }));
    // página 2: em cima, logo antes da tabela; as duas barras andam juntas
    expect(navCima().nextElementSibling!.querySelector('table.republicadas')).not.toBeNull();
    for (const nav of [navCima(), navBaixo()]) expect(within(nav).getByText('página 2 de 2')).toBeInTheDocument();
    // os de cima mudam a página como os de baixo; de volta à 1, a barra de cima some
    await usuario.click(within(navCima()).getByRole('button', { name: /Anterior/ }));
    expect(nomes(container)[0]).toBe('Cidade 01/MG');
    expect(screen.queryByRole('navigation', { name: 'Paginação, acima da lista' })).toBeNull();
  });

  it('?pagina além da última cai na última', async () => {
    fetchFalso({ '/api/analytics': { ...DADOS, republicadas: MUITAS } });
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa?pagina=9' });
    await screen.findByText('Cidade 11/MG');
    expect(nomes(container)).toHaveLength(5);
    expect(screen.getAllByText('página 2 de 2')).toHaveLength(2);                 // nas duas barras
  });

  it('a quantidade por vez também mora na URL', async () => {
    fetchFalso({ '/api/analytics': { ...DADOS, republicadas: MUITAS } });
    const { container } = renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa?itens=todos' });
    await screen.findByText('Cidade 01/MG');
    expect(nomes(container)).toHaveLength(15);
  });

  it('sem coleta ainda: diz que está vazio, nada quebra', async () => {
    fetchFalso({ '/api/analytics': { ...DADOS, republicadas: [] } });
    renderizar(<AnalyticsHistorico />, { rota: '/analytics/historico-fopa' });
    expect(await screen.findByText('Nenhum edital republicado encontrado para os filtros selecionados.')).toBeInTheDocument();
  });

  it('auxiliares: o começo do período e o link do PNCP', () => {
    const d = (a: number, m: number, dia: number) => new Date(a, m - 1, dia);
    expect(inicioDoPeriodo(d(2026, 9, 26), 1)).toEqual(d(2026, 8, 26));
    expect(inicioDoPeriodo(d(2026, 9, 26), 48)).toEqual(d(2022, 9, 26));
    expect(inicioDoPeriodo(d(2026, 3, 31), 1)).toEqual(d(2026, 2, 28));       // fevereiro não tem 31
    expect(linkPncp('00000000000191-1-000015/2026')).toBe('https://pncp.gov.br/app/editais/00000000000191/2026/15');
    expect(linkPncp('lixo')).toBeNull();
  });
});
