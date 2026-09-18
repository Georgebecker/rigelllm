#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
executor.py — GESTOR DE ATIVIDADES do backend (dashboard = gestor, backend = executor).

Pedido do usuário (05/08):
  "o dashboard pode e deve ser capaz de rodar comando no backend, mantendo
   canal de comunicação, recebendo resultados/informações... ele é tipo um
   gestor, dá as ordens e o backend que faz o serviço, sempre respeitando
   aqueles limites (guardião) com relação a hardware, deve ser capaz de reger
   MAIS DE UMA atividade paralela, ficando registrado na tela quantas
   atividades paralelas estão rodando no backend em nome dele."

O que este módulo faz:
  - GERENCIADOR MULTI-ATIVIDADE: cada comando vira uma ATIVIDADE com id único
    (atv-<timestamp>-<n>). Várias podem rodar EM PARALELO.
  - GUARDIÃO: ANTES de iniciar cada atividade, consulta o guardião de limites
    (dashboard/services/estrutura_cache.py → memoria_ok / disco_ok / cpu).
    Se a máquina está sem memória/disco/CPU, RECUSA iniciar e informa o motivo.
  - SUBPROCESSO (não thread): sobrevive ao --reload do uvicorn; estado persistido.
  - CANAL DE COMUNICAÇÃO: buffer de saída por atividade, servido via SSE
    (GET /api/executor/stream?id=...).
  - RESULTADO ESTRUTURADO: se o script gravar um JSON em resultado_path, o
    executor expõe em status(id)['resultado'].
  - CONTROLE: iniciar / parar(id) / parar_todas / status(id) / listar.

Estado:   estado/executor_estado.json   (todas as atividades persistidas)
Log:      logs/executor.log             (linha do tempo global)
Buffer:   logs/executor_buffer_<id>.log (saída recente de cada atividade)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))

_PASTA_ESTADO = PROJETO_ROOT / "estado"
_ARQUIVO_ESTADO = _PASTA_ESTADO / "executor_estado.json"
_ARQUIVO_LOG = PROJETO_ROOT / "logs" / "executor.log"
_PASTA_BUFFERS = PROJETO_ROOT / "logs"

MAX_BUFFER = 2000            # linhas máx por atividade em memória (SSE)
MAX_ATIVIDADES = 20          # teto de atividades registradas (evita crescer sem fim)
# ⚡ Concorrência INTELIGENTE (regra do usuário): no máximo 3 atividades ao
# mesmo tempo, mas apenas 1 POR TIPO DE SERVIÇO (não pode 2 Ollama, 2 treinos,
# 2 conversões...). Tipos diferentes podem rodar juntos (ex.: conversão +
# geração de texto + RSS).
MAX_CONCORRENCIA = 3         # teto GLOBAL de atividades paralelas
MAX_POR_TIPO = 1             # teto POR TIPO de serviço


# Classificação do comando por "serviço" — o recurso que ele usa.
def _tipo_servico(comando: str) -> str:
    """Tipo de serviço de um comando (para não rodar 2 do mesmo tipo)."""
    c = (comando or "").lower()
    # Ollama (geração de texto) — o recurso mais escasso (e o usuário é claro:
    # "não pode 3 ollama rodando ao mesmo tempo")
    if any(k in c for k in ("ollama", "gerar_massa", "dialogos2", "rss_processor")):
        return "ollama"
    if "sanitiz" in c:
        return "sanitizacao"
    if "limpeza" in c:
        return "limpeza"
    if "converter_txt" in c:
        return "conversao"
    if "scrap" in c:
        return "scrap"
    if "treino" in c or "treinar" in c:
        return "treino"
    if "executor_pipeline" in c:
        return "pipeline"
    if any(k in c for k in ("download", "downdata", "ultra", "datasets")):
        return "download"
    if "explosao" in c or "explod" in c:
        return "explosao"
    if "verificar" in c or "encoding" in c:
        return "verificacao"
    return "outro"

_lock = threading.Lock()
# id -> {id, nome, comando, cwd, pid, status, inicio, fim, exit_code, erro,
#        mensagens, resultado, resultado_path, _processo}
_atividades: dict[str, dict] = {}


def _persistir() -> None:
    """Persiste as atividades (sem os objetos Popen). Sobrevive ao --reload."""
    try:
        _PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
        limpo = {}
        for aid, atv in _atividades.items():
            a = dict(atv)
            a.pop("_processo", None)
            a["mensagens"] = a.get("mensagens", [])[-50:]  # persiste só as últimas
            limpo[aid] = a
        _ARQUIVO_ESTADO.write_text(
            json.dumps(limpo, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _log_linha(linha: str) -> None:
    try:
        _ARQUIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {linha}\n")
    except Exception:
        pass


def _guardiao() -> tuple[bool, str]:
    """(ok, motivo). Consulta o guardião de limites (memória/disco/CPU).

    Precedência: config_recursos.json < env < runtime (recursos.py).
    Se não conseguir consultar, segue OTIMISTA (não bloqueia sem evidência).
    """
    try:
        from dashboard.services.estrutura_cache import memoria_ok, disco_ok
        ok, motivo = memoria_ok()
        if not ok:
            return False, f"GUARDIÃO: {motivo} — não vou iniciar (regra do usuário)."
        ok, motivo = disco_ok(str(PROJETO_ROOT))
        if not ok:
            return False, f"GUARDIÃO: {motivo} — não vou iniciar (regra do usuário)."
        # CPU: se estiver estourando o limite, recusa (não sobrecarrega)
        try:
            from dashboard.services.estrutura_cache import _cpu_ok
            if not _cpu_ok():
                return False, "GUARDIÃO: uso de CPU alto — não vou iniciar agora (respire)."
        except Exception:
            pass
        return True, ""
    except Exception as e:
        _log_linha(f"Guardião indisponível ({e}) — seguindo otimista.")
        return True, ""


def _concorrencia_ok(comando: str | None = None) -> tuple[bool, str]:
    """(ok, motivo). Concorrência INTELIGENTE (regra do usuário):
    - no máximo MAX_CONCORRENCIA atividades ao mesmo tempo (3);
    - apenas 1 POR TIPO DE SERVIÇO (não pode 2 Ollama / 2 treinos...);
    - tipos DIFERENTES podem rodar juntos (ex.: conversão + geração + RSS)."""
    rodando = sum(1 for a in _atividades.values() if a.get("_processo") is not None
                  or a.get("status") == "rodando")
    if rodando >= MAX_CONCORRENCIA:
        return False, (f"Já há {rodando} atividades rodando (máx {MAX_CONCORRENCIA} — "
                       f"1 por serviço). Pare uma antes de iniciar outra.")
    if comando:
        tipo = _tipo_servico(comando)
        # Só 1 do MESMO tipo: verifica as atividades RODANDO agora
        for a in _atividades.values():
            if not (a.get("_processo") is not None or a.get("status") == "rodando"):
                continue
            t_atv = _tipo_servico(a.get("comando") or "")
            if t_atv == tipo:
                return False, (f"Já há uma atividade do tipo '{tipo}' rodando "
                               f"(só 1 por serviço). Aguarde terminar ou pare a outra.")
    return True, ""


# ============================================================================
# STATUS / LISTAGEM
# ============================================================================
MAX_REINICIOS_RELOAD = 6  # quantas vezes re-spawnar atividade morta pelo --reload
                         # (após cair 6x seguidas, pergunta se quer continuar +6)


def _recuperar_apos_reload() -> None:
    """Após --reload, reancora as atividades que ainda estão rodando (PID órfão).

    Se o processo morreu no reinício do servidor, REINICIA automaticamente o
    comando (até MAX_REINICIOS_RELOAD) — regra de ouro: o pipeline NÃO pode
    morrer junto com o --reload do uvicorn (era isso que "travava" a geração
    em massa: o servidor reiniciava e o filho morria em silêncio)."""
    try:
        if not _ARQUIVO_ESTADO.exists() or _atividades:
            return
        disco = json.loads(_ARQUIVO_ESTADO.read_text(encoding="utf-8"))
        for aid, dados in disco.items():
            if not isinstance(dados, dict):
                continue
            dados["mensagens"] = dados.get("mensagens", [])
            if dados.get("status") == "rodando" and dados.get("pid"):
                try:
                    import psutil
                    if psutil.pid_exists(dados["pid"]):
                        dados["status"] = "rodando_externo"
                    else:
                        _reiniciar_apos_reload(aid, dados)
                except Exception:
                    _reiniciar_apos_reload(aid, dados)
            _atividades[aid] = dados
        _persistir()  # reflete no disco: respawn / aguardando / rodando_externo
    except Exception:
        pass


def _reiniciar_apos_reload(aid: str, dados: dict) -> None:
    """Re-spawna o comando da atividade que morreu junto com o servidor.

    Se cair MAX_REINICIOS_RELOAD vezes seguidas, PARA e PERGUNTA ao usuário
    se deseja continuar por mais MAX_REINICIOS_RELOAD tentativas
    (status 'aguardando' → botão ▶️ Continuar no painel /executor)."""
    reinicios = int(dados.get("reinicios") or 0)
    comando = dados.get("comando") or ""
    cwd = dados.get("cwd") or str(PROJETO_ROOT)
    if reinicios >= MAX_REINICIOS_RELOAD or (not comando and not dados.get("comando_lista")):
        dados["status"] = "aguardando"
        dados["rodando"] = False
        dados["aguardando_continuar"] = True
        dados["pid"] = None
        dados["_processo"] = None
        dados["erro"] = (
            f"⚠️ Este processo caiu {MAX_REINICIOS_RELOAD} vezes após "
            f"reinícios do servidor. Clique em ▶️ Continuar para tentar mais "
            f"{MAX_REINICIOS_RELOAD} vezes, ou em Parar para abandonar.")
        _persistir()
        return
    try:
        # Usa a LISTA EXATA de argumentos quando disponível (comando_lista) —
        # re-divisar a string quebraria argumentos com espaços (ex.:
        # "--nome TODAS as atividades" → 3 args) e caminhos do Windows.
        cmd = list(dados.get("comando_lista") or [])
        if not cmd:
            import shlex
            # posix=False preserva as barras invertidas dos caminhos (o modo
            # POSIX destruiria D:\Projetos\... e falharia com [WinError 2]).
            cmd = shlex.split(comando, posix=False)
        if cmd and cmd[0].lower() in ("python", "python3"):
            cmd[0] = sys.executable
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        # Windows: grupo de processo próprio — o filho NÃO é cancelado junto
        # com o uvicorn/watchdog (regra 13/08: atividade deve rodar em paralelo).
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(cmd, cwd=cwd,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace",
                                env=env, bufsize=1, creationflags=flags)
        dados["pid"] = proc.pid
        dados["_processo"] = proc
        dados["reinicios"] = reinicios + 1
        dados["status"] = "rodando"
        dados["rodando"] = True
        dados["aguardando_continuar"] = False
        dados["erro"] = None
        dados["fim"] = None
        dados["exit_code"] = None
        dados.setdefault("mensagens", []).append(
            f"🔄 Reiniciado automaticamente após reinício do servidor "
            f"(tentativa {reinicios + 1}/{MAX_REINICIOS_RELOAD}).")
        threading.Thread(target=_ler_saida, args=(aid, proc), daemon=True).start()
        threading.Thread(target=_ler_stderr, args=(aid, proc), daemon=True).start()
        threading.Thread(target=_monitorar_fim, args=(aid, proc), daemon=True).start()
        _log_linha(f"🔄 [{aid}] reiniciado automaticamente (PID {proc.pid})")
        _persistir()
    except Exception as e:
        dados["status"] = "interrompido"
        dados["rodando"] = False
        dados["aguardando_continuar"] = False
        dados["erro"] = f"Falha ao reiniciar após reload: {e}"
        _persistir()


def continuar_apos_reload(aid: str) -> dict:
    """Continua por mais MAX_REINICIOS_RELOAD tentativas uma atividade que
    caiu o número máximo de vezes após reinícios do servidor (status
    'aguardando'). Zera o contador e re-spawna o comando."""
    with _lock:
        a = _atividades.get(aid)
        if a is None:
            return {"ok": False, "erro": "Atividade não encontrada."}
        if not a.get("aguardando_continuar"):
            return {"ok": False,
                    "erro": "Atividade não está aguardando continuação."}
        a["aguardando_continuar"] = False
        a["reinicios"] = 0
        a["status"] = "rodando"
        a["rodando"] = True
    _reiniciar_apos_reload(aid, a)
    if a.get("status") == "rodando":
        return {"ok": True, "mensagem":
                f"▶️ Continuando — nova rodada de {MAX_REINICIOS_RELOAD} tentativas."}
    return {"ok": False, "erro": a.get("erro") or "Falha ao continuar."}


def _detectar_processos_mortos() -> None:
    """Detecta atividades marcadas como 'rodando' cujo processo JÁ MORREU
    (estado fantasma: PID não existe mais no sistema — ex.: morreu em silêncio
    após um --reload sem respawn eficaz).

    Marca como status 'morto' + mensagem + log — o painel oferece o botão
    🔄 Reiniciar para o USUÁRIO tratar pelo próprio sistema (regra 13/08:
    recomeçar deve ser algo previsto, registrado e tratado pelo sistema).
    """
    try:
        import psutil
    except Exception:
        return
    with _lock:
        alvos = [(aid, a) for aid, a in _atividades.items()
                 if a.get("status") in ("rodando", "rodando_externo") and a.get("pid")]
    for aid, a in alvos:
        proc = a.get("_processo")
        try:
            if proc is not None and proc.poll() is None:
                continue  # Popen vivo
            if not psutil.pid_exists(a["pid"]):
                with _lock:
                    atv = _atividades.get(aid)
                    if atv is None or atv.get("status") not in ("rodando", "rodando_externo"):
                        continue
                    atv["status"] = "morto"
                    atv["rodando"] = False
                    atv["pid"] = None
                    atv["_processo"] = None
                    atv.setdefault("mensagens", []).append(
                        "💀 Processo morreu sem aviso (PID não existe mais). "
                        "Clique em 🔄 Reiniciar para recomeçar — registro feito pelo sistema.")
                    _persistir()
                _log_linha(
                    f"💀 [{aid}] processo morto detectado (PID {a['pid']} não existe) "
                    f"— status 'morto', aguardando Reiniciar.")
        except Exception:
            continue


def reiniciar(aid: str) -> dict:
    """🔄 Recomeça uma atividade que morreu/interrompeu (mesmo comando).

    Ação DENTRO do sistema (regra 13/08): o usuário trata pelo painel. Cria
    uma NOVA atividade com o comando original registrado (comando_lista),
    passando pelo guardião + concorrência + persistência. Zera o contador de
    reinícios (recomeço manual = nova rodada de auto-restart).
    """
    with _lock:
        a = _atividades.get(aid)
        if a is None:
            return {"ok": False, "erro": "Atividade não encontrada."}
        if a.get("status") in ("rodando", "rodando_externo"):
            return {"ok": False, "erro": "Atividade ainda está rodando."}
        if a.get("aguardando_continuar"):
            return {"ok": False,
                    "erro": "Esta atividade está aguardando sua decisão — use ▶️ Continuar."}
        cmd = list(a.get("comando_lista") or [])
        if not cmd:
            import shlex
            cmd = shlex.split(a.get("comando") or "", posix=False)
        if not cmd:
            return {"ok": False, "erro": "Sem comando registrado para reiniciar."}
        nome = a.get("nome") or "atividade"
        cwd = a.get("cwd") or str(PROJETO_ROOT)
        resultado_path = a.get("resultado_path")
        a["reinicios"] = 0  # recomeço manual = nova rodada de auto-restart
        _persistir()
    _log_linha(f"🔄 [{aid}] reinício MANUAL solicitado pelo usuário: {nome}")
    return iniciar(cmd, nome=nome, cwd=cwd, resultado_path=resultado_path)


def _atividade_externa() -> dict | None:
    """Detecta execução EXTERNA (CLI) pelo arquivo de progresso.

    Se logs/sanitizacao_progresso.json existe e está sendo ATUALIZADO mas não
    há atividade registrada do executor para esse comando, o painel mostra uma
    'atividade externa' com a barra real — REGRA DE OURO: o dashboard informa
    tudo, inclusive o que roda fora dele (harmonia dashboard↔backend, 04/08).
    """
    try:
        import time as _t
        caminho = PROJETO_ROOT / "logs" / "sanitizacao_progresso.json"
        if not caminho.exists():
            return None
        idade = _t.time() - caminho.stat().st_mtime
        if idade > 300:  # inativo há 5 min → não é mais "rodando"
            return None
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        pct = dados.get("pct") or 0
        if pct >= 100:
            return None  # concluída

        # Já existe atividade registrada que cobre esse progresso?
        with _lock:
            coberto = any(
                "sanitizar" in (a.get("comando") or "").lower()
                for a in _atividades.values()
                if a.get("status") in ("rodando", "rodando_externo"))
        if coberto:
            return None

        # Atividade virtual "externa" (CLI rodando por fora)
        return {
            "id": "externo-sanitizacao",
            "nome": "sanitização (CLI externa)",
            "comando": "rodado fora do executor — CLI/terminal",
            "status": "rodando_externo",
            "rodando": True,
            "pid": None,
            "inicio": None,
            "fim": None,
            "exit_code": None,
            "erro": None,
            "mensagens": [],
            "resultado": None,
            "progresso": dados,
            "externo": True,
        }
    except Exception:
        return None


def listar() -> dict:
    """Lista TODAS as atividades registradas + contador de paralelas rodando.

    Inclui execuções EXTERNAS detectadas pelo progresso (harmonia com o backend).
    """
    _recuperar_apos_reload()
    _detectar_processos_mortos()
    with _lock:
        items = []
        for aid, a in _atividades.items():
            it = dict(a)
            it.pop("_processo", None)
            it["mensagens"] = list(a.get("mensagens", []))
            items.append(it)
        items.sort(key=lambda x: x.get("inicio") or "", reverse=True)
        rodando = sum(1 for it in items
                      if it.get("status") in ("rodando", "rodando_externo"))
    # ⚠️ FORA do lock: _atividade_externa também adquire _lock (não reentrante)
    ext = _atividade_externa()
    if ext and ext["id"] not in [x.get("id") for x in items]:
        items.append(ext)
        rodando += 1
    return {
        "total": len(items),
        "rodando": rodando,
        "max_concorrencia": MAX_CONCORRENCIA,
        "atividades": items,
    }


def status(aid: str = "") -> dict:
    """Status de UMA atividade (ou resumo se aid vazio)."""
    _recuperar_apos_reload()
    _detectar_processos_mortos()
    if not aid:
        # ⚠️ NÃO chama listar() dentro de lock (deadlock: Lock não é reentrante).
        resumo = listar()
        resumo["atividades"] = [
            {k: v for k, v in a.items() if k != "mensagens"}
            for a in resumo.get("atividades", [])
        ]
        # Barra de progresso real: lê o progresso persistido de cada atividade
        for a in resumo.get("atividades", []):
            prog = _ler_progresso(a.get("id", ""))
            if prog:
                a["progresso"] = prog
        return resumo
    with _lock:
        a = _atividades.get(aid)
        if not a:
            return {"ok": False, "erro": f"Atividade não encontrada: {aid}"}
        it = dict(a)
        it.pop("_processo", None)
        it["mensagens"] = list(a.get("mensagens", []))
    # ⚠️ FORA do lock: _ler_progresso também adquire _lock (Lock não é reentrante)
    prog = _ler_progresso(aid)
    if prog:
        it["progresso"] = prog
    return it


def stream_linhas(aid: str) -> list[str]:
    """Buffer de saída de uma atividade (p/ SSE)."""
    with _lock:
        a = _atividades.get(aid)
        if not a:
            return []
        return list(a.get("mensagens", []))


def limpar_buffer(aid: str = "") -> dict:
    """Limpa o buffer de uma atividade (ou de todas)."""
    with _lock:
        alvos = [aid] if aid else list(_atividades.keys())
        for a in alvos:
            if a in _atividades:
                _atividades[a]["mensagens"] = []
    return {"ok": True, "mensagem": "Buffer limpo."}


def ler_buffer_disco(aid: str, linhas: int = 40) -> dict:
    """Lê as últimas linhas do buffer em disco de uma atividade.

    O buffer é gravado em logs/executor_buffer_<id>.log a cada linha —
    isso sobrevive ao fechamento do SSE e mostra o RESULTADO real
    (ex.: '✅ 494 aprovados | 🟡 299 suspeitos') mesmo após concluir.
    """
    try:
        p = _PASTA_BUFFERS / f"executor_buffer_{aid}.log"
        if not p.exists():
            return {"ok": True, "aid": aid, "linhas": [], "existe": False}
        texto = p.read_text(encoding="utf-8", errors="replace")
        todas = [l for l in texto.splitlines() if l.strip()]
        return {"ok": True, "aid": aid, "linhas": todas[-linhas:],
                "total": len(todas), "existe": True}
    except Exception as e:
        return {"ok": False, "aid": aid, "erro": str(e)}


def limpar_historico() -> dict:
    """Remove atividades CONCLUÍDAS/ERRO/PARADAS antigas (mantém as rodando)."""
    with _lock:
        ativos = [aid for aid, a in _atividades.items()
                  if a.get("status") in ("rodando", "rodando_externo")]
        for aid in list(_atividades.keys()):
            if aid not in ativos:
                del _atividades[aid]
        _persistir()
    return {"ok": True, "mensagem": "Histórico de atividades limpo (mantidas as ativas)."}


# ============================================================================
# MURAL DE RESULTADOS — registra tudo que o pipeline executou (limpo sob demanda)
# ============================================================================
_MURAL_PATH = PROJETO_ROOT / "logs" / "mural_pipeline.json"


def ler_mural() -> dict:
    """Lê o mural de resultados do pipeline."""
    try:
        if not _MURAL_PATH.exists():
            return {"ok": True, "mural": [], "total": 0}
        dados = json.loads(_MURAL_PATH.read_text(encoding="utf-8"))
        if not isinstance(dados, list):
            return {"ok": True, "mural": [], "total": 0}
        return {"ok": True, "mural": dados, "total": len(dados)}
    except Exception as e:
        return {"ok": False, "erro": str(e), "mural": [], "total": 0}


def limpar_mural() -> dict:
    """Apaga o mural de resultados (pode ser limpo a qualquer momento)."""
    try:
        if _MURAL_PATH.exists():
            _MURAL_PATH.unlink()
        return {"ok": True, "mensagem": "Mural de resultados limpo."}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


# ============================================================================
# EXECUÇÃO (multi-atividade, guardião, subprocesso)
# ============================================================================
def _anexar(aid: str, linha: str) -> None:
    """Anexa linha ao buffer da atividade (memória + disco)."""
    with _lock:
        a = _atividades.get(aid)
        if a is None:
            return
        a.setdefault("mensagens", []).append(linha)
        if len(a["mensagens"]) > MAX_BUFFER:
            a["mensagens"] = a["mensagens"][-MAX_BUFFER:]
    try:
        with open(_PASTA_BUFFERS / f"executor_buffer_{aid}.log", "a",
                  encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def _ler_saida(aid: str, proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for linha in proc.stdout:
        linha = linha.rstrip("\n")
        if linha.strip():
            _anexar(aid, linha)


def _ler_stderr(aid: str, proc: subprocess.Popen) -> None:
    erros: list[str] = []
    assert proc.stderr is not None
    for linha in proc.stderr:
        linha = linha.rstrip("\n")
        if linha.strip():
            erros.append(linha)
            if len(erros) > 30:
                erros = erros[-30:]
    if erros:
        with _lock:
            a = _atividades.get(aid)
            if a is not None:
                a["erro"] = "\n".join(erros[-15:])


def _monitorar_fim(aid: str, proc: subprocess.Popen) -> None:
    codigo = proc.wait()
    with _lock:
        a = _atividades.get(aid)
        if a is None:
            return
        a["rodando"] = False
        a["pid"] = None
        a["fim"] = datetime.now().isoformat()
        a["exit_code"] = codigo
        a["_processo"] = None
        rp = a.get("resultado_path")
        if rp and Path(rp).exists():
            try:
                a["resultado"] = json.loads(Path(rp).read_text(encoding="utf-8"))
            except Exception as e:
                a["resultado"] = {"erro_leitura": str(e)}
        if codigo == 0:
            a["status"] = "concluido"
        else:
            a["status"] = "erro"
        _persistir()
    if codigo == 0:
        msg = f"✅ Atividade {a.get('nome') or aid} concluída (código 0)."
        _log_linha(msg)
    else:
        msg = f"❌ Atividade {a.get('nome') or aid} terminou com código {codigo}."
        _log_linha(msg)


# Caminhos de progresso que o executor conhece (lê p/ expor a barra no painel)
# Ordem importa: pipeline_progresso.json é o que o executor_pipeline grava
# quando a atividade roda "todas as origens" (o sanitizar (todas)). Sem ele
# o painel lia sanitizacao_progresso.json (do script direto) e o % ficava
# parado mesmo com o pipeline avançando (bug 18/08).
_CAMINHOS_PROGRESSO = [
    ("sanitizar", PROJETO_ROOT / "logs" / "pipeline_progresso.json"),
    ("sanitizar", PROJETO_ROOT / "logs" / "sanitizacao_progresso.json"),
    ("limpeza_leve", PROJETO_ROOT / "logs" / "pipeline_progresso.json"),
    ("limpeza_leve", PROJETO_ROOT / "logs" / "limpeza_progresso.json"),
    ("limpeza", PROJETO_ROOT / "logs" / "limpeza_progresso.json"),
    ("espaco", PROJETO_ROOT / "logs" / "espaco_progresso.json"),
]


def _ler_progresso(aid: str) -> dict | None:
    """Lê o arquivo de progresso associado à atividade (se o comando gravar).

    O script (ex.: gerar_sanitizados.py) grava logs/sanitizacao_progresso.json
    a cada N exemplos; o executor expõe isso em status() para o painel
    desenhar a BARRA DE PERCENTUAL real (regra de ouro: usuário vê movimento).
    """
    with _lock:
        a = _atividades.get(aid)
        if not a:
            return None
        comando = (a.get("comando") or "").lower()
    for nome, caminho in _CAMINHOS_PROGRESSO:
        if nome in comando and caminho.exists():
            try:
                return json.loads(caminho.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


def iniciar(comando: list[str], nome: str = "", cwd: str | None = None,
            resultado_path: str | None = None) -> dict:
    """Inicia UMA atividade (subprocesso). Respeita o GUARDIÃO antes de rodar.

    Retorna {ok, id, mensagem} — o id identifica a atividade nas demais rotas.
    """
    global _atividades
    # 1) Guardião: hardware (memória/disco/CPU) — regra de ouro do usuário
    ok, motivo = _guardiao()
    if not ok:
        return {"ok": False, "erro": motivo}

    # 2) Concorrência INTELIGENTE: máx 3 simultâneas + 1 por tipo de serviço
    ok, motivo = _concorrencia_ok(" ".join(comando))
    if not ok:
        return {"ok": False, "erro": motivo}

    # 3) Comando válido
    if not comando or not isinstance(comando, list) or not comando[0]:
        return {"ok": False, "erro": "Comando vazio."}
    cmd = list(comando)
    if cmd[0].lower() in ("python", "python3"):
        cmd[0] = sys.executable
        # -u (unbuffered): o SSE recebe as linhas em TEMPO REAL (streaming),
        # senão o stdout fica em buffer e o painel mostra "(sem saída ainda)".
        # Regra de ouro 05/08: o usuário precisa VER acontecendo.
        cmd.insert(1, "-u")

    aid = f"atv-{datetime.now().strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"
    with _lock:
        # Teto de atividades registradas (limpa as concluídas mais velhas)
        if len(_atividades) >= MAX_ATIVIDADES:
            for old in sorted(_atividades, key=lambda x: _atividades[x].get("inicio") or ""):
                if _atividades[old].get("status") not in ("rodando", "rodando_externo"):
                    del _atividades[old]
                    if len(_atividades) < MAX_ATIVIDADES:
                        break
        _atividades[aid] = {
            "id": aid, "nome": nome or os.path.basename(cmd[0]),
            "comando": " ".join(cmd), "cwd": cwd or str(PROJETO_ROOT),
            "comando_lista": list(cmd),  # args EXATOS p/ re-spawnar (não re-divisar string)
            "status": "rodando", "rodando": True, "pid": None,
            "inicio": datetime.now().isoformat(), "fim": None,
            "exit_code": None, "erro": None, "mensagens": [],
            "resultado": None, "resultado_path": resultado_path,
            "reinicios": 0, "_processo": None,
        }
        _persistir()
    _log_linha(f">>> [{aid}] {nome or ''}: {' '.join(cmd)}")

    try:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        # Windows: grupo de processo próprio — sobrevive ao reload do uvicorn
        # e ao taskkill /T do watchdog (regra 13/08: rodar em paralelo).
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(cmd, cwd=_atividades[aid]["cwd"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace",
                                env=env, bufsize=1, creationflags=flags)
        with _lock:
            _atividades[aid]["pid"] = proc.pid
            _atividades[aid]["_processo"] = proc
            _persistir()
        threading.Thread(target=_ler_saida, args=(aid, proc), daemon=True).start()
        threading.Thread(target=_ler_stderr, args=(aid, proc), daemon=True).start()
        threading.Thread(target=_monitorar_fim, args=(aid, proc), daemon=True).start()
        return {"ok": True, "id": aid,
                "mensagem": f"Atividade iniciada: {nome or aid} (PID {proc.pid}).",
                "pid": proc.pid}
    except Exception as e:
        with _lock:
            a = _atividades.get(aid)
            if a:
                a["status"] = "erro"
                a["rodando"] = False
                a["erro"] = f"Falha ao iniciar: {e}"
                a["_processo"] = None
                _persistir()
        _log_linha(f"ERRO [{aid}]: {e}")
        return {"ok": False, "id": aid, "erro": str(e)}


def parar(aid: str = "") -> dict:
    """Para uma atividade (taskkill no Windows). Se aid vazio, para TODAS."""
    with _lock:
        if aid:
            alvos = {aid: _atividades.get(aid)}
        else:
            alvos = {k: v for k, v in _atividades.items()
                     if v.get("_processo") is not None or v.get("status") == "rodando"}
    if not alvos:
        return {"ok": False, "erro": "Nenhuma atividade em execução."}

    resultados = []
    for a_id, a in alvos.items():
        if not a:
            resultados.append({"id": a_id, "ok": False, "erro": "não encontrada"})
            continue
        proc = a.get("_processo")
        pid = a.get("pid")
        try:
            if proc is not None and proc.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   capture_output=True, timeout=30)
                else:
                    proc.terminate()
                resultados.append({"id": a_id, "ok": True, "mensagem": "parada solicitada"})
            elif pid:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                                   capture_output=True, timeout=30)
                resultados.append({"id": a_id, "ok": True, "mensagem": "parada (órfão)"})
            else:
                if a.get("status") == "aguardando":
                    # Abandonar: para de pedir confirmação e marca interrompido
                    with _lock:
                        a["status"] = "interrompido"
                        a["rodando"] = False
                        a["aguardando_continuar"] = False
                        a["pid"] = None
                        a["_processo"] = None
                        _persistir()
                    resultados.append({"id": a_id, "ok": True,
                                       "mensagem": "abandonada (sem mais reinícios)"})
                else:
                    resultados.append({"id": a_id, "ok": False, "erro": "sem processo"})
        except Exception as e:
            resultados.append({"id": a_id, "ok": False, "erro": str(e)})
    _log_linha(f"⏹️ Parada solicitada para {len(resultados)} atividade(s).")
    return {"ok": True, "resultados": resultados}


# ============================================================================
# ORIGENS — dropdown automático (o usuário NÃO digita caminho no celular)
# ============================================================================
def _carregar_historico_sanitizacao() -> list[dict]:
    """Carrega logs/sanitizacao_historico.json (origens já sanitizadas).

    Prevê: arquivo inexistente (lista vazia), JSON corrompido (recomeça).
    """
    try:
        caminho = PROJETO_ROOT / "logs" / "sanitizacao_historico.json"
        if not caminho.exists():
            return []
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if not isinstance(dados, list):
            return []
        return [d for d in dados if isinstance(d, dict)]
    except Exception:
        return []


def _agrupar_jsonl_por_pasta(pastas: list[Path]) -> list[dict]:
    """Agrupa os .jsonl encontrados por pasta-pai → itens do dropdown.

    Cada item: {nome, caminho, tipo: 'pasta'|'arquivo', arquivos, sanitizado,
    completo, parcial, gravados, gerado_em}. Apenas pastas/arquivos com
    .jsonl aparecem (dropdown limpo, sem opção vazia).
    """
    agrupados: dict[str, dict] = {}
    for p in pastas:
        if not p.exists():
            continue
        pai = p.parent
        chave = str(pai)
        if chave not in agrupados:
            rel = pai.relative_to(PROJETO_ROOT)
            agrupados[chave] = {
                "nome": pai.name or str(rel),
                "caminho": str(rel).replace("\\", "/"),
                "tipo": "pasta",
                "arquivos": 0,
            }
        agrupados[chave]["arquivos"] += 1

    # Arquivos .jsonl soltos na raiz de dados/ também contam como item
    for p in pastas:
        if p.parent == PROJETO_ROOT / "dados":
            rel = p.relative_to(PROJETO_ROOT)
            agrupados[str(p)] = {
                "nome": p.name,
                "caminho": str(rel).replace("\\", "/"),
                "tipo": "arquivo",
                "arquivos": 1,
            }
    for it in agrupados.values():
        it.setdefault("formatos", ["jsonl"])
    return list(agrupados.values())


def _contar_arquivos(c: Path, exts: tuple, limite: int = 1500,
                     prof_max: int = 1, tempo_max: float = 6.0) -> int:
    """Conta arquivos das extensões até a profundidade prof_max.
    Para CEDO ao atingir o limite OU o orçamento de tempo — nunca varre a
    árvore inteira nem trava o painel (regras 05/08)."""
    n = 0
    fim = time.time() + tempo_max
    try:
        base_s = str(c)
        for raiz, dirs, files in os.walk(c):
            if time.time() > fim:
                return n
            prof = raiz[len(base_s):].count(os.sep)
            if prof >= prof_max:
                dirs[:] = []
                continue
            for f in files:
                if f.lower().endswith(exts):
                    n += 1
                    if n >= limite:
                        return n
    except Exception:
        pass
    return n


def _itens_txt(tempo_max: float = 6.0) -> list[dict]:
    """Pastas com .txt — RASO (nível 1 de gerados/processed) e LIMITADO."""
    itens = []
    vistos = set()
    for base in (PROJETO_ROOT / "dados" / "gerados",
                 PROJETO_ROOT / "dados" / "processed"):
        if not base.exists():
            continue
        try:
            subdirs = [d for d in base.iterdir() if d.is_dir()]
        except Exception:
            continue
        for d in subdirs:
            nome = (d.name or "").lower()
            if nome.startswith("_") or nome in ("jsonl", "parquet", "estado",
                                                 "logs", "raw", "celular",
                                                 "descartados", "arquivo",
                                                 "massa_final", "gerados_local"):
                continue
            chave = str(d).lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            n = _contar_arquivos(d, (".txt",), limite=1500, prof_max=1,
                                 tempo_max=tempo_max)
            if n == 0:
                continue
            rel = d.relative_to(PROJETO_ROOT)
            itens.append({
                "nome": d.name, "caminho": str(rel).replace("\\", "/"),
                "tipo": "pasta", "arquivos": n, "formatos": ["txt"],
                "sanitizado": False, "parcial": False,
            })
    return itens


def _itens_parquet(tempo_max: float = 6.0) -> list[dict]:
    """Pastas com .parquet — RASO (nível 1 de processed/raw) e LIMITADO."""
    itens = []
    vistos = set()
    for base in (PROJETO_ROOT / "dados" / "processed",
                 PROJETO_ROOT / "dados" / "raw"):
        if not base.exists():
            continue
        try:
            subdirs = [d for d in base.iterdir() if d.is_dir()]
        except Exception:
            continue
        for d in subdirs:
            chave = str(d).lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            n = _contar_arquivos(d, (".parquet",), limite=1500, prof_max=1,
                                 tempo_max=tempo_max)
            if n == 0:
                continue
            rel = d.relative_to(PROJETO_ROOT)
            itens.append({
                "nome": d.name, "caminho": str(rel).replace("\\", "/"),
                "tipo": "pasta", "arquivos": n, "formatos": ["parquet"],
                "sanitizado": False, "parcial": False,
            })
    return itens


def listar_origens() -> dict:
    """Lista origens de sanitização disponíveis + flag de já feito.

    Usado pelo dropdown do painel /executor: o usuário NÃO digita o caminho
    (regra 05/08 — celular, TV); escolhe numa lista. O que já foi sanitizado
    ganha 'sanitizado': True e pode ser desabilitado (flag ✅).
    """
    try:
        historico = _carregar_historico_sanitizacao()
        feitas: dict[str, dict] = {}
        for h in historico:
            chave = os.path.abspath(h.get("origem", ""))
            feitas[chave] = h

        # Varredura LIMITADA (não é scan pesado): só pastas com .jsonl
        # Fonte: onde os datasets ficam — processed (promovido), gerados/jsonl
        # (explosão deposita AQUI), raw (baixado), e dados/ (raiz, arquivos soltos)
        pastas: list[Path] = []
        alvos = [
            PROJETO_ROOT / "dados" / "processed" / "jsonl",
            PROJETO_ROOT / "dados" / "gerados" / "jsonl",
            PROJETO_ROOT / "dados" / "raw",
        ]
        fim_orcamento = time.time() + 6.0   # 🛡️ orçamento: nunca travar o painel
        for base in alvos:
            if not base.exists():
                continue
            try:
                for p in base.glob("**/*.jsonl"):
                    if time.time() > fim_orcamento:
                        break
                    pastas.append(p)
                    if len(pastas) >= 2500:   # cap de segurança (dropdown)
                        break
            except Exception:
                continue
            if len(pastas) >= 2500 or time.time() > fim_orcamento:
                break
        # Arquivos .jsonl soltos na raiz de dados/
        try:
            for p in (PROJETO_ROOT / "dados").glob("*.jsonl"):
                pastas.append(p)
        except Exception:
            pass

        itens = _agrupar_jsonl_por_pasta(pastas)
        for it in itens:
            caminho_abs = os.path.abspath(PROJETO_ROOT / it["caminho"].replace("/", os.sep))
            h = feitas.get(caminho_abs)
            it["sanitizado"] = bool(h and h.get("completo"))
            it["parcial"] = bool(h and not h.get("completo"))
            it["gravados"] = h.get("gravados") if h else None
            it["gerado_em"] = h.get("gerado_em") if h else None
            it["total_arquivos"] = h.get("total_arquivos") if h else None
            it["arquivos_processados"] = h.get("arquivos_processados") if h else None

        # 🆕 Origens universais: TXT e PARQUET (qualificação vale p/ qualquer
        # formato — regra 14/08). Raso, limitado e com orçamento de tempo.
        restante = max(0.5, fim_orcamento - time.time())
        itens += _itens_txt(tempo_max=restante)
        restante = max(0.5, fim_orcamento - time.time())
        itens += _itens_parquet(tempo_max=restante)

        # Cap de segurança (dropdown não explode) — prioriza pendentes
        itens.sort(key=lambda it: (0 if not it.get("sanitizado") else 1,
                                   it["nome"].lower()))
        itens = itens[:500]

        return {
            "ok": True,
            "total": len(itens),
            "pendentes": sum(1 for i in itens if not i["sanitizado"] and not i["parcial"]),
            "parciais": sum(1 for i in itens if i["parcial"]),
            "concluidas": sum(1 for i in itens if i["sanitizado"]),
            "origens": itens,
        }
    except Exception as e:
        _log_linha(f"Erro ao listar origens: {e}")
        return {"ok": False, "erro": str(e), "origens": []}

