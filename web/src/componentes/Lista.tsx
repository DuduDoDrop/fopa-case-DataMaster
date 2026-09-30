/**
 * Uma escolha em lista com rótulo — o que substitui os grupos de botões soltos da barra de filtros. O rótulo fica
 * visível ao lado; a lista tem o mesmo nome para o leitor de tela, e a mesma altura da busca.
 */
export interface OpcaoLista {
  valor: string;
  texto: string;
}

export function Lista({
  rotulo,
  valor,
  opcoes,
  aoMudar,
}: {
  rotulo: string;
  valor: string;
  opcoes: OpcaoLista[];
  aoMudar: (valor: string) => void;
}) {
  return (
    <label className="lista">
      <span aria-hidden="true">{rotulo}</span>
      <select aria-label={rotulo} value={valor} onChange={(e) => aoMudar(e.target.value)}>
        {opcoes.map((o) => (
          <option key={o.valor} value={o.valor}>
            {o.texto}
          </option>
        ))}
      </select>
    </label>
  );
}
