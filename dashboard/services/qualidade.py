#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
qualidade.py — "CARTEIRA DE VACINAÇÃO" dos dados (15/08/2026).

Registra, por PASTA/arquivo, quais PROCESSOS já ocorreram:
  - sanitizado        : passou pela sanitização PT-BR (ABNT2, mojibake)
  - verificado_encoding: passou pela verificação de encoding/mojibake
  - ajuizado          : passou pelo ajuizador de qualidade (aprovados/suspeitos/lixo)
  - limpo             : passou pela limpeza leve (dedup + qualidade)
  - promovido         : foi promovido p/ processed (validado)
  - pronto_treino     : bandeira FINAL — pode ir para o treino

Regra de ouro do usuário: NUNCA mandar dado cru/sem tratamento para o treino.
Este registro diferencia material PRONTO (vacinado) de material CRU (novo,
sem supervisão). Persistente em estado/qualidade_pastas.json.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
_ESTADO = PROJETO_ROOT / "estado" / "qualidade_pastas.json"
# RLock (reentrante) — NUNCA trocar por Lock: `marcar()` chama `status()`
# dentro do próprio `with _lock:`, e Lock não-reentrante trava a thread
# para sempre (deadlock) — foi a causa do congelamento da extração.
_lock = threading.RLock()

# Etapas em ordem (uma pasta "pronta" precisa de sanitizar/verificar + ajuizar
# + promover). A presença da etapa marca que ela aconteceu.
_ETAPAS_NECESSARIAS_PRONTO = ("sanitizado", "verificado_encoding", "ajuizado", "promovido")


def pode_ajuizar(pasta: str) -> tuple[bool, list[str]]:
    """Confirma que o material recebeu tratamento antes do ajuizamento."""
    st = status(pasta)
    faltam = [e for e in ("sanitizado", "verificado_encoding")
              if e not in st.get("etapas", {})]
    return not faltam, faltam


def _carregar() -> dict:
    try:
        if _ESTADO.exists():
            dados = json.loads(_ESTADO.read_text(encoding="utf-8"))
            if isinstance(dados, dict) and isinstance(dados.get("pastas"), dict):
                return dados
    except Exception:
        pass
    return {"pastas": {}}


def _salvar(dados: dict) -> None:
    try:
        _ESTADO.parent.mkdir(parents=True, exist_ok=True)
        _ESTADO.write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    except Exception:
        pass


def _chave(pasta: str) -> str:
    """Chave canônica da pasta (nome simples)."""
    return (pasta or "").strip().replace("\\", "/").rstrip("/").split("/")[-1] or "dataset"


def marcar(pasta: str, etapa: str, **extra) -> dict:
    """Marca que um processo (etapa) ocorreu na pasta. Retorna o status novo."""
    chave = _chave(pasta)
    with _lock:
        dados = _carregar()
        reg = dados["pastas"].setdefault(chave, {
            "etapas": {}, "criado_em": datetime.now().isoformat(),
        })
        reg.setdefault("etapas", {})
        reg["etapas"][etapa] = datetime.now().isoformat(timespec="seconds")
        if etapa == "ajuizado":
            prereqs = {"sanitizado", "verificado_encoding"}
            if not prereqs.issubset(reg["etapas"]):
                return status(chave) | {"bloqueado": True,
                    "motivo": "Tratamento e verificação de encoding ainda não concluídos."}
        for k, v in extra.items():
            reg[k] = v
        # Calcula bandeira final
        presentes = {e for e in reg["etapas"]}
        necessarias = set(_ETAPAS_NECESSARIAS_PRONTO)
        reg["pronto_treino"] = bool(necessarias.issubset(presentes))
        _salvar(dados)
        return status(chave)


def status(pasta: str) -> dict:
    """Status da carteira de uma pasta (crua / parcial / pronta)."""
    chave = _chave(pasta)
    with _lock:
        dados = _carregar()
        reg = dados["pastas"].get(chave) or {}
        etapas = reg.get("etapas") or {}
    presentes = set(etapas)
    necessarias = set(_ETAPAS_NECESSARIAS_PRONTO)
    pronto = bool(necessarias.issubset(presentes))
    # Classificação leiga
    if pronto:
        situacao = "pronta"
        label = "✅ Pronto para treino"
    elif not presentes:
        situacao = "crua"
        label = "🥩 Crua (sem tratamento)"
    else:
        situacao = "parcial"
        label = "🔄 Parcial (ainda não pronta)"
    faltam = sorted(necessarias - presentes)
    return {
        "pasta": chave,
        "etapas": dict(sorted(etapas.items())),
        "pronto_treino": pronto,
        "situacao": situacao,
        "label": label,
        "faltam": faltam,
        "criado_em": reg.get("criado_em"),
    }


def listar() -> dict:
    """Carteira de todas as pastas conhecidas."""
    with _lock:
        dados = _carregar()
        nomes = sorted(dados["pastas"].keys())
    itens = [status(n) for n in nomes]
    prontas = sum(1 for i in itens if i["pronto_treino"])
    cruas = sum(1 for i in itens if i["situacao"] == "crua")
    return {
        "total": len(itens),
        "prontas": prontas,
        "cruas": cruas,
        "parciais": len(itens) - prontas - cruas,
        "itens": itens,
    }


def desmarcar(pasta: str, etapa: str | None = None) -> dict:
    """Remove uma etapa (ou toda a carteira) de uma pasta."""
    chave = _chave(pasta)
    with _lock:
        dados = _carregar()
        if chave not in dados["pastas"]:
            return {"ok": True, "mensagem": f"'{chave}' sem carteira registrada."}
        if etapa:
            dados["pastas"][chave].setdefault("etapas", {}).pop(etapa, None)
            dados["pastas"][chave]["pronto_treino"] = False
        else:
            del dados["pastas"][chave]
        _salvar(dados)
    return {"ok": True, "mensagem": f"Carteira de '{chave}' atualizada."}
