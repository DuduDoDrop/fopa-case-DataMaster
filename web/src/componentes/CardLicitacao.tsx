/**
 * Um card por CONTROLE (ADR-013), no molde de `painel.py:_card`:
 * topo (local, meta, objeto) + prazo à direita, faixa `.nums`, até 3
 * alertas, documentos, ações. As classes são as de painel.css.
 */
import { Link } from 'react-router-dom';
import type { Card, JevFiltro } from '../api/tipos';
import { custo, milhar } from '../lib/formato';
import { calcularPrazo } from '../lib/prazo';
import { AVISO_IA_FOLHA, opiniaoIa } from '../lib/respostas';
import { DocumentosCard } from './Documentos';
import { MarcaProcedencia } from './MarcaProcedencia';
import { PrazoBadge } from './PrazoBadge';
import { ehAdmin, useSessao } from './Sessao';

const TAG_INJECAO = 'Prompt Injection - Conteúdo Suspeito';

/**
 * O selo da IA: a opinião do Jev sobre ser compra de folha, em palavras ("IA: é folha (93%)"), nunca decisão. Só
 * ganha destaque âmbar (olho humano, README §2) quando o Jev discorda do escopo com convicção (candidata) — aí o selo
 * leva à aba de escopo da /revisao.
 */
function SeloJev({ jev, controle }: { jev: JevFiltro; controle: string }) {
  // API anterior sem p_folha: no card (sempre dentro do escopo) a chance de o filtro acertar É a de ser folha
  // A revisão de escopo é só do admin: o usuário vê o destaque, mas o selo não leva à aba que ele não vê.
  // (o hook vem antes de qualquer return: regra dos hooks)
  const admin = ehAdmin(useSessao());
  const op = opiniaoIa(jev.p_folha ?? jev.p_filtro_ok);
  if (op === null) return null;
  const atencao = jev.discorda && jev.candidata;
  const dica = `${AVISO_IA_FOLHA}${atencao ? ` A IA discorda do escopo com alta confiança.${admin ? ' Clique para revisar.' : ''}` : ''}`;
  if (atencao && !admin) {
    return (
      <span className={`marca jev ${op.classe} jev-atencao`} title={dica}>
        {op.texto}
      </span>
    );
  }
  if (!atencao) {
    return (
      <span className={`marca jev ${op.classe}`} title={dica}>
        {op.texto}
      </span>
    );
  }
  return (
    <Link
      className={`marca jev ${op.classe} jev-atencao`}
      title={dica}
      to={`/revisao?aba=escopo&controle=${encodeURIComponent(controle)}`}
    >
      {op.texto}
    </Link>
  );
}

export function CardLicitacao({ card: c, agora }: { card: Card; agora: Date }) {
  const prazo = calcularPrazo(c, agora);
  // "Modalidade · controle": só o que acrescenta; nunca repetir o nome da
  // pasta embaixo do título (painel.py, "Credenciamento · Credenciamento - …").
  const meta = [c.modalidade || 'modalidade não informada', c.controle].filter(Boolean).join(' · ');
  const alertas = (c.alertas_globais ?? []).slice(0, 3);
  const outrasTags = (c.tags ?? []).filter((t) => t !== TAG_INJECAO);

  return (
    <article className={prazo.classe ? `card ${prazo.classe}` : 'card'} data-controle={c.controle}>
      <div className="topo">
        <div>
          <p className="nome">{c.local}</p>
          <p className="meta">{meta}</p>
          <p className="obj">{(c.objeto ?? '').slice(0, 340)}</p>
          <p className="rotulos">
            <MarcaProcedencia origem={c.procedencia} provedor={c.provedor} />
            {c.procedencia_completa === false && (
              <span className="marca" title="Não foi possível comprovar a origem desta execução na importação.">
                procedência incompleta
              </span>
            )}
            {c.ensaio && (
              <span className="marca" title="Licitação de teste: aceita extração simulada.">
                ensaio
              </span>
            )}
            {c.injecao_suspeita && <span className="tagsusp">{TAG_INJECAO}</span>}
            {c.sem_pdf && (
              // Sem arquivo PDF válido, a flag avisa
              <span
                className="marca sem-pdf"
                title={`O edital não está em PDF legível (${c.sem_pdf}), formato que o sistema não processa. Solicite o PDF ao órgão.`}
              >
                sem PDF válido
              </span>
            )}
            {outrasTags.map((t) => (
              <span key={t} className="marca">
                {t}
              </span>
            ))}
            {c.no_recorte === false && (
              <span className="marca" title="Sessão ou publicação anterior ao ano mínimo do acompanhamento.">
                fora do recorte
              </span>
            )}
            {c.jev_filtro && <SeloJev jev={c.jev_filtro} controle={c.controle} />}
          </p>
        </div>
        <PrazoBadge prazo={prazo} />
      </div>

      <div className="nums">
        {c.extraida ? (
          <>
            <div className={c.ancoradas === c.respondidas && c.respondidas > 0 ? 'num ok' : 'num al'}>
              <b>
                {milhar(c.ancoradas)}/{milhar(c.respondidas)}
              </b>
              <span>ancoragem</span>
            </div>
            <div className={c.conflitos > 0 ? 'num am' : 'num'}>
              <b>{milhar(c.conflitos)}</b>
              <span>conflitos</span>
            </div>
            <div className="num">
              <b>{milhar(c.nao_localizado)}</b>
              <span>não localizado</span>
            </div>
            <div className={c.revisar > 0 ? 'num am' : 'num'}>
              <b>{milhar(c.revisar)}</b>
              <span>revisar</span>
            </div>
            <div className="num">
              <b>{custo(c)}</b>
              <span>custo</span>
            </div>
          </>
        ) : (
          <div className="num">
            <b>—</b>
            <span>ainda não extraída</span>
          </div>
        )}
      </div>

      {alertas.map((a, i) => (
        <p key={i} className="alerta">
          {a.slice(0, 300)}
        </p>
      ))}

      <DocumentosCard slug={c.slug} total={c.n_arquivos} />

      <div className="acoes">
        {c.extraida ? (
          <Link className="forte" to={`/licitacao/${c.slug}`}>
            Ver as 17 respostas
          </Link>
        ) : (
          // Botão morto é pior que botão nenhum: sem href, com o motivo.
          <a
            aria-disabled="true"
            title="Esta licitação ainda não foi extraída."
          >
            sem extração
          </a>
        )}
        {!c.extraida && (
          <Link to={`/licitacao/${c.slug}`} title="Documentos, estado e linha do tempo">
            Ver a licitação
          </Link>
        )}
        {c.link && (
          <a href={c.link} target="_blank" rel="noopener">
            Abrir no PNCP
          </a>
        )}
      </div>
    </article>
  );
}
