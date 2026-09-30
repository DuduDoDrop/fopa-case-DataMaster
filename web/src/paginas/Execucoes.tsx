/**
 * `/execucoes` — o bloco "Últimas execuções" do painel v2 virou página:
 * quando · o quê · duração · custo (âmbar se gastou) · resultado, com link
 * para a execução no n8n; e o custo por dia e por modelo, com o teto.
 *
 * Log que depende de alguém lembrar de ler não é auditoria (painel.py
 * `_bloco_execucoes`): esta é a tela que o operador já abre.
 */
import '../../design/painel.css';
import { Link, useSearchParams } from 'react-router-dom';
import { useCusto, useExecucoes } from '../api/consultas';
import type { ExecucaoWorkflow } from '../api/tipos';
import { Carregando, Falha } from '../componentes/Estado';
import { Rolagem } from '../componentes/Rolagem';
import {
  brl,
  custoRodada,
  custo as textoCusto,
  data,
  dataHora,
  datasNoTexto,
  duracao,
  milhar,
  numero,
  SEM_CHAMADA_REGISTRADA,
} from '../lib/formato';

// Identificador não é contagem: o W10/W40 gravam o `email_id` do aviso e o W11 o `execucao_id` do W01
// nos contadores, e a coluna mostrava "261 email_id".
const EH_ID = /(^|_)id$/;
// Status que não é o da rodada normal vem antes dos números: o "disjuntor" do W10 (0 reivindicadas),
// o "parcial" do W50 e o "revertido" do W30 sumiam atrás dos contadores.
const STATUS_NORMAL = new Set(['ok', 'em_curso']);
const STATUS_TEXTO: Record<string, string> = { disjuntor: 'Proteção acionada (disjuntor): nenhuma licitação reivindicada' };

function resultado(e: ExecucaoWorkflow): string {
  const partes: string[] = [];
  if (e.status && !STATUS_NORMAL.has(e.status)) partes.push(STATUS_TEXTO[e.status] ?? e.status);
  for (const [k, v] of Object.entries(e.contadores ?? {})) {
    // o nome do contador vem do fluxo (voltam_para_a_fila): na tela, com espaço
    if (typeof v === 'number' && v && !EH_ID.test(k)) partes.push(`${milhar(v)} ${k.replace(/_/g, ' ')}`);
  }
  if (e.cego) partes.push('coleta incompleta');
  if (e.erro) partes.push(datasNoTexto(e.erro));
  return partes.join(' · ') || e.status || '—';
}

export function Execucoes() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1);
  const consulta = useExecucoes(page);
  const execucoes = consulta.data?.itens;
  const paginas = consulta.data ? Math.max(1, consulta.data.paginas) : 1;
  const custo = useCusto();
  const teto = numero(custo.data?.teto_brl_dia);
  const hojeSemPreco = custo.data?.hoje_sem_preco ?? 0;

  function irPara(nova: number) {
    const p = new URLSearchParams(params);
    if (nova > 1) p.set('page', String(nova));
    else p.delete('page');
    setParams(p, { replace: true });
  }

  return (
    <div className="pg-painel">
      <div className="wrap">
        <header>
          <p className="eyebrow">FOPA · operação</p>
          <h1>Execuções</h1>
          <p className="sub">Execuções do processamento, com duração, custo e resultado.</p>
        </header>

        {consulta.isError ? (
          <Falha erro={consulta.error} oque="as execuções" />
        ) : !execucoes ? (
          <Carregando />
        ) : execucoes.length === 0 ? (
          <p className="vazio">Nenhuma execução registrada.</p>
        ) : (
          <Rolagem min={720}>
            <table>
              <thead>
                <tr>
                  <th>Quando</th>
                  <th>Processo</th>
                  <th>Duração</th>
                  <th>Custo</th>
                  <th>Resultado</th>
                </tr>
              </thead>
              <tbody>
                {execucoes.map((e) => {
                  const c = numero(e.custo_brl);
                  const textoRodada = custoRodada(e);
                  return (
                    <tr key={e.id}>
                      <td className="sha nw">{dataHora(e.iniciado_em)}</td>
                      <td>
                        <code>{e.workflow}</code>
                        {e.script_legado && (
                          <>
                            {' '}
                            <span className="sha">{e.script_legado}</span>
                          </>
                        )}
                        {e.controle && (
                          <>
                            {' '}
                            · <Link to={`/licitacao/${e.controle.replace('/', '-')}`}>{e.controle}</Link>
                          </>
                        )}
                        {e.n8n_execution_id && <span className="sha"> · n8n #{e.n8n_execution_id}</span>}
                        {e.buscas_falhas ? (
                          <span className="sha">
                            {' '}
                            · {milhar(e.buscas_falhas)} {e.buscas_falhas === 1 ? 'busca falhou' : 'buscas falharam'}
                          </span>
                        ) : null}
                      </td>
                      <td className="sha nw">{duracao(e.duracao_s)}</td>
                      <td
                        className={c !== null && c > 0 ? 'gastou nw' : 'nw'}
                        title={textoRodada === '—' ? SEM_CHAMADA_REGISTRADA : undefined}
                      >
                        {textoRodada}
                      </td>
                      <td>{resultado(e)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Rolagem>
        )}

        {consulta.data && paginas > 1 && (
          <nav className="paginacao" aria-label="Paginação das execuções">
            <button
              type="button"
              className="secundario"
              disabled={page <= 1}
              title={page <= 1 ? 'Esta é a primeira página.' : undefined}
              onClick={() => irPara(page - 1)}
            >
              ← Anterior
            </button>
            <span className="atualmsg">
              página {milhar(page)} de {milhar(paginas)} · {milhar(consulta.data.total)} execuções
            </span>
            <button
              type="button"
              className="secundario"
              disabled={page >= paginas}
              title={page >= paginas ? 'Esta é a última página.' : undefined}
              onClick={() => irPara(page + 1)}
            >
              Próxima →
            </button>
          </nav>
        )}

        <h2>Custo</h2>
        <p className="sub">
          Teto por dia: <b>{teto === null ? 'sem teto' : brl(teto)}</b>
          {custo.data
            ? ` · hoje: ${brl(custo.data.hoje_brl)}${hojeSemPreco > 0 ? ` + ${milhar(hojeSemPreco)} sem preço` : ''}`
            : ''}
          . Chamadas sem tabela de preço são registradas como "sem
          preço", nunca como R$ 0,00.
        </p>
        {custo.isError ? (
          <Falha erro={custo.error} oque="o custo" />
        ) : !custo.data ? (
          <Carregando />
        ) : (
          <>
            <Rolagem min={480}>
              <table>
                <thead>
                  <tr>
                    <th>Dia</th>
                    <th>Custo conhecido</th>
                    <th>Chamadas</th>
                    <th>Sem preço</th>
                  </tr>
                </thead>
                <tbody>
                  {custo.data.por_dia.length === 0 && (
                    <tr>
                      <td colSpan={4} className="vazio">
                        Nenhuma chamada ao modelo registrada.
                      </td>
                    </tr>
                  )}
                  {custo.data.por_dia.map((d) => (
                    <tr key={d.dia}>
                      <td className="sha nw">{data(d.dia)}</td>
                      <td className={teto !== null && (numero(d.brl) ?? 0) > teto ? 'gastou nw' : 'nw'}>{brl(d.brl)}</td>
                      <td>{milhar(d.chamadas)}</td>
                      <td>{milhar(d.sem_preco)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Rolagem>
            <Rolagem min={560}>
              <table>
                <thead>
                  <tr>
                    <th>Origem · modelo</th>
                    <th>Custo</th>
                    <th>Execuções</th>
                    <th>Sem preço</th>
                  </tr>
                </thead>
                <tbody>
                  {custo.data.por_modelo.length === 0 && (
                    <tr>
                      <td colSpan={4} className="vazio">
                        Nenhuma execução de modelo registrada.
                      </td>
                    </tr>
                  )}
                  {custo.data.por_modelo.map((m) => (
                    <tr key={`${m.origem}|${m.provedor ?? ''}|${m.modelo ?? ''}`}>
                      <td>
                        <code>{m.origem}</code> · <code>{m.modelo ?? '?'}</code>
                        {m.provedor ? <span className="sha"> ({m.provedor})</span> : null}
                      </td>
                      <td>
                        {/* soma NULL = nenhuma execução com preço: nunca R$ 0,00 */}
                        {textoCusto({ brl: m.brl, brl_legado: m.brl_legado, preco_conhecido: null })}
                      </td>
                      <td>{milhar(m.execucoes)}</td>
                      <td>{milhar(m.sem_preco)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Rolagem>
          </>
        )}
      </div>
    </div>
  );
}
