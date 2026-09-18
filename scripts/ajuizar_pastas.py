#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ajuizar_pastas.py — RODA A AVALIAÇÃO DE QUALIDADE nas pastas PENDENTES.

Pedido do usuário (13/08/2026): "rodar uma limpeza... adicionar o ajuizar
(limpar rigorosamente)" — um botão que avalia TODAS as pastas de geração que
ainda não têm bandeira ✓ de verificada.

Comportamento:
  - Varre as pastas de geração (dados/gerados + massa_final + gerados_local).
  - Para CADA pasta SEM bandeira ✓, roda a camada 1 (gates determinísticos) e,
    se --juiz, a camada 2 (deepseek-r1:7b) nos "suspeitos".
  - Ao terminar cada pasta (100%), MARCA a bandeira (estado/avaliacao_pastas.json).
  - NÃO apaga nada: só classifica + marca bandeira + relatório.
  - Progresso real persistido em logs/ajuizar_progresso.json (painel lê).

Uso:
  python scripts/ajuizar_pastas.py [--juiz] [--pasta NOME] [--limite N]
    --juiz     usa o deepseek-r1:7b na camada 2 (mais lento)
    --pasta    avalia SÓ esta pasta (nome relativo a dados/gerados)
    --limite   máx. de arquivos por pasta (teste)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))

sys.path.insert(0, str(PROJETO_ROOT / "scripts"))
from avaliador_qualidade import (  # noqa: E402
    _metricas, _pontuar, _classificar, _juiz_ollama,
    _memoria_ok, _modelo_instalado, PROMPT_JUIZ, RELATORIO_DEFAULT,
)
from dashboard.services.avaliacao import (  # noqa: E402
    _carregar, _salvar, _nome_pasta, _pastas_candidatas, marcar_verificada,
)

LOGS = PROJETO_ROOT / "logs"
PROGRESSO = LOGS / "ajuizar_progresso.json"
RELATORIO = LOGS / "ajuizar_relatorio.json"


def _progresso(d: dict) -> None:
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        PROGRESSO.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _resolver_pasta(arg: str) -> list[Path]:
    """Resolve o argumento --pasta de forma TOLERANTE (tratamento previsto):

    - nome relativo a dados/gerados/ (contrato, ex.: 'debates')
    - com prefixo dados/gerados (rota do dashboard, ex.: 'gerados\\debates')
    - caminho absoluto

    Retorna lista com os diretórios válidos (deduplicada); vazia se não achar.
    """
    arg = (arg or "").strip().strip('"').strip("'")
    if not arg:
        return []
    candidatos: list[Path] = []
    cand = Path(arg)
    if cand.is_absolute():
        candidatos.append(cand)
    else:
        candidatos.append((PROJETO_ROOT / "dados" / "gerados" / arg).resolve())
        norm = arg.replace("\\", "/")
        if norm.startswith("gerados/"):
            sem_prefixo = norm.split("/", 1)[1]
            candidatos.append((PROJETO_ROOT / "dados" / "gerados" / sem_prefixo).resolve())
        candidatos.append((PROJETO_ROOT / "dados" / arg).resolve())
    vistos: set[str] = set()
    alvos: list[Path] = []
    for c in candidatos:
        chave = str(c).lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        if c.is_dir():
            alvos.append(c)
    return alvos


def _avaliar_arquivo(texto: str, usar_juiz: bool, modelo: str) -> tuple[str, dict | None]:
    """(classe_final, dict_juiz). Camada 1 sempre; camada 2 nos suspeitos."""
    m = _metricas(texto)
    pontos = _pontuar(m)
    classe = _classificar(pontos)
    juiz = None
    if usar_juiz and classe == "suspeito":
        juiz = _juiz_ollama(texto, modelo)
        if juiz.get("ok"):
            if juiz.get("aprovado"):
                classe = "aprovado"
            else:
                classe = "lixo" if pontos >= 4 else "suspeito"
    return classe, juiz


def _avaliar_pasta(pasta: Path, usar_juiz: bool, modelo: str,
                   limite: int | None) -> dict:
    arqs = sorted(pasta.rglob("*.txt"))
    if limite:
        arqs = arqs[:limite]
    res = {"total": len(arqs), "aprovados": 0, "suspeitos": 0, "lixos": 0,
           "arquivos": []}
    for i, f in enumerate(arqs, 1):
        try:
            texto = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        classe, juiz = _avaliar_arquivo(texto, usar_juiz, modelo)
        res[classe + ("s" if classe != "lixo" else "") if classe != "lixo"
            else "lixos"] += 1
        res["arquivos"].append({"arquivo": f.name, "classe": classe,
                                "juiz": juiz})
        if i % 25 == 0 or i == len(arqs):
            _progresso({
                "pasta": _nome_pasta(pasta), "pct": round(100 * i / len(arqs), 1),
                "atual": f.name, "total_pasta": len(arqs), "i": i,
                "aprovados": res["aprovados"], "suspeitos": res["suspeitos"],
                "lixos": res["lixos"], "atualizado": datetime.now().isoformat(),
            })
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--juiz", action="store_true")
    ap.add_argument("--pasta", default="")
    ap.add_argument("--limite", type=int, default=None)
    args = ap.parse_args()

    usar_juiz = args.juiz
    modelo = "deepseek-r1:7b"
    if usar_juiz:
        ok, liv = _memoria_ok()
        if not ok:
            print(f"⚠️ RAM livre {liv:.1f} GB < 6 GB — juiz DESLIGADO.")
            usar_juiz = False
        elif not _modelo_instalado(modelo):
            print(f"⚠️ Modelo '{modelo}' não encontrado — juiz DESLIGADO.")
            usar_juiz = False

    # Pastas alvo
    if args.pasta:
        alvos = _resolver_pasta(args.pasta)
        if not alvos:
            print(f"❌ Pasta não encontrada: {args.pasta}")
            print("   Use um nome relativo a dados/gerados (ex.: 'debates'),")
            print("   um caminho relativo a dados (ex.: 'gerados/debates') ou")
            print("   um caminho absoluto.")
            return 2
    else:
        registro = _carregar()
        alvos = [p for p in _pastas_candidatas()
                 if not (registro.get(_nome_pasta(p)) or {}).get("verificada")]

    if not alvos:
        print("✅ Nenhuma pasta pendente (todas já com bandeira ✓).")
        _progresso({"pct": 100, "pasta": None, "msg": "sem pendentes",
                    "atualizado": datetime.now().isoformat()})
        return 0

    print(f"🔎 Ajuizando {len(alvos)} pasta(s) pendente(s) "
          f"(juiz {'ON' if usar_juiz else 'OFF'})...")
    geral = {"inicio": datetime.now().isoformat(), "pasta_total": len(alvos),
             "pastas": [], "juiz": modelo if usar_juiz else None}

    for idx, pasta in enumerate(alvos, 1):
        nome = _nome_pasta(pasta)
        print(f"\n[{idx}/{len(alvos)}] ⚖️ {nome} ...")
        res = _avaliar_pasta(pasta, usar_juiz, modelo, args.limite)
        marcar_verificada(nome, res, juiz=modelo if usar_juiz else None,
                          relatorio=str(RELATORIO))
        geral["pastas"].append({"pasta": nome, **res})
        print(f"    ✅ {res['aprovados']} aprovados | 🟡 {res['suspeitos']} "
              f"suspeitos | ❌ {res['lixos']} lixo (total {res['total']}) — "
              f"bandeira ✓ marcada")
        _progresso({"pct": round(100 * idx / len(alvos), 1), "pasta": nome,
                    "pasta_i": idx, "pasta_total": len(alvos),
                    "atualizado": datetime.now().isoformat()})

    geral["fim"] = datetime.now().isoformat()
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        RELATORIO.write_text(json.dumps(geral, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    except Exception:
        pass
    _progresso({"pct": 100, "pasta": None, "msg": "concluido",
                "atualizado": datetime.now().isoformat()})
    print(f"\n✅ Ajuizamento concluído. Relatório: {RELATORIO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
