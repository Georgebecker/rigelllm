# -*- coding: utf-8 -*-
"""
saude_dashboard.py — Guardião de saúde do dashboard (regra de ouro 14/08/2026).

"Somos como um sistema: se cairmos, devemos nos levantar; se tropeçarmos,
devemos prestar atenção; se não cuidarmos, acontecerá de novo."

Auditoria + auto-recuperação do servidor na porta 8000. Detecta e corrige o
travamento por SOCKET ÓRFÃO (workers spawn_main do uvicorn --reload que
herdam o LISTEN da porta e seguram o bind mesmo com o pai morto).

Uso:
    python scripts/saude_dashboard.py                # diagnóstico (read-only)
    python scripts/saude_dashboard.py --corrigir     # corrige e reinicia
    python scripts/saude_dashboard.py --porta 8000

Modo --corrigir:
    1. Se a porta está saudável (HTTP OK)  -> apenas registra, não mexe.
    2. Se não responde -> limpa uvicorn/spawn_main órfãos (PRESERVANDO os
       jobs do executor: fila, sanitizar, treino) e sobe 1 servidor limpo.
    3. Espera o health voltar e registra o resultado.

Log de auditoria: logs/saude.log (append, com timestamps).
"""

import argparse
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
LOG = PROJETO / "logs" / "saude.log"
PORTA_PADRAO = 8000


def log(msg: str) -> None:
    linha = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(linha)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception as e:
        print(f"  (falha ao gravar log: {e})")


def http_ok(porta: int, timeout: float = 4.0) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/status", timeout=timeout)
        return True
    except Exception:
        return False


def bind_ok(porta: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", porta))
        s.close()
        return True
    except OSError:
        return False


def processos_uvicorn() -> list[dict]:
    """python do projeto com dashboard.main/spawn_main/uvicorn na cmdline."""
    out = []
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
             "Where-Object { $_.CommandLine -match 'dashboard\\.main|spawn_main|uvicorn' } | "
             "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=30,
        )
        import json as _json
        dados = _json.loads(r.stdout) if r.stdout.strip() else []
        if isinstance(dados, dict):
            dados = [dados]
        for d in dados:
            out.append({"pid": int(d["ProcessId"]), "cmd": (d.get("CommandLine") or "")[:90]})
    except Exception as e:
        log(f"  aviso: não consegui listar processos ({e})")
    return out


def pids_na_porta(porta: int) -> list[int]:
    """PIDs que o netstat vê na porta (pode incluir PIDs mortos = socket órfão)."""
    pids = set()
    try:
        r = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=20,
        )
        for linha in r.stdout.splitlines():
            if f":{porta}" in linha and ("LISTEN" in linha or "LISTENING" in linha):
                partes = linha.split()
                if partes:
                    try:
                        pids.add(int(partes[-1]))
                    except ValueError:
                        pass
    except Exception as e:
        log(f"  aviso: netstat falhou ({e})")
    return sorted(pids)


def pid_vivo(pid: int) -> bool:
    try:
        subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True, timeout=15)
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=15)
        return f'"{pid}"' in r.stdout
    except Exception:
        return True  # se não consegue verificar, assume vivo (cautela)


def diagnosticar(porta: int) -> dict:
    responde = http_ok(porta)
    livre = bind_ok(porta)
    pids = pids_na_porta(porta)
    orfaos = [p for p in pids if not pid_vivo(p)]
    uvicorns = processos_uvicorn()
    return {
        "porta": porta,
        "responde_http": responde,
        "bind_livre": livre,
        "pids_na_porta": pids,
        "sockets_orfaos": orfaos,
        "n_uvicorns": len(uvicorns),
        "uvicorns": uvicorns,
    }


def corrigir(porta: int) -> bool:
    """Limpa órfãos/uvicorns e sobe 1 servidor limpo. Preserva executor/fila/sanitizar."""
    log("🛠️  CORRIGINDO: limpando uvicorn/spawn órfãos (preservando jobs do executor)...")
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
        "Where-Object { $_.CommandLine -match 'dashboard\\.main|spawn_main|uvicorn' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=30)
    except Exception as e:
        log(f"  aviso: falha ao limpar ({e})")

    # espera a porta liberar (kernel limpa sockets órfãos)
    for _ in range(20):
        if bind_ok(porta):
            break
        time.sleep(3)
    if not bind_ok(porta):
        log("❌ Porta ainda presa após limpeza (kernel segurando socket órfão). "
            "Pode ser necessário reiniciar a máquina.")
        return False

    # sobe 1 servidor limpo (sem --reload: evita novo acúmulo de spawn workers)
    log("🚀 Subindo servidor limpo (sem --reload, 1 processo)...")
    cmd = (
        f'start "" /min cmd /c "cd /d {PROJETO} && '
        f'call .venv\\Scripts\\activate.bat && '
        f'python -m uvicorn dashboard.main:app --host 0.0.0.0 --port {porta} '
        f'--timeout-keep-alive 30"'
    )
    subprocess.run(["cmd", "/c", cmd], timeout=15)

    for _ in range(20):
        if http_ok(porta, timeout=3):
            log("✅ Dashboard no ar e respondendo!")
            return True
        time.sleep(3)
    log("⚠️  Servidor subiu mas não respondeu em 60s — investigar.")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Guardião de saúde do dashboard.")
    ap.add_argument("--porta", type=int, default=PORTA_PADRAO)
    ap.add_argument("--corrigir", action="store_true", help="Corrige e reinicia se necessário.")
    ap.add_argument("--monitor", action="store_true",
                    help="Modo vigilância contínua: checa a cada --intervalo e auto-corrige.")
    ap.add_argument("--intervalo", type=int, default=20, help="Segundos entre checagens (--monitor).")
    args = ap.parse_args()

    if args.monitor:
        return _monitorar(args)

    log(f"🔍 Auditoria porta {args.porta} (corrigir={args.corrigir})")
    d = diagnosticar(args.porta)
    log(f"   responde_http={d['responde_http']} | bind_livre={d['bind_livre']} "
        f"| sockets_órfãos={d['sockets_orfaos']} | uvicorns={d['n_uvicorns']}")

    if d["responde_http"]:
        log("✅ Dashboard SAUDÁVEL. Nada a fazer.")
        return 0

    log("⚠️  Dashboard NÃO responde.")
    if not args.corrigir:
        log("   (rode com --corrigir para auto-recuperar)")
        return 1

    ok = corrigir(args.porta)
    return 0 if ok else 2


def _monitorar(args) -> int:
    """Vigilância contínua: a cada --intervalo, audita e auto-corrige se cair."""
    log(f"🛡️  GUARDIÃO em modo vigilância (porta {args.porta}, intervalo {args.intervalo}s). "
        f"Regra de ouro: se cair, levantar.")
    while True:
        try:
            d = diagnosticar(args.porta)
            if not d["responde_http"]:
                log(f"⚠️  Queda detectada (sockets_órfãos={d['sockets_orfaos']}). Auto-corrigindo...")
                corrigir(args.porta)
            elif d["sockets_orfaos"]:
                log(f"⚠️  Sockets órfãos detectados ({d['sockets_orfaos']}) mesmo com servidor "
                    f"OK — sinal de risco. Recomendo reiniciar em horário seguro.")
        except Exception as e:
            log(f"❌ Erro no ciclo do guardião: {e}")
        time.sleep(max(5, args.intervalo))


if __name__ == "__main__":
    sys.exit(main())
