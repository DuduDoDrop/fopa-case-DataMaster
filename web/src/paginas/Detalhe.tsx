/**
 * `/licitacao/:slug` — o RELATORIO.html (pagina.py) como página viva:
 * cabeçalho, procedência, tiles da verificação, "como conferir", alertas,
 * condições ACIMA do questionário, as 17, divergências, documentos,
 * histórico de verificações, revisões humanas e linha do tempo. As classes
 * são as de relatorio.css; os blocos de ação usam as de painel.css
 * (`.achados`).
 *
 * O contrato é o de `GET /api/licitacoes/{slug}` (api/consultas.py:detalhe):
 * `respostas` (do modelo) e `verificacao_respostas` (do verificador) chegam
 * SEPARADAS e o site junta por pergunta; o histórico é `historico`.
 */
import '../../design/relatorio.css';
import '../../design/painel.css';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useEnviar, useLicitacao, useModelosIa, useResumo } from '../api/consultas';
import type {
  Arquivo,
  Detalhe as TDetalhe,
  LicitacaoCompleta,
  RespostaDetalhe,
  RevisaoHumana,
  VerificacaoHistorico,
  WorkflowDaLicitacao,
} from '../api/tipos';
import { Condicoes, temCondicoes } from '../componentes/Condicoes';
import { Confirmacao } from '../componentes/Confirmacao';
import { EscolhaIa, escolhaPadrao, type Escolha } from '../componentes/EscolhaIa';
import { TabelaArquivos } from '../componentes/Documentos';
import { Carregando, Falha } from '../componentes/Estado';
import { MarcaProcedencia } from '../componentes/MarcaProcedencia';
import { nomeProvedor, rodouLocal } from '../lib/procedencia';
import { Decisao } from './Revisao';
import { PrazoBadge } from '../componentes/PrazoBadge';
import { Rolagem } from '../componentes/Rolagem';
import { ehAdmin, useSessao } from '../componentes/Sessao';
import { Legenda, TabelaRespostas } from '../componentes/TabelaRespostas';
import { useAgora } from '../lib/agora';
import { ACOMPANHAR_MAX_MS, ACOMPANHAR_MS, ESTADOS_SEM_TEXTO, aindaAndando } from '../lib/acompanhar';
import { ESTIMATIVA_REVERIFICAR, estimativaPorEdital, gastaApi } from '../lib/estimativa';
import {
  custo,
  custoRodada,
  dataHora,
  datasNoTexto,
  duracao,
  milhar,
  numero,
  PRECO_NAO_CONFIGURADO,
  SEM_API_LOCAL,
  SEM_CHAMADA_REGISTRADA,
} from '../lib/formato';
import { calcularPrazo, dataDaQ1 } from '../lib/prazo';
import { mesclarRespostas } from '../lib/respostas';

function TilesVerificacao({ l, respostas }: { l: TDetalhe; respostas: RespostaDetalhe[] }) {
  const taxa = numero(l.taxa_ancorada) ?? 0;
  const criticas = respostas.filter((r) => r.critico);
  const critOk = criticas.filter((r) => r.veredito === 'APROVADO').length;
  const textoCusto = custo(l);
  return (
    <div className="tiles">
      <div className={taxa >= 0.95 ? 'tile ok' : 'tile al'}>
        <b>
          {milhar(l.ancoradas)}/{milhar(l.respondidas)}
        </b>
        <span>ancoragem verificada</span>
      </div>
      <div className="tile">
        <b>{milhar(l.aprovadas)}</b>
        <span>aprovadas sem ressalva</span>
      </div>
      <div className={l.revisar > 0 ? 'tile al' : 'tile'}>
        <b>{milhar(l.revisar)}</b>
        <span>para revisão</span>
      </div>
      <div className={l.reprovadas > 0 ? 'tile al' : 'tile ok'}>
        <b>{milhar(l.reprovadas)}</b>
        <span>reprovadas</span>
      </div>
      <div className="tile">
        <b>
          {critOk}/{criticas.length}
        </b>
        <span>críticas aprovadas</span>
      </div>
      {textoCusto === SEM_API_LOCAL ? (
        <div className="tile">
          <b>local</b>
          <span>sem serviço pago</span>
        </div>
      ) : textoCusto === PRECO_NAO_CONFIGURADO ? (
        <div className="tile">
          <b>—</b>
          <span>{PRECO_NAO_CONFIGURADO}</span>
        </div>
      ) : (
        <div className="tile">
          <b>{textoCusto.replace(' (legado)', '')}</b>
          <span>custo da extração{textoCusto.endsWith('(legado)') ? ' (legado)' : ''}</span>
        </div>
      )}
    </div>
  );
}

function Procedencia({ l }: { l: TDetalhe }) {
  if (!l.execucao_id) return null;
  // Rodou local: tokens, tempo e custo não existem para medir — a linha diz isso em vez de "0 tokens · 0,0 s".
  const partes = rodouLocal(l.procedencia) ? [nomeProvedor(l.provedor), l.modelo, 'extração local, sem serviço pago; tokens, tempo e custo não medidos'] : [
    nomeProvedor(l.provedor),
    l.modelo,
    l.effort ? `effort ${l.effort}` : null,
    l.modo ? `modo ${l.modo}` : null,
    l.chamadas !== null ? `${milhar(l.chamadas)} ${l.chamadas === 1 ? 'chamada' : 'chamadas'}` : null,
    l.tok_entrada !== null ? `${milhar(l.tok_entrada)} tokens de entrada` : null,
    l.tok_saida !== null ? `${milhar(l.tok_saida)} de saída` : null,
    l.segundos !== null ? duracao(l.segundos) : null,
    custo(l),
  ].filter(Boolean);
  return (
    <>
      <p className="sub procedencia">
        <MarcaProcedencia origem={l.procedencia} provedor={l.provedor} /> {partes.join(' · ')}
        {l.versao_prompt && (
          <>
            {' '}
            · prompt <code>{l.versao_prompt.slice(0, 12)}</code>
          </>
        )}
        {l.versao_regras && (
          <>
            {' '}
            · regras <code>{l.versao_regras.slice(0, 12)}</code>
          </>
        )}
      </p>
      {l.procedencia_completa === false && (
        <div className="cond deg">
          <b>Procedência incompleta.</b> A importação não comprovou de qual execução vieram estas respostas; os números
          de custo e de tokens são aproximados.
        </div>
      )}
    </>
  );
}

/**
 * Rodapé do RELATORIO (pagina.py): modelo · chamadas · tokens de entrada ·
 * "verificação determinística, sem IA". O que não foi medido não vira zero:
 * o agente não conta tokens, e licitação sem extração não tem modelo — o
 * rodapé dizia "- · 0 chamada(s) ao modelo · 0 tokens de entrada".
 */
export function rodape(l: Pick<TDetalhe, 'execucao_id' | 'modelo' | 'chamadas' | 'tok_entrada'>): string {
  const deterministica = 'verificação determinística, sem IA';
  if (!l.execucao_id) return `ainda não extraída · ${deterministica}`;
  return [
    l.modelo,
    l.chamadas === null ? null : `${milhar(l.chamadas)} ${l.chamadas === 1 ? 'chamada' : 'chamadas'} ao modelo`,
    l.tok_entrada === null ? 'tokens de entrada não medidos' : `${milhar(l.tok_entrada)} tokens de entrada`,
    deterministica,
  ]
    .filter(Boolean)
    .join(' · ');
}

/** Diff de vereditos entre cada verificação e a anterior a ela. */
export function diffVereditos(atual: VerificacaoHistorico, anterior: VerificacaoHistorico | undefined): string[] {
  if (!anterior || !atual.vereditos || !anterior.vereditos) return [];
  const ids = Array.from(new Set([...Object.keys(atual.vereditos), ...Object.keys(anterior.vereditos)])).sort(
    (a, b) => Number(a.slice(1)) - Number(b.slice(1)),
  );
  return ids
    .filter((id) => atual.vereditos![id] !== anterior.vereditos![id])
    .map((id) => `${id}: ${anterior.vereditos![id] ?? '—'} → ${atual.vereditos![id] ?? '—'}`);
}

function Historico({ historico }: { historico: VerificacaoHistorico[] }) {
  const ordenadas = [...historico].sort((a, b) => (a.verificado_em < b.verificado_em ? 1 : -1));
  if (!ordenadas.length) return <p className="sub">Nenhuma verificação registrada.</p>;
  return (
    <Rolagem min={640}>
      <table>
        <thead>
          <tr>
            <th>Quando</th>
            <th>Regras</th>
            <th>Resultado</th>
            <th>Mudanças em relação à anterior</th>
          </tr>
        </thead>
        <tbody>
          {ordenadas.map((v, i) => {
            const diff = diffVereditos(v, ordenadas[i + 1]);
            return (
              <tr key={v.id}>
                <td className="info">
                  {dataHora(v.verificado_em)}
                  {v.vigente && (
                    <>
                      {' '}
                      <span className="marca">vigente</span>
                    </>
                  )}
                </td>
                <td className="info">
                  <code>{v.versao_regras.replace(/^legado:/, 'legado ').slice(0, 19)}</code>
                  {v.origem && (
                    <>
                      {' '}
                      <MarcaProcedencia origem={v.origem} provedor={v.provedor ?? null} />
                    </>
                  )}
                </td>
                <td>
                  {milhar(v.aprovadas)} aprovadas · {milhar(v.revisar)} revisar · {milhar(v.reprovadas)} reprovadas ·{' '}
                  {milhar(v.nao_localizado)} não localizado
                </td>
                <td>
                  {i === ordenadas.length - 1 ? (
                    <span className="nl">primeira verificação</span>
                  ) : diff.length ? (
                    diff.map((d) => (
                      <span key={d} className="diffv">
                        {d}
                      </span>
                    ))
                  ) : (
                    <span className="nl">nenhum veredito alterado</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Rolagem>
  );
}

function LinhaDoTempo({ eventos }: { eventos: LicitacaoCompleta['eventos'] }) {
  const ordenados = [...eventos].sort((a, b) => (a.em < b.em ? 1 : -1));
  if (!ordenados.length) return <p className="sub">Sem eventos registrados.</p>;
  return (
    <Rolagem min={600}>
      <table>
        <thead>
          <tr>
            <th>Quando</th>
            <th>Transição</th>
            <th>Motivo</th>
            <th>Execução</th>
          </tr>
        </thead>
        <tbody>
          {ordenados.map((e) => (
            <tr key={e.id}>
              <td className="info">{dataHora(e.em)}</td>
              <td className="info">
                <code>{e.de ?? 'nascimento'}</code> → <code>{e.para}</code>
              </td>
              <td>{e.motivo ?? '—'}</td>
              <td className="info">
                {e.n8n_execution_id ? <code>#{e.n8n_execution_id}</code> : <span className="nl">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Rolagem>
  );
}

function Revisoes({ revisoes, controle }: { revisoes: RevisaoHumana[]; controle: string }) {
  if (!revisoes.length) return <p className="sub">Nenhuma revisão humana registrada.</p>;
  return (
    <Rolagem min={600}>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Motivo</th>
            <th>Decisão</th>
            <th>Responsável e data</th>
          </tr>
        </thead>
        <tbody>
          {revisoes.map((r) => (
            <tr key={r.id}>
              <td className="qid">{r.pergunta_id ?? '—'}</td>
              <td>{r.motivo ?? '—'}</td>
              <td>
                <code>{r.status}</code>
                {r.resposta_corrigida && <span className="resposta"> — {r.resposta_corrigida}</span>}
                {r.nota && <span className="perg">{r.nota}</span>}
                {/* Plano §8: o operador decide aqui mesmo, sem ir à fila — o mesmo formulário da /revisao. */}
                {r.status === 'aberta' && <Decisao item={r} />}
              </td>
              <td className="info">
                {r.decidido_por ? (
                  <>
                    {r.decidido_por} · {dataHora(r.decidido_em)}
                  </>
                ) : (
                  <>
                    aberta desde {dataHora(r.criado_em)} ·{' '}
                    <Link to={`/revisao?controle=${encodeURIComponent(controle)}`}>abrir na fila de revisão</Link>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Rolagem>
  );
}

function Workflows({ itens }: { itens: WorkflowDaLicitacao[] }) {
  if (!itens.length) return null;
  return (
    <Rolagem min={600}>
      <table>
        <thead>
          <tr>
            <th>Quando</th>
            <th>Processamento</th>
            <th>Custo</th>
            <th>Resultado</th>
          </tr>
        </thead>
        <tbody>
          {itens.map((w) => (
            <tr key={w.id}>
              <td className="info">{dataHora(w.iniciado_em)}</td>
              <td className="info">
                <code>{w.workflow}</code>
                {w.n8n_execution_id ? ` · execução nº ${w.n8n_execution_id}` : ''}
                {w.duracao_s !== null ? ` · ${duracao(w.duracao_s)}` : ''}
              </td>
              <td title={custoRodada(w) === '—' ? SEM_CHAMADA_REGISTRADA : undefined}>{custoRodada(w)}</td>
              <td>
                {w.status ?? '—'}
                {w.cego ? ' · coleta incompleta' : ''}
                {w.erro ? ` · ${datasNoTexto(w.erro)}` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Rolagem>
  );
}

type Acao = 'processar' | 'reverificar' | 'gpt' | null;

/** O que o W11 devolve pelas ações (o site repassa como veio: api/site.py:_chamar_n8n). */
interface RespostaAcao {
  execucao_id?: number;
  job_id?: string;
  verificacao_id?: number;
  aceitos?: string[];
  recusados?: unknown[];
}

function Acoes({
  l,
  arquivos,
  provedor,
  aoAcompanhar,
}: {
  l: TDetalhe;
  arquivos: Arquivo[];
  provedor: string | null;
  /** o pedido foi aceito: a página passa a acompanhar o processamento (lib/acompanhar.ts) */
  aoAcompanhar: () => void;
}) {
  const me = useSessao();
  const [aberta, setAberta] = useState<Acao>(null);
  const seAceito = { onSuccess: (r: RespostaAcao | undefined) => (r?.recusados?.length ? undefined : aoAcompanhar()) };
  const processar = useEnviar<void, RespostaAcao>(
    () => ({ caminho: '/api/acoes/processar', metodo: 'POST', corpo: { controles: [l.controle] } }),
    ['/api/licitacoes', '/api/execucoes'],
  );
  const reverificar = useEnviar<void, RespostaAcao>(
    () => ({ caminho: '/api/acoes/reverificar', metodo: 'POST', corpo: { controle: l.controle } }),
    ['/api/licitacoes'],
  );
  // O botão "Extrair com IA": pedido para ESTA licitação (db/033), com o provedor, o modelo e o esforço
  // escolhidos (db/037; api/modelos_ia.py); o provedor global não muda.
  const catalogo = useModelosIa();
  const [escolha, setEscolha] = useState<Escolha | null>(null);
  const escolhaAtual = escolha ?? (catalogo.data ? escolhaPadrao(catalogo.data) : null);
  const gpt = useEnviar<Escolha, RespostaAcao>(
    (e) => ({
      caminho: '/api/acoes/extrair-ia',
      metodo: 'POST',
      corpo: { controle: l.controle, provedor: e.provedor, modelo: e.modelo },
    }),
    ['/api/licitacoes', '/api/execucoes'],
  );
  // Os botões da API: para os outros papéis eles nem são desenhados.
  const admin = ehAdmin(me);
  const motivoReverificar = !l.extraida ? 'Não há verificação para refazer: a licitação ainda não foi extraída.' : null;
  const motivoProcessar = null;
  // Sem texto para ler (Vale de São Domingos, 25/09: o edital era RTF com nome .pdf), o pedido nunca seria usado.
  const semTexto = ESTADOS_SEM_TEXTO.has(l.estado);
  const porQueSemTexto = [...new Set(arquivos.filter((a) => a.status === l.estado && a.motivo).map((a) => a.motivo))].join('; ');
  const motivoGpt =
    motivoProcessar ??
    (semTexto
      ? `O edital não está em PDF legível (${porQueSemTexto || l.estado}). Sem texto, não há o que extrair; o sistema processa apenas PDF.`
      : null);

  function feito(r: RespostaAcao | undefined) {
    const id = r?.execucao_id ?? r?.job_id ?? r?.verificacao_id;
    const recusados = r?.recusados ?? [];
    if (recusados.length) {
      return <>O processamento recusou o pedido: {recusados.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join('; ')}.</>;
    }
    return (
      <>
        Pedido aceito{id !== undefined ? ` (execução ${id})` : ''}. Esta página é atualizada automaticamente durante o
        processamento; o detalhe de cada etapa está em <Link to="/execucoes">Execuções</Link>.
      </>
    );
  }

  return (
    <>
      <div className="rodape-nav">
        {/* Sem o botão "Abrir RELATORIO": esta
            página já mostra as respostas. O RELATORIO segue gerado na publicação e com rota própria
            (/licitacao/:slug/relatorio) — é para ele que o e-mail da extração aponta. */}
        {l.link && (
          <a className="voltar" href={l.link} target="_blank" rel="noopener">
            Abrir no PNCP
          </a>
        )}
        {admin && (
          <>
        <button
          type="button"
          className="voltar"
          disabled={!!motivoReverificar}
          title={motivoReverificar ?? 'Refaz a verificação com as regras atuais, sem chamar o modelo.'}
          onClick={() => setAberta('reverificar')}
        >
          Reverificar
        </button>
        <button
          type="button"
          className="voltar"
          disabled={!!motivoProcessar}
          title={motivoProcessar ?? `Refaz a extração com o provedor vigente (${provedor ?? 'não informado'}).`}
          onClick={() => setAberta('processar')}
        >
          {l.extraida ? 'Processar novamente' : 'Processar'}
        </button>
        <button
          type="button"
          className="voltar gpt"
          disabled={!!motivoGpt}
          title={motivoGpt ?? 'Extrai esta licitação com o modelo selecionado (serviço pago); o provedor geral não muda.'}
          onClick={() => setAberta('gpt')}
        >
          Extrair com IA
        </button>
          </>
        )}
      </div>
      <div className="pg-painel">
        {aberta === 'processar' && (
          <Confirmacao
            rotulo="Confirmar processamento"
            titulo={l.extraida ? 'Processar novamente esta licitação?' : 'Processar esta licitação?'}
            confirmar="Confirmar e processar"
            aoConfirmar={() => processar.mutate(undefined, seAceito)}
            aoCancelar={() => setAberta(null)}
            ocupado={processar.isPending}
            erro={processar.isError ? processar.error.message : null}
            feito={processar.isSuccess ? feito(processar.data) : undefined}
          >
            <p>
              Provedor vigente: <b>{provedor ?? 'desconhecido'}</b> · custo estimado: <b>{estimativaPorEdital(provedor)}</b>
            </p>
            {gastaApi(provedor) ? (
              <p className="alerta">Este provedor é um serviço pago. A execução vigente é preservada; a nova gera outra verificação.</p>
            ) : (
              <p>Sem serviço pago. A execução vigente é preservada; a nova gera outra verificação.</p>
            )}
          </Confirmacao>
        )}
        {aberta === 'gpt' && (
          <Confirmacao
            rotulo="Confirmar extração com IA"
            titulo="Extrair esta licitação com IA?"
            confirmar="Confirmar e extrair"
            aoConfirmar={() => escolhaAtual && gpt.mutate(escolhaAtual, seAceito)}
            aoCancelar={() => setAberta(null)}
            ocupado={gpt.isPending || !escolhaAtual}
            erro={gpt.isError ? gpt.error.message : catalogo.isError ? 'Não foi possível carregar o catálogo de modelos.' : null}
            feito={gpt.isSuccess ? feito(gpt.data) : undefined}
          >
            {catalogo.data && escolhaAtual ? (
              <EscolhaIa catalogo={catalogo.data} escolha={escolhaAtual} aoMudar={setEscolha} />
            ) : (
              <p>Carregando os modelos…</p>
            )}
            <p className="alerta">
              Executa a extração desta licitação com o provedor selecionado (serviço pago), incluindo download e leitura,
              quando necessários, verificação e publicação. O provedor geral continua{' '}
              <b>{provedor ?? 'o atual'}</b>, e o processamento automático diário não passa a gerar custo. A execução
              vigente é preservada; a nova gera outra verificação.
            </p>
          </Confirmacao>
        )}
        {aberta === 'reverificar' && (
          <Confirmacao
            rotulo="Confirmar reverificação"
            titulo="Reverificar com as regras atuais?"
            confirmar="Confirmar e reverificar"
            aoConfirmar={() => reverificar.mutate(undefined, seAceito)}
            aoCancelar={() => setAberta(null)}
            ocupado={reverificar.isPending}
            erro={reverificar.isError ? reverificar.error.message : null}
            feito={reverificar.isSuccess ? feito(reverificar.data) : undefined}
          >
            <p>
              Custo: <b>{ESTIMATIVA_REVERIFICAR}</b>. As respostas não mudam; apenas os vereditos podem mudar, e o
              histórico registra as alterações.
            </p>
          </Confirmacao>
        )}
      </div>
    </>
  );
}

export function Detalhe() {
  const { slug } = useParams();
  const agora = useAgora();
  const qc = useQueryClient();
  // Depois de uma ação aceita, a página acompanha o processamento sozinha (lib/acompanhar.ts): `estado` é o do
  // clique, `mudou` diz se o fluxo já saiu dele.
  const [acomp, setAcomp] = useState<{ desde: number; estado: string; mudou: boolean } | null>(null);
  const consulta = useLicitacao(slug, true, acomp ? ACOMPANHAR_MS : false);
  const resumo = useResumo();
  const estadoAgora = consulta.data?.licitacao.estado;
  const pedidoPendente = !!consulta.data?.pedido_ia;

  useEffect(() => {
    if (!acomp || !estadoAgora) return;
    const mudou = acomp.mudou || estadoAgora !== acomp.estado;
    if (Date.now() - acomp.desde > ACOMPANHAR_MAX_MS || (mudou && !aindaAndando(estadoAgora, pedidoPendente))) {
      setAcomp(null);
      // parou: o gasto (tiles e custo) e as execuções também mudaram
      for (const k of ['/api/resumo', '/api/custo', '/api/execucoes']) qc.invalidateQueries({ queryKey: [k] });
    } else if (mudou !== acomp.mudou) {
      setAcomp({ ...acomp, mudou });
    }
  }, [acomp, estadoAgora, pedidoPendente, consulta.dataUpdatedAt, qc]);

  if (consulta.isError) {
    return (
      <div className="pg-relatorio">
        <div className="wrap">
          <Link className="voltar" to="/">
            <b>←</b> Voltar ao painel
          </Link>
          <Falha erro={consulta.error} oque="a licitação" />
        </div>
      </div>
    );
  }
  if (!consulta.data) {
    return (
      <div className="pg-relatorio">
        <div className="wrap">
          <Carregando />
        </div>
      </div>
    );
  }

  const { licitacao: l, arquivos, historico, eventos, revisoes, execucoes_workflow: workflows, jev } = consulta.data;
  const respostas = mesclarRespostas(consulta.data.respostas, consulta.data.verificacao_respostas);
  const jevSustenta = jev?.sustenta ?? null;
  const temJev = !!jevSustenta && respostas.some((r) => jevSustenta[r.pergunta_id]);
  const prazo = calcularPrazo({ ...l, sessao_q1: dataDaQ1(respostas) }, agora);
  const meta = [l.modalidade || 'modalidade não informada', l.controle, l.orgao].filter(Boolean).join(' · ');
  const conflitos = respostas.filter((r) => r.conflito);
  const alertas = l.alertas_globais ?? [];

  return (
    <div className="pg-relatorio">
      <div className="wrap">
        <Link className="voltar" to="/">
          <b>←</b> Voltar ao painel
        </Link>

        <header className="cabecalho">
          <div>
            <p className="eyebrow">{l.extraida ? 'FOPA · extração verificada' : 'FOPA · licitação'}</p>
            <h1>{l.local}</h1>
            <p className="sub">{meta}</p>
            {l.objeto && <p className="sub">{l.objeto}</p>}
            <p className="sub">
              Estado <code>{l.estado}</code>
              {l.estado_motivo ? ` — ${l.estado_motivo}` : ''} · {milhar(l.n_arquivos)}{' '}
              {l.n_arquivos === 1 ? 'arquivo' : 'arquivos'} ·{' '}
              {l.leitura_id ? `${milhar(l.n_paginas)} páginas (${milhar(l.n_paginas_ocr)} por OCR)` : 'páginas ainda não lidas'}
            </p>
          </div>
          <div className="pg-painel">
            <PrazoBadge prazo={prazo} />
          </div>
        </header>

        {ESTADOS_SEM_TEXTO.has(l.estado) && (
          // Sem arquivo PDF válido, o aviso aparece
          <div className="aviso-sem-pdf" role="alert" aria-label="Sem PDF válido">
            <b>Sem PDF válido.</b>{' '}
            {[...new Set(arquivos.filter((a) => a.status === l.estado && a.motivo).map((a) => a.motivo))].join('; ') ||
              'nenhum documento com texto legível'}
            . O sistema processa apenas PDF, e esta licitação não pode ser extraída. Solicite o PDF ao órgão; quando o PNCP
            disponibilizar o arquivo, use "Processar" para baixá-lo novamente.
          </div>
        )}
        <Procedencia l={l} />
        {consulta.data.pedido_ia && (
          <p className="sub alerta">
            Pedido de extração com IA pendente desde {dataHora(consulta.data.pedido_ia.pedido_em)} (
            {consulta.data.pedido_ia.pedido_por}):{' '}
            {[consulta.data.pedido_ia.provedor, consulta.data.pedido_ia.modelo, consulta.data.pedido_ia.effort]
              .filter(Boolean)
              .join(' · ')}{' '}
            . O pedido será usado quando a extração começar
            {ESTADOS_SEM_TEXTO.has(l.estado) ? '; como o edital não tem texto legível, a extração não será iniciada' : ''}.
          </p>
        )}
        {acomp && (
          <p className="sub atualmsg" role="status">
            Processamento em andamento. A página é atualizada automaticamente a cada etapa: download, leitura, extração,
            verificação e publicação.
          </p>
        )}
        <Acoes
          l={l}
          arquivos={arquivos}
          provedor={resumo.data?.provedor ?? null}
          aoAcompanhar={() => setAcomp({ desde: Date.now(), estado: l.estado, mudou: false })}
        />

        {l.extraida ? (
          <>
            <TilesVerificacao l={l} respostas={respostas} />

            <div className="nota">
              <b>Como conferir:</b> cada resposta cita o arquivo e a <b>página física</b>. O link em <i>Origem</i>{' '}
              abre o PDF exatamente nessa página. O trecho literal, em “Ver evidência”, foi conferido por comparação de
              texto com essa página, sem uso de IA. <b>Toda</b> resposta traz o bloco de evidência; quando ele informa que
              não há trecho, isso também é um resultado. Perguntas marcadas como <b>crítica</b> são as que influenciam o
              lance; o vermelho indica sempre um defeito.
            </div>

            {alertas.length > 0 && (
              <>
                <h2>Alertas</h2>
                <div className="nota">
                  {alertas.map((a, i) => (
                    <span key={i}>
                      {i > 0 && <br />}⚠ {a}
                    </span>
                  ))}
                </div>
              </>
            )}

            {temCondicoes(l.condicoes) && (
              <>
                <h2>Condições desta execução</h2>
                <Condicoes
                  c={l.condicoes}
                  tagsExtras={l.tags ?? []}
                  furtivos={consulta.data.furtivos ?? []}
                  varredura={consulta.data.furtivos_varredura ?? null}
                />
              </>
            )}

            <h2>Questionário</h2>
            <Legenda comJev={temJev} />
            <TabelaRespostas
              slug={l.slug}
              respostas={respostas}
              q13={l.q13_estruturada}
              jevSustenta={temJev ? jevSustenta : null}
              melhorDeN={consulta.data.melhor_de_n?.perguntas ?? null}
            />

            {conflitos.length > 0 && (
              <>
                <h2>Divergências entre documentos ({conflitos.length})</h2>
                <Rolagem min={600}>
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>O que diverge</th>
                        <th>Resposta adotada</th>
                      </tr>
                    </thead>
                    <tbody>
                      {conflitos.map((r) => (
                        <tr key={r.pergunta_id}>
                          <td className="qid">{r.pergunta_id}</td>
                          <td>{r.conflito}</td>
                          <td>{r.resposta.slice(0, 220)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Rolagem>
              </>
            )}
          </>
        ) : (
          <div className="nota">
            Esta licitação ainda não foi extraída; não há respostas para conferir. Documentos, estado e linha do tempo
            estão abaixo.
          </div>
        )}

        <h2>Documentos</h2>
        <TabelaArquivos slug={l.slug} arquivos={arquivos} />

        <h2>Histórico de verificações</h2>
        <Historico historico={historico} />

        <h2>Revisões humanas</h2>
        <Revisoes revisoes={revisoes} controle={l.controle} />

        <h2>Linha do tempo</h2>
        <LinhaDoTempo eventos={eventos} />
        <Workflows itens={workflows} />

        <footer>{rodape(l)}</footer>
      </div>
    </div>
  );
}
