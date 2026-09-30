# web/ — o site da FOPA v3

React 18 + Vite + TypeScript + React Router + TanStack Query. É o painel
(`amostras/index.html`) e o RELATORIO (`RELATORIO.html`) da v2 como páginas
vivas lendo o Postgres pela `fopa-api`. A referência visual é
[`design/README.md`](design/README.md), e ela vale para tudo aqui:
**o site segue o HTML do relatório**.

## Rodar

O host não tem Node: tudo roda no container `node:22-alpine`, com `web/`
montado. O volume anônimo em `node_modules` deixa as dependências do
container fora do host (e o `dist/` também, se não for para usar o build).

```sh
# instalar + testes + build (o que o orquestrador roda)
docker run --rm -v "<repo>/web:/web" -v /web/node_modules -v /web/dist -w /web node:22-alpine \
  sh -c "npm ci && npm test && npm run build"
```

No Git Bash do Windows, prefixe `MSYS_NO_PATHCONV=1` e use o caminho com
barra normal (`C:/Users/.../web:/web`), senão o `/web` vira caminho do Windows.

### Dev com a API de verdade

`npm run dev` sobe o Vite na porta 5173 e repassa `/api/*`, `/auth/*` e
`/login` para a `fopa-api` (proxy em `vite.config.ts`). O alvo padrão é
`http://127.0.0.1:8080`, que é onde o compose publica a api no host. **Dentro
de um container, 127.0.0.1 é o próprio container**, então aponte o proxy para o
host com `FOPA_API_URL`:

```sh
docker run --rm -it -p 5173:5173 -v "<repo>/web:/web" -v /web/node_modules -w /web \
  -e FOPA_API_URL=http://host.docker.internal:8080 \
  node:22-alpine sh -c "npm ci && npm run dev"
# abra http://localhost:5173
```

A sessão é o cookie HttpOnly da api. Como o proxy mantém a mesma origem
(`localhost:5173`), o cookie do login vai junto.

## O contrato é o da API — e os testes provam com a API de verdade

`src/api/tipos.ts` descreve o que `api/site.py` + `api/consultas.py`
devolvem **de fato**. As fixtures dos testes não são escritas à mão: saem da
API real.

```sh
# da raiz do repositório; precisa de Docker (Postgres efêmero) e do Python do projeto
python web/scripts/gerar_fixtures.py
```

O script sobe `api.site` contra o Postgres efêmero dos testes
(`tests/pg_efemero.py`), importa o acervo sintético pelo importador de
verdade (`migracao/tests/fabrica.py`, o mesmo cenário de
`api/tests/test_site.py`, com os casos que o front precisa ver: os três
estados de ausência, página corrigida, pirâmide da Q13, histórico com duas
verificações, sinais do Jev, rótulo de escopo), entra pelo **login local da
demo** (`FOPA_ENV=demo`, `FOPA_AUTH_MODE=local`) e grava cada resposta em
`src/__fixtures__/contrato/<nome>.json` como `{metodo, caminho, status,
corpo}`, mais `_meta.json` com o instante da geração (os prazos do cenário
são relativos a ele e os testes fixam o relógio nele). O worker
(`/health`, `/questionario`) é o `api.worker` rodando no mesmo processo; o
único mock é o n8n (o W11 ainda não existe): 202 `{execucao_id}` no
"verificar", como no plano §5. Nenhuma API paga é chamada.

`src/__fixtures__/contrato.ts` atribui cada `corpo` ao tipo de `tipos.ts`:
se o site passar a exigir um campo que a API não manda, o `tsc` do
`npm run build` quebra ali. Casos que a API real ainda não gera (campo de
versão anterior ausente, provedor que só o servidor sabe que cobra) são
**derivados** de um corpo real, mudando só o campo do caso, e o teste diz
isso. Mudou a API? Rode o script de novo e veja o que fica vermelho.

## Páginas e o que consomem

| rota | API |
|---|---|
| `/` Painel | `GET /api/resumo[?recorte=todos]`, `GET /api/licitacoes?q&filtro&page[&recorte=todos]` |
| `/licitacao/:slug` | `GET /api/licitacoes/{slug}`, `GET /api/resumo` (provedor vigente), `POST /api/acoes/reverificar {controle}`, `POST /api/acoes/processar {controles}` |
| `/licitacao/:slug/relatorio` | navega para `GET /api/licitacoes/{slug}/relatorio` (text/html) |
| `/revisao` | `GET /api/fila-revisao`, `POST /api/revisoes {verificacao_id, pergunta_id, decisao, resposta_corrigida?, nota?}`; aba escopo: `GET /api/rotulos-escopo`, `POST /api/rotulos-escopo {controle, dentro, motivo?}` |
| `/questionario` | `GET /api/questionario` (proxy do `/questionario` do worker) |
| `/execucoes` | `GET /api/execucoes`, `GET /api/custo` |
| `/emails` | `GET /api/emails` |
| `/saude` | `GET /api/saude` (503 com corpo = peça caída: a tela mostra) |
| `/admin` | `GET/PUT /api/admin/configuracao {chave, valor, confirmar?}` (409 sem `confirmar` para provedor pago), `GET/PUT /api/admin/orcamento`, `GET/POST/PUT /api/admin/termos`, `GET/POST/PUT /api/admin/usuarios`, `POST /api/admin/reservar-demo {controles, dias}`, `POST /api/acoes/verificar` (202 `{execucao_id}`) + `GET /api/execucoes/{id}` |
| `/entrar` | botão → `/login` **do servidor** (modo local na demo; Google no resto). O rótulo vem do `auth_mode` da `/api/saude` |
| todas | `GET /api/me` → `{email, papel, nome}`; **401 → `/entrar`**; 403 mostra a mensagem, sem redirecionar |

Pontos do contrato que o site já errou e os testes seguram:

- `GET /api/licitacoes` → `{total, page, por_pagina, paginas, recorte,
  itens: v_card[]}`. `filtro=` aceita exatamente as chaves de
  `consultas.FILTROS` (`sem_extracao`, `revisao`, ... — com hífen é 422). O
  servidor filtra, ordena e pagina: o site não refiltra a página (o contador
  é o `total` dele). Por padrão só o recorte de 2026 (ADR-015);
  `?recorte=todos` traz o resto (`no_recorte: false` no card).
- `GET /api/licitacoes/{slug}` → `{licitacao, respostas, verificacao_respostas,
  arquivos, execucao, leitura, historico, eventos, gabarito, revisoes,
  execucoes_workflow, jev}`. `respostas` (do modelo) e
  `verificacao_respostas` (do verificador) vêm **separadas**; o site junta
  por pergunta (`lib/respostas.ts`). Sem isso não há veredito nem
  `arquivo_id`, e a Origem fica sem link `#page=N`.
- `GET /api/resumo` → `custo_conhecido_brl`, `custo_sem_preco`,
  `ultima_coleta {iniciado_em, cego, ...}`, `ano_minimo`, `fora_recorte`,
  `jev`.
- `GET /api/execucoes/{id}` → `{execucao: {status, ...}, buscas, ...}`: o
  status mora em `execucao`.
- 422 do FastAPI tem `detail` em lista: o cliente junta as mensagens.
- Valores `numeric` podem vir como string ("6.560"); o site converte.

Jev (score, nunca decisão): selo `filtro N%` no card (âmbar e com link para
a aba de escopo quando discorda com convicção) e `sustenta N%` ao lado de
cada resposta APROVADA no detalhe, sempre com "sinal do Jev — não muda
veredito nem escopo". Sem os campos, nada aparece.

## Como o build entra na imagem

`docker/worker.Dockerfile` tem um stage `web` (`node:22-alpine`): copia
`package.json` + `package-lock.json`, roda `npm ci`, copia `index.html`,
`vite.config.ts`, `tsconfig.json`, `design/` e `src/` (fixtures de contrato
incluídas), e roda `npm test && npm run build`. Teste vermelho = imagem não
sai. A imagem final recebe só `COPY --from=web /web/dist/ ./web/dist/` →
**`/app/web/dist`**; Node e `node_modules` não entram. A `fopa-api` serve esse
`dist/` na mesma origem de `/api` (sem CORS) e devolve `index.html` para as
rotas do React. `web/scripts/` não entra na imagem.

## CSS: os dois arquivos de `design/`, com escopo

`design/painel.css` e `design/relatorio.css` são extraídos de `painel.py` e
`pagina.py` e **não são editados à mão**. O site os importa como estão; um
plugin PostCSS em `vite.config.ts` prefixa cada seletor com `.pg-painel` ou
`.pg-relatorio` (só `:root`, `*` e `body`, idênticos nos dois, ficam globais),
porque num SPA os dois arquivos se contradizem (`td`, `details`, `.wrap`,
`.acoes`). O que o HTML não tinha (menu, paginação, formulários do admin e da
revisão, botão desabilitado, o selo do Jev, o recorte) está em
`src/estilo/extra.css`, só com os tokens de lá.

## Regras de design que os testes seguram

`src/__testes__/` (vitest + Testing Library, dados em `src/__fixtures__/contrato/`):

- **prazo** (`lib/prazo.ts`): a tabela da §4 do design README inteira, inclusive
  "sessão passou (da Q1)"; `dias` calculado no navegador em America/Sao_Paulo
  (o teste roda com `TZ=Asia/Tokyo` para provar que o fuso da máquina não
  entra); com hora declarada, a sessão de hoje que já passou é encerrada —
  "há 0 dia(s)", a linha da tabela, com a hora no `title`.
- **custo**: NULL / `preco_conhecido=false` = "preço não configurado", nunca
  `R$ 0,00`; legado = "R$ X (legado)"; milhar com Intl pt-BR.
- **as 17**: evidência em todas as linhas, com os três estados de ausência
  (`.naoaplica`, `.semev`, `.faltaev`); barra `st-ok/st-rev/st-nl`; crítica
  como `.marca`; link "arquivo — p. N" → `/api/pdf/{slug}/{id}#page=N` pelo
  `arquivo_id` do verificador, nunca pelo nome cru.
- **botões**: quem não pode agir vê o botão desabilitado com o motivo no
  `title`; processar e trocar provedor para claude/openai pedem confirmação
  com custo estimado e provedor (e o 409 da API também vira confirmação).
