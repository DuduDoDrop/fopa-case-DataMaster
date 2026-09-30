---
tipo: decisao
familia: decisoes
adr: 21
data: 2026-09-26
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, site, acesso, seguranca]
---

# ADR-021 — Quem vê o quê: usuário, operador, admin e admin supremo

> [!abstract] Em uma frase
> **Ver é amplo, agir é restrito:** qualquer conta Google que entra vira **usuário** e lê o painel, o histórico, as análises e decide revisões de respostas; só o **administrador** opera o sistema e aperta os botões que chamam a automação ou gastam API; e só o **administrador supremo** dá, bloqueia e remove acesso — sem que o site consiga alterá-lo.

## Problema

O acesso era uma lista fechada, e todo mundo via todas as páginas no menu, inclusive as de operação. O produto precisava abrir a leitura para quem vai usar a informação sem abrir o que custa dinheiro (a extração por API) ou mexe em dados (configuração, escopo).

## Opções

| Opção | Avaliação |
|---|---|
| lista fechada de convidados | cada leitor novo depende de cadastro manual |
| todos veem tudo | expõe operação e custo |
| **cadastro automático como usuário; operação só do admin; gestão de acesso só do supremo** | adotado |

## Escolha

| Papel | Quem é | Vê | Faz |
|---|---|---|---|
| **usuário** (`leitor`) | quem entra pelo Google pela primeira vez, cadastrado no próprio login | Painel, Histórico, Analytics, detalhe, relatório | lê e **decide revisões de respostas** |
| **operador** | quem o supremo promove | o mesmo que o usuário | papel mantido no banco, sem nada a mais hoje |
| **admin** | quem o supremo promove | tudo, inclusive Execuções, E-mails, Saúde e Admin | os botões da automação (extrair, processar, reverificar, verificar, importar), a configuração e a **revisão de escopo** |
| **admin supremo** | o dono do produto (marca `supremo` no cadastro) | tudo | dá e tira papel, **bloqueia** e **remove** usuários; o site não o altera — nem ele mesmo, por engano |

- **O servidor garante** (401 sem sessão, 403 sem papel) e **a tela não mostra**: o link some do menu, a rota por endereço direto diz "sem acesso", os botões de ação nem são desenhados.
- **A revisão de escopo é do admin** porque o rótulo "é/não é folha" prevalece sobre a regra e tira ou põe licitação no painel; a decisão de revisão de respostas fica numa camada própria e não altera o veredito ([[Verificador determinístico]]).
- **Bloquear** impede a entrada (a sessão aberta cai na requisição seguinte); **remover** apaga o cadastro e as sessões — a pessoa pode voltar como usuário, e o que ela fez continua no histórico.
- O supremo é um admin com uma marca, não um papel novo: o banco garante que ele é admin, ativo e único.
- O `/api/saude` resumido continua público (é o healthcheck dos containers); a **página** Saúde é do admin.

## O que custa

Qualquer conta Google lê o painel — adequado a um produto de leitura; o que custa dinheiro ou muda dados continua atrás do admin.

## Onde vive em produção

`api/site.py` (dependências de papel por rota), `db/046` (supremo), `db/048` (remoção), `web/src/componentes/Restrita.tsx`; a tela de usuários no [[Página Admin|Admin]]. Detalhe em [[Papéis e acesso]] e [[Login com Google]].

## O que reabriria a decisão

A necessidade de restringir a leitura a um grupo (por exemplo, dados sensíveis de negócio no painel) — aí o cadastro automático volta a ser lista.

## Relacionadas

[[MOC Decisões]] · [[Papéis e acesso]] · [[Login com Google]] · [[Controle de acesso e segredos]] · [[API do site — endpoints]] · [[Privacidade e LGPD]]
