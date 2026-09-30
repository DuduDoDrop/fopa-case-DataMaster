---
tipo: decisao
familia: decisoes
adr: 22
data: 2026-09-26
decisao: aceita
status: verificado
atualizado: 2026-09-29
tags: [decisao, infra, aws, deploy, lgpd]
---

# ADR-022 — Produção na AWS, em São Paulo, numa máquina pequena

> [!abstract] Em uma frase
> A solução roda numa **EC2 t3.small em São Paulo (sa-east-1)**, com os documentos num **bucket S3 privado na mesma região** — banco e editais ficam no Brasil —, domínio **licitacaofopa.com.br** com HTTPS automático, acesso por SSH blindado, imagem construída fora e enviada pronta, e backup diário dentro e fora da máquina.

## Problema

O roteiro de implantação deixava abertas as escolhas de provedor, tamanho de máquina, armazenamento, residência dos dados, domínio, proxy e migração de dados. O guia sugeria 4 vCPU e 8 GB; o uso previsto era baixo (uma apresentação, poucos acessos) e o orçamento, o crédito inicial da conta.

## Opções e escolhas

| Decisão | Escolha | Por quê |
|---|---|---|
| máquina | **EC2 t3.small** (2 vCPU, 2 GB), Ubuntu 24.04, IP elástico, 4 GB de swap, **um job de OCR ou conversão por vez** (`FOPA_JOBS_CONCORRENCIA=1`) | uso baixo; cabe no crédito; crescer é trocar o tipo da instância, com o mesmo disco e o mesmo IP ([[Escalabilidade]]) |
| armazenamento e LGPD | **S3 `fopa-editais-1`**, privado, na **mesma região**; um usuário de acesso só com listar, ler e gravar — **sem apagar** | o banco **e** os editais (que trazem nome e salário de servidor) ficam no Brasil ([[Privacidade e LGPD]]) |
| domínio | **licitacaofopa.com.br**, DNS no Registro.br: o domínio e `n8n.` apontam para o IP | os dois hosts que a composição de produção pede |
| proxy de borda | **nenhum** (sem Cloudflare) | o Caddy faz o TLS, e nada no meio corta chamadas longas |
| dados | levar o estado da montagem (banco + PDFs) | revisões, rótulos, usuários e execuções só existiam ali |
| acesso à máquina | SSH aberto só por chave, sem root, com fail2ban, firewall em 22/80/443 e atualizações automáticas de segurança | quem administra muda de IP; restringir por IP exigiria refazer a regra a cada troca |

## Como o código e a imagem chegam

- **O servidor não fala com o repositório de código:** o código vai por `git push` para um repositório na própria máquina (atualizado no lugar), sem chave de implantação.
- **A imagem é construída fora e enviada pronta** (`git archive` → `docker build` → `docker save | gzip | ssh … docker load`): a t3.small levaria muito para compilar o Tesseract. A tag da imagem é o SHA curto do commit, e o SHA completo vai para dentro da imagem (aparece no `/health`).
- **Segredos de produção são novos**, gerados na hora e escritos no `.env` da máquina, nunca passados pela tela.
- **O login Google tem cliente OAuth próprio de produção**, com a tela de consentimento **publicada** (28/09/2026): qualquer conta Google entra como usuário, com os escopos `openid email profile` ([[Login com Google]]).

## Estado em produção (28/09/2026)

| Item | Estado |
|---|---|
| Versão | v3.1 no ar desde 28/09/2026 07:58, com `fopa-api` e `fopa-worker` na imagem do commit `d978355` ([[Página Saúde]]); a versão em execução, sempre atualizada, está em [[Deploy e atualização#A versão que está no ar]] |
| OCR na máquina | medido antes de ligar a leitura: a EC2 reproduz a imagem de referência página por página ([[ADR-008 OCR — stack, configuração e limites]]) |
| Backup | agendado: 03:15 cópia dos bancos (retenção de 7); 03:35 cópia de cada backup bom para o S3 (classe de acesso infrequente, credencial que não apaga, conferência por SHA-256); domingo 03:45 restauração de prova num Postgres efêmero; no S3, os backups expiram em 30 dias. Restauração de prova em 28/09: 147 s, contagens iguais ao manifesto ([[Backup e restauração]]) |
| Ponto de restauração | antes de cada versão, um ponto com banco verificado e imagens, mais um roteiro de volta ([[Deploy e atualização]]) |
| Esteira | a fila das 06:00 às 07:50 baixa e lê com o provedor `simulado` (sem custo); a extração paga acontece por pedido no botão ([[Modelos e provedores]]) |

## O que custa

- Um OCR ou conversão por vez: uma licitação grande e escaneada demora mais do que numa máquina maior.
- **Janela sensível:** com uma vaga de job, reiniciar o worker entre 06:00 e 07:50 (a fila) ou perto das 04:30 (o histórico) perde o job em andamento; atualização só da API ou do site não reinicia o worker ([[Deploy e atualização]]).
- A instância pode cobrar CPU acima da linha de base, do crédito — centavos para uma máquina de apresentação.
- O crédito da conta tem data para acabar (26/03/2027); decidir antes o destino da máquina.

## O que reabriria a decisão

Uso real com volume — mais licitações por dia, extração automática ligada, muitos usuários simultâneos: a primeira alavanca é trocar o tipo da instância e subir a concorrência de jobs ([[Escalabilidade]]).

## Relacionadas

[[MOC Decisões]] · [[Hospedagem na AWS]] · [[Containers e serviços]] · [[Domínio, DNS e HTTPS]] · [[Deploy e atualização]] · [[Backup e restauração]] · [[Segurança do servidor]] · [[Custo de infraestrutura]] · [[Privacidade e LGPD]]
