# -*- coding: utf-8 -*-
"""
Teste decisivo: modelo.pt direto em Python (sem GGUF).
Responde: o modelo realmente fala portugues? Ou o problema e 100% o export GGUF?
"""
import sys, os, torch
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _RAIZ)
os.chdir(_RAIZ)
from treino import RigelSLM, DISPOSITIVO, MODEL_PATH, TOKENIZER_PATH
from tokenizers import Tokenizer

def main():
    tokenizer = Tokenizer.from_file(TOKENIZER_PATH)
    print(f"Tokenizer: {TOKENIZER_PATH} | vocab={tokenizer.get_vocab_size()}")

    model = RigelSLM().to(DISPOSITIVO)
    if os.path.exists(MODEL_PATH):
        model.load_state_dict(torch.load(MODEL_PATH, map_location=DISPOSITIVO))
        print(f"Modelo carregado: {MODEL_PATH}")
    else:
        print(f"ERRO: {MODEL_PATH} nao existe")
        sys.exit(1)

    prompts = [
        "Ola, tudo bem?",
        "Qual e a capital do Brasil?",
        "Conte uma historia curta sobre um gato.",
    ]

    for p in prompts:
        print("\n" + "=" * 60)
        print(f"PROMPT: {p!r}")
        try:
            saida = model.generate(tokenizer, p, max_new_tokens=80,
                                   temperature=0.8, repetition_penalty=1.2, top_k=50)
            print(f"SAIDA : {saida!r}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"ERRO na geracao: {e}")

    # Tambem mostra a decodificacao dos tokens do prompt para conferir o tokenizer
    print("\n" + "=" * 60)
    print("DECODIFICACAO DIRETA DO TOKENIZER (token -> texto):")
    for t in [0, 1, 2, 3, 4, 50, 323, 120]:
        try:
            dec = tokenizer.decode([t])
            print(f"  token {t}: {dec!r}")
        except Exception as e:
            print(f"  token {t}: ERRO {e}")

if __name__ == "__main__":
    main()
