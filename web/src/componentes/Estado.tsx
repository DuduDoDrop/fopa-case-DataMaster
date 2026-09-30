/** Carregando / erro, no tom do `.vazio` do painel. */
import { ErroApi } from '../api/cliente';

export function Carregando({ texto = 'Carregando…' }: { texto?: string }) {
  return <p className="vazio">{texto}</p>;
}

export function Falha({ erro, oque }: { erro: unknown; oque: string }) {
  const msg = erro instanceof Error ? erro.message : String(erro);
  const codigo = erro instanceof ErroApi ? ` ${erro.status}` : '';
  return (
    <p className="vazio" role="alert">
      Não foi possível carregar {oque}. Tente novamente em instantes.
      <br />
      <small>
        Detalhe{codigo}: {msg}
      </small>
    </p>
  );
}
