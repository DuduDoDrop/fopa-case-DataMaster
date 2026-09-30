# -*- coding: utf-8 -*-
"""
Relatório de reconciliação da migração — seção 9, passo 8 do plano.

A importação já garante o mecânico: é idempotente, confere o manifesto e roda as
invariantes. O que o humano precisa é outra coisa: saber o que ficou para ele
decidir e o que a migração inferiu no lugar dele. Este relatório lê o banco (só
lê) e diz, em seções fixas:

  · controles com mais de uma pasta no legado, e qual delas é a canônica;
  · arquivos e licitações de procedência incerta (monitor sobrescreveu PDF);
  · execuções com procedência inferida (custo e tokens como vieram, campos
    deduzidos), com a fonte de cada uma;
  · gêmeas (mesmo conjunto de documentos em controles diferentes);
  · extraídas que a regra de escopo de hoje põe fora do escopo;
  · controles com mais de uma execução canônica vindas de pastas diferentes;
  · empates sem critério (`decisoes` da importação, `legado_suspeito`).

Seção vazia diz que está vazia: silêncio num relatório de reconciliação lê como
"conferido", e ausência de caso é informação.

A reimportação de respostas pelo site (`/importar-respostas`) grava cada
execução como canônica — `canonica` nasce `true` em toda execução real e quem
escolhe é a verificação vigente. Por isso o achado de "mais de uma canônica"
olha só as execuções que vieram de PASTAS diferentes do legado, que é o caso
que a seção 9 manda decidir.

Uso:
    python -m migracao.relatorio                 # DATABASE_URL do ambiente
    python -m migracao.relatorio --saida migracao/relatorio-2026-09-24.md
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

RAIZ = Path(__file__).resolve().parents[1]


def _cel(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v) or "—"
    return str(v).replace("|", "\\|").replace("\n", " ")


def _tabela(cabecalho: list[str], linhas: list[list]) -> str:
    out = ["| " + " | ".join(cabecalho) + " |", "|" + "---|" * len(cabecalho)]
    out += ["| " + " | ".join(_cel(c) for c in linha) + " |" for linha in linhas]
    return "\n".join(out)


def _q(conn, sql: str, *args) -> list[dict]:
    return conn.execute(sql, args).fetchall()


def _importacoes(conn) -> str:
    rows = _q(conn, "SELECT id, snapshot, manifesto_sha256, iniciado_em, finalizado_em, avisos, decisoes"
                    " FROM importacoes ORDER BY id")
    if not rows:
        return "Nenhuma importação registrada em `importacoes`."
    linhas = [[r["id"], r["snapshot"], (r["manifesto_sha256"] or "")[:12] or None,
               r["iniciado_em"].strftime("%Y-%m-%d %H:%M") if r["iniciado_em"] else None,
               r["finalizado_em"].strftime("%Y-%m-%d %H:%M") if r["finalizado_em"] else None,
               len(r["avisos"] or []), len(r["decisoes"] or [])] for r in rows]
    partes = [_tabela(["id", "snapshot", "manifesto", "início (UTC)", "fim (UTC)", "avisos", "decisões"], linhas)]
    avisos = [(r["id"], a) for r in rows for a in (r["avisos"] or [])]
    if avisos:
        partes.append("Avisos:\n\n" + "\n".join("- importação %s: %s" % (i, _cel(a)) for i, a in avisos))
    return "\n\n".join(partes)


def _contagens(conn) -> str:
    um = lambda sql: conn.execute(sql).fetchone()["n"]  # noqa: E731
    base = [
        ["licitações", um("SELECT count(*) AS n FROM licitacoes")],
        ["pastas do legado", um("SELECT count(*) AS n FROM pastas_legado")],
        ["arquivos", um("SELECT count(*) AS n FROM arquivos")],
        ["leituras (texto congelado)", um("SELECT count(*) AS n FROM leituras")],
        ["execuções de modelo", um("SELECT count(*) AS n FROM execucoes_modelo")],
        ["verificações vigentes", um("SELECT count(*) AS n FROM verificacoes WHERE vigente")],
        ["verificações legadas vigentes", um("SELECT count(*) AS n FROM verificacoes"
                                             " WHERE vigente AND versao_regras LIKE 'legado:%%'")],
        ["publicações", um("SELECT count(*) AS n FROM publicacoes")],
    ]
    estados = _q(conn, "SELECT estado::text AS k, count(*) AS n FROM licitacoes GROUP BY 1 ORDER BY 2 DESC, 1")
    status = _q(conn, "SELECT status::text AS k, count(*) AS n FROM arquivos GROUP BY 1 ORDER BY 2 DESC, 1")
    leituras = _q(conn, "SELECT procedencia_texto AS k, count(*) AS n FROM leituras GROUP BY 1 ORDER BY 2 DESC, 1")
    execs = _q(conn, "SELECT origem || CASE WHEN canonica THEN ' (canônica)' ELSE ' (não canônica)' END AS k,"
                     " count(*) AS n FROM execucoes_modelo GROUP BY 1 ORDER BY 2 DESC, 1")
    partes = [_tabela(["medida", "valor"], base)]
    for titulo, rows in (("Licitações por estado", estados), ("Arquivos por status", status),
                         ("Leituras por procedência do texto", leituras), ("Execuções por origem", execs)):
        partes.append("**%s:** %s" % (titulo, "; ".join("%s %s" % (r["k"], r["n"]) for r in rows) or "nenhuma"))
    return "\n\n".join(partes)


def _duplicados(conn) -> str:
    rows = _q(conn, "SELECT controle, pasta, canonica, motivo FROM pastas_legado"
                    " WHERE controle IN (SELECT controle FROM pastas_legado GROUP BY 1 HAVING count(*) > 1)"
                    " ORDER BY controle, pasta")
    if not rows:
        return "Nenhum controle com mais de uma pasta."
    n = len({r["controle"] for r in rows})
    return ("%d controle(s). Todas as pastas entraram em `pastas_legado`; a canônica é a que dá os"
            " metadados e a leitura vigente.\n\n" % n
            + _tabela(["controle", "pasta", "canônica", "motivo"],
                      [[r["controle"], r["pasta"], r["canonica"], r["motivo"]] for r in rows]))


def _incerta(conn) -> str:
    arqs = _q(conn, "SELECT controle, seq, nome, motivo FROM arquivos WHERE status = 'procedencia_incerta'"
                    " ORDER BY controle, seq, nome")
    lics = _q(conn, "SELECT controle, estado::text AS estado FROM licitacoes WHERE procedencia_incerta"
                    " ORDER BY controle")
    if not arqs and not lics:
        return "Nenhum arquivo nem licitação de procedência incerta."
    partes = []
    if arqs:
        partes.append("%d arquivo(s) sem correspondência no `/arquivos` do controle — não são lidos nem"
                      " publicados até decisão:\n\n" % len(arqs)
                      + _tabela(["controle", "seq", "arquivo", "motivo"],
                                [[r["controle"], r["seq"], r["nome"], r["motivo"]] for r in arqs]))
    if lics:
        partes.append("%d licitação(ões) marcadas `procedencia_incerta`:\n\n" % len(lics)
                      + _tabela(["controle", "estado"], [[r["controle"], r["estado"]] for r in lics]))
    return "\n\n".join(partes)


def _inferida(conn) -> str:
    rows = _q(conn, "SELECT id, controle, origem, provedor, modelo, canonica, brl_legado,"
                    " fonte_migracao->'inferidos' AS inferidos,"
                    " coalesce(fonte_migracao->>'pasta', fonte_migracao->>'arquivo', fonte_migracao->>'chave') AS fonte"
                    " FROM execucoes_modelo WHERE NOT procedencia_completa ORDER BY origem, controle, id")
    if not rows:
        return "Nenhuma execução com procedência inferida."
    sem_fonte = sum(1 for r in rows if not r["fonte"])
    cab = ("%d execução(ões) com campo deduzido — custo e tokens como vieram, nunca recalculados;"
           " %s sem `fonte_migracao`.\n\n" % (len(rows), "nenhuma" if not sem_fonte else sem_fonte))
    return cab + _tabela(["execução", "controle", "origem", "provedor", "modelo", "canônica",
                          "R$ legado", "campos inferidos", "fonte"],
                         [[r["id"], r["controle"], r["origem"], r["provedor"], r["modelo"], r["canonica"],
                           r["brl_legado"], r["inferidos"], r["fonte"]] for r in rows])


def _gemeas(conn) -> str:
    rows = _q(conn, "SELECT controle, gemea_de, estado::text AS estado FROM licitacoes"
                    " WHERE gemea_de IS NOT NULL ORDER BY gemea_de, controle")
    if not rows:
        return "Nenhuma gêmea registrada."
    return ("%d controle(s) com o mesmo conjunto de documentos de outro (`gemea_de`)."
            " Gêmea não é duplicata: cada controle segue com a sua licitação.\n\n" % len(rows)
            + _tabela(["controle", "gêmea de", "estado"],
                      [[r["controle"], r["gemea_de"], r["estado"]] for r in rows]))


def _fora_escopo(conn) -> str:
    rows = _q(conn, "SELECT l.controle, l.municipio, l.uf, l.escopo_motivo, v.id AS verificacao"
                    " FROM licitacoes l JOIN verificacoes v ON v.controle = l.controle AND v.vigente"
                    " WHERE NOT l.escopo_dentro ORDER BY l.controle")
    if not rows:
        return "Nenhum controle extraído está fora do escopo pela regra de hoje."
    return ("%d extraída(s) que a regra de escopo de hoje põe fora — o dado existe; decidir se fica"
            " visível ou vai para o rótulo humano.\n\n" % len(rows)
            + _tabela(["controle", "município", "UF", "motivo da regra", "verificação vigente"],
                      [[r["controle"], r["municipio"], r["uf"], r["escopo_motivo"], r["verificacao"]]
                       for r in rows]))


def _canonicas(conn) -> str:
    rows = _q(conn, """
        WITH c AS (
          SELECT controle FROM execucoes_modelo
           WHERE canonica AND fonte_migracao ? 'pasta'
           GROUP BY controle HAVING count(DISTINCT fonte_migracao->>'pasta') > 1)
        SELECT e.controle, e.id, e.origem, e.fonte_migracao->>'pasta' AS pasta,
               (SELECT v.id FROM verificacoes v WHERE v.execucao_id = e.id AND v.vigente) AS vigente
          FROM execucoes_modelo e JOIN c USING (controle)
         WHERE e.canonica AND e.fonte_migracao ? 'pasta'
         ORDER BY e.controle, e.id""")
    if not rows:
        return "Nenhum controle com execuções canônicas de pastas diferentes."
    n = len({r["controle"] for r in rows})
    return ("%d controle(s) com mais de uma execução canônica vinda de pastas diferentes do legado."
            " Só uma verificação é a vigente; a outra extração existe e não aparece — decidir qual vale.\n\n" % n
            + _tabela(["controle", "execução", "origem", "pasta", "verificação vigente"],
                      [[r["controle"], r["id"], r["origem"], r["pasta"], r["vigente"]] for r in rows]))


def _decisoes(conn) -> str:
    dec = [(r["id"], d) for r in _q(conn, "SELECT id, decisoes FROM importacoes ORDER BY id")
           for d in (r["decisoes"] or [])]
    susp = _q(conn, "SELECT controle, estado_motivo FROM licitacoes WHERE estado = 'legado_suspeito'"
                    " ORDER BY controle")
    if not dec and not susp:
        return "Nenhuma decisão pendente: nenhum empate sem critério na escolha da pasta canônica."
    partes = []
    if dec:
        partes.append("\n".join("- importação %s: %s — pastas %s (%s)"
                                % (i, d.get("controle"), _cel(d.get("pastas")), d.get("motivo"))
                                for i, d in dec))
    if susp:
        partes.append(_tabela(["controle (legado_suspeito)", "motivo"],
                              [[r["controle"], r["estado_motivo"]] for r in susp]))
    return "\n\n".join(partes)


SECOES = (
    ("Importações", _importacoes),
    ("Contagens", _contagens),
    ("Controles com mais de uma pasta", _duplicados),
    ("Procedência incerta", _incerta),
    ("Procedência inferida", _inferida),
    ("Gêmeas", _gemeas),
    ("Extraídas fora do escopo", _fora_escopo),
    ("Mais de uma execução canônica", _canonicas),
    ("Decisões pendentes", _decisoes),
)


def montar(conn, hoje: date) -> str:
    conn.row_factory = dict_row
    partes = ["# Reconciliação da migração — %s" % hoje.isoformat(),
              "Seção 9, passo 8 do plano da v3. Gerado por `python -m migracao.relatorio`, só leitura do"
              " banco. Cada seção diz também quando está vazia."]
    for titulo, fn in SECOES:
        partes.append("## %s\n\n%s" % (titulo, fn(conn)))
    return "\n\n".join(partes) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Relatório de reconciliação da migração (seção 9, passo 8).")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--hoje", default=date.today().isoformat())
    ap.add_argument("--saida", default=None, help="padrão: migracao/relatorio-<hoje>.md")
    a = ap.parse_args(argv)
    if not a.database_url:
        print("falta --database-url (ou DATABASE_URL)", file=sys.stderr)
        return 2
    hoje = date.fromisoformat(a.hoje)
    saida = Path(a.saida) if a.saida else RAIZ / "migracao" / ("relatorio-%s.md" % hoje.isoformat())
    with psycopg.connect(a.database_url) as conn:
        texto = montar(conn, hoje)
    saida.write_text(texto, encoding="utf-8", newline="\n")
    print(saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
