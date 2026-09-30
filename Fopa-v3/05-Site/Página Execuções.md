---
tipo: pagina
familia: site
rota: "/execucoes"
papel_minimo: admin
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Execucoes.tsx
  - api/consultas.py
  - db/007_execucoes_workflow_buscas_termos_orcamento.sql
tags: [site, pagina, operacao, observabilidade]
---

# Página Execuções

> [!abstract] Em uma frase
> O registro de **cada rodada de cada fluxo** do n8n — quando, qual workflow, sobre qual licitação, quanto durou, quanto custou e o que produziu —, a mais recente primeiro: é o diário de bordo da automação.

## Papel na solução

Toda rodada de fluxo deixa uma linha em `execucoes_workflow` ([[Convenções dos fluxos n8n]]). Esta página é a janela para esse registro: mostra se a descoberta rodou, se a fila andou, quanto custou uma extração e onde algo falhou ([[Saúde e observabilidade]]).

![[site-execucoes.jpg]]

## O que mostra

| Coluna | O que é |
|---|---|
| Quando | início da rodada |
| O quê | o workflow (W01, W10, W20…), a licitação (link) quando há, e o número da execução no n8n |
| Duração | tempo da rodada |
| Custo | custo de modelo da rodada (só quando houve chamada paga) |
| Resultado | o resumo dos contadores ("1 reivindicadas", "1 enviados · 1 reservados", "ok") ou o erro |

Nas rodadas da descoberta, a linha diz também quantas buscas ao PNCP falharam. A lista é paginada (50 por página).

O detalhe de uma rodada (`GET /api/execucoes/{id}`: argumentos, contadores, erro, a cobertura de cada consulta ao PNCP, página a página, e as execuções de modelo ligadas a ela) é usado pela [[Página Admin]] para acompanhar ao vivo o "Verificar agora".

## Exemplos reais (28/09/2026)

No print, o fim da tarde:
- **17:14 a 17:19 · Itapecuru Mirim/MA, segunda extração** — o W10 reivindica a licitação que o site mandou reprocessar, o W20 a processa em 3 min 52 s por **R$ 0,20**, com o GPT-6 Luna, e o W50 envia o e-mail da extração.
- **17:37, 17:47 e 18:04 · W20 · Bertioga/SP** — três extrações com o GPT-6 Luna pedidas pelo botão "Extrair com IA", duas em `medium` e uma em `high` (R$ 0,09, R$ 0,03 e R$ 0,11), cada uma seguida do seu e-mail: a comparação registrada em [[Comparação de modelos]].
- **17:53 · W01** — o "Verificar agora" da [[Página Admin]]: 2 min 40 s, "4 novas · 566 conhecidas · 3 retificadas", com 3 buscas ao PNCP que falharam; só consulta, sem gravar.

Mais cedo, no mesmo dia:
- **07:00 · W40** — "23 p1 · 5 p2 · 146 p6 · 5 p3 novas · 3.334 p5 respostas · 2 p3 publicadas · 626 p5 licitações · 1 jev candidatas · 5 p1 sem valor mínimo" — as seis prioridades do [[W40 Alerta diário]].
- **06:00 a 07:50 · W10** — uma linha a cada 10 minutos ("ok" ou "N reivindicadas").
- **06:20 · W20** — licitações baixadas e lidas pela esteira (dezenas de segundos cada).
- **10:22 · W20 · Itapecuru Mirim/MA** — 2 min 14 s, **R$ 0,78**: a extração pedida pelo botão "Extrair com IA".
- **10:25 · W50** — "1 enviados · 1 reservados": o e-mail da extração.

## De onde vêm os dados

`GET /api/execucoes?page=` e `GET /api/execucoes/{id}` — tabela `execucoes_workflow` e a view `v_execucoes_workflow_custo` ([[API do site — endpoints]]).

## Quem vê

Só administradores ([[Papéis e acesso]]).

## Relacionadas

[[MOC Site]] · [[MOC Fluxos n8n]] · [[Horários e agendamentos]] · [[Página Saúde]] · [[Saúde e observabilidade]] · [[Convenções dos fluxos n8n]]
