---
tipo: negocio
familia: negocio
status: verificado
atualizado: 2026-09-28
tags: [negocio, problema, dor, nucleo]
---

# Problema de negócio

> [!abstract] Em uma frase
> O banco disputa a compra de **folhas de pagamento públicas** em licitações, mas recebe a informação **tarde** (três dias depois da publicação, de um fornecedor que manda um PDF por e-mail), **cara** e **sem prova**, e depende de uma área inteira lendo documentos que se contradizem — enquanto concorrentes com software próprio leem o portal público direto, muitas vezes antes da data oficial de publicação.

## Papel na solução

É o ponto de partida: a dor que a solução existe para resolver, contada com o que o banco informou e com exemplos tirados dos documentos reais. Todas as escolhas técnicas deste vault respondem a um dos três problemas desta nota — tempo, custo e confiança.

## O negócio

Um órgão público — prefeitura, estado, autarquia, tribunal, câmara — concede a uma instituição financeira o direito de processar e pagar a folha dos seus servidores, em geral com exclusividade e por prazo determinado, e **recebe** por isso. O banco paga porque o que compra é uma **base de clientes**: conta-salário, crédito consignado de baixo risco, cartões, seguros, investimentos ([[Cessão onerosa da folha - fundamentos]]).

Para dar o lance certo, o banco precisa responder, para cada licitação, as **17 perguntas** do questionário da área: a data da sessão, o valor mínimo (com o rótulo exato), a vigência, a infraestrutura exigida, a pirâmide salarial, o total de servidores, a garantia e outras dez ([[Questionário — as 17 perguntas]]).

## A dor

> [!info] Informado pelo banco
> - **Uma área de 26 pessoas** lê editais e anexos que frequentemente se contradizem — datas alteradas por aviso, valores com rótulos diferentes em documentos diferentes, pirâmides espalhadas em várias tabelas.
> - **Um fornecedor terceirizado** entrega o material, e o trabalho dele é, literalmente, **mandar um PDF por e-mail** — por cerca de **R$ 100 mil por ano**.
> - **O material chega em D+3**: três dias depois da publicação da licitação.
> - **A regra interna dá 5 dias para atacar a folha** a partir da publicação. Com D+3, **sobram 2 dias** para analisar o documento, decidir e preparar o lance.
> - **Os concorrentes têm software próprio** e leem a API do PNCP diretamente — e, em vários casos, a API disponibiliza a licitação e os documentos **antes** da data de publicação.
> - **O que está em jogo:** o banco investe cerca de **R$ 1,05 bilhão por ano** na compra de folhas de pagamento.

Os três problemas se somam: **tempo** (dois dos cinco dias consumidos antes de começar), **custo** (pagar por algo que é público e consultável por máquina) e **confiança** (uma resposta sem fonte não se confere — e o erro plausível não aparece).

## Por que é automatizável

- O insumo é **público e completo por força de lei**: o art. 54 da Lei 14.133/2021 obriga a publicação do **inteiro teor** do edital e anexos no PNCP, com acesso gratuito, sem cadastro e por API documentada ([[Lei 14.133-2021 - visão geral]]).
- O valor do fornecedor não está no **acesso**, que é público — está na **leitura**. E ler, com prova, é exatamente o que a solução faz.

## As divergências são reais — exemplos dos documentos

| Licitação | O que um leitor desatento erra |
|---|---|
| Bertioga/SP | a sessão do edital foi **suspensa** por comunicado posterior; "1.896 servidores" são **vínculos**, não pessoas; a pirâmide **exclui** aposentados e está **truncada** (faltam 488 vínculos, nas faixas mais altas); o valor aparece com **três rótulos**; os "10% de garantia" estavam só num pedido de esclarecimento |
| São Lourenço do Sul/RS | três arquivos "Edital" ativos — dois dizem valor **estimado**, um diz valor **mínimo**; a pirâmide está em **três tabelas** (ler a primeira dá 287 em vez de 1.782) |
| Pirapó/RS | o edital licita ativos, inativos e pensionistas; a minuta de contrato, só os Poderes — **31,9% da folha** de diferença; o edital pune a perda de uma garantia que não exige |

Detalhe em [[Gabaritos]].

## O tempo que existe, medido

Entre o registro de uma licitação de folha no PNCP e o fim do prazo de propostas há, em mediana, **16 dias úteis** (198 licitações medidas em 23/09/2026; 94,4% com ao menos 10) — e há casos em que o registro aparece no portal no próprio dia da sessão ([[Lei 14.133-2021 - visão geral]]). Cada dia de atraso na chegada da informação sai desse tempo.

## O mercado

Medido pela própria solução no histórico do PNCP (28/09/2026): **2.071** licitações de folha, **726** com comprador, **R$ 5,56 bilhões** homologados, **79** instituições compradoras, e **284** licitações desertas ou fracassadas — que costumam voltar ao portal ([[Concorrência e mercado]]).

## O que a solução não é

- não é sistema de gestão de folha nem plataforma de consignado;
- não cobre empresas privadas — só o setor público ([[ADR-001 Escopo somente setor público]]);
- não decide o lance nem dá parecer jurídico: entrega as respostas com prova, a fila do que precisa de olho humano e o contexto de mercado.

## Relacionadas

[[MOC Negócio]] · [[Proposta de valor]] · [[Ganho para o negócio]] · [[Quem usa a solução]] · [[Concorrência e mercado]] · [[Cessão onerosa da folha - fundamentos]] · [[Visão geral da solução]]
