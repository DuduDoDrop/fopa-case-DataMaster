---
tipo: pagina
familia: site
rota: "/privacidade"
papel_minimo: publico
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - api/site.py
tags: [site, pagina, lgpd, privacidade]
---

# Página Privacidade

> [!abstract] Em uma frase
> A política de privacidade pública do site: o que é coletado no login (só nome e e-mail), para que é usado (identificar a pessoa e os dois e-mails do produto), onde fica (AWS em São Paulo), por quanto tempo e como exercer os direitos da LGPD.

## Papel na solução

É a transparência exigida pela LGPD e pelo Google para um aplicativo de login aberto. Os editais e os dados de compras são públicos; a página trata **só** dos dados de quem entra no site ([[Privacidade e LGPD]]).

![[site-privacidade.jpg]]

> [!note] No print, o e-mail de contato aparece como "[e-mail oculto]".

## O que diz

| Tema | Conteúdo |
|---|---|
| O que coletamos | no login com Google, apenas **nome e e-mail** (escopos `openid`, `email` e `profile`); a sessão de login (cookie de 12 horas) e o registro das ações feitas no site |
| Para que usamos | identificar a pessoa e decidir o que ela pode ver e fazer; enviar e-mail aos administradores quando surge licitação nova; enviar, a quem pediu uma extração, o resultado dela |
| O que não fazemos | não enviar outros e-mails, não vender nem compartilhar dados, não usar dados da conta Google para treinar modelos de IA ou para publicidade; os e-mails saem por um provedor contratado só para isso |
| Onde e por quanto tempo | servidores em São Paulo (AWS `sa-east-1`); o cadastro fica enquanto o acesso existir; o administrador pode removê-lo, e a remoção apaga cadastro e sessões |
| Direitos | acesso, correção e exclusão pelo e-mail de contato indicado na página |

## Como é servida

`GET /privacidade` — pública (sem login), servida pela API do site.

## Relacionadas

[[MOC Site]] · [[Login com Google]] · [[Privacidade e LGPD]] · [[E-mails do produto]]
