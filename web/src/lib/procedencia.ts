/**
 * Procedência de uma execução, como RÓTULO (`.marca`), nunca como cor
 * (README §6): cor no site é status — vermelho é defeito, âmbar é olho
 * humano, teal é conferido — e "de onde veio a resposta" não é nenhum dos três.
 *
 * O rótulo diz ONDE A EXTRAÇÃO RODOU:
 * - `local` — uma execução do agente de IA (Claude Code, na máquina local), sem chamada
 *   de API; as respostas entram pelo caminho oficial de custo zero (ADR-014).
 *   Por isso não há tokens, tempo nem custo medidos — e o site não os mostra
 *   como se fossem zero;
 * - `api` — o modelo pago chamado pelo n8n (ou, na v2, pelo script/harness),
 *   com tokens e custo; qual API (Anthropic, OpenAI) vai na dica;
 * - `simulado`/`gravado` — ensaio, nenhuma das duas; `reconstruída` — execução
 *   da v2 remontada pelo importador.
 */

export function rodouLocal(origem: string | null | undefined): boolean {
  return origem === 'agente';
}

/**
 * Nome do provedor na linha de procedência. O id técnico da extração local (`claude-code`) continua no banco,
 * porque o servidor decide por ele; na tela ele aparece como "agente de IA" (docs/textos-do-site.md).
 */
export function nomeProvedor(provedor: string | null | undefined): string | null {
  if (!provedor) return null;
  return provedor === 'claude-code' ? 'agente de IA' : provedor;
}

export function rotuloProcedencia(origem: string | null | undefined, provedor?: string | null): string | null {
  if (!origem) return null;
  switch (origem) {
    case 'agente':
      return 'local';
    case 'api':
    case 'harness':
    case 'experimento':
      // O plano B (ADR-012) sai pela mesma origem 'api'; o provedor vai na dica.
      void provedor;
      return 'api';
    case 'legado':
      // Execução da v2 remontada pelo importador a partir da auditoria.
      return 'reconstruída';
    default:
      // simulado · gravado: o nome já diz.
      return origem;
  }
}

const DICAS: Record<string, string> = {
  simulado: 'Provedor simulado, sem serviço pago; usado apenas em testes.',
  gravado: 'Repetição de respostas gravadas, sem serviço pago; usada apenas em testes.',
  'reconstruída': 'Execução da versão anterior, reconstruída na importação.',
};

export function dicaProcedencia(origem: string | null | undefined, provedor?: string | null): string {
  switch (origem) {
    case 'agente':
      return 'Extração local, sem serviço pago; tokens, tempo e custo não são medidos.';
    case 'api':
      return provedor === 'openai' ? 'Extração no serviço da OpenAI (provedor alternativo).' : 'Extração no serviço da Anthropic.';
    case 'harness':
      return 'Extração em serviço pago, na avaliação de qualidade.';
    case 'experimento':
      return 'Extração em serviço pago, em caráter experimental.';
    default: {
      const r = rotuloProcedencia(origem, provedor);
      return (r && DICAS[r]) ?? `Procedência: ${r ?? 'desconhecida'}`;
    }
  }
}

/**
 * O provedor de extração com um nome legível. "simulado" é o nome técnico do
 * provedor de ensaio (não chama modelo nenhum); na tela ele ganha um nome que
 * não se confunde com outros usos da palavra.
 */
const ROTULO_PROVEDOR: Record<string, string> = {
  simulado: 'sem IA (ensaio)',
  gravado: 'gravado (ensaio)',
  claude: 'Claude (API)',
  openai: 'OpenAI (API)',
};

export function rotuloProvedor(provedor: string | null | undefined): string {
  if (!provedor) return '—';
  return ROTULO_PROVEDOR[provedor] ?? provedor;
}
