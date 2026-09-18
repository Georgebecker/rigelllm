#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Teste REAL (isolado) das funções novas do executor:
  1) _detectar_processos_mortos()  → atividade com PID morto vira 'morto'
  2) reiniciar(aid)                → recomeça atividade com mesmo comando
Faz backup do estado, roda o teste e RESTAURA o estado original.
"""
import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ESTADO = RAIZ / "estado" / "executor_estado.json"
BACKUP = RAIZ / "estado" / "executor_estado_test.bak"

# 1) Backup do estado real
if ESTADO.exists():
    shutil.copy2(ESTADO, BACKUP)

from dashboard.services import executor

ok = True

try:
    # ---- Teste 1: detecção de processo morto ----
    with executor._lock:
        executor._atividades.clear()
        executor._atividades["atv-teste-morta"] = {
            "id": "atv-teste-morta", "nome": "Teste morta",
            "comando": "python -c 'x'", "comando_lista": [sys.executable, "-c", "x"],
            "cwd": str(RAIZ), "status": "rodando", "rodando": True,
            "pid": 999999999, "_processo": None, "mensagens": [],
            "inicio": "2026-08-13T00:00:00", "erro": None,
        }
    executor._detectar_processos_mortos()
    st = executor._atividades.get("atv-teste-morta", {}).get("status")
    print(f"[1] detecção de morta: status={st}  ->", "OK" if st == "morto" else "FALHOU")
    if st != "morto":
        ok = False

    # ---- Teste 2: reiniciar atividade (comando inofensivo) ----
    with executor._lock:
        executor._atividades.clear()
        executor._atividades["atv-teste-reiniciar"] = {
            "id": "atv-teste-reiniciar", "nome": "Teste reiniciar",
            "comando": f"{sys.executable} -c \"print('RIGEL_TESTE_OK')\"",
            "comando_lista": [sys.executable, "-c", "print('RIGEL_TESTE_OK')"],
            "cwd": str(RAIZ), "status": "interrompido", "rodando": False,
            "pid": None, "_processo": None, "mensagens": [],
            "inicio": "2026-08-13T00:00:00", "erro": "morreu",
            "reinicios": 3,
        }
    r = executor.reiniciar("atv-teste-reiniciar")
    print(f"[2] reiniciar -> ok={r.get('ok')} id={r.get('id')} msg={str(r.get('mensagem'))[:60]}")
    if not r.get("ok"):
        ok = False
    else:
        # confere que nova atividade foi criada e zera reinicios
        nova = executor._atividades.get(r["id"], {})
        print(f"    nova atividade status={nova.get('status')} reinicios={nova.get('reinicios')}")
        if nova.get("status") != "rodando":
            ok = False
        # para a atividade de teste
        executor.parar(r["id"])

    # ---- Teste 3: reiniciar atividade ainda rodando → recusa ----
    with executor._lock:
        executor._atividades["atv-teste-rodando"] = {
            "id": "atv-teste-rodando", "nome": "Teste rodando",
            "comando": "python -c 'x'", "comando_lista": [sys.executable, "-c", "x"],
            "cwd": str(RAIZ), "status": "rodando", "rodando": True,
            "pid": None, "_processo": None, "mensagens": [],
        }
    r2 = executor.reiniciar("atv-teste-rodando")
    print(f"[3] reiniciar rodando -> ok={r2.get('ok')} (esperado False) ->", "OK" if not r2.get("ok") else "FALHOU")
    if r2.get("ok"):
        ok = False

    print("\nRESULTADO:", "✅ TODOS OS TESTES PASSARAM" if ok else "❌ HOUVE FALHA")
finally:
    # 3) Restaura o estado original
    if BACKUP.exists():
        shutil.copy2(BACKUP, ESTADO)
        BACKUP.unlink()
    print("Estado original restaurado.")
    sys.exit(0 if ok else 1)
