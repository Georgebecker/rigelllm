#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
================================================================================
RIGELSLM - CONVERSOR PARA GGUF + MODELFILE (v1.0.0)
================================================================================
Converte o modelo treinado (.pt) para GGUF com transposição do embedding
para compatibilidade com llama.cpp/Ollama.

Uso:
    python converter_para_gguf.py --model modelo/modelo_melhor.pt --quant Q4_K_M
    python converter_para_gguf.py --model modelo/modelo.pt --quant Q8_0 --output meu_modelo.gguf
================================================================================
"""

import os
import sys
import json
import argparse
import time
import platform
import subprocess
from pathlib import Path
from datetime import datetime

# Console UTF-8 (evita crash com emojis no cp1252 do Windows)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
# 2. CONFIGURAÇÕES PADRÃO
# =============================================================================

ROOT = Path(__file__).resolve().parent
PASTA_MODELO = ROOT / "modelo"
PASTA_TOKENIZER = ROOT / "tokenizer"
PASTA_LOGS = ROOT / "logs"
PASTA_GGUF = ROOT / "gguf"
PASTA_GGUF.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 3. METADADOS
# =============================================================================

NOME_MODELO = "RigelSLM"
VERSAO = "1.0.0"
AUTOR = "George Herman Becker"
DESCRICAO = "RigelSLM - Small Language Model para Português Brasileiro"
LICENCA = "MIT"

# =============================================================================
# 4. PARÂMETROS DO MODELO (extraídos do treino.py)
# =============================================================================

def importar_parametros():
    """Importa os parâmetros do modelo a partir do treino.py."""
    sys.path.insert(0, str(ROOT))
    try:
        from treino import VOCAB_SIZE, EMBED_DIM, NUM_LAYERS, NUM_HEADS, FF_DIM, SEQ_LEN
        return VOCAB_SIZE, EMBED_DIM, NUM_LAYERS, NUM_HEADS, FF_DIM, SEQ_LEN
    except ImportError as e:
        print(f"❌ Erro ao importar treino.py: {e}")
        print("⚠️  Usando valores padrão (pode causar incompatibilidade).")
        return 23830, 512, 8, 8, 2048, 512

VOCAB_SIZE, EMBED_DIM, NUM_LAYERS, NUM_HEADS, FF_DIM, SEQ_LEN = importar_parametros()

# Contexto gravado no GGUF. O Ollama LIMITA o contexto do modelo a este valor
# (ignora num_ctx do pedido quando o GGUF é menor) — com 512 o chat estourava
# ("exceeds context size"). Usamos 2048: a posição é sinusoidal e extrapola
# bem além dos 512 do treino.
CONTEXT_LENGTH_GGUF = 2048

# =============================================================================
# 5. MAPEAMENTO DE TENSORES (com transposição do embedding)
# =============================================================================

def mapear_tensores(state_dict):
    """
    Mapeia os tensores do PyTorch para o formato GGUF (arquitetura llama).
    Baseado na estrutura do tinyllama (que funciona no Ollama).
    
    Regras:
    - SEM biases (llama.cpp não usa biases em nenhum tensor)
    - token_embd.weight: transposto para [embed_dim, vocab_size]
    - output.weight: transposto para [embed_dim, vocab_size]
    - ffn_gate/ffn_up: transpostos para [embed_dim, ff_dim]
    - ffn_down: transposto para [ff_dim, embed_dim]
    - attn_q/k/v/output: transpostos para [embed_dim, embed_dim]
    - output_norm.weight: identidade (modelo não tem norm final)
    """
    tensores = {}

    def to_f32(arr):
        """Converte para float32 2D."""
        a = np.asarray(arr, dtype=np.float32)
        if a.ndim > 2:
            a = a.reshape(a.shape[0], -1)
        return a

    # Embedding: mantém [vocab_size, embed_dim] (sem transpor)
    if "embedding.weight" in state_dict:
        emb = to_f32(state_dict["embedding.weight"])
        tensores["token_embd.weight"] = np.ascontiguousarray(emb)

    # Output (lm_head): mantém [vocab_size, embed_dim] (sem transpor)
    if "lm_head.weight" in state_dict:
        out = to_f32(state_dict["lm_head.weight"])
        tensores["output.weight"] = np.ascontiguousarray(out)

    # Output norm (identidade - modelo não tem norm final)
    tensores["output_norm.weight"] = np.ones(EMBED_DIM, dtype=np.float32)

    # Camadas
    for i in range(NUM_LAYERS):
        prefix = f"decoder.layers.{i}."

        # --- Atenção ---
        # in_proj_weight: [3*embed_dim, embed_dim] -> split Q,K,V cada [embed_dim, embed_dim]
        if f"{prefix}self_attn.in_proj_weight" in state_dict:
            in_proj = to_f32(state_dict[f"{prefix}self_attn.in_proj_weight"])
            q, k, v = np.split(in_proj, 3, axis=0)
            # Cada um: [embed_dim, embed_dim] - já está no formato GGUF
            tensores[f"blk.{i}.attn_q.weight"] = np.ascontiguousarray(q)
            tensores[f"blk.{i}.attn_k.weight"] = np.ascontiguousarray(k)
            tensores[f"blk.{i}.attn_v.weight"] = np.ascontiguousarray(v)

        # out_proj: [embed_dim, embed_dim]
        if f"{prefix}self_attn.out_proj.weight" in state_dict:
            out_proj = to_f32(state_dict[f"{prefix}self_attn.out_proj.weight"])
            tensores[f"blk.{i}.attn_output.weight"] = np.ascontiguousarray(out_proj)

        # --- FFN ---
        # linear1: [ff_dim, embed_dim] (PyTorch: out_features, in_features)
        # Mantém como [ff_dim, embed_dim] para ffn_gate
        if f"{prefix}linear1.weight" in state_dict:
            lin1 = to_f32(state_dict[f"{prefix}linear1.weight"])
            tensores[f"blk.{i}.ffn_gate.weight"] = np.ascontiguousarray(lin1)
            # ffn_up = cópia (modelo usa GELU simples, não SwiGLU)
            tensores[f"blk.{i}.ffn_up.weight"] = np.ascontiguousarray(lin1.copy())

        # linear2: [embed_dim, ff_dim] (PyTorch: out_features, in_features)
        # Mantém como [embed_dim, ff_dim] para ffn_down
        if f"{prefix}linear2.weight" in state_dict:
            lin2 = to_f32(state_dict[f"{prefix}linear2.weight"])
            tensores[f"blk.{i}.ffn_down.weight"] = np.ascontiguousarray(lin2)

        # --- Layer Norms (sem bias) ---
        if f"{prefix}norm1.weight" in state_dict:
            tensores[f"blk.{i}.attn_norm.weight"] = to_f32(state_dict[f"{prefix}norm1.weight"])
        if f"{prefix}norm2.weight" in state_dict:
            tensores[f"blk.{i}.ffn_norm.weight"] = to_f32(state_dict[f"{prefix}norm2.weight"])

    return tensores

# =============================================================================
# 6. EXPORTAÇÃO DO TOKENIZER (CORRIGIDA)
# =============================================================================

def exportar_tokenizer_gguf(writer, tokenizer: Tokenizer):
    """
    Exporta o tokenizer no formato esperado pelo GGUF.
    - Usa arrays para tokens/scores/token_type (Ollama aceita).
    - Usa STRING única para merges (Ollama NÃO aceita ARRAY de strings).
    - Define tokens especiais e configurações BPE.
    """
    vocab = tokenizer.get_vocab()
    sorted_vocab = sorted(vocab.items(), key=lambda x: x[1])
    tokens = [token for token, _ in sorted_vocab]
    scores = [0.0] * len(tokens)

    # ✅ CORRIGIDO (06/08): o tokenizer HF ByteLevel (estilo GPT-2) marca espaço
    # com 'Ġ' (U+0120). Com `tokenizer.ggml.model = "gpt2"` o llama.cpp faz
    # byte-encoding GPT-2 (espaço 0x20 → 'Ġ') e espera 'Ġ' no vocab E nos
    # merges — NÃO '▁' (U+2581). A conversão Ġ→▁ quebrava o BPE (IDs errados →
    # saída vazia/lixo, palavras coladas). Confirmado em src/llama-vocab.cpp
    # (llm_tokenizer_bpe, byte_encode=true). Logo: NÃO converter.
    # tokens = [t.replace("\u0120", "\u2581") for t in tokens]

    # Extrai merges do tokenizer
    merges_list = []
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
            temp_path = f.name
        tokenizer.save(temp_path)
        with open(temp_path, 'r', encoding='utf-8') as f:
            tok_data = json.load(f)
        os.unlink(temp_path)
        merges_list = tok_data.get("model", {}).get("merges", [])
        # Converte pares ['a', 'b'] para string 'a b'
        if merges_list and isinstance(merges_list[0], list):
            merges_list = [f"{a} {b}" for a, b in merges_list]
        # ✅ Idem tokens: manter 'Ġ' nos merges (byte-encoding GPT-2).
        # merges_list = [m.replace("\u0120", "\u2581") for m in merges_list]
    except Exception as e:
        print(f"   ⚠️ Erro ao extrair merges: {e}")

    # Define modelo como 'gpt2' (BPE ByteLevel)
    writer.add_string("tokenizer.ggml.model", "gpt2")
    # ✅ CORRIGIDO (06/08): `tokenizer.ggml.pre` define o PRÉ-TOKENIZER. Para
    # ByteLevel BPE (GPT-2) o valor correto é "gpt-2" (byte-encoding: espaço →
    # 'Ġ'). Antes ficava SEM pre → llama.cpp usava 'default' e avisava
    # "missing pre-tokenizer type... GENERATION QUALITY WILL BE DEGRADED".
    # ("bytelevel" não é valor válido — por isso o LOAD quebrava em 05/08.)
    writer.add_string("tokenizer.ggml.pre", "gpt-2")
    writer.add_array("tokenizer.ggml.tokens", tokens)
    writer.add_array("tokenizer.ggml.scores", scores)
    # ⚠️ token_type (04/08): marcar os tokens ESPECIAIS (índices fixos do treino)
    # como CONTROL/UNKNOWN — antes TUDO era 0 (NORMAL) e o llama.cpp avisava
    # "control-looking token was not control-type; this is probably a bug" e
    # sobrescrevia, o que quebrava o EOG/entrega da geração no Ollama.
    # 0=NORMAL, 1=UNKNOWN, 2=CONTROL (padrão gpt2/ByteLevel).
    _tipos = [0] * len(tokens)
    for _i, _tipo in ((0, 2), (1, 1), (2, 2), (3, 2), (4, 2)):  # PAD,UNK,BOS,EOS,SEP
        if _i < len(_tipos):
            _tipos[_i] = _tipo
    writer.add_array("tokenizer.ggml.token_type", _tipos)

    # Merges como ARRAY de strings — é o formato que o llama.cpp espera.
    # (o formato "string única" não era lido: o BPE degenerava para letras
    # soltas e a decodificação saía vazia/corrompida no Ollama)
    if merges_list:
        writer.add_array("tokenizer.ggml.merges", merges_list)
        print(f"   ✅ {len(merges_list)} merges adicionados (como array).")
    else:
        print("   ⚠️ Nenhum merge encontrado!")

    # Configuração ByteLevel
    # ✅ add_space_prefix=false (06/08): no path BPE do llama.cpp o padrão é
    # false — o espaço entra via byte-encoding 'Ġ'. True aqui somava com o
    # byte-encoding e bagunçava a decodificação.
    writer.add_bool("tokenizer.ggml.add_space_prefix", False)
    writer.add_bool("tokenizer.ggml.add_bos_token", True)
    writer.add_bool("tokenizer.ggml.remove_extra_whitespace", False)

    # Tokens especiais (IDs fixos conforme treino)
    special_tokens = {"pad": 0, "unk": 1, "bos": 2, "eos": 3, "sep": 4}
    for name, token_id in special_tokens.items():
        writer.add_uint32(f"tokenizer.ggml.{name}_token_id", token_id)
    writer.add_string("tokenizer.ggml.eos_token", "[EOS]")

    # ⚠️ CHAT TEMPLATE (04/08): o llama.cpp/Ollama usa sintaxe JINJA, NÃO
    # Go-template. `{{ .Prompt }}` quebra o load ("Unexpected token: . of type 17").
    # Template mínimo de completion em Jinja válido: `{{ prompt }}`.
    writer.add_string("tokenizer.chat_template", "{{ prompt }}")

    print(f"   ✅ Tokenizer exportado: {len(tokens)} tokens, {len(merges_list)} merges")

# =============================================================================
# 7. ESCRITA DO GGUF
# =============================================================================

def escrever_gguf(tensores_gguf, tokenizer, quantizacao="Q4_K_M", metadados=None, output_path=None, dtype_base="F16"):
    """
    Cria o arquivo GGUF com todos os metadados e tensores.
    O dtype REAL dos tensores é `dtype_base` (F16 por padrão). A quantização
    K/Q (Q4_K_M, Q8_0, ...) é feita em PASSO SEPARADO com o llama-quantize —
    a lib Python `gguf` NÃO quantiza (add_tensor grava o dtype que recebe).
    """
    if metadados is None:
        metadados = {}

    # Dtype REAL dos tensores no arquivo (F16 = metade do F32, base ideal p/ quantizar)
    dtype_base = dtype_base.upper()
    if dtype_base == "F32":
        ggml_dtype = gguf.GGMLQuantizationType.F32
    else:
        ggml_dtype = gguf.GGMLQuantizationType.F16
        dtype_base = "F16"

    # Mapeamento de quantização (referência: general.file_type + Modelfile)
    quant_map = {
        "F16": gguf.GGMLQuantizationType.F16,
        "F32": gguf.GGMLQuantizationType.F32,
        "Q8_0": gguf.GGMLQuantizationType.Q8_0,
        "Q4_0": gguf.GGMLQuantizationType.Q4_0,
        "Q4_1": gguf.GGMLQuantizationType.Q4_1,
        "Q5_0": gguf.GGMLQuantizationType.Q5_0,
        "Q5_1": gguf.GGMLQuantizationType.Q5_1,
        "Q4_K": gguf.GGMLQuantizationType.Q4_K,
        "Q4_K_M": gguf.GGMLQuantizationType.Q4_K,
        "Q5_K": gguf.GGMLQuantizationType.Q5_K,
        "Q5_K_M": gguf.GGMLQuantizationType.Q5_K,
        "Q6_K": gguf.GGMLQuantizationType.Q6_K,
        "Q2_K": gguf.GGMLQuantizationType.Q2_K,
        "Q3_K": gguf.GGMLQuantizationType.Q3_K,
    }

    if quantizacao not in quant_map:
        print(f"⚠️  Quantização '{quantizacao}' não reconhecida. Usando Q4_K_M.")
        quantizacao = "Q4_K_M"
    quant_type = quant_map[quantizacao]

    # Define caminho de saída
    if output_path is None:
        output_path = PASTA_GGUF / f"rigelslm_{quantizacao}.gguf"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Cria o escritor com architecture='llama'
    writer = gguf.GGUFWriter(path=str(output_path), arch="llama")

    # ======== METADADOS OBRIGATÓRIOS ========
    # NOTA: O GGUFWriter já adiciona 'general.architecture' automaticamente.
    # Não adicionamos novamente para evitar duplicação.
    writer.add_uint32("llama.context_length", CONTEXT_LENGTH_GGUF)
    writer.add_uint32("llama.embedding_length", EMBED_DIM)
    writer.add_uint32("llama.block_count", NUM_LAYERS)
    writer.add_uint32("llama.feed_forward_length", FF_DIM)
    writer.add_uint32("llama.attention.head_count", NUM_HEADS)
    writer.add_uint32("llama.attention.head_count_kv", NUM_HEADS)  # mesmo número para Llama
    writer.add_float32("llama.attention.layer_norm_rms_epsilon", 1e-5)
    writer.add_uint32("llama.rope.dimension_count", EMBED_DIM // NUM_HEADS)
    writer.add_float32("llama.rope.freq_base", 10000.0)
    writer.add_string("llama.rope.scaling.type", "none")
    writer.add_float32("llama.rope.scaling.factor", 1.0)

    writer.add_uint32("llama.vocab_size", VOCAB_SIZE)
    writer.add_uint32("general.vocab_size", VOCAB_SIZE)
    # file_type = dtype REAL gravado (F32=0, F16=1). A quantização (Q4_K_M
    # etc.) é aplicada DEPOIS pelo llama-quantize, que regrava este campo
    # com o tipo real da quantização aplicada.
    writer.add_uint32("general.file_type", ggml_dtype.value)

    # ======== METADADOS PERSONALIZADOS ========
    writer.add_string("general.name", NOME_MODELO)
    writer.add_string("general.version", VERSAO)
    writer.add_string("general.author", AUTOR)
    writer.add_string("general.description", DESCRICAO)
    writer.add_string("general.license", LICENCA)

    for key, value in metadados.items():
        writer.add_string(f"training.{key}", str(value))

    writer.add_string("system.build_date", datetime.now().isoformat())
    writer.add_string("system.os", platform.system())
    writer.add_string("system.python_version", platform.python_version())
    writer.add_string("system.torch_version", torch.__version__)

    # ======== TOKENIZER ========
    exportar_tokenizer_gguf(writer, tokenizer)

    # ======== TENSORES ========
    # Converte para o dtype base REAL antes de gravar (add_tensor NÃO converte
    # — o array precisa estar no dtype declarado no cabeçalho).
    # ⚠️ CRÍTICO (04/08): os NORMS (1D) ficam SEMPRE F32. A ativação do
    # llama.cpp é F32 e ggml_mul(f32, f16) não é suportado em CPU →
    # "binary_op: unsupported types: dst: f32, src0: f32, src1: f16" ao
    # carregar/inferir. Só as MATRIZES grandes (≥2D) vão no dtype base (F16).
    _SUFIXOS_NORM = ("attn_norm.weight", "ffn_norm.weight", "output_norm.weight")
    for nome, tensor in tensores_gguf.items():
        if nome.endswith(_SUFIXOS_NORM):
            tensor = np.asarray(tensor, dtype=np.float32)
            writer.add_tensor(nome, tensor,
                              raw_dtype=gguf.GGMLQuantizationType.F32)
        else:
            if dtype_base == "F16":
                tensor = np.asarray(tensor, dtype=np.float16)
            writer.add_tensor(nome, tensor, raw_dtype=ggml_dtype)

    # Escreve o arquivo
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()

    return output_path

# =============================================================================
# 8. GERAÇÃO DO MODELFILE
# =============================================================================

def gerar_modelfile(caminho_gguf, nome_modelo="rigelslm", quantizacao="Q4_K_M"):
    """
    Gera um Modelfile para uso com o Ollama.
    """
    caminho_modelfile = caminho_gguf.parent / f"Modelfile.{nome_modelo}_{quantizacao}"
    conteudo = f"""# Modelfile para {nome_modelo} (quantização {quantizacao})
FROM {caminho_gguf.absolute()}

TEMPLATE \"\"\"{{{{ .Prompt }}}}\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_predict 256
PARAMETER num_ctx 2048
PARAMETER repeat_penalty 1.1
PARAMETER stop "</s>"

SYSTEM \"\"\"Você é {nome_modelo}, um assistente de IA em português brasileiro.\"\"\"
"""
    with open(caminho_modelfile, 'w', encoding='utf-8') as f:
        f.write(conteudo)
    return caminho_modelfile

# =============================================================================
# 9. FUNÇÕES AUXILIARES
# =============================================================================

def localizar_modelo():
    """Procura automaticamente por um checkpoint na pasta modelo/."""
    candidatos = ["modelo_melhor.pt", "modelo.pt", "modelo_last.pt"]
    for nome in candidatos:
        caminho = PASTA_MODELO / nome
        if caminho.exists():
            return caminho
    return None

def carregar_metricas():
    """Carrega as últimas métricas de treino (para metadados)."""
    metricas_path = PASTA_LOGS / "metricas.json"
    if not metricas_path.exists():
        return {}
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


# =============================================================================
# 9b. QUANTIZAÇÃO REAL (llama-quantize)
# =============================================================================

QUANTS_REAIS = {"Q2_K", "Q3_K", "Q3_K_S", "Q3_K_M", "Q3_K_L",
                "Q4_0", "Q4_1", "Q4_K", "Q4_K_S", "Q4_K_M",
                "Q5_0", "Q5_1", "Q5_K", "Q5_K_S", "Q5_K_M",
                "Q6_K", "Q8_0"}


def _localizar_llama_quantize():
    """Localiza o llama-quantize (PATH ou pasta do winget llama.cpp)."""
    import shutil
    nome = "llama-quantize.exe" if platform.system() == "Windows" else "llama-quantize"
    caminho = shutil.which(nome)
    if caminho:
        return Path(caminho)
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if base.exists():
        for p in sorted(base.glob("ggml.llamacpp*")):
            cand = p / nome
            if cand.exists():
                return cand
    return None


def quantizar_com_llama(entrada: Path, saida: Path, quant: str) -> bool:
    """Aplica quantização REAL (Q4_K_M, Q8_0, ...) via llama-quantize."""
    llama_quantize = _localizar_llama_quantize()
    if llama_quantize is None:
        print("⚠️  llama-quantize não encontrado — GGUF fica no base (F16/F32).")
        return False
    print(f"🔄 Quantização REAL {quant} com llama-quantize...")
    r = subprocess.run([str(llama_quantize), str(entrada), str(saida),
                        quant, "8"],  # 8 threads
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode == 0 and saida.exists():
        print(f"   ✅ Quantizado: {saida} ({saida.stat().st_size / 1048576:.2f} MB)")
        return True
    print(f"   ⚠️  llama-quantize falhou (código {r.returncode}).")
    saida_tail = (r.stdout or "").strip().splitlines()[-15:]
    if saida_tail:
        print("   --- saída ---")
        for linha in saida_tail:
            print("   ", linha)
    err_tail = (r.stderr or "").strip().splitlines()[-5:]
    if err_tail:
        print("   --- stderr ---")
        for linha in err_tail:
            print("   ", linha)
    return False


# =============================================================================
# 10. MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Conversor de .pt para GGUF (RigelSLM)")
    parser.add_argument("--model", type=str, help="Caminho do modelo .pt (se não especificado, busca automaticamente)")
    parser.add_argument("--quant", type=str, default="Q4_K_M",
                        choices=["F16", "F32", "Q8_0", "Q4_0", "Q4_1",
                                 "Q5_0", "Q5_1", "Q4_K", "Q4_K_M",
                                 "Q5_K", "Q5_K_M", "Q6_K", "Q2_K", "Q3_K"],
                        help="Quantização (padrão: Q4_K_M)")
    parser.add_argument("--output", type=str, help="Caminho de saída para o arquivo GGUF (opcional)")
    parser.add_argument("--modelfile", type=str, default="rigelslm",
                        help="Nome do modelo para o Modelfile (padrão: rigelslm)")
    parser.add_argument("--tokenizer", type=str, help="Caminho do tokenizer.json (opcional)")
    parser.add_argument("--no-modelfile", action="store_true", help="Não gerar Modelfile")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print(f"   ⭐ {NOME_MODELO} - CONVERSOR PARA GGUF (v1.0.0)")
    print("=" * 70)

    # --- Localiza modelo ---
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

    # --- Detecta vocab real ---
    state_dict_check = torch.load(caminho_modelo, map_location='cpu')
    if "embedding.weight" in state_dict_check:
        real_vocab = state_dict_check["embedding.weight"].shape[0]
        print(f"📊 Vocab detectado no embedding: {real_vocab} (config: {VOCAB_SIZE})")
    del state_dict_check

    # --- Tokenizer ---
    tokenizer_path = Path(args.tokenizer) if args.tokenizer else PASTA_TOKENIZER / "tokenizer.json"
    if not tokenizer_path.exists():
        print(f"❌ Tokenizer não encontrado em {tokenizer_path}")
        sys.exit(1)
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    print(f"✅ Tokenizer carregado: {tokenizer_path}")

    # --- Carrega pesos ---
    print("🔄 Carregando pesos...")
    state_dict = torch.load(caminho_modelo, map_location='cpu')

    # --- Métricas ---
    metricas = carregar_metricas()
    if metricas:
        print(f"📊 Última época: {metricas.get('epoch', 'N/A')}, Loss: {metricas.get('val_loss', 'N/A')}")

    # --- Trunca embedding se necessário ---
    real_vocab_tokenizer = len(tokenizer.get_vocab())
    if "embedding.weight" in state_dict:
        emb_shape = state_dict["embedding.weight"].shape
        if emb_shape[0] > real_vocab_tokenizer:
            print(f"   ✂️ Truncando embedding de {emb_shape[0]} para {real_vocab_tokenizer} tokens")
            state_dict["embedding.weight"] = state_dict["embedding.weight"][:real_vocab_tokenizer]
            # Atualiza VOCAB_SIZE global
            globals()['VOCAB_SIZE'] = real_vocab_tokenizer
        elif emb_shape[0] != real_vocab_tokenizer:
            print(f"   ⚠️ Embedding tem {emb_shape[0]} tokens, tokenizer tem {real_vocab_tokenizer}")
    if "lm_head.weight" in state_dict:
        lm_shape = state_dict["lm_head.weight"].shape
        if lm_shape[0] > real_vocab_tokenizer:
            state_dict["lm_head.weight"] = state_dict["lm_head.weight"][:real_vocab_tokenizer]
        if "lm_head.bias" in state_dict and state_dict["lm_head.bias"].shape[0] > real_vocab_tokenizer:
            state_dict["lm_head.bias"] = state_dict["lm_head.bias"][:real_vocab_tokenizer]

    # --- Mapeia tensores ---
    print("🔄 Mapeando tensores (com transposição do embedding)...")
    tensores_gguf = mapear_tensores(state_dict)
    print(f"   ✅ {len(tensores_gguf)} tensores mapeados.")

    # --- Determina o fluxo de quantização ---
    quant_alvo = args.quant.upper()
    eh_quant_real = quant_alvo in QUANTS_REAIS

    # Base: F16 (ideal p/ quantizar depois); F32 só se pedido explicitamente.
    dtype_base = "F16"
    arquivo_base = Path(args.output) if args.output else (
        PASTA_GGUF / f"rigelslm_f32.gguf" if quant_alvo == "F32"
        else PASTA_GGUF / "rigelslm_f16.gguf"
    )
    arquivo_base.parent.mkdir(parents=True, exist_ok=True)

    # --- Gera o GGUF base (dtype real) ---
    print(f"🔄 Gerando GGUF base ({dtype_base})...")
    inicio = time.time()
    caminho_base = escrever_gguf(
        tensores_gguf,
        tokenizer,
        quantizacao=dtype_base,
        metadados=metricas,
        output_path=arquivo_base,
        dtype_base=dtype_base,
    )
    tempo = time.time() - inicio
    tamanho_mb = caminho_base.stat().st_size / (1024 * 1024)
    print(f"✅ GGUF base: {caminho_base}")
    print(f"   Tamanho: {tamanho_mb:.2f} MB | Tempo: {tempo:.2f}s")

    # --- Quantização REAL (se pedida) ---
    caminho_final = caminho_base
    tag = dtype_base.lower()
    if eh_quant_real:
        saida_quant = PASTA_GGUF / f"rigelslm_{quant_alvo}.gguf"
        if quantizar_com_llama(caminho_base, saida_quant, quant_alvo):
            caminho_final = saida_quant
            tag = quant_alvo.lower()
        else:
            print("   Usando o GGUF base (F16) como resultado final.")

    # --- Modelfile ---
    if not args.no_modelfile:
        print("🔄 Gerando Modelfile para Ollama...")
        caminho_modelfile = gerar_modelfile(caminho_final, args.modelfile, quant_alvo if eh_quant_real else dtype_base)
        print(f"✅ Modelfile criado: {caminho_modelfile}")
    else:
        caminho_modelfile = None

    # --- Resumo final ---
    print("\n" + "=" * 70)
    print("🚀 CONVERSÃO CONCLUÍDA!")
    print(f"   GGUF final: {caminho_final}")
    if caminho_modelfile:
        print(f"   Modelfile: {caminho_modelfile}")
        print(f"\n   Para criar no Ollama:")
        print(f"   ollama create rigelslm:{tag} -f {caminho_modelfile.absolute()}")
    print("\n   Teste com llama.cpp:")
    print(f"   llama-cli -m {caminho_final} -p 'Olá' -n 20")
    print("=" * 70)

if __name__ == "__main__":
    main()