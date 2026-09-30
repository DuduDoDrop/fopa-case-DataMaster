/**
 * Quem está logado e o que o papel permite. Desde 26/09:
 * - usuário (`leitor`, quem entra pelo Google pela primeira vez): painel, histórico, analytics, o detalhe e — desde
 *   27/09 — a Revisão, onde decide e rotula escopo;
 * - operador: hoje, o mesmo que o usuário (o papel continua no banco);
 * - admin: + Execuções, E-mails, Saúde, Admin e os botões da API (extrair, processar, reverificar);
 * - admin supremo (um admin com `supremo`, db/046): + dar e tirar acesso; o site não o altera.
 * O servidor é quem garante (403); aqui é para o link e o botão nem aparecerem para quem não pode.
 */
import { createContext, useContext } from 'react';
import type { Me } from '../api/tipos';

export const SessaoContexto = createContext<Me | null>(null);

export function useSessao(): Me | null {
  return useContext(SessaoContexto);
}

/** Decide revisão e rotula escopo: qualquer usuário logado desde 27/09 (ADR-021, emenda); antes, operador ou admin. */
export function podeOperar(me: Me | null): boolean {
  return !!me;
}

export function ehAdmin(me: Me | null): boolean {
  return me?.papel === 'admin';
}

/** Quem dá e tira acesso: só o admin supremo (db/046). */
export function ehSupremo(me: Me | null): boolean {
  return ehAdmin(me) && !!me?.supremo;
}

export type Minimo = 'operador' | 'admin';
const NIVEL: Record<string, number> = { leitor: 1, operador: 2, admin: 3 };

/** O papel alcança o mínimo? (a mesma escada do servidor, api/site.py:NIVEL) */
export function permitido(me: Me | null, minimo: Minimo): boolean {
  return (NIVEL[me?.papel ?? ''] ?? 0) >= NIVEL[minimo];
}

/** O papel como a tela diz, com inicial maiúscula: o leitor aparece como "Usuário"; o admin supremo, como "Admin Supremo". */
const NOMES_PAPEL: Record<string, string> = { leitor: 'Usuário', operador: 'Operador', admin: 'Admin' };

export function nomePapel(me: Pick<Me, 'papel' | 'supremo'> | null): string {
  if (!me) return '';
  if (me.papel === 'admin' && me.supremo) return 'Admin Supremo';
  return NOMES_PAPEL[me.papel] ?? me.papel;
}

export const MOTIVO_SO_OPERADOR = 'Faça login para registrar a decisão.';
export const MOTIVO_SO_ADMIN = 'Ação restrita a administradores.';
export const MOTIVO_SO_SUPREMO = 'Somente o administrador supremo concede e revoga acessos.';
