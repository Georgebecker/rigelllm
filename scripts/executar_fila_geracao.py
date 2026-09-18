#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
executar_fila_geracao.py — EXECUTA A FILA DE GERAÇÃO EM SÉRIE (nunca paralelo).
v2 (13/08/2026) — ROBUSTO, com tratamento de erros PREVISTO:

  ▶️ SÉRIE: uma ordem por vez; re-lê a fila entre ordens (novas entram).
  ⏸️ PAUSA: se `estado/fila_geracao.json` tiver `pausado: true`, encerra no
     próximo ponto seguro — as ordens não processadas continuam 'aguardando'.
     Retomar = 'continuar' + iniciar de novo (ordens aguardando prosseguem).
  🛡️ GUARDA: antes de cada ordem checa memória/disco (config_recursos.json via
     estrutura_cache). Se insuficiente, espera até 10 min; se continuar ruim,
     encerra e a ordem volta a aguardar (não trava, não queima o SSD).
  🚨 TRAVAMENTO: cada ordem roda como SUBPROCESSO vigiado:
     - stall (sem progresso por 4 min) → mata e REINICIA (até 2x);
     - timeout total (meta × tempo por item + folga) → mata e trata;
     - reinícios esgotados → ordem vira 'erro' com diagnóstico.
  🔁 FALLBACK/DIAGNÓSTICO: se a taxa de erro da ordem for alta, o log registra
     as causas prováveis (modelo incapaz / timeout curto / pergunta não encaixa /
     RSS sem categoria) e o gerar_massa TROCA a pergunta por uma mais simples.
  📜 LOG: `logs/fila.log` (append) + log por ordem no estado + progresso em
     `logs/fila_progresso.json` (barra real no painel).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))
sys.path.insert(0, str(PROJETO_ROOT / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from dashboard.services import fila_geracao as fila  # noqa: E402
from dashboard.services.templates_conteudo import ORDEM_TIPOS  # noqa: E402

STALL_SEG = 240          # sem progresso por 4 min = travou
POLL_SEG = 5             # intervalo de vigilância
ESPERA_RECURSOS_SEG = 600  # espera máx. por recursos (10 min)
RECURSOS_POLL_SEG = 30
LOG_PATH = PROJETO_ROOT / "logs" / "fila.log"


def _log(msg: str) -> None:
    linha = f"[{datetime.now().isoformat()}] {msg}"
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass
    print(linha)


def _ler_massa_progresso() -> dict:
    p = PROJETO_ROOT / "logs" / "massa_progresso.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _recursos_ok() -> dict:
    """Guardião: memória e disco suficientes (config_recursos.json)."""
    try:
        from dashboard.services.estrutura_cache import memoria_ok, disco_ok
        ok_mem, msg_mem = memoria_ok()
        ok_disco, msg_disco = disco_ok(str(PROJETO_ROOT))
        return {"ok": ok_mem and ok_disco,
                "msg": f"{msg_mem or 'mem ok'} · {msg_disco or 'disco ok'}"}
    except Exception as e:
        return {"ok": True, "msg": f"guardião indisponível ({e})"}


def _aguardar_recursos(oid) -> None:
    """Espera recursos liberarem (até 10 min), avisando no log a cada poll."""
    fila.registrar_log(oid, "🛡️ Recursos insuficientes — aguardando liberar...")
    inicio = time.time()
    while time.time() - inicio < ESPERA_RECURSOS_SEG:
        time.sleep(RECURSOS_POLL_SEG)
        r = _recursos_ok()
        if r["ok"]:
            fila.registrar_log(oid, f"✅ Recursos OK — prosseguindo. {r['msg']}")
            return
        fila.registrar_log(oid, f"  ⏳ ainda sem recursos... {r['msg']}")


def _montar_cmd(ordem: dict) -> list[str]:
    tpls = ordem.get("templates") or ["todos"]
    ests = ordem.get("estilos") or ["todos"]
    arg_t = ",".join(tpls) if tpls != ["todos"] else "todos"
    arg_e = ",".join(ests) if ests != ["todos"] else "todos"
    return [sys.executable,
            str(PROJETO_ROOT / "scripts" / "gerar_massa_local.py"),
            "--modelo", ordem.get("modelo", "llama3.2:3b"),
            "--repeticoes", "1",
            "--meta", str(ordem.get("meta", 1)),
            "--templates", arg_t,
            "--estilos", arg_e,
            "--formato", ordem.get("formato", "txt"),
            "--fonte", ordem.get("fonte", "categorias"),
            "--categorias", ordem.get("categorias", "todas"),
            "--rss_limite", str(ordem.get("rss_limite", 0)),
            "--timeout", str(ordem.get("timeout_item", 300)),
            "--pos", "true",
            "--nome", f"Fila #{ordem.get('id')}: {ordem.get('titulo', '')}"]


def _spawn(cmd: list[str]) -> subprocess.Popen:
    """Sobe o subprocesso do gerar_massa; stdout do filho vai p/ arquivo
    (streaming visível sem entupir pipe)."""
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    buf = PROJETO_ROOT / "logs" / f"fila_buffer_{int(time.time())}.log"
    try:
        out = open(buf, "a", encoding="utf-8", errors="replace")
    except Exception:
        out = subprocess.DEVNULL
    return subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,
                            env=env, creationflags=flags)


def _matar(proc) -> None:
    """Mata o subprocesso E a árvore (taskkill /T — inclui o ollama filho)."""
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, timeout=20)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _monitorar(proc, oid: int, ordem: dict) -> int | str:
    """Vigia o subprocesso: progresso, stall, timeout e pausa.
    Retorna: 0 (ok), 'stall...', 'timeout total', 'pausado' ou 'falha:<rc>'."""
    inicio = time.time()
    ultimo_pct = -1
    ultima_mudanca = time.time()
    timeout_total = int(ordem.get("meta", 1)) * (int(ordem.get("timeout_item", 300)) + 60) + 300
    fila.registrar_log(oid, f"⏱️ Vigilância ativa (stall {STALL_SEG}s · timeout total ~{timeout_total}s)")
    while proc.poll() is None:
        time.sleep(POLL_SEG)
        mp = _ler_massa_progresso()
        pct = mp.get("pct", 0)
        if pct != ultimo_pct:
            ultimo_pct = pct
            ultima_mudanca = time.time()
            fila.registrar_log(oid, f"  ▸ {pct}% — {mp.get('atual', '')[:60]}")
            fila.marcar(oid, gerados=mp.get("gerados", 0), erros=mp.get("erros", 0))
            _gravar_progresso(fila.carregar())
        elif time.time() - ultima_mudanca > STALL_SEG:
            _matar(proc)
            return "stall (sem progresso por 4 min)"
        if time.time() - inicio > timeout_total:
            _matar(proc)
            return "timeout total"
        if fila.carregar().get("pausado"):
            _matar(proc)
            return "pausado"
    # terminou
    rc = proc.returncode
    mp = _ler_massa_progresso()
    fila.marcar(oid, gerados=mp.get("gerados", 0), erros=mp.get("erros", 0))
    if rc == 0:
        return 0
    return f"falha (código {rc})"


def _rodar_ordem(ordem: dict, idx: int, total: int) -> int:
    """Roda UMA ordem (subprocesso) com reinício por travamento.
    Retorna: 0=ok, 1=erro, -2=sem recursos, -3=pausado."""
    oid = ordem["id"]
    cmd = _montar_cmd(ordem)
    limite = int(ordem.get("max_reinicio", 2) or 2)
    reinicios = 0

    # Guarda de recursos ANTES de começar (e a cada reinício)
    if not _recursos_ok()["ok"]:
        _aguardar_recursos(oid)
        if not _recursos_ok()["ok"]:
            _log(f"🛑 Ordem #{oid}: recursos insuficientes após espera — volta a aguardar.")
            return -2

    while True:
        fila.registrar_log(oid, f"▶️ Subprocesso iniciado (tentativa {reinicios + 1}).")
        proc = _spawn(cmd)
        resultado = _monitorar(proc, oid, ordem)
        fila.marcar(oid, reinicios=reinicios)

        if resultado == 0:
            fila.registrar_log(oid, "✅ Subprocesso concluído com sucesso.")
            return 0
        if resultado == "pausado":
            fila.registrar_log(oid, "⏸️ Pausa detectada — ordem voltou para 'aguardando'.")
            return -3

        # travou / timeout / falhou → reinicia até o limite
        reinicios += 1
        fila.marcar(oid, reinicios=reinicios)
        if reinicios <= limite:
            fila.registrar_log(oid, f"🔄 {resultado} — REINICIANDO ordem ({reinicios}/{limite})...")
            if not _recursos_ok()["ok"]:
                _aguardar_recursos(oid)
            continue
        fila.registrar_log(oid, f"❌ {resultado} após {limite} reinícios — ordem marcada como erro.")
        return 1


def _diagnosticar_ordem(estado: dict, oid: int) -> None:
    """Se a taxa de erro da ordem for alta, registra as causas prováveis."""
    ordem = next((o for o in estado.get("ordens", []) if o.get("id") == oid), None)
    if not ordem:
        return
    gerados = ordem.get("gerados", 0)
    erros = ordem.get("erros", 0)
    total = gerados + erros
    if total < 3:
        return
    taxa = erros / total
    if taxa >= 0.4:
        diag = (f"⚠️ TAXA DE ERRO ALTA ({taxa:.0%}) — {erros} falhas em {total} itens. "
                "Causas prováveis: (1) modelo não consegue responder (troque para llama3.2:3b); "
                "(2) timeout por item curto demais; (3) a pergunta não encaixa no modelo — "
                "use fonte 'topicos' ou template 'artigo'; (4) fonte RSS sem categoria detectada "
                "(título não bate com as listas). O gerar_massa já tentou TROCAR a pergunta por "
                "uma mais simples. Se continuar, ajuste a ordem e rode de novo.")
        fila.registrar_log(oid, diag)
        fila.marcar(oid, diagnostico=diag)
        _log(f"⚠️ Ordem #{oid}: {diag[:200]}")
    elif taxa >= 0.2:
        fila.registrar_log(oid, f"ℹ️ Taxa de erro moderada ({taxa:.0%}) — acompanhe.")


def _ajuizar_ordem(estado: dict, oid: int) -> None:
    ordem = next((o for o in estado.get("ordens", []) if o.get("id") == oid), None)
    if not ordem:
        return
    if ordem.get("formato") != "txt" or not ordem.get("ajuizar"):
        return
    tpls = ordem.get("templates") or []
    if tpls == ["todos"] or not tpls:
        fila.registrar_log(oid, "ℹ️ Ajuizar automático: ordem com templates variados — "
                                "use o botão ⚖️ Ajuizar no painel para massa_final.")
        return
    for tpl in tpls:
        if tpl not in ORDEM_TIPOS:
            continue
        pasta = f"massa_final/{tpl}"
        fila.registrar_log(oid, f"⚖️ Ajuizando {pasta} ...")
        try:
            proc = subprocess.run(
                [sys.executable, str(PROJETO_ROOT / "scripts" / "ajuizar_pastas.py"),
                 "--pasta", pasta],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=1800, env={"PYTHONIOENCODING": "utf-8", **os.environ})
            if proc.returncode == 0:
                fila.registrar_log(oid, f"✅ Ajuizamento de {pasta} concluído.")
            else:
                fila.registrar_log(oid, f"⚠️ Ajuizamento de {pasta} retornou código {proc.returncode}.")
        except subprocess.TimeoutExpired:
            fila.registrar_log(oid, f"⚠️ Ajuizamento de {pasta} excedeu o tempo.")
        except Exception as e:
            fila.registrar_log(oid, f"⚠️ Ajuizamento falhou: {e}")


def _gravar_progresso(estado_atual: dict) -> None:
    ordens = estado_atual.get("ordens", [])
    total = len(ordens)
    rodando = estado_atual.get("rodando", False)
    mp = _ler_massa_progresso()
    pct_ordem = mp.get("pct", 0)
    concluidas = sum(1 for o in ordens if o.get("status") in ("concluido", "erro"))
    rodando_i = next((i for i, o in enumerate(ordens) if o.get("status") == "rodando"), -1)
    if total:
        pct = round((concluidas + (pct_ordem / 100 if rodando_i >= 0 else 0)) / total * 100, 1)
    else:
        pct = 100
    pendentes = [o for o in ordens if o.get("status") in ("aguardando", "rodando")]
    status = ("rodando" if rodando
              else ("concluido" if not pendentes else "aguardando"))
    fila.gravar_progresso({
        "rodando": rodando,
        "pausado": bool(estado_atual.get("pausado")),
        "ordem_atual": rodando_i + 1 if rodando_i >= 0 else concluidas,
        "total_ordens": total,
        "pct": pct,
        "status": status,
        "ordem_id": ordens[rodando_i]["id"] if rodando_i >= 0 else None,
        "ordem_titulo": ordens[rodando_i]["titulo"] if rodando_i >= 0 else "",
        "ordem_fonte": ordens[rodando_i].get("fonte", "") if rodando_i >= 0 else "",
        "atual": mp.get("atual", ""),
        "categoria": mp.get("categoria", ""),
        "gerados": mp.get("gerados", 0),
        "erros": mp.get("erros", 0),
        "retries": mp.get("retries", 0),
        "meta_ordem": mp.get("meta", 0),
        "decorrido_s": mp.get("decorrido_s", 0),
        "previsao_s": mp.get("previsao_s", 0),
        "media_s": mp.get("media_s", 0),
    })


def main() -> int:
    _log("🧾 Executor da fila iniciado.")
    fila.gravar_progresso({"rodando": True, "pct": 0, "ordem_atual": 0,
                           "total_ordens": 0, "status": "rodando",
                           "atual": "iniciando fila...", "decorrido_s": 0,
                           "previsao_s": 0, "media_s": 0, "retries": 0})
    try:
        while True:
            estado = fila.carregar()
            if estado.get("pausado"):
                _log("⏸️ Fila pausada — encerrando (retome com 'Continuar').")
                break
            estado["rodando"] = True
            fila.gravar(estado)
            # 🔄 RECUPERAÇÃO: ordens 'rodando' órfãs (execução anterior caiu —
            # parou, travou, PC desligou) voltam a 'aguardando' para reprocessar.
            for o in estado["ordens"]:
                if o.get("status") == "rodando":
                    fila.marcar(o["id"], status="aguardando")
                    fila.registrar_log(o["id"], "🔄 Recuperada: estava 'rodando' de execução "
                                                "anterior (parou/desligou) — voltou a aguardar.")
            ordens = [o for o in fila.carregar()["ordens"] if o.get("status") == "aguardando"]
            if not ordens:
                _log("✅ Nenhuma ordem pendente — encerrando.")
                break
            total = len(ordens)
            for idx, ordem in enumerate(ordens, 1):
                if fila.carregar().get("pausado"):
                    _log("⏸️ Pausa detectada entre ordens.")
                    break
                oid = ordem["id"]
                fila.marcar(oid, status="rodando")
                fila.registrar_log(oid, f"▶️ Ordem {idx}/{total}: {ordem['titulo']} "
                                        f"({ordem['meta']} itens · {ordem['fonte']} · "
                                        f"{ordem['formato']})")
                _gravar_progresso(fila.carregar())
                rc = _rodar_ordem(ordem, idx, total)
                if rc == 0:
                    fila.marcar(oid, status="concluido")
                    fila.registrar_log(oid, "✅ Ordem concluída.")
                    _diagnosticar_ordem(fila.carregar(), oid)
                    _ajuizar_ordem(fila.carregar(), oid)
                elif rc in (-2, -3):
                    fila.marcar(oid, status="aguardando")
                    _log("⏸️🛑 Encerrando fila (pausa ou recursos) — ordem volta a aguardar.")
                    break
                else:
                    fila.marcar(oid, status="erro")
                    _diagnosticar_ordem(fila.carregar(), oid)
                _gravar_progresso(fila.carregar())
                if fila.carregar().get("pausado"):
                    break
    finally:
        estado = fila.carregar()
        estado["rodando"] = False
        fila.gravar(estado)
        _gravar_progresso(fila.carregar())
        _log("🏁 Executor da fila encerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
