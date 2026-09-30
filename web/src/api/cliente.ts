/**
 * `fetch` da fopa-api, na mesma origem (plano §8: sem CORS; o cookie de
 * sessão HttpOnly vai sozinho na navegação e no fetch same-origin).
 *
 * 401 = sem sessão → a página `/entrar`, cujo botão leva ao `/login` do
 * SERVIDOR (que decide: modo local na demo, Google no resto). 403 NÃO
 * redireciona: é falta de papel, e mandar de volta ao login viraria um laço —
 * a tela mostra a mensagem do servidor.
 */

export class ErroApi extends Error {
  constructor(
    public status: number,
    mensagem: string,
    public corpo?: unknown,
  ) {
    super(mensagem);
    this.name = 'ErroApi';
  }
}

export const PAGINA_ENTRAR = '/entrar';

/** Para onde mandar no 401; null se já está na página de entrada (sem laço). */
export function destinoDoLogin(caminho: string): string | null {
  return caminho === PAGINA_ENTRAR ? null : PAGINA_ENTRAR;
}

export function irParaLogin(): void {
  const destino = destinoDoLogin(window.location.pathname);
  if (destino) window.location.assign(destino);
}

/**
 * O texto do erro como o servidor escreveu. O FastAPI manda `detail` como
 * string nos HTTPException e como LISTA de `{loc, msg}` na validação (422) —
 * sem tratar a lista, a tela dizia "a API respondeu 422".
 */
export function mensagemDe(corpo: unknown, status: number): string {
  if (corpo && typeof corpo === 'object') {
    const c = corpo as Record<string, unknown>;
    if (typeof c.detail === 'string') return c.detail;
    if (Array.isArray(c.detail)) {
      const msgs = c.detail
        .map((d) => {
          if (!d || typeof d !== 'object') return String(d);
          const item = d as { msg?: unknown; loc?: unknown };
          const campo = Array.isArray(item.loc) ? item.loc.filter((p) => p !== 'body' && p !== 'query').join('.') : '';
          const msg = typeof item.msg === 'string' ? item.msg.replace(/^Value error, /, '') : JSON.stringify(d);
          return campo ? `${campo}: ${msg}` : msg;
        })
        .filter(Boolean);
      if (msgs.length) return msgs.join('; ');
    }
    if (typeof c.erro === 'string') return c.erro;
    if (typeof c.mensagem === 'string') return c.mensagem;
  }
  if (typeof corpo === 'string' && corpo.trim()) return corpo.trim().slice(0, 300);
  return `a API respondeu ${status}`;
}

/**
 * `aceitos`: status fora de 2xx cujo corpo É a resposta (a `/api/saude`
 * responde 503 dizendo QUAL peça caiu — isso é o dado, não um erro de tela).
 */
export async function api<T = unknown>(
  caminho: string,
  init: RequestInit = {},
  aoPerderSessao: () => void = irParaLogin,
  aceitos: number[] = [],
): Promise<T> {
  const cabecalhos: Record<string, string> = { Accept: 'application/json' };
  if (init.body !== undefined && !(init.body instanceof FormData)) cabecalhos['Content-Type'] = 'application/json';
  const r = await fetch(caminho, {
    ...init,
    credentials: 'same-origin',
    headers: { ...cabecalhos, ...(init.headers as Record<string, string> | undefined) },
  });
  const tipo = r.headers.get('Content-Type') ?? '';
  const corpo: unknown = r.status === 204 ? null : tipo.includes('json') ? await r.json().catch(() => null) : await r.text();
  if (aceitos.includes(r.status)) return corpo as T;
  if (r.status === 401) {
    aoPerderSessao();
    throw new ErroApi(401, 'sessão expirada: entre de novo', corpo);
  }
  if (!r.ok) throw new ErroApi(r.status, mensagemDe(corpo, r.status), corpo);
  return corpo as T;
}

export function enviar<T = unknown>(caminho: string, metodo: 'POST' | 'PUT' | 'PATCH' | 'DELETE', corpo?: unknown) {
  return api<T>(caminho, { method: metodo, body: corpo === undefined ? undefined : JSON.stringify(corpo) });
}
