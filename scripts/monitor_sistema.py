# -*- coding: utf-8 -*-
"""
monitor_sistema.py — Guardião de vigilância contínua do RigelSLM.

Regra de ouro (14/08/2026): "se cairmos, devemos nos levantar; se tropeçarmos,
devemos prestar atenção; se não cuidarmos, acontecerá de novo."

Verifica periodicamente e REGISTRA (persistente, à prova de queda de luz):
    - Espaço em disco            (alerta se < MIN_LIVRE_GB)
    - Memória RAM                (alerta se livre < MIN_LIVRE_MB ou % alto)
    - Processamento (CPU)        (alerta se > MAX_CPU por amostras seguidas)
    - Temperatura (WMI)          (se disponível)
    - Ping do dashboard (:8000)  e Ollama (:11434)
    - Logs: tamanho + erros recentes
    - Processos: uvicorn vivo? fila rodando? sockets órfãos na porta?
    - BACKUP de estados: copia estado/*.json + fila_progresso para
      logs/backup_estado/ (a cada ciclo, mantém os N mais recentes) — protege
      contra perda em queda de luz/congelamento.

Uso:
    python scripts/monitor_sistema.py             # 1 ciclo de diagnóstico
    python scripts/monitor_sistema.py --monitor   # vigilância contínua (loop)
    python scripts/monitor_sistema.py --intervalo 60

Saída: logs/saude_sistema.log (linhas) + logs/saude_sistema.json (último ciclo).
"""

import argparse
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
LOG_LINHAS = PROJETO / "logs" / "saude_sistema.log"
LOG_JSON = PROJETO / "logs" / "saude_sistema.json"
BACKUP_DIR = PROJETO / "logs" / "backup_estado"
ESTADO_DIR = PROJETO / "estado"

# limites de alerta (proporcionais à máquina do usuário: 32GB RAM, SSD)
MIN_LIVRE_GB = 5.0          # disco
MIN_LIVRE_MB = 2048         # RAM livre
MAX_CPU_PCT = 90.0
MAX_LOG_MB = 50.0
MAX_BACKUPS = 12            # retenção de backups de estado


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(msg: str):
    linha = f"[{agora()}] {msg}"
    print(linha)
    try:
        LOG_LINHAS.parent.mkdir(parents=True, exist_ok=True)
        with LOG_LINHAS.open("a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def _http_ok(host: str, porta: int, timeout: float = 4.0) -> bool:
    try:
        urllib.request.urlopen(f"http://{host}:{porta}", timeout=timeout)
        return True
    except Exception:
        return False


def temperatura_cpu() -> str:
    """Temperatura da CPU via WMI (se disponível). Retorna 'n/d' se não houver."""
    try:
        r = subprocess.run(
            ["wmic", "/namespace:\\\\root\\wmi", "PATH", "MSAcpi_ThermalZoneTemperature",
             "get", "CurrentTemperature", "/value"],
            capture_output=True, text=True, timeout=10,
        )
        for linha in r.stdout.splitlines():
            if "CurrentTemperature" in linha:
                val = linha.split("=")[-1].strip()
                if val.isdigit():
                    # WMI retorna em décimos de Kelvin
                    celsius = (int(val) / 10.0) - 273.15
                    return f"{celsius:.1f}°C"
        return "n/d"
    except Exception:
        return "n/d"


def pids_na_porta(porta: int) -> list[int]:
    pids = set()
    try:
        r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=15)
        for linha in r.stdout.splitlines():
            if f":{porta}" in linha and "LISTEN" in linha.upper():
                partes = linha.split()
                if partes:
                    try:
                        pids.add(int(partes[-1]))
                    except ValueError:
                        pass
    except Exception:
        pass
    return sorted(pids)


def pid_vivo(pid: int) -> bool:
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=15)
        return f'"{pid}"' in r.stdout
    except Exception:
        return True


def cpu_por_servico() -> dict:
    """Uso de CPU/RAM por serviço do projeto (dash, ollama, fila, monitor, sanitiz)."""
    import psutil as _p
    servicos = {"dashboard": 0, "ollama": 0, "fila": 0, "monitor": 0, "sanitizar": 0, "outros_py": 0}
    ram = {k: 0 for k in servicos}
    try:
        for proc in _p.process_iter(["name", "cmdline", "cpu_percent", "memory_info"]):
            try:
                nome = (proc.info["name"] or "").lower()
                cmd = " ".join(proc.info["cmdline"] or []).lower()
                cpu = proc.info["cpu_percent"] or 0
                rss = (proc.info["memory_info"] and proc.info["memory_info"].rss or 0) / 1e6
                if "ollama" in nome:
                    servicos["ollama"] += cpu; ram["ollama"] += rss
                elif "monitor_sistema" in cmd:
                    servicos["monitor"] += cpu; ram["monitor"] += rss
                elif "executar_fila" in cmd or "gerar_massa" in cmd:
                    servicos["fila"] += cpu; ram["fila"] += rss
                elif "gerar_sanitizado" in cmd or "sanitiz" in cmd:
                    servicos["sanitizar"] += cpu; ram["sanitizar"] += rss
                elif "uvicorn" in cmd or "dashboard.main" in cmd:
                    servicos["dashboard"] += cpu; ram["dashboard"] += rss
                elif "python" in nome:
                    servicos["outros_py"] += cpu; ram["outros_py"] += rss
            except Exception:
                pass
    except Exception:
        pass
    return {"cpu": servicos, "ram_mb": {k: round(v, 0) for k, v in ram.items()}}


def definir_prioridade(pid: int, prioridade: str = "idle") -> None:
    """Define prioridade de um processo no Windows (idle=baixa, normal, etc.)."""
    mapa = {"idle": "Idle", "below_normal": "BelowNormal", "normal": "Normal"}
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-Process -Id {pid}).PriorityClass = '{mapa.get(prioridade, 'Normal')}'"],
                       capture_output=True, text=True, timeout=15)
    except Exception:
        pass


def _erros_recentes_log(arquivo: Path, n: int = 3) -> list[str]:
    """Últimas linhas com erro de um log (limitado)."""
    try:
        linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
        erros = [l.strip()[:120] for l in linhas
                 if any(k in l.upper() for k in ("ERRO", "ERROR", "TRACEBACK", "EXCEPTION"))]
        return erros[-n:]
    except Exception:
        return []


def backup_estados() -> dict:
    """Copia estados críticos para logs/backup_estado/ (proteção contra perda)."""
    feito, falhas = [], []
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        alvos = []
        if ESTADO_DIR.is_dir():
            for f in ESTADO_DIR.glob("*.json"):
                if any(k in f.name for k in ("fila", "executor", "explosao", "sanitiz", "datasets")):
                    alvos.append(f)
        p = PROJETO / "logs" / "fila_progresso.json"
        if p.exists():
            alvos.append(p)
        for f in alvos:
            try:
                destino = BACKUP_DIR / f"{f.stem}_{stamp}{f.suffix}"
                shutil.copy2(f, destino)
                feito.append(destino.name)
            except Exception as e:
                falhas.append(f"{f.name}:{e}")
        # retenção
        for f in sorted(BACKUP_DIR.glob("*.json"))[:-MAX_BACKUPS]:
            try:
                f.unlink()
            except Exception:
                pass
    except Exception as e:
        falhas.append(str(e))
    return {"feitos": len(feito), "falhas": falhas, "exemplos": feito[-3:]}


def ciclo(porta: int) -> dict:
    import psutil

    d = {"ts": agora(), "porta": porta}
    # disco
    try:
        u = shutil.disk_usage(str(PROJETO))
        d["disco_livre_gb"] = round(u.free / 1e9, 1)
        d["disco_pct"] = round(u.used / u.total * 100, 1)
        d["alerta_disco"] = u.free / 1e9 < MIN_LIVRE_GB
    except Exception as e:
        d["disco_erro"] = str(e)
    # memória
    m = psutil.virtual_memory()
    d["ram_livre_mb"] = round(m.available / 1e6, 0)
    d["ram_pct"] = m.percent
    d["alerta_ram"] = m.available / 1e6 < MIN_LIVRE_MB
    # CPU
    c = psutil.cpu_percent(interval=1)
    d["cpu_pct"] = c
    d["alerta_cpu"] = c > MAX_CPU_PCT
    # temperatura
    d["temp_cpu"] = temperatura_cpu()
    # ping
    d["ping_dashboard"] = _http_ok("127.0.0.1", porta)
    d["ping_ollama"] = _http_ok("127.0.0.1", 11434)
    # processos / porta
    pids = pids_na_porta(porta)
    d["pids_porta"] = pids
    d["sockets_orfaos"] = [p for p in pids if not pid_vivo(p)]
    d["alerta_orfao"] = bool(d["sockets_orfaos"])
    # fila
    try:
        f = json.loads((PROJETO / "estado" / "fila_geracao.json").read_text(encoding="utf-8"))
        ordens = f.get("ordens", [])
        d["fila_ordens"] = len(ordens)
        d["fila_rodando"] = sum(1 for o in ordens if o.get("status") == "rodando")
        d["fila_gerados"] = sum((o.get("gerados") or 0) for o in ordens)
        d["fila_pausado"] = f.get("pausado", False)
    except Exception as e:
        d["fila_erro"] = str(e)
    # logs grandes
    grandes = []
    for f in sorted((PROJETO / "logs").glob("*.log"), key=lambda x: x.stat().st_size, reverse=True)[:5]:
        mb = f.stat().st_size / 1e6
        if mb > MAX_LOG_MB:
            grandes.append(f"{f.name}:{mb:.0f}MB")
    d["logs_grandes"] = grandes
    # erros recentes nos logs principais
    erros = {}
    for nome in ("treinar_jsonl.log", "executor.log", "fila.log"):
        p = PROJETO / "logs" / nome
        if p.exists():
            e = _erros_recentes_log(p)
            if e:
                erros[nome] = e
    d["erros_recentes"] = erros
    # backup de estados
    d["backup"] = backup_estados()
    # CPU por serviço
    d["cpu_por_servico"] = cpu_por_servico()
    # resumo
    d["alerta"] = any(d.get(k) for k in ("alerta_disco", "alerta_ram", "alerta_cpu", "alerta_orfao"))
    return d


def _emitir(d: dict):
    try:
        LOG_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    alertas = []
    if d.get("alerta_disco"): alertas.append("DISCO")
    if d.get("alerta_ram"): alertas.append("RAM")
    if d.get("alerta_cpu"): alertas.append("CPU")
    if d.get("alerta_orfao"): alertas.append(f"ORFAO{sorted(d['sockets_orfaos'])}")
    status = "⚠️ " + "+".join(alertas) if alertas else "✅ OK"
    log(f"{status} | disco {d.get('disco_livre_gb')}GB | RAM {d.get('ram_livre_mb')}MB | "
        f"CPU {d.get('cpu_pct')}% | temp {d.get('temp_cpu')} | dash {d.get('ping_dashboard')} | "
        f"ollama {d.get('ping_ollama')} | fila {d.get('fila_rodando')} rod | "
        f"backup {d.get('backup', {}).get('feitos', 0)} | logs grandes {len(d.get('logs_grandes', []))}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Guardião de vigilância do sistema.")
    ap.add_argument("--porta", type=int, default=8000)
    ap.add_argument("--monitor", action="store_true", help="Vigilância contínua (loop).")
    ap.add_argument("--intervalo", type=int, default=60, help="Segundos entre ciclos.")
    args = ap.parse_args()

    log(f"🛡️  GUARDIÃO DE SISTEMA iniciado (porta {args.porta})")
    # prioridade baixa: o guardião não compete com fila/sanitizar/treino
    try:
        definir_prioridade(__import__("os").getpid(), "idle")
        log("   Prioridade do guardião: BAIXA (não compete com serviços pesados).")
    except Exception:
        pass
    if not args.monitor:
        _emitir(ciclo(args.porta))
        return 0
    log(f"   Vigilância contínua a cada {args.intervalo}s. Ctrl+C para parar.")
    while True:
        try:
            _emitir(ciclo(args.porta))
        except Exception as e:
            log(f"❌ erro no ciclo: {e}")
        time.sleep(max(10, args.intervalo))


if __name__ == "__main__":
    sys.exit(main())
