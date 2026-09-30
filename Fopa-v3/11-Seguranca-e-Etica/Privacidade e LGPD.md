---
tipo: etica
familia: seguranca-e-etica
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - api/site.py
  - api/oauth.py
  - api/sessao.py
  - api/storage.py
  - scripts/fopa/questionario.py
tags: [etica, lgpd, privacidade, dados-pessoais]
---

# Privacidade e LGPD

> [!abstract] Em uma frase
> A solução trata dois tipos de dado pessoal — o **nome e o e-mail de quem entra no site** e os **dados de servidores que podem aparecer em anexos de editais públicos** —; a pergunta que ela faz aos documentos é **agregada** (quantos servidores por faixa salarial, nunca quem), os documentos ficam **no Brasil**, num bucket **privado**, abertos só a quem está logado, e nada é compartilhado, vendido ou usado para treinar modelos.

## Papel na solução

Um banco regulado só pode usar uma ferramenta que trate dado pessoal com base legal, finalidade clara e mínimo necessário. A privacidade aqui vem do **desenho** — as perguntas pedem agregados — e é reforçada por controles de acesso e de localização.

## Os dados pessoais envolvidos

| Titular | Dado | De onde vem | Para quê |
|---|---|---|---|
| quem usa o site | **nome e e-mail** (escopos `openid email profile` do Google) | o login | identificar a pessoa, decidir o que ela vê e faz, registrar quem decidiu cada revisão, enviar os dois e-mails do produto |
| servidores públicos | nome, matrícula, cargo e salário — quando um órgão publica anexo nominal | os documentos da licitação no PNCP | **nenhum uso individual**: a solução pergunta pela **pirâmide** (quantidade por faixa) e pelo **total**; o documento é guardado como evidência da citação |
| agentes públicos | nome em assinatura e em ato | os documentos | nenhum: é ato público no exercício da função e não é alvo da extração; a tarja de assinatura é removida do texto antes da leitura das tabelas |

## Por que o tratamento é legítimo

| Fundamento | O que diz | Consequência |
|---|---|---|
| Lei 14.133/2021, arts. 54 e 174 | o inteiro teor do edital é publicado no PNCP, obrigatório para todos os entes | os documentos são **atos de publicidade obrigatória** |
| Lei 12.527/2011 (LAI), art. 8º, §3º, III | o órgão deve *possibilitar o acesso automatizado por sistemas externos em formatos abertos, estruturados e legíveis por máquina* | a coleta automatizada é o acesso que a lei manda existir ([[Legalidade da automação]]) |
| LGPD (Lei 13.709/2018), art. 7º, IX — legítimo interesse | base para o tratamento privado de dado já público | vale com duas condições que a solução cumpre: o dado é **público por obrigação legal** e a finalidade é **avaliar uma licitação**, não perfilar pessoas |
| LGPD, princípios de finalidade e necessidade (art. 6º) — para os usuários do site | o dado de login se limita ao necessário para prestar o acesso e controlar quem vê e faz o quê, e isso é informado na política de privacidade | só nome e e-mail |

> [!danger] O que o legítimo interesse não cobre
> Cruzar dado da folha com base de clientes, enriquecer cadastro ou extrair nomes de servidores. A solução lê **agregados**; se um dia passar a extrair nomes, a base legal muda e precisa ser refeita. O acesso ao documento público é resolvido pela LAI; o tratamento de dado pessoal continua sob a LGPD.

## Os princípios, na prática

| Princípio | Como se concretiza |
|---|---|
| **Finalidade** | só as 17 perguntas sobre a licitação; nada é extraído "por via das dúvidas" |
| **Minimização** | a Q13 pede quantidade por faixa, nunca registro individual; do Google, só nome e e-mail |
| **Localização** | banco e documentos na AWS em **São Paulo**; e-mail pelo Resend com o domínio configurado na região São Paulo |
| **Segurança** | bucket privado; o PDF só abre para quem está logado, por URL assinada de 10 minutos; sessão com cookie `HttpOnly` e `Secure`, e só o hash do identificador no banco ([[Controle de acesso e segredos]]) |
| **Processamento local onde há documento inteiro** | OCR local: o documento **não** vai a serviço de terceiro para ser lido; o que vai ao modelo de IA é o texto da licitação, pela API contratada, na extração pedida |
| **Transparência** | a [[Página Privacidade]] pública diz o que é coletado, para quê, onde, por quanto tempo e como exercer direitos; cada resposta é rastreável até arquivo e página |
| **Não uso secundário** | nenhum dado é vendido ou compartilhado; nada é usado para publicidade ou para treinar modelos |

## Direitos e retenção

- **Usuários do site:** acesso, correção e exclusão pelo contato indicado na página de privacidade; o cadastro fica enquanto o acesso existir, e a remoção apaga cadastro e sessões (o histórico de quem decidiu uma revisão guarda o e-mail como texto, para auditoria).
- **Documentos públicos:** ficam como evidência das respostas publicadas.

## O que depende do banco

A adoção formal numa instituição financeira pede documentos internos que não são da ferramenta: **relatório de impacto à proteção de dados (RIPD)**, **parecer do encarregado (DPO)**, **política de retenção** dos documentos e **política interna de uso de IA** com documentos externos ([[Próximos passos]]).

> [!aviso] Leitura de engenharia, não parecer jurídico
> A análise acima parte do texto legal, com cada afirmação apontando o artigo. Para peça formal, passa pelo jurídico do banco.

## Relacionadas

[[MOC Segurança e Ética]] · [[Página Privacidade]] · [[Login com Google]] · [[Legalidade da automação]] · [[Armazenamento de arquivos (S3)]] · [[Controle de acesso e segredos]] · [[Premissas éticas e matriz de cenários]] · [[MOC Legal]]
