/**
 * A escolha do botão "Extrair com IA": o provedor (Claude ou OpenAI) e os modelos disponíveis, filtrados pelo
 * provedor. O ESFORÇO É FIXO desde 26/09 (ADR-020): cada modelo
 * traz o seu no catálogo (GET /api/modelos-ia, api/modelos_ia.py) e a tela só o mostra.
 */
import type { CatalogoIa } from '../api/tipos';

export interface Escolha {
  provedor: 'openai' | 'claude';
  modelo: string;
}

export function escolhaPadrao(cat: CatalogoIa): Escolha {
  const p = cat.provedores[0];
  return { provedor: p.id, modelo: p.modelos[0].id };
}

const NOME_ESFORCO: Record<string, string> = {
  none: 'nenhum',
  low: 'baixo',
  medium: 'médio',
  high: 'alto',
  xhigh: 'muito alto',
  max: 'máximo',
};

const POR_QUE_FIXO =
  'Definido pelo projeto: nos testes, os níveis baixo, médio e alto tiveram a mesma acurácia, e o médio custa menos.';

const usd = (n: number) => `US$ ${n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const brl = (n: number) => `R$ ${n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export function EscolhaIa({
  catalogo,
  escolha,
  aoMudar,
}: {
  catalogo: CatalogoIa;
  escolha: Escolha;
  aoMudar: (e: Escolha) => void;
}) {
  const prov = catalogo.provedores.find((p) => p.id === escolha.provedor) ?? catalogo.provedores[0];
  const modelo = prov.modelos.find((m) => m.id === escolha.modelo) ?? prov.modelos[0];
  const est = modelo.estimativa;

  return (
    <div className="escolha-ia">
      <label>
        Modelo generativo{' '}
        <select
          aria-label="Modelo generativo"
          value={prov.id}
          onChange={(e) => {
            const p = catalogo.provedores.find((x) => x.id === e.target.value) ?? prov;
            aoMudar({ provedor: p.id, modelo: p.modelos[0].id });
          }}
        >
          {catalogo.provedores.map((p) => (
            <option key={p.id} value={p.id}>
              {p.rotulo}
            </option>
          ))}
        </select>
      </label>
      <label>
        Modelo{' '}
        <select
          aria-label="Modelo"
          value={modelo.id}
          onChange={(e) => {
            const m = prov.modelos.find((x) => x.id === e.target.value) ?? modelo;
            aoMudar({ provedor: prov.id, modelo: m.id });
          }}
        >
          {prov.modelos.map((m) => (
            <option key={m.id} value={m.id}>
              {m.rotulo} — {m.nota}
            </option>
          ))}
        </select>
      </label>
      {modelo.esforco ? (
        <p className="esforco-fixo" title={POR_QUE_FIXO}>
          Esforço: {NOME_ESFORCO[modelo.esforco] ?? modelo.esforco} (fixo)
        </p>
      ) : (
        <p className="sub">O {modelo.rotulo} não tem controle de esforço.</p>
      )}
      {est && (
        <p>
          Custo estimado: <b>≈ {usd(est.usd)}</b> por edital (≈ {brl(est.brl)}) · no máximo {usd(est.usd_max)}{' '}
          <span className="sub">({catalogo.base})</span>
        </p>
      )}
    </div>
  );
}
