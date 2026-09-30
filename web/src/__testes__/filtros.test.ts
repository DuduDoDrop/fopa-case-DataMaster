/**
 * Filtros do painel contra o CONTRATO: a lista de chaves que a API aceita
 * sai da própria recusa dela (`contrato/erro-filtro-sem-extracao.json`, o 422
 * que a chave com hífen do front levava). O filtro é do servidor — o site não
 * refiltra a página que chega, senão o contador (total do servidor) e a lista
 * divergem.
 */
import { describe, expect, it } from 'vitest';
import { caminhoAnalytics, caminhoLista } from '../api/consultas';
import { FILTROS, VENCIMENTOS, alternarFiltro, ehChaveFiltro, vencimentoDaUrl } from '../lib/filtros';
import { filtrosAceitosPelaApi, registros } from '../__fixtures__/contrato';

describe('chaves de filtro', () => {
  it('a API recusou a chave antiga com hífen (422)', () => {
    expect(registros.erroFiltro.status).toBe(422);
    expect(filtrosAceitosPelaApi()).not.toContain('sem-extracao');
  });

  it('toda chave do painel é uma que a API aceita', () => {
    const aceitas = filtrosAceitosPelaApi();
    for (const f of FILTROS) expect(aceitas).toContain(f.chave);
  });

  it('o painel oferece os filtros da API, menos os quatro tirados das duas barras (25/09)', () => {
    const tirados = ['injecao', 'retificadas', 'revisao', 'ensaio'];
    expect(FILTROS.map((f) => f.chave).sort()).toEqual(filtrosAceitosPelaApi().filter((c) => !tirados.includes(c)).sort());
  });

  it('rótulos do design (README §3)', () => {
    const rotulo = Object.fromEntries(FILTROS.map((f) => [f.chave, f.rotulo]));
    expect(rotulo.todas).toBe('Todas');
    expect(rotulo.urgentes).toBe('Fecham em ≤7 dias');
    expect(rotulo.sem_extracao).toBe('Sem extração');
  });

  it('chave da URL antiga não vale', () => {
    expect(ehChaveFiltro('sem-extracao')).toBe(false);
    expect(ehChaveFiltro('revisao-pendente')).toBe(false);
    expect(ehChaveFiltro('sem_extracao')).toBe(true);
    // tirada da barra: a URL antiga cai em "Todas"
    expect(ehChaveFiltro('revisao')).toBe(false);
  });
});

describe('caminho da lista', () => {
  it('manda filtro, busca, página e recorte como a API espera', () => {
    expect(caminhoLista({ q: '', filtros: [], page: 1, recorteTodos: false })).toBe('/api/licitacoes');
    expect(caminhoLista({ q: 'niteroi', filtros: ['sem_extracao'], page: 2, recorteTodos: true })).toBe(
      '/api/licitacoes?q=niteroi&filtro=sem_extracao&page=2&recorte=todos',
    );
    expect(caminhoLista({ q: '', filtros: [], page: 1, recorteTodos: false, situacao: 'historico' })).toBe(
      '/api/licitacoes?situacao=historico',
    );
  });

  it('vários filtros vão repetidos e o vencimento como vence_em', () => {
    expect(caminhoLista({ q: '', filtros: ['conflito', 'extraidas'], venceEm: 15, page: 1, recorteTodos: false })).toBe(
      '/api/licitacoes?filtro=conflito&filtro=extraidas&vence_em=15',
    );
    expect(caminhoLista({ q: '', filtros: ['todas'], venceEm: null, page: 1, recorteTodos: false })).toBe('/api/licitacoes');
  });

  it('"apenas FOPA (a IA confirma)" vai como so_fopa_ia, na lista e no analytics (db/034)', () => {
    expect(caminhoLista({ q: '', filtros: [], page: 1, recorteTodos: false, situacao: 'historico', soFopaIa: true })).toBe(
      '/api/licitacoes?situacao=historico&so_fopa_ia=true',
    );
    expect(caminhoLista({ q: '', filtros: [], page: 1, recorteTodos: false, soFopaIa: false })).toBe('/api/licitacoes');
    expect(caminhoAnalytics({ escopoTodos: false, soFopaIa: true })).toBe('/api/analytics?so_fopa_ia=true');
    expect(caminhoAnalytics({ escopoTodos: false })).toBe('/api/analytics');
  });
});

describe('marcar vários no "Mostrar" e o vencimento', () => {
  it('marca, desmarca, e "Todas" limpa', () => {
    expect(alternarFiltro([], 'conflito')).toEqual(['conflito']);
    expect(alternarFiltro(['conflito'], 'extraidas')).toEqual(['conflito', 'extraidas']);
    expect(alternarFiltro(['conflito', 'extraidas'], 'conflito')).toEqual(['extraidas']);
    expect(alternarFiltro(['conflito', 'extraidas'], 'todas')).toEqual([]);
  });

  it('"Já extraídas" e "Sem extração" se excluem', () => {
    expect(alternarFiltro(['conflito', 'extraidas'], 'sem_extracao')).toEqual(['conflito', 'sem_extracao']);
    expect(alternarFiltro(['sem_extracao'], 'extraidas')).toEqual(['extraidas']);
  });

  it('vencimento: só 7, 15, 30, 45 ou 60', () => {
    expect([...VENCIMENTOS]).toEqual([7, 15, 30, 45, 60]);
    expect(vencimentoDaUrl('15')).toBe(15);
    expect(vencimentoDaUrl('10')).toBeNull();
    expect(vencimentoDaUrl('')).toBeNull();
    expect(vencimentoDaUrl(null)).toBeNull();
    expect(vencimentoDaUrl('abc')).toBeNull();
  });
});
