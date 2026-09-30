/**
 * O que cada instituição financeira comprou: embaixo do gráfico, a instituição num filtro pesquisável e, abaixo, a
 * grade com a licitação comprada, a rodada de publicação, o preço e a data da compra, com o filtro de período ao
 * lado, igual ao de cima. A coluna do contrato — valor com os aditivos e
 * até quando vale — é o dado novo da API do PNCP (db/049).
 *
 * Tudo mora na URL, com nomes próprios para não brigar com os filtros de cima: `banco`, `bde`, `bate`, `bpagina`,
 * `bitens`. O período olha a DATA DA COMPRA. O escopo segue a caixa "mostrar fora do escopo" da página: por padrão só
 * FOPA; com a caixa, o que está fora do escopo entra marcado, distinguido do que é FOPA.
 */
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useComprasPorBanco } from '../api/consultas';
import type { BancoComprador } from '../api/tipos';
import { brl, data, milhar } from '../lib/formato';
import { AVISO_FORA_DO_ESCOPO } from '../lib/respostas';
import { linkPncp } from '../paginas/AnalyticsHistorico';
import { Carregando, Falha } from './Estado';
import { dataDaUrl, FiltroDatas } from './FiltroDatas';
import { Lista } from './Lista';
import { Paginacao, rolarAoTopo, trecho } from './Paginacao';
import { Rolagem } from './Rolagem';

// 10 por vez, como as outras tabelas
const QUANTOS = [
  { chave: '10', n: 10 },
  { chave: '50', n: 50 },
  { chave: '100', n: 100 },
  { chave: 'todos', n: Infinity },
];
const RE_BANCO = /^\d{8}(\d{6})?$/;

/** O nome de cada banco na lista; dois com o mesmo nome (CNPJ-raiz diferentes) levam a raiz junto. */
export function rotulosDosBancos(bancos: BancoComprador[]): Map<string, BancoComprador> {
  const vezes = new Map<string, number>();
  for (const b of bancos) vezes.set(b.banco, (vezes.get(b.banco) ?? 0) + 1);
  return new Map(bancos.map((b) => [(vezes.get(b.banco) ?? 0) > 1 ? `${b.banco} · ${b.cnpj_raiz}` : b.banco, b]));
}

const semAcento = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toLowerCase();

export function ComprasPorBanco({ escopoTodos, soFopaIa, anos }: { escopoTodos: boolean; soFopaIa: boolean; anos: number[] }) {
  const [params, setParams] = useSearchParams();
  // o container da tabela: passar de página ou trocar a quantidade leva a tela ao alto dele
  const topo = useRef<HTMLDivElement>(null);
  const banco = RE_BANCO.test(params.get('banco') ?? '') ? params.get('banco') : null;
  const de = dataDaUrl(params.get('bde'));
  const ate = dataDaUrl(params.get('bate'));
  const quantos = QUANTOS.find((x) => x.chave === params.get('bitens')) ?? QUANTOS[0];
  const consulta = useComprasPorBanco({ escopoTodos, soFopaIa, banco, de, ate });
  const d = consulta.data;
  const rotulos = rotulosDosBancos(d?.bancos ?? []);
  const [texto, setTexto] = useState('');

  // quem chega pelo link (o banco já na URL) vê o nome dele no campo assim que a lista chega
  const nomeDaUrl = banco ? ([...rotulos].find(([, b]) => b.cnpj_raiz === banco.slice(0, 8))?.[0] ?? null) : null;
  useEffect(() => {
    if (nomeDaUrl) setTexto((t) => t || nomeDaUrl);
  }, [nomeDaUrl]);

  // Mudar banco ou período volta à primeira página; só a paginação mexe em `bpagina`.
  function mudar(novos: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    if (!('bpagina' in novos)) p.delete('bpagina');
    for (const [k, v] of Object.entries(novos)) {
      if (v === null || v === '') p.delete(k);
      else p.set(k, v);
    }
    setParams(p, { replace: true });
  }

  function digitar(v: string) {
    setTexto(v);
    const alvo = semAcento(v);
    const achado = rotulos.get(v) ?? [...rotulos].find(([r]) => semAcento(r) === alvo)?.[1];
    if (achado) mudar({ banco: achado.cnpj_raiz });
    else if (!alvo) mudar({ banco: null });
  }

  const compras = d?.banco ? d.compras : [];
  const paginas = Number.isFinite(quantos.n) ? Math.max(1, Math.ceil(compras.length / quantos.n)) : 1;
  const pagina = Math.min(paginas, Math.max(1, Number(params.get('bpagina') ?? 1) || 1));
  const visiveis = Number.isFinite(quantos.n) ? compras.slice((pagina - 1) * quantos.n, pagina * quantos.n) : compras;
  const irParaPagina = (n: number) => mudar({ bpagina: n > 1 ? String(n) : null });
  const nomeBanco = d?.banco?.banco ?? nomeDaUrl ?? 'esta instituição';

  return (
    <section className="compras-banco">
      <h2>O que cada instituição financeira comprou</h2>
      <p className="sub contador">
        <label className="busca-banco">
          <span aria-hidden="true">Instituição financeira</span>
          <input
            type="search"
            list="bancos-compradores"
            aria-label="Instituição financeira"
            placeholder="Digite o nome da instituição"
            value={texto}
            onChange={(e) => digitar(e.target.value)}
          />
        </label>
        <datalist id="bancos-compradores">
          {[...rotulos].map(([r, b]) => (
            <option key={b.cnpj_raiz} value={r} label={`${milhar(b.licitacoes)} ${b.licitacoes === 1 ? 'licitação' : 'licitações'}`} />
          ))}
        </datalist>
        <FiltroDatas rotulo="Período da compra" acao="comprada" de={de} ate={ate} anos={anos} aoMudar={(novoDe, novoAte) => mudar({ bde: novoDe, bate: novoAte })} />
      </p>
      {consulta.isError ? (
        <Falha erro={consulta.error} oque="as compras por instituição financeira" />
      ) : !d ? (
        <Carregando />
      ) : !banco ? (
        <p className="vazio">
          Selecione uma das {milhar(d.bancos.length)} instituições financeiras que compraram folha para ver as licitações
          adquiridas.
        </p>
      ) : compras.length === 0 ? (
        <p className="vazio">
          Nenhuma licitação comprada por {nomeBanco} {de || ate ? 'no período' : 'no histórico'}.
        </p>
      ) : (
        <>
          <p className="sub resumo-banco">
            {nomeBanco}: <b>{milhar(d.total.licitacoes)}</b> {d.total.licitacoes === 1 ? 'licitação comprada' : 'licitações compradas'} ·{' '}
            <b>{brl(d.total.valor)}</b> homologados{de || ate ? ' no período' : ''}.
          </p>
          <div className="barra">
            <Lista
              rotulo="Mostrar compras"
              valor={quantos.chave}
              opcoes={QUANTOS.map((x) => ({ valor: x.chave, texto: x.chave === 'todos' ? 'Todas' : `${x.chave} por página` }))}
              aoMudar={(v) => {
                mudar({ bitens: v === '10' ? null : v });
                rolarAoTopo(topo);
              }}
            />
            <span className="sha">{trecho(pagina, Number.isFinite(quantos.n) ? quantos.n : compras.length, visiveis.length, compras.length)}</span>
          </div>
          <div className="grade-lista" ref={topo}>
            <Paginacao posicao="topo" pagina={pagina} paginas={paginas} topo={topo} irPara={irParaPagina} />
            <Rolagem min={760}>
              <table className="compras-do-banco">
                <thead>
                  <tr>
                    <th>Licitação</th>
                    <th>Publicação</th>
                    <th>Preço</th>
                    <th>Comprada em</th>
                    <th>Contrato</th>
                  </tr>
                </thead>
                <tbody>
                  {visiveis.map((c) => {
                    const link = linkPncp(c.controle);
                    const nome = [c.modalidade, c.numero_compra ? `nº ${c.numero_compra}` : null].filter(Boolean).join(' ');
                    return (
                      <tr key={c.controle} className={c.fopa ? undefined : 'fora-escopo'}>
                        <td>
                          <b>
                            {c.municipio ?? '—'}
                            {c.uf ? `/${c.uf}` : ''}
                          </b>
                          {!c.fopa && (
                            <>
                              {' '}
                              <span className="marca" title={AVISO_FORA_DO_ESCOPO}>
                                fora do escopo
                              </span>
                            </>
                          )}
                          <div className="sha">
                            {c.orgao ?? '—'}
                            {nome ? ` · ${nome}` : ''}
                          </div>
                          {link && (
                            <div className="sha">
                              <a href={link} target="_blank" rel="noreferrer">
                                {c.controle} ↗
                              </a>
                            </div>
                          )}
                        </td>
                        <td className="nw">{c.rodada}ª publicação</td>
                        <td className="nw">
                          {brl(c.valor)}
                          {c.fonte_valor === 'contrato' && (
                            <div className="sha" title="O PNCP registrou um valor homologado simbólico (até R$ 1); prevalece o valor do contrato.">
                              pelo contrato
                            </div>
                          )}
                          {c.fonte_valor === 'simbolico' && (
                            <div className="sha" title="O PNCP registrou até R$ 1 e ainda não disponibiliza o contrato desta compra.">
                              valor simbólico no PNCP
                            </div>
                          )}
                        </td>
                        <td className="nw">{c.comprada_em ? data(c.comprada_em) : '—'}</td>
                        <td className="nw">
                          {c.contrato ? (
                            <>
                              {brl(c.contrato.valor)}
                              <div className="sha">{c.contrato.vigencia_fim ? `vigente até ${data(c.contrato.vigencia_fim)}` : 'sem vigência no PNCP'}</div>
                            </>
                          ) : (
                            <span className="sha" title="O PNCP ainda não disponibiliza o contrato desta compra.">
                              —
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Rolagem>
          </div>
          <Paginacao posicao="fim" pagina={pagina} paginas={paginas} topo={topo} irPara={irParaPagina} />
        </>
      )}
    </section>
  );
}
