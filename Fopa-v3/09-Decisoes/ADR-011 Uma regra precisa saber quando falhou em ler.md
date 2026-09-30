---
tipo: decisao
familia: decisoes
adr: 11
data: 2026-09-22
decisao: aceita
status: verificado
atualizado: 2026-09-28
tags: [decisao, verificador, avaliacao, nucleo]
---

# ADR-011 — Uma regra precisa saber quando falhou em ler

> [!abstract] Em uma frase
> Toda regra determinística do verificador **declara quando não conseguiu ler** o material, e esse estado é diferente de aprovar; tolerância vale para **identificador**, nunca para **evidência**; e toda métrica guarda a evidência que a produziu.

## Problema

Toda regra do verificador é uma expressão regular ou uma comparação de texto sobre algo que **outro sistema escreveu** — o modelo, o OCR ou quem redigiu o edital. Numa única sessão de medição (22/09/2026), **cinco regras diferentes reprovaram material correto**, sempre pelo mesmo motivo: o padrão cobria uma grafia e o mundo usava outra.

| Regra | Esperava | O mundo escreveu | Efeito |
|---|---|---|---|
| ancoragem | `01 - Edital - EDITAL.pdf` | `EDITAL.pdf`, `ARQUIVO 01 - Edital - EDITAL.pdf` | um modelo caiu para 0/13 |
| RN-09 | "de R$ X até R$ Y" | "R$ X a R$ Y: N", "2.001,00 > 3.000,00: 274" | somava 3 contra 297 numa pirâmide íntegra |
| RN-09 (total) | `1.896` | pontos removidos antes do casamento | lia 189 e **invertia** o alarme |
| gabarito | `09:00` | `09h00` | reprovou os três modelos na Q1 |
| RN-13 | definição de objeto | "ativo" dentro de "Legisl-ativo" | minuta sem população lida como se tivesse |

Nenhum desses erros era do modelo. O que os denunciou foi **regularidade onde deveria haver variação**: modelos diferentes erram de formas diferentes; quando erram igual, o que é igual entre eles é o código que os mede.

## Opções

| Opção | Avaliação |
|---|---|
| usar um modelo como juiz das respostas | devolveria a subjetividade que o sistema existe para eliminar |
| afrouxar o limiar da ancoragem | compra taxa de aprovação vendendo a única garantia do produto |
| deixar a regra calada quando não entende | foi o estado anterior: silêncio lido como conferência — o pior dos mundos, porque parece seguro |
| tolerar nome de arquivo ambíguo | em Bertioga há três `RESPOSTA.pdf`: a citação viraria decoração |
| **regra que declara quando não leu; tolerância só de identificador; evidência guardada** | adotada |

## Escolha

1. **Silêncio nunca significa "conferido":** com menos de duas faixas reconhecidas numa resposta que descreve pirâmide, a RN-09 emite "não aplicada — a pirâmide precisa de conferência humana".
2. **Tolerância resolve identificador, nunca evidência:** o nome citado é resolvido por apelido **só se** resolver para um único arquivo.
3. **Toda métrica guarda a evidência:** arquivo, página, trecho e alertas por resposta, com as causas de falha agrupadas.
4. **Corrigir a regra e remedir são passos separados** — e gratuitos, porque o verificador não usa IA e o texto está congelado.

## O que foi medido

Validação das cinco correções sem gastar um token: um modelo foi de 0/13 para 12/13 ancoradas em Pirapó; a RN-09 ficou silenciosa nos três modelos na pirâmide íntegra e apontou os 488 faltantes nos três na truncada; a RN-13 ficou silenciosa em 11 dos 13 editais consistentes; as 89 respostas de produção da época continuaram 89/89 ([[A medição que mediu o medidor]]).

## O que custa

- Mais estados para quem revisa entender: aprovado, reprovado e **não aplicada**.
- Regras mais longas, porque precisam detectar o próprio fracasso.
- A tolerância de identificador exige um teste de ambiguidade que também pode ter defeito.

## Onde vive em produção

- As mensagens "não aplicada" e "página corrigida" do [[Verificador determinístico]].
- `versao_regras` = hash do código das regras; mudar uma linha gera versão nova, e o [[W30 Reverificar em lote]] reaplica ao acervo a custo zero, gravando o diff.
- Falso positivo do verificador é tratado como defeito grave: ele é a peça em que o usuário confia sem reconferir.

## O que reabriria a decisão

É um princípio de método; o que muda são as regras, sempre por versão nova.

## Relacionadas

[[MOC Decisões]] · [[Verificador determinístico]] · [[A medição que mediu o medidor]] · [[Harness de avaliação]] · [[ADR-004 Evidência obrigatória]]
