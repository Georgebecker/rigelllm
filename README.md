# ⭐ RigelSLM – Small Language Model para Português Brasileiro

**Versão:** 3.1  
**Autor:** George Herman Becker  
**Licença:** MIT  
**Última atualização:** Julho de 2026

---

## 📖 O que é o RigelSLM?

RigelSLM é um **modelo de linguagem pequeno (SLM)** treinado do zero com foco exclusivo no **português do Brasil**. Possui aproximadamente **66 milhões de parâmetros**, sendo leve o suficiente para rodar em CPUs convencionais sem GPU.

O projeto nasceu da necessidade de ter um modelo que entenda a **cultura brasileira**, expressões regionais, história e geografia do país — algo que modelos grandes frequentemente ignoram ou tratam de forma genérica.

O nome **Rigel** vem da estrela mais brilhante da constelação de Órion.  
**SLM** significa *Small Language Model*.

---

## 🧠 Arquitetura do Modelo

| Parâmetro | Valor |
|-----------|-------|
| `VOCAB_SIZE` | **23830** (auto-detectado do tokenizer) |
| `EMBED_DIM` | 512 |
| `NUM_LAYERS` | 8 (decoder Transformer) |
| `NUM_HEADS` | 8 |
| `FF_DIM` | 2048 |
| `DROPOUT` | 0.15 |
| `SEQ_LEN` | 512 |
| `BATCH_SIZE` | 8 |
| `GRADIENT_ACCUMULATION` | 4 (batch efetivo = 32) |
| `EPOCHS` | 20 (configurável) |
| **Parâmetros totais** | ~66,4M |
| **Tamanho do checkpoint** | ~254 MB (FP32) |

### Tokens Especiais

| Token | ID | Função |
|-------|----|--------|
| `[PAD]` | 0 | Preenchimento |
| `[UNK]` | 1 | Desconhecido |
| `[BOS]` | 2 | Início da sequência |
| `[EOS]` | 3 | Fim da sequência |
| `[SEP]` | 4 | Separador de turnos |

---

## � Estrutura do Projeto

```
C:\Rigelllm\
├── dashboard/           # Interface web (FastAPI + Tailwind + Alpine.js)
│   ├── main.py          # App FastAPI, rotas principais, status do sistema
│   ├── routes/          # Rotas organizadas por funcionalidade
│   │   ├── train.py     # Treino: iniciar, parar, progresso, logs
│   │   ├── chat.py      # Chat: Ollama + Modo Local PyTorch
│   │   ├── rss.py       # RSS: processar feeds, testar, adicionar
│   │   ├── convert.py   # GGUF: conversão de .pt para GGUF
│   │   ├── generate.py  # Dados: gerar diálogos, executar scripts
│   │   ├── logs.py      # Logs: listar, visualizar, métricas
│   │   ├── diagnostico.py # Diagnóstico: contagem real de arquivos
│   │   └── ollama.py    # Ollama: status e reinicialização
│   ├── services/        # Serviços auxiliares
│   │   ├── runner.py    # Execução de scripts em background com log
│   │   └── monitor.py   # Monitoramento do sistema (CPU, RAM, disco)
│   ├── templates/       # Templates HTML (Alpine.js)
│   │   └── index.html   # Dashboard completo (SPA)
│   └── static/          # CSS e assets
├── modelo/              # Checkpoints do modelo (.pt)
│   ├── modelo_melhor.pt # Melhor modelo (val_loss mínimo)
│   ├── modelo.pt        # Último checkpoint
│   └── checkpoint.pt    # Checkpoint intermediário
├── tokenizer/
│   └── tokenizer.json   # Tokenizer BPE treinado
├── dados/
│   ├── processed/       # Dados processados para treino (2.16M+ arquivos)
│   ├── gerados/         # Dados sintéticos gerados
│   └── raw/             # Dados brutos (fonte original)
├── logs/                # Logs do sistema
├── gguf/                # Modelos convertidos para GGUF
├── treino.py            # Treino do modelo (arquitetura + pipeline)
├── chat.py              # Chat interativo (modo conversa e one-shot)
├── dialogos.py          # Geração de dados sintéticos v1 (DeepSeek)
├── dialogos2.py         # Geração de dados sintéticos v2 (22 tipos)
├── preparar_dados.py    # Qualificação e preparação dos dados
├── converter_para_gguf.py# Conversão .pt → GGUF
├── rss_processor.py     # Coleta de notícias via RSS
├── agrupar.py           # Agrupa arquivos pequenos em lotes
├── downdata.py          # Download de datasets públicos
├── download_datasets.py # Download alternativo de datasets
├── ultra.py             # Ultra-processamento de dados
├── limpeza.py           # Limpeza e remoção de ruídos
├── tradutor.py          # Tradução de textos
├── traduza.py           # Tradução alternativa
├── validation.py        # Validação de dados gerados
├── generation.py        # Geração de texto auxiliar
├── config.py            # Configurações centralizadas
├── state.py             # Gerenciamento de estado
├── categories.py        # Categorias de dados
├── utils.py             # Utilitários gerais
├── app.py               # Aplicativo principal (legado)
├── main.py              # Ponto de entrada (legado)
└── requirements.txt     # Dependências Python

---

## 📜 Descrição dos Arquivos .py

### 🧠 Modelo e Treino

| Arquivo | Descrição |
|---------|-----------|
| `treino.py` | **Arquivo principal.** Define a arquitetura `RigelSLM` (Transformer decoder), carregamento de dados, pipeline de treino com auto-recuperação, checkpointing, salvamento do melhor modelo e geração de texto. Suporta TXT, PDF, HTML, XML, CSV, JSONL. |
| `chat.py` | **Chat interativo.** Carrega o modelo treinado e permite conversar. Modo interativo com histórico (últimas 3 trocas) e modo `--one-shot` para integração com o dashboard. Parâmetros: temperatura, top-k, repetition penalty. |
| `converter_para_gguf.py` | Converte o checkpoint `.pt` para o formato GGUF (compatível com Ollama, llama.cpp, LM Studio). Suporta quantizações: F16, Q8_0, Q4_K, Q5_K. |

### 📊 Dados Sintéticos

| Arquivo | Descrição |
|---------|-----------|
| `dialogos.py` | Geração de dados sintéticos via API DeepSeek (v1). Gera pares pergunta-resposta sobre cultura brasileira. |
| `dialogos2.py` | Geração de dados sintéticos (v2) com **22 tipos** de conteúdo: conversa, artigo, conto, poema, carta, entrevista, debate, tutorial, resenha, relatório, ensaio, crônica, receita, dica, auto, etc. Usa DeepSeek ou Ollama. |
| `preparar_dados.py` | Prepara e qualifica dados brutos para o formato de treino. Remove ruídos, padroniza codificação UTF-8. |
| `rss_processor.py` | Coleta notícias e artigos de feeds RSS. Alimenta o modelo com conteúdo jornalístico atualizado. |
| `agrupar.py` | Agrupa arquivos pequenos em lotes maiores para processamento mais eficiente. |
| `downdata.py` | Download de datasets públicos da internet. |
| `download_datasets.py` | Método alternativo de download de datasets. |
| `ultra.py` | Ultra-processamento: sharding, checkpointing e otimização de datasets grandes. |
| `limpeza.py` | Limpeza de dados: remove duplicatas, corrige encoding, elimina ruídos. |
| `validation.py` | Validação de dados gerados (qualidade, formato, consistência). |

### 🔧 Utilitários

| Arquivo | Descrição |
|---------|-----------|
| `config.py` | Configurações centralizadas do projeto. |
| `state.py` | Gerenciamento de estado entre execuções. |
| `categories.py` | Definição das categorias de dados. |
| `utils.py` | Funções utilitárias gerais. |
| `generation.py` | Funções auxiliares de geração de texto. |
| `tradutor.py` | Tradução de textos para português. |
| `traduza.py` | Método alternativo de tradução. |
| `app.py` | Aplicativo principal (versão legada). |
| `main.py` | Ponto de entrada (versão legada). |
# Conversão automática (busca o melhor modelo)
python converter_para_gguf.py

# Especificando modelo e quantização
python converter_para_gguf.py --model modelo/modelo_melhor.pt --quant Q4_K_M
Quantizações disponíveis: F16, Q8_0, Q4_K_M, Q5_K_M.

Saída: Arquivo .gguf em gguf/ e modelo_info.json com metadados.

4. Chat Interativo (chat.py)
O que faz: Interface de chat para testar o modelo treinado, com histórico de conversa e parâmetros ajustáveis.

Comando:

bash
python chat.py --temperature 0.8 --max-tokens 200
Comandos dentro do chat:

/clear – Limpa o histórico.

/exit ou sair – Sai do programa.

/help – Mostra ajuda.

## 🖥️ Dashboard (Interface Web)

O dashboard é uma **SPA (Single Page Application)** construída com:

- **Backend:** FastAPI + Uvicorn (porta 8000)
- **Frontend:** Tailwind CSS + Alpine.js (client-side reativo)
- **Monitoramento:** psutil (CPU por núcleo, RAM, disco)

### Funcionalidades

| Aba | Função |
|-----|--------|
| **Dashboard** | Visão geral: status do modelo, CPU, RAM, disco, arquivos processados, log ao vivo, últimas épocas de treino |
| **Treinamento** | Iniciar/parar treino, selecionar pastas de dados, progresso em tempo real, log |
| **Chat** | Conversar com o modelo via Ollama **ou** Modo Local (PyTorch direto). Salvar conversas, feedback, teste |
| **RSS & Web** | Processar feeds RSS, testar URLs, adicionar novos feeds, estatísticas |
| **Converter GGUF** | Converter modelo .pt para GGUF com quantização |
| **Gerar Dados** | Gerar dados sintéticos (v1, v2), download de datasets, executar scripts |
| **Logs** | Visualizar todos os logs do sistema em tempo real |

### 🔄 Modo Local (PyTorch sem Ollama)

O dashboard agora suporta **dois modos** de chat:

1. **Ollama** (requer `ollama serve` rodando) — usa GGUF carregado no Ollama
2. **Local** (PyTorch direto) — carrega o `.pt` no próprio processo do dashboard

O Modo Local permite usar o modelo **sem depender do Ollama**, ideal para testes e desenvolvimento.

---

## ⚠️ Desafios e Problemas Encontrados

### 1. 🎯 VOCAB_SIZE vs Tokenizer Real

**Problema:** O modelo foi inicialmente configurado com `VOCAB_SIZE=32000`, mas o tokenizer treinado tinha apenas **23830 tokens**. Isso criava:
- 8170 slots de embedding **nunca utilizados** (peso morto)
- O `lm_head` podia predizer tokens inválidos (IDs 23830–31999) que o tokenizer não reconhecia
- Impossibilidade de carregar o checkpoint se o `VOCAB_SIZE` mudasse

**Solução:** O `VOCAB_SIZE` agora é **auto-detectado** do `tokenizer.json` em tempo real. O `generate()` também zera as probabilidades de tokens além do vocabulário real.

### 2. 🔁 Repetition Penalty Incorreto

**Problema:** No `generate()`, a penalidade de repetição era aplicada como `last_logit[idx] /= repetition_penalty` para **todos** os tokens. Para logits **negativos**, isso **aumentava** a probabilidade em vez de diminuí-la — efeito contrário ao desejado, causando repetições.

**Solução:** Agora aplica a penalidade corretamente:
```python
if last_logit[idx] >= 0:
    last_logit[idx] /= repetition_penalty
else:
    last_logit[idx] *= repetition_penalty
```

### 3. 🔄 GGUF Incompatível com Ollama

**Problema:** O `converter_para_gguf.py` gera arquivos GGUF válidos (verificados com `gguf.GGUFReader`), mas o Ollama **não consegue carregá-los**. O erro é:
```
llama runner process has terminated
```

**Causa:** A arquitetura `RigelSLM` (definida no `treino.py`) não corresponde a nenhuma arquitetura conhecida pelo `llama.cpp`. O Ollama espera arquiteturas padrão como `llama`, `mistral`, `gemma`, etc. O modelo RigelSLM usa `nn.TransformerDecoder` do PyTorch, que tem nomes de parâmetros diferentes.

**Status:** ⏳ Não resolvido. O modelo pode ser usado via `chat.py` (PyTorch direto) ou pelo Modo Local do dashboard.

### 4. 📡 Integração Frontend-Backend

**Problemas enfrentados:**

| Problema | Solução |
|----------|---------|
| `capture_output=True` descartava saída de subprocessos | Criado `stream_subprocess_to_log()` com `Popen` + streaming |
| Erros 422 (validação) em endpoints sem Pydantic | Adicionados modelos `BaseModel` para todos os requests |
| UnicodeEncodeError com emojis no Windows (cp1252) | Forçado `PYTHONIOENCODING=utf-8` + `encoding='utf-8'` |
| Training progress falsamente preso em 65% | Detectado marcador "TREINO CONCLUÍDO" no log |
| Tooltips faltando em botões | Adicionados `title` em todos os botões |
| Sem feedback visual ao executar scripts | Polling automático do `scripts.log` após execução |

### 5. 📐 Arquitetura e Parâmetros

- **Embedding 4D:** Tensor de embedding em formato 4D `[vocab, embed, 1, 1]` em vez de 2D `[embed, vocab]`. Corrigido no conversor GGUF.
- **Seq Len vs Memória:** Com `SEQ_LEN=512`, RAM ~8-10 GB. Aumentar para 1024 dobra o consumo.
- **Overfitting:** Com < 1000 arquivos, val_loss ~7.5. Com 20.000+, val_loss cai para ~1.5.

### 6. 🐌 Treino em CPU Apenas

Hardware: Intel Xeon E5-2699 v3 (18 núcleos, 36 threads), 32 GB RAM, **sem GPU** (GTX 550 Ti sem CUDA moderno). Impactos:
- Cada época com 20.000 arquivos leva **~9 horas** (aceito pix no meu e-mail  :)
- PyTorch limitado a 16 threads para estabilidade
- Use `--max-arquivos` para controlar o tempo de treino

---

## 🚀 Como Usar

### Treinar o Modelo

```powershell
# Treino completo (todas as pastas)
python treino.py

# Com limite de arquivos e pastas específicas
python treino.py --dados tucano,ultrachat --max-arquivos 5000 --epochs 30

# Retomar treino interrompido
python treino.py --resume --max-arquivos 20000

# Ajustar threads para CPU (importante!)
$env:OMP_NUM_THREADS = 16
python treino.py --max-arquivos 10000

# Testar modelo em dados específicos (sem treinar)
python treino.py --test "dados/processed/longos" --max-arquivos 500
```

### Chat com o Modelo

```powershell
# Modo interativo
python chat.py --temperature 0.8 --max-tokens 200

# Modo one-shot (para chamadas de programa/dashboard)
python chat.py --one-shot "Qual a capital do Brasil?"

# Com parâmetros personalizados
python chat.py --temperature 0.7 --top-k 40 --repetition-penalty 1.3 --no-stream
```

### Dashboard

```powershell
python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000
# Depois abra http://127.0.0.1:8000/
```

### Gerar Dados Sintéticos

```powershell
# v2 (22 tipos de conteúdo)
python dialogos2.py --quantidade 100 --tipo artigo

# v1 (pergunta-resposta via DeepSeek)
python dialogos.py --quantidade 500 --tipo auto --limite 5.00
```

---

## 💰 Custo da Geração com DeepSeek

| Tipo | Preço (por 1M tokens) |
|-----|----------------------|
| Entrada (prompt) | $0.14 |
| Saída (resposta) | $0.28 |

Com US$ 5,00 é possível gerar **~60.000** pares pergunta-resposta.

Configure no `.env`:
```env
DEEPSEEK_API_KEY=sua_chave_aqui
MODEL_NAME=deepseek-chat
MAX_COST_USD=5.00
DELAY_SECONDS=2.0
```

---

## 📦 Dependências

```bash
pip install -r requirements.txt
```

Principais: `torch>=2.0.0`, `tokenizers>=0.13.0`, `openai>=1.0.0`, `httpx>=0.24.0`, `fastapi>=0.104.0`, `uvicorn>=0.24.0`, `psutil>=5.9.0`, `gguf>=0.3.0`.

---

## 📋 Atualizações desta Versão (v3.1)

- ✅ `VOCAB_SIZE` auto-detectado do tokenizer (23830)
- ✅ `repetition_penalty` corrigido para logits negativos
- ✅ `chat.py` com modo `--one-shot` para integração
- ✅ Dashboard com **Modo Local** (PyTorch sem Ollama)
- ✅ Botão alternar entre Ollama e modo local
- ✅ Polling de status do modelo local
- ✅ Interface do chat adaptada para ambos os modos
- ✅ Tooltips em todos os botões
- ✅ Pós-processamento de respostas mais robusto
- ✅ Correção do argumento `--categoria` → `--tipo` no `dialogos2.py`

---

## 📜 Licença

MIT — use, modifique, distribua e comercialize, desde que mantenha os créditos.

---

## 🤝 Contribuições

Contribuições são bem-vindas! Abra issues ou envie pull requests no GitHub.

---

**Última atualização:** Julho de 2026  
**Versão do README:** 3.1

## 💡 Treino Eficiente com Múltiplas Pastas

Em vez de treinar pasta por pasta, use vírgulas para combinar:

```powershell
# Treina com várias pastas de uma vez
python treino.py --dados tucano,ultrachat,blogset,guara,canarim --max-arquivos 20000 --epochs 30
```

Para listar todas as pastas disponíveis:
```powershell
python treino.py --list-pastas
```

Para ver o help completo:
```powershell
python treino.py --help
```