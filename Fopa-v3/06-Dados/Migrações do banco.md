---
tipo: referencia
familia: dados
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - db/migrar.py
  - db/invariantes.sql
  - db/tests
  - docker/compose.yml
tags: [dados, banco, migracoes, reprodutibilidade]
---

# Migrações do banco

> [!abstract] Em uma frase
> O esquema do banco é construído por **50 arquivos SQL numerados**, aplicados em ordem por um script que registra o SHA-256 de cada um e **aborta se um arquivo já aplicado mudar** — migração é histórico, não configuração: mudar o esquema é escrever o arquivo seguinte.

## Papel na solução

É o que torna o banco reproduzível: um Postgres vazio, com as migrações aplicadas, tem exatamente o esquema de produção — tabelas, funções, gatilhos, papéis de acesso e as sementes (questionário, termos, orçamento, configuração). O mesmo aplicador serve ao teste efêmero do CI, à infraestrutura local e à produção ([[Testes e CI]]).

## Como o aplicador funciona (`db/migrar.py`)

1. Lista `db/0NN_*.sql` em ordem alfabética.
2. Para cada arquivo, calcula o SHA-256 **com fim de linha normalizado** (a conversão automática do Git mudaria os bytes sem ninguém ter editado a migração).
3. Arquivo já registrado em `schema_migracoes` com o mesmo hash: pula. Com hash diferente: **aborta**.
4. Arquivo novo: roda numa **transação própria** — se falhar no meio, nada dele fica e o registro não é gravado.
5. Aplica as senhas dos papéis (`n8n_rw`, `worker_rw`, `api_ro`, `api_rw`) a partir de variáveis de ambiente, só se existirem: **nenhum segredo no SQL**.
6. Imprime `aplicadas=N puladas=M`, que o teste e o serviço de migração conferem.

Em produção, a migração roda por um serviço dedicado da composição (`fopa-migrate`), **depois** do backup e **antes** de subir a imagem nova ([[Deploy e atualização]]).

## As 51 migrações

| Nº | O que faz |
|---|---|
| 001 | tipos e a tabela-mãe `licitacoes` (chave = número de controle; *slug* e CNPJ gerados), o enum dos 20 estados, `pastas_legado` |
| 002 | máquina de estados: `transicoes` permitidas e `licitacao_eventos` (só inserção), com o gatilho que recusa transição inválida |
| 003 | `arquivos`, `leituras` e `paginas` — o **texto congelado** |
| 004 | `perguntas`, `execucoes_modelo`, `chamadas_modelo`, `respostas` — a procedência de cada resposta |
| 005 | `verificacoes` e `verificacao_respostas`; o gatilho que impede resultado de ensaio vigente em licitação real (T15) |
| 006 | `publicacoes`, `revisoes_humanas`, `rotulos_escopo`, `gabaritos`, `itens_api` |
| 007 | `execucoes_workflow`, `buscas_paginas`, `buscas`, `termos`, `orcamento` |
| 008 | `emails`, `usuarios`, `sessoes`, `jobs`, `saude` |
| 009 | as funções que o n8n chama em vez de carregar regra no canvas (transição, classificação, vaga de extração) |
| 010 | as views do site (`gasto_diario`, `v_execucoes_workflow_custo`, `v_card`, `v_detalhe`) |
| 011 | os papéis de acesso e as permissões (tabelas imutáveis só com inserção) |
| 012 | sementes: o questionário, os termos de busca, o orçamento e o administrador inicial |
| 013 | correções da revisão da primeira fase |
| 014 | o que a importação do acervo anterior precisa (`importacoes`, status novos de arquivo) |
| 015 | a identidade da leitura inclui os **nomes** dos arquivos |
| 016 | `configuracao` no Postgres e o papel `api_rw` do site |
| 017 | `sinais_jev`, fora das tabelas do pipeline |
| 018 | o recorte de 2026 no banco (`ano_minimo`, `fn_no_recorte`) |
| 019 | a vaga de extração guardada por escopo e recorte; reaplicar a regra de escopo quando ela muda |
| 020 | `fn_registrar_vista`: o W01 grava cada resultado numa chamada, e a rodada seca não escreve nada |
| 021 | a fila do W10 em funções: *claim*, falha com espera crescente, *lease* vencido, disjuntor |
| 022 | o pedido "Processar" do site pelo caminho auditado (`fn_pedir_processamento`) |
| 023 | a licitação reservada para demonstração fica de pé |
| 024 | tipos de e-mail da reverificação (depois restritos pela 039) |
| 024 | a proteção T15 fechada pelos outros dois caminhos |
| 025 | duas rodadas simultâneas do W01 não inserem nem pontuam a mesma licitação duas vezes |
| 026 | RAG de produção com **12 páginas por pergunta** |
| 027 | o histórico de compra e venda da folha direto do PNCP (`pncp_compras`, `pncp_itens`, `pncp_resultados`, `pncp_coletas`) |
| 028 | o texto furtivo com o **texto** e a classificação de suspeito |
| 029 | "revisão pendente" é a da verificação vigente |
| 030 | o histórico inteiro do PNCP (desde 2021) registrado só como histórico |
| 031 | o rótulo humano de escopo **prevalece** na tela (`fn_escopo_efetivo`) |
| 032 | a fila respeita o rótulo humano e o provedor (sem provedor pago, só baixa e lê) |
| 033 | o botão "Extrair com IA" (`pedidos_extracao`) |
| 034 | o que a IA não reconhece como folha: a nota média, a trava e o filtro |
| 035 | a trava da IA só com a nota do **edital** |
| 036 | a fila pega o que parou entre baixar e ler |
| 037 | o pedido do botão carrega modelo, esforço e teto de saída |
| 038 | os **dois** e-mails do produto, parte 1: destinatário e tipos novos |
| 039 | os dois e-mails, parte 2: só eles cabem na tabela |
| 041 | o arquivo convertido para PDF (status `convertido`) |
| 042 | baixar de novo uma licitação que já tinha PDF |
| 043 | OCR forçado e rotação por arquivo |
| 044 | licitação sem documento na fonte |
| 045 | `gastos_ia`: o gasto real por fornecedor |
| 046 | o administrador supremo e o usuário comum |
| 047 | data de sessão absurda vira "sem data" no cartão |
| 048 | o site remove usuário |
| 049 | os contratos da folha e os termos aditivos, direto do PNCP |
| 050 | Best-of-N: a rodada de cada chamada e o registro da escolha |
| 051 | a descrição da configuração `k_rag`, mostrada na página Admin, sem citação pessoal (só texto; o valor não muda) |

Não existe o número 040, e há dois arquivos 024 — os dois foram aplicados em produção com esses nomes, e renumerar agora mudaria o histórico que o aplicador confere.

## Invariantes

Depois de migrar, `db/invariantes.sql` confere a integridade do acervo: zero linhas = banco íntegro ([[Modelo de dados#Invariantes]]).

## Relacionadas

[[MOC Dados]] · [[Modelo de dados]] · [[Funções e views do banco]] · [[Acervo e migração da v2]] · [[Deploy e atualização]] · [[Testes e CI]]
