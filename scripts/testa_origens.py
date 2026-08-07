# -*- coding: utf-8 -*-
"""testa_origens.py — Testa o endpoint /api/executor/origens na porta 8000."""
import sys, urllib.request, json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

for porta in (8000,):
    try:
        req = urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/executor/origens", timeout=8)
        body = json.loads(req.read().decode())
        print(f"{porta} /origens: HTTP {req.status}")
        print("  total:", body.get("total"), "| pendentes:", body.get("pendentes"),
              "| parciais:", body.get("parciais"), "| concluidas:", body.get("concluidas"))
        for o in body.get("origens", [])[:15]:
            print(f"   - {o.get('nome')} | arq: {o.get('arquivos')} | "
                  f"sanitizado: {o.get('sanitizado')} | parcial: {o.get('parcial')}")
    except Exception as e:
        print(f"{porta} /origens: {type(e).__name__}: {str(e)[:200]}")
