---
tipo: pagina
familia: site
rota: "/emails"
papel_minimo: admin
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Emails.tsx
  - api/consultas.py
  - db/008_emails_usuarios_sessoes_jobs_saude.sql
tags: [site, pagina, email, operacao]
---

# Página E-mails

> [!abstract] Em uma frase
> A fila de e-mails do produto como ela é: cada e-mail com a hora, o tipo, a licitação, o destinatário, o assunto, o **corpo exatamente como saiu** e o status (pendente, enviado, falhou) com o canal e o erro.

## Papel na solução

Permite conferir o que o sistema mandou e para quem, sem abrir a caixa de correio de ninguém — e ver na hora se o canal de e-mail está falhando ([[E-mails do produto]]).

![[site-emails.jpg]]

> [!note] No print, os endereços da coluna "Para" aparecem como "[e-mail oculto]", para não expor endereços pessoais.

## O que mostra

| Coluna | O que é |
|---|---|
| Quando | quando o e-mail entrou na fila |
| Tipo | `licitacao_nova` ou `extracao`, com o link da licitação |
| Para | o destinatário (os administradores, ou quem pediu a extração) |
| Assunto | como foi enviado; "ver o corpo enviado" mostra o HTML |
| Status | `pendente`, `enviado · smtp` ou `falhou`, com tentativas e erro |

## Exemplos reais (28/09/2026)

No print, do mais recente para o mais antigo:
- **17:42, 17:51 e 18:11** — três `extracao` de Bertioga/SP ("16/16 ancoradas"; R$ 0,09, R$ 0,03 e R$ 0,11): as extrações com o GPT-6 Luna da [[Comparação de modelos]].
- **17:19** — `extracao`: "[FOPA] Processada: Itapecuru Mirim/MA · 16/16 ancoradas · R$ 0,20", a segunda extração, com o GPT-6 Luna.
- **10:25** — `extracao`: "[FOPA] Processada: Itapecuru Mirim/MA · 9/16 ancoradas · R$ 0,78", a primeira, com o Claude Haiku 4.5, para quem clicou em "Extrair com IA".
- **06:04** — cinco e-mails `licitacao_nova` da descoberta das 06:00: três dispensas de Brasília/DF, Muzambinho/MG e Itapecuru Mirim/MA.
- **02:08** — `extracao` de Rubiataba/GO ("5/10 ancoradas", R$ 1,03).

Antes disso, outras extrações pedidas pelo botão (Santa Cruz da Baixa Verde/PE, Esperança/PB, Muriaé/MG, Brasília/DF), com o custo no assunto — "R$ n/d" quando o preço do modelo não era conhecido.

## De onde vêm os dados

`GET /api/emails` — tabela `emails`, preenchida pelos fluxos e atualizada pelo [[W50 Envio de e-mails]].

## Quem vê

Só administradores.

## Relacionadas

[[MOC Site]] · [[E-mails do produto]] · [[W50 Envio de e-mails]] · [[W01 Descoberta]] · [[W24 Verificar e publicar]] · [[ADR-016 O produto manda só dois e-mails]]
