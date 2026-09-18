#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sanitizar_baixados.py — Sanitizador DEDICADO a datasets RECÉM BAIXADOS ou
baixados PARCIALMENTE (ex.: dados/raw/<repo>).

Nome próprio (sanitizar_baixados) -> NÃO conflita com o "sanitizar (todas)"
do executor; pode rodar como processo separado (outro PID) sem briga.

Uso:
    python scripts/sanitizar_baixados.py --origem todos
    python scripts/sanitizar_baixados.py --origem dados/raw/cnmoro_reasoning-v1-20m-portuguese
    python scripts/sanitizar_baixados.py --origem todos --max-docs 5000   # teste rápido

O que faz por dataset (detecta o formato):
  - parquet             -> limpeza leve (limpeza_leve_rigel_v2.py) -> --saida (padrão processed/parquet)
  - jsonl com 'messages' -> SFT (gerar_sanitizados.py) -> dados/sanitizados/<nome>
  - desconhecido/outro  -> avisa e pula (nunca quebra)

Progresso e relatório persistidos em logs/sanitizar_baixados_*.json.
Sem emojis (regra do usuário: emojis só no dashboard/HTML).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PROJETO_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJETO_ROOT / "dados" / "raw"
SANITIZADOS = PROJETO_ROOT / "dados" / "sanitizados"
RELOGIO = PROJETO_ROOT / "logs" / f"sanitizar_baixados_relatorio.json"
PROGRESSO = PROJETO_ROOT / "logs" / f"sanitizar_baixados_progresso.json"


def _agora() -> str:
    return datetime.now().isoformat()


def _log(msg: str) -> None:
    print(msg, flush=True)


def _listar_origens(origem_arg: str) -> list[Path]:
    """Resolve 'todos' (varre dados/raw) ou uma pasta/arquivo específico."""
    alvo = (origem_arg or "").strip()
    if alvo.lower() in ("todos", "all", "*"):
        if not RAW.is_dir():
            _log(f"Pasta de downloads não existe: {RAW}")
            return []
        origens = sorted(
            [p for p in RAW.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
        _log(f"Encontrados {len(origens)} dataset(s) em dados/raw.")
        return origens
    p = Path(alvo)
    if not p.is_absolute():
        p = PROJETO_ROOT / p
    if not p.exists():
        _log(f"Origem não existe: {p}")
        return []
    if p.is_dir():
        return [p]
    return [p.parent]  # arquivo -> usa a pasta pai


def _detectar_formato(origem: Path) -> str:
    """Detecta o formato dominante: 'parquet' | 'jsonl' | 'desconhecido'."""
    parquet = list(origem.rglob("*.parquet"))[:1]
    if parquet:
        return "parquet"
    for j in origem.rglob("*.jsonl"):
        try:
            with open(j, encoding="utf-8", errors="replace") as f:
                linha = f.readline().strip()
            if linha:
                ex = json.loads(linha)
                if any(k in ex for k in ("messages", "conversations", "chat")):
                    return "jsonl"
                return "jsonl_nao_sft"  # texto corrido — precisa decisão
        except Exception:
            continue
    return "desconhecido"


def _sanitizar_parquet(origem: Path, saida: Path, max_docs: int, sem_ptbr: bool) -> int:
    """Roda limpeza_leve_rigel_v2.py no dataset parquet. Retorna exit code."""
    cmd = [sys.executable, "-u", "limpeza_leve_rigel_v2.py",
           "--origem", str(origem), "--saida", str(saida)]
    if max_docs > 0:
        cmd += ["--max-docs", str(max_docs)]
    if sem_ptbr:
        cmd.append("--sem-ptbr")
    _log(f"  [parquet] limpeza_leve -> {saida}")
    _log(f"  comando: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(PROJETO_ROOT))


def _sanitizar_jsonl(origem: Path, max_arquivos: int, sem_ptbr: bool) -> int:
    """Roda gerar_sanitizados.py (SFT) no dataset jsonl messages. Retorna exit code."""
    saida_dir = SANITIZADOS / origem.name
    cmd = [sys.executable, "-u", "scripts/gerar_sanitizados.py",
           str(origem), "--saida-dir", str(saida_dir)]
    if max_arquivos > 0:
        cmd += ["--max-arquivos", str(max_arquivos)]
    if sem_ptbr:
        cmd.append("--sem-ptbr")
    _log(f"  [jsonl] SFT -> {saida_dir}")
    _log(f"  comando: {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=str(PROJETO_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sanitiza datasets recém-baixados ou baixados parcialmente "
                    "(parquet -> limpeza leve; jsonl messages -> SFT).")
    ap.add_argument("--origem", default="todos",
                    help="pasta/arquivo em dados/raw ou 'todos' (padrão)")
    ap.add_argument("--saida", default=str(PROJETO_ROOT / "dados" / "processed" / "parquet"),
                    help="destino dos parquet (padrão: processed/parquet)")
    ap.add_argument("--max-docs", type=int, default=0,
                    help="limite de documentos p/ parquet (0 = todos) — teste")
    ap.add_argument("--max-arquivos", type=int, default=0,
                    help="limite de arquivos p/ jsonl (0 = todos) — teste")
    ap.add_argument("--sem-ptbr", action="store_true",
                    help="ignora a checagem PT-BR (só para testes)")
    args = ap.parse_args()

    saida = Path(args.saida)
    origens = _listar_origens(args.origem)
    if not origens:
        return 1

    relatorio = {"nome": "sanitizar_baixados", "inicio": _agora(), "fim": None,
                 "origens": len(origens), "ok": 0, "erros": 0, "pulados": 0,
                 "itens": []}

    for i, origem in enumerate(origens, 1):
        fmt = _detectar_formato(origem)
        item = {"origem": origem.name, "formato": fmt, "status": "rodando",
                "inicio": _agora(), "fim": None, "exit_code": None, "erro": None}
        relatorio["itens"].append(item)
        _log(f"\n[{i}/{len(origens)}] {origem.name} (formato: {fmt})")
        try:
            if fmt == "parquet":
                item["exit_code"] = _sanitizar_parquet(
                    origem, saida, args.max_docs, args.sem_ptbr)
            elif fmt == "jsonl":
                item["exit_code"] = _sanitizar_jsonl(
                    origem, args.max_arquivos, args.sem_ptbr)
            elif fmt == "jsonl_nao_sft":
                item["status"] = "pulado"
                item["erro"] = "jsonl sem 'messages' (texto/pré-treino) — usar limpeza leve ou arquivar"
                relatorio["pulados"] += 1
                _log(f"  pulado: {item['erro']}")
                item["fim"] = _agora()
                _salvar(relatorio)
                continue
            else:
                item["status"] = "pulado"
                item["erro"] = "formato desconhecido (sem parquet nem jsonl messages)"
                relatorio["pulados"] += 1
                _log(f"  pulado: {item['erro']}")
                item["fim"] = _agora()
                _salvar(relatorio)
                continue
            if item["exit_code"] == 0:
                item["status"] = "ok"
                relatorio["ok"] += 1
                _log(f"  OK ({origem.name})")
            else:
                item["status"] = "erro"
                item["erro"] = f"exit code {item['exit_code']}"
                relatorio["erros"] += 1
                _log(f"  ERRO: exit code {item['exit_code']}")
        except Exception as e:
            item["status"] = "erro"
            item["erro"] = str(e)
            relatorio["erros"] += 1
            _log(f"  ERRO: {e}")
        item["fim"] = _agora()
        _salvar(relatorio)

    relatorio["fim"] = _agora()
    _salvar(relatorio)
    _log(f"\nRESUMO: ok={relatorio['ok']} erros={relatorio['erros']} "
         f"pulados={relatorio['pulados']} de {relatorio['origens']}")
    _log(f"Relatório: {RELOGIO}")
    return 0 if relatorio["erros"] == 0 else 1


def _salvar(relatorio: dict) -> None:
    try:
        RELOGIO.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        PROGRESSO.write_text(json.dumps({
            "atual": relatorio["itens"][-1]["origem"] if relatorio["itens"] else "",
            "ok": relatorio["ok"], "erros": relatorio["erros"],
            "pulados": relatorio["pulados"], "total": relatorio["origens"],
            "timestamp": _agora(),
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
