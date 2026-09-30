/**
 * O que a confirmação de uma ação diz sobre custo, antes de gastar.
 *
 * O número "~R$ 3–4 por edital" é o do plano (§8, /admin): média medida das
 * extrações pela API com o modelo do ADR-009. Simulado e gravado não chamam
 * modelo pago; reverificar nunca chama modelo (é o verificador, sem IA).
 */

export const PROVEDORES_PAGOS = new Set(['claude', 'openai']);

export function gastaApi(provedor: string | null | undefined): boolean {
  return PROVEDORES_PAGOS.has((provedor ?? '').toLowerCase());
}

export function estimativaPorEdital(provedor: string | null | undefined): string {
  if (!provedor) return 'Provedor vigente não informado. Confira na Administração antes de continuar.';
  return gastaApi(provedor) ? '~R$ 3–4 por edital' : 'R$ 0,00 (sem serviço pago)';
}

export const ESTIMATIVA_REVERIFICAR = 'R$ 0,00 (verificação determinística, sem IA)';

/** O botão "Extrair com GPT" (db/033): o modelo da configuração `modelo_openai` e o preço conferido na tabela. */
export const ESTIMATIVA_GPT = 'gpt-5.6-sol · ~US$ 0,49 por edital (≈ R$ 2,70)';
