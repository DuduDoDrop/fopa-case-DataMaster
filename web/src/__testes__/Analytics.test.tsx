/**
 * Analytics: ranking de bancos, compras por mês por banco (linhas) e os
 * editais sem comprador publicados de novo — com o filtro de ano e, só aqui, "mostrar fora do escopo".
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Analytics as TipoAnalytics, ComprasPorBanco } from '../api/tipos';
import { caminhoSuave, escalaY, GraficoLinhas, mesPorExtenso, rotuloMes } from '../componentes/GraficoLinhas';
import { brl, brlEixo } from '../lib/formato';
import { corDoBanco, COR_OUTROS } from '../lib/bancos';
import { Analytics } from '../paginas/Analytics';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';
import { copia } from '../__fixtures__/contrato';

const DADOS: TipoAnalytics = {
  filtro: { escopo: 'dentro', ano: null, de: null, ate: null },
  resumo: {
    compras: 8, com_vencedor: 3, bancos: 2, valor_homologado: 1800000, valor_estimado: 29000000,
    desertas: 2, republicadas: 1, coletadas_em: '2026-09-24T23:50:00+00:00',
  },
  bancos: [
    { banco: 'BANCO DO BRASIL SA', cnpj_raiz: '00000000', natureza_juridica: 'Sociedade de Economia Mista', licitacoes: 2,
      valor_total: 1550000, ticket_medio: 775000, participacao: 2 / 3, primeira: '2026-03-05', ultima: '2026-05-20' },
    { banco: 'CAIXA ECONOMICA FEDERAL', cnpj_raiz: '00360305', natureza_juridica: 'Empresa Pública', licitacoes: 1,
      valor_total: 250000, ticket_medio: 250000, participacao: 1 / 3, primeira: '2026-03-30', ultima: '2026-03-30' },
    { banco: 'COMPANHIA DE PROCESSAMENTO DE DADOS DO ESTADO DE SAO PAULO - PRODESP', cnpj_raiz: '62577929',
      natureza_juridica: 'Empresa Pública', licitacoes: 1, valor_total: 10, ticket_medio: 10, participacao: 1 / 4,
      primeira: '2026-04-20', ultima: '2026-04-20', financeira: false },
  ],
  mensal: {
    meses: ['2026-03', '2026-04', '2026-05'],
    series: [
      { banco: 'BANCO DO BRASIL SA', cnpj_raiz: '00000000', licitacoes: [1, 0, 1], valor: [1000000, 0, 550000] },
      { banco: 'CAIXA ECONOMICA FEDERAL', cnpj_raiz: '00360305', licitacoes: [1, 0, 0], valor: [250000, 0, 0] },
    ],
  },
  republicadas: [
    {
      orgao_cnpj: '44444444000101', orgao: 'Prefeitura de Bento', municipio: 'Bento', uf: 'RS', tentativas: 3,
      situacao_atual: 'aberta', sem_comprador: true, ultima_publicacao: '2026-05-13T11:00:00+00:00',
      historico: [
        { publicacao: 1, controles: ['44444444000101-1-000650/2025'], publicado_em: '2025-11-10T11:00:00+00:00', resultado: 'deserta', valor_estimado: 8805657.81 },
        { publicacao: 2, controles: ['44444444000101-1-000738/2025', '44444444000101-1-000739/2025'], publicado_em: '2026-01-06T11:00:00+00:00', resultado: 'deserta', valor_estimado: 8858147.76 },
        { publicacao: 3, controles: ['44444444000101-1-000317/2026'], publicado_em: '2026-05-13T11:00:00+00:00', resultado: 'aberta', valor_estimado: 9058141.48 },
      ],
    },
  ],
};

const VAZIO: TipoAnalytics = {
  ...DADOS,
  resumo: { ...DADOS.resumo, compras: 0, com_vencedor: 0, bancos: 0, valor_homologado: 0, desertas: 0, republicadas: 0 },
  bancos: [], mensal: { meses: [], series: [] }, republicadas: [],
};

// O que cada instituição financeira comprou (GET /api/analytics/compras): a lista do filtro e as compras.
const COMPRAS: ComprasPorBanco = {
  filtro: { escopo: 'dentro', so_fopa_ia: true, banco: null, de: null, ate: null },
  bancos: [
    { cnpj_raiz: '00000000', banco: 'BANCO DO BRASIL SA', licitacoes: 2, valor_total: 1550000 },
    { cnpj_raiz: '00360305', banco: 'CAIXA ECONOMICA FEDERAL', licitacoes: 1, valor_total: 250000 },
  ],
  banco: null,
  compras: [],
  total: { licitacoes: 0, valor: 0 },
  coletadas_em: '2026-09-27T09:00:00+00:00',
};
const DA_CAIXA: ComprasPorBanco = {
  ...COMPRAS,
  filtro: { ...COMPRAS.filtro, banco: '00360305' },
  banco: { cnpj_raiz: '00360305', banco: 'CAIXA ECONOMICA FEDERAL' },
  compras: [
    { controle: '44444444000101-1-000317/2026', fopa: true, municipio: 'Bento', uf: 'RS', orgao: 'Prefeitura de Bento',
      modalidade: 'Pregão - Eletrônico', numero_compra: '90012', objeto: 'folha', publicado_em: '2026-05-13T11:00:00+00:00',
      rodada: 3, valor: 9100000, comprada_em: '2026-06-20',
      contrato: { controle: '44444444000101-2-000001/2026', contratos: 1, valor: 9200000, assinado_em: '2026-07-01',
                  vigencia_fim: '2031-06-30' } },
    { controle: '55555555000101-1-000077/2026', fopa: false, municipio: 'Longe', uf: 'SC', orgao: 'Prefeitura de Longe',
      modalidade: null, numero_compra: null, objeto: 'consignado', publicado_em: null, rodada: 1, valor: 70000,
      comprada_em: null, contrato: null },
  ],
  total: { licitacoes: 2, valor: 9170000 },
};
const comprasPorBanco = (u: URL) => (u.searchParams.get('banco') === '00360305' ? DA_CAIXA : COMPRAS);

afterEach(() => vi.unstubAllGlobals());

describe('Analytics', () => {
  it('tiles, ranking por banco e linhas por mês — as republicadas foram para a aba Histórico FOPA', async () => {
    fetchFalso({ '/api/analytics': DADOS });
    const usuario = userEvent.setup();
    const { container } = renderizar(<Analytics />, { rota: '/analytics' });
    expect((await screen.findAllByText('BANCO DO BRASIL SA')).length).toBe(2);   // ranking + legenda
    const resumo = screen.getByRole('region', { name: 'resumo' });
    // valor grande encurta no tile, com o valor inteiro no title
    expect(within(resumo).getByText('R$ 1,80 mi')).toHaveAttribute('title', 'R$ 1.800.000,00');
    // as republicadas foram para a outra aba
    expect(screen.getByRole('heading', { name: 'Analytics de Mercado' })).toBeInTheDocument();
    const abas = screen.getByRole('navigation', { name: 'Páginas do Analytics' });
    expect(within(abas).getByRole('link', { name: 'Analytics de Mercado' })).toHaveAttribute('aria-current', 'page');
    expect(within(abas).getByRole('link', { name: 'Analytics Histórico FOPA' })).toHaveAttribute('href', '/analytics/historico-fopa');
    expect(within(resumo).queryByText('republicadas (2ª publicação ou mais)')).toBeNull();
    expect(screen.queryByText('Editais sem comprador publicados novamente')).toBeNull();
    // ranking: o maior primeiro, com valor, ticket e participação — só instituição financeira; quem não é banco
    // (a PRODESP) vai para o "ver mais" logo abaixo, sem sumir
    const linhas = container.querySelectorAll('table.ranking tbody tr');
    expect(linhas).toHaveLength(2);
    const outros = container.querySelector('details.nao-bancos')!;
    expect(outros.querySelector('summary')!.textContent).toMatch(/1 fornecedor/);
    expect(outros.textContent).toContain('PRODESP');
    expect(linhas[0]).toHaveTextContent('R$ 1.550.000,00');
    expect(linhas[0]).toHaveTextContent('66,7%');
    // uma linha por banco no gráfico
    expect(container.querySelectorAll('figure.grafico path.linha')).toHaveLength(2);
    // o último mês ancora para dentro (saía cortado na borda direita)
    const meses = Array.from(container.querySelectorAll('figure.grafico text.eixo')).filter((t) => /\//.test(t.textContent ?? ''));
    expect(meses[meses.length - 1]).toHaveTextContent('mai/26');
    expect(meses[meses.length - 1]).toHaveAttribute('text-anchor', 'end');
    // o mês inteiro num quadro: as setas do teclado andam mês a mês (o mouse e o dedo também)
    screen.getByRole('img', { name: /Compras por mês/ }).focus();
    await usuario.keyboard('{ArrowRight}');
    const quadro = container.querySelector('.quadro-mes') as HTMLElement;
    expect(quadro).toHaveTextContent('Março de 2026');
    expect(within(quadro).getByText('BANCO DO BRASIL SA').closest('li')).toHaveTextContent('1');
    expect(quadro.querySelector('.total')).toHaveTextContent('2');
    await usuario.keyboard('{ArrowRight}');
    expect(container.querySelector('.quadro-mes')).toHaveTextContent('Abril de 2026');
    // não há 2021 nos atalhos: o PNCP não tem compra de folha antes de 2022
    const anos = [...(screen.getByRole('combobox', { name: 'Período' }) as HTMLSelectElement).options].map((o) => o.text);
    expect(anos).not.toContain('2021');
    expect(anos).toContain('2022');
  });

  it('valor homologado no gráfico e filtros de data e escopo vão para a API', async () => {
    const { chamadas } = fetchFalso({ '/api/analytics': DADOS });
    const usuario = userEvent.setup();
    const { container } = renderizar(<Analytics />, { rota: '/analytics' });
    await screen.findAllByText('BANCO DO BRASIL SA');
    // sem filtro, TODO o histórico: nenhuma data vai para a API
    expect(chamadas.every((c) => !c.url.searchParams.has('escopo') && !c.url.searchParams.has('de'))).toBe(true);
    await usuario.click(screen.getByRole('radio', { name: /Valor homologado/ }));
    // o eixo com rótulo curto e a margem do tamanho dele (o "R$ 1.000.000,00" saía comido à esquerda)
    const eixoY = Array.from(container.querySelectorAll('figure.grafico text.eixo.y'));
    expect(eixoY.map((t) => t.textContent)).toEqual(['R$ 0', 'R$ 200 mil', 'R$ 400 mil', 'R$ 600 mil', 'R$ 800 mil', 'R$ 1 mi']);
    for (const t of eixoY) expect(Number(t.getAttribute('x'))).toBeGreaterThanOrEqual((t.textContent ?? '').length * 7.2);
    screen.getByRole('img', { name: /Compras por mês/ }).focus();
    await usuario.keyboard('{ArrowRight}');
    expect(within(container.querySelector('.quadro-mes') as HTMLElement).getByText('BANCO DO BRASIL SA').closest('li')).toHaveTextContent(
      'R$ 1,00 mi',
    );
    // atalho de ano = as duas pontas do ano
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Período' }), '2025');
    await waitFor(() =>
      expect(chamadas.some((c) => c.url.searchParams.get('de') === '2025-01-01' && c.url.searchParams.get('ate') === '2025-12-31')).toBe(true),
    );
    // e as datas à mão, com o fora do escopo
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Período' }), 'Escolher datas');
    fireEvent.change(screen.getByLabelText('publicada de'), { target: { value: '2024-03-01' } });
    await usuario.click(screen.getByRole('checkbox', { name: /Mostrar fora do escopo/ }));
    await waitFor(() =>
      expect(
        chamadas.some(
          (c) =>
            c.url.searchParams.get('de') === '2024-03-01' &&
            c.url.searchParams.get('ate') === '2025-12-31' &&
            c.url.searchParams.get('escopo') === 'todos',
        ),
      ).toBe(true),
    );
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Período' }), 'Todo o histórico');
    await waitFor(() => expect(chamadas[chamadas.length - 1].url.searchParams.has('de')).toBe(false));
  });

  it('só o que a IA confirma por padrão; "mostrar fora do escopo" traz tudo de volta — sem caixa "apenas FOPA"', async () => {
    const { chamadas } = fetchFalso({ '/api/analytics': DADOS });
    const usuario = userEvent.setup();
    renderizar(<Analytics />, { rota: '/analytics' });
    await screen.findAllByText('BANCO DO BRASIL SA');
    const doAnalytics = () => chamadas.filter((c) => c.url.pathname === '/api/analytics');
    expect(doAnalytics().length).toBeGreaterThan(0);
    expect(
      doAnalytics().every((c) => c.url.searchParams.get('so_fopa_ia') === 'true' && !c.url.searchParams.has('escopo')),
    ).toBe(true);
    expect(screen.queryByRole('checkbox', { name: /apenas FOPA/ })).toBeNull();
    await usuario.click(screen.getByRole('checkbox', { name: /Mostrar fora do escopo/ }));
    await waitFor(() => {
      const u = doAnalytics()[doAnalytics().length - 1].url.searchParams;
      expect(u.get('escopo') === 'todos' && !u.has('so_fopa_ia')).toBe(true);
    });
  });

  it('cada banco com a cor da marca: BB amarelo, Caixa azul, Santander vermelho, Bradesco vermelho claro, Itaú laranja', async () => {
    fetchFalso({ '/api/analytics': DADOS });
    const { container } = renderizar(<Analytics />, { rota: '/analytics' });
    await screen.findAllByText('CAIXA ECONOMICA FEDERAL');
    const bb = corDoBanco('00000000', 'BANCO DO BRASIL SA', 0);
    const caixa = corDoBanco('00360305', 'CAIXA ECONOMICA FEDERAL', 1);
    expect(container.querySelector('g[data-serie="BANCO DO BRASIL SA"] path.linha')).toHaveAttribute('stroke', bb);
    expect(container.querySelector('g[data-serie="CAIXA ECONOMICA FEDERAL"] path.linha')).toHaveAttribute('stroke', caixa);
    // o ponto do ranking tem a MESMA cor da linha do banco no gráfico
    const pontos = container.querySelectorAll('table.ranking tbody tr .ponto');
    expect((pontos[0] as HTMLElement).dataset.cor).toBe(bb);
    expect((pontos[1] as HTMLElement).dataset.cor).toBe(caixa);
    // a paleta: por raiz de CNPJ; cooperativa pelo nome; o resto neutro; "Outros" cinza
    expect(bb).toBe('#E5B800');
    expect(caixa).toBe('#005CA9');
    expect(corDoBanco('90400888', 'BANCO SANTANDER (BRASIL) S.A.', 2)).toBe('#EC0000');
    expect(corDoBanco('60746948', 'BANCO BRADESCO S.A.', 3)).toBe('#F0707A');
    expect(corDoBanco('60701190', 'ITAU UNIBANCO S.A.', 4)).toBe('#EC7000');
    expect(corDoBanco('22749014', 'COOPERATIVA DE CREDITO DA REGIAO CENTRAL - SICOOB UNIAO CENTRAL', 5)).toBe('#00A091');
    expect(corDoBanco(null, 'Outros', 6)).toBe(COR_OUTROS);
    expect(corDoBanco('12345678', 'BANCO QUALQUER', 0)).toMatch(/^#[0-9A-F]{6}$/i);
  });

  it('a legenda liga e desliga cada banco (o eixo se refaz) e destaca a linha com o mouse em cima', async () => {
    fetchFalso({ '/api/analytics': DADOS });
    const usuario = userEvent.setup();
    const { container } = renderizar(<Analytics />, { rota: '/analytics' });
    await screen.findAllByText('CAIXA ECONOMICA FEDERAL');
    const chip = (nome: string) => screen.getByRole('button', { name: new RegExp(nome) });
    const topo = () => container.querySelectorAll('figure.grafico text.eixo.y')[container.querySelectorAll('figure.grafico text.eixo.y').length - 1].textContent;
    expect(topo()).toBe('1');
    await usuario.hover(chip('CAIXA ECONOMICA FEDERAL'));
    expect(container.querySelector('g[data-serie="BANCO DO BRASIL SA"]')).toHaveClass('apagada');
    expect(container.querySelector('g[data-serie="CAIXA ECONOMICA FEDERAL"] path.area')).not.toBeNull();
    await usuario.unhover(chip('CAIXA ECONOMICA FEDERAL'));
    await usuario.click(chip('BANCO DO BRASIL SA'));
    expect(chip('BANCO DO BRASIL SA')).toHaveAttribute('aria-pressed', 'false');
    expect(container.querySelector('g[data-serie="BANCO DO BRASIL SA"]')).toBeNull();
    expect(container.querySelectorAll('figure.grafico path.linha')).toHaveLength(1);
    // a última que sobrou não se desliga: um gráfico vazio não diz nada
    await usuario.click(chip('CAIXA ECONOMICA FEDERAL'));
    expect(chip('CAIXA ECONOMICA FEDERAL')).toHaveAttribute('aria-pressed', 'true');
    await usuario.click(chip('BANCO DO BRASIL SA'));
    expect(container.querySelectorAll('figure.grafico path.linha')).toHaveLength(2);
  });

  it('ranking longo: os 15 maiores e um botão para ver os outros (o gráfico não fica a 4.600 px da tela)', async () => {
    const muitos = copia(DADOS);
    muitos.bancos = Array.from({ length: 20 }, (_, i) => ({
      ...DADOS.bancos[0], banco: `COOPERATIVA DE CREDITO ${i + 1}`, cnpj_raiz: String(10000000 + i), licitacoes: 20 - i,
    }));
    fetchFalso({ '/api/analytics': muitos });
    const usuario = userEvent.setup();
    const { container } = renderizar(<Analytics />, { rota: '/analytics' });
    await screen.findByText('COOPERATIVA DE CREDITO 1');
    expect(container.querySelectorAll('table.ranking tbody tr.banco')).toHaveLength(15);
    await usuario.click(screen.getByRole('button', { name: /Ver as outras 5 instituições/ }));
    expect(container.querySelectorAll('table.ranking tbody tr.banco')).toHaveLength(20);
  });

  it('sem coleta ainda: diz que está vazio, nada quebra', async () => {
    fetchFalso({ '/api/analytics': VAZIO });
    renderizar(<Analytics />, { rota: '/analytics' });
    expect(await screen.findByText('Nenhuma compra com vencedor no período.')).toBeInTheDocument();
    expect(screen.getByText('Nenhuma compra no período.')).toBeInTheDocument();
  });

  it('eixo largo (51 meses, o acervo real): uma letra por mês e o ano embaixo — nenhum mês some', async () => {
    // Agosto no fim e junho no começo sumiam: o eixo nomeava 1 mês a cada 3
    const real = copia(DADOS);
    const meses = Array.from({ length: 51 }, (_, i) => {
      const t = 2022 * 12 + 6 + i;
      return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`;
    });
    real.mensal = { meses, series: [{ ...DADOS.mensal.series[0], licitacoes: meses.map(() => 1), valor: meses.map(() => 1) }] };
    fetchFalso({ '/api/analytics': real });
    const { container } = renderizar(<Analytics />, { rota: '/analytics' });
    await screen.findAllByText('BANCO DO BRASIL SA');
    const letras = Array.from(container.querySelectorAll('figure.grafico text.eixo.mes'));
    expect(letras).toHaveLength(51);
    expect(letras[0]).toHaveTextContent('J'); // julho de 2022, o primeiro mês com compra
    expect(letras[49]).toHaveTextContent('A'); // agosto de 2026
    expect(letras[50]).toHaveTextContent('S');
    const xs = letras.map((t) => Number(t.getAttribute('x')));
    for (let i = 1; i < xs.length; i++) expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual(12);
    expect(Array.from(container.querySelectorAll('figure.grafico text.eixo.ano')).map((t) => t.textContent)).toEqual([
      '2022', '2023', '2024', '2025', '2026',
    ]);
  });

  it('eixo estreito (celular): 1 mês a cada N, sem sobrepor, com as pontas', () => {
    const meses = Array.from({ length: 51 }, (_, i) => {
      const t = 2022 * 12 + 6 + i;
      return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, '0')}`;
    });
    const { container } = render(
      <GraficoLinhas
        meses={meses}
        series={[{ nome: 'X', cor: '#000', valores: meses.map(() => 1) }]}
        formatar={String}
        unidade=""
        larguraInicial={360}
      />,
    );
    const caixas = Array.from(container.querySelectorAll('text.eixo.mes')).map((t) => {
      const x = Number(t.getAttribute('x'));
      const a = t.getAttribute('text-anchor');
      return a === 'end' ? [x - 46, x] : a === 'start' ? [x, x + 46] : [x - 23, x + 23];
    });
    expect(caixas.length).toBeGreaterThan(2);
    for (let i = 1; i < caixas.length; i++) expect(caixas[i][0]).toBeGreaterThanOrEqual(caixas[i - 1][1]);
    const textos = Array.from(container.querySelectorAll('text.eixo.mes')).map((t) => t.textContent);
    expect(textos[0]).toBe('jul/22');
    expect(textos[textos.length - 1]).toBe('set/26');
  });

  it('o mês em curso é tracejado e o quadro diz que ele ainda está aberto', async () => {
    const usuario = userEvent.setup();
    const { container } = render(
      <GraficoLinhas
        meses={['2026-07', '2026-08', '2026-09']}
        series={[{ nome: 'CAIXA', cor: '#005CA9', valores: [9, 12, 8] }]}
        formatar={String}
        unidade="licitação(ões)"
        mesCorrente="2026-09"
      />,
    );
    expect(container.querySelector('path.linha.parcial')).not.toBeNull();
    expect(screen.getByText(/setembro de 2026 ainda está em curso/)).toBeInTheDocument();
    screen.getByRole('img', { name: /Compras por mês/ }).focus();
    await usuario.keyboard('{End}');
    expect(container.querySelector('.quadro-mes')).toHaveTextContent('Setembro de 2026 (em curso)');
  });

  it('auxiliares: mês e topo do eixo', () => {
    expect(rotuloMes('2026-03')).toBe('mar/26');
    expect(mesPorExtenso('2026-03')).toBe('março de 2026');
    // 3 a 5 intervalos redondos; contagem só com passo inteiro
    expect(escalaY(0)).toEqual({ topo: 1, passo: 1 });
    expect(escalaY(21, true)).toEqual({ topo: 25, passo: 5 });
    expect(escalaY(3, true)).toEqual({ topo: 3, passo: 1 });
    expect(escalaY(1234044000)).toEqual({ topo: 1250000000, passo: 250000000 });
    // a curva suave não inventa pico nem desce abaixo de zero: o trecho plano continua plano
    expect(caminhoSuave([[0, 100], [10, 0], [20, 0], [30, 100]]).split(' C')[2]).toBe('13.3,0 16.7,0 20,0');
    expect(brlEixo(1250000000)).toBe('R$ 1,25 bi');
    expect(brlEixo(200000)).toBe('R$ 200 mil');
  });
});

describe('O que cada instituição financeira comprou (embaixo do gráfico)', () => {
  const doBanco = (chamadas: { url: URL }[]) => chamadas.filter((c) => c.url.pathname === '/api/analytics/compras');

  it('escolher o banco pelo nome mostra as licitações dele: rodada, preço, data e contrato', async () => {
    const { chamadas } = fetchFalso({ '/api/analytics': DADOS, '/api/analytics/compras': comprasPorBanco });
    const usuario = userEvent.setup();
    const { container } = renderizar(<Analytics />, { rota: '/analytics' });
    expect(await screen.findByText(/Selecione uma das 2 instituições financeiras/)).toBeInTheDocument();
    // o filtro pesquisável: as instituições financeiras que compraram folha
    const opcoes = [...container.querySelectorAll('#bancos-compradores option')].map((o) => (o as HTMLOptionElement).value);
    expect(opcoes).toEqual(['BANCO DO BRASIL SA', 'CAIXA ECONOMICA FEDERAL']);
    // sem acento e em minúsculas também acha
    await usuario.type(screen.getByLabelText('Instituição financeira'), 'caixa economica federal');
    await waitFor(() => expect(container.querySelector('table.compras-do-banco')).not.toBeNull());
    const linhas = [...container.querySelectorAll('table.compras-do-banco tbody tr')];
    expect(linhas).toHaveLength(2);
    for (const trecho of ['Bento/RS', 'Prefeitura de Bento · Pregão - Eletrônico nº 90012', '3ª publicação', brl(9100000),
                          '20/06/2026', brl(9200000), 'vigente até 30/06/2031']) {
      expect(linhas[0].textContent).toContain(trecho);
    }
    expect(within(linhas[0] as HTMLElement).getByRole('link')).toHaveAttribute(
      'href', 'https://pncp.gov.br/app/editais/44444444000101/2026/317');
    expect(screen.getByText(/licitações compradas/).closest('p')?.textContent).toContain(brl(9170000));
    // FOPA separado do resto: o que está fora do escopo vem marcado e apagado
    expect(linhas[1].className).toBe('fora-escopo');
    expect(within(linhas[1] as HTMLElement).getByText('fora do escopo')).toBeInTheDocument();
    expect(doBanco(chamadas).some((c) => c.url.searchParams.get('banco') === '00360305'
      && c.url.searchParams.get('so_fopa_ia') === 'true')).toBe(true);
  });

  it('o período da compra é uma cópia do de cima, com nome próprio, e vai só para as compras do banco', async () => {
    const { chamadas } = fetchFalso({ '/api/analytics': DADOS, '/api/analytics/compras': comprasPorBanco });
    const usuario = userEvent.setup();
    renderizar(<Analytics />, { rota: '/analytics?banco=00360305' });
    // chegando pelo link, o campo já traz o nome do banco
    await waitFor(() => expect(screen.getByLabelText('Instituição financeira')).toHaveValue('CAIXA ECONOMICA FEDERAL'));
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Período da compra' }), '2025');
    await waitFor(() =>
      expect(doBanco(chamadas).some((c) => c.url.searchParams.get('de') === '2025-01-01'
        && c.url.searchParams.get('ate') === '2025-12-31')).toBe(true),
    );
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Período da compra' }), 'Escolher datas');
    fireEvent.change(screen.getByLabelText('comprada de'), { target: { value: '2025-03-01' } });
    await waitFor(() => expect(doBanco(chamadas).some((c) => c.url.searchParams.get('de') === '2025-03-01')).toBe(true));
    // o filtro de cima não mexeu: o analytics continua sem datas
    expect(chamadas.filter((c) => c.url.pathname === '/api/analytics').every((c) => !c.url.searchParams.has('de'))).toBe(true);
    // e a caixa "mostrar fora do escopo" da página vale também aqui
    await usuario.click(screen.getByRole('checkbox', { name: /Mostrar fora do escopo/ }));
    await waitFor(() => expect(doBanco(chamadas).some((c) => c.url.searchParams.get('escopo') === 'todos'
      && !c.url.searchParams.has('so_fopa_ia'))).toBe(true));
  });

  it('banco sem compra no período diz isso; a rota fora do ar não derruba o resto da página', async () => {
    fetchFalso({ '/api/analytics': DADOS, '/api/analytics/compras': { ...DA_CAIXA, compras: [], total: { licitacoes: 0, valor: 0 } } });
    const { unmount } = renderizar(<Analytics />, { rota: '/analytics?banco=00360305&bde=2020-01-01&bate=2020-12-31' });
    expect(await screen.findByText('Nenhuma licitação comprada por CAIXA ECONOMICA FEDERAL no período.')).toBeInTheDocument();
    unmount();
    vi.unstubAllGlobals();
    fetchFalso({ '/api/analytics': DADOS });
    renderizar(<Analytics />, { rota: '/analytics?banco=00000000' });
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível carregar as compras por instituição financeira');
    expect(screen.getAllByText('BANCO DO BRASIL SA').length).toBeGreaterThan(0);   // o resto da página segue
  });
});
