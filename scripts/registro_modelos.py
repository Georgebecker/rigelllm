#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
registro_modelos.py — Gera o manifesto de modelos (modelo/versoes.json).

É a FONTE ÚNICA de organização: mostra qual versão/tipo/data/quantização de
cada artefato (modelo.pt, modelo_melhor.pt, checkpoints, GGUFs) existe, de
qual treino veio e qual é usado por quem.

Uso:
    python scripts/registro_modelos.py [--atualizar]
      --atualizar  também grava o estado de treino atual no manifesto

O manifesto é consumido por:
  - chat.py            -> identidade do modelo em teste
  - dashboard /versoes -> página Converter (histórico de versões)
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELO_DIR = RAIZ / "modelo"
GGUF_DIR = RAIZ / "gguf"
ESTADO_DIR = RAIZ / "estado"
SAIDA = MODELO_DIR / "versoes.json"

# Quais arquivos .pt são "oficiais" e de qual treinador
TREINADORES = {
    "modelo.pt": ("treinar_com_jsonl.py (SFT)", "modelo final / interrompido"),
    "modelo_melhor.pt": ("treinar_com_jsonl.py (SFT)", "melhor validação — usado pelo chat e conversor"),
    "checkpoint.pt": ("treino.py (causal)", "checkpoint de retomada (antigo)"),
    "checkpoint_jsonl.pt": ("treinar_com_jsonl.py (SFT)", "checkpoint de retomada SFT"),
}

# Estados de treino correspondentes a cada .pt oficial
ESTADO_POR_ARQUIVO = {
    "modelo.pt": "estado_treino_jsonl.json",
    "modelo_melhor.pt": "estado_treino_jsonl.json",
    "checkpoint.pt": "estado_treino.json",
    "checkpoint_jsonl.pt": "estado_treino_jsonl.json",
}

QUANT_RE = re.compile(r"(Q\d+_K?_\d+|Q\d+_[A-Z0-9_]+|F16|F32|Q8_0|Q4_K_M|Q5_K_M)", re.IGNORECASE)


def mb(tamanho: int) -> float:
    return round(tamanho / (1024 * 1024), 1)


def ler_json(caminho: Path) -> dict | None:
    try:
        if caminho.exists():
            return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def estado_de(arquivo_pt: str) -> dict | None:
    """Retorna o estado de treino associado ao .pt (época, best_val_loss)."""
    nome_estado = ESTADO_POR_ARQUIVO.get(arquivo_pt)
    if nome_estado:
        est = ler_json(MODELO_DIR / nome_estado)
        if est:
            return {
                "epoch": est.get("epoch"),
                "best_val_loss": est.get("best_val_loss"),
                "no_improve": est.get("no_improve"),
                "total_batches": est.get("total_batches"),
                "timestamp": est.get("timestamp", "")[:19],
            }
    return None


def quant_de(nome_gguf: str) -> str:
    m = QUANT_RE.search(nome_gguf)
    return m.group(1).upper() if m else "?"


def gerar() -> dict:
    versoes = []

    # ── Modelos .pt ──
    for f in sorted(MODELO_DIR.glob("*.pt"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = f.stat()
        nome = f.name
        info = {
            "nome": nome,
            "tipo": "pt",
            "tamanho_mb": mb(st.st_size),
            "data": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M"),
            "arquivo": str(f.relative_to(RAIZ)),
        }
        if nome in TREINADORES:
            treinador, papel = TREINADORES[nome]
            info["treinador"] = treinador
            info["papel"] = papel
            est = estado_de(nome)
            if est:
                info["estado_treino"] = est
            info["usado_por"] = "chat.py + dashboard (local)" if nome == "modelo_melhor.pt" else (
                "treino (retomada)" if nome.startswith("checkpoint") else "referência")
        else:
            info["treinador"] = "desconhecido"
            info["papel"] = "backup/checkpoint manual"
        versoes.append(info)

    # ── GGUFs ──
    ultima_criacao = ler_json(ESTADO_DIR / "ollama_ultima_criacao.json") or {}
    gguf_base = ultima_criacao.get("gguf", "")
    for f in sorted(GGUF_DIR.glob("*.gguf"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = f.stat()
        versoes.append({
            "nome": f.name,
            "tipo": "gguf",
            "quantizacao": quant_de(f.name),
            "tamanho_mb": mb(st.st_size),
            "data": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M"),
            "arquivo": str(f.relative_to(RAIZ)),
            "fonte": "última criação no Ollama" if f.name == gguf_base else "conversão manual/antiga",
            "usado_por": "Ollama (rigelslm:latest)" if f.name == gguf_base else "—",
        })

    # ── Modelo ativo do Ollama ──
    preferido = ler_json(ESTADO_DIR / "ollama_modelo_preferido.json") or {}
    manifesto = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "modelo_chat_local": "modelo/modelo_melhor.pt",
        "modelo_preferido_ollama": preferido.get("modelo", ""),
        "ultima_criacao_ollama": ultima_criacao,
        "versoes": versoes,
    }
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifesto


if __name__ == "__main__":
    m = gerar()
    print(f"✅ Manifesto gerado: {SAIDA}")
    print(f"   {len(m['versoes'])} artefatos registrados "
          f"({sum(1 for v in m['versoes'] if v['tipo']=='pt')} .pt, "
          f"{sum(1 for v in m['versoes'] if v['tipo']=='gguf')} .gguf)")
    for v in m["versoes"][:12]:
        tag = f" {v.get('quantizacao','')}" if v["tipo"] == "gguf" else ""
        print(f"   • {v['nome']}{tag} — {v['tamanho_mb']} MB — {v['data']}")
