---
tipo: moc
familia: infra
status: verificado
atualizado: 2026-09-28
tags: [moc, infra]
---

# MOC Infra

> [!abstract] Em uma frase
> Onde e como a solução roda: uma instância em São Paulo com Docker Compose, HTTPS automático, documentos num bucket privado no Brasil, implantação por imagem construída do commit, backup diário provado por restauração, dois e-mails pelo Resend e saúde conferida de hora em hora.

## Papel na solução

A infraestrutura é pequena de propósito e segura por desenho: uma porta de entrada (o Caddy), segredos que não saem da máquina, a chave do modelo só no orquestrador, dados no Brasil e um caminho de volta para cada mudança.

## As notas

| Nota | O que responde |
|---|---|
| [[Hospedagem na AWS]] | a instância, o bucket, o usuário de acesso, os serviços externos |
| [[Containers e serviços]] | os sete serviços, a imagem do worker, os healthchecks, desenvolvimento × produção |
| [[Domínio, DNS e HTTPS]] | os endereços, o DNS, o Caddy, o que é público no n8n |
| [[Deploy e atualização]] | os passos de uma atualização, a janela sensível, como voltar |
| [[Backup e restauração]] | o backup diário, a cópia fora da máquina, a prova de restauração |
| [[Segurança do servidor]] | rede, acesso, segredos, contenção do n8n |
| [[E-mails do produto]] | os dois e-mails, o envio e as novas tentativas |
| [[Saúde e observabilidade]] | está de pé, é o que foi medido, o que aconteceu |
| [[Custo de infraestrutura]] | a parte fixa, a parte variável e o gasto real |

## A agenda do sistema

| Horário (São Paulo) | O quê |
|---|---|
| 03:15 | backup dos bancos |
| 03:35 | cópia do backup para o S3 |
| domingo 03:45 | restauração de prova |
| 04:30 | histórico e contratos do PNCP |
| domingo 05:00 | retificações |
| 06:00 (seg–sex) | descoberta |
| 06:00–07:50, a cada 10 min | fila |
| 07:00 | alerta diário |
| de hora em hora | saúde |
| a cada minuto | envio de e-mails |

Detalhe em [[Horários e agendamentos]].

## Relacionadas

[[Home]] · [[Arquitetura]] · [[MOC Fluxos n8n]] · [[MOC Segurança e Ética]] · [[Escalabilidade]] · [[Como acessar a versão no ar]]
