---
tipo: referencia
familia: site
rota: "/entrar · /login · /auth/google/login · /auth/google/callback · /auth/sair"
papel_minimo: publico
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - api/oauth.py
  - api/sessao.py
  - api/site.py
  - web/src/paginas/Login.tsx
tags: [site, login, oauth, seguranca, lgpd]
---

# Login com Google

> [!abstract] Em uma frase
> O acesso ao site é pelo **Google** (OAuth 2.0 com OpenID Connect): o site recebe só **nome e e-mail**, valida o token recebido, cria o cadastro como usuário no primeiro acesso e mantém uma **sessão de 12 horas** num cookie assinado que o banco consegue revogar.

## Papel na solução

Não guardar senha é a forma mais segura de ter login: a autenticação é do Google, e o site só confia num token que ele mesmo confere. Isso atende o requisito de privacidade (o mínimo de dado pessoal: nome e e-mail — [[Privacidade e LGPD]]) e o de segurança (sem senha para vazar, sessão revogável — [[Controle de acesso e segredos]]).

![[site-entrar.jpg]]

## O fluxo, passo a passo

```mermaid
sequenceDiagram
    autonumber
    participant N as Navegador
    participant A as API do site
    participant G as Google
    participant B as Postgres
    N->>A: GET /entrar (página) → clique em "Entrar com Google"
    N->>A: GET /auth/google/login
    A->>N: cookie de estado (10 min, só em /auth) + redireciona ao Google
    N->>G: autorização (scope openid email profile, PKCE, state, nonce)
    G->>N: redireciona para /auth/google/callback?code=…&state=…
    N->>A: GET /auth/google/callback
    A->>A: confere o state do cookie
    A->>G: troca o code (com o verificador PKCE) pelo id_token
    A->>A: valida o id_token: assinatura (JWKS do Google), iss, aud, exp, nonce, email_verified
    A->>B: procura o e-mail em usuarios (novo → cria como usuário; bloqueado → 403)
    A->>B: grava a sessão (hash do id)
    A->>N: cookie fopa_sessao (12 h, HttpOnly, SameSite=Lax, Secure) → redireciona para /
```

## Detalhes que importam

| Ponto | Como é feito | Por quê |
|---|---|---|
| Escopos | `openid email profile` | só nome e e-mail |
| Proteções do OAuth | `state` (contra falsificação de pedido), `nonce` (contra reapresentação de token) e **PKCE** | padrão atual do OAuth para aplicações web |
| Validação do token | assinatura pelas chaves públicas do Google, emissor, **audiência = o app do FOPA**, validade, `nonce` e e-mail verificado | sem conferir a audiência, um token emitido para outro aplicativo seria aceito |
| Primeiro acesso | cadastro automático como **usuário** (menor acesso) | qualquer conta Google entra para ver; agir exige papel ([[Papéis e acesso]]) |
| Bloqueio | usuário bloqueado recebe 403 "Acesso não liberado" | o supremo controla quem entra |
| Sessão | cookie assinado + linha em `sessoes`; o banco guarda só o **hash** do id | sair, expirar e bloquear derrubam a sessão de verdade; um dump do banco não vira sessão válida |
| Cookie | `HttpOnly` (o JavaScript não lê), `SameSite=Lax` (um POST vindo de outro site não leva o cookie — proteção contra CSRF), `Secure` em produção | segurança de navegador |
| Duração | 12 horas | um dia de trabalho |
| Sair | `POST /auth/sair` apaga a sessão no banco e o cookie | logout real |

## O aplicativo no Google

O cliente OAuth está publicado ("Em produção") no projeto do Google Cloud do FOPA, com a página de [[Página Privacidade|política de privacidade]] pública — requisito do Google para um app aberto a qualquer conta.

## Relacionadas

[[MOC Site]] · [[Papéis e acesso]] · [[Página Privacidade]] · [[API do site — endpoints]] · [[Privacidade e LGPD]] · [[Controle de acesso e segredos]]
