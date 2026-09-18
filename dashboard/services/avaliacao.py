#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
avaliacao.py — SERVIÇO DE BANDEIRAS DE QUALIDADE (ajuizar).

Pedido do usuário (13/08/2026):
  "não tem uma bandeira (✓) verdinha de verificadas... a pessoa deixou
   criando arquivos com ollama/geração em massa, mas os arquivos não foram
   ajuizados, não foram verificados."

O que este módulo faz:
  - MANTÉM o registro de pastas AVALIADAS/VERIFICADAS (estado/avaliacao_pastas.json).
  - LISTA pastas de geração (dados/gerados/**) com .txt e sua bandeira:
      🟢 verificada | 🟡 parcial | ⚪ não verificada.
  - MARCA uma pasta como verificada após rodar o avaliador até o fim (100%).
  - NÃO apaga nada — só registra bandeiras e relatórios.

Bandeira (estado/avaliacao_pastas.json):
  { "<pasta_nome>": {
      "verificada": true, "data": "ISO", "total": n,
      "aprovados": n, "suspeitos": n, "lixos": n,
      "juiz": "deepseek-r1:7b" | None, "relatorio": "path" } }

Uso (de outras partes do dashboard):
  from dashboard.services.avaliacao import listar_pastas, marcar_verificada, ...
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
_ESTADO = PROJETO_ROOT / "estado" / "avaliacao_pastas.json"

# Pastas de geração onde ficam os .txt a avaliar (não varre tudo — regra 05/08:
# nunca varrer a árvore inteira de dados/; aqui é raso e barato).
PASTAS_GERACAO = [
    "dados/gerados",
    "dados/gerados/massa_final",
    "dados/gerados/gerados_local",
]

# Nomes de subpastas que NÃO são conteúdo (ignora)
_IGNORAR = {"_rejeitados", "_filtro", "_massa", "descartados", "estado", "logs",
            "jsonl", "parquet", ".cache", "_temp"}


def _carregar() -> dict:
    try:
        if _ESTADO.exists():
            return json.loads(_ESTADO.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _salvar(dados: dict) -> None:
    try:
        _ESTADO.parent.mkdir(parents=True, exist_ok=True)
        _ESTADO.write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    except Exception:
        pass


def _nome_pasta(path: Path) -> str:
    """Nome canônico da pasta (relativo a dados/gerados)."""
    try:
        return str(path.relative_to(PROJETO_ROOT / "dados" / "gerados"))
    except Exception:
        return path.name


def _pastas_candidatas() -> list[Path]:
    """Pastas com pelo menos 1 .txt dentro (nível raso: pastas de 1º/2º nível)."""
    achadas: list[Path] = []
    vistos: set[str] = set()
    for base_rel in PASTAS_GERACAO:
        base = PROJETO_ROOT / base_rel
        if not base.is_dir():
            continue
        # 1º nível: a própria base e subpastas diretas
        candidatas = [base]
        try:
            candidatas += sorted(base.iterdir())
        except Exception:
            pass
        for cand in candidatas:
            if not cand.is_dir():
                continue
            if cand == base:
                continue  # NÃO lista a base raiz (só as subpastas de conteúdo)
            if cand.name in _IGNORAR or cand.name.startswith("_"):
                continue
            key = str(cand).lower()
            if key in vistos:
                continue
            if any(cand.rglob("*.txt")):  # tem texto p/ avaliar
                vistos.add(key)
                achadas.append(cand)
    return achadas


def listar_pastas() -> dict:
    """Lista pastas de geração com .txt + bandeira de verificação."""
    registro = _carregar()
    itens = []
    for p in _pastas_candidatas():
        nome = _nome_pasta(p)
        n_txt = len(list(p.rglob("*.txt")))
        reg = registro.get(nome) or {}
        status = "verificada" if reg.get("verificada") else "nao_verificada"
        itens.append({
            "nome": nome,
            "caminho": str(p),
            "txt": n_txt,
            "status": status,
            "data": reg.get("data"),
            "aprovados": reg.get("aprovados"),
            "suspeitos": reg.get("suspeitos"),
            "lixos": reg.get("lixos"),
            "juiz": reg.get("juiz"),
        })
    itens.sort(key=lambda x: (x["status"] != "verificada", x["nome"].lower()))
    pendentes = sum(1 for i in itens if i["status"] != "verificada")
    return {"total": len(itens), "pendentes": pendentes, "pastas": itens,
            "estado_path": str(_ESTADO)}


def marcar_verificada(nome_pasta: str, resumo: dict | None = None,
                      juiz: str | None = None, relatorio: str | None = None) -> None:
    """Marca uma pasta como verificada (após avaliação 100%)."""
    registro = _carregar()
    resumo = resumo or {}
    registro[nome_pasta] = {
        "verificada": True,
        "data": datetime.now().isoformat(),
        "total": resumo.get("total"),
        "aprovados": resumo.get("aprovados"),
        "suspeitos": resumo.get("suspeitos"),
        "lixos": resumo.get("lixos"),
        "juiz": juiz,
        "relatorio": relatorio,
    }
    _salvar(registro)
    # 💉 CARTEIRA DE QUALIDADE: marca que o material passou pelo ajuizador.
    try:
        from dashboard.services.qualidade import marcar as _marcar_qualidade
        _marcar_qualidade(nome_pasta, "ajuizado", aprovados=resumo.get("aprovados"),
                          suspeitos=resumo.get("suspeitos"), lixos=resumo.get("lixos"))
    except Exception:
        pass


def desmarcar(nome_pasta: str) -> dict:
    """Remove a bandeira de uma pasta (para re-avaliar)."""
    registro = _carregar()
    if nome_pasta in registro:
        del registro[nome_pasta]
        _salvar(registro)
        return {"ok": True, "mensagem": f"Bandeira removida: {nome_pasta}"}
    return {"ok": False, "erro": "Pasta sem bandeira registrada."}


def resumo() -> dict:
    """Resumo global: quantas verificadas / pendentes."""
    r = listar_pastas()
    return {"total": r["total"], "pendentes": r["pendentes"],
            "verificadas": r["total"] - r["pendentes"]}
