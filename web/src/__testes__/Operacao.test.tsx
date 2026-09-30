/**
 * Páginas de operação com o contrato real: /saude (inclusive o 503 que diz
 * QUEM caiu — a página tem de mostrar, não "não deu para carregar"), e os
 * campos novos opcionais dela; /execucoes (custo por modelo com legado);
 * /emails (link pelo slug que a API manda).
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Emails } from '../paginas/Emails';
import { Execucoes } from '../paginas/Execucoes';
import { Saude } from '../paginas/Saude';
import { copia, custo, emails, execucoes, registros, responder, saude } from '../__fixtures__/contrato';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

afterEach(() => vi.unstubAllGlobals());

describe('Saúde', () => {
  it('200: API, worker (tesseract) e Postgres ok', async () => {
    fetchFalso({ '/api/saude': saude });
    const { container } = renderizar(<Saude />);
    const tiles = (await screen.findByText(/Leitura e extração \(worker\) · tesseract/)).closest('.tiles') as HTMLElement;
    expect(within(tiles).getByText(/^Leitura e extração \(worker\) · /).closest('.tile')).toHaveClass('ok');
    expect(within(tiles).getByText(/Postgres/).closest('.tile')).toHaveClass('ok');
    expect(container.textContent).toContain(`Ambiente: ${saude.ambiente}`);
  });

  it('503 real (worker e n8n fora): mostra quem caiu e por quê, em vez de "não deu para carregar"', async () => {
    fetchFalso({ '/api/saude': responder(registros.saude503) });
    const { container } = renderizar(<Saude />);
    const corpo = registros.saude503.corpo as { worker: { erro: string }; n8n: { erro: string } };
    const worker = (await screen.findByText(`Leitura e extração (worker) · ${corpo.worker.erro}`)).closest('.tile')!;
    expect(worker).toHaveClass('al');
    expect(screen.getByText(`Processamento (n8n) · ${corpo.n8n.erro}`).closest('.tile')).toHaveClass('al');
    expect(container.textContent).not.toContain('Não foi possível carregar');
    expect(container.textContent).toContain('indisponível: worker');
    // o n8n não derruba: vem em `avisos`, com a frase do que isso muda
    expect(screen.getByText(/Processamento \(n8n\) indisponível: verificar, processar e reverificar ficam suspensos/)).toBeInTheDocument();
  });

  it('200 real: n8n, última coleta (CEGA) e último alerta {em, workflow, mensagem}', async () => {
    fetchFalso({ '/api/saude': saude });
    const { container } = renderizar(<Saude />);
    const n8n = (await screen.findByText(/Processamento \(n8n\) · HTTP 200/)).closest('.tile')!;
    expect(n8n).toHaveClass('ok');
    const alerta = saude.ultimo_alerta!;
    expect(container.textContent).toContain('Última coleta · incompleta');
    expect(container.textContent).toContain(`Último alerta · ${alerta.workflow} · ${alerta.mensagem}`);
    expect(container.querySelector('p.alerta')).toBeNull();
  });

  it('API anterior (sem n8n, coleta, alerta, avisos): só as três peças, nada inventado', async () => {
    const s = copia(saude);
    delete s.n8n;
    delete s.ultima_coleta;
    delete s.ultimo_alerta;
    delete s.avisos;
    fetchFalso({ '/api/saude': s });
    const { container } = renderizar(<Saude />);
    await screen.findByText(/Leitura e extração \(worker\) · tesseract/);
    expect(container.querySelectorAll('.tile')).toHaveLength(3);
  });

  it('corpo reduzido de produção sem sessão ({ok, caiu, avisos}) não quebra', async () => {
    fetchFalso({ '/api/saude': { ok: saude.ok, caiu: saude.caiu, avisos: saude.avisos } });
    const { container } = renderizar(<Saude />);
    await screen.findByText(/API/);
    expect(container.querySelectorAll('.tile')).toHaveLength(1);
  });
});

describe('Execuções', () => {
  it('lista real e custo por modelo com o legado dito como legado', async () => {
    fetchFalso({ '/api/execucoes': execucoes, '/api/custo': custo });
    const { container } = renderizar(<Execucoes />);
    await screen.findByText('R$ 4,83 (legado)');
    await waitFor(() => expect(container.querySelectorAll('tbody tr').length).toBeGreaterThanOrEqual(execucoes.itens.length));
    expect(container.textContent).toContain('R$ 4,83 (legado)');
    expect(container.textContent).toContain('coleta incompleta');
    expect(container.textContent).not.toContain('NaN');
  });
});

describe('Execuções (QA visual)', () => {
  it('rodada sem chamada registrada mostra "—" com o motivo, nunca "R$ 0,00"; a paga mostra o valor', async () => {
    fetchFalso({ '/api/execucoes': execucoes, '/api/custo': custo });
    const { container } = renderizar(<Execucoes />);
    await screen.findByText('R$ 4,83 (legado)');
    const lista = container.querySelector('table') as HTMLElement;
    expect(lista.textContent).not.toContain('R$ 0,00');
    const semChamada = execucoes.itens.filter((e) => !e.chamadas && !Number(e.custo_brl)).length;
    const tracos = Array.from(lista.querySelectorAll('td')).filter((td) => td.textContent === '—' && td.title);
    expect(tracos).toHaveLength(semChamada);
    expect(tracos[0].title).toMatch(/nenhuma chamada ao modelo registrada/);
    expect(lista.textContent).toContain('R$ 1,50');
  });

  it('as tabelas rolam no celular (.rolagem) e custo/duração/data não partem ao meio (.nw)', async () => {
    fetchFalso({ '/api/execucoes': execucoes, '/api/custo': custo });
    const { container } = renderizar(<Execucoes />);
    await screen.findByText('R$ 4,83 (legado)');
    const tabelas = Array.from(container.querySelectorAll('table'));
    expect(tabelas).toHaveLength(3);
    for (const t of tabelas) expect(t.parentElement).toHaveClass('rolagem');
    const primeira = tabelas[0].querySelector('tbody tr')!;
    expect(Array.from(primeira.querySelectorAll('td.nw'))).toHaveLength(3);
  });

  it('mais de uma página: mostra "página 1 de N" e a próxima pede ?page=2', async () => {
    const varias = { ...copia(execucoes), total: 120, paginas: 3 };
    const { chamadas } = fetchFalso({ '/api/execucoes': varias, '/api/custo': custo });
    renderizar(<Execucoes />);
    expect(await screen.findByText(/página 1 de 3 · 120 execuções/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '← Anterior' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Próxima →' }));
    await waitFor(() => expect(chamadas.some((c) => c.url.pathname === '/api/execucoes' && c.url.searchParams.get('page') === '2')).toBe(true));
  });

  it('uma página só: sem paginação', async () => {
    fetchFalso({ '/api/execucoes': execucoes, '/api/custo': custo });
    const { container } = renderizar(<Execucoes />);
    await screen.findByText('R$ 4,83 (legado)');
    expect(container.querySelector('nav.paginacao')).toBeNull();
  });

  it('custo sem nenhuma chamada: as duas tabelas dizem que não há registro, em vez de ficar só o cabeçalho', async () => {
    fetchFalso({ '/api/execucoes': execucoes, '/api/custo': { ...copia(custo), por_dia: [], por_modelo: [] } });
    renderizar(<Execucoes />);
    expect(await screen.findByText('Nenhuma chamada ao modelo registrada.')).toBeInTheDocument();
    expect(screen.getByText('Nenhuma execução de modelo registrada.')).toBeInTheDocument();
  });

  it('resultado: id não é contagem e status fora do normal aparece (disjuntor do W10, revertido do W30)', async () => {
    // O W10 grava {reivindicadas: 0, disjuntor: true, email_id: 261} com status 'disjuntor', e o W40
    // grava o email_id do alerta: a coluna mostrava "261 email_id" e o disjuntor sumia atrás dele.
    const base = execucoes.itens[0];
    const itens = [
      { ...base, id: 9001, workflow: 'W10', status: 'disjuntor', erro: null, cego: null,
        contadores: { liberados: 0, reivindicadas: 0, disjuntor: true, email_id: 261 } },
      { ...base, id: 9002, workflow: 'W40', status: 'ok', erro: null, cego: null,
        contadores: { p1: 20, email_id: 5, execucao_id: 77 } },
      { ...base, id: 9003, workflow: 'W30', status: 'revertido', erro: null, cego: null,
        contadores: { republicadas: 90 } },
    ];
    fetchFalso({ '/api/execucoes': { ...copia(execucoes), itens, total: 3, paginas: 1 }, '/api/custo': custo });
    const { container } = renderizar(<Execucoes />);
    await screen.findByText(/Proteção acionada \(disjuntor\)/);
    const lista = container.querySelector('table') as HTMLElement;
    expect(lista.textContent).not.toMatch(/email_id|execucao_id/);
    expect(lista.textContent).toContain('Proteção acionada (disjuntor): nenhuma licitação reivindicada');
    expect(lista.textContent).toContain('20 p1');
    expect(lista.textContent).toContain('revertido · 90 republicadas');
  });

  it('resultado: nome de contador com sublinhado sai com espaço ("2 voltam para a fila")', async () => {
    const base = execucoes.itens[0];
    const itens = [{ ...base, id: 9101, workflow: 'W50', status: 'parcial', erro: null, cego: null,
      contadores: { reservados: 2, voltam_para_a_fila: 2, falhou_definitivo: 1 } }];
    fetchFalso({ '/api/execucoes': { ...copia(execucoes), itens, total: 1, paginas: 1 }, '/api/custo': custo });
    const { container } = renderizar(<Execucoes />);
    await screen.findByText(/voltam para a fila/);
    const lista = container.querySelector('table') as HTMLElement;
    expect(lista.textContent).toContain('parcial · 2 reservados · 2 voltam para a fila · 1 falhou definitivo');
    expect(lista.textContent).not.toContain('_');
  });

  it('hoje com chamada sem preço: "hoje: R$ X + N sem preço"', async () => {
    fetchFalso({ '/api/execucoes': execucoes, '/api/custo': { ...copia(custo), hoje_brl: 0, hoje_sem_preco: 2 } });
    const { container } = renderizar(<Execucoes />);
    await screen.findByText('R$ 4,83 (legado)');
    expect(container.textContent).toContain('hoje: R$ 0,00 + 2 sem preço');
  });
});

describe('Saúde (QA visual)', () => {
  it('mensagem longa do último alerta: o tile mostra o começo e o title guarda tudo, com a data legível', async () => {
    const longa = `execução manual 89 morreu no nó Executar W23 Extrair (Invalid input for workflow_execucao_id: bigint chegou como texto) em 2026-09-24T07:14:00Z; lease devolvido à mão como o W90 faria`;
    fetchFalso({ '/api/saude': { ...copia(saude), ultimo_alerta: { em: saude.ultimo_alerta!.em, workflow: 'W20', mensagem: longa } } });
    renderizar(<Saude />);
    const tile = (await screen.findByText(/^Último alerta · W20 · /)).closest('.tile') as HTMLElement;
    const visivel = tile.querySelector('span')!.textContent!;
    expect(visivel.length).toBeLessThan(longa.length);
    expect(visivel.endsWith('…')).toBe(true);
    expect(tile.title).toContain('em 24/09/2026 04:14; lease devolvido');
    expect(tile.title).not.toContain('2026-09-24T');
  });

  it('valores do worker /health quebram dentro da célula (hash de 64 hex não empurra a página)', async () => {
    fetchFalso({ '/api/saude': saude });
    const { container } = renderizar(<Saude />);
    await screen.findByText(/Leitura e extração \(worker\) · tesseract/);
    const sha = await screen.findByText(saude.worker!.health!.tessdata_sha256 as string);
    expect(sha).toHaveClass('quebra');
    expect(container.querySelector('table')!.parentElement).toHaveClass('rolagem');
  });
});

describe('E-mails', () => {
  it('erro com instante ISO do n8n sai em dd/mm/aaaa hh:mm', async () => {
    const e = copia(emails);
    e.itens[0] = { ...e.itens[0], status: 'pendente', erro: 'tentativa 1/5 falhou; nova tentativa a partir de 2026-09-24T09:01:01Z' };
    fetchFalso({ '/api/emails': e });
    const { container } = renderizar(<Emails />);
    expect(await screen.findByText(/nova tentativa a partir de 24\/09\/2026 06:01/)).toBeInTheDocument();
    expect(container.textContent).not.toContain('2026-09-24T');
  });

  it('mostra para quem vai cada e-mail: a extração, para quem pediu; a licitação nova, para os admins', async () => {
    // db/038: o produto manda só dois e-mails; a API resolve o destinatário como o W50.
    fetchFalso({ '/api/emails': emails });
    renderizar(<Emails />);
    const extracao = emails.itens.find((e) => e.tipo === 'extracao')!;
    const nova = emails.itens.find((e) => e.tipo === 'licitacao_nova')!;
    const linha = (await screen.findByText(extracao.assunto)).closest('tr') as HTMLElement;
    expect(linha.textContent).toContain(extracao.para!);
    expect((screen.getByText(nova.assunto).closest('tr') as HTMLElement).textContent).toContain(nova.para!);
    expect(screen.getByRole('columnheader', { name: 'Para' })).toBeInTheDocument();
  });

  it('link para a licitação pelo slug da API e falha em vermelho', async () => {
    fetchFalso({ '/api/emails': emails });
    const { container } = renderizar(<Emails />);
    const comLic = emails.itens.find((e) => e.slug)!;
    expect(await screen.findByRole('link', { name: comLic.controle! })).toHaveAttribute('href', `/licitacao/${comLic.slug}`);
    expect(container.querySelector('td.falhou')).not.toBeNull();
  });
});
