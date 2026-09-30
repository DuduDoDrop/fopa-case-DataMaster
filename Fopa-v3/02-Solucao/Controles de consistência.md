---
tipo: arquitetura
familia: solucao
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - db/001_tipos_licitacoes.sql
  - db/002_eventos_transicoes.sql
  - db/004_perguntas_execucoes_chamadas_respostas.sql
  - db/005_verificacoes.sql
  - db/011_papeis.sql
  - db/024_t15_pelos_outros_lados.sql
  - db/invariantes.sql
  - api/versao.py
  - scripts/fopa/questionario.py
  - ci/tests/test_guardas_texto.py
  - api/tests/test_jev.py
tags: [arquitetura, consistencia, controles, integridade, nucleo]
---

# Controles de consistência

> [!abstract] Em uma frase
> O conjunto de travas que mantém a solução coerente mesmo com três escritores no banco, fluxos rodando em paralelo, modelos que variam e pessoas decidindo por cima: identidade única, máquina de estados, tabelas que só acumulam, uma versão vigente por licitação, ensaio que nunca vira resultado, saída em esquema fechado, versões por hash, filas com trava de linha, custo que nunca é zero por falta de preço, invariantes e guardas no CI.

## Papel na solução

É o que responde ao requisito de **respostas consistentes e controladas**: não basta o modelo acertar — o sistema inteiro precisa garantir que o que aparece na tela é o que foi verificado, na versão certa, sem estado impossível.

## Os controles

### Identidade e estado

| Controle | Como | Onde |
|---|---|---|
| **identidade única** | o número de controle do PNCP é a chave; o *slug* e o CNPJ são **gerados** a partir dele — ninguém grava um *slug* que não bate | [[ADR-013 Identidade de licitação é o número de controle]] |
| **máquina de estados** | 20 estados; um gatilho recusa qualquer transição fora da tabela; toda mudança passa por `fn_transicao` e gera um evento | [[Ciclo de vida de uma licitação]] |
| **eventos imutáveis** | `licitacao_eventos` só recebe inserção: a história de cada licitação não se reescreve | [[Modelo de dados]] |

### O que a máquina produz

| Controle | Como | Onde |
|---|---|---|
| **tabelas que só acumulam** | páginas, respostas, chamadas ao modelo, vereditos, buscas e eventos: só inserção, para qualquer papel | [[Modelo de dados]] |
| **uma leitura e uma verificação vigentes** | índices únicos parciais: no máximo uma leitura vigente e uma verificação vigente por licitação | [[Funções e views do banco]] |
| **uma verificação por execução e versão de regras** | restrição única; verificar de novo com as mesmas regras devolve 409, nunca duplica | [[Verificador determinístico]] |
| **a verificação nasce não vigente** | tornar vigente é decisão do fluxo (W24 ou W30), nunca efeito colateral | [[W24 Verificar e publicar]] |
| **saída em esquema fechado** | JSON validado com todos os campos obrigatórios e nenhum campo extra; pergunta que não veio vira "não localizado" (e, no reforço, é pulada) | [[Prompt do extrator]] |

### Ensaio nunca vira resultado (T15)

Resposta de expressão regular (`simulado`) ou de replay (`gravado`) **nunca** pode aparecer como resposta de modelo numa licitação real:

1. restrição: execução de ensaio não pode ser canônica;
2. gatilho: verificação de ensaio só fica vigente em licitação marcada como ensaio;
3. dois gatilhos fecham os caminhos laterais: trocar a origem de uma execução já vigente e desmarcar o ensaio de uma licitação com resultado de ensaio vigente;
4. a fila, sem provedor pago, só baixa e lê — não leva licitação real à extração de mentira;
5. um invariante confere depois do fato.

### Versões e procedência

| Controle | Como |
|---|---|
| `versao_regras` | SHA-256 do código que decide veredito e tag |
| `versao_prompt` | SHA-256 do que o modelo vê (instrução, esquema, molde da mensagem, perguntas e termos) |
| `escopo_versao` | SHA-256 da regra de escopo e da camada de ajuste |
| `git_sha` | o commit da imagem, informado pelo `/health` |
| OCR | versão do Tesseract e SHA-256 do modelo de idioma conferidos no build e de hora em hora |
| chamada ao modelo | SHA-256 do corpo enviado; o envelope inteiro da resposta guardado |
| respostas | hash das respostas cruas de cada execução |

Nada disso depende de alguém lembrar de incrementar um número: o hash muda sozinho quando o código muda ([[Pipeline de dados]]).

### Concorrência e operação

| Controle | Como |
|---|---|
| **fila com trava de linha** | `FOR UPDATE SKIP LOCKED` e *lease* de 2 horas: duas rodadas nunca pegam a mesma licitação |
| **vaga de extração exclusiva** | trava exclusiva do banco ao conferir simultaneidade e teto — duas extrações não passam juntas pelo mesmo teto |
| **rodadas simultâneas da descoberta** | a segunda rodada vê `visto_concorrente` em vez de inserir e pontuar de novo |
| **disjuntor** | 3 erros do processamento em 30 minutos sem sucesso param a fila |
| **espera crescente** | 15 min → 2 h → 12 h; na 4ª falha, `erro_definitivo` |
| **lease vencido** | vira a falha do passo, com espera, pelo mesmo caminho |
| **e-mail uma vez** | um e-mail de extração por verificação; só os dois tipos cabem na tabela |
| **idempotência** | migrações, importação do acervo, importação dos fluxos e publicação podem rodar de novo sem duplicar |

### Custo

| Controle | Como |
|---|---|
| preço desconhecido é **nulo**, nunca zero | execução por API com R$ 0 é violação de invariante |
| gasto do dia pela soma das chamadas | inclui lotes pagos de execuções que falharam no meio |
| teto diário com reserva | a vaga só é dada se couber no teto ([[Custo por edital]]) |

### Pessoas por cima, nunca por dentro

Revisões e rótulos ficam em camadas próprias: a decisão humana **não reescreve** a resposta nem o veredito da máquina, e o site entra no banco com um papel que só grava decisões humanas. O Jev, que é um modelo, **não escreve** veredito, confiança nem escopo — um teste de guarda confere ([[Jev — score de escopo e sustentação]]).

## Invariantes e guardas

- **Invariantes SQL** (zero linhas = íntegro): publicada sem exatamente uma verificação vigente; aprovada apontando para página inexistente; execução por API com custo zero; arquivo `ok` sem objeto no armazenamento; ensaio vigente em licitação real ([[Modelo de dados#Invariantes]]).
- **Guardas no CI:** o endereço da API do modelo só no ramo de extração do W23, nunca no worker nem no site; nada do Jev atribuído a veredito, confiança ou escopo; o nó do W01 que dispararia a fila fora da janela conferido como desligado, e a agenda do W10 conferida como ligada ([[Testes e CI]]).

## Relacionadas

[[MOC Solução]] · [[Arquitetura]] · [[Ciclo de vida de uma licitação]] · [[Funções e views do banco]] · [[Verificador determinístico]] · [[Consciência operacional]] · [[Testes e CI]]
