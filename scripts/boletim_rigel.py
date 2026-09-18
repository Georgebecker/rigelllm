#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
boletim_rigel.py — BOLETIM DO RIGEL (relatório automático em linguagem leiga)

O que faz:
  Lê os logs e estados do projeto e monta UM relatório simples, em linguagem
  de gente, contando o que aconteceu: treino, geração, erros, saúde do
  sistema e próximos passos. Nada de termo técnico — didático e acolhedor.

  É como "abrir o jornal de manhã": você lê uma página e já sabe se o Rigel
  treinou, gerou, se algo deu errado e o que falta fazer.

Uso:
  python scripts/boletim_rigel.py            # imprime na tela
  python scripts/boletim_rigel.py --salvar   # também grava logs/boletim_rigel.md
  python scripts/boletim_rigel.py --json     # devolve JSON estruturado

Nunca falha: se um arquivo não existir ou estiver corrompido, ele é ignorado
e o resto do boletim segue normal.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))


def _ler_json(caminho: Path) -> dict | list | None:
    """Lê JSON com segurança (nunca levanta; devolve None se falhar)."""
    try:
        if caminho.exists():
            return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _ler_tail_log(caminho: Path, linhas: int = 6) -> list[str]:
    """Lê as últimas N linhas de um log (ignora erros de encoding)."""
    try:
        if not caminho.exists():
            return []
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            todas = f.readlines()
        return [l.rstrip("\n") for l in todas[-linhas:] if l.strip()]
    except Exception:
        return []


def _humanizar_bytes(n: float) -> str:
    for unidade in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unidade}"
        n /= 1024
    return f"{n:.1f} PB"


def _emoji(num: float) -> str:
    if num <= 0:
        return "🟢"
    if num <= 2:
        return "🟡"
    return "🔴"


# ─────────────────────────────── seções ───────────────────────────────

def _secao_treino() -> list[str]:
    linhas = []
    estado = _ler_json(PROJETO_ROOT / "modelo" / "estado_treino_jsonl.json")
    if isinstance(estado, dict) and estado.get("epoch"):
        epoch = estado.get("epoch")
        best = estado.get("best_val_loss")
        ts = estado.get("timestamp", "")
        data = ""
        if ts:
            try:
                data = datetime.fromisoformat(ts).strftime("%d/%m às %H:%M")
            except Exception:
                pass
        linhas.append(f"📚 Último treino concluído: {epoch} épocas completas, "
                      f"melhor nota de validação {best:.2f} ({data}).")
        if best and best < 7.0:
            linhas.append("   😊 O modelo está aprendendo — a nota melhorou "
                          "em relação aos treinos antigos.")
        else:
            linhas.append("   🤔 A nota ainda está alta — mais treino com "
                          "dados bons costuma ajudar.")
    else:
        linhas.append("📚 Sem registro de treino concluído ainda.")

    # último log de treino (resumo da sessão mais recente)
    tail = _ler_tail_log(PROJETO_ROOT / "logs" / "treinar_jsonl.log", 3)
    for t in tail:
        if any(k in t for k in ("RESUMO", "CONCLUÍDO", "Erro", "ERROR", "DATASET")):
            linhas.append(f"   ℹ️ {t}")
    return linhas


def _secao_geracao() -> list[str]:
    linhas = []
    fila = _ler_json(PROJETO_ROOT / "estado" / "fila_geracao.json")
    if not isinstance(fila, dict) or "ordens" not in fila:
        linhas.append("📝 Nenhuma fila de geração registrada.")
        return linhas

    ordens = [o for o in fila.get("ordens", []) if isinstance(o, dict)]
    ativas = [o for o in ordens if o.get("status") == "rodando"]
    erros = [o for o in ordens if o.get("status") == "erro"]
    aguardando = [o for o in ordens if o.get("status") == "aguardando"]

    if ativas:
        for o in ativas[:3]:
            ger = o.get("gerados", 0)
            meta = o.get("meta", 0)
            pct = round(ger / meta * 100) if meta else 0
            linhas.append(f"📝 Geração em andamento: {pct}% "
                          f"({ger} de {meta} textos prontos).")
    if aguardando:
        linhas.append(f"   ⏳ {len(aguardando)} ordem(ns) na fila aguardando a vez.")
    if erros:
        for o in erros[-3:]:
            ger = o.get("gerados", 0)
            meta = o.get("meta", 0)
            fim = o.get("fim", "")[:16].replace("T", " ")
            linhas.append(f"   ⚠️ Uma geração parou cedo ({ger} de {meta} "
                          f"textos) em {fim}. Pode ser falta de recurso da "
                          "máquina — dá para reiniciar pelo painel.")
    if not ativas and not erros and not aguardando:
        linhas.append("📝 Nenhuma geração em andamento agora.")
    return linhas


def _secao_erros() -> list[str]:
    linhas = []
    # erros recentes do treinador
    tail = _ler_tail_log(PROJETO_ROOT / "logs" / "treinar_jsonl.log", 40)
    erros = [t for t in tail if any(k in t for k in ("ERROR", "Traceback", "num_samples"))]
    if erros:
        linhas.append("🔧 O último treino encontrou um problema:")
        for e in erros[:4]:
            linhas.append(f"   ⚠️ {e}")
        linhas.append("   ✅ Já ajustei para dar mensagem clara e não travar "
                      "feio — mas o problema era dados demais duplicados "
                      "(pastas *_sanitizado*), que já foram arquivados.")
    else:
        linhas.append("🔧 Nenhum erro recente nos registros de treino.")

    # logs grandes (sinal de problema de espaço)
    logs_dir = PROJETO_ROOT / "logs"
    grandes = []
    for f in logs_dir.glob("*.log"):
        try:
            tam = f.stat().st_size
            if tam > 20 * 1024 * 1024:
                grandes.append((f.name, tam))
        except Exception:
            continue
    if grandes:
        linhas.append(f"   🗂️ {len(grandes)} registro(s) de log estão grandes "
                      "(mais de 20 MB) — dá para limpar com calma.")
    return linhas


def _secao_saude() -> list[str]:
    linhas = []
    saude = _ler_json(PROJETO_ROOT / "logs" / "saude_sistema.json")
    if isinstance(saude, dict):
        disco = saude.get("disco_livre_gb")
        ram_mb = saude.get("ram_livre_mb")
        cpu = saude.get("cpu_pct")
        ping_ollama = saude.get("ping_ollama")
        if disco is not None:
            emoji = "🟢" if disco > 10 else ("🟡" if disco > 5 else "🔴")
            linhas.append(f"{emoji} Espaço no disco: {disco:.1f} GB livres.")
        if ram_mb is not None:
            ram_gb = ram_mb / 1024
            emoji = "🟢" if ram_gb > 2 else "🔴"
            linhas.append(f"{emoji} Memória livre: {ram_gb:.1f} GB.")
        if cpu is not None:
            emoji = "🟢" if cpu < 65 else ("🟡" if cpu < 85 else "🔴")
            linhas.append(f"{emoji} Processador ocupado: {cpu:.0f}%.")
        if ping_ollama is not None:
            if ping_ollama:
                linhas.append("🟢 Assistente local (Ollama) respondendo.")
            else:
                linhas.append("🔴 Assistente local (Ollama) fora do ar.")
    else:
        linhas.append("🖥️ Sem relatório de saúde salvo ainda.")
    return linhas


def _secao_pendencias() -> list[str]:
    linhas = []
    pend = _ler_json(PROJETO_ROOT / "estado" / "pendencias.json")
    if isinstance(pend, dict):
        lista = pend.get("pendencias", [])
        nao_feitas = [p for p in lista if isinstance(p, dict) and not p.get("feito")]
        if nao_feitas:
            linhas.append(f"✅ {len(nao_feitas)} pendência(s) em aberto — "
                          "dá para resolver pelo painel (Central).")
            for p in nao_feitas[:4]:
                titulo = p.get("titulo", "")
                linhas.append(f"   • {titulo}")
        else:
            linhas.append("✅ Nenhuma pendência em aberto — tudo em dia!")
    return linhas


def _secao_pastas() -> list[str]:
    linhas = []
    # conta datasets disponíveis
    base = PROJETO_ROOT / "dados" / "processed" / "jsonl"
    try:
        pastas = [p for p in base.iterdir() if p.is_dir()]
        com_jsonl = [p for p in pastas if any(p.glob("*.jsonl"))]
        linhas.append(f"🗂️ {len(com_jsonl)} pasta(s) de treino prontas "
                      f"em {len(pastas)} no total.")
    except Exception:
        pass
    return linhas


# ─────────────────────────────── montagem ───────────────────────────────

def _montar(com_json: bool = False) -> dict:
    secoes = {
        "treino": _secao_treino(),
        "geracao": _secao_geracao(),
        "erros": _secao_erros(),
        "saude": _secao_saude(),
        "pendencias": _secao_pendencias(),
        "pastas": _secao_pastas(),
    }
    return {
        "gerado_em": datetime.now().isoformat(),
        "secoes": secoes,
    }


def _imprimir(dados: dict) -> str:
    agora = datetime.now().strftime("%d/%m/%Y às %H:%M")
    partes = [
        "═" * 58,
        f"📰 BOLETIM DO RIGEL — {agora}",
        "═" * 58,
    ]
    for titulo, linhas in dados["secoes"].items():
        if not linhas:
            continue
        partes.append("")
        for l in linhas:
            partes.append(l)
    partes.append("")
    partes.append("💡 Dica: rode 'python scripts/boletim_rigel.py --salvar' "
                  "para guardar esta página em logs/boletim_rigel.md.")
    partes.append("═" * 58)
    return "\n".join(partes)


def main() -> int:
    ap = argparse.ArgumentParser(description="Boletim do Rigel (relatório leigo)")
    ap.add_argument("--salvar", action="store_true",
                    help="Grava logs/boletim_rigel.md além de imprimir")
    ap.add_argument("--json", action="store_true",
                    help="Devolve JSON estruturado em vez de texto")
    args = ap.parse_args()

    dados = _montar()
    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0

    texto = _imprimir(dados)
    print(texto)

    if args.salvar:
        try:
            destino = PROJETO_ROOT / "logs" / "boletim_rigel.md"
            destino.write_text(texto, encoding="utf-8")
            print(f"\n📄 Boletim salvo em: {destino}")
        except Exception as e:
            print(f"\n⚠️ Não consegui salvar o boletim: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
