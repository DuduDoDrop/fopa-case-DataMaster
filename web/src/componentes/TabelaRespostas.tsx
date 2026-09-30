/**
 * A tabela das 17 (pagina.py:escrever, bloco "questionário").
 *
 * - A barra à esquerda codifica o STATUS, e nada mais: st-ok conferido,
 *   st-rev revisar, st-nl não localizado — que vence o veredito.
 * - Crítica é RÓTULO (.marca), nunca cor: a barra vermelha da crítica fazia
 *   uma linha perfeita parecer defeito.
 * - O bloco de evidência aparece em TODAS as linhas. Num relatório cuja tese
 *   é "nada entra sem evidência", evidência faltando é a informação mais
 *   importante da linha — e era a única que não estava escrita.
 * - Origem: "arquivo — p. N" → /api/pdf/{slug}/{arquivo_id}#page=N, pelo ID.
 * - As linhas chegam JÁ juntadas (lib/respostas.ts:mesclarRespostas): a API
 *   manda `respostas` e `verificacao_respostas` separadas.
 * - Jev (opcional): "sustenta N%" ao lado de TODA resposta que cita trecho,
 *   qualquer veredito — um score, nunca um veredito; a pílula do
 *   verificador continua a mesma. Sem trecho citado não há passagem para o
 *   Jev julgar, e a linha diz isso em vez de ficar muda.
 * - Best-of-N (opcional, v3.1): a pergunta que ganhou tentativas extras diz
 *   qual ficou, numa nota discreta na célula da verificação (MelhorDeN.tsx).
 */
import type { Ausencia, JevSustenta, Q13, RespostaDetalhe, TentativasMelhorDeN } from '../api/tipos';
import { AVISO_JEV, percentual } from '../lib/respostas';
import { urlPdf } from './Documentos';
import { DistribuicaoQ13 } from './DistribuicaoQ13';
import { NotaMelhorDeN } from './MelhorDeN';
import { Rolagem } from './Rolagem';

function normalizar(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .trim();
}

/** verificador.py:nao_encontrou — "Não localizado" em qualquer das formas. */
export function naoEncontrou(resposta: string | null | undefined): boolean {
  return normalizar(resposta ?? '').startsWith('nao localizado');
}

const PREFIXO_NAO_APLICA = 'não se aplica a esta modalidade';

const AUSENCIAS: readonly string[] = ['nao_se_aplica', 'sem_evidencia', 'falta_evidencia'];

function ehAusencia(v: string | null | undefined): v is Ausencia {
  return !!v && AUSENCIAS.includes(v);
}

/**
 * O motivo da ausência. Vem pronto de `verificacao_respostas.ausencia`
 * (migracao/regras.py:ausencia); se faltar, a mesma regra roda aqui.
 */
export function ausenciaDe(r: RespostaDetalhe): Ausencia | null {
  if (r.trecho_literal) return null;
  if (ehAusencia(r.ausencia)) return r.ausencia;
  if (naoEncontrou(r.resposta)) {
    return (r.alertas ?? []).some((a) => (a ?? '').startsWith(PREFIXO_NAO_APLICA)) ? 'nao_se_aplica' : 'sem_evidencia';
  }
  return 'falta_evidencia';
}

export type Status = 'st-ok' | 'st-rev' | 'st-nl';

export function statusDaLinha(r: RespostaDetalhe): Status {
  if (naoEncontrou(r.resposta) || !r.arquivo_citado) return 'st-nl';
  return r.veredito === 'APROVADO' ? 'st-ok' : 'st-rev';
}

export function Evidencia({ r }: { r: RespostaDetalhe }) {
  const ausencia = ausenciaDe(r);
  if (!ausencia) {
    return (
      <details>
        <summary>Ver evidência</summary>
        <blockquote>{r.trecho_literal}</blockquote>
      </details>
    );
  }
  if (ausencia === 'nao_se_aplica') {
    const alerta = (r.alertas ?? []).find((a) => a.startsWith(PREFIXO_NAO_APLICA)) ?? '';
    const motivo = alerta.includes('—') ? alerta.split('—').slice(1).join('—').trim() : '';
    return (
      <details>
        <summary>Ver evidência</summary>
        <blockquote className="naoaplica">
          <b>Não se aplica a esta modalidade.</b> {motivo ? `${motivo}. ` : ''}A pergunta foi desenhada para pregão e
          concorrência; aqui não há o que citar.
        </blockquote>
      </details>
    );
  }
  if (ausencia === 'sem_evidencia') {
    return (
      <details>
        <summary>Ver evidência</summary>
        <blockquote className="semev">
          Sem trecho: a informação não consta dos documentos. A ausência é a resposta e pode motivar um pedido de
          esclarecimento ao órgão.
        </blockquote>
      </details>
    );
  }
  return (
    <details open>
      <summary>Ver evidência</summary>
      <blockquote className="faltaev">
        <b>Evidência não encontrada.</b> A resposta não traz trecho literal e não pode ser conferida no documento.
        Revise na fonte antes de usar.
      </blockquote>
    </details>
  );
}

export function Origem({ slug, r, status }: { slug: string; r: RespostaDetalhe; status: Status }) {
  if (status === 'st-nl') return <span className="nl">não localizado</span>;
  const pagina = r.pagina_final ?? r.pagina_citada;
  // "p. N" não se separa: a coluna é estreita e o número caía sozinho na linha de baixo
  const texto = (
    <>
      {r.arquivo_citado}
      {pagina ? (
        <>
          {' — '}
          <span className="pag">p. {pagina}</span>
        </>
      ) : null}
    </>
  );
  if (r.arquivo_id === null || r.arquivo_id === undefined) {
    // Sem id o link só poderia ser pelo nome cru — o defeito dos 26-29 links
    // quebrados. Melhor dizer que não resolveu do que apontar para um 404.
    return (
      <span className="nl" title="O arquivo citado não foi localizado no inventário.">
        {texto}
      </span>
    );
  }
  return (
    <a
      href={urlPdf(slug, r.arquivo_id, pagina)}
      target="_blank"
      rel="noopener"
      title={r.pagina_citada && pagina !== r.pagina_citada ? `O modelo citou a p. ${r.pagina_citada}; o verificador encontrou o trecho na p. ${pagina}.` : undefined}
    >
      {texto}
    </a>
  );
}

export function Legenda({ comJev = false }: { comJev?: boolean }) {
  return (
    <p className="legenda">
      <span className="lg lg-ok">conferido</span>
      <span className="lg lg-rev">revisar</span>
      <span className="lg lg-nl">não localizado</span>
      <span className="lgnota">a barra à esquerda de cada linha</span>
      {comJev && (
        <span className="lgnota">
          <span className="marca">sustenta N%</span> = {AVISO_JEV}
        </span>
      )}
    </p>
  );
}

/** A pílula do veredito; `null` (sem linha na verificação) não vira APROVADO. */
export function PilulaVeredito({ veredito }: { veredito: string | null }) {
  return <span className={`v ${veredito ?? ''}`.trim()}>{veredito ?? 'sem veredito'}</span>;
}

function SustentaJev({ s, semTrecho }: { s: JevSustenta | undefined; semTrecho: boolean }) {
  const p = s ? percentual(s.p_sustenta) : null;
  if (semTrecho && !s) {
    return (
      <span className="marca jev nada" title="A resposta não cita trecho; não há passagem para o Jev avaliar.">
        Jev: sem trecho
      </span>
    );
  }
  if (!s || p === null) return null;
  const detalhe = [s.resposta, s.contexto_enviado ? `contexto: ${s.contexto_enviado}` : null].filter(Boolean).join(' · ');
  return (
    <span className="marca jev" title={`${AVISO_JEV}${detalhe ? ` (${detalhe})` : ''}`}>
      sustenta {p}
    </span>
  );
}

export function TabelaRespostas({
  slug,
  respostas,
  q13,
  jevSustenta,
  melhorDeN,
}: {
  slug: string;
  respostas: RespostaDetalhe[];
  q13: Q13 | null;
  jevSustenta?: Record<string, JevSustenta> | null;
  /** `melhor_de_n.perguntas` do detalhe: só as perguntas que ganharam tentativas extras */
  melhorDeN?: Record<string, TentativasMelhorDeN> | null;
}) {
  const ordenadas = [...respostas].sort((a, b) => Number(a.pergunta_id.slice(1)) - Number(b.pergunta_id.slice(1)));
  return (
    <Rolagem min={720}>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Resposta</th>
            <th>Origem</th>
            <th>Verificação</th>
          </tr>
        </thead>
        <tbody>
          {ordenadas.map((r) => {
            const status = statusDaLinha(r);
            const alertas = r.alertas ?? [];
            return (
              <tr key={r.pergunta_id} className={status} data-pergunta={r.pergunta_id}>
                <td className="qid">
                  {r.pergunta_id}
                  <span className="perg">{r.pergunta}</span>
                  {r.critico && (
                    <span className="marca" title="Entra no cálculo do lance">
                      crítica
                    </span>
                  )}
                </td>
                <td>
                  <span className="resposta">{r.resposta}</span>
                  {r.pergunta_id === 'Q13' && <DistribuicaoQ13 q13={q13} />}
                  <Evidencia r={r} />
                  {r.conflito && (
                    <details open>
                      <summary>conflito entre documentos</summary>
                      <blockquote className="conf">{r.conflito}</blockquote>
                    </details>
                  )}
                  {alertas.length > 0 && (
                    <details>
                      <summary>
                        {alertas.length} {alertas.length === 1 ? 'alerta' : 'alertas'} da verificação
                      </summary>
                      <blockquote>{alertas.join(' · ')}</blockquote>
                    </details>
                  )}
                </td>
                <td className="info">
                  <Origem slug={slug} r={r} status={status} />
                </td>
                <td>
                  <PilulaVeredito veredito={r.veredito} />
                  {jevSustenta && (
                    <SustentaJev s={jevSustenta[r.pergunta_id]} semTrecho={!(r.trecho_literal ?? '').trim()} />
                  )}
                  <NotaMelhorDeN registro={melhorDeN?.[r.pergunta_id]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Rolagem>
  );
}
