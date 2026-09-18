# 📥 Guia de Instalação - RigelSLM

**Zero-to-hero:** de uma máquina limpa até o modelo rodando.

**Autor:** George Herman Becker · **Licença:** MIT · **Versão:** 1.0.0 · **Atualização:** 02/08/2026

> 💚 **Gostou do projeto? Apoie o desenvolvimento:**
> - **PIX:** `a8b68e14-edfe-4450-88f2-c2af4aca2a6c`
> - **Buy Me a Coffee:** <https://buymeacoffee.com/georgehbecker>

---

## Prova de Conceito — busca pelo conhecimento

Este projeto é uma **prova de conceito pessoal** cuja intenção é a **busca pelo conhecimento**: aprender construindo um modelo de linguagem pequeno do zero em português brasileiro — e **conhecer, na prática, os problemas mais comuns** desse caminho (todos documentados no [README](README.md), na seção "Problemas Enfrentados e Soluções"). A intenção nunca foi lançar um produto.

### Conselhos para quem quer aprender também

- **Use o VS Code** — editor gratuito, com terminal integrado, depuração, controle de versão e IA de apoio (GitHub Copilot) para escrever e revisar código: <https://code.visualstudio.com/>
- **Comece por uma API barata** — a **API da DeepSeek** é uma das opções mais acessíveis para quem está aprendendo (foi ela que ajudou na geração de dados deste projeto): <https://platform.deepseek.com/> — preços: <https://api-docs.deepseek.com/quick_start/pricing>

### A realidade do treino em CPU (aviso honesto)

Treinar na própria máquina pede **muitos núcleos de CPU, bastante RAM e disco SSD** — e mesmo com uma máquina razoável (o caso deste projeto: **~32 GB de RAM, 36 núcleos, SSD de 223 GB, sem GPU aproveitável**) o processo é **massante**: o ritmo ficou em torno de **274 tokens/s**, ou cerca de **2 arquivos de 1.000 exemplos a cada 2 horas** de treino. **Não é impossível** — dá para aprender treinando lotes pequenos com paciência — mas no fim o autor apelou para o **Google Colab** (GPU com uso gratuito limitado) para acelerar: <https://colab.research.google.com/>

Mais sobre o autor: <https://ghbecker.com.br>

---

## 📖 Glossário (para entender o que este guia diz)

| Termo | Significado |
|---|---|
| **SLM** | *Small Language Model* — modelo de linguagem pequeno e eficiente (o Rigel tem ~58M de parâmetros) |
| **SFT** | *Supervised Fine-Tuning* — ajuste fino supervisionado que ensina o modelo no formato `messages` |
| **JSONL** | Formato de arquivo: uma linha = um JSON (um exemplo de conversa) |
| **messages** | Estrutura de conversa: `{"messages": [{"role": "system"...}, {"role": "user"...}, {"role": "assistant"...}]}` |
| **Explodir** | Dividir um dataset grande em vários arquivos menores (ex.: 1000 exemplos por arquivo) |
| **Promover** | Validar e copiar só os arquivos bons para `dados/processed/jsonl/` |
| **Bandeira** | Marca de quantas vezes um arquivo foi treinado: sem (0x), branca (1x), amarela (2x), vermelha (3x+) |
| **Checkpoint** | Salvar o estado do treino para retomar (`checkpoint_jsonl.pt` + `--resume`) |
| **Loss** | Número que mede o erro do modelo (menor = melhor; se cai, está aprendendo) |
| **Learning Rate (LR)** | "Velocidade" do aprendizado (sobe no warmup, desce no decay) |
| **GGUF** | Formato otimizado de modelo para rodar no Ollama/llama.cpp |
| **Gated** | Dataset do HuggingFace que exige login/token (defina `HF_TOKEN`) |
| **Mojibake** | Texto com acentos quebrados ("VocÃª" em vez de "Você") — o pipeline corrige |
| **Shard** | Parte de um arquivo grande (ex.: `dataset_rigel_0002.jsonl`) |

---

## � Super Menu de Comandos

> **Quando precisar fazer algo no projeto** (converter, treinar, sanitizar, baixar, empacotar...),
> consulte o **guia de comandos**: **📄 [`docs/COMANDOS.md`](docs/COMANDOS.md)** — organizado por tarefa, com os comandos exatos de terminal e as páginas do dashboard.

---

## �🤖 Modelos do Ollama (IMPORTANTE)

### Obrigatórios (para o fluxo funcionar de verdade)
```bash
ollama pull llama3.2:3b    # geração de dados (padrão CPU do createjsonl.py)
ollama pull gemma2:2b      # leve, ótimo em PT-BR (alternativa de geração)
```

### Extras (rodam bem localmente, mas não são necessários)
```bash
ollama pull tinyllama:1.1b     # muito leve, testes rápidos
ollama pull phi3:mini          # raciocínio leve
ollama pull qwen2.5-coder:7b   # código (recomendado p/ GPU/Colab na geração)
```

### ⚠️ REGRA DE OURO
**NUNCA use o modelo `rigelslm` para gerar dados.** Ele é o modelo em treinamento — respostas dele contaminariam o dataset.

---

## 🪟 Windows

### Pré-requisitos
- Nenhum! O `setup.bat` cuida de tudo.

### Passo a passo

1. **Baixe o projeto**
   ```
   git clone https://github.com/seu-usuario/rigelllm.git
   cd rigelllm
   ```
   Ou extraia o ZIP baixado.

2. **Execute o setup**
   ```
   setup.bat
   ```
   O script vai:
   - ✅ Verificar se Python 3.10+ existe (se não, baixa e instala)
   - ✅ Criar ambiente virtual (`.venv`)
   - ✅ Instalar todas as dependências
   - ✅ Criar pastas necessárias
   - ✅ Configurar arquivo `.env`
   - 🛡️ **Detectar o hardware e gravar limites proporcionais** (RAM, CPU, GPU, SSD/NVMe/HDD) em `config_recursos.json`
   - ✅ Oferecer instalação do Ollama

3. **Configure a chave DeepSeek** (opcional)
   ```
   notepad .env
   ```
   Altere `DEEPSEEK_API_KEY=deepseek-aqui` para sua chave real.

4. **Verifique a instalação**
   ```
   .venv\Scripts\activate
   python verificador.py
   ```

5. **Inicie o sistema**
   ```
   python rigel.py
   ```

---

## 🛡️ Guardião de Limites (proporcionais à máquina)

O RigelSLM detecta o **hardware da sua máquina** na instalação e grava limites
proporcionais em `config_recursos.json` (na raiz do projeto). Cada máquina é
diferente — notebook, PC, servidor, com ou sem placa de vídeo, HD/SSD/NVMe —
então os limites acompanham os recursos:

| Limite | O que faz | Exemplo (32 GB RAM, SSD) |
| --- | --- | --- |
| `MEM_MIN_LIVRE_PCT` / `MEM_MIN_LIVRE_MB` | Aborta escaneamento se a memória livre cair abaixo (percentual da RAM) | 12% (~3,9 GB) |
| `SCAN_MAX_ARQUIVOS` / `SCAN_MAX_DIRETORIOS` | Cap de arquivos/pastas visitados por scan (proporcional à RAM) | 2,1M / 178k |
| `SCAN_PAUSA_CADA` / `SCAN_PAUSA_SEG` | Pausa periódica durante o scan (protege o SSD; mais agressiva em HD) | a cada 2000 itens / 2 ms |
| `CPU_MAX_USO_PCT` | Scan "respira" se o uso de CPU passar disso | 65% (sem GPU) / 80% (com GPU) |
| `DISCO_MIN_LIVRE_PCT` / `DISCO_MIN_LIVRE_MB` | Não grava cache sem disco livre suficiente | 5% (~11 GB) |
| `SCAN_MAX_NOMES_CACHE` | Cap de nomes guardados no cache JSONL | 2000 |

- Para **ver o que foi detectado**: `python -m dashboard.services.recursos`
- Para **regenerar** (ex.: trocou de máquina/disco): `python -m dashboard.services.recursos --salvar`
- Para **ajustar um limite**, edite o `config_recursos.json` ou use variável de
  ambiente (elas têm prioridade), ex.: `set MEM_MIN_LIVRE_PCT=15`.
- Tudo fica registrado em `logs/recursos.log` (rastro).

### ⚡ Estabilidade do dashboard (02/08/2026)
- O `run_dashboard.bat` **v2.3.1** corrigiu a **cascata de abas no Chrome** e o
  **loop de reinício**: navegador abre **1x por sessão**, monitor único e a
  limpeza agora mata os **workers órfãos do `--reload`** (`spawn_main`) que
  seguravam a porta 8000.
- Para **máxima estabilidade**, rode o uvicorn **sem `--reload`** (processo
  único). Com `--reload`, use sempre `--reload-dir dashboard` (não varre `dados/`).
- Se o dashboard travar com a porta 8000 presa: feche as janelas "RigelSLM
  Uvicorn", mate os pythons (`dashboard.main` e `spawn_main`) e espere ~2s.

---

## 🐧 Linux / macOS

### Passo a passo

1. **Baixe o projeto**
   ```bash
   git clone https://github.com/seu-usuario/rigelllm.git
   cd rigelllm
   ```

2. **Execute o setup**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
   O `setup.sh` também detecta o hardware e grava os limites proporcionais em
   `config_recursos.json` (ver seção 🛡️ Guardião de Limites acima).

3. **Configure a chave DeepSeek** (opcional)
   ```bash
   nano .env
   ```

4. **Verifique a instalação**
   ```bash
   source .venv/bin/activate
   python verificador.py
   ```

5. **Inicie o sistema**
   ```bash
   python rigel.py
   ```

---

## ☁️ Google Colab

### Opção 1: Usar o notebook pronto
1. Acesse [RigelSLM_Colab.ipynb](RigelSLM_Colab.ipynb)
2. Faça upload para o Google Colab
3. Execute célula por célula

### Opção 2: Via GitHub
1. Abra https://colab.research.google.com/
2. File → Open notebook → GitHub
3. Cole o URL do seu repositório
4. Selecione `RigelSLM_Colab.ipynb`

---

## 🔄 Recuperação de Falhas

O sistema foi projetado para se recuperar automaticamente de:

```
Queda de luz / Travamento
        │
        ▼
┌─────────────────────┐
│  Iniciar rigel.py   │
│  via setup ou       │
│  python rigel.py    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Verificador.py     │
│  Checa todos os     │
│  serviços           │
└─────────┬───────────┘
          │
     ┌────┴────┐
     ▼         ▼
┌────────┐ ┌────────┐
│ Ollama │ │Dashboard│
│ offline│ │ offline │
└───┬────┘ └───┬────┘
    │          │
    ▼          ▼
┌────────┐ ┌────────┐
│ Inicia │ │ Inicia │
│ ollama │ │ uvicorn│
│ serve  │ │ :8000  │
└────────┘ └────────┘
    │          │
    └────┬─────┘
         ▼
┌─────────────────────┐
│  estado_global.json │
│  Registra tudo      │
│  (sobrevive a       │
│   quedas)           │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  log_manager.py     │
│  Analisa erros e   │
│  gera resumos       │
└─────────────────────┘
```

### O que acontece em cada falha:

| Problema | Comportamento |
|----------|---------------|
| **Queda de luz** | `estado_global.json` mantém o estado. Ao reiniciar, `verificador.py` checa tudo e `rigel.py` pergunta se quer retomar. |
| **Internet caiu** | Sistemas locais (Ollama, geração local) continuam. DeepSeek API dá erro gracioso. |
| **HD cheio** | `verificador.py` alerta se disco >95%. `log_manager.py` compacta logs antigos. |
| **Ollama travou** | Diagnóstico detecta e tenta reiniciar automaticamente. |
| **Checkpoint corrompido** | `agrupar.py` faz backup e recria checkpoint vazio (pergunta ao usuário). |
| **Sem créditos DeepSeek** | Fallback automático para geração local via Ollama. |

---

## 📁 Estrutura de Pastas

```
rigelllm/
├── dashboard/                  # Interface web (FastAPI + HTML)
│   ├── main.py                 # Backend (entrada do dashboard)
│   ├── routes/                 # Endpoints da API (/api/...)
│   ├── services/               # Lógica (HF datasets, treino local...)
│   ├── templates/              # Páginas HTML (base, datasets, treino_local...)
│   └── static/                 # JS/CSS
├── dados/                      # Dados do projeto
│   ├── raw/                    # Downloads brutos (não mexer; pode limpar depois)
│   ├── gerados/
│   │   └── jsonl/
│   │       ├── <dataset>_DATA/ # Datasets explodidos (área de trabalho)
│   │       └── jsonlocal/      # Geração local: rigel_YYYYMMDD.jsonl
│   └── processed/
│       └── jsonl/<dataset>/    # Datasets VALIDADOS/promovidos (prontos p/ treino)
├── modelo/                     # PESOS DO MODELO (viaja pro Drive/Colab!)
│   ├── modelo.pt               # Modelo final
│   ├── modelo_melhor.pt        # Melhor modelo (usado pelo conversor GGUF)
│   ├── checkpoint_jsonl.pt     # Checkpoint SFT (retomada do treino JSONL)
│   ├── checkpoint.pt           # Checkpoint do treinador legado (.txt)
│   ├── tokenizer.json          # Tokenizador
│   ├── backups/                # 💾 Cópias de segurança (automáticas + manuais)
│   └── jsonlogs/               # Registro de bandeiras por dataset
├── logs/                       # Logs do sistema
├── gguf/                       # Modelos convertidos (GGUF) + Modelfiles
├── estado/                     # Estado persistente
├── requirements.txt            # Dependências Python
├── setup.bat / setup.sh        # Instaladores
├── run_dashboard.bat           # 🚀 Iniciar o dashboard com 1 clique
├── rigel.py                    # Orquestrador principal
├── verificador.py              # Diagnóstico de serviços
├── createjsonl.py              # Gerar / baixar / explodir datasets JSONL
├── treinar_com_jsonl.py        # ✅ Treinador SFT de datasets JSONL (messages)
├── treino.py / treinov2.py     # Treinadores legados (dados .txt)
└── download_datasets.py        # Pipeline de dados .txt (BlogSet, Wiki, brWaC...)
```

---

## 🚀 Comandos principais (os difíceis de lembrar)

### Dashboard / Backend
```bash
# ✅ CORRETO — iniciar o dashboard (recomendado: SEM --reload = processo único e estável)
python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000

# Para desenvolvimento (hot-reload SÓ na pasta dashboard — não varre dados/)
python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir dashboard

# ❌ NUNCA use isto (quebra com erro de import relativo):
python dashboard/main.py

# 🚀 Mais fácil: dê 2 cliques no run_dashboard.bat (v2.3.1)
# - limpa a porta 8000 (inclusive workers órfãos do --reload)
# - navegador abre 1x por sessão (sem cascata de abas)
# - monitor único (instância duplicada não nasce)
```

### Treinamento (SFT com JSONL)
```bash
# Treinar TODOS os datasets de trabalho
python treinar_com_jsonl.py --dados dados/gerados/jsonl

# Treinar somente os datasets promovidos (validados)
python treinar_com_jsonl.py --dados dados/processed

# Treinar UM arquivo específico
python treinar_com_jsonl.py --dados dados/gerados/jsonl --arquivo adalbertojunior_Guara_00001.jsonl

# Treinar com limite (ex.: 20 arquivos)
python treinar_com_jsonl.py --dados dados/gerados/jsonl --max-arquivos 20

# Continuar de onde parou
python treinar_com_jsonl.py --dados dados/gerados/jsonl --resume

# Treinar no Colab o MENOR arquivo (teste rápido; célula %%bash)
MENOR=$(find dados/gerados/jsonl -name "*.jsonl" -printf "%s %p\n" | sort -n | head -1 | cut -d' ' -f2-)
python treinar_com_jsonl.py --dados "$(dirname "$MENOR")" --arquivo "$(basename "$MENOR")" --epochs 1 --max-exemplos 30 --no-interactive --resume
```

### Gerar dados (createjsonl.py)
```bash
python createjsonl.py --count 500                   # 500 exemplos (CPU: gemma2:2b)
python createjsonl.py --count 500 --gpu             # se tiver GPU/Colab (qwen2.5:7b)
python createjsonl.py --count 500 --usar-topicos-txt  # usa topicos.txt (RSS)
python createjsonl.py --count 100 --dry-run         # testa sem salvar
# Saída: dados/gerados/jsonl/jsonlocal/rigel_YYYYMMDD.jsonl (nunca sobrescreve)

# Baixar dataset do HuggingFace e explodir
python createjsonl.py --hf-dataset adalbertojunior/Guara

# Baixar de URL e explodir
python createjsonl.py --download "https://.../dataset.zip"

# Processar pasta/arquivo local
python createjsonl.py --process "caminho/para/dataset"
```

### Baixar dados (dashboard — o jeito recomendado)
1. Abra o dashboard → **Datasets HF** (`/datasets`)
2. Busque (ex.: `portuguese instruction`, `pt-br`, ou cole o ID exato `org/nome`)
3. Clique em **Baixar** (mostra % real de bytes) → sai em `dados/gerados/jsonl/<nome>_DATA/`

### Pipeline de dados .txt (legado, treino.py)
```bash
python download_datasets.py            # menu interativo de fontes
python download_datasets.py --qualificar --fonte tucano
python download_datasets.py --max-gb 10
```

### Converter para GGUF (rodar no Ollama)
```bash
python converter_para_gguf.py --model modelo/modelo_melhor.pt --quant Q4_K_M
```

> ⚠️ **Importante (06/08/2026) — tokenizer ByteLevel:** o `tokenizer.json` do Rigel é
> BPE ByteLevel (estilo GPT-2) e usa `Ġ` (U+0120) para marcar espaço. O `converter_para_gguf.py`
> (já corrigido) mantém `Ġ` no vocab/merges e grava `tokenizer.ggml.model="gpt2"` +
> `tokenizer.ggml.pre="gpt-2"` + `add_space_prefix=false`. **NÃO** converta `Ġ→▁`
> (U+2581): isso quebra o BPE do llama.cpp e o GGUF gera vazio/lixo. Depois de converter,
> crie no Ollama com a quantização distinta: `ollama create rigelslm:q8_0 -f gguf/Modelfile.rigelslm_Q8_0`.
> Backup do conversor antigo: `converter_para_gguf.py.bak_20260806`. Detalhes: README.md → "Problemas Enfrentados e Soluções" #3.7.

### Converter .txt legados (pergunta/resposta) para JSONL SFT

Seus milhares de arquivos `.txt` antigos podem virar JSONL `messages` (ensina o modelo
**a responder**, não só a prever a próxima letra):

```bash
# Converte uma pasta inteira (Pergunta/Resposta + artigos) → dados/gerados/jsonl/<saida>/
python converter_txt_jsonl.py --pasta dados/processed --saida txt_convertido

# Só Q&A com marcadores (pula artigos)
python converter_txt_jsonl.py --pasta dados/processed/canarim --saida canarim_sft --apenas-qna

# Teste rápido
python converter_txt_jsonl.py --pasta dados/processed --saida txt_convertido --max-arquivos 100
```

O conversor adiciona o system prompt do Rigel, corrige mojibake, remove duplicatas,
e explode em arquivos de 1000 exemplos — o resultado aparece direto no **Treino Local** do dashboard.

### 🤖 Disponibilizar ao Ollama (no dashboard)

Abra o dashboard → **Converter GGUF** → botão **"Criar no Ollama"** (por GGUF) ou use a **Conversão rápida**:

1. Converte o modelo .pt escolhido para GGUF
2. Cria/atualiza o modelo `rigelslm` no Ollama → pronto: `ollama run rigelslm`

> 💡 O RigelSLM é pequeno o suficiente para rodar até em um smartwatch ou robozinho. 😉

### 💾 Backups do modelo / recuperação rápida

O sistema **nunca deixa você perder o modelo**: antes de **qualquer** sobrescrita de
`modelo.pt`/`modelo_melhor.pt` (treino, restauração, conversão para Ollama), uma cópia
é guardada em `modelo/backups/` com timestamp (mantém os 20 mais recentes).

**Via dashboard:** Treino Local → seção "Backups do modelo" → 📦 Fazer backup agora / ↩ Restaurar.

**Via backend (terminal):**

```bash
# Ver quais backups existem
python modelo_backup.py listar

# Fazer backup manual agora
python modelo_backup.py criar

# RESTAURAR um backup (recuperação rápida)
python modelo_backup.py restaurar modelo_20260802_034457.pt
```

**Se o modelo ficar ruim depois de um treino:**

```bash
python modelo_backup.py listar          # 1. veja o backup anterior
python modelo_backup.py restaurar <arquivo>   # 2. restaure (o atual ruim é guardado como pre_restauro_*)
```

### Verificação / Orquestração
```bash
python verificador.py    # ping real nos serviços
python rigel.py          # orquestrador principal (menu)
```

---

## ❓ FAQ / Problemas Comuns

**P: "ollama não está rodando" mesmo mostrando Online**
R: Execute `python verificador.py` para um ping real. Às vezes o processo existe mas a API não responde.

**P: O setup.bat não funciona**
R: Certifique-se de executar como administrador. Se o download do Python falhar, baixe manualmente de python.org.

**P: Queda de energia durante o treino**
R: O `treino.py` salva checkpoints periodicamente. Use `--resume` para continuar de onde parou.

---

**Licença:** MIT
**Autor:** George Herman Becker
**Versão:** 1.0.0
**Última atualização:** 02/08/2026
**💚 Doações:**
- **PIX:** `a8b68e14-edfe-4450-88f2-c2af4aca2a6c`
- **Buy Me a Coffee:** <https://buymeacoffee.com/georgehbecker>
