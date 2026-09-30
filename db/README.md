# db/ — o banco

PostgreSQL 16, banco `fopa`: **42 tabelas, 36 funções, 4 views e 7 gatilhos**, criados por **51 migrações** numeradas (`001` a `051`; não há `040`, e há duas `024`).

| Arquivo | O que é |
|---|---|
| `0NN_*.sql` | as migrações, aplicadas em ordem |
| `migrar.py` | o aplicador: registra o SHA-256 de cada migração aplicada (com o fim de linha normalizado) e **aborta** se uma já aplicada mudou; aplica as senhas dos papéis a partir do ambiente, nunca do SQL |
| `invariantes.sql` | uma consulta em que zero linhas significa banco íntegro |
| `tests/` | as migrações num Postgres efêmero: funções, gatilhos, estados, filas, invariantes |

O que mora no banco — e não no fluxo — de propósito:

- **a máquina de estados** de cada licitação (`fn_transicao`), com as transições permitidas;
- **a fila** (`fn_reivindicar`, trava de linha com `SKIP LOCKED`, *lease* de 2 horas, *backoff* e disjuntor);
- **o freio de gasto** (`fn_tomar_vaga_extracao`: até 4 extrações ao mesmo tempo e teto diário, sob trava exclusiva);
- **a trava de ensaio**: resultado simulado só vira vigente em licitação de ensaio;
- **a imutabilidade**: tabelas de histórico só aceitam inserção;
- **os papéis**: `n8n_rw`, `worker_rw`, `api_ro` e `api_rw`, cada um com o mínimo que precisa.

```bash
docker compose --profile migrate run --rm fopa-migrate    # a partir de docker/
python -m pytest db/tests -q                              # 71 funções de teste, Postgres efêmero em porta sorteada
```

Documentação: [Modelo de dados](<../Fopa-v3/06-Dados/Modelo de dados.md>) · [Funções e views do banco](<../Fopa-v3/06-Dados/Funções e views do banco.md>) · [Migrações do banco](<../Fopa-v3/06-Dados/Migrações do banco.md>)
