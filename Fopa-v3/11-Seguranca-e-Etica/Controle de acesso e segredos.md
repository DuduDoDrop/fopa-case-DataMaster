---
tipo: referencia
familia: seguranca-e-etica
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/site.py
  - api/auth.py
  - api/sessao.py
  - api/oauth.py
  - db/011_papeis.sql
  - db/016_configuracao_e_papel_do_site.sql
  - docker/compose.yml
  - docker/compose.prod.yml
  - docs/n8n-credenciais.md
  - ci/tests/test_guardas_texto.py
tags: [seguranca, acesso, segredos, autenticacao]
---

# Controle de acesso e segredos

> [!abstract] Em uma frase
> Cada peça só pode o que precisa: pessoas entram pelo **Google** com papéis (usuário, admin, supremo); serviços falam entre si com **tokens** próprios (o n8n com o worker, o site com os webhooks do n8n); cada serviço entra no banco com um **papel** que só grava o que é dele; e os segredos — sobretudo a **chave do modelo** — vivem num lugar só, cifrados, fora de imagem, repositório e backup.

## Papel na solução

A solução mexe com dinheiro (extração paga), com decisões de negócio (revisões, rótulos) e com documentos que trazem dados pessoais. O controle de acesso garante que ver é amplo, agir é restrito e cada ação fica registrada com quem a fez.

## Pessoas

| Camada | Como |
|---|---|
| autenticação | Google OAuth 2.0 com OpenID Connect, `state`, `nonce` e PKCE; token validado (assinatura, emissor, audiência, validade, e-mail verificado) — [[Login com Google]] |
| sessão | cookie assinado de 12 horas, `HttpOnly`, `SameSite=Lax`, `Secure`; o banco guarda só o **hash** do identificador; sair, expirar e bloquear derrubam a sessão |
| autorização | papéis `leitor` (usuário), `operador`, `admin` e a marca `supremo`; cada rota declara o papel mínimo — sem sessão, 401; sem papel, 403 — [[Papéis e acesso]] |
| registro | revisões e rótulos gravam quem decidiu e quando; pedidos de extração gravam quem pediu |

## Serviços

| De → para | Autenticação |
|---|---|
| n8n → worker | `Authorization: Bearer` com o token do worker (credencial `worker` do n8n); em produção, por HTTPS dentro da rede interna; só o `/health` dispensa token |
| site → n8n (webhooks do W11) | cabeçalho `X-FOPA-Token` com o token do site, conferido pelo próprio fluxo (credencial `site`) |
| n8n → site (aviso de publicação) | o mesmo token do site em `POST /api/interno/invalidar` |
| n8n → Postgres | papel `n8n_rw` (credencial Postgres) |
| n8n → provedores de modelo, Jev, SMTP | credenciais do n8n (`anthropicApi`, `openai`, `jev`, `smtp`) |
| site → S3 | usuário de aplicação que lista, lê e grava — não apaga |

No banco, cada serviço tem seu papel: o site (`api_rw`) grava **só decisões humanas**; tabelas imutáveis só aceitam inserção ([[Modelo de dados]]).

## Segredos

| Segredo | Onde vive | Onde **não** vive |
|---|---|---|
| **chaves das APIs de modelo** | **só** nas credenciais do n8n, cifradas com a chave do n8n | em nenhum container, variável de ambiente, imagem, repositório ou log |
| chave de cifragem do n8n | `.env` da produção e cofre | backup (o manifesto guarda só um prefixo do hash para conferência) |
| senhas dos papéis do banco | `.env`, aplicadas pela migração | SQL, repositório, backup (os papéis vão sem senha) |
| tokens do worker e do site, segredo da sessão | `.env` da produção | repositório |
| credenciais do Google e do S3 | `.env` da produção | repositório |
| senha do acesso ao editor do n8n | só o hash bcrypt no `.env` | em claro em qualquer arquivo |

- Os segredos de produção foram **gerados na própria máquina** e escritos direto no `.env`, sem passar pela tela.
- Cada container recebe só as variáveis que usa, **por nome**.
- **Guardas automáticas:** um teste do CI garante que o endereço da API da Anthropic só aparece no ramo de extração do W23 e nunca no worker ou no site; em produção, o `/health` informa `anthropic_key_presente: false`, conferido de hora em hora pelo [[W00 Saúde]]; e a contagem da variável da chave no ambiente dos containers é zero.
- O repositório tem um `.env.exemplo` com os **nomes** das variáveis e nenhum valor.

## Relacionadas

[[MOC Segurança e Ética]] · [[Papéis e acesso]] · [[Login com Google]] · [[Segurança do servidor]] · [[Modelo de dados]] · [[Endpoints do worker]] · [[API do site — endpoints]] · [[ADR-021 Quem vê o quê — usuário, operador, admin e admin supremo]]
