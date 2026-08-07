#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""teste_geracao_rigel.py — Testa a geração do RigelSLM via API do Ollama
em várias temperaturas (modelo local subtreinado: pode gerar vazio/garble,
mas a ponte precisa responder). Lê o stream completo.

Uso:
  python scripts/teste_geracao_rigel.py [modelo]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

PROJETO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "http://127.0.0.1:11434"


def chat_stream(modelo: str, prompt: str, temp: float, max_tokens: int = 40) -> str:
    corpo = {"model": modelo,
             "messages": [{"role": "user", "content": prompt}],
             "stream": True,
             "options": {"num_predict": max_tokens, "temperature": temp}}
    req = urllib.request.Request(
        URL + "/api/chat",
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    texto = ""
    done = False
    with urllib.request.urlopen(req, timeout=180) as resp:
        for linha in resp:
            if not linha.strip():
                continue
            try:
                obj = json.loads(linha)
            except Exception:
                continue
            msg = obj.get("message") or {}
            texto += msg.get("content") or ""
            if obj.get("done"):
                done = True
    return f"done={done} | tokens={len(texto)} | saida={texto!r}"


def main() -> int:
    modelo = sys.argv[1] if len(sys.argv) > 1 else "rigelslm:q4_k_m"
    print(f"Modelo: {modelo}\n")
    for temp in (0.3, 0.8, 1.2, 1.8):
        try:
            r = chat_stream(modelo, "Ola, tudo bem? Conte uma historia curta.", temp)
            print(f"temp={temp:<4} -> {r}")
        except Exception as e:
            print(f"temp={temp:<4} -> ERRO: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
