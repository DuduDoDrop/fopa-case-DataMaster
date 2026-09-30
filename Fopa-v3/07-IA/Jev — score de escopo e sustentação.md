---
tipo: tecnica
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/jev.py
  - api/jev.py
  - api/rotas_jev.py
  - api/consultas.py
  - db/017_sinais_jev.sql
  - db/034_ia_nao_fopa.sql
  - db/035_trava_ia_com_edital.sql
  - n8n/workflows/W01.json
  - n8n/workflows/W22.json
  - n8n/workflows/W24.json
tags: [ia, jev, escopo, sinal, revisao, calibracao]
---

# Jev — score de escopo e sustentação

> [!abstract] Em uma frase
> O Jev (TypeSafe) é um modelo de **decisão tipada com probabilidade** que a solução usa em dois lugares, sempre como **segundo sinal**: para dizer se a licitação **é mesmo compra de folha** (lendo o objeto e, depois, o edital) e se o trecho citado **sustenta** a resposta aprovada; ele nunca aprova, nunca vira confiança e nunca reclassifica sozinho — a discordância com convicção vira fila de revisão humana.

## Papel na solução

Cobre dois pontos cegos das peças determinísticas:

1. **A regra de escopo** é vocabulário: erra quando o objeto usa palavras que ela não conhece ([[Regras antes de IA]]).
2. **A ancoragem** garante que o trecho **existe** na página, não que ele **responde** à pergunta: *"o prazo é de 60 meses"* com o trecho *"prazo de 12 meses para a garantia"* passa na ancoragem e está errado — comparação de texto não sabe ler ([[Verificador determinístico]]).

O Jev olha esses dois pontos com outro método (um modelo, não uma regra) e **aponta onde vale olhar**. Quem decide continua sendo a regra, o verificador ou uma pessoa.

## A linha que não pode ser cruzada

> [!danger] Nunca aprova, nunca vira confiança, nunca reclassifica sozinho
> - Nenhuma saída do Jev escreve o **veredito** de uma resposta.
> - Nenhuma saída do Jev escreve a **confiança** da resposta — esse campo é do extrator.
> - Nenhuma saída do Jev escreve o **escopo** da licitação (`escopo_dentro` é da regra; o rótulo humano é de gente).
>
> Um teste de guarda (`api/tests/test_jev.py`) lê o código do Jev no worker e os fluxos exportados do n8n e falha se encontrar qualquer atribuição a esses campos; outro teste, de ponta a ponta, confere que o sinal nunca muda um veredito. Os sinais ficam numa tabela própria, `sinais_jev`, fora das tabelas do pipeline.

## Como a API funciona

- `POST https://api.typesafe.ai/v1/systemone`, com `state` (o texto a julgar), `model` e `questions`. Duas primitivas: **`noul`** (probabilidade de "sim", de 0 a 1) e **`choice`** (uma opção entre várias, com `confidence` e a distribuição de probabilidades).
- **Modelo fixado em `jev-1.13.0`**, a versão em que os cortes de convicção foram medidos (o apelido `jev-latest` troca de modelo quando sai versão nova).
- **Sem trecho, citação ou posição na resposta** — conferido contra a API real. É por isso que o Jev **não pode extrair**: sem trecho não há o que o verificador confira.
- **Preço:** US$ 0,042 por milhão de tokens de entrada; saída gratuita. **Limite útil:** 32 mil tokens no `state` somado à maior pergunta — sondado: 63.750 caracteres passam, 67.500 voltam `max_tokens_exceeded`; a solução usa até 63.000.
- A chave vive na credencial `jev` do n8n; o worker só **monta** os corpos e **interpreta** as respostas (rotas `/jev/*`, [[Endpoints do worker]]).

## Uso 1 — é compra de folha?

| Onde | Contexto enviado | Critério |
|---|---|---|
| [[W01 Descoberta]] | só o **objeto** das licitações que a rodada inseriu (novas e fora de escopo), as novas primeiro; até 300 chamadas por rodada agendada (100 na manual); nunca na rodada seca | `v3.1` |
| [[W22 Ler]] | o objeto **mais as páginas do edital** que mais contêm termos de folha (até 12.000 caracteres, cada página cortada em 4.000), logo depois da leitura | `v3+edital` |
| [[W24 Verificar e publicar]] | a mesma nota com o edital, uma vez por licitação lida, se ainda faltar | `v3+edital` |

**A pergunta** (Noul, em inglês — a língua principal do modelo; o objeto vai em português): *"Is the public body contracting or accrediting ('credenciamento') a bank or financial institution to RUN ITS PAYROLL — that is, to process, manage and pay the salary credits of its public servants…? Judge what is being CONTRACTED, not words that are merely mentioned."* O critério do "sim" admite outros serviços bancários agregados (arrecadação, pagamento a fornecedores, consignado como extra); o do "não" lista consignado isolado, software de folha, consultoria, tarifas pagas pelo órgão, conta institucional e bens ou serviços sem relação.

**Como a resposta é lida** (`api/jev.py`):

| Campo gravado | Cálculo |
|---|---|
| `p_sim` | a probabilidade de ser folha |
| `resposta` | "sim" se `p_sim` ≥ 0,5 |
| `confianca` | distância do meio: \|p − 0,5\| × 2 |
| `p_filtro_ok` | a probabilidade de a **regra** ter acertado: `p_sim` se a regra aceitou, `1 − p_sim` se recusou — agregado, mede o ruído do filtro |
| `discorda` | o Jev está do outro lado da regra |
| `candidata` | discorda **com convicção**: p ≤ 0,25 ou p ≥ 0,75 |

**O que a tela usa:** a **média** da nota mais recente só com o objeto e da mais recente com o edital. Medido: a média derruba o alarme falso nas folhas reais de 4% para 0,8% e pega as mesmas recusas humanas que a nota com o edital sozinha.

**Os limiares:**

| Uso | Limiar | Onde |
|---|---|---|
| **Trava da extração paga** | nota **com o edital** ≤ 0,25 | fila (W10), W22, painel: a licitação sai do painel e da fila e vai para o histórico |
| **Filtro "apenas FOPA"** | média < 0,5 | Histórico e Analytics |
| **Candidata na aba Escopo** | discordância com convicção | [[Página Revisão]] |

O rótulo humano "dentro" prevalece sobre qualquer nota. A trava só age depois que a IA **viu o edital**: com o objeto sozinho, o Jev dava 0,24 a um credenciamento legítimo ("instituição financeira … administração e processamento"), e a trava barraria uma folha de verdade antes de ela ser lida.

## Uso 2 — o trecho sustenta a resposta?

No [[W24 Verificar e publicar]], depois de uma verificação nova (nunca para execução `simulado` ou `gravado`), o worker monta uma pergunta por **resposta que cita trecho**:

- **`state`**: a afirmação (a resposta), a pergunta respondida, o trecho citado, onde ("arquivo, página N") e o texto do arquivo — **inteiro**, se couber em 63.000 caracteres; senão, uma **janela em volta da página citada**, crescendo uma página para cada lado por vez. Nunca os primeiros N caracteres: isso cortaria justamente a página citada, e o "nada diz" que viria disso pareceria achado.
- **A pergunta** (`choice`): *"A passagem citada do edital sustenta a afirmação? Julgue apenas a relação entre as duas … Não avalie se a afirmação é verdadeira no mundo — só se ESTA passagem a sustenta."* Opções: **sustenta**, **contradiz** ("afirma o oposto, ou um valor, prazo ou nome diferente"), **nada_diz** ("não trata do que a declaração afirma").
- **O sinal** vai para `sinais_jev` e aparece no cartão da pergunta como "sustenta N%".
- **A candidata:** se a resposta estava **APROVADA** e o Jev diz "contradiz" ou "nada diz" com confiança ≥ 0,75, abre-se uma revisão humana com o motivo (por exemplo, "jev: contradiz p=0,99 (janela 3p de 60)"). **O veredito não muda.** As respostas que já estão em revisão só recebem a nota.

Caso real — Itapecuru Mirim/MA (28/09/2026): a Q1 aprovada teve "sustenta 100%"; a Q10, também aprovada pela ancoragem, teve **"sustenta 13%"** — o trecho existe na página, mas o Jev duvida que ele responda à pergunta, e isso chama olho humano.

**Medido** (prova adversarial com a página real e a afirmação adulterada): data trocada → "contradiz" com 1,00; valor inventado → "nada diz" com 1,00. Mandar a janela em vez de só a página citada reduziu as falsas divergências de 5 para 1 em 137 respostas (US$ 0,094 contra US$ 0,009). Custo em produção: cerca de **US$ 0,01 por licitação**.

## Os limites que definem o encaixe

| Limite (medido por terceiros ou pelo projeto) | Consequência |
|---|---|
| acurácia **plana** entre confiança 0,50 e 0,95 (auditoria independente) | distância do 0,5 nessa faixa não ordena nada: só conta a convicção (≤ 0,25 ou ≥ 0,75) |
| fora da distribuição de treino, erro de calibração de 0,325 (44,7% de acerto com probabilidade média 0,74) | "confiança calibrada" não sobrevive a verificação independente: o número do Jev nunca vira confiança |
| com critério mal descrito, a acurácia caiu a 16,7% em teste de terceiros, abaixo do acaso; e o modelo nunca se recusa a responder | a redação do critério é a variável de engenharia — fica versionada (`criterio_versao`) e só muda com medição |
| sem cache e com ruído: 50 pedidos idênticos deram 15 respostas diferentes (teste de terceiros); no projeto, a mesma chamada mudou de lado do 0,5 em 5 de 174 itens | nada decide pelo 0,5; os cortes de convicção absorvem o ruído |
| a língua do `state` custa acerto; a da instrução, não | instrução em inglês, texto em português |

## A configuração, medida

Dezoito variações foram medidas nos mesmos itens (124 folhas publicadas com leitura e 19 recusas humanas; os rótulos humanos como validação separada):

| Resultado | Variações |
|---|---|
| **Comprovadas e em produção** | média objeto + edital; modelo fixado em `jev-1.13.0`; cortes de convicção 0,25/0,75; trava só com a nota do edital; nota com o edital pedida logo depois da leitura; critério **v3.1** — o v3 com "contracting **or accrediting ('credenciamento')**": folhas reconhecidas de 96,8% para 100%, AUC de 0,969 para 0,982, credenciamentos de folha com nota < 0,5 de 23 para 6 em 137, e a troca de lado entre chamadas iguais de 10 para 0 |
| **Sem efeito** | primeira página do edital sempre no contexto (desfeita); `state` como objeto JSON; metade do contexto do edital; critérios estruturados; candidata pela probabilidade em vez da confiança; um pedido por página; o v3.1 também na nota com o edital |
| **Refutadas** | decompor em 5 perguntas atômicas com a regra no código (AUC 0,624); pergunta sem critérios; critério reescrito para os erros restantes (9 folhas recusadas com convicção) |
| **A testar** | combinar as 5 perguntas por regressão logística (AUC 0,985 em validação cruzada, mas com erros convictos e só 48 negativos para aprender) |

> [!important] O Jev não tem "esforço"
> A API recebe só `state`, `model` e `questions`; o modelo não raciocina nem gera texto. O que faz o papel de esforço é quanto texto vai no `state` e quantas perguntas se faz — os dois medidos acima, sem ganho — e escalar o caso incerto para um modelo que raciocina (o botão "Extrair com IA").

## No site e nos alertas

| Onde | O que mostra |
|---|---|
| [[Página Painel]] e [[Página Histórico]] | "Não reconhecidas como folha pela IA: X de Y" (probabilidade média Z%) — em 28/09/2026, 0 de 76 no painel (média 92%) e 0 de 2.015 no histórico (média 93%) |
| [[Página Detalhe da licitação]] | a nota de escopo da licitação e o "sustenta N%" de cada resposta |
| [[Página Revisão]] | a aba Escopo com as candidatas (1 pendente em 28/09/2026) e as revisões abertas pelo "sustenta?" |
| [[W40 Alerta diário]] | a contagem de candidatas do Jev ("1 jev candidatas" em 28/09/2026) |
| [[Custo por edital]] | o gasto com o Jev na fatura: US$ 17,85 desde 21/09/2026, a maior parte da importação do acervo, quando o "sustenta?" rodou sobre as licitações importadas |

## Relacionadas

[[MOC IA]] · [[Regras antes de IA]] · [[Verificador determinístico]] · [[W01 Descoberta]] · [[W22 Ler]] · [[W24 Verificar e publicar]] · [[Página Revisão]] · [[Técnicas avaliadas e descartadas]] · [[ADR-004 Evidência obrigatória]] · [[ADR-019 O site mostra só o que a IA confirma como folha]]
