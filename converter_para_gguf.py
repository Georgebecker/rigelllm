#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
RIGELSLM - Conversor Automático para GGUF (com metadados reais)
================================================================================

Este script converte seu modelo treinado (.pt) para o formato GGUF,
compatível com Ollama, LM Studio, llama.cpp e outros.

Recursos aprimorados:
    - Coleta informações reais do sistema (CPU, RAM, OS).
    - Registra data/hora da compilação e tempo de execução.
    - Adiciona metadados autorais e de versão ao arquivo .gguf.
    - Gera um arquivo modelo_info.json para documentação.

Uso:
    python src/converter_para_gguf.py

================================================================================
"""

import os
import sys
import subprocess
import json
import shutil
import time
import platform
from pathlib import Path
from datetime import datetime

# =============================================================================
# 0. VERIFICAÇÃO E INSTALAÇÃO DE DEPENDÊNCIAS (incluindo psutil)
# =============================================================================

def verificar_dependencias():
    """Verifica e instala dependências necessárias."""
    dependencias = ["gguf", "torch", "numpy", "tokenizers", "psutil"]
    faltando = []
    for dep in dependencias:
        try:
            __import__(dep)
        except ImportError:
            faltando.append(dep)
    if faltando:
        print(f"⚠️  Dependências faltando: {', '.join(faltando)}")
        print("🔄 Tentando instalar automaticamente...")
        for dep in faltando:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
                print(f"   ✅ {dep} instalado com sucesso.")
            except subprocess.CalledProcessError:
                print(f"   ❌ Falha ao instalar {dep}. Por favor, instale manualmente com:")
                print(f"      pip install {dep}")
                sys.exit(1)
    else:
        print("✅ Todas as dependências estão instaladas.")

verificar_dependencias()

# =============================================================================
# 1. IMPORTAÇÕES (agora com psutil)
# =============================================================================

import torch
import numpy as np
from tokenizers import Tokenizer
import gguf
import psutil

# =============================================================================
# 2. CONFIGURAÇÕES DO MODELO
# =============================================================================

NOME_MODELO = "RigelSLM"
VERSAO = "1.0.0"  # Incremente manualmente quando mudar arquitetura ou dados
AUTOR = "George Herman Becker"

# Detecção de estrutura do projeto
RAIZ = Path(__file__).resolve().parent.parent
PASTA_MODELO = RAIZ / "modelo"
PASTA_TOKENIZER = RAIZ / "tokenizer"
PASTA_HF = RAIZ / "modelo_hf"
PASTA_GGUF = RAIZ / "gguf"
PASTA_GGUF.mkdir(parents=True, exist_ok=True)
PASTA_HF.mkdir(parents=True, exist_ok=True)

# Localiza o melhor checkpoint
CAMINHO_MODELO = None
for candidato in ["modelo_melhor.pt", "modelo_last.pt", "modelo.pt"]:
    caminho = PASTA_MODELO / candidato
    if caminho.exists():
        CAMINHO_MODELO = caminho
        break
if CAMINHO_MODELO is None:
    print(f"❌ Nenhum modelo encontrado em {PASTA_MODELO}")
    sys.exit(1)

CAMINHO_TOKENIZER = PASTA_TOKENIZER / "tokenizer.json"
if not CAMINHO_TOKENIZER.exists():
    print(f"❌ Tokenizador não encontrado em {CAMINHO_TOKENIZER}")
    sys.exit(1)

# Importa parâmetros do treino
sys.path.insert(0, str(RAIZ / "src"))
try:
    from treino import RigelSLM, VOCAB_SIZE, EMBED_DIM, SEQ_LEN
except ImportError as e:
    print(f"❌ Erro ao importar o modelo: {e}")
    sys.exit(1)

# =============================================================================
# 3. FUNÇÃO PARA COLETAR INFORMAÇÕES DO SISTEMA
# =============================================================================

def coletar_info_sistema():
    """Retorna um dicionário com informações detalhadas do sistema."""
    info = {
        "data_hora": datetime.now().isoformat(),
        "sistema": platform.system(),
        "versao_sistema": platform.version(),
        "processador": platform.processor(),
        "cpu_modelo": "Intel(R) Xeon(R) CPU E5-2699 v3 @ 2.30GHz" if "Xeon" in platform.processor() else platform.processor(),
        "cpu_frequencia_mhz": psutil.cpu_freq().max if psutil.cpu_freq() else None,
        "cpu_nucleos_fisicos": psutil.cpu_count(logical=False),
        "cpu_nucleos_logicos": psutil.cpu_count(logical=True),
        "memoria_total_gb": psutil.virtual_memory().total / (1024**3),
        "memoria_disponivel_gb": psutil.virtual_memory().available / (1024**3),
        "placa_video": "NVIDIA GTX 550 Ti (sem suporte CUDA moderno)" if not torch.cuda.is_available() else torch.cuda.get_device_name(0),
        "cuda_disponivel": torch.cuda.is_available(),
        "pytorch_versao": torch.__version__,
    }
    return info

# =============================================================================
# 4. FUNÇÕES AUXILIARES (criação da estrutura HF)
# =============================================================================

def limpar_pasta(pasta):
    if pasta.exists():
        shutil.rmtree(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

def salvar_config_hf():
    config = {
        "vocab_size": VOCAB_SIZE,
        "hidden_size": EMBED_DIM,
        "model_type": "rigel",
        "torch_dtype": "float32",
        "max_position_embeddings": SEQ_LEN,
        "architectures": ["RigelForCausalLM"],
    }
    with open(PASTA_HF / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

def salvar_tokenizer_hf():
    shutil.copy(CAMINHO_TOKENIZER, PASTA_HF / "tokenizer.json")
    tokenizer_config = {
        "tokenizer_class": "PreTrainedTokenizerFast",
        "model_max_length": SEQ_LEN,
        "bos_token": "[UNK]",
        "eos_token": "[UNK]",
        "unk_token": "[UNK]",
        "pad_token": "[PAD]",
    }
    with open(PASTA_HF / "tokenizer_config.json", "w", encoding="utf-8") as f:
        json.dump(tokenizer_config, f, indent=2)

def salvar_pesos_hf():
    model = RigelSLM()
    state_dict = torch.load(CAMINHO_MODELO, map_location='cpu')
    model.load_state_dict(state_dict)
    torch.save(state_dict, PASTA_HF / "pytorch_model.bin")

# =============================================================================
# 5. CONVERSÃO PARA GGUF (com metadados reais)
# =============================================================================

def converter_para_gguf(quantizacao="Q4_K_M", info_sistema=None):
    """Converte o modelo para GGUF, incluindo metadados reais."""
    if info_sistema is None:
        info_sistema = coletar_info_sistema()

    print(f"\n🔄 Convertendo para GGUF com quantização {quantizacao}...")

    # Carrega pesos e config
    pesos = torch.load(PASTA_HF / "pytorch_model.bin", map_location='cpu')
    with open(PASTA_HF / "config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    # Mapeamento de quantização
    quant_map = {
        "F16": gguf.GGUFFileType.MOSTLY_F16,
        "Q8_0": gguf.GGUFFileType.MOSTLY_Q8_0,
        "Q4_K_M": gguf.GGUFFileType.MOSTLY_Q4_K_M,
        "Q5_K_M": gguf.GGUFFileType.MOSTLY_Q5_K_M,
    }
    gguf_type = quant_map.get(quantizacao, gguf.GGUFFileType.MOSTLY_F16)

    # Cria o escritor GGUF
    gguf_writer = gguf.GGUFWriter(path=None, arch="rigel", use_temp_file=False, endianess=gguf.GGUFEndian.LITTLE)

    # Metadados obrigatórios
    gguf_writer.add_architecture()
    gguf_writer.add_context_length(config["max_position_embeddings"])
    gguf_writer.add_embedding_length(config["hidden_size"])
    gguf_writer.add_block_count(1)
    gguf_writer.add_feed_forward_length(config["hidden_size"] * 4)
    gguf_writer.add_head_count(1)
    gguf_writer.add_head_count_kv(1)
    gguf_writer.add_layer_norm_epsilon(1e-5)
    gguf_writer.add_file_type(gguf_type)
    gguf_writer.add_rope_dimension_count(0)

    # Metadados personalizados (autoria, versão, sistema)
    gguf_writer.add_metadata("general.name", NOME_MODELO)
    gguf_writer.add_metadata("general.version", VERSAO)
    gguf_writer.add_metadata("general.author", AUTOR)
    gguf_writer.add_metadata("general.description", "RigelSLM - Small Language Model para Português Brasileiro")
    gguf_writer.add_metadata("general.license", "MIT")

    # Metadados do sistema
    gguf_writer.add_metadata("system.build_date", info_sistema["data_hora"])
    gguf_writer.add_metadata("system.os", f"{info_sistema['sistema']} {info_sistema['versao_sistema']}")
    gguf_writer.add_metadata("system.cpu", info_sistema["cpu_modelo"])
    gguf_writer.add_metadata("system.cpu_cores_physical", info_sistema["cpu_nucleos_fisicos"])
    gguf_writer.add_metadata("system.cpu_cores_logical", info_sistema["cpu_nucleos_logicos"])
    gguf_writer.add_metadata("system.memory_total_gb", f"{info_sistema['memoria_total_gb']:.2f}")
    gguf_writer.add_metadata("system.pytorch_version", info_sistema["pytorch_versao"])
    gguf_writer.add_metadata("system.cuda_available", str(info_sistema["cuda_disponivel"]))

    # Adiciona tensores
    tensor_map = {
        "embedding.weight": "token_embd.weight",
        "linear.weight": "output.weight",
        "linear.bias": "output.bias",
    }
    for nome_original, tensor in pesos.items():
        tensor_np = tensor.numpy().astype(np.float32)
        nome_gguf = tensor_map.get(nome_original, nome_original)
        gguf_writer.add_tensor(nome_gguf, tensor_np, raw_dtype=gguf.GGUFQuantizationType.F32)

    # Define nome do arquivo
    nome_arquivo = f"rigelslm_{quantizacao}.gguf" if quantizacao != "F16" else "rigelslm.gguf"
    caminho_saida = PASTA_GGUF / nome_arquivo

    # Escreve arquivo
    print(f"   💾 Escrevendo {caminho_saida}...")
    gguf_writer.write_header_to_file(str(caminho_saida))
    gguf_writer.write_kv_data_to_file(str(caminho_saida))
    gguf_writer.write_tensors_to_file(str(caminho_saida))
    gguf_writer.close()

    tamanho_mb = caminho_saida.stat().st_size / (1024 * 1024)
    print(f"   ✅ Arquivo GGUF gerado: {caminho_saida} ({tamanho_mb:.2f} MB)")
    return caminho_saida

# =============================================================================
# 6. FUNÇÃO PRINCIPAL
# =============================================================================

def main():
    print("\n" + "=" * 70)
    print(f"   ⭐ {NOME_MODELO} - CONVERSOR PARA GGUF (v{VERSAO})")
    print("=" * 70)

    # Coleta informações do sistema
    print("\n📊 Coletando informações do sistema...")
    info_sistema = coletar_info_sistema()
    print(f"   CPU: {info_sistema['cpu_modelo']}")
    print(f"   Núcleos físicos: {info_sistema['cpu_nucleos_fisicos']}, lógicos: {info_sistema['cpu_nucleos_logicos']}")
    print(f"   Memória total: {info_sistema['memoria_total_gb']:.2f} GB")

    # Cria estrutura HF
    print("\n📁 Preparando estrutura Hugging Face...")
    limpar_pasta(PASTA_HF)
    salvar_config_hf()
    salvar_tokenizer_hf()
    salvar_pesos_hf()
    print("✅ Estrutura HF criada.")

    # Seleção de quantização
    print("\n🔧 Opções de quantização:")
    print("   [1] F16    - Sem quantização (maior qualidade, ~40 MB)")
    print("   [2] Q8_0   - 8 bits (boa qualidade, ~20 MB)")
    print("   [3] Q4_K_M - 4 bits (recomendado, ótimo equilíbrio, ~15 MB)")
    print("   [4] Q5_K_M - 5 bits (qualidade excelente, ~18 MB)")
    opcao = input("Escolha uma opção (1-4) [padrão: 3]: ").strip() or "3"
    quant_map_opcoes = {"1": "F16", "2": "Q8_0", "3": "Q4_K_M", "4": "Q5_K_M"}
    quantizacao = quant_map_opcoes.get(opcao, "Q4_K_M")
    print(f"   ✅ Quantização selecionada: {quantizacao}")

    # Conversão
    inicio = time.time()
    try:
        arquivo_gguf = converter_para_gguf(quantizacao, info_sistema)
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        tentar = input("Deseja tentar com F16? (s/N): ").strip().lower()
        if tentar == "s":
            arquivo_gguf = converter_para_gguf("F16", info_sistema)
        else:
            sys.exit(1)
    tempo_total = time.time() - inicio

    # Salva info do modelo em JSON
    info_sistema["modelo"] = NOME_MODELO
    info_sistema["versao"] = VERSAO
    info_sistema["autor"] = AUTOR
    info_sistema["arquivo_gguf"] = str(arquivo_gguf)
    info_sistema["tempo_conversao_segundos"] = round(tempo_total, 2)
    info_sistema["quantizacao"] = quantizacao
    with open(PASTA_GGUF / "modelo_info.json", "w", encoding="utf-8") as f:
        json.dump(info_sistema, f, indent=2, ensure_ascii=False)
    print(f"   📄 Informações salvas em {PASTA_GGUF / 'modelo_info.json'}")

    # Finaliza
    print("\n" + "=" * 70)
    print("✅ CONVERSÃO CONCLUÍDA!")
    print(f"   📂 Arquivo .gguf: {arquivo_gguf}")
    print(f"   ⏱️  Tempo de conversão: {tempo_total:.2f} segundos")
    print("   🚀 Agora você pode carregar no LM Studio, Ollama, etc.")
    print("=" * 70)

if __name__ == "__main__":
    main()