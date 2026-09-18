#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
recursos.py - Detecção de hardware e limites PROPORCIONAIS à máquina.
Versão: 1.0.0 | Data: 02/08/2026

Regra do usuário (memória /memories/limites_recursos.md):
  - Os recursos de cada máquina são DIFERENTES (notebook, PC, servidor):
    memória, CPU, placa de vídeo, HD/SSD/NVMe — tudo faz diferença.
  - Quem baixar o projeto deve receber limites PROPORCIONAIS à máquina nova,
    definidos no INÍCIO da instalação (setup_env.py → setup.bat/setup.sh).
  - Limites em PERCENTUAL ficam à mão do guardião (estrutura_cache.py).
  - Ordem de precedência:  config_recursos.json (instalação)
                           < variáveis de ambiente (env)
                           < cálculo em runtime (se não houver arquivo).

Uso (instalação / diagnóstico):
    python -m dashboard.services.recursos [--salvar]
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJETO_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_RECURSOS = PROJETO_DIR / "config_recursos.json"
LOG_RECURSOS = PROJETO_DIR / "logs" / "recursos.log"

_CHAVES = [
    "SCAN_MAX_ARQUIVOS", "SCAN_MAX_DIRETORIOS",
    "SCAN_PAUSA_CADA", "SCAN_PAUSA_SEG",
    "MEM_MIN_LIVRE_MB", "MEM_MIN_LIVRE_PCT",
    "CPU_MAX_USO_PCT", "DISCO_MIN_LIVRE_PCT", "DISCO_MIN_LIVRE_MB",
    "SCAN_MAX_NOMES_CACHE",
    "NUCLEOS_USO", "WORKERS_TREINO", "BATCH_TREINO",
]

# Tipos de conversão por chave (para env / arquivo)
_CASTS = {
    "SCAN_MAX_ARQUIVOS": int, "SCAN_MAX_DIRETORIOS": int,
    "SCAN_PAUSA_CADA": int, "SCAN_PAUSA_SEG": float,
    "MEM_MIN_LIVRE_MB": int, "MEM_MIN_LIVRE_PCT": float,
    "CPU_MAX_USO_PCT": float, "DISCO_MIN_LIVRE_PCT": float,
    "DISCO_MIN_LIVRE_MB": int, "SCAN_MAX_NOMES_CACHE": int,
    "WORKERS_TREINO": int, "BATCH_TREINO": int,
}


# ---------------------------------------------------------------------------
# Rastro (log) — regra do usuário: sempre gravar o que está sendo feito
# ---------------------------------------------------------------------------
def _log(msg: str, nivel: str = "INFO") -> None:
    try:
        LOG_RECURSOS.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_RECURSOS, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] [{nivel}] {msg}\n")
    except Exception:
        pass
    print(f"[recursos] {msg}")


# ---------------------------------------------------------------------------
# Detecção de hardware (com fallback stdlib — funciona antes de instalar deps)
# ---------------------------------------------------------------------------
def _ram_gb() -> float:
    """RAM total em GB. tenta psutil → ctypes (Windows) → sysconf (Linux)."""
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        pass
    if os.name == "nt":
        try:
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            m = _MEMORYSTATUSEX()
            m.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return round(m.ullTotalPhys / (1024 ** 3), 1)
        except Exception:
            pass
    try:
        return round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024 ** 3), 1)
    except Exception:
        pass
    return 16.0  # padrão conservador


def _disco_tipo(pasta: Path, rapido: bool = False) -> str:
    """hdd | ssd | nvme. Windows: PowerShell Get-Disk (MediaType/BusType/Model).
    rapido=True pula a sondagem (usa 'ssd' — padrão seguro e rápido)."""
    if rapido or os.name != "nt":
        return "ssd"
    try:
        letra = pasta.anchor[0] if pasta.anchor else "C"
        cmd = [
            "powershell", "-NoProfile", "-Command",
            f"$d = Get-Partition -DriveLetter {letra} -ErrorAction SilentlyContinue | "
            f"Get-Disk | Select-Object -First 1 MediaType,BusType,Model; "
            f"if ($d) {{ '{0};{1};{2}' -f $d.MediaType,$d.BusType,$d.Model }}",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        partes = [p.strip() for p in r.stdout.split(";")] if r.stdout else []
        media = partes[0] if len(partes) >= 1 else ""
        bus = partes[1] if len(partes) >= 2 else ""
        modelo = " ".join(partes[2:]).lower()
        if bus == "17" or "nvme" in modelo:
            return "nvme"
        if media in ("4", "5") or "ssd" in modelo or "solid state" in modelo:
            return "ssd"
        if media == "3" or "hdd" in modelo:
            return "hdd"
    except Exception:
        pass
    return "ssd"


def _gpu() -> tuple[bool, str]:
    """(tem_gpu, nome). Só nvidia-smi (rápido; sem importar torch aqui)."""
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=8)
            if r.returncode == 0 and r.stdout.strip():
                return True, r.stdout.strip().splitlines()[0]
        except Exception:
            pass
    return False, ""


def detectar_hardware(rapido: bool = False) -> dict:
    """Detecta RAM, CPU, GPU, tipo de disco e espaço livre. Nunca levanta."""
    gpu, gpu_nome = _gpu()
    hw = {
        "ram_gb": _ram_gb(),
        "cpu_cores": os.cpu_count() or 4,
        "gpu": gpu,
        "gpu_nome": gpu_nome,
        "disco_tipo": _disco_tipo(PROJETO_DIR, rapido=rapido),
        "disco_total_gb": 0.0,
        "disco_livre_gb": 0.0,
        "so": platform.platform(),
    }
    try:
        uso = shutil.disk_usage(str(PROJETO_DIR))
        hw["disco_total_gb"] = round(uso.total / (1024 ** 3), 1)
        hw["disco_livre_gb"] = round(uso.free / (1024 ** 3), 1)
    except Exception:
        pass
    return hw


# ---------------------------------------------------------------------------
# Margem de núcleos (regra do usuário, 06/08): SEMPRE deixar núcleos livres
# ---------------------------------------------------------------------------
def margem_nucleos(n: int) -> int:
    """Núcleos a deixar LIVRES (regra do usuário): 2→1, 4→2, 36→16
    (~45% de folga, sempre pelo menos 1)."""
    n = max(1, int(n or 1))
    return max(1, round(n * 0.45))


def nucleos_recomendados(n: int) -> int:
    """Núcleos a USAR no treino (total - margem). 36→20, 4→2, 2→1."""
    n = max(1, int(n or 1))
    return max(1, n - margem_nucleos(n))


# ---------------------------------------------------------------------------
# Cálculo dos limites PROPORCIONAIS (percentuais à mão do guardião)
# ---------------------------------------------------------------------------
def calcular_limites(hw: dict) -> dict:
    """Traduz o hardware em limites de segurança do guardião.

    Percentuais e escalas:
      - MEM_MIN_LIVRE_PCT: % da RAM que deve sobrar (máquina menor = folga maior).
      - DISCO_MIN_LIVRE_PCT: % do disco que deve sobrar (HDD pede mais folga).
      - SCAN_PAUSA_*: throttle proporcional ao tipo de disco (HDD lento → pausa maior).
      - SCAN_MAX_*: caps de arquivos/diretórios proporcionais à RAM.
      - CPU_MAX_USO_PCT: se o uso de CPU passar disso durante o scan, o scan respira.
    """
    ram = max(2.0, float(hw.get("ram_gb") or 16))
    tipo = str(hw.get("disco_tipo") or "ssd")
    gpu = bool(hw.get("gpu"))

    if ram >= 64:
        pct_mem = 6.0
    elif ram >= 32:
        pct_mem = 8.0
    elif ram >= 16:
        pct_mem = 12.0
    elif ram >= 8:
        pct_mem = 15.0
    else:
        pct_mem = 20.0
    # REGRA 70% (usuário, 06/08): RAM usada nunca passa de 70% (sobra ≥30%
    # p/ o sistema). Pode ser reduzido, nunca aumentado além disso.
    pct_mem = max(30.0, pct_mem)
    mem_min_mb = max(512, int(ram * 1024 * pct_mem / 100))

    pct_disco = 10.0 if tipo == "hdd" else 5.0
    disco_min_mb = 1024
    try:
        uso = shutil.disk_usage(str(PROJETO_DIR))
        disco_min_mb = max(1024, int(uso.total / (1024 ** 2) * pct_disco / 100))
    except Exception:
        pass

    pausa = {"nvme": 0.001, "ssd": 0.002, "hdd": 0.02}.get(tipo, 0.002)
    pausa_cada = {"nvme": 4000, "ssd": 2000, "hdd": 800}.get(tipo, 2000)

    max_arq = int(500_000 + ram * 50_000)      # 32 GB → 2,1M | 8 GB → 900k
    max_dir = int(50_000 + ram * 4_000)        # 32 GB → 178k | 8 GB → 82k
    # REGRA 70% (usuário, 06/08): 70% é o TETO do guardião — sempre sobra
    # espaço p/ o sistema (nunca travar). Só pode ser REDUZIDO (régua p/ baixo).
    cpu_max = 70.0

    return {
        "SCAN_MAX_ARQUIVOS": max_arq,
        "SCAN_MAX_DIRETORIOS": max_dir,
        "SCAN_PAUSA_CADA": pausa_cada,
        "SCAN_PAUSA_SEG": pausa,
        "MEM_MIN_LIVRE_MB": mem_min_mb,
        "MEM_MIN_LIVRE_PCT": pct_mem,
        "CPU_MAX_USO_PCT": cpu_max,
        "DISCO_MIN_LIVRE_PCT": pct_disco,
        "DISCO_MIN_LIVRE_MB": disco_min_mb,
        "SCAN_MAX_NOMES_CACHE": 2000,
    }


# ---------------------------------------------------------------------------
# Persistência: config_recursos.json (gravado na instalação)
# ---------------------------------------------------------------------------
def salvar_limites(limites: dict, hw: dict | None = None) -> Path:
    """Grava hardware + limites em config_recursos.json (raiz do projeto)."""
    hw = hw or detectar_hardware(rapido=True)
    dados = {
        "gerado_em": datetime.now().isoformat(),
        "hardware": hw,
        "limites": limites,
    }
    CONFIG_RECURSOS.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"config_recursos.json salvo em {CONFIG_RECURSOS}", nivel="OK")
    return CONFIG_RECURSOS


_CACHE_LIMITES: dict | None = None  # cache em memória: loga limites 1x por processo


def carregar_limites() -> dict:
    """Limites efetivos do guardião.

    Precedência: config_recursos.json (instalação) → variáveis de ambiente
    → cálculo proporcional em runtime (rápido; sem sondar disco via PowerShell).

    O resultado é CACHEADO em memória (loga 1x por processo — antes logava a
    cada chamada e poluía o terminal com dezenas de linhas por segundo).
    """
    global _CACHE_LIMITES
    if _CACHE_LIMITES is not None:
        return _CACHE_LIMITES
    base = None
    origem = "calculado-em-runtime (rápido)"
    if CONFIG_RECURSOS.exists():
        try:
            dados = json.loads(CONFIG_RECURSOS.read_text(encoding="utf-8"))
            if isinstance(dados, dict) and isinstance(dados.get("limites"), dict):
                base = {k: v for k, v in dados["limites"].items() if k in _CHAVES}
                origem = f"config_recursos.json (instalação)"
        except Exception as e:
            _log(f"config_recursos.json inválido ({e}) — recalculando", nivel="AVISO")
    if base is None:
        base = calcular_limites(detectar_hardware(rapido=True))
    final = dict(base)
    for chave, cast in _CASTS.items():
        val = os.environ.get(chave)
        if val is not None and val.strip() != "":
            try:
                final[chave] = cast(val)
            except ValueError:
                _log(f"{chave}={val!r} inválido no ambiente — ignorado", nivel="AVISO")
    _CACHE_LIMITES = final
    _log(f"Limites carregados de: {origem} | "
         + ", ".join(f"{k}={v}" for k, v in final.items()))
    return final


# ---------------------------------------------------------------------------
# CLI: diagnóstico / regenerar (também chamado pelo setup_env.py)
# ---------------------------------------------------------------------------
def main() -> int:
    salvar = "--salvar" in sys.argv
    rapido = "--rapido" in sys.argv
    hw = detectar_hardware(rapido=rapido)
    print("=== HARDWARE DETECTADO ===")
    for k, v in hw.items():
        print(f"  {k}: {v}")
    lim = calcular_limites(hw)
    print("=== LIMITES PROPORCIONAIS (guardião) ===")
    for k, v in lim.items():
        print(f"  {k}: {v}")
    if salvar:
        salvar_limites(lim, hw)
        print(f"Salvo em: {CONFIG_RECURSOS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
