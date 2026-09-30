/**
 * `details.docs` do card: "Documentos do edital (N)" com Tipo · Arquivo ·
 * Pág. · SHA-256 (painel.py:_card). O link é pelo ID do arquivo,
 * `/api/pdf/{slug}/{id}` — o painel v2 linkava pelo nome cru, e os 26-29
 * nomes com `%` davam 404 (plano §8, defeito que não volta).
 *
 * `tem_pdf` (da API) decide o link: arquivo recusado ou ausente do storage
 * aparece com o status, sem link que daria 404.
 *
 * v_card só traz a contagem; a lista vem do detalhe e só é buscada quando
 * alguém abre o bloco — 770 cards não disparam 770 consultas.
 */
import { useState } from 'react';
import { useLicitacao } from '../api/consultas';
import type { Arquivo } from '../api/tipos';
import { milhar } from '../lib/formato';
import { Rolagem } from './Rolagem';

export function urlPdf(slug: string, arquivoId: number, pagina?: number | null): string {
  const base = `/api/pdf/${encodeURIComponent(slug)}/${arquivoId}`;
  return pagina ? `${base}#page=${pagina}` : base;
}

export function TabelaArquivos({ slug, arquivos }: { slug: string; arquivos: Arquivo[] }) {
  if (!arquivos.length) return <p className="vazio">sem inventário</p>;
  return (
    <Rolagem min={560}>
      <table>
        <thead>
          <tr>
            <th>Tipo</th>
            <th>Arquivo</th>
            <th>Pág.</th>
            <th>SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {arquivos.map((a) => (
            <tr key={a.id}>
              <td>{a.tipo || '—'}</td>
              <td>
                {a.tem_pdf ? (
                  <a href={urlPdf(slug, a.id)}>{a.nome}</a>
                ) : (
                  // Sem PDF no storage não há o que abrir: nome e motivo, sem link morto.
                  <span title={a.motivo ?? `Status do arquivo: ${a.status}`}>
                    {a.nome} <span className="sha">({a.status})</span>
                  </span>
                )}
              </td>
              <td>{a.paginas ? milhar(a.paginas) : '—'}</td>
              <td className="sha">{(a.sha256 ?? '').slice(0, 16)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Rolagem>
  );
}

export function DocumentosCard({ slug, total, arquivos }: { slug: string; total: number; arquivos?: Arquivo[] }) {
  const [aberto, setAberto] = useState(false);
  const consulta = useLicitacao(slug, aberto && !arquivos);
  const lista = arquivos ?? consulta.data?.arquivos;
  return (
    <details className="docs" onToggle={(e) => setAberto((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>Documentos do edital ({milhar(total)})</summary>
      {aberto &&
        (lista ? (
          <TabelaArquivos slug={slug} arquivos={lista} />
        ) : consulta.isError ? (
          <p className="vazio">Não foi possível carregar os documentos: {String(consulta.error.message)}</p>
        ) : (
          <p className="vazio">Carregando…</p>
        ))}
    </details>
  );
}
