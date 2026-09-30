---
tipo: referencia
familia: worker-e-api
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/site.py
  - api/consultas.py
  - api/analytics.py
  - api/sessao.py
  - api/oauth.py
tags: [api, site, endpoints, referencia, seguranca]
---

# API do site — endpoints

> [!abstract] Em uma frase
> As **46 rotas** do serviço `fopa-api` (FastAPI) que o site React usa: login, leitura das licitações, análises, revisão, operação e as ações que acionam o n8n — cada uma com o papel mínimo exigido.

## Papel na solução

É a única porta entre o navegador e os dados. Ela **lê do Postgres** (com o papel `api_rw`, que só grava decisões humanas), serve o build do React e o relatório, entrega o PDF por URL assinada e, para qualquer trabalho, **chama o n8n** com token ([[Arquitetura]], [[Papéis e acesso]]).

## Autenticação e sessão

| Método e rota | Papel | O que faz |
|---|---|---|
| `GET /login` | público | redireciona para o login com Google |
| `GET /auth/google/login` | público | inicia o OAuth (state, nonce, PKCE) |
| `GET /auth/google/callback` | público | valida o token do Google, cria/lê o usuário, abre a sessão |
| `POST /auth/sair` | sessão | encerra a sessão |
| `GET /api/me` | usuário | quem está logado, papel, se é supremo |

Detalhes em [[Login com Google]].

## Leitura — licitações

| Rota | Papel | O que devolve | Tela |
|---|---|---|---|
| `GET /api/resumo` | usuário | os quadros (ativas ou histórico; recorte; datas; só FOPA pela IA) | [[Página Painel]], [[Página Histórico]] |
| `GET /api/licitacoes` | usuário | cartões paginados, com filtros (busca, estado, UF, modalidade, filtros rápidos — vários, somados com E —, vencimento em até 7, 15, 30, 45 ou 60 dias, situação, datas, página); a nota do Jev entra calculada uma vez por consulta | Painel, Histórico |
| `GET /api/licitacoes/{slug}` | usuário | o detalhe completo (respostas, vereditos, arquivos, leitura, execução, histórico, eventos, revisões, sinais do Jev, pedido pendente) | [[Página Detalhe da licitação]] |
| `GET /api/licitacoes/{slug}/relatorio` | usuário | o relatório HTML da verificação vigente | [[Página Relatório]] |
| `GET /api/pdf/{slug}/{arquivo_id}` | usuário | **302** para URL assinada de 10 min do S3 (ou o arquivo, no armazenamento local); o `#page=N` abre na página | detalhe, relatório, e-mail |
| `GET /api/questionario` | usuário | as 17 perguntas e o contrato do prompt (vem do worker) | — |
| `GET /api/modelos-ia` | usuário | catálogo do "Extrair com IA" com o esforço fixo e a estimativa | detalhe |
| `GET /api/gastos-ia` | usuário | gasto com IA por fornecedor | Painel |

## Leitura — mercado

| Rota | Papel | O que devolve |
|---|---|---|
| `GET /api/analytics` | usuário | números do mercado, ranking de instituições, série mensal, cadeias de republicação ([[Página Analytics de Mercado]], [[Página Analytics Histórico FOPA]]) |
| `GET /api/analytics/compras` | usuário | as compras de uma instituição, com contrato e vigência |

## Revisão humana

| Rota | Papel | O que faz |
|---|---|---|
| `GET /api/fila-revisao/licitacoes` | usuário | licitações com campos pendentes (busca) |
| `GET /api/fila-revisao` | usuário | os campos pendentes de uma licitação |
| `POST /api/revisoes` | usuário | registra a decisão (aceita, corrigida, rejeitada) com nota |
| `GET /api/rotulos-escopo` | admin | a aba Escopo |
| `POST /api/rotulos-escopo` | admin | grava o rótulo "dentro"/"fora" com motivo |

## Operação (só administradores)

| Rota | O que faz |
|---|---|
| `GET /api/execucoes`, `GET /api/execucoes/{id}` | rodadas dos fluxos e o detalhe de uma ([[Página Execuções]]) |
| `GET /api/custo` | custo de modelo agregado |
| `GET /api/emails` | a fila de e-mails ([[Página E-mails]]) |
| `GET/PUT /api/admin/configuracao` | parâmetros da extração ([[Página Admin]]) |
| `GET/PUT /api/admin/orcamento` | teto do dia, máximo por execução, processar automaticamente |
| `GET/POST/PUT /api/admin/termos` | termos de busca |
| `GET /api/admin/usuarios` | lista de usuários |
| `POST/PUT/DELETE /api/admin/usuarios` | **só o supremo**: criar, mudar papel, bloquear, remover |
| `POST /api/admin/reservar-demo` | reservar licitações para demonstração |

## Ações que acionam a automação (só administradores)

| Rota | Webhook do n8n | O que faz |
|---|---|---|
| `POST /api/acoes/verificar` | `fopa/verificar` | "Verificar agora" (busca seca no PNCP) |
| `POST /api/acoes/processar` | `fopa/processar` | põe até 20 licitações na fila |
| `POST /api/acoes/extrair-ia` | `fopa/processar` (com `forcar`) | grava o pedido (provedor e modelo) e processa **só esta** licitação com IA paga |
| `POST /api/acoes/reverificar` | `fopa/reverificar` | reverificação sem modelo |
| `POST /api/acoes/importar-respostas` | `fopa/importar-respostas` | 17 respostas prontas pelo mesmo verificador |

Detalhes em [[W11 Ações do site]]. A resposta do n8n (202, 409, 422) volta ao site como veio.

## Internas e públicas

| Rota | Quem | O que faz |
|---|---|---|
| `POST /api/interno/invalidar` | o n8n, com `X-FOPA-Token` | aviso de publicação nova |
| `GET /api/saude` | público (resumido) / sessão (completo) | saúde do site, do worker, do Postgres e do n8n; 503 se o Postgres ou o worker caem ([[Página Saúde]]) |
| `GET /privacidade` | público | política de privacidade ([[Página Privacidade]]) |
| `GET /{caminho}` | — | serve o build do React (as rotas do site) |

## Regras comuns

- Toda rota `/api/*` de leitura exige sessão: sem cookie, **401** — inclusive para o PDF (nenhum anexo servido fora do login).
- Papel insuficiente: **403** "ação exige papel …".
- As telas de licitações só enxergam o **escopo de folha efetivo** (regra ou rótulo humano); nada fora do escopo aparece em lista, contador, detalhe, relatório ou PDF.
- Entradas validadas por modelo de dados (Pydantic): formato do controle, até 20 controles por ação, 17 respostas na importação, esforço fixo por modelo.

## Relacionadas

[[MOC Worker e API]] · [[MOC Site]] · [[Papéis e acesso]] · [[Endpoints do worker]] · [[W11 Ações do site]] · [[Modelo de dados]]
