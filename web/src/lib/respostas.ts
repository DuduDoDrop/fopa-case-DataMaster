/**
 * As 17 linhas da tela a partir do detalhe REAL da API.
 *
 * `GET /api/licitacoes/{slug}` manda duas listas separadas, e de propósito:
 * `respostas` é o que o MODELO disse (execução) e `verificacao_respostas` é o
 * que o VERIFICADOR decidiu (verificação vigente, sem IA). A mesma resposta
 * pode ter várias verificações (ADR-014), então a junção é do site, por
 * `pergunta_id`. Sem ela o veredito e o `arquivo_id` sumiam, e a Origem
 * virava vermelha sem link `#page=N`.
 */
import type { RespostaCrua, RespostaDetalhe, VerificacaoResposta } from '../api/tipos';
import { numero } from './formato';

function ordemDa(id: string): number {
  const n = Number(id.slice(1));
  return Number.isFinite(n) ? n : Number.MAX_SAFE_INTEGER;
}

export function mesclarRespostas(respostas: RespostaCrua[], verificacao: VerificacaoResposta[]): RespostaDetalhe[] {
  const porPergunta = new Map(verificacao.map((v) => [v.pergunta_id, v]));
  return [...respostas]
    .sort((a, b) => ordemDa(a.pergunta_id) - ordemDa(b.pergunta_id))
    .map((r) => {
      const v = porPergunta.get(r.pergunta_id);
      return {
        pergunta_id: r.pergunta_id,
        pergunta: r.pergunta,
        critico: r.critico,
        resposta: r.resposta,
        arquivo_citado: r.arquivo_citado,
        // a página que o modelo citou é a da resposta crua; a do verificador
        // (quando corrigiu) é `pagina_final`
        pagina_citada: r.pagina_citada ?? v?.pagina_citada ?? null,
        trecho_literal: r.trecho_literal,
        conflito: r.conflito,
        confianca: r.confianca,
        veredito: v?.veredito ?? null,
        arquivo_canonico: v?.arquivo_canonico ?? null,
        arquivo_id: v?.arquivo_id ?? null,
        pagina_final: v?.pagina_final ?? null,
        alertas: v?.alertas ?? null,
        ausencia: v?.ausencia ?? null,
      };
    });
}

/** "93%" a partir de uma probabilidade 0–1 (número ou numeric em string); null se não houver. */
export function percentual(p: number | string | null | undefined): string | null {
  const n = numero(p);
  if (n === null) return null;
  return `${Math.round(n * 100)}%`;
}

/** O aviso que acompanha todo número do Jev na tela (Jev na v3: score, nunca decisão). */
export const AVISO_JEV = 'Indicador do Jev; não altera o veredito nem o escopo.';

/**
 * A opinião da IA (Jev) sobre ser compra de folha, em palavras. O número é a chance de SER folha
 * (`p_folha`), não a de "o filtro estar certo". As faixas seguem as do site: 50% é o corte do filtro da IA, 25% o da
 * trava (ADR-019).
 */
export function opiniaoIa(p: number | string | null | undefined): { texto: string; classe: string } | null {
  const n = numero(p);
  const pct = percentual(p);
  if (n === null || pct === null) return null;
  if (n >= 0.75) return { texto: `IA: é folha (${pct})`, classe: 'jev-sim' };
  if (n >= 0.5) return { texto: `IA: provavelmente é folha (${pct})`, classe: 'jev-provavel' };
  if (n > 0.25) return { texto: `IA: provavelmente não é folha (${pct})`, classe: 'jev-duvida' };
  return { texto: `IA: não é folha (${pct})`, classe: 'jev-nao' };
}

/** O que acompanha a opinião da IA na tela: o que o número é, e que ele não decide. */
export const AVISO_IA_FOLHA =
  'Probabilidade de ser compra de folha, segundo a IA (Jev). Não altera o escopo: prevalece a classificação manual.';

/**
 * A caixa "mostrar fora do escopo" do analytics. Desde 25/09 o site mostra só o que a IA confirma como folha, sem
 * caixa e sem aviso; o que a regra de
 * escopo recusou e o que a IA (Jev) estima que não é folha (nota abaixo de 50%, db/034) só aparece por esta caixa.
 */
export const AVISO_FORA_DO_ESCOPO = 'Inclui as licitações que não são compra de folha. Nenhum registro é excluído.';
