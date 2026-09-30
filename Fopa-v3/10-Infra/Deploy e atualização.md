---
tipo: componente
familia: infra
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - docs/DEPLOY.md
  - docker/worker.Dockerfile
  - docker/backup.py
  - docker/ponto.py
  - n8n/importar.py
  - db/migrar.py
tags: [infra, deploy, atualizacao, rollback]
---

# Deploy e atualização

> [!abstract] Em uma frase
> Uma versão nova chega à produção em passos fixos — **código por Git, imagem construída fora a partir do commit e enviada pronta, backup, troca da tag, migração, subida da API e do worker, importação dos fluxos do n8n e conferência** —, e voltar é trocar a tag de volta (ou restaurar o ponto criado antes).

## Papel na solução

Garante que o que roda é **exatamente** o que está versionado (a imagem nasce do commit, e o `/health` diz qual), que toda mudança de banco tem um ponto de volta, e que atualizar não perde trabalho em andamento.

## Os passos de uma atualização

| # | Passo | Por quê |
|---|---|---|
| 1 | **código:** `git push` para o repositório da própria máquina | o servidor não precisa de chave para o GitHub |
| 2 | **imagem:** construída **fora** da máquina a partir do commit (`git archive HEAD \| docker build`, com o SHA completo como argumento) e enviada comprimida por SSH (`docker save \| gzip \| ssh … docker load`) | a t3.small levaria muito para compilar o Tesseract; o binário não usa instruções específicas da CPU de quem compilou |
| 3 | **backup** (`docker/backup.py`) | é o ponto de volta antes de migrar |
| 4 | **troca da tag** da imagem no `docker/.env` (`FOPA_IMAGEM_TAG` = SHA curto de 12) | anotar a tag anterior é o que permite voltar |
| 5 | **migração** (`docker compose --profile migrate run --rm fopa-migrate`) | as migrações só avançam ([[Migrações do banco]]) |
| 6 | **conferir que não há job vivo** e subir `fopa-worker` e `fopa-api` | reiniciar o worker mata o job que estiver rodando |
| 7 | **fluxos do n8n** (`python3 n8n/importar.py`) | os 15 fluxos daquele commit |
| 8 | **conferência:** `/api/saude`, o bundle do site, o histórico do fluxo novo e o SHA da imagem | a versão no ar é a pretendida |

- **Só o site:** mudança apenas da API ou do front sobe com `docker compose up -d --no-deps fopa-api`, sem tocar no worker.
- **A janela sensível:** com uma vaga de job, **não se reinicia o worker das 06:00 às 07:50** (a fila roda a cada 10 minutos) **nem perto das 04:30** (o histórico ocupa a vaga por cerca de 20 minutos). Na versão em produção, o worker declara órfão, ao iniciar, todo job que estava ativo — reiniciar não deixa mais job preso, mas ainda mata o que estava rodando ([[Worker — visão geral e jobs]]).
- **Ponto de restauração:** antes de trocar de versão, `docker/ponto.py criar <rótulo>` guarda numa pasta só o backup verificado dos bancos, as imagens em execução, o commit, a tag, o crontab e os comandos exatos para voltar; o novo ponto só apaga o anterior depois de verificado, e uma cópia vai para fora da AWS.

## Voltar de versão

1. `git checkout` do commit anterior;
2. a tag anterior de volta no `docker/.env`;
3. subir `fopa-worker` e `fopa-api`;
4. importar os fluxos da versão anterior.

Se a versão nova aplicou uma migração que o código anterior não entende (o `/api/saude` responde 503 com o nome do objeto), a volta inclui o banco: restaurar o backup do passo 3 — e o que entrou depois dele se perde. As três últimas imagens ficam guardadas.

## A versão que está no ar

A v3.1 está no ar desde **28/09/2026 às 07:58**. Desde **30/09/2026 às 05:38**, `fopa-api` e `fopa-worker` rodam a imagem do commit `ab55f75` (a aba Escopo da Revisão só com as pendentes e a coleta do PNCP que nunca desfaz uma coleta boa), com as mesmas versões de regras, prompt e escopo da v3.1; o `/health` do worker informa o SHA completo, a versão das regras (`b32b66ede7f6…`), a do prompt (`f224a746b51a…`) e a do escopo ([[Página Saúde]]).

## Relacionadas

[[MOC Infra]] · [[Containers e serviços]] · [[Backup e restauração]] · [[Migrações do banco]] · [[Testes e CI]] · [[Horários e agendamentos]] · [[Linha do tempo da construção]]
