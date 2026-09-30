# -*- coding: utf-8 -*-
"""
Suíte do filtro de escopo — os 13 objetos reais mais os casos de fronteira.

    python 23_testa_escopo.py

Custo R$ 0,00. Não chama modelo nem rede: os objetos das 13 licitações saem do
`auditoria.json` que já está no disco, e os casos de fronteira estão escritos
aqui.

POR QUE ISTO EXISTE COMO SCRIPT E NÃO COMO COMENTÁRIO
O filtro é o portão mais barato do pipeline e o mais caro de errar: cada objeto
que passa indevidamente custa uma extração inteira e produz um relatório com
metade das perguntas em branco. Rio Azul/PR passou, custou R$ 4,26 e voltou com
6 de 17 vazias.

Um filtro assim precisa de suíte, não de revisão por leitura — e a suíte precisa
dos documentos REAIS, porque foi lendo os doze objetos verdadeiros que o critério
apareceu: todos nomeiam o contratado como instituição financeira, ou declaram
cessão onerosa. Nenhum diz "contratação de empresa".
"""
from __future__ import annotations

import glob
import json
import os
import sys

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

from fopa import escopo, inventario                          # noqa: E402

SAIDAS = os.path.join(RAIZ, "saidas")
AMOSTRAS = os.path.join(RAIZ, "amostras")

# Licitações da amostra que NÃO são de folha. Fora daqui, espera-se que passe.
# Duas das treze da amostra nao eram licitacao de folha, e as duas foram
# descobertas pelo mesmo sintoma: metade das perguntas em branco.
#   Rio Azul/PR  gestao de consignacoes (terceirizada)
#   Jaboatao/PE  credenciamento de bancos para CONCEDER consignado
FORA_DA_AMOSTRA = {"ABERTO Pregao - Eletronico - Rio Azul-PR",
                   "Inexigibilidade - Jaboatao dos Guararapes-PE"}

# Casos que a amostra não cobre, escritos a partir do vocabulário observado.
FRONTEIRA = [
    # (deve passar?, rótulo, objeto)
    (False, "terceirizada de consignações (Rio Azul, o caso real)",
     "CONTRATAÇÃO DE EMPRESA PARA PRESTAÇÃO DE SERVIÇOS DE IMPLANTAÇÃO E GESTÃO "
     "DE CONSIGNAÇÕES FACULTATIVAS EM FOLHA DE PAGAMENTO"),
    (False, "software de folha",
     "Contratação de empresa para licença de uso de sistema de gestão de folha "
     "de pagamento e recursos humanos"),
    (False, "assessoria contábil",
     "Contratação de empresa especializada em assessoria contábil para "
     "conferência da folha de pagamento do Município"),
    (False, "averbação de consignado",
     "Contratação de empresa para sistema de averbação de consignações em folha "
     "de pagamento dos servidores"),
    (False, "vale-alimentação",
     "Contratação de empresa para fornecimento de vale-alimentação com desconto "
     "em folha de pagamento dos servidores"),
    (False, "menciona folha de passagem",
     "Aquisição de material de expediente, com pagamento previsto na folha "
     "orçamentária do exercício"),
    (True, "cessão onerosa clássica",
     "Constitui objeto a cessão onerosa do direito de efetuar o pagamento da "
     "folha de pagamento dos servidores do Município"),
    (True, "contratação de instituição financeira",
     "Contratação de instituição financeira, pública ou privada, para prestação "
     "de serviços de processamento e gerenciamento da folha de pagamento"),
    (True, "cooperativa de crédito",
     "Seleção de instituição financeira e/ou cooperativa de crédito para a "
     "cessão onerosa do direito de efetuar o pagamento da folha dos servidores"),
    (True, "credenciamento de banco",
     "Credenciamento de instituição financeira para prestação de serviços "
     "bancários de gerenciamento de créditos provenientes da Folha de Pagamento"),
    (True, "empresa especializada QUE É instituição financeira",
     "Contratação de empresa especializada, instituição financeira autorizada "
     "pelo Banco Central, para operacionalização da folha de pagamento em "
     "caráter de exclusividade"),
    (True, "cessão com consignado acessório",
     "Cessão onerosa da folha de pagamento com oferta de crédito consignado aos "
     "servidores, mediante instituição financeira"),
    # ADR-015 (24/09/2026): 18 objetos que o inventario marcou DENTRO e nao sao
    # compra de folha -- lidos um a um pela sessao de extracao. A regra de entao
    # ainda deixava passar 12; estes sao os 12, com o objeto real inteiro.
    (False, 'ADR-015 Fortim-CE: migração de banco de dados do sistema de folha',
     'CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA REALIZAR A MIGRAÇÃO DE DADOS (BANCO DE DADOS FIREBIRD PARA BANCO DE DADOS POSTGRESQL) DO SISTEMA DE FOLHA DE PAGAMENTO DOS ANOS DE 2013 A 2022, NO ÂMBITO DA SECRETARIA DE ADMINISTRAÇÃO E FINANÇAS DO MUNICÍPIO DE FORTIM/CE. Ato que autoriza a Contratação Direta nº 0812.01/2025-SMAF/2025'),
    (False, 'ADR-015 Russas-CE: migração de banco de dados do sistema de folha',
     'CONTRATAÇÃO DE EMPRESA ESPECIALIZADA PARA REALIZAR A MIGRAÇÃO DE DADOS (BANCO DE DADOS FIREBIRD PARA BANCO DE DADOS POSTGRESQL) DO SISTEMA DE FOLHA DE PAGAMENTO DOS ANOS 2013 A 2022. Ato que autoriza a Contratação Direta nº 001.05.11.2024-SEGEP/2024'),
    (False, 'ADR-015 Santa Cruz Do Sul-RS: envio/retorno de arquivos e tarifas (sem cessão da folha)',
     'Contratação de instituição bancária para serviços de envio/retorno de arquivos de contas a pagar, folhas de pagamento e respectivas tarifas, convênio 03651. Ato que autoriza a Contratação Direta nº 51/2026'),
    (False, 'ADR-015 Santa Cruz Do Sul-RS - 190-2026: envio/retorno de arquivos (sem cessão da folha)',
     'Contratação de instituição bancária para serviços de envio/retorno de arquivos de folhas de pagamento dos funcionários do Fundeb, convênio 27514. Ato que autoriza a Contratação Direta nº 50/2026'),
    (False, 'ADR-015 Serranos-MG: cessão de sistema (software) de folha',
     'Prestação de serviços cessão onerosa de sistema de folha de pagamento para processamento das informações relativas ao exercício 2024. Ato que autoriza a Contratação Direta nº 4/2024'),
    (False, 'ADR-015 Serv Assistencia E Seg Social Municipiar: backup de informática',
     'Objeto: Contratação de empresa de informática para prestação de serviços de backup’s diários de arquivos e banco de dados do servidor do SASSOM: movimentação de cadastro de convênios médicos, folha de pagamento, emissão de guias médicas, relatórios e documentos diversos, aproximadamente 300 MB diários. Ato que autoriza a Contratação Direta nº 00014/2025'),
    (False, 'ADR-015 Vereadores Barra Do Quarai-RS: conta institucional; exclui expressamente a folha',
     'Contratação de instituição financeira oficial para prestação de serviços bancários, consistentes na manutenção de conta bancária institucional destinada ao recebimento de duodécimos, realização de pagamentos, movimentações financeiras e demais operações necessárias à execução orçamentária e financeira da Câmara Municipal, exceto pagamento de despesas decorrentes da folha de pagamento. Ato que autoriza a Contratação Direta nº 17/2026'),
    (False, 'ADR-015 Acailandia-MA: consultoria EVEF',
     'Contratação de serviços especializados para realização de Estudo Técnico Preliminar, para estimar o melhor valor a ser pago pelos serviços referente à gestão bancária da folha de pagamento dos servidores e funcionários ativos, inativos, pensionistas, crédito consignado, pagamento de fornecedores, arrecadação das receitas diversas e outros serviços. Ato que autoriza a Contratação Direta nº 002/2024 SEMEF/2024'),
    (False, 'ADR-015 Aguanil-MG: tarifas bancárias',
     "PRESTACAO DE SERVICO RELACIONADO A TARIFAS BANCARIAS E OPERACIONALIZACAO INCIDENTES SOBRE OS SERVICOS PRESTADOS POR INSTITUICAO FINANCEIRA PUBLICA OFICIAL, BEM COMO A REALIZACAO DE OPERACOES FINANCEIRAS, COMO TRANSFERENCIA ELETRONICA DISPONIVEL 'TED', DOCUMENTO DE ORDEM DE CREDITO 'DOC' E TRANSACOES VIA PIX, BEM COMO A EXECUCAO DOS SERVICOS NECESSARIOS AO PROCESSAMENTO, GERENCIAMENTO E PAGAMENTO DA FOLHA DE PAGAMENTO DOS SERVIDORES, AGENTES POLITICOS E DEMAIS BENEFICIARIOS Ato que autoriza a Contratação Direta nº 5/2026"),
    (False, 'ADR-015 Cameta-PA: software de folha',
     '[Portal de Compras Públicas] - CONTRATAÇÃO DE EMPRESA PARA CONTRATAÇÃO DE PRESTADORA DE SERVIÇOS ESPECIALIZADOS DE IMPLEMENTAÇÃO, INTEGRAÇÃO E OTIMIZAÇÃO DA FOLHA DE PAGAMENTO, A QUAL JÁ ATENDE AS NECESSIDADES DO MUNICIPIO NO QUAL SE REFERE AO BANCO DE DADOS DOS SERVIDORES CELEBRADO. Ato que autoriza a Contratação Direta nº 029/2026'),
    (False, 'ADR-015 Diorama-GO: tarifas bancárias',
     'Nº 29038. ADOÇÃO DAS PROVIDÊNCIAS NECESSÁRIAS PARA CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA OFICIALMENTE AUTORIZADA PELO BANCO CENTRAL DO BRASIL, EM ESPECÍFICO PARA OS BANCOS: CAIXA ECONÔMICA FEDERAL E BANCO DO BRASIL, VISANDO À PRESTAÇÃO DE SERVIÇOS BANCÁRIOS REFERENTES ÀS DESPESAS DECORRENTES DE TARIFAS, FATURAS, COBRANÇAS E DEMAIS ENCARGOS REALIZADOS PELOS BANCOS EM RAZÃO DE TRANSAÇÕES FINANCEIRAS E OUTRAS MOVIMENTAÇÕES DAS CONTAS PÚBLICAS MUNICIPAIS. A PRESENTE SOLICITAÇÃO JUSTIFICA-SE PELA NECESSIDADE DE MANUTENÇÃO REGULAR DAS CONTAS BANCÁRIAS DO MUNICÍPIO, IMPRESCINDÍVEIS PARA OPERACIONALIZAÇÃO DE RECEITAS, PAGAMENTOS, TRANSFERÊNCIAS, ARRECADAÇÕES, FOLHA DE PAGAMENTO E DEMAIS ATOS DA EXECUÇÃO ORÇAMENTÁRIA E FINANCEIRA. TAIS DESPESAS POSSUEM NATUREZA CONTÍNUA E SÃO INDISPENSÁVEIS AO REGULAR FUNCIONAMENTO DA ADMINISTRAÇÃO PÚBLICA. FONTE: 100. Ato que autoriza a Contratação Direta nº ('),
    (False, 'ADR-015 Macae-RJ: empréstimo pessoal/compra de dívida',
     'Prestação de serviços de concessão de empréstimo pessoal, compra de dívida dos Servidores Públicos Municipais Estatutários diretos, ativos, inativos e pensionistas da Administração Direta e do Instituto de Previdência Social do Município de Macaé. MACAEPREV, bem como a concessão de Cartão de Crédito sem ônus, mediante desconto em folha de pagamento, conforme especificado no termo de referência anexo ao edital. Instituição financeira: CDC SOCIEDADE DE CRÉDITO DIRETO S.A-CNPJ nº 18.394.228/0001-79 Ato que autoriza a Contratação Direta nº 286/2026'),
    # ADR-015, o outro lado: DENTRO da fila humana e citam tarifa. A tarifa aqui
    # é isenção (Olaria) ou serviço correlato (Jardim do Seridó), não o objeto.
    (True, 'ADR-015 Olaria-MG 10/2026: folha com menção a tarifas',
     '[Portal de Compras Públicas] - O objeto da presente licitação é a Contratação de instituição bancária para prestação dos serviços de pagamento de remuneração de servidores e serviços similares, incluindo operar os serviços de processamento e gerenciamento de créditos provenientes da Folha de Pagamento dos servidores ativos, inativos e pensionistas do Município de Olaria, com isenção total de tarifas bancárias para a Administração Pública do Município em caráter de exclusividade, conforme condições, quantidades e exigências  estabelecidas neste Edital e seus anexos.   Edital nº 03/2026'),
    (True, 'ADR-015 Olaria-MG 96/2025: folha com menção a tarifas',
     '[Portal de Compras Públicas] - objeto da presente licitação é a Contratação de instituição bancária para prestação dos serviços de pagamento de remuneração de servidores e serviços similares, incluindo operar os serviços de processamento e gerenciamento de créditos provenientes da Folha de Pagamento dos servidores ativos, inativos e pensionistas do Município de Olaria, com isenção total de tarifas bancárias para a Administração Pública do Município em caráter de exclusividade, conforme condições, quantidades e exigências estabelecidas neste Edital e seus anexos.   Edital nº 015/2025'),
    (True, 'ADR-015 Jardim do Seridó-RN (JARDIMPREV): folha com menção a tarifas',
     'Contratação direta, por dispensa de licitação, de instituição financeira para a prestação de serviços bancários, compreendendo o processamento, gerenciamento e operacionalização da folha de pagamento dos servidores ativos, aposentados e pensionistas do JARDIMPREV, mediante crédito em contas individuais, bem como a execução de serviços correlatos, incluindo a cobrança e administração de tarifas bancárias, disponibilização de canais de atendimento e suporte operacional, visando assegurar a continuidade, eficiência e segurança na execução dos serviços, nos termos da legislação vigente.   Ato que autoriza a Contratação Direta nº 3/2026'),
    # Jev v3 (24/09/2026): o score do filtro sobre as 1.162 do recorte achou estes
    # objetos que a regra RECUSAVA e são compra de folha de livro-texto: "operar,
    # com exclusividade, a folha" com consignado acessório, "pagamento dos
    # servidores" sem a palavra folha, "folha de benefícios", texto truncado pelo
    # PNCP ("FOLHA DE PAGAMENT") e plataforma/suporte técnico como parte do
    # serviço do banco. Motivo antigo entre parênteses.
    (True, 'Jev v3 Piracuruca-PI (era: fala de folha, mas não é a operação dela)',
     'A operacionalização e o gerenciamento, com exclusividade, da folha de pagamento dos servidores ativos e inativos do Município de Piracuruca/PI, incluindo aqueles que vierem a ser contratados futuramente pela Administração, abrangendo os entes e fundos vinculados à municipalidade   Ato que autoriza a Contratação Direta nº 0000004/2026'),
    (True, 'Jev v3 Itu-SP (era: não é sobre folha de pagamento)',
     'CONTRATACAO DE INSTITUICAO BANCARIA PARA SERVICOS BANCARIOS FOLHA DE PAGAMEN   Edital nº 00071/2025'),
    (True, 'Jev v3 Barra do Garças-MT (era: não é sobre folha de pagamento)',
     'CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA OFICIAL, DEVIDAMENTE AUTORIZADA A FUNCIONAR PELO BANCO CENTRAL DO BRASIL, PARA A PRESTAÇÃO DE SERVIÇOS BANCÁRIOS E FINANCEIROS AO MUNICÍPIO DE BARRA DO GARÇAS/MT, COMPREENDENDO A OPERACIONALIZAÇÃO DA FOLHA DE PAGAMENT   Aviso de Contratação Direta nº 50/2026'),
    (True, 'Jev v3 Xaxim-SC (era: consignado ou margem consignável, não a )',
     'CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA PARA OPERAR, COM EXCLUSIVIDADE*, A FOLHA DE PAGAMENTO DOS SERVIDORES DA ADMINISTRAÇÃO DIRETA, INCLUINDO ATIVOS, INATIVOS, PENSIONISTAS E COMISSIONADOS; COM POSSIBILIDADE DE CONCESSÃO DE EMPRÉSTIMOS CONSIGNADOS (SEM EXCLUSIVIDADE), PARA ATENDER A DEMANDA DO MUNICÍPIO DE XAXIM   Edital nº PE 31/2026'),
    (True, 'Jev v3 Papagaios-MG (era: não é sobre folha de pagamento)',
     'CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA, COM EXCLUSIVIDADE, PARA PRESTAÇÃO DOS SERVIÇOS DE PAGAMENTO DOS SERVIDORES MUNICIPAIS   Edital nº 036/2026'),
    (True, 'Jev v3 Santa Terezinha-BA (era: consignado ou margem consignável, não a )',
     'Constitui-se objeto desta licitação a contratação de Instituição Financeira Pública ou Privada, regularmente em atividade, conforme legislação específica, para operar, com exclusividade, a folha de pagamento dos servidores da Administração Direta, incluindo ativos, inativos, pensionistas e comissionados; com possibilidade de concessão de empréstimos consignados (sem exclusividade), conforme Termo de Referência.   Edital nº 011/2026'),
    (True, 'Jev v3 Cajuri-MG (era: consignado ou margem consignável, não a )',
     'Contratação de Instituição Financeira, pública ou privada, com autorização pelo Banco Central do Brasil, para a prestação de serviços bancários, com exclusividade de folha, necessários ao pagamento de salários, proventos, vencimentos, pensões, consignado (sem exclusividade, por todo o prazo do contrato) e similares, de servidores ou empregados públicos ativos e inativos, da Prefeitura Municipal de Cajuri, mediante crédito em conta, conforme disposto nas Resoluções do Conselho Monetário Nacional,   Edital nº 11/2026'),
    (True, 'Jev v3 Três Corações-MG (era: não é sobre folha de pagamento)',
     'Contratação de instituição financeira autorizada para prestação de serviços bancários de gerenciamento e processamento de pagamento da folha de benefícios dos servidores aposentados, pensionistas e ativos do Instituto de Previdência Municipal de Três Corações – IPRECOR. Como também agentes políticos, estagiários e pagamentos de fornecedores diversos.   Edital nº 90001/2026'),
    (True, 'Jev v3 Três Corações-MG (era: não é sobre folha de pagamento)',
     'Contratação de instituição financeira autorizada para prestação de serviços bancários de gerenciamento e processamento de pagamento da folha de benefícios dos servidores aposentados, pensionistas e ativos do Instituto de Previdência Municipal de Três Corações – IPRECOR. Como também estagiários e futuros servidores e beneficiários ao longo da vigência do contrato.   Edital nº 5/2026'),
    (True, 'Jev v3 Itajaí-SC (era: consignado ou margem consignável, não a )',
     'Contratação de instituição financeira para operar, com exclusividade, a folha de pagamento dos servidores da Administração Direta e Indireta, incluindo ativos, inativos, pensionistas e comissionados; com possibilidade de concessão de empréstimos consignados (sem exclusividade), para atender a demanda da Secretaria Municipal da Fazenda   Edital nº PE 240/2025/2026'),
    (True, 'Jev v3 Maravilhas-MG (era: não é sobre folha de pagamento)',
     'Contratação de instituição financeira, com exclusividade, para prestação dos serviços de pagamento dos servidores municipais, por um período de 05 (cinco) anos.   Edital nº 031/2026'),
    (True, 'Jev v3 Ponte Serrada-SC (era: serviço SOBRE a folha (consultoria, cont)',
     'Contratação de instituição financeira, pública ou privada, inclusive cooperativa de crédito, devidamente autorizada pelo Banco Central do Brasil, para a prestação de serviços bancários, em caráter de exclusividade, destinados ao processamento, gerenciamento e pagamento da folha salarial dos servidores públicos ativos, inativos, pensionistas e demais agentes vinculados à Administração Pública Municipal de Ponte Serrada, compreendendo a abertura e manutenção de contas-salário ou contas-correntes, crédito mensal das remunerações, disponibilização de canais de atendimento presencial e digital, bem como suporte técnico-operacional necessário à integração dos sistemas e à execução regular dos pagamentos, mediante contrapartida financeira em favor do Município.   Edital nº PE 17/2026'),
    (True, 'Jev v3 Ponte Serrada-SC (era: serviço SOBRE a folha (consultoria, cont)',
     'Contratação de instituição financeira, pública ou privada, inclusive cooperativa de crédito, devidamente autorizada pelo Banco Central do Brasil, para a prestação de serviços bancários, em caráter de exclusividade, destinados ao processamento, gerenciamento e pagamento da folha salarial dos servidores públicos ativos, inativos, pensionistas e demais agentes vinculados à Administração Pública Municipal de Ponte Serrada, compreendendo a abertura e manutenção de contas-salário ou contas-correntes, crédito mensal das remunerações, disponibilização de canais de atendimento presencial e digital, bem como suporte técnico-operacional necessário à integração dos sistemas e à execução regular dos pagamentos, mediante contrapartida financeira em favor do Município.   Edital nº PE 26/2026'),
    (True, 'Jev v3 Ponte Serrada-SC (era: serviço SOBRE a folha (consultoria, cont)',
     'Contratação de instituição financeira, pública ou privada, inclusive cooperativa de crédito, devidamente autorizada pelo Banco Central do Brasil, para a prestação de serviços bancários, em caráter de exclusividade, destinados ao processamento, gerenciamento e pagamento da folha salarial dos servidores públicos ativos, inativos, pensionistas e demais agentes vinculados à Administração Pública Municipal de Ponte Serrada, compreendendo a abertura e manutenção de contas-salário ou contas-correntes, crédito mensal das remunerações, disponibilização de canais de atendimento presencial e digital, bem como suporte técnico-operacional necessário à integração dos sistemas e à execução regular dos pagamentos, mediante contrapartida financeira em favor do Município.   Edital nº PE 30/2026'),
    (True, 'Jev v3 Albertina-MG (era: não é sobre folha de pagamento)',
     'Pregão Presencial para Contratação de Instituição financeira pública ou privada, inclusive sobre forma de Cooperativa de Créditos, para prestação de serviços bancários, necessários ao pagamento dos servidores municipais ativos (efetivos, estáveis, estatutários, celetistas, contratados, comissionados, estagiários e agentes políticos) da Prefeitura Municipal de Albertina, conforme termo de referência.   Edital nº 12/2026'),
    (True, 'Jev v3 Itabuna-BA (era: consignado ou margem consignável, não a )',
     '[LICITANET] - CONTRATAÇÃO, COM EXCLUSIVIDADE, DOS SERVIÇOS BANCÁRIOS, POR INSTITUIÇÃO FINANCEIRA PÚBLICA OU PRIVADA DEVIDAMENTE AUTORIZADA PELO BANCO CENTRAL DO BRASIL, DESTINADOS AO PROCESSAMENTO, GERENCIAMENTO E OPERACIONALIZAÇÃO DO PAGAMENTO DE VENCIMENTOS, SALÁRIOS, PROVENTOS, PENSÕES E DEMAIS VERBAS DE NATUREZA REMUNERATÓRIA DOS EMPREGADOS PÚBLICOS, SERVIDORES MUNICIPAIS, EFETIVOS, COMISSIONADOS, TEMPORÁRIOS E ESTAGIÁRIOS; E, SEM EXCLUSIVIDADE, A CONSIGNAÇÃO EM FOLHA DE PAGAMENTO DOS EMPRÉSTIMOS E FINANCIAMENTOS CONCEDIDOS AOS SERVIDORES, COM A FINALIDADE DE ATENDER A ADMINISTRAÇÃO DIRETA E INDIRETA DO PODER EXECUTIVO DO MUNICÍPIO DE ITABUNA.   Edital nº 15/2026'),
    (True, 'Jev v3 Xaxim-SC (era: consignado ou margem consignável, não a )',
     '[Portal de Compras Públicas] - CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA PARA OPERAR, COM EXCLUSIVIDADE*, A FOLHA DE PAGAMENTO DOS SERVIDORES DA ADMINISTRAÇÃO DIRETA, INCLUINDO ATIVOS, INATIVOS, PENSIONISTAS E COMISSIONADOS; COM POSSIBILIDADE DE CONCESSÃO DE EMPRÉSTIMOS CONSIGNADOS (SEM EXCLUSIVIDADE), PARA ATENDER A DEMANDA DO MUNICÍPIO DE XAXIM   Edital nº 21/2026'),
    (True, 'Jev v3 Xaxim-SC (era: consignado ou margem consignável, não a )',
     '[Portal de Compras Públicas] - CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA PARA OPERAR, COM EXCLUSIVIDADE*, A FOLHA DE PAGAMENTO DOS SERVIDORES DA ADMINISTRAÇÃO DIRETA, INCLUINDO ATIVOS, INATIVOS, PENSIONISTAS E COMISSIONADOS; COM POSSIBILIDADE DE CONCESSÃO DE EMPRÉSTIMOS CONSIGNADOS (SEM EXCLUSIVIDADE), PARA ATENDER A DEMANDA DO MUNICÍPIO DE XAXIM   Edital nº 31/2026'),
    (True, 'Jev v3 Xaxim-SC (era: consignado ou margem consignável, não a )',
     '[Portal de Compras Públicas] - CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA PARA OPERAR, COM EXCLUSIVIDADE, A FOLHA DE PAGAMENTO DOS SERVIDORES DA ADMINISTRAÇÃO DIRETA, INCLUINDO ATIVOS, INATIVOS, PENSIONISTAS E COMISSIONADOS; COM POSSIBILIDADE DE CONCESSÃO DE EMPRÉSTIMOS CONSIGNADOS (SEM EXCLUSIVIDADE), PARA ATENDER A DEMANDA DO MUNICÍPIO DE XAXIM.   Edital nº 13/2026'),
    (True, 'Jev v3 José de Freitas-PI (era: sistema ou plataforma que opera sobre a )',
     '[Portal de Compras Públicas] - Prestação de Serviços através de instituição financeira oficial (integrante da AP, criada p/ fim específico), a fim de executar as atividades: processamento da folha de pagamento dos servidores ativos, inativos, pensionistas, agentes políticos e contratados; abertura e manutenção de contas-salário; processamento eletrônico dos arquivos bancários; disponibilização de plataforma eletrônica para transmissão dos arquivos; emissão de relatórios; suporte técnico; atendimento aos servidores; demais  serviços correlatos necessários ao processamento da folha municipal, conforme condições, quantidades e exigências estabelecidas.   Aviso de Contratação Direta nº 001/2026'),
    # Jev v3, a volta do conserto: dois achados de brinde (folha real) e os dois falsos positivos que o
    # primeiro conserto abriu e o refinamento fechou (serviço SOBRE a folha).
    (True, 'Jev v3 regressão Guanhães-MG',
     'CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA PARA PRESTAÇÃO DE SERVIÇOS DE PAGAMENTO DOS SERVIDORES DA PREFEITURA MUNICIPAL DE GUANHÃES/MG, ATIVOS E EFETIVOS, CONTRATADOS, COMISSIONADOS/AGENTE POLÍTICO DA ADMINISTRAÇÃO DIRETA DO MUNICÍPIO DE GUANHÃES/MG.   Edital nº 000052/2025'),
    (True, 'Jev v3 regressão Cachoeira Alta-GO',
     '[LICITANET] - CONTRATAÇÃO DE INSTITUIÇÃO FINANCEIRA PÚBLICA OU PRIVADA, PARA PROCESSAMENTO E GERENCIAMENTO DE CRÉDITOS DA FOLHA PAGAMENTOS DOS SERVIDORES DA ADMINISTRAÇÃO PÚBLICA MUNICIPAL DIRETA E INDIRETA, EM CARÁTER DE EXCLUSIVIDADE, CONFORME ESPECIFICAÇÕES E EXIGÊNCIAS CONSTANTES NO TERMO DE REFERÊNCIA   Edital nº 43/2025'),
    (False, 'Jev v3 regressão Criciúma-SC',
     'Contratação de empresa especializada para prestação de serviços técnicos de apoio para lançamentos contábeis compreendendo: inclusão de empenhos; Processamento de liquidação (entrada) da folha de pagamento, materiais e serviços; Processos de pagamento (baixas) de OP e Despesas Extras; Lançamento de receitas; Conciliação bancária; Auxílio no envio da prestação de contas (Sistema S-Finge); dentre outros lançamentos congêneres, do CISAMREC   Ato que autoriza a Contratação Direta nº DL3/2024'),
    (False, 'Jev v3 regressão Sangão-SC',
     'O objeto da presente Inexigibilidade de Licitação é a contratação de empresa especializada para prestação de serviços de elaboração da parametrização e elaboração da folha pagamento dos servidores, bem como suas integrações com sistema de ponto, folha de pagamento e bancos, ESOCIAL, E-SFINGE, SIOPE, GFIP, RAIS, DIRF, da prefeitura municipal de Sangão/SC, conforme detalhamento e anexos.   Ato que autoriza a Contratação Direta nº IL 11/2022'),
    # Jev v3, a volta que achou falso POSITIVO: serviço de empresa em volta da folha.
    # Bauru fica como prova de que a regra, não o Jev, manda (T25).
    (False, 'Jev v3 Confins-MG: manutenção do ponto eletrônico',
     'A contratação dos serviços de manutenção preventiva e corretiva dos equipamentos de ponto eletrônico é necessária para garantir o funcionamento contínuo e adequado do sistema de controle de frequência dos servidores municipais. A realização da manutenção reduz a ocorrência de falhas, assegura a confiabilidade dos registros de jornada e evita interrupções que possam comprometer a gestão de pessoal, o processamento da folha de pagamento e o cumprimento das normas administrativas.Além disso, a manutenção periódica contribui para prolongar a vida útil dos equipamentos, reduzir custos com substituições e assegurar a continuidade dos serviços prestados pela Administração Pública.   Ato que autoriza a Contratação Direta nº 000021/2026'),
    (False, 'Jev v3 Deodápolis-MS: programa de estágio',
     'Contratação de empresa especializada para o gerenciamento, operacionalização e acompanhamento do Programa de Estágio “Mais Oportunidades” da Prefeitura Municipal de Deodápolis/MS, abrangendo atividades de recrutamento, seleção, administração e supervisão de estagiários, emissão e controle de documentação, gestão de folha de pagamento e frequência, contratação de seguro contra acidentes pessoais, bem como orientações e capacitações aos estagiários e supervisores, conforme proposta apresentada pela contratada e demais especificações constantes do processo.   Ato que autoriza a Contratação Direta nº DL 26/2026'),
    (False, 'Jev v3 Porto Alegre-RS (CRPRS): contabilidade terceiriza o DP',
     'Contratação de empresa de contabilidade especializada para terceirização da operacionalização da folha de pagamento e departamento pessoal do CRPRS.   Ato que autoriza a Contratação Direta nº 51/2026'),
    (True, 'Jev v3 Bauru-SP (COHAB): folha real com consignado acessório — o Jev errava',
     'OBJETO: contratação de instituição financeira, pública ou privada, para processamento e gerenciamento de créditos provenientes da folha de pagamento dos estagiários, funcionários e administradores da COHAB BAURU, sem ônus para a CONTRATANTE, e concessão de empréstimo consignado em folha de pagamento, sem exclusividade, abrangendo todos os empregados.   Edital nº 06/2026/2026'),
    # Jev v3 no W01 (24/09): Jaraguá do Sul contrata empresa de RH que processa a folha (falso
    # positivo, estava na fila paga); José de Freitas 21/2026 escreve "gerenciamento folha pagamento"
    # sem o "de" (falso negativo).
    (False, 'Jev v3 W01 Jaraguá do Sul-SC: gestão de RH e apoio fiscal',
     'Contratação de empresa especializada para a prestação de serviços continuados de gestão de Recursos Humanos, processamento de folha de pagamento e apoio fiscal e tributário.'),
    (True, 'Jev v3 W01 José de Freitas-PI 21/2026: folha pagamento sem preposição',
     ' Serviços operacionalização, processamento e gerenciamento folha pagamento servidores municipais ativos, inativos, pensionistas e demais beneficiários, incluindo a abertura de contas-salário processamento de créditos, disponibilização de canais eletrônico'),
]


def objetos_da_amostra() -> list[tuple[str, str]]:
    """
    O objeto de cada licitação — o `objetoCompra` da API, como em PRODUÇÃO.

    ANTES ISTO USAVA A RESPOSTA Q2 DO EXTRATOR, E ERA OUTRA COISA.
      O filtro nunca vê a Q2. Em produção ele recebe o `objetoCompra` que a API
      devolve na busca, e é sobre esse texto que decide. A Q2 é um RESUMO que o
      extrator escreve lendo o edital inteiro -- e ele cita o que achar útil.

      Castro/PR mostrou o tamanho da diferença. A Q2 tem 1.384 caracteres e
      junta o objeto (item 1.1), a cláusula 1.3 da MINUTA DO CONTRATO e uma
      observação sobre o ETP. Nesse caldo aparece "suporte técnico", que faz o
      filtro recusar como serviço-sobre-a-folha. O `objetoCompra` real de
      Castro diz folha, e o filtro aprova.

      Resultado: três casos da suíte falhavam acusando um defeito que não
      existe em produção. Um teste que reprova o código por um texto que o
      código nunca recebe treina a ignorar o teste.

    A Q2 fica como RESERVA, para licitação que ainda não esteja no corpus --
    melhor um caso medido pelo texto errado do que caso nenhum, desde que
    esteja dito qual foi usado.

    Pastas com `_` na frente ficam de fora. Elas são execuções de COMPARAÇÃO —
    `_openai_pirapo`, `_openai_bertioga`, `_duelo_*` — e não licitações novas.
    Sem esta linha a suíte passou de 23 para 25 casos sozinha, contando Pirapó
    e Bertioga duas vezes cada e anunciando cobertura que não ganhou. Um número
    de teste que cresce quando ninguém escreveu teste é um número quebrado,
    mesmo quando todos passam.
    """
    # o corpus guarda o `objetoCompra` de cada licitação, por número de controle
    por_ctrl = {}
    corpus = os.path.join(SAIDAS, "_corpus_escopo.json")
    if os.path.isfile(corpus):
        try:
            regs = json.load(open(corpus, encoding="utf-8"))["registros"]
            regs = list(regs.values()) if isinstance(regs, dict) else regs
            por_ctrl = {r.get("controle"): r.get("objeto") for r in regs
                        if r.get("controle") and r.get("objeto")}
        except (OSError, ValueError, KeyError):
            por_ctrl = {}

    saida = []
    for f in sorted(glob.glob(os.path.join(SAIDAS, "*", "auditoria.json"))):
        nome = os.path.basename(os.path.dirname(f))
        if nome.startswith("_"):
            continue
        d = json.load(open(f, encoding="utf-8"))
        inv = inventario.ler(os.path.join(AMOSTRAS, d.get("licitacao") or nome))
        real = por_ctrl.get((inv or {}).get("controle"))
        if real:
            saida.append((nome, real))
            continue
        q2 = next((r for r in d.get("respostas", []) if r["id"] == "Q2"), None)
        if q2 and q2.get("resposta"):
            saida.append((nome + "  [via Q2]", q2["resposta"]))

    # DEDUPLICAR POR OBJETO. A mesma licitacao aparece em mais de uma pasta
    # quando houve reextracao ou comparacao de modelo, e o objeto e o mesmo.
    # Contar duas vezes anuncia cobertura que nao se ganhou -- e este arquivo
    # ja levou essa licao uma vez, quando passou de 23 para 25 casos sozinho.
    vistos, unicos = set(), []
    for nome, objeto in saida:
        chave = " ".join((objeto or "").split())[:400]
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append((nome, objeto))
    return unicos


def main() -> int:
    falhas = []

    print("=" * 100)
    print("  FILTRO DE ESCOPO — os 13 objetos reais")
    print("=" * 100)
    for nome, objeto in objetos_da_amostra():
        esperado = nome not in FORA_DA_AMOSTRA
        obtido, motivo = escopo.avaliar(objeto)
        ok = obtido == esperado
        if not ok:
            falhas.append((nome, esperado, obtido, motivo))
        print("  %-46s %-9s %-4s %s"
              % (nome[:46], "FOLHA" if obtido else "fora",
                 "ok" if ok else "ERRO", motivo[:34]))

    print("\n" + "=" * 100)
    print("  CASOS DE FRONTEIRA")
    print("=" * 100)
    for esperado, rotulo, objeto in FRONTEIRA:
        obtido, motivo = escopo.avaliar(objeto)
        ok = obtido == esperado
        if not ok:
            falhas.append((rotulo, esperado, obtido, motivo))
        print("  %-46s %-9s %-4s %s"
              % (rotulo[:46], "FOLHA" if obtido else "fora",
                 "ok" if ok else "ERRO", motivo[:34]))

    print("\n" + "-" * 100)
    if falhas:
        print("  %d FALHA(S):" % len(falhas))
        for nome, esp, obt, motivo in falhas:
            print("    %-46s esperava %-5s obteve %-5s — %s"
                  % (nome[:46], esp, obt, motivo[:40]))
        return 1

    print("  todos os %d casos passaram · custo R$ 0,00"
          % (len(objetos_da_amostra()) + len(FRONTEIRA)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
