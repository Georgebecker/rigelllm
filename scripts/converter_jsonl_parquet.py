#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
converter_jsonl_parquet.py — Converte .jsonl para .parquet (schema de treino).

Saída (mesmo schema do limpeza_leve / scrap / rigel_sft.parquet):
  - rigel_sft.parquet       → coluna `messages` = list<struct<role, content>> (SFT)
  - rigel_pretrain.parquet  → coluna `text` (pretrain: user + assistant concatenados)

NUNCA apaga nada: lê os .jsonl e escreve os .parquet na pasta de saída.
Reutilizável: aceita 1 arquivo ou pasta (varre recursivamente *.jsonl).

Uso:
  python scripts/converter_jsonl_parquet.py [--origem dados/gerados/massa_final]
      [--saida dados/processed/parquet_massa] [--nome base]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))


def _coletar_jsonl(origem: Path) -> list[Path]:
    if origem.is_file():
        return [origem] if origem.suffix.lower() == ".jsonl" else []
    if origem.is_dir():
        return sorted(origem.rglob("*.jsonl"))
    return []


def _extrair_messages(ex: dict) -> list[dict] | None:
    msgs = ex.get("messages")
    if isinstance(msgs, list) and msgs:
        turnos = []
        for m in msgs:
            if isinstance(m, dict) and m.get("role") and m.get("content"):
                turnos.append({"role": str(m["role"]), "content": str(m["content"])})
        if turnos:
            return turnos
    # formatos alternativos (conversations/chat)
    for chave in ("conversations", "chat"):
        lista = ex.get(chave)
        if isinstance(lista, list) and lista:
            turnos = []
            for m in lista:
                if not isinstance(m, dict):
                    continue
                role = m.get("role") or m.get("from") or ""
                content = m.get("content") or m.get("value") or ""
                if role and content:
                    turnos.append({"role": str(role), "content": str(content)})
            if turnos:
                return turnos
    return None


def _texto_pretrain(msgs: list[dict]) -> str:
    """Texto corrido p/ pretrain: ignora system, junta user+assistant."""
    partes = []
    for m in msgs:
        if m["role"] in ("user", "assistant", "human", "gpt", "modelo", "system"):
            partes.append(m["content"])
    return "\n\n".join(p for p in partes if p)


def converter(origem: Path, saida: Path, nome: str) -> dict:
    """Lê jsonl → grava rigel_sft.parquet + rigel_pretrain.parquet."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    arquivos = _coletar_jsonl(origem)
    if not arquivos:
        return {"arquivos": 0, "exemplos": 0, "sft": "", "pretrain": ""}

    linhas_sft: list[dict] = []
    linhas_pretrain: list[dict] = []
    exemplos = 0
    for arq in arquivos:
        for l in arq.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            try:
                ex = json.loads(l)
            except Exception:
                continue
            msgs = _extrair_messages(ex)
            if not msgs:
                continue
            exemplos += 1
            linhas_sft.append({"messages": msgs})
            linhas_pretrain.append({"text": _texto_pretrain(msgs)})

    if not linhas_sft:
        return {"arquivos": len(arquivos), "exemplos": 0, "sft": "", "pretrain": ""}

    saida.mkdir(parents=True, exist_ok=True)

    # SFT — mesmo schema do limpeza_leve (messages = list<struct<role, content>>)
    campo_role = pa.field("role", pa.string())
    campo_content = pa.field("content", pa.string())
    struct_turno = pa.struct([campo_role, campo_content])
    schema = pa.schema([pa.field("messages", pa.list_(struct_turno))])
    arrays = [[{"role": m["role"], "content": m["content"]} for m in e["messages"]]
              for e in linhas_sft]
    tabela = pa.Table.from_arrays([pa.array(arrays, type=pa.list_(struct_turno))],
                                  schema=schema)
    sft_path = saida / f"{nome}_sft.parquet"
    pq.write_table(tabela, str(sft_path))

    # Pretrain
    pretrain_path = saida / f"{nome}_pretrain.parquet"
    pq.write_table(pa.table({"text": [e["text"] for e in linhas_pretrain]}),
                   str(pretrain_path))

    return {"arquivos": len(arquivos), "exemplos": exemplos,
            "sft": str(sft_path), "pretrain": str(pretrain_path)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Converte .jsonl → .parquet (SFT+pretrain)")
    ap.add_argument("--origem", default="dados/gerados/massa_final",
                    help="Arquivo ou pasta com .jsonl")
    ap.add_argument("--saida", default="dados/processed/parquet_massa",
                    help="Pasta de saída dos .parquet")
    ap.add_argument("--nome", default="massa",
                    help="Nome base dos arquivos (massa → massa_sft.parquet)")
    args = ap.parse_args()

    res = converter(Path(args.origem), Path(args.saida), args.nome)
    print(f"📂 arquivos lidos: {res['arquivos']}")
    print(f"📦 exemplos (com messages): {res['exemplos']}")
    if res["sft"]:
        import pyarrow.parquet as pq
        print(f"  ✅ SFT: {res['sft']} — "
              f"{pq.ParquetFile(res['sft']).metadata.num_rows} linhas")
        print(f"  ✅ Pretrain: {res['pretrain']} — "
              f"{pq.ParquetFile(res['pretrain']).metadata.num_rows} linhas")
    else:
        print("⚠️ Nenhum exemplo válido (sem messages) — nada gravado.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
