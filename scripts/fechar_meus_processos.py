# -*- coding: utf-8 -*-
"""fechar_meus_processos.py — Fecha APENAS processos python -c (testes que deixei).

SEGURANÇA: verifica o cmdline antes de matar. NÃO toca em ollama/llama/rss/
ipykernel/uvicorn de terceiros. Só mata python.exe com '-c import sys' (meus
testes inline esquecidos) e registra o que fez.
"""
import sys, time, subprocess
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MEUS_TESTES = ("-c import sys", "-c import sys;", "-c import sys,urllib",
               "-c import sys,time", "-c import sys,glob")

print("=== Procurando meus testes esquecidos (python -c import sys...) ===")
alvos = []
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
    try:
        nome = (p.info["name"] or "").lower()
        cl = " ".join(p.info["cmdline"] or [])
        if nome == "python.exe" and any(t in cl for t in MEUS_TESTES):
            idade = (time.time() - p.info["create_time"]) / 60
            print(f"  PID {p.info['pid']} | {idade:.0f}min | {cl[:90]}")
            alvos.append(p.info["pid"])
    except Exception:
        pass

if not alvos:
    print("  (nenhum teste esquecido rodando)")
else:
    print()
    print("=== Fechando (verificação por cmdline já feita) ===")
    for pid in alvos:
        try:
            p = psutil.Process(pid)
            cl = " ".join(p.cmdline() or [])
            # Dupla verificação imediatamente antes de matar
            if "python.exe" in (p.name() or "").lower() and any(
                    t in cl for t in MEUS_TESTES):
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=20)
                print(f"  ✅ Fechado PID {pid}")
            else:
                print(f"  ⚠️ PID {pid} mudou — NÃO fechei (segurança)")
        except psutil.NoSuchProcess:
            print(f"  PID {pid} já morreu sozinho")
        except Exception as e:
            print(f"  PID {pid}: erro {e}")

print()
print("=== Registro gravado ===")
with open("logs/meus_processos_fechados.log", "a", encoding="utf-8") as f:
    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] fechei: {alvos}\n")
print("  logs/meus_processos_fechados.log")
