/**
 * O gráfico do Analytics — as compras de licitações por mês e por instituição —, em SVG
 * puro, sem biblioteca. Refeito em 25/09 para ficar interativo e com o eixo legível (os valores
 * eram cortados à esquerda):
 *
 *   - o eixo Y tem 3 a 5 marcas redondas com rótulo curto ("R$ 1,25 bi", "20") e a margem esquerda do tamanho do
 *     maior rótulo — o "R$ 200.000.000,00" do eixo antigo não cabia nos 64 px fixos;
 *   - curvas suaves e monotônicas (Fritsch–Carlson): entre dois meses a linha nunca passa dos dois valores nem desce
 *     abaixo de zero — suavizar não inventa pico;
 *   - o mouse, o dedo ou as setas do teclado mostram o mês inteiro: a linha-guia, o ponto de cada banco e um quadro
 *     com os valores do maior para o menor e o total;
 *   - a legenda liga e desliga cada banco — o eixo se refaz para os que ficaram (um mês de R$ 1,2 bi do Banrisul
 *     achatava todos os outros) — e, com o mouse em cima, destaca a linha dele;
 *   - o SVG é desenhado na largura real (ResizeObserver): o texto não encolhe no celular.
 */
import { useCallback, useId, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { corNoTema, useTema } from '../lib/tema';

export interface Serie {
  nome: string;
  valores: number[];
  cor: string;
}

const MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const MESES_LONGOS = [
  'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
];
const LARGURA_PADRAO = 960;
const MARGEM = { dir: 18, cima: 18, baixo: 34 };
const LARGURA_CARACTERE = 7.4; // IBM Plex Mono a 12 px, com folga
const LARGURA_ROTULO_MES = 58; // "mar/26" e o respiro até o próximo
const LARGURA_TEXTO_MES = 46; // só o "mar/26" a 12 px

/** "2026-03" → "mar/26" */
export function rotuloMes(m: string): string {
  const [a, mm] = m.split('-');
  return `${MESES[Number(mm) - 1] ?? mm}/${a.slice(2)}`;
}

/** "2026-03" → "março de 2026" */
export function mesPorExtenso(m: string): string {
  const [a, mm] = m.split('-');
  return `${MESES_LONGOS[Number(mm) - 1] ?? mm} de ${a}`;
}

/**
 * A escala do eixo Y: o passo redondo (1, 2, 2,5 ou 5 × 10ⁿ) que cobre o máximo em 3 a 5 intervalos. Contagem só
 * anda de inteiro em inteiro — "2,5 licitações" não existe.
 */
export function escalaY(maximo: number, inteiro = false): { topo: number; passo: number } {
  if (!(maximo > 0)) return { topo: 1, passo: 1 };
  const bruto = maximo / 5;
  const mag = 10 ** Math.floor(Math.log10(bruto));
  let passo = [1, 2, 2.5, 5, 10].map((f) => f * mag).find((p) => p >= bruto && (!inteiro || Number.isInteger(p))) ?? 10 * mag;
  if (inteiro) passo = Math.max(1, Math.ceil(passo));
  return { topo: passo * Math.ceil(maximo / passo - 1e-9), passo };
}

const LETRAS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'];

/** "2026-09": o mês de hoje, no relógio de quem olha. */
function mesDeHoje(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

const um = (v: number) => Math.round(v * 10) / 10;
const maiuscula = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/**
 * A curva suave pelos pontos (Fritsch–Carlson): as tangentes são limitadas para a curva ser monotônica entre dois
 * pontos seguidos — nunca passa de nenhum dos dois, e um trecho plano continua plano.
 */
export function caminhoSuave(p: Array<[number, number]>): string {
  const n = p.length;
  if (n === 0) return '';
  if (n === 1) return `M${um(p[0][0])},${um(p[0][1])}`;
  const dx: number[] = [];
  const m: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    dx.push(p[i + 1][0] - p[i][0]);
    m.push((p[i + 1][1] - p[i][1]) / dx[i]);
  }
  const t: number[] = [m[0]];
  for (let i = 1; i < n - 1; i++) t.push(m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2);
  t.push(m[n - 2]);
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) {
      t[i] = 0;
      t[i + 1] = 0;
      continue;
    }
    const a = t[i] / m[i];
    const b = t[i + 1] / m[i];
    const s = a * a + b * b;
    if (s > 9) {
      const k = 3 / Math.sqrt(s);
      t[i] = k * a * m[i];
      t[i + 1] = k * b * m[i];
    }
  }
  let d = `M${um(p[0][0])},${um(p[0][1])}`;
  for (let i = 0; i < n - 1; i++) {
    const h = dx[i] / 3;
    d +=
      ` C${um(p[i][0] + h)},${um(p[i][1] + t[i] * h)}` +
      ` ${um(p[i + 1][0] - h)},${um(p[i + 1][1] - t[i + 1] * h)}` +
      ` ${um(p[i + 1][0])},${um(p[i + 1][1])}`;
  }
  return d;
}

/** A largura real do elemento; sem ResizeObserver (testes, navegador antigo), a padrão — o SVG escala do mesmo jeito. */
function useLargura(padrao: number): [number, (el: HTMLElement | null) => void] {
  const [largura, setLargura] = useState(padrao);
  const observador = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: HTMLElement | null) => {
    observador.current?.disconnect();
    observador.current = null;
    if (!el || typeof ResizeObserver === 'undefined') return;
    observador.current = new ResizeObserver((entradas) => {
      const w = Math.round(entradas[0]?.contentRect.width ?? 0);
      if (w > 0) setLargura(w);
    });
    observador.current.observe(el);
  }, []);
  return [largura, ref];
}

export function GraficoLinhas({
  meses,
  series: seriesDadas,
  formatar,
  formatarEixo = formatar,
  inteiro = false,
  unidade,
  larguraInicial = LARGURA_PADRAO,
  mesCorrente = mesDeHoje(),
}: {
  meses: string[];
  series: Serie[];
  /** o valor no quadro do mês e na dica da legenda ("12", "R$ 191,69 mi") */
  formatar: (n: number) => string;
  /** o rótulo curto do eixo Y e da legenda ("20", "R$ 1,25 bi") */
  formatarEixo?: (n: number) => string;
  /** contagem: o eixo só marca inteiros */
  inteiro?: boolean;
  /** "licitação(ões)" ou "": vai no quadro do mês */
  unidade: string;
  /** a largura antes de medir a tela — e a única, sem ResizeObserver */
  larguraInicial?: number;
  /** "2026-09": o mês que ainda não fechou; o último trecho dele é tracejado */
  mesCorrente?: string;
}) {
  const id = useId().replace(/:/g, '');
  const [largura, refCaixa] = useLargura(larguraInicial);
  const [ocultas, setOcultas] = useState<Set<string>>(() => new Set());
  const [destaque, setDestaque] = useState<string | null>(null);
  const [foco, setFoco] = useState<number | null>(null);
  // No modo escuro, a cor escura de um banco clareia até ler no fundo (lib/tema.ts); no claro, é a da marca.
  const tema = useTema();
  const series = seriesDadas.map((s) => ({ ...s, cor: corNoTema(s.cor, tema) }));

  if (meses.length === 0 || series.length === 0) return <p className="vazio">Nenhuma compra no período.</p>;

  const visiveis = series.filter((s) => !ocultas.has(s.nome));
  const { topo, passo } = escalaY(Math.max(0, ...visiveis.flatMap((s) => s.valores)), inteiro);
  // toPrecision: 3 × 0,2 dá 0.6000000000000001 em ponto flutuante, e o rótulo comprido comia a margem.
  const marcas = Array.from({ length: Math.round(topo / passo) + 1 }, (_, i) => Number((i * passo).toPrecision(12)));
  const rotulosY = marcas.map(formatarEixo);
  const esq = Math.ceil(Math.max(...rotulosY.map((r) => r.length)) * LARGURA_CARACTERE) + 18;
  const altura = largura < 560 ? 260 : 320;
  const w = Math.max(40, largura - esq - MARGEM.dir);
  const ultimo = meses.length - 1;
  // O eixo X: com espaço, cada mês
  // tem o seu "mar/26"; no meio-termo — o acervo inteiro na tela do computador —, uma letra por mês e o ano embaixo,
  // e nenhum mês fica sem marca; só na tela estreita, um rótulo a cada N meses.
  const pxMes = meses.length > 1 ? w / ultimo : w;
  const modo: 'todos' | 'letras' | 'ritmo' = pxMes >= LARGURA_ROTULO_MES ? 'todos' : pxMes >= 13 ? 'letras' : 'ritmo';
  const h = altura - MARGEM.cima - (modo === 'letras' ? 48 : MARGEM.baixo);
  const anos: { ano: string; de: number; ate: number }[] = [];
  meses.forEach((m, i) => {
    const u = anos[anos.length - 1];
    if (u && u.ano === m.slice(0, 4)) u.ate = i;
    else anos.push({ ano: m.slice(0, 4), de: i, ate: i });
  });
  // O mês que ainda não fechou cai no fim da linha porque não acabou, não porque a compra parou: tracejado.
  const parcial = meses.length > 1 && meses[ultimo] === mesCorrente;
  const x = (i: number) => esq + (meses.length === 1 ? w / 2 : (i * w) / ultimo);
  const y = (v: number) => MARGEM.cima + h - (v / topo) * h;
  const passoX = Math.max(1, Math.ceil(meses.length / Math.max(2, Math.floor(w / LARGURA_ROTULO_MES))));
  const mesAtual = foco !== null && foco <= ultimo ? foco : null;
  // As pontas ancoram para dentro (o primeiro começa no tique, o último termina nele); um rótulo do meio só entra se
  // couber inteiro entre elas — "jul/26" e "set/26" se sobrepunham na ponta direita (25/09).
  const folgaPonta = LARGURA_TEXTO_MES * 1.5 + 8;
  const temRotulo = (i: number) =>
    i === 0 || i === ultimo || (i % passoX === 0 && x(ultimo) - x(i) >= folgaPonta && x(i) - x(0) >= folgaPonta);

  function mesNoPonto(e: PointerEvent<SVGSVGElement>): number | null {
    const r = e.currentTarget.getBoundingClientRect();
    if (!r.width) return null;
    const px = ((e.clientX - r.left) / r.width) * largura;
    const i = meses.length === 1 ? 0 : Math.round(((px - esq) / w) * ultimo);
    return Math.max(0, Math.min(ultimo, i));
  }

  function teclas(e: KeyboardEvent<SVGSVGElement>) {
    const novo =
      e.key === 'ArrowRight'
        ? Math.min(ultimo, (mesAtual ?? -1) + 1)
        : e.key === 'ArrowLeft'
          ? Math.max(0, (mesAtual ?? meses.length) - 1)
          : e.key === 'Home'
            ? 0
            : e.key === 'End'
              ? ultimo
              : e.key === 'Escape'
                ? null
                : undefined;
    if (novo === undefined) return;
    e.preventDefault();
    setFoco(novo);
  }

  function alternar(nome: string) {
    setOcultas((atual) => {
      const nova = new Set(atual);
      if (nova.has(nome)) nova.delete(nome);
      else if (series.length - nova.size > 1) nova.add(nome); // a última que sobrou fica
      return nova;
    });
    setDestaque(null);
  }

  const linhasDoMes =
    mesAtual === null ? [] : visiveis.map((s) => ({ s, v: s.valores[mesAtual] ?? 0 })).sort((a, b) => b.v - a.v);
  const totalDoMes = linhasDoMes.reduce((t, l) => t + l.v, 0);

  return (
    <figure className="grafico">
      <div className="area-grafico" ref={refCaixa}>
        <svg
          viewBox={`0 0 ${largura} ${altura}`}
          role="img"
          tabIndex={0}
          aria-label={`Compras por mês: ${visiveis.map((s) => s.nome).join(', ')}. Use as setas para navegar mês a mês.`}
          onPointerMove={(e) => setFoco(mesNoPonto(e))}
          onPointerDown={(e) => setFoco(mesNoPonto(e))}
          onPointerLeave={(e) => {
            if (e.pointerType === 'mouse') setFoco(null);
          }}
          onKeyDown={teclas}
          onBlur={() => setFoco(null)}
        >
          <defs>
            {visiveis.map((s, i) => (
              <linearGradient key={s.nome} id={`${id}-g${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.cor} stopOpacity={0.3} />
                <stop offset="100%" stopColor={s.cor} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          {marcas.map((t, i) => (
            <g key={t}>
              <line className={i === 0 ? 'base' : 'grade'} x1={esq} x2={largura - MARGEM.dir} y1={y(t)} y2={y(t)} />
              <text className="eixo y" x={esq - 10} y={y(t) + 4} textAnchor="end">
                {rotulosY[i]}
              </text>
            </g>
          ))}
          {modo === 'letras'
            ? meses.map((m, i) => (
                <text
                  key={m}
                  className={i === mesAtual ? 'eixo mes letra atual' : 'eixo mes letra'}
                  x={x(i)}
                  y={altura - 28}
                  textAnchor="middle"
                >
                  {LETRAS[Number(m.slice(5)) - 1] ?? '?'}
                </text>
              ))
            : meses.map((m, i) =>
                temRotulo(i) ? (
                  <text
                    key={m}
                    className={i === mesAtual ? 'eixo mes atual' : 'eixo mes'}
                    x={x(i)}
                    y={altura - 10}
                    textAnchor={meses.length > 1 && i === ultimo ? 'end' : i === 0 && meses.length > 1 ? 'start' : 'middle'}
                  >
                    {rotuloMes(m)}
                  </text>
                ) : null,
              )}
          {modo === 'letras' &&
            anos.map(({ ano, de, ate }) => (
              <g key={ano}>
                {de > 0 && (
                  <line className="virada" x1={x(de) - pxMes / 2} x2={x(de) - pxMes / 2} y1={y(0) + 6} y2={altura - 4} />
                )}
                <text className="eixo ano" x={(x(de) + x(ate)) / 2} y={altura - 8} textAnchor="middle">
                  {ano}
                </text>
              </g>
            ))}
          {visiveis.map((s, i) => {
            const pontos = s.valores.map((v, j) => [x(j), y(v)] as [number, number]);
            const d = caminhoSuave(parcial ? pontos.slice(0, -1) : pontos);
            const cheia = destaque === s.nome || visiveis.length === 1;
            return (
              <g key={s.nome} data-serie={s.nome} className={destaque !== null && destaque !== s.nome ? 'serie apagada' : 'serie'}>
                {cheia && (
                  <path
                    className="area"
                    d={`${caminhoSuave(pontos)} L${um(x(ultimo))},${um(y(0))} L${um(x(0))},${um(y(0))} Z`}
                    fill={`url(#${id}-g${i})`}
                  />
                )}
                <path className="linha" d={d} stroke={s.cor} pathLength={1} />
                {parcial && (
                  <path
                    className="linha parcial"
                    d={`M${um(pontos[ultimo - 1][0])},${um(pontos[ultimo - 1][1])} L${um(pontos[ultimo][0])},${um(pontos[ultimo][1])}`}
                    stroke={s.cor}
                  />
                )}
              </g>
            );
          })}
          {mesAtual !== null && (
            <g className="foco">
              <line className="guia" x1={x(mesAtual)} x2={x(mesAtual)} y1={MARGEM.cima} y2={y(0)} />
              {visiveis.map((s) => (
                <circle
                  key={s.nome}
                  cx={x(mesAtual)}
                  cy={y(s.valores[mesAtual] ?? 0)}
                  r={4.5}
                  fill={s.cor}
                  className={destaque !== null && destaque !== s.nome ? 'apagada' : undefined}
                />
              ))}
            </g>
          )}
        </svg>
        {mesAtual !== null && (
          <div
            className={x(mesAtual) > largura * 0.62 ? 'quadro-mes esquerda' : 'quadro-mes'}
            style={{ left: `${(x(mesAtual) / largura) * 100}%` }}
            role="status"
            aria-live="polite"
          >
            <b>
              {maiuscula(mesPorExtenso(meses[mesAtual]))}
              {parcial && mesAtual === ultimo ? ' (em curso)' : ''}
              {unidade && <small>{unidade}</small>}
            </b>
            <ul>
              {linhasDoMes.map(({ s, v }) => (
                <li key={s.nome} className={v === 0 ? 'zero' : undefined}>
                  <i style={{ background: s.cor }} />
                  <span>{s.nome}</span>
                  <em>{formatar(v)}</em>
                </li>
              ))}
            </ul>
            {linhasDoMes.length > 1 && (
              <p className="total">
                <span>total</span>
                <em>{formatar(totalDoMes)}</em>
              </p>
            )}
          </div>
        )}
      </div>
      {parcial && (
        <p className="nota-parcial">
          Linha tracejada: {mesPorExtenso(meses[ultimo])} ainda está em curso; os números serão atualizados até o fim do mês.
        </p>
      )}
      <figcaption className="legenda" aria-label="Instituições no gráfico: clique para exibir ou ocultar">
        {series.map((s) => {
          const ligada = !ocultas.has(s.nome);
          const total = s.valores.reduce((t, v) => t + v, 0);
          return (
            <button
              key={s.nome}
              type="button"
              aria-pressed={ligada}
              className={ligada ? 'chip' : 'chip desligada'}
              title={`${s.nome}: ${formatar(total)} no período — clique para ${ligada ? 'esconder' : 'mostrar'}`}
              onClick={() => alternar(s.nome)}
              onMouseEnter={() => ligada && setDestaque(s.nome)}
              onMouseLeave={() => setDestaque(null)}
              onFocus={() => ligada && setDestaque(s.nome)}
              onBlur={() => setDestaque(null)}
            >
              <i style={{ background: s.cor }} />
              <span>{s.nome}</span>
              <small>{formatarEixo(total)}</small>
            </button>
          );
        })}
      </figcaption>
    </figure>
  );
}
