# Referência de design do site v3 — "siga o HTML"

O painel (`amostras/index.html`, gerado por `scripts/fopa/painel.py`) e o
RELATORIO por licitação (`scripts/fopa/pagina.py`) são a referência visual e
funcional do site React. A construção segue o HTML à risca.
Este arquivo diz **o que** preservar e **por
quê**; os dois CSS ao lado são o **como**, extraídos literalmente dos módulos
que geram o HTML hoje (`painel.css`, `relatorio.css`) — nunca editados à mão.

## 1. Tokens

Um único `:root`, igual nos dois HTML. O site usa os mesmos nomes.

| token | valor | significa |
|---|---|---|
| `--ink` | `#11243D` | texto principal, cabeçalho de tabela, botão pressionado |
| `--ink2` | `#1B3454` | texto secundário, links de ação, objeto da licitação |
| `--paper` | `#FFFFFF` | fundo da página |
| `--surf` / `--surf2` | `#FFFFFF` / `#F4F2EE` | superfícies (cards, tiles) / faixa de números e evidência |
| `--line` | `#DCD7CC` | toda borda |
| `--muted` | `#55606E` | legendas, metadados, rodapé |
| `--red` / `--reds` | `#B23A32` / `#F6E4E2` | **defeito, e só defeito** (ver §2) |
| `--teal` / `--teals` | `#1D6F63` / `#DDEAE7` | conferido, aprovado, "não se aplica" |
| `--amber` / `--ambers` | `#8A6A18` / `#F5EBD2` | precisa de olho humano: revisar, conflito, degradado |
| `--sans` | IBM Plex Sans | texto |
| `--mono` | IBM Plex Mono | números, códigos (`Q13`, controle, sha), eyebrow, links de origem |

Números sempre em `--mono` com `font-variant-numeric: tabular-nums` e
separador de milhar (`R$ 1.234,56`, `1.925 páginas`). `color-scheme: light`;
não há tema escuro no HTML atual e o site não inventa um.

## 2. Semântica das cores — regras que o projeto tratou como não negociáveis

Saíram de defeitos reais registrados nas sessões de 22-23/09/2026:

1. **Vermelho é defeito, e só defeito.** A barra da pergunta crítica era
   vermelha e uma linha perfeita parecia errada. Crítica virou **rótulo de
   texto** (`.marca`, "crítica"), nunca cor.
2. **A barra à esquerda da linha codifica o status, e nada mais:**
   teal `st-ok` = trecho conferido na página; âmbar `st-rev` = revisar
   (página corrigida, conflito, regra); vermelho `st-nl` = não localizado.
   "Não localizado" vence o veredito.
3. **Três estados visuais de ausência de evidência**, sempre presentes
   (o bloco de evidência aparece em TODAS as 17 linhas, mesmo vazio):
   `.naoaplica` (teal, "não se aplica a esta modalidade"),
   `.semev` (cinza itálico, "sem evidência: a informação não está nos documentos"),
   `.faltaev` (vermelho, "respondeu sem trecho — defeito").
4. **Condições de leitura ficam ACIMA do questionário** (`.cond`, `deg`/`ok`),
   e a tag de injeção (`.tagsusp`, "Prompt Injection - Conteúdo Suspeito") é
   deliberadamente mais forte que o resto do bloco.
5. **Custo desconhecido = "preço não configurado", nunca `R$ 0,00`.**
   93 relatórios do agente saíram dizendo "de graça". O JSON grava `null`.
6. **Botão morto é pior que botão nenhum.** O bloco "Verificar licitações
   novas" só aparece com backend vivo. No site: ação indisponível fica
   desabilitada **com o motivo no `title`**, nunca link que não faz nada
   (`sem extração` é o exemplo que já existe).
7. **Um card por controle, nunca por pasta** (ADR-013). O painel atual tem
   um por pasta e é um dos defeitos que não voltam (plano, §8).

## 3. Componentes do painel (`painel.css`)

| componente | classes | regra de conteúdo |
|---|---|---|
| Cabeçalho | `header`, `.eyebrow`, `h1`, `.sub` | eyebrow em mono vermelho ("Folha de pagamento · setor público"); sub explica a ordenação por prazo |
| Tiles | `.tiles > .tile(.ok/.al)` | `b` número mono 22px + `span` legenda. Painel: licitações, extraídas, fecham em ≤7 dias (`al` se >0), ancoragem N/M (`ok` só se N==M e M>0), conflitos achados, custo acumulado (+ "N sem preço" na v3). v3 acrescenta: para revisar, última coleta (e se foi cega), teto, **provedor vigente** |
| Barra | `.barra > input[type=search] + button[data-filtro][aria-pressed]` | filtro pressionado fica `--ink` sobre `--paper`. Filtros atuais: Todas · Fecham em ≤7 dias · Com conflito · Com alerta de regra · Já extraídas · Sem extração. v3 (plano §8): + Urgentes só ABERTAS (`dias ≥ 0`), Injeção suspeita, Retificadas, Revisão pendente, Encerradas, Ensaio |
| Contador | `<p class=sub><b id=conta>N</b> licitação(ões) na lista</p>` | sempre visível; `#vazio` quando 0 |
| Card | `article.card(.urgente/.aviso)` | borda esquerda 4px vermelha (≤7 dias) ou âmbar (≤20) |
| Card › topo | `.topo > div(.nome,.meta,.obj) + .prazo` | `.nome` = "Município/UF"; `.meta` = "Modalidade · controle" (só o que acrescenta: nunca repetir o nome da pasta); `.obj` = objeto[:340] |
| Card › prazo | `.prazo(.urgente/.aviso) > b + span` | ver §4 |
| Card › números | `.nums > .num(.ok/.al/.am)` | ancoragem `N/M` (`ok` se N==M>0, senão `al`); conflitos (`am` se >0); não localizado; revisar (`am` se >0); custo (`_brl` ou "preço não configurado"). Sem extração: um único `— ainda não extraída` |
| Card › alertas | `p.alerta` | até 3 alertas globais, 300 chars cada |
| Card › documentos | `details.docs > summary + table` | "Documentos do edital (N)"; colunas Tipo · Arquivo (link) · Pág. · SHA-256 (16 hex, `.sha`). v3: link por **id** (`/api/pdf/{slug}/{id}`), nunca pelo nome cru com `%` |
| Card › ações | `.acoes > a(.forte)` | `Ver as 17 respostas` (forte) ou `sem extração` (desabilitado com `title`); `Abrir no PNCP` (`target=_blank rel=noopener`). v3: + Reverificar, Processar (operador) |
| Últimas execuções | `h2 + table` | quando · o quê (`code`) · duração · custo (`td.gastou` âmbar se >0) · resultado. v3: página `/execucoes` com link do n8n |
| Rodapé | `footer` | "Gerado em … · Fonte: PNCP — dados abertos, Lei 14.133/2021 art. 54 · Nenhum dado pessoal é armazenado" |
| Ação viva | `.atual > .primario + .atualmsg`, `.achados`, `.progresso` | padrão "botão → achados com custo estimado → Processar as N / Agora não → progresso em mono". v3: `POST /api/acoes/verificar` (202) + `GET /api/execucoes/{id}` até `buscas` completar |

## 4. Regra do prazo (o campo que ordena a lista)

`dias = fim_prazo − hoje`, **calculado no navegador** em America/Sao_Paulo
(no HTML era congelado na geração: defeito que não volta).

| condição | classe | `b` | `span` |
|---|---|---|---|
| `dias` desconhecido e Q1 APROVADA com data | — | `sessão` / `sessão passou` | `em dd/mm/aaaa (da Q1)` |
| `dias` desconhecido | — | `—` | `prazo não informado` |
| `dias < 0` | — | `encerrado` | `há N dia(s)` |
| `0 ≤ dias ≤ 7` | `urgente` (vermelho) | `N dia(s)` | `até a sessão` |
| `8 ≤ dias ≤ 20` | `aviso` (âmbar) | `N dias` | `até a sessão` |
| `dias > 20` | — | `N dias` | `até a sessão` |

Ordenação: abertas por `dias` crescente → encerradas → sem prazo; nome
desempata. A data da Q1 só vale se o veredito for APROVADO.

## 5. Componentes do RELATORIO reaproveitados no detalhe (`relatorio.css`)

- **Tiles da verificação:** ancoragem N/M (`ok` se ≥ 95%), aprovadas sem
  ressalva, para revisão (`al` se >0), reprovadas (`al` se >0, `ok` se 0),
  críticas aprovadas N/7, custo (ou "preço não configurado").
- **Nota "Como conferir"** (`.nota`, borda vermelha): explica página física,
  evidência conferida por string sem IA, crítica = move o lance, "o vermelho,
  aqui, é sempre defeito".
- **Alertas globais** (`h2 + .nota`, "⚠ RN-xx: …").
- **Condições** (`.cond.deg|.ok`, `.tagsusp`, `ul li`, `.meta` com
  provedor/modelo/effort).
- **Legenda** (`.legenda > .lg.lg-ok|lg-rev|lg-nl + .lgnota`).
- **Tabela das 17:** `#` (`.qid` + `.perg` + `.marca` crítica) · Resposta
  (+ `details` "ver evidência" com `blockquote`, ou o estado de ausência) ·
  Origem (`.info a` mono teal: "arquivo — p. N" → `/api/pdf/{slug}/{id}#page=N`;
  ou `.nl` "não localizado") · Verificação (`.v.APROVADO|REVISAR|REPROVADO`).
- **Q13 estruturada:** `table.dist` com caption, `.dl` faixa, `.dq` quantidade,
  `.db` barra proporcional, `.dv` valor, `tr.dt` total, `.dok/.dbad/.dmut`,
  `.avisodist` quando a pirâmide não fecha, `.somatot`.
- **Divergências entre documentos** (tabela `#`, o que diverge, resposta adotada).
- **Documentos lidos** (arquivo, páginas). v3 acrescenta status do arquivo
  (ok, recusado, fora do inventário) e procedência.
- **Rodapé:** modelo · chamadas · tokens de entrada · "verificação
  determinística, sem IA".

## 6. O que a v3 acrescenta sem quebrar o estilo

- Badge de **procedência** no card e no detalhe: `api` · `agente` · `openai`
  · `simulado` · `reconstruída` — em `.marca` (rótulo), nunca em cor.
- **Histórico de verificações** com diff de vereditos por pergunta.
- **Linha do tempo** (`licitacao_eventos` + execuções do n8n com link).
- **Revisão humana inline** (operador) numa camada própria: nunca altera
  `respostas` nem `verificacoes`.
- Páginas novas com os mesmos blocos: `/execucoes`, `/emails` (corpo como foi
  enviado), `/saude`, `/admin` (provedor vigente com aviso de custo ao trocar;
  teto `NULL` por padrão com "~R$ 3-4 por edital").

## 7. Defeitos do HTML atual que NÃO voltam (plano §8)

link pelo nome cru com `%` (26-29 quebrados) → id numérico · filtro "≤7 dias"
incluindo encerradas → `dias ≥ 0` · `dias` congelado na geração → navegador ·
custo `null` como `R$ 0,00` → "preço não configurado" · um card por pasta →
por controle · JS com `SyntaxError` (`painel.py:565`) → sem HTML gerado para
a lista · `35_servidor.py:78` chamando função inexistente → W11.
