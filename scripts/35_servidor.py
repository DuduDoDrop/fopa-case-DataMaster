# -*- coding: utf-8 -*-
"""
Servidor local do painel — o botão "atualizar" que fala com o PNCP.

    python 35_servidor.py              sobe em http://127.0.0.1:8770
    python 35_servidor.py --porta 9000

POR QUE PRECISA DE SERVIDOR
  O painel é HTML estático: ele não consegue consultar o PNCP nem disparar uma
  extração. Um arquivo aberto do disco não tem como executar Python.

  Este servidor é a ponte, e é deliberadamente mínimo: serve `amostras/` e expõe
  dois endpoints. Nada de framework, nada de dependência nova — `http.server` da
  biblioteca padrão.

A SEPARAÇÃO QUE IMPORTA
  `/api/verificar` é GRÁTIS: consulta o PNCP, roda o filtro de escopo e responde
  quantas licitações novas são de folha. Nenhum modelo é chamado.

  `/api/processar` GASTA: baixa documentos e roda a extração. Só é acionado por
  um clique humano, depois de ver o número e o custo estimado.

  Essa fronteira não é detalhe de implementação — é a razão do desenho. Um botão
  que descobrisse e processasse no mesmo clique gastaria dinheiro sem ninguém ter
  decidido gastar.

SEGURANÇA
  Escuta em 127.0.0.1 e só isso: nada exposto para fora da máquina. Não há
  autenticação porque não há superfície — se um dia precisar ouvir em 0.0.0.0,
  precisa de autenticação ANTES.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

for _f in (sys.stdout, sys.stderr):
    try:
        _f.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

AMOSTRAS = os.path.join(RAIZ, "amostras")
SAIDAS = os.path.join(RAIZ, "saidas")

# Custo médio medido por edital, em reais. Serve só para o aviso antes do
# clique; o custo real sai da fatura depois (`32_custo_real.py`).
CUSTO_POR_EDITAL = 4.34

_trabalho = {"rodando": False, "log": [], "feito": 0, "total": 0}


def _descobrir() -> dict:
    """Consulta o PNCP e conta o que é folha e ainda não está no acervo. Custo R$ 0,00."""
    from fopa import escopo, pncp                                 # noqa: PLC0415
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "baixar", os.path.join(AQUI, "28_baixar_licitacao.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    try:
        itens = pncp.dedup(pncp.buscar("folha de pagamento", paginas=2, tam=50))
    except Exception as e:                                        # noqa: BLE001
        return {"erro": "PNCP indisponível: %s" % str(e)[:120]}

    pastas = m.pastas_no_disco()
    novas = []
    for it in itens:
        lic = pncp.Licitacao.de_item(it)
        if lic is None:
            continue
        objeto = it.get("description") or ""
        dentro, motivo = escopo.avaliar(objeto)
        if not dentro:
            continue
        reg = {"controle": lic.controle,
               "orgao": it.get("orgao_nome") or it.get("orgao_razao_social") or "",
               "uf": it.get("uf") or it.get("uf_sigla") or "",
               "modalidade": it.get("modalidade_licitacao_nome") or "",
               "objeto": objeto}
        if m.ja_baixada(reg):
            continue
        novas.append({"controle": reg["controle"], "orgao": reg["orgao"],
                      "uf": reg["uf"], "modalidade": reg["modalidade"],
                      "motivo": motivo, "objeto": objeto[:180]})
    return {"vistas": len(itens), "novas": novas,
            "custo_estimado": round(len(novas) * CUSTO_POR_EDITAL, 2)}


def _processar(controles: list[str]) -> None:
    """Baixa e extrai, uma por vez. Roda em thread para não travar o painel."""
    _trabalho.update(rodando=True, log=[], feito=0, total=len(controles))
    try:
        for ctrl in controles:
            _trabalho["log"].append("baixando %s" % ctrl)
            r = subprocess.run(
                [sys.executable, "28_baixar_licitacao.py", "--controle", ctrl],
                cwd=AQUI, capture_output=True, text=True, timeout=900)
            if r.returncode != 0:
                _trabalho["log"].append("  falhou o download de %s" % ctrl)
                continue
            # a pasta criada é a última modificada em amostras/
            pastas = [d for d in os.listdir(AMOSTRAS)
                      if os.path.isdir(os.path.join(AMOSTRAS, d))
                      and not d.startswith("_")]
            alvo = max(pastas, key=lambda d: os.path.getmtime(
                os.path.join(AMOSTRAS, d)))
            _trabalho["log"].append("extraindo %s" % alvo)
            subprocess.run([sys.executable, "10_extrair_edital.py", alvo],
                           cwd=AQUI, capture_output=True, text=True, timeout=1800)
            _trabalho["feito"] += 1
        subprocess.run([sys.executable, "16_painel.py"], cwd=AQUI,
                       capture_output=True, text=True, timeout=300)
        _trabalho["log"].append("painel regenerado")
    except Exception as e:                                        # noqa: BLE001
        _trabalho["log"].append("erro: %s" % str(e)[:160])
    finally:
        _trabalho["rodando"] = False


class Manipulador(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=AMOSTRAS, **kw)

    def log_message(self, *a):                                    # noqa: A003
        pass                                                      # silêncio

    def _json(self, dados: dict, codigo: int = 200) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):                                             # noqa: N802
        if self.path.startswith("/api/verificar"):
            print("  consultando o PNCP...", flush=True)
            return self._json(_descobrir())
        if self.path.startswith("/api/status"):
            return self._json({k: v for k, v in _trabalho.items()})
        return super().do_GET()

    def do_POST(self):                                            # noqa: N802
        if not self.path.startswith("/api/processar"):
            return self._json({"erro": "rota desconhecida"}, 404)
        if _trabalho["rodando"]:
            return self._json({"erro": "já há um processamento em curso"}, 409)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            pedido = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except ValueError:
            return self._json({"erro": "corpo inválido"}, 400)
        controles = pedido.get("controles") or []
        if not controles:
            return self._json({"erro": "nenhuma licitação informada"}, 400)
        threading.Thread(target=_processar, args=(controles,),
                         daemon=True).start()
        return self._json({"iniciado": len(controles)})


def main() -> int:
    ap = argparse.ArgumentParser(description="Servidor local do painel")
    ap.add_argument("--porta", type=int, default=8770)
    ap.add_argument("--sem-abrir", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(os.path.join(AMOSTRAS, "index.html")):
        print("painel não existe ainda — rode antes: python 16_painel.py")
        return 2

    url = "http://127.0.0.1:%d/index.html" % a.porta
    print("=" * 78)
    print("  PAINEL FOPA — %s" % url)
    print("=" * 78)
    print("  verificar ... consulta o PNCP e aplica o filtro     R$ 0,00")
    print("  processar ... baixa e extrai                        ~R$ %.2f por edital"
          % CUSTO_POR_EDITAL)
    print("\n  Escutando só em 127.0.0.1. Ctrl+C encerra.\n")

    servidor = ThreadingHTTPServer(("127.0.0.1", a.porta), Manipulador)
    if not a.sem_abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  encerrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
