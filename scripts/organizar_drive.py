# -*- coding: utf-8 -*-
"""
organizar_drive.py — Organiza o projeto e prepara a pasta pronta p/ upload ao Google Drive (05/08/2026).

1) MOVE para D:\\apaguemedepois\\rigelllm_organizar_20260805\\ (NADA apagado; MANIFESTO.txt):
   - dados/processed/jsonl/rigeljsonl_20260804_2149  (4,21 GB — SUJO, sintético, será recriado na re-explosão sanitizada)
   - tokenizer/tokenizer_hf.json                      (só usado por scripts/test_hfjson.py — recriável do tokenizer.json)

2) CRIA drive_upload/rigelllm/ (estrutura que o notebook Colab espera):
   scripts + tokenizer/tokenizer.json + modelo/ + LEIA_ME_Drive.txt
   (dados ficam NO PROJETO em dados/processed/jsonl — copiar/re-explodir antes de subir)
"""
import os
import shutil
import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = r"D:\apaguemedepois\rigelllm_organizar_20260805"
UPLOAD = os.path.join(RAIZ, "drive_upload", "rigelllm")
MANIFESTO = os.path.join(DESTINO, "MANIFESTO.txt")

# Scripts que o Colab precisa (treinar_com_jsonl importa treino; chat testa; converter opcional)
SCRIPTS_UPLOAD = [
    "treinar_com_jsonl.py",
    "treino.py",
    "chat.py",
    "converter_para_gguf.py",
    "modelo_backup.py",
]

def mover(origem: str, motivo: str, linhas: list) -> None:
    if os.path.exists(origem):
        dest = os.path.join(DESTINO, os.path.relpath(origem, RAIZ).replace(os.sep, "_"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(origem, dest)
        if os.path.isfile(dest):
            mb = os.path.getsize(dest) / 1e6
            linhas.append(f"[MOVIDO] {origem} ({mb:.1f} MB) -> {dest}\n         motivo: {motivo}\n")
            print(f"  MOVIDO: {origem} ({mb:.1f} MB)")
        else:
            total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(dest) for f in fs)
            linhas.append(f"[MOVIDO] {origem}/ ({total/1e9:.2f} GB) -> {dest}\n         motivo: {motivo}\n")
            print(f"  MOVIDO: {origem}/ ({total/1e9:.2f} GB)")
    else:
        print(f"  (ausente, pulado): {origem}")

def main() -> None:
    os.makedirs(DESTINO, exist_ok=True)
    linhas = [f"MANIFESTO - Organizacao p/ Drive em {datetime.datetime.now().isoformat()}\n",
              "=" * 70 + "\n"]

    # ---- 1) MOVE sujo / inutil para apaguemedepois ----
    print("== 1) Movendo sujo/inutil para apaguemedepois ==")
    mover(os.path.join(RAIZ, "dados", "processed", "jsonl", "rigeljsonl_20260804_2149"),
          "dataset SUJO (sintetico, chain-of-thought, lixo) - sera recriado na re-explosao com sanitizacao", linhas)
    mover(os.path.join(RAIZ, "tokenizer", "tokenizer_hf.json"),
          "so usado por scripts/test_hfjson.py (debug GGUF) - recriavel a partir do tokenizer.json", linhas)

    # ---- 2) CRIA pasta pronta p/ upload ----
    print("\n== 2) Criando pasta de upload: drive_upload/rigelllm/ ==")
    os.makedirs(UPLOAD, exist_ok=True)

    for s in SCRIPTS_UPLOAD:
        origem = os.path.join(RAIZ, s)
        if os.path.exists(origem):
            shutil.copy2(origem, os.path.join(UPLOAD, s))
            print(f"  + script: {s}")

    # tokenizer
    tok_dir = os.path.join(UPLOAD, "tokenizer")
    os.makedirs(tok_dir, exist_ok=True)
    shutil.copy2(os.path.join(RAIZ, "tokenizer", "tokenizer.json"), os.path.join(tok_dir, "tokenizer.json"))
    print("  + tokenizer/tokenizer.json")

    # modelo
    mod_dir = os.path.join(UPLOAD, "modelo")
    os.makedirs(mod_dir, exist_ok=True)
    for f in ("modelo.pt", "modelo_melhor.pt", "estado_treino_jsonl.json"):
        origem = os.path.join(RAIZ, "modelo", f)
        if os.path.exists(origem):
            shutil.copy2(origem, os.path.join(mod_dir, f))
    print("  + modelo/modelo.pt, modelo_melhor.pt, estado_treino_jsonl.json")

    # LEIA_ME
    leia = os.path.join(UPLOAD, "LEIA_ME_Drive.txt")
    with open(leia, "w", encoding="utf-8") as f:
        f.write("""RIGELSLM - PACOTE PARA GOOGLE DRIVE (gerado em 05/08/2026)
================================================================
ESTRUTURA DESTA PASTA (e o que o notebook Colab espera):

rigelllm/                     <- esta pasta vai para: MyDrive/rigelllm/
|-- treinar_com_jsonl.py      <- treino SFT (pipeline atual)
|-- treino.py                 <- importado pelo treinador
|-- chat.py                   <- teste do modelo (one-shot)
|-- converter_para_gguf.py    <- (opcional) converter p/ GGUF
|-- modelo_backup.py          <- backups cautelosos
|-- tokenizer/
|   `-- tokenizer.json        <- VOCAB 23830 (o CORRETO - nao usar outro)
`-- modelo/
    |-- modelo.pt             <- modelo BOM (val 6.87, 04/08)
    |-- modelo_melhor.pt      <- = copia do modelo.pt (default do treino)
    `-- estado_treino_jsonl.json  <- registro (epoch 5, best 6.87)

ANTES DE TREINAR:
1) Os DADOS ficam no projeto em: dados/processed/jsonl/
   -> copie as pastas desejadas para: dados/processed/jsonl/ (na pasta do Drive)
   -> (ou re-exploda com sanitizacao e copie os limpos)
2) Na celula 5 do notebook:
   - PASTA_DADOS = "dados/processed/jsonl"
   - RESUME = False   <- treino com dados NOVOS (checkpoint antigo foi movido)
   - MAX_ARQUIVOS = 5 (ou mais)
3) Rode as celulas em ordem.

ATENCAO: o tokenizer correto e o de VOCAB 23830 (tokenizer/tokenizer.json).
NUNCA use o que estava em modelo/tokenizer.json (vocab 32000 - errado).
""")
    print("  + LEIA_ME_Drive.txt")

    # ---- 3) Manifesto ----
    with open(MANIFESTO, "w", encoding="utf-8") as f:
        f.writelines(linhas)
    print("\nMANIFESTO em:", MANIFESTO)

    print("\n== Estrutura final drive_upload/rigelllm/ ==")
    for r, _, fs in os.walk(UPLOAD):
        nivel = r.replace(UPLOAD, "").count(os.sep)
        print("  " + "  " * nivel + os.path.basename(r) + "/")
        for f in sorted(fs):
            mb = os.path.getsize(os.path.join(r, f)) / 1e6
            print("  " + "  " * (nivel + 1) + f + (f"  ({mb:.1f} MB)" if mb > 1 else ""))

if __name__ == "__main__":
    main()
