/**
 * "← Anterior · página X de Y · Próxima →" — a mesma navegação no painel (paginado no servidor) e na Analytics
 * Histórico FOPA (paginada no navegador). Só aparece
 * com mais de uma página; quem chama decide o que "ir para a página N" faz (em geral, mudar a URL).
 *
 * Vai em cima e embaixo da grade, com
 * nomes diferentes para o leitor de tela. A de cima só da página 2 em diante.
 *
 * Ao passar de página, a tela vai ao alto da grade: quem chama embrulha a barra de cima e os itens num container
 * (`.grade-lista`) e passa o ref dele em `topo`. O alto do container é a barra de cima quando ela existe e o primeiro
 * item quando não — e ele está na tela
 * antes e depois da troca, que acontece dentro dele.
 */
import type { RefObject } from 'react';
import { milhar } from '../lib/formato';

/** Leva a tela ao alto da grade. `?.` duas vezes: sem a grade na tela, ou num navegador sem scrollIntoView, nada. */
export function rolarAoTopo(topo: RefObject<HTMLElement | null>) {
  topo.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
}

export interface PropsPaginacao {
  pagina: number;
  paginas: number;
  irPara: (pagina: number) => void;
  /** em cima ou embaixo da grade: dá o nome da barra ("Paginação, acima/abaixo da lista"); a de cima só da página 2 */
  posicao: 'topo' | 'fim';
  /** o container da grade (`.grade-lista`): ao trocar de página, a tela vai ao alto dele */
  topo?: RefObject<HTMLElement | null>;
}

export function Paginacao({ pagina, paginas, irPara, posicao, topo }: PropsPaginacao) {
  if (paginas <= 1 || (posicao === 'topo' && pagina <= 1)) return null;
  const ir = (n: number) => {
    irPara(n);
    if (topo) rolarAoTopo(topo);
  };
  return (
    <nav className="paginacao" aria-label={posicao === 'topo' ? 'Paginação, acima da lista' : 'Paginação, abaixo da lista'}>
      <button
        type="button"
        className="secundario"
        disabled={pagina <= 1}
        title={pagina <= 1 ? 'Esta é a primeira página.' : undefined}
        onClick={() => ir(pagina - 1)}
      >
        ← Anterior
      </button>
      <span className="atualmsg">
        página {milhar(pagina)} de {milhar(paginas)}
      </span>
      <button
        type="button"
        className="secundario"
        disabled={pagina >= paginas}
        title={pagina >= paginas ? 'Esta é a última página.' : undefined}
        onClick={() => ir(pagina + 1)}
      >
        Próxima →
      </button>
    </nav>
  );
}

/** "mostrando 11–20 de 57": o trecho da lista que está na tela (página começa em 1). */
export function trecho(pagina: number, porPagina: number, naTela: number, total: number): string {
  const de = (pagina - 1) * porPagina + 1;
  return naTela === 0 ? `mostrando 0 de ${milhar(total)}` : `mostrando ${milhar(de)}–${milhar(de + naTela - 1)} de ${milhar(total)}`;
}
