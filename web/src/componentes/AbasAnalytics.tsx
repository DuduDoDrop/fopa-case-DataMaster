/**
 * As duas páginas do Analytics em abas. O menu de cima tem só
 * "Analytics": a troca é por estes botões, grandes, no topo da
 * página, com a atual marcada.
 */
import { NavLink } from 'react-router-dom';

export function AbasAnalytics() {
  return (
    <nav className="abas" aria-label="Páginas do Analytics">
      <NavLink to="/analytics" end>
        Analytics de Mercado
      </NavLink>
      <NavLink to="/analytics/historico-fopa">Analytics Histórico FOPA</NavLink>
    </nav>
  );
}
