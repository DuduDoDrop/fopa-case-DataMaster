/**
 * `/licitacao/:slug/relatorio` — abre o RELATORIO.html publicado
 * (`GET /api/licitacoes/{slug}/relatorio`, text/html gerado pelo
 * `pagina.escrever` no worker, links já em /api/pdf/...#page=N).
 *
 * Navegação de página inteira, não iframe: o relatório é um documento
 * completo, com o próprio "Voltar ao painel", e os links de PDF com #page
 * precisam abrir no navegador como se o arquivo tivesse sido aberto direto.
 */
import '../../design/relatorio.css';
import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';

export function urlRelatorio(slug: string): string {
  return `/api/licitacoes/${encodeURIComponent(slug)}/relatorio`;
}

const substituirPagina = (u: string) => window.location.replace(u);

export function Relatorio({ navegar = substituirPagina }: { navegar?: (u: string) => void }) {
  const { slug = '' } = useParams();
  const destino = urlRelatorio(slug);
  useEffect(() => {
    if (slug) navegar(destino);
  }, [slug, destino, navegar]);
  return (
    <div className="pg-relatorio">
      <div className="wrap">
        <Link className="voltar" to={`/licitacao/${slug}`}>
          <b>←</b> Voltar à licitação
        </Link>
        <p className="sub">
          Abrindo o relatório… Caso não abra, <a href={destino}>clique aqui</a>.
        </p>
      </div>
    </div>
  );
}
