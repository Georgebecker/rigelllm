# -*- coding: utf-8 -*-
"""ver_rss_atividade.py — CPU/tempo dos rss_processor para decidir qual llama matar."""
import sys, time
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== rss_processor: atividade (CPU) ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "rss_processor" in cl:
            p.cpu_percent(None)
    except Exception:
        pass

time.sleep(2.0)
agora = time.time()
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "cpu_percent", "memory_info"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "rss_processor" in cl:
            idade = (agora - p.info["create_time"]) / 60
            cpu = p.info["cpu_percent"] or 0
            mem = (p.info["memory_info"].rss or 0) / 1e6
            modelo = "?"
            if "--modelo-resumo" in cl:
                modelo = cl.split("--modelo-resumo", 1)[1].split()[0]
            print(f"  PID {p.info['pid']} | {idade:.0f}min | CPU {cpu:.1f}% | RAM {mem:.0f}MB | modelo={modelo}")
    except Exception:
        pass

print()
print("=== Mapa llama-servers -> modelo ===")
# 9028 = llama3.2:3b, 21292 = gemma2:2b (do diag anterior)
print("  PID 9028  -> llama3.2:3b  (usado pelo rss PID 11640)")
print("  PID 21292 -> gemma2:2b    (usado pelo rss PID 19308)")
