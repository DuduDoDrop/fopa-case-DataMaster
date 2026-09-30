# migracao/ — a importação do acervo da versão anterior

A prova de conceito gravava tudo em pastas e arquivos JSON. Este pacote levou esse acervo para o banco **sem reprocessar nada** — nenhum OCR, nenhuma chamada de modelo —, com a procedência de cada linha registrada.

| Passo | Módulo | Garantia |
|---|---|---|
| 1. congelar | `congelar.py` | um retrato datado, com manifesto de SHA-256 de cada PDF |
| 2. planejar | `plano.py` · `regras.py` · `acervo.py` | o acervo inteiro traduzido em linhas, em memória, por funções puras testadas |
| 3. importar | `importar.py` | uma transação só; um PDF diferente do manifesto aborta tudo; idempotente |
| 4. publicar | `publicar.py` | relatório de cada licitação verificada, pela máquina de estados |
| 5. reconciliar | `relatorio.py` | o que ficou para decisão humana e o que foi inferido; `relatorio-2026-09-24.md` é o da importação feita |

O acervo em si não está no repositório; a importação roda pelo serviço `fopa-importar` da composição (`docker/`).

```bash
python -m pytest migracao/tests -q     # 63 funções de teste, com retratos sintéticos
```

Documentação: [Acervo e migração da v2](<../Fopa-v3/06-Dados/Acervo e migração da v2.md>)
