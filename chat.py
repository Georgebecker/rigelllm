#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
chat.py - Teste interativo do modelo treinado com geração controlada.
Uso: python chat.py [--model MODELO] [--max-tokens N] [--temperature T] [--top-k K] [--repetition-penalty P] [--no-stream]
"""

import torch
import os
import sys
import argparse
import time
from tokenizers import Tokenizer
from treino import RigelSLM, BOS_TOKEN, EOS_TOKEN, SEP_TOKEN, DISPOSITIVO

# Configurações padrão
TOKENIZER_PATH = "tokenizer/tokenizer.json"
MODEL_PATH = "modelo/modelo_melhor.pt"
DEFAULT_MAX_TOKENS = 200
DEFAULT_TEMPERATURE = 0.8
DEFAULT_TOP_K = 50
DEFAULT_REPETITION_PENALTY = 1.2
HISTORY_LIMIT = 3  # número de trocas anteriores a manter


def print_stream(text: str, delay: float = 0.03, stream: bool = True):
    """Exibe o texto com efeito de digitação caractere por caractere."""
    if not stream:
        print(text)
        return
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()  # quebra de linha final


def gerar_resposta(model, tokenizer, prompt, history, args):
    """Gera uma resposta para o prompt usando o histórico."""
    from treino import SEP_TOKEN, BOS_TOKEN
    
    # Monta o contexto com histórico (últimas 3 trocas)
    context = ""
    for q, a in history[-HISTORY_LIMIT:]:
        context += f"Pergunta: {q}\nResposta: {a}\n{SEP_TOKEN}\n"
    context += f"Pergunta: {prompt}\nResposta:"

    # Gera a resposta
    resposta = model.generate(
        tokenizer,
        context,
        max_new_tokens=args.max_tokens,
        temperature=args.temperature,
        repetition_penalty=args.repetition_penalty,
        top_k=args.top_k
    )

    # Pós-processamento robusto
    # Remove o prompt inicial (tudo antes da primeira "Resposta:" que geramos)
    marker_resposta = "Resposta:"
    if marker_resposta in resposta:
        # Pega a última ocorrência (o modelo pode repetir o padrão)
        partes = resposta.split(marker_resposta)
        # Se o modelo repetiu o formato, a resposta real é a última parte
        resposta = partes[-1].strip()
    
    # Remove o texto da pergunta se o modelo repetiu
    if prompt in resposta:
        resposta = resposta.replace(prompt, "").strip()

    # Remove tokens especiais residuais
    resposta = resposta.replace(SEP_TOKEN, "").strip()
    resposta = resposta.replace("[BOS]", "").strip()
    resposta = resposta.replace("[EOS]", "").strip()
    
    return resposta


def main():
    parser = argparse.ArgumentParser(description="Chat interativo com o RigelSLM")
    parser.add_argument("--model", type=str, default=MODEL_PATH,
                        help="Caminho do modelo (.pt)")
    parser.add_argument("--tokenizer", type=str, default=TOKENIZER_PATH,
                        help="Caminho do tokenizer (tokenizer.json)")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help="Máximo de tokens gerados por resposta")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                        help="Temperatura (0.0 a 2.0) – maior = mais criativo")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                        help="Top-K para amostragem (0 desabilita)")
    parser.add_argument("--repetition-penalty", type=float, default=DEFAULT_REPETITION_PENALTY,
                        help="Penalidade para repetição de tokens (>=1.0)")
    parser.add_argument("--no-stream", action="store_true",
                        help="Desabilita o efeito de digitação (mostra resposta de uma vez)")
    parser.add_argument("--one-shot", type=str, default=None,
                        help="Modo one-shot: gera resposta para o prompt e sai (para dashboard)")
    parser.add_argument("--historico", type=str, default=None,
                        help="Histórico em JSON (para one-shot): [{\"pergunta\":...,\"resposta\":...}]")
    args = parser.parse_args()

    # Verifica arquivos
    if not os.path.exists(args.tokenizer):
        print(f"❌ Tokenizer não encontrado em: {args.tokenizer}")
        return
    if not os.path.exists(args.model):
        print(f"❌ Modelo não encontrado em: {args.model}")
        print("   Treine o modelo primeiro ou ajuste o caminho com --model")
        return

    # Carrega tokenizer e modelo
    print("🔄 Carregando modelo...")
    tokenizer = Tokenizer.from_file(args.tokenizer)
    model = RigelSLM().to(DISPOSITIVO)
    model.load_state_dict(torch.load(args.model, map_location=DISPOSITIVO))
    model.eval()

    print("✅ Modelo carregado com sucesso!")
    print(f"   📊 Max tokens: {args.max_tokens}")
    print(f"   🌡️ Temperatura: {args.temperature}")
    print(f"   🎯 Top-K: {args.top_k}")
    print(f"   🔁 Repetition penalty: {args.repetition_penalty}")
    # ─── Modo one-shot (para dashboard / subprocesso) ───
    if args.one_shot:
        prompt = args.one_shot
        resposta = gerar_resposta(model, tokenizer, prompt, [], args)
        # Apenas a resposta final, sem formatação extra
        sys.stdout.write(resposta)
        sys.stdout.flush()
        return

    print("\n💬 Digite sua pergunta. Comandos especiais:")
    print("   /clear   - limpa o histórico da conversa")
    print("   /exit    - sai do programa")
    print("   /help    - mostra esta mensagem")
    print("-" * 60)

    history = []  # lista de tuplas (pergunta, resposta)

    while True:
        try:
            prompt = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Saindo...")
            break

        if not prompt:
            continue

        # Processa comandos
        if prompt.lower() in ["/exit", "/quit", "sair", "exit"]:
            print("👋 Até logo!")
            break
        if prompt.lower() == "/clear":
            history = []
            print("🧹 Histórico limpo.")
            continue
        if prompt.lower() == "/help":
            print("Comandos: /clear, /exit, /help")
            continue

        try:
            resposta = gerar_resposta(model, tokenizer, prompt, history, args)
            print_stream(f"🤖 {resposta}", stream=not args.no_stream)
            history.append((prompt, resposta))
        except Exception as e:
            print(f"❌ Erro durante a geração: {e}")


if __name__ == "__main__":
    main()