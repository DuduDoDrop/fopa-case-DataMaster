/**
 * A cor de cada banco nos gráficos do Analytics: Santander vermelho, Banco do Brasil amarelo, Caixa azul,
 * Bradesco vermelho claro, Itaú laranja, e assim por diante.
 *
 * Pela RAIZ do CNPJ (os 8 primeiros dígitos: o mesmo banco com CNPJs de agência diferentes cai junto,
 * como no ranking — api/analytics.py). Cooperativa de crédito tem um CNPJ por singular, então vai pelo
 * NOME do sistema. Quem não tem marca aqui pega um tom neutro da paleta do painel; "Outros", cinza.
 * O amarelo do BB é o da marca escurecido o bastante para ler sobre o papel.
 */
export const COR_OUTROS = '#9AA3AE';

const POR_RAIZ: Record<string, string> = {
  '00000000': '#E5B800', // Banco do Brasil — amarelo
  '00360305': '#005CA9', // Caixa — azul
  '90400888': '#EC0000', // Santander — vermelho
  '60746948': '#F0707A', // Bradesco — vermelho claro
  '60701190': '#EC7000', // Itaú — laranja
  '92702067': '#4DA3DB', // Banrisul — azul claro (o escuro é da Caixa)
  '00000208': '#1B3D6D', // BRB — azul-marinho
  '07237373': '#8C1D40', // Banco do Nordeste — vinho
  '28127603': '#2E7D6B', // Banestes — verde-petróleo
  '04913711': '#1F5AA6', // Banpará — azul
  '13009717': '#0B8A4C', // Banese — verde
  '00416968': '#FF9A3D', // Inter — laranja claro (o forte é do Itaú)
  '18236120': '#820AD1', // Nubank — roxo
};

const POR_NOME: [RegExp, string][] = [
  [/SICOOB/i, '#00A091'], // Sicoob — verde-água
  [/SICREDI/i, '#3FA110'], // Sicredi — verde
  [/CRESOL/i, '#8BBF3F'], // Cresol — verde-limão
  [/UNICRED/i, '#6D2077'], // Unicred — roxo
];

// Tons do painel (design/painel.css) que não brigam com as marcas acima.
const NEUTRAS = ['#11243D', '#1D6F63', '#8A6A18', '#4B6A9B', '#7A5C99', '#5E6B78'];

export function corDoBanco(cnpjRaiz: string | null, nome: string | null, i: number): string {
  if (cnpjRaiz === null) return COR_OUTROS;
  const marca = POR_RAIZ[cnpjRaiz];
  if (marca) return marca;
  for (const [re, cor] of POR_NOME) if (re.test(nome ?? '')) return cor;
  return NEUTRAS[i % NEUTRAS.length];
}
