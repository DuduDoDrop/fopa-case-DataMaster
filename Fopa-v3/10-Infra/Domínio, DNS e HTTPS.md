---
tipo: componente
familia: infra
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docker/Caddyfile.exemplo
  - docker/compose.prod.yml
  - docs/DEPLOY.md
tags: [infra, dns, https, tls, caddy, seguranca]
---

# Domínio, DNS e HTTPS

> [!abstract] Em uma frase
> O site responde em **https://licitacaofopa.com.br** e o n8n em **n8n.licitacaofopa.com.br**, com o DNS no Registro.br e certificados do **Let's Encrypt emitidos e renovados automaticamente pelo Caddy**; no host do n8n, **só os webhooks são públicos** — o editor e todo o resto pedem senha antes do próprio login do n8n —, e o tráfego do n8n para o worker também é HTTPS, dentro da rede interna.

## Papel na solução

É a porta de entrada: tudo o que chega de fora passa pelo Caddy, com TLS, e só o que precisa ser público é público. Os endereços públicos (o retorno do login Google, a URL dos webhooks, os links dos e-mails) são **derivados** dos dois domínios, para não divergirem do certificado emitido.

## Os endereços

| Host | Destino | O que é público |
|---|---|---|
| `licitacaofopa.com.br` | `fopa-api:8080` | tudo: o site React, a API (que exige sessão nas rotas de dados), o login e a política de privacidade |
| `n8n.licitacaofopa.com.br` | `fopa-n8n:5678` | **só `/webhook/*`** — os webhooks que o site chama, autenticados pelo próprio fluxo (token do site); editor, API interna, webhooks de teste e o servidor MCP pedem **basic auth** antes do login do n8n |
| `fopa-worker-tls:8443` | `fopa-worker:8000` | **nada**: existe só dentro da rede da composição; certificado próprio, em que o n8n confia; o worker confere o token em cada chamada |

## DNS (Registro.br, modo avançado)

- Registros `A` do domínio e de `n8n.` apontando para o IP fixo da instância.
- Os registros de autenticação do remetente de e-mail (`avisos@licitacaofopa.com.br`, via Resend) ficam na mesma zona ([[E-mails do produto]]).
- **Sem proxy de borda** (sem Cloudflare): o Caddy faz o TLS, e nada no meio corta requisições longas.

> [!aviso] Uma lição de operação
> O editor de zona do registrador grava a zona **que a página carregou**: duas edições simultâneas fazem uma apagar a outra. Recarregar antes de salvar, uma alteração por vez.

## HTTPS com o Caddy

- **Certificados automáticos:** o Let's Encrypt valida pela porta 80 (desafio HTTP-01), e o Caddy renova sozinho; as contas e certificados ficam num volume próprio (apagá-lo força reemissão, e o Let's Encrypt limita emissões por semana).
- **Cabeçalhos:** `Strict-Transport-Security` de um ano nos dois hosts; compressão zstd e gzip; HTTP/3.
- **Atrás do proxy:** o n8n confia em um salto de `X-Forwarded-For` (`N8N_PROXY_HOPS=1`) e a API aceita os cabeçalhos encaminhados só do Caddy (ela não tem porta pública).
- **Cookies:** o cookie de sessão do site é `Secure` e `HttpOnly` em produção; o do n8n, `Secure` ([[Login com Google]]).
- **O retorno do login** é `https://licitacaofopa.com.br/auth/google/callback`, a mesma string cadastrada no Google.

## Relacionadas

[[MOC Infra]] · [[Containers e serviços]] · [[Hospedagem na AWS]] · [[Segurança do servidor]] · [[Login com Google]] · [[W11 Ações do site]] · [[Controle de acesso e segredos]]
