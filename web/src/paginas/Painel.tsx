/**
 * `/` — o painel (amostras/index.html, painel.py), agora com dados vivos:
 * tiles de /api/resumo, barra de busca e filtros, contador, um card por
 * controle e paginação do servidor. Busca, filtro, página e escopo moram na
 * URL, para que "voltar" do detalhe devolva a mesma lista.
 *
 * O servidor filtra, ORDENA e pagina (api/consultas.py). A página mostra a
 * lista como veio: refiltrar ou reordenar aqui fazia o contador (o `total`
 * do servidor) contar cards que a tela escondia.
 */
import '../../design/painel.css';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useGastosIa, useLicitacoes, useResumo, type Situacao } from '../api/consultas';
import { CardLicitacao } from '../componentes/CardLicitacao';
import { dataDaUrl, FiltroDatas } from '../componentes/FiltroDatas';
import { Lista } from '../componentes/Lista';
import { Carregando, Falha } from '../componentes/Estado';
import { Paginacao, rolarAoTopo, trecho } from '../componentes/Paginacao';
import { QuadrosResumo } from '../componentes/QuadrosResumo';
import { useAgora } from '../lib/agora';
import { FILTROS, VENCIMENTOS, alternarFiltro, ehChaveFiltro, vencimentoDaUrl, type ChaveFiltro } from '../lib/filtros';
import { ListaMultipla } from '../componentes/ListaMultipla';
import { milhar } from '../lib/formato';
import { AVISO_IA_FOLHA } from '../lib/respostas';

/**
 * A mesma grade serve à home e ao histórico. Na home só o que ainda é trabalho (sessão por vir, ou sem data — não
 * dá para dizer que passou); no histórico, o que a sessão já aconteceu e o legado de antes de 2026 — é análise
 * (quem ganhou, por quanto), não trabalho do dia. Nada foi apagado para isso.
 */
// Os atalhos do filtro de datas do histórico: o PNCP começa em 2021 (Lei 14.133), mas a primeira compra de folha nele
// é de 2022 — o atalho de 2021 não mostrava nada.
const ANOS_HISTORICO = [2026, 2025, 2024, 2023, 2022];

// 10 por página por padrão, na home e no histórico, com 50 ou 100 — a mesma lista da Analytics Histórico
// FOPA, sem "todos": aqui o servidor pagina (até 200 por página) e o histórico tem milhares.
const ITENS = ['10', '50', '100'];

export function Painel({ situacao = 'ativas' }: { situacao?: Situacao }) {
  const historico = situacao === 'historico';
  const [params, setParams] = useSearchParams();
  const agora = useAgora();
  // Os itens do "Mostrar": "Encerradas" é o próprio histórico; "Com alerta de regra" só no histórico;
  // "Fecham em ≤7 dias" saiu das duas páginas — o prazo virou a lista "Vencimento", só na home.
  const chips = FILTROS.filter(
    (f) => f.chave !== 'encerradas' && f.chave !== 'urgentes' && !(!historico && f.chave === 'alerta'),
  );
  // Vários itens somam-se com E. Item da URL sem opção nesta página não vale (ficaria ativo sem como
  // desmarcar).
  const filtros = params
    .getAll('filtro')
    .filter((f): f is ChaveFiltro => ehChaveFiltro(f) && f !== 'todas' && chips.some((c) => c.chave === f));
  const venceEm = historico ? null : vencimentoDaUrl(params.get('vence_em'));
  const q = params.get('q') ?? '';
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1);
  const itensUrl = params.get('itens');
  const porPagina = Number(itensUrl && ITENS.includes(itensUrl) ? itensUrl : ITENS[0]);
  // Filtro de datas pela publicação, só no histórico.
  const de = historico ? dataDaUrl(params.get('de')) : null;
  const ate = historico ? dataDaUrl(params.get('ate')) : null;
  // Só o que a IA confirma como folha, SEMPRE: o que a IA (Jev) estima que não é folha — nota abaixo de 50% — sai do
  // painel e do histórico; no Analytics volta com "mostrar fora do escopo". Sem nota da IA, fica; o rótulo "é folha"
  // manda (db/034).
  const soFopaIa = true;
  // As escolhas da barra são um rascunho até o "Filtrar": começam no que está na URL e voltam
  // a ele quando a URL muda (o link, o voltar do navegador, o próprio "Filtrar"). A busca por texto segue ao digitar.
  const aplicado = { filtros, venceEm, de, ate };
  const chaveAplicado = JSON.stringify(aplicado);
  const [rascunho, setRascunho] = useState(aplicado);
  useEffect(() => setRascunho(JSON.parse(chaveAplicado) as typeof aplicado), [chaveAplicado]);
  const [texto, setTexto] = useState(q);
  // o container da grade (a barra de páginas de cima, da página 2 em diante, e os cards): passar de página ou trocar a
  // quantidade leva a tela ao alto dele
  const topo = useRef<HTMLDivElement>(null);

  // Sem recorte de ano aqui: home e histórico particionam o acervo, e o que é de antes de 2026 já é histórico —
  // "mostrar anteriores" na home traria de volta, em dobro, o que o histórico mostra.
  // Só folha, sempre: o que a regra de escopo recusou não chega a esta tela.
  const resumo = useResumo(false, situacao, { de, ate }, soFopaIa);
  const lista = useLicitacoes({ q, filtros, venceEm, page, porPagina, recorteTodos: false, situacao, de, ate, soFopaIa });
  const noHistorico = resumo.data?.historico;
  // Os gastos com IA são da home; no histórico, nem se pedem.
  const gastos = useGastosIa(!historico);

  function mudar(novos: Record<string, string | string[] | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(novos)) {
      p.delete(k);
      if (Array.isArray(v)) for (const x of v) p.append(k, x);
      else if (v !== null && v !== '') p.set(k, v);
    }
    setParams(p, { replace: true });
  }

  // O "Filtrar": as escolhas da barra vão juntas para a URL, e a lista volta à página 1.
  function filtrar() {
    mudar({
      filtro: rascunho.filtros,
      vence_em: rascunho.venceEm ? String(rascunho.venceEm) : null,
      de: rascunho.de,
      ate: rascunho.ate,
      page: null,
    });
  }

  // o que as duas barras de páginas (em cima e embaixo da grade) fazem: a página 1 não vai para a URL
  function irParaPagina(n: number) {
    mudar({ page: n > 1 ? String(n) : null });
  }

  // A busca espera o usuário parar de digitar: cada tecla não é uma consulta.
  useEffect(() => {
    if (texto === q) return;
    const t = setTimeout(() => mudar({ q: texto.trim() || null, page: null }), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [texto]);

  const dados = lista.data;
  const itens = dados?.itens ?? [];
  const total = dados?.total ?? 0;
  const paginas = dados ? Math.max(1, dados.paginas) : 1;
  const temJev = itens.some((c) => c.jev_filtro);

  return (
    <div className="pg-painel">
      <div className="wrap">
        {historico ? (
          <header>
            <p className="eyebrow">Folha de pagamento · histórico</p>
            <h1>Histórico</h1>
            <p className="sub">
              Licitações <b>encerradas</b>, da mais recente para a mais antiga: sessão já realizada; vencedor homologado
              no PNCP (o credenciamento com inscrições abertas permanece no painel); licitação revogada ou anulada; sem
              data de sessão e publicada há mais de 60 dias; e todas as anteriores a 2026. Também constam, sem extração, as
              licitações que a IA não reconhece como folha com alta confiança (nota até 25%), exceto as classificadas
              manualmente como folha. Nenhum registro foi excluído.{' '}
              <Link to="/">← Voltar ao painel</Link>
            </p>
          </header>
        ) : (
          <header>
            <p className="eyebrow">Folha de pagamento · setor público</p>
            <h1>Painel de licitações</h1>
            <p className="sub">
              Licitações <b>em andamento</b>: sessão a realizar, ou sem data definida e sem vencedor (publicadas nos
              últimos 60 dias). A lista é ordenada por <b>prazo</b>, para priorizar as que encerram primeiro. Cada resposta
              abre o PDF na página citada.
              {noHistorico !== undefined && (
                <>
                  {' '}
                  <Link to="/historico">{milhar(noHistorico)} no histórico →</Link>
                </>
              )}
            </p>
          </header>
        )}

        {resumo.data ? (
          <QuadrosResumo r={resumo.data} historico={historico} gastos={gastos.data} />
        ) : resumo.isError ? (
          <Falha erro={resumo.error} oque="o resumo" />
        ) : null}

        <div className="barra">
          <input
            type="search"
            placeholder="Buscar por município, órgão, modalidade, número de controle ou objeto"
            aria-label="Buscar licitações"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
          {/* os botões soltos viraram listas; o "Mostrar" aceita vários itens e tudo vale no "Filtrar" (28/09) */}
          <ListaMultipla
            rotulo="Mostrar"
            marcados={rascunho.filtros.length ? rascunho.filtros : ['todas']}
            opcoes={chips.map((f) => ({ valor: f.chave, texto: f.rotulo }))}
            aoAlternar={(v) => setRascunho((r) => ({ ...r, filtros: alternarFiltro(r.filtros, v as ChaveFiltro) }))}
          />
          {!historico && (
            <Lista
              rotulo="Vencimento"
              valor={rascunho.venceEm ? String(rascunho.venceEm) : ''}
              opcoes={[
                { valor: '', texto: 'Qualquer prazo' },
                ...VENCIMENTOS.map((n) => ({ valor: String(n), texto: `Até ${n} dias` })),
              ]}
              aoMudar={(v) => setRascunho((r) => ({ ...r, venceEm: vencimentoDaUrl(v) }))}
            />
          )}
          {historico && (
            <FiltroDatas
              de={rascunho.de}
              ate={rascunho.ate}
              anos={ANOS_HISTORICO}
              aoMudar={(d, a) => setRascunho((r) => ({ ...r, de: d, ate: a }))}
            />
          )}
          <button type="button" className="primario" onClick={filtrar}>
            Filtrar
          </button>
        </div>

        <p className="sub contador">
          <span>
            <b id="conta">{milhar(total)}</b> {total === 1 ? 'licitação' : 'licitações'} na lista
          </span>
        </p>
        {total > 0 && (
          <div className="barra">
            {/* "Itens", não "Mostrar": a lista "Mostrar" desta página é a do filtro */}
            <Lista
              rotulo="Itens"
              valor={String(porPagina)}
              opcoes={ITENS.map((n) => ({ valor: n, texto: `${n} por página` }))}
              aoMudar={(v) => {
                mudar({ itens: v === ITENS[0] ? null : v, page: null });
                rolarAoTopo(topo);
              }}
            />
            <span className="sha">{trecho(page, porPagina, itens.length, total)}</span>
          </div>
        )}
        {temJev && (
          // uma linha corrida, sem a largura de leitura do .sub
          <p className="sub legenda-ia">
            <span className="marca jev">IA: é folha (N%)</span> = {AVISO_IA_FOLHA}
          </p>
        )}

        {lista.isError ? (
          <Falha erro={lista.error} oque="as licitações" />
        ) : !dados ? (
          <Carregando />
        ) : itens.length === 0 ? (
          <p id="vazio" className="vazio">
            Nenhuma licitação encontrada para os filtros selecionados.
          </p>
        ) : (
          <div className="grade-lista" ref={topo}>
            {/* os botões de página também em cima da grade, da página 2 em diante */}
            <Paginacao posicao="topo" pagina={page} paginas={paginas} topo={topo} irPara={irParaPagina} />
            {itens.map((c) => (
              <CardLicitacao key={c.controle} card={c} agora={agora} />
            ))}
          </div>
        )}

        {dados && <Paginacao posicao="fim" pagina={page} paginas={paginas} topo={topo} irPara={irParaPagina} />}

        <footer>
          Dados atualizados continuamente. Fonte: Portal Nacional de Contratações Públicas (PNCP), dados abertos (Lei
          nº 14.133/2021, art. 54). Nenhum dado pessoal é armazenado.
        </footer>
      </div>
    </div>
  );
}
