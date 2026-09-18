# -*- coding: utf-8 -*-
"""
preparar_colab.py — Monta o pacote de treino para o Google Colab.

Junta em UM jsonl (schema padrão do Rigel):
  1. O material da FILA AJUIZADO (classe 'aprovado' no relatório do ajuizador)
  2. Os LIVROS (dados/gerados/jsonl/livros/*.jsonl)

Uso:
    python scripts/preparar_colab.py [--saida dados/gerados/colab/rigel_colab.jsonl]

Saída: jsonl com exemplos únicos (dedup por pergunta) + resumo impresso.
"""

import argparse
import glob
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJETO = Path(__file__).resolve().parent.parent
REPORT = PROJETO / "logs" / "ajuizar_relatorio.json"
LIVROS = PROJETO / "dados" / "gerados" / "jsonl" / "livros"


def _extrair_qa_txt(texto: str):
    """Extrai (pergunta, resposta) de um txt da fila (#PERGUNTA/#ASSUNTO + texto)."""
    m = re.search(r"#PERGUNTA:\s*(.+)", texto)
    pergunta = m.group(1).strip() if m else ""
    # remove linhas de metadados (#...) e pega o restante como resposta
    linhas = []
    for l in texto.splitlines():
        s = l.strip()
        if not s or s.startswith("#"):
            continue
        linhas.append(s)
    resposta = " ".join(linhas).strip()
    return pergunta, resposta


def _carregar_aprovados() -> list[dict]:
    """Lista de (arquivo, caminho) aprovados no relatório do ajuizador."""
    if not REPORT.exists():
        print("⚠️ Relatório do ajuizador não encontrado — sem material da fila.")
        return []
    d = json.loads(REPORT.read_text(encoding="utf-8"))
    aprovados = []
    for p in d.get("pastas", []):
        base = PROJETO / "dados" / "gerados" / p.get("pasta", "")
        for a in p.get("arquivos", []):
            if a.get("classe") == "aprovado":
                aprovados.append({"arquivo": a["arquivo"], "base": base})
    return aprovados


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepara pacote de treino para o Colab.")
    ap.add_argument("--saida", default=str(PROJETO / "dados" / "gerados" / "colab" / "rigel_colab.jsonl"))
    ap.add_argument("--max-fila", type=int, default=None, help="Limite de exemplos da fila.")
    args = ap.parse_args()

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)

    sistema = "Você é o Rigel, um assistente em português brasileiro."
    vistos = set()
    total = 0
    fila_n = 0
    livros_n = 0
    duplicatas = 0

    def gravar(pergunta, resposta, fonte, categoria):
        nonlocal total, duplicatas
        if not pergunta or not resposta or len(resposta) < 40:
            return
        if pergunta in vistos:
            duplicatas += 1
            return
        vistos.add(pergunta)
        ex = {
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": pergunta},
                {"role": "assistant", "content": resposta},
            ],
            "_fonte": fonte,
            "_tipo": "fila" if fonte.startswith("fila") else "artigo",
            "_categoria": categoria,
            "_idioma": "pt-BR",
            "_data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return ex

    exemplos = []

    # 1) Fila aprovada
    for item in _carregar_aprovados():
        p = item["base"] / item["arquivo"]
        if not p.exists():
            continue
        try:
            texto = p.read_text(encoding="utf-8")
        except Exception:
            continue
        pergunta, resposta = _extrair_qa_txt(texto)
        if not pergunta or not resposta:
            continue
        if fila_n >= (args.max_fila if args.max_fila else 10**9):
            break
        pergunta_key = pergunta.strip().lower()
        if pergunta_key in vistos:
            duplicatas += 1
            continue
        vistos.add(pergunta_key)
        exemplos.append({
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": pergunta},
                         {"role": "assistant", "content": resposta}],
            "_fonte": f"fila:{item['arquivo'][:40]}",
            "_tipo": "fila",
            "_categoria": "massa_final",
            "_idioma": "pt-BR",
            "_data": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        fila_n += 1

    # 2) Livros
    for arq in sorted(glob.glob(str(LIVROS / "*.jsonl"))):
        for l in open(arq, encoding="utf-8"):
            try:
                e = json.loads(l)
            except Exception:
                continue
            msgs = e.get("messages", [])
            user = next((m.get("content", "") for m in msgs if m.get("role") == "user"), "")
            assist = next((m.get("content", "") for m in msgs if m.get("role") == "assistant"), "")
            key = user.strip().lower()
            if not key or key in vistos:
                duplicatas += 1
                continue
            vistos.add(key)
            e["_fonte"] = f"livro:{Path(arq).stem}"
            exemplos.append(e)
            livros_n += 1

    # grava
    with saida.open("w", encoding="utf-8") as f:
        for e in exemplos:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"✅ Pacote Colab pronto: {saida}")
    print(f"   fila aprovada: {fila_n} | livros: {livros_n} | TOTAL: {len(exemplos)} | duplicatas: {duplicatas}")
    print(f"   tamanho: {round(saida.stat().st_size/1e6,1)} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
