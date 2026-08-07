#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
deploy.py — Backup/distribuição do RigelSLM pelo dashboard.

Reaproveita a lógica de `deploy_package.py` (raiz do projeto) para gerar um
ZIP distribuível, MAS com rotação: no máximo 2 versões em dist/ (a mais nova
e a anterior) — nada de infinitos. Sem checkpoints grandes (pacote leve,
baixável no celular para testes).

Endpoints usados (routes/deploy.py):
  GET  /api/deploy/status    → estado + versões disponíveis
  POST /api/deploy/criar     → gera novo backup (thread)
  GET  /api/deploy/download/{nome} → baixa o ZIP (funciona no celular)
  POST /api/deploy/remover   → remove uma versão
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

# Garante que a raiz do projeto esteja no path (import do deploy_package.py)
RAIZ = Path(__file__).resolve().parent.parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from deploy_package import criar_zip, listar_conteudo, montar_pacote  # noqa: E402

DESTINO = RAIZ / "dist"
MAX_VERSAOES = 2

# Estado global (thread-safe)
_estado: dict = {
    "rodando": False,
    "etapa": "idle",        # idle | empacotando | concluido | erro
    "mensagem": "",
    "inicio": None,
    "fim": None,
    "erro": None,
    "versoes": [],
}
_lock = threading.Lock()


def _atualizar(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)


def _listar_versoes() -> list[dict]:
    """Versões em dist/ (ordenadas da mais nova para a mais antiga)."""
    if not DESTINO.exists():
        return []
    versoes = []
    for p in sorted(DESTINO.glob("rigelslm_dist_*.zip"), reverse=True):
        try:
            versoes.append({
                "nome": p.name,
                "tamanho_mb": round(p.stat().st_size / 1e6, 1),
                "data": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "url": f"/api/deploy/download/{p.name}",
            })
        except OSError:
            continue
    return versoes


def _rotacionar() -> None:
    """Mantém só as MAX_VERSAOES mais novas; apaga o resto."""
    versoes = sorted(DESTINO.glob("rigelslm_dist_*.zip"), reverse=True)
    for p in versoes[MAX_VERSAOES:]:
        try:
            p.unlink()
        except OSError:
            pass


def get_estado() -> dict:
    with _lock:
        est = dict(_estado)
    est["versoes"] = _listar_versoes()
    return est


def criar_backup() -> dict:
    """Dispara o empacotamento em thread. Retorna o estado inicial."""
    with _lock:
        if _estado["rodando"]:
            return {"ok": False, "mensagem": "Já existe um backup sendo gerado."}
        _estado.update({
            "rodando": True,
            "etapa": "empacotando",
            "mensagem": "Montando plano do pacote...",
            "inicio": datetime.now().isoformat(),
            "fim": None,
            "erro": None,
        })
    threading.Thread(target=_trabalho, daemon=True).start()
    return {"ok": True, "mensagem": "Backup iniciado."}


def _trabalho() -> None:
    _inicio = time.time()
    try:
        _atualizar(mensagem="Montando plano do pacote...")
        arquivos = listar_conteudo(incluir_checkpoints=False)
        if not arquivos:
            raise RuntimeError("Nenhum arquivo para empacotar.")
        tamanho = sum(p.stat().st_size for p, _ in arquivos)

        DESTINO.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = DESTINO / f"rigelslm_dist_{ts}.zip"

        _atualizar(mensagem=f"Copiando {len(arquivos)} arquivos ({tamanho / 1e6:.0f} MB)...")
        with tempfile.TemporaryDirectory(prefix="rigel_dist_") as tmp:
            pasta_tmp = Path(tmp)
            montar_pacote(arquivos, pasta_tmp, quiet=True)
            _atualizar(mensagem="Compactando ZIP...")
            total = criar_zip(pasta_tmp, zip_path, quiet=True)

        _rotacionar()
        _atualizar(
            rodando=False, etapa="concluido",
            mensagem=(f"✅ Backup pronto: {zip_path.name} "
                      f"({zip_path.stat().st_size / 1e6:.1f} MB, {total} arquivos) "
                      f"em {time.time() - _inicio:.0f}s"),
            fim=datetime.now().isoformat(),
        )
    except Exception as e:  # noqa: BLE001
        _atualizar(
            rodando=False, etapa="erro",
            mensagem=f"❌ Falha no backup: {e}",
            erro=str(e)[:300],
            fim=datetime.now().isoformat(),
        )


def remover_versao(nome: str) -> dict:
    """Remove uma versão (protege o nome contra path traversal)."""
    nome = Path(nome).name
    if not nome.startswith("rigelslm_dist_") or not nome.endswith(".zip"):
        return {"ok": False, "mensagem": "Nome inválido."}
    p = DESTINO / nome
    if not p.exists():
        return {"ok": False, "mensagem": "Versão não encontrada."}
    try:
        p.unlink()
        return {"ok": True, "mensagem": f"Removido {nome}."}
    except OSError as e:
        return {"ok": False, "mensagem": f"Erro ao remover: {e}"}
