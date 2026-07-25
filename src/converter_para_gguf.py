#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
RIGELSLM - CONVERSOR PARA GGUF + MODELFILE (v3.7 - CORREÇÃO FINAL)
================================================================================
Converte o modelo treinado (.pt) para GGUF com transposição do embedding
para compatibilidade com llama.cpp/Ollama.

Uso:
    python converter_para_gguf.py
    python converter_para_gguf.py --quant Q4_K --modelfile rigelslm
================================================================================
"""

import os
import sys
import json
import argparse
import subprocess
import time
import platform
from pathlib import Path
from datetime import datetime

# =============================================================================
# 0. VERIFICAÇÃO DE DEPENDÊNCIAS
# =============================================================================

def verificar_dependencias():
    dependencias = ["gguf", "torch", "numpy", "tokenizers"]
    faltando = []
    for dep in dependencias:
        try:
            __import__(dep)
        except ImportError:
            faltando.append(dep)
    if faltando:
        print(f"⚠️  Dependências faltando: {', '.join(faltando)}")
        print("🔄 Instalando...")
        for dep in faltando:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            print(f"   ✅ {dep} instalado.")
    else:
        print("✅ Todas as dependências estão instaladas.")

verificar_dependencias()

# =============================================================================
# 1. IMPORTAÇÕES
# =============================================================================

import torch
import numpy as np
from tokenizers import Tokenizer
import gguf

# =============================================================================
# 2. CONFIGURAÇÕES
# =============================================================================

ROOT = Path(__file__).resolve().parent
if (ROOT / "modelo").exists():
    RAIZ = ROOT
else:
    RAIZ = ROOT.parent

PASTA_MODELO = RAIZ / "modelo"
PASTA_TOKENIZER = RAIZ / "tokenizer"
PASTA_LOGS = RAIZ / "logs"
PASTA_GGUF = RAIZ / "gguf"
PASTA_GGUF.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 3. METADADOS E IMPORTAÇÃO DO MODELO
# =============================================================================

NOME_MODELO = "RigelSLM"
VERSAO = "1.0.0"
AUTOR = "George Herman Becker"

def localizar_modelo():
    candidatos = ["modelo_melhor.pt", "modelo.pt", "modelo_last.pt"]
    for nome in candidatos:
        caminho = PASTA_MODELO / nome
        if caminho.exists():
            return caminho
    return None

def carregar_metricas():
    metricas_path = PASTA_LOGS / "metricas.json"
    if metricas_path.exists():
        try:
            with open(metricas_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            historico = data.get("historico", [])
            if historico:
                ultimo = historico[-1]
                return {
                    "epoch": ultimo.get("epoch", "N/A"),
                    "train_loss": ultimo.get("train_loss", "N/A"),
                    "val_loss": ultimo.get("val_loss", "N/A"),
                }
        except:
            pass
    return {}

def importar_parametros():
    sys.path.insert(0, str(RAIZ))
    try:
        from treino import RigelSLM, VOCAB_SIZE, EMBED_DIM, NUM_LAYERS, NUM_HEADS, FF_DIM, SEQ_LEN
        return RigelSLM, VOCAB_SIZE, EMBED_DIM, NUM_LAYERS, NUM_HEADS, FF_DIM, SEQ_LEN
    except ImportError as e:
        print(f"❌ Erro ao importar treino.py: {e}")
        sys.exit(1)

RigelSLM, VOCAB_SIZE, EMBED_DIM, NUM_LAYERS, NUM_HEADS, FF_DIM, SEQ_LEN = importar_parametros()

# =============================================================================
# 4. MAPEAMENTO DE TENSORES (COM TRANSPOSIÇÃO DO EMBEDDING)
# =============================================================================

def mapear_tensores(state_dict):
    tensores = {}

    # Embedding - GGUF llama espera [embed_dim, vocab_size] (transposto)
    if "embedding.weight" in state_dict:
        emb = state_dict["embedding.weight"].numpy().astype(np.float32)
        # Remove dimensões extras (ex: [vocab_size, embed_dim, 1, 1] -> [vocab_size, embed_dim])
        while emb.ndim > 2:
            emb = emb.squeeze()
        # Transpõe: (vocab_size, embed_dim) -> (embed_dim, vocab_size)
        tensores["token_embd.weight"] = emb.T

    # Output (lm_head) - geralmente [vocab_size, embed_dim], mas no GGUF espera [embed_dim, vocab_size]? 
    # No padrão llama, output.weight é [vocab_size, embed_dim] (não transposto). Vamos manter.
    if "lm_head.weight" in state_dict:
        tensores["output.weight"] = state_dict["lm_head.weight"].numpy().astype(np.float32)
    if "lm_head.bias" in state_dict:
        tensores["output.bias"] = state_dict["lm_head.bias"].numpy().astype(np.float32)

    # Camadas (mantém)
    for i in range(NUM_LAYERS):
        prefix = f"decoder.layers.{i}."

        # Atenção (Q, K, V)
        if f"{prefix}self_attn.in_proj_weight" in state_dict:
            in_proj = state_dict[f"{prefix}self_attn.in_proj_weight"].numpy()
            q, k, v = np.split(in_proj, 3, axis=0)
            tensores[f"blk.{i}.attn_q.weight"] = q.astype(np.float32)
            tensores[f"blk.{i}.attn_k.weight"] = k.astype(np.float32)
            tensores[f"blk.{i}.attn_v.weight"] = v.astype(np.float32)

        if f"{prefix}self_attn.in_proj_bias" in state_dict:
            in_proj_bias = state_dict[f"{prefix}self_attn.in_proj_bias"].numpy()
            q_b, k_b, v_b = np.split(in_proj_bias, 3, axis=0)
            tensores[f"blk.{i}.attn_q.bias"] = q_b.astype(np.float32)
            tensores[f"blk.{i}.attn_k.bias"] = k_b.astype(np.float32)
            tensores[f"blk.{i}.attn_v.bias"] = v_b.astype(np.float32)

        if f"{prefix}self_attn.out_proj.weight" in state_dict:
            tensores[f"blk.{i}.attn_output.weight"] = state_dict[f"{prefix}self_attn.out_proj.weight"].numpy().astype(np.float32)

        # FFN
        if f"{prefix}linear1.weight" in state_dict:
            tensores[f"blk.{i}.ffn_gate.weight"] = state_dict[f"{prefix}linear1.weight"].numpy().astype(np.float32)
        if f"{prefix}linear1.bias" in state_dict:
            tensores[f"blk.{i}.ffn_gate.bias"] = state_dict[f"{prefix}linear1.bias"].numpy().astype(np.float32)

        if f"{prefix}linear2.weight" in state_dict:
            tensores[f"blk.{i}.ffn_down.weight"] = state_dict[f"{prefix}linear2.weight"].numpy().astype(np.float32)
        if f"{prefix}linear2.bias" in state_dict:
            tensores[f"blk.{i}.ffn_down.bias"] = state_dict[f"{prefix}linear2.bias"].numpy().astype(np.float32)

        # Layer Norm
        if f"{prefix}norm1.weight" in state_dict:
            tensores[f"blk.{i}.attn_norm.weight"] = state_dict[f"{prefix}norm1.weight"].numpy().astype(np.float32)
        if f"{prefix}norm1.bias" in state_dict:
            tensores[f"blk.{i}.attn_norm.bias"] = state_dict[f"{prefix}norm1.bias"].numpy().astype(np.float32)

        if f"{prefix}norm2.weight" in state_dict:
            tensores[f"blk.{i}.ffn_norm.weight"] = state_dict[f"{prefix}norm2.weight"].numpy().astype(np.float32)
        if f"{prefix}norm2.bias" in state_dict:
            tensores[f"blk.{i}.ffn_norm.bias"] = state_dict[f"{prefix}norm2.bias"].numpy().astype(np.float32)

    return tensores

# =============================================================================
# 5. EXPORTAÇÃO DO TOKENIZER (COMPATÍVEL)
# =============================================================================

def exportar_tokenizer_gguf(writer, tokenizer: Tokenizer):
    vocab = tokenizer.get_vocab()
    sorted_vocab = sorted(vocab.items(), key=lambda x: x[1])
    tokens = [token for token, _ in sorted_vocab]
    scores = [0.0] * len(tokens)

    merges = []
    if hasattr(tokenizer, "merges") and tokenizer.merges is not None:
        merges = [f"{a} {b}" for a, b in tokenizer.merges]

    writer.add_string("tokenizer.ggml.model", "llama")
    writer.add_array("tokenizer.ggml.tokens", tokens)
    writer.add_array("tokenizer.ggml.scores", scores)
    writer.add_array("tokenizer.ggml.token_type", [0] * len(tokens))
    if merges:
        writer.add_array("tokenizer.ggml.merges", merges)

    special_tokens = {"pad": 0, "unk": 1, "bos": 2, "eos": 3, "sep": 4}
    for name, id in special_tokens.items():
        writer.add_uint32(f"tokenizer.ggml.{name}_token_id", id)
    writer.add_string("tokenizer.ggml.eos_token", "[EOS]")

    print(f"   ✅ Tokenizer exportado: {len(tokens)} tokens, {len(merges)} merges")

# =============================================================================
# 6. ESCRITA DO GGUF (com architecture='llama')
# =============================================================================

def escrever_gguf(tensores_gguf, tokenizer: Tokenizer, quantizacao="Q4_K", metadados=None):
    if metadados is None:
        metadados = {}

    quant_map = {
        "F16": gguf.GGMLQuantizationType.F16,
        "F32": gguf.GGMLQuantizationType.F32,
        "Q8_0": gguf.GGMLQuantizationType.Q8_0,
        "Q4_0": gguf.GGMLQuantizationType.Q4_0,
        "Q4_1": gguf.GGMLQuantizationType.Q4_1,
        "Q5_0": gguf.GGMLQuantizationType.Q5_0,
        "Q5_1": gguf.GGMLQuantizationType.Q5_1,
        "Q4_K": gguf.GGMLQuantizationType.Q4_K,
        "Q5_K": gguf.GGMLQuantizationType.Q5_K,
        "Q6_K": gguf.GGMLQuantizationType.Q6_K,
        "Q2_K": gguf.GGMLQuantizationType.Q2_K,
        "Q3_K": gguf.GGMLQuantizationType.Q3_K,
    }

    if quantizacao not in quant_map:
        print(f"⚠️  Quantização '{quantizacao}' não reconhecida. Usando Q4_K.")
        quantizacao = "Q4_K"

    quant_type = quant_map[quantizacao]
    tipo_arquivo_valor = quant_type.value

    nome_arquivo = f"rigelslm_{quantizacao}.gguf"
    caminho_saida = PASTA_GGUF / nome_arquivo

    # Cria escritor com architecture='llama'
    writer = gguf.GGUFWriter(path=str(caminho_saida), arch="llama")

    # ======== METADADOS OBRIGATÓRIOS ========
    writer.add_string("general.architecture", "llama")
    writer.add_uint32("llama.context_length", SEQ_LEN)
    writer.add_uint32("llama.embedding_length", EMBED_DIM)
    writer.add_uint32("llama.block_count", NUM_LAYERS)
    writer.add_uint32("llama.feed_forward_length", FF_DIM)
    writer.add_uint32("llama.attention.head_count", NUM_HEADS)
    writer.add_uint32("llama.attention.head_count_kv", NUM_HEADS)
    writer.add_float32("llama.attention.layer_norm_rms_epsilon", 1e-5)
    writer.add_uint32("llama.rope.dimension_count", EMBED_DIM // NUM_HEADS)
    writer.add_float32("llama.rope.freq_base", 10000.0)
    writer.add_string("llama.rope.scaling.type", "none")
    writer.add_float32("llama.rope.scaling.factor", 1.0)

    # ===== VOCAB_SIZE =====
    writer.add_uint32("llama.vocab_size", VOCAB_SIZE)
    writer.add_uint32("general.vocab_size", VOCAB_SIZE)

    writer.add_uint32("general.file_type", tipo_arquivo_valor)

    # ======== METADADOS PERSONALIZADOS ========
    writer.add_string("general.name", NOME_MODELO)
    writer.add_string("general.version", VERSAO)
    writer.add_string("general.author", AUTOR)
    writer.add_string("general.description", "RigelSLM - Small Language Model para Português Brasileiro")
    writer.add_string("general.license", "MIT")

    if metadados:
        for key, value in metadados.items():
            writer.add_string(f"training.{key}", str(value))

    writer.add_string("system.build_date", datetime.now().isoformat())
    writer.add_string("system.os", platform.system())
    writer.add_string("system.python_version", platform.python_version())
    writer.add_string("system.torch_version", torch.__version__)

    # ======== EXPORTA TOKENIZER ========
    exportar_tokenizer_gguf(writer, tokenizer)

    # ======== ADICIONA TENSORES ========
    for nome, tensor in tensores_gguf.items():
        writer.add_tensor(nome, tensor, raw_dtype=gguf.GGMLQuantizationType.F32)

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    return caminho_saida

# =============================================================================
# 7. GERAÇÃO DO MODELFILE
# =============================================================================

def gerar_modelfile(caminho_gguf: Path, nome_modelo: str, quantizacao: str) -> Path:
    caminho_modelfile = caminho_gguf.parent / f"Modelfile.rigelslm_{quantizacao}"
    conteudo = f"""# Modelfile para RigelSLM (quantização {quantizacao})
FROM {caminho_gguf.absolute()}

TEMPLATE \"\"\"{{{{ .Prompt }}}}\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_predict 256
PARAMETER repeat_penalty 1.1
PARAMETER stop "</s>"

SYSTEM \"\"\"Você é RigelSLM, um assistente de IA em português brasileiro.\"\"\"
"""
    with open(caminho_modelfile, 'w', encoding='utf-8') as f:
        f.write(conteudo)
    return caminho_modelfile

# =============================================================================
# 8. MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, help="Caminho do modelo .pt")
    parser.add_argument("--quant", type=str, default="Q4_K",
                        choices=["F16", "F32", "Q8_0", "Q4_0", "Q4_1",
                                 "Q5_0", "Q5_1", "Q4_K", "Q5_K", "Q6_K", "Q2_K", "Q3_K"],
                        help="Quantização (padrão: Q4_K)")
    parser.add_argument("--modelfile", type=str, default="rigelslm",
                        help="Nome do modelo no Ollama")
    parser.add_argument("--tokenizer", type=str, default=None,
                        help="Caminho do tokenizer.json")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print(f"   ⭐ {NOME_MODELO} - CONVERSOR PARA GGUF + MODELFILE (v3.7)")
    print("=" * 70)

    # Localiza modelo
    if args.model:
        caminho_modelo = Path(args.model)
        if not caminho_modelo.exists():
            print(f"❌ Modelo não encontrado: {caminho_modelo}")
            sys.exit(1)
    else:
        caminho_modelo = localizar_modelo()
        if caminho_modelo is None:
            print("❌ Nenhum modelo encontrado na pasta 'modelo'.")
            sys.exit(1)
    print(f"📦 Modelo: {caminho_modelo}")

    # Detecta vocab_size real do embedding
    state_dict_check = torch.load(caminho_modelo, map_location='cpu')
    if "embedding.weight" in state_dict_check:
        real_vocab = state_dict_check["embedding.weight"].shape[0]
        print(f"📊 Vocab detectado: {real_vocab} (config: {VOCAB_SIZE})")
    del state_dict_check

    # Tokenizer
    tokenizer_path = Path(args.tokenizer) if args.tokenizer else PASTA_TOKENIZER / "tokenizer.json"
    if not tokenizer_path.exists():
        print(f"❌ Tokenizer não encontrado em {tokenizer_path}")
        sys.exit(1)
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    print(f"✅ Tokenizer carregado: {tokenizer_path}")

    # Carrega pesos
    print("🔄 Carregando pesos...")
    state_dict = torch.load(caminho_modelo, map_location='cpu')

    # Métricas
    metricas = carregar_metricas()
    if metricas:
        print(f"📊 Última época: {metricas.get('epoch', 'N/A')}, Loss: {metricas.get('val_loss', 'N/A')}")

    # Trunca embedding para o tamanho real do tokenizer
    real_vocab_tokenizer = len(tokenizer.get_vocab())
    if "embedding.weight" in state_dict:
        emb_shape = state_dict["embedding.weight"].shape
        if emb_shape[0] > real_vocab_tokenizer:
            print(f"   ✂️ Truncando embedding de {emb_shape[0]} para {real_vocab_tokenizer} tokens")
            state_dict["embedding.weight"] = state_dict["embedding.weight"][:real_vocab_tokenizer]
            globals()['VOCAB_SIZE'] = real_vocab_tokenizer
        elif emb_shape[0] != real_vocab_tokenizer:
            print(f"   ⚠️ Embedding tem {emb_shape[0]} tokens, tokenizer tem {real_vocab_tokenizer}")
    if "lm_head.weight" in state_dict:
        lm_shape = state_dict["lm_head.weight"].shape
        if lm_shape[0] > real_vocab_tokenizer:
            state_dict["lm_head.weight"] = state_dict["lm_head.weight"][:real_vocab_tokenizer]
        if "lm_head.bias" in state_dict and state_dict["lm_head.bias"].shape[0] > real_vocab_tokenizer:
            state_dict["lm_head.bias"] = state_dict["lm_head.bias"][:real_vocab_tokenizer]

    # Mapeia tensores (com transposição)
    print("🔄 Mapeando tensores (com transposição do embedding)...")
    tensores_gguf = mapear_tensores(state_dict)
    print(f"   ✅ {len(tensores_gguf)} tensores mapeados.")

    # Gera GGUF
    print(f"🔄 Gerando GGUF com quantização {args.quant}...")
    inicio = time.time()
    caminho_gguf = escrever_gguf(tensores_gguf, tokenizer, args.quant, metricas)
    tempo_gguf = time.time() - inicio

    tamanho_mb = caminho_gguf.stat().st_size / (1024 * 1024)
    print(f"✅ GGUF gerado: {caminho_gguf}")
    print(f"   Tamanho: {tamanho_mb:.2f} MB")
    print(f"   Tempo: {tempo_gguf:.2f}s")

    # Modelfile
    print("🔄 Gerando Modelfile para Ollama...")
    caminho_modelfile = gerar_modelfile(caminho_gguf, args.modelfile, args.quant)
    print(f"✅ Modelfile criado: {caminho_modelfile}")

    print("\n" + "=" * 70)
    print("🚀 CONVERSÃO CONCLUÍDA!")
    print(f"   Teste primeiro no llama.cpp:")
    print(f"   .\\llama.exe cli -m {caminho_gguf} -p 'Olá' -n 20")
    print(f"\n   Depois crie no Ollama:")
    print(f"   ollama create {args.modelfile} -f {caminho_modelfile.absolute()}")
    print("=" * 70)

if __name__ == "__main__":
    main()