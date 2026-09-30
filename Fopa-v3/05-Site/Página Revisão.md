---
tipo: pagina
familia: site
rota: "/revisao"
papel_minimo: usuario
status: verificado
atualizado: 2026-09-30
fonte_codigo:
  - web/src/paginas/Revisao.tsx
  - api/site.py
  - api/consultas.py
  - db/006_publicacoes_revisoes_rotulos_gabaritos_itens_api.sql
  - db/031_rotulo_humano_prevalece.sql
tags: [site, pagina, revisao, humano-no-loop]
---

# Página Revisão

> [!abstract] Em uma frase
> A fila dos itens que **exigem revisão humana**: as **respostas a revisar** — as que o verificador reprovou ou deixou em revisão numa pergunta crítica —, para alguém aceitar, corrigir ou rejeitar, com o passo a passo na própria tela; e, só para administradores, a aba **Escopo**, com as licitações em que a IA discorda da regra de escopo, para rotular "é folha" ou "não é folha".

## Papel na solução

É o **humano no processo** ([[Premissas éticas e matriz de cenários]]). O sistema nunca decide sozinho o que não conseguiu provar: publica com o selo e manda para cá. A decisão humana fica numa **camada própria**, com nome e data — a resposta do modelo e o veredito do verificador **não mudam**, e o histórico continua auditável.

![[site-revisao.jpg]]

## Respostas a revisar

**Em produção (29/09/2026):** 5.685 respostas a revisar.

### Como se usa
Quem não é administrador vê o título **Respostas a revisar (N)**, sem botão; o administrador vê as abas **Respostas (N)** e **Escopo**. Logo abaixo vem o passo a passo que a própria tela mostra, e depois a busca:
1. **Buscar** a licitação por município, órgão, modalidade, número de controle ou objeto. Sem busca, a página não carrega a fila: pedir as milhares de respostas de uma vez travava o navegador.
2. **Selecionar** a licitação na lista, que mostra quantas respostas ela tem a revisar e quantas são críticas. Abrem-se as respostas dela, só da **verificação vigente**, no formato da tabela do detalhe: resposta, evidência, origem com link para a página do PDF e veredito.
3. **Conferir** cada resposta no documento de origem, pelo link da coluna Origem.
4. **Registrar a decisão:** Aceita (resposta correta), Corrigida (informe a resposta correta) ou Rejeitada (sem base nos documentos), com uma nota opcional.

### O que entra na fila
Aberto pelo [[W24 Verificar e publicar]] (passo "Abrir revisões"): toda resposta **REPROVADA**, toda **REVISAR em pergunta crítica** e a licitação inteira quando há suspeita de **injeção de prompt**. Resultados simulados não entram.

### Quem decide
Qualquer usuário logado ([[Papéis e acesso]]).

## Aba Escopo (só administradores)

![[site-revisao-escopo.jpg]]

**Em produção (30/09/2026):** 1 pendente (o Jev discordou da regra com convicção e ninguém rotulou); as 281 já rotuladas ficam fora da lista.

- A lista mostra **só as pendentes**: as licitações em que o **Jev discorda da regra com convicção** (nota ≤ 25% quando a regra diz "dentro", ou ≥ 75% quando diz "fora") e **ainda sem rótulo**. Desde 30/09/2026, a que recebe rótulo sai da lista; o rótulo continua valendo no card, no painel e no analytics, e pode ser refeito pelo formulário, com o número de controle.
- Colunas: a licitação (controle, modalidade e objeto), o que a **regra** decidiu e por quê, a opinião do **Jev** ("IA: não é folha (25%)", "discorda da regra") e o **rótulo humano** atual, com o motivo.
- **Rotular:** "dentro" ou "fora", com motivo. O rótulo humano **prevalece** na tela, na fila e no analytics ([[Escopo — o que é licitação de folha]]); um rótulo "dentro" numa licitação que a regra tinha mandado para fora a devolve à fila.
- É também o **gabarito** que mede a regra e o Jev ([[Gabaritos]]).

## De onde vêm os dados

| Parte | Rota da API | Fonte |
|---|---|---|
| totais e busca | `GET /api/fila-revisao/licitacoes?q=` | `revisoes_humanas` (abertas, da vigente) + `v_card` |
| campos de uma licitação | `GET /api/fila-revisao?controle=` | `revisoes_humanas` + `verificacao_respostas` + `respostas` |
| decisão | `POST /api/revisoes` | grava em `revisoes_humanas` |
| aba Escopo | `GET /api/rotulos-escopo` · `POST /api/rotulos-escopo` | `sinais_jev`, `licitacoes`, `rotulos_escopo` |

## Relacionadas

[[MOC Site]] · [[Página Detalhe da licitação]] · [[W24 Verificar e publicar]] · [[Jev — score de escopo e sustentação]] · [[Escopo — o que é licitação de folha]] · [[Premissas éticas e matriz de cenários]] · [[Papéis e acesso]]
