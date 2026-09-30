/**
 * Depois de "Processar" ou "Extrair com GPT", o detalhe se atualiza sozinho enquanto a licitação anda — antes o
 * botão parecia não funcionar, porque nem a licitação nem os gastos mudavam na tela. O fluxo (baixar → ler → extrair
 * → verificar → publicar) leva minutos, e a página só mudava no ↻.
 *
 * A regra: acompanha até o estado MUDAR em relação ao do clique (o W11 ainda não pegou) e, depois, enquanto o
 * estado for de fluxo andando. Com o pedido do GPT pendente, `preparada` também é andando (o W23 vem a seguir).
 * Teto de 15 minutos, para nunca perguntar para sempre.
 */
export const ACOMPANHAR_MS = 5000;
export const ACOMPANHAR_MAX_MS = 15 * 60 * 1000;

/** Estados em que o fluxo está andando (db/002): baixar, ler, extrair, verificar. */
const ANDANDO = new Set(['nova', 'retificada', 'baixando', 'baixada_ok', 'lendo', 'extraindo', 'respondida', 'verificada']);

export function aindaAndando(estado: string, pedidoIaPendente: boolean): boolean {
  return ANDANDO.has(estado) || (estado === 'preparada' && pedidoIaPendente);
}

/** Onde não há texto para ler (o W21/W22 param aqui): um pedido de extração nunca seria usado. */
export const ESTADOS_SEM_TEXTO = new Set(['formato_nao_suportado', 'sem_pdf_legivel']);
