# -*- coding: utf-8 -*-
"""
supervisor.py — MESTRE de auto-manutenção do RigelSLM (regra de ouro 14/08:
"a palavra tem que ter valor"; "se cair, levantar").

O que faz (a cada --intervalo):
  1. Mantém o GUARDIÃO (monitor_sistema.py) VIVO — se morreu, reinicia
     (processo independente CREATE_NO_WINDOW — não depende de janela/terminal).
  2. Mantém a FILA de geração RODANDO — se não há worker ativo e há ordens
     aguardando (e não pausada), dispara /api/local-generate/fila/iniciar.
  3. Quando a FILA TERMINA (0 rodando + 0 aguardando) → dispara o
     PÓS-PROCESSAMENTO uma única vez: ajuizamento do material gerado
     (ajuizar_pastas.py) + registra pendências de conversão/treino.
  4. Registra TUDO em logs/supervisor.log (persistente, à prova de queda).

Uso:
    python scripts/supervisor.py                # 1 ciclo (diagnóstico)
    python scripts/supervisor.py --daemon       # loop contínuo (deixar rodando)
    python scripts/supervisor.py --intervalo 120
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
LOG = PROJETO / "logs" / "supervisor.log"
ESTADO = PROJETO / "logs" / "supervisor_estado.json"
MONITOR = "scripts/monitor_sistema.py"
BASE = "http://127.0.0.1:8000"

# nomes de arquivos de monitor que identificam o processo
_IDENT = ("monitor_sistema",)


def log(msg: str):
    linha = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(linha)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def _python() -> str:
    """Caminho do python do venv do projeto."""
    p = PROJETO / ".venv" / "Scripts" / "python.exe"
    return str(p) if p.exists() else "python"


def iniciar_processo(args: list, prioridade_idle: bool = True) -> int:
    """Inicia processo independente (sem janela) e retorna o PID."""
    flags = subprocess.CREATE_NO_WINDOW
    try:
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    except Exception:
        pass
    p = subprocess.Popen(args, cwd=str(PROJETO), creationflags=flags)
    if prioridade_idle:
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"(Get-Process -Id {p.pid}).PriorityClass = 'Idle'"],
                           capture_output=True, timeout=15)
        except Exception:
            pass
    return p.pid


def _processos_por_ident(ident: tuple) -> list[int]:
    """PIDs de processos python cuja cmdline contém algum ident."""
    import psutil
    pids = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            nome = (proc.info["name"] or "").lower()
            if "python" not in nome:
                continue
            cmd = " ".join(proc.info["cmdline"] or [])
            if any(i in cmd for i in ident):
                pids.append(proc.info["pid"])
        except Exception:
            continue
    return pids


def manter_monitor() -> dict:
    vivos = _processos_por_ident(_IDENT)
    if vivos:
        return {"ok": True, "acao": "já_rodando", "pids": vivos}
    pid = iniciar_processo([_python(), str(PROJETO / MONITOR), "--monitor", "--intervalo", "60"])
    log(f"🔄 Guardião estava MORTO → reiniciado (PID {pid})")
    return {"ok": True, "acao": "reiniciado", "pid": pid}


def _fila_estado() -> dict:
    try:
        f = json.loads((PROJETO / "estado" / "fila_geracao.json").read_text(encoding="utf-8"))
        ordens = f.get("ordens", [])
        rod = sum(1 for o in ordens if o.get("status") == "rodando")
        agu = sum(1 for o in ordens if o.get("status") == "aguardando")
        ger = sum((o.get("gerados") or 0) for o in ordens)
        return {"ordens": len(ordens), "rodando": rod, "aguardando": agu,
                "gerados": ger, "pausado": bool(f.get("pausado"))}
    except Exception as e:
        return {"erro": str(e)}


def _http_post(path: str) -> dict:
    try:
        req = urllib.request.Request(BASE + path, data=b"{}",
                                     headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=20)
        return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def manter_fila() -> dict:
    e = _fila_estado()
    if e.get("erro"):
        return {"ok": False, "erro": e["erro"]}
    if e.get("pausado"):
        return {"ok": True, "acao": "pausada", "fila": e}
    if e.get("rodando", 0) > 0:
        return {"ok": True, "acao": "já_rodando", "fila": e}
    if e.get("aguardando", 0) == 0:
        return {"ok": True, "acao": "terminada", "fila": e}
    # sem worker e há aguardando → dispara
    r = _http_post("/api/local-generate/fila/iniciar")
    log(f"🔄 Fila sem worker ({e['aguardando']} aguardando) → disparando: ok={r.get('ok')} {str(r.get('mensagem'))[:60]}")
    return {"ok": bool(r.get("ok")), "acao": "iniciada", "fila": e}


def _estado_persistente() -> dict:
    try:
        if ESTADO.exists():
            return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"pos_processou": False, "ultimo_fim_fila": ""}


def fila_terminada_e_pos_processar(e: dict) -> None:
    st = _estado_persistente()
    if st.get("pos_processou"):
        return  # já fez
    if e.get("rodando", 0) > 0 or e.get("aguardando", 0) > 0:
        return  # fila ainda ativa
    # fila terminou: dispara ajuizamento uma única vez
    log("🏁 FILA TERMINOU — disparando pós-processamento (ajuizamento)...")
    pid = iniciar_processo([_python(), str(PROJETO / "scripts" / "ajuizar_pastas.py")])
    st["pos_processou"] = True
    st["ultimo_fim_fila"] = datetime.now().isoformat(timespec="seconds")
    st["ajuizamento_pid"] = pid
    try:
        ESTADO.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    log(f"⚖️ Ajuizamento disparado (PID {pid}). Registre pendências de conversão/treino depois.")


# ============================================================================
# 🧹 LIMPEZA AUTOMÁTICA (regra do usuário 15/08: "não acumular lixo; logs
# devem servir, não entulhar"). Roda 1x ao dia via --limpeza-diaria.
# ============================================================================
_CACHE_SCANS = ("estrutura_jsonl", "estrutura_txt", "estrutura_parquet")
_LOGS_DIR = PROJETO / "logs"
_MAX_TAMANHO_LOG_MB = 20      # logs maiores que isso são truncados/rotacionados
_MAX_BUFFERS_EXECUTOR = 15    # mantém só os buffers de executor mais recentes


def limpeza_geral() -> dict:
    """Limpa: buffers antigos, logs gigantes, caches de scan sem valor e
    pastas VAZIAS em dados/gerados/jsonl + dados/sanitizados (lixo real).

    Retorna resumo do que foi feito. NUNCA apaga dados com arquivos.
    """
    import shutil
    resumo = {"buffers": 0, "logs_grandes": 0, "caches": [], "pastas_vazias": []}

    # 1) Buffers de executor antigos (atividades já finalizadas)
    try:
        buffers = sorted(
            (f for f in _LOGS_DIR.glob("executor_buffer_*.log")),
            key=lambda f: f.stat().st_mtime, reverse=True)
        for f in buffers[_MAX_BUFFERS_EXECUTOR:]:
            try:
                f.unlink()
                resumo["buffers"] += 1
            except Exception:
                pass
    except Exception:
        pass

    # 2) Logs que passaram do tamanho saudável (mantém só as últimas ~2k linhas)
    try:
        for f in _LOGS_DIR.glob("*.log"):
            try:
                if f.stat().st_size > _MAX_TAMANHO_LOG_MB * 1024 * 1024:
                    linhas = f.read_text(encoding="utf-8", errors="replace").splitlines()
                    f.write_text("\n".join(linhas[-2000:]), encoding="utf-8")
                    resumo["logs_grandes"] += 1
            except Exception:
                pass
    except Exception:
        pass

    # 3) Caches de scan órfãos/antigos (> 2 dias) — regeneram no próximo acesso
    try:
        for nome in _CACHE_SCANS:
            c = _LOGS_DIR / "estrutura_cache" / f"{nome}.json"
            try:
                if c.exists() and (time.time() - c.stat().st_mtime) > 2 * 86400:
                    c.unlink()
                    resumo["caches"].append(nome)
            except Exception:
                pass
    except Exception:
        pass

    # 4) Pastas VAZIAS em dados/gerados/jsonl + dados/sanitizados (lixo real)
    try:
        for base_rel in ("dados/gerados/jsonl", "dados/sanitizados"):
            base = PROJETO / base_rel
            if not base.exists():
                continue
            for item in base.iterdir():
                try:
                    if item.is_dir() and not any(item.rglob("*")):
                        shutil.rmtree(item, ignore_errors=True)
                        resumo["pastas_vazias"].append(str(item.relative_to(PROJETO)))
                except Exception:
                    pass
    except Exception:
        pass

    log(f"🧹 Limpeza: buffers={resumo['buffers']} logs_grandes={resumo['logs_grandes']} "
        f"caches={resumo['caches']} pastas_vazias={len(resumo['pastas_vazias'])}")
    return resumo


def ciclo() -> dict:
    r1 = manter_monitor()
    r2 = manter_fila()
    e = _fila_estado()
    if not e.get("erro"):
        fila_terminada_e_pos_processar(e)
    # 🧹 Limpeza 1x ao dia (flag persistente com data)
    try:
        _st = _estado_persistente()
        hoje = datetime.now().strftime("%Y-%m-%d")
        if _st.get("ultima_limpeza") != hoje:
            limpeza_geral()
            _st["ultima_limpeza"] = hoje
            ESTADO.write_text(json.dumps(_st, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except Exception:
        pass
    return {"monitor": r1, "fila": r2, "fila_estado": e}


def main() -> int:
    ap = argparse.ArgumentParser(description="Mestre de auto-manutenção do RigelSLM.")
    ap.add_argument("--daemon", action="store_true", help="Loop contínuo (deixar rodando).")
    ap.add_argument("--intervalo", type=int, default=120)
    args = ap.parse_args()

    log("🛡️  SUPERVISOR MESTRE iniciado")
    try:
        import psutil  # noqa
    except ImportError:
        log("❌ psutil ausente — instale: pip install psutil")
        return 1

    if not args.daemon:
        r = ciclo()
        log(f"ciclo: monitor={r['monitor'].get('acao')} | fila={r['fila'].get('acao')} | "
            f"fila_estado={r['fila_estado']}")
        return 0

    # prioridade baixa
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-Process -Id {os.getpid()}).PriorityClass = 'Idle'"],
                       capture_output=True, timeout=15)
        log("   prioridade: BAIXA (não compete com serviços pesados).")
    except Exception:
        pass
    log(f"   loop contínuo a cada {args.intervalo}s. Log: logs/supervisor.log")
    while True:
        try:
            r = ciclo()
            log(f"ok | monitor={r['monitor'].get('acao')} | fila={r['fila'].get('acao')} | "
                f"gerados={r['fila_estado'].get('gerados')} aguardando={r['fila_estado'].get('aguardando')}")
        except Exception as ex:
            log(f"❌ erro no ciclo: {ex}")
        time.sleep(max(30, args.intervalo))


if __name__ == "__main__":
    sys.exit(main())
