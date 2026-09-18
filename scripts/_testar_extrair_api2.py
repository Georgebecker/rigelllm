# -*- coding: utf-8 -*-
# TEMP: teste rápido do endpoint (timeout curto p/ ver comportamento)
import json
import time
import urllib.request

print("testando /api/pdfs/extrair (timeout 15s)...")
body = json.dumps({"caminho": "contos-populares-do-brasil.pdf"}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/pdfs/extrair",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
t0 = time.time()
try:
    r = urllib.request.urlopen(req, timeout=15)
    print(f"resposta em {time.time()-t0:.1f}s status={r.status}")
    print(r.read().decode()[:500])
except Exception as e:
    print(f"apos {time.time()-t0:.1f}s -> {type(e).__name__}: {e}")
