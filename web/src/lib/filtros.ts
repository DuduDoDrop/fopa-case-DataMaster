/**
 * Filtros do painel (painel.css `.barra`; plano §8).
 *
 * As chaves são EXATAMENTE as de `api/consultas.py:FILTROS` — a API recusa
 * qualquer outra com 422 (o front mandava `sem-extracao` e
 * `revisao-pendente`, e a lista quebrava). O teste confere contra a lista que
 * a própria API devolve no 422 (`__fixtures__/contrato`).
 *
 * O filtro é do SERVIDOR, com a paginação: o site não refiltra a página que
 * chega. Refiltrar escondia cards que o contador (o `total` do servidor)
 * contava. A regra "urgente = aberta, 0 ≤ dias ≤ 7" mora no SQL
 * (`consultas.FILTROS['urgentes']`), no mesmo dia civil de São Paulo que o
 * card usa.
 *
 * Desde 25/09 saem das duas barras "Injeção suspeita", "Retificadas", "Revisão
 * pendente" e "Ensaio"; "Com alerta de regra" sai só da home (paginas/Painel.tsx).
 * A API continua aceitando as chaves; o site só não oferece o botão.
 */

export type ChaveFiltro =
  | 'todas'
  | 'urgentes'
  | 'conflito'
  | 'alerta'
  | 'extraidas'
  | 'sem_extracao'
  | 'encerradas';

export const FILTROS: { chave: ChaveFiltro; rotulo: string }[] = [
  { chave: 'todas', rotulo: 'Todas' },
  { chave: 'urgentes', rotulo: 'Fecham em ≤7 dias' },
  { chave: 'conflito', rotulo: 'Com conflito' },
  { chave: 'alerta', rotulo: 'Com alerta de regra' },
  { chave: 'extraidas', rotulo: 'Já extraídas' },
  { chave: 'sem_extracao', rotulo: 'Sem extração' },
  { chave: 'encerradas', rotulo: 'Encerradas' },
];

export function ehChaveFiltro(v: string | null): v is ChaveFiltro {
  return !!v && FILTROS.some((f) => f.chave === v);
}

/**
 * Vencimento "até N dias": substitui o "Fecham em ≤7 dias" no Painel. Só abertas; a regra mora no SQL
 * (`api/consultas.py:cond_vence_em`), no mesmo dia civil de São Paulo que o card usa. Não existe no histórico.
 */
export const VENCIMENTOS = [7, 15, 30, 45, 60] as const;
export type Vencimento = (typeof VENCIMENTOS)[number];

export function vencimentoDaUrl(v: string | null): Vencimento | null {
  const n = Number(v);
  return v && (VENCIMENTOS as readonly number[]).includes(n) ? (n as Vencimento) : null;
}

/**
 * Marcar ou desmarcar um item do "Mostrar": vários somam-se com E.
 * "Todas" limpa a escolha; "Já extraídas" e "Sem extração" se excluem — juntas, nada sobraria.
 */
const OPOSTO: Partial<Record<ChaveFiltro, ChaveFiltro>> = { extraidas: 'sem_extracao', sem_extracao: 'extraidas' };

export function alternarFiltro(atuais: ChaveFiltro[], chave: ChaveFiltro): ChaveFiltro[] {
  if (chave === 'todas') return [];
  if (atuais.includes(chave)) return atuais.filter((c) => c !== chave);
  return [...atuais.filter((c) => c !== OPOSTO[chave]), chave];
}
