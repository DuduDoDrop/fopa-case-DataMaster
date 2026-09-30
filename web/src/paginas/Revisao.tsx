/**
 * `/revisao` — a revisão humana (plano §8; README §6 "revisão humana numa
 * camada própria").
 *
 * Aba "respostas": a fila `GET /api/fila-revisao` (revisões abertas, com a
 * resposta do modelo e o veredito do verificador) no mesmo molde da tabela
 * das 17 do RELATORIO — barra de status, evidência, origem por id com
 * `#page=N`, pílula do veredito — e, por linha, a decisão do operador em
 * `POST /api/revisoes {verificacao_id, pergunta_id, decisao,
 * resposta_corrigida?, nota?}`. A decisão fica em `revisoes_humanas` com
 * nome e data; a resposta e o veredito continuam como estavam.
 *
 * Aba "escopo": rótulos humanos de escopo (`GET/POST /api/rotulos-escopo
 * {controle, dentro, motivo?}`), para onde o selo do Jev "discorda" do card
 * leva. Também camada própria: não muda `licitacoes.escopo_dentro` (ADR-003).
 * A tabela mostra só as pendentes: a que ganha rótulo sai da lista, e o rótulo
 * continua valendo no card e no formulário (pelo controle).
 * A rota é nova; sem ela a aba diz que a API ainda não expõe.
 *
 * As abas são só do admin, o único com duas. Os outros veem o título
 * "Respostas a revisar (N)", sem botão. Nos dois casos, as respostas abrem com o passo a passo
 * antes da busca.
 */
import '../../design/relatorio.css';
import '../../design/painel.css';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useEnviar, useFilaRevisao, useLicitacoesEmRevisao, useRotulosEscopo } from '../api/consultas';
import type { ItemRevisao, RespostaDetalhe } from '../api/tipos';
import { Carregando, Falha } from '../componentes/Estado';
import { Rolagem } from '../componentes/Rolagem';
import { ehAdmin, MOTIVO_SO_OPERADOR, podeOperar, useSessao } from '../componentes/Sessao';
import { Evidencia, Legenda, Origem, PilulaVeredito, statusDaLinha } from '../componentes/TabelaRespostas';
import { data, dataHora, milhar } from '../lib/formato';
import { AVISO_IA_FOLHA, opiniaoIa } from '../lib/respostas';

const RE_CONTROLE = /^\d{14}-\d+-\d+\/\d{4}$/;

/** A linha da fila no formato da tabela das 17. */
function comoResposta(i: ItemRevisao): RespostaDetalhe {
  return {
    pergunta_id: i.pergunta_id ?? '—',
    pergunta: i.pergunta ?? '',
    critico: !!i.critico,
    resposta: i.resposta ?? '',
    arquivo_citado: i.arquivo_citado,
    pagina_citada: i.pagina_citada,
    trecho_literal: i.trecho_literal,
    conflito: i.conflito,
    veredito: i.veredito,
    arquivo_canonico: null,
    arquivo_id: i.arquivo_id,
    pagina_final: i.pagina_final,
    alertas: i.alertas,
    ausencia: i.ausencia,
  };
}

function localDe(i: { municipio?: string | null; uf?: string | null; orgao?: string | null; controle: string }): string {
  if (i.municipio && i.uf) return `${i.municipio}/${i.uf}`;
  return i.municipio || i.orgao || i.controle;
}

// ------------------------------------------------------------ decisão
interface DecisaoIn {
  verificacao_id: number;
  pergunta_id: string;
  decisao: string;
  resposta_corrigida?: string;
  nota?: string;
}

/** O formulário de decisão da fila; o detalhe da licitação usa o mesmo (plano §8: revisão inline). */
export function Decisao({ item }: { item: { verificacao_id: number | null; pergunta_id: string | null } }) {
  const me = useSessao();
  const [decisao, setDecisao] = useState('aceita');
  const [corrigida, setCorrigida] = useState('');
  const [nota, setNota] = useState('');
  const enviar = useEnviar<DecisaoIn>((corpo) => ({ caminho: '/api/revisoes', metodo: 'POST', corpo }), [
    '/api/fila-revisao',
    '/api/resumo',
    '/api/licitacoes',
  ]);
  const motivo = !podeOperar(me)
    ? MOTIVO_SO_OPERADOR
    : item.verificacao_id === null || !item.pergunta_id
      ? 'Revisão sem verificação ou pergunta associada: registre a decisão pelo detalhe da licitação.'
      : decisao === 'corrigida' && !corrigida.trim()
        ? 'Informe a resposta corrigida.'
        : null;

  function registrar() {
    if (item.verificacao_id === null || !item.pergunta_id) return;
    const corpo: DecisaoIn = { verificacao_id: item.verificacao_id, pergunta_id: item.pergunta_id, decisao };
    if (decisao === 'corrigida') corpo.resposta_corrigida = corrigida.trim();
    if (nota.trim()) corpo.nota = nota.trim();
    enviar.mutate(corpo);
  }

  const desabilitado = !podeOperar(me);
  return (
    <div className="pg-painel">
      <form
        className="formulario"
        onSubmit={(e) => {
          e.preventDefault();
          registrar();
        }}
      >
        <label>
          Decisão
          <select value={decisao} disabled={desabilitado} title={desabilitado ? MOTIVO_SO_OPERADOR : undefined} onChange={(e) => setDecisao(e.target.value)}>
            <option value="aceita">Aceita</option>
            <option value="corrigida">Corrigida</option>
            <option value="rejeitada">Rejeitada</option>
          </select>
        </label>
        {decisao === 'corrigida' && (
          <label>
            Resposta corrigida
            <textarea rows={2} value={corrigida} onChange={(e) => setCorrigida(e.target.value)} />
          </label>
        )}
        <label>
          Nota
          <input value={nota} disabled={desabilitado} title={desabilitado ? MOTIVO_SO_OPERADOR : undefined} onChange={(e) => setNota(e.target.value)} />
        </label>
        <button type="submit" className="secundario" disabled={!!motivo || enviar.isPending} title={motivo ?? 'Registra a decisão; a resposta e o veredito originais não são alterados.'}>
          Registrar decisão
        </button>
        {enviar.isError && (
          <span className="erro" role="alert">
            {enviar.error.message}
          </span>
        )}
      </form>
    </div>
  );
}

/** "3 respostas a revisar" — um nome só na página inteira (antes: "revisões abertas" e "campos pendentes"). */
function aRevisar(n: number): string {
  return `${milhar(n)} ${n === 1 ? 'resposta a revisar' : 'respostas a revisar'}`;
}

/** "3 respostas a revisar · 1 crítica" */
function pendentes(n: number, criticas: number): string {
  return criticas ? `${aRevisar(n)} · ${milhar(criticas)} ${criticas === 1 ? 'crítica' : 'críticas'}` : aRevisar(n);
}

/** O "como usar" da revisão de respostas. */
function ComoRevisar() {
  return (
    <ol className="revisao-passos" aria-label="Como revisar">
      <li>Busque a licitação por município, órgão, modalidade, número de controle ou objeto</li>
      <li>Selecione a licitação na lista para abrir as respostas a revisar</li>
      <li>Confira cada resposta no documento de origem, pelo link da coluna Origem</li>
      <li>
        Registre a decisão: Aceita (resposta correta), Corrigida (informe a resposta correta) ou Rejeitada (sem base nos
        documentos)
      </li>
    </ol>
  );
}

/** Busca por licitação: a mesma do painel, guardada em `?q=` — o detalhe linka já filtrado. */
function BuscaFila({ q }: { q: string }) {
  const [params, setParams] = useSearchParams();
  const [texto, setTexto] = useState(q);

  // A busca espera o usuário parar de digitar: cada tecla não é uma consulta.
  useEffect(() => {
    if (texto.trim() === q) return;
    const t = setTimeout(() => {
      const p = new URLSearchParams(params);
      if (texto.trim()) p.set('q', texto.trim());
      else p.delete('q');
      setParams(p, { replace: true });
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [texto]);

  return (
    <div className="pg-painel">
      <div className="barra">
        <input
          type="search"
          placeholder="Buscar por município, órgão, modalidade, número de controle ou objeto"
          aria-label="Buscar revisões por licitação"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
        />
      </div>
    </div>
  );
}

/**
 * A aba "respostas":
 * sem busca, só os totais; com a busca, as licitações achadas (a lista leve); o clique abre os campos dela.
 */
function RevisaoPorLicitacao({ q, controle }: { q: string; controle: string }) {
  return controle ? <CamposDaLicitacao controle={controle} q={q} /> : <BuscaDeLicitacoes q={q} />;
}

function BuscaDeLicitacoes({ q }: { q: string }) {
  const lista = useLicitacoesEmRevisao(q);
  const d = lista.data;
  return (
    <>
      <BuscaFila q={q} />
      {lista.isError ? (
        <Falha erro={lista.error} oque="a revisão" />
      ) : !d ? (
        <Carregando />
      ) : !q ? (
        // Sem busca, nada embaixo dela: o total está no título, e o passo a passo, acima.
        d.total_revisoes ? null : (
          <p className="sub">
            Nenhuma resposta a revisar. As respostas que o verificador marcar para revisão humana aparecem aqui.
          </p>
        )
      ) : !d.itens.length ? (
        <p className="sub">Nenhuma licitação com respostas a revisar para “{q}”.</p>
      ) : (
        <>
          <p className="sub">
            {d.encontradas > d.itens.length
              ? `${milhar(d.itens.length)} de ${milhar(d.encontradas)} licitações. Refine a busca para encontrar as demais.`
              : `${milhar(d.encontradas)} ${d.encontradas === 1 ? 'licitação' : 'licitações'} com respostas a revisar.`}
          </p>
          <ul className="revisao-licitacoes">
            {d.itens.map((l) => (
              <li key={l.controle}>
                <Link to={`/revisao?${new URLSearchParams({ q, controle: l.controle })}`}>
                  <b>{localDe(l)}</b>
                  <span className="perg">
                    {l.orgao ? `${l.orgao} · ` : ''}
                    {l.controle} · prazo {data(l.fim_prazo)}
                  </span>
                </Link>
                <span className={l.criticas ? 'marca alerta' : 'marca'}>{pendentes(l.abertas, l.criticas)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

function CamposDaLicitacao({ controle, q }: { controle: string; q: string }) {
  const fila = useFilaRevisao(controle);
  const itens = fila.data?.itens ?? [];
  const primeiro = itens[0];
  const criticas = itens.filter((i) => i.critico).length;
  return (
    <>
      <p className="sub">
        <Link to={q ? `/revisao?${new URLSearchParams({ q })}` : '/revisao'}>← Voltar à busca</Link>
        {primeiro && (
          <>
            {' · '}
            <Link to={`/licitacao/${primeiro.slug}`}>{localDe(primeiro)}</Link> · {primeiro.controle}
          </>
        )}
      </p>
      {fila.isError ? (
        <Falha erro={fila.error} oque="os campos em revisão" />
      ) : !fila.data ? (
        <Carregando />
      ) : !itens.length ? (
        <p className="sub">Nenhuma resposta a revisar nesta licitação.</p>
      ) : (
        <>
          <p className="sub">
            <span>{aRevisar(itens.length)}</span>
            {criticas > 0 && <span>{` · ${milhar(criticas)} ${criticas === 1 ? 'crítica' : 'críticas'}`}</span>}
          </p>
          <TabelaFila itens={itens} />
        </>
      )}
    </>
  );
}

function TabelaFila({ itens }: { itens: ItemRevisao[] }) {
  return (
    <>
      <Legenda />
      <Rolagem min={980}>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Licitação</th>
              <th>Resposta</th>
              <th>Origem</th>
              <th>Verificação</th>
              <th>Decisão</th>
            </tr>
          </thead>
          <tbody>
            {itens.map((i) => {
              const r = comoResposta(i);
              const status = statusDaLinha(r);
              return (
                <tr key={i.id} className={status} data-revisao={i.id}>
                  <td className="qid">
                    {r.pergunta_id}
                    <span className="perg">{r.pergunta}</span>
                    {r.critico && (
                      <span className="marca" title="Entra no cálculo do lance">
                        crítica
                      </span>
                    )}
                  </td>
                  <td>
                    <Link to={`/licitacao/${i.slug}`}>{localDe(i)}</Link>
                    <span className="perg">
                      {i.controle} · prazo {data(i.fim_prazo)}
                    </span>
                    <span className="perg">motivo: {i.motivo ?? '—'}</span>
                  </td>
                  <td>
                    <span className="resposta">{r.resposta}</span>
                    <Evidencia r={r} />
                    {r.conflito && (
                      <details open>
                        <summary>conflito entre documentos</summary>
                        <blockquote className="conf">{r.conflito}</blockquote>
                      </details>
                    )}
                  </td>
                  <td className="info">
                    <Origem slug={i.slug} r={r} status={status} />
                  </td>
                  <td>
                    <PilulaVeredito veredito={r.veredito} />
                  </td>
                  <td>
                    <Decisao item={i} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Rolagem>
    </>
  );
}

// ------------------------------------------------------------ escopo
function Escopo({ controleInicial }: { controleInicial: string }) {
  const me = useSessao();
  const opera = podeOperar(me);
  const rotulos = useRotulosEscopo();
  const [controle, setControle] = useState(controleInicial);
  const [dentro, setDentro] = useState<boolean | null>(null);
  const [motivo, setMotivo] = useState('');
  const gravar = useEnviar<{ controle: string; dentro: boolean; motivo?: string }>(
    (corpo) => ({ caminho: '/api/rotulos-escopo', metodo: 'POST', corpo }),
    ['/api/rotulos-escopo', '/api/licitacoes'],
  );

  if (rotulos.isError) return <Falha erro={rotulos.error} oque="os rótulos de escopo" />;
  if (!rotulos.data) return <Carregando />;
  if (!rotulos.data.disponivel) {
    return (
      <div className="nota">
        A rotulagem manual de escopo ainda não está disponível. O escopo segue as regras de classificação.
      </div>
    );
  }

  const { pendentes, rotuladas } = rotulos.data;
  const itens = rotulos.data.itens.filter((r) => r.rotulo === null);
  const controleOk = RE_CONTROLE.test(controle.trim());
  const motivoBotao = !opera
    ? MOTIVO_SO_OPERADOR
    : !controleOk
      ? 'Informe o controle no formato do PNCP (00000000000000-1-000000/2026).'
      : dentro === null
        ? 'Escolha dentro ou fora do escopo.'
        : null;

  return (
    <>
      <p className="sub">
        Só as licitações em que o Jev discordou da regra com alta confiança e que ainda não foram rotuladas (
        {milhar(pendentes)} {pendentes === 1 ? 'pendente' : 'pendentes'}). As já rotuladas ({milhar(rotuladas)}) saem
        desta lista e o rótulo continua valendo. O rótulo humano é registrado à parte: não altera o escopo da regra e
        serve de referência para avaliar a regra e o Jev.
      </p>
      <p className="lgnota">IA: é folha (N%) = {AVISO_IA_FOLHA}</p>
      {itens.length === 0 ? (
        <p className="sub">Nenhuma licitação pendente de rótulo de escopo.</p>
      ) : (
        <Rolagem min={760}>
          <table>
            <thead>
              <tr>
                <th>Licitação</th>
                <th>Regra</th>
                <th>Jev</th>
                <th>Rótulo humano</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {itens.map((r) => {
                // a chance de SER folha (26/09); API anterior sem p_folha: a do filtro, virada quando a regra diz fora
                const pf = r.jev_filtro?.p_folha ?? null;
                const pok = r.jev_filtro?.p_filtro_ok ?? null;
                const op = opiniaoIa(
                  pf ?? (pok === null ? null : r.escopo_dentro === false ? 1 - Number(pok) : pok),
                );
                return (
                  <tr key={r.controle} data-controle={r.controle}>
                    <td className="info">
                      <Link to={`/licitacao/${r.slug}`}>{localDe(r)}</Link>
                      <span className="perg">
                        {r.controle}
                        {r.modalidade ? ` · ${r.modalidade}` : ''}
                      </span>
                      {r.objeto && <span className="perg">{r.objeto.slice(0, 200)}</span>}
                    </td>
                    <td>
                      <code>{r.escopo_dentro === true ? 'dentro' : r.escopo_dentro === false ? 'fora' : '—'}</code>
                      {r.escopo_motivo && <span className="perg">{r.escopo_motivo}</span>}
                    </td>
                    <td>
                      {op ? (
                        <>
                          <span
                            className={`marca jev ${op.classe}${r.jev_filtro?.discorda ? ' jev-atencao' : ''}`}
                            title={AVISO_IA_FOLHA}
                          >
                            {op.texto}
                          </span>
                          {r.jev_filtro?.discorda && <span className="perg">discorda da regra</span>}
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      {r.rotulo ? (
                        <>
                          <code>{r.rotulo.dentro ? 'dentro' : 'fora'}</code>
                          {r.rotulo.motivo && <span className="perg">{r.rotulo.motivo}</span>}
                          <span className="perg">
                            {r.rotulo.por ?? '—'} · {dataHora(r.rotulo.em)}
                          </span>
                        </>
                      ) : (
                        <span className="nl">pendente</span>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="voltar"
                        disabled={!opera}
                        title={opera ? 'Preenche o formulário abaixo com esta licitação.' : MOTIVO_SO_OPERADOR}
                        onClick={() => setControle(r.controle)}
                      >
                        Rotular
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Rolagem>
      )}
      <div className="pg-painel">
        <form
          className="formulario"
          onSubmit={(e) => {
            e.preventDefault();
            if (motivoBotao || dentro === null) return;
            const corpo: { controle: string; dentro: boolean; motivo?: string } = { controle: controle.trim(), dentro };
            if (motivo.trim()) corpo.motivo = motivo.trim();
            gravar.mutate(corpo, { onSuccess: () => setMotivo('') });
          }}
        >
          <label>
            Controle
            <input
              value={controle}
              disabled={!opera}
              title={opera ? undefined : MOTIVO_SO_OPERADOR}
              onChange={(e) => setControle(e.target.value)}
            />
          </label>
          <label>
            <input type="radio" name="dentro" checked={dentro === true} disabled={!opera} onChange={() => setDentro(true)} />{' '}
            dentro do escopo
          </label>
          <label>
            <input type="radio" name="dentro" checked={dentro === false} disabled={!opera} onChange={() => setDentro(false)} />{' '}
            fora do escopo
          </label>
          <label>
            Motivo
            <input
              value={motivo}
              disabled={!opera}
              title={opera ? undefined : MOTIVO_SO_OPERADOR}
              onChange={(e) => setMotivo(e.target.value)}
            />
          </label>
          <button type="submit" className="secundario" disabled={!!motivoBotao || gravar.isPending} title={motivoBotao ?? undefined}>
            Registrar rótulo
          </button>
          {gravar.isSuccess && <span className="atualmsg">Rótulo registrado.</span>}
          {gravar.isError && (
            <span className="erro" role="alert">
              {gravar.error.message}
            </span>
          )}
        </form>
      </div>
    </>
  );
}

export function Revisao() {
  const [params, setParams] = useSearchParams();
  // A revisão de ESCOPO é só do admin: para os outros a aba nem aparece, e ?aba=escopo abre as respostas.
  const admin = ehAdmin(useSessao());
  const aba = admin && params.get('aba') === 'escopo' ? 'escopo' : 'respostas';
  // O número da aba vem da lista leve (os totais), nunca da fila inteira.
  const abertas = useLicitacoesEmRevisao('').data?.total_revisoes;

  function irPara(nova: 'respostas' | 'escopo') {
    const p = new URLSearchParams(params);
    if (nova === 'respostas') p.delete('aba');
    else p.set('aba', nova);
    setParams(p, { replace: true });
  }

  return (
    <div className="pg-relatorio">
      <div className="wrap">
        <header>
          <p className="eyebrow">FOPA · revisão humana</p>
          <h1>Revisão</h1>
          <p className="sub">
            Itens que exigem revisão humana. Cada decisão é registrada com responsável e data, sem alterar a resposta do
            modelo nem o veredito do verificador; o histórico permanece auditável.
          </p>
        </header>
        {admin && (
          <div className="pg-painel">
            <div className="barra">
              <button type="button" aria-pressed={aba === 'respostas'} onClick={() => irPara('respostas')}>
                Respostas{abertas !== undefined ? ` (${milhar(abertas)})` : ''}
              </button>
              <button type="button" aria-pressed={aba === 'escopo'} onClick={() => irPara('escopo')}>
                Escopo
              </button>
            </div>
          </div>
        )}
        {aba === 'respostas' && (
          <section className="revisao-guia">
            {!admin && <h2>Respostas a revisar{abertas !== undefined ? ` (${milhar(abertas)})` : ''}</h2>}
            <ComoRevisar />
          </section>
        )}
        {aba === 'respostas' ? (
          <RevisaoPorLicitacao q={(params.get('q') ?? '').trim()} controle={(params.get('controle') ?? '').trim()} />
        ) : (
          <Escopo controleInicial={params.get('controle') ?? ''} />
        )}
      </div>
    </div>
  );
}
