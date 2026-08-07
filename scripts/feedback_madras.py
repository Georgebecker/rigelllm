# -*- coding: utf-8 -*-
"""feedback_madras.py — Feedback ao vivo: processo vivo? progresso? travou?
Uso: python scripts/feedback_madras.py [--verbose]
"""
import sys, json, time, os
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 1) Processo vivo?
vivo = False
procs = []
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time", "cpu_percent"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "limpeza_leve" in cl and "Madras1_corpus-ptbr-v2" in cl:
            idade = (time.time() - p.info["create_time"]) / 60
            cpu = p.info["cpu_percent"] or 0
            procs.append((p.info["pid"], idade, cpu))
            vivo = True
    except Exception:
        pass

# 2) Progresso
d = None
try:
    d = json.load(open("logs/limpeza_progresso.json", encoding="utf-8"))
except Exception:
    pass

print("=" * 60)
print("📊 FEEDBACK — Madras1 v2 COMPLETO (371.002 docs)")
print("=" * 60)

if not vivo:
    print("❌ NENHUM processo limpeza_leve rodando — travou/terminou/caiu!")
else:
    for pid, idade, cpu in procs:
        print(f"✅ Processo VIVO: PID {pid} | {idade:.0f} min | CPU {cpu:.0f}%")

if d:
    lidos = d.get("lidos", 0)
    total = 371002
    pct_real = lidos / total * 100
    pretrain = d.get("pretrain", 0)
    desc = d.get("descartados", 0)
    seg = d.get("decorrido_s", 0)
    ruido = d.get("ruido_ia", "?")
    print(f"\n📄 Lidos:     {lidos:,} de {total:,}  ({pct_real:.1f}%)")
    print(f"📝 Pretrain:  {pretrain:,}")
    print(f"🗑️ Descart:   {desc:,}  (ruído IA: {ruido})")
    print(f"⏱️  Tempo:     {seg:.0f}s ({seg/60:.1f} min)")
    vel = lidos / max(1, seg)
    restante = (total - lidos) / max(1, vel) / 60
    print(f"⚡ Veloc.:    {vel:.0f} docs/s | restante ~{restante:.0f} min")
    mt = os.path.getmtime("logs/limpeza_progresso.json")
    idade_s = time.time() - mt
    print(f"\n📡 Última atualização: {d.get('atualizado_em')} (há {idade_s:.0f}s)")
    print(f"   Estado: {'🟢 ATIVO (processando)' if idade_s < 90 else '🔴 PARADO há ' + str(int(idade_s)) + 's — ATENÇÃO!'}")
else:
    print("\n(progresso ainda não gravado — iniciando...)")

m = psutil.virtual_memory()
print(f"\n💾 RAM livre: {m.available/1e9:.1f} GB ({m.percent}% usado)")
print("=" * 60)
