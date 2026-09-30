/**
 * Os números do topo do painel e do histórico.
 *
 * Uma faixa só, como o cabeçalho de um relatório: uma coluna por pergunta (o que há, o que foi extraído, o quanto
 * confere, quanto a IA custou), separadas por fio. Cada coluna tem o número que responde, em destaque, e uma barra que
 * mostra do que ele é feito — a do prazo usa as cores da barrinha dos cards (vermelho até 7 dias, âmbar até 20, verde
 * depois). De onde veio cada número vai no `title`, não no corpo.
 *
 * O que cada número É não mudou (api/consultas.py:resumo): "sem preço" nunca vira R$ 0 (ADR-012), a ancoragem fica
 * verde só acima de 99%, o Jev é opinião e não decide.
 */
import type { ReactNode } from 'react';
import type { GastoProvedor, GastosIa, Resumo } from '../api/tipos';
import { brl, data, dataHora, milhar, numero, usd } from '../lib/formato';
import { rotuloProvedor } from '../lib/procedencia';
import { AVISO_IA_FOLHA, percentual } from '../lib/respostas';

type Tom = 'ok' | 'al' | 'am' | undefined;

// Ancoragem como taxa: "23.002/23.006" não cabia no quadro do histórico. Arredonda para BAIXO: 99,995% não vira 100%
// enquanto falta uma.
function taxa(n: number, d: number): string {
  if (!d) return '—';
  const p = Math.floor((n / d) * 10000) / 100;
  return `${p.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`;
}

function Grupo({ titulo, valor, unidade, tom, children }: { titulo: string; valor: string; unidade?: string; tom?: Tom; children?: ReactNode }) {
  return (
    <section className="grupo" aria-label={titulo}>
      <h2>{titulo}</h2>
      <p className={tom ? `destaque ${tom}` : 'destaque'}>
        <b>{valor}</b>
        {unidade && <span>{unidade}</span>}
      </p>
      {children}
    </section>
  );
}

/** Uma parte da barra: quanto, a cor (o que significa) e o texto da legenda. */
interface Parte {
  n: number;
  classe: 'al' | 'am' | 'ok' | 'neutro' | 'c1' | 'c2' | 'c3';
  texto: string;
}

/**
 * A barra de composição e, se pedida, a legenda embaixo ("23 fecham em até 7 dias"). Parte zerada não entra — nem na
 * barra nem na legenda. O leitor de tela ouve a barra inteira pelo `aria-label`.
 */
function Partes({ partes, rotulo, legenda = true }: { partes: Parte[]; rotulo: string; legenda?: boolean }) {
  const cheias = partes.filter((p) => p.n > 0);
  if (cheias.length === 0) return null;
  return (
    <>
      <div className="partes" role="img" aria-label={`${rotulo}: ${cheias.map((p) => `${milhar(p.n)} ${p.texto}`).join(', ')}`}>
        {cheias.map((p) => (
          <i key={p.texto} className={p.classe} style={{ flexGrow: p.n }} />
        ))}
      </div>
      {legenda && (
        <ul className="legenda-partes">
          {cheias.map((p) => (
            <li key={p.texto} className={p.classe}>
              <b>{milhar(p.n)}</b> {p.texto}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Linha({
  rotulo,
  valor,
  nota,
  tom,
  title,
  classe,
}: {
  rotulo: string;
  valor: string;
  nota?: string;
  tom?: Tom;
  title?: string;
  classe?: string;
}) {
  // Cada par numa linha própria (dl > div): o valor comprido de uma linha (a data da coleta) não estreita o rótulo das
  // outras, como fazia a coluna única da grade.
  return (
    <div className={classe}>
      <dt title={title}>
        {rotulo}
        {nota && <small>{nota}</small>}
      </dt>
      <dd className={tom}>{valor}</dd>
    </div>
  );
}

/** De onde veio o número de cada provedor, em palavras (vai no title da linha). */
function fonteDoGasto(p: GastoProvedor): string {
  if (p.fonte === 'admin-api') return `Fatura lida em ${dataHora(p.lido_em)}`;
  if (p.fonte === 'painel') {
    const depois = numero(p.medido_depois_usd) ?? 0;
    const lido = `Painel da TypeSafe, lido em ${dataHora(p.lido_em)}`;
    return depois >= 0.005 ? `${lido}, mais ${usd(depois)} medidos depois` : lido;
  }
  if (p.fonte === 'medido') return 'Medido pelo sistema (tokens × preço)';
  return 'Ainda sem leitura';
}

const CORES_PROVEDOR = ['c1', 'c2', 'c3'] as const;

function GrupoGastos({ g }: { g: GastosIa }) {
  // do maior para o menor: a barra lê da esquerda para a direita como as linhas embaixo
  const provedores = [...g.provedores].sort((a, b) => (numero(b.usd) ?? -1) - (numero(a.usd) ?? -1));
  const desde = g.provedores.map((p) => p.desde).filter((d): d is string => !!d).sort()[0];
  const faltam = provedores.filter((p) => p.usd === null).map((p) => p.rotulo);
  const cor = (i: number) => CORES_PROVEDOR[i % CORES_PROVEDOR.length];
  return (
    <Grupo
      titulo="Gastos com IA"
      valor={usd(g.total_usd)}
      unidade={g.total_brl === null ? 'em dólares' : `≈ ${brl(g.total_brl)}${desde ? `, desde ${data(desde).slice(0, 5)}` : ''}`}
    >
      <Partes
        rotulo="Gasto por provedor, em dólares"
        legenda={false}
        partes={provedores.map((p, i) => ({ n: numero(p.usd) ?? 0, classe: cor(i), texto: p.rotulo }))}
      />
      <dl>
        {provedores.map((p, i) => (
          <Linha
            key={p.provedor}
            classe={p.usd === null ? undefined : cor(i)}
            rotulo={p.rotulo}
            valor={p.usd === null ? 'sem leitura' : usd(p.usd)}
            title={fonteDoGasto(p)}
          />
        ))}
      </dl>
      <p className="nota">
        {faltam.length > 0
          ? `O total ainda não inclui ${faltam.join(' nem ')}.`
          : 'Fonte: faturas dos provedores (Claude, GPT) e painel da TypeSafe (Jev). Extrações locais não entram no total.'}
      </p>
    </Grupo>
  );
}

export function QuadrosResumo({ r, historico, gastos }: { r: Resumo; historico: boolean; gastos?: GastosIa | null }) {
  const custo = numero(r.custo_conhecido_brl);
  const teto = numero(r.teto_brl_dia);
  const coleta = r.ultima_coleta;
  const jev = r.jev;
  const semDocumento = r.sem_documento_fonte ?? 0;
  const ancorada = r.respondidas > 0 && r.ancoradas / r.respondidas > 0.99;
  const aviso = r.aviso ?? 0;
  const notaCusto = [
    r.custo_sem_preco > 0 ? `${milhar(r.custo_sem_preco)} sem preço` : '',
    r.extraidas_local > 0 ? `${milhar(r.extraidas_local)} extraídas localmente, sem custo` : '',
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <div className={historico ? 'resumo tres' : 'resumo'}>
      {historico ? (
        // Os motivos de estar no histórico: "abertas" e "≤7 dias" não dizem nada sobre o que já passou.
        <Grupo titulo="No histórico" valor={milhar(r.licitacoes)} unidade="licitações">
          <Partes
            rotulo="Situação das licitações"
            partes={[
              { n: r.com_vencedor ?? 0, classe: 'ok', texto: 'com vencedor homologado' },
              { n: r.desfeitas ?? 0, classe: 'al', texto: 'revogadas ou anuladas' },
              {
                n: Math.max(0, r.licitacoes - (r.com_vencedor ?? 0) - (r.desfeitas ?? 0)),
                classe: 'neutro',
                texto: 'sem vencedor registrado',
              },
            ]}
          />
          <dl>
            <Linha rotulo={`Anteriores a ${r.ano_minimo ?? 2026}`} valor={milhar(r.antes_do_recorte ?? 0)} />
          </dl>
        </Grupo>
      ) : (
        <Grupo titulo="Em andamento" valor={milhar(r.licitacoes)} unidade="licitações de folha">
          {/* As faixas da barrinha dos cards: vermelho até 7 dias, âmbar até 20, verde depois. */}
          <Partes
            rotulo="Prazo até a sessão"
            partes={[
              { n: r.urgentes, classe: 'al', texto: 'fecham em até 7 dias' },
              { n: aviso, classe: 'am', texto: 'de 8 a 20 dias' },
              { n: Math.max(0, r.abertas - r.urgentes - aviso), classe: 'ok', texto: 'depois de 20 dias' },
              { n: Math.max(0, r.licitacoes - r.abertas), classe: 'neutro', texto: 'sem data de sessão' },
            ]}
          />
          <dl>
            <Linha
              rotulo="Última coleta"
              nota={coleta?.cego ? 'Incompleta: a consulta ao PNCP falhou' : undefined}
              valor={coleta?.iniciado_em ? dataHora(coleta.iniciado_em) : '—'}
              tom={coleta?.cego ? 'al' : undefined}
            />
          </dl>
        </Grupo>
      )}
      <Grupo titulo="Extração" valor={milhar(r.extraidas)} unidade={`extraídas de ${milhar(r.licitacoes)}`}>
        <Partes
          rotulo="Extração"
          legenda={false}
          partes={[
            { n: r.extraidas, classe: 'ok', texto: 'extraídas' },
            { n: Math.max(0, r.licitacoes - r.extraidas), classe: 'neutro', texto: 'por extrair' },
          ]}
        />
        <dl>
          {/* O PNCP não entrega documento que se leia (db/044): nunca vai ser extraída, então sai da conta e fica à
              parte. */}
          {semDocumento > 0 && (
            <Linha
              rotulo="Sem documento na fonte"
              valor={milhar(semDocumento)}
              title="O PNCP não disponibiliza o edital destas licitações: não há arquivo, ou o arquivo não é o edital."
            />
          )}
          <Linha rotulo="Custo das extrações" valor={custo === null ? '—' : brl(custo)} nota={notaCusto || undefined} />
          {/* Os números do dia (teto, extração vigente) são da home: no histórico não dizem nada sobre o que passou. */}
          {!historico && (
            <Linha
              rotulo="Extração vigente"
              valor={rotuloProvedor(r.provedor)}
              title={r.provedor ? `Provedor configurado: ${r.provedor}` : undefined}
            />
          )}
          {!historico && <Linha rotulo="Teto por dia" valor={teto === null ? 'sem teto' : brl(teto)} />}
        </dl>
      </Grupo>
      {/* Verde acima de 99% ancorado, na home e no histórico — 23.522 de 23.526 não é alarme. */}
      <Grupo
        titulo="Conferência"
        valor={taxa(r.ancoradas, r.respondidas)}
        unidade={`${milhar(r.ancoradas)} de ${milhar(r.respondidas)} respostas com o trecho do edital`}
        tom={ancorada ? 'ok' : 'al'}
      >
        <Partes
          rotulo="Ancoragem"
          legenda={false}
          partes={[
            { n: r.ancoradas, classe: 'ok', texto: 'com o trecho' },
            { n: Math.max(0, r.respondidas - r.ancoradas), classe: 'al', texto: 'sem o trecho' },
          ]}
        />
        <dl>
          <Linha rotulo="Para revisar" valor={milhar(r.para_revisar)} tom={r.para_revisar > 0 ? 'am' : undefined} />
          {jev && (
            <Linha
              rotulo="Não reconhecidas como folha pela IA"
              nota={
                percentual(jev.p_filtro_ok_medio) ? `Probabilidade média de ser folha: ${percentual(jev.p_filtro_ok_medio)}` : undefined
              }
              valor={`${milhar(jev.escopo_discordancias)} de ${milhar(jev.escopo_avaliadas)}`}
              tom={jev.escopo_discordancias > 0 ? 'am' : undefined}
              title={AVISO_IA_FOLHA}
            />
          )}
        </dl>
      </Grupo>
      {!historico && gastos && <GrupoGastos g={gastos} />}
    </div>
  );
}
