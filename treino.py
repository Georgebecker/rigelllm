#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================================
# RIGELSLM - TREINO CONTÍNUO E INTELIGENTE (v6.6.0) - COM REGISTRO DE PASTAS
# ============================================================================
# CARACTERÍSTICAS ATUALIZADAS:
# - Menu interativo para escolher subpasta (sempre exibido)
# - Pergunta quantos arquivos usar (baseado no total disponível)
# - Otimização automática de workers: GPU => mais workers, CPU => conservador
# - Após completar épocas: continuar, trocar pasta ou reset (com confirmação)
# - Feedback claro durante treino: loss, LR, exemplos de geração
# - Checkpoint único (checkpoint.pt) para economia de espaço
# - NOVO: Uso de registro persistente para evitar escaneamento recursivo
# - NOVO: Contador de vezes que cada pasta foi treinada
# ============================================================================

import os
import sys
import re
import json
import time
import math
import random
import gc
import argparse
import traceback
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
import subprocess

# ============================================================================
# BIBLIOTECAS OPCIONAIS
# ============================================================================
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BeautifulSoup = None
    BS4_AVAILABLE = False
    warnings.warn("⚠️ BeautifulSoup não encontrado. HTML/XML serão lidos sem parsing.")

try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    fitz = None
    FITZ_AVAILABLE = False
    warnings.warn("⚠️ PyMuPDF (fitz) não encontrado. PDF serão ignorados.")

try:
    import csv
    CSV_AVAILABLE = True
except ImportError:
    csv = None
    CSV_AVAILABLE = False

# ============================================================================
# 1. CONFIGURAÇÕES GLOBAIS
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

BATCH_SIZE = 8
GRADIENT_ACCUMULATION = 4
EPOCHS = 20
LEARNING_RATE = 3e-4
WEIGHT_DECAY = 0.01
WARMUP_STEPS = 1000
MAX_GRAD_NORM = 1.0
LABEL_SMOOTHING = 0.1
PATIENCE = 5
REDUCE_ON_PLATEAU_PATIENCE = 2
REDUCE_ON_PLATEAU_FACTOR = 0.5

LOG_INTERVAL = 50
CHECKPOINT_INTERVAL = 50
MAX_NAN_RETRIES = 3
VAL_BATCHES_LIMIT = 200

PASTA_BASE = "dados"
PASTA_PROCESSED = os.path.join(PASTA_BASE, "processed")
PASTA_GERADOS = os.path.join(PASTA_BASE, "gerados")
PASTA_CURTOS = os.path.join(PASTA_GERADOS, "curtos")
PASTA_LONGOS = os.path.join(PASTA_GERADOS, "longos")
PASTA_RESUMIDOS = os.path.join(PASTA_GERADOS, "resumidos")

PASTAS_ULTRACHAT = ["ultrachat1", "ultrachat2"]

TOKENIZER_PATH = "tokenizer/tokenizer.json"
MODEL_PATH = "modelo/modelo.pt"
LOG_PATH = "logs/treino.log"
CHECKPOINT_PATH = "modelo/checkpoint.pt"
MELHOR_MODELO_PATH = "modelo/modelo_melhor.pt"
METRICAS_PATH = "logs/metricas.json"
ESTADO_PATH = "modelo/estado_treino.json"
DECISOES_LOG = "logs/decisoes.log"

## NOVO: Caminho do registro de pastas
REGISTRO_PATH = "registro_pastas.json"

PAD_TOKEN = "[PAD]"
UNK_TOKEN = "[UNK]"
BOS_TOKEN = "[BOS]"
EOS_TOKEN = "[EOS]"
SEP_TOKEN = "[SEP]"
SPECIAL_TOKENS = [PAD_TOKEN, UNK_TOKEN, BOS_TOKEN, EOS_TOKEN, SEP_TOKEN]

# ============================================================================
# 2. FUNÇÕES DE LOG E SUPORTE
# ============================================================================

def detectar_dispositivo() -> torch.device:
    """Detecta GPU ou CPU e imprime mensagem uma única vez."""
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

# DETECTA UMA ÚNICA VEZ E ARMAZENA
DISPOSITIVO = detectar_dispositivo()

def log(msg: str, nivel: str = "INFO", console: bool = True, arquivo: str = LOG_PATH):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{timestamp}] [{nivel}] {msg}"
    if console:
        print(linha)
    os.makedirs(os.path.dirname(arquivo), exist_ok=True)
    with open(arquivo, "a", encoding="utf-8") as f:
        f.write(linha + "\n")

def log_decisao(acao: str, detalhes: str):
    log(f"[DECISAO] {acao}: {detalhes}", "INFO", console=False, arquivo=DECISOES_LOG)

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

def carregar_estado_treino() -> dict:
    return carregar_json(ESTADO_PATH, {})

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

def log_gpu_usage():
    if not torch.cuda.is_available():
        return
    try:
        output = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total',
             '--format=csv,noheader,nounits'],
            universal_newlines=True
        )
        util, mem_used, mem_total = output.strip().split(', ')
        log(f"🖥️  GPU Util: {util}% | Mem: {mem_used}MiB / {mem_total}MiB", "INFO", console=False)
    except Exception as e:
        log(f"⚠️ Não foi possível obter info GPU: {e}", "WARNING", console=False)

# ============================================================================
# 2.5 INTERAÇÃO COM O USUÁRIO
# ============================================================================

## MODIFICADO: usa registro para listar pastas em vez de escanear
def listar_subpastas_com_contagem(pasta_base: str, usar_registro: bool = False) -> List[Tuple[str, str, int]]:
    """
    Lista subpastas com contagem de arquivos.
    Se usar_registro=True, lê do registro em vez de escanear.
    """
    if not usar_registro:
        # Comportamento antigo: escaneia o sistema
        if not os.path.exists(pasta_base):
            log(f"⚠️ Pasta base não encontrada: {pasta_base}", "WARNING")
            return []
        subpastas = []
        extensoes = ('.txt', '.pdf', '.html', '.htm', '.xml', '.csv', '.jsonl')
        for item in os.listdir(pasta_base):
            caminho_item = os.path.join(pasta_base, item)
            if os.path.isdir(caminho_item):
                total = 0
                for raiz, _, arquivos in os.walk(caminho_item):
                    for arq in arquivos:
                        if arq.lower().endswith(extensoes):
                            total += 1
                subpastas.append((item, caminho_item, total))
        subpastas.sort(key=lambda x: x[2], reverse=True)
        return subpastas
    else:
        ## NOVO: lê do registro
        if not os.path.exists(REGISTRO_PATH):
            log(f"⚠️ Registro {REGISTRO_PATH} não encontrado. Use --usar-registro apenas após organizar.", "WARNING")
            return []
        with open(REGISTRO_PATH, 'r', encoding='utf-8') as f:
            registro = json.load(f)
        subpastas = []
        for nome, info in registro.get("pastas", {}).items():
            caminho = info.get("caminho", os.path.join(pasta_base, nome))
            qtd = info.get("arquivos", 0)
            if qtd > 0:
                subpastas.append((nome, caminho, qtd))
        subpastas.sort(key=lambda x: x[2], reverse=True)
        return subpastas

def menu_interativo(lista_pastas: List[Tuple[str, str, int]]) -> Optional[str]:
    if not lista_pastas:
        return None
    print("\n" + "="*60)
    print("📂  PASTAS DISPONÍVEIS (do registro)" if len(lista_pastas) > 0 else "📂  PASTAS DISPONÍVEIS")
    print("="*60)
    for i, (nome, caminho, qtd) in enumerate(lista_pastas, start=1):
        print(f"  [{i}] {nome:30} -> {qtd:6} arquivos")
    print("="*60)
    print("  [0] Cancelar e usar a pasta padrão/fornecida")
    while True:
        try:
            opcao = input("\n👉 Escolha o número da pasta: ").strip()
            if opcao == "0":
                return None
            idx = int(opcao) - 1
            if 0 <= idx < len(lista_pastas):
                return lista_pastas[idx][1]
            else:
                print(f"⚠️ Opção inválida. Digite 0 a {len(lista_pastas)}.")
        except ValueError:
            print("⚠️ Entrada inválida. Digite um número.")

def selecionar_pasta_interativamente(pasta_base: str, pasta_fornecida: str = None, usar_registro: bool = False) -> str:
    print("\n🧠 Verificando estrutura de pastas...")
    subpastas = listar_subpastas_com_contagem(pasta_base, usar_registro)
    if not subpastas:
        log("⚠️ Nenhuma subpasta encontrada. Usando pasta fornecida.", "WARNING")
        return pasta_fornecida if pasta_fornecida else pasta_base
    print(f"📊 Encontradas {len(subpastas)} subpastas com arquivos suportados.")
    caminho_escolhido = menu_interativo(subpastas)
    if caminho_escolhido is None:
        escolha = pasta_fornecida if pasta_fornecida else pasta_base
        log_decisao("ESCOLHA_PASTA", f"Cancelou. Usando pasta: {escolha}")
        return escolha
    nome_escolhido = os.path.basename(caminho_escolhido)
    qtd = next((q for n, c, q in subpastas if c == caminho_escolhido), 0)
    log_decisao("ESCOLHA_PASTA", f"Escolheu '{nome_escolhido}' ({qtd} arquivos)")
    print(f"\n✅ Pasta selecionada: {nome_escolhido} ({qtd} arquivos)")
    return caminho_escolhido

def perguntar_quantidade_arquivos(total_disponivel: int) -> int:
    """
    Pergunta ao usuário quantos arquivos usar no treino.
    Retorna o número escolhido (<= total_disponivel).
    """
    print("\n" + "="*60)
    print(f"📁 Total de arquivos suportados nesta pasta: {total_disponivel}")
    print("   Você pode treinar com todos ou com uma parte (ex: para testes rápidos).")
    print("="*60)
    while True:
        resp = input("👉 Digite a quantidade de arquivos para treino (ou 'todos' / Enter para usar todos): ").strip().lower()
        if resp == "" or resp == "todos" or resp == "all":
            return total_disponivel
        try:
            qtd = int(resp)
            if 1 <= qtd <= total_disponivel:
                return qtd
            else:
                print(f"⚠️ Digite um número entre 1 e {total_disponivel}.")
        except ValueError:
            print("⚠️ Entrada inválida. Digite um número ou 'todos'.")

def perguntar_continuar_apos_epocas(epoch_atual: int, total_epochs: int, pasta_atual: str,
                                    best_val_loss: float = float('inf')) -> Tuple[str, int, bool]:
    """
    Retorna: (nova_pasta, novas_epocas, resetar)
    - novas_epocas > 0: adiciona épocas extras na pasta atual.
    - resetar = True: reinicia treino do zero (apenas em caso extremo).
    - Se resetar = False e pasta mudar, mantém checkpoint.
    """
    print("\n" + "="*60)
    print(f"📌 Você completou {epoch_atual} épocas (limite: {total_epochs}).")
    if best_val_loss != float('inf'):
        print(f"🏆 Melhor loss até agora: {best_val_loss:.4f}")
    print("\nO que você gostaria de fazer?")
    print("  [1] Continuar TREINANDO MAIS na pasta ATUAL (adicionar épocas)")
    print("  [2] Trocar para OUTRA PASTA e continuar o treino (aproveitar o aprendizado)")
    print("  [3] SAIR (finalizar o programa)")
    print("  [digite 'reset'] para REINICIAR DO ZERO (perde todo o progresso)")
    print("="*60)

    while True:
        opcao = input("👉 Digite o número da opção (ou 'reset'): ").strip().lower()

        if opcao == "1":
            while True:
                try:
                    extra = input("👉 Quantas épocas adicionais você quer treinar? (ex: 10): ").strip()
                    if extra.isdigit() and int(extra) > 0:
                        novas_epocas = int(extra)
                        log_decisao("CONTINUAR_EPOCAS", f"Adicionou {novas_epocas} épocas na pasta '{pasta_atual}'.")
                        return pasta_atual, novas_epocas, False
                    else:
                        print("⚠️ Digite um número inteiro positivo.")
                except:
                    print("⚠️ Entrada inválida.")

        elif opcao == "2":
            ## MODIFICADO: passa usar_registro=True para obter pastas do registro
            nova_pasta = selecionar_pasta_interativamente(PASTA_PROCESSED, pasta_atual, usar_registro=True)
            if nova_pasta and nova_pasta != pasta_atual:
                log_decisao("TROCAR_PASTA", f"Trocou de '{pasta_atual}' para '{nova_pasta}' (mantendo checkpoint).")
                return nova_pasta, 0, False
            else:
                print("⚠️ Nenhuma pasta diferente selecionada. Tente novamente.")
                continue

        elif opcao == "3":
            log_decisao("SAIR", "Usuário encerrou.")
            print("👋 Saindo.")
            sys.exit(0)

        elif opcao == "reset":
            print("\n⚠️ ATENÇÃO: Isso vai APAGAR TODO O PROGRESSO do treino atual.")
            print("   - O otimizador e scheduler serão reiniciados.")
            print("   - A contagem de épocas voltará a zero.")
            print("   - O melhor modelo salvo (modelo_melhor.pt) será mantido, mas o checkpoint será sobrescrito.")
            conf1 = input("   Tem certeza que quer reiniciar do zero? (s/N): ").strip().lower()
            if conf1 != 's':
                print("   Reinicialização cancelada.")
                continue
            conf2 = input("   ÚLTIMA CHANCE: Digite 'SIM' para confirmar: ").strip().upper()
            if conf2 != "SIM":
                print("   Reinicialização cancelada.")
                continue
            log_decisao("REINICIAR_ZERO", "Usuário confirmou reinicialização total do treino.")
            print("🔄 Reiniciando treino do zero.")
            return pasta_atual, 0, True

        else:
            print("⚠️ Opção inválida. Digite 1, 2, 3 ou 'reset'.")

# ============================================================================
# 3. EXTRAÇÃO DE TEXTO (mantida da versão anterior)
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
        log(f"⚠️ PyMuPDF não instalado. Pulando PDF: {os.path.basename(caminho)}", "WARNING")
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
# 4. CRIAÇÃO DO TOKENIZER
# ============================================================================

def listar_arquivos_recurssivo(pasta: str) -> List[str]:
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
        arquivos.extend(listar_arquivos_recurssivo(pasta))

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
        tokenizer.decoder = decoders.ByteLevel()
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
# 5. DEFINIÇÃO DO MODELO
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
# 6. DATASET STREAMING
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
# 7. FUNÇÃO PRINCIPAL
# ============================================================================

def obter_pastas_dados(incluir_ultrachat: bool = False) -> List[str]:
    return [PASTA_DADOS]

def main():
    global BATCH_SIZE, SEQ_LEN, CHECKPOINT_INTERVAL, GRADIENT_ACCUMULATION, PATIENCE, PASTA_DADOS, EPOCHS, MAX_ARQUIVOS

    parser = argparse.ArgumentParser(description="Treino do RigelSLM com aprendizado contínuo")
    parser.add_argument("--dados", type=str, default=PASTA_PROCESSED,
                        help="Pasta com dados (padrão: dados/processed)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--seq-len", type=int, default=SEQ_LEN)
    parser.add_argument("--no-validar", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Força continuação do checkpoint")
    parser.add_argument("--max-arquivos", type=int, default=None, help="Limite de arquivos (se não definido, pergunta interativamente)")
    parser.add_argument("--val-batches", type=int, default=VAL_BATCHES_LIMIT)
    parser.add_argument("--incluir-ultrachat", action="store_true")
    parser.add_argument("--test", type=str, default=None, help="Modo teste")
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument("--save-every", type=int, default=50)
    parser.add_argument("--precision", type=str, default="amp", choices=["fp32", "fp16", "amp"])
    parser.add_argument("--early-stop-patience", type=int, default=PATIENCE)
    parser.add_argument("--no-interactive", action="store_true", help="Pula menu interativo")
    parser.add_argument("--epochs", type=int, default=None, help="Número total de épocas (sobrescreve EPOCHS)")
    ## NOVO: opção para usar registro
    parser.add_argument("--usar-registro", action="store_true",
                        help="Usa registro persistente (registro_pastas.json) para listar pastas, evitando escaneamento recursivo")
    parser.add_argument("--registro", type=str, default=REGISTRO_PATH,
                        help="Caminho do arquivo de registro (padrão: registro_pastas.json)")

    args = parser.parse_args()

    # Se o usuário passou --epochs, atualiza EPOCHS
    if args.epochs is not None:
        EPOCHS = args.epochs

    # --- SELEÇÃO INTERATIVA DE PASTA (sempre, a menos que --no-interactive) ---
    if not args.no_interactive:
        ## MODIFICADO: passar usar_registro=args.usar_registro
        pasta_escolhida = selecionar_pasta_interativamente(PASTA_PROCESSED, args.dados, usar_registro=args.usar_registro)
        if pasta_escolhida is not None:
            args.dados = pasta_escolhida
            log(f"📁 Pasta selecionada: {args.dados}")
        else:
            log(f"📁 Usando pasta: {args.dados}")
    else:
        log(f"📁 Modo não-interativo. Pasta: {args.dados}")

    PASTA_DADOS = args.dados

    # --- CONTAGEM TOTAL DE ARQUIVOS NA PASTA ESCOLHIDA ---
    if args.usar_registro:
        ## NOVO: obtém contagem do registro
        if os.path.exists(args.registro):
            with open(args.registro, 'r', encoding='utf-8') as f:
                registro = json.load(f)
            nome_pasta = os.path.basename(PASTA_DADOS)
            total_disponivel = registro.get("pastas", {}).get(nome_pasta, {}).get("arquivos", 0)
            log(f"📊 Do registro: {total_disponivel} arquivos na pasta '{nome_pasta}'")
        else:
            log(f"⚠️ Registro {args.registro} não encontrado. Escaneando sistema...")
            todos_arquivos = listar_arquivos_recurssivo(PASTA_DADOS)
            total_disponivel = len(todos_arquivos)
    else:
        todos_arquivos = listar_arquivos_recurssivo(PASTA_DADOS)
        total_disponivel = len(todos_arquivos)

    if total_disponivel == 0:
        log(f"❌ Nenhum arquivo suportado em {PASTA_DADOS}. Verifique o caminho.", "ERROR")
        sys.exit(1)

    log(f"📊 Total de arquivos suportados na pasta: {total_disponivel}")

    # --- PERGUNTA QUANTOS ARQUIVOS USAR (se --max-arquivos não foi especificado e não é modo teste) ---
    if args.max_arquivos is None and not args.no_interactive and args.test is None:
        MAX_ARQUIVOS = perguntar_quantidade_arquivos(total_disponivel)
        log(f"📌 Serão usados {MAX_ARQUIVOS} arquivos para treino.")
    else:
        # Se foi fornecido via argumento ou modo não-interativo/teste, usa o valor
        MAX_ARQUIVOS = args.max_arquivos if args.max_arquivos is not None else total_disponivel
        log(f"📌 Limite de arquivos definido: {MAX_ARQUIVOS} (total disponível: {total_disponivel})")

    # --- MODO TESTE (se ativado) ---
    if args.test:
        if not os.path.exists(TOKENIZER_PATH):
            log("❌ Tokenizer não encontrado.", "ERROR")
            sys.exit(1)
        tokenizer = Tokenizer.from_file(TOKENIZER_PATH)

        model = RigelSLM().to(DISPOSITIVO)
        if os.path.exists(MELHOR_MODELO_PATH):
            model.load_state_dict(torch.load(MELHOR_MODELO_PATH, map_location=DISPOSITIVO))
            log(f"✅ Melhor modelo carregado de {MELHOR_MODELO_PATH}")
        elif os.path.exists(MODEL_PATH):
            model.load_state_dict(torch.load(MODEL_PATH, map_location=DISPOSITIVO))
            log(f"✅ Modelo final carregado de {MODEL_PATH}")
        else:
            log("❌ Nenhum modelo encontrado para testar.", "ERROR")
            sys.exit(1)

        test_dataset = StreamingTextDataset(
            args.test, tokenizer, SEQ_LEN, validar_dialogos=True, shuffle=False,
            max_arquivos=MAX_ARQUIVOS
        )
        test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False,
                                 num_workers=args.num_workers if args.num_workers is not None else 1,
                                 pin_memory=torch.cuda.is_available(),
                                 timeout=0, multiprocessing_context='fork' if 'fork' in multiprocessing.get_all_start_methods() else None)

        model.eval()
        total_loss = 0
        total_batches = 0
        loss_fn = nn.CrossEntropyLoss(ignore_index=0, label_smoothing=0.0)

        log(f"🧪 Testando modelo em: {args.test}")
        with torch.no_grad():
            for batch in tqdm(test_loader, desc="Testando", unit="batch"):
                batch = batch.to(DISPOSITIVO)
                logits = model(batch)
                target = batch[:, 1:].contiguous()
                logits = logits[:, :-1, :].contiguous()
                loss = loss_fn(logits.view(-1, VOCAB_SIZE), target.view(-1))
                total_loss += loss.item()
                total_batches += 1

        avg_loss = total_loss / total_batches if total_batches > 0 else 0
        perplexity = math.exp(avg_loss) if avg_loss < 10 else float('inf')

        log(f"📊 Resultado do teste:")
        log(f"   Loss média: {avg_loss:.4f}")
        log(f"   Perplexidade: {perplexity:.2f}")
        log(f"   Total de batches processados: {total_batches}")
        sys.exit(0)

    # --- CONFIGURAÇÃO DO TREINO ---
    BATCH_SIZE = args.batch_size
    SEQ_LEN = args.seq_len
    VALIDAR = not args.no_validar
    RESUME = args.resume
    INCLUIR_ULTRACHAT = args.incluir_ultrachat
    PATIENCE = args.early_stop_patience
    PRECISION = args.precision
    CHECKPOINT_INTERVAL = args.save_every

    # --- DETECÇÃO AUTOMÁTICA DE NÚCLEOS E OTIMIZAÇÃO DE WORKERS ---
    cpu_count = os.cpu_count() or 1
    if torch.cuda.is_available():
        if cpu_count <= 2:
            recommended_workers = 1
            recommended_threads = 1
        else:
            recommended_workers = min(cpu_count - 1, 4)
            recommended_threads = min(cpu_count - 1, 8)
        log(f"✅ GPU detectada. Usando configuração otimizada para GPU.")
    else:
        if cpu_count <= 4:
            recommended_workers = 1
            recommended_threads = max(1, cpu_count - 1)
        else:
            recommended_workers = min(cpu_count - 2, 4)
            recommended_threads = min(cpu_count - 2, 8)
        log(f"💡 CPU detectada. Usando configuração conservadora para CPU.")

    if args.num_workers is not None:
        num_workers = args.num_workers
        log(f"🧵 Workers definidos pelo usuário: {num_workers}")
    else:
        num_workers = recommended_workers
        log(f"🧠 Detectados {cpu_count} núcleos. Usando {num_workers} workers e {recommended_threads} threads.")

    torch.set_num_threads(recommended_threads)
    log(f"🔧 PyTorch configurado com {torch.get_num_threads()} threads.")

    # --- PRECISÃO ---
    if PRECISION in ("fp16", "amp"):
        if not torch.cuda.is_available():
            log("⚠️ AMP requer GPU. Mudando para fp32.", "WARNING")
            PRECISION = "fp32"
            scaler = None
        else:
            log(f"✅ Precisão mista ({PRECISION.upper()})")
            scaler = GradScaler('cuda')
    else:
        scaler = None

    # --- CRIAÇÃO DE DIRETÓRIOS ---
    for p in [os.path.dirname(TOKENIZER_PATH), os.path.dirname(MODEL_PATH),
              os.path.dirname(LOG_PATH), PASTA_PROCESSED, PASTA_GERADOS,
              PASTA_CURTOS, PASTA_LONGOS, PASTA_RESUMIDOS]:
        os.makedirs(p, exist_ok=True)

    # --- LOG INICIAL ---
    log("="*80)
    log("🚀 RIGELSLM v6.6.0 – TREINO CONTÍNUO E INTELIGENTE")
    log(f"📅 {datetime.now()}")
    log(f"💻 Dispositivo: {DISPOSITIVO}")
    log(f"📁 Dados: {PASTA_DADOS}")
    log(f"📊 Batch: {BATCH_SIZE}, Seq: {SEQ_LEN}")
    log(f"🧵 Workers: {num_workers}, Threads: {torch.get_num_threads()}")
    log(f"💾 Save every: {CHECKPOINT_INTERVAL}")
    log(f"🎯 Precisão: {PRECISION}")
    log(f"📂 Arquivos para treino: {MAX_ARQUIVOS} de {total_disponivel} disponíveis")
    if args.usar_registro:
        log(f"📋 Usando registro: {args.registro}")
    log("="*80)

    # --- TOKENIZER ---
    if not os.path.exists(TOKENIZER_PATH):
        log("⚠️ Tokenizer não encontrado. Criando...")
        if not criar_tokenizer():
            log("❌ Falha ao criar tokenizer.", "ERROR")
            sys.exit(1)
    else:
        log(f"✅ Tokenizer carregado de {TOKENIZER_PATH}")
    tokenizer = Tokenizer.from_file(TOKENIZER_PATH)

    # --- MODELO ---
    model = RigelSLM().to(DISPOSITIVO)
    start_epoch = 0
    best_val_loss = float('inf')
    no_improve = 0
    total_batches = 0

    # --- CARREGAR CHECKPOINT ---
    checkpoint_disponivel = os.path.exists(CHECKPOINT_PATH)
    if checkpoint_disponivel and not RESUME:
        try:
            checkpoint = torch.load(CHECKPOINT_PATH, map_location=DISPOSITIVO)
            ep = checkpoint.get('epoch', 0)
            best_loss = checkpoint.get('best_val_loss', float('inf'))
            log(f"📦 Checkpoint encontrado (época {ep}, melhor loss {best_loss:.4f})")
            resp = input("   Continuar de onde parou? (s/N): ").strip().lower()
            if resp == 's':
                RESUME = True
        except:
            log("⚠️ Checkpoint corrompido. Iniciando do zero.", "WARNING")
            RESUME = False

    if RESUME and checkpoint_disponivel:
        try:
            checkpoint = torch.load(CHECKPOINT_PATH, map_location=DISPOSITIVO)
            model.load_state_dict(checkpoint["model_state_dict"])
            start_epoch = checkpoint.get("epoch", 0) + 1
            best_val_loss = checkpoint.get("best_val_loss", float('inf'))
            no_improve = checkpoint.get("no_improve", 0)
            total_batches = checkpoint.get("total_batches", 0)
            log(f"✅ Checkpoint carregado. Retomando da época {start_epoch-1}")
            log(f"✅ Melhor validação: {best_val_loss:.4f}")
            log(f"⏱️ Batches processados: {total_batches}")
        except Exception as e:
            log(f"⚠️ Falha ao carregar checkpoint: {e}. Iniciando do zero.", "ERROR")
            start_epoch = 0
            best_val_loss = float('inf')
            no_improve = 0
            total_batches = 0
    elif os.path.exists(MODEL_PATH):
        try:
            model.load_state_dict(torch.load(MODEL_PATH, map_location=DISPOSITIVO))
            log("📦 Modelo carregado de modelo.pt (pesos apenas).")
        except:
            log("⚠️ Falha ao carregar modelo.pt. Iniciando do zero.", "WARNING")

    # --- EXIBE TAMANHOS ---
    log(f"🧠 Parâmetros do modelo: {sum(p.numel() for p in model.parameters()):,}")
    model_size_mb = sum(p.numel() * p.element_size() for p in model.parameters()) / (1024**2)
    log(f"📦 Tamanho do modelo (pesos): {model_size_mb:.2f} MB")
    if os.path.exists(CHECKPOINT_PATH):
        ckpt_size_mb = os.path.getsize(CHECKPOINT_PATH) / (1024**2)
        log(f"📦 Tamanho do checkpoint: {ckpt_size_mb:.2f} MB (inclui otimizador e estado)")
        log(f"ℹ️  O checkpoint é maior porque salva o estado do otimizador, scheduler e metadados.")
        log(f"ℹ️  Para reduzir, você pode salvar apenas os pesos (como modelo.pt). A quantização pode reduzir o tamanho, mas com possível perda de qualidade.")

    # --- OTIMIZADOR, SCHEDULER ---
    optimizer = AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
    scheduler_warmup = None
    scheduler_plateau = None
    loss_fn = nn.CrossEntropyLoss(ignore_index=0, label_smoothing=LABEL_SMOOTHING)

    # --- LOOP PRINCIPAL (aprendizado contínuo) ---
    while True:
        # --- SE HOUVER TROCA DE PASTA OU RESET, RECARREGA DADOS ---
        arquivos = listar_arquivos_recurssivo(PASTA_DADOS)
        if not arquivos:
            log(f"❌ Nenhum arquivo suportado em {PASTA_DADOS}. Verifique o caminho.", "ERROR")
            sys.exit(1)

        random.shuffle(arquivos)
        val_size = max(1, int(len(arquivos) * 0.1))
        train_arquivos = arquivos[val_size:]
        val_arquivos = arquivos[:val_size]
        if MAX_ARQUIVOS and MAX_ARQUIVOS < len(train_arquivos):
            train_arquivos = train_arquivos[:MAX_ARQUIVOS]
            val_arquivos = val_arquivos[:min(len(val_arquivos), MAX_ARQUIVOS//10)]
        log(f"📂 {len(train_arquivos)} treino, {len(val_arquivos)} validação")

        # --- DATASETS E DATALOADERS ---
        train_dataset = StreamingTextDataset(PASTA_DADOS, tokenizer, SEQ_LEN, VALIDAR, shuffle=True, max_arquivos=MAX_ARQUIVOS)
        train_dataset._arquivos = train_arquivos
        val_dataset = StreamingTextDataset(PASTA_DADOS, tokenizer, SEQ_LEN, VALIDAR, shuffle=False, max_arquivos=MAX_ARQUIVOS)
        val_dataset._arquivos = val_arquivos

        ctx = 'fork' if 'fork' in multiprocessing.get_all_start_methods() else None
        pin_mem = torch.cuda.is_available()

        train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=False,
                                  num_workers=num_workers, pin_memory=pin_mem, timeout=0,
                                  multiprocessing_context=ctx)
        val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False,
                                num_workers=num_workers, pin_memory=pin_mem, timeout=0,
                                multiprocessing_context=ctx)

        # --- RECRIAR SCHEDULERS SE RESETOU ---
        if scheduler_warmup is None:
            chunks_por_arquivo = 10
            estimated_batches_per_epoch = max(1, len(train_arquivos) * chunks_por_arquivo // (BATCH_SIZE * GRADIENT_ACCUMULATION))
            total_steps = estimated_batches_per_epoch * EPOCHS
            log(f"🧮 Estimativa de batches/época: {estimated_batches_per_epoch}")
            log(f"📊 Total de steps estimado: {total_steps}")
            warmup_steps = min(WARMUP_STEPS, total_steps // 10)

            def lr_lambda(step):
                if step < warmup_steps:
                    return step / warmup_steps
                else:
                    progress = (step - warmup_steps) / (total_steps - warmup_steps)
                    return 0.5 * (1 + math.cos(math.pi * progress))

            scheduler_warmup = LambdaLR(optimizer, lr_lambda)
            scheduler_plateau = ReduceLROnPlateau(optimizer, mode='min', factor=REDUCE_ON_PLATEAU_FACTOR,
                                                  patience=REDUCE_ON_PLATEAU_PATIENCE)

        # --- VERIFICA SE JÁ COMPLETOU AS ÉPOCAS ---
        if start_epoch >= EPOCHS:
            log(f"ℹ️ O checkpoint já completou {EPOCHS} épocas (limite: {EPOCHS}).", "INFO")
            nova_pasta, novas_epocas, resetar = perguntar_continuar_apos_epocas(start_epoch, EPOCHS, PASTA_DADOS, best_val_loss)
            if resetar:
                log("🔄 Reiniciando treino do zero.")
                start_epoch = 0
                best_val_loss = float('inf')
                no_improve = 0
                total_batches = 0
                optimizer = AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY)
                scheduler_warmup = None
                scheduler_plateau = None
                if args.epochs is None:
                    EPOCHS = 20
                else:
                    EPOCHS = args.epochs
                continue
            elif novas_epocas > 0:
                EPOCHS += novas_epocas
                log(f"📈 Total de épocas ajustado para {EPOCHS}")
                continue
            elif nova_pasta != PASTA_DADOS:
                PASTA_DADOS = nova_pasta
                args.dados = nova_pasta
                log(f"🔄 Pasta alterada para {PASTA_DADOS}. Mantendo checkpoint (época atual: {start_epoch}/{EPOCHS}).")
                continue
            else:
                break

        # --- LOOP DE ÉPOCAS ---
        for epoch in range(start_epoch, EPOCHS):
            model.train()
            total_loss = 0
            steps = 0
            epoch_start_time = time.time()
            log(f"\n🚀 Epoch {epoch+1}/{EPOCHS}")

            progress_bar = tqdm(train_loader, desc=f"Epoch {epoch+1}", unit="batch")
            optimizer.zero_grad()
            nan_retries = 0

            for i, batch in enumerate(progress_bar):
                try:
                    batch = batch.to(DISPOSITIVO)

                    if PRECISION in ("fp16", "amp"):
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
                        if PRECISION in ("fp16", "amp"):
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
                            log_gpu_usage()

                        if total_batches % CHECKPOINT_INTERVAL == 0:
                            torch.save({
                                'epoch': epoch,
                                'model_state_dict': model.state_dict(),
                                'best_val_loss': best_val_loss,
                                'no_improve': no_improve,
                                'total_batches': total_batches,
                                'optimizer_state_dict': optimizer.state_dict(),
                                'scheduler_state_dict': scheduler_warmup.state_dict()
                            }, CHECKPOINT_PATH)
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

            avg_train_loss = total_loss / steps if steps > 0 else 0
            log(f"✅ Epoch {epoch+1} - Loss média treino: {avg_train_loss:.4f}")

            # Validação
            model.eval()
            val_loss = 0
            val_steps = 0
            with torch.no_grad():
                for batch in val_loader:
                    if val_steps > args.val_batches:
                        break
                    try:
                        batch = batch.to(DISPOSITIVO)
                        if PRECISION in ("fp16", "amp"):
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

            # Feedback sobre loss
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
                    break
                else:
                    log("📉 O loss SUBIU ou estagnou → isso é RUIM. Talvez precise ajustar LR ou dados.")

            # Feedback sobre learning rate
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
            salvar_metricas(epoch+1, avg_train_loss, avg_val_loss, lr_atual, tempo_epoch)
            salvar_estado_treino(epoch+1, best_val_loss, no_improve, total_batches)
            limpar_cache()
            log_gpu_usage()

        # --- FIM DO LOOP DE ÉPOCAS ---
        log(f"🏁 Todas as {EPOCHS} épocas foram concluídas.")
        start_epoch = EPOCHS

        ## NOVO: Atualiza registro de treino (incrementa contador)
        if args.usar_registro:
            try:
                from organizar_pastas import incrementar_treino
                nome_pasta = os.path.basename(PASTA_DADOS)
                incrementar_treino([nome_pasta], args.registro)
                log(f"📋 Registro atualizado: pasta '{nome_pasta}' treinada mais uma vez.")
            except ImportError:
                log("⚠️ Módulo organizar_pastas não encontrado. Registro não atualizado.", "WARNING")
            except Exception as e:
                log(f"⚠️ Erro ao atualizar registro: {e}", "WARNING")

    # --- FIM DO LOOP PRINCIPAL ---
    torch.save(model.state_dict(), MODEL_PATH)
    log(f"\n💾 Modelo final salvo em {MODEL_PATH}")
    log("="*80)
    log("🏁 TREINO CONCLUÍDO")
    log(f"🏆 Melhor loss: {best_val_loss:.4f}")
    log(f"📂 Modelo final: {MODEL_PATH}")
    log(f"📂 Melhor modelo: {MELHOR_MODELO_PATH}")
    log(f"📊 Métricas: {METRICAS_PATH}")
    log(f"📝 Log: {LOG_PATH}")
    log(f"📋 Decisões: {DECISOES_LOG}")
    if args.usar_registro:
        log(f"📋 Registro usado: {args.registro}")
    log("="*80)

if __name__ == "__main__":
    main()