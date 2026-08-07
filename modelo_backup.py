#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modelo_backup.py - Backup e restauração cautelosa do modelo RigelSLM.
Versão: 1.1.0 | Data: 02/08/2026

Garante que NUNCA se perca o modelo: antes de QUALQUER sobrescrita de
modelo.pt / modelo_melhor.pt (treino, restauração, etc.), uma cópia é
guardada em `modelo/backups/`.

Política de retenção (eficiência > redundância cega):
  - Deduplicação: não copia se o conteúdo for idêntico ao último backup do alvo.
  - Throttle: no máximo 1 cópia do mesmo alvo a cada 5 min (a fila de treino
    salva o modelo a cada arquivo — sem isso a pasta enche de cópias de 228 MB).
  - Retenção MÍNIMA: 1 backup por alvo + teto de 1 GB na pasta (o backup
    completo do sistema fica por conta do deploy_package.py).
  - Nomes legíveis: <alvo>_<motivo>_<timestamp>.pt (ex: modelo_antes_save_20260802_224203.pt)

Uso (backend):
    python modelo_backup.py listar                 # lista os backups
    python modelo_backup.py criar                  # faz backup manual agora
    python modelo_backup.py limpar                 # aplica a política de retenção agora
    python modelo_backup.py restaurar <arquivo>    # restaura um backup (guarda o atual antes)

Também usado pelo dashboard (rota /api/treino_local/backups...) e pelo
treinador (backup automático antes de sobrescrever).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_RAIZ = Path(__file__).resolve().parent
PASTA_MODELO = _RAIZ / "modelo"
PASTA_BACKUPS = PASTA_MODELO / "backups"

# Arquivos críticos que SEMPRE ganham backup antes de qualquer sobrescrita
ALVOS_PADRAO = ("modelo.pt", "modelo_melhor.pt")

# Política de retenção (backup é para emergência, não para encher o disco):
MAX_POR_ALVO = 1          # mínimo: só o backup mais recente de cada alvo
TETO_TOTAL_GB = 1.0       # teto absoluto de espaço da pasta de backups
INTERVALO_MINIMO_SEG = 300  # não copia o MESMO alvo mais de 1x a cada 5 min
CHUNK_HASH = 1024 * 1024  # leitura de 1 MB para o hash (não carrega 228 MB na RAM)


def _apagar_seguro(f: Path) -> None:
    try:
        f.unlink()
    except Exception:
        pass


def _hash_arquivo(caminho: Path) -> str:
    """SHA-1 em streaming (não carrega o arquivo inteiro na RAM)."""
    h = hashlib.sha1()
    try:
        with open(caminho, "rb") as fh:
            while True:
                bloco = fh.read(CHUNK_HASH)
                if not bloco:
                    break
                h.update(bloco)
    except Exception:
        return ""
    return h.hexdigest()


def _ultimo_backup_do_alvo(alvo_stem: str) -> Path | None:
    """Backup mais recente cujo nome começa com 'alvo_stem_' (ex.: modelo_ / modelo_melhor_)."""
    if not PASTA_BACKUPS.exists():
        return None
    candidatos = [f for f in PASTA_BACKUPS.glob("*.pt")
                  if f.stem.startswith(alvo_stem + "_")]
    if not candidatos:
        return None
    return max(candidatos, key=lambda f: f.stat().st_mtime)


def _limpar_antigos() -> None:
    """Política de retenção: máximo por alvo + teto de espaço total.

    Mantém os MAX_POR_ALVO backups mais recentes de cada alvo e, se a pasta
    ainda passar do teto (TETO_TOTAL_GB), apaga os mais antigos até caber.
    """
    try:
        if not PASTA_BACKUPS.exists():
            return
        arquivos = list(PASTA_BACKUPS.glob("*.pt"))
        if not arquivos:
            return
        # 1) Retenção POR ALVO (modelo.pt / modelo_melhor.pt / outros)
        grupos: dict[str, list[Path]] = {}
        for f in arquivos:
            chave = _alvo_do_backup(f.name) or "outros"
            grupos.setdefault(chave, []).append(f)
        for lista in grupos.values():
            lista.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for f in lista[MAX_POR_ALVO:]:
                _apagar_seguro(f)
        # 2) Teto de espaço total (apaga os mais antigos até caber)
        restantes = sorted(PASTA_BACKUPS.glob("*.pt"),
                           key=lambda p: p.stat().st_mtime)  # mais antigos primeiro
        total = sum(f.stat().st_size for f in restantes)
        teto = int(TETO_TOTAL_GB * 1024 * 1024 * 1024)
        for f in restantes:
            if total <= teto:
                break
            total -= f.stat().st_size
            _apagar_seguro(f)
    except Exception:
        pass


def criar_backup_arquivo(origem: str | Path, motivo: str = "auto",
                         forcar: bool = False) -> dict:
    """Faz backup de UM arquivo de modelo antes de ser sobrescrito.

    Inteligente (eficiência > redundância cega):
      1. DEDUPLICAÇÃO: se o conteúdo é idêntico ao último backup do mesmo
         alvo, NÃO copia de novo (ex.: saves repetidos sem mudança).
      2. THROTTLE: não copia o mesmo alvo mais de 1x a cada
         INTERVALO_MINIMO_SEG (a fila de treino salva o modelo a cada arquivo).
      3. RETENÇÃO: a pasta nunca passa de MAX_POR_ALVO por alvo + teto de
         espaço (a limpeza roda após cada cópia).
    """
    origem = Path(origem)
    if not origem.exists():
        return {"ok": False, "caminho": None, "motivo": motivo}
    try:
        os.makedirs(PASTA_BACKUPS, exist_ok=True)
        alvo_stem = origem.stem  # modelo / modelo_melhor
        ultimo = _ultimo_backup_do_alvo(alvo_stem)

        # 1) Deduplicação por conteúdo (não duplica cópias idênticas)
        if ultimo is not None and _hash_arquivo(origem) == _hash_arquivo(ultimo):
            return {"ok": True, "caminho": str(ultimo), "motivo": motivo,
                    "deduplicado": True}

        # 2) Throttle: evita rajada de cópias de 228 MB na fila de treino
        if not forcar and motivo != "manual" and ultimo is not None:
            idade = time.time() - ultimo.stat().st_mtime
            if idade < INTERVALO_MINIMO_SEG:
                return {"ok": True, "caminho": str(ultimo), "motivo": motivo,
                        "throttle": True}

        # 3) Cópia real com nome legível (motivo + timestamp)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        motivo_limpo = re.sub(r"[^A-Za-z0-9_-]", "_", str(motivo))[:24].strip("_")
        destino = PASTA_BACKUPS / f"{alvo_stem}_{motivo_limpo}_{stamp}.pt"
        # Desambigua: se já existe backup criado neste mesmo segundo, não sobrescreve
        n = 2
        while destino.exists():
            destino = PASTA_BACKUPS / f"{alvo_stem}_{motivo_limpo}_{stamp}_{n}.pt"
            n += 1
        shutil.copy2(origem, destino)
        _limpar_antigos()
        return {"ok": True, "caminho": str(destino), "motivo": motivo}
    except Exception as e:
        return {"ok": False, "erro": str(e), "caminho": None, "motivo": motivo}


def criar_backup(motivo: str = "manual", alvos: tuple[str, ...] | None = None) -> dict:
    """Faz backup dos modelos atuais (modelo.pt + modelo_melhor.pt)."""
    criados = []
    for nome in (alvos or ALVOS_PADRAO):
        r = criar_backup_arquivo(PASTA_MODELO / nome, motivo=motivo)
        if r.get("ok"):
            criados.append(r["caminho"])
    return {"ok": bool(criados), "criados": criados, "motivo": motivo}


def listar_backups() -> list:
    """Lista os backups disponíveis (mais recentes primeiro)."""
    if not PASTA_BACKUPS.exists():
        return []
    itens = []
    for f in sorted(PASTA_BACKUPS.glob("*.pt"), key=lambda f: f.stat().st_mtime,
                    reverse=True):
        itens.append({
            "arquivo": f.name,
            "caminho": str(f),
            "tamanho_mb": round(f.stat().st_size / (1024 * 1024), 2),
            "modificado": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return itens


def _alvo_do_backup(nome: str) -> str | None:
    """Descobre para qual arquivo o backup deve restaurar (ex: modelo_2026... → modelo.pt)."""
    stem = Path(nome).stem
    for alvo in ("modelo_melhor", "modelo"):
        if stem.startswith(alvo + "_"):
            return alvo + ".pt"
    return None


def restaurar_backup(nome: str) -> dict:
    """Restaura um backup. Antes de sobrescrever, guarda o modelo atual (cautela)."""
    backup = PASTA_BACKUPS / nome
    if not backup.exists():
        return {"ok": False, "erro": f"Backup '{nome}' não encontrado em "
                                     f"{PASTA_BACKUPS}."}
    alvo_nome = _alvo_do_backup(nome)
    if alvo_nome is None:
        return {"ok": False, "erro": f"Nome de backup inválido: '{nome}'."}
    alvo = PASTA_MODELO / alvo_nome

    guarda_atual = ""
    if alvo.exists():
        # Cautela: antes de sobrescrever, guarda o que está lá agora
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        guarda = PASTA_BACKUPS / f"pre_restauro_{stamp}_{alvo_nome}"
        try:
            shutil.copy2(alvo, guarda)
            guarda_atual = str(guarda)
        except Exception:
            guarda_atual = ""

    try:
        shutil.copy2(backup, alvo)
    except Exception as e:
        return {"ok": False, "erro": f"Falha ao restaurar: {e}"}

    msg = (f"✅ '{alvo_nome}' restaurado a partir de '{nome}'.")
    if guarda_atual:
        msg += f" O modelo que estava lá foi guardado em backups/ (pre_restauro)."
    return {"ok": True, "mensagem": msg, "alvo": alvo_nome}


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Backup/restauração cautelosa do modelo RigelSLM")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar", help="Lista os backups disponíveis")
    sub.add_parser("criar", help="Faz backup manual dos modelos atuais")
    r = sub.add_parser("restaurar", help="Restaura um backup (guarda o atual antes)")
    r.add_argument("arquivo", help="Nome do backup em modelo/backups/ (ex: modelo_20260802_033000.pt)")
    sub.add_parser("limpar", help="Aplica a política de retenção agora (apaga backups antigos)")

    args = parser.parse_args()
    if args.cmd == "listar":
        backups = listar_backups()
        if not backups:
            print("📭 Nenhum backup em modelo/backups/ ainda.")
            return
        print(f"📦 {len(backups)} backup(s) em {PASTA_BACKUPS}:\n")
        for b in backups:
            print(f"   • {b['arquivo']}  ({b['tamanho_mb']} MB)  {b['modificado']}")
    elif args.cmd == "criar":
        r = criar_backup(motivo="manual")
        if r["ok"]:
            print("✅ Backup criado:")
            for c in r["criados"]:
                print(f"   • {c}")
        else:
            print("ℹ️ Nenhum modelo para backup (modelo.pt/modelo_melhor.pt não existem).")
    elif args.cmd == "limpar":
        antes = listar_backups()
        _limpar_antigos()
        depois = listar_backups()
        print(f"🗑️  Limpeza aplicada: {len(antes)} -> {len(depois)} backup(s).")
        for b in depois:
            print(f"   • {b['arquivo']}  ({b['tamanho_mb']} MB)")
    elif args.cmd == "restaurar":
        print("⚠️  ATENÇÃO: recuperar um backup vai SUBSTITUIR seu último modelo "
              "(modelo.pt / modelo_melhor.pt).")
        print("    O modelo atual será guardado como pre_restauro_* antes, por segurança.\n")
        try:
            resp = input("Digite RESTAURAR para confirmar: ").strip()
        except Exception:
            resp = ""
        if resp.upper() != "RESTAURAR":
            print("❌ Cancelado. Nada foi alterado.")
            return
        r = restaurar_backup(args.arquivo)
        print(r["mensagem"] if r["ok"] else f"❌ {r['erro']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()
