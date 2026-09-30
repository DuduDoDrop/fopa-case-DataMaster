---
tipo: componente
familia: infra
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docs/DEPLOY.md
  - docker/compose.prod.yml
tags: [infra, aws, hospedagem, lgpd]
---

# Hospedagem na AWS

> [!abstract] Em uma frase
> A produção roda numa **EC2 t3.small (2 vCPU, 2 GB de memória, 4 GB de swap) com Ubuntu 24.04 em São Paulo (sa-east-1)**, com IP fixo, e guarda documentos, relatórios e cópias de backup num **bucket S3 privado na mesma região** — banco e editais ficam no Brasil.

## Papel na solução

É onde o produto está no ar, em **https://licitacaofopa.com.br**. A escolha foi dimensionada para o uso de hoje (poucos acessos, extração paga por pedido) e para crescer sem migração: trocar o tipo da instância mantém o disco e o IP ([[ADR-022 Produção na AWS, em São Paulo, numa máquina pequena]]).

## O que existe na AWS

| Recurso | Configuração | Por quê |
|---|---|---|
| **EC2** | t3.small, sa-east-1, Ubuntu 24.04, IP elástico, 4 GB de swap | apresentação e uso inicial; cabe no crédito da conta; região no Brasil |
| **S3** | bucket `fopa-editais-1`, privado, sa-east-1, sem versionamento | PDFs, relatórios e cópias dos backups no Brasil |
| **IAM** | um usuário de aplicação que só **lista, lê e grava** no bucket — **não apaga** | um erro, um script ou um invasor na máquina não conseguem apagar documentos nem backups |
| **Ciclo de vida** | regra que expira o prefixo `backups/` em 30 dias | cerca de 30 cópias diárias, sem acumular para sempre |

## A máquina

- **Acesso:** SSH aberto só por chave, sem login de root, com limite de tentativas, fail2ban, firewall liberando só 22, 80 e 443 e atualizações automáticas de segurança ([[Segurança do servidor]]).
- **O que roda:** a composição Docker descrita em [[Containers e serviços]], com o `docker/.env` de produção (segredos gerados na própria máquina).
- **Código:** um repositório Git na própria máquina, atualizado por *push*; a imagem chega pronta, construída fora ([[Deploy e atualização]]).
- **Agenda do sistema operacional:** os backups (03:15, 03:35 e domingo 03:45); a agenda dos fluxos é do n8n ([[Horários e agendamentos]]).
- **Um job de OCR ou conversão por vez:** com 2 GB de memória, o worker processa um documento pesado de cada vez; a fila da manhã e o histórico da madrugada foram encaixados em horários que não disputam essa vaga.

## Serviços externos

| Serviço | Para quê | Onde a credencial fica |
|---|---|---|
| Registro.br | domínio `licitacaofopa.com.br` e o DNS | painel do registrador |
| Let's Encrypt | certificados HTTPS, emitidos e renovados pelo Caddy | automático |
| Google Cloud (OAuth) | o login do site | `docker/.env` da produção |
| Anthropic e OpenAI | a extração | credenciais do n8n |
| TypeSafe (Jev) | o segundo sinal | credencial do n8n |
| Resend | o envio dos e-mails | credencial do n8n |
| PNCP | a fonte dos dados | pública, sem credencial |

## O que isso significa para dados pessoais

Os editais trazem nome e salário de servidores; a política da solução é guardar o **agregado** (a pirâmide), e o documento original fica num bucket privado **no Brasil**, sem acesso público — o PDF só abre para quem está logado, por URL assinada de 10 minutos ([[Privacidade e LGPD]], [[Armazenamento de arquivos (S3)]]).

## Relacionadas

[[MOC Infra]] · [[Containers e serviços]] · [[Domínio, DNS e HTTPS]] · [[Segurança do servidor]] · [[Custo de infraestrutura]] · [[Escalabilidade]] · [[ADR-022 Produção na AWS, em São Paulo, numa máquina pequena]]
