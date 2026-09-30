import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ListaMultipla } from '../componentes/ListaMultipla';

const OPCOES = [
  { valor: 'todas', texto: 'Todas' },
  { valor: 'conflito', texto: 'Com conflito' },
  { valor: 'extraidas', texto: 'Já extraídas' },
  { valor: 'alerta', texto: 'Com alerta de regra' },
];

describe('ListaMultipla', () => {
  it('o botão resume o que está marcado e abre as caixas', async () => {
    const u = userEvent.setup();
    render(<ListaMultipla rotulo="Mostrar" marcados={['conflito', 'extraidas']} opcoes={OPCOES} aoAlternar={() => {}} />);
    const botao = screen.getByRole('button', { name: 'Mostrar: Com conflito, Já extraídas' });
    expect(botao).toHaveAttribute('aria-expanded', 'false');
    await u.click(botao);
    expect(botao).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('checkbox', { name: 'Com conflito' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Com alerta de regra' })).not.toBeChecked();
  });

  it('mais de dois marcados vira contagem', () => {
    render(<ListaMultipla rotulo="Mostrar" marcados={['conflito', 'extraidas', 'alerta']} opcoes={OPCOES} aoAlternar={() => {}} />);
    expect(screen.getByRole('button', { name: 'Mostrar: 3 selecionados' })).toBeInTheDocument();
  });

  it('marcar uma caixa avisa o valor; Esc e clique fora fecham', async () => {
    const u = userEvent.setup();
    const aoAlternar = vi.fn();
    render(
      <div>
        <ListaMultipla rotulo="Mostrar" marcados={['todas']} opcoes={OPCOES} aoAlternar={aoAlternar} />
        <p>fora</p>
      </div>,
    );
    await u.click(screen.getByRole('button', { name: 'Mostrar: Todas' }));
    await u.click(screen.getByRole('checkbox', { name: 'Com conflito' }));
    expect(aoAlternar).toHaveBeenCalledWith('conflito');
    await u.keyboard('{Escape}');
    expect(screen.queryByRole('checkbox', { name: 'Com conflito' })).toBeNull();
    await u.click(screen.getByRole('button', { name: 'Mostrar: Todas' }));
    await u.click(screen.getByText('fora'));
    expect(screen.queryByRole('checkbox', { name: 'Com conflito' })).toBeNull();
  });
});
