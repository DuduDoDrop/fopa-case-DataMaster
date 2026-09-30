/**
 * Condições de leitura (pagina.py, bloco "condições de operação").
 *
 * Fica ACIMA do questionário de propósito: quem lê as respostas precisa
 * saber antes, não depois, se a leitura aconteceu com um documento faltando
 * ou com OCR num anexo digitalizado. A tag de injeção é deliberadamente mais
 * forte que o resto: as outras condições dizem "leia com ressalva"; esta diz
 * "alguém tentou manipular este documento".
 *
 * Logo abaixo do aviso, o "ver mais" com o texto escondido que a varredura achou
 * (db/028, api/injecao.py): o que tem cara de instrução para IA primeiro, e o
 * resto com o que é — timbre, camada de OCR, planta —, para quem lê decidir.
 */
import type { Condicoes as TCondicoes, TrechoFurtivo, VarreduraFurtivos } from '../api/tipos';
import { milhar } from '../lib/formato';

export function TextoEscondido({
  furtivos,
  varredura,
}: {
  furtivos: TrechoFurtivo[];
  varredura?: VarreduraFurtivos | null;
}) {
  if (!varredura && furtivos.length === 0) return null;
  const total = varredura?.achados ?? furtivos.length;
  const suspeitos = varredura?.suspeitos ?? furtivos.filter((f) => f.suspeito).length;
  if (total === 0 && !varredura?.erro) return null;
  return (
    <details className={suspeitos > 0 ? 'furtivos susp' : 'furtivos'}>
      <summary>
        Ver mais: {milhar(total)} {total === 1 ? 'trecho' : 'trechos'} de texto oculto
        {suspeitos > 0
          ? `, ${milhar(suspeitos)} com aparência de instrução para IA`
          : ', nenhum com aparência de instrução para IA'}
      </summary>
      {varredura?.erro && <p className="aviso">Não foi possível concluir a varredura: {varredura.erro}</p>}
      <ol>
        {furtivos.map((f, i) => (
          <li key={i} className={f.suspeito ? 'susp' : undefined}>
            <span className="onde">
              {f.arquivo} · p.{f.pagina} · {f.motivo}
              {f.linhas > 1 ? ` · ${milhar(f.linhas)} linhas` : ''}
            </span>
            <span className="classe">{f.classe}</span>
            <blockquote>
              {f.texto}
              {f.caracteres > f.texto.length ? ` … (+${milhar(f.caracteres - f.texto.length)} caracteres)` : ''}
            </blockquote>
          </li>
        ))}
      </ol>
      {total > furtivos.length && (
        <p className="meta">
          mostrando {milhar(furtivos.length)} de {milhar(total)} — os com cara de instrução sempre entram primeiro
        </p>
      )}
    </details>
  );
}

export function temCondicoes(c: TCondicoes | null | undefined): c is TCondicoes {
  if (!c) return false;
  return !!((c.motivos && c.motivos.length) || (c.abstencoes && c.abstencoes.length) || c.modelo?.modelo || c.degradada || (c.tags && c.tags.length));
}

export function Condicoes({
  c,
  tagsExtras = [],
  furtivos = [],
  varredura = null,
}: {
  c: TCondicoes;
  tagsExtras?: string[];
  furtivos?: TrechoFurtivo[];
  varredura?: VarreduraFurtivos | null;
}) {
  const tags = Array.from(new Set([...(c.tags ?? []), ...tagsExtras]));
  const motivos = c.motivos ?? [];
  const abst = c.abstencoes ?? [];
  const docs = c.documentos ?? {};
  const obtidos = docs.obtidos ?? 0;
  return (
    <div className={c.degradada ? 'cond deg' : 'cond ok'}>
      {tags.map((t) => (
        <span key={t}>
          <span className="tagsusp">{t}</span>
          <br />
        </span>
      ))}
      <TextoEscondido furtivos={furtivos} varredura={varredura} />
      <b>{c.degradada ? 'Esta leitura ocorreu em condição degradada' : 'Condições normais de leitura'}</b>
      {motivos.length > 0 ? (
        <ul>
          {motivos.map((m, i) => (
            <li key={i}>{m}</li>
          ))}
        </ul>
      ) : abst.length === 0 ? (
        <ul>
          <li>Todos os documentos do inventário foram lidos, nenhum exigiu OCR, e o modelo principal respondeu.</li>
        </ul>
      ) : null}
      {abst.length > 0 && (
        <ul>
          <li>
            O sistema <b>absteve-se</b> em {abst.length} {abst.length === 1 ? 'pergunta' : 'perguntas'}: {abst.join(', ')}.
            A evidência foi procurada e não foi encontrada.
          </li>
        </ul>
      )}
      {docs.faltando && docs.faltando.length > 0 && (
        <ul>
          <li>Documentos ausentes: {docs.faltando.join(', ')}</li>
        </ul>
      )}
      <span className="meta">
        {c.modelo?.modelo || '?'} · effort {c.modelo?.effort || '?'} · {milhar(obtidos)} de{' '}
        {milhar(docs.esperados || obtidos)} {(docs.esperados || obtidos) === 1 ? 'documento' : 'documentos'} · corpus há{' '}
        {c.corpus_horas !== null && c.corpus_horas !== undefined ? `${Math.round(c.corpus_horas)}h` : '—'}
      </span>
    </div>
  );
}
