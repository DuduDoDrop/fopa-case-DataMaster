/**
 * `/saude` — `GET /api/saude`: API, worker (Tesseract), Postgres, n8n,
 * última coleta e último alerta (`{em, workflow, mensagem}`, a última falha
 * que o W90/W00 registrou). Cada peça em um tile: `ok` teal, falha `al`
 * vermelho (é defeito), desconhecido sem cor.
 *
 * A rota responde **503** quando o Postgres ou o worker caem — com o corpo
 * dizendo QUAL (`caiu`) e por quê. Esse 503 é o dado desta tela: ela mostra
 * as peças, não "não deu para carregar". O n8n fora NÃO derruba o site (a
 * leitura é toda do Postgres): vem em `avisos`.
 */
import '../../design/painel.css';
import { useSaude } from '../api/consultas';
import { Carregando, Falha } from '../componentes/Estado';
import { Rolagem } from '../componentes/Rolagem';
import { dataHora, datasNoTexto } from '../lib/formato';

/**
 * Num tile cabe uma frase. A mensagem do último alerta (um erro inteiro do
 * n8n, 200+ caracteres) esticava a fileira toda: os outros cinco tiles
 * ficavam com ~200 px de vazio embaixo do "ok". O texto completo vai no
 * `title`; o tile mostra o começo.
 */
const MAX_TILE = 90;

export function resumoTile(texto: string): string {
  return texto.length > MAX_TILE ? `${texto.slice(0, MAX_TILE - 1).trimEnd()}…` : texto;
}

function Tile({ nome, ok, detalhe }: { nome: string; ok: boolean | null | undefined; detalhe?: string }) {
  const classe = ok === true ? 'tile ok' : ok === false ? 'tile al' : 'tile';
  return (
    <div className={classe} title={detalhe}>
      <b>{ok === true ? 'ok' : ok === false ? 'falhou' : '—'}</b>
      <span>
        {nome}
        {detalhe ? ` · ${resumoTile(detalhe)}` : ''}
      </span>
    </div>
  );
}

/** `avisos` traz NOMES de peças (como `caiu`); a frase diz o que isso muda para quem opera. */
const AVISOS: Record<string, string> = {
  n8n: 'Processamento (n8n) indisponível: verificar, processar e reverificar ficam suspensos até o retorno; a consulta continua disponível.',
};

function textoAviso(a: unknown): string {
  if (typeof a === 'string') return AVISOS[a] ?? a;
  return JSON.stringify(a);
}

export function Saude() {
  const saude = useSaude();
  const s = saude.data;
  const health = (s?.worker?.health ?? {}) as Record<string, unknown>;
  const coleta = s?.ultima_coleta;
  const alerta = s?.ultimo_alerta;
  const mensagemAlerta = alerta?.mensagem ? datasNoTexto(alerta.mensagem) : '';
  const avisos = s?.avisos ?? [];
  return (
    <div className="pg-painel">
      <div className="wrap">
        <header>
          <p className="eyebrow">FOPA · operação</p>
          <h1>Saúde</h1>
          <p className="sub">
            Atualização a cada 30 segundos. Ambiente: {s?.ambiente ?? '—'}
            {s?.auth_mode ? ` · login ${s.auth_mode}` : ''}
            {s && s.caiu.length > 0 ? ` · indisponível: ${s.caiu.join(', ')}` : ''}.
          </p>
        </header>
        {saude.isError ? (
          <Falha erro={saude.error} oque="a saúde" />
        ) : !s ? (
          <Carregando />
        ) : (
          <>
            <div className="tiles">
              <Tile nome="Site (API)" ok={s.api_ok ?? true} />
              {s.worker && (
                <Tile
                  nome="Leitura e extração (worker)"
                  ok={s.worker.ok}
                  detalhe={s.worker.erro ?? (health.tesseract ? `tesseract ${String(health.tesseract)}` : undefined)}
                />
              )}
              {s.postgres && <Tile nome="Banco de dados (Postgres)" ok={s.postgres.ok} detalhe={s.postgres.erro} />}
              {s.n8n && (
                <Tile
                  nome="Processamento (n8n)"
                  ok={s.n8n.ok}
                  detalhe={s.n8n.erro ?? (s.n8n.status !== undefined ? `HTTP ${s.n8n.status}` : undefined)}
                />
              )}
              {coleta !== undefined && (
                <div className={coleta?.cego ? 'tile quando al' : 'tile quando'}>
                  <b>{dataHora(coleta?.iniciado_em ?? null)}</b>
                  <span>{coleta?.cego ? 'Última coleta · incompleta' : 'Última coleta'}</span>
                </div>
              )}
              {alerta !== undefined && (
                <div className="tile quando" title={mensagemAlerta || undefined}>
                  <b>{dataHora(alerta?.em ?? null)}</b>
                  <span>
                    {alerta ? 'Último alerta' : 'Nenhum alerta registrado'}
                    {alerta?.workflow ? ` · ${alerta.workflow}` : ''}
                    {mensagemAlerta ? ` · ${resumoTile(mensagemAlerta)}` : ''}
                  </span>
                </div>
              )}
            </div>
            {avisos.length > 0 && (
              <>
                <h2>Avisos</h2>
                {avisos.map((a, i) => (
                  <p key={i} className="alerta">
                    {textoAviso(a)}
                  </p>
                ))}
              </>
            )}
            {Object.keys(health).length > 0 && (
              <>
                <h2>Detalhes da leitura e extração (worker)</h2>
                <Rolagem min={0}>
                  <table>
                    <tbody>
                      {Object.entries(health).map(([k, v]) => (
                        <tr key={k}>
                          <td>
                            <code>{k}</code>
                          </td>
                          <td className="sha quebra">{typeof v === 'string' ? v : JSON.stringify(v)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Rolagem>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
