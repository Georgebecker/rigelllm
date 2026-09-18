# -*- coding: utf-8 -*-
# TEMP: testar endpoint /api/pdfs/extrair
import json
import urllib.request

body = json.dumps({"caminho": "contos-populares-do-brasil.pdf"}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/pdfs/extrair",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    r = urllib.request.urlopen(req, timeout=300)
    d = json.loads(r.read().decode())
    print("ok:", d.get("ok"))
    print("extrair:", d.get("extrair"))
    print("converter:", d.get("converter"))
    print("jsonl:", d.get("jsonl"))
    print("aviso:", d.get("aviso"))
except Exception as e:
    print("ERRO:", type(e).__name__, e)
    try:
        print(e.read().decode()[:400])
    except Exception:
        pass
