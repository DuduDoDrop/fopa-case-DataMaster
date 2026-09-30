/**
 * A distribuição da Q13 estruturada (pagina.py:_tabela_distribuicao).
 *
 * A distribuição é o insumo mais caro da folha e chega como uma frase de
 * quinze linhas; quem confere precisaria somar de cabeça. A barra é
 * proporção, não enfeite: é onde a concentração da folha aparece sem
 * ninguém calcular nada.
 */
import type { Q13 } from '../api/tipos';
import { brl, milhar } from '../lib/formato';

export function DistribuicaoQ13({ q13 }: { q13: Q13 | null }) {
  if (!q13 || !q13.grupos?.length) return null;
  const todas = q13.grupos.flatMap((g) => g.linhas);
  const maior = Math.max(0, ...todas.map((l) => l.quantidade)) || 1;
  const n = todas.length;

  return (
    <details open>
      <summary>
        distribuição estruturada ({n} linha{n === 1 ? '' : 's'})
      </summary>
      {!q13.por_faixa ? (
        <p className="avisodist">
          <b>Não é pirâmide por faixa salarial.</b> O edital apresenta a distribuição por <b>{q13.tipo}</b>; sem faixa
          salarial, não há ticket médio nem estimativa de consignado.
        </p>
      ) : q13.parcial && !q13.completa ? (
        <p className="avisodist">
          <b>Leitura incompleta.</b> A própria resposta informa que faltam dados; a soma abaixo não representa a
          população.
        </p>
      ) : null}
      {q13.grupos.map((g, i) => (
        <table className="dist" key={i}>
          {g.nome && <caption>{g.nome}</caption>}
          <tbody>
            {g.linhas.map((l, j) => (
              <tr key={j}>
                <td className="dl">{l.rotulo}</td>
                <td className="dq">{milhar(l.quantidade)}</td>
                <td className="db">
                  <span style={{ width: `${Math.round((100 * l.quantidade) / maior)}%` }} />
                </td>
                <td className="dv">{l.valor !== null && l.valor !== undefined ? brl(l.valor) : ''}</td>
              </tr>
            ))}
            {g.confere === true ? (
              <tr className="dt">
                <td>total</td>
                <td className="dq">{milhar(g.soma)}</td>
                <td colSpan={2} className="dok">
                  confere com o total impresso
                </td>
              </tr>
            ) : g.confere === false ? (
              <tr className="dt">
                <td>soma</td>
                <td className="dq">{milhar(g.soma)}</td>
                <td colSpan={2} className="dbad">
                  total impresso: {milhar(g.total_declarado)} — diverge
                </td>
              </tr>
            ) : (
              <tr className="dt">
                <td>soma das linhas</td>
                <td className="dq">{milhar(g.soma)}</td>
                <td colSpan={2} className="dmut">
                  sem total impresso para conferir
                </td>
              </tr>
            )}
          </tbody>
        </table>
      ))}
      {q13.grupos.length > 1 && (
        <p className="somatot">
          {q13.grupos.length} tabelas · {q13.rotulo_soma}: <b>{milhar(q13.soma)}</b>
        </p>
      )}
    </details>
  );
}
