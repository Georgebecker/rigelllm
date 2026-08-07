#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
converter_txt.py - Serviço de conversão TXT → JSONL (SFT messages).
Versão: 1.0.0 | Data: 06/08/2026

- Roda `converter_txt_jsonl.py` (raiz) em um SUBPROCESSO — sobrevive ao
  --reload do uvicorn e isola a conversão do processo do dashboard.
- Captura a saída do conversor em tempo real (progresso por arquivo).
- Lista pastas com .txt disponíveis para conversão (com limites, sem
  martelar o SSD — mesmo guardião do treino).
- Saída: dados/gerados/jsonl/<saida>/  (aparece no Treino/JSONL em seguida;
  pode ser promovido para dados/processed depois de validado).

⚠️ REGRA: conversão NÃO pode rodar junto com um treino de modelo — os dois
escrevem em dados/ e disputam CPU. O frontend consulta o lock global
(dashboard.services.treino_global) antes de iniciar.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from dashboard.services.estrutura_cache import (
    walk_com_limites, LimiteEstourado, memoria_ok,
    SCAN_MAX_ARQUIVOS,
)

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))

CONVERTER_SCRIPT = PROJETO_ROOT / "converter_txt_jsonl.py"
DESTINO_BASE = PROJETO_ROOT / "dados" / "gerados" / "jsonl"

# Bases onde procuramos .txt para converter (processed = textos tratados;
# raw = downloads crus). A ordem define preferência de exibição.
BASES_TXT = [
    ("processed", PROJETO_ROOT / "dados" / "processed"),
    ("raw", PROJETO_ROOT / "dados" / "raw"),
]

MAX_MENSAGENS = 400
MAX_ERROS_STDERR = 50

# Estado global (thread-safe) da conversão
_estado: dict = {
    "rodando": False,
    "pid": None,
    "pasta": None,
    "saida": None,
    "etapa": "idle",        # idle | convertendo | concluido | erro
    "mensagem": "",
    "inicio": None,
    "fim": None,
    "erro": None,
    "mensagens": [],
    "resultado": None,
}
_lock = threading.Lock()
_processo: subprocess.Popen | None = None
_leitor: threading.Thread | None = None
_drenador: threading.Thread | None = None
_parada_solicitada = False


def _atualizar_estado(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)


def get_estado() -> dict:
    with _lock:
        est = dict(_estado)
        est["mensagens"] = list(est["mensagens"])
    return est


# ============================================================================
# LISTAGEM DE PASTAS TXT (com guardião de limites)
# ============================================================================

def _contar_txt(pasta: Path) -> int:
    """Conta .txt recursivamente com limites (nunca materializa listas)."""
    qtde = 0
    try:
        for _c in walk_com_limites(pasta, extensoes=(".txt",)):
            qtde += 1
            if qtde >= SCAN_MAX_ARQUIVOS:
                break
    except LimiteEstourado:
        return SCAN_MAX_ARQUIVOS
    return qtde


def _tamanho_txt(pasta: Path) -> int:
    """Tamanho total (MB) dos .txt da pasta, com cap de arquivos lidos."""
    total = 0
    n = 0
    try:
        for c in walk_com_limites(pasta, extensoes=(".txt",)):
            try:
                total += Path(c).stat().st_size
            except Exception:
                pass
            n += 1
            if n >= 2000:  # amostra (não martela o SSD)
                break
    except LimiteEstourado:
        pass
    return round(total / 1e6, 1)


def listar_pastas_txt() -> list[dict]:
    """Pastas com .txt disponíveis para conversão.

    RÁPIDO: usa o CACHE persistente do escaneador_txt (mesmo da página de
    Treinamento) — nunca varre milhões de arquivos no request. Se não houver
    cache válido, devolve [] e dispara o scan em background (o front consulta
    o status e recarrega quando terminar).
    """
    try:
        from dashboard.services.estrutura_cache import escaneador_txt
        cache = escaneador_txt.carregar_cache()
        if cache and cache.get("resultado"):
            itens = []
            for p in cache["resultado"]:
                nome = p.get("nome", "")
                itens.append({
                    "nome": nome,
                    "caminho": f"dados/processed/{nome}",
                    "base": "processed",
                    "arquivos": p.get("arquivos", 0),
                    "tamanho_mb": None,
                })
            itens.sort(key=lambda x: x["arquivos"], reverse=True)
            return itens
    except Exception:
        pass
    # Sem cache: inicia o escaneamento em background (barra de % no front).
    try:
        from dashboard.services.estrutura_cache import escaneador_txt
        if not escaneador_txt.status().get("rodando"):
            from dashboard.routes.train import _scan_estrutura_txt
            escaneador_txt.iniciar(_scan_estrutura_txt, descricao="Pastas TXT")
    except Exception:
        pass
    return []


def status_scan_txt() -> dict:
    """Status do escaneamento de pastas TXT (para a barra de % no front)."""
    try:
        from dashboard.services.estrutura_cache import escaneador_txt
        return escaneador_txt.status()
    except Exception:
        return {"rodando": False}


# ============================================================================
# EXECUÇÃO DA CONVERSÃO (subprocesso)
# ============================================================================

def _ler_saida(proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for linha in proc.stdout:
        linha = linha.rstrip("\n")
        if not linha.strip():
            continue
        with _lock:
            _estado["mensagens"].append(linha)
            if len(_estado["mensagens"]) > MAX_MENSAGENS:
                _estado["mensagens"] = _estado["mensagens"][-MAX_MENSAGENS:]
            _estado["mensagem"] = linha


def _drenar_stderr(proc: subprocess.Popen) -> None:
    erros: list[str] = []
    assert proc.stderr is not None
    for linha in proc.stderr:
        linha = linha.rstrip("\n")
        if not linha.strip():
            continue
        erros.append(linha)
        if len(erros) > MAX_ERROS_STDERR:
            erros = erros[-MAX_ERROS_STDERR:]
    if erros:
        with _lock:
            _estado["erro_detalhe"] = "\n".join(erros[-10:])


def _monitorar_fim(proc: subprocess.Popen) -> None:
    global _processo, _leitor, _drenador, _parada_solicitada
    codigo = proc.wait()
    with _lock:
        _estado["rodando"] = False
        _estado["pid"] = None
        _processo = None
        _leitor = None
        _drenador = None
        _estado["fim"] = datetime.now().isoformat()
        parada = _parada_solicitada
        _parada_solicitada = False
        if parada:
            _estado["etapa"] = "parado"
            _estado["mensagem"] = "⏹️ Conversão parada pelo usuário."
            _estado["mensagens"].append(_estado["mensagem"])
        elif codigo == 0:
            _estado["etapa"] = "concluido"
            _estado["mensagem"] = "✅ Conversão concluída! Dataset em dados/gerados/jsonl."
            _estado["mensagens"].append(_estado["mensagem"])
        else:
            detalhe = _estado.get("erro_detalhe", "")
            _estado["etapa"] = "erro"
            _estado["erro"] = f"Conversão terminou com código {codigo}"
            _estado["mensagem"] = f"❌ Conversão falhou (código {codigo})."
            if detalhe:
                _estado["mensagem"] += f"\n{detalhe}"
            _estado["mensagens"].append(_estado["mensagem"])


def _proximo_nome_rigeljsonl() -> str:
    """Próximo nome sequencial da convenção Rigel: rigeljsonl1, rigeljsonl2, ..."""
    try:
        import re
        if not DESTINO_BASE.exists():
            return "rigeljsonl1"
        maior = 0
        for p in DESTINO_BASE.iterdir():
            if p.is_dir():
                m = re.match(r"^rigeljsonl(\d+)$", p.name)
                if m:
                    maior = max(maior, int(m.group(1)))
        return f"rigeljsonl{maior + 1}"
    except Exception:
        return "rigeljsonl1"


def iniciar_conversao(pasta: str, saida: str | None = None,
                      max_exemplos: int | None = None,
                      max_arquivos: int | None = None,
                      apenas_qna: bool = False) -> dict:
    """Inicia a conversão TXT → JSONL em subprocesso."""
    global _processo, _leitor, _drenador

    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe uma conversão em andamento."}

    # Resolve a pasta (caminho direto ou nome em uma das bases)
    pasta_path = Path(pasta)
    if not pasta_path.is_dir():
        cand = None
        for _rotulo, base in BASES_TXT:
            c = base / pasta
            if c.is_dir():
                cand = c
                break
        if cand is None:
            return {"ok": False, "erro": f"Pasta '{pasta}' não encontrada."}
        pasta_path = cand

    if not _contar_txt(pasta_path):
        return {"ok": False, "erro": f"Nenhum .txt em '{pasta_path}'."}

    saida_efetiva = (saida or "").strip() or _proximo_nome_rigeljsonl()
    # Segurança: saída nunca sai de dados/gerados/jsonl (evita sobrescrever processado)
    destino = DESTINO_BASE / saida_efetiva
    if destino.exists():
        return {"ok": False,
                "erro": f"Já existe o dataset '{saida_efetiva}' em dados/gerados/jsonl/. "
                        "Escolha outro nome ou remova o antigo."}

    comando = [sys.executable, "-u", str(CONVERTER_SCRIPT),
               "--pasta", str(pasta_path),
               "--saida", saida_efetiva,
               "--exemplos-por-arquivo", "1000"]
    if max_exemplos and max_exemplos > 0:
        comando += ["--max-exemplos", str(max_exemplos)]
    if max_arquivos and max_arquivos > 0:
        comando += ["--max-arquivos", str(max_arquivos)]
    if apenas_qna:
        comando += ["--apenas-qna"]

    _atualizar_estado(
        rodando=True, pid=None, pasta=str(pasta_path), saida=saida_efetiva,
        etapa="convertendo", mensagem="Iniciando conversão...",
        inicio=datetime.now().isoformat(), fim=None, erro=None,
        mensagens=[], resultado=None, erro_detalhe="",
    )

    try:
        proc = subprocess.Popen(
            comando,
            cwd=str(PROJETO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        _atualizar_estado(rodando=False, etapa="erro", erro=str(e),
                          mensagem=f"❌ Falha ao iniciar conversão: {e}")
        return {"ok": False, "erro": str(e)}

    _processo = proc
    _atualizar_estado(pid=proc.pid)
    _leitor = threading.Thread(target=_ler_saida, args=(proc,), daemon=True)
    _leitor.start()
    _drenador = threading.Thread(target=_drenar_stderr, args=(proc,), daemon=True)
    _drenador.start()
    threading.Thread(target=_monitorar_fim, args=(proc,), daemon=True).start()

    return {"ok": True,
            "mensagem": f"Conversão iniciada: {pasta_path.name} → {saida_efetiva}",
            "saida": saida_efetiva}


def parar_conversao() -> dict:
    """Para a conversão em andamento (mata o subprocesso)."""
    global _processo, _parada_solicitada
    with _lock:
        proc = _processo
        _parada_solicitada = True
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            import time as _t
            _t.sleep(1)
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        return {"ok": True, "mensagem": "Conversão interrompida."}
    return {"ok": False, "mensagem": "Nenhuma conversão em andamento."}
