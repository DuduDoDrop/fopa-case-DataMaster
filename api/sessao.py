# -*- coding: utf-8 -*-
"""
Sessão do site: cookie assinado + linha em `sessoes` (plano, seção 8).

POR QUE COOKIE ASSINADO **E** TABELA
  Só o cookie assinado (sessão "stateless") não deixa sair de verdade: um
  cookie copiado continuaria valendo até expirar, e desativar um usuário não
  derrubaria quem já entrou. Só a tabela exigiria um id impossível de
  adivinhar e nada mais — mas aí qualquer valor inválido no cookie viraria consulta ao
  banco. Com os dois: a assinatura (itsdangerous, `SESSION_SECRET`) barra o
  valor inválido sem tocar no Postgres, e a linha em `sessoes` é o que "sair",
  "expirar" e "desativar usuário" apagam.

POR QUE O BANCO GUARDA O HASH DO ID
  `sessoes.id` = sha256 do id que está no cookie. Um dump do banco (backup,
  réplica, o `psql` de alguém) não vira sessão válida: seria preciso o id
  original E o `SESSION_SECRET` para montar um cookie aceito.

ATRIBUTOS DO COOKIE
  HttpOnly (JS do front não lê), SameSite=Lax (um POST vindo de outro site não
  leva o cookie — é a proteção de CSRF das rotas de ação), Secure só em
  `FOPA_ENV=prod` (em dev/demo o site roda em http://localhost, e um cookie
  Secure nunca voltaria). 12 h: um dia de trabalho; a demo com Wi-Fi desligado
  usa o modo local justamente porque a sessão não sobrevive à noite.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from itsdangerous import BadSignature, URLSafeTimedSerializer

NOME_COOKIE = "fopa_sessao"
DURACAO = timedelta(hours=12)
_SAL = "fopa-sessao-v1"


def _assinador(segredo: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(segredo, salt=_SAL)


def _hash(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def _sid_do_cookie(valor: str | None, segredo: str | None) -> str | None:
    """Id da sessão se o cookie tem assinatura válida e não passou de 12 h; senão None."""
    if not valor or not segredo:
        return None
    try:
        sid = _assinador(segredo).loads(valor, max_age=int(DURACAO.total_seconds()))
    except BadSignature:            # inclui SignatureExpired
        return None
    return sid if isinstance(sid, str) and sid else None


def emitir(conn, email: str, segredo: str) -> str:
    """Cria a linha em `sessoes` e devolve o valor do cookie. Quem chama faz o commit."""
    sid = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessoes (id, email, expira_em) VALUES (%s, %s, now() + %s)",
                 (_hash(sid), email, DURACAO))
    # Faxina oportunista: sessões vencidas não servem para nada e a tabela não
    # tem outro coletor. Barato (índice em expira_em) e só no login.
    conn.execute("DELETE FROM sessoes WHERE expira_em < now() - interval '1 day'")
    return _assinador(segredo).dumps(sid)


def ler(conn, valor: str | None, segredo: str | None) -> dict | None:
    """`{email, nome, papel, supremo}` da sessão viva de um usuário ativo, ou None (supremo: db/046)."""
    sid = _sid_do_cookie(valor, segredo)
    if sid is None:
        return None
    linha = conn.execute(
        "SELECT u.email, u.nome, u.papel, u.supremo FROM sessoes s JOIN usuarios u ON u.email = s.email"
        " WHERE s.id = %s AND s.expira_em > now() AND u.ativo", (_hash(sid),)).fetchone()
    if linha is None:
        return None
    if isinstance(linha, dict):
        return {"email": linha["email"], "nome": linha["nome"], "papel": linha["papel"], "supremo": linha["supremo"]}
    return {"email": linha[0], "nome": linha[1], "papel": linha[2], "supremo": linha[3]}


def assinatura_valida(valor: str | None, segredo: str | None) -> bool:
    """Confere só a assinatura, sem banco: é o que decide o 401 antes de abrir conexão."""
    return _sid_do_cookie(valor, segredo) is not None


def encerrar(conn, valor: str | None, segredo: str | None) -> None:
    sid = _sid_do_cookie(valor, segredo)
    if sid is not None:
        conn.execute("DELETE FROM sessoes WHERE id = %s", (_hash(sid),))


def gravar_cookie(resposta, valor: str, seguro: bool) -> None:
    resposta.set_cookie(NOME_COOKIE, valor, max_age=int(DURACAO.total_seconds()), path="/",
                        httponly=True, samesite="lax", secure=seguro)


def apagar_cookie(resposta, seguro: bool) -> None:
    resposta.delete_cookie(NOME_COOKIE, path="/", httponly=True, samesite="lax", secure=seguro)


__all__ = ["NOME_COOKIE", "DURACAO", "emitir", "ler", "encerrar", "assinatura_valida",
           "gravar_cookie", "apagar_cookie"]
