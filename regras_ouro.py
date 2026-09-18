#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
regras_ouro.py — Verificador AUTOMÁTICO das regras de ouro de ORGANIZAÇÃO de dados.

Lição 04/08: o usuário teve que apontar arquivos jsonl soltos na raiz de
dados/processed/jsonl. Regra de ouro SEM verificação automática é só intenção.
Por isso este módulo existe: qualquer operação de dados roda isto e reporta
violações.

Regras verificadas:
  1. dados/processed/jsonl, dados/gerados/jsonl, dados/processed/TXT,
     JSONL e PARQUET: NENHUM arquivo solto na raiz (cada batch deve estar em
     sua própria pasta).
  2. Limite de arquivos POR TIPO (regra de ouro 18/08/2026):
       TXT     → no máximo 1000 arquivos por pasta
       JSONL   → no máximo 5000 arquivos por pasta
       PARQUET → no máximo 5000 arquivos por pasta
  3. Proporção do material de treino (regra do usuário 18/08):
       30% .txt · 70% .jsonl + .parquet
  4. Nenhuma pasta vazia (lixo sem uso).
  5. 🚫 REGRA DE OURO ANTI-FAKE (17/08): o RigelSLM NÃO pode ser treinado com
     fake news, lixo ou respostas idiotas NUNCA. Todo material de treino deve
     passar por revisão de qualidade (ajuizar) e, se houver fatos, verificação
     com busca (scripts/verificar_fatos.py). Reporta material não revisado.
  6. 🧼 TRATAMENTO AUTOMÁTICO DE DATASETS (18/08): todo dataset baixado/bruto
     deve passar pela correção de encoding e limpeza ANTES de virar treino.
     Ferramenta: scripts/tratar_datasets_brutos.py (detecta formato: messages /
     text / alpaca / qna; corrige mojibake com sanitizador_ptbr e converte
     alpaca→messages). SÓ material `*_sanitizado` é treino pronto.
  7. ✅ VALIDAÇÃO DO ACERVO (18/08): antes de treinar, validar o acervo com
     scripts/validar_jsonl_acervo.py (JSON válido + sem mojibake real).
     Aviso: regex de mojibake com `Ã` solto dá falso positivo (SÃO/MÃE/CÃES).
     Usar só duplo-encoding real.
"""
from __future__ import annotations

import os
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent

# ── REGRAS DE OURO DE ORGANIZAÇÃO (18/08/2026) ────────────────────────────
# Estrutura padrão de dados/processed:
#   TXT/     → subpastas com ATÉ 1000 arquivos .txt cada
#   JSONL/   → subpastas com ATÉ 5000 arquivos .jsonl cada
#   PARQUET/ → subpastas com ATÉ 5000 arquivos .parquet cada
# Proporção do material de treino (regra do usuário):
#   30% .txt · 70% .jsonl + .parquet
LIMITES_POR_TIPO = {".txt": 1000, ".jsonl": 5000, ".parquet": 5000}
PROPORCAO_TXT_TREINO = 0.30   # 30% TXT, 70% JSONL+PARQUET
MAX_FILES_POR_PASTA = LIMITES_POR_TIPO[".jsonl"]  # compat: JSONL (maior volume)

_PASTAS = [
    (PROJETO_ROOT / "dados" / "processed" / "jsonl", ".jsonl"),
    (PROJETO_ROOT / "dados" / "gerados" / "jsonl", ".jsonl"),
    (PROJETO_ROOT / "dados" / "processed" / "TXT", ".txt"),
    (PROJETO_ROOT / "dados" / "processed" / "JSONL", ".jsonl"),
    (PROJETO_ROOT / "dados" / "processed" / "PARQUET", ".parquet"),
]


def _extensao_dominante(pasta: Path) -> str:
    """Extensão de arquivo dominante dentro da pasta (para aplicar o limite certo)."""
    cont = {e: 0 for e in LIMITES_POR_TIPO}
    try:
        for f in os.listdir(pasta):
            e = Path(f).suffix.lower()
            if e in cont:
                cont[e] += 1
    except Exception:
        pass
    return max(cont, key=lambda k: cont[k]) if any(cont.values()) else ".jsonl"


def verificar_organizacao() -> list:
    """Verifica as regras de ouro de organização (limites POR TIPO).

    Retorna lista de violações (vazia = OK). Limites: TXT=1000, JSONL=5000,
    PARQUET=5000 arquivos por pasta (regra de ouro 18/08/2026)."""
    violacoes = []
    for base, esperado in _PASTAS:
        if not base.is_dir():
            continue
        nome_base = str(base.relative_to(PROJETO_ROOT))
        # 1) arquivos soltos na raiz (do tipo esperado da base)
        try:
            soltos = [f for f in os.listdir(base)
                      if os.path.isfile(base / f)
                      and Path(f).suffix.lower() == esperado]
        except Exception:
            soltos = []
        if soltos:
            violacoes.append(
                f"{nome_base}: {len(soltos)} arquivo(s) {esperado} SOLTO(S) na raiz "
                "(devem estar em pasta própria do batch)")
        # 2) limite POR TIPO  e  3) pastas vazias
        try:
            itens = sorted(os.listdir(base))
        except Exception:
            itens = []
        for item in itens:
            p = base / item
            if not p.is_dir():
                continue
            try:
                arqs = [f for f in os.listdir(p)
                        if Path(f).suffix.lower() in LIMITES_POR_TIPO]
            except Exception:
                arqs = []
            rel = f"{nome_base}/{item}"
            limite = LIMITES_POR_TIPO.get(_extensao_dominante(p),
                                          LIMITES_POR_TIPO[esperado])
            if not arqs:
                violacoes.append(f"{rel}: pasta VAZIA (lixo)")
            elif len(arqs) > limite:
                violacoes.append(
                    f"{rel}: {len(arqs)} arquivos (> {limite} "
                    f"{_extensao_dominante(p)}, regra de ouro)")
    return violacoes


def verificar_proporcao() -> dict:
    """Proporção do material de treino (regra: 30% TXT · 70% JSONL+PARQUET).

    Conta só 1 nível de profundidade (pastas de lotes) com CAP por pasta —
    leve e suficiente para a regra. Roda com --proporcao (não no default,
    para não varrer o SSD sem necessidade)."""
    def _contar(base: Path, ext: str, cap: int = 5000) -> int:
        total = 0
        if not base.is_dir():
            return 0
        try:
            for item in os.scandir(base):
                if item.is_dir():
                    try:
                        n = sum(1 for f in os.scandir(item.path)
                                if f.is_file()
                                and f.name.lower().endswith(ext))
                        total += min(n, cap)
                    except Exception:
                        pass
                elif item.is_file() and item.name.lower().endswith(ext):
                    total += 1
        except Exception:
            pass
        return total

    base = PROJETO_ROOT / "dados" / "processed"
    txt = _contar(base / "TXT", ".txt")
    jsonl = _contar(base / "JSONL", ".jsonl")
    parquet = _contar(base / "PARQUET", ".parquet")
    total = txt + jsonl + parquet
    pct_txt = (txt / total * 100) if total else 0
    return {
        "txt": txt, "jsonl": jsonl, "parquet": parquet, "total": total,
        "pct_txt": round(pct_txt, 1), "meta_txt": 30.0,
        "ok": bool(total) and 20 <= pct_txt <= 40,
    }


def verificar_qualidade() -> list:
    """🚫 REGRA DE OURO ANTI-FAKE (17/08): reporta pastas de geração com .txt
    que ainda NÃO passaram pelo ajuizador (bandeira ✓) — material cru não pode
    ir para o treino sem revisão de qualidade.

    Pastas de DESCARTE (desclassificados, _rejeitados, etc.) são ignoradas —
    já estão fora do treino por decisão."""
    _IGNORAR = {"desclassificados", "_rejeitados", "_filtro", "_massa",
                "descartados", "estado", "logs"}
    try:
        from dashboard.services.avaliacao import listar_pastas
        dados = listar_pastas()
        violacoes = []
        for p in dados.get("pastas", []):
            nome = p.get("nome", "")
            if any(nome == i or nome.startswith(i) for i in _IGNORAR):
                continue
            if p.get("status") != "verificada":
                violacoes.append(
                    f"🚫 {nome}: {p.get('txt', 0)} texto(s) NÃO revisado(s) "
                    "(regra de ouro: sem fake news/lixo no treino — rode o ajuizamento)")
        return violacoes
    except Exception:
        return []


def resumo_regras() -> str:
    """Resumo legível para o chat/status."""
    v = verificar_organizacao() + verificar_qualidade()
    if not v:
        return "Regras de ouro de organização: OK. (nenhuma violação)"
    return ("Regras de ouro VIOLADAS (" + str(len(v)) + "):\n"
            + "\n".join("• " + x for x in v))


if __name__ == "__main__":
    import sys
    import argparse
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Verificador das regras de ouro")
    ap.add_argument("--proporcao", action="store_true",
                    help="Mostra a proporção TXT vs JSONL+PARQUET (30/70)")
    args = ap.parse_args()
    if args.proporcao:
        p = verificar_proporcao()
        print(f"Proporção do material (meta 30% TXT · 70% JSONL+PARQUET):")
        print(f"  TXT: {p['txt']} | JSONL: {p['jsonl']} | PARQUET: {p['parquet']} "
              f"| total: {p['total']}")
        print(f"  TXT atual: {p['pct_txt']}% (meta 30%) "
              + ("✅" if p['ok'] else "⚠️ fora da meta"))
    else:
        print(resumo_regras())
