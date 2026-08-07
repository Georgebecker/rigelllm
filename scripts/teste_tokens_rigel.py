#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""teste_tokens_rigel.py — Captura TODOS os chunks da geração do RigelSLM,
decodifica os tokens gerados (contexto) e mostra o que o modelo produziu.

Uso:
  python scripts/teste_tokens_rigel.py [modelo] [prompt]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

PROJETO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "http://127.0.0.1:11434"


def main() -> int:
    modelo = sys.argv[1] if len(sys.argv) > 1 else "rigelslm:teste"
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Ola, tudo bem?"
    with open(os.path.join(PROJETO_ROOT, "tokenizer", "tokenizer.json"),
              encoding="utf-8") as f:
        vocab = json.load(f)["model"]["vocab"]
    inv = {i: t for t, i in vocab.items()}

    corpo = {"model": modelo, "prompt": prompt, "stream": True,
             "options": {"num_predict": 30, "temperature": 1.0}}
    req = urllib.request.Request(
        URL + "/api/generate",
        data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    chunks = []
    texto = ""
    with urllib.request.urlopen(req, timeout=180) as resp:
        for linha in resp:
            if not linha.strip():
                continue
            try:
                obj = json.loads(linha)
            except Exception:
                continue
            chunks.append(obj)
            texto += obj.get("response", "")
    print(f"chunks: {len(chunks)}")
    if not chunks:
        print("NENHUM chunk recebido (servidor nao enviou resposta)")
        return 1
    ult = chunks[-1]
    print(f"done: {ult.get('done')} | done_reason: {ult.get('done_reason')}")
    print(f"eval_count: {ult.get('eval_count')} | prompt_eval_count: {ult.get('prompt_eval_count')}")
    print(f"texto entregue: {texto!r}")
    ctx = ult.get("context") or []
    ppc = ult.get("prompt_eval_count") or 0
    gerados = [inv.get(i, "?") for i in ctx[ppc:]]
    print(f"tokens gerados ({len(gerados)}): {gerados}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
