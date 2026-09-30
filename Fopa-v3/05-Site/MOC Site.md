---
tipo: moc
familia: site
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - web/src/App.tsx
  - web/src/componentes/Layout.tsx
  - api/site.py
tags: [moc, site]
---

# MOC Site

> [!abstract] Em uma frase
> O site `https://licitacaofopa.com.br` é por onde a equipe usa o produto: **13 telas** atrás do login com Google — painel do dia, histórico, dois painéis de mercado, detalhe e relatório de cada licitação, revisão humana, governança e compliance e quatro telas de operação —, mais a política de privacidade pública.

## Papel na solução

O site **só lê do banco** e grava decisões humanas (revisões, rótulos, configuração); todo trabalho pesado ou pago é pedido ao n8n pelos botões ([[W11 Ações do site]]). Assim a tela nunca espera um processamento e nunca tem acesso direto ao modelo ou ao PNCP ([[Arquitetura]]).

## As telas

| Tela | Rota | Quem vê | Para quê |
|---|---|---|---|
| [[Login com Google\|Entrar]] | `/entrar` | público | login com Google |
| [[Página Painel\|Painel]] | `/` | usuário | as licitações em andamento, por prazo |
| [[Página Histórico\|Histórico]] | `/historico` | usuário | as que já não estão valendo |
| [[Página Analytics de Mercado\|Analytics de Mercado]] | `/analytics` | usuário | quem compra folha, por quanto e quando |
| [[Página Analytics Histórico FOPA\|Analytics Histórico FOPA]] | `/analytics/historico-fopa` | usuário | licitações republicadas e a segunda chance |
| [[Página Detalhe da licitação\|Detalhe]] | `/licitacao/:slug` | usuário (ações: admin) | as 17 respostas com prova, e tudo da licitação |
| [[Página Relatório\|Relatório]] | `/licitacao/:slug/relatorio` | usuário | o relatório HTML da extração |
| [[Página Revisão\|Revisão]] | `/revisao` | usuário (escopo: admin) | os itens que exigem revisão humana |
| [[Página Governança\|Governança]] | `/governanca` | usuário | princípios, controles e normas que regem o uso de IA na solução |
| [[Página Execuções\|Execuções]] | `/execucoes` | admin | o diário de cada fluxo |
| [[Página E-mails\|E-mails]] | `/emails` | admin | a fila de e-mails como saiu |
| [[Página Saúde\|Saúde]] | `/saude` | admin | a saúde e o contrato do sistema |
| [[Página Admin\|Admin]] | `/admin` | admin (usuários: supremo) | operação e configuração |
| [[Página Privacidade\|Privacidade]] | `/privacidade` | público | política de privacidade |

## Como o site é feito

| Camada | Tecnologia | Detalhe |
|---|---|---|
| Interface | React + TypeScript, empacotado com Vite | rotas com React Router; dados com React Query (cache no navegador, revalidação automática) |
| Servidor | FastAPI (`api/site.py`), a mesma imagem do worker | serve o build do React, as rotas `/api/*`, o login e a privacidade — mesma origem, sem CORS |
| Acesso | sessão por cookie assinado + banco | [[Login com Google]], [[Papéis e acesso]] |
| Visual | tema claro e escuro (o botão diz para onde vai: **Modo Escuro** no fundo claro, **Modo Claro** no escuro; a escolha fica no navegador), textos com contraste acima de 5:1, layout que funciona no celular (390 px) | linguagem do painel: prazo colorido, vermelho só para defeito, números em fonte monoespaçada |
| Testes | Vitest nas telas e nos componentes; *fixtures* do contrato da API | [[Testes e CI]] |

A barra do topo, em maiúsculas, tem as abas (Painel, Histórico, Analytics, Revisão, Governança e, para administradores, Execuções, E-mails, Saúde e Admin), o e-mail de quem está logado — a única coisa em minúsculas — e o papel dele, o botão de tema e **Atualizar** (recarrega os dados da tela). Esses três andam juntos, à direita: quando a barra não cabe numa linha (o caso do administrador com e-mail longo), descem juntos para a linha de baixo.

## Relacionadas

[[Home]] · [[API do site — endpoints]] · [[Papéis e acesso]] · [[Arquitetura]] · [[MOC Fluxos n8n]]
