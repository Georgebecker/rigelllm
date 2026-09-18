#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fila_geracao.py — FILA DE ORDENS de geração local (pipeline em SÉRIE).

Criado em 13/08/2026 (pedido do usuário):
  O usuário monta um CONJUNTO DE ORDENS (ex.: 10 perguntas, depois 20 artigos,
  depois 15 receitas). Cada ordem vira um item da fila e é executada UMA POR VEZ,
  em sequência — NUNCA em paralelo (não trava a máquina).

  Cada ordem é processada pelo `scripts/gerar_massa_local.py` (fonte de temas:
  tópicos, categorias, misto ou rss) e passa pelo pipeline pós-geração
  (filtrar qualidade → sanitizar → classificar → pasta certa/JSONL).
  Opcionalmente ajuiza os textos gerados (formato txt).

Estado : estado/fila_geracao.json
Log    : logs/fila_progresso.json (lido pelo painel, barra de % REAL)
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
ESTADO_PATH = PROJETO_ROOT / "estado" / "fila_geracao.json"
PROGRESSO_PATH = PROJETO_ROOT / "logs" / "fila_progresso.json"

STATUS_VALIDOS = ("aguardando", "rodando", "concluido", "erro")


def _agora() -> str:
    return datetime.now().isoformat()


def carregar() -> dict:
    """Lê o estado da fila (ordens + próximo id + rodando + pausado). Nunca levanta erro."""
    padrao = {"ordens": [], "proximo_id": 1, "rodando": False, "pausado": False}
    if ESTADO_PATH.exists():
        try:
            d = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
            d.setdefault("ordens", [])
            d.setdefault("proximo_id", 1)
            d.setdefault("rodando", False)
            d.setdefault("pausado", False)
            return d
        except Exception:
            pass
    return padrao


def gravar(d: dict) -> None:
    try:
        ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
        ESTADO_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass


def nova_ordem(modelo: str = "llama3.2:3b",
               templates: Optional[list] = None,
               estilos: Optional[list] = None,
               fonte: str = "categorias",
               categorias: str = "todas",
               rss_limite: int = 0,
               meta: int = 10,
               formato: str = "txt",
               ajuizar: bool = False,
               titulo: str = "") -> dict:
    """Adiciona UMA ordem ao final da fila (aguardando). Retorna a ordem."""
    d = carregar()
    oid = int(d.get("proximo_id", 1))
    d["proximo_id"] = oid + 1

    if fonte not in ("topicos", "categorias", "misto", "rss"):
        fonte = "categorias"
    templates = [t for t in (templates or ["todos"]) if t]
    estilos = [e for e in (estilos or ["todos"]) if e]
    if not templates:
        templates = ["todos"]
    if not estilos:
        estilos = ["todos"]
    if fonte == "topicos":
        categorias = "todas"
    if fonte != "rss":
        rss_limite = 0

    ordem = {
        "id": oid,
        "titulo": (titulo or f"Ordem #{oid}").strip(),
        "modelo": modelo,
        "templates": templates,        # ["todos"] = aleatório | ["artigo"] = específico
        "estilos": estilos,            # ["todos"] = aleatório | ["professor"] = específico
        "fonte": fonte,
        "categorias": categorias,
        "rss_limite": int(rss_limite or 0),
        "meta": max(1, int(meta or 1)),
        "formato": formato,
        "ajuizar": bool(ajuizar),
        "timeout_item": 300,          # segundos por item (Ollama)
        "max_reinicio": 2,            # máx. reinícios da ordem se travar (stall/timeout)
        "reinicios": 0,
        "diagnostico": "",
        "status": "aguardando",
        "gerados": 0,
        "erros": 0,
        "inicio": "",
        "fim": "",
        "log": [],
    }
    d["ordens"].append(ordem)
    gravar(d)
    return ordem


def remover(oid) -> dict:
    """Remove uma ordem (aguardando/erro/concluido). Retorna ok/erro."""
    d = carregar()
    for i, o in enumerate(d["ordens"]):
        if str(o.get("id")) == str(oid):
            if o.get("status") == "rodando":
                return {"ok": False, "erro": "Ordem em execução — não pode remover agora."}
            d["ordens"].pop(i)
            gravar(d)
            return {"ok": True, "mensagem": f"Ordem #{oid} removida."}
    return {"ok": False, "erro": f"Ordem #{oid} não encontrada."}


def limpar_concluidas() -> dict:
    """Remove ordens concluídas/erro (mantém aguardando/rodando)."""
    d = carregar()
    antes = len(d["ordens"])
    d["ordens"] = [o for o in d["ordens"]
                   if o.get("status") not in ("concluido", "erro")]
    gravar(d)
    return {"ok": True, "removidas": antes - len(d["ordens"])}


def limpar_tudo() -> dict:
    """🗑️ Limpa TODA a fila (aguardando/concluído/erro). Mantém a ordem rodando
    (não pode remover em execução) — volta outra vez se rodar de novo."""
    d = carregar()
    antes = len(d["ordens"])
    d["ordens"] = [o for o in d["ordens"] if o.get("status") == "rodando"]
    gravar(d)
    return {"ok": True, "removidas": antes - len(d["ordens"]),
            "mantidas": len(d["ordens"]),
            "mensagem": "Fila limpa (mantida a ordem em execução, se houver)."}


def pausar() -> dict:
    """⏸️ Pausa a fila: o worker encerra no próximo ponto seguro e as ordens
    não processadas continuam 'aguardando' (podem ser retomadas amanhã)."""
    d = carregar()
    d["pausado"] = True
    d["rodando"] = False
    gravar(d)
    return {"ok": True, "mensagem": "Fila pausada — ordens não processadas continuam aguardando."}


def continuar() -> dict:
    """▶️ Retoma a fila pausada."""
    d = carregar()
    d["pausado"] = False
    gravar(d)
    return {"ok": True, "mensagem": "Fila retomada."}


# Estimativa aproximada de segundos por item (por template)
_EST_SEG_TEMPLATE = {
    "dicionario": 15, "saudacao": 10, "dica": 15, "resumo": 20,
    "poema": 30, "carta": 45, "pergunta_resposta": 40, "conversa": 50,
    "explicacao": 60, "iteracao": 60, "entrevista": 70, "tutorial": 70,
    "resenha": 50, "relatorio": 60, "ensaio": 70, "cronica": 50,
    "receita": 40, "artigo": 90, "conto": 90, "debate": 90,
    "dialogo_profundo": 120,
}


def estimativa_seg(estado: dict | None = None) -> int:
    """Estimativa aproximada (segundos) para processar as ordens pendentes."""
    d = estado or carregar()
    total = 0
    for o in d.get("ordens", []):
        if o.get("status") not in ("aguardando", "rodando"):
            continue
        tpls = o.get("templates") or ["todos"]
        if tpls == ["todos"]:
            seg_item = 40
        else:
            seg_item = max((_EST_SEG_TEMPLATE.get(t, 40) for t in tpls), default=40)
        total += (o.get("meta") or 1) * seg_item
    return int(total)


def marcar(oid, **campos) -> bool:
    """Atualiza campos de uma ordem (status, gerados, log...)."""
    d = carregar()
    for o in d["ordens"]:
        if str(o.get("id")) == str(oid):
            o.update(campos)
            if campos.get("status") == "rodando" and not o.get("inicio"):
                o["inicio"] = _agora()
            if campos.get("status") in ("concluido", "erro"):
                o["fim"] = _agora()
            gravar(d)
            return True
    return False


def registrar_log(oid, msg: str) -> None:
    """Adiciona uma linha ao log da ordem (máx. 50 linhas)."""
    d = carregar()
    for o in d["ordens"]:
        if str(o.get("id")) == str(oid):
            o.setdefault("log", []).append({"t": _agora(), "msg": msg})
            o["log"] = o["log"][-50:]
            gravar(d)
            return


def contar_aguardando() -> int:
    """Ordens que podem ser processadas (aguardando OU órfãs-rodando)."""
    return sum(1 for o in carregar()["ordens"]
               if o.get("status") in ("aguardando", "rodando"))


def recuperar_orfas() -> int:
    """🔄 Ordem 'rodando' órfã (worker parou/desligou/morreu) volta a 'aguardando'.
    O worker da fila é o ÚNICO executor — se ele não está rodando, qualquer ordem
    'rodando' é órfã e precisa ser reprocessada."""
    d = carregar()
    n = 0
    for o in d["ordens"]:
        if o.get("status") == "rodando":
            o["status"] = "aguardando"
            o.setdefault("log", []).append({
                "t": _agora(),
                "msg": "🔄 Recuperada: estava 'rodando' (parou/desligou/PC reiniciou) "
                       "— voltou a aguardar."})
            n += 1
    if n:
        gravar(d)
    return n


def listar_resumo() -> dict:
    """Resumo para o painel (sem logs longos)."""
    d = carregar()
    return {
        "rodando": bool(d.get("rodando")),
        "pausado": bool(d.get("pausado")),
        "estimativa_seg": estimativa_seg(d),
        "ordens": [
            {k: v for k, v in o.items() if k != "log"}
            for o in d["ordens"]
        ],
        "proximo_id": d.get("proximo_id", 1),
        "resumo": {
            "aguardando": sum(1 for o in d["ordens"] if o.get("status") == "aguardando"),
            "rodando": sum(1 for o in d["ordens"] if o.get("status") == "rodando"),
            "concluido": sum(1 for o in d["ordens"] if o.get("status") == "concluido"),
            "erro": sum(1 for o in d["ordens"] if o.get("status") == "erro"),
        },
    }


def ordem(oid) -> dict | None:
    """Retorna UMA ordem com o log completo (p/ exibir no painel)."""
    for o in carregar()["ordens"]:
        if str(o.get("id")) == str(oid):
            return o
    return None


def progresso() -> dict:
    """Progresso persistido da fila (logs/fila_progresso.json)."""
    if PROGRESSO_PATH.exists():
        try:
            return json.loads(PROGRESSO_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"rodando": False, "pct": 0, "ordem_atual": 0, "total_ordens": 0}


def gravar_progresso(p: dict) -> None:
    try:
        PROGRESSO_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROGRESSO_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    except Exception:
        pass
