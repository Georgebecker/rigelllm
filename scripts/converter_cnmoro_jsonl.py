#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# converter_cnmoro_jsonl.py — cnmoro (prompt/thought/answer) → messages (SFT)
# Data: 19/08/2026
# ============================================================================
# Converte o dataset.jsonl BRUTO do cnmoro para o formato que o treinador SFT
# aceita:
#   {"messages": [{"role": "user", "content": "..."},
#                 {"role": "assistant", "content": "..."}]}
#
# - Descarta o raciocínio 'thought' (decisão do usuário — mesmo critério do
#   scripts/tratar_parquet_grande.py).
# - Limpa mojibake real (duplo-encoding; NUNCA "Ã" solto — falso positivo).
# - Dedup por md5 (conjunto LIMITADO p/ não estourar RAM com ~20M de linhas).
# - Streaming: memória constante (lê linha, escreve linha) + progresso REAL
#   persistido em logs/converter_cnmoro_progresso.json (regra de ouro).
# - Saída em lotes de EXEMPLOS_POR_ARQUIVO (padrão do projeto).
#
# Uso:
#   python scripts/converter_cnmoro_jsonl.py \
#       --origem dados/gerados/jsonl/cnmoro_reasoning-v1-20m-portuguese/dataset.jsonl \
#       --saida  dados/processed/jsonl/cnmoro_sanitizado
# ============================================================================
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# Apenas combinações REAIS de duplo-encoding (lição: "Ã" solto = falso positivo
# com SÃO/MÃE/CÃES).
_MOJIBAKE_FIX = {
    "Ã£": "ã", "Ã©": "é", "Ãª": "ê", "Ã§": "ç", "Ã³": "ó", "Ã¡": "á",
    "Ã­": "í", "Ã¼": "ü", "Ã´": "ô", "Ã¢": "â", "Ãµ": "õ", "Ã¨": "è",
    "Ã²": "ò", "Ã±": "ñ", "Ãº": "ú",
    "â€œ": '"', "â€\u009d": '"', "â€™": "'", "â€“": "–", "â€”": "—",
    "â€¦": "...", "\ufffd": "",
}

MAX_DEDUP = 1_000_000          # teto do conjunto de hashes (memória constante)
EXEMPLOS_POR_ARQUIVO = 2000    # exemplos por arquivo .jsonl de saída
MIN_CAMPO_CHARS = 5            # pergunta/resposta com menos que isso = lixo
LOG_PROGRESSO = os.path.join("logs", "converter_cnmoro_progresso.json")


def _limpar_leve(texto: str) -> str:
    """Corrige mojibake real + normaliza espaços (rápido, str.replace)."""
    for antigo, novo in _MOJIBAKE_FIX.items():
        if antigo in texto:
            texto = texto.replace(antigo, novo)
    return " ".join(texto.split()).strip()


def _tratar_linha(obj: dict, vistos: set):
    """prompt/answer → messages (descarta thought). None se lixo/duplicado."""
    if not isinstance(obj, dict):
        return None
    # Já vem no formato certo? Aproveita sem re-converter.
    msgs = obj.get("messages")
    if isinstance(msgs, list) and msgs:
        return obj
    prompt = str(obj.get("prompt") or "").strip()
    answer = str(obj.get("answer") or "").strip()
    if not prompt or not answer:
        return None
    prompt = _limpar_leve(prompt)
    answer = _limpar_leve(answer)
    if len(prompt) < MIN_CAMPO_CHARS or len(answer) < MIN_CAMPO_CHARS:
        return None
    chave = hashlib.md5((prompt + "\x01" + answer).encode("utf-8", "replace")).hexdigest()
    if chave in vistos:
        return None
    if len(vistos) < MAX_DEDUP:
        vistos.add(chave)
    return {"messages": [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": answer},
    ]}


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
    ap.add_argument("--origem", required=True, help="dataset.jsonl bruto do cnmoro")
    ap.add_argument("--saida", required=True, help="pasta de saída (messages)")
    ap.add_argument("--max-linhas", type=int, default=0, help="limita p/ teste")
    args = ap.parse_args()

    origem = Path(args.origem)
    saida = Path(args.saida)
    if not origem.exists():
        print(f"ERRO: origem não encontrada: {origem}")
        return 1
    saida.mkdir(parents=True, exist_ok=True)

    # Conta linhas antes (barra de % REAL — regra de ouro do usuário)
    print("Contando linhas...")
    total_linhas = 0
    with open(origem, encoding="utf-8", errors="replace") as f:
        for _ in f:
            total_linhas += 1
    print(f"Total de linhas: {total_linhas:,}")

    vistos: set = set()
    lidas = validas = invalidas = 0
    arquivo_atual = 0
    buff: list = []
    t0 = time.time()

    def _flush(ultimo: bool = False) -> None:
        nonlocal arquivo_atual, buff
        if not buff:
            return
        arquivo_atual += 1
        destino = saida / f"cnmoro_sanitizado_{arquivo_atual:05d}.jsonl"
        with open(destino, "w", encoding="utf-8") as f:
            f.write("\n".join(buff) + "\n")
        buff = []
        if not ultimo:
            _progresso(pasta=str(saida), arquivo_atual=arquivo_atual,
                       lidas=lidas, validas=validas, invalidas=invalidas,
                       percentual=round(100.0 * lidas / max(1, total_linhas), 1))

    with open(origem, encoding="utf-8", errors="replace") as f:
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
            novo = _tratar_linha(obj, vistos)
            if novo is None:
                invalidas += 1
                continue
            validas += 1
            buff.append(json.dumps(novo, ensure_ascii=False))
            if len(buff) >= EXEMPLOS_POR_ARQUIVO:
                _flush()
            if lidas % 100_000 == 0:
                print(f"  {lidas:,}/{total_linhas:,} "
                      f"({100.0 * lidas / max(1, total_linhas):.1f}%) | "
                      f"válidas: {validas:,} | descartadas: {invalidas:,} | "
                      f"{time.time() - t0:.0f}s")
                _progresso(pasta=str(saida), arquivo_atual=arquivo_atual,
                           lidas=lidas, validas=validas, invalidas=invalidas,
                           percentual=round(100.0 * lidas / max(1, total_linhas), 1))

    _flush(ultimo=True)

    # Verificação final (regra de ouro: verificar antes de entregar)
    n_arquivos = arquivo_atual
    total_saida = 0
    for arq in sorted(saida.glob("*.jsonl")):
        with open(arq, encoding="utf-8") as f:
            total_saida += sum(1 for _ in f)
    print("=" * 60)
    print(f"CONCLUÍDO: {lidas:,} lidas | {validas:,} convertidas | "
          f"{invalidas:,} descartadas")
    print(f"Saída: {n_arquivos} arquivo(s) em {saida} ({total_saida:,} exemplos)")
    _progresso(pasta=str(saida), arquivo_atual=n_arquivos, lidas=lidas,
               validas=validas, invalidas=invalidas,
               percentual=100.0, concluido=True, exemplos_saida=total_saida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
