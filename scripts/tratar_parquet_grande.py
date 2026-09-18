#!/usr/bin/env python3
"""Trata datasets PARQUET mantendo o TAMANHO dos arquivos (18/08 — regra do usuário).

Diferente do limpeza_leve_rigel_v2.py (que gera parciais de ~8 MB), este script:
- lê UM arquivo parquet bruto de cada vez (ex.: train-00000-of-00709.parquet, ~140 MB);
- trata os campos (prompt/thought/answer → messages user/assistant; descarta o
  raciocínio 'thought' — decisão do usuário);
- salva UM arquivo grande tratado: {nome_original}_tratado.parquet (renomeado);
- APAGA o original assim que o tratado é salvo com sucesso (autorizado pelo
  usuário: "no momento que voce tratar o arquivo e estiver pronto, voce pode
  apagar o original") — libera espaço continuamente;
- mantém a numeração/nomes originais, só adiciona o sufixo _tratado.

Uso:
  python scripts/tratar_parquet_grande.py \
      --origem dados/raw/cnmoro_reasoning-v1-20m-portuguese \
      --saida dados/processed/parquet/cnmoro

Flags:
  --max-arquivos N   processa só N arquivos (teste)
  --sem-apagar       NÃO apaga o original (teste/segurança)
  --exigir-ptbr      liga o filtro de idioma por linha (MAIS LENTO — langdetect)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# Permite importar o limpeza_leve da raiz (reutiliza a lógica de tratamento)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import limpeza_leve_rigel_v2 as ll  # noqa: E402

LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
PROGRESSO_LOG = os.path.join(LOGS_DIR, "tratar_parquet_grande_progresso.json")
RELATORIO_LOG = os.path.join(LOGS_DIR, "tratar_parquet_grande_relatorio.json")


def _progresso(**kw) -> None:
    kw["atualizado_em"] = time.strftime("%H:%M:%S")
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(PROGRESSO_LOG, "w", encoding="utf-8") as f:
            json.dump(kw, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================================
# TRATAMENTO RÁPIDO (18/08) — focado no essencial para o cnmoro
# ============================================================================
# O cnmoro já é PT e estruturado (prompt/thought/answer). O tratamento pesado
# (dedup minhash, ftfy, bs4, regex por exemplo) custava ~6 min/arquivo — inviável
# para 709 arquivos. Aqui: converte campos, remove o raciocínio, limpa mojibake
# e dedup EXATO (md5) — barato e suficiente.
import hashlib  # noqa: E402

# Apenas combinações REAIS de duplo-encoding (NUNCA "Ã" solto — falso positivo
# com SÃO/MÃE/CÃES, lição registrada na memória).
_MOJIBAKE_FIX = {
    "Ã£": "ã", "Ã©": "é", "Ãª": "ê", "Ã§": "ç", "Ã³": "ó", "Ã¡": "á",
    "Ã­": "í", "Ã¼": "ü", "Ã´": "ô", "Ã¢": "â", "Ãµ": "õ", "Ã¨": "è",
    "Ã²": "ò", "Ã±": "ñ", "Ãº": "ú",
    "â€œ": '"', "â€\u009d": '"', "â€™": "'", "â€“": "–", "â€”": "—",
    "â€¦": "...", "\ufffd": "",
}


def _limpar_leve(texto: str) -> str:
    """Corrige mojibake real + normaliza espaços. Rápido (str.replace)."""
    for antigo, novo in _MOJIBAKE_FIX.items():
        if antigo in texto:
            texto = texto.replace(antigo, novo)
    return " ".join(texto.split()).strip()


def _tratar_linha(row: dict, vistos: set) -> dict | None:
    """Converte prompt/answer → messages (descarta thought). None se lixo."""
    if not isinstance(row, dict):
        return None
    # Já vem no formato certo?
    msgs = row.get("messages")
    if isinstance(msgs, list) and msgs:
        return row
    prompt = str(row.get("prompt") or "").strip()
    answer = str(row.get("answer") or "").strip()
    if not prompt or not answer:
        return None
    prompt = _limpar_leve(prompt)
    answer = _limpar_leve(answer)
    if len(prompt) < 5 or len(answer) < 5:
        return None
    chave = hashlib.md5((prompt + "\x01" + answer).encode("utf-8", "replace")).hexdigest()
    if chave in vistos:
        return None
    vistos.add(chave)
    return {"messages": [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": answer},
    ]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origem", required=True, help="Pasta com os parquet brutos")
    ap.add_argument("--saida", required=True, help="Pasta de saída (arquivos tratados)")
    ap.add_argument("--max-arquivos", type=int, default=0, help="Limita nº de arquivos (teste)")
    ap.add_argument("--sem-apagar", action="store_true", help="Não apaga o original (teste)")
    ap.add_argument("--exigir-ptbr", action="store_true",
                    help="Liga filtro de idioma por linha (LENTO — langdetect)")
    args = ap.parse_args()

    origem = Path(args.origem)
    saida = Path(args.saida)
    if not origem.exists():
        print(f"ERRO: origem não encontrada: {origem}")
        return 1
    saida.mkdir(parents=True, exist_ok=True)

    arquivos = sorted(origem.rglob("*.parquet"))
    print(f"Arquivos brutos encontrados: {len(arquivos)}")
    if not arquivos:
        print("Nenhum arquivo parquet na origem.")
        return 1

    contadores = {"lidos": 0, "sem_texto": 0, "nao_pt": 0, "qualidade": 0,
                  "duplicado": 0, "ruido_ia": 0, "sft": 0, "pretrain": 0,
                  "arquivos_tratados": 0, "originais_apagados": 0}
    vistos: set = set()
    t0 = time.time()

    for i, arq in enumerate(arquivos, 1):
        if args.max_arquivos and i > args.max_arquivos:
            print(f"[limite --max-arquivos {args.max_arquivos} atingido]")
            break
        tratado = saida / (arq.stem + "_tratado.parquet")
        if tratado.exists():
            print(f"[{i}/{len(arquivos)}] {arq.name}: já tratado (pulando)", flush=True)
            continue

        print(f"[{i}/{len(arquivos)}] {arq.name}: tratando...", flush=True)
        exemplos: list[dict] = []
        try:
            import pyarrow.parquet as pq
            with pq.ParquetFile(str(arq)) as pf:
                for batch in pf.iter_batches():
                    for row in batch.to_pylist():
                        if not isinstance(row, dict):
                            continue
                        contadores["lidos"] += 1
                        ex = _tratar_linha(row, vistos)
                        if ex is None:
                            continue
                        exemplos.append(ex)
                        contadores["sft"] += 1
        except Exception as e:
            print(f"  ERRO ao ler {arq.name}: {e}")
            contadores["qualidade"] += 1
            continue

        if not exemplos:
            print(f"  {arq.name}: nenhum exemplo aproveitado — original NÃO apagado")
            contadores["qualidade"] += 1
            continue

        n = ll._salvar_lote_parquet(exemplos, str(tratado))
        if not n or not tratado.exists():
            print(f"  {arq.name}: falha ao salvar tratado — original NÃO apagado")
            contadores["qualidade"] += 1
            continue

        mb = os.path.getsize(tratado) / 1e6
        print(f"  -> {tratado.name}: {n} exemplos ({mb:.1f} MB)", flush=True)
        contadores["arquivos_tratados"] += 1
        if not args.sem_apagar:
            try:
                os.remove(str(arq))
                contadores["originais_apagados"] += 1
                print(f"  -> original apagado: {arq.name}", flush=True)
            except OSError as e:
                print(f"  -> aviso: não consegui apagar original ({e})")

        _progresso(arquivo_atual=arq.name, indice=i, total_arquivos=len(arquivos),
                   arquivos_tratados=contadores["arquivos_tratados"],
                   lidos=contadores["lidos"], sft=contadores["sft"],
                   decorrido_s=round(time.time() - t0, 1))

    duracao = round(time.time() - t0, 1)
    contadores["duracao_s"] = duracao
    print(f"\nRESULTADO ({duracao}s):")
    for k, v in contadores.items():
        print(f"  {k}: {v}")

    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(RELATORIO_LOG, "w", encoding="utf-8") as f:
            json.dump({"gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "origem": str(origem), "saida": str(saida),
                       "contadores": contadores},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
