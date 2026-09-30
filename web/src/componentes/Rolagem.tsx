/**
 * Tabela larga no celular rola dentro do próprio bloco.
 *
 * Em 390 px o RELATORIO.html (e o site, que segue o molde) espremia as
 * colunas até o texto quebrar letra a letra — a resposta da Q1 virava uma
 * coluna de 70 px com 19 linhas — e as tabelas de execuções, e-mails, saúde
 * e admin estouravam a página para o lado. Abaixo de 640 px a tabela ganha
 * uma largura mínima (`min`) e rola na horizontal aqui dentro; acima disso
 * nada muda: a tabela continua com 100% da largura, como no HTML
 * (extra.css, `.rolagem`).
 */
import type { CSSProperties, ReactNode } from 'react';

export function Rolagem({ min = 640, children }: { min?: number; children: ReactNode }) {
  return (
    <div className="rolagem" style={{ '--min-tabela': `${min}px` } as CSSProperties}>
      {children}
    </div>
  );
}
