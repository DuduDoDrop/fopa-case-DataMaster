/**
 * Sessão e erros, com os corpos que a API devolve de verdade: 401 leva à
 * página /entrar (o botão dela vai ao /login do servidor); 403 NÃO
 * redireciona (é falta de papel, e mandar para o login de novo seria um
 * laço); o 422 do FastAPI vem com `detail` em LISTA e tem de virar texto.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ErroApi, api, destinoDoLogin } from '../api/cliente';
import { registros } from '../__fixtures__/contrato';
import jSemSessao from '../__fixtures__/contrato/erro-sem-sessao-401.json';
import jConflito from '../__fixtures__/contrato/admin-configuracao-put-409.json';

function respostaJson(status: number, corpo: unknown) {
  return new Response(JSON.stringify(corpo), { status, headers: { 'Content-Type': 'application/json' } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('cliente da API', () => {
  it('401 (corpo real) chama o redirecionamento e rejeita', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respostaJson(jSemSessao.status, jSemSessao.corpo)));
    const ir = vi.fn();
    await expect(api('/api/licitacoes', {}, ir)).rejects.toMatchObject({ status: 401 });
    expect(ir).toHaveBeenCalledTimes(1);
  });

  it('409 rejeita com a mensagem do servidor e não redireciona', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respostaJson(jConflito.status, jConflito.corpo)));
    const ir = vi.fn();
    const erro = (await api('/api/admin/configuracao', { method: 'PUT' }, ir).catch((e: unknown) => e)) as ErroApi;
    expect(erro).toBeInstanceOf(ErroApi);
    expect(erro.message).toBe(jConflito.corpo.detail);
    expect(ir).not.toHaveBeenCalled();
  });

  it('422 do FastAPI (detail em lista) vira a mensagem legível', async () => {
    const r = registros.erroRevisao;
    vi.stubGlobal('fetch', vi.fn(async () => respostaJson(r.status, r.corpo)));
    const erro = (await api('/api/revisoes', { method: 'POST' }).catch((e: unknown) => e)) as ErroApi;
    expect(erro.status).toBe(422);
    expect(erro.message).toContain("decisão 'corrigida' exige resposta_corrigida");
    expect(erro.message).not.toContain('[object Object]');
  });

  it('status aceito devolve o corpo (a /api/saude responde 503 dizendo quem caiu)', async () => {
    const r = registros.saude503;
    vi.stubGlobal('fetch', vi.fn(async () => respostaJson(r.status, r.corpo)));
    await expect(api('/api/saude', {}, undefined, [503])).resolves.toEqual(r.corpo);
  });

  it('manda o cookie da mesma origem e devolve o JSON', async () => {
    const f = vi.fn(async () => respostaJson(200, { email: 'a@b', papel: 'admin' }));
    vi.stubGlobal('fetch', f);
    await expect(api('/api/me')).resolves.toEqual({ email: 'a@b', papel: 'admin' });
    expect((f.mock.calls[0] as unknown[])[1]).toMatchObject({ credentials: 'same-origin' });
  });

  it('o 401 leva à página /entrar, nunca em laço', () => {
    expect(destinoDoLogin('/licitacao/x-1')).toBe('/entrar');
    expect(destinoDoLogin('/entrar')).toBeNull();
  });
});
