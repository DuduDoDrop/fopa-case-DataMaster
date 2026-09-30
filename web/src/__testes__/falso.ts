/**
 * Um `fetch` falso que responde por rota, e registra o que foi pedido. O
 * teste da página exercita o caminho real (TanStack Query → cliente → fetch),
 * só troca a rede.
 */
import { vi } from 'vitest';

type Resposta = unknown | ((url: URL, init?: RequestInit) => unknown);

export function fetchFalso(rotas: Record<string, Resposta>) {
  const chamadas: { url: URL; init?: RequestInit }[] = [];
  const f = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(entrada), 'http://localhost');
    chamadas.push({ url, init });
    const chave = `${(init?.method ?? 'GET').toUpperCase()} ${url.pathname}`;
    const achada = rotas[chave] ?? rotas[url.pathname];
    if (achada === undefined) {
      return new Response(JSON.stringify({ detail: `rota falsa ausente: ${chave}` }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    const corpo = typeof achada === 'function' ? (achada as (u: URL, i?: RequestInit) => unknown)(url, init) : achada;
    if (corpo instanceof Response) return corpo;
    return new Response(JSON.stringify(corpo), { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
  vi.stubGlobal('fetch', f);
  return { f, chamadas };
}
