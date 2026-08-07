#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
treino_cloud.py - Detecção de ambiente e treino em nuvem (Colab, AWS, Kaggle)
Versão: 1.0.0 | Data: 31/07/2026
Detecta automaticamente o ambiente e ajusta workers/batch.
"""
import os
import sys
import subprocess
import json
from pathlib import Path

# ============================================================================
# DETECÇÃO DE AMBIENTE
# ============================================================================

def detectar_ambiente() -> dict:
    """Detecta o ambiente de execução e retorna configurações otimizadas."""
    info = {
        "ambiente": "local",
        "gpu": False,
        "gpu_nome": None,
        "cuda_disponivel": False,
        "workers_otimo": 1,
        "batch_otimo": 4,
        "precision": "fp32"
    }

    # Detecta Colab
    try:
        import google.colab  # noqa
        info["ambiente"] = "colab"
    except ImportError:
        pass

    # Detecta Kaggle
    if os.path.exists("/kaggle/input"):
        info["ambiente"] = "kaggle"

    # Detecta AWS (presença de metadata)
    if os.path.exists("/sys/hypervisor/uuid"):
        with open("/sys/hypervisor/uuid") as f:
            if "ec2" in f.read().lower():
                info["ambiente"] = "aws"

    # Detecta GPU
    try:
        import torch
        info["cuda_disponivel"] = torch.cuda.is_available()
        if info["cuda_disponivel"]:
            info["gpu"] = True
            info["gpu_nome"] = torch.cuda.get_device_name(0)
            # Ajusta workers/batch para GPU
            info["workers_otimo"] = 4
            info["batch_otimo"] = 16
            info["precision"] = "amp"
    except ImportError:
        pass

    # Ajustes por ambiente
    if info["ambiente"] == "colab":
        info["workers_otimo"] = min(info["workers_otimo"], 4)
        info["batch_otimo"] = min(info["batch_otimo"], 12)  # T4 limit
    elif info["ambiente"] == "kaggle":
        info["workers_otimo"] = min(info["workers_otimo"], 2)

    return info


def main():
    """Ponto de entrada: detecta ambiente e executa treino com parâmetros otimizados."""
    env = detectar_ambiente()

    print("=" * 60)
    print(f"   ☁️  RIGELSLM - TREINO EM NUVEM")
    print("=" * 60)
    print(f"   Ambiente: {env['ambiente']}")
    print(f"   GPU: {env['gpu_nome'] if env['gpu'] else '❌'}")
    print(f"   Workers: {env['workers_otimo']}")
    print(f"   Batch: {env['batch_otimo']}")
    print(f"   Precision: {env['precision']}")
    print("=" * 60)

    # Parâmetros do argparse (se chamado diretamente)
    import argparse
    parser = argparse.ArgumentParser(description="Treino em nuvem RigelSLM")
    parser.add_argument("--dados", default="dados/processed", help="Pasta de dados")
    parser.add_argument("--max-arquivos", type=int, default=20000, help="Máx de arquivos")
    parser.add_argument("--epochs", type=int, default=20, help="Número de épocas")
    parser.add_argument("--resume", action="store_true", help="Continuar de checkpoint")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size (auto se vazio)")
    parser.add_argument("--workers", type=int, default=None, help="Workers (auto se vazio)")
    args = parser.parse_args()

    # Usa valores detectados se não especificados
    batch = args.batch_size or env["batch_otimo"]
    workers = args.workers or env["workers_otimo"]

    # Monta comando
    cmd = [
        "python", "treino.py",
        "--dados", args.dados,
        "--max-arquivos", str(args.max_arquivos),
        "--epochs", str(args.epochs),
        "--batch-size", str(batch),
        "--workers", str(workers),
        "--precision", env["precision"]
    ]
    if args.resume:
        cmd.append("--resume")

    print(f"\n🚀 Comando: {' '.join(cmd)}\n")

    # Executa
    processo = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for linha in processo.stdout:
        print(linha, end="")

    processo.wait()
    sys.exit(processo.returncode)


if __name__ == "__main__":
    main()
