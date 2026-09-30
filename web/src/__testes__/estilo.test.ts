/**
 * Regras do CSS que o jsdom não vê (ele não aplica folha de estilo): conferidas no texto do arquivo, lido do disco —
 * o `import '...css?raw'` chega VAZIO no vitest (ele descarta o conteúdo do CSS), e o teste passava sem olhar nada.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

// A partir de web/ (onde o `npm test` roda, aqui e no CI): no ambiente jsdom o import.meta.url não é um file://.
const extra = readFileSync(resolve(process.cwd(), 'src/estilo/extra.css'), 'utf8');

/** As regras do arquivo, a mais interna de cada bloco (dentro de @media também): seletor e corpo. */
function regras(css: string) {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map(([, seletor, corpo]) => ({ seletor: seletor.trim(), corpo }));
}

/** O corpo da primeira regra com exatamente este seletor (sem o comentário que vem antes dela no arquivo). */
function corpo(seletor: string) {
  return regras(extra).find((r) => r.seletor.replace(/\/\*[\s\S]*?\*\//g, '').trim() === seletor)?.corpo ?? '';
}

/** O valor de uma propriedade no corpo de uma regra (`width` não casa com `max-width`). */
function valor(corpoDaRegra: string, propriedade: string) {
  return corpoDaRegra.match(new RegExp(`(?:^|;)\\s*${propriedade}\\s*:\\s*([^;]+)`))?.[1].trim();
}

describe('extra.css', () => {
  it('o arquivo foi lido de verdade (senão os testes abaixo passariam sem olhar nada)', () => {
    expect(extra.length).toBeGreaterThan(1000);
    expect(regras(extra).some((r) => r.seletor.endsWith('.escolha-ia select'))).toBe(true);
  });

  it('nenhum select com fundo transparente: no escuro a lista que abre fica clara, com o texto claro', () => {
    // No modo escuro, as listas de "Extrair com IA" ficavam com as cores trocadas. O Chrome desenha a lista
    // aberta fora da página: com o fundo do select transparente, ela não pega o fundo escuro do painel, e as opções
    // herdam o texto quase branco do modo escuro (--ink #E3E9F0). As listas da barra (.lista select) têm fundo sólido.
    const transparentes = regras(extra).filter(
      (r) => /\bselect\b/.test(r.seletor) && /background(-color)?\s*:\s*transparent/.test(r.corpo),
    );
    expect(transparentes.map((r) => r.seletor)).toEqual([]);
  });

  it('no cabeçalho em maiúsculas, só o e-mail fica em minúsculas', () => {
    expect(valor(corpo('nav.menu'), 'text-transform')).toBe('uppercase');
    expect(valor(corpo('nav.menu .quem .email'), 'text-transform')).toBe('lowercase');
    // o papel, ao lado do e-mail, segue o menu
    expect(valor(corpo('nav.menu .quem'), 'text-transform')).toBeUndefined();
  });

  it('a busca do banco fica ao lado do rótulo, na altura e no canto da lista do período', () => {
    // Com width:min(340px,100%), os 100% eram a largura do próprio rótulo: a caixa descia para baixo dele e ficava 14 px
    // abaixo da lista do período, com 2 px a mais de altura e outro canto.
    const busca = corpo('.pg-analytics .busca-banco');
    const caixa = corpo('.pg-analytics .busca-banco input');
    const lista = corpo('.lista select');
    expect(valor(busca, 'flex-wrap')).toBeUndefined();
    expect(valor(busca, 'white-space')).toBe('nowrap');
    expect(valor(caixa, 'width')).toBe('340px');
    expect(valor(caixa, 'min-height')).toBe(valor(lista, 'min-height'));
    expect(valor(caixa, 'border-radius')).toBe(valor(lista, 'border-radius'));
    // 20 px de linha + 8 + 8 de respiro + 1 + 1 de borda = os 38 px da lista. O `font:inherit` tem de vir antes: depois,
    // ele devolveria a linha de 1,55 da página (40 px).
    expect(valor(caixa, 'line-height')).toBe('20px');
    expect(caixa.indexOf('line-height')).toBeGreaterThan(caixa.indexOf('font:inherit'));
  });

  it('o "Filtrar" da barra do painel é o botão principal, na altura das listas', () => {
    // O painel.css entra com escopo (.pg-painel .barra button) e venceria o .primario: o botão sairia com o fundo dos
    // outros botões da barra.
    const filtrar = corpo('.pg-painel .barra button.primario');
    expect(valor(filtrar, 'background')).toBe('var(--teal)');
    expect(valor(filtrar, 'min-height')).toBe(valor(corpo('.lista select'), 'min-height'));
  });

  it('o grupo da conta (e-mail, tema e "Atualizar") fica à direita e desce inteiro quando o menu não cabe', () => {
    // Medido no ar: o menu do admin com a Governança e um e-mail de 34 caracteres pede 1.389 px, e o menu tem 1.240.
    const conta = corpo('nav.menu .conta');
    expect(valor(conta, 'margin-left')).toBe('auto');
    expect(valor(conta, 'flex-wrap')).toBe('wrap');
    expect(valor(conta, 'justify-content')).toBe('flex-end');
    // quem empurra para a direita agora é o grupo, não o e-mail sozinho
    expect(valor(corpo('nav.menu .quem'), 'margin-left')).toBeUndefined();
  });

  it('a Governança em duas colunas, e em uma no celular', () => {
    expect(valor(corpo('.governanca-grade'), 'grid-template-columns')).toBe('repeat(2,minmax(0,1fr))');
    expect(extra).toMatch(/@media\(max-width:860px\)\{\.governanca-grade\{grid-template-columns:1fr\}\}/);
  });

  it('na Revisão, o título e os passos ficam juntos, e o título vence o h2 do relatório', () => {
    // O relatorio.css entra com escopo (.pg-relatorio h2{margin:14px 0 0}): sem o .pg-relatorio na frente, as duas
    // regras empatariam e a ordem dos arquivos no pacote decidiria a margem do título.
    expect(valor(corpo('.pg-relatorio .revisao-guia h2'), 'margin')).toBe('0');
    expect(valor(corpo('.revisao-guia'), 'gap')).toBe('8px');
  });

  it('o botão do "Mostrar" tem os 38 px das listas: linha de 20 px depois do font:inherit', () => {
    // Medido na página: com o font:inherit, o botão herdava a linha de 1,55 da página e ficava com 40 px, 1 px acima e
    // abaixo do "Vencimento" e do "Filtrar". 20 de linha + 8 + 8 de respiro + 1 + 1 de borda = 38.
    const botao = corpo('.lista-multipla>button,.pg-painel .barra .lista-multipla>button');
    expect(valor(botao, 'min-height')).toBe(valor(corpo('.lista select'), 'min-height'));
    expect(valor(botao, 'padding')).toBe('8px 10px');
    expect(valor(botao, 'line-height')).toBe('20px');
    expect(botao.indexOf('line-height')).toBeGreaterThan(botao.indexOf('font:inherit'));
  });
});
