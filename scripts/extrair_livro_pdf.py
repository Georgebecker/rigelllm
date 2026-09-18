# -*- coding: utf-8 -*-
"""
extrair_livro_pdf.py — Extrai texto de livros PDF usando pdfplumber (ferramenta
madura/gratuita) com filtro por POSIÇÃO na página — genérico para qualquer livro.

Por que pdfplumber em vez de regex:
    - Cada livro tem layout diferente; regex de texto específico só serve para um.
    - pdfplumber dá as coordenadas de cada linha. Em livros com margem padrão,
      o conteúdo real fica entre as margens; headers/footers/nº de página e
      "lixo de impressão" ficam nas bordas (topo/base). Cortar por posição
      funciona para QUALQUER livro, sem conhecer o texto.

Uso:
    python scripts/extrair_livro_pdf.py --pdf dados/raw/livros/X.pdf
        [--saida dados/gerados/txt_livros/X.txt]
        [--margem-topo 0.08] [--margem-base 0.88]
        [--min-chars-linha 3]

Ajustes por livro (se um livro tiver margens maiores/menores):
    --margem-topo: fração da altura da página a descartar no topo (default 0.08).
    --margem-base: fração a partir da qual descarta na base (default 0.88).
"""

import argparse
import re
import sys
from pathlib import Path


def extrair(pdf: Path, margem_topo: float, margem_base: float, min_chars: int) -> str:
    import pdfplumber

    paginas = []
    with pdfplumber.open(str(pdf)) as doc:
        for page in doc.pages:
            h = page.height
            linhas = page.extract_text_lines()
            selecionadas = []
            for ln in linhas:
                top = ln["top"] / h
                texto = (ln.get("text") or "").strip()
                if top < margem_topo or top > margem_base:
                    continue
                if len(texto) < min_chars:
                    continue
                selecionadas.append(texto)
            if selecionadas:
                paginas.append("\n".join(selecionadas))
    return "\n\n".join(paginas).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Extrai texto de livro PDF (pdfplumber + posição).")
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--saida", default="")
    ap.add_argument("--margem-topo", type=float, default=0.08)
    ap.add_argument("--margem-base", type=float, default=0.88)
    ap.add_argument("--min-chars-linha", type=int, default=3)
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"ERRO: PDF não encontrado: {pdf}", file=sys.stderr)
        return 1

    try:
        texto = extrair(pdf, args.margem_topo, args.margem_base, args.min_chars_linha)
    except Exception as e:
        print(f"ERRO ao extrair: {e}", file=sys.stderr)
        return 1

    if len(texto) < 500:
        print(f"⚠️  Texto curto demais ({len(texto)} chars) — ajuste --margem-topo/--margem-base "
              f"para este livro (ou é um PDF escaneado, sem camada de texto).", file=sys.stderr)
        return 2

    saida = args.saida or str(pdf.parent / (pdf.stem + "_limpo.txt"))
    Path(saida).parent.mkdir(parents=True, exist_ok=True)
    Path(saida).write_text(texto, encoding="utf-8")
    palavras = len(re.findall(r"\b\w+\b", texto))
    print(f"OK: {len(texto):,} chars | {palavras:,} palavras | {pdf.name}")
    print(f"Saída: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
