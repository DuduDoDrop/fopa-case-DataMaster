import { dicaProcedencia, rotuloProcedencia } from '../lib/procedencia';

/** Badge de procedência: rótulo `.marca`, nunca cor (README §6). */
export function MarcaProcedencia({ origem, provedor }: { origem: string | null; provedor: string | null }) {
  const rotulo = rotuloProcedencia(origem, provedor);
  if (!rotulo) return null;
  return (
    <span className="marca" title={dicaProcedencia(origem, provedor)}>
      {rotulo}
    </span>
  );
}
