# -*- coding: utf-8 -*-
"""
Escreve o plano de importação no Postgres e os PDFs no storage (plano, seção 9).

    python -m migracao.importar --snapshot acervo/2026-09-24_0150 --amostras amostras \
        [--database-url URL] [--storage-root DIR] [--hoje AAAA-MM-DD] [--seco]

GARANTIAS
  · Uma transação só: um PDF que mudou depois do snapshot (sha diferente do
    manifesto) aborta TUDO, e o banco fica como estava.
  · Idempotente: toda linha tem chave natural (controle, pasta, controle+nome,
    controle+assinatura+versão, chave_migracao, execução+versão das regras) e
    entra com ON CONFLICT DO NOTHING. Rodar duas vezes não muda nada; rodar
    sobre um snapshot maior só acrescenta.
  · Nunca desfaz a v3: estado de licitação só é escrito no nascimento, e
    leitura/verificação vigente só é marcada quando o controle ainda não tem
    uma. Reimportar depois que o worker produziu uma leitura nova não devolve
    a vigência ao legado.
  · Nenhuma chamada de modelo, nenhum OCR: o texto é o congelado pelo agente.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import time
from datetime import date

import psycopg
from psycopg.types.json import Jsonb

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from api.storage import Storage, chave_pdf  # noqa: E402

from migracao import plano as plano_mod  # noqa: E402
from migracao import regras  # noqa: E402
from migracao.acervo import Acervo  # noqa: E402

RE_OFFSET = re.compile(r"([+-]\d{2})(\d{2})$")
FUSO_LOCAL = "-03:00"      # o manifesto grava mtime em hora local sem fuso


def _ts(s: str | None, local_sem_fuso: bool = False) -> str | None:
    """'2026-09-23T23:57:55-0300' -> '...-03:00'; hora local sem fuso ganha -03:00."""
    if not s:
        return None
    s = str(s).strip()
    s = RE_OFFSET.sub(r"\1:\2", s)
    if local_sem_fuso and not re.search(r"[+-]\d{2}:\d{2}$|Z$", s):
        s += FUSO_LOCAL
    return s


def _jsonb(v):
    return Jsonb(v) if v is not None else None


# ------------------------------------------------------------------ licitações
COLUNAS_LIC = ("ano", "seq", "orgao", "uf", "municipio", "modalidade", "objeto", "situacao",
               "publicado_em", "fim_prazo", "fim_prazo_tem_hora", "link", "atualizado_pncp",
               "visto_em", "escopo_dentro", "escopo_motivo", "escopo_versao", "rotulo", "origem")


def _licitacoes(conn, plano, imp_id, cont):
    sql = ("INSERT INTO licitacoes (controle, %s, estado, estado_motivo, procedencia_incerta)"
           " VALUES (%%s, %s, %%s, %%s, %%s) ON CONFLICT (controle) DO NOTHING RETURNING controle"
           % (", ".join(COLUNAS_LIC), ", ".join(["%s"] * len(COLUNAS_LIC))))
    for c, lic in plano.licitacoes.items():
        valores = [lic.campos.get(k) for k in COLUNAS_LIC]
        novo = conn.execute(sql, [c, *valores, lic.estado, lic.estado_motivo,
                                  lic.procedencia_incerta]).fetchone()
        if not novo:
            continue
        cont["licitacoes"] += 1
        # O nascimento é um evento: de NULL para o estado em que o acervo estava.
        conn.execute(
            "INSERT INTO licitacao_eventos (controle, de, para, motivo, dados)"
            " VALUES (%s, NULL, %s, %s, %s)",
            (c, lic.estado, "importado do acervo v2 (snapshot %s)" % plano.carimbo,
             Jsonb({"importacao": imp_id, "pastas": lic.pastas, "canonica": lic.canonica,
                    "canonica_motivo": lic.canonica_motivo, "estado_motivo": lic.estado_motivo})))
        cont["eventos"] += 1


def _pastas(conn, plano, cont):
    for p in plano.pastas_legado:
        r = conn.execute(
            "INSERT INTO pastas_legado (pasta, controle, canonica, motivo, manifesto_sha256)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (pasta) DO NOTHING RETURNING pasta",
            (p["pasta"], p["controle"], p["canonica"], p["motivo"], plano.manifesto_sha256)).fetchone()
        cont["pastas_legado"] += 1 if r else 0


# ------------------------------------------------------------------ arquivos
def _arquivos(conn, plano, acervo: Acervo, storage: Storage, cont) -> dict:
    """Linhas de `arquivos` e objetos no storage. Devolve {controle: {nome: id}}."""
    ids: dict[str, dict] = {}
    for c, linhas in plano.arquivos.items():
        cnpj, ano, seq = regras.partes_controle(c)
        for a in linhas:
            chave = None
            if a.tem_bytes and a.sha256:
                chave = chave_pdf(cnpj, ano, seq, a.sha256)
                if not storage.existe(chave):
                    # ler_pdf confere o sha contra o manifesto: divergência aborta tudo
                    storage.put(chave, acervo.ler_pdf(a.pasta, a.nome))
                    cont["objetos_storage"] += 1
            prov = dict(a.proveniencia or {}, pasta=a.pasta)
            r = conn.execute(
                "INSERT INTO arquivos (controle, seq, tipo, titulo, nome, sha256, bytes, bytes_aproximado,"
                " origem_url, status, motivo, paginas, chars, requer_ocr, storage_key, ativo_pncp, proveniencia)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (controle, nome) DO NOTHING RETURNING id",
                (c, a.seq, a.tipo, a.titulo, a.nome, a.sha256, a.bytes, a.bytes_aproximado,
                 a.origem_url, a.status, a.motivo, a.paginas, a.chars, a.requer_ocr, chave,
                 a.ativo_pncp, Jsonb(prov))).fetchone()
            cont["arquivos"] += 1 if r else 0
        mapa = dict(conn.execute("SELECT nome, id FROM arquivos WHERE controle = %s", (c,)).fetchall())
        for a in linhas:
            if a.pai and a.pai in mapa:
                conn.execute("UPDATE arquivos SET pai_id = %s WHERE id = %s AND pai_id IS NULL",
                             (mapa[a.pai], mapa[a.nome]))
            if a.alias_de and a.alias_de in mapa:
                conn.execute("UPDATE arquivos SET alias_de = %s WHERE id = %s AND alias_de IS NULL",
                             (mapa[a.alias_de], mapa[a.nome]))
        ids[c] = mapa
    return ids


# ------------------------------------------------------------------ leituras
def _leituras(conn, plano, acervo: Acervo, ids_arquivo, cont) -> dict:
    """Leituras + páginas congeladas. Devolve {pasta: leitura_id}."""
    por_pasta: dict[str, int] = {}
    vigentes = []
    for le in plano.leituras:
        r = conn.execute(
            "INSERT INTO leituras (controle, preparado_em, segundos, versao_ocr, tessdata_sha256,"
            " condicoes, hashes_bytes, assinatura, assinatura_conjunto, assinatura_nomes, modo_sugerido,"
            " chars_total, procedencia_texto, vigente)"
            " VALUES (%s, COALESCE(%s::timestamptz, now()), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, false)"
            " ON CONFLICT (controle, assinatura_nomes, versao_ocr) DO NOTHING RETURNING id",
            (le.controle, _ts(le.preparado_em), le.segundos, le.versao_ocr, le.tessdata_sha256,
             Jsonb(le.condicoes), Jsonb(le.hashes_bytes), Jsonb(le.assinatura), le.assinatura_conjunto,
             le.assinatura_nomes, le.modo_sugerido, le.chars_total, le.procedencia_texto)).fetchone()
        if r:
            lid = r[0]
            cont["leituras"] += 1
            cont["paginas"] += _paginas(conn, lid, le, acervo, ids_arquivo.get(le.controle, {}), cont)
        else:
            lid = conn.execute(
                "SELECT id FROM leituras WHERE controle = %s AND assinatura_nomes = %s AND versao_ocr = %s",
                (le.controle, le.assinatura_nomes, le.versao_ocr)).fetchone()[0]
        por_pasta[le.pasta] = lid
        if le.vigente:
            vigentes.append((le.controle, lid))
    for c, lid in vigentes:
        # Só quando o controle ainda não tem leitura vigente: reimportar nunca
        # tira a vigência de uma leitura nova feita pelo worker.
        r = conn.execute(
            "UPDATE leituras SET vigente = true WHERE id = %s AND NOT vigente"
            " AND NOT EXISTS (SELECT 1 FROM leituras WHERE controle = %s AND vigente) RETURNING id",
            (lid, c)).fetchone()
        if r:
            conn.execute("UPDATE licitacoes SET leitura_vigente_id = %s WHERE controle = %s", (lid, c))
    return por_pasta


def _paginas(conn, leitura_id, le, acervo: Acervo, ids_arquivo: dict, cont) -> int:
    dados = acervo.leitura(le.pasta) or {}
    ocr = set((dados.get("condicoes") or {}).get("arquivos_ocr") or [])
    linhas = []
    for ordem, p in enumerate(dados.get("paginas") or []):
        texto = p.get("texto") or ""
        if "\x00" in texto:
            # O Postgres não guarda NUL em text; nenhum trecho citável tem NUL.
            texto = texto.replace("\x00", "")
            cont["paginas_com_nul"] += 1
        arq = p.get("arquivo")
        if arq not in ids_arquivo:
            cont["paginas_sem_arquivo"] += 1
        linhas.append((leitura_id, ids_arquivo.get(arq), arq, p.get("numero"), ordem, texto, arq in ocr))
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO paginas (leitura_id, arquivo_id, arquivo_nome, numero, ordem, texto, via_ocr)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING", linhas)
    return len(linhas)


# ------------------------------------------------------------------ execuções
COLUNAS_EXEC = ("origem", "provedor", "modelo", "modo", "effort", "lote", "k_rag", "rotulo", "chamadas",
                "tok_entrada", "tok_saida", "tok_cache_escrita", "tok_cache_leitura", "tok_raciocinio",
                "segundos", "usd", "brl", "preco_conhecido", "status", "canonica",
                "procedencia_completa", "brl_legado", "custo_formula", "respostas_sha256")


def _quando(ex, acervo: Acervo) -> tuple[str | None, bool]:
    """Quando a execução terminou; (valor, inferido)."""
    if ex.finalizado_em:
        return _ts(ex.finalizado_em), False
    if ex.origem in ("api", "experimento"):
        m = acervo.mtime("saidas/%s/auditoria.json" % ex.pasta)
    elif ex.origem == "harness":
        m = acervo.mtime("saidas/%s" % ex.fonte_migracao.get("arquivo"))
    else:
        m = None
    return _ts(m, local_sem_fuso=True), bool(m)


def _execucoes(conn, plano, acervo: Acervo, ids_leitura, ids_arquivo, cont) -> dict:
    ids: dict[str, int] = {}
    sql = ("INSERT INTO execucoes_modelo (controle, leitura_id, %s, fonte_migracao, iniciado_em,"
           " finalizado_em, chave_migracao) VALUES (%%s, %%s, %s, %%s,"
           " COALESCE(%%s::timestamptz, now()), %%s, %%s)"
           " ON CONFLICT (chave_migracao) DO NOTHING RETURNING id"
           % (", ".join(COLUNAS_EXEC), ", ".join(["%s"] * len(COLUNAS_EXEC))))
    promover = []
    for ex in plano.execucoes:
        quando, inferido = _quando(ex, acervo)
        fonte = dict(ex.fonte_migracao)
        if inferido:
            fonte["inferidos"] = sorted(set(fonte.get("inferidos") or []) | {"finalizado_em (mtime)"})
        leitura_id = ids_leitura.get(ex.leitura_pasta) if ex.leitura_pasta else None
        valores = [getattr(ex, k) for k in COLUNAS_EXEC]
        r = conn.execute(sql, [ex.controle, leitura_id, *valores, Jsonb(fonte), quando, quando,
                               ex.chave]).fetchone()
        if r:
            eid = r[0]
            cont["execucoes"] += 1
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO respostas (execucao_id, pergunta_id, resposta, arquivo_citado,"
                    " pagina_citada, trecho_literal, conflito, confianca)"
                    " SELECT %s, %s, %s, %s, %s, %s, %s, %s WHERE EXISTS (SELECT 1 FROM perguntas WHERE id = %s)"
                    " ON CONFLICT DO NOTHING",
                    [(eid, x["pergunta_id"], x["resposta"], x["arquivo_citado"], x["pagina_citada"],
                      x["trecho_literal"], x["conflito"], x["confianca"], x["pergunta_id"])
                     for x in ex.respostas])
            cont["respostas"] += len(ex.respostas)
        else:
            eid = conn.execute("SELECT id FROM execucoes_modelo WHERE chave_migracao = %s",
                               (ex.chave,)).fetchone()[0]
        ids[ex.chave] = eid
        if ex.verificacao is not None:
            if _verificacao(conn, eid, ex, leitura_id, quando, ids_arquivo.get(ex.controle, {}), cont):
                promover.append(ex.controle)
    for ex in plano.execucoes:
        if ex.reaproveitado_de_pasta:
            origem = ids.get("agente:" + ex.reaproveitado_de_pasta)
            if origem:
                conn.execute("UPDATE execucoes_modelo SET reaproveitado_de = %s"
                             " WHERE id = %s AND reaproveitado_de IS NULL", (origem, ids[ex.chave]))
    for c in promover:
        _promover(conn, c, plano.carimbo, cont)
    return ids


def _verificacao(conn, eid, ex, leitura_id, quando, ids_arquivo, cont) -> bool:
    """Grava a verificação; devolve True se ela virou a vigente agora."""
    v = ex.verificacao
    r = conn.execute(
        "INSERT INTO verificacoes (execucao_id, controle, leitura_id, versao_regras, verificado_em,"
        " aprovadas, revisar, reprovadas, nao_localizado, ancoradas, respondidas, taxa_ancorada,"
        " alertas_globais, tags, degradada, condicoes, q13_estruturada, itens_api_usados,"
        " auditoria_json, vigente)"
        " VALUES (%s, %s, %s, %s, COALESCE(%s::timestamptz, now()), %s, %s, %s, %s, %s, %s, %s,"
        " %s, %s, %s, %s, %s, %s, %s, false)"
        " ON CONFLICT (execucao_id, versao_regras) DO NOTHING RETURNING id",
        (eid, ex.controle, leitura_id, v.versao_regras, quando, v.aprovadas, v.revisar,
         v.reprovadas, v.nao_localizado, v.ancoradas, v.respondidas, v.taxa_ancorada,
         v.alertas_globais, v.tags, v.degradada, Jsonb(v.condicoes), Jsonb(v.q13_estruturada),
         v.itens_api_usados, Jsonb(v.auditoria_json))).fetchone()
    if r:
        vid = r[0]
        cont["verificacoes"] += 1
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO verificacao_respostas (verificacao_id, pergunta_id, veredito,"
                " arquivo_canonico, arquivo_id, pagina_final, pagina_citada, alertas, ausencia)"
                " SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s WHERE EXISTS (SELECT 1 FROM perguntas WHERE id = %s)"
                " ON CONFLICT DO NOTHING",
                [(vid, x["pergunta_id"], x["veredito"], x["arquivo_canonico"],
                  ids_arquivo.get(x["arquivo_canonico"]), x["pagina_final"], x["pagina_citada"],
                  x["alertas"], x["ausencia"], x["pergunta_id"]) for x in v.respostas])
        cont["verificacao_respostas"] += len(v.respostas)
    else:
        vid = conn.execute("SELECT id FROM verificacoes WHERE execucao_id = %s AND versao_regras = %s",
                           (eid, v.versao_regras)).fetchone()[0]
    if not v.vigente:
        return False
    virou = conn.execute(
        "UPDATE verificacoes SET vigente = true WHERE id = %s AND NOT vigente"
        " AND NOT EXISTS (SELECT 1 FROM verificacoes WHERE controle = %s AND vigente) RETURNING id",
        (vid, ex.controle)).fetchone()
    return bool(virou)


def _promover(conn, controle, carimbo, cont):
    """
    Importação incremental: uma licitação que entrou `preparada` e, num
    snapshot posterior, ganhou extração do agente. O caminho no banco é o que
    de fato aconteceu fora dele: extraída, respondida, verificada.
    """
    estado = conn.execute("SELECT estado FROM licitacoes WHERE controle = %s", (controle,)).fetchone()[0]
    if estado != "preparada":
        return
    motivo = "importação incremental: extração por agente (snapshot %s)" % carimbo
    for para in ("extraindo", "respondida", "verificada"):
        conn.execute("SELECT fn_transicao(%s, %s, %s, NULL)", (controle, para, motivo))
    cont["promovidas"] += 1


# ------------------------------------------------------------------ auxiliares
def _auxiliares(conn, plano, cont):
    for g in plano.gabaritos:
        r = conn.execute(
            "INSERT INTO gabaritos (controle, pergunta_id, critica, resposta_referencia,"
            " fatos_obrigatorios, fatos_desejaveis, fonte) SELECT %s, %s, %s, %s, %s, %s, %s"
            " WHERE EXISTS (SELECT 1 FROM perguntas WHERE id = %s)"
            " ON CONFLICT DO NOTHING RETURNING controle",
            (g["controle"], g["pergunta_id"], g["critica"], g["resposta_referencia"],
             g["fatos_obrigatorios"], g["fatos_desejaveis"], Jsonb(g["fonte"]),
             g["pergunta_id"])).fetchone()
        cont["gabaritos"] += 1 if r else 0
    for c, payload in plano.itens_api.items():
        r = conn.execute("INSERT INTO itens_api (controle, payload) VALUES (%s, %s)"
                         " ON CONFLICT (controle) DO NOTHING RETURNING controle",
                         (c, Jsonb(payload))).fetchone()
        cont["itens_api"] += 1 if r else 0
    for w in plano.execucoes_workflow:
        r = conn.execute(
            "INSERT INTO execucoes_workflow (workflow, script_legado, iniciado_em, duracao_s,"
            " argumentos, custo_brl, contadores, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (script_legado, iniciado_em) WHERE script_legado IS NOT NULL DO NOTHING"
            " RETURNING id",
            (w["workflow"], w["script_legado"], _ts(w["iniciado_em"]), w["duracao_s"],
             Jsonb(w["argumentos"]), w["custo_brl"], Jsonb(w["contadores"]), w["status"])).fetchone()
        cont["execucoes_workflow"] += 1 if r else 0


def _gemeas(conn, plano):
    for c, lic in plano.licitacoes.items():
        if lic.gemea_de:
            conn.execute("UPDATE licitacoes SET gemea_de = %s WHERE controle = %s AND gemea_de IS NULL",
                         (lic.gemea_de, c))


# ------------------------------------------------------------------ aplicar
def aplicar(conn: psycopg.Connection, plano, acervo: Acervo, storage: Storage) -> dict:
    """Escreve o plano numa transação só. Devolve as contagens do que ENTROU agora."""
    cont: collections.Counter = collections.Counter()
    with conn.transaction():
        imp_id = conn.execute(
            "INSERT INTO importacoes (snapshot, manifesto_sha256) VALUES (%s, %s) RETURNING id",
            (plano.carimbo, plano.manifesto_sha256)).fetchone()[0]
        _licitacoes(conn, plano, imp_id, cont)
        _pastas(conn, plano, cont)
        ids_arquivo = _arquivos(conn, plano, acervo, storage, cont)
        ids_leitura = _leituras(conn, plano, acervo, ids_arquivo, cont)
        _execucoes(conn, plano, acervo, ids_leitura, ids_arquivo, cont)
        _auxiliares(conn, plano, cont)
        _gemeas(conn, plano)
        conn.execute("UPDATE importacoes SET finalizado_em = now(), contagens = %s, avisos = %s,"
                     " decisoes = %s WHERE id = %s",
                     (Jsonb(dict(cont)), Jsonb(plano.avisos), Jsonb(plano.decisoes), imp_id))
    for k in ("licitacoes", "execucoes", "paginas", "arquivos", "leituras", "verificacoes"):
        cont.setdefault(k, 0)
    return dict(cont)


# ------------------------------------------------------------------ CLI
def main(argv=None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Importa um snapshot do acervo v2 para o Postgres da v3.")
    ap.add_argument("--snapshot", required=True, help="acervo/<carimbo> gerado por congelar.py")
    ap.add_argument("--amostras", required=True, help="amostras/ vivo, de onde vêm os bytes dos PDFs")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--storage-root", default=os.environ.get("STORAGE_ROOT"))
    ap.add_argument("--hoje", default=date.today().isoformat())
    ap.add_argument("--seco", action="store_true", help="monta o plano e mostra; não escreve nada")
    a = ap.parse_args(argv)

    t0 = time.time()
    acervo = Acervo(a.snapshot, a.amostras)
    plano = plano_mod.montar(acervo, hoje=date.fromisoformat(a.hoje))
    estados = collections.Counter(l.estado for l in plano.licitacoes.values())
    print("plano do snapshot %s em %.1fs" % (plano.carimbo, time.time() - t0))
    print("  licitações ... %d  %s" % (len(plano.licitacoes), dict(estados.most_common())))
    print("  arquivos ..... %d" % sum(len(v) for v in plano.arquivos.values()))
    print("  leituras ..... %d  execuções %d  decisões pendentes %d  avisos %d"
          % (len(plano.leituras), len(plano.execucoes), len(plano.decisoes), len(plano.avisos)))
    if a.seco:
        print("seco: nada escrito")
        return 0
    if not a.database_url or not a.storage_root:
        print("faltam --database-url e --storage-root (ou DATABASE_URL / STORAGE_ROOT)", file=sys.stderr)
        return 2
    with psycopg.connect(a.database_url) as conn:
        cont = aplicar(conn, plano, acervo, Storage(a.storage_root))
    print("importado em %.1fs: %s" % (time.time() - t0, json.dumps(cont, ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
