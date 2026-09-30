---
tipo: pagina
familia: site
rota: "/admin"
papel_minimo: admin
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Admin.tsx
  - api/site.py
  - api/demo_reservar.py
  - db/016_configuracao_e_papel_do_site.sql
tags: [site, pagina, admin, operacao, configuracao]
---

# Página Admin

> [!abstract] Em uma frase
> O painel de operação: verificar agora se há licitações novas, mandar licitações para processamento, importar respostas prontas, ajustar a configuração da extração, o orçamento e os termos de busca, gerir usuários e reservar licitações para demonstração — com toda mudança registrada com quem mudou e quando.

## Papel na solução

Tudo o que muda o comportamento do sistema **sem mexer em código** passa por aqui. Os parâmetros ficam no banco (tabela `configuracao`, `orcamento`, `termos`), e os fluxos os leem a cada rodada ([[Convenções dos fluxos n8n]]).

![[site-admin.jpg]]

## As seções

### 1. Verificar licitações novas
- Botão **Verificar agora**: consulta o PNCP e aplica o filtro de folha **sem gravar** (≈ 2 minutos, R$ 0,00) — o [[W11 Ações do site]] chama o [[W01 Descoberta]] em modo seco.
- Mostra a **última rodada** (lida do servidor), com o número da execução, os contadores (novas, conhecidas, retificadas, fora do escopo, fora do recorte, custo) e a lista das novas (até 50, com lugar, objeto, prazo e link do PNCP).
- No print, a rodada de 28/09 às 17:53 (execução 5107, n8n nº 17067): 4 novas, 566 conhecidas, 3 retificadas, 1 fora do escopo, 0 fora do recorte, custo R$ 0,00 — e o aviso de que nada foi gravado.
- Lembra a agenda: "De segunda a sexta, às 6h, o FOPA verifica automaticamente e registra as novas licitações no painel"; o "Verificar agora" apenas consulta, sem registrar.

### 2. Processar selecionadas
- Uma caixa para colar **até 20 controles** (ou os endereços do site), a opção **forçar** (refaz do download também as publicadas, fora do escopo ou em erro definitivo) e o botão **Processar** — manda o lote ao [[W11 Ações do site]] → [[W10 Fila]] → [[W20 Processar uma licitação]].

### 3. Importar respostas do agente
- Controle, o **JSON com as 17 respostas** e o modelo do agente (opcional). As respostas passam pelo **mesmo verificador** da API: numa licitação `preparada` são publicadas; numa já publicada, viram uma extração nova e a página é republicada com o que mudou. Nenhuma chamada paga ([[ADR-014 Extração por agente, sem API]]).

### 4. Configuração
Uma tabela com **chave, valor, o que é e quem alterou quando**. Em produção (28/09/2026):

| Chave | Valor | O que é |
|---|---|---|
| `provedor` | `simulado` | quem responde na esteira automática: `simulado`, `gravado`, `claude` ou `openai` ([[Modelos e provedores]]) |
| `modelo` | `claude-opus-5-5` | o modelo do extrator no Claude ([[ADR-020 Esforço fixo e Claude Opus 5.5 no extrator]]) |
| `modelo_openai` | `gpt-5.6-sol` | o modelo no provedor alternativo ([[ADR-012 Segundo provedor de modelo]]) |
| `effort` | `medium` | esforço de raciocínio |
| `lote` | 6 | perguntas por chamada (3 chamadas por edital) |
| `k_rag` | 12 | páginas por pergunta no modo RAG ([[RAG com BM25]]) |
| `max_tokens` | 16000 | teto de saída por chamada |
| `max_extracoes` | 4 | extrações simultâneas |
| `melhor_de_n` | 3 | Best-of-N: tentativas por pergunta que falha (1 = desligado) ([[Best-of-N]]) |
| `ano_minimo` | 2026 | recorte de ano ([[ADR-015 Acervo só de 2026 e só compra de folha]]) |

> [!info] O que "provedor = simulado" significa em produção
> A esteira automática das 06:00 **baixa e lê** tudo o que é novo (custo zero) e deixa a licitação `preparada`; a extração paga acontece **por pedido**, no botão "Extrair com IA" do detalhe. É uma escolha de operação: gasto só com decisão humana.

### 5. Orçamento
- **Teto por dia** (R$; vazio = nenhum): **R$ 25,00** em produção. A extração só começa se o gasto do dia + R$ 6,56 por extração em curso couber no teto ([[W23 Extrair]]).
- **Máximo por execução** da fila (vazio = só o limite de 4 simultâneas).
- **Processar automaticamente o que o W01 achar** (ligado em produção).

### 6. Termos de busca
Os termos que o [[W01 Descoberta]] usa no PNCP, cada um ativável: em produção, os seis de fábrica, todos ativos — "cessão onerosa folha de pagamento", "folha de pagamento servidores instituição financeira", "folha de pagamento instituição bancária", "créditos da folha de pagamento", "créditos provenientes da folha de pagamento", "folha salarial instituição financeira".

### 7. Usuários
A lista de quem já entrou, com papel e situação. **Só o administrador supremo** muda papel, bloqueia, desbloqueia ou remove ([[Papéis e acesso]]).

### 8. Reservar para a demo
Marca licitações abertas como reservadas e empurra o fim do prazo para daqui a N dias (1 a 60) — nenhum processo automático as toca, e a demonstração ao vivo tem casos garantidos.

## De onde vêm os dados

| Seção | Rotas da API |
|---|---|
| Verificar agora | `POST /api/acoes/verificar`; acompanha por `GET /api/execucoes/{id}` e `GET /api/execucoes?workflow=W01` |
| Processar | `POST /api/acoes/processar` |
| Importar | `POST /api/acoes/importar-respostas` |
| Configuração | `GET/PUT /api/admin/configuracao` |
| Orçamento | `GET/PUT /api/admin/orcamento` |
| Termos | `GET/POST/PUT /api/admin/termos` |
| Usuários | `GET /api/admin/usuarios`; `POST/PUT/DELETE` só para o supremo |
| Reservar | `POST /api/admin/reservar-demo` |

## Quem vê

Só administradores; a gestão de usuários, só o supremo.

## Relacionadas

[[MOC Site]] · [[Papéis e acesso]] · [[W11 Ações do site]] · [[W01 Descoberta]] · [[Modelos e provedores]] · [[Custo por edital]] · [[Convenções dos fluxos n8n]]
