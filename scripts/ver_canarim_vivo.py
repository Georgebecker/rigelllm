# -*- coding: utf-8 -*-
"""ver_canarim_vivo.py — Processo vivo? Progresso real? Travou?"""
import sys, json, time, os
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== Processo limpeza_leve vivo? ===")
vivo = False
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "limpeza_leve" in cl:
            idade = (time.time() - p.info["create_time"]) / 60
            print(f"  PID {p.info['pid']} | rodando há {idade:.0f} min | {cl[:70]}")
            vivo = True
    except Exception:
        pass
if not vivo:
    print("  (nenhum processo limpeza_leve rodando — terminou ou caiu)")

print()
print("=== Progresso (logs/limpeza_progresso.json) ===")
try:
    d = json.load(open("logs/limpeza_progresso.json", encoding="utf-8"))
    print(f"  pct(taxa aprovação): {d.get('pct')}%")
    print(f"  lidos: {d.get('lidos')} | SFT: {d.get('sft')} | descartados: {d.get('descartados')}")
    print(f"  tempo decorrido: {d.get('decorrido_s')}s")
    print(f"  atualizado em: {d.get('atualizado_em')}")
    mt = os.path.getmtime("logs/limpeza_progresso.json")
    idade_s = time.time() - mt
    estado = "ATIVO" if idade_s < 60 else ("⚠️ PARADO há " + str(int(idade_s)) + "s")
    print(f"  arquivo de progresso atualizado há {idade_s:.0f}s → {estado}")
except Exception as e:
    print("  erro:", e)

print()
print("=== Memória livre ===")
m = psutil.virtual_memory()
print(f"  RAM livre: {m.available/1e9:.1f} GB ({m.percent}% usado)")
