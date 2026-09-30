---
tipo: referencia
familia: dados
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - migracao/congelar.py
  - migracao/acervo.py
  - migracao/plano.py
  - migracao/importar.py
  - migracao/publicar.py
  - migracao/relatorio.py
  - migracao/relatorio-2026-09-24.md
  - db/014_importacao.sql
tags: [dados, migracao, acervo, procedencia]
---

# Acervo e migração da v2

> [!abstract] Em uma frase
> O que a versão anterior — a prova de conceito em scripts, que gravava tudo em pastas e arquivos JSON — já tinha produzido (licitações, PDFs, texto lido, extrações e verificações) foi **congelado num retrato com manifesto de hashes** e **importado sem reprocessar nada** para o banco da versão em produção, com a procedência de cada linha registrada e os casos duvidosos listados para decisão humana.

## Papel na solução

O acervo histórico é a base do Histórico, do Analytics e da calibragem de preço. Reprocessá-lo custaria OCR, chamadas de modelo e — pior — produziria respostas diferentes das já auditadas. A migração preserva o que foi feito e verificado, prova que o que entrou é o que existia, e deixa explícito tudo o que precisou ser **inferido**.

## Os cinco passos

| Passo | Módulo | O que faz | Garantia |
|---|---|---|---|
| 1. Congelar | `migracao/congelar.py` | copia a evidência (inventários, auditorias, texto lido, respostas, relatórios, gabaritos) para um retrato datado e registra **cada PDF** num manifesto por caminho, bytes, SHA-256 e data | o importador só enxerga o retrato; arquivo modificado há menos de 60 s fica de fora (poderia estar pela metade) |
| 2. Planejar | `migracao/plano.py` | traduz o acervo inteiro em linhas da nova versão, **em memória**: estado de cada licitação, pasta canônica, status de cada arquivo, leituras, execuções com procedência, verificações | nada toca o banco; cada regra de decisão tem teste com retrato sintético |
| 3. Importar | `migracao/importar.py` | escreve o plano no Postgres e os PDFs no armazenamento | **uma transação só** — um PDF que mudou depois do retrato (hash diferente do manifesto) aborta tudo; **idempotente** (chaves naturais e `ON CONFLICT DO NOTHING`); **nunca desfaz** a nova versão (estado só no nascimento; vigência só se ainda não houver) |
| 4. Publicar | `migracao/publicar.py` | gera o relatório de cada licitação verificada e a leva a `publicada` pela máquina de estados | uma licitação por transação; relatório que falha não desfaz a verificação |
| 5. Reconciliar | `migracao/relatorio.py` | relatório só de leitura do que ficou para decisão humana e do que foi inferido | **seção vazia diz que está vazia** — silêncio num relatório de reconciliação seria lido como "conferido" |

A importação rodou **dentro da infraestrutura**, por um serviço dedicado (`fopa-importar`), com o retrato montado só para leitura — para os PDFs irem ao mesmo armazenamento que o site serve.

## As regras de decisão

| Situação | Regra |
|---|---|
| identidade | tudo pelo **número de controle**; o nome da pasta é só origem ([[ADR-013 Identidade de licitação é o número de controle]]) |
| mais de uma pasta para o mesmo controle | todas entram em `pastas_legado`; a **canônica** é escolhida por critérios em ordem — a pasta cuja leitura só tem arquivos do próprio inventário, depois a finalização mais recente, depois a execução original sobre a reaproveitada; sem critério, `legado_suspeito` e decisão humana |
| arquivo na pasta que não está no inventário da licitação | `procedencia_incerta`: não é lido nem publicado até decisão |
| texto lido | vem do `paginas.json` da versão anterior, com procedência `legado_paginas_json` — o texto contra o qual as respostas foram verificadas |
| custo e tokens das execuções | **como vieram, nunca recalculados**; o campo deduzido é listado com a fonte |
| estado da licitação | segue a fase real: verificada → publicada no passo 4; lida sem execução → `preparada`; baixada → `baixada_ok`; sessão já passada e sem documento → `fora_janela` |
| execuções de ensaio | entram como **não canônicas** — nunca viram resultado ([[Controles de consistência]]) |
| a identidade da leitura inclui os **nomes** dos arquivos | um caso real juntava duas pastas com o mesmo texto e nomes diferentes, e 15 respostas aprovadas passaram a citar arquivos inexistentes — pego pelo invariante `aprovada_sem_pagina` e corrigido (`db/015`) |

## O que entrou (reconciliação de 24/09/2026)

| Medida | Valor |
|---|---|
| licitações | 2.070 |
| pastas do acervo anterior | 770 |
| arquivos | 2.734 (2.520 `ok`, 134 duplicatas, 27 contêineres ZIP, 17 formato não suportado, 12 fora do inventário, 10 recusados pela política da época, 9 de procedência incerta, 5 ausentes no disco) |
| leituras (texto congelado) | 755 |
| execuções de modelo | 552 (497 do agente e 10 por API como canônicas; simulado, harness e experimento como não canônicas) |
| verificações vigentes | 505 |
| publicações | 528 |
| controles com mais de uma pasta | 5, cada um com a canônica e o motivo |
| execuções com procedência inferida | 30, todas com a fonte registrada |

Depois da importação, o acervo continuou crescendo pela descoberta diária, pela descoberta histórica, pela extração por agente e pelos downloads refeitos com os formatos convertidos: em 28/09/2026, o Histórico tem 2.020 licitações de folha com 2.019 extraídas ([[Resultados medidos]]).

## Relacionadas

[[MOC Dados]] · [[Modelo de dados]] · [[Migrações do banco]] · [[ADR-013 Identidade de licitação é o número de controle]] · [[ADR-014 Extração por agente, sem API]] · [[Linha do tempo da construção]]
