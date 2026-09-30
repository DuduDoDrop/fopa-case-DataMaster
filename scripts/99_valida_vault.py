# -*- coding: utf-8 -*-
"""Valida os wikilinks do vault de entrega.

    python 99_valida_vault.py
    python 99_valida_vault.py --vault ../FOPA     (o vault v1, aposentado)

Um [[link]] quebrado so aparece quando alguem clica — que, na pratica, e durante
a apresentacao, diante de quem avalia. Sai com codigo 1 se houver quebra, para servir em CI.
"""
import argparse, os, re, io, collections, sys

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)

# O entregavel e o Fopa-v2, e o vault v1 foi APAGADO em 23/09/2026: manter dois
# vaults com o mesmo assunto so criava chance de abrir o errado na hora errada.
# Este script chegou a validar o v1 por um tempo, em silencio, enquanto os 800
# links do vault que importa nunca eram conferidos.
_ap = argparse.ArgumentParser()
_ap.add_argument("--vault", default=os.path.join(RAIZ, "Fopa-v2"))
BASE = _ap.parse_args().vault

if not os.path.isdir(BASE):
    print("vault nao encontrado: %s" % BASE)
    raise SystemExit(2)

notas = {}
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d != ".obsidian"]
    for f in files:
        if f.endswith(".md"):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, BASE).replace("\\", "/")
            notas[f[:-3]] = rel

print("=== ARVORE DO VAULT ===")
for root, dirs, files in os.walk(BASE):
    dirs[:] = [d for d in dirs if d != ".obsidian"]
    dirs.sort()
    rel = os.path.relpath(root, BASE)
    depth = 0 if rel == "." else rel.count(os.sep) + 1
    if rel != ".":
        print("  " * (depth - 1) + "|- " + os.path.basename(root) + "/")
    for f in sorted(files):
        if f.endswith((".md", ".canvas")):
            print("  " * depth + "|- " + f)

link_re = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
quebrados = collections.defaultdict(list)
total_links = 0
status_map = collections.defaultdict(list)
pendencias = {}

for nome, rel in sorted(notas.items()):
    txt = io.open(os.path.join(BASE, rel), encoding="utf-8").read()
    for alvo in link_re.findall(txt):
        alvo = alvo.strip()
        total_links += 1
        if alvo.endswith(".canvas"):
            if not os.path.exists(os.path.join(BASE, alvo)):
                quebrados[rel].append(alvo)
        elif alvo not in notas:
            quebrados[rel].append(alvo)
    m = re.search(r"^status:\s*(\S+)", txt, re.M)
    st = m.group(1) if m else "(sem status)"
    status_map[st].append(rel)
    todos = re.findall(r"^> \- \[ \] (.+)$", txt, re.M)
    if todos:
        pendencias[rel] = todos

print("\n=== LINKS ===")
print("total de wikilinks: %d" % total_links)
if quebrados:
    print("QUEBRADOS:")
    for k, v in sorted(quebrados.items()):
        for alvo in sorted(set(v)):
            print("   %s  ->  [[%s]]" % (k, alvo))
else:
    print("nenhum link quebrado.")

print("\n=== STATUS ===")
for st in sorted(status_map):
    print("%-14s %d notas" % (st, len(status_map[st])))

print("\n=== NOTAS 'a-verificar' E O QUE FALTA ===")
for rel in sorted(status_map.get("a-verificar", [])):
    print("\n## %s" % rel)
    for t in pendencias.get(rel, [])[:6]:
        print("   [ ] %s" % re.sub(r"\*\*|\[\[|\]\]|`", "", t)[:150])

print("\n=== SCRIPTS CITADOS ===")
# Uma nota que manda rodar um script inexistente quebra a demonstracao ao vivo
# com a mesma eficiencia de um link quebrado.
faltando = []
for _nome, _rel in sorted(notas.items()):
    _txt = io.open(os.path.join(BASE, _rel), encoding="utf-8").read()
    for _cam in re.findall(r"`(scripts/[A-Za-z0-9_./-]+\.py)`", _txt):
        if not os.path.isfile(os.path.join(RAIZ, _cam)):
            faltando.append((_rel, _cam))
if faltando:
    for _rel, _cam in faltando:
        print("   %s  ->  %s  (NAO EXISTE)" % (_rel, _cam))
else:
    print("todos os scripts citados existem.")

print("\n=== TOTAIS ===")
print("notas .md: %d" % len(notas))
print("links quebrados: %d" % sum(len(set(v)) for v in quebrados.values()))
raise SystemExit(1 if quebrados or faltando else 0)
