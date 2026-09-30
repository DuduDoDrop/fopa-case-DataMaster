/**
 * `/emails` — o que o W50 enviou (ou tentou), com o corpo COMO FOI enviado:
 * o administrador vê os e-mails sem abrir o Gmail (plano §8).
 *
 * O corpo vai num iframe `sandbox` sem nenhuma permissão: é HTML gerado a
 * partir de dados do PNCP (objeto, órgão), e script ali não pode rodar com
 * a sessão do site.
 */
import '../../design/painel.css';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useEmails } from '../api/consultas';
import { Carregando, Falha } from '../componentes/Estado';
import { Rolagem } from '../componentes/Rolagem';
import { dataHora, datasNoTexto, milhar } from '../lib/formato';

export function Emails() {
  const consulta = useEmails();
  const emails = consulta.data?.itens;
  const [aberto, setAberto] = useState<number | null>(null);
  return (
    <div className="pg-painel">
      <div className="wrap">
        <header>
          <p className="eyebrow">FOPA · comunicação</p>
          <h1>E-mails</h1>
          <p className="sub">Fila de envio de e-mails: pendentes, enviados e com falha, com o conteúdo enviado.</p>
        </header>
        {consulta.isError ? (
          <Falha erro={consulta.error} oque="os e-mails" />
        ) : !emails ? (
          <Carregando />
        ) : emails.length === 0 ? (
          <p className="vazio">Nenhum e-mail na fila.</p>
        ) : (
          <Rolagem min={640}>
            <table>
              <thead>
                <tr>
                  <th>Quando</th>
                  <th>Tipo</th>
                  <th>Para</th>
                  <th>Assunto</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {emails.map((e) => (
                  <tr key={e.id}>
                    <td className="sha nw">{dataHora(e.enviado_em ?? e.em)}</td>
                    <td>
                      <code>{e.tipo}</code>
                      {e.controle && (
                        <>
                          {' '}
                          ·{' '}
                          {e.slug ? <Link to={`/licitacao/${e.slug}`}>{e.controle}</Link> : <span className="sha">{e.controle}</span>}
                        </>
                      )}
                    </td>
                    <td className="sha">{e.para ?? '—'}</td>
                    <td>
                      {e.assunto}
                      {e.corpo_html ? (
                        <details open={aberto === e.id} onToggle={(ev) => setAberto((ev.currentTarget as HTMLDetailsElement).open ? e.id : null)}>
                          <summary>Ver o conteúdo enviado</summary>
                          {aberto === e.id && (
                            <iframe className="corpo-email" title={`Conteúdo do e-mail ${e.id}`} sandbox="" srcDoc={e.corpo_html} />
                          )}
                        </details>
                      ) : (
                        <span className="sha"> (sem corpo gravado)</span>
                      )}
                    </td>
                    <td className={e.status === 'falhou' ? 'falhou' : e.status === 'pendente' ? 'gastou' : undefined}>
                      {e.status}
                      {e.canal ? ` · ${e.canal}` : ''}
                      {e.tentativas > 1 ? ` · ${milhar(e.tentativas)} tentativas` : ''}
                      {e.erro && <div className="sha">{datasNoTexto(e.erro)}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Rolagem>
        )}
      </div>
    </div>
  );
}
