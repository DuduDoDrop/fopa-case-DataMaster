# -*- coding: utf-8 -*-
"""
Painel — a porta de entrada para quem NÃO vai abrir um JSON.

O `pagina.py` responde "o que diz este edital". Este responde a pergunta que vem
antes, e que é a de negócio: **em quais destes o banco entra, e o que fecha primeiro?**

Por isso a ordenação padrão é por prazo, não por nome nem por valor. Um edital
com resposta perfeita e sessão amanhã é mais urgente que um impecável para o mês
que vem, e uma lista alfabética esconde exatamente isso.

Fica em `amostras/index.html`, junto das pastas das licitações, para que os links
relativos abram o relatório e os PDFs sem servidor nenhum.
"""
from __future__ import annotations

import datetime
import html
import json
import os
import time
import re

from . import inventario

CSS = """
:root{color-scheme:light;--ink:#11243D;--ink2:#1B3454;--paper:#FFFFFF;--surf:#FFFFFF;--surf2:#F4F2EE;
--line:#DCD7CC;--muted:#55606E;--red:#B23A32;--reds:#F6E4E2;--teal:#1D6F63;
--teals:#DDEAE7;--amber:#8A6A18;--ambers:#F5EBD2;
--sans:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
--mono:'IBM Plex Mono',ui-monospace,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
font-size:15px;line-height:1.55;padding-inline:16px}
.wrap{max-width:1240px;margin-inline:auto;padding-block:32px 64px;
display:flex;flex-direction:column;gap:22px}
header h1{font-size:31px;font-weight:600;margin:0 0 6px;line-height:1.2}
.sub{color:var(--muted);margin:0;font-size:14.5px;max-width:78ch}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.16em;
text-transform:uppercase;color:var(--red);margin:0 0 8px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px}
.tile{background:var(--surf);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile b{display:block;font-family:var(--mono);font-size:22px;font-variant-numeric:tabular-nums}
.tile span{font-size:12.5px;color:var(--muted)}
.tile.ok b{color:var(--teal)} .tile.al b{color:var(--red)}
.barra{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.barra input{flex:1 1 240px;min-width:0;padding:9px 12px;border-radius:8px;
border:1px solid var(--line);background:var(--surf);color:var(--ink);
font-family:var(--sans);font-size:14px}
.barra button{padding:9px 13px;border-radius:8px;border:1px solid var(--line);
background:var(--surf);color:var(--ink2);font-family:var(--sans);font-size:13px;
cursor:pointer}
.barra button[aria-pressed=true]{background:var(--ink);color:var(--paper);
border-color:var(--ink)}
.card{background:var(--surf);border:1px solid var(--line);border-radius:12px;
overflow:hidden}
.card.urgente{border-left:4px solid var(--red)}
.card.aviso{border-left:4px solid var(--amber)}\ntd.gastou{color:var(--amber);font-weight:600}
.topo{display:grid;grid-template-columns:1fr auto;gap:12px;padding:15px 18px;
align-items:start}
.nome{font-size:17px;font-weight:600;margin:0 0 3px}
.meta{font-size:13px;color:var(--muted);margin:0}
.obj{font-size:13.5px;color:var(--ink2);margin:9px 0 0;max-width:92ch}
.prazo{text-align:right;white-space:nowrap}
.prazo b{display:block;font-family:var(--mono);font-size:19px;
font-variant-numeric:tabular-nums}
.prazo.urgente b{color:var(--red)} .prazo.aviso b{color:var(--amber)}
.prazo span{font-size:12px;color:var(--muted)}
.nums{display:flex;flex-wrap:wrap;gap:0;border-top:1px solid var(--line);
background:var(--surf2)}
.num{padding:10px 18px;border-right:1px solid var(--line);min-width:118px}
.num b{display:block;font-family:var(--mono);font-size:15px;
font-variant-numeric:tabular-nums}
.num span{font-size:11.5px;color:var(--muted);text-transform:uppercase;
letter-spacing:.06em}
.num.ok b{color:var(--teal)} .num.al b{color:var(--red)} .num.am b{color:var(--amber)}
.acoes{display:flex;flex-wrap:wrap;gap:8px;padding:12px 18px;
border-top:1px solid var(--line)}
.acoes a{font-size:13px;text-decoration:none;padding:7px 12px;border-radius:7px;
border:1px solid var(--line);color:var(--ink2);background:var(--surf)}
.acoes a.forte{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.acoes a:hover{border-color:var(--ink2)}
details.docs{border-top:1px solid var(--line)}
details.docs>summary{cursor:pointer;padding:11px 18px;font-size:13px;
color:var(--muted);list-style:none}
details.docs>summary::-webkit-details-marker{display:none}
details.docs>summary::before{content:'▸ ';color:var(--red)}
details.docs[open]>summary::before{content:'▾ '}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:var(--ink);color:var(--paper);text-align:left;font-size:11.5px;
letter-spacing:.06em;text-transform:uppercase;padding:9px 14px;font-weight:600}
td{padding:9px 14px;border-top:1px solid var(--line);vertical-align:top}
td a{color:var(--ink2)}
.sha{font-family:var(--mono);font-size:11px;color:var(--muted)}
.alerta{margin:0;padding:11px 18px;background:var(--reds);color:var(--red);
font-size:13px;border-top:1px solid var(--line)}
.vazio{padding:28px;text-align:center;color:var(--muted)}
footer{color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);
padding-top:16px}
@media(max-width:620px){.topo{grid-template-columns:1fr}.prazo{text-align:left}}

/* ---- atualizacao ao vivo (so com o servidor local) ---- */
.atual{display:flex;align-items:center;gap:14px;margin:18px 0 0;flex-wrap:wrap}
.primario{background:var(--teal);color:#fff;border:1px solid var(--teal);
border-radius:8px;padding:9px 16px;font-size:13.5px;font-weight:600;
cursor:pointer;font-family:inherit}
.primario:hover{filter:brightness(1.08)}
.primario:disabled{opacity:.55;cursor:default}
.atualmsg{font-size:12.5px;color:var(--muted)}
.achados{margin:14px 0 0;border:1px solid var(--line);border-radius:10px;
background:var(--surf);padding:16px 18px}
.achados h3{margin:0 0 8px;font-size:15px}
.achados ul{margin:8px 0 0;padding-left:18px}
.achados li{margin:5px 0;font-size:13px;line-height:1.45}
.achados .alerta{color:var(--amber);font-weight:600}
.acoes{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.secundario{background:transparent;color:var(--ink);border:1px solid var(--line);
border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer;font-family:inherit}
.progresso{margin-top:12px;font-family:var(--mono);font-size:12px;
color:var(--muted);white-space:pre-wrap;line-height:1.6}
"""

JS = """
const cards=[...document.querySelectorAll('.card')];
const busca=document.getElementById('busca');
const botoes=[...document.querySelectorAll('.barra button')];
let filtro='todos';
function aplica(){
  const q=(busca.value||'').toLowerCase().trim();
  let n=0;
  for(const c of cards){
    const texto=c.dataset.busca||'';
    const okTexto=!q||texto.includes(q);
    const okFiltro=filtro==='todos'
      ||(filtro==='urgente'&&c.dataset.dias!==''&&Number(c.dataset.dias)<=7)
      ||(filtro==='alerta'&&c.dataset.alertas==='1')
      ||(filtro==='conflito'&&Number(c.dataset.conflitos)>0)
      ||(filtro==='extraida'&&c.dataset.extraida==='1')
      ||(filtro==='sem-extracao'&&c.dataset.extraida!=='1');
    const mostra=okTexto&&okFiltro;
    c.hidden=!mostra; if(mostra)n++;
  }
  document.getElementById('vazio').hidden=n>0;
  document.getElementById('conta').textContent=n;
}
busca.addEventListener('input',aplica);
for(const b of botoes){b.addEventListener('click',()=>{
  filtro=b.dataset.filtro;
  for(const o of botoes)o.setAttribute('aria-pressed',String(o===b));
  aplica();});}
aplica();
"""



# "ABERTO Pregao - Eletronico - Adrianopolis-PR" -> Pregao - Eletronico | Adrianopolis | PR
RE_PASTA = re.compile(r"^(?:ABERTO\s+)?(?P<modalidade>.+?)\s+-\s+(?P<municipio>[^-]+)-(?P<uf>[A-Z]{2})$")


def _do_nome(nome: str) -> tuple[str, str, str]:
    """Deriva município, UF e modalidade do nome da pasta.

    Os inventários da primeira coleta não gravavam esses campos, e o cartão caía
    no nome da pasta duas vezes — em cima como título e embaixo como
    identificação, produzindo "Credenciamento - Santa Efigenia de Minas-MG"
    repetido logo abaixo de si mesmo.

    O nome da pasta já carrega a informação, porque foi montado a partir dela.
    Extrair de volta é mais honesto que repetir: nada é inventado, só relido.
    """
    m = RE_PASTA.match(nome.strip())
    if not m:
        return "", "", ""
    return m.group("municipio").strip(), m.group("uf"), m.group("modalidade").strip()


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


RE_DATA_Q1 = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})")


def _bloco_execucoes(limite: int = 8) -> str:
    """
    As últimas execuções, em HTML.

    POR QUE ISTO FICA NO PAINEL E NÃO NUM ARQUIVO DE LOG
      A pergunta do vault era *"definir para onde vai o log e quem lê"*, e a
      segunda metade é a que importa. Um `>> monitor.log` responde só a
      primeira: o arquivo cresce, ninguém abre, e quando alguém abre é porque
      já deu problema.

      Aqui o leitor é a tela que o operador já abre todo dia. Log que depende
      de alguém lembrar de ler não é auditoria — é arquivo morto com data.
    """
    try:
        from . import execucao
        regs = execucao.ler(limite)
    except Exception:                                             # noqa: BLE001
        return ""
    if not regs:
        return ""
    linhas = []
    for r in regs:
        feito = " · ".join(
            "%s %s" % (v, k) for k, v in sorted(r.items())
            if k not in ("em", "script", "duracao_s", "argumentos", "custo_brl")
            and isinstance(v, (int, float)) and v)
        custo = r.get("custo_brl", 0) or 0
        linhas.append(
            "<tr><td class=info>%s</td><td><code>%s</code></td>"
            "<td class=info>%.1fs</td><td class=\"info %s\">%s</td>"
            "<td>%s</td></tr>"
            % (_e(r.get("em", "")[:16].replace("T", " ")),
               _e(r.get("script", "")), r.get("duracao_s", 0) or 0,
               "gastou" if custo else "", "R$ %.2f" % custo,
               _e(feito) or "—"))
    return ("<h2>Últimas execuções</h2>"
            "<table><thead><tr><th>quando</th><th>o quê</th><th>duração</th>"
            "<th>custo</th><th>resultado</th></tr></thead><tbody>%s</tbody>"
            "</table>" % "".join(linhas))


def _data_da_q1(aud) -> str | None:
    """
    A data da sessão que a extração encontrou, em AAAA-MM-DD.

    POR QUE ISTO EXISTE
      O painel mostrava **"prazo não informado"** para Paulo Bento/RS, e a
      extração daquela mesma licitação responde a Q1 com `29/05/2025 às 14h00`,
      ancorada e aprovada no `Convocacao-Aviso de edital.pdf`.

      O dado estava no disco, verificado, e a tela dizia que não existia. Não é
      falta de informação: é informação que o painel não foi buscar.

      O caso não é raro por acaso — em 171 licitações, 3 foram publicadas no
      PNCP em ano posterior ao do processo, e uma delas com **16 meses** de
      atraso. Elas entram na busca parecendo novas.

    NÃO DECIDE NADA. Só mostra a data e diz se já passou. A régua de "vencida"
    — e o que fazer com ela — está em `BACKLOG.md`, porque é escolha de
    operação.
    """
    if not aud:
        return None
    for r in aud.get("respostas", []):
        if r.get("id") != "Q1":
            continue
        if r.get("veredito") != "APROVADO":
            return None          # data não verificada não vale para decidir nada
        m = RE_DATA_Q1.search(r.get("resposta") or "")
        if m:
            return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
    return None


def _dias(fim: str | None, hoje: datetime.date) -> int | None:
    """Dias até o fim do prazo. É o campo que ordena a lista."""
    if not fim:
        return None
    try:
        d = datetime.date.fromisoformat(fim[:10])
    except (ValueError, TypeError):
        return None
    return (d - hoje).days


def _brl(v) -> str:
    """R$ com separador de milhar.

    A versão anterior trocava ponto por vírgula e pronto, o que funcionava só
    abaixo de mil: `"%0.2f" % 1234.5` é "1234.50", e o Python não agrupa milhar
    sozinho. O custo acumulado passava de R$ 1.000 e virava "R$ 1234,56".
    """
    try:
        return "R$ " + ("{:,.2f}".format(float(v))
                        .replace(",", "\x00").replace(".", ",").replace("\x00", "."))
    except (TypeError, ValueError):
        return "—"


def coletar(amostras: str, saidas: str, hoje: datetime.date) -> list[dict]:
    """Junta inventário (o que é) com auditoria (o que se descobriu)."""
    itens = []
    for nome in sorted(os.listdir(amostras)):
        pasta = os.path.join(amostras, nome)
        if not os.path.isdir(pasta) or nome.startswith("_"):
            continue
        # LEITURA NORMALIZADA. O acervo tem 12 esquemas de inventario, e o
        # painel lia `numero_controle`, que existe em 8% das pastas. Nos
        # outros 92% o card saia SEM numero de controle -- nao na linha de
        # metadados e nao no indice de busca. Quem procurasse por controle no
        # painel nao achava quase nada, e o card nao mostrava o numero que
        # identifica a licitacao no PNCP.
        #
        # `fopa/inventario.ler` resolve `numero_controle` -> `controle` sem
        # apagar o original.
        inv_p = os.path.join(pasta, "_inventario.json")
        inv = inventario.ler(pasta) or {}
        if False:
            try:
                inv = json.load(open(inv_p, encoding="utf-8"))
            except (ValueError, OSError):
                inv = {}

        aud_p = os.path.join(saidas, nome, "auditoria.json")
        aud = None
        if os.path.isfile(aud_p):
            try:
                aud = json.load(open(aud_p, encoding="utf-8"))
            except (ValueError, OSError):
                aud = None

        itens.append(dict(
            nome=nome, inv=inv, aud=aud,
            tem_relatorio=os.path.isfile(os.path.join(pasta, "RELATORIO.html")),
            dias=_dias(inv.get("fim_prazo"), hoje)))

    # Prazo primeiro, e prazo vencido/ausente por último: a lista serve para
    # decidir onde entrar, e o que já fechou não é mais decisão.
    def chave(i):
        d = i["dias"]
        if d is None:
            return (2, 0, i["nome"])
        if d < 0:
            return (1, d, i["nome"])
        return (0, d, i["nome"])

    return sorted(itens, key=chave)


def _resposta(aud, qid) -> str:
    if not aud:
        return ""
    for r in aud.get("respostas", []):
        if r.get("id") == qid:
            return r.get("resposta", "") or ""
    return ""


def _card(it: dict) -> str:
    inv, aud, nome = it["inv"], it["aud"], it["nome"]
    dias = it["dias"]
    v = (aud or {}).get("verificacao", {})
    uso = (aud or {}).get("uso", {})

    nao_loc = v.get("nao_localizado", 0)
    respondidas = 17 - nao_loc if aud else 0
    ancoradas = int(round(v.get("taxa_ancorada", 0) * respondidas)) if aud else 0
    conflitos = sum(1 for r in (aud or {}).get("respostas", []) if r.get("conflito"))
    alertas = v.get("alertas_globais", []) or []

    if dias is None:
        # O inventário não trouxe prazo — mas a extração pode ter a data.
        d_q1 = _data_da_q1(aud)
        if d_q1:
            hoje_s = time.strftime("%Y-%m-%d")
            if d_q1 < hoje_s:
                cls, txt, sub = "", "sessão passou", "em %s (da Q1)" % (
                    "/".join(reversed(d_q1.split("-"))))
            else:
                cls, txt, sub = "", "sessão", "em %s (da Q1)" % (
                    "/".join(reversed(d_q1.split("-"))))
        else:
            cls, txt, sub = "", "—", "prazo não informado"
    elif dias < 0:
        cls, txt, sub = "", "encerrado", "há %d dia(s)" % abs(dias)
    elif dias <= 7:
        cls, txt, sub = "urgente", "%d dia%s" % (dias, "" if dias == 1 else "s"), "até a sessão"
    elif dias <= 20:
        cls, txt, sub = "aviso", "%d dias" % dias, "até a sessão"
    else:
        cls, txt, sub = "", "%d dias" % dias, "até a sessão"

    municipio = inv.get("municipio") or ""
    uf = inv.get("uf") or ""
    modalidade = inv.get("modalidade") or ""
    if not municipio or not uf or not modalidade:
        m_nome, uf_nome, mod_nome = _do_nome(nome)
        municipio = municipio or m_nome
        uf = uf or uf_nome
        modalidade = modalidade or mod_nome

    local = ("%s/%s" % (municipio, uf)) if (municipio and uf) else (
        municipio or inv.get("orgao") or nome)

    # A identificação só entra se acrescentar algo. Repetir o nome da pasta
    # embaixo do título produzia a linha "Credenciamento · Credenciamento -
    # Santa Efigenia de Minas-MG", que ocupa espaço e não informa nada.
    # `inventario.ler` ja resolveu `numero_controle` -> `controle`;
    # repetir o apelido aqui era a regra escrita duas vezes.
    controle = inv.get("controle") or ""
    partes_meta = [p for p in (modalidade or "modalidade não informada", controle) if p]
    meta = " &middot; ".join(_e(p) for p in partes_meta)

    arquivos = inv.get("arquivos") or []
    linhas = []
    for a in arquivos:
        arq = a.get("arquivo") or a.get("nome") or ""
        destino = "%s/%s" % (nome.replace("#", "%23"), arq.replace("#", "%23"))
        sha = (a.get("sha256") or "")[:16]
        linhas.append(
            "<tr><td>%s</td><td><a href=\"%s\">%s</a></td><td>%s</td>"
            "<td class=sha>%s</td></tr>"
            % (_e(a.get("tipo") or "—"), _e(destino.replace(" ", "%20")),
               _e(arq), _e(a.get("paginas") or "—"), _e(sha)))
    tabela_docs = (
        "<table><tr><th>Tipo</th><th>Arquivo</th><th>Pág.</th><th>SHA-256</th></tr>"
        + "".join(linhas) + "</table>") if linhas else "<p class=vazio>sem inventário</p>"

    acoes = []
    if it["tem_relatorio"]:
        acoes.append("<a class=forte href=\"%s/RELATORIO.html\">Ver as 17 respostas</a>"
                     % _e(nome.replace(" ", "%20").replace("#", "%23")))
    else:
        acoes.append("<a href=\"#\" aria-disabled=true "
                     "title=\"esta licitação ainda não foi extraída\">sem extração</a>")
    if inv.get("link"):
        acoes.append("<a href=\"%s\" target=_blank rel=noopener>Abrir no PNCP</a>"
                     % _e(inv["link"]))

    if aud:
        nums = (
            "<div class='num %s'><b>%d/%d</b><span>ancoragem</span></div>"
            "<div class='num %s'><b>%d</b><span>conflitos</span></div>"
            "<div class=num><b>%d</b><span>não localizado</span></div>"
            "<div class='num %s'><b>%d</b><span>revisar</span></div>"
            "<div class=num><b>%s</b><span>custo</span></div>"
            % ("ok" if ancoradas == respondidas and respondidas else "al",
               ancoradas, respondidas,
               "am" if conflitos else "", conflitos,
               nao_loc,
               "am" if v.get("revisar") else "", v.get("revisar", 0),
               _brl(uso.get("brl"))))
    else:
        nums = "<div class=num><b>—</b><span>ainda não extraída</span></div>"

    bloco_alertas = "".join(
        "<p class=alerta>%s</p>" % _e(g[:300]) for g in alertas[:3])

    busca = " ".join([nome, local, municipio, uf, modalidade, controle,
                      inv.get("orgao") or "", inv.get("licitacao") or "",
                      inv.get("objeto") or ""]).lower()

    # `data-extraida` existe porque o acervo passou de 183 para 292 num dia e
    # ficou impossível achar a olho o que já foi lido. As 10 extraídas são
    # 3% do painel; sem filtro, elas somem no meio das outras 282.
    return """<article class="card %s" data-dias="%s" data-conflitos="%d"
 data-alertas="%d" data-extraida="%d" data-busca="%s">
 <div class=topo>
  <div>
   <p class=nome>%s</p>
   <p class=meta>%s</p>
   <p class=obj>%s</p>
  </div>
  <div class="prazo %s"><b>%s</b><span>%s</span></div>
 </div>
 <div class=nums>%s</div>
 %s
 <details class=docs><summary>Documentos do edital (%d)</summary>%s</details>
 <div class=acoes>%s</div>
</article>""" % (
        cls, "" if dias is None else dias, conflitos, 1 if alertas else 0,
        1 if it.get("aud") else 0, _e(busca),
        _e(local), meta,
        _e((inv.get("objeto") or "")[:340]),
        cls, _e(txt), _e(sub),
        nums, bloco_alertas, len(arquivos), tabela_docs, " ".join(acoes))


def escrever(amostras: str, saidas: str, destino: str,
             hoje: datetime.date | None = None) -> str:
    hoje = hoje or datetime.date.today()
    itens = coletar(amostras, saidas, hoje)

    extraidas = [i for i in itens if i["aud"]]
    resp = sum(17 - i["aud"]["verificacao"].get("nao_localizado", 0) for i in extraidas)
    anc = sum(int(round(i["aud"]["verificacao"].get("taxa_ancorada", 0)
                        * (17 - i["aud"]["verificacao"].get("nao_localizado", 0))))
              for i in extraidas)
    confl = sum(sum(1 for r in i["aud"].get("respostas", []) if r.get("conflito"))
                for i in extraidas)
    # `brl` e `null` quando nao ha tabela de preco (e na extracao por agente,
    # que nao passa pela API). `.get("brl", 0)` devolvia o None e o painel
    # inteiro caia no `sum`.
    custo = sum(i["aud"].get("uso", {}).get("brl") or 0 for i in extraidas)
    urgentes = sum(1 for i in itens if i["dias"] is not None and 0 <= i["dias"] <= 7)

    tiles = (
        "<div class=tile><b>%d</b><span>licitações</span></div>"
        "<div class=tile><b>%d</b><span>extraídas</span></div>"
        "<div class='tile %s'><b>%d</b><span>fecham em ≤7 dias</span></div>"
        "<div class='tile %s'><b>%d/%d</b><span>ancoragem</span></div>"
        "<div class=tile><b>%d</b><span>conflitos achados</span></div>"
        "<div class=tile><b>%s</b><span>custo acumulado</span></div>"
        % (len(itens), len(extraidas),
           "al" if urgentes else "", urgentes,
           "ok" if anc == resp and resp else "al", anc, resp,
           confl, _brl(custo)))

    cards = "\n".join(_card(i) for i in itens)

    corpo = """<title>Painel FOPA</title>
<style>%s</style>
<div class=wrap>
 <header>
  <p class=eyebrow>Folha de pagamento · setor público</p>
  <h1>Painel de licitações</h1>
  <p class=sub>Ordenado por <b>prazo</b>, não por nome: a decisão de negócio é
  onde entrar e o que fecha primeiro. Cada resposta abre o PDF na página citada.</p>
 </header>
 <div class=tiles>%s</div>
 <!-- ATUALIZAR: so aparece quando o painel e servido pelo `35_servidor.py`.
      Aberto direto do disco (file://) nao ha backend, e um botao morto e pior
      que botao nenhum: promete e nao entrega. -->
 <div id=atualizar class=atual hidden>
  <button id=btnver class=primario>Verificar licitações novas</button>
  <span id=vermsg class=atualmsg>consulta o PNCP e aplica o filtro de folha · <b>R$ 0,00</b></span>
 </div>
 <div id=achados class=achados hidden></div>
 <div class=barra>
  <input id=busca type=search placeholder="Filtrar por município, órgão, modalidade ou objeto…"
   aria-label="Filtrar licitações">
  <button data-filtro=todos aria-pressed=true>Todas</button>
  <button data-filtro=urgente aria-pressed=false>Fecham em ≤7 dias</button>
  <button data-filtro=conflito aria-pressed=false>Com conflito</button>
  <button data-filtro=alerta aria-pressed=false>Com alerta de regra</button>
  <button data-filtro=extraida aria-pressed=false>J&aacute; extra&iacute;das</button>
  <button data-filtro=sem-extracao aria-pressed=false>Sem extra&ccedil;&atilde;o</button>
 </div>
 <p class=sub><b id=conta>0</b> licitação(ões) na lista</p>
 %s
 <p id=vazio class=vazio hidden>Nenhuma licitação corresponde ao filtro.</p>
 <script>
 // O painel so mostra o botao se houver backend atras. A sonda e barata e
 // falha rapido: aberto do disco, `fetch` rejeita e o bloco continua oculto.
 (function(){
   var box=document.getElementById('atualizar'), achados=document.getElementById('achados');
   var btn=document.getElementById('btnver'), msg=document.getElementById('vermsg');
   fetch('/api/status').then(function(r){ if(r.ok) box.hidden=false; }).catch(function(){});

   function esc(t){ var d=document.createElement('div'); d.textContent=t||''; return d.innerHTML; }

   btn.addEventListener('click', function(){
     btn.disabled=true; msg.textContent='consultando o PNCP…';
     fetch('/api/verificar').then(function(r){return r.json();}).then(function(d){
       btn.disabled=false; msg.textContent='consulta o PNCP e aplica o filtro de folha · R$ 0,00';
       achados.hidden=false;
       if(d.erro){ achados.innerHTML='<h3>Não deu para consultar</h3><p class=alerta>'+esc(d.erro)+'</p>'; return; }
       var n=d.novas.length;
       if(!n){ achados.innerHTML='<h3>Nada novo</h3><p>'+d.vistas+' licitações vistas no portal; nenhuma de folha que já não tenhamos.</p>'; return; }
       var h='<h3>'+n+' licitação(ões) nova(s) passam no filtro de folha</h3>';
       h+='<p>De '+d.vistas+' vistas no portal. Processar custaria <b>~R$ '+d.custo_estimado.toFixed(2)+'</b>.</p><ul>';
       d.novas.forEach(function(x){
         h+='<li><b>'+esc(x.orgao)+'/'+esc(x.uf)+'</b> — '+esc(x.modalidade)+'<br><span style="color:var(--muted)">'+esc(x.motivo)+'</span></li>';
       });
       h+='</ul><div class=acoes><button id=btnproc class=primario>Processar as '+n+'</button>'
        +'<button id=btnnao class=secundario>Agora não</button></div><div id=prog class=progresso></div>';
       achados.innerHTML=h;
       document.getElementById('btnnao').onclick=function(){ achados.hidden=true; };
       document.getElementById('btnproc').onclick=function(){
         var ctrls=d.novas.map(function(x){return x.controle;});
         this.disabled=true; this.textContent='processando…';
         fetch('/api/processar',{method:'POST',headers:{'Content-Type':'application/json'},
           body:JSON.stringify({controles:ctrls})}).then(function(r){return r.json();}).then(function(){
             var p=document.getElementById('prog');
             var t=setInterval(function(){
               fetch('/api/status').then(function(r){return r.json();}).then(function(st){
                 p.textContent=(st.feito||0)+' de '+(st.total||0)+'\n'+(st.log||[]).join('\n');
                 if(!st.rodando){ clearInterval(t); p.textContent+='\n\nPronto. Recarregue a página.'; }
               });
             },2000);
           });
       };
     }).catch(function(e){
       btn.disabled=false; achados.hidden=false;
       achados.innerHTML='<h3>Falhou</h3><p class=alerta>'+esc(String(e))+'</p>';
     });
   });
 })();
 </script>
 %s
 <footer>
  Gerado em %s a partir de <code>_inventario.json</code> e <code>auditoria.json</code>.
  Fonte dos documentos: PNCP — dados abertos, Lei 14.133/2021 art. 54.
  Nenhum dado pessoal é armazenado.
 </footer>
</div>
<script>%s</script>
""" % (CSS, tiles, cards, _bloco_execucoes(), hoje.strftime("%d/%m/%Y"), JS)

    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write(corpo)
    return destino
