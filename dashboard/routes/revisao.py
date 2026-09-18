#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
revisao.py - Rotas da página de revisão dos suspeitos (/revisar).

  GET  /api/revisao/suspeitos           - lista suspeitos por pasta
  GET  /api/revisao/conteudo            - conteúdo de um arquivo (?pasta=&arquivo=)
  POST /api/revisao/aprovar             - aprova um suspeito (vai pro treino)
  POST /api/revisao/descartar           - descarta um suspeito (arquiva fora)
  POST /api/revisao/juizar              - inicia o juiz nos suspeitos (deepseek)
  GET  /api/revisao/juizar/progresso    - progresso do juiz (barra %)

Página: /revisar (template revisar.html)
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.services import revisao
from dashboard.services import sanitizar_suspeitos as ss
from dashboard.services import transformar as tx

router = APIRouter(prefix="/api/revisao", tags=["Revisão de suspeitos"])

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
PROGRESSO = PROJETO_ROOT / "logs" / "juiz_progresso.json"
_SAN_PROGRESSO = PROJETO_ROOT / "logs" / "sanitizar_progresso.json"
_TRANSF_PROGRESSO = PROJETO_ROOT / "logs" / "transformar_progresso.json"
_JUIZ_PROC = {"proc": None}
_SANITIZAR = {"thread": None}
_TRANSFORMAR = {"thread": None}


def _verificar_fatos_texto(texto: str) -> dict:
    """Roda a verificação de fatos com busca na internet (scripts/verificar_fatos.py)."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(PROJETO_ROOT / "scripts"))
        import verificar_fatos as vf
        return vf.verificar_fatos(texto)
    except Exception as e:
        return {"ok": False, "veredito_geral": "erro", "motivo": str(e),
                "afirmacoes": []}


def _python() -> str:
    p = PROJETO_ROOT / ".venv" / "Scripts" / "python.exe"
    return str(p) if p.exists() else "python"


@router.get("/suspeitos")
async def suspeitos():
    """Lista os textos marcados como suspeitos, agrupados por pasta."""
    return JSONResponse(revisao.listar_suspeitos())


@router.get("/conteudo")
async def conteudo(pasta: str = "", arquivo: str = ""):
    """Lê o conteúdo de um arquivo suspeito (para o usuário ler e decidir)."""
    pasta_p = revisao._resolver_pasta(pasta)
    if not pasta_p:
        return JSONResponse({"ok": False, "erro": "Pasta não encontrada."})
    arq = revisao._localizar_arquivo(pasta_p, arquivo)
    if not arq:
        return JSONResponse({"ok": False, "erro": "Arquivo não encontrado."})
    return JSONResponse(revisao._conteudo_arquivo(str(arq)))


@router.post("/aprovar")
async def aprovar(body: dict):
    """✅ Aprova um suspeito → vai para o treino."""
    pasta = (body or {}).get("pasta", "")
    arquivo = (body or {}).get("arquivo", "")
    return JSONResponse(revisao.aprovar(pasta, arquivo))


@router.post("/descartar")
async def descartar(body: dict):
    """❌ Descarta um suspeito → arquiva fora do treino (não apaga)."""
    pasta = (body or {}).get("pasta", "")
    arquivo = (body or {}).get("arquivo", "")
    return JSONResponse(revisao.descartar(pasta, arquivo))


@router.post("/aprovar-todos")
async def aprovar_todos():
    """✅ Aprova TODOS os suspeitos pendentes de uma vez (com confirmação na
    UI). Cada um vai para o treino — NÃO passam pelo juiz."""
    return JSONResponse(revisao.aprovar_todos())


# ============================================================================
# 🔄 TRANSFORMAR TUDO (TXT → JSONL → PARQUET)
# ============================================================================
def _iniciar_transformacao(fn):
    t = _TRANSFORMAR["thread"]
    if t is not None and t.is_alive():
        return JSONResponse({"ok": False, "erro": "Já há uma transformação rodando. Aguarde."})

    def _rodar():
        try:
            fn()
        except Exception:
            pass
        finally:
            _TRANSFORMAR["thread"] = None

    th = threading.Thread(target=_rodar, daemon=True)
    _TRANSFORMAR["thread"] = th
    th.start()
    return JSONResponse({"ok": True})


@router.post("/transformar/jsonl")
async def transformar_jsonl():
    """🔄 TXT aprovados → JSONL SFT em processed/JSONL/rigel<data_hora>."""
    return _iniciar_transformacao(tx.converter_tudo_jsonl)


@router.post("/transformar/parquet")
async def transformar_parquet():
    """🗃️ JSONL → .parquet em processed/PARQUET/rigel<data_hora>."""
    return _iniciar_transformacao(tx.converter_tudo_parquet)


@router.get("/transformar/progresso")
async def transformar_progresso():
    """Progresso da transformação (polling)."""
    try:
        if _TRANSF_PROGRESSO.exists():
            d = json.loads(_TRANSF_PROGRESSO.read_text(encoding="utf-8"))
        else:
            d = {}
    except Exception:
        d = {}
    t = _TRANSFORMAR["thread"]
    d["rodando"] = bool(t is not None and t.is_alive())
    if not d.get("rodando") and d.get("fim") is None and d.get("pct"):
        d["fim"] = True
    return JSONResponse(d)


@router.post("/juizar")
async def juizar(body: dict | None = None):
    """⚖️ Inicia o juiz (deepseek-r1:7b) nos suspeitos pendentes.

    Roda em PROCESSO independente (sobrevive ao --reload do uvicorn).
    Os aprovados sobem para o treino; os lixo são arquivados; o que o juiz
    confirmar como suspeito fica para revisão humana.
    """
    if _JUIZ_PROC["proc"] is not None:
        p = _JUIZ_PROC["proc"]
        if p.poll() is None:
            return JSONResponse({"ok": False,
                                 "erro": "O juiz já está rodando. Aguarde."})
        _JUIZ_PROC["proc"] = None

    pasta = (body or {}).get("pasta", "") if body else ""
    cmd = [_python(), "-u", str(PROJETO_ROOT / "scripts" / "juizar_suspeitos.py"),
           "--seco"]
    if pasta:
        cmd += ["--pasta", pasta]
    try:
        proc = subprocess.Popen(cmd, cwd=str(PROJETO_ROOT),
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=subprocess.CREATE_NO_WINDOW
                                if sys.platform == "win32" else 0)
        _JUIZ_PROC["proc"] = proc
        return JSONResponse({"ok": True,
                             "mensagem": "⚖️ Juiz iniciado! Ele vai revisar os "
                                         "suspeitos um por um (demora em CPU).",
                             "pid": proc.pid})
    except Exception as e:
        return JSONResponse({"ok": False, "erro": str(e)})


@router.get("/verificar")
async def verificar(pasta: str = "", arquivo: str = ""):
    """🔎 Verifica os FATOS de um texto com busca na internet (DuckDuckGo).

    Lê o arquivo, extrai as afirmações factuais (números/datas/nomes) e
    busca cada uma na web. Veredito: ✅ confirmado | ⚠️ não encontrado |
    ❌ contradito. Ajuda a pegar "resposta fake" (invenção do modelo).
    """
    pasta_p = revisao._resolver_pasta(pasta)
    if not pasta_p:
        return JSONResponse({"ok": False, "erro": "Pasta não encontrada."})
    arq = revisao._localizar_arquivo(pasta_p, arquivo)
    if not arq:
        return JSONResponse({"ok": False, "erro": "Arquivo não encontrado."})
    try:
        texto = arq.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return JSONResponse({"ok": False, "erro": f"Não consegui ler o arquivo: {e}"})
    # busca na internet pode demorar — roda em thread (não bloqueia o servidor)
    import asyncio
    resultado = await asyncio.to_thread(_verificar_fatos_texto, texto)
    resultado["arquivo"] = arquivo
    resultado["pasta"] = pasta
    return JSONResponse(resultado)


@router.get("/juizar/progresso")
async def juizar_progresso():
    """Progresso do juiz (a página faz polling e mostra a barra)."""
    try:
        if PROGRESSO.exists():
            d = json.loads(PROGRESSO.read_text(encoding="utf-8"))
        else:
            d = {}
    except Exception:
        d = {}
    proc = _JUIZ_PROC["proc"]
    rodando = False
    if proc is not None and proc.poll() is None:
        rodando = True
    # também detecta processo vivo pelo PID (sobrevive a reload do uvicorn)
    if not rodando:
        pid = d.get("pid") or (proc.pid if proc is not None else None)
        if pid:
            try:
                import psutil
                rodando = psutil.pid_exists(int(pid))
            except Exception:
                rodando = False
    d["rodando"] = rodando
    d["pausado"] = bool(ss.controle().get("pausado"))
    return JSONResponse(d)


# ============================================================================
# 🧹 SANITIZAR TUDO (todas as ferramentas antes do juiz)
# ============================================================================
@router.post("/sanitizar")
async def sanitizar():
    """🧹 Roda TODAS as ferramentas de limpeza (ANSI, mojibake, ABNT, espaços,
    emojis) nos suspeitos pendentes. Limpa cada arquivo no lugar — o juiz e o
    painel passam a ver texto limpo. Roda em thread (não bloqueia o servidor)."""
    t = _SANITIZAR["thread"]
    if t is not None and t.is_alive():
        return JSONResponse({"ok": False,
                             "erro": "A limpeza já está rodando. Aguarde."})
    ss.set_controle(pausado=False, parar=False)

    def _rodar():
        try:
            ss.sanitizar_pendentes()
        except Exception:
            pass
        finally:
            _SANITIZAR["thread"] = None

    th = threading.Thread(target=_rodar, daemon=True)
    _SANITIZAR["thread"] = th
    th.start()
    return JSONResponse({"ok": True,
                         "mensagem": "🧹 Limpeza iniciada! Aplicando todas as "
                                     "ferramentas nos textos pendentes..."})


@router.get("/sanitizar/progresso")
async def sanitizar_progresso():
    """Progresso da limpeza (a página faz polling e mostra a barra)."""
    try:
        if _SAN_PROGRESSO.exists():
            d = json.loads(_SAN_PROGRESSO.read_text(encoding="utf-8"))
        else:
            d = {}
    except Exception:
        d = {}
    t = _SANITIZAR["thread"]
    d["rodando"] = bool(t is not None and t.is_alive())
    if not d.get("rodando") and d.get("fim") is None and d.get("pct"):
        d["fim"] = True
    return JSONResponse(d)


# ============================================================================
# ⏸️ ▶️ ⏹️ CONTROLE DO JUIZ (pausar / retomar / parar)
# ============================================================================
@router.post("/juizar/pausar")
async def juizar_pausar():
    """⏸️ Pausa o juiz (ele continua de onde parou ao retomar)."""
    ss.set_controle(pausado=True, parar=False)
    return JSONResponse({"ok": True,
                         "mensagem": "⏸️ Juiz pausado. Use Retomar para continuar."})


@router.post("/juizar/retomar")
async def juizar_retomar():
    """▶️ Retoma o juiz pausado."""
    ss.set_controle(pausado=False, parar=False)
    return JSONResponse({"ok": True,
                         "mensagem": "▶️ Juiz retomado!"})


@router.post("/juizar/parar")
async def juizar_parar():
    """⏹️ Para o juiz agora (o que já foi feito fica salvo).
    Sinaliza parada (parada limpa entre itens) e encerra o processo se vivo."""
    ss.set_controle(parar=True, pausado=False)
    try:
        import psutil
        # encerra o processo do juiz (se ainda vivo) para parar rápido
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cl = " ".join(proc.info.get("cmdline") or [])
            if "juizar_suspeitos" in cl:
                try:
                    proc.terminate()
                except Exception:
                    pass
        pid = None
        try:
            if PROGRESSO.exists():
                pid = json.loads(PROGRESSO.read_text(encoding="utf-8")).get("pid")
        except Exception:
            pid = None
        if pid:
            try:
                psutil.Process(int(pid)).terminate()
            except Exception:
                pass
    except Exception:
        pass
    return JSONResponse({"ok": True,
                         "mensagem": "⏹️ Parando o juiz... (o que já foi feito fica salvo)"})
