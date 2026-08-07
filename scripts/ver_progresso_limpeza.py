# -*- coding: utf-8 -*-
"""ver_progresso_limpeza.py — Lê o progresso ao vivo da limpeza."""
import sys, json, time, os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

caminho = "logs/limpeza_progresso.json"
if not os.path.exists(caminho):
    print("(arquivo de progresso ainda não criado — pipeline iniciando...)")
else:
    d = json.load(open(caminho, encoding="utf-8"))
    print("=== PROGRESSO DA LIMPEZA (ao vivo) ===")
    print(f"  Pct:          {d.get('pct', 0)}%")
    print(f"  Lidos:        {d.get('lidos', 0)}")
    print(f"  SFT aprovado: {d.get('sft', 0)}")
    print(f"  Pretrain:     {d.get('pretrain', 0)}")
    print(f"  Descartados:  {d.get('descartados', 0)}")
    print(f"  Tempo:        {d.get('decorrido_s', 0)}s")
    print(f"  Origem:       {d.get('origem', '')}")
    print(f"  Arquivo:      {d.get('arquivo_atual', '')}")
    print(f"  Atualizado:   {d.get('atualizado_em', '')}")
