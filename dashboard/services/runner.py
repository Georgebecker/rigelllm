#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
runner.py - Executor de scripts em background para o Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
import subprocess
from subprocess import Popen, PIPE, STDOUT
from pathlib import Path
from datetime import datetime


def stream_subprocess_to_log(cmd, cwd=None, log_path=None):
    """Executa um comando e escreve stdout/stderr em tempo real no arquivo de log.
    
    Args:
        cmd: list[str] — comando e argumentos.
        cwd: Path | str | None — diretório de trabalho.
        log_path: Path | None — caminho do arquivo de log. Se None, não escreve.
    """
    if log_path is None:
        # Fallback: executa normalmente sem log
        subprocess.run(cmd, cwd=cwd, capture_output=True)
        return

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat()

    with open(log_path, "a", encoding="utf-8", errors="ignore") as f:
        f.write(f"[{ts}] >>> CMD: {' '.join(cmd)}\n")
        try:
            # Força UTF-8 nas saídas do subprocesso para evitar erro de encoding com emojis no Windows
            env = None
            if hasattr(cmd, '__iter__') and cmd and ('python' in str(cmd[0]).lower() or 'conda' in str(cmd[0]).lower()):
                import os as _os
                env = dict(_os.environ)
                env['PYTHONIOENCODING'] = 'utf-8'
            proc = Popen(cmd, cwd=str(cwd) if cwd else None,
                         stdout=PIPE, stderr=STDOUT, encoding='utf-8', errors='replace', env=env)
            if proc.stdout:
                for linha in proc.stdout:
                    f.write(linha)
                    f.flush()
            proc.wait()
            f.write(f"[{datetime.now().isoformat()}] <<< CODIGO: {proc.returncode}\n")
        except Exception as e:
            f.write(f"[{datetime.now().isoformat()}] ERRO: {e}\n")
            f.flush()
