---
tipo: pagina
familia: site
rota: "/saude"
papel_minimo: admin
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Saude.tsx
  - api/site.py
  - api/worker.py
tags: [site, pagina, saude, observabilidade]
---

# Página Saúde

> [!abstract] Em uma frase
> O painel de saúde do sistema, atualizado a cada 30 segundos: se a API, o worker (com o OCR na versão certa), o Postgres e o n8n estão de pé, quando foi a última coleta, qual foi o último alerta e o **contrato completo** do worker — o código que está rodando, a versão do OCR e de suas regras, o armazenamento e a prova de que o worker não tem a chave do modelo.

## Papel na solução

Responde, numa olhada, **"o sistema está bem e é o que foi medido?"** ([[Saúde e observabilidade]]).

![[site-saude.jpg]]

## O que mostra (em produção, 29/09/2026)

### Quadros
| Quadro | Valor |
|---|---|
| Site (API) | ok |
| Leitura e extração (worker) | ok · tesseract 5.4.0 |
| Banco de dados (Postgres) | ok |
| Processamento (n8n) | ok · HTTP 200 |
| Última coleta | 28/09/2026 17:53 |
| Último alerta | 27/09/2026 06:30 — a última falha registrada (fluxo e mensagem) |

Se algo cai, a página diz **quem** caiu e o que isso muda para quem opera; o n8n fora aparece como **aviso** (o site continua lendo do banco; só as ações ficam indisponíveis).

### "Detalhes da leitura e extração (worker)"
O `/health` do worker, campo a campo:

| Campo | Valor em produção | Significado |
|---|---|---|
| `ok` | true | configuração válida e OCR no contrato |
| `git_sha` | `ab55f759efccde3a8310bfc8a76377a6c8a58eed` | o commit do código em produção |
| `tesseract` | 5.4.0 | a versão do OCR das medições |
| `tessdata_sha256` | `c4932b93…` | o arquivo de treino do português é o pinado no build |
| `idiomas` | `["por"]` | OCR em português |
| `storage` | S3 `fopa-editais-1`, `sa-east-1`, ok | onde ficam os documentos |
| `anthropic_key_presente` | **false** | o worker não tem a chave do modelo |
| `versao_regras` | `b32b66ede7f6…` | o hash das regras do verificador vigentes |
| `versao_prompt` | `f224a746b51a…` | o hash do prompt que o modelo vê |
| `escopo_versao` | `5700476d5b8c…` | o hash da regra de escopo |

## De onde vêm os dados

`GET /api/saude` — consulta o `/health` do worker, o Postgres (com a última coleta e o último alerta) e o n8n. Sem sessão, em produção, a rota responde só `ok`/`caiu`/`avisos` (é o que o *healthcheck* do Docker consulta); o detalhe é para quem entrou. Responde **503** quando o Postgres ou o worker caem.

## Quem vê

Só administradores.

## Relacionadas

[[MOC Site]] · [[Saúde e observabilidade]] · [[W00 Saúde]] · [[OCR]] · [[Controle de acesso e segredos]] · [[Containers e serviços]]
