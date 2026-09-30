/**
 * Analytics Histórico FOPA: a segunda das duas páginas do Analytics (a outra é a de Mercado), com os editais sem
 * comprador publicados de novo — com
 * filtro de período (último mês, 3 e 6 meses, 1, 2 e 4 anos), a busca do painel e o número de tentativas do edital.
 *
 * As cadeias vêm do histórico INTEIRO (GET /api/analytics, só o que a IA confirma como folha): a tentativa de antes do
 * período continua contando — o edital na 3ª publicação segue na 3ª com "último mês". O período olha a ÚLTIMA
 * publicação da cadeia. Os filtros rodam aqui, sem ir de novo ao servidor, e moram na URL, como nas outras páginas.
 */
import '../../design/painel.css';
import { useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useAnalytics } from '../api/consultas';
import type { CadeiaRepublicacao, ResultadoTentativa } from '../api/tipos';
import { AbasAnalytics } from '../componentes/AbasAnalytics';
import { Carregando, Falha } from '../componentes/Estado';
import { Lista } from '../componentes/Lista';
import { Paginacao, rolarAoTopo, trecho } from '../componentes/Paginacao';
import { Rolagem } from '../componentes/Rolagem';
import { useAgora } from '../lib/agora';
import { data, dataHora, milhar } from '../lib/formato';

const PERIODOS = [
  { chave: '1m', rotulo: 'Último mês', meses: 1 },
  { chave: '3m', rotulo: '3 meses', meses: 3 },
  { chave: '6m', rotulo: '6 meses', meses: 6 },
  { chave: '1a', rotulo: '1 ano', meses: 12 },
  { chave: '2a', rotulo: '2 anos', meses: 24 },
  { chave: '4a', rotulo: '4 anos', meses: 48 },
];

// No acervo real (26/09) as cadeias vão de 2 a 6 publicações; de 4 em diante são poucas, e ficam juntas.
const TENTATIVAS = [
  { chave: '2', rotulo: '2', aceita: (n: number) => n === 2 },
  { chave: '3', rotulo: '3', aceita: (n: number) => n === 3 },
  { chave: '4+', rotulo: '4 ou mais', aceita: (n: number) => n >= 4 },
];

// A tabela mostra 10 por vez, com 50, 100 ou todos.
const QUANTOS = [
  { chave: '10', n: 10 },
  { chave: '50', n: 50 },
  { chave: '100', n: 100 },
  { chave: 'todos', n: Infinity },
];

const ROTULO_RESULTADO: Record<ResultadoTentativa, string> = {
  comprada: 'comprada',
  deserta: 'deserta',
  fracassada: 'fracassada',
  revogada: 'revogada',
  anulada: 'anulada',
  aberta: 'em aberto',
};

/** "12345678000199-1-000650/2025" → link do edital no PNCP */
export function linkPncp(controle: string): string | null {
  const m = /^(\d{14})-\d+-(\d+)\/(\d{4})$/.exec(controle);
  return m ? `https://pncp.gov.br/app/editais/${m[1]}/${m[3]}/${Number(m[2])}` : null;
}

function ordinal(n: number): string {
  return `${n}ª`;
}

/** O começo do período: o mesmo dia, N meses antes, à meia-noite (31/03 menos um mês é 28/02, não 03/03). */
export function inicioDoPeriodo(agora: Date, meses: number): Date {
  const d = new Date(agora.getFullYear(), agora.getMonth() - meses, 1);
  const ultimoDia = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(agora.getDate(), ultimoDia));
  return d;
}

const semAcento = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

/** Cada palavra da busca aparece no município, na UF, no órgão (nome ou CNPJ) ou num controle da cadeia. */
function casaBusca(c: CadeiaRepublicacao, busca: string): boolean {
  const palavras = semAcento(busca).split(/\s+/).filter(Boolean);
  if (!palavras.length) return true;
  const onde = c.municipio && c.uf ? `${c.municipio}/${c.uf}` : '';
  const alvo = semAcento([c.municipio, c.uf, onde, c.orgao, c.orgao_cnpj, ...c.historico.flatMap((t) => t.controles)].filter(Boolean).join(' | '));
  return palavras.every((p) => alvo.includes(p));
}

function Tentativas({ c }: { c: CadeiaRepublicacao }) {
  return (
    <ol className="tentativas">
      {c.historico.map((t) => {
        const link = linkPncp(t.controles[0]);
        return (
          <li key={t.publicacao} className={`res-${t.resultado}`}>
            <b>{ordinal(t.publicacao)}</b>{' '}
            {link ? (
              <a href={link} target="_blank" rel="noreferrer" title={t.controles.join(' + ')}>
                {data(t.publicado_em)}
              </a>
            ) : (
              data(t.publicado_em)
            )}{' '}
            <span className="marca">{ROTULO_RESULTADO[t.resultado]}</span>
            {t.controles.length > 1 && (
              <span className="sha" title="O mesmo edital foi cadastrado duas vezes no mesmo dia e conta como uma tentativa.">
                {' '}
                · cadastro duplicado
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export function AnalyticsHistorico() {
  const [params, setParams] = useSearchParams();
  const agora = useAgora();
  // o container da tabela (a barra de páginas de cima, da página 2 em diante, e a tabela): passar de página ou trocar a
  // quantidade leva a tela ao alto dele
  const topo = useRef<HTMLDivElement>(null);
  const q = params.get('q') ?? '';
  const periodo = PERIODOS.find((p) => p.chave === params.get('periodo')) ?? null;
  const tentativas = TENTATIVAS.find((t) => t.chave === params.get('tentativas')) ?? null;
  const quantos = QUANTOS.find((x) => x.chave === params.get('itens')) ?? QUANTOS[0];
  // Sempre só folha (a IA confirma) e o histórico inteiro: a mesma consulta da aba de Mercado sem filtro.
  const consulta = useAnalytics({ escopoTodos: false, de: null, ate: null, soFopaIa: true });
  const d = consulta.data;

  // Mudar filtro, busca ou quantidade volta à primeira página; só a paginação mexe em `pagina`.
  function mudar(novos: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    if (!('pagina' in novos)) p.delete('pagina');
    for (const [k, v] of Object.entries(novos)) {
      if (v === null || v === '') p.delete(k);
      else p.set(k, v);
    }
    setParams(p, { replace: true });
  }

  // o que as duas barras de páginas (em cima e embaixo da tabela) fazem: a página 1 não vai para a URL
  function irParaPagina(n: number) {
    mudar({ pagina: n > 1 ? String(n) : null });
  }

  const inicio = periodo ? inicioDoPeriodo(agora, periodo.meses) : null;
  const lista = (d?.republicadas ?? []).filter(
    (c) =>
      (!inicio || new Date(c.ultima_publicacao) >= inicio) && (!tentativas || tentativas.aceita(c.tentativas)) && casaBusca(c, q),
  );
  const semComprador = lista.filter((c) => c.sem_comprador).length;
  // A página vem da URL; além da última (o filtro encolheu a lista), vale a última, não uma tabela vazia.
  const paginas = Number.isFinite(quantos.n) ? Math.max(1, Math.ceil(lista.length / quantos.n)) : 1;
  const pagina = Math.min(paginas, Math.max(1, Number(params.get('pagina') ?? 1) || 1));
  const visiveis = Number.isFinite(quantos.n) ? lista.slice((pagina - 1) * quantos.n, pagina * quantos.n) : lista;

  return (
    <div className="pg-painel pg-analytics">
      <div className="wrap">
        <AbasAnalytics />
        <header>
          <p className="eyebrow">FOPA · histórico da folha</p>
          <h1>Analytics Histórico FOPA</h1>
          <p className="sub">
            Editais de compra de folha publicados novamente porque a tentativa anterior não teve comprador (deserta,
            fracassada, revogada ou sem resultado). Como o PNCP não vincula a republicação à anterior, a sequência é estimada
            (mesmo órgão, até 540 dias, tentativa anterior sem vencedor). Apenas licitações confirmadas pela IA como folha. O
            período considera a última publicação; as tentativas consideram todo o histórico.
            {d?.resumo.coletadas_em ? ` Coleta de ${dataHora(d.resumo.coletadas_em)}.` : ''}
          </p>
        </header>

        <div className="barra">
          <input
            type="search"
            placeholder="Buscar por município, UF, órgão ou número de controle"
            aria-label="Buscar editais republicados"
            value={q}
            onChange={(e) => mudar({ q: e.target.value })}
          />
          {/* as fileiras de botões viraram listas */}
          <Lista
            rotulo="Período"
            valor={periodo?.chave ?? ''}
            opcoes={[{ valor: '', texto: 'Todo o histórico' }, ...PERIODOS.map((p) => ({ valor: p.chave, texto: p.rotulo }))]}
            aoMudar={(v) => mudar({ periodo: v || null })}
          />
          <Lista
            rotulo="Tentativas"
            valor={tentativas?.chave ?? ''}
            opcoes={[{ valor: '', texto: 'Todas' }, ...TENTATIVAS.map((t) => ({ valor: t.chave, texto: t.rotulo }))]}
            aoMudar={(v) => mudar({ tentativas: v || null })}
          />
        </div>

        {consulta.isError ? (
          <Falha erro={consulta.error} oque="o histórico de republicações" />
        ) : !d ? (
          <Carregando />
        ) : (
          <>
            <section className="tiles" aria-label="resumo">
              <div className="tile">
                <b>{milhar(lista.length)}</b>
                <span>publicados novamente</span>
              </div>
              <div className="tile al">
                <b>{milhar(semComprador)}</b>
                <span>ainda sem comprador</span>
              </div>
              <div className="tile ok">
                <b>{milhar(lista.length - semComprador)}</b>
                <span>comprados após republicação</span>
              </div>
            </section>

            <section>
              <h2>Editais sem comprador publicados novamente</h2>
              {lista.length > 0 && (
                <div className="barra">
                  <Lista
                    rotulo="Mostrar"
                    valor={quantos.chave}
                    opcoes={QUANTOS.map((x) => ({ valor: x.chave, texto: x.chave === 'todos' ? 'Todos' : `${x.chave} por página` }))}
                    aoMudar={(v) => {
                      mudar({ itens: v === '10' ? null : v });
                      rolarAoTopo(topo);
                    }}
                  />
                  <span className="sha">{trecho(pagina, Number.isFinite(quantos.n) ? quantos.n : lista.length, visiveis.length, lista.length)}</span>
                </div>
              )}
              {lista.length === 0 ? (
                <p className="vazio">Nenhum edital republicado encontrado para os filtros selecionados.</p>
              ) : (
                <div className="grade-lista" ref={topo}>
                  {/* os botões de página também em cima da tabela, da página 2 em diante */}
                  <Paginacao posicao="topo" pagina={pagina} paginas={paginas} topo={topo} irPara={irParaPagina} />
                  <Rolagem min={760}>
                    <table className="republicadas">
                      <thead>
                        <tr>
                          <th>Local</th>
                          <th>Publicações</th>
                          <th>Histórico</th>
                          <th>Situação</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visiveis.map((c) => (
                          <tr key={`${c.orgao_cnpj}-${c.ultima_publicacao}`} className={c.sem_comprador ? 'sem-comprador' : ''}>
                            <td>
                              <b>
                                {c.municipio ?? '—'}
                                {c.uf ? `/${c.uf}` : ''}
                              </b>
                              <div className="sha">{c.orgao}</div>
                            </td>
                            <td className="nw">
                              <b>{ordinal(c.tentativas)} publicação</b>
                            </td>
                            <td>
                              <Tentativas c={c} />
                            </td>
                            <td className="nw">
                              {c.sem_comprador ? (
                                <span className="marca alerta">sem comprador</span>
                              ) : (
                                <span className="marca">comprada na {ordinal(c.tentativas)}</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Rolagem>
                </div>
              )}
              <Paginacao posicao="fim" pagina={pagina} paginas={paginas} topo={topo} irPara={irParaPagina} />
            </section>
          </>
        )}
      </div>
    </div>
  );
}
