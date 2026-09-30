/**
 * O que o site deriva dos corpos reais, sem tela: fim de uma execução
 * (`GET /api/execucoes/{id}` devolve `{execucao:{status}, buscas}` — ler
 * `status` no topo fazia o "Verificar agora" nunca terminar).
 */
import { describe, expect, it } from 'vitest';
import { execucaoTerminou } from '../api/consultas';
import { execucaoCega, execucaoConcluida, execucaoEmCurso } from '../__fixtures__/contrato';

describe('execucaoTerminou', () => {
  it('em curso não terminou', () => {
    expect(execucaoEmCurso.execucao.status).toBe('em_curso');
    expect(execucaoTerminou(execucaoEmCurso)).toBe(false);
  });

  it('ok terminou (inclusive a coleta cega: terminou, só que cega)', () => {
    expect(execucaoTerminou(execucaoConcluida)).toBe(true);
    expect(execucaoTerminou(execucaoCega)).toBe(true);
  });

  it('sem resposta ainda não terminou', () => {
    expect(execucaoTerminou(undefined)).toBe(false);
  });
});
