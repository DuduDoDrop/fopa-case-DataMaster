/**
 * O padrão "botão → achados com custo estimado → Confirmar / Agora não →
 * progresso" do painel v2 (`.achados`, `.primario`, `.secundario`,
 * `.progresso`). Nada que possa gastar dinheiro sai sem esta tela dizer
 * quanto e por qual provedor.
 */
import type { ReactNode } from 'react';

export function Confirmacao({
  rotulo,
  titulo,
  children,
  confirmar,
  aoConfirmar,
  aoCancelar,
  ocupado = false,
  erro,
  feito,
}: {
  rotulo: string;
  titulo: string;
  children: ReactNode;
  confirmar: string;
  aoConfirmar: () => void;
  aoCancelar: () => void;
  ocupado?: boolean;
  erro?: string | null;
  feito?: ReactNode;
}) {
  return (
    <div className="achados" role="group" aria-label={rotulo}>
      <h3>{titulo}</h3>
      {children}
      {feito ? (
        <div className="progresso">{feito}</div>
      ) : (
        <div className="acoes">
          <button type="button" className="primario" onClick={aoConfirmar} disabled={ocupado}>
            {ocupado ? 'Enviando…' : confirmar}
          </button>
          <button type="button" className="secundario" onClick={aoCancelar} disabled={ocupado}>
            Cancelar
          </button>
        </div>
      )}
      {erro && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
    </div>
  );
}
