#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
painel_dados.py - Funil de dados: o que está pendente até chegar em processed.
Versão: 1.0.0 | Data: 06/08/2026

Ideia (regra do usuário): "a pasta processed é o FUNDO do funil; acima dela
têm que ter os filtros (raw → gerados → sanitizados → processed). Sempre há
algo na borda para ser visto, e o que não servir para nada deve ser apagado."

Este serviço varre dados/ com GUARDIÃO DE LIMITES (streaming, caps, aborta se
memória baixa) e classifica cada item:
  - raw/*          → cru (não tratado)          → ação: sanitizar/converter
  - gerados/jsonl/*→ provisório                 → ação: validar e promover p/ processed
  - sanitizados/*  → tratados mas não promovidos→ ação: verificar e promover
  - processed/*.txt→ texto pronto               → ação: pode converter p/ jsonl
  - processed/jsonl/* → VALIDADO (fundo do funil) → ok (não aparece)

Roda em THREAD com progresso real (barra de %) e estado persistente — o
frontend faz polling e mostra o resultado.
"""
from __future__ import annotations

import json
import os
import threading
import time as _time
from collections import Counter
from datetime import datetime
from pathlib import Path

from dashboard.services.estrutura_cache import (
    walk_com_limites, LimiteEstourado, memoria_ok, SCAN_MAX_ARQUIVOS,
)

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
DADOS = PROJETO_ROOT / "dados"

CAP_POR_PASTA = 2000          # não conta mais que isso por pasta (SSD)
MAX_PENDENTES = 80            # limites de itens retornados ao front

_estado: dict = {
    "varrendo": False,
    "varrido": False,
    "percentual": 0,
    "pasta_atual": "",
    "resumo": {"raw": 0, "gerados": 0, "sanitizados": 0, "processed": 0},
    "pendentes": [],
    "atualizado": None,
}
_lock = threading.Lock()

# Cache da classificação SFT (evita re-varredura a cada poll do dashboard —
# protege o SSD e deixa a página responsiva). Atualizar = forçar novo scan.
_sft_cache: dict = {"dados": None, "atualizado": None}
_SFT_CACHE_TTL = 300  # 5 minutos


def get_estado() -> dict:
    with _lock:
        return dict(_estado, pendentes=list(_estado["pendentes"]))


def _contar(pasta: Path, ext: str, cap: int = CAP_POR_PASTA) -> int:
    """Conta arquivos com extensão em pasta (recursivo, com caps)."""
    n = 0
    try:
        for _c in walk_com_limites(pasta, extensoes=(ext,)):
            n += 1
            if n >= cap:
                break
    except LimiteEstourado:
        return cap
    return n


def _tem_arquivo(pasta: Path, ext: str) -> bool:
    try:
        for _c in walk_com_limites(pasta, extensoes=(ext,)):
            return True
    except LimiteEstourado:
        return True
    return False


def _subpastas(base: Path) -> list[Path]:
    if not base.exists():
        return []
    try:
        return sorted(p for p in base.iterdir() if p.is_dir())
    except Exception:
        return []


def _varredura() -> None:
    pendentes: list[dict] = []
    resumo = {"raw": 0, "gerados": 0, "sanitizados": 0, "processed": 0}

    areas = [
        ("raw", DADOS / "raw", "cru"),
        ("gerados", DADOS / "gerados" / "jsonl", "provisorio"),
        ("sanitizados", DADOS / "sanitizados", "sanitizado"),
        ("processed_txt", DADOS / "processed", "txt_pronto"),
        ("processed_jsonl", DADOS / "processed" / "jsonl", "validado"),
    ]
    total_areas = len(areas)
    for idx, (area, base, tipo) in enumerate(areas):
        pastas = _subpastas(base)
        n_sub = len(pastas)
        for j, item in enumerate(pastas):
            ok, motivo = memoria_ok()
            if not ok:
                with _lock:
                    _estado.update(pasta_atual=f"memória baixa: {motivo}",
                                   varrendo=False, varrido=True)
                return
            with _lock:
                _estado["pasta_atual"] = item.name
                _estado["percentual"] = round(
                    (idx + (j + 1) / max(1, n_sub)) / total_areas * 100, 1)

            nome = item.name
            if area == "raw":
                n_txt = _contar(item, ".txt")
                n_json = _contar(item, ".jsonl")
                if n_txt or n_json:
                    resumo["raw"] += 1
                    pendentes.append({
                        "local": "dados/raw",
                        "item": nome,
                        "situacao": f"{n_txt} txt · {n_json} jsonl (cru, não tratado)",
                        "acao": "🧼 sanitizar / 🧾 converter p/ jsonl",
                    })
            elif area == "gerados":
                n_json = _contar(item, ".jsonl")
                if n_json:
                    resumo["gerados"] += 1
                    # Se já existe em processed, está promovido (ok)
                    if _tem_arquivo(DADOS / "processed" / "jsonl" / nome, ".jsonl"):
                        continue
                    pendentes.append({
                        "local": "dados/gerados/jsonl",
                        "item": nome,
                        "situacao": f"{n_json} jsonl (provisório)",
                        "acao": "✅ validar e promover p/ processed",
                    })
            elif area == "sanitizados":
                n_json = _contar(item, ".jsonl")
                if n_json:
                    resumo["sanitizados"] += 1
                    pendentes.append({
                        "local": "dados/sanitizados",
                        "item": nome,
                        "situacao": f"{n_json} jsonl (tratado, não promovido)",
                        "acao": "📋 verificar e promover p/ processed",
                    })
            elif area == "processed_txt":
                if nome in ("jsonl", "parquet"):
                    continue
                n_txt = _contar(item, ".txt")
                if n_txt:
                    resumo["processed"] += 1
                    # txt pronto e que NÃO tem jsonl processado equivalente
                    if not _tem_arquivo(DADOS / "processed" / "jsonl" / nome, ".jsonl"):
                        pendentes.append({
                            "local": "dados/processed",
                            "item": nome,
                            "situacao": f"{n_txt} txt (pronto)",
                            "acao": "🧾 pode converter p/ jsonl",
                        })
            else:  # processed_jsonl (fundo do funil)
                n_json = _contar(item, ".jsonl")
                if n_json:
                    resumo["processed"] += 1

            if len(pendentes) > MAX_PENDENTES * 3:
                break
        if len(pendentes) > MAX_PENDENTES * 3:
            break

    with _lock:
        _estado.update(
            varrendo=False, varrido=True, percentual=100,
            pasta_atual="", resumo=resumo,
            pendentes=pendentes[:MAX_PENDENTES],
            atualizado=datetime.now().isoformat(),
        )


def iniciar_varredura() -> dict:
    """Dispara a varredura em thread (não bloqueia o request)."""
    with _lock:
        if _estado["varrendo"]:
            return {"ok": False, "erro": "Varredura já em andamento."}
        _estado.update(varrendo=True, varrido=False, percentual=0,
                       pasta_atual="iniciando...", pendentes=[])
    threading.Thread(target=_varredura, daemon=True).start()
    return {"ok": True, "mensagem": "Varredura iniciada."}


# ============================================================================
# CLASSIFICAÇÃO SFT — ONDE ESTÁ O MATERIAL PRONTO PARA TREINAR
# (espelha normalizar_turnos do treinar_com_jsonl.py SEM importar torch,
#  leve para o dashboard; amostra poucas linhas por pasta — respeita limites)
# ============================================================================

def _classificar_linha_sft(linha: str) -> dict:
    """Retorna formato + se a linha é válida p/ SFT (formato messages)."""
    try:
        obj = json.loads(linha)
    except Exception:
        return {"formato": "json inválido", "valido": False}
    if not isinstance(obj, dict):
        return {"formato": "outro", "valido": False}
    msgs = obj.get("messages") or obj.get("conversations") or obj.get("chat")
    if isinstance(msgs, list):
        roles = set()
        for m in msgs:
            if isinstance(m, dict):
                role = str(m.get("role") or m.get("from") or "").strip().lower()
                content = m.get("content") or m.get("value") or m.get("text")
                if content and role in ("user", "human", "h"):
                    roles.add("user")
                elif content and role in ("assistant", "gpt", "a", "bot", "ia"):
                    roles.add("assistant")
        if "user" in roles and "assistant" in roles:
            return {"formato": "messages", "valido": True}
        return {"formato": "messages incompleto", "valido": False}
    if obj.get("pergunta") and obj.get("resposta"):
        return {"formato": "pergunta/resposta", "valido": True}
    if obj.get("text"):
        return {"formato": "text (pré-treino)", "valido": False}
    if obj.get("prompt") and obj.get("thought") and obj.get("answer"):
        return {"formato": "prompt/thought/answer (raciocínio)", "valido": False}
    if obj.get("content"):
        return {"formato": "content solto", "valido": False}
    return {"formato": "outro", "valido": False}


def _primeiros_jsonl(pasta: Path, limite: int) -> list:
    """Retorna até `limite` arquivos .jsonl (RECURSIVO — pastas podem ter
    subpastas, ex.: mini-backups). Para cedo ao achar o suficiente (SSD)."""
    achados = []
    try:
        for raiz, _, arquivos in os.walk(pasta):
            for arq in arquivos:
                if arq.lower().endswith(".jsonl"):
                    achados.append(Path(raiz) / arq)
                    if len(achados) >= limite:
                        return achados
    except Exception:
        pass
    return achados


def classificar_pastas_sft(amostra: int = 100, max_arquivos: int = 2,
                           forcar: bool = False) -> dict:
    """Classifica cada subpasta de processed/jsonl: PRONTA p/ SFT ou não, com motivo.
    Com CACHE (~5 min): o poll do dashboard não re-varre tudo a cada ciclo.
    `forcar=True` refaz a varredura (usado no botão de atualizar)."""
    agora = _time.time()
    with _lock:
        if (not forcar and _sft_cache["dados"] and _sft_cache["atualizado"]
                and (agora - _sft_cache["atualizado"]) < _SFT_CACHE_TTL):
            return dict(_sft_cache["dados"],
                        itens=list(_sft_cache["dados"]["itens"]))
    base = DADOS / "processed" / "jsonl"
    itens = []
    for item in _subpastas(base):
        ok, motivo = memoria_ok()
        if not ok:
            itens.append({"pasta": item.name, "status": "nao_scan",
                          "motivo": f"memória baixa: {motivo}", "percentual": 0})
            break
        arquivos = _primeiros_jsonl(item, max_arquivos)
        total = validos = 0
        formatos: dict = {}
        for arq in arquivos:
            try:
                with open(arq, encoding="utf-8", errors="replace") as f:
                    for i, linha in enumerate(f):
                        if i >= amostra:
                            break
                        linha = linha.strip()
                        if not linha:
                            continue
                        total += 1
                        r = _classificar_linha_sft(linha)
                        formatos[r["formato"]] = formatos.get(r["formato"], 0) + 1
                        if r["valido"]:
                            validos += 1
            except Exception:
                continue
        pct = round(100.0 * validos / total, 1) if total else 0.0
        if total == 0:
            status, motivo = "vazio", "sem linhas na amostra"
        elif pct >= 95:
            status, motivo = "pronto", "formato de conversa válido"
        elif pct > 0:
            status, motivo = "misto", f"só {pct:.0f}% no formato certo"
        else:
            status, motivo = "nao_serve", f"formato: {', '.join(formatos) or '?'}"
        itens.append({
            "pasta": item.name,
            "caminho": str(item),
            "arquivos": len(arquivos),
            "linhas_amostradas": total,
            "validos": validos,
            "percentual": pct,
            "status": status,
            "motivo": motivo,
            "formatos": formatos,
        })
    ordem = {"pronto": 0, "misto": 1, "vazio": 2, "nao_serve": 3, "nao_scan": 4}
    itens.sort(key=lambda x: ordem.get(x["status"], 9))
    resultado = {"base": str(base), "itens": itens,
                 "atualizado": datetime.now().isoformat(timespec="seconds")}
    with _lock:
        _sft_cache["dados"] = resultado
        _sft_cache["atualizado"] = agora
    return resultado


# Inicia vazio; o front chama /api/dados/painel (que dispara se nunca varreu)
