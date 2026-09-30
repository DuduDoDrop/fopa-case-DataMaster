# n8n da FOPA: credenciais, segredos locais e MCP

Instância: `fopa-n8n` (n8nio/n8n:2.37.10), editor em <http://127.0.0.1:5679>. A instância
`localhost:5678` é de outra stack n8n e **não** é esta.

Nenhum valor secreto aparece neste arquivo nem em `n8n/workflows/*.json`. Os fluxos
referenciam credenciais por **nome** (`{{CRED:nome}}`) e o `n8n/importar.py` troca o nome
pelo id da instância. Por isso trocar uma senha no `docker/.env` pede só
`python n8n/bootstrap.py`: a credencial é reescrita no mesmo id, sem reimportar fluxo.

## Subir do zero

```bash
cd docker && docker compose up -d fopa-n8n      # espera /healthz/readiness
cd .. && python n8n/bootstrap.py                # owner, chave da API, credenciais, token MCP
python n8n/importar.py                          # fluxos, das folhas para a raiz, e publica
python -m pytest n8n/tests -v                   # prova na instância real
```

As duas execuções do `bootstrap.py` e do `importar.py` são idempotentes: a segunda não cria
nada (`existente` / `inalterado`).

## Credenciais (criadas pelo `n8n/bootstrap.py`)

| Nome no n8n | Tipo | De onde vem o valor (`docker/.env`) | Usada por |
|---|---|---|---|
| `fopa-postgres (n8n_rw)` | Postgres | host `fopa-postgres:5432`, banco `fopa`, usuário `n8n_rw`, senha `N8N_RW_PASSWORD` | W00, W50, W90 (todo nó Postgres) |
| `worker` | Header Auth | `Authorization: Bearer ` + `FOPA_WORKER_TOKEN` | chamadas autenticadas ao worker (W21-W24, W30) |
| `site` | Header Auth | `X-FOPA-Token: ` + `FOPA_SITE_TOKEN` | webhooks do W11 e `POST /api/interno/invalidar` |
| `smtp` | SMTP | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | W50 (canal principal de e-mail) |
| `jev` | Header Auth | `Authorization: Bearer ` + `JEV_API_KEY` (só se houver) | W01 (score do filtro de escopo) e W24/W30 (score "sustenta?") — sinal, nunca decisão |
| `anthropicApi` / `openAiApi` | (F4: W23) | criadas à mão na UI, **nunca** em env de container | W23, só com `provedor` = `claude`/`openai` |
| `gmail` (opcional) | Gmail OAuth2 | Google Cloud, consent screen "In production" | W50, segundo canal (não configurado) |

O W00 não usa credencial para o `/health`: a rota é pública dentro da rede do compose.

### SMTP: Resend, domínio `licitacaofopa.com.br` (26/09/2026)

Histórico: até 24/09 o `SMTP_HOST` estava vazio; em 26/09 de manhã ligou-se o Gmail com senha
de app; na tarde de 26/09 trocou-se pelo **Resend** (remetente próprio, SPF/DKIM/DMARC do
domínio, log de cada envio no painel). As linhas do Gmail ficaram em
`n8n/.segredos/smtp-gmail.env` (gitignorado) para voltar se preciso.

| `docker/.env` | valor |
|---|---|
| `SMTP_HOST` / `SMTP_PORT` | `smtp.resend.com` / `587` (STARTTLS) |
| `SMTP_USER` | `resend` (literal) |
| `SMTP_PASSWORD` | chave de API do Resend `fopa-n8n-smtp`, permissão *Sending access*, restrita ao domínio `licitacaofopa.com.br` (27/09) |
| `SMTP_FROM` | `FOPA <avisos@licitacaofopa.com.br>` |

No Resend: domínio na região São Paulo (`sa-east-1`), **TLS Enforced**, rastreamento de
abertura e clique desligado (reescreveria os links do e-mail da extração). Plano grátis:
3.000/mês, **100/dia**.

DNS no Registro.br (zona em modo avançado):

| tipo | nome | valor | papel |
|---|---|---|---|
| TXT | `resend._domainkey` | chave pública do Resend (`p=MIGf…`) | DKIM |
| CNAME | `send` | `send.forge.rmta.net` | Return-Path / SPF |
| CNAME | `rsend` | `rsend-sae1.forge.rmta.net` | envio pela região sa-east-1 |
| TXT | `_dmarc` | `v=DMARC1; p=quarantine; adkim=r; aspf=r; pct=100` | DMARC, quarentena desde 27/09 |
| TXT | `@` (nome vazio) | `v=spf1 -all` | a raiz não envia e-mail |
| ~~MX~~ | ~~`@`~~ | ~~`0 .` (null MX)~~ | **o Registro.br não aceita** (ver abaixo) |

O `v=spf1 -all` e o null MX vinham da zona padrão do Registro.br: ao passar para o modo avançado
a zona começa vazia, e o save de 26/09 que sobrescreveu a zona (duas sessões no editor) levou os
registros do Resend junto. Estado conferido no servidor autoritativo (`nslookup … f.sec.dns.br`)
em 27/09: os do Resend voltaram (domínio verificado; envios com SPF/DKIM/DMARC `pass`), o SPF
da raiz voltou (serial `2026270001`) e o DMARC passou de `p=none` para `p=quarantine`
(`2026270002`). **O null MX não entra**: o formulário do Registro.br aceita MX com prioridade `0`
e servidor `.`, mas o save não publica — a linha some do editor e o serial não muda (27/09,
mais de 6 min; os outros saves publicaram em 1-2 min). Foi isso, e não o formulário aberto, que
fez o save de 6 entradas de 26/09 não gravar. Sem MX nenhum, quem mandar e-mail para
`@licitacaofopa.com.br` cai no registro A (o servidor, sem porta 25): falha do mesmo jeito, só
mais devagar. A proteção contra se passar pelo domínio é o SPF `-all` + DMARC `quarantine`.
Nada disso atrapalha o Resend, que usa o subdomínio `send` no envelope e assina com DKIM
alinhado. Sem `rua=` no DMARC: relatório para o Gmail seria
descartado (falta a autorização de destino externo).

Editar a zona (modo avançado): **uma entrada por save**; recarregar a página antes (o editor grava
a zona INTEIRA que carregou); raiz = campo Nome vazio (`@` e `*` são recusados); trocar um
registro = marcar o antigo para remoção e adicionar o novo no mesmo save; fechar o formulário
"Nova entrada" (o X dele, não o Cancelar de baixo) antes de "Salvar alterações"; **nunca MX
`0 .` no mesmo save** (derruba o save inteiro, em silêncio). O painel não mostra confirmação: a
prova é o serial subir no autoritativo (publica em ~1-2 min). Depois de um save a página do
domínio pode ficar em branco por minutos — esperar ~40 s ou voltar mais tarde.

Sem `SMTP_HOST`, o `bootstrap.py` **não** cria a credencial `smtp` e o `importar.py` publica o
W50 com o id sentinela `ausente:smtp`. A 2.37.10 recusa publicar nó com credencial de id vazio,
mas não confere se o id existe. Em execução o nó falha e cada e-mail da fila vira
`status='falhou'`, `canal='smtp'`, com este erro:

> SMTP não configurado: credencial 'smtp' ausente no n8n (SMTP_HOST vazio no docker/.env); o Send Email falhou antes de enviar.

Para ligar ou trocar o SMTP:

1. Preencha os `SMTP_*` no `docker/.env` (tabela acima).
2. `cd docker && docker compose up -d fopa-n8n`: recria o container com `FOPA_EMAIL_FROM` e
   `FOPA_SMTP_CONFIGURADO=sim`.
3. `python n8n/bootstrap.py` cria a credencial `smtp`.
4. `python n8n/importar.py` troca o sentinela pelo id real e republica o W50.
5. E-mails que já ficaram `falhou` não voltam sozinhos: para reenviar, volte-os a `pendente`
   (o W50 respeita `tentativas < 5`).

A porta 465 vira TLS direto (`secure=true`); qualquer outra usa STARTTLS.

### Gmail OAuth2 (opcional, não configurado)

Com o consent screen em "Testing", o refresh token morre em 7 dias (plano, seção 5, W50). Se for
configurado, use "In production" e registre aqui a data de autorização:

- Data da autorização: _não configurado_
- Callback: `{FOPA_N8N_PUBLIC_URL}rest/oauth2-credential/callback`

## Segredos locais (`n8n/.segredos/`, gitignorado)

| Arquivo | O que é | Se sumir |
|---|---|---|
| `owner.json` | e-mail e senha do owner (`admin@exemplo.com`) | o owner continua no banco `n8n`; troque a senha pela UI e regrave o arquivo, ou recrie o volume `fopa_n8n_data` |
| `api_key` | chave da API pública (rótulo `fopa-scripts`, todos os escopos) | o `bootstrap.py` apaga a chave antiga e cria outra |
| `cookie` | sessão da REST interna | refeita no próximo login. O `POST /rest/login` tem limite de taxa (HTTP 429), por isso o cookie é reaproveitado |
| `credenciais.sha256.json` | sha256 do que o bootstrap gravou em cada credencial | a próxima execução reescreve as credenciais uma vez (a 2.37.10 devolve o segredo redigido, então só a impressão permite comparar) |
| `mcp_token` | token do servidor MCP do owner | o `bootstrap.py` busca de novo |

## Variáveis que o n8n lê do ambiente (compose, bloco `fopa-n8n`)

Nada disto é segredo. Os segredos ficam nas credenciais.

| Variável | Uso |
|---|---|
| `FOPA_WORKER_URL`, `FOPA_SITE_URL` | URLs internas (`$env`, plano seção 4) |
| `FOPA_TESSERACT_ESPERADO`, `FOPA_TESSDATA_SHA256` | contrato que o W00 confere; mesmos valores do build do worker |
| `FOPA_EMAIL_FROM` | remetente do W50 (`SMTP_FROM`) |
| `FOPA_SMTP_CONFIGURADO` | `sim` quando há `SMTP_HOST`; o W50 usa para explicar a falha |
| `N8N_MCP_MANAGED_BY_ENV`, `N8N_MCP_ACCESS_ENABLED` | liga o servidor MCP por env (a UI fica travada) |

Os ajustes de execução (provedor, modelo, lote, `k_rag`, `max_tokens`) **não** ficam numa Data
Table do n8n. Ficam na tabela `configuracao` do Postgres (migração 016, `provedor=simulado`),
editada pelo site e lida por um nó Postgres. Nenhuma Data Table é necessária hoje.

## Servidor MCP da instância

- Ligado por env no compose (`N8N_MCP_MANAGED_BY_ENV=true`, `N8N_MCP_ACCESS_ENABLED=true`).
- Endpoint: `http://127.0.0.1:5679/mcp-server/http` (streamable HTTP, `Authorization: Bearer <token>`).
- Fluxos expostos: só os que têm `settings.availableInMCP = true` no JSON versionado. Hoje é
  só o **W00 Saúde**, que tem gatilho Manual/Schedule, suportados pelo MCP da 2.37.10.
- O token é do owner e dá acesso de owner. Ele fica **só** em `n8n/.segredos/mcp_token`.

### Configurar um cliente (Claude Code)

Use escopo `local` ou `user` (grava em `~/.claude.json`, fora do repositório). **Nunca** use
`--scope project`: isso grava o token no `.mcp.json`, que é versionado.

```bash
claude mcp add --transport http --scope local fopa-n8n \
  http://127.0.0.1:5679/mcp-server/http \
  --header "Authorization: Bearer $(cat n8n/.segredos/mcp_token)"
```

Conferido em 24/09/2026: `initialize` responde 200, `tools/list` traz `search_workflows`,
`execute_workflow`, `get_workflow_execution` e outras, e `search_workflows` lista o W00 com
`availableInMCP: true`. Para girar o token, use a UI (Settings → MCP → rotate) ou
`POST /rest/mcp/api-key/rotate`, e depois rode `python n8n/bootstrap.py`.

## Versionamento dos fluxos

- Fonte: `n8n/workflows/W00.json`, `W50.json`, `W90.json`. Sem id da instância: o Error Workflow
  aparece como `{{WF:W90}}` e as credenciais como `{{CRED:nome}}`.
- `python n8n/importar.py`: upsert por nome, na ordem das folhas para a raiz, e publica. O que
  já está igual fica `inalterado`, sem versão nova.
- `python n8n/exportar.py`: faz o caminho inverso depois de uma edição no canvas. Ids viram
  placeholders e o sentinela `ausente:smtp` volta a `{{CRED:smtp}}`.
- `python n8n/executar.py W00`: roda um fluxo pelo gatilho Manual (a API pública não executa).
  Execução manual não dispara o W90.
- Error Workflow = W90 **só nas raízes** (W00, W50, e depois W01, W10, W11, W20, W30, W40, W70).
