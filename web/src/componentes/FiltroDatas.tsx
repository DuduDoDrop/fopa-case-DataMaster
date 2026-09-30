/**
 * Filtro de datas pela PUBLICAÇÃO. As duas pontas entram; sem nenhuma, é todo o histórico. O valor mora na URL
 * (`de`, `ate`), como os outros filtros.
 *
 * Desde 26/09 é uma LISTA "Período" — todo o histórico, os anos
 * (cada um preenche as duas pontas) e "escolher datas…", que mostra os dois campos de data.
 *
 * `rotulo` e `acao` dão nome a uma SEGUNDA cópia na mesma página — "Período da compra", "comprada de" —, que olha
 * outra data: dois campos com o mesmo nome confundem quem usa leitor de tela e quem procura o campo pelo nome.
 */
import { useState } from 'react';
import { Lista } from './Lista';

const RE_DATA = /^\d{4}-\d{2}-\d{2}$/;
const DATAS = 'datas';

/** A data da URL, se for uma data de verdade (AAAA-MM-DD); senão, nada. */
export function dataDaUrl(v: string | null): string | null {
  if (!v || !RE_DATA.test(v)) return null;
  const d = new Date(`${v}T12:00:00Z`);
  return Number.isNaN(d.getTime()) || d.toISOString().slice(0, 10) !== v ? null : v;
}

export function FiltroDatas({
  de,
  ate,
  anos = [],
  aoMudar,
  rotulo = 'Período',
  acao = 'publicada',
}: {
  de: string | null;
  ate: string | null;
  anos?: number[];
  aoMudar: (de: string | null, ate: string | null) => void;
  rotulo?: string;
  acao?: string;
}) {
  // "escolher datas…" mostra os campos mesmo quando as pontas ainda estão vazias ou formam um ano inteiro
  const [escolhendo, setEscolhendo] = useState(false);
  const ano = anos.find((a) => de === `${a}-01-01` && ate === `${a}-12-31`);
  const modo = escolhendo ? DATAS : !de && !ate ? '' : ano ? String(ano) : DATAS;
  const opcoes = [
    { valor: '', texto: 'Todo o histórico' },
    ...anos.map((a) => ({ valor: String(a), texto: String(a) })),
    { valor: DATAS, texto: 'Escolher datas' },
  ];
  return (
    <span className="filtro-datas">
      <Lista
        rotulo={rotulo}
        valor={modo}
        opcoes={opcoes}
        aoMudar={(v) => {
          if (v === DATAS) {
            setEscolhendo(true);
            return;
          }
          setEscolhendo(false);
          if (v === '') aoMudar(null, null);
          else aoMudar(`${v}-01-01`, `${v}-12-31`);
        }}
      />
      {modo === DATAS && (
        <>
          <label>
            {acao} de{' '}
            <input
              type="date"
              aria-label={`${acao} de`}
              value={de ?? ''}
              max={ate ?? undefined}
              onChange={(e) => aoMudar(dataDaUrl(e.target.value), ate)}
            />
          </label>{' '}
          <label>
            até{' '}
            <input
              type="date"
              aria-label={`${acao} até`}
              value={ate ?? ''}
              min={de ?? undefined}
              onChange={(e) => aoMudar(de, dataDaUrl(e.target.value))}
            />
          </label>
        </>
      )}
    </span>
  );
}
