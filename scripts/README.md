# scripts/ — o núcleo de extração e as medições

## `fopa/` — o pacote que a produção usa

O worker importa este pacote: é o mesmo código que produziu as medições da avaliação.

| Módulo | O que faz |
|---|---|
| `questionario.py` | as 17 perguntas, legíveis por máquina: termos, críticas, o que não se aplica a cada modalidade |
| `extrator.py` | monta o prompt (documentos antes das perguntas, com cache), chama o modelo em lotes e lê as respostas |
| `recuperacao.py` | a recuperação de páginas com BM25 — a camada RAG, sem embeddings |
| `melhor_de_n.py` | o Best-of-N: decide o que falhou e escolhe entre as tentativas pelo veredito do verificador |
| `verificador.py` | a verificação sem IA: ancoragem do trecho na página, guarda numérica e as regras de negócio |
| `distribuicao.py` · `condicoes.py` | a leitura estruturada da pirâmide salarial e as condições em que cada execução leu |
| `modelos.py` | a camada de modelo: provedores, preços e contabilidade de custo |
| `ocr.py` · `furtivo.py` | o OCR (Tesseract 5.4.0, perfil fixo) e o detector de texto escondido |
| `escopo.py` | a regra que diz o que é, e o que não é, licitação de folha |
| `pncp.py` | o cliente da API do PNCP |
| `jev.py` | o cliente do Jev (decisão tipada com probabilidade) |
| `pagina.py` · `painel.py` · `saida.py` | o relatório HTML por edital, o painel e as saídas da prova de conceito |
| `execucao.py` · `inventario.py` · `metadados.py` · `nomes.py` · `segredos.py` · `sintetico.py` | registro de execução, inventário de download, metadados, nomes de pasta, carga de segredos e editais sintéticos para teste |

## Os scripts numerados

São a prova de conceito e as medições que decidiram a arquitetura; cada um está citado nas notas de avaliação e de decisão do vault. Os principais:

| Script | Para quê |
|---|---|
| `10_extrair_edital.py` | extrair uma licitação pela linha de comando (com `--simulado`, sem chave) |
| `11_avaliar.py` · `15_acuracia.py` · `17_benchmark.py` · `34_placar.py` | o harness (modelos, esforços e modos sobre o mesmo edital), a acurácia contra gabarito, o quadro consolidado e o placar com custo real |
| `13_reverificar.py` · `14_reverificar_harness.py` | reverificar respostas gravadas, a custo zero |
| `21_adversarial.py` · `36_injecao_furtiva.py` | a bateria de injeção e de texto escondido |
| `22_recall.py` · `46_recall_recuperacao.py` | o recall da recuperação |
| `23_testa_escopo.py` | a suíte do filtro de escopo (roda no CI) |
| `35_antes_depois.py` | a medição antes e depois da v3.1 |
| `40_fumaca.py` | as garantias do verificador, sem chamar modelo (roda no CI) |
| `70_extracao_por_agente.py` | a extração por agente, sem API |
| `82_gastos_ia.py` | grava os gastos com IA efetivamente cobrados, que a página inicial do site mostra |

`deploy/` guarda os dois scripts que levaram o banco e os arquivos da instalação local para a produção.

Documentação: [MOC IA](<../Fopa-v3/07-IA/MOC IA.md>) · [Harness de avaliação](<../Fopa-v3/08-Avaliacao/Harness de avaliação.md>) · [Resultados medidos](<../Fopa-v3/08-Avaliacao/Resultados medidos.md>)
