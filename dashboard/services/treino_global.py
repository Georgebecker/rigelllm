#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
treino_global.py - Semáforo GLOBAL de treino/conversão de dados.
Versão: 1.0.0 | Data: 06/08/2026

Garante a regra do usuário:
  - SÓ UM treino por vez (txt, jsonl OU parquet — nunca dois ao mesmo tempo);
  - Conversão TXT→JSONL nunca roda junto com um treino.

Por que detecção por PROCESSO (e não flag manual):
  - O dashboard roda com --reload; flags em memória se perdem no reload.
  - Processos podem ficar órfãos (treino iniciado antes de um reload).
  - O subprocesso é a fonte da verdade: se o processo pesado está vivo,
    a operação está rodando.

Padrões detectados (cmdline de processos python):
  - treino.py            → treino TXT (causal)
  - treinoparquet.py     → treino PARQUET
  - treinar_com_jsonl.py → treino JSONL (SFT)
  - converter_txt_jsonl.py → conversão TXT→JSONL
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
ESTADO_PATH = PROJETO_ROOT / "estado" / "treino_global.json"

_PADROES = {
    "treino_txt": re.compile(r"(?:^|[\s\\/])treino\.py", re.I),
    "treino_parquet": re.compile(r"(?:^|[\s\\/])treinoparquet\.py", re.I),
    "treino_jsonl": re.compile(r"(?:^|[\s\\/])treinar_com_jsonl\.py", re.I),
    "conversao_txt": re.compile(r"(?:^|[\s\\/])converter_txt_jsonl\.py", re.I),
}

# rótulos amigáveis para exibição
ROTULOS = {
    "treino_txt": "Treino TXT",
    "treino_parquet": "Treino PARQUET",
    "treino_jsonl": "Treino JSONL",
    "conversao_txt": "Conversão TXT→JSONL",
}


def _tipo_de(cmdline: str) -> str | None:
    for tipo, padrao in _PADROES.items():
        if padrao.search(cmdline):
            return tipo
    return None


def processos_ativos() -> list[dict]:
    """Processos python pesados (treino/conversão) vivos, via psutil."""
    ativos: list[dict] = []
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline", "create_time"]):
            try:
                cmd = " ".join(p.info["cmdline"] or [])
            except Exception:
                continue
            tipo = _tipo_de(cmd)
            if tipo is None:
                continue
            ativos.append({
                "pid": p.info["pid"],
                "tipo": tipo,
                "rotulo": ROTULOS.get(tipo, tipo),
                "inicio": datetime.fromtimestamp(p.info["create_time"]).isoformat()
                           if p.info.get("create_time") else None,
            })
    except Exception:
        pass
    return ativos


def disponivel() -> tuple[bool, dict | None]:
    """(True, None) se pode iniciar operação pesada; senão (False, ocupante)."""
    ativos = processos_ativos()
    if ativos:
        return False, ativos[0]
    return True, None


def get_estado() -> dict:
    """Estado atual do semáforo (para exibir no frontend)."""
    ativos = processos_ativos()
    ultimo = {}
    try:
        if ESTADO_PATH.exists():
            ultimo = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
    except Exception:
        ultimo = {}
    return {
        "ocupado": bool(ativos),
        "processos": ativos,
        "ultimo": ultimo,
        "timestamp": datetime.now().isoformat(),
    }


def registrar(tipo: str, pid: int | None, detalhe: str = "") -> None:
    """Registra a operação pesada iniciada (histórico + estado persistente)."""
    try:
        os.makedirs(ESTADO_PATH.parent, exist_ok=True)
        dados = {
            "tipo": tipo,
            "rotulo": ROTULOS.get(tipo, tipo),
            "pid": pid,
            "detalhe": detalhe,
            "inicio": datetime.now().isoformat(),
        }
        ESTADO_PATH.write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass
