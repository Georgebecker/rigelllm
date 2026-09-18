#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# converter_jsonl_txt.py — extrai TEXTO de jsonl de pré-treino → arquivos .txt
# Data: 19/08/2026
# ============================================================================
# Lê linhas {"text": "..."} (pré-treino) e gera arquivos .txt em <saida>/
# (para o pipeline de PRÉ-TREINO — treinov2 usa pastas de .txt). Limpa o
# texto com o sanitizador do projeto e descarta lixo.
#
# Uso:
#   python scripts/converter_jsonl_txt.py \
#       --origem <pasta-ou-arquivo.jsonl> \
#       --saida  <pasta-destino-txt>
# ============================================================================
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sanitizador_ptbr import (  # noqa: E402
    corrigir_mojibake_inteligente,
    remover_invalidos,
    avaliar_conteudo,
)

TEXTOS_POR_ARQUIVO = 500
LOG_PROGRESSO = os.path.join("logs", "converter_jsonl_txt_progresso.json")


def _tratar_texto(texto: str):
    """Tratamento completo (mojibake + inválidos + elimina lixo)."""
    if not texto:
        return None
    corrigido = corrigir_mojibake_inteligente(str(texto))
    limpo, n_removidos = remover_invalidos(corrigido)
    status, _motivo = avaliar_conteudo(limpo, n_removidos)
    if status == "descartado":
        return None
    final = " ".join(limpo.split()).strip()
    return final or None


def _extrair_texto(obj) -> str | None:
    """Pega o texto de pré-treino de uma linha (text/prompt/answer/content)."""
    if not isinstance(obj, dict):
        return None
    txt = obj.get("text")
    if txt:
        return str(txt)
    # fallback: junta prompt+answer (caso não seja messages)
    p = obj.get("prompt") or obj.get("instruction") or obj.get("pergunta")
    a = obj.get("answer") or obj.get("output") or obj.get("resposta") or obj.get("completion")
    if p and a:
        return f"{p}\n{a}"
    return None


def _progresso(**kw) -> None:
    kw["atualizado_em"] = time.strftime("%H:%M:%S")
    try:
        os.makedirs("logs", exist_ok=True)
        with open(LOG_PROGRESSO, "w", encoding="utf-8") as f:
            json.dump(kw, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origem", required=True)
    ap.add_argument("--saida", required=True)
    ap.add_argument("--max-linhas", type=int, default=0)
    args = ap.parse_args()

    origem = Path(args.origem)
    saida = Path(args.saida)
    if not origem.exists():
        print(f"ERRO: origem não encontrada: {origem}")
        return 1
    saida.mkdir(parents=True, exist_ok=True)

    if origem.is_dir():
        arquivos = sorted(p for p in origem.rglob("*")
                          if p.is_file() and p.suffix.lower() in (".jsonl", ".json"))
    else:
        arquivos = [origem]
    if not arquivos:
        print("Nenhum arquivo .jsonl/.json encontrado.")
        return 1
    print(f"Arquivos de origem: {len(arquivos)}")

    lidas = validas = invalidas = 0
    arquivo_atual = 0
    buff: list = []
    t0 = time.time()

    def _flush(ultimo: bool = False) -> None:
        nonlocal arquivo_atual, buff
        if not buff:
            return
        arquivo_atual += 1
        destino = saida / f"{args.saida.replace(os.sep, '_').replace('\\\\', '_').replace('/', '_')}__{arquivo_atual:05d}.txt"
        with open(destino, "w", encoding="utf-8") as f:
            f.write("\n\n".join(buff) + "\n")
        buff = []

    for arq in arquivos:
        with open(arq, encoding="utf-8", errors="replace") as f:
            for linha in f:
                lidas += 1
                if args.max_linhas and lidas > args.max_linhas:
                    break
                linha = linha.strip()
                if not linha:
                    invalidas += 1
                    continue
                try:
                    obj = json.loads(linha)
                except Exception:
                    invalidas += 1
                    continue
                texto = _tratar_texto(_extrair_texto(obj))
                if not texto or len(texto) < 20:
                    invalidas += 1
                    continue
                validas += 1
                buff.append(texto)
                if len(buff) >= TEXTOS_POR_ARQUIVO:
                    _flush()
                if lidas % 100_000 == 0:
                    print(f"  {lidas:,} lidas | textos válidos: {validas:,} | descartados: {invalidas:,} | {time.time() - t0:.0f}s")
                    _progresso(lidas=lidas, validas=validas, invalidas=invalidas)
        if args.max_linhas and lidas > args.max_linhas:
            break

    _flush(ultimo=True)
    print("=" * 60)
    print(f"CONCLUÍDO: {lidas:,} lidas | {validas:,} textos | {invalidas:,} descartados")
    print(f"Saída: {arquivo_atual} arquivo(s) .txt em {saida}")
    _progresso(lidas=lidas, validas=validas, invalidas=invalidas, concluido=True,
               saida=str(saida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
