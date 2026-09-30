/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import type { AtRule, Plugin as PluginPostcss } from 'postcss';

/**
 * Escopo dos dois CSS de referência (web/design/).
 *
 * POR QUE NÃO COPIAR O CSS PARA DENTRO DE src/: `painel.css` e `relatorio.css`
 * são extraídos literalmente de `painel.py` e `pagina.py` e "nunca editados à
 * mão" (web/design/README.md). Uma cópia ajustada no site divergiria do HTML
 * na primeira mudança de lá, e a regra é seguir o HTML.
 *
 * POR QUE PRECISA DE ESCOPO: num SPA o CSS importado vale para a página toda,
 * e os dois arquivos se contradizem (`td` 13px × 14.5px, `details` com margem,
 * `.wrap` 1240 × 1180, `.acoes` definido duas vezes). Aqui cada seletor ganha
 * o prefixo da página que o usa — `.pg-painel` ou `.pg-relatorio` —, e só
 * `:root`, `*` e `body` (idênticos nos dois) ficam globais.
 */
function escopoDoDesign(): PluginPostcss {
  return {
    postcssPlugin: 'fopa-escopo-design',
    Once(raiz) {
      const arquivo = (raiz.source?.input.file ?? '').split('\\').join('/');
      const achado = arquivo.match(/\/design\/(painel|relatorio)\.css$/);
      if (!achado) return;
      const escopo = achado[1] === 'painel' ? '.pg-painel' : '.pg-relatorio';
      raiz.walkRules((regra) => {
        const pai = regra.parent;
        if (pai && pai.type === 'atrule' && /keyframes$/i.test((pai as AtRule).name)) return;
        regra.selectors = regra.selectors.map((sel) => {
          const s = sel.trim();
          if (s === ':root' || s === '*' || s === 'body') return s;
          return `${escopo} ${s}`;
        });
      });
    },
  };
}

// Em dev o Vite serve o front e repassa /api, /auth e /login para a
// fopa-api (127.0.0.1:8080 no host) — `/login` é do servidor (modo local da
// demo ou Google), como em produção. Dentro de um container, 127.0.0.1 é o
// próprio container: aí FOPA_API_URL=http://host.docker.internal:8080
// (web/README.md).
const alvo = process.env.FOPA_API_URL ?? 'http://127.0.0.1:8080';

export default defineConfig({
  plugins: [react()],
  css: { postcss: { plugins: [escopoDoDesign()] } },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: alvo, changeOrigin: false },
      '/auth': { target: alvo, changeOrigin: false },
      '/login': { target: alvo, changeOrigin: false },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/__testes__/preparo.ts'],
    // O relógio do teste é fixado em cada caso; o fuso do processo NÃO pode
    // influenciar o cálculo de `dias` (ele usa America/Sao_Paulo explícito).
    env: { TZ: 'Asia/Tokyo' },
  },
});
