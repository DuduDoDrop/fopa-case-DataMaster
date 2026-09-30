---
tipo: referencia
familia: reproducao
status: verificado
atualizado: 2026-09-29
tags: [reproducao, acesso, producao, site]
---

# Como acessar a versão no ar

> [!abstract] Em uma frase
> A solução está no ar em **https://licitacaofopa.com.br**: qualquer conta Google entra como **usuário** e vê o painel, o histórico, as análises de mercado, o detalhe de cada licitação com as respostas verificadas e a fila de revisão; as ações que chamam a automação ou gastam API são dos **administradores**.

## Papel na solução

É o caminho mais curto para ver a solução funcionando, sem instalar nada — o "link para acessar" que complementa as instruções de execução em outra máquina ([[Como rodar em outra máquina]]).

## Passo a passo

1. Abrir **https://licitacaofopa.com.br**.
2. Clicar em **"Entrar com Google"** e escolher a conta. O site lê só **nome e e-mail** ([[Login com Google]], [[Página Privacidade]]).
3. No primeiro acesso, o cadastro é criado como **usuário**, com acesso de leitura e à revisão de respostas.
4. Navegar:

| Onde | O que ver |
|---|---|
| [[Página Painel]] | as licitações de folha em andamento, com prazo, estado, custo e os filtros "fecham em até 7 dias", "com conflito", "já extraídas" |
| [[Página Detalhe da licitação]] | as 17 respostas com veredito, trecho literal e o link "arquivo p. N" que abre o PDF na página; as condições da leitura; a linha do tempo; os documentos |
| [[Página Relatório]] | o relatório da verificação vigente |
| [[Página Histórico]] | as licitações passadas, com a extração e a conferência |
| [[Página Analytics de Mercado]] e [[Página Analytics Histórico FOPA]] | quem compra folha, por quanto, até quando, e o que voltou ao portal |
| [[Página Revisão]] | a fila de respostas a conferir |
| [[Página Governança]] | os princípios, os controles e as normas que regem o uso de IA na solução |

5. **Ações da automação** (Extrair com IA, Processar, Reverificar, Verificar agora) e as páginas de operação (Execuções, E-mails, Saúde, Admin) exigem o papel de **administrador**, concedido pelo administrador supremo ([[Papéis e acesso]]).

## Para conferir que é a versão documentada

- O resumo público de saúde responde em `https://licitacaofopa.com.br/api/saude`.
- Para administradores, a [[Página Saúde]] mostra o contrato completo do worker, com o SHA do commit em execução (`ab55f759efcc…`, desde 30/09/2026), a versão do OCR e as versões das regras e do prompt.

## Relacionadas

[[MOC Reprodução]] · [[Como rodar em outra máquina]] · [[MOC Site]] · [[Papéis e acesso]] · [[Hospedagem na AWS]]
