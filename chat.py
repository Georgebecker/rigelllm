#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
chat.py - Teste interativo do modelo treinado com geração controlada.
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
Uso: python chat.py [--model MODELO] [--max-tokens N] [--temperature T] [--top-k K] [--repetition-penalty P] [--no-stream]

Melhorias v1.0.0:
  - Exibe métricas de treino (melhor loss, época) se disponíveis
  - Barra de maturidade visual baseada no best_val_loss
  - Explicações curtas dos parâmetros na inicialização
  - Feedback mais claro sobre o que está acontecendo
"""

import torch
import os
import sys
import json
import argparse
import time
from datetime import datetime
from pathlib import Path
from tokenizers import Tokenizer
from treino import RigelSLM, BOS_TOKEN, EOS_TOKEN, SEP_TOKEN, DISPOSITIVO

# ============================================================================
# Configurações padrão
# ============================================================================
TOKENIZER_PATH = "tokenizer/tokenizer.json"
MODEL_PATH = "modelo/modelo_melhor.pt"
DEFAULT_MAX_TOKENS = 200
DEFAULT_TEMPERATURE = 0.8
DEFAULT_TOP_K = 50
DEFAULT_REPETITION_PENALTY = 1.2
HISTORY_LIMIT = 3  # número de trocas anteriores a manter


# ============================================================================
# Funções de carregamento de métricas e estado do treino
# ============================================================================

def carregar_metricas():
    """
    Tenta carregar o histórico de métricas do treino.
    Prioriza o histórico do treinador SFT (metricas_jsonl.json), que é o que
    gerou os modelos atuais (modelo_melhor.pt / modelo.pt).
    Retorna (historico, origem) — origem identifica o treinador.
    """
    for nome, origem in (("logs/metricas_jsonl.json", "SFT (treinar_com_jsonl.py)"),
                         ("logs/metricas.json", "causal antigo (treino.py)")):
        metricas_path = Path(nome)
        if not metricas_path.exists():
            continue
        try:
            with open(metricas_path, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            return dados.get("historico", []), origem
        except (json.JSONDecodeError, KeyError) as e:
            print(f"   ⚠️ Erro ao ler métricas ({nome}): {e}")
    return None, ""


def carregar_estado_treino():
    """
    Tenta carregar o estado atual do treino (época atual, best_val_loss, etc.).
    Prioriza o estado do treinador SFT (estado_treino_jsonl.json), que é o que
    gerou os modelos atuais (modelo_melhor.pt / modelo.pt). Se não existir,
    tenta o estado do treino causal antigo.
    """
    for nome in ("estado_treino_jsonl.json", "estado_treino.json"):
        estado_path = Path("modelo") / nome
        if not estado_path.exists():
            continue
        try:
            with open(estado_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"   ⚠️ Erro ao ler estado ({nome}): {e}")
    return None


def carregar_versoes():
    """Carrega o manifesto de modelos (modelo/versoes.json), se existir."""
    v_path = Path("modelo/versoes.json")
    if not v_path.exists():
        return None
    try:
        with open(v_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError) as e:
        print(f"   ⚠️ Erro ao ler manifesto de modelos: {e}")
        return None


def exibir_identidade_modelo(caminho: str):
    """Mostra QUEM é o modelo em teste: arquivo, data, tamanho e origem."""
    p = Path(caminho)
    nome = p.name
    tamanho = "?"
    data = "?"
    origem = "desconhecida"

    if p.exists():
        st = p.stat()
        tamanho = f"{st.st_size / (1024 * 1024):.1f} MB"
        data = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")

    # Consulta o manifesto (fonte única de organização)
    manifesto = carregar_versoes()
    if manifesto:
        for v in manifesto.get("versoes", []):
            if v.get("nome") == nome and v.get("tipo") == "pt":
                origem = v.get("treinador", "desconhecida")
                est = v.get("estado_treino")
                if est:
                    origem += f" — época {est.get('epoch', '?')}, val_loss {est.get('best_val_loss', '?')}"
                break

    print("\n" + "=" * 60)
    print("   🧠 MODELO EM TESTE")
    print("=" * 60)
    print(f"   📄 Arquivo: {caminho}")
    print(f"   💾 Tamanho: {tamanho}  •  📅 Data: {data}")
    print(f"   🏷️  Origem: {origem}")
    print("=" * 60 + "\n")


def calcular_barra_maturidade(best_val_loss: float, largura: int = 20) -> str:
    """
    Calcula uma barra de maturidade visual baseada no best_val_loss.
    
    Quanto menor o loss, mais maduro o modelo.
    - loss < 1.0  → ████████████████████ (100% - excelente)
    - loss < 2.0  → ██████████████████░░ (80% - bom)
    - loss < 3.0  → ████████████████░░░░ (60% - razoável)
    - loss < 5.0  → ██████████░░░░░░░░░░ (40% - básico)
    - loss < 8.0  → ██████░░░░░░░░░░░░░░ (20% - inicial)
    - loss >= 8.0 → ███░░░░░░░░░░░░░░░░░ (10% - cru)
    """
    # Mapeia loss para percentual (0% = loss >= 10, 100% = loss <= 0.5)
    if best_val_loss <= 0.5:
        pct = 1.0
    elif best_val_loss >= 10.0:
        pct = 0.05
    else:
        # Interpolação linear: loss 10 → 5%, loss 0.5 → 100%
        pct = max(0.05, min(1.0, 1.0 - (best_val_loss - 0.5) / 9.5))
    
    preenchidos = round(pct * largura)
    vazios = largura - preenchidos
    barra = "▓" * preenchidos + "░" * vazios
    return f"[{barra}] {round(pct * 100)}%"


def exibir_info_treino():
    """
    Exibe informações do treino (métricas + estado) na inicialização.
    Tenta carregar os arquivos; se não existirem, mostra mensagem padrão.
    """
    # Carrega estado atual (época, best_val_loss)
    estado = carregar_estado_treino()

    # Carrega histórico de métricas (com a origem rotulada)
    historico, origem_hist = carregar_metricas()
    
    print("\n" + "=" * 60)
    print("   📊 INFORMAÇÕES DO TREINO")
    print("=" * 60)
    
    if estado is None and not historico:
        # Nenhum dado de treino disponível
        print("   ℹ️  Informações de treino não disponíveis")
        print("   Execute 'python treino.py' para treinar o modelo")
        return
    
    # --- Dados do estado ---
    if estado:
        epoch = estado.get("epoch", "?")
        best_loss = estado.get("best_val_loss")
        no_improve = estado.get("no_improve", 0)
        total_batches = estado.get("total_batches", "?")
        timestamp = estado.get("timestamp", "")
        
        print(f"   📅 Última atualização: {timestamp[:19] if timestamp else 'N/A'}")
        print(f"   🔢 Época atual: {epoch}")
        print(f"   📦 Total batches: {total_batches}")
        print(f"   ⏳ Épocas sem melhora: {no_improve}")
        
        # Barra de maturidade baseada no melhor loss
        if best_loss is not None:
            barra = calcular_barra_maturidade(best_loss)
            print(f"   📈 Melhor loss (val): {best_loss:.4f}")
            print(f"   🧠 Maturidade: {barra}")
    
    # --- Dados do histórico (melhor época) ---
    if historico:
        melhor_epoca = min(historico, key=lambda x: x.get("val_loss", float('inf')))
        melhor_idx = historico.index(melhor_epoca) + 1
        ultima = historico[-1]
        
        print(f"\n   📋 Histórico de treino ({len(historico)} épocas — {origem_hist}):")
        print(f"   🏆 Melhor época: #{melhor_idx} (val_loss: {melhor_epoca.get('val_loss', '?'):.4f})")
        print(f"   📉 Último train_loss: {ultima.get('train_loss', '?'):.4f}")
        print(f"   📉 Último val_loss: {ultima.get('val_loss', '?'):.4f}")
        print(f"   💧 LR final: {ultima.get('learning_rate', '?'):.8f}")
    
    print("=" * 60 + "\n")


# ============================================================================
# Funções de geração e exibição
# ============================================================================

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
        resposta = partes[-1].strip()
    
    # Remove o texto da pergunta se o modelo repetiu
    if prompt in resposta:
        resposta = resposta.replace(prompt, "").strip()

    # Remove tokens especiais residuais
    resposta = resposta.replace(SEP_TOKEN, "").strip()
    resposta = resposta.replace("[BOS]", "").strip()
    resposta = resposta.replace("[EOS]", "").strip()
    
    return resposta


# ============================================================================
# Função principal
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Chat interativo com o RigelSLM")
    parser.add_argument("--model", type=str, default=MODEL_PATH,
                        help="Caminho do modelo (.pt)")
    parser.add_argument("--tokenizer", type=str, default=TOKENIZER_PATH,
                        help="Caminho do tokenizer (tokenizer.json)")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help="Máx. tokens gerados por resposta")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                        help="Temperatura (0.0 a 2.0) – maior = mais criativo")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                        help="Top-K amostragem (0 desabilita)")
    parser.add_argument("--repetition-penalty", type=float, default=DEFAULT_REPETITION_PENALTY,
                        help="Penalidade repetição (>=1.0)")
    parser.add_argument("--no-stream", action="store_true",
                        help="Desabilita efeito de digitação")
    parser.add_argument("--one-shot", type=str, default=None,
                        help="Modo one-shot: gera resposta e sai (para dashboard)")
    parser.add_argument("--historico", type=str, default=None,
                        help="Histórico JSON para one-shot: [{\"pergunta\":...,\"resposta\":...}]")
    args = parser.parse_args()

    # ─── Verifica se os arquivos existem ───
    if not os.path.exists(args.tokenizer):
        print(f"❌ Tokenizer não encontrado em: {args.tokenizer}")
        return
    if not os.path.exists(args.model):
        print(f"❌ Modelo não encontrado em: {args.model}")
        print("   Treine o modelo primeiro ou ajuste o caminho com --model")
        return

    # ─── Carrega tokenizer e modelo ───
    print("🔄 Carregando modelo...")
    tokenizer = Tokenizer.from_file(args.tokenizer)
    model = RigelSLM().to(DISPOSITIVO)
    model.load_state_dict(torch.load(args.model, map_location=DISPOSITIVO))
    model.eval()
    print("✅ Modelo carregado com sucesso!")

    # ─── Identidade do modelo em teste (organização) ───
    exibir_identidade_modelo(args.model)

    # ─── Exibe informações do treino (se disponíveis) ───
    exibir_info_treino()

    # ─── Exibe parâmetros de geração ───
    print("   ⚙️  Parâmetros de geração:")
    print(f"      📊 Tokens máx: {args.max_tokens}  (tamanho máximo da resposta)")
    print(f"      🌡️ Temperatura: {args.temperature}  (criatividade: 0=exato, 2=criativo)")
    print(f"      🎯 Top-K: {args.top_k}  (diversidade: amostra dos K melhores tokens)")
    print(f"      🔁 Repetição: {args.repetition_penalty}x  (penalidade p/ repetir tokens)")
    
    # ─── Modo one-shot (para dashboard / subprocesso) ───
    if args.one_shot:
        prompt = args.one_shot
        # Se houver histórico, carrega do JSON
        historico_carregado = []
        if args.historico:
            try:
                historico_carregado = json.loads(args.historico)
                historico_carregado = [(h.get("pergunta",""), h.get("resposta","")) for h in historico_carregado]
            except json.JSONDecodeError:
                pass
        resposta = gerar_resposta(model, tokenizer, prompt, historico_carregado, args)
        # Apenas a resposta final, sem formatação extra (para consumo por outros scripts)
        sys.stdout.write(resposta)
        sys.stdout.flush()
        return

    # ─── Modo interativo ───
    print("\n💬 Digite sua pergunta. Comandos especiais:")
    print("   /clear   - limpa o histórico da conversa")
    print("   /exit    - sai do programa")
    print("   /help    - mostra esta mensagem")
    print("   /stats   - exibe estatísticas do modelo")
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
        if prompt.lower() == "/stats":
            # Re-exibe informações do treino
            exibir_info_treino()
            continue
        if prompt.lower() == "/help":
            print("Comandos: /clear, /exit, /help, /stats")
            continue

        # Gera resposta
        try:
            print("🤔 Gerando resposta...", end="\r")
            sys.stdout.flush()
            inicio = time.time()
            resposta = gerar_resposta(model, tokenizer, prompt, history, args)
            tempo = time.time() - inicio
            print(" " * 40, end="\r")  # limpa a mensagem "Gerando..."
            print_stream(f"🤖 {resposta}", stream=not args.no_stream)
            print(f"   ⏱️  {tempo:.1f}s • {len(resposta)} caracteres")
            history.append((prompt, resposta))
        except Exception as e:
            print(f"❌ Erro durante a geração: {e}")


if __name__ == "__main__":
    main()