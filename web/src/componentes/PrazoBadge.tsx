import type { Prazo } from '../lib/prazo';

/** `.prazo(.urgente/.aviso) > b + span` (painel.css; README §4). */
export function PrazoBadge({ prazo }: { prazo: Prazo }) {
  return (
    <div className={prazo.classe ? `prazo ${prazo.classe}` : 'prazo'} title={prazo.dica || undefined}>
      <b>{prazo.titulo}</b>
      <span>{prazo.detalhe}</span>
    </div>
  );
}
