import os
import re
import torch
import torch.nn as nn
import xml.etree.ElementTree as ET
import random
from tokenizers import Tokenizer, models, trainers, pre_tokenizers, normalizers
from datetime import datetime, timedelta

# ==============================
# CONFIGURAÇÕES
# ==============================

PASTA_DADOS = "dados"
TOKENIZER_PATH = "tokenizer/tokenizer.json"
MODEL_PATH = "modelo/modelo.pt"
LOG_PATH = "logs/treino.log"

EPOCHS = 2
SEQ_LEN = 32
VOCAB_SIZE = 20000
EMBED_DIM = 128
CHECKPOINT_INTERVAL = 1  # salva a cada batch
LOG_INTERVAL = 1000      # loga o progresso a cada 1000 batches para não poluir demais
ROLLING_CHECKPOINT = "modelo/modelo_last.pt"

# ==============================
# PASTAS
# ==============================

os.makedirs("tokenizer", exist_ok=True)
os.makedirs("modelo", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# ==============================
# LOG
# ==============================

def log(msg):
    print(msg)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

# ==============================
# XML
# ==============================

def ler_xml(caminho):
    try:
        tree = ET.parse(caminho)
        root = tree.getroot()

        textos = []
        for elem in root.iter():
            if elem.text:
                t = elem.text.strip()
                if len(t) > 30:
                    textos.append(t)

        return "\n".join(textos)

    except Exception as e:
        log(f"❌ Erro XML: {e}")
        return ""

# ==============================
# TOKENIZER
# ==============================

def criar_tokenizer():
    log("🔧 Criando tokenizer...")

    arquivos = [
        os.path.join(PASTA_DADOS, f)
        for f in os.listdir(PASTA_DADOS)
        if f.endswith((".txt", ".xml"))
    ]

    if not arquivos:
        log("❌ Sem arquivos de dados no diretório")
        return

    total_arquivos = len(arquivos)
    textos = []
    tamanho_total = 0

    for idx, arq in enumerate(arquivos, start=1):
        log(f"  [{idx}/{total_arquivos}] Lendo {os.path.basename(arq)}")

        if arq.endswith(".xml"):
            texto = ler_xml(arq)
        else:
            with open(arq, encoding="utf-8") as f:
                texto = f.read()

        tamanho_total += len(texto)
        if len(texto) > 100:
            textos.append(texto)

    if not textos:
        log("❌ Sem dados válidos para treino")
        return

    log(f"📦 Arquivos processados: {len(textos)}/{total_arquivos} com texto útil")
    log(f"📄 Tamanho total aproximado do texto: {tamanho_total:,} caracteres")

    temp = os.path.join(PASTA_DADOS, "_temp.txt")

    # write cleaned texts to temp file (normalize whitespace and remove control chars)
    with open(temp, "w", encoding="utf-8") as f:
        for idx, texto in enumerate(textos, start=1):
            # simple cleaning
            txt = re.sub(r"[\x00-\x1F\x7F]", " ", texto)
            txt = re.sub(r"\s+", " ", txt).strip()
            f.write(txt)
            if idx < len(textos):
                f.write("\n")

    tokenizer = Tokenizer(models.BPE(unk_token="[UNK]"))
    # normalize unicode to NFKC
    tokenizer.normalizer = normalizers.NFKC()
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()

    trainer = trainers.BpeTrainer(
        vocab_size=VOCAB_SIZE,
        min_frequency=2,
        special_tokens=["[UNK]", "[PAD]"],
        show_progress=True
    )

    log("⏳ Iniciando treinamento do tokenizer (BPE). Isso pode demorar alguns minutos...")
    tokenizer.train([temp], trainer)
    try:
        vocab_size_actual = tokenizer.get_vocab_size()
    except Exception:
        vocab_size_actual = VOCAB_SIZE
    tokenizer.save(TOKENIZER_PATH)

    os.remove(temp)

    log(f"✅ Tokenizer criado (vocab aprox.: {vocab_size_actual})")

# ==============================
# MODELO
# ==============================

class MiniGPT(nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding = nn.Embedding(VOCAB_SIZE, EMBED_DIM)
        self.linear = nn.Linear(EMBED_DIM, VOCAB_SIZE)

    def forward(self, x):
        return self.linear(self.embedding(x))

# ==============================
# GERAR BATCHES (MELHORADO)
# ==============================

def gerar_batches(tokens):
    indices = list(range(0, len(tokens) - SEQ_LEN))
    random.shuffle(indices)

    for i in indices:
        x = tokens[i:i+SEQ_LEN]
        y = tokens[i+1:i+SEQ_LEN+1]
        yield torch.tensor(x), torch.tensor(y)

# ==============================
# TREINO
# ==============================

def treinar():

    log(f"\n=== INÍCIO {datetime.now()} ===\n")

    if not os.path.exists(TOKENIZER_PATH):
        criar_tokenizer()
    else:
        log("Tokenizer carregado")

    tokenizer = Tokenizer.from_file(TOKENIZER_PATH)

    model = MiniGPT()

    if os.path.exists(MODEL_PATH):
        log("📦 Carregando modelo")
        checkpoint = torch.load(MODEL_PATH)
        try:
            model.load_state_dict(checkpoint)
            log("Checkpoint carregado com sucesso (shapes compatíveis).")
        except RuntimeError as e:
            log(f"Aviso: checkpoint incompatível — adaptando pesos parcialmente: {e}")
            new_state = model.state_dict()
            old_state = checkpoint
            for name, old_param in old_state.items():
                if name not in new_state:
                    continue
                new_param = new_state[name]
                try:
                    if old_param.shape == new_param.shape:
                        new_state[name] = old_param
                    else:
                        if old_param.ndim == 2 and new_param.ndim == 2:
                            r = min(old_param.shape[0], new_param.shape[0])
                            c = min(old_param.shape[1], new_param.shape[1])
                            tmp = new_param.clone()
                            tmp[:r, :c] = old_param[:r, :c]
                            new_state[name] = tmp
                        elif old_param.ndim == 1 and new_param.ndim == 1:
                            r = min(old_param.shape[0], new_param.shape[0])
                            tmp = new_param.clone()
                            tmp[:r] = old_param[:r]
                            new_state[name] = tmp
                        else:
                            log(f"  Não foi possível adaptar {name} (shapes {old_param.shape} -> {new_param.shape})")
                except Exception as ex:
                    log(f"  Erro ao adaptar {name}: {ex}")

            model.load_state_dict(new_state)
            log("Checkpoint adaptado e carregado (parte dos pesos reutilizados).")
    else:
        log("🆕 Novo modelo")

    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_fn = nn.CrossEntropyLoss()

    # 🔴 NOVO: junta TODOS os textos
    textos = []

    for nome in os.listdir(PASTA_DADOS):
        caminho = os.path.join(PASTA_DADOS, nome)

        if nome.endswith(".xml"):
            texto = ler_xml(caminho)
        elif nome.endswith(".txt"):
            with open(caminho, encoding="utf-8") as f:
                texto = f.read()
        else:
            continue

        if len(texto) > 100:
            textos.append(texto)

    if not textos:
        log("❌ Sem dados para treino")
        return

    # 🔴 mistura tudo
    random.shuffle(textos)
    texto_total = "\n".join(textos)

    tokens = tokenizer.encode(texto_total).ids

    log(f"Total tokens: {len(tokens)}")

    for epoch in range(EPOCHS):

        total_loss = 0
        steps = 0
        num_batches = max(1, len(tokens) - SEQ_LEN)
        epoch_start_time = datetime.now()

        log(f"🚀 Epoch {epoch+1}/{EPOCHS} iniciada ({num_batches} batches previstos)")
        log(f"   ⏰ Início: {epoch_start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        model_size_bytes = sum(param.numel() * param.element_size() for param in model.parameters())
        model_size_mb = model_size_bytes / (1024 ** 2)
        log(f"📦 Tamanho do modelo: {model_size_mb:.2f} MB")

        for step, (x, y) in enumerate(gerar_batches(tokens), start=1):

            optimizer.zero_grad()

            output = model(x)

            loss = loss_fn(output.view(-1, VOCAB_SIZE), y.view(-1))

            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            steps += 1

            if step % LOG_INTERVAL == 0 or step == num_batches:
                pct = step / num_batches * 100
                log(f"    batch {step}/{num_batches} ({pct:.1f}%) | loss atual: {loss.item():.4f}")

            # checkpoint contínuo a cada batch
            if step % CHECKPOINT_INTERVAL == 0 or step == num_batches:
                checkpoint_path = ROLLING_CHECKPOINT
                torch.save(model.state_dict(), checkpoint_path)
                log(f"💾 Checkpoint atualizado: {checkpoint_path} (batch {step})")

        media = total_loss / steps
        log(f"✅ Epoch {epoch+1}/{EPOCHS} concluída | Loss média: {media:.4f}")

    final_model_path = MODEL_PATH
    torch.save(model.state_dict(), final_model_path)
    log(f"💾 Modelo final salvo: {final_model_path}")

    # ===== GERAÇÃO DE AMOSTRAS AUTOMÁTICA (avaliação rápida) =====
    try:
        log("🔎 Gerando amostras de teste...")

        def gerar_texto(prompt, max_tokens=40):
            ids = tokenizer.encode(prompt).ids
            tokens = torch.tensor(ids, dtype=torch.long)
            for _ in range(max_tokens):
                with torch.no_grad():
                    out = model(tokens)
                next_id = int(torch.argmax(out[-1]).item())
                tokens = torch.cat([tokens, torch.tensor([next_id], dtype=torch.long)])
            return tokenizer.decode(tokens.tolist())

        exemplos = [
            "Hoje eu fui ao parque e",
            "O melhor cuidado para um cachorro é",
            "Como cuidar do pelo do meu pet:",
            "Dicas para alimentar um filhote:",
            "Rotina de banho para cães de pelo longo:",
            "Quais vacinas um cão adulto precisa?"
        ]

        amostras_path = os.path.join('logs', 'samples.txt')
        with open(amostras_path, 'a', encoding='utf-8') as sf:
            sf.write(f"=== Amostras geradas em {datetime.now()} ===\n")
            for ex in exemplos:
                resultado = gerar_texto(ex, max_tokens=60)
                cont = resultado.replace(ex, '').strip()
                log(f"Prompt: {ex}")
                log(f"Geração: {cont}\n")
                sf.write(f"Prompt: {ex}\n")
                sf.write(f"Geração: {cont}\n\n")
            sf.write('\n')

    except Exception as e:
        log(f"❌ Erro ao gerar amostras: {e}")

    log("\n=== FINALIZADO ===\n")

# ==============================
# EXECUTAR
# ==============================

if __name__ == "__main__":
    treinar()