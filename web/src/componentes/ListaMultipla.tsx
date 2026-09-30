import { useEffect, useId, useRef, useState } from 'react';
import type { OpcaoLista } from './Lista';

/**
 * Escolha de vários itens com rótulo. Um botão com
 * o resumo do que está marcado abre as caixas; Esc ou clique fora fecha. A mesma medida da `Lista` (extra.css).
 */
export function ListaMultipla({
  rotulo,
  marcados,
  opcoes,
  aoAlternar,
}: {
  rotulo: string;
  marcados: string[];
  opcoes: OpcaoLista[];
  aoAlternar: (valor: string) => void;
}) {
  const [aberta, setAberta] = useState(false);
  const id = useId();
  const raiz = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberta) return;
    const fora = (e: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAberta(false);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setAberta(false);
    };
    document.addEventListener('mousedown', fora);
    document.addEventListener('keydown', tecla);
    return () => {
      document.removeEventListener('mousedown', fora);
      document.removeEventListener('keydown', tecla);
    };
  }, [aberta]);

  const textos = opcoes.filter((o) => marcados.includes(o.valor)).map((o) => o.texto);
  const resumo = textos.length === 0 ? '—' : textos.length <= 2 ? textos.join(', ') : `${textos.length} selecionados`;

  return (
    <div className="lista lista-multipla" ref={raiz}>
      <span aria-hidden="true">{rotulo}</span>
      <button
        type="button"
        aria-label={`${rotulo}: ${resumo}`}
        aria-expanded={aberta}
        aria-controls={id}
        onClick={() => setAberta((a) => !a)}
      >
        {resumo}
      </button>
      {aberta && (
        <fieldset id={id} className="lista-multipla-opcoes" aria-label={rotulo}>
          {opcoes.map((o) => (
            <label key={o.valor}>
              <input type="checkbox" checked={marcados.includes(o.valor)} onChange={() => aoAlternar(o.valor)} />
              {o.texto}
            </label>
          ))}
        </fieldset>
      )}
    </div>
  );
}
