/**
 * `/admin` (plano §8): "Verificar agora", configuração (provedor com aviso
 * de custo), orçamento, termos, usuários e reserva para a demo.
 *
 * Contrato: `api/site.py`, rotas `/api/admin/*` (listas em `{itens:[...]}`).
 * Configuração é `PUT /api/admin/configuracao {chave, valor, confirmar}`:
 * trocar o provedor para um que cobra devolve 409 sem `confirmar=true` — a
 * tela mostra o aviso de custo da própria API e só reenvia com confirmação
 * explícita.
 *
 * Quem não tem o papel vê tudo, mas com os controles desabilitados e o
 * motivo no `title` — botão morto é pior que botão nenhum, e botão escondido
 * esconde também que a função existe. O servidor é quem garante (403).
 */
import '../../design/painel.css';
import { Fragment, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ErroApi } from '../api/cliente';
import {
  execucaoTerminou,
  statusEmCurso,
  useConfiguracao,
  useEnviar,
  useExecucao,
  useOrcamento,
  useTermos,
  useUltimasVerificacoes,
  useUsuarios,
} from '../api/consultas';
import type {
  ConfiguracaoResposta,
  ExecucaoWorkflow,
  ItemConfiguracao,
  OrcamentoResposta,
  ReservaResposta,
  Termo,
  Usuario,
} from '../api/tipos';
import { Confirmacao } from '../componentes/Confirmacao';
import { Carregando, Falha } from '../componentes/Estado';
import { Rolagem } from '../componentes/Rolagem';
import { MOTIVO_SO_ADMIN, MOTIVO_SO_SUPREMO, ehAdmin, ehSupremo, nomePapel, useSessao } from '../componentes/Sessao';
import { estimativaPorEdital, gastaApi } from '../lib/estimativa';
import { brl, data, dataHora, decimal1, hora, milhar, numero, plural } from '../lib/formato';

const PAPEIS = ['leitor', 'operador', 'admin'];

function valorTexto(v: unknown): string {
  return typeof v === 'string' ? v : JSON.stringify(v);
}

/** O texto do campo de volta ao tipo que a chave já tinha (a API valida: `lote` é inteiro ≥ 1). */
function valorDoCampo(texto: string, atual: unknown): unknown {
  const t = texto.trim();
  if (typeof atual === 'number') return t !== '' && Number.isFinite(Number(t)) ? Number(t) : t;
  if (typeof atual === 'boolean') return t === 'true' ? true : t === 'false' ? false : t;
  if (typeof atual === 'string') return texto;
  try {
    return JSON.parse(t);
  } catch {
    return texto;
  }
}

// ------------------------------------------------------------ Verificar agora
/**
 * O que o W01 viu, pelas contagens que ele grava em `contadores`. Sem isto a tela só mostrava as
 * buscas: quem clicou não sabia quantas novas havia. O "Verificar agora" é sempre seco (W11 → W01
 * seco): lista, não grava, e o custo é zero porque o Jev nem é chamado.
 */
function resumoW01(c: Record<string, unknown> | null): string | null {
  if (!c || typeof c.vistas !== 'number') return null;
  const n = (k: string) => (typeof c[k] === 'number' ? (c[k] as number) : 0);
  const conta = (k: string, um: string, varios: string) => `${milhar(n(k))} ${n(k) === 1 ? um : varios}`;
  return [
    conta('novas', 'nova', 'novas'),
    conta('conhecidas', 'conhecida', 'conhecidas'),
    conta('retificadas', 'retificada', 'retificadas'),
    `${milhar(n('fora_escopo'))} fora do escopo`,
    `${milhar(n('fora_recorte'))} fora do recorte`,
    ...(c.seco === true ? ['custo R$ 0,00'] : []),
  ].join(' · ');
}

// A agenda do W01 (n8n/workflows/W01.json, cron "0 6 * * 1-5"): a rodada real, a que grava as novas.
const AGENDA_W01 =
  'De segunda a sexta, às 6h, o FOPA verifica automaticamente e registra as novas licitações no painel. O "Verificar ' +
  'agora" apenas consulta: mostra as novas licitações sem registrá-las.';
// Uma rodada leva uns 2 min (a mais lenta até 27/09, 3 min): "em curso" há mais que isto é rodada que morreu no meio,
// e não pode segurar o botão para sempre.
const RODADA_TRAVADA_MS = 15 * 60_000;

/** "hoje às 14:32" ou "em 25/09 às 06:00", no fuso de Brasília. */
function quando(iso: string): string {
  const dia = data(iso);
  return `${dia === data(new Date().toISOString()) ? 'hoje' : `em ${dia.slice(0, 5)}`} às ${hora(new Date(iso))}`;
}

/** Quanto o botão costuma levar: a mediana das últimas rodadas secas (sem nenhuma, das rodadas que houver). */
function tempoDeCostume(rodadas: ExecucaoWorkflow[]): string | null {
  const feitas = rodadas.filter((r) => r.status === 'ok' && numero(r.duracao_s) !== null);
  const secas = feitas.filter((r) => r.contadores?.seco === true);
  const s = (secas.length ? secas : feitas).map((r) => numero(r.duracao_s) as number).sort((a, b) => a - b);
  return s.length ? `~${Math.max(1, Math.round(s[Math.floor(s.length / 2)] / 60))} min` : null;
}

/** A última rodada em uma frase: "Rodou às (horário), sem licitações novas" ou "Rodou às (horário), 9 licitações
 * novas". */
function rodou(e: { status: string | null; iniciado_em: string; contadores: Record<string, unknown> | null }): string {
  const n = typeof e.contadores?.novas === 'number' ? e.contadores.novas : null;
  const novas = n === null ? '' : n === 0 ? ' · sem licitações novas' : ` · ${plural(n, 'licitação nova', 'licitações novas')}`;
  const verbo = e.status === 'ok' ? 'Rodou' : e.status === 'erro' ? 'Falhou' : `Terminou (${e.status})`;
  return `${verbo} ${quando(e.iniciado_em)}${novas}`;
}

function VerificarAgora() {
  const me = useSessao();
  const [execucaoId, setExecucaoId] = useState<number | null>(null);
  const pedir = useEnviar<void, { execucao_id?: number }>(
    () => ({ caminho: '/api/acoes/verificar', metodo: 'POST', corpo: {} }),
    ['/api/execucoes'],
  );
  // A última rodada vem do servidor, não da memória da tela: sair e voltar (ou abrir em outro computador) mostra a
  // mesma — a do botão ou a das 6h.
  const ultimas = useUltimasVerificacoes();
  const rodadas = (ultimas.data?.itens ?? []).filter((r) => r.workflow === 'W01');
  const ultima = rodadas[0];
  const travada =
    !!ultima && statusEmCurso(ultima.status) && Date.now() - Date.parse(ultima.iniciado_em) > RODADA_TRAVADA_MS;
  const alvo = execucaoId ?? (ultima && !travada ? ultima.id : null);
  const execucao = useExecucao(alvo);
  const motivo = ehAdmin(me) ? null : MOTIVO_SO_ADMIN;
  const d = execucao.data;
  const terminou = execucaoTerminou(d);
  const emCurso = d ? !terminou : execucaoId !== null || (alvo !== null && statusEmCurso(ultima?.status));
  const rodando = pedir.isPending || (alvo !== null && emCurso);
  const tempo = tempoDeCostume(rodadas);
  const aviso = rodando
    ? `Rodando…${d ? ` começou ${quando(d.execucao.iniciado_em)}` : ''}${tempo ? ` · costuma levar ${tempo}` : ''}`
    : d && terminou
      ? rodou(d.execucao)
      : travada && execucaoId === null
        ? `A última verificação começou ${quando(ultima.iniciado_em)} e não foi concluída. Consulte Execuções.`
        : null;

  return (
    <section>
      <h2>Verificar licitações novas</h2>
      <div className="atual">
        <button
          type="button"
          className="primario"
          disabled={!!motivo || rodando}
          title={motivo ?? (rodando ? 'Já há uma verificação em andamento.' : 'Inicia a descoberta de licitações (W01) no processamento (n8n).')}
          onClick={() =>
            pedir.mutate(undefined, {
              onSuccess: (r) => setExecucaoId(r?.execucao_id ?? null),
            })
          }
        >
          Verificar agora
        </button>
        <span className="atualmsg">
          Consulta o PNCP e aplica o filtro de folha{tempo ? ` · duração aproximada: ${tempo}` : ''} · <b>R$ 0,00</b> (sem custo)
        </span>
      </div>
      <p className="atualmsg">{AGENDA_W01}</p>
      {aviso && (
        <p className={rodando ? 'aviso-verificacao rodando' : 'aviso-verificacao'} role="status">
          {aviso}
        </p>
      )}
      {pedir.isError && (
        <p className="erro" role="alert">
          {pedir.error.message}
        </p>
      )}
      {pedir.isSuccess && execucaoId === null && (
        <p className="atualmsg">O processamento (n8n) aceitou o pedido, mas não informou o número da execução. Acompanhe em Execuções.</p>
      )}
      {/* O cabeçalho tem só três linhas (status, contagens, aviso do seco); as buscas por termo e a lista
          das novas ficam na página de Execuções. */}
      {alvo !== null && (
        <div className="achados" role="group" aria-label="Última verificação">
          <h3>
            Execução {alvo}
            {d?.execucao.n8n_execution_id ? ` · n8n nº ${d.execucao.n8n_execution_id}` : ''}
          </h3>
          <div className="progresso">
            {!d ? (
              execucao.isError ? (
                <div>{execucao.error.message}</div>
              ) : (
                <div>Aguardando o processamento…</div>
              )
            ) : (
              <>
                <div>
                  {terminou ? `Concluída (${d.execucao.status})` : 'Em andamento…'}
                  {d.execucao.cego ? ' · coleta incompleta: uma ou mais buscas falharam' : ''}
                </div>
                {d.execucao.erro && <div>{d.execucao.erro}</div>}
                {terminou && resumoW01(d.execucao.contadores) && <div>{resumoW01(d.execucao.contadores)}</div>}
                {terminou && d.execucao.contadores?.seco === true && (
                  <div>
                    Verificação sem registro: nenhuma licitação foi gravada. As novas entram na próxima descoberta
                    automática (de segunda a sexta, às 6h).
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

// ------------------------------------------------------------ Configuração
interface MudancaConfig {
  chave: string;
  valor: unknown;
  confirmar?: boolean;
}

function Configuracao({ dados }: { dados: ConfiguracaoResposta }) {
  const me = useSessao();
  const admin = ehAdmin(me);
  const itens: ItemConfiguracao[] = dados.itens;
  const provedorAtual = valorTexto(itens.find((i) => i.chave === 'provedor')?.valor ?? 'simulado');
  // Troca de provedor esperando confirmação: a que o site já sabe que cobra,
  // ou a que a API recusou com 409 (e aí a mensagem é a dela).
  const [pendente, setPendente] = useState<{ valor: string; mensagem?: string } | null>(null);
  const [edicao, setEdicao] = useState<Record<string, string>>({});
  const gravar = useEnviar<MudancaConfig>((corpo) => ({ caminho: '/api/admin/configuracao', metodo: 'PUT', corpo }), [
    '/api/admin/configuracao',
    '/api/resumo',
  ]);
  const erro409 = gravar.error instanceof ErroApi && gravar.error.status === 409;
  const erroTexto = gravar.isError && !(pendente && erro409) ? gravar.error.message : null;

  function trocarProvedor(novo: string) {
    if (novo === provedorAtual) return;
    // Trocar para quem cobra passa a gastar dinheiro em toda extração: a
    // troca só acontece depois de alguém ler quanto.
    if (gastaApi(novo)) {
      setPendente({ valor: novo });
      return;
    }
    gravar.mutate(
      { chave: 'provedor', valor: novo },
      {
        onError: (e) => {
          if (e instanceof ErroApi && e.status === 409) setPendente({ valor: novo, mensagem: e.message });
        },
      },
    );
  }

  const outros = itens.filter((i) => i.chave !== 'provedor');
  // Um botão só para a tabela: grava, uma a uma, as chaves que mudaram.
  const alterados = outros.filter((i) => edicao[i.chave] !== undefined && edicao[i.chave] !== valorTexto(i.valor));
  async function salvarAlteracoes() {
    try {
      for (const i of alterados) {
        await gravar.mutateAsync({ chave: i.chave, valor: valorDoCampo(edicao[i.chave], i.valor) });
      }
      setEdicao({});
    } catch {
      // o erro aparece na tela (gravar.error); o que já foi gravado fica gravado
    }
  }

  return (
    <section>
      <h2>Configuração</h2>
      <p className="sub">
        <label htmlFor="provedor">Provedor vigente</label>{' '}
        <select
          id="provedor"
          value={pendente?.valor ?? provedorAtual}
          disabled={!admin || gravar.isPending}
          title={admin ? 'Simulado e gravado não geram custo; Claude e OpenAI são serviços pagos.' : MOTIVO_SO_ADMIN}
          onChange={(e) => trocarProvedor(e.target.value)}
        >
          {dados.provedores.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>{' '}
        · custo por edital: <b>{gastaApi(provedorAtual) ? dados.aviso_custo : 'R$ 0,00 (sem serviço pago)'}</b>
      </p>
      {pendente && (
        <Confirmacao
          rotulo="Confirmar troca de provedor"
          titulo={`Passar a extrair com ${pendente.valor}?`}
          confirmar={`Confirmar: usar ${pendente.valor}`}
          aoConfirmar={() =>
            gravar.mutate({ chave: 'provedor', valor: pendente.valor, confirmar: true }, { onSuccess: () => setPendente(null) })
          }
          aoCancelar={() => {
            setPendente(null);
            gravar.reset();
          }}
          ocupado={gravar.isPending}
          erro={erroTexto}
        >
          {pendente.mensagem && <p className="alerta">{pendente.mensagem}</p>}
          <p className="alerta">
            {pendente.valor} é um serviço pago: <b>{dados.aviso_custo}</b> em cada nova extração a partir de agora, até
            o provedor voltar para simulado.
          </p>
          <p>O teto diário do orçamento continua valendo; sem teto, não há limite de gasto.</p>
        </Confirmacao>
      )}
      {erroTexto && !pendente && (
        <p className="erro" role="alert">
          {erroTexto}
        </p>
      )}
      <Rolagem min={720}>
        <table>
          <thead>
            <tr>
              <th>Chave</th>
              <th>Valor</th>
              <th>O que é</th>
              <th>Alterado</th>
            </tr>
          </thead>
          <tbody>
            {outros.map((i) => {
              const atual = valorTexto(i.valor);
              const editado = edicao[i.chave] ?? atual;
              return (
                <tr key={i.chave}>
                  <td>
                    <code>{i.chave}</code>
                  </td>
                  <td>
                    <input
                      aria-label={`valor de ${i.chave}`}
                      value={editado}
                      disabled={!admin}
                      title={admin ? undefined : MOTIVO_SO_ADMIN}
                      onChange={(e) => setEdicao({ ...edicao, [i.chave]: e.target.value })}
                    />
                  </td>
                  <td>{i.descricao ?? '—'}</td>
                  <td className="sha">
                    {i.alterado_por ?? '—'} · {dataHora(i.em)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Rolagem>
      <p>
        <button
          type="button"
          className="primario"
          disabled={!admin || alterados.length === 0 || gravar.isPending}
          title={!admin ? MOTIVO_SO_ADMIN : alterados.length === 0 ? 'nada mudou' : undefined}
          onClick={salvarAlteracoes}
        >
          Salvar alterações{alterados.length ? ` (${alterados.length})` : ''}
        </button>
      </p>
    </section>
  );
}

// ------------------------------------------------------------ Orçamento
interface OrcamentoIn {
  teto_brl_dia: number | null;
  max_por_execucao: number | null;
  auto_processar: boolean;
}

function FormOrcamento({ dados }: { dados: OrcamentoResposta }) {
  const me = useSessao();
  const admin = ehAdmin(me);
  const o = dados.vigente;
  const teto = numero(o?.teto_brl_dia);
  const [tetoTxt, setTetoTxt] = useState(teto === null ? '' : String(teto));
  const [maxTxt, setMaxTxt] = useState(o?.max_por_execucao == null ? '' : String(o.max_por_execucao));
  const [auto, setAuto] = useState(o?.auto_processar ?? true);
  const gravar = useEnviar<OrcamentoIn>((corpo) => ({ caminho: '/api/admin/orcamento', metodo: 'PUT', corpo }), [
    '/api/admin/orcamento',
    '/api/resumo',
  ]);

  function enviar(ev: FormEvent) {
    ev.preventDefault();
    gravar.mutate({
      teto_brl_dia: tetoTxt.trim() === '' ? null : Number(tetoTxt.replace(',', '.')),
      max_por_execucao: maxTxt.trim() === '' ? null : Number(maxTxt),
      auto_processar: auto,
    });
  }

  return (
    <section>
      <h2>Orçamento</h2>
      <p className="sub">
        Teto vigente: <b>{teto === null ? 'sem teto' : `${brl(teto)} por dia`}</b> — referência: {dados.aviso_custo}
        {o?.alterado_por ? ` · alterado por ${o.alterado_por} em ${dataHora(o.em)}` : ''}
      </p>
      <form className="formulario" onSubmit={enviar}>
        <label>
          Teto por dia (R$, vazio = nenhum)
          <input
            inputMode="decimal"
            value={tetoTxt}
            disabled={!admin}
            title={admin ? undefined : MOTIVO_SO_ADMIN}
            onChange={(e) => setTetoTxt(e.target.value)}
          />
        </label>
        <label>
          Máximo por execução
          <input
            inputMode="numeric"
            value={maxTxt}
            disabled={!admin}
            title={admin ? undefined : MOTIVO_SO_ADMIN}
            onChange={(e) => setMaxTxt(e.target.value)}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={auto}
            disabled={!admin}
            title={admin ? undefined : MOTIVO_SO_ADMIN}
            onChange={(e) => setAuto(e.target.checked)}
          />{' '}
          processar automaticamente o que o W01 achar
        </label>
        <button type="submit" className="primario" disabled={!admin || gravar.isPending} title={admin ? undefined : MOTIVO_SO_ADMIN}>
          Salvar orçamento
        </button>
        {gravar.isSuccess && <span className="atualmsg">Orçamento salvo.</span>}
        {gravar.isError && (
          <span className="erro" role="alert">
            {gravar.error.message}
          </span>
        )}
      </form>
    </section>
  );
}

// ------------------------------------------------------------ Termos
function Termos({ termos }: { termos: Termo[] }) {
  const me = useSessao();
  const admin = ehAdmin(me);
  const [novo, setNovo] = useState('');
  // PUT /api/admin/termos com o termo NO CORPO e só o campo que mudou.
  const gravar = useEnviar<{ termo: string; ativo: boolean }>(
    (t) => ({ caminho: '/api/admin/termos', metodo: 'PUT', corpo: t }),
    ['/api/admin/termos'],
  );
  const criar = useEnviar<{ termo: string }>((t) => ({ caminho: '/api/admin/termos', metodo: 'POST', corpo: t }), [
    '/api/admin/termos',
  ]);
  const titulo = admin ? undefined : MOTIVO_SO_ADMIN;
  const erro = gravar.error ?? criar.error;
  return (
    <section>
      <h2>Termos de busca</h2>
      <Rolagem min={560}>
        <table>
          <thead>
            <tr>
              <th>Termo</th>
              <th>Páginas</th>
              <th>Prioridade</th>
              <th>Densidade</th>
              <th>Ativo</th>
            </tr>
          </thead>
          <tbody>
            {termos.map((t) => (
              <tr key={t.termo}>
                <td>{t.termo}</td>
                <td>{milhar(t.paginas)}</td>
                <td>{milhar(t.prioridade)}</td>
                <td>{numero(t.densidade_pct) === null ? '—' : `${decimal1(t.densidade_pct)}%`}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`termo ${t.termo} ativo`}
                    checked={t.ativo}
                    disabled={!admin}
                    title={titulo}
                    onChange={(e) => gravar.mutate({ termo: t.termo, ativo: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Rolagem>
      <form
        className="formulario"
        onSubmit={(e) => {
          e.preventDefault();
          if (novo.trim()) criar.mutate({ termo: novo.trim() }, { onSuccess: () => setNovo('') });
        }}
      >
        <label>
          Novo termo
          <input value={novo} disabled={!admin} title={titulo} onChange={(e) => setNovo(e.target.value)} />
        </label>
        <button
          type="submit"
          className="secundario"
          disabled={!admin || novo.trim().length < 3}
          title={titulo ?? (novo.trim().length >= 3 ? undefined : 'Digite o termo (mínimo de 3 letras).')}
        >
          Adicionar
        </button>
        {erro && (
          <span className="erro" role="alert">
            {erro.message}
          </span>
        )}
      </form>
    </section>
  );
}

// ------------------------------------------------------------ Usuários
type MudancaUsuario = { email: string; papel: string } | { email: string; ativo: boolean };

function Usuarios({ usuarios }: { usuarios: Usuario[] }) {
  const me = useSessao();
  // O admin supremo dá e tira o poder de admin, e ninguém tira o dele. O admin normal vê a lista; mudar é com o
  // supremo (a API responde 403 para os outros).
  const admin = ehSupremo(me);
  const titulo = admin ? undefined : MOTIVO_SO_SUPREMO;
  const [email, setEmail] = useState('');
  const [papel, setPapel] = useState('leitor');
  // PUT /api/admin/usuarios com o e-mail NO CORPO e só o campo que mudou (a
  // API grava o que vier: mandar `nome: null` apagaria o nome).
  const gravar = useEnviar<MudancaUsuario>((u) => ({ caminho: '/api/admin/usuarios', metodo: 'PUT', corpo: u }), [
    '/api/admin/usuarios',
  ]);
  const criar = useEnviar<{ email: string; papel: string; ativo: boolean }>(
    (u) => ({ caminho: '/api/admin/usuarios', metodo: 'POST', corpo: u }),
    ['/api/admin/usuarios'],
  );
  // Dois botões por usuário, remover e bloquear. Remover apaga de vez (DELETE, com
  // confirmação); bloquear é o PUT {ativo:false} — bloqueado não entra, e o botão vira Desbloquear.
  const remover = useEnviar<{ email: string }>((u) => ({ caminho: '/api/admin/usuarios', metodo: 'DELETE', corpo: u }), [
    '/api/admin/usuarios',
  ]);
  const [removendo, setRemovendo] = useState<string | null>(null);
  const erro = gravar.error ?? criar.error;
  return (
    <section>
      <h2>Usuários</h2>
      <p className="sub">
        Quem entra com o Google pela primeira vez vira usuário: vê o painel, o histórico e o analytics, e revisa as
        respostas. Admin vê tudo e usa os botões da API. Só o admin supremo dá e tira acesso: bloqueado não entra;
        removido sai da lista e, se entrar com o Google de novo, volta como usuário.
      </p>
      <Rolagem min={560}>
        <table>
          <thead>
            <tr>
              <th>E-mail</th>
              <th>Nome</th>
              <th>Papel</th>
              <th>Acesso</th>
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => {
              const eleMesmo = u.email === me?.email;
              const motivo = u.supremo
                ? 'O administrador supremo não pode ser alterado pelo site.'
                : titulo ?? (eleMesmo ? 'Não é permitido rebaixar nem desativar a própria conta.' : undefined);
              return (
                <Fragment key={u.email}>
                <tr>
                  <td>
                    {u.email}
                    {!u.ativo && <span className="bloqueado"> · bloqueado</span>}
                  </td>
                  <td>{u.nome ?? '—'}</td>
                  <td>
                    {u.supremo ? (
                      <b title={motivo}>{nomePapel(u)}</b>
                    ) : (
                      <select
                        aria-label={`papel de ${u.email}`}
                        value={u.papel}
                        disabled={!admin || eleMesmo}
                        title={motivo}
                        onChange={(e) => gravar.mutate({ email: u.email, papel: e.target.value })}
                      >
                        {PAPEIS.map((p) => (
                          <option key={p} value={p}>
                            {nomePapel({ papel: p })}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td>
                    {!u.supremo && (
                      <span className="acoes-usuario">
                        <button
                          type="button"
                          className="secundario"
                          aria-label={`${u.ativo ? 'Bloquear' : 'Desbloquear'} ${u.email}`}
                          disabled={!admin || eleMesmo}
                          title={motivo}
                          onClick={() => gravar.mutate({ email: u.email, ativo: !u.ativo })}
                        >
                          {u.ativo ? 'Bloquear' : 'Desbloquear'}
                        </button>
                        <button
                          type="button"
                          className="secundario"
                          aria-label={`Remover ${u.email}`}
                          disabled={!admin || eleMesmo}
                          title={motivo}
                          onClick={() => {
                            remover.reset();
                            setRemovendo(u.email);
                          }}
                        >
                          Remover
                        </button>
                      </span>
                    )}
                  </td>
                </tr>
                {removendo === u.email && (
                  <tr>
                    <td colSpan={4}>
                      <Confirmacao
                        rotulo={`Confirmar remoção de ${u.email}`}
                        titulo={`Remover ${u.email}?`}
                        confirmar="Remover"
                        aoConfirmar={() => remover.mutate({ email: u.email }, { onSuccess: () => setRemovendo(null) })}
                        aoCancelar={() => setRemovendo(null)}
                        ocupado={remover.isPending}
                        erro={remover.error?.message ?? null}
                      >
                        <p>
                          Apaga o cadastro e derruba a sessão na hora. Se a pessoa entrar com o Google de novo, volta
                          como usuário; para impedir a volta, use Bloquear.
                        </p>
                      </Confirmacao>
                    </td>
                  </tr>
                )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </Rolagem>
      <form
        className="formulario"
        onSubmit={(e) => {
          e.preventDefault();
          criar.mutate({ email: email.trim().toLowerCase(), papel, ativo: true }, { onSuccess: () => setEmail('') });
        }}
      >
        <label>
          E-mail
          <input type="email" value={email} disabled={!admin} title={titulo} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label>
          Papel
          <select value={papel} disabled={!admin} title={titulo} onChange={(e) => setPapel(e.target.value)}>
            {PAPEIS.map((p) => (
              <option key={p} value={p}>
                {nomePapel({ papel: p })}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="secundario"
          disabled={!admin || !email.includes('@')}
          title={titulo ?? (email.includes('@') ? undefined : 'digite um e-mail')}
        >
          Adicionar usuário
        </button>
        {erro && (
          <span className="erro" role="alert">
            {erro.message}
          </span>
        )}
      </form>
    </section>
  );
}

// ------------------------------------------------------------ Reserva de demo
// ------------------------------------------------------------ Processar selecionadas
// O limite do W11 (e do site, api/site.py MAX_CONTROLES_POR_ACAO): mais que isso, o pedido inteiro é recusado.
const MAX_POR_PEDIDO = 20;
const RE_CONTROLE_OU_SLUG = /^(\d{14}-\d+-\d+)[-/](\d{4})$/;

interface RespostaProcessar {
  aceitos?: string[];
  recusados?: unknown[];
  execucao_id?: number;
}

/** Controles do texto colado: o slug do site (`…-2026`) vira controle (`…/2026`); repetidos saem; o resto é inválido. */
export function lerControles(texto: string): { validos: string[]; invalidos: string[] } {
  const validos: string[] = [];
  const invalidos: string[] = [];
  for (const bruto of texto.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean)) {
    const m = RE_CONTROLE_OU_SLUG.exec(bruto);
    if (!m) invalidos.push(bruto);
    else if (!validos.includes(`${m[1]}/${m[2]}`)) validos.push(`${m[1]}/${m[2]}`);
  }
  return { validos, invalidos };
}

function recusa(x: unknown): string {
  if (typeof x === 'string') return x;
  const r = (x ?? {}) as { controle?: string; motivo?: string };
  return r.controle ? `${r.controle}${r.motivo ? `: ${r.motivo}` : ''}` : JSON.stringify(x);
}

/**
 * Plano §8 (admin): "Processar selecionadas". Com a esteira desligada (DEPLOY D12) é por aqui que o operador manda
 * um lote ao W11 → W20: cola os controles (o slug do site também serve), confirma vendo o provedor vigente e o
 * custo, e vê o que o n8n aceitou e o que recusou, com o motivo (fora do escopo, fora do recorte, erro definitivo
 * sem forçar...). Até 20 por pedido, o limite do W11.
 */
function ProcessarSelecionadas({ provedor }: { provedor: string | null }) {
  const me = useSessao();
  const opera = ehAdmin(me);
  const titulo = opera ? undefined : MOTIVO_SO_ADMIN;
  const [texto, setTexto] = useState('');
  const [forcar, setForcar] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const { validos, invalidos } = lerControles(texto);
  const demais = validos.length > MAX_POR_PEDIDO;
  const processar = useEnviar<{ controles: string[]; forcar: boolean }, RespostaProcessar>(
    (c) => ({ caminho: '/api/acoes/processar', metodo: 'POST', corpo: c }),
    ['/api/licitacoes', '/api/execucoes'],
  );
  const r = processar.data;
  return (
    <section>
      <h2>Processar selecionadas</h2>
      <p className="sub">
        Envia um lote ao processamento (n8n), com até {MAX_POR_PEDIDO} licitações por pedido. Útil com o processamento
        automático desligado e para refazer uma licitação específica.
      </p>
      <form
        className="formulario"
        onSubmit={(e) => {
          e.preventDefault();
          processar.reset();
          setConfirmando(true);
        }}
      >
        <label>
          Controles a processar (um por linha; o slug do site também serve)
          <textarea rows={3} value={texto} disabled={!opera} title={titulo} onChange={(e) => setTexto(e.target.value)} />
        </label>
        <label>
          <input type="checkbox" checked={forcar} disabled={!opera} onChange={(e) => setForcar(e.target.checked)} /> Forçar
          (refaz desde o download, inclusive as publicadas, as fora do escopo e as com erro definitivo)
        </label>
        <button
          type="submit"
          className="secundario"
          disabled={!opera || validos.length === 0 || demais || processar.isPending}
          title={titulo ?? (validos.length ? undefined : 'Informe ao menos um controle.')}
        >
          {validos.length ? `Processar ${milhar(validos.length)}` : 'Processar'}
        </button>
      </form>
      {invalidos.length > 0 && <p className="atualmsg">Fora do formato: {invalidos.join(', ')}</p>}
      {demais && (
        <p className="erro" role="alert">
          no máximo {MAX_POR_PEDIDO} por pedido — o W11 recusaria o lote inteiro; divida em partes.
        </p>
      )}
      {confirmando && (
        <Confirmacao
          rotulo="Confirmar processamento em lote"
          titulo={`Processar ${milhar(validos.length)} ${validos.length === 1 ? 'licitação' : 'licitações'}?`}
          confirmar="Confirmar e processar"
          aoConfirmar={() => processar.mutate({ controles: validos, forcar })}
          aoCancelar={() => setConfirmando(false)}
          ocupado={processar.isPending}
          erro={processar.isError ? processar.error.message : null}
          feito={
            processar.isSuccess ? (
              <>
                {milhar(r?.aceitos?.length ?? 0)} {(r?.aceitos?.length ?? 0) === 1 ? 'aceita' : 'aceitas'}
                {(r?.recusados?.length ?? 0) > 0 && (
                  <>
                    {' '}
                    · recusadas: <span>{(r?.recusados ?? []).map(recusa).join('; ')}</span>
                  </>
                )}
                . Acompanhe em <Link to="/execucoes">Execuções</Link>.
              </>
            ) : undefined
          }
        >
          <p>
            Provedor vigente: <b>{provedor ?? 'desconhecido'}</b> · custo estimado: <b>{estimativaPorEdital(provedor)}</b>{' '}
            (por licitação)
          </p>
          {gastaApi(provedor) ? (
            <p className="alerta">Este provedor é um serviço pago: serão até {milhar(validos.length)} extrações.</p>
          ) : (
            <p>Sem serviço pago.</p>
          )}
        </Confirmacao>
      )}
    </section>
  );
}

interface RespostaImportar {
  aceito?: boolean;
  controle?: string;
  modo?: 'publicar' | 'republicar';
  execucao_id?: number;
  verificacao_id?: number | null;
}

const IDS_Q = Array.from({ length: 17 }, (_, i) => `Q${i + 1}`);

/**
 * O que o agente gravou: o `respostas.json` dele (`{"respostas": [...]}`, 70_extracao_por_agente.py) ou a lista pura.
 * O site confere só a forma (JSON, 17 objetos, Q1 a Q17) para não mandar ao n8n o que ele recusaria; o conteúdo de
 * cada resposta é do worker (api/extracao.py validar_respostas) e o veredito, do verificador.
 */
export function lerRespostas(texto: string): { respostas: Record<string, unknown>[] | null; erro: string | null } {
  if (!texto.trim()) return { respostas: null, erro: null };
  let dado: unknown;
  try {
    dado = JSON.parse(texto);
  } catch (e) {
    return { respostas: null, erro: `O conteúdo não é um JSON válido: ${(e as Error).message}` };
  }
  const embrulho = dado && typeof dado === 'object' && !Array.isArray(dado) ? (dado as { respostas?: unknown }).respostas : dado;
  if (!Array.isArray(embrulho)) {
    return { respostas: null, erro: 'Formato esperado: o respostas.json do agente ({"respostas": [...]}) ou a lista das 17 respostas.' };
  }
  if (embrulho.length !== 17) return { respostas: null, erro: `São esperadas 17 respostas (Q1 a Q17); foram recebidas ${embrulho.length}.` };
  if (embrulho.some((r) => !r || typeof r !== 'object' || Array.isArray(r))) {
    return { respostas: null, erro: 'Cada resposta deve ser um objeto.' };
  }
  const ids = embrulho.map((r) => (r as { id?: unknown }).id);
  const faltam = IDS_Q.filter((q) => !ids.includes(q));
  if (faltam.length) return { respostas: null, erro: `Respostas ausentes: ${faltam.join(', ')}.` };
  return { respostas: embrulho as Record<string, unknown>[], erro: null };
}

/**
 * Plano §8 (admin) e ADR-014: "Importar respostas do agente", o caminho oficial de custo zero. O operador cola o
 * controle (ou o slug) e o respostas.json que o agente gravou sobre a leitura congelada; o W11 passa as respostas
 * pelo MESMO verificador da API (worker /importar-respostas) e o W24 publica — ou republica, com o diff, se a
 * licitação já estava publicada. Uma por vez: cada respostas.json é de uma leitura só.
 */
function ImportarRespostas() {
  const me = useSessao();
  const opera = ehAdmin(me);
  const titulo = opera ? undefined : MOTIVO_SO_ADMIN;
  const [controleTexto, setControleTexto] = useState('');
  const [json, setJson] = useState('');
  const [modelo, setModelo] = useState('');
  const { validos, invalidos } = lerControles(controleTexto);
  const { respostas, erro } = lerRespostas(json);
  const importar = useEnviar<{ controle: string; respostas: Record<string, unknown>[]; modelo?: string }, RespostaImportar>(
    (c) => ({ caminho: '/api/acoes/importar-respostas', metodo: 'POST', corpo: c }),
    ['/api/licitacoes', '/api/execucoes'],
  );
  const pronto = validos.length === 1 && invalidos.length === 0 && respostas !== null;
  const r = importar.data;
  return (
    <section>
      <h2>Importar respostas do agente</h2>
      <p className="sub">
        As 17 respostas produzidas por um agente local (sem serviço pago) sobre a leitura registrada passam pelo mesmo
        verificador das demais extrações: numa licitação <code>preparada</code>, são publicadas; numa já publicada, geram
        uma nova extração e a página é republicada com as alterações. Nenhum custo de serviço.
      </p>
      <form
        className="formulario"
        onSubmit={(e) => {
          e.preventDefault();
          if (!pronto || !respostas) return;
          importar.mutate({ controle: validos[0], respostas, ...(modelo.trim() ? { modelo: modelo.trim() } : {}) });
        }}
      >
        <label>
          Controle (ou o slug do site)
          <input
            value={controleTexto}
            disabled={!opera}
            title={titulo}
            onChange={(e) => {
              importar.reset();
              setControleTexto(e.target.value);
            }}
          />
        </label>
        <label>
          respostas.json do agente
          <textarea
            rows={6}
            spellCheck={false}
            value={json}
            disabled={!opera}
            title={titulo}
            onChange={(e) => {
              importar.reset();
              setJson(e.target.value);
            }}
          />
        </label>
        <label>
          Modelo do agente (opcional)
          <input value={modelo} disabled={!opera} title={titulo} placeholder="claude-opus-5-5" onChange={(e) => setModelo(e.target.value)} />
        </label>
        <button
          type="submit"
          className="secundario"
          disabled={!opera || !pronto || importar.isPending}
          title={titulo ?? (pronto ? undefined : 'Informe um controle e as 17 respostas.')}
        >
          Importar e publicar
        </button>
      </form>
      {validos.length > 1 && (
        <p className="atualmsg">Uma licitação por vez: {milhar(validos.length)} controles informados.</p>
      )}
      {invalidos.length > 0 && <p className="atualmsg">Fora do formato: {invalidos.join(', ')}</p>}
      {erro && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      {importar.isError && (
        <p className="erro" role="alert">
          {importar.error.message}
        </p>
      )}
      {r && (
        <p className="atualmsg">
          Respostas aceitas (execução {r.execucao_id}). O processamento{' '}
          {r.modo === 'republicar' ? 'republicará a página com as alterações' : 'fará a verificação e a publicação'} em seguida.
          Acompanhe em{' '}
          <Link to="/execucoes">Execuções</Link>.
        </p>
      )}
    </section>
  );
}

function ReservaDemo() {
  const me = useSessao();
  const admin = ehAdmin(me);
  const titulo = admin ? undefined : MOTIVO_SO_ADMIN;
  const [texto, setTexto] = useState('');
  const [dias, setDias] = useState('7');
  const controles = texto
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const reservar = useEnviar<{ controles: string[]; dias: number }, ReservaResposta>(
    (c) => ({ caminho: '/api/admin/reservar-demo', metodo: 'POST', corpo: c }),
    ['/api/licitacoes'],
  );
  const r = reservar.data;
  return (
    <section>
      <h2>Reservar para a demo</h2>
      <p className="sub">
        Marca a licitação como reservada para demonstração (<code>reserva_demo</code>) e estende o prazo final em N dias
        (de 1 a 60).
      </p>
      <form
        className="formulario"
        onSubmit={(e) => {
          e.preventDefault();
          reservar.mutate({ controles, dias: Number(dias) || 7 });
        }}
      >
        <label>
          Controles (um por linha)
          <textarea rows={3} value={texto} disabled={!admin} title={titulo} onChange={(e) => setTexto(e.target.value)} />
        </label>
        <label>
          Prazo (+ dias)
          <input inputMode="numeric" value={dias} disabled={!admin} title={titulo} onChange={(e) => setDias(e.target.value)} />
        </label>
        <button
          type="submit"
          className="secundario"
          disabled={!admin || controles.length === 0 || reservar.isPending}
          title={titulo ?? (controles.length ? undefined : 'Informe ao menos um controle.')}
        >
          Reservar {controles.length ? milhar(controles.length) : ''}
        </button>
        {reservar.isError && (
          <span className="erro" role="alert">
            {reservar.error.message}
          </span>
        )}
      </form>
      {r && (
        <p className="atualmsg">
          {milhar(r.reservadas.length)} {r.reservadas.length === 1 ? 'reservada' : 'reservadas'}{r.fim_prazo ? ` · prazo até ${dataHora(r.fim_prazo)}` : ''}
          {r.nao_encontradas.length > 0 && ` · não encontradas: ${r.nao_encontradas.join(', ')}`}
        </p>
      )}
    </section>
  );
}

export function Admin() {
  const config = useConfiguracao();
  const provedor = config.data
    ? valorTexto(config.data.itens.find((i) => i.chave === 'provedor')?.valor ?? 'simulado')
    : null;
  const orcamento = useOrcamento();
  const termos = useTermos();
  const usuarios = useUsuarios();
  return (
    <div className="pg-painel">
      <div className="wrap">
        <header>
          <p className="eyebrow">FOPA · administração</p>
          <h1>Administração</h1>
          <p className="sub">
            Provedor, orçamento, termos de busca e acessos. Toda alteração é registrada com responsável e data.
          </p>
        </header>
        <VerificarAgora />
        <ProcessarSelecionadas provedor={provedor} />
        <ImportarRespostas />
        {config.data ? (
          <Configuracao dados={config.data} />
        ) : config.isError ? (
          <Falha erro={config.error} oque="a configuração" />
        ) : (
          <Carregando />
        )}
        {orcamento.data ? (
          <FormOrcamento dados={orcamento.data} />
        ) : orcamento.isError ? (
          <Falha erro={orcamento.error} oque="o orçamento" />
        ) : null}
        {termos.data ? <Termos termos={termos.data.itens} /> : termos.isError ? <Falha erro={termos.error} oque="os termos" /> : null}
        {usuarios.data ? (
          <Usuarios usuarios={usuarios.data.itens} />
        ) : usuarios.isError ? (
          <Falha erro={usuarios.error} oque="os usuários" />
        ) : null}
        <ReservaDemo />
      </div>
    </div>
  );
}
