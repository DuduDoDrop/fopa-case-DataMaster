---
tipo: referencia
familia: infra
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docs/DEPLOY.md
  - docker/backup_fora.py
  - api/consultas.py
tags: [infra, custo, finops]
---

# Custo de infraestrutura

> [!abstract] Em uma frase
> O custo da solução tem duas partes com naturezas diferentes: a **infraestrutura fixa** (uma instância pequena, armazenamento, domínio, e-mail) e o **uso de IA**, pago por extração e limitado por um teto diário; a infraestrutura de produção roda sobre o crédito inicial da conta AWS, e o gasto de IA é lido da fatura dos fornecedores.

## Papel na solução

Custo previsível é requisito de produto num banco. A arquitetura foi escolhida para que a parte fixa seja pequena e a parte variável tenha **teto** e **medição na fatura** — nunca estimativa sem fonte.

## A parte fixa

| Item | O que é | Como é cobrado |
|---|---|---|
| **EC2 t3.small** (sa-east-1) | a máquina que roda tudo | por hora; CPU acima da linha de base, no modo ilimitado, é cobrada à parte — centavos para o uso atual |
| **S3** (`fopa-editais-1`) | PDFs, relatórios e as cópias de backup | por GB armazenado e por requisição; as cópias de backup ficam na classe de acesso infrequente (estimativa registrada no código: cerca de US$ 0,02 por GB-mês em sa-east-1, com ~640 MB por dia e expiração em 30 dias — cerca de 20 GB guardados) |
| **Domínio** `licitacaofopa.com.br` | registro anual no Registro.br | anual |
| **E-mail** (Resend) | envio dos dois e-mails | plano gratuito — até 3.000 por mês e 100 por dia, acima do volume atual |
| **Certificados** | Let's Encrypt | sem custo |

A conta AWS da produção tem **US$ 100 de crédito inicial, válido até 26/03/2027**; a instância e o armazenamento correm sobre ele. O destino da máquina depois disso é uma decisão registrada ([[ADR-022 Produção na AWS, em São Paulo, numa máquina pequena]]).

## A parte variável: IA

| Item | Como é controlado |
|---|---|
| **extração** (Claude ou GPT) | só por pedido explícito enquanto o provedor configurado for `simulado`; **teto de R$ 25,00 por dia**, com reserva de R$ 6,56 por extração; até 4 simultâneas; custo por chamada calculado na hora ([[Custo por edital]]) |
| **Jev** (segundo sinal) | até 300 chamadas por rodada da descoberta; ~US$ 0,01 por licitação no "sustenta?"; preço de US$ 0,042 por milhão de tokens de entrada |

**Gasto real, pela fatura, desde 21/09/2026: US$ 47,82 ≈ R$ 243,89** (Claude US$ 24,06; Jev US$ 17,85; GPT US$ 5,91) — a organização inteira, incluindo construção e medições.

## O que custa zero em modelo

Coleta, download, conversão, OCR, regra de escopo, verificação, reverificação do acervo inteiro, relatório, e-mail e saúde — tudo determinístico e local ([[MOC IA]]).

## Relacionadas

[[MOC Infra]] · [[Custo por edital]] · [[Hospedagem na AWS]] · [[Escalabilidade]] · [[Backup e restauração]] · [[Página Admin]]
