/**
 * O painel com o que a API DEVOLVE (fixtures de contrato): tiles do
 * /api/resumo, filtros com as chaves que a API aceita, contador que bate com
 * a lista (o servidor filtra e pagina; o site não refiltra), home × histórico
 * e o selo do Jev quando a API mandar.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Card, Pagina } from '../api/tipos';
import { dataHora, milhar, usd } from '../lib/formato';
import { Painel } from '../paginas/Painel';
import {
  AGORA_CONTRATO,
  SLUGS,
  copia,
  gastosIa,
  lista,
  listaPagina2,
  listaSemExtracao,
  listaUrgentes,
  resumo,
  listaRecorteTodos,
  resumoRecorteTodos,
} from '../__fixtures__/contrato';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(AGORA_CONTRATO);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// Os números do topo em grupos (componentes/QuadrosResumo, 26/09): cada grupo é uma região com nome.
const grupo = (raiz: HTMLElement, titulo: string) => within(raiz).getByRole('region', { name: titulo });
const destaque = (g: HTMLElement) => g.querySelector('.destaque b')!.textContent;
function linha(g: HTMLElement, rotulo: string) {
  const dt = [...g.querySelectorAll('dt')].find((d) => d.firstChild?.textContent === rotulo);
  if (!dt) throw new Error(`sem a linha "${rotulo}" em ${g.getAttribute('aria-label')}`);
  return { dt, dd: dt.nextElementSibling as HTMLElement };
}
const valor = (g: HTMLElement, rotulo: string) => linha(g, rotulo).dd.textContent;
/** A parte da barra pelo texto da legenda ("fecham em até 7 dias") → o número dela. */
function parte(g: HTMLElement, texto: string) {
  const li = [...g.querySelectorAll('.legenda-partes li')].find((l) => l.textContent!.replace(/^[\d.]+\s*/, '') === texto);
  if (!li) throw new Error(`sem a parte "${texto}" em ${g.getAttribute('aria-label')}`);
  return li.querySelector('b')!.textContent;
}

// As duas barras de página, em cima e embaixo da grade, com nomes diferentes para o leitor de tela.
const navCima = () => screen.getByRole('navigation', { name: 'Paginação, acima da lista' });
const navBaixo = () => screen.getByRole('navigation', { name: 'Paginação, abaixo da lista' });

// As opções do "Mostrar" (vários itens): o botão abre as caixas, uma por opção.
async function opcoesDoMostrar(usuario: ReturnType<typeof userEvent.setup>) {
  await usuario.click(screen.getByRole('button', { name: /^Mostrar: / }));
  return within(screen.getByRole('group', { name: 'Mostrar' }))
    .getAllByRole('checkbox')
    .map((c) => c.closest('label')!.textContent);
}

describe('Painel com o contrato real', () => {
  it('os números da home em grupos: custo, coleta CEGA, teto, provedor', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const { container } = renderizar(<Painel />);
    await screen.findByText('sem IA (ensaio)');
    const andamento = grupo(container, 'Em andamento');
    expect(destaque(andamento)).toBe(milhar(resumo.licitacoes));
    // a barra do prazo: as faixas da barrinha dos cards (vermelho até 7 dias, âmbar até 20, verde depois) e as sem data
    expect(parte(andamento, 'fecham em até 7 dias')).toBe(milhar(resumo.urgentes));
    expect(parte(andamento, 'de 8 a 20 dias')).toBe(milhar(resumo.aviso!));
    expect(parte(andamento, 'sem data de sessão')).toBe(milhar(resumo.licitacoes - resumo.abertas));
    expect(andamento.querySelector('.partes')).toHaveAttribute('aria-label', expect.stringContaining('fecham em até 7 dias'));
    const coleta = linha(andamento, 'Última coleta');
    expect(coleta.dd).toHaveTextContent(dataHora(resumo.ultima_coleta!.iniciado_em));
    expect(coleta.dd).toHaveClass('al');
    expect(coleta.dt).toHaveTextContent('Incompleta: a consulta ao PNCP falhou');
    const extracao = grupo(container, 'Extração');
    expect(destaque(extracao)).toBe(milhar(resumo.extraidas));
    expect(valor(extracao, 'Custo das extrações')).toBe('R$ 4,83');
    // as 2 que rodaram LOCAL contam à parte: não são "sem preço" (não houve chamada de API)
    expect(resumo.extraidas_local).toBe(2);
    expect(linha(extracao, 'Custo das extrações').dt).toHaveTextContent('2 extraídas localmente, sem custo');
    expect(valor(extracao, 'Teto por dia')).toBe('sem teto');
    expect(valor(extracao, 'Extração vigente')).toBe('sem IA (ensaio)');
    const conferencia = grupo(container, 'Conferência');
    expect(destaque(conferencia)).toBe('100%');                          // ancoragem como taxa (25/09)
    expect(conferencia.querySelector('.destaque')).toHaveClass('ok');
    expect(conferencia).toHaveTextContent('44 de 44 respostas');
    const numeros = container.querySelector('.resumo')!.textContent!;
    expect(numeros).not.toContain('sem preço');
    expect(numeros).not.toContain('NaN');
  });

  it('as sem documento na fonte (db/044) aparecem à parte, fora da conta das licitações', async () => {
    fetchFalso({ '/api/resumo': { ...copia(resumo), sem_documento_fonte: 11 }, '/api/licitacoes': lista });
    const { container } = renderizar(<Painel />);
    await screen.findByText('Sem documento na fonte');
    expect(valor(grupo(container, 'Extração'), 'Sem documento na fonte')).toBe('11');
    expect(destaque(grupo(container, 'Em andamento'))).toBe(milhar(resumo.licitacoes));
  });

  it('sem nenhuma sem documento na fonte, o quadro não aparece', async () => {
    fetchFalso({ '/api/resumo': { ...copia(resumo), sem_documento_fonte: 0 }, '/api/licitacoes': lista });
    renderizar(<Painel />);
    await screen.findByText('sem IA (ensaio)');
    expect(screen.queryByText('Sem documento na fonte')).not.toBeInTheDocument();
  });

  it('contador = total do servidor = cards na tela (sem refiltrar no cliente)', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': listaUrgentes });
    const { container } = renderizar(<Painel />, { rota: '/?filtro=urgentes' });
    const conta = await screen.findByText(String(listaUrgentes.total), { selector: '#conta' });
    expect(conta.parentElement!.textContent).toContain(`${listaUrgentes.total} ${listaUrgentes.total === 1 ? 'licitação' : 'licitações'} na lista`);
    await waitFor(() => expect(container.querySelectorAll('article.card')).toHaveLength(listaUrgentes.itens.length));
  });

  it('a lista inteira do servidor vira um card por controle, na ordem do servidor', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const { container } = renderizar(<Painel />);
    await waitFor(() => expect(container.querySelectorAll('article.card')).toHaveLength(lista.itens.length));
    const ordem = [...container.querySelectorAll('article.card')].map((a) => a.getAttribute('data-controle'));
    expect(ordem).toEqual(lista.itens.map((c) => c.controle));
    expect(screen.getByText(String(lista.total), { selector: '#conta' })).toBeInTheDocument();
  });

  it.each([
    ['Sem extração', 'sem_extracao'],
    ['Já extraídas', 'extraidas'],
    ['Com conflito', 'conflito'],
  ])('o filtro "%s" vai para a API como filtro=%s (a chave que ela aceita)', async (rotulo, chave) => {
    const { chamadas } = fetchFalso({
      '/api/resumo': resumo,
      '/api/licitacoes': (url: URL) => (url.searchParams.get('filtro') === 'sem_extracao' ? listaSemExtracao : lista),
    });
    const usuario = userEvent.setup();
    renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    // os botões soltos viraram uma lista, que desde 28/09 aceita vários itens e vale no "Filtrar"
    await usuario.click(screen.getByRole('button', { name: 'Mostrar: Todas' }));
    await usuario.click(screen.getByRole('checkbox', { name: rotulo }));
    expect(screen.getByRole('button', { name: `Mostrar: ${rotulo}` })).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Filtrar' }));
    await waitFor(() =>
      expect(chamadas.some((c) => c.url.pathname === '/api/licitacoes' && c.url.searchParams.get('filtro') === chave)).toBe(true),
    );
  });

  it('a barra da home não tem os cinco botões tirados em 25/09 nem o "≤7 dias" (28/09)', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const usuario = userEvent.setup();
    renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const opcoes = await opcoesDoMostrar(usuario);
    for (const rotulo of ['Com alerta de regra', 'Injeção suspeita', 'Retificadas', 'Revisão pendente', 'Ensaio', 'Fecham em ≤7 dias']) {
      expect(opcoes).not.toContain(rotulo);
    }
    expect(opcoes).toContain('Com conflito');
    expect(screen.queryByRole('button', { name: 'Com conflito' })).toBeNull();          // não há mais botão solto
  });

  it('o histórico tira quatro e o "≤7 dias", mas mantém "Com alerta de regra"', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const usuario = userEvent.setup();
    renderizar(<Painel situacao="historico" />, { rota: '/historico' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const opcoes = await opcoesDoMostrar(usuario);
    for (const rotulo of ['Injeção suspeita', 'Retificadas', 'Revisão pendente', 'Ensaio', 'Fecham em ≤7 dias']) {
      expect(opcoes).not.toContain(rotulo);
    }
    expect(opcoes).toContain('Com alerta de regra');
  });

  it('no histórico, os quadros são os de análise: com vencedor, revogadas, de antes de 2026', async () => {
    const r = { ...resumo, com_vencedor: 1800, desfeitas: 42, antes_do_recorte: 1500, ano_minimo: 2026 };
    fetchFalso({ '/api/resumo': r, '/api/licitacoes': lista });
    const { container } = renderizar(<Painel situacao="historico" />, { rota: '/historico' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const acervo = grupo(container, 'No histórico');
    expect(parte(acervo, 'com vencedor homologado')).toBe('1.800');
    expect(parte(acervo, 'revogadas ou anuladas')).toBe('42');
    expect(valor(acervo, 'Anteriores a 2026')).toBe('1.500');
    const numeros = container.querySelector('.resumo')!.textContent!;
    for (const fora of ['abertas', 'fecham em até 7 dias', 'Última coleta', 'Teto por dia', 'Extração vigente', 'Gastos com IA']) {
      expect(numeros).not.toContain(fora);
    }
  });

  it('o texto do histórico diz tudo o que manda para cá, como a API (api/consultas.py HISTORICO)', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(<Painel situacao="historico" />, { rota: '/historico' });
    const texto = (await screen.findByRole('heading', { name: 'Histórico' })).parentElement!.textContent!;
    for (const regra of [
      'sessão já realizada',
      'vencedor homologado no PNCP (o credenciamento com inscrições abertas permanece no painel)',
      'revogada ou anulada',
      'sem data de sessão e publicada há mais de 60 dias',
      'todas as anteriores a 2026',
      'nota até 25%',
    ]) {
      expect(texto).toContain(regra);
    }
    // quem ganhou e por quanto não está nesta tela, e sim no analytics
    expect(texto).not.toContain('quem ganhou');
  });

  it('ancoragem cabe no quadro: percentual no número grande, as contagens na legenda', async () => {
    const r = { ...resumo, ancoradas: 23002, respondidas: 23006 };
    fetchFalso({ '/api/resumo': r, '/api/licitacoes': lista });
    const { container } = renderizar(<Painel situacao="historico" />, { rota: '/historico' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const conferencia = grupo(container, 'Conferência');
    expect(destaque(conferencia)).toBe('99,98%');
    expect(conferencia.querySelector('.destaque span')).toHaveTextContent('23.002 de 23.006 respostas com o trecho do edital');
  });

  it('ancoragem acima de 99% fica verde, na home e no histórico', async () => {
    const r = { ...resumo, ancoradas: 23522, respondidas: 23526 };
    fetchFalso({ '/api/resumo': r, '/api/licitacoes': lista });
    const { container, unmount } = renderizar(<Painel situacao="historico" />, { rota: '/historico' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const anc = (raiz: HTMLElement) => grupo(raiz, 'Conferência').querySelector('.destaque');
    expect(anc(container)).toHaveClass('ok');
    unmount();
    const baixa = { ...resumo, ancoradas: 900, respondidas: 1000 };
    fetchFalso({ '/api/resumo': baixa, '/api/licitacoes': lista });
    const h = renderizar(<Painel situacao="historico" />, { rota: '/historico' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(anc(h.container)).toHaveClass('al');
    h.unmount();
    fetchFalso({ '/api/resumo': r, '/api/licitacoes': lista });
    const home = renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(anc(home.container)).toHaveClass('ok');
    home.unmount();
    fetchFalso({ '/api/resumo': { ...resumo, ancoradas: 99, respondidas: 100 }, '/api/licitacoes': lista });
    const limite = renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    // 99% exatos não é "acima de 99%"
    expect(anc(limite.container)).toHaveClass('al');
  });

  it('na home, os quadros do dia continuam', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const { container } = renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const numeros = container.querySelector('.resumo')!.textContent!;
    for (const dentro of ['fecham em até 7 dias', 'Última coleta', 'Teto por dia', 'Extração vigente']) {
      expect(numeros).toContain(dentro);
    }
    expect(numeros).not.toContain('com vencedor homologado');
  });

  it('a barra do prazo soma as abertas pelas faixas dos cards; o verde é o resto das abertas', async () => {
    const r = { ...resumo, licitacoes: 12, abertas: 10, urgentes: 2, aviso: 3 };
    fetchFalso({ '/api/resumo': r, '/api/licitacoes': lista });
    const { container } = renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const andamento = grupo(container, 'Em andamento');
    expect(parte(andamento, 'fecham em até 7 dias')).toBe('2');
    expect(parte(andamento, 'de 8 a 20 dias')).toBe('3');
    expect(parte(andamento, 'depois de 20 dias')).toBe('5');
    expect(parte(andamento, 'sem data de sessão')).toBe('2');
    const cores = [...andamento.querySelectorAll('.partes i')].map((i) => i.className);
    expect(cores).toEqual(['al', 'am', 'ok', 'neutro']);
  });

  it('filtro da URL sem botão na página não vale: ?filtro=alerta na home lista todas', async () => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(<Painel />, { rota: '/?filtro=alerta' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const pedidas = chamadas.filter((c) => c.url.pathname === '/api/licitacoes');
    expect(pedidas.length).toBeGreaterThan(0);
    expect(pedidas.every((c) => c.url.searchParams.get('filtro') === null)).toBe(true);
    expect(screen.getByRole('button', { name: 'Mostrar: Todas' })).toBeInTheDocument();
  });

  it('a home não oferece "mostrar anteriores a 2026" e não manda recorte nem com ?recorte=todos na URL', async () => {
    // O que é de antes de 2026 é legado e mora no histórico: a caixa traria de volta,
    // em dobro, o que o histórico já mostra. A home e o histórico particionam o acervo.
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(<Painel />, { rota: '/?recorte=todos' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(screen.queryByRole('checkbox', { name: /mostrar anteriores a/ })).toBeNull();
    expect(chamadas.length).toBeGreaterThan(0);
    expect(chamadas.every((c) => !c.url.searchParams.has('recorte'))).toBe(true);
  });

  it('só folha: nenhuma caixa "mostrar fora do escopo", nenhum ?escopo na lista nem no resumo', async () => {
    // O que não entra no escopo sai de todas as telas: a tela de licitações não oferece
    // o que a regra recusou — isso fica na aba "escopo" da revisão e no analytics.
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(screen.queryByRole('checkbox', { name: /fora do escopo/ })).toBeNull();
    expect(screen.queryByText(/fora do escopo/)).toBeNull();
    expect(chamadas.length).toBeGreaterThan(0);
    expect(chamadas.every((c) => !c.url.searchParams.has('escopo'))).toBe(true);
    expect(lista.itens.every((c) => c.escopo_dentro !== false)).toBe(true);
  });

  it('home × histórico: a home pede situacao=ativas (lista E resumo), sem o chip Encerradas, e aponta o histórico', async () => {
    // O que já passou da sessão vira legado e sai da grade de trabalho — sem apagar nada.
    const { chamadas } = fetchFalso({ '/api/resumo': { ...copia(resumo), historico: 479 }, '/api/licitacoes': lista });
    renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    await waitFor(() => {
      for (const p of ['/api/licitacoes', '/api/resumo']) {
        expect(chamadas.some((c) => c.url.pathname === p && c.url.searchParams.get('situacao') === 'ativas')).toBe(true);
      }
    });
    expect(screen.queryByRole('button', { name: 'Encerradas' })).toBeNull();
    const link = screen.getByRole('link', { name: /479 no histórico/ });
    expect(link).toHaveAttribute('href', '/historico');
  });

  it('histórico: pede situacao=historico, título próprio, sem "≤7 dias" nem o recorte de ano, e volta às abertas', async () => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(<Painel situacao="historico" />);
    expect(await screen.findByRole('heading', { name: 'Histórico' })).toBeInTheDocument();
    await waitFor(() => {
      for (const p of ['/api/licitacoes', '/api/resumo']) {
        expect(chamadas.some((c) => c.url.pathname === p && c.url.searchParams.get('situacao') === 'historico')).toBe(true);
      }
    });
    expect(screen.queryByRole('button', { name: 'Fecham em ≤7 dias' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Encerradas' })).toBeNull();
    expect(screen.queryByRole('checkbox', { name: /mostrar anteriores a/ })).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Vencimento' })).toBeNull();
    expect(screen.getByRole('link', { name: /Voltar ao painel/ })).toHaveAttribute('href', '/');
  });

  it('histórico: filtro de datas pela publicação vai para a lista E o resumo', async () => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const usuario = userEvent.setup();
    renderizar(<Painel situacao="historico" />);
    // o período é uma lista (26/09): todo o histórico, os anos e "escolher datas"; não há 2021 (o PNCP não tem compra de
    // folha antes de 2022); as datas só aparecem em "escolher datas"
    const periodo = await screen.findByRole('combobox', { name: 'Período' });
    const anos = [...(periodo as HTMLSelectElement).options].map((o) => o.text);
    expect(anos).toContain('2022');
    expect(anos).not.toContain('2021');
    expect(screen.queryByLabelText('publicada de')).toBeNull();
    await screen.findByRole('heading', { name: 'Histórico' });
    await usuario.selectOptions(periodo, 'Escolher datas');
    fireEvent.change(screen.getByLabelText('publicada de'), { target: { value: '2024-01-01' } });
    fireEvent.change(screen.getByLabelText('publicada até'), { target: { value: '2024-12-31' } });
    // as escolhas da barra valem no "Filtrar": antes dele, nada foi pedido com as datas
    expect(chamadas.some((c) => c.url.searchParams.get('de') === '2024-01-01')).toBe(false);
    await usuario.click(screen.getByRole('button', { name: 'Filtrar' }));
    await waitFor(() => {
      for (const p of ['/api/licitacoes', '/api/resumo']) {
        expect(
          chamadas.some(
            (c) =>
              c.url.pathname === p && c.url.searchParams.get('de') === '2024-01-01' && c.url.searchParams.get('ate') === '2024-12-31',
          ),
        ).toBe(true);
      }
    });
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Período' }), 'Todo o histórico');
    await usuario.click(screen.getByRole('button', { name: 'Filtrar' }));
    await waitFor(() => expect(chamadas[chamadas.length - 1].url.searchParams.has('de')).toBe(false));
  });

  it.each([
    ['histórico', true],
    ['home', false],
  ])('%s: só o que a IA confirma como folha, SEMPRE — so_fopa_ia na lista e no resumo, sem caixa', async (_nome, historico) => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(historico ? <Painel situacao="historico" /> : <Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const daTela = () => chamadas.filter((c) => ['/api/licitacoes', '/api/resumo'].includes(c.url.pathname));
    await waitFor(() => {
      for (const p of ['/api/licitacoes', '/api/resumo']) {
        expect(daTela().some((c) => c.url.pathname === p)).toBe(true);
      }
    });
    expect(daTela().every((c) => c.url.searchParams.get('so_fopa_ia') === 'true')).toBe(true);
    expect(screen.queryByRole('checkbox', { name: /apenas FOPA/ })).toBeNull();
  });

  it('home: vários itens no "Mostrar" e o "Vencimento" valem no "Filtrar": filtro repetido e vence_em, na página 1', async () => {
    // Vários itens no "Mostrar" e o botão "Filtrar", que aplica tudo de uma vez
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const u = userEvent.setup();
    renderizar(<Painel />, { rota: '/?page=3' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    await u.click(screen.getByRole('button', { name: 'Mostrar: Todas' }));
    expect(screen.queryByRole('checkbox', { name: 'Fecham em ≤7 dias' })).toBeNull();
    await u.click(screen.getByRole('checkbox', { name: 'Com conflito' }));
    await u.click(screen.getByRole('checkbox', { name: 'Já extraídas' }));
    await u.selectOptions(screen.getByRole('combobox', { name: 'Vencimento' }), '15');
    const daLista = () => chamadas.filter((c) => c.url.pathname === '/api/licitacoes');
    expect(daLista().every((c) => !c.url.searchParams.has('filtro') && !c.url.searchParams.has('vence_em'))).toBe(true);
    await u.click(screen.getByRole('button', { name: 'Filtrar' }));
    await waitFor(() => {
      const ultima = daLista().at(-1)!;
      expect(ultima.url.searchParams.getAll('filtro')).toEqual(['conflito', 'extraidas']);
      expect(ultima.url.searchParams.get('vence_em')).toBe('15');
      expect(ultima.url.searchParams.has('page')).toBe(false);
    });
    expect(screen.getByRole('button', { name: 'Mostrar: Com conflito, Já extraídas' })).toBeInTheDocument();
  });

  it('a URL guarda a escolha; vencimento fora da lista não vale', async () => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(<Painel />, { rota: '/?filtro=conflito&filtro=extraidas&filtro=urgentes&vence_em=30' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(screen.getByRole('button', { name: 'Mostrar: Com conflito, Já extraídas' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Vencimento' })).toHaveValue('30');
    const pedida = chamadas.find((c) => c.url.pathname === '/api/licitacoes')!;
    expect(pedida.url.searchParams.getAll('filtro')).toEqual(['conflito', 'extraidas']);
    expect(pedida.url.searchParams.get('vence_em')).toBe('30');
  });

  it('home com ?vence_em=10 e histórico com ?vence_em=30: nenhum dos dois manda vence_em', async () => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const { unmount } = renderizar(<Painel />, { rota: '/?vence_em=10' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(screen.getByRole('combobox', { name: 'Vencimento' })).toHaveValue('');
    unmount();
    renderizar(<Painel situacao="historico" />, { rota: '/historico?vence_em=30' });
    await screen.findByRole('heading', { name: 'Histórico' });
    await waitFor(() => expect(chamadas.some((c) => c.url.searchParams.get('situacao') === 'historico')).toBe(true));
    expect(chamadas.filter((c) => c.url.pathname === '/api/licitacoes').every((c) => !c.url.searchParams.has('vence_em'))).toBe(true);
  });

  it('home (ativas) sem filtro de datas', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(<Painel />);
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(screen.queryByLabelText('publicada de')).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Período' })).toBeNull();
  });

  it('paginação pelos campos do servidor (page, paginas)', async () => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': listaPagina2 });
    const usuario = userEvent.setup();
    renderizar(<Painel />, { rota: '/?page=2' });
    expect(listaPagina2.page).toBe(2);
    const baixo = await screen.findByRole('navigation', { name: 'Paginação, abaixo da lista' });
    expect(within(baixo).getByText(`página 2 de ${listaPagina2.paginas}`)).toBeInTheDocument();
    const proxima = within(baixo).getByRole('button', { name: /Próxima/ });
    expect(proxima).toBeDisabled();
    expect(proxima).toHaveAttribute('title', 'Esta é a última página.');
    await usuario.click(within(baixo).getByRole('button', { name: /Anterior/ }));
    await waitFor(() =>
      expect(chamadas.some((c) => c.url.pathname === '/api/licitacoes' && !c.url.searchParams.has('page'))).toBe(true),
    );
  });

  it.each([
    ['home', false],
    ['histórico', true],
  ])('%s: 10 por página por padrão, com a lista "Itens" de 10, 50 ou 100', async (_nome, historico) => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    const usuario = userEvent.setup();
    renderizar(historico ? <Painel situacao="historico" /> : <Painel />, { rota: historico ? '/historico?page=3' : '/?page=3' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    const pedidas = () => chamadas.filter((c) => c.url.pathname === '/api/licitacoes');
    expect(pedidas().every((c) => c.url.searchParams.get('por_pagina') === '10')).toBe(true);
    const itens = screen.getByRole('combobox', { name: 'Itens' });
    expect(itens).toHaveValue('10');
    // sem "todos": a API pagina no servidor, até 200 por página, e o histórico tem milhares
    expect([...(itens as HTMLSelectElement).options].map((o) => o.text)).toEqual(['10 por página', '50 por página', '100 por página']);
    await usuario.selectOptions(itens, '50');
    // trocar a quantidade volta à primeira página
    await waitFor(() => {
      const ultima = pedidas()[pedidas().length - 1].url.searchParams;
      expect(ultima.get('por_pagina')).toBe('50');
      expect(ultima.has('page')).toBe(false);
    });
  });

  it('a quantidade por página mora na URL e o contador diz o trecho mostrado', async () => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': listaPagina2 });
    renderizar(<Painel />, { rota: '/?page=2&itens=100' });
    // as duas barras dizem a mesma página
    expect(await screen.findAllByText(`página 2 de ${listaPagina2.paginas}`)).toHaveLength(2);
    expect(chamadas.filter((c) => c.url.pathname === '/api/licitacoes').every((c) => c.url.searchParams.get('por_pagina') === '100')).toBe(true);
    expect(screen.getByRole('combobox', { name: 'Itens' })).toHaveValue('100');
    // página 2 de 100 em 100: do 101º ao último que veio
    const ate = 100 + listaPagina2.itens.length;
    expect(screen.getByText(`mostrando ${milhar(101)}–${milhar(ate)} de ${milhar(listaPagina2.total)}`)).toBeInTheDocument();
  });

  it.each([
    ['home', false],
    ['histórico', true],
  ])('%s: passar de página ou trocar a quantidade leva ao alto da grade; mudar o filtro não', async (_nome, historico) => {
    const alvos: Element[] = [];
    const rolar = vi.fn(function (this: Element) {
      alvos.push(this);
    });
    Element.prototype.scrollIntoView = rolar;
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': listaPagina2 });
    const usuario = userEvent.setup();
    const { container } = renderizar(historico ? <Painel situacao="historico" /> : <Painel />, {
      rota: historico ? '/historico?page=2' : '/?page=2',
    });
    await screen.findByRole('navigation', { name: 'Paginação, acima da lista' });
    // o alvo é o alto da grade: a barra de cima quando ela existe (da página 2 em diante), senão o primeiro card
    const grade = container.querySelector('.grade-lista')!;
    expect(grade.firstElementChild).toBe(navCima());
    await usuario.click(within(navBaixo()).getByRole('button', { name: /Anterior/ }));    // 2 → 1
    expect(alvos).toEqual([grade]);
    expect(grade.firstElementChild).toBe(container.querySelector('article.card'));       // na 1, o alto é o 1º card
    await usuario.click(within(navBaixo()).getByRole('button', { name: /Próxima/ }));     // 1 → 2
    expect(alvos).toEqual([grade, grade]);
    await usuario.click(within(navCima()).getByRole('button', { name: /Anterior/ }));     // os de cima também
    expect(alvos).toEqual([grade, grade, grade]);
    await usuario.selectOptions(screen.getByRole('combobox', { name: 'Itens' }), '50');
    expect(alvos).toEqual([grade, grade, grade, grade]);
    await usuario.click(screen.getByRole('button', { name: /^Mostrar: / }));
    await usuario.click(screen.getByRole('checkbox', { name: 'Já extraídas' }));
    await usuario.click(screen.getByRole('button', { name: 'Filtrar' }));
    expect(rolar).toHaveBeenCalledTimes(4);
  });

  it.each([
    ['home', false],
    ['histórico', true],
  ])('%s: a barra de páginas de cima só aparece da página 2 em diante', async (_nome, historico) => {
    // A barra de páginas de cima só aparece a partir da página 2: na primeira ela não tem função, porque a barra
    // de baixo já leva adiante.
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': listaPagina2 });
    const usuario = userEvent.setup();
    const { container } = renderizar(historico ? <Painel situacao="historico" /> : <Painel />, {
      rota: historico ? '/historico' : '/',
    });
    const baixo = await screen.findByRole('navigation', { name: 'Paginação, abaixo da lista' });
    await waitFor(() => expect(container.querySelectorAll('article.card').length).toBeGreaterThan(0));
    expect(screen.queryByRole('navigation', { name: 'Paginação, acima da lista' })).toBeNull();     // página 1: só embaixo
    await usuario.click(within(baixo).getByRole('button', { name: /Próxima/ }));
    await waitFor(() =>
      expect(chamadas.some((c) => c.url.pathname === '/api/licitacoes' && c.url.searchParams.get('page') === '2')).toBe(true),
    );
    // página 2: em cima, logo antes do primeiro card; embaixo, logo depois da grade — as duas andando juntas
    const cima = navCima();
    expect(cima.nextElementSibling).toBe(container.querySelector('article.card'));
    expect(container.querySelector('.grade-lista')!.nextElementSibling).toBe(navBaixo());
    for (const nav of [cima, navBaixo()]) {
      expect(within(nav).getByText(`página 2 de ${listaPagina2.paginas}`)).toBeInTheDocument();
    }
    // os de cima mudam a página como os de baixo; de volta à 1, a barra de cima some
    await usuario.click(within(cima).getByRole('button', { name: /Anterior/ }));
    expect(screen.queryByRole('navigation', { name: 'Paginação, acima da lista' })).toBeNull();
    expect(within(navBaixo()).getByText(`página 1 de ${listaPagina2.paginas}`)).toBeInTheDocument();
  });

  it('?itens com valor que não existe na lista vale 10', async () => {
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista });
    renderizar(<Painel />, { rota: '/?itens=5000' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(chamadas.filter((c) => c.url.pathname === '/api/licitacoes').every((c) => c.url.searchParams.get('por_pagina') === '10')).toBe(true);
    expect(screen.getByRole('combobox', { name: 'Itens' })).toHaveValue('10');
  });

  it('lista vazia mostra o aviso', async () => {
    const vazia: Pagina<Card> = { ...copia(lista), itens: [], total: 0, paginas: 0 };
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': vazia });
    renderizar(<Painel />);
    expect(await screen.findByText('Nenhuma licitação encontrada para os filtros selecionados.')).toBeInTheDocument();
  });

  it('jev_filtro real: selo "IA: é folha (X%)" em palavras, destacado quando discorda e é candidata', async () => {
    // Os percentuais em palavras, fáceis de entender
    // C4 (no escopo, o Jev discorda com convicção: candidata) está no recorte inteiro.
    const comJev = listaRecorteTodos;
    fetchFalso({ '/api/resumo': resumoRecorteTodos, '/api/licitacoes': comJev });
    // a revisão de escopo é só do admin: é ele quem ganha o link do selo
    const { container } = renderizar(<Painel />, { me: { email: 'a@x', papel: 'admin', nome: null } });
    await waitFor(() => expect(container.querySelectorAll('article.card')).toHaveLength(comJev.itens.length));
    const artigo = (slug: string) =>
      container.querySelector(`article[data-controle="${comJev.itens.find((c) => c.slug === slug)!.controle}"]`) as HTMLElement;
    const selo1 = within(artigo(SLUGS.c1)).getByText('IA: é folha (93%)');
    expect(selo1).toHaveAttribute('title', expect.stringContaining('Probabilidade de ser compra de folha'));
    expect(selo1).toHaveClass('jev-sim');
    expect(selo1).not.toHaveClass('jev-atencao');
    const selo4 = within(artigo(SLUGS.c4)).getByText('IA: não é folha (20%)');
    expect(selo4).toHaveClass('jev-atencao');
    expect(selo4).toHaveClass('jev-nao');
    // candidata leva à aba de escopo da revisão, com o controle
    expect(selo4.closest('a')).toHaveAttribute('href', expect.stringContaining('/revisao?aba=escopo&controle='));
    expect(screen.getByText(/segundo a IA \(Jev\)/, { selector: 'p' })).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/filtro \d+%/);                        // a leitura antiga saiu
    // a linha do resumo real: quantas a IA estima que não são folha, de quantas avaliou
    const jev = resumoRecorteTodos.jev!;
    const ia = linha(grupo(container, 'Conferência'), 'Não reconhecidas como folha pela IA');
    expect(ia.dd).toHaveClass('am');
    expect(ia.dd).toHaveTextContent(`${milhar(jev.escopo_discordancias)} de ${milhar(jev.escopo_avaliadas)}`);
    expect(ia.dt).toHaveAttribute('title', expect.stringContaining('Probabilidade de ser compra de folha'));
  });

  it('para o usuário, o selo da candidata fica destacado, mas sem link para a revisão de escopo', async () => {
    const comJev = listaRecorteTodos;
    fetchFalso({ '/api/resumo': resumoRecorteTodos, '/api/licitacoes': comJev });
    const { container } = renderizar(<Painel />);
    await waitFor(() => expect(container.querySelectorAll('article.card')).toHaveLength(comJev.itens.length));
    const selo4 = within(
      container.querySelector(`article[data-controle="${comJev.itens.find((c) => c.slug === SLUGS.c4)!.controle}"]`) as HTMLElement,
    ).getByText('IA: não é folha (20%)');
    expect(selo4).toHaveClass('jev-atencao');
    expect(selo4.closest('a')).toBeNull();
    expect(selo4.getAttribute('title')).not.toMatch(/clique para revisar/i);
  });

  it('gastos com IA na home: Jev, Claude e GPT somados, e de onde veio cada número', async () => {
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista, '/api/gastos-ia': gastosIa });
    const { container } = renderizar(<Painel />);
    await screen.findByRole('region', { name: 'Gastos com IA' });
    const g = grupo(container, 'Gastos com IA');
    expect(destaque(g)).toBe(usd(gastosIa.total_usd));
    expect(g.querySelector('.destaque span')).toHaveTextContent('≈ R$');
    for (const p of gastosIa.provedores) expect(valor(g, p.rotulo)).toBe(usd(p.usd));
    // de onde veio cada número fica no title; embaixo, uma nota só
    expect(linha(g, 'Claude (Anthropic)').dt).toHaveAttribute('title', expect.stringContaining('Fatura lida em'));
    expect(linha(g, 'Jev (TypeSafe)').dt).toHaveAttribute(
      'title',
      expect.stringMatching(/Painel da TypeSafe, lido em .+, mais US\$ 0,04 medidos depois/),
    );
    expect(g).toHaveTextContent('Extrações locais não entram no total');
    // do maior para o menor, na barra e nas linhas
    const ordem = [...g.querySelectorAll('dt')].map((d) => d.firstChild!.textContent);
    expect(ordem).toEqual([...gastosIa.provedores].sort((a, b) => Number(b.usd) - Number(a.usd)).map((p) => p.rotulo));
    expect(g.querySelectorAll('.partes i')).toHaveLength(gastosIa.provedores.length);
  });

  it('gasto sem leitura diz "sem leitura", nunca US$ 0; no histórico os gastos nem se pedem', async () => {
    const semOpenai = copia(gastosIa);
    Object.assign(semOpenai.provedores.find((p) => p.provedor === 'openai')!, { usd: null, fonte: null, lido_em: null, desde: null });
    semOpenai.sem_leitura = ['openai'];
    fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista, '/api/gastos-ia': semOpenai });
    const { container, unmount } = renderizar(<Painel />);
    await screen.findByRole('region', { name: 'Gastos com IA' });
    const g = grupo(container, 'Gastos com IA');
    expect(valor(g, 'GPT (OpenAI)')).toBe('sem leitura');
    expect(g).toHaveTextContent('O total ainda não inclui GPT (OpenAI).');
    expect(g).not.toHaveTextContent('US$ 0,00');
    unmount();
    const { chamadas } = fetchFalso({ '/api/resumo': resumo, '/api/licitacoes': lista, '/api/gastos-ia': gastosIa });
    const h = renderizar(<Painel situacao="historico" />, { rota: '/historico' });
    await screen.findByText(String(lista.total), { selector: '#conta' });
    expect(within(h.container).queryByRole('region', { name: 'Gastos com IA' })).toBeNull();
    expect(chamadas.some((c) => c.url.pathname === '/api/gastos-ia')).toBe(false);
  });

  it('API sem os campos do Jev (versão anterior): nenhum selo, nenhuma nota, nada quebra', async () => {
    // Derivada: o payload real sem `jev_filtro` nos cards e sem `jev` no resumo.
    const semJev = copia(lista);
    for (const c of semJev.itens) delete c.jev_filtro;
    const resumoSemJev = copia(resumo);
    delete resumoSemJev.jev;
    fetchFalso({ '/api/resumo': resumoSemJev, '/api/licitacoes': semJev });
    const { container } = renderizar(<Painel />);
    await waitFor(() => expect(container.querySelectorAll('article.card')).toHaveLength(semJev.itens.length));
    await screen.findByText('sem IA (ensaio)');
    expect(container.textContent).not.toMatch(/IA: /);
    expect(container.textContent).not.toContain('opinião da IA');
    expect(container.textContent).not.toContain('acha que não é folha');
  });
});
