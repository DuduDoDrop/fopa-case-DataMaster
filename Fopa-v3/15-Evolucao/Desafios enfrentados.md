---
tipo: referencia
familia: evolucao
status: verificado
atualizado: 2026-09-28
fontes:
  - histórico do repositório (22/09 a 28/09/2026)
  - notas de decisão e de avaliação deste vault
tags: [evolucao, desafios, licoes, qualidade]
---

# Desafios enfrentados

> [!abstract] Em uma frase
> Os problemas que mais custaram na construção não foram de IA: foram a **fonte** (um portal público com três serviços de confiabilidade diferente), os **documentos** (arquivos que não são o que dizem ser), a **reprodutibilidade** (o mesmo OCR lendo diferente em outra máquina), a **identidade** dos dados e o **próprio instrumento de medição**; cada um virou uma regra, um teste ou uma trava que está em produção.

## Papel na solução

Mostra de onde vieram as proteções que parecem excessivas à primeira vista — a trava de ensaio no banco, o hash das migrações, o OCR com versão fixa, o número de controle como única identidade — e o que cada uma impede. Cada linha diz **o que aconteceu, o que foi feito e o que garante hoje**.

## 1. A fonte de dados não é uma API só

| | |
|---|---|
| **O que aconteceu** | o PNCP são três serviços com comportamentos diferentes. O de documentos ficou fora do ar por dias numa semana de construção; o de consulta tem limite de ritmo e três modos de falha distintos (espera, erro do servidor, conexão derrubada); e uma **página curta no meio** do conjunto não significa fim — tratar como fim fazia ler só 2,3% do que a API entregava. A busca perdia licitações não por vocabulário, e sim por parar na página 2. |
| **O que foi feito** | paginação explícita, com cada página gravada antes de pedir a próxima; novas tentativas por tipo de falha; ritmo medido, não escolhido; rodada **cega** registrada como diferente de "nada novo" |
| **O que garante hoje** | "não consegui olhar" nunca aparece como "não há nada"; o alerta e a saúde mostram a rodada cega ([[Disponibilidade do PNCP]], [[W01 Descoberta]], [[W00 Saúde]]) |

## 2. O arquivo não é o que diz ser

| | |
|---|---|
| **O que aconteceu** | a extensão `.pdf` do PNCP é sufixo, não formato: dos 2.252 arquivos ".pdf" do acervo medidos em 23/09, 2.185 eram PDF de verdade — o resto era Word ou Excel, ZIP (alguns com outro ZIP dentro), RAR ou formato não identificado —, e 15 licitações não tinham **nenhum** arquivo que abrisse. Depois vieram o PDF dentro de assinatura digital, o PDF de zero páginas e conversões que travavam |
| **O que foi feito** | o formato é identificado pelo conteúdo; o que não é PDF passa por um fluxo de exceção que converte (LibreOffice, `bsdtar`), com tempo-limite que encerra o processo inteiro e aviso quando o PDF sai cortado |
| **O que garante hoje** | nenhum arquivo fica "ok" sem ser um PDF legível; o que não converte fica com o motivo escrito ([[Conversão de formatos]], [[ADR-017 O arquivo que não é PDF vira PDF]], [[W21 Baixar]]) |

## 3. O mesmo OCR lê diferente em outra máquina

| | |
|---|---|
| **O que aconteceu** | a versão do Tesseract que as distribuições Linux instalam (5.3) muda vereditos; e mesmo a 5.4.0 compilada não reproduziu byte a byte a máquina das primeiras medições — 0 de 6 páginas idênticas, similaridade mínima de 0,9922; numa tabela salarial, uma lia o fio vertical da tabela como "\|", a outra como o algarismo "1" |
| **O que foi feito** | versão do OCR e modelo de idioma **fixados por sha256** no *build*; a imagem virou a referência; seis páginas digitalizadas versionadas como linha de base |
| **O que garante hoje** | o *build* falha se a versão ou o idioma mudarem; o `/health` recusa OCR errado; em 28/09 o servidor de produção reproduziu a imagem local página por página ([[ADR-008 OCR — stack, configuração e limites]], [[OCR]]) |

## 4. A mesma licitação com dois nomes — e duas com o mesmo nome

| | |
|---|---|
| **O que aconteceu** | o nome da pasta virou, sem ninguém decidir, a chave de "já temos isso?". O defeito apareceu **quatro vezes**, nos dois sentidos: uma licitação com dois nomes (pelo município e pelo órgão) e seis licitações diferentes com o mesmo nome — numa das vezes, 30 de 172 licitações foram descartadas em silêncio |
| **O que foi feito** | o **número de controle do PNCP** é a identidade; o nome é só endereço |
| **O que garante hoje** | o banco identifica cada licitação pelo controle; a importação do acervo casou tudo por ele, sem consultar nome de pasta ([[ADR-013 Identidade de licitação é o número de controle]], [[Modelo de dados]]) |

## 5. O filtro de escopo errava para os dois lados

| | |
|---|---|
| **O que aconteceu** | uma terceirização de consignado passou pelo filtro, custou uma extração e voltou com 6 de 17 respostas vazias; na direção oposta, o filtro perdia 5 licitações de folha — duas nunca usam a palavra "folha", e uma delas envolvia 2.210 servidores; e uma justificativa colada no campo do objeto chegou a decidir o escopo |
| **O que foi feito** | a regra reescrita a partir dos documentos reais (o objeto nomeia instituição financeira ou declara cessão onerosa); 23 casos julgados à mão versionados como suíte; o Jev como segundo sinal; o rótulo humano prevalecendo; e o site mostrando só o que a IA confirma como folha depois de ler o edital |
| **O que garante hoje** | o filtro é testado a cada mudança; a discordância entre regra e IA vira fila de revisão ([[Regras antes de IA]], [[Escopo — o que é licitação de folha]], [[ADR-019 O site mostra só o que a IA confirma como folha]]) |

## 6. Um ensaio sobrescreveu um resultado real

| | |
|---|---|
| **O que aconteceu** | uma execução com o provedor simulado — que responde por expressões regulares, sem modelo — gravou por cima da extração real de uma licitação do acervo; em outro ponto, a reverificação apagava a procedência da verificação anterior |
| **O que foi feito** | a trava passou para o **banco**: resultado simulado ou gravado só pode ser o vigente de uma licitação marcada como ensaio; a reverificação cria uma verificação nova, com a versão das regras, e nunca apaga a anterior |
| **O que garante hoje** | gatilhos no Postgres recusam a gravação; um invariante confere que nenhum simulado está vigente fora de ensaio ([[Controles de consistência]], [[W30 Reverificar em lote]]) |

## 7. O instrumento de medição também erra

| | |
|---|---|
| **O que aconteceu** | a primeira comparação deu 0 de 13 respostas ancoradas para o modelo mais barato — e o defeito era do verificador, não do modelo; uma taxa de retificação medida em 4,8% era 0,6% (o inventário contava arquivos recusados como novos); um recall de busca publicado teve de ser retirado por denominador errado |
| **O que foi feito** | todo resultado guarda a evidência de cada resposta; toda regra declara quando não conseguiu ler; um número que despenca acusa primeiro o medidor; o que foi retirado fica registrado como retirado |
| **O que garante hoje** | a reverificação a custo zero refaz qualquer medição sobre as respostas gravadas ([[A medição que mediu o medidor]], [[ADR-011 Uma regra precisa saber quando falhou em ler]], [[Variância e como citar números]]) |

## 8. O trecho existe, mas sustenta a resposta?

| | |
|---|---|
| **O que aconteceu** | a ancoragem prova que o trecho citado está na página citada — não que ele sustenta a resposta; esse ponto cego foi medido |
| **O que foi feito** | o Jev lê cada resposta com o trecho e dá uma nota de sustentação; nota baixa não muda veredito, entra como sinal para a revisão; e o campo estruturado do PNCP, que contradisse o edital em 5% dos casos medidos, é cruzado como **alerta**, nunca como resposta |
| **O que garante hoje** | a fila de revisão recebe as respostas mal sustentadas com o motivo ([[Jev — score de escopo e sustentação]], [[Verificador determinístico]]) |

## 9. Leituras longas e processos que morrem no meio

| | |
|---|---|
| **O que aconteceu** | processos grandes levaram 776 s e 881 s para ler, e o fluxo desistia com o texto quase pronto; depois de um reinício, jobs que estavam em execução ficaram "vivos" para sempre no banco |
| **O que foi feito** | a espera da leitura subiu para até 40 minutos; no arranque, o worker declara órfão todo job ativo, e o fluxo que esperava trata como falha, com *backoff* |
| **O que garante hoje** | nenhuma licitação fica presa num estado intermediário; a próxima tentativa retoma do ponto certo ([[W22 Ler]], [[Worker — visão geral e jobs]]) |

## 10. Custo real diferente do custo estimado

| | |
|---|---|
| **O que aconteceu** | o preço da OpenAI não tinha fonte pública conferida e precisou ser derivado da fatura; o documento ia sem cache e era pago cheio a cada lote; na OpenAI, a gravação em cache chegou a ser contada duas vezes |
| **O que foi feito** | o custo é conferido na fatura; o documento vai antes das perguntas e em cache (−32,5% no Claude em contexto completo, com a mesma acurácia); a gravação de cache da OpenAI entra uma vez, a 1,25× |
| **O que garante hoje** | o custo de cada chamada é gravado na hora, e preço desconhecido fica nulo, nunca zero ([[Custo por edital]], [[Cache de prompt e ordem do prompt]], [[Antes e depois da v3.1]]) |

## 11. Duas instalações processando ao mesmo tempo

| | |
|---|---|
| **O que aconteceu** | uma instalação de desenvolvimento com os fluxos agendados publicados coletaria no PNCP e mandaria e-mails em dobro com a produção |
| **O que foi feito** | a importação dos fluxos escolhe o que publicar; a instalação de desenvolvimento publica só os subfluxos, que não têm agenda |
| **O que garante hoje** | o modo de demonstração sem agenda está documentado e é o recomendado ([[Como rodar em outra máquina]]) |

## Relacionadas

[[MOC Evolução]] · [[Linha do tempo da construção]] · [[Próximos passos]] · [[Decisões de construção da v3]] · [[MOC Avaliação]] · [[Controles de consistência]]
