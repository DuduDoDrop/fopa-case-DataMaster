---
tipo: pagina
familia: site
rota: "/"
papel_minimo: usuario
status: verificado
atualizado: 2026-09-29
fonte_codigo:
  - web/src/paginas/Painel.tsx
  - web/src/componentes/QuadrosResumo.tsx
  - web/src/componentes/CardLicitacao.tsx
  - api/site.py
  - api/consultas.py
  - db/047_data_de_sessao_absurda.sql
tags: [site, pagina, painel, nucleo]
---

# Página Painel

> [!abstract] Em uma frase
> A tela de trabalho do dia: **só as licitações de folha em andamento**, ordenadas pelo **prazo** (a que fecha primeiro vem primeiro), cada uma num cartão com o que o sistema extraiu, quanto disso está provado no documento, o que precisa de revisão e quanto custou.

## Papel na solução

É onde a equipe **decide onde entrar**: a pergunta de negócio não é "quais licitações existem", é "em qual eu entro e qual fecha primeiro". Por isso a ordem é por prazo e cada resposta leva ao PDF na página citada ([[Problema de negócio]], [[Proposta de valor]]).

![[site-painel.jpg]]

## O que entra no Painel ("em andamento")

Entra toda licitação **no escopo de folha** (a regra, ou o rótulo humano, que prevalece) que **não** está no histórico. Vai para o [[Página Histórico|Histórico]] a que:
- teve a sessão **já realizada** (prazo vencido);
- está fora do recorte de ano (antes de 2026);
- tem **vencedor homologado** no PNCP (exceto credenciamento com a janela ainda aberta — nele outros bancos ainda podem se credenciar);
- foi **revogada ou anulada**;
- não tem data de sessão e foi publicada **há mais de 60 dias**;
- está **travada pela IA** (a IA leu o edital e diz, com convicção, que não é folha).

As duas páginas **particionam** o acervo: toda licitação está em exatamente uma delas. Nada é apagado.

## O que a página mostra

### Faixa de números (quadros)

| Quadro | O que é | Em produção (29/09/2026) |
|---|---|---|
| **Em andamento** | licitações valendo; barra por prazo: fecham em até 7 dias, de 8 a 20, depois de 20, sem data; e a hora da última coleta | **69** — 23 em até 7 dias · 21 de 8 a 20 · 15 depois de 20 · 10 sem data; última coleta 28/09, 17:53 |
| **Extração** | quantas já têm extração; custo das extrações; quantas rodaram localmente (sem API); o provedor vigente da esteira; o teto por dia | **57 de 69**; R$ 33,79; 48 locais; "sem IA (ensaio)"; teto R$ 25,00 |
| **Conferência** | % de respostas com trecho encontrado no edital; quantas para revisar; quantas a IA estima que não são folha | **99,5%** (804 de 808); 163 para revisar; 0 de 74 (média 92% de chance de ser folha) |
| **Gastos com IA** | gasto total com IA desde o início do projeto, por fornecedor, pela fatura das APIs e pelo painel do Jev | **US$ 47,87 ≈ R$ 244,15** desde 21/09 — Claude US$ 24,06 · Jev US$ 17,90 · GPT US$ 5,91 |

### Filtros e busca

- **Busca** por município, órgão, modalidade, controle ou objeto (sem acento, sem diferenciar maiúsculas), aplicada enquanto se digita.
- **Mostrar**, com vários itens marcados ao mesmo tempo, somados com E: Todas · Com conflito · Já extraídas · Sem extração ("Já extraídas" e "Sem extração" se excluem).
- **Vencimento:** Qualquer prazo · Até 7, 15, 30, 45 ou 60 dias — só as abertas, em dias civis de São Paulo até a sessão, a mesma conta da cor do prazo no cartão.
- **Filtrar:** as escolhas do "Mostrar" e do "Vencimento" valem ao clicar no botão, que leva a lista de volta à página 1. O endereço guarda a escolha (`?filtro=conflito&filtro=extraidas&vence_em=30`); um link antigo com uma opção que saiu da barra lista todas.
- **Itens por página:** 10, 50 ou 100, com paginação em cima e embaixo.
- Link "**N no histórico →**" para a outra metade do acervo.

### O cartão de cada licitação

![[site-painel-cartoes.jpg]]

| Elemento | O que diz |
|---|---|
| Local, modalidade e controle | quem compra, como e o número de controle do PNCP |
| Objeto | o texto do objeto, como publicado |
| Marca de procedência | de onde vieram as respostas: `API` (modelo pago), `LOCAL` (extração sem API), `OPENAI`, `SIMULADO`, "procedência incompleta" |
| Selo da IA | "IA: é folha (97%)", "provavelmente é folha", "provavelmente não é folha", "não é folha" — a chance de **ser** compra de folha na opinião do Jev; **não muda o escopo** |
| Prazo | dias até a sessão, com a cor da urgência: vermelho até 7 dias, amarelo até 20, verde depois |
| Ancoragem | `respostas com trecho encontrado / respostas com trecho` |
| Conflitos · Não localizado · Revisar · Custo | contagens da verificação vigente e o custo da extração ("local · sem API", "R$ X" ou "preço não configurado") |
| Alertas em vermelho | os alertas globais do verificador (RN-09, RN-13, RN-14, RN-15…) com o texto completo |
| Documentos do edital | lista recolhível dos arquivos |
| **Ver as 17 respostas** | abre o [[Página Detalhe da licitação\|detalhe]] |
| **Abrir no PNCP** | abre o edital no portal oficial |
| Aviso "sem PDF válido" | quando o edital está num formato que não virou PDF legível |

## De onde vêm os dados

| Parte | Rota da API | Fonte no banco |
|---|---|---|
| quadros | `GET /api/resumo?situacao=ativas` | `v_card`, `chamadas_modelo`, `revisoes_humanas`, `sinais_jev`, `execucoes_workflow`, `configuracao`, `orcamento` |
| gastos com IA | `GET /api/gastos-ia` | `gastos_ia` (fatura das APIs) |
| lista de cartões | `GET /api/licitacoes?situacao=ativas&…` (`filtro` repetível, somado com E; `vence_em` de 7, 15, 30, 45 ou 60) | a view `v_card` (um cartão por controle), com o sinal do Jev e as marcas |
| usuário logado | `GET /api/me` | `usuarios`, `sessoes` |

Ver [[API do site — endpoints]] e [[Modelo de dados]].

## Quem vê

Todo usuário logado ([[Papéis e acesso]]). Não há botão que gaste ou mude nada nesta página.

## Relacionadas

[[MOC Site]] · [[Página Histórico]] · [[Página Detalhe da licitação]] · [[Ciclo de vida de uma licitação]] · [[Jev — score de escopo e sustentação]] · [[Escopo — o que é licitação de folha]] · [[Verificador determinístico]] · [[W01 Descoberta]]
