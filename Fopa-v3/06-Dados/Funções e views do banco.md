---
tipo: referencia
familia: dados
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - db/002_eventos_transicoes.sql
  - db/005_verificacoes.sql
  - db/009_funcoes.sql
  - db/010_views.sql
  - db/015_identidade_leitura.sql
  - db/018_recorte_2026.sql
  - db/019_fila_guardada_e_escopo_reavaliado.sql
  - db/020_registrar_vista.sql
  - db/021_fila_w10.sql
  - db/022_pedido_de_processamento.sql
  - db/023_demo_reservada.sql
  - db/024_t15_pelos_outros_lados.sql
  - db/025_registrar_vista_concorrente.sql
  - db/030_registrar_historico.sql
  - db/031_rotulo_humano_prevalece.sql
  - db/032_fila_rotulo_e_provedor.sql
  - db/033_pedido_extracao_ia.sql
  - db/034_ia_nao_fopa.sql
  - db/035_trava_ia_com_edital.sql
  - db/036_fila_pega_baixada_ok.sql
  - db/037_pedido_modelo_esforco.sql
  - db/047_data_de_sessao_absurda.sql
tags: [dados, banco, funcoes, fila, regras]
---

# Funções e views do banco

> [!abstract] Em uma frase
> As regras que não podem depender de quem chama — a máquina de estados, a fila com concorrência segura, o recorte de 2026, o escopo efetivo, a trava da IA, a vaga de extração dentro do teto e a proibição de publicar ensaio como real — são **funções e gatilhos do PostgreSQL**, testados em SQL e chamados pelos fluxos do n8n como uma linha de código legível.

## Papel na solução

Três atores escrevem no banco (n8n, worker e site). Uma regra escrita no canvas de um fluxo poderia ser esquecida por outro; escrita no banco, vale para todos. Por isso o canvas do n8n tem nós Postgres com chamadas como `fn_reivindicar('W10', NULL)` — e a lógica, com os casos-limite, está aqui, com teste ([[Decisões de construção da v3]]).

## Máquina de estados

| Função | O que faz |
|---|---|
| `fn_transicao_permitida(de, para)` | consulta a tabela `transicoes` |
| `fn_valida_transicao()` — **gatilho** em `licitacoes` | recusa qualquer mudança de estado que não esteja na tabela |
| `fn_transicao(controle, para, motivo, detalhes)` | o **único caminho** para mudar estado: valida, atualiza e grava o evento em `licitacao_eventos` |
| `fn_guarda_rearmar()` — **gatilho** | a volta de `publicada` para `preparada` só existe para licitação reservada para demonstração |

Detalhe dos 20 estados e das transições em [[Ciclo de vida de uma licitação]].

## Descoberta e registro

| Função | O que faz |
|---|---|
| `fn_vista_pura(controle, payload, hoje)` | classifica um resultado da busca **sem escrever nada**: fora do recorte, nova, encerrada, fora de escopo, retificada, conhecida |
| `fn_classificar_vista(...)` | a mesma classificação, mais o carimbo de atualização do PNCP |
| `fn_registrar_vista(controle, payload, hoje, seco, origem)` | a decisão do [[W01 Descoberta]] para cada item, numa chamada: `ignorar` (fora do recorte), `inserir_nova`, `inserir_fora_escopo`, `inserir_fora_janela`, `retificar`, `visto`, `visto_reservada` (reservada para demonstração não é retificada no dia) ou `visto_concorrente` (outra rodada inseriu no mesmo instante — evita contar e pontuar duas vezes). Com `seco`, **nada é escrito** |
| `fn_registrar_historico(controle, payload, hoje)` | registra o passado (desde 2021) só como histórico — `fora_janela` ou `fora_escopo`, origem `historico` —, nunca na fila paga, sem tocar no que já existe |
| `fn_assinatura_nomes(assinatura)` | a identidade da leitura inclui os **nomes** dos arquivos (a resposta cita pelo nome): hash de "nome⇥hash" em ordem de bytes, igual ao cálculo em Python |

## Recorte e escopo

| Função | O que faz |
|---|---|
| `fn_ano_minimo()` | lê `configuracao.ano_minimo` (2026) |
| `fn_no_recorte(fim_prazo, publicado_em)` | sessão no ano mínimo ou depois; sem sessão, publicação no ano mínimo; sem data nenhuma, fora ([[ADR-015 Acervo só de 2026 e só compra de folha]]) |
| `fn_prazo_plausivel(fim, publicado)` | data de sessão mais de 730 dias depois da publicação é tratada como **sem data** no cartão (um "2036" digitado no lugar de "2026") — o dado original do PNCP fica guardado |
| `fn_aplicar_escopo(controle, dentro, motivo, versao, origem)` | grava o veredito da regra e, se mudou, move o estado: sem evidência → `fora_escopo`; aceita de novo → `nova`; publicada só troca a marca |
| `fn_escopo_efetivo(controle, regra)` | o **rótulo humano** mais recente, se houver; senão, a regra |
| `fn_rotulo_dentro_volta_a_fila(...)` | rótulo "dentro" numa licitação que a regra mandou para `fora_escopo` a devolve a `nova` |
| `fn_ia_p_folha(controle)` | a nota da IA: média da nota mais recente só com o objeto e da mais recente com o edital |
| `fn_ia_nao_fopa(controle, limiar)` | a IA recusa abaixo do limiar **e** não há rótulo humano "dentro" |
| `fn_ia_tem_edital(controle)` · `fn_ia_trava(controle)` | a **trava**: nota **com o edital** ≤ 0,25 e sem rótulo humano "dentro" — a licitação não vai à extração paga e sai do painel ([[Jev — score de escopo e sustentação]]) |

## A fila

| Função | O que faz |
|---|---|
| `fn_reivindicar(por, max_por_execucao)` | o *claim* do [[W10 Fila]]: vagas = 4 − extrações em curso (limitado pelo máximo por execução do orçamento); candidatas nos estados `nova`, `retificada`, `falha_rede`, `baixada_ok`, `erro_leitura`, `erro_extracao`, `aguardando_orcamento`, `preparada`, `verificada`, com a próxima tentativa vencida, menos de 4 tentativas, sem reserva de demonstração, prazo não vencido, sem *lease* vivo, **escopo efetivo**, **sem a trava da IA**, **no recorte**; sem provedor pago, só o que ainda falta baixar e ler (grátis), o que tem pedido do botão e o que é ensaio. Ordem: prioridade, retificadas, prazo mais curto. Trava as linhas com `FOR UPDATE SKIP LOCKED` e dá *lease* de 2 horas |
| `fn_liberar_leases_vencidos()` | *lease* vencido no meio de um passo (worker morto) vira a falha daquele passo, com tentativa e espera; fora de passo, só devolve o *lease* |
| `fn_registrar_falha(controle, estado_erro, motivo, cega)` | leva ao estado de erro, soma tentativa (não quando a coleta foi cega), agenda a próxima: **15 min → 2 h → 12 h**, e `erro_definitivo` na 4ª |
| `fn_backoff(tentativas)` | a tabela de espera acima |
| `fn_disjuntor_w20_aberto()` | **3 ou mais erros do W20 em 30 minutos e nenhum sucesso** → a fila não reivindica nada |
| `fn_pedir_processamento(controle, forcar, solicitante)` | o pedido "Processar" do site: recusa fora do escopo ou do recorte; aceita "já em curso"; estados terminais só voltam a `nova` com `forcar`; o resto ganha prioridade 1 e o nome de quem pediu |
| `fn_provedor_real()` | a configuração tem provedor pago (não `simulado` nem `gravado`)? |
| `fn_provedor_pedido(controle)` · `fn_pedido_ia(controle)` · `fn_extrai_com_ia(controle)` | o pedido pendente do botão "Extrair com IA" (provedor, modelo, esforço, teto de saída) e se a licitação vai mesmo à extração paga |

## A vaga de extração

`fn_tomar_vaga_extracao(controle, max, teto_brl_dia)`, sob trava exclusiva do banco (`pg_advisory_xact_lock`), recusa em ordem: licitação que não existe; fora do escopo efetivo; **trava da IA**; fora do recorte; estado que não permite extrair; **sem vaga** (já há o máximo de extrações em curso); **sem orçamento** (gasto do dia + R$ 6,56 por extração em curso e pela nova passaria do teto). Só então faz a transição para `extraindo` ([[Custo por edital]], [[W23 Extrair]]).

## Ensaio nunca vira resultado real (T15)

| Função | O que faz |
|---|---|
| `fn_vigente_exige_ensaio()` — **gatilho** em `verificacoes` | uma verificação de execução `simulado` ou `gravado` só pode ficar vigente em licitação marcada como ensaio |
| `fn_t15_origem_da_execucao()` · `fn_t15_ensaio_da_licitacao()` — **gatilhos** | fecham os outros caminhos: mudar a origem de uma execução já vigente, ou desmarcar o ensaio de uma licitação com resultado de ensaio vigente |

Somado à restrição que impede execução de ensaio canônica e ao invariante `simulado_vigente_sem_ensaio`, o resultado de regex ou de replay não tem como aparecer como resposta de modelo numa licitação real ([[Controles de consistência]]).

## Utilitárias

`fn_carimbar_atualizado_em()` e `fn_carimbar_em()` — gatilhos que mantêm as datas de atualização de `licitacoes` e de `configuracao`, para que nenhum dos três escritores precise lembrar de carimbar.

## As views

| View | Conteúdo |
|---|---|
| `gasto_diario` | custo de `chamadas_modelo` por dia de São Paulo — a base do teto |
| `v_execucoes_workflow_custo` | cada rodada de fluxo com o custo somado das chamadas |
| `v_card` | o cartão das listas do site: dados da licitação, estado, prazo (com a data absurda tratada), contagens da verificação vigente |
| `v_detalhe` | o detalhe da licitação, com a verificação vigente |

## Relacionadas

[[MOC Dados]] · [[Modelo de dados]] · [[Ciclo de vida de uma licitação]] · [[Migrações do banco]] · [[W10 Fila]] · [[W23 Extrair]] · [[Controles de consistência]]
