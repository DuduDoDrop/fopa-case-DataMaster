---
tipo: decisao
familia: decisoes
status: verificado
atualizado: 2026-09-28
tags: [decisao, implementacao, v3]
---

# Decisões de construção da v3

> [!abstract] Em uma frase
> As escolhas de **implementação** feitas durante a construção da versão em produção — quando o plano, a especificação e o código não respondiam —, cada uma com o motivo e **o custo se estiver errada**; são diferentes dos ADRs, que registram decisões de produto e de arquitetura.

## Papel na solução

Um ADR explica **o que** a solução faz e por quê. Estas decisões explicam **como** algumas partes foram construídas e onde está o risco residual de cada uma. Todas estão em produção; cada linha pode ser revista sem reescrever a arquitetura.

## Orquestração e configuração

| Decisão | Por quê | Custo se estiver errada |
|---|---|---|
| **A orquestração e as decisões de fluxo moram no n8n; OCR, BM25/prompt, verificador, relatório e regra de escopo ficam no worker, como serviços HTTP** | o fluxo fica visível e editável no canvas; o processamento pesado e testado continua em Python, o mesmo código que produziu as medições | nenhum medido; é a fronteira da [[Arquitetura]] |
| **Configuração de execução numa tabela do Postgres (`configuracao`)**, não em tabelas internas do n8n | o site edita e o n8n lê pelo mesmo banco; tudo auditável | o n8n lê com nó Postgres em vez de recurso próprio |
| **A regra da fila mora no banco** (`fn_reivindicar`, com trava de linha e `SKIP LOCKED`), não no canvas | concorrência correta sob rodadas sobrepostas; testável em SQL | nenhum medido ([[Funções e views do banco]]) |
| **"Todo dia às 06:00" virou uma janela de 06:00 a 07:50, a cada 10 minutos** | a fila pega até 4 por rodada; uma rodada só andaria 4 por dia | roda 12 vezes de manhã; sem provedor pago, sem custo ([[W10 Fila]]) |
| **O nó que chamaria a fila direto do W01 ficou desligado** | com a descoberta às 06:00 e a janela da fila, o encadeamento é desnecessário; ligado, dispararia processamento fora de hora | habilitar um nó |
| **O W30 não tem webhook para reverificar o acervo inteiro** | ninguém chama; um gatilho remoto para o acervo inteiro é risco sem uso | reverificação em lote pelo editor do n8n ([[W30 Reverificar em lote]]) |
| **W01 linear, com `fn_registrar_vista` decidindo a ação de cada item**, em vez de um desvio com quatro ramos | ramo sem item não roda no n8n, e a rodada seca acabava gravando | menos nós visíveis no canvas ([[W01 Descoberta]]) |

## Banco e dados

| Decisão | Por quê | Custo se estiver errada |
|---|---|---|
| **O aplicador de migrações normaliza fim de linha antes do SHA-256** | a conversão automática de fim de linha do Git reescreveria os `.sql` e o aplicador abortaria contra um banco íntegro; o mesmo vale para os hashes de versão | nenhum ([[Migrações do banco]]) |
| **Invariante "aprovada sem página"** no lugar de "página citada inexistente" | a resposta crua do modelo **pode** citar página inexistente — é o que o verificador reprova; a garantia está no veredito APROVADO | o invariante antigo acusaria toda citação alucinada do acervo |
| **O papel do n8n pode atualizar `emails`** | o W50 precisa marcar enviado ou falhou | um fluxo poderia reescrever um e-mail já enfileirado |
| **"Baixar de novo" tem transições próprias** (`db/042`), sem passar por `retificada` | `retificada` deixaria a licitação para sempre no filtro de retificadas sem o PNCP ter mudado | duas transições a mais, só para operador ([[Ciclo de vida de uma licitação]]) |
| **A vaga de extração recusa também pedido manual fora do recorte de ano** | o recorte protege o gasto; o administrador muda o `ano_minimo` se quiser | quem opera não extrai 2025 sem mudar a configuração |

## Escopo e IA

| Decisão | Por quê | Custo se estiver errada |
|---|---|---|
| **A trava da IA usa só a nota com o edital** | a nota só com o objeto dava 0,24 a um credenciamento legítimo e barraria folha antes de ela ser lida | licitação que a IA recusa só pelo objeto é lida (sem custo) antes de travar |
| **Critério v3.1 do Jev só na nota com o objeto; na nota com o edital fica o v3** | medido: 136 de 143 nas duas versões com o edital | nenhum medido |
| **A guarda do ajuste de escopo protege qualquer sinal de folha de banco, sem nomes de banco** | "certidões … Caixa Econômica" era serviço de RH | um falso positivo com palavra de banco segue dentro; o Jev e o rótulo humano pegam |
| **O esforço cobra no teto de saída** (32 mil tokens em `xhigh`, 64 mil em `max`) e a tela mostra o máximo | o custo previsto nunca subestima | hoje irrelevante: o esforço é fixo em `medium` |

## Leitura de documentos

| Decisão | Por quê | Custo se estiver errada |
|---|---|---|
| **Modelo `por` do Tesseract fixado por commit e SHA-256 no build** | a leitura precisa ser reproduzível | o build falha na conferência — nunca em silêncio |
| **RAR pelo `bsdtar`, tudo ou nada** | o pacote de 7-Zip da distribuição vem sem o código do RAR; extração parcial silenciosa seria pior que recusa | um RAR com um membro cifrado perde os outros — com o motivo escrito |
| **Imagem sempre construída do commit** (`git archive`), nunca da árvore de trabalho | o que roda é exatamente o que está versionado; o `/health` informa o SHA | nenhum |

## Site

| Decisão | Por quê | Custo se estiver errada |
|---|---|---|
| **"Ativa" = prazo por vir, ou sem prazo publicada há até 60 dias e sem resultado homologado; revogada ou anulada vai ao histórico** | 85 de 157 "ativas" eram contratações diretas sem prazo, várias antigas e já homologadas | uma contratação direta sem prazo e sem resultado com mais de 60 dias sai do Painel (continua no Histórico) |
| **Fila e contador de revisão só da verificação vigente**, sem apagar as antigas | a pessoa revisa o que está publicado | a decisão humana não atravessa uma republicação: o W24 reabre a pergunta na verificação nova |
| **Os cabeçalhos da compra (API de consulta) só depois da descoberta** | as duas dividem o limite do PNCP por IP | só tempo |
| **Os filtros do Analytics Histórico FOPA rodam no navegador** | 0,6 s e 310 KB para o acervo atual, sem endpoint novo | um endpoint próprio se o acervo crescer muito |
| **A página de detalhe acompanha o processamento até o estado parar de andar (ou 15 minutos)** | evita consulta infinita | numa falha longa, a pessoa volta a atualizar a página |

## Relacionadas

[[MOC Decisões]] · [[Arquitetura]] · [[Funções e views do banco]] · [[Migrações do banco]] · [[Linha do tempo da construção]] · [[Desafios enfrentados]]
