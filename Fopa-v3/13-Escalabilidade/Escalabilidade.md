---
tipo: arquitetura
familia: escalabilidade
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - docker/compose.yml
  - docker/compose.prod.yml
  - api/jobs.py
  - db/021_fila_w10.sql
  - db/035_trava_ia_com_edital.sql
  - api/storage.py
tags: [escalabilidade, arquitetura, capacidade, custo, desempenho]
---

# Escalabilidade

> [!abstract] Em uma frase
> A solução foi desenhada para crescer **sem reescrever nada**: os serviços não guardam estado (tudo está no Postgres e no S3), a fila distribui trabalho com trava de linha, o armazenamento é endereçado pelo conteúdo e o custo de IA cresce **linearmente e com teto**; hoje ela roda numa máquina pequena porque o volume é pequeno — o volume real de licitações de folha é de **poucas por dia** —, e cada gargalo tem uma alavanca conhecida, da mais barata à mais estrutural.

## Papel na solução

O enunciado pede uma solução **escalável, segura e eficiente**. Esta nota mostra, com números medidos, a carga que existe, onde estão os gargalos e o que fazer quando a carga crescer — ou quando o banco quiser aplicar a mesma arquitetura a outros tipos de documento.

## A carga real

| Medida | Valor |
|---|---|
| licitações de folha publicadas por dia | **mediana de 2**; pico de **12** num dia (658 licitações em 293 dias distintos, medido em 23/09/2026) |
| licitações ativas acompanhadas | 71 no painel (28/09/2026) |
| histórico | ~2.000 licitações de folha; ~6.600 compras coletadas diariamente no histórico do PNCP |
| usuários | a área de negócio (dezenas de pessoas), leitura concorrente leve |

## Quanto cada etapa custa em tempo e recurso

| Etapa | Medida | Onde pesa |
|---|---|---|
| baixar e ler 60 páginas com texto (Itapecuru) | **36,7 s** | rede e CPU |
| OCR | 1,6 a 2,2 s por página (texto); tabela mais lenta, a 400 dpi | **CPU e memória — o gargalo da máquina** |
| conversão de formato | até 180 s por arquivo (LibreOffice) | CPU e memória |
| extração (3 a 5 chamadas) | 1 a 2 minutos; Itapecuru: 2 min 14 s no total | **o provedor do modelo** (tempo e limite de tokens por minuto) |
| verificação | segundos; sem modelo | CPU leve |
| histórico e contratos | ~20 minutos por dia, ~16 mil chamadas ao PNCP | rede e o limite do PNCP |

## O que já foi desenhado para escalar

| Propriedade | Por quê escala |
|---|---|
| **serviços sem estado** | API do site e worker guardam tudo no Postgres e no S3 — mais processos podem ser adicionados sem migração de estado |
| **fila no banco com `SKIP LOCKED`** | vários consumidores pegam trabalhos diferentes sem colisão; *lease* com vencimento recupera trabalho de processo morto |
| **jobs longos assíncronos** | o n8n dispara e acompanha; o worker executa numa fila própria (`jobs`), com concorrência configurável |
| **limite de simultaneidade e de gasto no banco** | até 4 extrações ao mesmo tempo e teto diário, sob trava exclusiva — crescer não vira conta surpresa |
| **armazenamento pelo conteúdo, no S3** | o bucket escala sozinho; arquivos idênticos são guardados uma vez |
| **cache de prompt** | o documento é pago cheio uma vez por extração; leituras de cache não contam para o limite de tokens por minuto do provedor (segundo a documentação da Anthropic) |
| **modo por tamanho** | acima de 180 mil caracteres, o RAG manda só as páginas relevantes — documento maior não significa custo proporcional |
| **idempotência** | reprocessar, reimportar e republicar não duplicam; uma falha no meio recomeça do ponto certo |
| **custo por chamada gravado na hora** | o gasto do dia é conhecido em tempo real |

## Os gargalos e as alavancas, em ordem de custo

| # | Gargalo | Alavanca | Custo |
|---|---|---|---|
| 1 | **CPU e memória da máquina** (OCR, conversão) — hoje um job por vez | trocar o tipo da instância (o mesmo disco e o mesmo IP) e subir `FOPA_JOBS_CONCORRENCIA` | minutos de parada |
| 2 | **limite de tokens por minuto do provedor** | a extração já roda em série e com cache; paralelizar exige limitar a 4–5 simultâneas (o banco já limita a 4) ou subir de faixa no provedor | configuração |
| 3 | **custo de IA com volume** | modelo menor para triagem (Claude Sonnet 5 + RAG custou R$ 1,28 com as 7 críticas corretas), cache, lotes | escolha no Admin, medida |
| 4 | **um único worker** | mais réplicas do worker sobre o mesmo banco e o mesmo bucket (a fila de jobs e a de licitações já são concorrentes) | composição |
| 5 | **um único n8n** | modo de fila do n8n com execução distribuída, ou mover agendas para mais instâncias | infraestrutura |
| 6 | **uma única máquina** | serviços gerenciados (banco gerenciado, containers orquestrados) — a composição já separa os serviços | migração planejada |
| 7 | **o limite do PNCP** | fora do nosso controle: ritmo conservador, cabeçalhos com limite de tempo, coleta mínima ([[Disponibilidade do PNCP]]) | — |

> [!warning] O cálculo que precisa ser lido antes de paralelizar a extração
> No dia de pico medido (12 licitações), disparar **todas no mesmo minuto** usaria 3,6% do limite de requisições do provedor — mas, no pior caso do acervo (um edital de 212 mil tokens), **127% do limite de tokens de entrada por minuto** da faixa inicial. Em série, como roda hoje, o pico se espalha por ~22 minutos e fica em **~6%** do limite. O gargalo de um edital é o **peso**, não a quantidade de chamadas.

## Custo com volume

- **Fixo:** uma instância e o armazenamento ([[Custo de infraestrutura]]).
- **Variável:** de R$ 0,20 a ~R$ 5 por edital extraído, com teto diário configurável; o que custa zero em modelo (coleta, leitura, verificação, reverificação) não cresce com a conta de IA.
- **Com o volume real** (mediana de 2 licitações de folha por dia, ~60 por mês), extrair todas as novas no modelo padrão ficaria em torno de **R$ 150 por mês** (60 × R$ 2,50, o custo medido do Claude Opus 5.5 em contexto completo, com esforço alto — o esforço de produção é menor).

## Escalar para outros problemas

A arquitetura não é específica de folha: trocar o **questionário** (as perguntas, os termos e as regras do verificador) e a **regra de escopo** aplica o mesmo pipeline — descobrir, ler com prova, verificar sem IA, revisar — a contratos, aditivos ou outros editais que o banco acompanhe ([[Próximos passos]]).

## Relacionadas

[[Arquitetura]] · [[Stack e justificativa tecnológica]] · [[Hospedagem na AWS]] · [[Containers e serviços]] · [[Custo por edital]] · [[Custo de infraestrutura]] · [[RAG com BM25]] · [[Cache de prompt e ordem do prompt]] · [[Funções e views do banco]] · [[Próximos passos]]
