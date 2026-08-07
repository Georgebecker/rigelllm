#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================================
# RIGELSLM - TREINO AUTOMATIZADO OTIMIZADO (treinov2.py)
# Versão focada em máximo aprendizado com poucas pastas.
# Uso: python treinov2.py
# ============================================================================
#
# Características:
# - Escaneia automaticamente dados/processed/ em busca de subpastas com >= 10 .txt
# - Treina STEP épocas por pasta (padrão: 5, ajustável)
# - Reseta otimizador e scheduler a cada nova pasta (cada pasta começa com LR alta)
# - Early stopping mais tolerante (PATIENCE=20)
# - Scheduler com redução suave (factor=0.75, patience=6)
# - INTERRUPÇÃO SEGURA: Ctrl+C salva checkpoint e modelo antes de sair.
# ============================================================================

import os
import sys
import re
import json
import time
import math
import random
import gc
import traceback
import tempfile
import warnings
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
import multiprocessing

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau, LambdaLR
from torch.utils.data import IterableDataset, DataLoader
from torch.amp import GradScaler, autocast

from tokenizers import Tokenizer, models, trainers, pre_tokenizers, normalizers, processors, decoders
from tqdm import tqdm
import unicodedata

# ============================================================================
# BIBLIOTECAS OPCIONAIS
# ============================================================================
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BeautifulSoup = None
    BS4_AVAILABLE = False

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    fitz = None
    FITZ_AVAILABLE = False

try:
    import csv
    CSV_AVAILABLE = True
except ImportError:
    csv = None
    CSV_AVAILABLE = False

# Garante saída UTF-8 no console (emojis quebram no cp1252 do Windows)
for _stream in (sys.stdout, sys.stderr):
    _reconf = getattr(_stream, "reconfigure", None)
    if callable(_reconf):
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ============================================================================
# 1. CONFIGURAÇÕES GLOBAIS (OTIMIZADAS)
# ============================================================================

try:
    from tokenizers import Tokenizer as _Tok
    _tok = _Tok.from_file("tokenizer/tokenizer.json")
    VOCAB_SIZE_REAL = _tok.get_vocab_size()
    del _tok
except Exception:
    VOCAB_SIZE_REAL = 23830

VOCAB_SIZE = VOCAB_SIZE_REAL
EMBED_DIM = 512
NUM_LAYERS = 8
NUM_HEADS = 8
FF_DIM = 2048
DROPOUT = 0.15
SEQ_LEN = 512

# --- PARÂMETROS AJUSTÁVEIS (auto-detectam GPU vs CPU) ---
BATCH_SIZE = 16 if torch.cuda.is_available() else 8
GRADIENT_ACCUMULATION = 2 if torch.cuda.is_available() else 4
EPOCHS_POR_PASTA = 5  # AUMENTADO: 5 épocas por pasta (antes 2)
LEARNING_RATE = 3e-4  # Fixo em 3e-4 (bom para ambos)
WEIGHT_DECAY = 0.01
WARMUP_STEPS = 2000  # AUMENTADO: mais tempo de aquecimento
MAX_GRAD_NORM = 1.0
LABEL_SMOOTHING = 0.1

# --- EARLY STOPPING E SCHEDULER (MAIS TOLERANTES) ---
PATIENCE = 20  # AUMENTADO: para só após 20 épocas sem melhora
REDUCE_ON_PLATEAU_PATIENCE = 6  # AUMENTADO: scheduler reduz LR após 6 épocas
REDUCE_ON_PLATEAU_FACTOR = 0.75  # AUMENTADO: redução mais suave (antes 0.5)

LOG_INTERVAL = 50
CHECKPOINT_INTERVAL = 50
MAX_NAN_RETRIES = 3
VAL_BATCHES_LIMIT = 200

# --- Caminhos ---
PASTA_BASE = "dados"
PASTA_PROCESSED = os.path.join(PASTA_BASE, "processed")
TOKENIZER_PATH = "tokenizer/tokenizer.json"
MODEL_PATH = "modelo/modelo.pt"
LOG_PATH = "logs/treino.log"
CHECKPOINT_PATH = "modelo/checkpoint.pt"
MELHOR_MODELO_PATH = "modelo/modelo_melhor.pt"
METRICAS_PATH = "logs/metricas.json"
ESTADO_PATH = "modelo/estado_treino.json"

PAD_TOKEN = "[PAD]"
UNK_TOKEN = "[UNK]"
BOS_TOKEN = "[BOS]"
EOS_TOKEN = "[EOS]"
SEP_TOKEN = "[SEP]"
SPECIAL_TOKENS = [PAD_TOKEN, UNK_TOKEN, BOS_TOKEN, EOS_TOKEN, SEP_TOKEN]

# --- Limites ---
MAX_ARQUIVOS_POR_PASTA = 5000  # AUMENTADO: aproveita mais dados
MIN_ARQUIVOS_POR_PASTA = 10

# ============================================================================
# 2. FUNÇÃO DE SALVAMENTO SEGURO (com temp file)
# ============================================================================

def salvar_checkpoint_seguro(caminho: str, estado: dict) -> bool:
    """
    Salva um checkpoint de forma atômica:
    - Escreve em um arquivo temporário.
    - Renomeia para o caminho final.
    Isso evita corrupção se o sistema cair durante a escrita.
    """
    try:
        dir_name = os.path.dirname(caminho)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # Cria arquivo temporário no mesmo diretório
        with tempfile.NamedTemporaryFile(dir=dir_name, delete=False, suffix='.pt') as tmp:
            torch.save(estado, tmp.name)
            tmp_path = tmp.name

        # Renomeia (substitui se existir)
        os.replace(tmp_path, caminho)
        return True
    except Exception as e:
        print(f"❌ Erro ao salvar checkpoint seguramente: {e}")
        return False

# ============================================================================
# 3. FUNÇÕES DE LOG E SUPORTE
# ============================================================================

def detectar_dispositivo() -> torch.device:
    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"✅ GPU detectada: {torch.cuda.get_device_name(0)}")
        print(f"✅ Memória total: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
        print(f"✅ CUDA version: {torch.version.cuda}")
        print(f"✅ PyTorch version: {torch.__version__}")
    else:
        device = torch.device("cpu")
        print("💡 GPU não detectada. Treino em CPU (mais lento, mas funcional).")
    print(f"   Dispositivo selecionado: {device}")
    return device

DISPOSITIVO = detectar_dispositivo()

def log(msg: str, nivel: str = "INFO", console: bool = True, arquivo: str = LOG_PATH):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{timestamp}] [{nivel}] {msg}"
    if console:
        print(linha)
    os.makedirs(os.path.dirname(arquivo), exist_ok=True)
    with open(arquivo, "a", encoding="utf-8") as f:
        f.write(linha + "\n")

def carregar_json(caminho: str, padrao: Any) -> Any:
    if not os.path.exists(caminho):
        return padrao
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return padrao

def salvar_json(caminho: str, dados: Any) -> None:
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def salvar_estado_treino(epoch: int, best_val_loss: float, no_improve: int, total_batches: int):
    estado = {
        "epoch": epoch,
        "best_val_loss": best_val_loss,
        "no_improve": no_improve,
        "total_batches": total_batches,
        "timestamp": datetime.now().isoformat()
    }
    salvar_json(ESTADO_PATH, estado)

def salvar_metricas(epoch: int, train_loss: float, val_loss: float, lr: float, tempo: float, outras: Optional[dict] = None):
    metricas = carregar_json(METRICAS_PATH, {"historico": []})
    entry = {
        "epoch": epoch,
        "train_loss": train_loss,
        "val_loss": val_loss,
        "learning_rate": lr,
        "tempo_segundos": tempo
    }
    if outras:
        entry.update(outras)
    metricas["historico"].append(entry)
    if len(metricas["historico"]) > 100:
        metricas["historico"] = metricas["historico"][-100:]
    salvar_json(METRICAS_PATH, metricas)

def limpar_cache():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

def verificar_nan(tensor: torch.Tensor, nome: str = "tensor") -> bool:
    if torch.isnan(tensor).any():
        log(f"⚠️ Valor inválido (NaN) em {nome}. Instabilidade?", "WARNING")
        return True
    return False

# ============================================================================
# Funções de extração de texto
# ============================================================================

def extrair_texto_pdf(caminho: str) -> str:
    if FITZ_AVAILABLE and fitz is not None:
        try:
            doc = fitz.open(caminho)
            texto = ""
            for pagina in doc:
                texto = texto + str(pagina.get_text())
            doc.close()
            return re.sub(r'\s+', ' ', texto).strip()
        except Exception as e:
            log(f"⚠️ Erro ao ler PDF {os.path.basename(caminho)}: {e}", "WARNING")
            return ""
    else:
        return ""

def extrair_texto_html(caminho: str) -> str:
    if BS4_AVAILABLE and BeautifulSoup is not None:
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
            soup = BeautifulSoup(conteudo, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            texto = soup.get_text(separator=' ')
            return re.sub(r'\s+', ' ', texto).strip()
        except Exception as e:
            log(f"⚠️ Erro ao ler HTML {os.path.basename(caminho)}: {e}", "WARNING")
            return ""
    else:
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
            texto = re.sub(r'<[^>]+>', ' ', conteudo)
            texto = re.sub(r'\s+', ' ', texto).strip()
            return texto
        except:
            return ""

def extrair_texto_xml(caminho: str) -> str:
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(caminho)
        root = tree.getroot()
        texto = ""
        for elem in root.iter():
            if elem.text:
                texto = texto + str(elem.text) + " "
        return re.sub(r'\s+', ' ', texto).strip()
    except Exception as e:
        log(f"⚠️ Erro ao ler XML {os.path.basename(caminho)}: {e}", "WARNING")
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
            texto = re.sub(r'<[^>]+>', ' ', conteudo)
            texto = re.sub(r'\s+', ' ', texto).strip()
            return texto
        except:
            return ""

def extrair_texto_csv(caminho: str) -> str:
    if CSV_AVAILABLE and csv is not None:
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                leitor = csv.reader(f)
                linhas = []
                for linha in leitor:
                    linhas.append(" ".join(linha))
                return "\n".join(linhas)
        except Exception as e:
            log(f"⚠️ Erro ao ler CSV {os.path.basename(caminho)}: {e}", "WARNING")
            return ""
    else:
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
            return re.sub(r'[,\t;]', ' ', conteudo).strip()
        except:
            return ""

def extrair_texto_jsonl(caminho: str) -> str:
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            textos = []
            for linha in f:
                try:
                    dados = json.loads(linha)
                    if 'pergunta' in dados and 'resposta' in dados:
                        textos.append(f"Pergunta: {str(dados['pergunta'])} Resposta: {str(dados['resposta'])}")
                    elif 'text' in dados:
                        textos.append(str(dados['text']))
                    elif 'content' in dados:
                        textos.append(str(dados['content']))
                    elif 'conversa' in dados:
                        for turno in dados['conversa']:
                            if isinstance(turno, dict):
                                if 'humano' in turno and 'assistente' in turno:
                                    textos.append(f"Pergunta: {str(turno['humano'])} Resposta: {str(turno['assistente'])}")
                except:
                    continue
            return "\n\n".join(textos)
    except Exception as e:
        log(f"⚠️ Erro ao ler JSONL {os.path.basename(caminho)}: {e}", "WARNING")
        return ""

def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize('NFKC', texto)
    texto = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def processar_arquivo(caminho: str, validar_dialogos: bool = True) -> Optional[Dict]:
    extensao = os.path.splitext(caminho)[1].lower()
    texto_bruto = ""

    try:
        if extensao == '.txt':
            with open(caminho, 'r', encoding='utf-8') as f:
                texto_bruto = f.read()
        elif extensao == '.pdf':
            texto_bruto = extrair_texto_pdf(caminho)
        elif extensao in ['.html', '.htm']:
            texto_bruto = extrair_texto_html(caminho)
        elif extensao == '.xml':
            texto_bruto = extrair_texto_xml(caminho)
        elif extensao == '.csv':
            texto_bruto = extrair_texto_csv(caminho)
        elif extensao == '.jsonl':
            texto_bruto = extrair_texto_jsonl(caminho)
        else:
            return None

        if not texto_bruto:
            return None

        texto_limpo = normalizar_texto(texto_bruto)
        if not texto_limpo:
            return None

        if validar_dialogos and ("Pergunta:" in texto_limpo and "Resposta:" in texto_limpo):
            partes = texto_limpo.split("Resposta:", 1)
            if len(partes) > 1:
                resposta = partes[1].strip()
                if resposta:
                    perg_part = partes[0].split("Pergunta:", 1)
                    if len(perg_part) > 1:
                        pergunta = perg_part[1].strip()
                        if pergunta:
                            return {"pergunta": pergunta, "resposta": resposta, "tipo": "dialogo"}

        return {"texto": texto_limpo, "tipo": "texto"}

    except Exception as e:
        log(f"⚠️ Erro ao processar {os.path.basename(caminho)}: {e}", "WARNING")
        return None

# ============================================================================
# Tokenizer
# ============================================================================

def listar_arquivos_recursivo(pasta: str) -> List[str]:
    arquivos = []
    extensoes = ('.txt', '.pdf', '.html', '.htm', '.xml', '.csv', '.jsonl')
    if not os.path.exists(pasta):
        return arquivos
    for raiz, _, files in os.walk(pasta):
        for f in files:
            if f.lower().endswith(extensoes):
                arquivos.append(os.path.join(raiz, f))
    return arquivos

def criar_tokenizer() -> bool:
    log("🔧 Criando tokenizer (BPE) a partir das pastas de dados...")
    pastas_para_tokenizer = [PASTA_PROCESSED]
    arquivos = []
    for pasta in pastas_para_tokenizer:
        arquivos.extend(listar_arquivos_recursivo(pasta))

    if not arquivos:
        log("❌ Nenhum arquivo suportado encontrado.", "ERROR")
        return False

    textos = []
    for arq in arquivos[:5000]:
        item = processar_arquivo(arq, validar_dialogos=False)
        if item:
            texto = item.get("texto") or f"{item.get('pergunta', '')} {item.get('resposta', '')}"
            if texto and len(texto) > 100:
                textos.append(texto)
    if not textos:
        log("❌ Nenhum texto válido para treinar tokenizer.", "ERROR")
        return False

    temp = os.path.join(PASTA_PROCESSED, "_temp_tokenizer.txt")
    os.makedirs(PASTA_PROCESSED, exist_ok=True)
    try:
        with open(temp, "w", encoding='utf-8') as f:
            for txt in textos:
                f.write(txt + "\n")

        tokenizer = Tokenizer(models.BPE(unk_token=UNK_TOKEN))
        tokenizer.normalizer = normalizers.Sequence([normalizers.NFKC()])
        tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=True)
        trainer = trainers.BpeTrainer(
            vocab_size=VOCAB_SIZE,
            min_frequency=2,
            special_tokens=SPECIAL_TOKENS,
            show_progress=True
        )
        tokenizer.train([temp], trainer)
        tokenizer.post_processor = processors.ByteLevel(trim_offsets=True)
        tokenizer.decoder = decoders.ByteLevel(add_prefix_space=True)
        tokenizer.save(TOKENIZER_PATH)
        log(f"✅ Tokenizer salvo em {TOKENIZER_PATH}")
        return True
    except Exception as e:
        log(f"❌ Erro ao criar tokenizer: {e}", "ERROR")
        return False
    finally:
        if os.path.exists(temp):
            os.remove(temp)

# ============================================================================
# Modelo
# ============================================================================

class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, :x.size(1), :].to(x.device)
        return self.dropout(x)

class RigelSLM(nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding = nn.Embedding(VOCAB_SIZE, EMBED_DIM, padding_idx=0)
        self.pos_encoding = PositionalEncoding(EMBED_DIM, max_len=SEQ_LEN, dropout=DROPOUT)
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=EMBED_DIM,
            nhead=NUM_HEADS,
            dim_feedforward=FF_DIM,
            dropout=DROPOUT,
            activation='gelu',
            batch_first=True
        )
        self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=NUM_LAYERS)
        self.lm_head = nn.Linear(EMBED_DIM, VOCAB_SIZE)
        self.apply(self._init_weights)

    def _init_weights(self, module: nn.Module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        seq_len = x.size(1)
        mask = torch.triu(torch.ones(seq_len, seq_len, device=x.device), diagonal=1).bool()
        x = self.embedding(x)
        x = self.pos_encoding(x)
        out = self.decoder(x, x, tgt_mask=mask)
        return self.lm_head(out)

    def generate(self, tokenizer: Tokenizer, prompt: str, max_new_tokens: int = 100,
                 temperature: float = 0.8, repetition_penalty: float = 1.2, top_k: int = 50) -> str:
        self.eval()
        try:
            ids = tokenizer.encode(prompt).ids
            if not ids or ids[0] != tokenizer.token_to_id(BOS_TOKEN):
                ids = [tokenizer.token_to_id(BOS_TOKEN)] + ids
            tokens = torch.tensor(ids, dtype=torch.long).unsqueeze(0).to(DISPOSITIVO)

            for _ in range(max_new_tokens):
                with torch.no_grad():
                    logits = self(tokens)
                    last_logit = logits[0, -1, :] / temperature

                    if top_k > 0:
                        valores, indices = torch.topk(last_logit, top_k)
                        mascara = torch.ones_like(last_logit) * float('-inf')
                        mascara[indices] = valores
                        last_logit = mascara

                    for idx in set(tokens[0].tolist()):
                        if last_logit[idx] >= 0:
                            last_logit[idx] /= repetition_penalty
                        else:
                            last_logit[idx] *= repetition_penalty

                    vocab_real = tokenizer.get_vocab_size()
                    if last_logit.size(0) > vocab_real:
                        last_logit[vocab_real:] = float('-inf')

                    probs = F.softmax(last_logit, dim=-1)
                    next_id = torch.multinomial(probs, 1).item()
                    if next_id == tokenizer.token_to_id(EOS_TOKEN):
                        break
                    if next_id >= tokenizer.get_vocab_size():
                        break
                    tokens = torch.cat([tokens, torch.tensor([[next_id]], device=DISPOSITIVO)], dim=1)
            return tokenizer.decode(tokens[0].tolist())
        except Exception as e:
            log(f"⚠️ Erro na geração: {e}", "WARNING")
            return "[Erro na geração]"

# ============================================================================
# Dataset Streaming
# ============================================================================

class StreamingTextDataset(IterableDataset):
    def __init__(self, pasta_dados: str, tokenizer: Tokenizer, seq_len: int = SEQ_LEN,
                 validar_dialogos: bool = True, shuffle: bool = True, max_arquivos: Optional[int] = None):
        self.pasta_dados = pasta_dados
        self.tokenizer = tokenizer
        self.seq_len = seq_len
        self.validar_dialogos = validar_dialogos
        self.shuffle = shuffle
        self.max_arquivos = max_arquivos
        self._arquivos = None

    def _listar_arquivos(self) -> List[str]:
        if self._arquivos is not None:
            return self._arquivos
        arquivos = []
        extensoes = ('.txt', '.pdf', '.html', '.htm', '.xml', '.csv', '.jsonl')
        if not os.path.exists(self.pasta_dados):
            return arquivos
        for raiz, _, files in os.walk(self.pasta_dados):
            for f in files:
                if f.lower().endswith(extensoes):
                    arquivos.append(os.path.join(raiz, f))
        if self.shuffle:
            random.shuffle(arquivos)
        if self.max_arquivos is not None and len(arquivos) > self.max_arquivos:
            arquivos = arquivos[:self.max_arquivos]
        self._arquivos = arquivos
        return arquivos

    def __iter__(self):
        bos_id = self.tokenizer.token_to_id(BOS_TOKEN)
        eos_id = self.tokenizer.token_to_id(EOS_TOKEN)
        sep_id = self.tokenizer.token_to_id(SEP_TOKEN)

        for caminho in self._listar_arquivos():
            try:
                item = processar_arquivo(caminho, validar_dialogos=self.validar_dialogos)
                if item is None:
                    continue
                if item["tipo"] == "dialogo":
                    pergunta = item.get("pergunta", "")
                    resposta = item.get("resposta", "")
                    if not pergunta or not resposta:
                        continue
                    texto_formatado = f"{pergunta} {SEP_TOKEN} {resposta}"
                else:
                    texto = item.get("texto", "")
                    if not texto or len(texto.split()) < 5:
                        continue
                    texto_formatado = texto

                ids = self.tokenizer.encode(texto_formatado).ids
                if not ids:
                    continue
                seq = [bos_id] + ids + [eos_id]
                stride = self.seq_len // 2
                for i in range(0, max(1, len(seq) - self.seq_len), stride):
                    chunk = seq[i:i+self.seq_len]
                    if len(chunk) < self.seq_len:
                        chunk = chunk + [0] * (self.seq_len - len(chunk))
                    yield torch.tensor(chunk, dtype=torch.long)
            except Exception as e:
                log(f"⚠️ Erro ao processar {caminho}: {e}", "WARNING", console=False)
                continue

# ============================================================================
# Detecção de pastas
# ============================================================================

def detectar_pastas_validas() -> List[Tuple[str, str, int]]:
    if not os.path.exists(PASTA_PROCESSED):
        log(f"❌ Pasta base não encontrada: {PASTA_PROCESSED}", "ERROR")
        return []

    pastas_validas = []
    log(f"🔍 Escaneando {PASTA_PROCESSED} em busca de pastas com >= {MIN_ARQUIVOS_POR_PASTA} arquivos .txt...")

    for item in os.listdir(PASTA_PROCESSED):
        caminho_item = os.path.join(PASTA_PROCESSED, item)

        if not os.path.isdir(caminho_item):
            continue

        total_txt = 0
        for raiz, _, arquivos in os.walk(caminho_item):
            for arq in arquivos:
                if arq.lower().endswith('.txt'):
                    total_txt += 1

        if total_txt >= MIN_ARQUIVOS_POR_PASTA:
            pastas_validas.append((item, caminho_item, total_txt))
            log(f"   ✅ {item}: {total_txt} arquivos .txt")
        else:
            log(f"   ⏭️  {item}: apenas {total_txt} arquivos .txt (mínimo: {MIN_ARQUIVOS_POR_PASTA})")

    pastas_validas.sort(key=lambda x: x[2], reverse=True)
    log(f"📂 Total de pastas válidas: {len(pastas_validas)}")
    return pastas_validas

# ============================================================================
# Função de treino por pasta (com interrupção segura)
# ============================================================================

def treinar_pasta(
    pasta_dados: str,
    nome_pasta: str,
    model: nn.Module,
    tokenizer: Tokenizer,
    start_epoch: int,
    epochs_para_treinar: int,
    best_val_loss: float,
    no_improve: int,
    total_batches: int,
    precision: str,
    num_workers: int,
    val_batches_limit: int
) -> Tuple[nn.Module, int, float, int, int, AdamW, LambdaLR, ReduceLROnPlateau, Optional[GradScaler]]:
    """
    Treina o modelo em uma pasta específica.
    RESETA otimizador e scheduler a cada nova pasta (LR volta a 3e-4).
    TRATA Ctrl+C salvando checkpoint seguro antes de sair.
    """
    # --- Prepara dados ---
    arquivos = listar_arquivos_recursivo(pasta_dados)
    if not arquivos:
        log(f"⚠️ Nenhum arquivo suportado em {pasta_dados}. Pulando pasta.", "WARNING")
        return model, start_epoch, best_val_loss, no_improve, total_batches, None, None, None, None

    if len(arquivos) > MAX_ARQUIVOS_POR_PASTA:
        random.shuffle(arquivos)
        arquivos = arquivos[:MAX_ARQUIVOS_POR_PASTA]
        log(f"📊 Limitado a {MAX_ARQUIVOS_POR_PASTA} arquivos (de {len(arquivos)} disponíveis)")

    random.shuffle(arquivos)
    val_size = max(1, int(len(arquivos) * 0.1))
    train_arquivos = arquivos[val_size:]
    val_arquivos = arquivos[:val_size]
    log(f"📂 {len(train_arquivos)} treino, {len(val_arquivos)} validação")

    # --- DataLoaders ---
    train_dataset = StreamingTextDataset(pasta_dados, tokenizer, SEQ_LEN, validar_dialogos=True,
                                         shuffle=True, max_arquivos=MAX_ARQUIVOS_POR_PASTA)
    train_dataset._arquivos = train_arquivos
    val_dataset = StreamingTextDataset(pasta_dados, tokenizer, SEQ_LEN, validar_dialogos=True,
                                       shuffle=False, max_arquivos=MAX_ARQUIVOS_POR_PASTA)
    val_dataset._arquivos = val_arquivos

    ctx = 'fork' if 'fork' in multiprocessing.get_all_start_methods() else None
    pin_mem = torch.cuda.is_available()

    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=False,
                              num_workers=num_workers, pin_memory=pin_mem, timeout=0,
                              multiprocessing_context=ctx)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False,
                            num_workers=num_workers, pin_memory=pin_mem, timeout=0,
                            multiprocessing_context=ctx)

    loss_fn = nn.CrossEntropyLoss(ignore_index=0, label_smoothing=LABEL_SMOOTHING)

    # --- RECRIA OTIMIZADOR E SCHEDULER (reset LR) ---
    log(f"🔄 Resetando otimizador e scheduler para a pasta '{nome_pasta}' (LR={LEARNING_RATE})")
    optimizer = AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)

    estimated_batches_per_epoch = max(1, len(train_arquivos) // BATCH_SIZE // GRADIENT_ACCUMULATION)
    total_steps = estimated_batches_per_epoch * epochs_para_treinar
    warmup_steps = min(WARMUP_STEPS, total_steps // 5)

    def lr_lambda(step):
        if step < warmup_steps:
            return step / warmup_steps
        else:
            progress = (step - warmup_steps) / (total_steps - warmup_steps)
            return 0.5 * (1 + math.cos(math.pi * progress))

    scheduler_warmup = LambdaLR(optimizer, lr_lambda)
    scheduler_plateau = ReduceLROnPlateau(optimizer, mode='min',
                                          factor=REDUCE_ON_PLATEAU_FACTOR,
                                          patience=REDUCE_ON_PLATEAU_PATIENCE)

    if precision in ("fp16", "amp") and torch.cuda.is_available():
        scaler = GradScaler('cuda')
    else:
        scaler = None

    # --- Loop de épocas com tratamento de interrupção ---
    epoch_final = start_epoch + epochs_para_treinar
    epoch = start_epoch  # para referência em caso de interrupção

    try:
        for epoch in range(start_epoch, epoch_final):
            model.train()
            total_loss = 0
            steps = 0
            epoch_start_time = time.time()
            log(f"\n🚀 Epoch {epoch+1}/{epoch_final} | Pasta: {nome_pasta}")

            progress_bar = tqdm(train_loader, desc=f"Epoch {epoch+1}", unit="batch")
            optimizer.zero_grad()
            nan_retries = 0

            for i, batch in enumerate(progress_bar):
                try:
                    batch = batch.to(DISPOSITIVO)

                    if precision in ("fp16", "amp") and scaler is not None:
                        with autocast('cuda'):
                            logits = model(batch)
                            target = batch[:, 1:].contiguous()
                            logits = logits[:, :-1, :].contiguous()
                            loss = loss_fn(logits.view(-1, VOCAB_SIZE), target.view(-1))
                            loss = loss / GRADIENT_ACCUMULATION
                        scaler.scale(loss).backward()
                    else:
                        logits = model(batch)
                        target = batch[:, 1:].contiguous()
                        logits = logits[:, :-1, :].contiguous()
                        loss = loss_fn(logits.view(-1, VOCAB_SIZE), target.view(-1))
                        loss = loss / GRADIENT_ACCUMULATION
                        loss.backward()

                    if verificar_nan(loss, "loss"):
                        nan_retries += 1
                        if nan_retries >= MAX_NAN_RETRIES:
                            log("❌ NaN persistente. Reduzindo LR.", "ERROR")
                            for param_group in optimizer.param_groups:
                                param_group['lr'] *= 0.5
                            optimizer.zero_grad()
                            nan_retries = 0
                            continue
                        else:
                            log(f"⚠️ NaN, tentativa {nan_retries}/{MAX_NAN_RETRIES}. Pulando batch.", "WARNING")
                            optimizer.zero_grad()
                            continue

                    total_loss += loss.item() * GRADIENT_ACCUMULATION

                    if (i + 1) % GRADIENT_ACCUMULATION == 0:
                        if precision in ("fp16", "amp") and scaler is not None:
                            scaler.unscale_(optimizer)
                            torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)
                            scaler.step(optimizer)
                            scaler.update()
                        else:
                            torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)
                            optimizer.step()
                        scheduler_warmup.step()
                        optimizer.zero_grad()
                        steps += 1
                        total_batches += 1
                        progress_bar.set_postfix({"loss": f"{loss.item() * GRADIENT_ACCUMULATION:.4f}"})

                        if steps % LOG_INTERVAL == 0:
                            lr_atual = optimizer.param_groups[0]['lr']
                            log(f"  Batch {steps} | loss: {loss.item() * GRADIENT_ACCUMULATION:.4f} | lr: {lr_atual:.6f}")

                        if total_batches % CHECKPOINT_INTERVAL == 0:
                            checkpoint_data = {
                                'epoch': epoch,
                                'model_state_dict': model.state_dict(),
                                'best_val_loss': best_val_loss,
                                'no_improve': no_improve,
                                'total_batches': total_batches,
                                'optimizer_state_dict': optimizer.state_dict(),
                                'scheduler_state_dict': scheduler_warmup.state_dict()
                            }
                            salvar_checkpoint_seguro(CHECKPOINT_PATH, checkpoint_data)
                            log(f"  💾 Checkpoint salvo em {CHECKPOINT_PATH}")

                    if i % 100 == 0:
                        limpar_cache()

                except RuntimeError as e:
                    if "out of memory" in str(e).lower():
                        log(f"⚠️ OOM. Pulando batch e liberando memória.", "WARNING")
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        optimizer.zero_grad()
                        continue
                    else:
                        log(f"❌ Erro no batch: {e}", "ERROR")
                        traceback.print_exc()
                        optimizer.zero_grad()
                        continue
                except Exception as e:
                    log(f"❌ Erro inesperado: {e}", "ERROR")
                    traceback.print_exc()
                    optimizer.zero_grad()
                    continue

            # --- Fim da época ---
            avg_train_loss = total_loss / steps if steps > 0 else 0
            log(f"✅ Epoch {epoch+1} - Loss média treino: {avg_train_loss:.4f}")

            # Validação
            model.eval()
            val_loss = 0
            val_steps = 0
            with torch.no_grad():
                for batch in val_loader:
                    if val_steps > val_batches_limit:
                        break
                    try:
                        batch = batch.to(DISPOSITIVO)
                        if precision in ("fp16", "amp") and scaler is not None:
                            with autocast('cuda'):
                                logits = model(batch)
                                target = batch[:, 1:].contiguous()
                                logits = logits[:, :-1, :].contiguous()
                                loss = loss_fn(logits.view(-1, VOCAB_SIZE), target.view(-1))
                        else:
                            logits = model(batch)
                            target = batch[:, 1:].contiguous()
                            logits = logits[:, :-1, :].contiguous()
                            loss = loss_fn(logits.view(-1, VOCAB_SIZE), target.view(-1))
                        val_loss += loss.item()
                        val_steps += 1
                    except Exception as e:
                        log(f"⚠️ Erro na validação: {e}", "WARNING")
                        continue

            avg_val_loss = val_loss / val_steps if val_steps > 0 else 0
            log(f"📉 Loss validação: {avg_val_loss:.4f}")

            # Atualiza melhor modelo
            if avg_val_loss < best_val_loss:
                log("📈 O loss está CAINDO → isso é BOM! O modelo está aprendendo.")
                best_val_loss = avg_val_loss
                no_improve = 0
                torch.save(model.state_dict(), MELHOR_MODELO_PATH)
                log("💾 Melhor modelo salvo.")
            else:
                no_improve += 1
                if no_improve >= PATIENCE:
                    log("⏹️ Early stopping! (loss não melhora há várias épocas)")
                    if epoch - start_epoch >= 2:
                        log("🛑 Parando esta pasta precocemente (early stopping).")
                        break
                    else:
                        log("   (Ainda não completou 3 épocas; continuando...)")
                else:
                    log("📉 O loss SUBIU ou estagnou → pode ser necessário ajustar LR ou dados.")

            lr_atual = optimizer.param_groups[0]['lr']
            if lr_atual < LEARNING_RATE * 0.5:
                log(f"🔽 Learning rate reduziu para {lr_atual:.6f} (ajuste fino)")
            else:
                log(f"🔄 Learning rate estável em {lr_atual:.6f}")

            # Exemplo de geração
            sample_prompt = "Olá, boa noite!"
            try:
                gerado = model.generate(tokenizer, sample_prompt, max_new_tokens=50, temperature=0.7)
                log(f"📝 Exemplo: '{sample_prompt}' -> '{gerado}'")
            except Exception as e:
                log(f"⚠️ Erro na geração: {e}", "WARNING")

            tempo_epoch = time.time() - epoch_start_time
            salvar_metricas(epoch + 1, avg_train_loss, avg_val_loss, lr_atual, tempo_epoch,
                            {"pasta": nome_pasta})
            salvar_estado_treino(epoch + 1, best_val_loss, no_improve, total_batches)
            limpar_cache()

        log(f"🏁 Finalizadas {epochs_para_treinar} épocas na pasta '{nome_pasta}'.")

    except KeyboardInterrupt:
        # ============================================================
        # INTERRUPÇÃO SEGURA (Ctrl+C) – SALVA CHECKPOINT E SAI
        # ============================================================
        print(f"\n⏹️ Interrupção (Ctrl+C) detectada na pasta '{nome_pasta}'.")
        print("🔄 Salvando checkpoint e modelo antes de sair...")

        # Salva checkpoint com o estado atual (mesmo que a época não tenha terminado)
        checkpoint_data = {
            'epoch': epoch,  # época atual (pode ser a que estava rodando)
            'model_state_dict': model.state_dict(),
            'best_val_loss': best_val_loss,
            'no_improve': no_improve,
            'total_batches': total_batches,
            'optimizer_state_dict': optimizer.state_dict(),
            'scheduler_state_dict': scheduler_warmup.state_dict()
        }
        if salvar_checkpoint_seguro(CHECKPOINT_PATH, checkpoint_data):
            log(f"💾 Checkpoint salvo com segurança em {CHECKPOINT_PATH}")
        else:
            log("⚠️ Falha ao salvar checkpoint. Tente novamente.")

        # Salva o modelo final (último estado)
        torch.save(model.state_dict(), MODEL_PATH)
        log(f"💾 Modelo final salvo em {MODEL_PATH}")

        print("👋 Saindo com segurança. Retome com 'python treinov2.py'.")
        sys.exit(0)

    return model, epoch_final, best_val_loss, no_improve, total_batches, optimizer, scheduler_warmup, scheduler_plateau, scaler

# ============================================================================
# MAIN - EXECUÇÃO PRINCIPAL
# ============================================================================

def main():
    print("=" * 80)
    print("🚀 RIGELSLM v1.0.0 - TREINO AUTOMATIZADO (OTIMIZADO + INTERRUPÇÃO SEGURA)")
    print(f"📅 {datetime.now()}")
    print(f"💻 Dispositivo: {DISPOSITIVO}")
    print(f"📊 Batch: {BATCH_SIZE}, Épocas por pasta: {EPOCHS_POR_PASTA}")
    print(f"📂 Max arquivos por pasta: {MAX_ARQUIVOS_POR_PASTA}")
    print(f"⏳ Patience: {PATIENCE}, Scheduler patience: {REDUCE_ON_PLATEAU_PATIENCE}")
    print("💡 Pressione Ctrl+C a qualquer momento para interromper com segurança.")
    print("=" * 80)

    # ------------------------------------------------------------------
    # ⚠️ AVISO: QUAL TREINADOR USA O QUÊ?
    # ------------------------------------------------------------------
    print("⚠️  AVISO: treino.py / treinov2.py treinam dados .txt (pergunta/resposta, texto).")
    print("   Para dados JSONL SFT (messages) dos datasets baixados no dashboard,")
    print("   use: python treinar_com_jsonl.py --dados dados/gerados/jsonl")
    print("=" * 80)

    # Cria diretórios
    for p in [os.path.dirname(TOKENIZER_PATH), os.path.dirname(MODEL_PATH),
              os.path.dirname(LOG_PATH), PASTA_PROCESSED]:
        os.makedirs(p, exist_ok=True)

    # Passo 1: Detectar pastas
    print("\n🔍 PASSO 1: Detectando pastas com dados suficientes...")
    pastas = detectar_pastas_validas()

    if not pastas:
        log("❌ Nenhuma pasta com dados suficientes encontrada.", "ERROR")
        log(f"   Mínimo exigido: {MIN_ARQUIVOS_POR_PASTA} arquivos .txt por pasta.", "ERROR")
        sys.exit(1)

    print(f"\n📂 Pastas selecionadas ({len(pastas)}):")
    for nome, caminho, qtd in pastas:
        print(f"   - {nome}: {qtd} arquivos .txt")

    # Passo 2: Tokenizer
    print("\n🔤 PASSO 2: Verificando tokenizer...")
    if not os.path.exists(TOKENIZER_PATH):
        log("⚠️ Tokenizer não encontrado. Criando...")
        if not criar_tokenizer():
            log("❌ Falha ao criar tokenizer.", "ERROR")
            sys.exit(1)
    else:
        log(f"✅ Tokenizer carregado de {TOKENIZER_PATH}")

    tokenizer = Tokenizer.from_file(TOKENIZER_PATH)

    # Passo 3: Modelo
    print("\n🧠 PASSO 3: Inicializando modelo...")
    model = RigelSLM().to(DISPOSITIVO)

    start_epoch = 0
    best_val_loss = float('inf')
    no_improve = 0
    total_batches = 0

    # Passo 4: Carregar checkpoint
    print("\n💾 PASSO 4: Verificando checkpoint...")
    if os.path.exists(CHECKPOINT_PATH):
        try:
            checkpoint = torch.load(CHECKPOINT_PATH, map_location=DISPOSITIVO)
            model.load_state_dict(checkpoint["model_state_dict"])
            start_epoch = checkpoint.get("epoch", 0) + 1
            best_val_loss = checkpoint.get("best_val_loss", float('inf'))
            no_improve = checkpoint.get("no_improve", 0)
            total_batches = checkpoint.get("total_batches", 0)
            log(f"✅ Checkpoint carregado! Retomando da época {start_epoch - 1}")
            log(f"🏆 Melhor loss anterior: {best_val_loss:.4f}")
            log(f"⏱️  Batches processados: {total_batches}")
        except Exception as e:
            log(f"⚠️ Falha ao carregar checkpoint: {e}. Iniciando do zero.", "WARNING")
            start_epoch = 0
            best_val_loss = float('inf')
            no_improve = 0
            total_batches = 0
    else:
        log("🆕 Nenhum checkpoint encontrado. Iniciando do zero.")

    log(f"🧠 Parâmetros do modelo: {sum(p.numel() for p in model.parameters()):,}")
    model_size_mb = sum(p.numel() * p.element_size() for p in model.parameters()) / (1024 ** 2)
    log(f"📦 Tamanho do modelo (pesos): {model_size_mb:.2f} MB")

    # Configura workers
    cpu_count = os.cpu_count() or 1
    if torch.cuda.is_available():
        num_workers = min(cpu_count, 8)
        torch.set_num_threads(cpu_count)
        precision = "amp"
    else:
        if cpu_count <= 4:
            num_workers = 1
        else:
            num_workers = min(cpu_count - 2, 4)
        torch.set_num_threads(max(1, cpu_count - 1))
        precision = "fp32"
    log(f"🔧 Workers: {num_workers}, Threads: {torch.get_num_threads()}")

    # Log inicial
    log("=" * 80)
    log("🚀 RIGELSLM v1.0.0 – TREINO AUTOMATIZADO (OTIMIZADO + SEGURO)")
    log(f"📅 {datetime.now()}")
    log(f"💻 Dispositivo: {DISPOSITIVO}")
    log(f"📂 Pastas detectadas: {len(pastas)}")
    log(f"📊 Batch: {BATCH_SIZE}, Seq: {SEQ_LEN}")
    log(f"🎯 Épocas por pasta: {EPOCHS_POR_PASTA}")
    log(f"🧵 Workers: {num_workers}, Threads: {torch.get_num_threads()}")
    log(f"💾 Save every: {CHECKPOINT_INTERVAL}")
    log(f"🎯 Precisão: {precision}")
    log(f"⏳ Patience: {PATIENCE}, Scheduler patience: {REDUCE_ON_PLATEAU_PATIENCE}")
    log("=" * 80)

    print(f"\n🏃 PASSO 5: Iniciando treino em {len(pastas)} pasta(s)...")
    print(f"   Épocas por pasta: {EPOCHS_POR_PASTA}")
    print(f"   Total estimado de épocas: {len(pastas) * EPOCHS_POR_PASTA}")

    pasta_idx = 0
    for nome_pasta, caminho_pasta, qtd_arquivos in pastas:
        pasta_idx += 1
        print(f"\n{'=' * 80}")
        print(f"📁 PASTA {pasta_idx}/{len(pastas)}: {nome_pasta} ({qtd_arquivos} arquivos)")
        print(f"📊 Épocas atuais: {start_epoch} → {start_epoch + EPOCHS_POR_PASTA}")
        print(f"{'=' * 80}")

        try:
            model, start_epoch, best_val_loss, no_improve, total_batches, _, _, _, _ = treinar_pasta(
                pasta_dados=caminho_pasta,
                nome_pasta=nome_pasta,
                model=model,
                tokenizer=tokenizer,
                start_epoch=start_epoch,
                epochs_para_treinar=EPOCHS_POR_PASTA,
                best_val_loss=best_val_loss,
                no_improve=no_improve,
                total_batches=total_batches,
                precision=precision,
                num_workers=num_workers,
                val_batches_limit=VAL_BATCHES_LIMIT
            )
            log(f"✅ Pasta '{nome_pasta}' concluída. Época atual: {start_epoch}")
        except Exception as e:
            log(f"❌ Erro ao treinar pasta '{nome_pasta}': {e}", "ERROR")
            traceback.print_exc()
            log("⚠️ Pulando para a próxima pasta...", "WARNING")
            continue

    # Finalização
    print(f"\n{'=' * 80}")
    print("🏁 TREINO AUTOMATIZADO CONCLUÍDO!")
    print(f"{'=' * 80}")
    print(f"📂 Pastas processadas: {pasta_idx}")
    print(f"🏆 Melhor loss: {best_val_loss:.4f}")
    print(f"📦 Modelo final: {MODEL_PATH}")
    print(f"📦 Melhor modelo: {MELHOR_MODELO_PATH}")
    print(f"📊 Métricas: {METRICAS_PATH}")
    print(f"📝 Log: {LOG_PATH}")
    print(f"{'=' * 80}")

    torch.save(model.state_dict(), MODEL_PATH)
    log(f"💾 Modelo final salvo em {MODEL_PATH}")

    checkpoint_data = {
        'epoch': start_epoch - 1,
        'model_state_dict': model.state_dict(),
        'best_val_loss': best_val_loss,
        'no_improve': no_improve,
        'total_batches': total_batches,
    }
    salvar_checkpoint_seguro(CHECKPOINT_PATH, checkpoint_data)
    log(f"💾 Checkpoint final salvo em {CHECKPOINT_PATH}")

    print("\n💡 Para continuar o treino depois, execute novamente:")
    print("   python treinov2.py")
    print("\n💡 Para continuar no Colab com o treino.py original:")
    print("   python treino.py --resume --dados <pasta>")
    print(f"{'=' * 80}\n")

if __name__ == "__main__":
    main()