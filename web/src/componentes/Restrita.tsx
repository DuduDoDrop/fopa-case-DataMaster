/**
 * A página que só um papel abre. O menu já não mostra o link; isto cobre quem digita o endereço. O servidor garante
 * com 403 de qualquer jeito — aqui a página nem pede os dados.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { permitido, useSessao, type Minimo } from './Sessao';

export function Restrita({ minimo, children }: { minimo: Minimo; children: ReactNode }) {
  const me = useSessao();
  if (permitido(me, minimo)) return <>{children}</>;
  return (
    <div className="pg-painel">
      <div className="wrap">
        <header>
          <h1>Sem acesso</h1>
          <p className="sub">
            {minimo === 'admin' ? 'Esta página é restrita a administradores.' : 'Esta página é restrita a revisores (operador ou administrador).'}{' '}
            <Link to="/">Voltar ao painel</Link>
          </p>
        </header>
      </div>
    </div>
  );
}
