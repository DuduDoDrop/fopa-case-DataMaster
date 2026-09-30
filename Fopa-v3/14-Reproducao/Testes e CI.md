---
tipo: referencia
familia: reproducao
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - ci/rodar.py
  - ci/sem_chave.py
  - .github/workflows/ci.yml
  - Makefile
  - ci/tests
  - db/tests
  - migracao/tests
  - api/tests
  - docker/tests
  - n8n/tests
  - tests/ocr_baseline
  - scripts/23_testa_escopo.py
tags: [reproducao, testes, ci, qualidade]
---

# Testes e CI

> [!abstract] Em uma frase
> Um executor único (`python ci/rodar.py`) roda, numa **cópia limpa** do repositório e **sem nenhuma chave de modelo**, as guardas de texto, os testes do banco, da migração, do worker e da API, dos containers, do site e do filtro de escopo — com um Postgres efêmero em porta sorteada —; o GitHub Actions roda essa mesma camada a cada *push*, e uma segunda camada, opcional, confere a instância do n8n e o banco da infraestrutura local.

## Papel na solução

É a prova de que a solução se reproduz fora da máquina em que foi construída e de que as garantias centrais — a verificação não usa IA, a chave do modelo existe num só lugar, o ensaio nunca vira dado oficial — **são testadas**, não dependem de disciplina.

## As suítes

| Suíte | O que prova | Camada | Funções de teste* |
|---|---|---|---|
| `ci/tests` — guardas de texto | o endereço da API da Anthropic só aparece no ramo `claude` do Switch do W23, nunca no worker nem no site; nenhum arquivo versionado tem cara de segredo nem carrega o valor de um segredo local; nenhum `SyntaxWarning` no Python do projeto. Cada guarda tem um teste que prova que ela sabe falhar | a | 15 |
| `ci/tests` — guardas da infraestrutura | nos containers que estão rodando (`fopa-worker`, `fopa-api`, `fopa-n8n`), nenhuma chave de modelo no ambiente; o `/health` do worker diz que a chave não está presente | b | 3 |
| `db/tests` | as migrações num Postgres efêmero: funções, gatilhos, máquina de estados, filas, imutabilidade, invariantes, o hash das migrações | a | 72 |
| `migracao/tests` | as regras de importação do acervo da versão anterior | a | 63 |
| `api/tests` | worker e API do site: rotas, papéis, login e sessão, prompt, reforço do Best-of-N, verificação, injeção, Jev (inclusive a guarda de que ele nunca escreve veredito), custo, armazenamento, conversão; e a **fumaça** — os invariantes do verificador sem rede — com o número real de asserções | a | 474 |
| `docker/tests` | sem subir nada, o que o `docker compose config` resolve: projeto `fopa`, portas só no *loopback*, em produção só o Caddy com porta pública e só o webhook do n8n aberto, nenhum serviço com chave de modelo, migração só no seu *profile*, Dockerfile com versão **e sha256** de tudo que baixa, `.env.exemplo` com todas as variáveis e nenhum valor; e a cópia dos backups para o S3 contra um S3 falso local, com a assinatura idêntica à do armazenamento do app; e a regra que confere as contagens do backup restaurado | a | 31 |
| `web` (Vitest) | componentes e páginas do site: cartões, filtros, detalhe, revisão, governança, a guarda de textos, custo "n/d" em vez de R$ 0,00 — seguidos do *build* de produção | a | 275 |
| `scripts/23_testa_escopo.py` | o filtro de escopo contra os 23 casos julgados à mão do catálogo versionado | a | — |
| `n8n/tests` | a instância real do n8n e o banco local, sem *mock*: *bootstrap* idempotente, importação sem duplicar, exportar e importar ida e volta, W00 gravando a saúde, W50 sem SMTP com espera crescente (2, 5, 15 e 40 min) e falha definitiva só na 5ª tentativa, W20 → W24 ponta a ponta com provedor simulado sobre uma licitação de ensaio, rajada de 8 W20 sem nunca passar de 4 em extração | b | 89 |
| `tests/ocr_baseline` | a linha de base do OCR: 6 páginas digitalizadas e o texto de referência do Tesseract 5.4.0, com sha256 de cada arquivo; roda à parte, na máquina que tem o Tesseract | à parte | 9 |

\* funções `test_` no código, sem contar parametrizações.

## O executor (`ci/rodar.py`)

**Camada (a) — sem acervo, sem infraestrutura, sem rede paga** (é o que o GitHub Actions roda):

1. monta uma **cópia** do repositório como a imagem do worker a enxerga (`.dockerignore`): código, testes, `amostras/_fixture` e o catálogo de escopo — sem documentos reais, sem saídas locais e **sem nenhum `.env`**;
2. roda as guardas de texto na árvore real (elas precisam do `git ls-files`) e as demais suítes na cópia, com o **Postgres efêmero** (`postgres:16-alpine`) subindo em container com **porta sorteada** em 127.0.0.1 — nunca a porta do banco local;
3. roda o site com `npm ci`, Vitest e *build* — o mesmo portão do estágio `web` da imagem —, com o Node 22 da máquina ou, sem ele, num container `node:22-alpine`;
4. **tira do ambiente** de todo processo filho as variáveis de chave (`ANTHROPIC_*`, `OPENAI_*`, `JEV_API_KEY`); os scripts rodam por `ci/sem_chave.py`, que impede um `.env` de devolver a chave e reprova se ela aparecer. A suíte inteira roda com a chave ausente, e nenhum segredo é impresso.

**Camada (b) — opcional, detectada:** a instância local do n8n (se responder), os **invariantes** de `db/invariantes.sql` no banco local com o papel só de leitura `api_ro`, as guardas dos containers e, na máquina de desenvolvimento, a fumaça e o filtro de escopo sobre o acervo local. O acervo de desenvolvimento não faz parte do repositório: numa máquina nova, esses passos saem como **pulados**, com o motivo.

**Regras:** sai 0 só se tudo que **rodou** passou; o que foi pulado sai listado com o motivo e **nunca conta como passou** — um passo com todos os testes pulados é "pulado".

**O OCR fora do container.** Os testes de leitura precisam do Tesseract 5.4.0 com o modelo de português em `tessdata/por.traineddata` (o `setup.ps1` baixa; a imagem do worker traz compilado e conferido por SHA-256). Sem o modelo, o executor desmarca os seis testes que fazem OCR de verdade, cada um com o motivo, e o resto da suíte roda. Até 28/09/2026, quatro deles — OCR forçado, texto escondido, camada de texto cortada e página de cabeça para baixo — estavam fora dessa lista e falhavam em vez de pular; a lista foi completada no executor.

**Resultado num clone limpo (28/09/2026):** com o modelo de português presente, a camada (a) aprovou os **8 passos**, com **1.131 testes** e nenhuma falha; os 9 pulados dizem por quê (LibreOffice, `bsdtar` e grupo de processos só existem na imagem Linux do worker; o acervo anterior não faz parte do repositório; não há `.env` local para a guarda de valores).

## No GitHub Actions (`.github/workflows/ci.yml`)

A cada *push*, *pull request* ou disparo manual, num `ubuntu-24.04` com limite de 40 minutos e permissão só de leitura: Python 3.12 e Node 22, as mesmas dependências da imagem (`requirements.txt`, `api/requirements.txt`, `db/requirements.txt`), o `docker pull` do `postgres:16-alpine` e `python ci/rodar.py --camada a`. **Nenhum segredo** no arquivo.

O runner não tem Tesseract — e o do Ubuntu seria a 5.3, que muda veredito ([[ADR-008 OCR — stack, configuração e limites]]). Por isso, lá, os testes de OCR saem desmarcados, com o motivo, e os oito passos passam. O portão do OCR em produção é o **build da imagem**, que confere a versão e o idioma e não gera imagem se algo diverge.

## Outros portões de qualidade

- **O build da imagem** roda os testes do site e confere o Tesseract; se algo falha, não há imagem ([[Containers e serviços]]).
- **O verificador determinístico** é, ele mesmo, um portão em produção ([[Verificador determinístico]]).
- **A reverificação a custo zero** mede o efeito de cada mudança de regra no acervo inteiro antes de ela valer ([[W30 Reverificar em lote]]).
- **Os invariantes** — uma consulta em que zero linhas significa banco íntegro — conferem que nenhuma licitação publicada está sem verificação vigente, que toda resposta aprovada aponta para uma página que existe, que nenhuma chamada paga tem custo zero, que todo arquivo baixado tem objeto no armazenamento e que nenhuma execução simulada virou vigente fora de ensaio ([[Modelo de dados]]).

## Como rodar

```bash
python ci/rodar.py              # camada (a) e, se houver infraestrutura local, a (b)
python ci/rodar.py --camada a   # só a (a), como no GitHub
make ci                         # o mesmo que o primeiro
```

## Relacionadas

[[MOC Reprodução]] · [[Como rodar em outra máquina]] · [[Controles de consistência]] · [[Harness de avaliação]] · [[Containers e serviços]] · [[OCR]] · [[Injeção de prompt e defesas]]
