#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
juizar_suspeitos.py — RODA O JUIZ (deepseek-r1:7b) NOS SUSPEITOS PENDENTES.

Pedido do usuário (17/08/2026): "temos que colocar um botão aqui marcar
(todos) para serem verificados se o Juiz concorda que são suspeitos ou não
são suspeitos. porque encontrei coisa aqui que não tinha nem pé nem cabeça,
não era só suspeito como era lixo."

O que faz:
  - Pega TODOS os arquivos marcados como SUSPEITO no relatório de ajuizamento
    que ainda estão pendentes (não decididos e ainda existem).
  - Para cada um, roda a camada 1 (gates determinísticos) e a camada 2 (juiz
    deepseek-r1:7b via Ollama).
  - ✅ Se o juiz APROVA → move para dados/processed/<pasta>_aprovado/ (vira
    material de treino) e registra a decisão.
  - ❌ Se o juiz REPROVA com pontos altos (lixo) → move para
    dados/gerados/desclassificados/<pasta>/ e registra a decisão.
  - 🟡 Se o juiz mantém SUSPEITO → fica na lista para revisão humana.
  - Progresso real persistido em logs/juiz_progresso.json (o painel lê).
  - Nunca apaga nada; nunca sobrescreve.

Uso:
  python scripts/juizar_suspeitos.py [--pasta NOME] [--limite N] [--seco]

  Sem --seco: pergunta antes de começar (para uso interativo).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))
sys.path.insert(0, str(PROJETO_ROOT / "scripts"))

from avaliador_qualidade import (  # noqa: E402
    _metricas, _pontuar, _classificar, _juiz_ollama, _veredito_aprovado,
    _memoria_ok, _modelo_instalado, MODELO_JUIZ,
)
from dashboard.services.revisao import (  # noqa: E402
    listar_suspeitos, _resolver_pasta, _localizar_arquivo,
    _carregar_decisoes, _salvar_decisoes, _chave_decisao, _registrar,
    PROCESSED, DESCLASSIFICADOS, _mover_arquivo,
)
from dashboard.services.sanitizar_suspeitos import (  # noqa: E402
    limpar_texto, controle, set_controle,
)

PROGRESSO = PROJETO_ROOT / "logs" / "juiz_progresso.json"


def _progresso(d: dict) -> None:
    try:
        PROGRESSO.parent.mkdir(parents=True, exist_ok=True)
        PROGRESSO.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _coletar_pendentes() -> list[dict]:
    """Retorna os suspeitos pendentes: [{pasta, arquivo, caminho}]."""
    dados = listar_suspeitos()
    pendentes = []
    for p in dados.get("pastas", []):
        for it in p.get("itens", []):
            if it.get("existe") and it.get("caminho"):
                pendentes.append({
                    "pasta": p["pasta"], "arquivo": it["arquivo"],
                    "caminho": it["caminho"],
                })
    return pendentes


def _decidir_arquivo(caminho: str, pasta: str, arquivo: str) -> str:
    """Limpa o texto (TODAS as ferramentas) e roda camada 1 + juiz.

    Regra 18/08: as ferramentas de depuração (ANSI/mojibake/ABNT/espaços)
    passam ANTES do juiz — o juiz analisa só texto limpo."""
    caminho_p = Path(caminho)
    texto = caminho_p.read_text(encoding="utf-8", errors="replace")
    # 🧹 limpeza em cadeia (limpar_ansi → mojibake → ABNT → emojis → espaços)
    texto_limpo, stats = limpar_texto(texto)
    if texto_limpo != texto:
        try:
            caminho_p.write_text(texto_limpo, encoding="utf-8")
            _registrar(f"🧹 Limpo antes do juiz: {pasta}/{arquivo} "
                       f"(ansi={stats['ansi']} abnt={stats['abnt']} "
                       f"mojibake={stats['mojibake']})")
        except Exception:
            pass
        texto = texto_limpo
    m = _metricas(texto)
    pontos = _pontuar(m)
    classe = _classificar(pontos)

    # camada 2: juiz nos suspeitos (e nos lixos de borda, para confirmar)
    if classe in ("suspeito", "lixo"):
        juiz = _juiz_ollama(texto, MODELO_JUIZ)
        if juiz.get("ok"):
            if juiz.get("aprovado"):
                classe = "aprovado"
            elif classe == "suspeito":
                # juiz não aprovou: lixo se pontos altos, senão segue suspeito
                classe = "lixo" if pontos >= 4 else "suspeito"
            # lixo confirmado pelo juiz → continua lixo

    # move conforme o veredito
    caminho_pasta = _resolver_pasta(pasta)
    origem = Path(caminho)
    if classe == "aprovado" and caminho_pasta:
        destino_dir = PROCESSED / f"{caminho_pasta.name}_aprovado"
        ok, msg = _mover_arquivo(origem, destino_dir)
        if ok:
            _registrar(f"✅ Juiz APROVOU: {pasta}/{arquivo} → {msg}")
            _registrar_decisao(pasta, arquivo, "aprovar", msg)
    elif classe == "lixo" and caminho_pasta:
        destino_dir = DESCLASSIFICADOS / caminho_pasta.name
        ok, msg = _mover_arquivo(origem, destino_dir)
        if ok:
            _registrar(f"❌ Juiz REPROVOU (lixo): {pasta}/{arquivo} → {msg}")
            _registrar_decisao(pasta, arquivo, "descartar", msg)
    return classe


def _registrar_decisao(pasta: str, arquivo: str, acao: str, destino: str) -> None:
    """Registra a decisão do juiz para o item sumir da lista."""
    decisoes = _carregar_decisoes()
    decisoes[_chave_decisao(pasta, arquivo)] = {
        "acao": acao, "data": datetime.now().isoformat(timespec="seconds"),
        "destino": destino, "juiz": MODELO_JUIZ,
    }
    _salvar_decisoes(decisoes)


def main() -> int:
    ap = argparse.ArgumentParser(description="Juiz nos suspeitos pendentes")
    ap.add_argument("--pasta", default="", help="Só esta pasta (nome relativo)")
    ap.add_argument("--limite", type=int, default=None, help="Máx. de arquivos (teste)")
    ap.add_argument("--seco", action="store_true", help="Sem confirmação")
    args = ap.parse_args()

    # pré-checagens (regra do guardião)
    ok, liv = _memoria_ok()
    if not ok:
        print(f"❌ Memória livre {liv:.1f} GB < 6 GB — o juiz NÃO pode rodar agora. "
              "Feche outros programas e tente de novo.")
        return 2
    if not _modelo_instalado(MODELO_JUIZ):
        print(f"❌ Modelo '{MODELO_JUIZ}' não encontrado no Ollama. "
              f"Rode: ollama pull {MODELO_JUIZ}")
        return 2

    pendentes = _coletar_pendentes()
    if args.pasta:
        pendentes = [p for p in pendentes if p["pasta"] == args.pasta]
    if args.limite:
        pendentes = pendentes[: args.limite]

    if not pendentes:
        print("✅ Nenhum suspeito pendente para o juiz revisar.")
        return 0

    print(f"⚖️ Juiz ({MODELO_JUIZ}) vai revisar {len(pendentes)} suspeito(s)...")
    print(f"   Memória livre: {liv:.1f} GB | Modelo: OK")
    if not args.seco:
        r = input("   Começar? [s/N] ").strip().lower()
        if r != "s":
            print("Cancelado.")
            return 0

    # limpa controles de pausa/parada de execuções anteriores
    set_controle(pausado=False, parar=False)

    # grava o PID no progresso (o painel detecta processo vivo mesmo com --reload)
    try:
        import os as _os
        _progresso({"pid": _os.getpid(), "pct": 0, "atual": "iniciando",
                    "atualizado": datetime.now().isoformat()})
    except Exception:
        pass

    resumo = {"aprovados": 0, "descartados": 0, "suspeitos": 0, "erros": 0}
    for i, p in enumerate(pendentes, 1):
        # ⏸️ pausa / ⏹️ parada (botões do painel /revisar)
        while controle().get("pausado") and not controle().get("parar"):
            time.sleep(2)
        if controle().get("parar"):
            set_controle(parar=False)
            print("⏹️ Parado pelo usuário.")
            _progresso({"pct": 0, "parado": True, **resumo,
                        "atualizado": datetime.now().isoformat()})
            return 0
        try:
            classe = _decidir_arquivo(p["caminho"], p["pasta"], p["arquivo"])
            if classe == "aprovado":
                resumo["aprovados"] += 1
            elif classe == "lixo":
                resumo["descartados"] += 1
            elif classe == "suspeito":
                resumo["suspeitos"] += 1
            print(f"  [{i}/{len(pendentes)}] {classe.upper():<9} {p['arquivo']}")
        except Exception as e:
            resumo["erros"] += 1
            print(f"  [{i}/{len(pendentes)}] ERRO {p['arquivo']}: {e}")
        _progresso({
            "pct": round(100 * i / len(pendentes), 1), "atual": p["arquivo"],
            "i": i, "total": len(pendentes), **resumo,
            "atualizado": datetime.now().isoformat(),
        })

    print(f"\n🏁 FIM: {resumo['aprovados']} aprovados ✅ | "
          f"{resumo['descartados']} lixo descartado ❌ | "
          f"{resumo['suspeitos']} seguem suspeitos 🟡 | "
          f"{resumo['erros']} erros")
    _progresso({"pct": 100, "fim": True, **resumo,
                "atualizado": datetime.now().isoformat()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
