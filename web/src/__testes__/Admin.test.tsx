/**
 * /admin contra as rotas REAIS (`/api/admin/...`, respostas `{itens:[...]}`):
 * trocar o provedor para um que gasta exige confirmação com o aviso de custo
 * da própria API (e o 409 sem `confirmar` também vira confirmação); "Verificar
 * agora" chama o W11 (202 + execucao_id) e acompanha `GET /api/execucoes/{id}`
 * — que devolve `{execucao:{status}, buscas}` — até terminar.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Admin, lerRespostas } from '../paginas/Admin';
import type { ExecucaoWorkflow } from '../api/tipos';
import {
  configuracao,
  copia,
  execucaoConcluida,
  execucaoEmCurso,
  execucoes,
  orcamento,
  registros,
  responder,
  termos,
  usuarios,
} from '../__fixtures__/contrato';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

const BASE = {
  'GET /api/admin/configuracao': configuracao,
  'GET /api/admin/orcamento': orcamento,
  'GET /api/admin/termos': termos,
  'GET /api/admin/usuarios': usuarios,
};
const ADMIN = { email: 'admin@exemplo.com', papel: 'admin', nome: 'Admin', supremo: true };
/** Um admin que o supremo liberou para testar (db/046): age na API, mas não mexe em usuários. */
const ADMIN_NORMAL = { email: 'o@x', papel: 'admin', nome: null, supremo: false };
/** O respostas.json do agente (70_extracao_por_agente.py): 17 objetos, Q1 a Q17. */
const DEZESSETE = Array.from({ length: 17 }, (_, i) => ({
  id: `Q${i + 1}`,
  resposta: 'Não localizado.',
  arquivo: null,
  pagina: null,
  trecho_literal: null,
  conflito: null,
  confianca: 'media',
}));
const IMPORTAR = '/api/acoes/importar-respostas';

function puts(chamadas: { url: URL; init?: RequestInit }[], caminho: string, metodo = 'PUT') {
  return chamadas.filter((c) => c.init?.method === metodo && c.url.pathname === caminho).map((c) => JSON.parse(String(c.init?.body)));
}

/** As rotas da última verificação: a lista do W01 (a mais recente na frente, como a API ordena) e o detalhe dela. */
function ultimaVerificacao(campos: Partial<ExecucaoWorkflow>) {
  const lista = copia(execucoes);
  lista.itens = lista.itens.filter((i) => i.workflow === 'W01');
  const ultima = Object.assign(lista.itens[0], campos);
  const detalhe = copia(ultima.status === 'em_curso' ? execucaoEmCurso : execucaoConcluida);
  const { id, n8n_execution_id, status, iniciado_em, duracao_s, contadores } = ultima;
  Object.assign(detalhe.execucao, { id, n8n_execution_id, status, iniciado_em, duracao_s, contadores });
  return { 'GET /api/execucoes': lista, [`/api/execucoes/${id}`]: detalhe };
}

afterEach(() => vi.unstubAllGlobals());

describe('Admin com o contrato real', () => {
  it('lê de /api/admin/* e não de rotas inventadas', async () => {
    const { chamadas } = fetchFalso(BASE);
    renderizar(<Admin />, { me: ADMIN });
    await screen.findByLabelText('Provedor vigente');
    await screen.findByText(termos.itens[0].termo);
    await screen.findByText(usuarios.itens[0].email);
    const caminhos = new Set(chamadas.map((c) => c.url.pathname));
    for (const p of ['/api/admin/configuracao', '/api/admin/orcamento', '/api/admin/termos', '/api/admin/usuarios']) {
      expect(caminhos.has(p)).toBe(true);
    }
  });

  it('trocar para claude mostra o aviso de custo da API e só grava com confirmar=true', async () => {
    const { chamadas } = fetchFalso({ ...BASE, 'PUT /api/admin/configuracao': responder(registros.configPut) });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    await usuario.selectOptions(await screen.findByLabelText('Provedor vigente'), 'claude');
    const aviso = screen.getByRole('group', { name: 'Confirmar troca de provedor' });
    expect(aviso.textContent).toContain(configuracao.aviso_custo);
    expect(puts(chamadas, '/api/admin/configuracao')).toHaveLength(0);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar: usar claude' }));
    await waitFor(() =>
      expect(puts(chamadas, '/api/admin/configuracao')).toEqual([{ chave: 'provedor', valor: 'claude', confirmar: true }]),
    );
  });

  it('409 da API (provedor pago sem confirmar) vira pedido de confirmação explícita', async () => {
    let n = 0;
    const { chamadas } = fetchFalso({
      ...BASE,
      'PUT /api/admin/configuracao': () => {
        n += 1;
        return n === 1 ? responder(registros.configPut409)() : responder(registros.configPut)();
      },
    });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    // 'gravado' não gasta pelo que o site sabe: vai direto — e a API responde 409.
    await usuario.selectOptions(await screen.findByLabelText('Provedor vigente'), 'gravado');
    const grupo = await screen.findByRole('group', { name: 'Confirmar troca de provedor' });
    expect(grupo.textContent).toContain('reenvie com confirmar=true');
    await usuario.click(within(grupo).getByRole('button', { name: /Confirmar/ }));
    await waitFor(() =>
      expect(puts(chamadas, '/api/admin/configuracao')).toEqual([
        { chave: 'provedor', valor: 'gravado' },
        { chave: 'provedor', valor: 'gravado', confirmar: true },
      ]),
    );
  });

  it('trocar para gravado (sem custo) grava direto, sem confirmação', async () => {
    const { chamadas } = fetchFalso({ ...BASE, 'PUT /api/admin/configuracao': responder(registros.configPut) });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    await usuario.selectOptions(await screen.findByLabelText('Provedor vigente'), 'gravado');
    await waitFor(() => expect(puts(chamadas, '/api/admin/configuracao')).toEqual([{ chave: 'provedor', valor: 'gravado' }]));
    expect(screen.queryByRole('group', { name: 'Confirmar troca de provedor' })).toBeNull();
  });

  it('um botão só, "Salvar alterações", grava o que mudou com o tipo certo', async () => {
    const { chamadas } = fetchFalso({ ...BASE, 'PUT /api/admin/configuracao': responder(registros.configPut) });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    const campo = await screen.findByLabelText('valor de lote');
    expect(screen.queryByRole('button', { name: 'Salvar' })).toBeNull();               // nada de um botão por linha
    const salvar = screen.getByRole('button', { name: /Salvar alterações/ });
    expect(salvar).toBeDisabled();                                                    // nada mudou ainda
    await usuario.clear(campo);
    await usuario.type(campo, '8');
    const outro = screen.getByLabelText('valor de max_extracoes');
    await usuario.clear(outro);
    await usuario.type(outro, '3');
    expect(salvar).toHaveTextContent('(2)');
    await usuario.click(salvar);
    await waitFor(() => expect(puts(chamadas, '/api/admin/configuracao')).toHaveLength(2));
    expect(puts(chamadas, '/api/admin/configuracao')).toEqual(
      expect.arrayContaining([{ chave: 'lote', valor: 8 }, { chave: 'max_extracoes', valor: 3 }]));
  });

  it('teto nulo mostra "sem teto" com o aviso de custo da API', async () => {
    fetchFalso(BASE);
    renderizar(<Admin />, { me: ADMIN });
    expect(await screen.findByText(/sem teto/)).toBeInTheDocument();
    expect(screen.getAllByText(new RegExp(orcamento.aviso_custo.replace(/[()$~]/g, '.'))).length).toBeGreaterThan(0);
  });

  it('termo: ativar/desativar vai em PUT /api/admin/termos {termo, ativo}', async () => {
    const { chamadas } = fetchFalso({ ...BASE, 'PUT /api/admin/termos': responder(registros.termosPut) });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    const t = termos.itens[0];
    await usuario.click(await screen.findByLabelText(`termo ${t.termo} ativo`));
    await waitFor(() => expect(puts(chamadas, '/api/admin/termos')).toEqual([{ termo: t.termo, ativo: !t.ativo }]));
  });

  it('usuário: trocar o papel manda só {email, papel}', async () => {
    const { chamadas } = fetchFalso({ ...BASE, 'PUT /api/admin/usuarios': responder(registros.usuariosPut) });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    await usuario.selectOptions(await screen.findByLabelText('papel de leitor@teste.br'), 'operador');
    await waitFor(() => expect(puts(chamadas, '/api/admin/usuarios')).toEqual([{ email: 'leitor@teste.br', papel: 'operador' }]));
  });

  it('usuário: Bloquear manda {email, ativo:false}; o bloqueado aparece como tal e tem Desbloquear', async () => {
    const { chamadas } = fetchFalso({ ...BASE, 'PUT /api/admin/usuarios': responder(registros.usuariosPut) });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    await usuario.click(await screen.findByRole('button', { name: 'Bloquear leitor@teste.br' }));
    const bloqueado = usuarios.itens.find((u) => !u.ativo)!;
    expect(screen.getByText(bloqueado.email).closest('tr')?.textContent).toContain('bloqueado');
    await usuario.click(screen.getByRole('button', { name: `Desbloquear ${bloqueado.email}` }));
    await waitFor(() =>
      expect(puts(chamadas, '/api/admin/usuarios')).toEqual([
        { email: 'leitor@teste.br', ativo: false },
        { email: bloqueado.email, ativo: true },
      ]),
    );
  });

  it('usuário: Remover pede confirmação e só então manda DELETE {email}', async () => {
    const { chamadas } = fetchFalso({ ...BASE, 'DELETE /api/admin/usuarios': () => new Response(null, { status: 204 }) });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    await usuario.click(await screen.findByRole('button', { name: 'Remover leitor@teste.br' }));
    let pergunta = screen.getByRole('group', { name: 'Confirmar remoção de leitor@teste.br' });
    expect(pergunta.textContent).toContain('entrar com o Google de novo');
    await usuario.click(within(pergunta).getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByRole('group', { name: /Confirmar remoção/ })).toBeNull();
    expect(puts(chamadas, '/api/admin/usuarios', 'DELETE')).toHaveLength(0);
    await usuario.click(screen.getByRole('button', { name: 'Remover leitor@teste.br' }));
    pergunta = screen.getByRole('group', { name: 'Confirmar remoção de leitor@teste.br' });
    await usuario.click(within(pergunta).getByRole('button', { name: 'Remover' }));
    await waitFor(() => expect(puts(chamadas, '/api/admin/usuarios', 'DELETE')).toEqual([{ email: 'leitor@teste.br' }]));
    await waitFor(() => expect(screen.queryByRole('group', { name: /Confirmar remoção/ })).toBeNull());
  });

  it('o admin normal vê os usuários, mas só o admin supremo dá e tira acesso', async () => {
    fetchFalso(BASE);
    renderizar(<Admin />, { me: ADMIN_NORMAL });
    const seletor = await screen.findByLabelText('papel de leitor@teste.br');
    expect(seletor).toBeDisabled();
    expect(seletor).toHaveAttribute('title', 'Somente o administrador supremo concede e revoga acessos.');
    expect(screen.getByRole('button', { name: 'Adicionar usuário' })).toBeDisabled();
    for (const acao of ['Bloquear', 'Remover']) {
      const botao = screen.getByRole('button', { name: `${acao} leitor@teste.br` });
      expect(botao).toBeDisabled();
      expect(botao).toHaveAttribute('title', 'Somente o administrador supremo concede e revoga acessos.');
    }
    // o supremo aparece como tal, sem lista nem botão para mudar — para ninguém, nem para ele
    const dono = usuarios.itens.find((u) => u.supremo)!;
    expect(screen.queryByLabelText(`papel de ${dono.email}`)).toBeNull();
    expect(screen.queryByRole('button', { name: `Bloquear ${dono.email}` })).toBeNull();
    expect(screen.queryByRole('button', { name: `Remover ${dono.email}` })).toBeNull();
    expect(screen.getAllByText('Admin Supremo').length).toBeGreaterThan(0);
    // "usuário" é o nome do leitor na tela
    expect(within(seletor as HTMLElement).getByRole('option', { name: 'Usuário' })).toHaveValue('leitor');
  });

  it('reserva de demo manda {controles, dias} e mostra o que a API reservou', async () => {
    const { chamadas } = fetchFalso({ ...BASE, 'POST /api/admin/reservar-demo': responder(registros.reserva) });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN });
    const pedido = registros.reserva.corpo as { reservadas: string[]; nao_encontradas: string[] };
    await usuario.type(await screen.findByLabelText(/Controles \(um por linha\)/), [...pedido.reservadas, ...pedido.nao_encontradas].join('\n'));
    await usuario.click(screen.getByRole('button', { name: /Reservar/ }));
    await waitFor(() => {
      const post = chamadas.find((c) => c.init?.method === 'POST');
      expect(post?.url.pathname).toBe('/api/admin/reservar-demo');
      expect(JSON.parse(String(post?.init?.body))).toEqual({
        controles: [...pedido.reservadas, ...pedido.nao_encontradas],
        dias: 7,
      });
    });
    expect(await screen.findByText(new RegExp(`não encontradas: ${pedido.nao_encontradas[0]}`))).toBeInTheDocument();
  });

  it('leitor não edita: controles desabilitados com o motivo', async () => {
    fetchFalso(BASE);
    renderizar(<Admin />, { me: { email: 'l@x', papel: 'leitor', nome: null } });
    const seletor = await screen.findByLabelText('Provedor vigente');
    expect(seletor).toBeDisabled();
    expect(seletor).toHaveAttribute('title', 'Ação restrita a administradores.');
    const verificar = screen.getByRole('button', { name: 'Verificar agora' });
    expect(verificar).toBeDisabled();
    expect(verificar.getAttribute('title')).toMatch(/admin/);   // os botões da API são do admin (26/09)
  });

  it('Verificar agora: POST 202 e acompanha {execucao:{status}, buscas} até terminar', async () => {
    let consultas = 0;
    const id = (registros.acaoVerificar.corpo as { execucao_id: number }).execucao_id;
    const { chamadas } = fetchFalso({
      ...BASE,
      'POST /api/acoes/verificar': responder(registros.acaoVerificar),
      [`/api/execucoes/${id}`]: () => {
        consultas += 1;
        return (consultas < 2 ? responder(registros.execucaoEmCurso) : responder(registros.execucaoConcluida))();
      },
    });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN_NORMAL });
    await usuario.click(await screen.findByRole('button', { name: 'Verificar agora' }));
    await waitFor(() => expect(chamadas.some((c) => c.url.pathname === '/api/acoes/verificar')).toBe(true));
    expect(await screen.findByText('Em andamento…')).toBeInTheDocument();
    expect(await screen.findByText('Concluída (ok)', {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByText(/folha de pagamento: /)).toBeNull();   // as buscas por termo ficam em Execuções (27/09)
  });
  it('Verificar agora terminado: resume o que o W01 viu e diz que o seco não gravou nada', async () => {
    // O W01 seco grava as contagens em `contadores` (novas, conhecidas, retificadas...), e a tela só
    // mostrava as buscas: quem clicou não via quantas novas havia nem que elas ainda não entraram.
    const id = (registros.acaoVerificar.corpo as { execucao_id: number }).execucao_id;
    const concluida = copia(execucaoConcluida);
    concluida.execucao.contadores = {
      seco: true, vistas: 877, novas: 3, conhecidas: 869, retificadas: 1, fora_escopo: 2, fora_recorte: 2,
    };
    fetchFalso({
      ...BASE,
      'POST /api/acoes/verificar': responder(registros.acaoVerificar),
      [`/api/execucoes/${id}`]: concluida,
    });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN_NORMAL });
    await usuario.click(await screen.findByRole('button', { name: 'Verificar agora' }));
    const resumo = await screen.findByText(/3 novas · 869 conhecidas · 1 retificada/);
    expect(resumo.textContent).toContain('2 fora do escopo · 2 fora do recorte · custo R$ 0,00');
    expect(screen.getByText(/Verificação sem registro: nenhuma licitação foi gravada/)).toBeInTheDocument();
  });
  it('a mensagem da verificação é o cabeçalho e só três linhas: status, contagens e o aviso do seco', async () => {
    const contadores = {
      seco: true, vistas: 842, novas: 5, conhecidas: 831, retificadas: 5, fora_escopo: 1, fora_recorte: 0,
      novas_lista: [{ controle: '12345678000199-1-000001/2026', municipio: 'Cidade A', uf: 'SP', modalidade: null,
        objeto: null, fim_prazo: null, link: 'https://pncp.gov.br/app/editais/12345678000199/2026/1' }],
    };
    fetchFalso({
      ...BASE,
      ...ultimaVerificacao({ id: 5026, n8n_execution_id: '14665', status: 'ok', duracao_s: 99, contadores }),
    });
    renderizar(<Admin />, { me: ADMIN });
    const bloco = await screen.findByRole('group', { name: 'Última verificação' });
    await within(bloco).findByText('Concluída (ok)');
    expect(within(bloco).getByRole('heading').textContent).toBe('Execução 5026 · n8n nº 14665');
    expect([...bloco.querySelectorAll('.progresso > div')].map((l) => l.textContent)).toEqual([
      'Concluída (ok)',
      '5 novas · 831 conhecidas · 5 retificadas · 1 fora do escopo · 0 fora do recorte · custo R$ 0,00',
      'Verificação sem registro: nenhuma licitação foi gravada. As novas entram na próxima descoberta automática (de segunda a sexta, às 6h).',
    ]);
    // a lista das novas, as buscas por termo e os links ficam na página de Execuções
    expect(within(bloco).queryByRole('list')).toBeNull();
    expect(within(bloco).queryByRole('link')).toBeNull();
  });

  it.each([
    [5, '5 licitações novas'],
    [1, '1 licitação nova'],
    [0, 'sem licitações novas'],
  ])('ao abrir, mostra a última verificação sem clicar — sair da página não perde: %i → %s', async (novas, texto) => {
    const { chamadas } = fetchFalso({
      ...BASE,
      ...ultimaVerificacao({ status: 'ok', duracao_s: 99, contadores: { seco: true, vistas: 900, novas } }),
    });
    renderizar(<Admin />, { me: ADMIN });
    // 26/09 08:40 UTC = 05:40 em Brasília
    const aviso = await screen.findByText(new RegExp(`^Rodou (hoje|em 26/09) às 05:40 · ${texto}$`));
    expect(aviso).toHaveAttribute('role', 'status');
    expect(screen.getByText(/De segunda a sexta, às 6h, o FOPA verifica automaticamente/)).toBeInTheDocument();
    expect(screen.getByText(/duração aproximada: ~2 min/)).toBeInTheDocument();         // a mediana das rodadas do botão: 99 s
    expect(screen.getByText(/sem custo/)).toBeInTheDocument();
    expect(chamadas.some((c) => c.init?.method === 'POST')).toBe(false);
  });

  it('a última verificação ainda rodando: "Rodando…" com a hora em que começou, e o botão espera ela acabar', async () => {
    const agora = new Date(Date.now() - 60_000).toISOString();
    fetchFalso({ ...BASE, ...ultimaVerificacao({ status: 'em_curso', iniciado_em: agora, duracao_s: null, contadores: null }) });
    renderizar(<Admin />, { me: ADMIN });
    expect(
      await screen.findByText(/^Rodando… começou (hoje|em \d{2}\/\d{2}) às \d{2}:\d{2} · costuma levar ~1 min$/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verificar agora' })).toBeDisabled();
  });

  it('a última ficou "em curso" há horas (morreu no meio): avisa e não trava o botão para sempre', async () => {
    fetchFalso({ ...BASE, ...ultimaVerificacao({ status: 'em_curso', duracao_s: null, contadores: null }) });
    renderizar(<Admin />, { me: ADMIN });
    expect(await screen.findByText(/^A última verificação começou .* às 05:40 e não foi concluída/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verificar agora' })).toBeEnabled();
  });
  it('Processar selecionadas: normaliza slug, tira repetida, lista inválida, confirma com provedor e custo, manda o lote', async () => {
    // Plano §8 (admin): "Processar selecionadas" — com a esteira desligada (D12), é por aqui que um lote vai ao W11.
    const { chamadas } = fetchFalso({
      ...BASE,
      'POST /api/acoes/processar': responder({ metodo: 'POST', caminho: '/api/acoes/processar', status: 202, corpo: { aceitos: ['12345678000101-1-000001/2026'], recusados: [] } }),
    });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN_NORMAL });
    const campo = await screen.findByLabelText(/Controles a processar/);
    await usuario.type(campo, '12345678000101-1-000001-2026, 12345678000101-1-000001/2026 lixo');
    expect(screen.getByText(/Fora do formato: lixo/)).toBeInTheDocument();
    await usuario.click(screen.getByRole('button', { name: 'Processar 1' }));
    const conf = await screen.findByRole('group', { name: 'Confirmar processamento em lote' });
    expect(conf.textContent).toContain('simulado');
    expect(conf.textContent).toContain('R$ 0,00 (sem serviço pago)');
    await usuario.click(within(conf).getByRole('button', { name: 'Confirmar e processar' }));
    expect(await screen.findByText(/1 aceita/)).toBeInTheDocument();
    const posts = chamadas.filter((c) => c.init?.method === 'POST' && c.url.pathname === '/api/acoes/processar');
    expect(posts.map((c) => JSON.parse(String(c.init?.body)))).toEqual([
      { controles: ['12345678000101-1-000001/2026'], forcar: false },
    ]);
  });

  it('Processar selecionadas: recusadas aparecem com o motivo; forçar vai no pedido', async () => {
    const { chamadas } = fetchFalso({
      ...BASE,
      'POST /api/acoes/processar': responder({
        metodo: 'POST',
        caminho: '/api/acoes/processar',
        status: 202,
        corpo: { aceitos: [], recusados: [{ controle: '12345678000101-1-000002/2026', motivo: 'fora do escopo' }] },
      }),
    });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN_NORMAL });
    await usuario.type(await screen.findByLabelText(/Controles a processar/), '12345678000101-1-000002/2026');
    await usuario.click(screen.getByLabelText(/Forçar/));
    await usuario.click(screen.getByRole('button', { name: 'Processar 1' }));
    const conf = await screen.findByRole('group', { name: 'Confirmar processamento em lote' });
    await usuario.click(within(conf).getByRole('button', { name: 'Confirmar e processar' }));
    expect(await screen.findByText(/12345678000101-1-000002\/2026: fora do escopo/)).toBeInTheDocument();
    const corpo = JSON.parse(String(chamadas.find((c) => c.init?.method === 'POST')?.init?.body));
    expect(corpo.forcar).toBe(true);
  });

  it('Processar selecionadas: mais de 20 não vai (o W11 recusa) e leitor não processa', async () => {
    fetchFalso(BASE);
    const usuario = userEvent.setup();
    const { unmount } = renderizar(<Admin />, { me: ADMIN_NORMAL });
    const muitos = Array.from({ length: 21 }, (_, i) => `12345678000101-1-${String(i + 1).padStart(6, '0')}/2026`).join(' ');
    await usuario.type(await screen.findByLabelText(/Controles a processar/), muitos);
    expect(screen.getByRole('button', { name: 'Processar 21' })).toBeDisabled();
    expect(screen.getByText(/no máximo 20 por pedido/)).toBeInTheDocument();
    unmount();
    renderizar(<Admin />, { me: { email: 'l@x', papel: 'leitor', nome: null } });
    expect(await screen.findByLabelText(/Controles a processar/)).toBeDisabled();
  });
  it('lerRespostas: o respostas.json do agente ou a lista pura; JSON ruim, contagem e ids faltando dizem o porquê', () => {
    expect(lerRespostas('')).toEqual({ respostas: null, erro: null });
    expect(lerRespostas(JSON.stringify({ respostas: DEZESSETE })).respostas).toHaveLength(17);
    expect(lerRespostas(JSON.stringify(DEZESSETE)).respostas).toHaveLength(17);
    expect(lerRespostas('{').erro).toMatch(/não é um JSON válido/);
    expect(lerRespostas('{"x": 1}').erro).toMatch(/respostas.json do agente/);
    expect(lerRespostas(JSON.stringify(DEZESSETE.slice(0, 16))).erro).toBe('São esperadas 17 respostas (Q1 a Q17); foram recebidas 16.');
    const semQ17 = DEZESSETE.map((r) => (r.id === 'Q17' ? { ...r, id: 'Q18' } : r));
    expect(lerRespostas(JSON.stringify(semQ17)).erro).toBe('Respostas ausentes: Q17.');
    expect(lerRespostas(JSON.stringify([...DEZESSETE.slice(0, 16), 'Q17'])).erro).toBe('Cada resposta deve ser um objeto.');
  });

  it('Importar respostas do agente: slug vira controle, o respostas.json colado vai inteiro e o modo volta na tela', async () => {
    // Plano §8 (admin) e ADR-014: o caminho oficial de custo zero — W11 → worker /importar-respostas → W24.
    const { chamadas } = fetchFalso({
      ...BASE,
      [`POST ${IMPORTAR}`]: responder({
        metodo: 'POST',
        caminho: IMPORTAR,
        status: 202,
        corpo: { aceito: true, controle: '12345678000101-1-000001/2026', modo: 'publicar', execucao_id: 501, verificacao_id: null },
      }),
    });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN_NORMAL });
    await usuario.type(await screen.findByLabelText(/Controle \(ou o slug do site\)/), '12345678000101-1-000001-2026');
    const botao = screen.getByRole('button', { name: 'Importar e publicar' });
    expect(botao).toBeDisabled();
    await usuario.click(screen.getByLabelText(/respostas\.json do agente/));
    await usuario.paste(JSON.stringify({ respostas: DEZESSETE }));
    await usuario.type(screen.getByLabelText(/Modelo do agente/), 'claude-opus-5-5');
    expect(botao).toBeEnabled();
    await usuario.click(botao);
    expect(await screen.findByText(/execução 501/)).toBeInTheDocument();
    expect(screen.getByText(/fará a verificação e a publicação/)).toBeInTheDocument();
    const posts = chamadas.filter((c) => c.init?.method === 'POST' && c.url.pathname === IMPORTAR);
    expect(posts.map((c) => JSON.parse(String(c.init?.body)))).toEqual([
      { controle: '12345678000101-1-000001/2026', respostas: DEZESSETE, modelo: 'claude-opus-5-5' },
    ]);
  });

  it('Importar respostas do agente: o que o site já sabe recusar não sai; a recusa do W11 aparece com o motivo', async () => {
    const detalhe = 'estado lendo: importar vale para preparada (primeira extração) ou publicada (extração nova)';
    const { chamadas } = fetchFalso({
      ...BASE,
      [`POST ${IMPORTAR}`]: responder({ metodo: 'POST', caminho: IMPORTAR, status: 409, corpo: { detail: detalhe, estado: 'lendo' } }),
    });
    const usuario = userEvent.setup();
    renderizar(<Admin />, { me: ADMIN_NORMAL });
    const controle = await screen.findByLabelText(/Controle \(ou o slug do site\)/);
    const json = screen.getByLabelText(/respostas\.json do agente/);
    const botao = screen.getByRole('button', { name: 'Importar e publicar' });
    await usuario.type(controle, '12345678000101-1-000001/2026 12345678000101-1-000002/2026');
    await usuario.click(json);
    await usuario.paste(JSON.stringify(DEZESSETE));
    expect(screen.getByText(/Uma licitação por vez/)).toBeInTheDocument();
    expect(botao).toBeDisabled();
    await usuario.clear(controle);
    await usuario.type(controle, '12345678000101-1-000001/2026');
    await usuario.clear(json);
    await usuario.click(json);
    await usuario.paste(JSON.stringify(DEZESSETE.slice(0, 16)));
    expect(screen.getByRole('alert').textContent).toBe('São esperadas 17 respostas (Q1 a Q17); foram recebidas 16.');
    expect(botao).toBeDisabled();
    await usuario.clear(json);
    await usuario.click(json);
    await usuario.paste(JSON.stringify(DEZESSETE));
    await usuario.click(botao);
    expect(await screen.findByText(detalhe)).toBeInTheDocument();
    expect(chamadas.filter((c) => c.init?.method === 'POST' && c.url.pathname === IMPORTAR)).toHaveLength(1);
  });

  it('Importar respostas do agente: leitor não importa', async () => {
    fetchFalso(BASE);
    renderizar(<Admin />, { me: { email: 'l@x', papel: 'leitor', nome: null } });
    expect(await screen.findByLabelText(/respostas\.json do agente/)).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Importar e publicar' })).toBeDisabled();
  });
});
