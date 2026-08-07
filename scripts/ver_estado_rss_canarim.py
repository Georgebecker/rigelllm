# -*- coding: utf-8 -*-
"""ver_estado_rss_canarim.py — Estado do rss_processor e do Canarim."""
import sys, json, time, os
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== rss_processor ativos ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "cpu_percent"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "rss_processor" in cl:
            idade = (time.time() - p.info["create_time"]) / 60
            cpu = p.info["cpu_percent"] or 0
            print(f"  PID {p.info['pid']} | {idade:.0f} min | CPU {cpu:.1f}% | {cl[:80]}")
    except Exception:
        pass

print()
print("=== Quem usa o Ollama (11434) ===")
for conn in psutil.net_connections(kind="tcp"):
    try:
        if conn.raddr and conn.raddr.port == 11434 and conn.status == "ESTABLISHED":
            try:
                p = psutil.Process(conn.pid)
                print(f"  pid {conn.pid} ({p.name()})")
            except Exception:
                pass
    except Exception:
        pass

print()
print("=== Canarim (progresso) ===")
try:
    d = json.load(open("logs/limpeza_progresso.json", encoding="utf-8"))
    mt = os.path.getmtime("logs/limpeza_progresso.json")
    idade_s = time.time() - mt
    print(f"  lidos: {d.get('lidos')} | SFT: {d.get('sft')} | desc: {d.get('descartados')} | tempo: {d.get('decorrido_s')}s")
    print(f"  atualizado há {idade_s:.0f}s → {'ATIVO' if idade_s < 60 else 'PARADO'}")
except Exception as e:
    print("  erro:", e)

print()
m = psutil.virtual_memory()
print(f"RAM livre: {m.available/1e9:.1f} GB ({m.percent}% usado)")
