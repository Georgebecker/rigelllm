# -*- coding: utf-8 -*-
"""arrumar_cpu.py — Para raspagem RSS + descarrega llama para liberar CPU.

Plano (cirúrgico, com verificação):
1. Verifica rss_processor ativos (quem segura o llama).
2. Para o rss_processor que usa o llama (se rodando) — kill simples, sem /T.
3. ollama stop dos modelos carregados (descarrega de verdade).
4. Confirma CPU livre.
"""
import sys, time, subprocess
import psutil

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def cmdline(pid):
    try:
        p = psutil.Process(pid)
        return p.name(), " ".join(p.cmdline() or [])
    except psutil.NoSuchProcess:
        return None, ""
    except Exception:
        return "?", ""

print("=== 1) rss_processor ativos ===")
rss = []
for p in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
    try:
        cl = " ".join(p.info["cmdline"] or [])
        if "rss_processor" in cl:
            idade = (time.time() - p.info["create_time"]) / 60
            modelo = "?"
            if "--modelo-resumo" in cl:
                modelo = cl.split("--modelo-resumo", 1)[1].split()[0]
            print(f"  PID {p.info['pid']} | {idade:.0f}min | modelo={modelo}")
            rss.append(p.info["pid"])
    except Exception:
        pass
if not rss:
    print("  (nenhum rss_processor rodando)")

print()
print("=== 2) Parando rss_processor (raspagem com llama em CPU) ===")
for pid in rss:
    nome, cl = cmdline(pid)
    if nome and "python" in nome.lower() and "rss_processor" in cl:
        r = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           capture_output=True, text=True, timeout=20)
        print(f"  PID {pid}: {r.stdout.strip() or r.stderr.strip()}")
    else:
        print(f"  PID {pid}: mudou — NÃO fechei (segurança)")

print()
print("=== 3) ollama stop (descarrega modelos) ===")
try:
    r = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=20,
                       encoding="utf-8", errors="replace")
    modelos = []
    for linha in r.stdout.splitlines()[1:]:
        partes = linha.split()
        if partes:
            modelos.append(partes[0])
    print(f"  modelos carregados: {modelos or '(nenhum)'}")
    for m in modelos:
        r2 = subprocess.run(["ollama", "stop", m], capture_output=True, text=True,
                            timeout=30, encoding="utf-8", errors="replace")
        print(f"  ollama stop {m}: {r2.stdout.strip() or r2.stderr.strip() or 'OK'}")
except Exception as e:
    print(f"  falha: {e}")

print()
print("=== 4) Registro ===")
with open("logs/meus_processos_fechados.log", "a", encoding="utf-8") as f:
    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] arrumar_cpu: parei rss "
            f"{rss} + ollama stop\n")
print("  gravado em logs/meus_processos_fechados.log")

time.sleep(2)
print()
print("=== 5) CPU agora (amostra 2s) ===")
for p in psutil.process_iter(["pid", "name"]):
    try:
        p.cpu_percent(None)
    except Exception:
        pass
time.sleep(2.0)
total = 0.0
for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
    try:
        total += p.info["cpu_percent"] or 0
    except Exception:
        pass
print(f"  CPU total usada (todos processos): {total:.0f}%")
print(f"  llama-server ainda: {'SIM' if any((p.info.get('name') or '')=='llama-server.exe' for p in psutil.process_iter(['name'])) else 'NÃO'}")
