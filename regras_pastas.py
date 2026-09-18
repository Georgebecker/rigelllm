#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
regras_pastas.py — FONTE DE VERDADE das pastas de dados (padrão 18/08/2026).

Estrutura padrão do acervo (TODAS MINÚSCULAS — Windows é case-insensitive,
`jsonl` e `JSONL` são a MESMA pasta):
  dados/processed/txt/      → subpastas com ATÉ 1000 .txt cada
  dados/processed/jsonl/    → subpastas com ATÉ 5000 .jsonl cada
  dados/processed/parquet/  → subpastas com ATÉ 5000 .parquet cada

Fluxo padrão (regra de ouro):
  1. GERAR/BAIXAR  → dados/gerados/<tipo>/           (provisório)
  2. TRATAR        → staging dados/sanitizados/      (sanitizar/limpar/verificar)
  3. PROMOVER      → dados/processed/<tipo>/<batch>[_sanitizado]/  (acervo final)

Palavra unificadora dos serviços de limpeza/qualidade: "TRATAMENTO"
(escolha do usuário em 18/08/2026 — cobre sanitizar, limpar, verificar, validar).
"""
from __future__ import annotations

from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent

DADOS = PROJETO_ROOT / "dados"
RAW = DADOS / "raw"
GERADOS = DADOS / "gerados"
SANITIZADOS = DADOS / "sanitizados"
TRATADOS = DADOS / "tratados"
DESCARTADOS = DADOS / "descartados"
PROCESSED = DADOS / "processed"

# ── Acervo final de treino: UMA pasta por tipo (minúsculas) ───────────────
PROCESSED_TXT = PROCESSED / "txt"
PROCESSED_JSONL = PROCESSED / "jsonl"
PROCESSED_PARQUET = PROCESSED / "parquet"

# Limites por tipo (regra de ouro — espelha regras_ouro.py)
LIMITES_POR_TIPO = {".txt": 1000, ".jsonl": 5000, ".parquet": 5000}

# Pastas-base de treino por tipo (fonte de verdade p/ os treinadores)
PASTAS_TREINO_POR_TIPO = {
    "txt": PROCESSED_TXT,
    "jsonl": PROCESSED_JSONL,
    "parquet": PROCESSED_PARQUET,
}

# Pasta de staging do TRATAMENTO (sanitização) — a "mesa de trabalho"
STAGING_TRATAMENTO = SANITIZADOS
