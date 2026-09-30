/**
 * Best-of-N na linha da pergunta (v3.1).
 *
 * Quando uma resposta falha no verificador (reprovada, ou "não localizado" numa pergunta que se aplica à
 * modalidade), o sistema pede ao modelo até N-1 tentativas extras só para ela e fica com a que a evidência
 * sustenta — quem escolhe é o próprio verificador (scripts/fopa/melhor_de_n.py), não uma IA. O registro vem em
 * `melhor_de_n.perguntas` do detalhe (db/050); a linha ganha uma nota discreta, no estilo das notas pequenas da
 * página (`.perg`). Sem registro, a linha fica como sempre foi.
 */
import type { TentativasMelhorDeN } from '../api/tipos';

export const AVISO_MELHOR_DE_N =
  'Best-of-N: a resposta não passou no verificador e o modelo tentou novamente; prevalece a tentativa que a evidência sustenta.';

/** "escolhida a 2ª de 3 tentativas" — ou "3 tentativas — ficou a primeira", quando nenhuma extra foi melhor. */
export function textoMelhorDeN({ tentativas, escolhida }: Pick<TentativasMelhorDeN, 'tentativas' | 'escolhida'>): string {
  return escolhida > 0
    ? `escolhida a ${escolhida + 1}ª de ${tentativas} tentativas`
    : `${tentativas} tentativas; prevaleceu a primeira`;
}

export function NotaMelhorDeN({ registro }: { registro: TentativasMelhorDeN | undefined }) {
  if (!registro) return null;
  return (
    <span className="perg" title={AVISO_MELHOR_DE_N}>
      {textoMelhorDeN(registro)}
    </span>
  );
}
