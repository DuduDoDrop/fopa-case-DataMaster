---
tipo: componente
familia: infra
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docker/backup.py
  - docker/backup_fora.py
  - docker/ponto.py
  - docs/DEPLOY.md
tags: [infra, backup, restauracao, schedule]
---

# Backup e restauração

> [!abstract] Em uma frase
> Todo dia às **03:15** os dois bancos (negócio e n8n) e o export dos fluxos e das credenciais **cifradas** do n8n são copiados, com manifesto de hashes; às **03:35** cada backup bom sobe para o **S3** com uma credencial que **não apaga**; e todo **domingo às 03:45** o backup mais recente é **restaurado de verdade** num Postgres temporário e as contagens são comparadas.

## Papel na solução

O banco guarda o que não se recupera do PNCP: as decisões humanas, as extrações pagas, as verificações, os usuários. O backup protege contra erro, perda da máquina e invasão — e só vale se a restauração for provada, não suposta.

## O que é copiado (`docker/backup.py`)

Numa pasta datada `backups/AAAA-MM-DD_HHMMSS/`:

| Arquivo | Conteúdo |
|---|---|
| `fopa.dump` | o banco de negócio (`pg_dump` em formato próprio) |
| `n8n.dump` | o banco do n8n: fluxos, execuções, credenciais cifradas |
| `globais.sql` | os papéis do cluster, **sem senha** |
| `n8n/workflows/*.json` | o export dos fluxos |
| `n8n/credenciais/*.json` | o export das credenciais, **cifradas** com a chave do n8n — o script confere arquivo a arquivo e **aborta** se alguma sair em texto aberto |
| `manifesto.json` | tamanho e SHA-256 de cada arquivo, contagens antes e depois do dump, versões e duração de cada passo |

- A pasta nasce como `.parcial-…` e só ganha o nome final quando tudo deu certo: a retenção (as **7** mais recentes) nunca conta um backup quebrado.
- **A chave de cifragem do n8n não vai no backup** (é segredo, guardado à parte); o manifesto guarda só os 12 primeiros caracteres do hash dela, para conferir a chave certa na restauração sem revelá-la.
- O script usa só a biblioteca padrão e `docker exec` (o Postgres não tem porta publicada), e só toca os containers do projeto `fopa`.

## Fora da máquina (`docker/backup_fora.py`)

Às 03:35, todo backup completo que ainda não está no bucket sobe para `s3://fopa-editais-1/backups/<carimbo>/`:

- com a credencial da aplicação, que **não tem permissão de apagar** — um erro, um script ou um invasor na máquina conseguem gravar lá, mas não apagar;
- arquivo a arquivo, direto do disco (sem carregar centenas de MB na memória de uma máquina de 2 GB), com o S3 conferindo a integridade pelo mesmo SHA-256 do manifesto;
- o `manifesto.json` sobe **por último**: no bucket, pasta com manifesto é cópia completa;
- na classe de acesso infrequente; uma regra de ciclo de vida apaga as cópias com mais de **30 dias** (cerca de 30 cópias, ~20 GB).

## A prova de restauração

Todo domingo às 03:45, `backup.py --verificar` restaura o backup mais recente num **Postgres efêmero** e compara as contagens com o manifesto — sem folga, exceto nas execuções do n8n, que o próprio n8n poda enquanto o dump roda: a contagem restaurada pode sair do intervalo antes/depois pelas execuções criadas durante o backup, e a folga é de 50. A restauração de prova de 28/09/2026 levou **147 segundos**, com as contagens iguais às do manifesto.

## Restaurar de verdade

1. Parar n8n, worker e API; subir só o Postgres (num volume novo, se for trocar tudo).
2. Restaurar, nesta ordem: os papéis globais, o banco `fopa`, o banco `n8n`; depois rodar a migração.
3. Subir tudo e, se quiser, provar o backup num efêmero.
4. A chave de cifragem do n8n no `.env` tem de ser a do backup — conferida pelo prefixo do hash no manifesto.
5. **Máquina perdida inteira:** máquina nova, backup trazido do S3, a restauração acima, os fluxos importados e o DNS apontado para o IP novo.

PDFs perdidos voltam do PNCP (o download confere o hash) e relatórios podem ser gerados de novo — por isso o bucket não entra no backup diário do banco.

## Ponto de restauração

Antes de trocar de versão, um **ponto** reúne o backup verificado, as imagens em execução, o commit, a tag, o crontab e os comandos exatos para voltar; o novo só apaga o anterior depois de verificado, e uma cópia fica fora da AWS ([[Deploy e atualização]]).

## Relacionadas

[[MOC Infra]] · [[Horários e agendamentos]] · [[Deploy e atualização]] · [[Armazenamento de arquivos (S3)]] · [[Segurança do servidor]] · [[Controle de acesso e segredos]]
