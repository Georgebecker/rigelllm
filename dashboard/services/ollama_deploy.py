#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ollama_deploy.py - Disponibilizar o RigelSLM ao Ollama.
Versão: 1.0.0 | Data: 02/08/2026

Fluxo (executado em thread, com mensagens ao vivo):
  1. Verifica se o Ollama está instalado (e rodando na porta 11434).
  2. Se não estiver, oferece instalação (winget no Windows) ou link oficial.
  3. Converte o melhor modelo (modelo/modelo_melhor.pt) para GGUF (Q4_K_M etc.).
  4. Cria o Modelfile e registra com `ollama create rigelslm`.
  5. Confirma com `ollama list`.

Visão: o RigelSLM é pequeno o suficiente para rodar em qualquer lugar —
smartwatch, robozinho, microcontrolador. 🚀
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent.parent
PASTA_MODELO = _RAIZ / "modelo"
PASTA_GGUF = _RAIZ / "gguf"

_estado: dict = {
    "rodando": False,
    "etapa": "idle",          # idle | verificando | convertendo | registrando | concluido | erro
    "mensagem": "",
    "erro": None,
    "quant": None,
    "mensagens": [],
    "fim": None,
}
_lock = threading.Lock()
_thread: threading.Thread | None = None


def _atualizar(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)


def get_estado() -> dict:
    with _lock:
        e = dict(_estado)
        e["mensagens"] = list(e["mensagens"])
        return e


def _anexar(msg: str) -> None:
    with _lock:
        _estado["mensagens"].append(msg)
        if len(_estado["mensagens"]) > 300:
            _estado["mensagens"] = _estado["mensagens"][-300:]
        _estado["mensagem"] = msg


def verificar_ollama() -> dict:
    """Verifica se o Ollama está instalado e rodando."""
    instalado = shutil.which("ollama") is not None
    if not instalado:
        caminhos = [r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe",
                    r"C:\Program Files\Ollama\ollama.exe"]
        instalado = any(os.path.exists(os.path.expandvars(p)) for p in caminhos)
    versao = None
    if instalado:
        try:
            r = subprocess.run(["ollama", "--version"], capture_output=True,
                               text=True, timeout=10)
            versao = (r.stdout.strip().splitlines() or [""])[0] or "instalado"
        except Exception:
            versao = "instalado"
    rodando = False
    if instalado:
        try:
            s = socket.create_connection(("127.0.0.1", 11434), timeout=2)
            s.close()
            rodando = True
        except Exception:
            rodando = False
    # O modelo rigelslm já está disponível no Ollama?
    tem_rigel = False
    if instalado:
        try:
            r = subprocess.run(["ollama", "list"], capture_output=True,
                               text=True, timeout=30)
            tem_rigel = "rigelslm" in (r.stdout or "")
        except Exception:
            tem_rigel = False
    return {"instalado": bool(instalado), "versao": versao, "rodando": rodando,
            "rigelslm": tem_rigel}


def _rodar_deploy(quant: str) -> None:
    try:
        _atualizar(rodando=True, etapa="verificando", erro=None, quant=quant, fim=None)

        verif = verificar_ollama()
        if not verif["instalado"]:
            _anexar("❌ Ollama não está instalado.")
            _anexar("   Instale em https://ollama.com/download ou use o botão "
                    "'Instalar Ollama' (winget).")
            _atualizar(rodando=False, etapa="erro",
                       erro="Ollama não instalado.")
            return
        _anexar(f"✅ Ollama: {verif['versao'] or 'instalado'} — "
                f"{'rodando (porta 11434)' if verif['rodando'] else 'instalado mas parado'}")
        if verif.get("rigelslm"):
            _anexar("ℹ️ O modelo 'rigelslm' JÁ existe no Ollama — "
                    "vou atualizar com o modelo mais novo.")

        modelo = PASTA_MODELO / "modelo_melhor.pt"
        if not modelo.exists():
            modelo = PASTA_MODELO / "modelo.pt"
        if not modelo.exists():
            _anexar("❌ Nenhum modelo em modelo/ (modelo_melhor.pt ou modelo.pt).")
            _atualizar(rodando=False, etapa="erro",
                       erro="Nenhum modelo para disponibilizar.")
            return
        _anexar(f"📦 Modelo: {modelo.name} ({modelo.stat().st_size / 1024 / 1024:.1f} MB)")

        # --- Backup cauteloso antes de qualquer conversão ---
        try:
            from modelo_backup import criar_backup
            r = criar_backup(motivo="antes_ollama")
            if r["ok"]:
                _anexar(f"💾 Backup de segurança criado em modelo/backups/ "
                        f"({len(r['criados'])} arquivo(s)).")
        except Exception:
            pass

        # --- Converte para GGUF ---
        _atualizar(etapa="convertendo")
        data = datetime.now().strftime("%Y%m%d")
        saida_gguf = PASTA_GGUF / f"rigelslm_{quant}_{data}.gguf"
        os.makedirs(PASTA_GGUF, exist_ok=True)
        cmd = [sys.executable, "converter_para_gguf.py",
               "--model", str(modelo),
               "--quant", quant,
               "--output", str(saida_gguf),
               "--modelfile", "rigelslm"]
        _anexar("🔄 Convertendo para GGUF (Q4_K_M ≈ 40-60 MB; pode levar alguns minutos)...")
        proc = subprocess.Popen(
            cmd, cwd=str(_RAIZ),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert proc.stdout is not None
        for linha in proc.stdout:
            l = linha.rstrip("\n")
            if l.strip():
                _anexar(l)
        cod = proc.wait()
        if cod != 0:
            _anexar("❌ Conversão GGUF falhou.")
            _atualizar(rodando=False, etapa="erro",
                       erro=f"Conversão falhou (código {cod}).")
            return

        # --- Localiza o Modelfile gerado ---
        modelfile = PASTA_GGUF / f"Modelfile.rigelslm_{quant}"
        if not modelfile.exists():
            achados = sorted(PASTA_GGUF.glob("Modelfile.rigelslm_*"))
            modelfile = achados[-1] if achados else None
        if modelfile is None or not modelfile.exists():
            _anexar("⚠️ Modelfile não encontrado — criando manualmente.")
            modelfile = PASTA_GGUF / f"Modelfile.rigelslm_{quant}"
            modelfile.write_text(
                f"FROM {saida_gguf.absolute()}\n\n"
                'TEMPLATE """{{{{ .Prompt }}}}"""\n\n'
                "PARAMETER temperature 0.7\nPARAMETER top_p 0.9\n"
                "PARAMETER top_k 40\nPARAMETER num_predict 256\n"
                "PARAMETER num_ctx 2048\n"
                'SYSTEM """Você é o Rigel, um assistente virtual brasileiro. '
                'Fale em português brasileiro padrão, com naturalidade e calor humano."""\n',
                encoding="utf-8")

        # --- Registra no Ollama ---
        _atualizar(etapa="registrando")
        _anexar("🔄 Registrando no Ollama: ollama create rigelslm ...")
        r = subprocess.run(["ollama", "create", "rigelslm", "-f", str(modelfile)],
                           capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            _anexar(f"❌ ollama create falhou: {r.stderr.strip()[:400]}")
            _atualizar(rodando=False, etapa="erro",
                       erro=f"ollama create falhou: {r.stderr.strip()[:200]}")
            return
        _anexar("✅ Modelo 'rigelslm' criado no Ollama!")
        try:
            lst = subprocess.run(["ollama", "list"], capture_output=True,
                                 text=True, timeout=30)
            if lst.stdout.strip():
                _anexar("📋 " + lst.stdout.strip().replace("\n", "\n📋 "))
        except Exception:
            pass

        _anexar("🎉 Pronto! O RigelSLM agora roda como 'rigelslm' no Ollama. "
                "Teste: ollama run rigelslm")
        _atualizar(rodando=False, etapa="concluido",
                   fim=datetime.now().isoformat())
    except Exception as e:
        _anexar(f"❌ {e}")
        _atualizar(rodando=False, etapa="erro", erro=str(e))


def disponibilizar(quant: str = "Q4_K_M") -> dict:
    """Inicia o fluxo de disponibilização ao Ollama (em thread)."""
    global _thread
    with _lock:
        if _estado["rodando"]:
            return {"ok": False, "erro": "Já existe uma operação em andamento."}
    _thread = threading.Thread(target=_rodar_deploy, args=(quant,), daemon=True)
    _thread.start()
    return {"ok": True, "mensagem": "Disponibilização ao Ollama iniciada."}


def instalar_ollama() -> dict:
    """Tenta instalar o Ollama (winget no Windows) em thread."""
    global _thread
    if os.name != "nt":
        return {"ok": False,
                "erro": "Instalação automática só no Windows. "
                        "Baixe em https://ollama.com/download"}
    if not shutil.which("winget"):
        return {"ok": False,
                "erro": "winget não disponível. Baixe em https://ollama.com/download"}

    def _rodar_instalacao():
        try:
            _atualizar(rodando=True, etapa="verificando", erro=None)
            _anexar("⬇️ Instalando Ollama via winget...")
            r = subprocess.run(
                ["winget", "install", "--id", "Ollama.Ollama", "-e",
                 "--accept-source-agreements", "--accept-package-agreements"],
                capture_output=True, text=True, timeout=900)
            if r.returncode == 0:
                _anexar("✅ Ollama instalado! Feche e reabra o terminal para usar 'ollama'.")
                _atualizar(rodando=False, etapa="concluido")
            else:
                _anexar(f"❌ winget falhou: {(r.stderr or r.stdout).strip()[:400]}")
                _atualizar(rodando=False, etapa="erro",
                           erro="Falha na instalação via winget.")
        except Exception as e:
            _anexar(f"❌ {e}")
            _atualizar(rodando=False, etapa="erro", erro=str(e))

    with _lock:
        if _estado["rodando"]:
            return {"ok": False, "erro": "Já existe uma operação em andamento."}
    _thread = threading.Thread(target=_rodar_instalacao, daemon=True)
    _thread.start()
    return {"ok": True, "mensagem": "Instalação do Ollama iniciada (winget)."}
