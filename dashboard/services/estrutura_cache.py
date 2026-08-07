#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
estrutura_cache.py - Cache de estrutura de dados + escaneamento em background.
Versão: 1.0.0 | Data: 02/08/2026

Problema resolvido:
  As abas de treino (Treino Local, Treinamento) escaneavam TUDO a cada carga
  (rglob recursivo em milhares de arquivos/pastas) — a página ficava travada
  no spinner por dezenas de segundos.

Solução:
  - Um escaneador roda em THREAD (não bloqueia o servidor).
  - A cada N itens, grava o PROGRESSO em memória (percentual, pasta atual,
    arquivos encontrados) para o frontend fazer barra de progresso.
  - Ao terminar, salva um CACHE PERSISTENTE em disco (JSON) com timestamp.
  - Ao abrir a tela, o frontend carrega IMEDIATAMENTE o último cache válido.
  - O botão "Ler estrutura" dispara um novo escaneamento com barra de %.

Uso típico (servidor):
    from dashboard.services.estrutura_cache import EscaneadorEstrutura

    esc = EscaneadorEstrutura("estrutura_jsonl")   # nome do cache (sem extensão)
    esc.iniciar(fn_scan)            # roda em thread; fn_scan(report) faz o scan
    esc.status()                    # {'rodando', 'percentual', 'fase', ...}
    esc.carregar_cache()            # dados do último scan (rápido, do disco)
"""
from __future__ import annotations

import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# ============================================================================
# GUARDIÃO DE LIMITES (regra do usuário: SEMPRE ter limites; hardware varia;
# nada de "mostrar tudo"; nunca carregar/indexar tudo em memória).
#
# Os limites vêm de dashboard/services/recursos.py, que calcula valores
# PROPORCIONAIS à máquina (RAM, CPU, GPU, disco SSD/NVMe/HDD) na instalação
# (setup_env.py → config_recursos.json). Precedência:
#   config_recursos.json < variáveis de ambiente < cálculo em runtime.
# ============================================================================
try:
    from dashboard.services.recursos import carregar_limites as _carregar_limites
    _LIM = _carregar_limites()
except Exception:
    _LIM = {}  # nunca quebra o servidor se o módulo falhar

SCAN_MAX_ARQUIVOS   = int(_LIM.get("SCAN_MAX_ARQUIVOS", 2000000))   # cap de arquivos visitados por scan
SCAN_MAX_DIRETORIOS = int(_LIM.get("SCAN_MAX_DIRETORIOS", 200000))  # cap de diretórios visitados por scan
SCAN_PAUSA_CADA     = int(_LIM.get("SCAN_PAUSA_CADA", 2000))        # throttle: pausa a cada N itens
SCAN_PAUSA_SEG      = float(_LIM.get("SCAN_PAUSA_SEG", 0.002))      # duração da pausa (protege o SSD)
MEM_MIN_LIVRE_MB    = int(_LIM.get("MEM_MIN_LIVRE_MB", 1024))       # aborta scan se memória livre baixa
MEM_MIN_LIVRE_PCT   = float(_LIM.get("MEM_MIN_LIVRE_PCT", 10))      # ... ou % do total baixa
DISCO_MIN_LIVRE_MB  = int(_LIM.get("DISCO_MIN_LIVRE_MB", 1024))     # disco mínimo p/ gravar cache
CPU_MAX_USO_PCT     = float(_LIM.get("CPU_MAX_USO_PCT", 75))        # scan "respira" se CPU passar disso
MAX_NOMES_CACHE     = int(_LIM.get("SCAN_MAX_NOMES_CACHE", 2000))   # nomes guardados no cache JSONL


def _cpu_ok() -> bool:
    """True se o uso de CPU está abaixo do limite (guarda de processador)."""
    try:
        import psutil
        return psutil.cpu_percent(interval=None) < CPU_MAX_USO_PCT
    except Exception:
        return True


class LimiteEstourado(Exception):
    """Interrompe o escaneamento graciosamente quando um limite é atingido.
    O cache antigo continua valendo e o frontend mostra o motivo."""
    pass


def memoria_ok() -> tuple[bool, str]:
    """(ok, motivo). True se há memória livre suficiente para escanear.
    Usa psutil (já instalado); sem psutil, segue otimista."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        livre_mb = vm.available / (1024 * 1024)
        pct = (vm.available / vm.total) * 100 if vm.total else 100.0
        if livre_mb < MEM_MIN_LIVRE_MB or pct < MEM_MIN_LIVRE_PCT:
            return False, (f"memória livre baixa ({livre_mb/1024:.1f} GB, {pct:.0f}%)"
                           f" — limite {MEM_MIN_LIVRE_MB/1024:.0f} GB / {MEM_MIN_LIVRE_PCT:.0f}%")
        return True, ""
    except Exception:
        return True, ""


def disco_ok(caminho) -> tuple[bool, str]:
    """(ok, motivo). True se há disco livre suficiente para gravar cache."""
    try:
        uso = shutil.disk_usage(str(caminho))
        livre_mb = uso.free / (1024 * 1024)
        if livre_mb < DISCO_MIN_LIVRE_MB:
            return False, f"disco livre baixo ({livre_mb/1024:.1f} GB) — limite {DISCO_MIN_LIVRE_MB/1024:.0f} GB"
        return True, ""
    except Exception:
        return True, ""


def _eh_reparse_caminho(caminho) -> bool:
    """True se o caminho é symlink ou junction (NÃO descer — evita loops
    infinitos que derrubam memória/SSD em pastas com milhões de arquivos)."""
    try:
        if os.path.islink(caminho):
            return True
        isj = getattr(os.path, "isjunction", None)
        if callable(isj):
            return bool(isj(caminho))
        return False
    except Exception:
        return True


def walk_com_limites(raiz, extensoes=(".jsonl",), on_dir=None):
    """os.walk STREAMING com limites de segurança:

    - NÃO materializa listas (evita MemoryError com milhões de arquivos).
    - Não desce em symlinks/junctions (evita loops → memória/SSD 100%).
    - Aborta com LimiteEstourado se passar de SCAN_MAX_ARQUIVOS/DIRETORIOS
      ou se a memória livre cair abaixo do mínimo.
    - Pausa a cada SCAN_PAUSA_CADA itens (evita saturar o SSD).
    - on_dir(raiz_atual, dirs_visitados) opcional p/ progresso real.

    Gera caminhos de arquivos com extensão em `extensoes`.
    """
    arquivos_vistos = 0
    dirs_vistos = 0
    desde_pausa = 0
    for raiz_atual, dirs, arquivos in os.walk(str(raiz)):
        dirs_vistos += 1
        if dirs_vistos > SCAN_MAX_DIRETORIOS:
            raise LimiteEstourado(
                f"limite de diretórios atingido ({SCAN_MAX_DIRETORIOS}) — scan interrompido")
        # Poda subdiretórios que sejam symlink/junction (não descer)
        dirs[:] = [d for d in dirs
                   if not _eh_reparse_caminho(os.path.join(raiz_atual, d))]
        if on_dir is not None and dirs_vistos % 10 == 0:
            try:
                on_dir(raiz_atual, dirs_vistos)
            except Exception:
                pass
        for nome in arquivos:
            arquivos_vistos += 1
            desde_pausa += 1
            if arquivos_vistos > SCAN_MAX_ARQUIVOS:
                raise LimiteEstourado(
                    f"limite de arquivos atingido ({SCAN_MAX_ARQUIVOS}) — scan interrompido")
            if desde_pausa >= SCAN_PAUSA_CADA:
                desde_pausa = 0
                if SCAN_PAUSA_SEG > 0:
                    time.sleep(SCAN_PAUSA_SEG)
                if not memoria_ok()[0]:
                    raise LimiteEstourado(
                        "memória livre baixa — scan interrompido para não travar o sistema")
                if not _cpu_ok():
                    # CPU saturada (ex.: outro processo pesado): o scan respira
                    # um pouco em vez de competir pelo processador.
                    time.sleep(0.05)
            if extensoes and not nome.lower().endswith(extensoes):
                continue
            yield os.path.join(raiz_atual, nome)


_RAIZ = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = _RAIZ / "logs" / "estrutura_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class EscaneadorEstrutura:
    """Escaneia pastas em background com progresso + cache persistente em disco."""

    def __init__(self, nome: str, itens_por_passo: int = 40):
        self.nome = nome
        self.itens_por_passo = max(1, itens_por_passo)
        self._cache_path = CACHE_DIR / f"{nome}.json"
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._status = {
            "rodando": False,
            "percentual": 0,
            "fase": "idle",          # idle | iniciando | varrendo | salvando | concluido | erro
            "pasta_atual": "",
            "itens_processados": 0,
            "total_itens": 0,
            "encontrados": 0,
            "inicio": None,
            "fim": None,
            "erro": None,
            "nome": nome,
        }

    # ------------------------------------------------------------------
    # Estado / progresso
    # ------------------------------------------------------------------
    def _atualizar(self, **kwargs) -> None:
        with self._lock:
            self._status.update(kwargs)

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    # ------------------------------------------------------------------
    # Cache persistente em disco
    # ------------------------------------------------------------------
    def carregar_cache(self) -> Optional[dict]:
        """Último resultado salvo (rápido, do disco). None se não existir."""
        try:
            if self._cache_path.exists():
                dados = json.loads(self._cache_path.read_text(encoding="utf-8"))
                if isinstance(dados, dict) and "gerado_em" in dados:
                    return dados
        except Exception:
            pass
        return None

    def _salvar_cache(self, resultado) -> None:
        ok_disco, motivo = disco_ok(CACHE_DIR)
        if not ok_disco:
            self._atualizar(erro=f"cache NÃO salvo — {motivo}")
            return
        dados = {
            "gerado_em": datetime.now().isoformat(),
            "nome": self.nome,
            "resultado": resultado,
        }
        try:
            self._cache_path.write_text(
                json.dumps(dados, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            self._atualizar(erro=f"falha ao salvar cache: {e}")

    # ------------------------------------------------------------------
    # Escaneamento em background
    # ------------------------------------------------------------------
    def iniciar(self, fn_scan: Callable, descricao: str = "Estrutura") -> dict:
        """Inicia o escaneamento em thread.

        ANTES de disparar, checa a memória livre (guardião de limites): se o
        sistema já estiver sem memória, RECUSA iniciar — evita a espiral de
        pagefile/SSD a 100%.

        fn_scan(report) deve:
          - report(percentual=..., fase=..., pasta_atual=...,
                   itens_processados=..., total_itens=..., encontrados=...)
          - retornar o RESULTADO (lista/dict) a ser salvo no cache.
          - levantar LimiteEstourado se um limite de segurança for atingido.
        """
        ok, motivo = memoria_ok()
        if not ok:
            return {"ok": False,
                    "erro": f"Escaneamento NÃO iniciado — {motivo}. "
                            "Feche outros programas e tente de novo."}
        with self._lock:
            if self._status["rodando"]:
                return {"ok": False, "erro": "Já existe um escaneamento em andamento."}
            self._status.update({
                "rodando": True,
                "percentual": 0,
                "fase": "iniciando",
                "pasta_atual": "",
                "itens_processados": 0,
                "total_itens": 0,
                "encontrados": 0,
                "inicio": datetime.now().isoformat(),
                "fim": None,
                "erro": None,
                "descricao": descricao,
            })

        def _report(percentual=None, fase=None, pasta_atual=None,
                    itens_processados=None, total_itens=None, encontrados=None,
                    erro=None):
            kwargs = {}
            if percentual is not None:
                kwargs["percentual"] = round(float(percentual), 1)
            if fase is not None:
                kwargs["fase"] = fase
            if pasta_atual is not None:
                kwargs["pasta_atual"] = pasta_atual
            if itens_processados is not None:
                kwargs["itens_processados"] = itens_processados
            if total_itens is not None:
                kwargs["total_itens"] = total_itens
            if encontrados is not None:
                kwargs["encontrados"] = encontrados
            if erro is not None:
                kwargs["erro"] = erro
            self._atualizar(**kwargs)

        def _worker():
            try:
                self._atualizar(fase="varrendo")
                resultado = fn_scan(_report)
                self._atualizar(fase="salvando", percentual=100)
                self._salvar_cache(resultado)
                self._atualizar(fase="concluido", rodando=False,
                                fim=datetime.now().isoformat())
            except LimiteEstourado as e:
                # Limite de segurança atingido: interrompe SEM salvar cache
                # parcial (o cache antigo continua valendo) e avisa o front.
                self._atualizar(fase="interrompido", rodando=False, erro=str(e),
                                fim=datetime.now().isoformat())
            except Exception as e:
                self._atualizar(fase="erro", rodando=False, erro=str(e),
                                fim=datetime.now().isoformat())

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()
        return {"ok": True, "mensagem": f"Escaneamento de '{descricao}' iniciado."}


# ============================================================================
# Instâncias compartilhadas (uma por área)
# ============================================================================
escaneador_jsonl = EscaneadorEstrutura("estrutura_jsonl", itens_por_passo=30)
escaneador_txt = EscaneadorEstrutura("estrutura_txt", itens_por_passo=40)
escaneador_parquet = EscaneadorEstrutura("estrutura_parquet", itens_por_passo=40)
