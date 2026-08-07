# 📋 Changelog do RigelSLM

Todos os cambios notáveis neste projeto serão documentados neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/), e o projeto segue [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## [1.0.0] - 2026-07-31

### 🚀 Adicionado
- **Reinício da numeração de versões** do projeto para **1.0.0**.
- Todos os cabeçalhos dos scripts atualizados para `Versão: 1.0.0 | Data: 31/07/2026`.
- Histórico de versões com incrementos planejados no `README.md` (1.0.1, 1.0.2, ...).

---

## [6.5.1] - 2026-07-30

### 🚀 Adicionado
- **Detecção automática GPU/CPU no `treino.py` e `treinov2.py`**
  - `BATCH_SIZE`: 16 (GPU) / 4 (CPU)
  - `GRADIENT_ACCUMULATION`: 2 (GPU) / 4 (CPU)
  - `LEARNING_RATE`: 5e-4 (GPU) / 3e-4 (CPU)
  - `num_workers`: até 8 (GPU) / 1-4 (CPU)
  - `torch.set_num_threads`: CPU total (GPU) / CPU-1 (CPU)
- **`converter_para_gguf.py` v4.0** — estrutura de tensores compatível com Ollama 0.32.5+
  - 75 tensores estilo Llama (sem biases)
  - `output_norm.weight` adicionado como identidade
  - `ffn_up.weight` copiado de `ffn_gate` (modelo usa GELU, não SwiGLU)
  - Merges do tokenizer serializados como STRING única (não ARRAY)
  - Embedding e Output mantidos sem transposição
- **Pasta `dados/descartados`** criada (separada de `dados/gerados/`)

### 🔧 Corrigido
- **Ollama atualizado** de 0.20.7 → 0.32.5 (necessário para suporte a arrays GGUF)
- **GGUF convertido com sucesso** para rodar no Ollama (`ollama ps` confirma modelo ativo)
- **Chat funciona** tanto via `chat.py` (PyTorch direto) quanto `ollama run rigelslm`

### 📚 Documentação
- README.md atualizado com seção detalhada de problemas e soluções GGUF/Ollama
- Instruções de conversão GGUF e uso no Ollama adicionadas ao README

## [6.4.4] - 2026-07-15

### 🚀 Adicionado
- **Backup Inteligente de Checkpoints**
  - Checkpoints agora são salvos com nome único: `checkpoint_epXX_batchXXXXX.pt`
  - Checkpoint ao final de cada época: `checkpoint_epXX_final.pt`
  - Mantém automaticamente os **5 checkpoints mais recentes** (limpeza automática)
  - O checkpoint padrão (`checkpoint.pt`) continua sendo atualizado para compatibilidade com `--resume`
- **Instrução de recuperação** adicionada no cabeçalho do `treino.py`
  - Se `checkpoint.pt` corromper, use `ln -sf` para substituir por um checkpoint nomeado

### 🔧 Corrigido
- **DataLoader**: `num_workers=1` e `timeout=0` para evitar workers mortos no Colab
- **Multiprocessing**: `multiprocessing_context='fork'` para compatibilidade com o Colab
- **Exceções no dataset**: agora são capturadas para não derrubar o worker
- **Apenas a pasta passada em `--dados` é usada** (ignora `PASTAS_ADICIONAIS`)

### 📚 Documentação
- Cabeçalho do `treino.py` atualizado com instruções de recuperação de checkpoint
- README atualizado com informações sobre o novo sistema de checkpoints

---

## [6.4.3] - 2026-07-14

### 🔧 Corrigido
- **DataLoader**: `num_workers=2` → `num_workers=1` (evita conflitos no Colab)
- **AMP**: `torch.cuda.amp.GradScaler` → `torch.amp.GradScaler('cuda')` (corrige FutureWarning)
- **autocast**: `torch.cuda.amp.autocast` → `torch.amp.autocast('cuda')` (corrige FutureWarning)
- **Timeout do Drive**: uso de `--max-arquivos` como padrão (5000) para evitar timeouts

### 📚 Documentação
- Versão do script atualizada para v6.4.3

---

## [6.4.2] - 2026-07-14

### 🔧 Corrigido
- **DataLoader**: `num_workers=2` (evita sobrecarga da CPU no Colab)
- **AMP**: `GradScaler('cuda')` e `autocast('cuda')` para compatibilidade com PyTorch 2.11+
- **Apenas a pasta passada em `--dados` é usada** (ignora `PASTAS_ADICIONAIS`)
- **Checkpoint**: mensagem de erro melhorada para checkpoint corrompido

### 🚀 Melhorado
- **Performance**: `torch.set_num_threads(min(2, cpu_count))` para evitar sobrecarga

---

## [6.4.1] - 2026-07-13

### 🚀 Adicionado
- **Suporte a AMP (mixed precision)** para acelerar o treino na Tesla T4
- **Parâmetros ajustáveis via argparse**: `--num-workers`, `--save-every`, `--precision`
- **Log automático de uso de GPU** via `nvidia-smi`
- **Tratamento de OOM** com redução dinâmica de batch
- **Scheduler com warmup e decay** mais suave
- **Early stopping configurável** via `--early-stop-patience`

### 🔧 Corrigido
- `PATIENCE` não era declarado como global → corrigido
- `GRADIENT_ACCUMULATION` padrão reduzido de 4 para 2 (batch efetivo = 16 * 2 = 32)

---

## [6.4.0] - 2026-07-12

### 🚀 Adicionado
- **Aumento de batch_size padrão** de 8 para 16 (melhor uso da GPU T4)
- **Aumento de seq_len padrão** de 512 para 1024 (experimental, depois revertido)
- **Suporte a múltiplas pastas de dados** (43 pastas configuradas)
- **Resume automático** com `--resume`

### 🔧 Corrigido
- **Timeout do Google Drive** ao listar muitas pastas
- **Erro de `UnboundLocalError`** no `PATIENCE`

---

## [6.3.0] - 2026-07-10

### 🚀 Adicionado
- **Suporte a múltiplos formatos**: TXT, PDF, HTML, XML, CSV, JSONL
- **Auto-recuperação** de treino com checkpoint
- **Tokenizer BPE** treinado a partir dos dados
- **StreamingDataset** para lidar com grandes volumes de dados

### 📚 Documentação
- README.md criado com visão geral do projeto

---

## [1.0.0] - 2026-07-01

### 🚀 Lançamento inicial
- Arquitetura Transformer decoder (8 layers, 8 heads, 512 embed)
- Vocabulário de 23.830 tokens (BPE)
- Treino com `batch_size=8`, `seq_len=512`, `gradient_accumulation=4`
- Suporte a CPU e GPU (CUDA)
- Geração de texto com temperatura, top-k e repetition penalty

---

## 📊 Visão Geral do Projeto

### Arquitetura do Modelo

| Parâmetro | Valor |
|-----------|-------|
| `VOCAB_SIZE` | 23.830 (auto-detectado) |
| `EMBED_DIM` | 512 |
| `NUM_LAYERS` | 8 |
| `NUM_HEADS` | 8 |
| `FF_DIM` | 2048 |
| `DROPOUT` | 0.15 |
| `SEQ_LEN` | 512 |
| **Parâmetros totais** | ~58M |

### Funcionalidades Principais

| Funcionalidade | Arquivo | Descrição |
|----------------|---------|-----------|
| **Treino** | `treino.py` | Pipeline completo com auto-recuperação, checkpointing e AMP |
| **Chat** | `chat.py` | Interação com o modelo treinado (modo conversa e one-shot) |
| **Dashboard** | `app.py` (Gradio) | Interface web para testar o modelo (porta 8001) |
| **GGUF** | `converter_para_gguf.py` | Conversão para formato GGUF (Ollama, llama.cpp, LM Studio) |
| **Dados Sintéticos** | `dialogos.py` / `dialogos2.py` | Geração de dados com DeepSeek ou Ollama |
| **RSS** | `rss_processor.py` | Coleta de notícias e artigos de feeds RSS |
| **Agrupamento** | `agrupar.py` | Agrupa arquivos pequenos em lotes para evitar timeout do Drive |

### Comandos Úteis

```bash
# Treinar o modelo (usando a pasta de lotes)
python treino.py --dados dados/processed_lotes --resume --save-every 50

# Chat interativo
python chat.py --temperature 0.8 --max-tokens 200

# Converter para GGUF (escolha a quantização)
python converter_para_gguf.py

# Agrupar arquivos em lotes (executar localmente)
python agrupar.py --entrada dados/processed --saida dados/processed_lotes --pares 500

# Dashboard Gradio
python app.py
