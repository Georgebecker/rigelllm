# -*- coding: utf-8 -*-
"""
limpar_modelo.py — Limpeza metódica da pasta modelo/ (05/08/2026).
Regra de ouro: NADA é apagado — tudo vai para D:\\apaguemedepois\\rigelllm_modelo_20260805\\
com um MANIFESTO.txt registrando origem/destino/motivo.

Quem cria cada arquivo (rastreado no código):
  modelo.pt              <- treinar_com_jsonl.py (SFT) / treino.py (causal)  [MANTER - bom val 6.87]
  modelo_melhor.pt       <- treinar_com_jsonl.py / treino.py  [default do chat/dashboard/conversor]
  checkpoint.pt          <- treino.py (causal) -> --resume do treino TXT antigo  [MOVER]
  checkpoint_jsonl.pt    <- treinar_com_jsonl.py (SFT) -> --resume do SFT antigo  [MOVER]
  estado_treino.json     <- treino.py (causal, epoch 72 antigo)  [MOVER]
  estado_treino_jsonl.json <- treinar_com_jsonl.py (SFT, epoch 5 best 6.87)  [MANTER - registro do bom]
  STOP_TREINO.signal     <- dashboard/routes/train.py (regenerado a cada stop)  [MOVER]
  tokenizer.json (32000) <- NINGUÉM cria/referencia - órfão ERRADO (vocab 32000 != 23830)  [MOVER]
  batch_config.json      <- dashboard/services/treino_local.py (regenerável)  [MOVER]
  versoes.json           <- scripts/registro_modelos.py (manifesto - chat/conversor leem)  [MANTER]
  desktop.ini            <- lixo do Windows  [MOVER]
  backups/               <- modelo_backup.py (automáticos; contém cópia idêntica ao modelo.pt)  [MOVER]
  jsonlogs/              <- treinar_com_jsonl.py (bandeiras - dashboard lê)  [MANTER]
"""
import os
import shutil
import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELO = os.path.join(RAIZ, "modelo")
DESTINO = r"D:\apaguemedepois\rigelllm_modelo_20260805"
MANIFESTO = os.path.join(DESTINO, "MANIFESTO.txt")

# Itens a mover (nunca apagar) com motivo
A_MOVER = [
    ("checkpoint.pt",            "treino.py (causal) - checkpoint de retomada do treino TXT antigo"),
    ("checkpoint_jsonl.pt",      "treinar_com_jsonl.py (SFT) - checkpoint de retomada do SFT antigo (vai treinar dados novos a partir do modelo.pt)"),
    ("estado_treino.json",       "treino.py (causal) - estado do treino TXT antigo (epoch 72)"),
    ("STOP_TREINO.signal",       "dashboard/routes/train.py - sinal de parada (regenerado a cada stop)"),
    ("tokenizer.json",           "ORFAO - tokenizer ERRADO (vocab 32000 != 23830); ninguem referencia no codigo"),
    ("batch_config.json",        "dashboard/services/treino_local.py - config de fila (regeneravel)"),
    ("desktop.ini",              "lixo do Windows (regenerado)"),
]

def mover_arquivo(origem: str, destino: str, motivo: str, linhas: list) -> None:
    if os.path.exists(origem):
        shutil.move(origem, destino)
        mb = os.path.getsize(destino) / 1e6
        linhas.append(f"[MOVIDO] {os.path.basename(origem)} ({mb:.1f} MB) -> {destino}\n         motivo: {motivo}\n")
        print(f"  MOVIDO: {os.path.basename(origem)} ({mb:.1f} MB)")
    else:
        print(f"  (ausente, pulado): {os.path.basename(origem)}")

def main() -> None:
    os.makedirs(DESTINO, exist_ok=True)
    linhas = [f"MANIFESTO - Limpeza modelo/ em {datetime.datetime.now().isoformat()}\n",
              "=" * 70 + "\n"]

    # 1) Move backups/ inteira (contém copia identica ao modelo.pt bom)
    origem_backups = os.path.join(MODELO, "backups")
    if os.path.isdir(origem_backups):
        dest_backups = os.path.join(DESTINO, "backups")
        if os.path.exists(dest_backups):
            shutil.rmtree(dest_backups)
        shutil.move(origem_backups, dest_backups)
        total = sum(os.path.getsize(os.path.join(dest_backups, f)) for f in os.listdir(dest_backups) if os.path.isfile(os.path.join(dest_backups, f)))
        linhas.append(f"[MOVIDO] backups/ ({total/1e6:.1f} MB) -> {dest_backups}\n         motivo: backups automaticos; contem copia identica ao modelo.pt (hash e12219a896ae)\n\n")
        print(f"  MOVIDO: backups/ ({total/1e6:.1f} MB)")

    # 2) Move arquivos individuais
    for nome, motivo in A_MOVER:
        mover_arquivo(os.path.join(MODELO, nome), os.path.join(DESTINO, nome), motivo, linhas)

    # 3) modelo_melhor.pt antigo -> move para apaguemedepois e copia o modelo.pt bom por cima
    #    (modelo_melhor.pt é o DEFAULT de chat.py/dashboard/conversor/ollama_deploy;
    #    hoje aponta para o antigo val 8.26 - atualizar para o bom val 6.87)
    mm = os.path.join(MODELO, "modelo_melhor.pt")
    mp = os.path.join(MODELO, "modelo.pt")
    if os.path.exists(mm) and os.path.exists(mp):
        dest_antigo = os.path.join(DESTINO, "modelo_melhor_ANTIGO_val826.pt")
        shutil.move(mm, dest_antigo)
        shutil.copy2(mp, mm)
        linhas.append(f"[MOVIDO] modelo_melhor.pt (ANTIGO val 8.26) -> {dest_antigo}\n")
        linhas.append(f"[ATUALIZADO] modelo_melhor.pt agora = copia do modelo.pt (bom val 6.87)\n"
                      f"         motivo: default de chat.py/dashboard/main.py/dashboard/routes/chat.py/converter/ollama_deploy\n\n")
        print("  MOVIDO: modelo_melhor.pt (antigo) -> apaguemedepois")
        print("  ATUALIZADO: modelo_melhor.pt = copia do modelo.pt (bom val 6.87)")

    # 4) Grava manifesto
    with open(MANIFESTO, "w", encoding="utf-8") as f:
        f.writelines(linhas)

    print("\n" + "=" * 70)
    print("MANIFESTO gravado em:", MANIFESTO)
    print("\nConteudo final de modelo/:")
    for f in sorted(os.listdir(MODELO)):
        p = os.path.join(MODELO, f)
        if os.path.isdir(p):
            print(f"   [PASTA] {f}/")
        else:
            print(f"   {f}  ({os.path.getsize(p)/1e6:.1f} MB)" if os.path.getsize(p) > 1e6 else f"   {f}")

if __name__ == "__main__":
    main()
