---
tipo: decisao
familia: decisoes
adr: 16
data: 2026-09-25
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, email, produto]
---

# ADR-016 — O produto manda só dois e-mails

> [!abstract] Em uma frase
> A solução envia **dois e-mails e nenhum outro**: o aviso de **licitação nova** que passou no filtro (para os administradores) e o resultado da **extração pedida** pelo botão "Extrair com IA" (para quem clicou); todos os outros sinais — erros, orçamento, texto escondido, coleta cega — ficam no site, e o banco recusa qualquer outro tipo.

## Problema

Na primeira montagem, cada fluxo enfileirava o próprio aviso: erro de saúde, coleta cega, disjuntor, "carregada" a cada download, texto escondido, orçamento, "processada" a cada extração de qualquer origem, resumo da reverificação, alerta diário, erro de fluxo. Em 25/09/2026 a fila tinha **2.698 mensagens** — 1.614 "carregada" de um único download em massa — e nenhuma tinha saído, porque o envio ainda não estava configurado. Ligado naquele dia, o envio teria despejado 2.698 e-mails numa caixa.

## Opções

| Opção | Avaliação |
|---|---|
| um e-mail por evento | ruído que ensina a ignorar o e-mail |
| um resumo diário | atraso justamente no que é urgente (licitação nova) |
| **só os dois e-mails que pedem ação; o resto no site** | adotado |

## Escolha

| E-mail | Quem enfileira | Quando | Para quem |
|---|---|---|---|
| `licitacao_nova` | [[W01 Descoberta]] | a rodada insere uma licitação nova que passa no filtro (escopo e janela); nunca na rodada seca | os administradores ativos |
| `extracao` | [[W24 Verificar e publicar]] | a execução nasceu de um pedido do botão "Extrair com IA" | quem clicou |

- A tabela `emails` aceita **só** esses dois tipos (restrição no banco, `db/039`): um fluxo que tentasse outro aviso falharia na hora, em vez de encher a fila em silêncio.
- Os outros fluxos continuam fazendo o trabalho deles; os sinais estão no site: coleta cega e erros em [[Página Execuções]] e [[Página Saúde]], orçamento no [[Página Admin|Admin]], texto escondido no [[Página Detalhe da licitação|detalhe]].
- A importação em lote e a fila automática das 06:00 não mandam e-mail de extração: só o clique de uma pessoa gera esse e-mail.
- O alerta diário das 07:00 ([[W40 Alerta diário]]) registra os números na execução, sem e-mail.

## Em produção

- **Envio:** o [[W50 Envio de e-mails]] roda a cada minuto, pelo SMTP do Resend com o remetente `avisos@licitacaofopa.com.br` (domínio próprio, com registros de autenticação no DNS); tenta de novo em 2, 5, 15 e 40 minutos e marca `falhou` na 5ª; só marca enviado com a confirmação do servidor de e-mail ([[E-mails do produto]]).
- **Caso real (28/09/2026):** Itapecuru Mirim/MA gerou o `licitacao_nova` às 06:04 e o `extracao` às 10:25 ("[FOPA] Processada: Itapecuru Mirim/MA · 9/16 ancoradas · R$ 0,78"), com a tabela das 17 respostas, os vereditos, o custo e o link para cada página citada.

## O que custa

Quem quiser acompanhar erro e orçamento precisa abrir o site — deliberadamente.

## O que reabriria a decisão

Um terceiro evento que exija ação imediata de uma pessoa e que o site não resolva.

## Relacionadas

[[MOC Decisões]] · [[E-mails do produto]] · [[W50 Envio de e-mails]] · [[W01 Descoberta]] · [[W24 Verificar e publicar]] · [[Página E-mails]]
