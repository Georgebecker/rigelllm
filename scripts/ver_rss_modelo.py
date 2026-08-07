# -*- coding: utf-8 -*-
"""ver_rss_modelo.py — Mostra cmdline dos rss_processor (qual modelo usam)."""
import sys
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== rss_processor: cmdline completo ===")
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "rss_processor" in cl:
            print(f"PID {p.info['pid']} | {cl}")
            print()
    except Exception:
        pass
