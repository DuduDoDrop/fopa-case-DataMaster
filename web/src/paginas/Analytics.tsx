/**
 * Analytics — o histórico de compra e venda da folha:
 *
 * visão geral das instituições financeiras (valores homologados, licitações compradas, a série mensal
 * de compras por instituição) e, na mesma página, os editais sem comprador que voltaram a ser publicados.
 *
 * Tudo vem da API do PNCP (GET /api/analytics, db/027) — sem edital, sem modelo. Esta é a única
 * tela em que o que está fora do escopo de folha pode entrar: a caixa "mostrar fora do escopo".
 * Filtro de datas pela publicação (sem ele, todo o histórico) e cada banco com a cor da marca
 * (lib/bancos.ts), desde 24/09.
 *
 * Em 26/09 a página foi dividida em duas: esta é a Analytics de Mercado; os editais sem
 * comprador publicados de novo foram para a Analytics Histórico FOPA (paginas/AnalyticsHistorico.tsx). Em 27/09, embaixo
 * do gráfico, o que cada instituição financeira comprou (componentes/ComprasPorBanco.tsx).
 */
import '../../design/painel.css';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAnalytics } from '../api/consultas';
import { AbasAnalytics } from '../componentes/AbasAnalytics';
import { ComprasPorBanco } from '../componentes/ComprasPorBanco';
import { Carregando, Falha } from '../componentes/Estado';
import { GraficoLinhas } from '../componentes/GraficoLinhas';
import { dataDaUrl, FiltroDatas } from '../componentes/FiltroDatas';
import { Rolagem } from '../componentes/Rolagem';
import { COR_OUTROS, corDoBanco } from '../lib/bancos';
import { brl, brlCompacto, brlEixo, data, dataHora, milhar } from '../lib/formato';
import { AVISO_FORA_DO_ESCOPO } from '../lib/respostas';
import { corNoTema, useTema } from '../lib/tema';

// Com o histórico inteiro o ranking passa de 90 bancos, a maioria com 1 licitação: os maiores na tela, o resto
// num clique — senão o gráfico mensal fica a 4.600 px do topo.
const LIMITE_RANKING = 15;

// Os atalhos do filtro de datas: o PNCP começa em 2021 (Lei 14.133), mas a primeira compra de folha nele é de 2022
// — o atalho de 2021 não mostrava nada.
const ANOS = [2026, 2025, 2024, 2023, 2022];

export function Analytics() {
  const [params, setParams] = useSearchParams();
  const tema = useTema();
  const escopoTodos = params.get('escopo') === 'todos';
  const de = dataDaUrl(params.get('de'));
  const ate = dataDaUrl(params.get('ate'));
  // O que a IA (Jev) não confirma como folha é "fora do escopo": some por padrão, junto com o que a regra recusou, e
  // volta com a caixa.
  const soFopaIa = !escopoTodos;
  const [medida, setMedida] = useState<'licitacoes' | 'valor'>('licitacoes');
  const [todosBancos, setTodosBancos] = useState(false);
  const consulta = useAnalytics({ escopoTodos, de, ate, soFopaIa });
  const d = consulta.data;

  function mudar(novos: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(novos)) {
      if (v === null || v === '') p.delete(k);
      else p.set(k, v);
    }
    setParams(p, { replace: true });
  }

  // A cor da marca de cada banco (lib/bancos.ts). O ponto do ranking usa a MESMA cor da linha do banco no
  // gráfico; quem não tem linha própria está dentro de "Outros", cinza.
  const corDaSerie = new Map((d?.mensal.series ?? []).map((s, i) => [s.cnpj_raiz, corDoBanco(s.cnpj_raiz, s.banco, i)]));
  const corNoRanking = (cnpj: string) => corNoTema(corDaSerie.get(cnpj) ?? COR_OUTROS, tema);
  // Só instituição financeira no ranking; quem venceu e não é banco (PRODESP, um tribunal...) vai para o
  // "ver mais" logo abaixo — nada some.
  const bancosFin = (d?.bancos ?? []).filter((b) => b.financeira !== false);
  const naoBancos = (d?.bancos ?? []).filter((b) => b.financeira === false);
  const maiorBanco = bancosFin.length ? bancosFin[0].licitacoes : 1;

  return (
    <div className="pg-painel pg-analytics">
      <div className="wrap">
        <AbasAnalytics />
        <header>
          <p className="eyebrow">FOPA · mercado da folha</p>
          <h1>Analytics de Mercado</h1>
          <p className="sub">
            Quem compra a folha, por quanto e quando, com dados obtidos diretamente do PNCP, sem leitura de edital. Os editais
            sem comprador que voltaram a ser publicados estão no Analytics Histórico FOPA.
            {d?.resumo.coletadas_em ? ` Coleta de ${dataHora(d.resumo.coletadas_em)}.` : ''}
            {d?.resumo.duplicadas || d?.resumo.pelo_contrato
              ? ` Ajustes nos dados do PNCP: ${milhar(d.resumo.duplicadas ?? 0)} ${(d.resumo.duplicadas ?? 0) === 1 ? 'compra cadastrada duas vezes é contada' : 'compras cadastradas duas vezes são contadas'} uma vez; `
                + `${milhar(d.resumo.pelo_contrato ?? 0)} com valor homologado simbólico (até R$ 1) ${(d.resumo.pelo_contrato ?? 0) === 1 ? 'é contada' : 'são contadas'} pelo valor do contrato.`
              : ''}
          </p>
        </header>

        <p className="sub contador">
          <FiltroDatas de={de} ate={ate} anos={ANOS} aoMudar={(novoDe, novoAte) => mudar({ de: novoDe, ate: novoAte, ano: null })} />
          <label className="recorte" title={AVISO_FORA_DO_ESCOPO}>
            <input type="checkbox" checked={escopoTodos} onChange={(e) => mudar({ escopo: e.target.checked ? 'todos' : null })} />{' '}
            Mostrar fora do escopo
          </label>
        </p>

        {consulta.isError ? (
          <Falha erro={consulta.error} oque="os dados de mercado" />
        ) : !d ? (
          <Carregando />
        ) : (
          <>
            <section className="tiles" aria-label="resumo">
              <div className="tile">
                <b>{milhar(d.resumo.compras)}</b>
                <span>licitações no histórico</span>
              </div>
              <div className="tile ok">
                <b>{milhar(d.resumo.com_vencedor)}</b>
                <span>compradas (com vencedor)</span>
              </div>
              <div className="tile">
                <b title={brl(d.resumo.valor_homologado)}>{brlCompacto(d.resumo.valor_homologado)}</b>
                <span>valor homologado</span>
              </div>
              <div className="tile">
                <b>{milhar(d.resumo.bancos)}</b>
                <span>instituições compradoras</span>
              </div>
              <div className="tile al">
                <b>{milhar(d.resumo.desertas)}</b>
                <span>desertas ou fracassadas</span>
              </div>
            </section>

            <section>
              <h2>Instituições financeiras compradoras</h2>
              {bancosFin.length === 0 ? (
                <p className="vazio">Nenhuma compra com vencedor no período.</p>
              ) : (
                <Rolagem min={760}>
                  <table className="ranking">
                    <thead>
                      <tr>
                        <th>Instituição financeira</th>
                        <th>Licitações compradas</th>
                        <th>Valor total</th>
                        <th>Ticket médio</th>
                        <th>Participação</th>
                        <th>Primeira e última compra</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(todosBancos ? bancosFin : bancosFin.slice(0, LIMITE_RANKING)).map((b) => (
                        <tr key={b.cnpj_raiz} className="banco">
                          <td>
                            <i className="ponto" data-cor={corNoRanking(b.cnpj_raiz)} style={{ background: corNoRanking(b.cnpj_raiz) }} />{' '}
                            {b.banco}
                            {b.natureza_juridica && <span className="sha"> · {b.natureza_juridica}</span>}
                          </td>
                          <td className="barra-celula">
                            <span
                              className="barra"
                              style={{ width: `${Math.max(4, (b.licitacoes / maiorBanco) * 100)}%`, background: corNoRanking(b.cnpj_raiz) }}
                            />
                            <b>{milhar(b.licitacoes)}</b>
                          </td>
                          <td className="nw">{brl(b.valor_total)}</td>
                          <td className="nw">{brl(b.ticket_medio)}</td>
                          <td className="nw">{(b.participacao * 100).toFixed(1).replace('.', ',')}%</td>
                          <td className="sha nw">
                            {data(b.primeira)} · {data(b.ultima)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Rolagem>
              )}
              {bancosFin.length > LIMITE_RANKING && (
                <p className="sub">
                  <button type="button" className="atalho" onClick={() => setTodosBancos(!todosBancos)}>
                    {todosBancos
                      ? `Mostrar apenas as ${LIMITE_RANKING} maiores`
                      : `Ver as outras ${milhar(bancosFin.length - LIMITE_RANKING)} instituições`}
                  </button>
                </p>
              )}
            </section>

            {naoBancos.length > 0 && (
              <details className="nao-bancos">
                <summary>
                  Ver mais: {milhar(naoBancos.length)}{' '}
                  {naoBancos.length === 1
                    ? 'fornecedor que venceu item de licitação de folha e não é instituição financeira'
                    : 'fornecedores que venceram item de licitação de folha e não são instituições financeiras'}
                </summary>
                <ul>
                  {naoBancos.map((b) => (
                    <li key={b.cnpj_raiz}>
                      {b.banco} · {milhar(b.licitacoes)} {b.licitacoes === 1 ? 'licitação' : 'licitações'} · {brl(b.valor_total)}
                    </li>
                  ))}
                </ul>
              </details>
            )}

            <section>
              <h2>Compras por mês e por instituição</h2>
              <p className="sub contador">
                <label>
                  <input type="radio" name="medida" checked={medida === 'licitacoes'} onChange={() => setMedida('licitacoes')} /> Número de
                  licitações
                </label>
                <label>
                  <input type="radio" name="medida" checked={medida === 'valor'} onChange={() => setMedida('valor')} /> Valor homologado
                </label>
              </p>
              <GraficoLinhas
                meses={d.mensal.meses}
                series={d.mensal.series.map((s, i) => ({
                  nome: s.banco,
                  valores: medida === 'valor' ? s.valor : s.licitacoes,
                  cor: corDoBanco(s.cnpj_raiz, s.banco, i),
                }))}
                formatar={medida === 'valor' ? brlCompacto : milhar}
                formatarEixo={medida === 'valor' ? brlEixo : milhar}
                inteiro={medida !== 'valor'}
                unidade={medida === 'valor' ? 'valor homologado' : 'licitações'}
              />
              <p className="sub dica-grafico">
                Posicione o cursor (ou toque, ou use as setas do teclado) para ver os dados do mês. Clique em uma instituição
                para ocultar ou exibir a respectiva linha; o eixo se ajusta automaticamente.
              </p>
            </section>

            <ComprasPorBanco escopoTodos={escopoTodos} soFopaIa={soFopaIa} anos={ANOS} />
          </>
        )}
      </div>
    </div>
  );
}
