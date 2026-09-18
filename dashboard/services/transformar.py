# -*- coding: utf-8 -*-
"""
transformar.py — Botões "Transformar tudo em JSONL" e "Transformar tudo em
PARQUET" (pedido do usuário 18/08/2026).

- converter_tudo_jsonl(): TXT aprovados → JSONL SFT, em processed/JSONL/rigel<ts>/
- converter_tudo_parquet(): JSONL → .parquet, em processed/PARQUET/rigel<ts>/
Reutiliza os conversores existentes (converter_txt_jsonl / converter_jsonl_parquet).
Progresso em logs/transformar_progresso.json.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))
if str(PROJETO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT / "scripts"))

PROCESSED = PROJETO_ROOT / "dados" / "processed"
PROGRESSO = PROJETO_ROOT / "logs" / "transformar_progresso.json"


def _progresso(d: dict) -> None:
    try:
        PROGRESSO.parent.mkdir(parents=True, exist_ok=True)
        PROGRESSO.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _pastas_txt() -> list[tuple[Path, int]]:
    """Pastas com .txt aprovados (processed/*_aprovado e processed/txt)."""
    pastas = []
    for p in PROCESSED.iterdir():
        if not p.is_dir():
            continue
        nome = p.name.lower()
        if nome.endswith("_aprovado") or nome == "txt":
            n = sum(1 for _ in p.rglob("*.txt"))
            if n:
                pastas.append((p, n))
    return sorted(pastas, key=lambda x: -x[1])


def converter_tudo_jsonl() -> dict:
    """TXT aprovados → JSONL SFT em processed/JSONL/rigel<ts>/<origem>/."""
    import converter_txt_jsonl as cj
    pastas = _pastas_txt()
    ts = _ts()
    destino = PROCESSED / "JSONL" / f"rigel{ts}"
    resumo = {"pastas": 0, "arquivos": 0, "erros": 0}
    for i, (pasta, _n) in enumerate(pastas, 1):
        nome = pasta.name
        try:
            r = cj.converter_pasta(str(pasta), f"rigel{ts}_{nome}")
            temp = PROJETO_ROOT / "dados" / "gerados" / "jsonl" / f"rigel{ts}_{nome}"
            alvo = destino / nome
            if temp.is_dir() and any(temp.iterdir()):
                alvo.parent.mkdir(parents=True, exist_ok=True)
                if alvo.exists():
                    shutil.rmtree(alvo)
                shutil.move(str(temp), str(alvo))
                resumo["arquivos"] += len(list(alvo.glob("*.jsonl")))
                resumo["pastas"] += 1
            else:
                shutil.rmtree(temp, ignore_errors=True)
                if not r.get("ok") and r.get("erro"):
                    resumo["erros"] += 1
        except Exception:
            resumo["erros"] += 1
        _progresso({"pct": round(100 * i / max(1, len(pastas)), 1), "atual": nome,
                    "tipo": "jsonl", **resumo,
                    "atualizado": datetime.now().isoformat()})
    _progresso({"pct": 100, "fim": True, "tipo": "jsonl", **resumo,
                "atualizado": datetime.now().isoformat()})
    return {"ok": True, **resumo, "destino": str(destino)}


def _fontes_jsonl() -> list[Path]:
    """Lotes de JSONL: processed/JSONL (novo) + processed/jsonl (antigo)."""
    fontes = []
    for base in (PROCESSED / "JSONL", PROCESSED / "jsonl"):
        if base.is_dir():
            for p in base.iterdir():
                if p.is_dir() and any(p.glob("*.jsonl")):
                    fontes.append(p)
    return fontes


def converter_tudo_parquet() -> dict:
    """JSONL → .parquet em processed/PARQUET/rigel<ts>/<origem>/."""
    import converter_jsonl_parquet as cp
    fontes = _fontes_jsonl()
    ts = _ts()
    destino = PROCESSED / "PARQUET" / f"rigel{ts}"
    resumo = {"pastas": 0, "arquivos": 0, "exemplos": 0, "erros": 0}
    for i, f in enumerate(fontes, 1):
        try:
            r = cp.converter(f, destino / f.name, "rigel")
            if r.get("sft"):
                resumo["pastas"] += 1
                resumo["arquivos"] += 1
                resumo["exemplos"] += int(r.get("exemplos", 0))
        except Exception:
            resumo["erros"] += 1
        _progresso({"pct": round(100 * i / max(1, len(fontes)), 1), "atual": f.name,
                    "tipo": "parquet", **resumo,
                    "atualizado": datetime.now().isoformat()})
    _progresso({"pct": 100, "fim": True, "tipo": "parquet", **resumo,
                "atualizado": datetime.now().isoformat()})
    return {"ok": True, **resumo, "destino": str(destino)}
