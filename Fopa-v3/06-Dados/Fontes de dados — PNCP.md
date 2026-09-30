---
tipo: referencia
familia: dados
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/pncp.py
  - n8n/workflows/W01.json
  - n8n/workflows/W21.json
  - n8n/workflows/W70.json
  - api/historico_pncp.py
  - api/contratos_pncp.py
  - api/descoberta_historica.py
  - db/012_seed.sql
tags: [dados, pncp, api, coleta]
---

# Fontes de dados — PNCP

> [!abstract] Em uma frase
> Tudo o que a solução sabe sobre licitações vem do **Portal Nacional de Contratações Públicas**: a **busca** acha as licitações pelos termos, `/arquivos` entrega os documentos, `/itens` e `/resultados` dizem quem venceu e por quanto, e a busca de **contratos** traz o contrato assinado com os aditivos — sempre com identificação, esperas conservadoras e sem contornar nenhum controle.

## Papel na solução

O PNCP é a fonte pública e obrigatória do inteiro teor dos editais (Lei 14.133/2021, art. 54), com API aberta, gratuita e sem cadastro ([[ADR-002 PNCP como fonte primária]]). A solução consome três serviços dele, com confiabilidades diferentes ([[Disponibilidade do PNCP]]).

## Os serviços e os endpoints usados

| Serviço | Endpoint | O que traz | Quem usa |
|---|---|---|---|
| **Busca** (`api/search`) | `GET /api/search/?q=<termo>&tipos_documento=edital&status=…&anos=…&tam_pagina=50&pagina=N` | licitações que casam com o termo: número de controle, órgão, UF, município, modalidade, objeto, situação, datas, data de atualização no PNCP | [[W01 Descoberta]]; a descoberta histórica (ano a ano, desde 2021) |
| **Busca de contratos** | `api/search` com `tipos_documento=contrato` | contratos assinados que casam com os termos | [[W41 Histórico do PNCP]] |
| **Documentos** (`api/pncp/v1`) | `GET /orgaos/{cnpj}/compras/{ano}/{sequencial}/arquivos` | a lista de documentos da compra (sequencial, tipo, título, se está ativo, URL) | [[W21 Baixar]], [[W70 Retificações]] |
| **Itens e resultados** (`api/pncp/v1`) | `…/compras/{ano}/{sequencial}/itens` e `…/itens/{n}/resultados` | cada item (situação, valor, critério de julgamento) e o resultado (fornecedor, valor homologado, data, cancelamento) | [[W41 Histórico do PNCP]]; o verificador usa os itens como conferência cruzada |
| **Contrato e termos** (`api/pncp/v1`) | `/orgaos/{cnpj}/contratos/{ano}/{sequencial}` e `/termos` | o vínculo com a compra, valores inicial e global, vigência, e os termos aditivos | [[W41 Histórico do PNCP]] |
| **Consulta** (`api/consulta/v1`) | cabeçalho da compra, varredura por data e modalidade | valores estimado e homologado, situação | [[W41 Histórico do PNCP]] (cabeçalhos, com tempo limitado) |

## Os termos de busca

Seis termos, na tabela `termos`, editáveis na [[Página Admin]], cada um lido em até 10 páginas de 50 itens:

- "cessão onerosa folha de pagamento"
- "folha de pagamento servidores instituição financeira"
- "folha de pagamento instituição bancária"
- "créditos da folha de pagamento"
- "créditos provenientes da folha de pagamento"
- "folha salarial instituição financeira"

Cada termo gera **duas consultas** por rodada — o recorte do ano (`status=todos`, `anos=2026|…|ano atual`) e tudo o que está **recebendo proposta** (sem ano) —, juntadas pelo número de controle. Os resultados passam pela regra de escopo antes de qualquer coisa ([[Regras antes de IA]]).

## Conduta da coleta

- **Identificação:** todo pedido leva um `User-Agent` que diz o que é o sistema, para que serve e um contato.
- **Esperas conservadoras:** 429, 5xx e queda de rede esperam 30 segundos e repetem uma vez no fluxo (o reprocessamento longo é da fila); o histórico faz uma pausa entre licitações; os cabeçalhos da API de consulta rodam depois da descoberta, porque as duas dividem o limite por IP.
- **Só o necessário:** documentos de licitações de folha no escopo; o agregado da pirâmide, nunca listas nominais de servidores ([[Privacidade e LGPD]]).
- **Nada contornado:** nenhum login, captcha ou controle de acesso — a API é pública e o consumo automatizado é o uso pretendido ([[Legalidade da automação]]).

## Particularidades dos dados que a solução trata

| Particularidade | Tratamento |
|---|---|
| a extensão `.pdf` não garante o formato | o formato é descoberto pelos bytes; o que não é PDF é convertido ([[ADR-017 O arquivo que não é PDF vira PDF]]) |
| vários "Edital" ativos, sem indicação do vigente | precedência documental pelo sequencial ([[ADR-006 Documento vigente é o de maior sequencial]]) |
| sequencial com buracos | a lista vem sempre do `/arquivos`, nunca de 1 a N |
| o ano do número de controle não é o da sessão | o recorte usa a data da sessão ([[ADR-015 Acervo só de 2026 e só compra de folha]]) |
| `fim_prazo` de homologadas é a vigência do contrato, não a sessão | as telas de histórico mostram os motivos de estar lá (vencedor, revogada), não "dias até a sessão" |
| data de sessão digitada errado (2036 no lugar de 2026) | mais de 730 dias depois da publicação vira "sem data" no cartão ([[Funções e views do banco]]) |
| critério de julgamento do campo estruturado contradiz o edital | o edital manda; o verificador compara **famílias** de critério ([[Verificador determinístico]]) |
| homologado simbólico (até R$ 1) com contrato de valor real; compra cadastrada duas vezes | o Analytics conta pelo contrato e junta as duplicadas, com o ajuste mostrado na tela ([[Página Analytics de Mercado]]) |
| a busca é uma **janela móvel**, não um censo | números de corpus citados com a data da coleta ([[Variância e como citar números]]) |

## Relacionadas

[[MOC Dados]] · [[Disponibilidade do PNCP]] · [[Pipeline de dados]] · [[W01 Descoberta]] · [[W21 Baixar]] · [[W41 Histórico do PNCP]] · [[ADR-002 PNCP como fonte primária]] · [[ADR-013 Identidade de licitação é o número de controle]]
