# n8n/ — os fluxos de automação

## `workflows/` — os 15 fluxos, versionados

| Fluxo | Nós | Gatilho | O que faz |
|---|---|---|---|
| `W00` Saúde | 9 | de hora em hora | confere se o worker está no contrato (OCR na versão certa, idioma, nenhuma chave) e grava a saúde |
| `W01` Descoberta | 46 | 06:00, dias úteis · manual · pelo site | busca as licitações de folha no PNCP e registra as novas |
| `W10` Fila | 15 | a cada 10 min, das 06:00 às 07:50 · pelo site | reivindica licitações e dispara o W20 |
| `W11` Ações do site | 52 | webhooks | a ponte entre os botões do site e a automação |
| `W20` Processar uma licitação | 24 | chamado | orquestra W21 → W22 → W23 → W24 conforme o estado |
| `W21` Baixar | 28 | chamado | baixa todos os documentos |
| `W22` Ler | 29 | chamado | congela o texto de cada página, com OCR |
| `W23` Extrair | 40 | chamado | o único que fala com o modelo; lotes, custo e reforço do Best-of-N |
| `W24` Verificar e publicar | 38 | chamado | verifica, publica, abre revisões e avisa |
| `W30` Reverificar em lote | 22 | manual · chamado | reaplica as regras às respostas gravadas, a custo zero |
| `W40` Alerta diário | 14 | 07:00 | as prioridades do dia |
| `W41` Histórico do PNCP | 14 | 04:30 | o histórico e os contratos de folha |
| `W50` Envio de e-mails | 11 | a cada minuto | a fila de e-mails, com novas tentativas |
| `W70` Retificações | 19 | domingo, 05:00 | detecta documentos novos nas licitações abertas |
| `W90` Erro | 7 | erro de fluxo | devolve a licitação e os e-mails que estavam reservados e fecha a execução como erro |

Os JSON não carregam nenhum id da instância: carregam marcadores (`{{WF:W90}}`, `{{CRED:worker}}`) que o `importar.py` resolve.

## Os scripts

| Script | O que faz |
|---|---|
| `bootstrap.py` | deixa a instância utilizável sem abrir a interface: dono, chave da API pública e credenciais (idempotente; nunca imprime segredo) |
| `importar.py` | sobe os 15 JSON, das folhas para a raiz; `--publicar todos` (padrão), `nenhum` ou uma lista como `W20,W21` |
| `exportar.py` | o caminho inverso: da instância para os JSON versionados |
| `executar.py` | dispara um fluxo pelo gatilho manual (ou de subfluxo, com `--itens`) e mostra o resultado nó a nó |
| `cliente.py` | o cliente das duas APIs do n8n usado pelos scripts |

Os segredos gerados ficam em `n8n/.segredos/`, fora do git.

> Numa instalação de desenvolvimento, publique só os fluxos sem agenda (`--publicar W20,W21,W22,W23,W24,W90`): publicar os agendados faz a instância coletar no PNCP e enviar e-mails sozinha.

## Testes

`n8n/tests/` roda contra a instância e o banco de verdade, sem *mock* (camada b do CI).

Documentação: [MOC Fluxos n8n](<../Fopa-v3/03-Fluxos-n8n/MOC Fluxos n8n.md>) — cada fluxo descrito nó a nó, com fluxograma · [Horários e agendamentos](<../Fopa-v3/03-Fluxos-n8n/Horários e agendamentos.md>)
