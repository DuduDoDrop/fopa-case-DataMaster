# Reconciliação da migração — 2026-09-24

Seção 9, passo 8 do plano da v3. Gerado por `python -m migracao.relatorio`, só leitura do banco. Cada seção diz também quando está vazia.

## Importações

| id | snapshot | manifesto | início (UTC) | fim (UTC) | avisos | decisões |
|---|---|---|---|---|---|---|
| 1 | 2026-09-24_0150 | 458fb9f94576 | 2026-09-24 05:45 | 2026-09-24 05:45 | 1 | 0 |
| 2 | 2026-09-24_1201 | df79a4e3b078 | 2026-09-24 15:05 | 2026-09-24 15:05 | 1 | 0 |

Avisos:

- importação 1: experimento _injecao_furtiva sem controle (licitacao='_injecao_furtiva'): não importado
- importação 2: experimento _injecao_furtiva sem controle (licitacao='_injecao_furtiva'): não importado

## Contagens

| medida | valor |
|---|---|
| licitações | 2070 |
| pastas do legado | 770 |
| arquivos | 2734 |
| leituras (texto congelado) | 755 |
| execuções de modelo | 552 |
| verificações vigentes | 505 |
| verificações legadas vigentes | 491 |
| publicações | 528 |

**Licitações por estado:** fora_escopo 1190; publicada 505; preparada 237; fora_janela 77; nova 45; baixada_ok 6; formato_nao_suportado 6; falha_rede 4

**Arquivos por status:** ok 2520; alias_duplicado 134; zip_container 27; formato_nao_suportado 17; fora_inventario 12; recusado_politica 10; procedencia_incerta 9; ausente_no_disco 5

**Leituras por procedência do texto:** legado_paginas_json 741; worker 14

**Execuções por origem:** agente (canônica) 497; simulado (não canônica) 22; harness (não canônica) 18; api (canônica) 10; agente (não canônica) 3; experimento (não canônica) 2

## Controles com mais de uma pasta

5 controle(s). Todas as pastas entraram em `pastas_legado`; a canônica é a que dá os metadados e a leitura vigente.

| controle | pasta | canônica | motivo |
|---|---|---|---|
| 04035135000143-1-000015/2026 | Dispensa - Rio Branco-AC | sim | única pasta com execução |
| 04035135000143-1-000015/2026 | Dispensa - Tribunal De Contas Do Estado Do Acre-AC | não | — |
| 08145153000139-1-000049/2026 | Pregão - Eletrônico - Passagem-RN | não | — |
| 08145153000139-1-000049/2026 | Pregão - Eletrônico - Passagem-RN - 49-2026 | sim | as outras pastas leram PDF fora do inventário |
| 18449140000107-1-000075/2026 | Pregão - Eletrônico - Fronteira-MG | sim | sem execução: pasta de referência para metadados e leitura |
| 18449140000107-1-000075/2026 | Pregão - Eletrônico - Fronteira-MG - 75-2026 | não | — |
| 58197948000169-1-000025/2026 | Pregão - Eletrônico - Caixa De Assistencia  Ao Servidor Publico Municipal De Santos - Capep-Saude-SP | não | — |
| 58197948000169-1-000025/2026 | Pregão - Eletrônico - Caixa De Assistencia Ao Servidor Publico Municipal De Santos - Capep | sim | a outra pasta reaproveitou as respostas desta |
| 77001311000108-1-000557/2026 | Pregão - Eletrônico - Castro-PR | não | — |
| 77001311000108-1-000557/2026 | Pregão - Eletrônico - Castro-PR - 557-2026 | sim | as outras pastas leram PDF fora do inventário |

## Procedência incerta

9 arquivo(s) sem correspondência no `/arquivos` do controle — não são lidos nem publicados até decisão:

| controle | seq | arquivo | motivo |
|---|---|---|---|
| 08145153000139-1-000049/2026 | — | 01 - Edital - EDITAL+DO+PE+N%c2%ba+011-2026+-+VENDA+DA+FOLHA.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |
| 77001311000108-1-000557/2026 | — | 02 - Outros Documentos - ANEXO_1__ETP__133_2026.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |
| 77001311000108-1-000557/2026 | — | 03 - Outros Documentos - Comprovante_de_Abertura_do_Processo__515424.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |
| 77001311000108-1-000557/2026 | — | 04 - Outros Documentos - DFD.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |
| 77001311000108-1-000557/2026 | — | 05 - Outros Documentos - Parecer_jurdico_PE_133_2026.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |
| 77001311000108-1-000557/2026 | — | 06 - Outros Documentos - Aviso_de_Edital_PE_133_2026.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |
| 77001311000108-1-000557/2026 | — | 07 - Outros Documentos - PE_N_133_2026__GERENCIAMENTO_DA_FOLHA_DE_PAGAMENTO__SMG_3849.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |
| 77001311000108-1-000557/2026 | — | 07 - Outros Documentos - PE_n_133_2026__Gerenciamento_da_folha_de_pagamento__SMG_38498.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |
| 77001311000108-1-000557/2026 | — | 08 - Outros Documentos - ANEXO_2__TERMO_DE_REFERNCIA__133_2026.pdf | PDF na pasta sem estar no inventário, em pasta que recebeu arquivo de outra licitação |

## Procedência inferida

30 execução(ões) com campo deduzido — custo e tokens como vieram, nunca recalculados; nenhuma sem `fonte_migracao`.

| execução | controle | origem | provedor | modelo | canônica | R$ legado | campos inferidos | fonte |
|---|---|---|---|---|---|---|---|---|
| 4 | 01612483000148-1-000037/2026 | api | claude | claude-opus-5 | sim | 5.835 | chamadas, effort, finalizado_em (mtime), lote, provedor | ABERTO Pregao - Eletronico - Fruta de Leite-MG |
| 15 | 04035135000143-1-000015/2026 | api | claude | claude-opus-5 | sim | 1.607 | chamadas, effort, finalizado_em (mtime), lote, provedor | Dispensa - Rio Branco-AC |
| 17 | 04213779000184-1-000304/2026 | api | claude | claude-opus-5 | sim | 5.874 | effort, finalizado_em (mtime), lote, provedor | ABERTO Concorrencia - Eletronica - Capao do Cipo-RS |
| 18 | 04215168000175-1-000044/2025 | api | claude | claude-opus-5 | sim | 3.341 | effort, finalizado_em (mtime), lote, provedor | Pregao - Presencial - Paulo Bento-RS |
| 47 | 18307462000111-1-000029/2026 | api | claude | claude-opus-5 | sim | 2.475 | effort, finalizado_em (mtime), lote, provedor | Credenciamento - Santa Efigenia de Minas-MG |
| 61 | 45701455000172-1-000034/2026 | api | claude | claude-opus-5 | sim | 6.526 | effort, finalizado_em (mtime), lote, provedor | Pregao - Eletronico - Santo Antonio do Pinhal-SP |
| 85 | 76105642000117-1-000027/2026 | api | claude | claude-opus-5 | sim | 6.563 | chamadas, effort, finalizado_em (mtime), lote, provedor | ABERTO Pregao - Eletronico - Adrianopolis-PR |
| 98 | 87893111000152-1-000381/2026 | api | claude | claude-opus-5 | sim | 3.950 | effort, finalizado_em (mtime), lote, provedor | Concorrencia - Eletronica - Sao Lourenco do Sul-RS |
| 100 | 91553941000108-1-000039/2026 | api | claude | claude-opus-5 | sim | 4.830 | effort, finalizado_em (mtime), lote, provedor | ABERTO Concorrencia - Eletronica - Pirapo-RS |
| 102 | 94444122000110-1-000073/2026 | api | claude | claude-opus-5 | sim | 4.322 | chamadas, effort, finalizado_em (mtime), lote, provedor | ABERTO Concorrencia - Eletronica - Quevedos-RS |
| 122 | 68020916000147-1-000190/2026 | experimento | openai | gpt-5.6-sol | não | 2.518 | finalizado_em (mtime) | _openai_bertioga |
| 123 | 91553941000108-1-000039/2026 | experimento | openai | gpt-5.6-sol | não | 2.500 | finalizado_em (mtime) | _openai_pirapo |
| 120 | 01612483000148-1-000037/2026 | harness | claude | claude-sonnet-5 | não | 2.463 | finalizado_em (mtime) | _harness_ABERTO Pregao - Eletronico - Fruta de Leite-MG.json |
| 121 | 04035135000143-1-000015/2026 | harness | claude | claude-sonnet-5 | não | 0.686 | finalizado_em (mtime) | _harness_Dispensa - Rio Branco-AC.json |
| 114 | 68020916000147-1-000190/2026 | harness | claude | claude-opus-5 | não | 2.911 | finalizado_em (mtime) | _harness_ABERTO Pregao - Eletronico - Bertioga-SP.json |
| 115 | 68020916000147-1-000190/2026 | harness | claude | claude-sonnet-5 | não | 1.185 | finalizado_em (mtime) | _harness_ABERTO Pregao - Eletronico - Bertioga-SP.json |
| 116 | 68020916000147-1-000190/2026 | harness | claude | claude-haiku-4-5 | não | 0.400 | finalizado_em (mtime) | _harness_ABERTO Pregao - Eletronico - Bertioga-SP.json |
| 117 | 68020916000147-1-000190/2026 | harness | claude | claude-opus-5 | não | 3.086 | finalizado_em (mtime) | _harness_ABERTO Pregao - Eletronico - Bertioga-SP_variancia.json |
| 118 | 68020916000147-1-000190/2026 | harness | claude | claude-opus-5 | não | 3.041 | finalizado_em (mtime) | _harness_ABERTO Pregao - Eletronico - Bertioga-SP_variancia.json |
| 119 | 68020916000147-1-000190/2026 | harness | claude | claude-opus-5 | não | 3.056 | finalizado_em (mtime) | _harness_ABERTO Pregao - Eletronico - Bertioga-SP_variancia.json |
| 113 | 76105642000117-1-000027/2026 | harness | claude | claude-sonnet-5 | não | 2.690 | finalizado_em (mtime) | _harness_ABERTO Pregao - Eletronico - Adrianopolis-PR.json |
| 104 | 91553941000108-1-000039/2026 | harness | claude | claude-opus-5 | não | 4.795 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Pirapo-RS.json |
| 105 | 91553941000108-1-000039/2026 | harness | claude | claude-sonnet-5 | não | 2.115 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Pirapo-RS.json |
| 106 | 91553941000108-1-000039/2026 | harness | claude | claude-haiku-4-5 | não | 0.644 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Pirapo-RS.json |
| 107 | 91553941000108-1-000039/2026 | harness | claude | claude-sonnet-5 | não | 1.854 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Pirapo-RS_efforts.json |
| 108 | 91553941000108-1-000039/2026 | harness | claude | claude-sonnet-5 | não | 1.645 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Pirapo-RS_efforts.json |
| 109 | 91553941000108-1-000039/2026 | harness | claude | claude-sonnet-5 | não | 1.623 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Pirapo-RS_efforts.json |
| 110 | 91553941000108-1-000039/2026 | harness | claude | claude-sonnet-5 | não | 1.992 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Pirapo-RS_modos.json |
| 111 | 91553941000108-1-000039/2026 | harness | claude | claude-sonnet-5 | não | 1.284 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Pirapo-RS_modos.json |
| 112 | 94444122000110-1-000073/2026 | harness | claude | claude-sonnet-5 | não | 1.756 | finalizado_em (mtime) | _harness_ABERTO Concorrencia - Eletronica - Quevedos-RS.json |

## Gêmeas

12 controle(s) com o mesmo conjunto de documentos de outro (`gemea_de`). Gêmea não é duplicata: cada controle segue com a sua licitação.

| controle | gêmea de | estado |
|---|---|---|
| 08145153000139-1-000052/2026 | 08145153000139-1-000049/2026 | publicada |
| 08159162000189-1-000032/2026 | 08159162000189-1-000029/2026 | publicada |
| 08159162000189-1-000029/2026 | 08159162000189-1-000032/2026 | preparada |
| 16418766000120-1-000048/2026 | 16418766000120-1-000043/2026 | publicada |
| 16418766000120-1-000043/2026 | 16418766000120-1-000048/2026 | preparada |
| 18409219000104-1-000030/2025 | 18409219000104-1-000029/2025 | preparada |
| 19243500000182-1-000094/2026 | 19243500000182-1-000093/2026 | publicada |
| 19243500000182-1-000093/2026 | 19243500000182-1-000094/2026 | preparada |
| 58993577000121-1-000060/2024 | 58993577000121-1-000031/2024 | preparada |
| 76002641000147-1-000324/2026 | 76002641000147-1-000323/2026 | publicada |
| 78200482000110-1-000180/2026 | 78200482000110-1-000171/2026 | publicada |
| 82940776000156-1-000724/2026 | 82940776000156-1-000721/2026 | publicada |

## Extraídas fora do escopo

Nenhum controle extraído está fora do escopo pela regra de hoje.

## Mais de uma execução canônica

1 controle(s) com mais de uma execução canônica vinda de pastas diferentes do legado. Só uma verificação é a vigente; a outra extração existe e não aparece — decidir qual vale.

| controle | execução | origem | pasta | verificação vigente |
|---|---|---|---|---|
| 04035135000143-1-000015/2026 | 15 | api | Dispensa - Rio Branco-AC | 15 |
| 04035135000143-1-000015/2026 | 276 | agente | Dispensa - Tribunal De Contas Do Estado Do Acre-AC | — |

## Decisões pendentes

Nenhuma decisão pendente: nenhum empate sem critério na escolha da pasta canônica.
