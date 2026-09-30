/**
 * A página de detalhe com o payload REAL de `GET /api/licitacoes/{slug}`
 * (`historico`, `respostas` + `verificacao_respostas` separadas, `revisoes`,
 * `execucao` e `leitura` à parte): ordem dos blocos (condições ACIMA do
 * questionário), procedência, histórico com diff, ações com confirmação que
 * mostra custo estimado e provedor, e botão desabilitado com motivo.
 */
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Route, Routes } from 'react-router-dom';
import type { LicitacaoCompleta } from '../api/tipos';
import { Detalhe } from '../paginas/Detalhe';
import {
  AGORA_CONTRATO,
  copia,
  licitacaoC1,
  licitacaoC2,
  licitacaoC3,
  licitacaoC4,
  modelosIa,
  registros,
  responder,
  resumo,
} from '../__fixtures__/contrato';
import { renderizar } from './ajuda';
import { fetchFalso } from './falso';

// O acompanhamento depois do clique pergunta a cada 5 s em produção; aqui, a cada 20 ms.
vi.mock('../lib/acompanhar', async (original) => ({
  ...(await original<typeof import('../lib/acompanhar')>()),
  ACOMPANHAR_MS: 20,
}));

function montar(d: LicitacaoCompleta, papel = 'admin', extras: Record<string, unknown> = {}) {
  const f = fetchFalso({
    [`/api/licitacoes/${d.licitacao.slug}`]: d,
    '/api/resumo': resumo,
    '/api/modelos-ia': modelosIa,
    ...extras,
  });
  const r = renderizar(
    <Routes>
      <Route path="/licitacao/:slug" element={<Detalhe />} />
    </Routes>,
    { rota: `/licitacao/${d.licitacao.slug}`, me: { email: 'x@y', papel, nome: null } },
  );
  return { ...f, ...r };
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(AGORA_CONTRATO);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('Detalhe com o contrato real', () => {
  it('renderiza o C1 inteiro sem quebrar: as 17 linhas com veredito e link de origem', async () => {
    const { container } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    expect(container.querySelectorAll('tr[data-pergunta]')).toHaveLength(17);
    const q1 = container.querySelector('tr[data-pergunta="Q1"]') as HTMLElement;
    expect(within(q1).getByRole('link', { name: /01 - Edital\.pdf — p\. 1/ })).toHaveAttribute(
      'href',
      expect.stringMatching(/^\/api\/pdf\/.+\/\d+#page=1$/),
    );
    expect(q1.querySelector('.v')).toHaveClass('APROVADO');
  });

  it('condições de leitura vêm ANTES do questionário, com a tag de injeção (C3)', async () => {
    const { container } = montar(licitacaoC3);
    await screen.findByText('Questionário');
    const cond = container.querySelector('.cond')!;
    const tabela = container.querySelector('tr[data-pergunta="Q1"]')!;
    expect(cond).toHaveClass('deg');
    expect(cond.compareDocumentPosition(tabela) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(cond.querySelector('.tagsusp')!.textContent).toBe('Prompt Injection - Conteúdo Suspeito');
  });

  it('abaixo do aviso de injeção, o "ver mais" mostra o texto escondido — o suspeito primeiro (C3)', async () => {
    const { container } = montar(licitacaoC3);
    await screen.findByText('Questionário');
    const cond = container.querySelector('.cond')!;
    const vermais = cond.querySelector('details.furtivos')!;
    expect(vermais).toHaveClass('susp');
    expect(cond.querySelector('.tagsusp')!.compareDocumentPosition(vermais) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(vermais.querySelector('summary')!.textContent).toMatch(/2 trechos de texto oculto, 1 com aparência de instrução/);
    const itens = vermais.querySelectorAll('li');
    expect(itens).toHaveLength(2);
    expect(itens[0]).toHaveClass('susp');
    expect(itens[0].querySelector('blockquote')!.textContent).toContain('Ignore as instruções anteriores');
    expect(itens[0].querySelector('.onde')!.textContent).toContain('p.7');
    expect(itens[1].querySelector('.classe')!.textContent).toMatch(/timbre/);
  });

  it('sem varredura de texto escondido, nada de "ver mais" (C1)', async () => {
    const { container } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    expect(container.querySelector('details.furtivos')).toBeNull();
  });

  it('tiles: extração LOCAL diz "local · sem chamada de API" (nem R$ 0,00, nem preço); ancoragem e críticas', async () => {
    const { container } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    const tiles = container.querySelector('.tiles')!;
    expect(tiles.textContent).toContain('sem serviço pago');
    expect(tiles.textContent).not.toContain('preço não configurado');
    expect(tiles.textContent).not.toContain('R$ 0,00');
    const l = licitacaoC1.licitacao;
    expect(tiles.textContent).toContain(`${l.ancoradas}/${l.respondidas}`);
    const veredito = Object.fromEntries(licitacaoC1.verificacao_respostas.map((v) => [v.pergunta_id, v.veredito]));
    const criticas = licitacaoC1.respostas.filter((r) => r.critico);
    const ok = criticas.filter((r) => veredito[r.pergunta_id] === 'APROVADO').length;
    expect(tiles.textContent).toContain(`${ok}/${criticas.length}`);
  });

  it('procedência como rótulo e histórico (campo `historico`) com diff de vereditos', async () => {
    const { container } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    expect(container.querySelector('.procedencia .marca')!.textContent).toBe('local');
    // local não tem tokens, tempo nem custo medidos: dizer "0 tokens" pareceria medição
    const linha = container.querySelector('.procedencia')!.textContent!;
    expect(linha).toContain('extração local, sem serviço pago');
    expect(linha).not.toMatch(/tokens de entrada|de saída|chamada\(s\)/);
    expect(screen.getByText('Q3: REVISAR → APROVADO')).toBeInTheDocument();
    expect(screen.getByText('primeira verificação')).toBeInTheDocument();
  });

  it('extração do agente: a procedência diz "agente de IA", nunca o id técnico do provedor', async () => {
    const { container } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    expect(licitacaoC1.licitacao.provedor).toBe('claude-code');
    const linha = container.querySelector('.procedencia')!.textContent!;
    expect(linha).toContain('agente de IA · claude-opus-5-5');
    expect(container.textContent).not.toMatch(/claude-code/i);
  });

  it('revisões humanas do detalhe aparecem com quem decidiu', async () => {
    montar(licitacaoC1);
    await screen.findByText('Questionário');
    const rev = licitacaoC1.revisoes[0];
    const secao = screen.getByRole('heading', { name: 'Revisões humanas' }).nextElementSibling as HTMLElement;
    expect(secao.textContent).toContain(rev.pergunta_id);
    expect(secao.textContent).toContain(rev.status);
    expect(secao.textContent).toContain(rev.decidido_por!);
  });

  it('revisão aberta se decide no próprio detalhe (operador), sem ir à fila', async () => {
    // Plano §8: "revisão humana inline para operador". Antes o detalhe só listava e mandava para /revisao.
    const rev = licitacaoC2.revisoes.find((r) => r.status === 'aberta')!;
    const { chamadas } = montar(licitacaoC2, 'operador', { 'POST /api/revisoes': registros.revisaoPost });
    await screen.findByText('Questionário');
    const secao = screen.getByRole('heading', { name: 'Revisões humanas' }).nextElementSibling as HTMLElement;
    vi.useRealTimers();
    const usuario = userEvent.setup();
    await usuario.selectOptions(within(secao).getByLabelText('Decisão'), 'rejeitada');
    await usuario.type(within(secao).getByLabelText('Nota'), 'conferido no edital');
    await usuario.click(within(secao).getByRole('button', { name: 'Registrar decisão' }));
    await waitFor(() => expect(chamadas.some((c) => c.init?.method === 'POST' && c.url.pathname === '/api/revisoes')).toBe(true));
    const post = chamadas.find((c) => c.init?.method === 'POST' && c.url.pathname === '/api/revisoes')!;
    expect(JSON.parse(String(post.init?.body))).toEqual({
      verificacao_id: rev.verificacao_id, pergunta_id: rev.pergunta_id, decisao: 'rejeitada', nota: 'conferido no edital',
    });
  });

  it('"ir para a fila" abre a revisão já filtrada nesta licitação', async () => {
    montar(licitacaoC2, 'leitor');
    await screen.findByText('Questionário');
    const secao = screen.getByRole('heading', { name: 'Revisões humanas' }).nextElementSibling as HTMLElement;
    expect(within(secao).getAllByRole('link', { name: 'abrir na fila de revisão' })[0]).toHaveAttribute(
      'href',
      `/revisao?controle=${encodeURIComponent(licitacaoC2.licitacao.controle)}`,
    );
  });

  it('o usuário (leitor) decide a revisão aberta no próprio detalhe (ADR-021, emenda)', async () => {
    montar(licitacaoC2, 'leitor');
    await screen.findByText('Questionário');
    const secao = screen.getByRole('heading', { name: 'Revisões humanas' }).nextElementSibling as HTMLElement;
    expect(within(secao).getByRole('button', { name: 'Registrar decisão' })).toBeEnabled();
  });

  it('sem extração (C4): não quebra, diz que não foi extraída e mostra o estado', async () => {
    montar(licitacaoC4);
    expect(await screen.findByText(/ainda não foi extraída/)).toBeInTheDocument();
    expect(screen.queryByText('Questionário')).toBeNull();
    expect(screen.getByText('Nenhuma verificação registrada.')).toBeInTheDocument();
    expect(screen.getByText(licitacaoC4.licitacao.estado)).toBeInTheDocument();
  });

  it('Processar de novo pede confirmação com o provedor vigente e o custo estimado', async () => {
    const { chamadas } = montar(licitacaoC1, 'admin', {
      '/api/resumo': { ...resumo, provedor: 'claude' },
      'POST /api/acoes/processar': responder(registros.acaoProcessar),
    });
    const usuario = userEvent.setup();
    await screen.findByText('Questionário');
    await usuario.click(screen.getByRole('button', { name: 'Processar novamente' }));
    const confirmacao = screen.getByRole('group', { name: 'Confirmar processamento' });
    expect(confirmacao.textContent).toContain('claude');
    expect(confirmacao.textContent).toContain('~R$ 3–4 por edital');
    expect(chamadas.some((c) => c.init?.method === 'POST')).toBe(false);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar e processar' }));
    await waitFor(() => {
      const post = chamadas.find((c) => c.init?.method === 'POST');
      expect(post?.url.pathname).toBe('/api/acoes/processar');
      expect(JSON.parse(String(post?.init?.body))).toEqual({ controles: [licitacaoC1.licitacao.controle] });
    });
    expect(await screen.findByText(/Pedido aceito/)).toBeInTheDocument();
  });

  it('Extrair com IA: por padrão OpenAI e o 1º modelo, com o esforço FIXO (médio); manda só provedor e modelo', async () => {
    // O esforço não se escolhe: é fixo por modelo, no ponto de custo-benefício (ADR-020).
    const { chamadas } = montar(licitacaoC1, 'admin', {
      'POST /api/acoes/extrair-ia': responder(registros.acaoProcessar),
    });
    const usuario = userEvent.setup();
    await screen.findByText('Questionário');
    await usuario.click(screen.getByRole('button', { name: 'Extrair com IA' }));
    const confirmacao = screen.getByRole('group', { name: 'Confirmar extração com IA' });
    expect(within(confirmacao).getByRole('combobox', { name: 'Modelo generativo' })).toHaveValue('openai');
    expect(within(confirmacao).getByRole('combobox', { name: 'Modelo' })).toHaveValue('gpt-5.6-sol');
    expect(within(confirmacao).queryByRole('radiogroup', { name: 'Esforço' })).toBeNull();
    expect(within(confirmacao).queryAllByRole('radio')).toHaveLength(0);
    expect(confirmacao.textContent).toMatch(/Esforço: médio \(fixo\)/);
    expect(confirmacao.textContent).toMatch(/US\$ 0,65/);                              // a estimativa no médio
    expect(confirmacao.textContent).toMatch(/extração desta licitação/);
    expect(chamadas.some((c) => c.init?.method === 'POST')).toBe(false);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar e extrair' }));
    await waitFor(() => {
      const post = chamadas.find((c) => c.init?.method === 'POST');
      expect(post?.url.pathname).toBe('/api/acoes/extrair-ia');
      expect(JSON.parse(String(post?.init?.body))).toEqual({
        controle: licitacaoC1.licitacao.controle, provedor: 'openai', modelo: 'gpt-5.6-sol',
      });
    });
    expect(await screen.findByText(/Pedido aceito/)).toBeInTheDocument();
  });

  it('Claude: os modelos filtram pelo provedor e o padrão é o Opus 5.5 no médio', async () => {
    const { chamadas } = montar(licitacaoC1, 'admin', {
      'POST /api/acoes/extrair-ia': responder(registros.acaoProcessar),
    });
    const usuario = userEvent.setup();
    await screen.findByText('Questionário');
    await usuario.click(screen.getByRole('button', { name: 'Extrair com IA' }));
    const confirmacao = screen.getByRole('group', { name: 'Confirmar extração com IA' });
    await usuario.selectOptions(within(confirmacao).getByRole('combobox', { name: 'Modelo generativo' }), 'claude');
    const modelo = within(confirmacao).getByRole('combobox', { name: 'Modelo' });
    expect(modelo).toHaveValue('claude-opus-5-5');
    expect([...(modelo as HTMLSelectElement).options].map((o) => o.value)).toEqual(
      ['claude-opus-5-5', 'claude-sonnet-5', 'claude-haiku-4-5']);
    expect(confirmacao.textContent).toMatch(/Esforço: médio \(fixo\)/);
    expect(confirmacao.textContent).toMatch(/no máximo US\$ 1,43/);                    // 3 chamadas no teto de 16 mil
    await usuario.click(screen.getByRole('button', { name: 'Confirmar e extrair' }));
    await waitFor(() => {
      const post = chamadas.find((c) => c.init?.method === 'POST');
      expect(JSON.parse(String(post?.init?.body))).toEqual({
        controle: licitacaoC1.licitacao.controle, provedor: 'claude', modelo: 'claude-opus-5-5',
      });
    });
  });

  it('Haiku 4.5 não tem esforço: a tela diz isso e o pedido vai só com provedor e modelo', async () => {
    const { chamadas } = montar(licitacaoC1, 'admin', {
      'POST /api/acoes/extrair-ia': responder(registros.acaoProcessar),
    });
    const usuario = userEvent.setup();
    await screen.findByText('Questionário');
    await usuario.click(screen.getByRole('button', { name: 'Extrair com IA' }));
    const confirmacao = screen.getByRole('group', { name: 'Confirmar extração com IA' });
    await usuario.selectOptions(within(confirmacao).getByRole('combobox', { name: 'Modelo generativo' }), 'claude');
    await usuario.selectOptions(within(confirmacao).getByRole('combobox', { name: 'Modelo' }), 'claude-haiku-4-5');
    expect(confirmacao.textContent).toMatch(/não tem controle de esforço/);
    await usuario.click(screen.getByRole('button', { name: 'Confirmar e extrair' }));
    await waitFor(() => {
      const post = chamadas.find((c) => c.init?.method === 'POST');
      expect(JSON.parse(String(post?.init?.body))).toEqual({
        controle: licitacaoC1.licitacao.controle, provedor: 'claude', modelo: 'claude-haiku-4-5',
      });
    });
  });

  it('depois do clique a página ACOMPANHA sozinha até a licitação parar, e atualiza os gastos', async () => {
    // Nem a licitação nem os gastos mudavam na tela: o fluxo leva minutos e a página
    // só mudava no ↻. Agora ela pergunta de novo enquanto o estado anda e, ao parar, recarrega o resumo (os gastos).
    let estado = 'preparada';
    let detalhes = 0;
    const d = copia(licitacaoC1);
    const { chamadas } = fetchFalso({
      [`/api/licitacoes/${d.licitacao.slug}`]: () => {
        detalhes += 1;
        if (estado === 'lendo' && detalhes > 4) estado = 'extraindo';
        else if (estado === 'extraindo' && detalhes > 6) estado = 'publicada';
        const c = copia(d);
        c.licitacao.estado = estado;
        return c;
      },
      '/api/resumo': resumo,
      '/api/custo': {},
      '/api/modelos-ia': modelosIa,
      'POST /api/acoes/extrair-ia': () => {
        estado = 'lendo';
        return registros.acaoProcessar.corpo;
      },
    });
    renderizar(
      <Routes>
        <Route path="/licitacao/:slug" element={<Detalhe />} />
      </Routes>,
      { rota: `/licitacao/${d.licitacao.slug}`, me: { email: 'x@y', papel: 'admin', nome: null } },
    );
    const usuario = userEvent.setup();
    await screen.findByText('Questionário');
    await usuario.click(screen.getByRole('button', { name: 'Extrair com IA' }));
    const resumos = () => chamadas.filter((c) => c.url.pathname === '/api/resumo').length;
    await usuario.click(screen.getByRole('button', { name: 'Confirmar e extrair' }));
    expect(await screen.findByText(/processamento em andamento/i)).toBeInTheDocument();
    const resumosNoClique = resumos();
    expect(await screen.findByText('publicada', { selector: 'code' }, { timeout: 3000 })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/processamento em andamento/i)).toBeNull());
    await waitFor(() => expect(resumos()).toBeGreaterThan(resumosNoClique));        // os gastos recarregam ao parar
    // parou: nenhuma pergunta nova ao detalhe depois de publicada
    const n = detalhes;
    await new Promise((r) => setTimeout(r, 120));
    expect(detalhes).toBe(n);
  });

  it('Extrair com GPT desabilitado quando o edital não é PDF legível, com o porquê (Vale de São Domingos: RTF)', async () => {
    const d = copia(licitacaoC1);
    d.licitacao.estado = 'formato_nao_suportado';
    d.arquivos = [{ ...d.arquivos[0], status: 'formato_nao_suportado', motivo: 'não abre como PDF — o arquivo é RTF' }];
    montar(d);
    await screen.findByText('formato_nao_suportado', { selector: 'code' });
    const b = screen.getByRole('button', { name: 'Extrair com IA' });
    expect(b).toBeDisabled();
    expect(b.getAttribute('title')).toMatch(/RTF/);
    expect(b.getAttribute('title')).toMatch(/PDF/);
  });

  it('sem PDF válido: o detalhe avisa no topo, com o motivo de cada arquivo', async () => {
    const d = copia(licitacaoC1);
    d.licitacao.estado = 'formato_nao_suportado';
    d.arquivos = [{ ...d.arquivos[0], status: 'formato_nao_suportado', motivo: 'não abre como PDF — o arquivo é RTF' }];
    montar(d);
    const aviso = await screen.findByRole('alert', { name: /sem PDF válido/i });
    expect(aviso.textContent).toMatch(/o arquivo é RTF/);
    expect(aviso.textContent).toMatch(/processa apenas PDF/);
  });

  it('o pedido de extração com IA ainda não usado aparece no detalhe, com a escolha', async () => {
    const d = copia(licitacaoC1);
    d.pedido_ia = { provedor: 'claude', pedido_por: 'admin@x', pedido_em: '2026-09-25T04:29:41Z', modelo: 'claude-opus-5',
                    effort: 'high' };
    montar(d);
    const aviso = await screen.findByText(/pedido de extração com IA pendente/i);
    expect(aviso.textContent).toMatch(/claude-opus-5/);
    expect(aviso.textContent).toMatch(/high/);
  });

  it('Reverificar é R$ 0: a confirmação diz que é determinístico', async () => {
    montar(licitacaoC1);
    const usuario = userEvent.setup();
    await screen.findByText('Questionário');
    await usuario.click(screen.getByRole('button', { name: 'Reverificar' }));
    const confirmacao = screen.getByRole('group', { name: 'Confirmar reverificação' });
    expect(confirmacao.textContent).toContain('R$ 0,00');
    expect(confirmacao.textContent).toContain('sem IA');
  });

  it('os botões da API só aparecem para o admin; usuário e operador nem os veem', async () => {
    for (const papel of ['leitor', 'operador']) {
      const { unmount } = montar(licitacaoC1, papel);
      await screen.findByText('Questionário');
      for (const nome of ['Reverificar', 'Processar novamente', 'Extrair com IA']) {
        expect(screen.queryByRole('button', { name: nome })).toBeNull();
      }
      unmount();
    }
    montar(licitacaoC1, 'admin');
    await screen.findByText('Questionário');
    for (const nome of ['Reverificar', 'Processar novamente', 'Extrair com IA']) {
      expect(screen.getByRole('button', { name: nome })).toBeEnabled();
    }
  });

  it('sem o botão "Abrir RELATORIO": a página já mostra as respostas; o PNCP continua', async () => {
    // O e-mail continua apontando para o relatório, mas o botão saiu. O RELATORIO segue gerado e com rota própria
    // (/licitacao/:slug/relatorio, rotas.test.tsx): é para ele que o e-mail da extração aponta.
    montar(licitacaoC1);
    await screen.findByText('Questionário');
    expect(screen.queryByRole('link', { name: 'Abrir RELATORIO' })).toBeNull();
    expect(screen.queryByText('Abrir RELATORIO')).toBeNull();                        // nem a versão desabilitada
    expect(screen.getByRole('link', { name: 'Abrir no PNCP' })).toHaveAttribute('href', licitacaoC1.licitacao.link);
  });

  it('jev real: "sustenta X%" ao lado da resposta APROVADA, com o aviso fixo; o veredito não muda', async () => {
    const { container } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    const sustenta = licitacaoC1.jev!.sustenta;
    const linha = (id: string) => container.querySelector(`tr[data-pergunta="${id}"]`) as HTMLElement;
    expect(within(linha('Q1')).getByText(`sustenta ${Math.round(Number(sustenta.Q1.p_sustenta) * 100)}%`)).toBeInTheDocument();
    // Q2: o Jev CONTRADIZ (12%) — e a pílula continua APROVADO, a do verificador
    expect(within(linha('Q2')).getByText(`sustenta ${Math.round(Number(sustenta.Q2.p_sustenta) * 100)}%`)).toBeInTheDocument();
    expect(linha('Q2').querySelector('.v')).toHaveClass('APROVADO');
    expect(linha('Q9').textContent).not.toMatch(/sustenta \d+%/);
    expect(screen.getByText(/Indicador do Jev; não altera o veredito nem o escopo\./)).toBeInTheDocument();
  });

  it('jev em TODA resposta com trecho: a REVISAR também tem "sustenta X%"; sem trecho, diz por quê', async () => {
    const { container } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    const sustenta = licitacaoC1.jev!.sustenta;
    const linha = (id: string) => container.querySelector(`tr[data-pergunta="${id}"]`) as HTMLElement;
    expect(within(linha('Q10')).getByText(`sustenta ${Math.round(Number(sustenta.Q10.p_sustenta) * 100)}%`)).toBeInTheDocument();
    expect(linha('Q10').querySelector('.v')).toHaveClass('REVISAR');
    // Q12 não cita trecho: não há passagem para o Jev julgar — e a linha diz isso em vez de ficar muda
    expect(within(linha('Q12')).getByText('Jev: sem trecho')).toBeInTheDocument();
    expect(linha('Q1').textContent).not.toContain('Jev: sem trecho');
  });

  it('API sem o campo jev (versão anterior): nenhum "sustenta", nada quebra', async () => {
    const d = copia(licitacaoC1);
    delete d.jev;
    const { container } = montar(d);
    await screen.findByText('Questionário');
    expect(container.textContent).not.toMatch(/sustenta \d+%/);
    expect(container.textContent).not.toContain('Indicador do Jev');
  });

  const AVISO_MELHOR_DE_N =
    'Best-of-N: a resposta não passou no verificador e o modelo tentou novamente; prevalece a tentativa que a evidência sustenta.';

  it('Best-of-N (v3.1): a pergunta refeita ganha, na própria linha, a nota discreta com o porquê no title', async () => {
    // Best-of-N: a resposta que falha no verificador ganha até 2 tentativas extras,
    // só ela, e fica a que a evidência sustenta. O que foi decidido vem em `melhor_de_n` (db/050).
    const d = copia(licitacaoC1);
    d.melhor_de_n = {
      n: 3,
      rodadas: 2,
      perguntas: {
        Q7: { tentativas: 2, escolhida: 1, pontos: [[-1, 0.41], [2, 1.0]] },
        Q12: { tentativas: 3, escolhida: 0, pontos: [[0, 0], [-1, 0.2], [-1, 0.1]] },
      },
    };
    const { container } = montar(d);
    await screen.findByText('Questionário');
    const linha = (id: string) => container.querySelector(`tr[data-pergunta="${id}"]`) as HTMLElement;
    expect(within(linha('Q7')).getByText('escolhida a 2ª de 2 tentativas')).toHaveAttribute('title', AVISO_MELHOR_DE_N);
    expect(within(linha('Q12')).getByText('3 tentativas; prevaleceu a primeira')).toHaveAttribute('title', AVISO_MELHOR_DE_N);
    expect(container.querySelectorAll('[title^="Best-of-N"]')).toHaveLength(2);        // só as que tiveram tentativa extra
    expect(linha('Q7').querySelector('.v')).toHaveClass('APROVADO');                    // o veredito é o do verificador
  });

  it('sem registro de Best-of-N (API anterior à v3.1, ou execução sem ele), nenhuma linha muda', async () => {
    const semCampo = copia(licitacaoC1);
    delete semCampo.melhor_de_n;
    const nulo = copia(licitacaoC1);
    nulo.melhor_de_n = null;
    for (const d of [semCampo, nulo]) {
      const { container, unmount } = montar(d);
      await screen.findByText('Questionário');
      expect(container.querySelector('[title^="Best-of-N"]')).toBeNull();
      expect(container.textContent).not.toMatch(/tentativas/);
      unmount();
    }
  });

  it('rodapé: o que não foi medido não vira zero (C1 agente sem tokens; C4 sem extração)', async () => {
    const { container, unmount } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    const rodape = container.querySelector('footer')!.textContent!;
    expect(rodape).toBe(
      `${licitacaoC1.licitacao.modelo} · 1 chamada ao modelo · tokens de entrada não medidos · verificação determinística, sem IA`,
    );
    unmount();
    const c4 = montar(licitacaoC4);
    await screen.findByText(/ainda não foi extraída/);
    const rodapeC4 = c4.container.querySelector('footer')!.textContent!;
    expect(rodapeC4).toBe('ainda não extraída · verificação determinística, sem IA');
    expect(rodapeC4).not.toMatch(/0 (chamada|tokens)|^- /);
  });

  it('toda tabela da página rola dentro do próprio bloco no celular (.rolagem); a Q13 fica dentro da célula', async () => {
    const { container } = montar(licitacaoC1);
    await screen.findByText('Questionário');
    const tabelas = Array.from(container.querySelectorAll('table:not(.dist)'));
    expect(tabelas.length).toBeGreaterThanOrEqual(4);
    for (const t of tabelas) expect(t.parentElement).toHaveClass('rolagem');
    const rolagem17 = container.querySelector('tr[data-pergunta="Q1"]')!.closest('.rolagem') as HTMLElement;
    expect(rolagem17.style.getPropertyValue('--min-tabela')).toBe('720px');
  });
});
