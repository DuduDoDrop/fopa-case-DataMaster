---
tipo: referencia
familia: fluxos-n8n
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - n8n/workflows/*.json
  - n8n/importar.py
  - n8n/bootstrap.py
  - docs/n8n-credenciais.md
  - docker/compose.yml
tags: [n8n, convencoes, resiliencia, seguranca]
---

# Convenções dos fluxos n8n

> [!abstract] Em uma frase
> As regras que **todos** os 15 workflows seguem — como tratam erro, como guardam estado, como falam com o worker e com o PNCP, onde ficam os segredos e como são versionados e publicados — para que o comportamento de um fluxo seja previsível lendo qualquer outro.

## Papel na solução

O n8n é o **orquestrador**: agenda, encadeia e registra. Ele não guarda regra de negócio pesada — a regra mora no **Postgres** (funções testadas) e no **worker** (Python testado). O canvas fica legível e cada decisão tem um único dono. Ver [[Stack e justificativa tecnológica]] para o porquê do n8n.

## As convenções

### 1. O banco é a fonte da verdade
- Toda mudança de estado de uma licitação passa por `fn_transicao`, que valida contra a tabela `transicoes` e grava o evento em `licitacao_eventos` — a linha do tempo que o site mostra ([[Ciclo de vida de uma licitação]]).
- Toda rodada de fluxo deixa **uma linha em `execucoes_workflow`** (status, duração, contadores, custo, erro) — é a [[Página Execuções]].
- Regras de fila, lease, backoff, disjuntor, orçamento e escopo são **funções SQL** (`fn_reivindicar`, `fn_tomar_vaga_extracao`, `fn_registrar_vista`…); o fluxo só as chama ([[Funções e views do banco]]).

### 2. Erro nunca é silêncio
- **HTTP com "nunca erro" + saída de erro ligada:** o status HTTP e as falhas de rede (DNS, recusa, tempo esgotado) viram **dado** no fluxo, com o motivo escrito — nunca exceção muda.
- **"Nada visto" ≠ "nada a fazer":** uma coleta que não conseguiu olhar é marcada `cega`; uma licitação que o PNCP não respondeu é "não conferida", nunca "sem novidade".
- **Workflow de erro só nas raízes:** o [[W90 Erro]] é o *Error Workflow* dos fluxos raiz; os sub-fluxos W21–W24 devolvem `{ok: false, motivo}` e o [[W20 Processar uma licitação]] decide.
- **Estado não recua por acidente:** uma falha depois de verificar deixa a licitação `verificada`; a próxima rodada completa.

### 3. Retentativas com critério
| Onde | Regra |
|---|---|
| PNCP (busca, arquivos, itens) | 429/5xx: espera 30 s e **uma** nova tentativa; queda de conexão na descoberta: até 5 tentativas (1, 2, 4, 8 s) |
| Modelo (W23) | só 408/429/500/502/503/529 e rede; até 3 tentativas; `retry-after` ou 30 s; recusa e truncamento **não** se repetem |
| Licitação (W10/W20) | backoff de 15 min → 2 h → 12 h; na 4ª falha seguida, `erro_definitivo` |
| E-mail (W50) | 2, 5, 15, 40 min; `falhou` na 5ª |

### 4. Trabalho pesado é job assíncrono no worker
- Baixar, ler (OCR) e recoletar o histórico levam de segundos a dezenas de minutos. O fluxo faz `POST /jobs/<tipo>` (202 com `job_id`) e consulta `GET /jobs/{id}` em intervalos fixos até `done` ou `error` — sem segurar conexão HTTP longa ([[Worker — visão geral e jobs]]).
- Limites de espera por tipo: baixar 60 × 15 s; ler 160 × 15 s; histórico 150 × 30 s.
- Uma volta sem resposta (worker reiniciando) não mata o laço.
- **O arquivo nunca passa pelo n8n.**

### 5. Reserva com prazo (lease)
- Quem processa uma licitação a reserva (`lease_por`, `lease_ate`, 2 horas). Nenhum outro fluxo a pega enquanto a reserva vale; reserva vencida é devolvida pelo [[W10 Fila]].

### 6. Segredos só em credenciais do n8n
| Credencial | Tipo | Usada por |
|---|---|---|
| `fopa-postgres (n8n_rw)` | Postgres (usuário `n8n_rw`, permissões mínimas) | todo nó Postgres |
| `worker` | cabeçalho `Authorization: Bearer <FOPA_WORKER_TOKEN>` | chamadas ao worker |
| `site` | cabeçalho `X-FOPA-Token` | webhooks do W11 e aviso ao site |
| `smtp` | SMTP | W50 |
| `anthropic` | API da Anthropic | W23 |
| `openai` | cabeçalho `Authorization` | W23 |
| `jev` | cabeçalho `Authorization` | W01, W22, W24 |

- Os JSON dos workflows **não contêm segredo**: referenciam credenciais por marcadores (`{{CRED:worker}}`) que o importador resolve pelo id da instância.
- A chave do modelo **só existe na credencial do n8n**; o worker nunca a recebe, e o [[W00 Saúde]] confere isso de hora em hora ([[Controle de acesso e segredos]]).

### 7. Configuração fora do fluxo
- Endereços (`FOPA_WORKER_URL`, `FOPA_SITE_URL`, `FOPA_SITE_PUBLIC_URL`, `WEBHOOK_URL`) vêm de variáveis de ambiente do container.
- Parâmetros de negócio (provedor, modelo, lote, `k_rag`, teto de saída, máximo de extrações, Best-of-N, ano mínimo, limite do W70) vêm da tabela `configuracao`, editável no [[Página Admin|Admin]] — mudar não exige republicar fluxo.

### 8. Versionamento e publicação
- Cada workflow é um arquivo em `n8n/workflows/Wnn.json`, versionado no Git junto do código.
- `python n8n/bootstrap.py` cria o dono da instância, a chave da API e as credenciais; `python n8n/importar.py` importa os fluxos e resolve os marcadores (`{{WF:W20}}`, `{{CRED:…}}`); `--publicar W00 …` publica só os listados.
- `n8n/exportar.py` traz de volta ao Git o que foi editado no editor.
- Os testes de `n8n/tests/` rodam os fluxos contra uma instância e um banco reais ([[Testes e CI]]).

### 9. Execução e segurança do n8n
- `executionOrder: v1` em todos: o primeiro ramo de um nó vai até o fim antes do segundo começar (é o que permite a um "resumo" ler o que o ramo principal fez).
- `NODES_EXCLUDE` retira os nós que executam comando no servidor e que leem arquivo local — nenhum fluxo pode rodar comando ou ler disco do host.
- Em produção, o editor do n8n fica atrás de autenticação no Caddy; só o caminho `/webhook/*` é público ([[Domínio, DNS e HTTPS]]).

## Notas de passo no canvas

Cada nó de execução tem, logo abaixo, uma nota adesiva verde com **"Passo N · nome do nó"** e, em uma ou duas frases, o que o passo faz. O número é o mesmo do passo na nota do fluxo neste vault: a tela do n8n e a documentação falam a mesma língua. As notas de passo não contam como nó nas contagens do vault (368 nós = os de execução mais as notas de seção); no JSON, cada uma se chama `Nota — passo N`. Elas são só documentação: nenhuma participa das conexões, e a guarda de texto do CI as trata como nota.

## Relacionadas

[[MOC Fluxos n8n]] · [[Horários e agendamentos]] · [[W90 Erro]] · [[Worker — visão geral e jobs]] · [[Funções e views do banco]] · [[Controle de acesso e segredos]] · [[Containers e serviços]] · [[Stack e justificativa tecnológica]]
