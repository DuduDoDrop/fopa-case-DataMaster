/**
 * /revisao — a fila de revisão humana (`GET /api/fila-revisao`) e a decisão
 * (`POST /api/revisoes`), camada própria: nunca altera respostas nem
 * vereditos. Aba "escopo": `GET/POST /api/rotulos-escopo` (rota nova; sem
 * ela a aba diz que a API ainda não expõe).
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Revisao } from '../paginas/Revisao';
import {
  AGORA_CONTRATO,
  SLUGS,
  filaRevisao,
  filaRevisaoControle,
  filaRevisaoLicitacoes,
  filaRevisaoLicitacoesBusca,
  meLeitor,
  registros,
  responder,
  rotuloPost,
  rotulosEscopo,
} from '../__fixtures__/contrato';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

const ITEM = filaRevisao.itens[0];
// os campos de UMA licitação: o clique na lista leve (ou o link do detalhe) põe ?controle= na URL
const ROTA_CAMPOS = `/revisao?controle=${encodeURIComponent(ITEM.controle)}`;
const LEVE = { 'GET /api/fila-revisao/licitacoes': filaRevisaoLicitacoes };
const OPERADOR = { email: 'operador@teste.br', papel: 'operador', nome: 'Operadora' };
// a revisão de ESCOPO é só do admin (ADR-021, emenda)
const ADMIN = { email: 'admin@teste.br', papel: 'admin', nome: 'Admin' };
// o "como usar" da revisão de respostas
const PASSOS = [
  'Busque a licitação por município, órgão, modalidade, número de controle ou objeto',
  'Selecione a licitação na lista para abrir as respostas a revisar',
  'Confira cada resposta no documento de origem, pelo link da coluna Origem',
  'Registre a decisão: Aceita (resposta correta), Corrigida (informe a resposta correta) ou Rejeitada (sem base nos documentos)',
];

function posts(chamadas: { url: URL; init?: RequestInit }[], caminho: string) {
  return chamadas.filter((c) => c.init?.method === 'POST' && c.url.pathname === caminho).map((c) => JSON.parse(String(c.init?.body)));
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(AGORA_CONTRATO);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('fila de revisão (contrato real)', () => {
  it('mostra a pergunta, a resposta, o conflito, a origem por id e o veredito', async () => {
    fetchFalso({ ...LEVE, 'GET /api/fila-revisao': filaRevisao });
    const { container } = renderizar(<Revisao />, { rota: ROTA_CAMPOS, me: OPERADOR });
    const linha = (await screen.findByText(ITEM.pergunta!)).closest('tr') as HTMLElement;
    expect(linha.textContent).toContain(ITEM.pergunta_id);
    expect(linha.textContent).toContain(ITEM.resposta!);
    expect(linha.textContent).toContain(ITEM.conflito!);
    expect(within(linha).getByRole('link', { name: /01 - Edital\.pdf — p\. 1/ })).toHaveAttribute(
      'href',
      `/api/pdf/${ITEM.slug}/${ITEM.arquivo_id}#page=${ITEM.pagina_final}`,
    );
    expect(linha.querySelector('.v')).toHaveClass(ITEM.veredito!);
    expect(within(linha).getByRole('link', { name: new RegExp(`${ITEM.municipio}/${ITEM.uf}`) })).toHaveAttribute(
      'href',
      `/licitacao/${SLUGS.c2}`,
    );
    expect(container.textContent).toContain(ITEM.motivo!);
  });

  it('operador aceita: POST /api/revisoes {verificacao_id, pergunta_id, decisao} e a fila recarrega', async () => {
    let fila = filaRevisao;
    const { chamadas } = fetchFalso({
      ...LEVE,
      'GET /api/fila-revisao': () => fila,
      'POST /api/revisoes': () => {
        fila = { itens: [] };
        return responder(registros.revisaoPost)();
      },
    });
    const usuario = userEvent.setup();
    renderizar(<Revisao />, { rota: ROTA_CAMPOS, me: OPERADOR });
    await screen.findByText(ITEM.pergunta!);
    await usuario.click(screen.getByRole('button', { name: 'Registrar decisão' }));
    await waitFor(() =>
      expect(posts(chamadas, '/api/revisoes')).toEqual([
        { verificacao_id: ITEM.verificacao_id, pergunta_id: ITEM.pergunta_id, decisao: 'aceita' },
      ]),
    );
    expect(await screen.findByText(/Nenhuma resposta a revisar nesta licitação/)).toBeInTheDocument();
  });

  it('"corrigida" exige a resposta corrigida antes de enviar', async () => {
    const { chamadas } = fetchFalso({
      ...LEVE,
      'GET /api/fila-revisao': filaRevisao,
      'POST /api/revisoes': responder(registros.revisaoPost),
    });
    const usuario = userEvent.setup();
    renderizar(<Revisao />, { rota: ROTA_CAMPOS, me: OPERADOR });
    await screen.findByText(ITEM.pergunta!);
    await usuario.selectOptions(screen.getByLabelText('Decisão'), 'corrigida');
    const registrar = screen.getByRole('button', { name: 'Registrar decisão' });
    expect(registrar).toBeDisabled();
    expect(registrar.getAttribute('title')).toMatch(/resposta corrigida/);
    await usuario.type(screen.getByLabelText('Resposta corrigida'), 'R$ 1.000,00');
    await usuario.type(screen.getByLabelText('Nota'), 'conferido no TR');
    await usuario.click(registrar);
    await waitFor(() =>
      expect(posts(chamadas, '/api/revisoes')).toEqual([
        {
          verificacao_id: ITEM.verificacao_id,
          pergunta_id: ITEM.pergunta_id,
          decisao: 'corrigida',
          resposta_corrigida: 'R$ 1.000,00',
          nota: 'conferido no TR',
        },
      ]),
    );
  });

  it('o 422 da API aparece legível', async () => {
    fetchFalso({ ...LEVE, 'GET /api/fila-revisao': filaRevisao, 'POST /api/revisoes': responder(registros.erroRevisao) });
    const usuario = userEvent.setup();
    renderizar(<Revisao />, { rota: ROTA_CAMPOS, me: OPERADOR });
    await screen.findByText(ITEM.pergunta!);
    await usuario.click(screen.getByRole('button', { name: 'Registrar decisão' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("decisão 'corrigida' exige resposta_corrigida");
  });

  it('o usuário não vê a revisão de escopo: sem a aba, e ?aba=escopo abre as respostas', async () => {
    // A revisão de escopo é restrita ao administrador; os demais papéis veem só a revisão de respostas.
    const { chamadas } = fetchFalso({ ...LEVE, 'GET /api/fila-revisao': filaRevisao });
    renderizar(<Revisao />, { rota: '/revisao?aba=escopo', me: meLeitor });
    expect(await screen.findByRole('heading', { level: 2, name: 'Respostas a revisar (1)' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Escopo' })).toBeNull();
    expect(chamadas.some((c) => c.url.pathname === '/api/rotulos-escopo')).toBe(false);
  });

  it('o usuário vê o título com o total, sem botão, e o passo a passo antes da busca', async () => {
    // Sem botão: o título com o total, o passo a passo e a busca. A aba sozinha parecia um botão que não fazia nada.
    fetchFalso(LEVE);
    const { container } = renderizar(<Revisao />, { rota: '/revisao', me: meLeitor });
    const titulo = await screen.findByRole('heading', { level: 2, name: 'Respostas a revisar (1)' });
    expect(screen.queryByRole('button', { name: /Respostas/ })).toBeNull();
    const passos = within(screen.getByRole('list', { name: 'Como revisar' })).getAllByRole('listitem');
    expect(passos.map((p) => p.textContent)).toEqual(PASSOS);
    const busca = screen.getByRole('searchbox', { name: 'Buscar revisões por licitação' });
    expect(titulo.compareDocumentPosition(passos[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(passos[PASSOS.length - 1].compareDocumentPosition(busca) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // embaixo da busca, sem a linha do total
    expect(container.textContent).not.toMatch(/licitaç(ão|ões) com/);
  });

  it('o admin vê as duas abas e, na de respostas, o mesmo passo a passo', async () => {
    fetchFalso({ ...LEVE, 'GET /api/fila-revisao': filaRevisao });
    renderizar(<Revisao />, { rota: '/revisao', me: ADMIN });
    expect(await screen.findByRole('button', { name: 'Respostas (1)' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Escopo' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Como revisar' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2, name: /Respostas a revisar/ })).toBeNull();
  });

  it('sem nenhuma resposta a revisar: o título diz 0 e a página diz que não há o que revisar', async () => {
    fetchFalso({
      'GET /api/fila-revisao/licitacoes': { ...filaRevisaoLicitacoes, total_revisoes: 0, total_licitacoes: 0, encontradas: 0 },
    });
    renderizar(<Revisao />, { rota: '/revisao', me: meLeitor });
    expect(await screen.findByRole('heading', { level: 2, name: 'Respostas a revisar (0)' })).toBeInTheDocument();
    expect(
      screen.getByText('Nenhuma resposta a revisar. As respostas que o verificador marcar para revisão humana aparecem aqui.'),
    ).toBeInTheDocument();
  });

  it('o usuário (leitor) decide: o formulário vem habilitado (ADR-021, emenda)', async () => {
    fetchFalso({ ...LEVE, 'GET /api/fila-revisao': filaRevisao });
    renderizar(<Revisao />, { rota: ROTA_CAMPOS, me: { email: 'l@x', papel: 'leitor', nome: null } });
    await screen.findByText(ITEM.pergunta!);
    const registrar = screen.getByRole('button', { name: 'Registrar decisão' });
    expect(registrar).toBeEnabled();
    expect(registrar).not.toHaveAttribute('title', expect.stringMatching(/operador/));
  });
});

describe('revisão por licitação: filtro, resultados, campos', () => {
  const BUSCA = 'Buscar revisões por licitação';
  const pesada = (chamadas: { url: URL }[]) => chamadas.filter((c) => c.url.pathname === '/api/fila-revisao');

  it('sem busca não carrega a fila: só o título com o total, os passos e a busca', async () => {
    const { chamadas } = fetchFalso({ ...LEVE, 'GET /api/fila-revisao': filaRevisao });
    const { container } = renderizar(<Revisao />, { rota: '/revisao', me: OPERADOR });
    expect(await screen.findByRole('heading', { level: 2, name: 'Respostas a revisar (1)' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Como revisar' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: BUSCA })).toHaveValue('');
    expect(container.querySelector('table')).toBeNull();
    expect(pesada(chamadas)).toHaveLength(0);
  });

  it('digitar mostra as licitações achadas; clicar abre os campos pendentes dela', async () => {
    const { chamadas } = fetchFalso({
      'GET /api/fila-revisao/licitacoes': (url: URL) => (url.searchParams.get('q') ? filaRevisaoLicitacoesBusca : filaRevisaoLicitacoes),
      'GET /api/fila-revisao': filaRevisaoControle,
    });
    const usuario = userEvent.setup();
    renderizar(<Revisao />, { rota: '/revisao', me: OPERADOR });
    await screen.findByRole('heading', { level: 2, name: 'Respostas a revisar (1)' });
    await usuario.type(screen.getByRole('searchbox', { name: BUSCA }), 'Teste');
    const achada = filaRevisaoLicitacoesBusca.itens[0];
    const botao = await screen.findByRole('link', { name: new RegExp(`${achada.municipio}/${achada.uf}`) });
    expect(botao.closest('li')).toHaveTextContent('1 resposta a revisar');
    expect(botao.closest('li')).toHaveTextContent('1 crítica');
    expect(pesada(chamadas)).toHaveLength(0);
    await usuario.click(botao);
    expect(await screen.findByText(ITEM.pergunta!)).toBeInTheDocument();
    expect(pesada(chamadas).some((c) => c.url.searchParams.get('controle') === achada.controle)).toBe(true);
    // voltar à busca mantém o que foi digitado
    await usuario.click(screen.getByRole('link', { name: /Voltar à busca/ }));
    expect(await screen.findByRole('searchbox', { name: BUSCA })).toHaveValue('Teste');
  });

  it('nada bate: diz, sem tabela', async () => {
    fetchFalso({
      'GET /api/fila-revisao/licitacoes': (url: URL) =>
        url.searchParams.get('q') ? { ...filaRevisaoLicitacoes, encontradas: 0, itens: [] } : filaRevisaoLicitacoes,
    });
    const usuario = userEvent.setup();
    renderizar(<Revisao />, { rota: '/revisao', me: OPERADOR });
    await usuario.type(await screen.findByRole('searchbox', { name: BUSCA }), 'Pelotas');
    expect(await screen.findByText(/Nenhuma licitação com respostas a revisar para .Pelotas./)).toBeInTheDocument();
  });

  it('o link do detalhe (?controle=) abre direto os campos da licitação', async () => {
    const { chamadas } = fetchFalso({ ...LEVE, 'GET /api/fila-revisao': filaRevisaoControle });
    renderizar(<Revisao />, { rota: ROTA_CAMPOS, me: OPERADOR });
    expect(await screen.findByText(ITEM.pergunta!)).toBeInTheDocument();
    expect(pesada(chamadas).every((c) => c.url.searchParams.get('controle') === ITEM.controle)).toBe(true);
    expect(screen.getByText('1 resposta a revisar')).toBeInTheDocument();
  });
});

describe('aba escopo (GET/POST /api/rotulos-escopo reais)', () => {
  const pendente = rotulosEscopo.itens.find((r) => r.rotulo === null)!;
  const rotulada = rotulosEscopo.itens.find((r) => r.rotulo !== null)!;

  it('só as candidatas do Jev sem rótulo aparecem; a rotulada sai da lista', async () => {
    fetchFalso({ 'GET /api/fila-revisao': filaRevisao, 'GET /api/rotulos-escopo': rotulosEscopo });
    const { container } = renderizar(<Revisao />, { rota: '/revisao?aba=escopo', me: ADMIN });
    await screen.findByText('pendente');
    const linhas = [...container.querySelectorAll('tr[data-controle]')];
    expect(linhas.map((l) => l.getAttribute('data-controle'))).toEqual(
      rotulosEscopo.itens.filter((r) => r.rotulo === null).map((r) => r.controle),
    );
    const lp = container.querySelector(`tr[data-controle="${pendente.controle}"]`) as HTMLElement;
    expect(within(lp).getByText('pendente')).toHaveClass('nl');
    expect(within(lp).getByText('IA: não é folha (20%)')).toHaveClass('jev-atencao');
    expect(within(lp).getByText('discorda da regra')).toBeInTheDocument();
    expect(container.querySelector(`tr[data-controle="${rotulada.controle}"]`)).toBeNull();
    expect(container.textContent).not.toContain(rotulada.rotulo!.motivo!);
    expect(screen.getByText(new RegExp(`${rotulosEscopo.pendentes} pendente`))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`já rotuladas \\(${rotulosEscopo.rotuladas}\\)`))).toBeInTheDocument();
    // o passo a passo é o das respostas: no escopo, não aparece
    expect(screen.queryByRole('list', { name: 'Como revisar' })).toBeNull();
  });

  it('a regra recusou e a IA estima que é folha: mostra a chance de SER folha (81%), não "filtro 19%"', async () => {
    const semRotulo = { ...rotulosEscopo, itens: rotulosEscopo.itens.map((r) => ({ ...r, rotulo: null })) };
    fetchFalso({ 'GET /api/fila-revisao': filaRevisao, 'GET /api/rotulos-escopo': semRotulo });
    const { container } = renderizar(<Revisao />, { rota: '/revisao?aba=escopo', me: ADMIN });
    await screen.findAllByText('pendente');
    const outra = rotulosEscopo.itens[1];
    const lo = container.querySelector(`tr[data-controle="${outra.controle}"]`) as HTMLElement;
    expect(within(lo).getByText('IA: é folha (81%)')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/filtro \d+%/);
  });

  it('"Rotular" preenche o controle e grava {controle, dentro, motivo} (201)', async () => {
    const { chamadas } = fetchFalso({
      'GET /api/fila-revisao': filaRevisao,
      'GET /api/rotulos-escopo': rotulosEscopo,
      'POST /api/rotulos-escopo': responder(registros.rotuloPost),
    });
    const usuario = userEvent.setup();
    const { container } = renderizar(<Revisao />, { rota: '/revisao?aba=escopo', me: ADMIN });
    await screen.findByText('pendente');
    const lp = container.querySelector(`tr[data-controle="${pendente.controle}"]`) as HTMLElement;
    await usuario.click(within(lp).getByRole('button', { name: 'Rotular' }));
    expect(screen.getByLabelText('Controle')).toHaveValue(pendente.controle);
    const gravar = screen.getByRole('button', { name: 'Registrar rótulo' });
    expect(gravar).toBeDisabled();
    expect(gravar.getAttribute('title')).toMatch(/dentro ou fora/);
    await usuario.click(screen.getByLabelText('dentro do escopo'));
    await usuario.type(screen.getByLabelText('Motivo'), rotuloPost.motivo!);
    await usuario.click(gravar);
    await waitFor(() =>
      expect(posts(chamadas, '/api/rotulos-escopo')).toEqual([
        { controle: pendente.controle, dentro: true, motivo: rotuloPost.motivo },
      ]),
    );
    expect(await screen.findByText('Rótulo registrado.')).toBeInTheDocument();
  });

  it('o ?controle= do selo do card já vem no formulário', async () => {
    fetchFalso({ 'GET /api/fila-revisao': filaRevisao, 'GET /api/rotulos-escopo': rotulosEscopo });
    renderizar(<Revisao />, { rota: `/revisao?aba=escopo&controle=${encodeURIComponent(rotulada.controle)}`, me: ADMIN });
    await screen.findByText('pendente');
    expect(screen.getByLabelText('Controle')).toHaveValue(rotulada.controle);
  });

  it('um 403 real da API aparece como mensagem, sem quebrar', async () => {
    // Desde 27/09 o leitor lê os rótulos (ADR-021, emenda); o 403 real que sobrou é o dos botões da API, que continuam
    // só do admin. A aba tem de mostrar qualquer recusa da API como mensagem.
    fetchFalso({ 'GET /api/fila-revisao': filaRevisao, 'GET /api/rotulos-escopo': responder(registros.erroLeitorProcessar) });
    renderizar(<Revisao />, { rota: '/revisao?aba=escopo', me: ADMIN });
    expect(await screen.findByRole('alert')).toHaveTextContent('Esta ação requer o perfil admin.');
  });

  it('API anterior à rota (404): a aba diz que ainda não expõe, sem quebrar', async () => {
    fetchFalso({ 'GET /api/fila-revisao': filaRevisao });
    renderizar(<Revisao />, { rota: '/revisao?aba=escopo', me: ADMIN });
    expect(await screen.findByText(/rotulagem manual de escopo ainda não está disponível/)).toBeInTheDocument();
  });
});
