/**
 * Guarda dos textos do site. Nos arquivos já
 * revisados (REVISADOS), nenhum texto visível pode ter jargão interno nem marca de informalidade. É um piso, não a
 * revisão inteira: o tom e a concisão se conferem lendo, pelo guia `docs/textos-do-site.md`.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// A partir de web/ (onde o `npm test` roda, aqui e no CI): no ambiente jsdom o import.meta.url não é um file://.
const SRC = resolve(process.cwd(), 'src');

/** Cresce a cada tarefa do plano de textos. Páginas de operação (Admin, Execuções, E-mails, Saúde) ficam fora do JARGAO. */
export const REVISADOS: string[] = [
  // Task 2: Painel e moldura
  'paginas/Painel.tsx',
  'paginas/Login.tsx',
  'componentes/Layout.tsx',
  'componentes/Sessao.tsx',
  'componentes/CardLicitacao.tsx',
  'componentes/QuadrosResumo.tsx',
  'componentes/PrazoBadge.tsx',
  'componentes/Paginacao.tsx',
  'componentes/FiltroDatas.tsx',
  'componentes/Estado.tsx',
  'componentes/Restrita.tsx',
  'lib/filtros.ts',
  'lib/prazo.ts',
  'lib/respostas.ts',
  // Task 3: Detalhe da licitação
  'paginas/Detalhe.tsx',
  'componentes/TabelaRespostas.tsx',
  'componentes/Documentos.tsx',
  'componentes/Condicoes.tsx',
  'componentes/DistribuicaoQ13.tsx',
  'componentes/MelhorDeN.tsx',
  'componentes/EscolhaIa.tsx',
  'componentes/Confirmacao.tsx',
  'componentes/MarcaProcedencia.tsx',
  'componentes/Rolagem.tsx',
  'lib/procedencia.ts',
  // Task 4: Revisão (e a Governança, 28/09, que nasceu no guia)
  'paginas/Revisao.tsx',
  'paginas/Governanca.tsx',
  // Task 5: Analytics e histórico
  'paginas/Analytics.tsx',
  'paginas/AnalyticsHistorico.tsx',
  'componentes/AbasAnalytics.tsx',
  'componentes/ComprasPorBanco.tsx',
  'componentes/GraficoLinhas.tsx',
  'componentes/Lista.tsx',
  'componentes/ListaMultipla.tsx',
  // Task 6: operação (só a lista de informalidade) e relatório
  'paginas/Admin.tsx',
  'paginas/Execucoes.tsx',
  'paginas/Emails.tsx',
  'paginas/Saude.tsx',
  'paginas/Relatorio.tsx',
  'lib/estimativa.ts',
];
const OPERACAO = ['paginas/Admin.tsx', 'paginas/Execucoes.tsx', 'paginas/Emails.tsx', 'paginas/Saude.tsx'];

const JARGAO: RegExp[] = [/\bW\d{2}\b/, /\bn8n\b/i, /\bPostgres\b/i, /\bADR-\d+/, /\bClaude Code\b/, /\bv2\b/, /\/api\//];
const INFORMAL: RegExp[] = [/!/, /\bpra\b/i, /\btá\b/i, /\ba gente\b/i, /\bvocê\b/i, /\bolho humano\b/i];

export function textosVisiveis(fonte: string): string[] {
  const sem = fonte
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
  const jsx = [...sem.matchAll(/>\s*([^<>{}]*[A-Za-zÀ-ú][^<>{}]*?)\s*</g)].map((m) => m[1]);
  const attrs = [...sem.matchAll(/\b(?:title|aria-label|placeholder|alt|rotulo|texto|titulo)=["']([^"']+)["']/g)].map(
    (m) => m[1],
  );
  return [...jsx, ...attrs]
    .map((s) => s.replace(/\s+/g, ' ').trim())
    .filter((s) => s && !/[;=()&|]/.test(s));
}

describe('textos do site', () => {
  it('a extração de textos visíveis pega texto de JSX e de atributos, e ignora comentário e código', () => {
    const fonte = `// comentário W50\n<p title="Olá">Fila do W50: pendentes</p>{/* n8n */}{a && b}`;
    expect(textosVisiveis(fonte)).toEqual(['Fila do W50: pendentes', 'Olá']);
  });

  for (const arq of REVISADOS) {
    it(`${arq}: sem jargão interno nem marca de informalidade`, () => {
      const textos = textosVisiveis(readFileSync(resolve(SRC, arq), 'utf8'));
      const regras = OPERACAO.includes(arq) ? INFORMAL : [...JARGAO, ...INFORMAL];
      const ruins = textos.filter((t) => regras.some((r) => r.test(t)));
      expect(ruins).toEqual([]);
    });
  }
});
