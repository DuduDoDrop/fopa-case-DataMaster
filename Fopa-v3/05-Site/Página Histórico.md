---
tipo: pagina
familia: site
rota: "/historico"
papel_minimo: usuario
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Painel.tsx
  - web/src/componentes/QuadrosResumo.tsx
  - api/consultas.py
tags: [site, pagina, historico, mercado]
---

# Página Histórico

> [!abstract] Em uma frase
> A outra metade do acervo: as licitações de folha que **já não estão valendo** — sessão realizada, vencedor homologado, revogadas ou anuladas, sem data e antigas, ou de antes de 2026 —, a mais recente primeiro, para análise de quem ganhou e do que aconteceu.

## Papel na solução

O Painel é trabalho do dia; o Histórico é **inteligência**. Aqui a equipe vê o que já passou, com as mesmas extrações e a mesma evidência, e cruza com os resultados do PNCP. Nada é apagado: uma licitação sai do Painel e aparece aqui ([[Página Painel#O que entra no Painel ("em andamento")]]).

![[site-historico.jpg]]

## O que a página mostra

### Quadros

| Quadro | O que é | Em produção (29/09/2026) |
|---|---|---|
| **No histórico** | total de licitações; barra: com vencedor homologado, revogadas ou anuladas, sem vencedor registrado; quantas são de antes de 2026 | **2.022** — 751 com vencedor · 60 revogadas/anuladas · 1.211 sem vencedor; 1.433 de antes de 2026 |
| **Extração** | extraídas; sem documento na fonte; custo das extrações; quantas sem preço e quantas rodaram localmente | **2.021 de 2.022**; 13 sem documento na fonte; R$ 18,19 (1 sem preço; 2.012 locais, sem API) |
| **Conferência** | % de respostas com trecho encontrado; para revisar; quantas a IA estima que não são folha | **99,96%** (25.139 de 25.147); 5.477 para revisar; 0 de 2.017 (média 93%) |

> [!info] Por que quase todo o histórico foi extraído "localmente"
> O acervo histórico foi extraído por um agente que leu a mesma leitura congelada e produziu as 17 respostas **sem chamar a API paga**; as respostas passaram pelo **mesmo verificador** e foram importadas pelo caminho oficial ([[W11 Ações do site]], ramo de importação). A procedência fica marcada como "local · sem API" em cada cartão ([[ADR-014 Extração por agente, sem API]]).

### Filtros

- **Busca** livre (município, órgão, modalidade, controle, objeto).
- **Mostrar**, com vários itens somados com E: Todas · Com conflito · Com alerta de regra · Já extraídas · Sem extração.
- **Período** (pela data de publicação): Todo o histórico · 2026 · 2025 · 2024 · 2023 · 2022 · Escolher datas.
- **Filtrar:** as escolhas do "Mostrar" e do "Período" valem ao clicar no botão, que volta à página 1. Não há "Vencimento": tudo aqui já fechou.
- **Itens por página:** 10, 50 ou 100.

### Cartões

Os mesmos do [[Página Painel|Painel]], com "encerrado · há N dias" no lugar do prazo.

## De onde vêm os dados

`GET /api/resumo?situacao=historico` e `GET /api/licitacoes?situacao=historico&…` — as mesmas consultas do Painel com a condição inversa ([[API do site — endpoints]]). Os resultados (vencedor homologado) vêm das tabelas `pncp_*` alimentadas pelo [[W41 Histórico do PNCP]].

## Quem vê

Todo usuário logado.

## Relacionadas

[[MOC Site]] · [[Página Painel]] · [[Página Analytics de Mercado]] · [[W41 Histórico do PNCP]] · [[Acervo e migração da v2]] · [[ADR-014 Extração por agente, sem API]] · [[ADR-015 Acervo só de 2026 e só compra de folha]]
