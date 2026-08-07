# -*- coding: utf-8 -*-
"""diag_porta8000.py — Quem está de fato na porta 8000 (psutil, não netstat)."""
import sys, time, urllib.request, socket
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== Quem escuta a porta 8000 (via psutil.net_connections) ===")
for conn in psutil.net_connections(kind="tcp"):
    if conn.laddr and conn.laddr.port == 8000:
        try:
            p = psutil.Process(conn.pid)
            cl = " ".join(p.cmdline() or [])
            idade = (time.time() - p.create_time()) / 60
            print(f"  LISTEN pid={conn.pid} | {p.name()} | idade={idade:.0f}min | {cl[:120]}")
        except psutil.NoSuchProcess:
            print(f"  LISTEN pid={conn.pid} | PROCESSO MORTO (fantasma)")

print()
print("=== Processos uvicorn 8000 ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "status"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "uvicorn" in cl.lower() and "--port 8000" in cl:
            idade = (time.time() - p.info["create_time"]) / 60
            print(f"  PID {p.info['pid']} | status={p.info['status']} | idade={idade:.0f}min | {cl[:110]}")
    except Exception:
        pass

print()
print("=== Teste HTTP na 8000 ===")
try:
    req = urllib.request.urlopen("http://127.0.0.1:8000/api/executor/status", timeout=4)
    print(f"  8000: HTTP {req.status}")
except Exception as e:
    print(f"  8000: {type(e).__name__}: {str(e)[:100]}")

print()
print("=== Teste socket cru (conecta?) ===")
s = socket.socket(); s.settimeout(2)
try:
    s.connect(("127.0.0.1", 8000))
    print("  connect OK (alguém aceita TCP)")
except Exception as e:
    print(f"  connect falhou: {type(e).__name__} {str(e)[:60]}")
finally:
    s.close()
