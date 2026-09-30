---
tipo: tecnica
familia: ia
status: verificado
atualizado: 2026-09-28
fonte_codigo:
  - scripts/fopa/condicoes.py
  - api/leitura.py
  - api/injecao.py
  - api/rotas_extracao.py
  - web/src/componentes/Condicoes.tsx
tags: [ia, observabilidade, abstencao, confianca, antialucinacao]
---

# Consciência operacional

> [!abstract] Em uma frase
> O sistema **declara sob que condições leu** cada licitação — páginas que precisaram de OCR, texto escondido com cara de instrução para IA, fornecedor secundário, perguntas em que se absteve —, a partir de **fatos observados**, e não da confiança que o modelo declara sobre si mesmo; o site mostra isso **acima** das respostas.

## Papel na solução

O campo `confianca` da resposta vem do **modelo dizendo o quanto confia em si** — exatamente o tipo de autoavaliação que a solução rejeita em toda parte: um modelo confiante e errado é indistinguível de um modelo confiante e certo. A consciência operacional inverte a lógica: a incerteza é derivada do que o sistema **observou** sobre a própria execução. É a mesma separação da verificação aplicada à incerteza: quem gera a resposta não é quem a verifica, nem quem declara o quanto ela é confiável ([[Verificador determinístico]]).

O nome técnico do comportamento é **monitoramento de si em tempo de execução** (*runtime self-monitoring*), somado à **abstenção seletiva** (*selective prediction*): responder "não localizado" quando não há base, em vez de arriscar. O termo "consciência situacional emergente" foi avaliado e **não** é usado: descreve uma propriedade de modelo medida em laboratório de segurança, não algo que se constrói num pipeline consumido por API ([[Técnicas avaliadas e descartadas]]).

## O que cada verificação registra

| Condição | Como é observada | Efeito |
|---|---|---|
| **OCR** | a leitura congelada guarda quais arquivos e quantas páginas foram lidas por OCR (e se algum arquivo teve OCR forçado ou girado) | **degrada**: o texto foi *reconhecido*, não extraído |
| **Fornecedor secundário** | a execução rodou num provedor que não é o principal (o GPT, plano B) | **degrada** |
| **Texto furtivo suspeito** | a varredura do PDF acha texto que a máquina lê e o humano não vê (branco, transparente, corpo abaixo de 3 pt, fora da página) **e** que tem cara de instrução para IA | **tag "Prompt Injection - Conteúdo Suspeito"**, degrada e abre revisão humana ([[Injeção de prompt e defesas]]) |
| **Abstenções** | as perguntas respondidas com "não localizado" | listadas: "o sistema absteve-se em N pergunta(s)" |
| **Documentos e modelo** | quantos documentos foram lidos, o modelo e o esforço usados | exibidos na linha de rodapé do bloco |

- **A lista do que degrada é curta de propósito.** Marcar tudo como degradado é o mesmo que não marcar nada — um aviso que dispara sem motivo ensina o leitor a ignorá-lo, que é o pior destino de um aviso. Por isso o provedor `simulado` (ensaio, custo zero) **não** conta como secundário.
- **A tag de injeção é mais forte que o resto.** As outras condições dizem "leia com ressalva"; esta diz "alguém pode ter tentado manipular este documento" e muda o que se faz com ele antes do lance.
- **A confiança do modelo convive com as condições.** A divergência entre as duas é informação: modelo confiante sob condição degradada é precisamente o caso que merece olho humano.

## Onde aparece no site

No [[Página Detalhe da licitação|detalhe da licitação]], o bloco de condições fica **acima do questionário** — quem lê as respostas precisa saber antes, e não depois, se a leitura aconteceu com OCR num anexo ou com texto escondido:

- "Condições normais de leitura" ou "Esta leitura aconteceu sob condição degradada", com os motivos em português, não em flags;
- as abstenções;
- o "ver mais" com todo texto escondido que a varredura achou, os suspeitos primeiro, cada trecho com o que ele é (timbre, camada de OCR, planta, metadado de impressão);
- a linha de rodapé: modelo · esforço · documentos lidos.

## A mesma ideia no resto do pipeline

A consciência operacional não é um módulo: é um princípio aplicado em vários pontos, todos em produção.

| Onde | O que o sistema sabe e declara sobre si |
|---|---|
| Verificador, RN-15 | todo "não localizado" é listado, e cinco ou mais de uma vez apontam falta de insumo, não edital omisso |
| Regras do verificador | "RN-09 não aplicada": a regra diz quando **não conseguiu ler**, em vez de calar ([[ADR-011 Uma regra precisa saber quando falhou em ler]]) |
| Regra de escopo | objeto curto demais para decidir passa para revisão em vez de ser descartado ([[Regras antes de IA]]) |
| [[W01 Descoberta]] | uma rodada que não conseguiu consultar o PNCP é marcada **cega** — "nada a fazer" é diferente de "não consegui olhar" |
| [[W20 Processar uma licitação]] | um **disjuntor** para o processamento quando há 3 ou mais erros em 30 minutos sem nenhum sucesso |
| [[W23 Extrair]] | a vaga de extração respeita o teto de gasto do dia e o limite de simultaneidade; sem vaga, adia em vez de estourar |
| [[Best-of-N]] | uma chamada de reforço que volta sem a pergunta é silêncio, não resposta — nunca vira um "não localizado" inventado |
| [[W00 Saúde]] e `/health` | de hora em hora confere os serviços, a versão do OCR e a última coleta; o worker responde 503 se o OCR estiver fora do contrato |
| Custo | preço desconhecido é gravado como nulo e mostrado como "n/d", nunca como R$ 0,00 ([[Custo por edital]]) |

## Relacionadas

[[MOC IA]] · [[Verificador determinístico]] · [[Injeção de prompt e defesas]] · [[OCR]] · [[Página Detalhe da licitação]] · [[Saúde e observabilidade]] · [[Técnicas avaliadas e descartadas]] · [[ADR-011 Uma regra precisa saber quando falhou em ler]]
