#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================================
# RIGELSLM - TREINO SFT COM DATASETS JSONL (treinar_com_jsonl.py) v1.0.0
# Data: 31/07/2026 | Arquivos de treino: 1.089
# ============================================================================
# O QUE ESTE MÓDULO FAZ:
#   Fine-Tuning SUPERVISIONADO (SFT) do RigelSLM usando datasets JSONL no
#   formato {"messages": [{"role": "system"|"user"|"assistant", ...}]}
#   (exatamente o que o createjsonl.py gera).
#
# DIFERENÇA ESSENCIAL vs treino.py:
#   - treino.py  : aprendizado CAUSAL (prevê TODOS os tokens do texto contínuo).
#   - este módulo: SFT com MÁSCARA DE LOSS — o modelo só aprende a prever os
#                  tokens do ASSISTANT (system/user ficam como contexto,
#                  ignorados no loss). É isso que ensina "como responder".
#
# REUTILIZAÇÃO (não duplica código):
#   - importa treino.py: classe RigelSLM, tokenizer, detecção de dispositivo,
#     funções de log, menus interativos, convenções de pastas e parâmetros.
#   - Mesmas convenções de saída do treino.py para o pipeline continuar:
#       modelo/modelo.pt            -> modelo final (pesos)
#       modelo/modelo_melhor.pt     -> melhor validação (usado pelo converter)
#       modelo/checkpoint_jsonl.pt  -> checkpoint de retomada (separado do treino.py)
#       modelo/estado_treino_jsonl.json -> progresso (epoch, best loss, batches)
#       logs/treinar_jsonl.log      -> log próprio
#       logs/metricas_jsonl.json    -> histórico de métricas próprio
#   - Depois: python converter_para_gguf.py --model modelo/modelo_melhor.pt
#
# USO:
#   python treinar_com_jsonl.py --dados dados/processed/<nome>
#   python treinar_com_jsonl.py --dados dados/gerados/jsonl/<nome> --epochs 5
#   python treinar_com_jsonl.py --dados <pasta> --resume --lr 3e-5 --batch-size 4
#
# ARGS IMPORTANTES:
#   --dados            Pasta com arquivos .jsonl (default: dados/processed).
#                      Se não existir, tenta dados/gerados/jsonl.
#   --modelo           Caminho dos pesos base (.pt). Default automático:
#                      checkpoint_jsonl.pt > modelo/modelo_melhor.pt > modelo/modelo.pt
#   --epochs, --batch-size, --seq-len, --lr, --accum (acumulação de gradiente)
#   --incluir-system   Inclui o system prompt no contexto (default: sim)
#   --resume           Retoma do checkpoint_jsonl.pt
#   --no-interactive   Pula o menu de escolha de subpasta
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
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import ReduceLROnPlateau, LambdaLR
from torch.utils.data import Dataset, DataLoader
from torch.amp import GradScaler, autocast
from tqdm import tqdm

# Garante que o diretório do script esteja no path (import de treino.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Garante saída UTF-8 no console (evita UnicodeEncodeError no Windows/cp1252)
for _stream in (sys.stdout, sys.stderr):
    _reconf = getattr(_stream, "reconfigure", None)
    if callable(_reconf):
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ============================================================================
# REUTILIZAÇÃO DO ECOSSISTEMA EXISTENTE (treino.py) — código único de verdade
# ============================================================================
try:
    import treino
    from treino import RigelSLM, PositionalEncoding  # noqa: F401 (re-export p/ clareza)
except Exception as _e:  # pragma: no cover
    print(f"❌ Não foi possível importar treino.py: {_e}")
    print("   Verifique se o script está na raiz do projeto RigelSLM.")
    sys.exit(1)

# Dispositivo detectado UMA vez pelo treino.py (GPU ou CPU)
DISPOSITIVO = treino.DISPOSITIVO
TOKENIZER_PATH = treino.TOKENIZER_PATH

# ============================================================================
# CONFIGURAÇÕES (herda os padrões do treino.py e ajusta para SFT)
# ============================================================================
SFT_IGNORE = -100  # token de máscara: posições que NÃO entram no loss (system/user/pad)

# Caminhos próprios deste módulo (não conflitam com os do treino.py)
LOG_PATH = "logs/treinar_jsonl.log"
METRICAS_PATH = "logs/metricas_jsonl.json"
ESTADO_PATH = "modelo/estado_treino_jsonl.json"
CHECKPOINT_PATH = "modelo/checkpoint_jsonl.pt"
# 📋 Registro consolidado de treino — lido pela plataforma (local OU Colab)
# para mostrar "o que foi treinado" (datasets, arquivos, épocas, loss, nível).
REGISTRO_TREINO_PATH = "modelo/registro_treino.json"

# Registro de PASTAS por tipo (gerado por scripts/registrar_pastas.py) — com
# --usar-registro o treino vai DIRETO às pastas registradas (sem escanear tudo).
REGISTRO_PASTAS_TREINO_PATH = "registro_pastas_treino.json"

# Caminhos COMPARTILHADOS com o treino.py (o pipeline continua funcionando)
MODEL_PATH = treino.MODEL_PATH            # modelo/modelo.pt (final)
MELHOR_MODELO_PATH = treino.MELHOR_MODELO_PATH  # modelo/modelo_melhor.pt (melhor val)

# Parâmetros de SFT (diferentes do treino causal: LR menor, sem label smoothing)
SFT_LEARNING_RATE = 5e-4
SFT_LABEL_SMOOTHING = 0.0
SFT_EPOCHS = 5
SFT_GRADIENT_ACCUMULATION = 4
SFT_WARMUP_FRACAO = 0.01   # fração dos steps totais para warmup

# Limites de segurança
MAX_EXEMPLOS_PADRAO = 200_000
MAX_NAN_RETRIES = 3
LOG_INTERVAL = 50
VAL_BATCHES_LIMIT = 200

# Extensões de dados aceitas
EXTENSOES_JSONL = (".jsonl", ".jsonl.gz", ".json", ".json.gz")


# ============================================================================
# 1. LOG (encapsula o log do treino.py apontando para o arquivo deste módulo)
# ============================================================================
def log(msg: str, nivel: str = "INFO", console: bool = True) -> None:
    """Registra no logs/treinar_jsonl.log (reusa a função do treino.py)."""
    treino.log(msg, nivel=nivel, console=console, arquivo=LOG_PATH)


def log_decisao(acao: str, detalhes: str) -> None:
    treino.log_decisao(acao, detalhes)


def _garantir_pasta(caminho: str) -> None:
    """Cria o diretório pai do caminho (idempotente, falha silenciosa)."""
    try:
        pasta = os.path.dirname(os.path.abspath(caminho))
        if pasta:
            os.makedirs(pasta, exist_ok=True)
    except Exception:
        pass


def _salvar_torch_seguro(dados, caminho: str, rotulo: str = "checkpoint",
                         tentativas: int = 4) -> bool:
    """torch.save com retry — tolera falhas transitórias de disco (ex.: Google
    Drive instável no Colab: 'Parent directory X does not exist').
    Se falhar em todas, avisa mas NÃO levanta exceção — o treino continua e o
    próximo save costuma funcionar."""
    import time as _time
    for tentativa in range(1, tentativas + 1):
        try:
            _garantir_pasta(caminho)
            torch.save(dados, caminho)
            return True
        except Exception as e:
            if tentativa < tentativas:
                log(f"⚠️ Falha transitória salvando {rotulo} ({e}). "
                    f"Tentativa {tentativa}/{tentativas}...", "WARNING")
                _time.sleep(2 * tentativa)
            else:
                log(f"❌ Falha ao salvar {rotulo} em {caminho}: {e}", "ERROR")
    return False


# ============================================================================
# 2. LOCALIZAÇÃO DE ARQUIVOS JSONL
# ============================================================================
def localizar_arquivos_jsonl(pasta: str) -> List[str]:
    """Localiza recursivamente arquivos .jsonl/.json/.gz dentro de uma pasta."""
    arquivos = []
    if not os.path.exists(pasta):
        return arquivos
    for raiz, _, arquivos_nome in os.walk(pasta):
        for nome in arquivos_nome:
            if nome.lower().endswith(EXTENSOES_JSONL):
                arquivos.append(os.path.join(raiz, nome))
    return sorted(arquivos)


def listar_subpastas_jsonl(pasta_base: str) -> List[Tuple[str, str, int]]:
    """Lista subpastas que contêm arquivos JSONL (com contagem)."""
    if not os.path.exists(pasta_base):
        return []
    subpastas = []
    for item in sorted(os.listdir(pasta_base)):
        caminho = os.path.join(pasta_base, item)
        if os.path.isdir(caminho):
            total = len(localizar_arquivos_jsonl(caminho))
            if total > 0:
                subpastas.append((item, caminho, total))
    subpastas.sort(key=lambda x: x[2], reverse=True)
    return subpastas


def _resolver_pastas_dados(args) -> List[str]:
    """Resolve --dados, que pode conter VÁRIAS pastas (separadas por vírgula
    ou ';') — exatamente como o dashboard envia (ex.: "--dados A,B,C").

    Cada item pode ser:
      - caminho relativo/absoluto de pasta com .jsonl (ex.: dados/processed/jsonl/X);
      - nome de subpasta dentro de dados/gerados/jsonl, dados/processed/jsonl
        ou dados/processed.

    Retorna a lista de pastas que realmente existem. Pastas inexistentes são
    ignoradas com aviso. Se o default do argparse (dados/processed) não
    existir, tenta dados/gerados/jsonl (comportamento antigo — SÓ no default).
    NUNCA cai num fallback mudo que treina pastas que o usuário não pediu.
    """
    bruto = (args.dados or "").strip()
    itens = [p.strip() for p in re.split(r"[;,]", bruto) if p.strip()]
    bases = ["dados/gerados/jsonl", "dados/processed/jsonl", "dados/processed"]
    encontradas: List[str] = []
    ignoradas: List[str] = []
    for item in itens:
        if os.path.isdir(item):
            encontradas.append(item)
            continue
        achou = False
        for base in bases:
            cand = os.path.join(base, item)
            if os.path.isdir(cand):
                encontradas.append(cand)
                achou = True
                break
        if not achou:
            ignoradas.append(item)
    if ignoradas:
        log(f"⚠️ Pasta(s) não encontradas e IGNORADAS: {', '.join(ignoradas)}", "WARNING")
    if not encontradas and bruto == treino.PASTA_PROCESSED:
        # Default do argparse não existe — compatibilidade com o comportamento
        # antigo: tenta a base de datasets explodidos.
        alt = os.path.join("dados", "gerados", "jsonl")
        if os.path.exists(alt) and localizar_arquivos_jsonl(alt):
            log(f"⚠️ '{bruto}' não existe. Usando '{alt}' como base.", "WARNING")
            encontradas = [alt]
    return encontradas


def _pastas_jsonl_do_registro() -> List[str]:
    """Lê registro_pastas_treino.json e devolve pastas tipo 'jsonl' que existem
    (vai DIRETO às pastas registradas — sem escanear o acervo inteiro)."""
    try:
        with open(REGISTRO_PASTAS_TREINO_PATH, "r", encoding="utf-8") as f:
            reg = json.load(f)
    except Exception:
        return []
    pastas = reg.get("pastas", {}) if isinstance(reg, dict) else {}
    out: List[str] = []
    for nome, info in pastas.items():
        if not isinstance(info, dict):
            continue
        if info.get("tipo", "") != "jsonl":
            continue
        caminho = info.get("caminho")
        if caminho and os.path.isdir(caminho) and localizar_arquivos_jsonl(caminho):
            out.append(caminho)
    return out


# ============================================================================
# 3. NORMALIZAÇÃO DOS EXEMPLOS (messages / conversations / chat / pergunta-resposta)
# ============================================================================
def normalizar_turnos(obj: Any) -> Optional[List[Tuple[str, str]]]:
    """
    Extrai e normaliza os turnos de um objeto JSON de qualquer dataset.
    Retorna [(role, content), ...] com roles em system/user/assistant,
    ou None se não for possível.
    """
    if not isinstance(obj, dict):
        return None

    msgs = None
    if isinstance(obj.get("messages"), list):
        msgs = obj["messages"]
    elif isinstance(obj.get("conversations"), list):
        # Formato HuggingFace: {"from": "human"/"gpt", "value": "..."}
        msgs = obj["conversations"]
    elif isinstance(obj.get("chat"), list):
        msgs = obj["chat"]
    elif "pergunta" in obj and "resposta" in obj:
        # Formato antigo do treino.py
        return [("user", str(obj.get("pergunta", "")).strip()),
                ("assistant", str(obj.get("resposta", "")).strip())]

    if not msgs:
        return None

    mapa = {"human": "user", "h": "user", "gpt": "assistant", "a": "assistant",
            "bot": "assistant", "ia": "assistant"}
    turnos = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or m.get("from") or "").strip().lower()
        content = m.get("content") or m.get("value") or m.get("text")
        if not content:
            continue
        role = mapa.get(role, role)
        if role not in ("system", "user", "assistant"):
            continue
        texto = str(content).strip()
        if not texto:
            continue
        turnos.append((role, texto))
    return turnos or None


# ============================================================================
# 4. CONSTRUÇÃO DOS EXEMPLOS SFT (texto + máscara de loss no assistant)
# ============================================================================
def construir_exemplo_sft(turnos: List[Tuple[str, str]], tokenizer,
                          seq_len: int, incluir_system: bool = True
                          ) -> Optional[Tuple[torch.Tensor, torch.Tensor]]:
    """
    Converte turnos em (input_ids, labels) para SFT.

    Formato: [BOS] system [SEP] user [SEP] assistant [EOS]
    labels:  -100 em system/user/SEP/padding (contexto), token id no assistant.

    Se a sequência passar de seq_len, trunca PELO COMEÇO (system primeiro,
    depois user), preservando ao máximo a resposta do assistant.
    """
    bos_id = tokenizer.token_to_id(treino.BOS_TOKEN)
    eos_id = tokenizer.token_to_id(treino.EOS_TOKEN)
    sep_id = tokenizer.token_to_id(treino.SEP_TOKEN)
    if None in (bos_id, eos_id, sep_id):
        return None

    # Separa por papel
    partes_sys: List[str] = []
    partes_usr: List[str] = []
    partes_ast: List[str] = []
    for role, texto in turnos:
        if role == "system":
            partes_sys.append(texto)
        elif role == "user":
            partes_usr.append(texto)
        elif role == "assistant":
            partes_ast.append(texto)

    if not partes_usr or not partes_ast:
        return None  # sem pergunta ou sem resposta -> não serve

    # Codifica cada parte separadamente (para saber onde o assistant começa)
    def _enc(texto: str) -> List[int]:
        try:
            return tokenizer.encode(texto).ids
        except Exception:
            return []

    blocos: List[Tuple[List[int], bool]] = []  # (ids, eh_assistente)
    if incluir_system:
        for txt in partes_sys:
            ids_txt = _enc(txt)
            if ids_txt:
                blocos.append((ids_txt, False))
    for txt in partes_usr:
        ids_txt = _enc(txt)
        if ids_txt:
            blocos.append((ids_txt, False))
    for txt in partes_ast:
        ids_txt = _enc(txt)
        if ids_txt:
            blocos.append((ids_txt, True))

    if not any(eh_ast for _, eh_ast in blocos):
        return None  # sem conteúdo de assistant tokenizado

    # Monta a sequência com [BOS] no início e [SEP] entre blocos
    ids: List[int] = [bos_id]
    eh_alvo: List[bool] = [False]
    inicio_assistente: Optional[int] = None
    for ids_bloco, eh_ast in blocos:
        if ids_bloco:
            ids.extend(ids_bloco)
            eh_alvo.extend([eh_ast] * len(ids_bloco))
            if eh_ast and inicio_assistente is None:
                inicio_assistente = len(ids) - len(ids_bloco)
        ids.append(sep_id)
        eh_alvo.append(eh_ast)
    if inicio_assistente is None:
        return None  # sem conteúdo de assistant na sequência final
    # O último [SEP] vira [EOS] (o modelo aprende a encerrar a resposta)
    ids[-1] = eos_id

    # Trunca PELO COMEÇO se passar do limite (preserva a resposta)
    if len(ids) > seq_len:
        cortar = len(ids) - seq_len
        # 1) corta o prefixo (system + user) primeiro
        cortar_prefixo = min(cortar, inicio_assistente)
        ids = ids[cortar_prefixo:]
        eh_alvo = eh_alvo[cortar_prefixo:]
        cortar -= cortar_prefixo
        # 2) se ainda passar, corta do início do assistant
        if cortar > 0:
            ids = ids[cortar:]
            eh_alvo = eh_alvo[cortar:]
        if not any(eh_alvo):
            return None  # a resposta inteira foi perdida no corte

    # labels: id do token onde é alvo (assistant), -100 no resto
    labels = [tid if alvo else SFT_IGNORE for tid, alvo in zip(ids, eh_alvo)]

    # Padding
    pad_id = tokenizer.token_to_id(treino.PAD_TOKEN) or 0
    if len(ids) < seq_len:
        ids = ids + [pad_id] * (seq_len - len(ids))
        labels = labels + [SFT_IGNORE] * (seq_len - len(labels))
    else:
        ids = ids[:seq_len]
        labels = labels[:seq_len]

    return (torch.tensor(ids, dtype=torch.long),
            torch.tensor(labels, dtype=torch.long))


# ============================================================================
# 5. DATASET SFT (pré-processa tudo em memória com barra de progresso)
# ============================================================================
class SFTDataset(Dataset):
    def __init__(self, arquivos: List[str], tokenizer, seq_len: int = treino.SEQ_LEN,
                 incluir_system: bool = True, max_exemplos: Optional[int] = None,
                 dedup: bool = True):
        self.amostras: List[Tuple[torch.Tensor, torch.Tensor]] = []
        vistos: set[str] = set()
        duplicatas = 0
        invalidos = 0

        for caminho in tqdm(arquivos, desc="Carregando datasets", unit="arq",
                            leave=False):
            try:
                if caminho.endswith(".gz"):
                    import gzip
                    # utf-8-sig remove o BOM (se houver) sem quebrar UTF-8 puro
                    abrir = gzip.open(caminho, "rt", encoding="utf-8-sig")
                else:
                    abrir = open(caminho, "r", encoding="utf-8-sig")
                with abrir as f:
                    for linha in f:
                        linha = linha.strip()
                        # tolerância extra a BOM no início da linha (ex.:
                        # arquivos salvos pelo PowerShell/Notepad)
                        if linha and linha[0] == "\ufeff":
                            linha = linha[1:].strip()
                        if not linha:
                            continue
                        try:
                            obj = json.loads(linha)
                        except Exception:
                            continue
                        # Linha pode ser uma lista de exemplos
                        objetos = obj if isinstance(obj, list) else [obj]
                        for item in objetos:
                            turnos = normalizar_turnos(item)
                            if not turnos:
                                invalidos += 1
                                continue
                            if dedup:
                                chave = _hash_pergunta(turnos)
                                if chave in vistos:
                                    duplicatas += 1
                                    continue
                                vistos.add(chave)
                            exemplo = construir_exemplo_sft(
                                turnos, tokenizer, seq_len, incluir_system)
                            if exemplo is None:
                                invalidos += 1
                                continue
                            self.amostras.append(exemplo)
                            if max_exemplos and len(self.amostras) >= max_exemplos:
                                break
                        if max_exemplos and len(self.amostras) >= max_exemplos:
                            break
            except Exception as e:
                log(f"⚠️ Erro ao ler {caminho}: {e}", "WARNING", console=False)
            if max_exemplos and len(self.amostras) >= max_exemplos:
                break

        log(f"🗂️ Exemplos válidos: {len(self.amostras)} "
            f"(duplicatas removidas: {duplicatas}, inválidos: {invalidos})")

    def __len__(self) -> int:
        return len(self.amostras)

    def __getitem__(self, idx: int):
        return self.amostras[idx]


def _hash_pergunta(turnos: List[Tuple[str, str]]) -> str:
    """Hash MD5 da pergunta do usuário (para deduplicação)."""
    for role, texto in turnos:
        if role == "user":
            return hashlib.md5(texto.strip().lower().encode("utf-8")).hexdigest()
    return hashlib.md5(repr(turnos).encode("utf-8")).hexdigest()


# ============================================================================
# 6. CARREGAMENTO DO MODELO (checkpoint SFT > pesos base)
# ============================================================================
def carregar_modelo(modelo_path: Optional[str], resume: bool,
                    interativo: bool = True) -> Tuple[Any, int, float, int, int, Optional[dict]]:
    """
    Carrega o RigelSLM com a seguinte prioridade:
      1. checkpoint_jsonl.pt (retomada SFT)  -> se --resume ou confirmado
      2. --modelo (pesos base informados)
      3. modelo/modelo_melhor.pt
      4. modelo/modelo.pt
      5. do zero (inicialização aleatória)
    Retorna (model, start_epoch, best_val_loss, no_improve, total_batches,
             otim_estado) — otim_estado é o estado do Adam do checkpoint
             (None se não houver), p/ o treino continuar sem perder momentum.
    """
    model = RigelSLM().to(DISPOSITIVO)
    start_epoch = 0
    best_val_loss = float("inf")
    no_improve = 0
    total_batches = 0
    otim_estado = None

    ckpt_disponivel = os.path.exists(CHECKPOINT_PATH)

    # Pergunta se quer retomar (mesmo comportamento do treino.py)
    if ckpt_disponivel and not resume and interativo:
        try:
            ckpt = torch.load(CHECKPOINT_PATH, map_location=DISPOSITIVO)
            ep = ckpt.get("epoch", 0)
            bl = ckpt.get("best_val_loss", float("inf"))
            log(f"📦 Checkpoint SFT encontrado (época {ep}, melhor loss {bl:.4f})")
            resp = input("   Continuar de onde parou? (s/N): ").strip().lower()
            resume = resp == "s"
        except Exception:
            log("⚠️ Checkpoint SFT corrompido. Iniciando do zero.", "WARNING")
            resume = False

    if resume and ckpt_disponivel:
        try:
            ckpt = torch.load(CHECKPOINT_PATH, map_location=DISPOSITIVO)
            model.load_state_dict(ckpt["model_state_dict"])
            start_epoch = ckpt.get("epoch", 0) + 1
            best_val_loss = ckpt.get("best_val_loss", float("inf"))
            no_improve = ckpt.get("no_improve", 0)
            total_batches = ckpt.get("total_batches", 0)
            otim_estado = ckpt.get("optimizer_state_dict") or None
            log(f"✅ Checkpoint SFT carregado. Retomando da época {start_epoch - 1}")
            log(f"✅ Melhor validação: {best_val_loss:.4f} | Batches: {total_batches}")
        except Exception as e:
            log(f"⚠️ Falha ao carregar checkpoint SFT: {e}. Iniciando do zero.", "ERROR")
            start_epoch = 0
            best_val_loss = float("inf")
            no_improve = 0
            total_batches = 0
            otim_estado = None
    else:
        # Pesos base: --modelo, senão modelo_melhor.pt, senão modelo.pt
        candidatos = [modelo_path] if modelo_path else []
        candidatos += [MELHOR_MODELO_PATH, MODEL_PATH]
        carregado = False
        for caminho in candidatos:
            if caminho and os.path.exists(caminho):
                try:
                    model.load_state_dict(torch.load(caminho, map_location=DISPOSITIVO))
                    log(f"📦 Pesos base carregados de {caminho}")
                    carregado = True
                    break
                except Exception as e:
                    log(f"⚠️ Falha ao carregar {caminho}: {e}", "WARNING")
        if not carregado:
            log("🌱 Nenhum peso encontrado. Inicializando modelo do zero.")

    return model, start_epoch, best_val_loss, no_improve, total_batches, otim_estado


# ============================================================================
# 7. AVALIAÇÃO (validação com máscara SFT)
# ============================================================================
def avaliar(model: Any, loader: DataLoader, loss_fn: nn.Module,
            precision: str = "fp32", val_batches: int = VAL_BATCHES_LIMIT) -> float:
    """Calcula o loss médio de validação (com a máscara SFT)."""
    model.eval()
    total = 0.0
    passos = 0
    with torch.no_grad():
        for batch_ids, batch_labels in loader:
            if passos >= val_batches:
                break
            try:
                batch_ids = batch_ids.to(DISPOSITIVO)
                batch_labels = batch_labels.to(DISPOSITIVO)
                if precision in ("fp16", "amp") and torch.cuda.is_available():
                    with autocast("cuda"):
                        logits = model(batch_ids)
                        logits = logits[:, :-1, :].contiguous()
                        target = batch_labels[:, 1:].contiguous()
                        loss = loss_fn(logits.view(-1, treino.VOCAB_SIZE),
                                       target.view(-1))
                else:
                    logits = model(batch_ids)
                    logits = logits[:, :-1, :].contiguous()
                    target = batch_labels[:, 1:].contiguous()
                    loss = loss_fn(logits.view(-1, treino.VOCAB_SIZE),
                                   target.view(-1))
                _li = loss.item()
                if math.isfinite(_li):
                    total += _li
                    passos += 1
                else:
                    log(f"⚠️ Validação: loss inválido ({_li}) ignorado.", "WARNING", console=False)
            except Exception as e:
                log(f"⚠️ Erro na validação: {e}", "WARNING", console=False)
                continue
    return total / passos if passos > 0 else float("inf")


def _feedback_treino(historico: list[float], lr_atual: float, lr_anterior: float | None,
                     no_improve: int) -> None:
    """Mensagens motivacionais/diagnóstico com base na tendência do loss e do LR."""
    # --- Direção do Learning Rate ---
    if lr_anterior is not None:
        if lr_atual > lr_anterior * 1.001:
            log(f"📈 LR SUBINDO ({lr_anterior:.6f} → {lr_atual:.6f}) — "
                f"fase de warmup, o modelo está aquecendo.")
        elif lr_atual < lr_anterior * 0.999:
            log(f"📉 LR DESCENDO ({lr_anterior:.6f} → {lr_atual:.6f}) — "
                f"decaimento, refinando os pesos.")
        else:
            log(f"➡️ LR estável: {lr_atual:.6f}")
    else:
        log(f"🔄 LR inicial: {lr_atual:.6f}")

    # --- Tendência do loss de treino ---
    if len(historico) >= 2:
        ant, novo = historico[-2], historico[-1]
        delta = novo - ant
        if delta <= -0.05:
            log(f"🎉 ÓTIMO! O modelo ESTÁ APRENDENDO — loss caindo: "
                f"{ant:.4f} → {novo:.4f} ({delta:+.4f}). Continue assim!")
        elif delta < 0.0:
            log(f"👍 Bom progresso — loss caindo aos poucos: "
                f"{ant:.4f} → {novo:.4f} ({delta:+.4f}).")
        elif abs(delta) <= 0.05:
            log(f"📊 O modelo está ESTÁVEL (loss {ant:.4f} → {novo:.4f}).")
            if no_improve >= 2:
                log("   💭 Se estagnar por 3+ épocas: tente dados MAIS DIVERSOS ou ajuste o LR.")
        else:
            log(f"⚠️ Loss SUBIU: {ant:.4f} → {novo:.4f} ({delta:+.4f}).")
            log("   💭 Pode ser ruído de batch. Se persistir, os dados podem estar repetitivos —")
            log("   💭 use dados de melhor qualidade/mais variados ou um LR menor.")


def _resumo_sessao(inicio: float, total_batches: int, args: argparse.Namespace) -> None:
    """Resumo da sessão: tempo, tokens processados, velocidade e orçamento diário."""
    decorrido = time.time() - inicio
    tokens = max(0, total_batches) * args.accum * args.batch_size * args.seq_len
    tps = tokens / decorrido if decorrido > 0 else 0.0
    # ~930 mil tokens por arquivo explodido (1000 exemplos, medido no Guará)
    TOKENS_POR_ARQUIVO = 930_000
    arquivos = tokens / TOKENS_POR_ARQUIVO
    log("=" * 80)
    log("⏱️ RESUMO DA SESSÃO")
    log(f"   Tempo: {decorrido / 60:.1f} min | Batches (otimizador): {total_batches}")
    log(f"   Tokens processados: ~{tokens / 1e6:.2f}M | Velocidade: {tps:.0f} tokens/s")
    log(f"   Equivale a ~{arquivos:.1f} arquivos (1000 exemplos cada)")
    if tps < 1000:
        log(f"   💡 Você está em CPU. Em 2h ≈ {max(1, int(tps * 7200 / TOKENS_POR_ARQUIVO))} arquivo(s).")
        log("   💡 Para volume maior, use a T4 do Colab (~50-100x mais rápido).")
    else:
        log(f"   💡 2h nesta velocidade ≈ {max(1, int(tps * 7200 / TOKENS_POR_ARQUIVO))} arquivos.")
    log("=" * 80)


def _marcar_conclusao_jsonlogs(pasta_dados: str, arquivos: list) -> None:
    """Marca os arquivos treinados em modelo/jsonlogs/<dataset>.json (bandeiras).
    Executado pelo PRÓPRIO treinador ao concluir — assim a marcação NÃO depende
    do processo do dashboard (sobrevive a --reload/restarts e vale no Colab)."""
    try:
        if not arquivos:
            return
        dataset = os.path.basename(os.path.normpath(os.path.dirname(arquivos[0]))) or "dataset"
        import json as _json
        pasta_logs = os.path.join("modelo", "jsonlogs")
        os.makedirs(pasta_logs, exist_ok=True)
        caminho = os.path.join(pasta_logs, dataset.replace("/", "_").replace("\\", "_") + ".json")
        log_dados = {}
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    log_dados = _json.load(f)
            except Exception:
                log_dados = {}
        if not isinstance(log_dados, dict):
            log_dados = {}
        log_dados.setdefault("dataset", dataset)
        log_dados.setdefault("arquivos", {})
        if not isinstance(log_dados["arquivos"], dict):
            log_dados["arquivos"] = {}
        agora = datetime.now().isoformat()
        for a in arquivos:
            nome = os.path.basename(a)
            info = log_dados["arquivos"].get(nome, {})
            if isinstance(info, int):  # compatibilidade com formato antigo
                info = {"vezes": info}
            vezes = int(info.get("vezes", 0)) + 1
            log_dados["arquivos"][nome] = {"vezes": vezes, "ultima": agora}
        with open(caminho, "w", encoding="utf-8") as f:
            _json.dump(log_dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _contagem_treinado(arquivo: str) -> int:
    """Quantas vezes este arquivo já foi treinado (modelo/jsonlogs/<dataset>.json)."""
    try:
        import json as _json
        dataset = os.path.basename(os.path.normpath(os.path.dirname(arquivo))) or "dataset"
        caminho = os.path.join("modelo", "jsonlogs",
                               dataset.replace("/", "_").replace("\\", "_") + ".json")
        if not os.path.exists(caminho):
            return 0
        with open(caminho, "r", encoding="utf-8") as f:
            dados = _json.load(f)
        info = (dados.get("arquivos") or {}).get(os.path.basename(arquivo), {})
        if isinstance(info, int):  # formato antigo
            return info
        return int(info.get("vezes", 0))
    except Exception:
        return 0


def _filtrar_ja_treinados(arquivos: list, limite: int, pasta_dados: str):
    """Filtra arquivos já treinados 'limite' ou mais vezes.
    Retorna (filtrados, pulados) onde pulados = [(nome, contagem)]."""
    if limite <= 0:
        return arquivos, []
    filtrados: list = []
    pulados: list = []
    for a in arquivos:
        contagem = _contagem_treinado(a)
        if contagem >= limite:
            pulados.append((os.path.basename(a), contagem))
        else:
            filtrados.append(a)
    if pulados:
        log(f"⏭️ Pulando {len(pulados)} arquivo(s) já treinado(s) "
            f"(limite >= {limite}):", "WARNING")
        for nome, contagem in pulados[:10]:
            log(f"   - {nome} ({contagem}x)")
        if len(pulados) > 10:
            log(f"   ... e mais {len(pulados) - 10} arquivo(s)")
    return filtrados, pulados


def _salvar_progresso(arquivo: str, epoch: int, total_epochs: int, step: int,
                      steps_por_epoch: int, loss: float | None, lr: float | None,
                      eta_segundos: float | None, inicio: str, status: str) -> None:
    """Escreve modelo/jsonlogs/progresso.json — alimenta a barra de percentual
    do dashboard. O PRÓPRIO treinador atualiza (sobrevive a --reload/restarts)."""
    try:
        import json as _json
        spo = max(1, steps_por_epoch)
        te = max(1, total_epochs)
        percentual = min(100.0, max(0.0, ((epoch - 1) + step / spo) / te * 100))
        dados = {
            "arquivo": arquivo,
            "epoch": epoch,
            "total_epochs": total_epochs,
            "step": step,
            "steps_por_epoch": steps_por_epoch,
            "loss": round(float(loss), 4) if loss is not None else None,
            "lr": round(float(lr), 6) if lr is not None else None,
            "percentual": round(percentual, 1),
            "eta_segundos": int(eta_segundos) if eta_segundos is not None else None,
            "inicio": inicio,
            "status": status,
            "atualizado": datetime.now().isoformat(),
        }
        pasta = os.path.join("modelo", "jsonlogs")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "progresso.json"), "w", encoding="utf-8") as f:
            _json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _backup_antes_de_salvar(caminho: str, motivo: str) -> None:
    """Backup cauteloso: guarda uma cópia em modelo/backups/ antes de sobrescrever."""
    try:
        if caminho and os.path.exists(caminho):
            from modelo_backup import criar_backup_arquivo
            criar_backup_arquivo(caminho, motivo=motivo)
    except Exception:
        pass


# ============================================================================
# 8. LOOP DE TREINO SFT
# ============================================================================
def treinar(args: argparse.Namespace) -> None:
    # --usar-registro: vai DIRETO às pastas registradas (tipo jsonl)
    if getattr(args, "usar_registro", False):
        reg_pastas = _pastas_jsonl_do_registro()
        if not reg_pastas:
            log("❌ Nenhuma pasta 'jsonl' no registro "
                "(registro_pastas_treino.json). Rode "
                "scripts/registrar_pastas.py --tipo jsonl primeiro.", "ERROR")
            sys.exit(1)
        log(f"📂 Usando pastas do REGISTRO (tipo jsonl): "
            f"{', '.join(os.path.basename(p) for p in reg_pastas)}")
        args.dados = ",".join(reg_pastas)

    # --- Pastas de dados (interativa como o treino.py) ---
    # --dados pode conter VÁRIAS pastas (separadas por vírgula ou ';'), como o
    # dashboard envia. Resolve cada uma e AVISA/para em vez de cair num
    # fallback mudo que treinava pastas que o usuário NÃO selecionou.
    pasta_dados = args.dados
    pastas_efetivas = _resolver_pastas_dados(args)
    if not pastas_efetivas:
        log(f"❌ Nenhuma pasta de dados encontrada em '{args.dados}'. "
            "Verifique o caminho (ou o nome da pasta em dados/gerados/jsonl "
            "ou dados/processed).", "ERROR")
        sys.exit(1)
    pasta_dados = pastas_efetivas[0]  # base usada nos logs

    if not args.no_interactive:
        subpastas = listar_subpastas_jsonl(pasta_dados)
        if subpastas:
            escolhida = treino.menu_interativo(subpastas)
            if escolhida is not None:
                pasta_dados = escolhida
                pastas_efetivas = [escolhida]
                log_decisao("ESCOLHA_PASTA", f"Escolheu '{os.path.basename(pasta_dados)}'")

    # Localiza os arquivos em TODAS as pastas resolvidas (sem caminhos duplicados)
    arquivos: List[str] = []
    for _p in pastas_efetivas:
        arquivos.extend(localizar_arquivos_jsonl(_p))
    arquivos = sorted(set(arquivos))
    if not arquivos:
        log(f"❌ Nenhum arquivo JSONL nas pastas selecionadas. Verifique o caminho.", "ERROR")
        sys.exit(1)
    log(f"📂 {len(arquivos)} arquivos JSONL em {len(pastas_efetivas)} pasta(s): "
        f"{', '.join(os.path.basename(p) for p in pastas_efetivas)}")

    # 💉 CARTEIRA DE QUALIDADE: verifica se o material passou pelos processos
    # (sanitizado/verificado/ajuizado/promovido). Material CRU NÃO vai para o
    # treino sem aviso claro — o usuário decide (regra: nada se perde, nada
    # cru treina). Desative com --sem-carteira.
    if not getattr(args, "sem_carteira", False):
        try:
            from dashboard.services.qualidade import status as _q_status
            crudas = []
            for _p in pastas_efetivas:
                _st = _q_status(os.path.basename(_p.rstrip("/\\")))
                if not _st.get("pronto_treino"):
                    faltam = _st.get("faltam") or []
                    crudas.append(f"{os.path.basename(_p.rstrip('/\\'))} "
                                  f"(falta: {', '.join(faltam) if faltam else 'registro'})")
            if crudas:
                log("💉 CARTEIRA DE QUALIDADE: algumas pastas NÃO estão marcadas "
                    "como prontas para treino:", "WARNING")
                for c in crudas:
                    log(f"   🥩 {c}", "WARNING")
                log("   → Pode ser material cru (sem sanitização/verificação/"
                    "ajuizamento/promoção) ou registro ainda não criado.", "WARNING")
                log("   → Para treinar mesmo assim, rode com --sem-carteira.", "WARNING")
        except Exception as _e:
            log(f"⚠️ Carteira de qualidade indisponível ({_e}) — seguindo sem verificação.", "WARNING")

    if args.arquivo:
        alvo = os.path.basename(args.arquivo)
        filtrados = [a for a in arquivos if os.path.basename(a) == alvo]
        if not filtrados:
            log(f"❌ Arquivo '{alvo}' não encontrado em {pasta_dados}.", "ERROR")
            sys.exit(1)
        arquivos = filtrados
        log(f"🎯 Treinando apenas o arquivo: {alvo}")

    max_arquivos = args.max_arquivos or len(arquivos)
    arquivos = arquivos[:max_arquivos]
    # Pula arquivos já treinados N ou mais vezes — exceto com --force
    if getattr(args, "force", False):
        log("⚡ --force ativo: treinando mesmo os arquivos já treinados.", "WARNING")
    elif getattr(args, "pular_treinados", 0) and args.pular_treinados > 0:
        arquivos, _pul = _filtrar_ja_treinados(arquivos, args.pular_treinados, pasta_dados)
        if not arquivos:
            log("⏭️ Todos os arquivos já foram treinados o suficiente. Nada a treinar.", "WARNING")
            sys.exit(0)
    log(f"📂 {len(arquivos)} arquivos JSONL em {pasta_dados}")

    # 📊 FEEDBACK DE MATERIAL (regra de ouro: o programa AVISA se o material é
    # suficiente ou insuficiente para o modelo — ~1000 exemplos/arquivo):
    _n_arq = len(arquivos)
    _ex_est = _n_arq * 1000
    if _n_arq < 10:
        log(f"⚠️ Material BAIXO: {_n_arq} arquivo(s) (~{_ex_est} exemplos). Para o "
            "SLM 58M o ideal é 100+ arquivos (~100k exemplos) por época. Serve como "
            "TESTE rápido, mas o modelo não vai 'aprender' de verdade.", "WARNING")
    elif _n_arq < 50:
        log(f"ℹ️ Material moderado: {_n_arq} arquivos (~{_ex_est} exemplos). Aceitável "
            "para ajuste fino; mais dados melhorariam o resultado.", "INFO")
    else:
        log(f"✅ Material suficiente: {_n_arq} arquivos (~{_ex_est} exemplos). "
            "Bom volume para o treino.", "INFO")

    # --- Detecção de núcleos / workers (mesma lógica do treino.py) ---
    cpu_count = os.cpu_count() or 1
    if torch.cuda.is_available():
        recommended_workers = min(cpu_count - 1, 4) if cpu_count > 2 else 1
        recommended_threads = min(cpu_count - 1, 8) if cpu_count > 2 else 1
    else:
        if cpu_count <= 4:
            recommended_workers = 1
            recommended_threads = max(1, cpu_count - 1)
        else:
            recommended_workers = min(cpu_count - 2, 4)
            recommended_threads = min(cpu_count - 2, 8)
    num_workers = args.num_workers if args.num_workers is not None else recommended_workers
    threads = args.threads if getattr(args, "threads", None) is not None else recommended_threads
    threads = max(1, min(cpu_count, int(threads)))
    torch.set_num_threads(threads)
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    log(f"🧠 {cpu_count} núcleos | workers: {num_workers} | threads: {threads}")

    # --- Precisão / AMP ---
    precision = args.precision
    scaler = None
    if precision in ("fp16", "amp"):
        if not torch.cuda.is_available():
            log("⚠️ AMP requer GPU. Mudando para fp32.", "WARNING")
            precision = "fp32"
        else:
            log(f"✅ Precisão mista ({precision.upper()})")
            scaler = GradScaler("cuda")

    # --- Tokenizer ---
    if not os.path.exists(TOKENIZER_PATH):
        log(f"❌ Tokenizer não encontrado em {TOKENIZER_PATH}.", "ERROR")
        sys.exit(1)
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(TOKENIZER_PATH)
    log(f"✅ Tokenizer carregado ({tokenizer.get_vocab_size()} tokens)")

    # --- Dataset SFT ---
    log(f"🧬 Pré-processando exemplos SFT (seq_len={args.seq_len}, "
        f"incluir_system={'sim' if args.incluir_system else 'não'})...")
    dataset = SFTDataset(arquivos, tokenizer, seq_len=args.seq_len,
                         incluir_system=args.incluir_system,
                         max_exemplos=args.max_exemplos)
    if len(dataset) == 0:
        log("❌ Nenhum exemplo válido encontrado. Verifique os arquivos JSONL.", "ERROR")
        sys.exit(1)

    # --- Divisão treino/validação ---
    random.seed(args.seed)
    indices = list(range(len(dataset)))
    random.shuffle(indices)
    val_size = max(1, int(len(indices) * args.val_split))
    val_indices = indices[:val_size]
    train_indices = indices[val_size:]
    log(f"📊 Treino: {len(train_indices)} | Validação: {len(val_indices)}")

    # ⚠️ Aviso claro quando o dataset é minúsculo — treino não ensina NADA.
    # (Sintoma clássico: LR preso em 0 e validação idêntica em todas as épocas.)
    if len(dataset) < 100:
        log(f"❌⚠️ DATASET MUITO PEQUENO: apenas {len(dataset)} exemplo(s) válido(s). "
            "Este treino praticamente NÃO vai ensinar nada.", "ERROR")
        log("   Verifique o FORMATO dos arquivos: o treinador SFT só aceita "
            "{\"messages\": [...]} (ou conversations/chat/pergunta-resposta). "
            "Arquivos {\"text\": ...} são DESCARTADOS!", "ERROR")
    elif len(dataset) < 1000:
        log(f"⚠️ Dataset pequeno: {len(dataset)} exemplo(s). Considere mais dados.", "WARNING")

    # 🔒 Proteção (correção 17/08): com 1 exemplo válido a divisão treino/val
    # pode deixar o conjunto de TREINO vazio → DataLoader estoura com
    # "num_samples should be a positive integer". Abortar com mensagem clara
    # em vez de traceback feio.
    if len(train_indices) == 0:
        log("❌ Conjunto de TREINO vazio (todos os exemplos viraram validação). "
            "O dataset tem exemplos demais duplicados ou de menos — não há "
            "nada para treinar.", "ERROR")
        log("   Dica: use mais arquivos/dados, ou confira se as pastas "
            "selecionadas não são cópias duplicadas (ex.: *_sanitizado*).",
            "ERROR")
        sys.exit(1)

    from torch.utils.data import Subset
    train_dataset = Subset(dataset, train_indices)
    val_dataset = Subset(dataset, val_indices)

    ctx = "fork" if "fork" in torch.multiprocessing.get_all_start_methods() else None
    pin_mem = torch.cuda.is_available()
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size,
                              shuffle=True, num_workers=num_workers,
                              pin_memory=pin_mem, timeout=0,
                              multiprocessing_context=ctx)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size,
                            shuffle=False, num_workers=num_workers,
                            pin_memory=pin_mem, timeout=0,
                            multiprocessing_context=ctx)

    # --- Acumulação de gradiente EFETIVA (corrige o "LR=0 / nada aprende") ---
    # Bug antigo: com poucos batches por época e accum grande, `(i+1) % accum`
    # nunca zerava → optimizer.step() NUNCA rodava → LR preso no valor do
    # warmup (0) e o modelo nunca era atualizado (validação idêntica a cada
    # época). Agora o accum é limitado ao nº real de batches e o último batch
    # de cada época SEMPRE dispara um step (flush).
    n_batches_reais = max(1, len(train_loader))
    accum_efetivo = max(1, min(args.accum, n_batches_reais))
    if accum_efetivo != args.accum:
        log(f"ℹ️ Accum efetivo reduzido de {args.accum} para {accum_efetivo} "
            f"({n_batches_reais} batch(es) reais/época) — garante ao menos "
            f"1 passo de otimização por época.", "WARNING")

    # --- Modelo ---
    model, start_epoch, best_val_loss, no_improve, total_batches, otim_estado = carregar_modelo(
        args.modelo, args.resume, interativo=not args.no_interactive)

    n_params = sum(p.numel() for p in model.parameters())
    log(f"🧠 Parâmetros do modelo: {n_params:,}")
    log(f"📦 Tamanho dos pesos: {n_params * 4 / 1024 / 1024:.1f} MB (fp32)")

    # --- Otimizador e scheduler (cosine + warmup, como treino.py) ---
    optimizer = AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    # Estado do Adam: restaurar no resume (senão cada restart perde o momentum
    # e o treino "esquece"). No modo fila, o reiniciar_lr abaixo ainda zera o LR.
    if otim_estado:
        try:
            optimizer.load_state_dict(otim_estado)
            log("✅ Estado do otimizador (Adam) restaurado do checkpoint SFT.")
        except Exception as e:
            log(f"⚠️ Não foi possível restaurar o Adam: {e}. Otimizador novo.", "WARNING")

    # 🔁 Fila: LR reinicializado explicitamente no início de cada arquivo.
    # O otimizador/scheduler são criados novos aqui (carregar_modelo não
    # restaura o estado do otimizador), mas garantimos o valor base para o
    # modelo nunca ficar estagnado com LR=0 ao trocar de arquivo.
    if getattr(args, "reiniciar_lr", False):
        for pg in optimizer.param_groups:
            pg["lr"] = args.lr
        log(f"🔁 LR reinicializado para {args.lr:.2e} (novo arquivo da fila).")

    scheduler_warmup = None
    scheduler_plateau = None
    loss_fn = nn.CrossEntropyLoss(ignore_index=SFT_IGNORE,
                                  label_smoothing=args.label_smoothing)

    # Passos de OTIMIZADOR por época (com o accum efetivo e flush no fim).
    batchs_por_epoch = max(1, math.ceil(n_batches_reais / accum_efetivo))
    total_steps = batchs_por_epoch * args.epochs
    warmup_steps = max(1, int(total_steps * SFT_WARMUP_FRACAO))
    # Nunca deixar o warmup dominar treinos curtos (máx. metade dos steps).
    warmup_steps = min(warmup_steps, max(1, total_steps // 2))
    log(f"🧮 Steps otimizador/época: {batchs_por_epoch} | total: {total_steps} | "
        f"warmup: {warmup_steps}")

    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / warmup_steps
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        # LR oscila entre 0.3 e 1.0 do valor inicial (em vez de 0.1~0.5)
        return float(0.3 + 0.7 * (0.5 + 0.5 * math.cos(math.pi * progress)))

    scheduler_warmup = LambdaLR(optimizer, lr_lambda)

    # --- Log inicial ---
    log("=" * 80)
    log("🚀 TREINAR_COM_JSONL v1.0.0 — SFT DO RIGELSLM (loss só no assistant)")
    log(f"📅 {datetime.now()}")
    log(f"💻 Dispositivo: {DISPOSITIVO}")
    log(f"📁 Dados: {pasta_dados} ({len(arquivos)} arquivos)")
    log(f"📊 Batch: {args.batch_size} | Accum: {args.accum} | Seq: {args.seq_len}")
    log(f"🎯 LR: {args.lr} | WD: {args.weight_decay} | Épocas: {args.epochs}")
    log(f"💾 Save every: {args.save_every} batches | Precisão: {precision}")
    log(f"🧪 Validação: {args.val_split * 100:.0f}% | Early stop: {args.early_stop_patience}")
    log("=" * 80)

    # --- LOOP DE ÉPOCAS ---
    arquivo_treino = os.path.basename(args.arquivo) if args.arquivo else "todos"
    inicio_iso = datetime.now().isoformat()
    _salvar_progresso(arquivo_treino, start_epoch, args.epochs, 0,
                      batchs_por_epoch, None, None, None, inicio_iso, "treinando")
    epoch = start_epoch - 1
    historico_train: list[float] = []
    lr_anterior: float | None = None
    inicio_treino = time.time()
    try:
        for epoch in range(start_epoch, args.epochs):
            model.train()
            total_loss = 0.0
            steps = 0
            n_batches_epoch = 0  # contagem REAL de batches (evita inflar por accum)
            epoch_start = time.time()
            log(f"\n🚀 Epoch {epoch + 1}/{args.epochs}")
            _atualizar_progresso_fila(args, epoch + 1, args.epochs, 0,
                                      batchs_por_epoch, None,
                                      optimizer.param_groups[0]["lr"])

            progress_bar = tqdm(train_loader, desc=f"Epoch {epoch + 1}", unit="batch")
            optimizer.zero_grad()
            nan_retries = 0
            ultimo_log_progresso = time.time()

            for i, (batch_ids, batch_labels) in enumerate(progress_bar):
                try:
                    batch_ids = batch_ids.to(DISPOSITIVO)
                    batch_labels = batch_labels.to(DISPOSITIVO)

                    if precision in ("fp16", "amp"):
                        with autocast("cuda"):
                            logits = model(batch_ids)
                            logits = logits[:, :-1, :].contiguous()
                            target = batch_labels[:, 1:].contiguous()
                            loss = loss_fn(logits.view(-1, treino.VOCAB_SIZE),
                                           target.view(-1))
                            loss = loss / accum_efetivo
                        scaler.scale(loss).backward()  # type: ignore[union-attr]
                    else:
                        logits = model(batch_ids)
                        logits = logits[:, :-1, :].contiguous()
                        target = batch_labels[:, 1:].contiguous()
                        loss = loss_fn(logits.view(-1, treino.VOCAB_SIZE),
                                       target.view(-1))
                        loss = loss / accum_efetivo
                        loss.backward()

                    if treino.verificar_nan(loss, "loss"):
                        nan_retries += 1
                        if nan_retries >= MAX_NAN_RETRIES:
                            log("❌ NaN persistente. Reduzindo LR.", "ERROR")
                            for pg in optimizer.param_groups:
                                pg["lr"] *= 0.5
                            nan_retries = 0
                        else:
                            log(f"⚠️ NaN, tentativa {nan_retries}/{MAX_NAN_RETRIES}. "
                                "Pulando batch.", "WARNING")
                        optimizer.zero_grad()
                        continue

                    total_loss += loss.item() * accum_efetivo
                    n_batches_epoch += 1

                    # Step a cada accum batches; o ÚLTIMO batch da época sempre
                    # dispara step (flush) — sem isso, com poucos batches o
                    # optimizer nunca rodava e o modelo não aprendia nada.
                    if (i + 1) % accum_efetivo == 0 or (i + 1) == n_batches_reais:
                        if precision in ("fp16", "amp"):
                            scaler.unscale_(optimizer)  # type: ignore[union-attr]
                            torch.nn.utils.clip_grad_norm_(model.parameters(),
                                                           treino.MAX_GRAD_NORM)
                            scaler.step(optimizer)  # type: ignore[union-attr]
                            scaler.update()  # type: ignore[union-attr]
                        else:
                            torch.nn.utils.clip_grad_norm_(model.parameters(),
                                                           treino.MAX_GRAD_NORM)
                            optimizer.step()
                        scheduler_warmup.step()
                        optimizer.zero_grad()
                        steps += 1
                        total_batches += 1
                        progress_bar.set_postfix(
                            {"loss": f"{loss.item() * accum_efetivo:.4f}"})

                        if steps % LOG_INTERVAL == 0:
                            lr_atual = optimizer.param_groups[0]["lr"]
                            log(f"  Batch {steps} | loss: "
                                f"{loss.item() * accum_efetivo:.4f} | lr: {lr_atual:.6f}")
                            treino.log_gpu_usage()

                        if total_batches % args.save_every == 0:
                            _salvar_torch_seguro({
                                "epoch": epoch,
                                "model_state_dict": model.state_dict(),
                                "best_val_loss": best_val_loss,
                                "no_improve": no_improve,
                                "total_batches": total_batches,
                                "optimizer_state_dict": optimizer.state_dict(),
                                "scheduler_state_dict": scheduler_warmup.state_dict(),
                            }, CHECKPOINT_PATH, "checkpoint")
                            log(f"  💾 Checkpoint salvo em {CHECKPOINT_PATH}")

                    if i % 100 == 0:
                        treino.limpar_cache()

                except RuntimeError as e:
                    if "out of memory" in str(e).lower():
                        log("⚠️ OOM. Pulando batch e liberando memória.", "WARNING")
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        optimizer.zero_grad()
                        continue
                    log(f"❌ Erro no batch: {e}", "ERROR")
                    traceback.print_exc()
                    optimizer.zero_grad()
                    continue
                except Exception as e:
                    log(f"❌ Erro inesperado: {e}", "ERROR")
                    traceback.print_exc()
                    optimizer.zero_grad()
                    continue

                # ⏳ Progresso periódico — no CPU o console ficava mudo por ~20 min
                # por época; agora mostra a cada 30s que o treino está vivo.
                agora = time.time()
                if agora - ultimo_log_progresso >= 30:
                    ultimo_log_progresso = agora
                    decorrido = agora - epoch_start
                    steps_otim = max(1, steps or ((i + 1) // accum_efetivo))
                    ritmo = decorrido / steps_otim if steps_otim else 0.0
                    eta_epoch = ritmo * max(0, batchs_por_epoch - steps_otim)
                    lr_atual = optimizer.param_groups[0]["lr"]
                    log(f"  ⏳ Epoch {epoch + 1}/{args.epochs} | step "
                        f"{steps_otim}/{batchs_por_epoch} | loss: "
                        f"{loss.item() * accum_efetivo:.4f} | lr: {lr_atual:.6f} "
                        f"| {decorrido:.0f}s decorridos | ETA época ~{eta_epoch:.0f}s")
                    _salvar_progresso(arquivo_treino, epoch + 1, args.epochs,
                                      steps_otim, batchs_por_epoch,
                                      loss.item() * accum_efetivo, lr_atual,
                                      eta_epoch, inicio_iso, "treinando")
                    _atualizar_progresso_fila(args, epoch + 1, args.epochs,
                                              steps_otim, batchs_por_epoch,
                                              loss.item() * accum_efetivo, lr_atual)

            avg_train = total_loss / n_batches_epoch if n_batches_epoch > 0 else 0.0
            historico_train.append(avg_train)
            tempo_epoch = time.time() - epoch_start

            # Feedback motivacional/diagnóstico (tendência do loss + direção do LR)
            lr_atual = optimizer.param_groups[0]["lr"]
            _feedback_treino(historico_train, lr_atual, lr_anterior, no_improve)
            lr_anterior = lr_atual

            log(f"✅ Epoch {epoch + 1} — Loss média treino: {avg_train:.4f} | "
                f"tempo: {tempo_epoch:.0f}s")
            if args.epochs - (epoch + 1) > 0:
                eta = tempo_epoch * (args.epochs - (epoch + 1))
                log(f"⏳ ETA para terminar as épocas restantes: ~{eta / 60:.1f} min")

            # Validação
            avg_val = avaliar(model, val_loader, loss_fn, precision,
                              val_batches=args.val_batches) if args.validar else float("inf")
            log(f"📉 Loss validação: {avg_val:.4f}")

            # Melhor modelo / early stopping
            if avg_val < best_val_loss:
                log("🏆 Validação melhorou — salvando melhor modelo!")
                best_val_loss = avg_val
                no_improve = 0
                _backup_antes_de_salvar(MELHOR_MODELO_PATH, "melhor_modelo")
                _salvar_torch_seguro(model.state_dict(), MELHOR_MODELO_PATH,
                                     "melhor modelo", tentativas=5)
                log(f"💾 Melhor modelo salvo em {MELHOR_MODELO_PATH}")
            else:
                no_improve += 1
                if no_improve >= args.early_stop_patience:
                    log("⏹️ Early stopping! (loss não melhora há várias épocas)")
                    break
                log(f"📉 Validação não melhorou ({no_improve}/{args.early_stop_patience}) — observando...")

            lr_atual = optimizer.param_groups[0]["lr"]
            log(f"🔄 Learning rate atual: {lr_atual:.6f}")

            # Exemplo de geração (qualitativo)
            try:
                gerado = model.generate(tokenizer, "Olá, tudo bem?",
                                        max_new_tokens=60, temperature=0.7)
                log(f"📝 Exemplo: 'Olá, tudo bem?' -> '{gerado}'")
            except Exception as e:
                log(f"⚠️ Erro na geração: {e}", "WARNING")

            # Métricas + estado
            tempo_epoch = time.time() - epoch_start
            _salvar_metricas(epoch + 1, avg_train, avg_val, lr_atual, tempo_epoch)
            _salvar_estado(epoch + 1, best_val_loss, no_improve, total_batches)
            treino.limpar_cache()
            treino.log_gpu_usage()

    except KeyboardInterrupt:
        log("⏹️ Interrompido pelo usuário. Salvando estado...", "WARNING")
        _salvar_checkpoint_seguro(model, optimizer, scheduler_warmup, epoch,
                                  best_val_loss, no_improve, total_batches)
        _backup_antes_de_salvar(MODEL_PATH, "interrompido")
        _salvar_torch_seguro(model.state_dict(), MODEL_PATH,
                             "modelo (interrompido)", tentativas=5)
        _salvar_estado(epoch + 1, best_val_loss, no_improve, total_batches)
        log("💾 Progresso salvo. Você pode retomar com --resume.")
        _resumo_sessao(inicio_treino, total_batches, args)
        _marcar_conclusao_jsonlogs(pasta_dados, arquivos)
        _salvar_registro_treino(pasta_dados, arquivos, epoch + 1,
                                best_val_loss, origem=getattr(args, "origem", "local"))
        _salvar_progresso(arquivo_treino, epoch + 1, args.epochs,
                          steps, batchs_por_epoch, None, None,
                          None, inicio_iso, "interrompido")
        return

    # --- Fim do treino ---
    _backup_antes_de_salvar(MODEL_PATH, "treino_concluido")
    _salvar_torch_seguro(model.state_dict(), MODEL_PATH,
                         "modelo final", tentativas=6)
    _resumo_sessao(inicio_treino, total_batches, args)
    _marcar_conclusao_jsonlogs(pasta_dados, arquivos)
    _salvar_registro_treino(pasta_dados, arquivos, args.epochs,
                            best_val_loss, origem=getattr(args, "origem", "local"))
    _salvar_progresso(arquivo_treino, args.epochs, args.epochs,
                      batchs_por_epoch, batchs_por_epoch,
                      best_val_loss, optimizer.param_groups[0]["lr"],
                      0, inicio_iso, "concluido")
    log(f"\n💾 Modelo final salvo em {MODEL_PATH}")
    log("=" * 80)
    log("🏁 TREINO SFT CONCLUÍDO")
    log(f"🏆 Melhor loss: {best_val_loss:.4f}")
    log(f"📂 Melhor modelo: {MELHOR_MODELO_PATH}")
    log(f"📂 Modelo final: {MODEL_PATH}")
    log(f"💾 Checkpoint: {CHECKPOINT_PATH}")
    log(f"📊 Métricas: {METRICAS_PATH}")
    log(f"📝 Log: {LOG_PATH}")
    log("=" * 80)
    log("➡️  Próximo passo: python converter_para_gguf.py "
        "--model modelo/modelo_melhor.pt --quant Q4_K_M")


def _salvar_metricas(epoch: int, train_loss: float, val_loss: float,
                     lr: float, tempo: float) -> None:
    """Append de métricas no logs/metricas_jsonl.json (mantém histórico)."""
    historico = treino.carregar_json(METRICAS_PATH, {"historico": []})
    historico.setdefault("historico", []).append({
        "epoch": epoch,
        "train_loss": train_loss,
        "val_loss": val_loss,
        "learning_rate": lr,
        "tempo_segundos": round(tempo, 2),
        "timestamp": datetime.now().isoformat(),
    })
    historico["historico"] = historico["historico"][-200:]
    treino.salvar_json(METRICAS_PATH, historico)


def _salvar_estado(epoch: int, best_val_loss: float, no_improve: int,
                   total_batches: int) -> None:
    """Salva o progresso no modelo/estado_treino_jsonl.json."""
    treino.salvar_json(ESTADO_PATH, {
        "epoch": epoch,
        "best_val_loss": best_val_loss,
        "no_improve": no_improve,
        "total_batches": total_batches,
        "timestamp": datetime.now().isoformat(),
    })


def _salvar_registro_treino(pasta_dados: str, arquivos: list, epoch: int,
                            best_val_loss: float, origem: str = "local") -> None:
    """📋 Grava o REGISTRO consolidado do treino (lido pela plataforma).

    Contém: origem (local/colab), datasets/arquivos treinados, épocas,
    melhor loss e data. Quando o usuário traz o modelo do Colab para cá,
    este arquivo vem junto e o dashboard lê para mostrar o que foi treinado
    (e se vale a pena treinar de novo localmente com outros arquivos).
    """
    try:
        import json as _json
        import os as _os
        datasets = {}
        total_arquivos = 0
        for a in arquivos:
            nome = _os.path.basename(a)
            ds = _os.path.basename(_os.path.normpath(_os.path.dirname(a))) or "dataset"
            datasets.setdefault(ds, []).append(nome)
            total_arquivos += 1
        # Nível do modelo (mesma fórmula do dashboard: loss → 0-100%)
        if best_val_loss <= 0.5:
            nivel_pct = 100
        elif best_val_loss >= 10.0:
            nivel_pct = 5
        else:
            nivel_pct = round(max(5, min(100, 100 - (best_val_loss - 0.5) / 9.5 * 100)))
        registro = {
            "origem": origem,               # 'local' ou 'colab'
            "data": datetime.now().isoformat(),
            "epochs": epoch,
            "best_val_loss": round(float(best_val_loss), 4),
            "nivel_modelo_pct": nivel_pct,
            "total_arquivos": total_arquivos,
            "datasets": {ds: {"arquivos": nomes, "quantidade": len(nomes)}
                         for ds, nomes in datasets.items()},
            "arquivos": arquivos,
        }
        treino.salvar_json(REGISTRO_TREINO_PATH, registro)
        log(f"📋 Registro de treino salvo em {REGISTRO_TREINO_PATH} "
            f"({total_arquivos} arquivo(s), {epoch} época(s))")
    except Exception as e:
        log(f"⚠️ Falha ao salvar registro de treino: {e}", "WARNING")


def _salvar_checkpoint_seguro(model, optimizer, scheduler, epoch,
                              best_val_loss, no_improve, total_batches) -> None:
    """Salva o checkpoint de retomada (com tratamento de erro)."""
    try:
        _salvar_torch_seguro({
            "epoch": epoch,
            "model_state_dict": model.state_dict(),
            "best_val_loss": best_val_loss,
            "no_improve": no_improve,
            "total_batches": total_batches,
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict() if scheduler else {},
        }, CHECKPOINT_PATH, "checkpoint seguro")
        log(f"💾 Checkpoint salvo em {CHECKPOINT_PATH}")
    except Exception as e:
        log(f"⚠️ Falha ao salvar checkpoint: {e}", "ERROR")


# ============================================================================
# 8b. FILA DE TREINAMENTO EM LOTE (batch) — um .jsonl por vez
# ============================================================================
# A fila NÃO altera o loop por época do `treinar()`: ela apenas o chama uma
# vez por arquivo, reutilizando TODA a lógica existente (dataset, validação,
# checkpoint, modelo_melhor). Entre arquivos o modelo é salvo e o estado da
# fila (estado_fila.json) é gravado — nada se perde se o PC cair.
#
#   Modos:
#     all   -> processa a fila até o fim
#     time  -> processa até o limite de tempo (termina o arquivo atual)
#     pause -> para ao detectar o arquivo de pausa (PAUSA_SEGURA.txt)


def _carregar_estado_fila(caminho: str) -> dict:
    """Lê o estado persistente da fila (para --resume)."""
    try:
        import json as _json
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                dados = _json.load(f)
            if isinstance(dados, dict):
                return dados
    except Exception:
        pass
    return {}


def _salvar_estado_fila(caminho: str, estado: dict) -> None:
    """Grava o estado da fila (arquivo_atual, indice, concluidos...)."""
    try:
        import json as _json
        os.makedirs(os.path.dirname(os.path.abspath(caminho)) or ".", exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            _json.dump(estado, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"⚠️ Falha ao salvar estado da fila: {e}", "WARNING")


def _atualizar_progresso_fila(args: argparse.Namespace, epoca: int,
                              total_epocas: int, passo: int, total_passos: int,
                              loss, lr) -> None:
    """Atualiza o progresso POR ÉPOCA no estado_fila.json (o dashboard mostra
    '80% da época 3'). Só age quando rodando em modo fila (args.em_fila)."""
    if not getattr(args, "em_fila", False):
        return
    try:
        estado = _carregar_estado_fila(args.estado_fila)
        if not estado:
            return
        estado["epoca_atual"] = epoca
        estado["total_epocas"] = total_epocas
        estado["progresso_porcent"] = round(100.0 * passo / max(1, total_passos), 1)
        estado["loss_atual"] = round(float(loss), 4) if loss is not None else None
        estado["lr_atual"] = lr
        estado["atualizado_em"] = datetime.now().isoformat()
        _salvar_estado_fila(args.estado_fila, estado)
    except Exception:
        pass


def _treinar_em_lote(args: argparse.Namespace) -> int:
    """Treina uma FILA de .jsonl, um por vez, com controle de tempo/pausa.

    Segurança:
      - Um arquivo por vez (SFTDataset só com esse arquivo) — RAM controlada.
      - modelo.pt/modelo_melhor.pt são salvos pelo treinar() ao fim de cada
        arquivo; aqui registramos cada conclusão no estado_fila.json.
      - --resume continua da fila: pula os concluídos e retoma o interrompido.
    """
    pasta = args.caminho_pasta or args.dados
    if not os.path.isdir(pasta):
        log(f"❌ Pasta da fila não encontrada: {pasta}", "ERROR")
        return 1

    arquivos = localizar_arquivos_jsonl(pasta)
    if not arquivos:
        log(f"❌ Nenhum .jsonl em '{pasta}'. Verifique o caminho.", "ERROR")
        return 1
    if args.max_arquivos:
        arquivos = arquivos[:args.max_arquivos]
    # Pula arquivos já treinados N ou mais vezes — exceto com --force
    if getattr(args, "force", False):
        log("⚡ --force ativo: treinando mesmo os arquivos já treinados.", "WARNING")
    elif getattr(args, "pular_treinados", 0) and args.pular_treinados > 0:
        arquivos, _pul = _filtrar_ja_treinados(arquivos, args.pular_treinados, pasta)
        if not arquivos:
            log("⏭️ Todos os arquivos já foram treinados o suficiente. Nada a treinar.", "WARNING")
            return 0
    total = len(arquivos)
    nomes_total = [os.path.basename(a) for a in arquivos]

    # Aliases de modo (usuário) -> modo interno do motor: arquivo/completo=all, tempo=time.
    _ALIASES_MODOS = {"arquivo": "all", "completo": "all", "tempo": "time"}
    modo = _ALIASES_MODOS.get(args.modo_fila, args.modo_fila or "all")
    limite_h = max(0.0, args.limite_tempo or 0.0)
    log(f"🎯 FILA DE TREINO | {total} arquivo(s) em '{pasta}' | modo: {modo}"
        + (f" | limite: {limite_h:.2f}h" if modo == "time" else ""))

    # Épocas por arquivo (default 5) — vale para TODOS os arquivos da fila.
    if getattr(args, "epocas_por_arquivo", 0) and args.epocas_por_arquivo > 0:
        args.epochs = args.epocas_por_arquivo
        log(f"🎯 {args.epocas_por_arquivo} época(s) por arquivo da fila.")
    # Sinais internos usados pelo treinar(): progresso por época no estado_fila
    # e reset explícito do LR ao iniciar cada arquivo (evita estagnação com LR=0).
    args.em_fila = True
    args.reiniciar_lr = True

    # Estado persistente (continuidade / --resume)
    estado = _carregar_estado_fila(args.estado_fila)
    concluidos = list(estado.get("arquivos_concluidos") or [])
    falharam = list(estado.get("arquivos_falharam") or [])
    alvo_resume = None
    if args.resume and estado.get("pasta") == pasta:
        log(f"↩️ Resume de fila: {len(concluidos)} concluído(s), "
            f"{len(falharam)} falhou(falharam).")
        atual = estado.get("arquivo_atual")
        if atual and atual not in concluidos and atual not in falharam \
                and atual in nomes_total:
            alvo_resume = atual
            log(f"↩️ Retomando o arquivo interrompido: {atual}")
    else:
        concluidos = []
        falharam = []

    inicio = time.time()
    resume_marcado = False
    estado.update({
        "versao": 1, "pasta": pasta, "modo": modo,
        "limite_tempo_horas": limite_h,
        "inicio": datetime.now().isoformat(),
        "status": "treinando",
        "arquivos_concluidos": concluidos,
        "arquivos_falharam": falharam,
    })
    if not args.resume:
        # Fila NOVA: zera indicadores (evita mostrar dados velhos de outra fila).
        estado["arquivo_atual"] = None
        estado["indice"] = 0
        estado["total"] = total
        estado["tempo_decorrido_seg"] = 0
    _salvar_estado_fila(args.estado_fila, estado)

    for i, arquivo in enumerate(arquivos, start=1):
        nome = os.path.basename(arquivo)
        if nome in concluidos or nome in falharam:
            continue  # já processado (resume)

        # Controle de TEMPO (modo time): termina o arquivo atual e para.
        if modo == "time" and limite_h > 0 \
                and (time.time() - inicio) / 3600 >= limite_h:
            log("⏰ Tempo limite atingido. Encerrando a fila "
                "(arquivo atual já foi salvo).", "WARNING")
            estado["status"] = "parado_tempo"
            _salvar_estado_fila(args.estado_fila, estado)
            break

        # Controle de PAUSA: se o marcador PAUSA_SEGURA.txt existir, a fila
        # termina o arquivo atual com segurança e pausa (qualquer modo — é o
        # botão ⏸️ Pausar do dashboard que cria esse marcador).
        if os.path.exists(args.pausa_arquivo):
            log("⏸️ PAUSA_SEGURA.txt detectado. Encerrando a fila "
                "(arquivo atual já foi salvo).", "WARNING")
            estado["status"] = "pausado"
            _salvar_estado_fila(args.estado_fila, estado)
            break

        # Estado: arquivo atual sendo treinado
        estado["arquivo_atual"] = nome
        estado["indice"] = i - 1
        estado["total"] = total
        estado["tempo_decorrido_seg"] = int(time.time() - inicio)
        estado["status"] = "treinando"
        estado["atualizado_em"] = datetime.now().isoformat()
        _salvar_estado_fila(args.estado_fila, estado)

        log(f"\n{'=' * 80}\n📌 FILA {i}/{total} — treinando: {nome}\n{'=' * 80}")

        # Treina APENAS este arquivo (reusa toda a lógica existente).
        args.arquivo = arquivo
        args.dados = pasta
        args.no_interactive = True
        # --resume só para o arquivo interrompido (continua do checkpoint).
        args.resume = (alvo_resume is not None and nome == alvo_resume
                       and not resume_marcado)
        if args.resume:
            resume_marcado = True

        try:
            treinar(args)
        except KeyboardInterrupt:
            log("⏹️ Fila interrompida (Ctrl+C). Estado salvo — "
                "rode de novo com --resume para continuar.", "WARNING")
            estado["status"] = "pausado"
            estado["tempo_decorrido_seg"] = int(time.time() - inicio)
            _salvar_estado_fila(args.estado_fila, estado)
            return 0
        except SystemExit as e:
            # Arquivo com erro (ex.: jsonl inválido): registra e segue.
            falharam.append(nome)
            estado["arquivos_falharam"] = falharam
            _salvar_estado_fila(args.estado_fila, estado)
            log(f"❌ FILA {i}/{total} FALHOU: {nome} (código {e.code}). Seguindo...",
                "ERROR")
            continue

        # Arquivo concluído: registra e salva estado.
        if nome not in concluidos:
            concluidos.append(nome)
        estado["arquivos_concluidos"] = concluidos
        estado["indice"] = i
        estado["tempo_decorrido_seg"] = int(time.time() - inicio)
        estado["atualizado_em"] = datetime.now().isoformat()
        _salvar_estado_fila(args.estado_fila, estado)
        log(f"✅ FILA {i}/{total} concluído: {nome}")

    # Fim da fila
    estado["status"] = "concluido" if len(concluidos) >= total \
        else estado.get("status", "concluido")
    estado["tempo_decorrido_seg"] = int(time.time() - inicio)
    estado["fim"] = datetime.now().isoformat()
    _salvar_estado_fila(args.estado_fila, estado)
    log(f"\n🏁 FILA FINALIZADA — {len(concluidos)}/{total} arquivos | "
        f"tempo total: {(time.time() - inicio) / 60:.1f} min")
    return 0


# ============================================================================
# 9. FUNÇÃO PRINCIPAL
# ============================================================================
def main() -> None:
    # ── Guardião de cabeçalhos (oculto + criptografado): execução implícita ──
    try:
        import os as _os
        _g = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".rigel_guard.py")
        if _os.path.exists(_g):
            with open(_g, "r", encoding="utf-8") as _f:
                exec(compile(_f.read(), _g, "exec"), {"__file__": _g, "__name__": "__rigel_guard__"})
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Treino SFT do RigelSLM com datasets JSONL "
                    "(formato messages, loss apenas no assistant)")
    parser.add_argument("--dados", type=str, default=treino.PASTA_PROCESSED,
                        help=f"Pasta com .jsonl (default: {treino.PASTA_PROCESSED}; "
                             "cai para dados/gerados/jsonl se vazia)")
    parser.add_argument("--modelo", type=str, default=None,
                        help="Pesos base .pt (default automático: "
                             "checkpoint_jsonl.pt > modelo_melhor.pt > modelo.pt)")
    parser.add_argument("--epochs", type=int, default=SFT_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=treino.BATCH_SIZE)
    parser.add_argument("--seq-len", type=int, default=treino.SEQ_LEN)
    parser.add_argument("--accum", type=int, default=SFT_GRADIENT_ACCUMULATION,
                        help="Acumulação de gradiente")
    parser.add_argument("--lr", type=float, default=SFT_LEARNING_RATE)
    parser.add_argument("--weight-decay", type=float, default=treino.WEIGHT_DECAY)
    parser.add_argument("--label-smoothing", type=float, default=SFT_LABEL_SMOOTHING)
    parser.add_argument("--max-arquivos", type=int, default=None,
                        help="Limite de arquivos JSONL a usar")
    parser.add_argument("--arquivo", type=str, default=None,
                        help="Treina apenas um arquivo específico (nome ou caminho)")
    parser.add_argument("--max-exemplos", type=int, default=MAX_EXEMPLOS_PADRAO,
                        help="Limite máximo de exemplos")
    parser.add_argument("--val-split", type=float, default=0.1,
                        help="Fração para validação (default: 0.1)")
    parser.add_argument("--val-batches", type=int, default=VAL_BATCHES_LIMIT)
    parser.add_argument("--no-validar", action="store_true",
                        help="Desativa a validação")
    parser.add_argument("--early-stop-patience", type=int, default=treino.PATIENCE)
    parser.add_argument("--resume", action="store_true",
                        help="Retoma do checkpoint_jsonl.pt")
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument("--threads", type=int, default=None,
                        help="Núcleos/threads a usar (default: automático com margem)")
    parser.add_argument("--save-every", type=int, default=50,
                        help="Salva checkpoint a cada N batches")
    parser.add_argument("--precision", type=str, default="amp",
                        choices=["fp32", "fp16", "amp"])
    parser.add_argument("--incluir-system", action="store_true", default=True,
                        help="Inclui o system prompt como contexto (loss fica "
                             "só no assistant). Use --no-incluir-system para "
                             "treinar sem o system.")
    parser.add_argument("--no-incluir-system", dest="incluir_system",
                        action="store_false")
    parser.add_argument("--no-interactive", action="store_true",
                        help="Pula o menu interativo de pastas")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--origem", type=str, default="local",
                        choices=["local", "colab"],
                        help="Onde o treino acontece — grava no registro "
                             "(default: local; use --origem colab no Colab)")
    parser.add_argument("--sem-carteira", action="store_true",
                        help="💉 Ignora a CARTEIRA DE QUALIDADE (não avisa "
                             "se o material está cru). Só para testes!")
    parser.add_argument("--usar-registro", action="store_true",
                        help="Usa as pastas registradas (tipo jsonl) em vez de "
                             "escanear o acervo — vai direto às pastas")
    # --- Fila de treinamento em lote (um .jsonl por vez) ---
    parser.add_argument("--modo-fila", type=str, default="arquivo",
                        choices=["all", "time", "pause", "completo", "tempo", "arquivo"],
                        help="Modo da fila: 'arquivo' (padrão, até o fim), 'tempo' (limite "
                             "de tempo em horas), 'pause' (para ao achar PAUSA_SEGURA.txt). "
                             "Aliases: completo=all, tempo=time.")
    parser.add_argument("--epocas-por-arquivo", type=int, default=5,
                        help="Épocas treinadas em CADA arquivo da fila (default: 5)")
    parser.add_argument("--limite-tempo", type=float, default=0.0,
                        help="Limite de tempo em HORAS para o modo 'time' (ex.: 8)")
    parser.add_argument("--caminho-pasta", type=str, default=None,
                        help="Pasta cheia de .jsonl para treinar em FILA (um por vez)")
    parser.add_argument("--estado-fila", type=str, default="modelo/estado_fila.json",
                        help="Onde guardar o estado da fila (resume)")
    parser.add_argument("--pausa-arquivo", type=str, default="PAUSA_SEGURA.txt",
                        help="Arquivo de sinal de pausa (modo 'pause')")
    parser.add_argument("--pular-treinados", type=int, default=0,
                        help="Pula arquivos JÁ treinados N ou mais vezes "
                             "(lê modelo/jsonlogs/<dataset>.json; 0 = não pula)")
    parser.add_argument("--force", action="store_true",
                        help="Ignora a regra de 'já treinado' e treina TODOS os arquivos")
    args = parser.parse_args()

    if args.epochs <= 0:
        parser.error("--epochs deve ser maior que 0")
    if not (0.0 <= args.lr <= 1.0):
        parser.error("--lr deve estar entre 0.0 e 1.0")
    if not (0.0 < args.val_split < 1.0):
        parser.error("--val-split deve estar entre 0.0 e 1.0")
    if args.seq_len <= 0:
        parser.error("--seq-len deve ser maior que 0")

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    args.validar = not args.no_validar
    if args.caminho_pasta:
        # Modo FILA: vários arquivos .jsonl, um por vez.
        sys.exit(_treinar_em_lote(args))
    treinar(args)


if __name__ == "__main__":
    main()
