# ⭐ RigelSLM – Small Language Model para Português Brasileiro

**Autor:** George Herman Becker · **Licença:** MIT · **Versão:** 1.0.0 · **Atualização:** 18/08/2026

> 🧭 **Precisa de um comando?** Consulte o **Super Menu de Comandos (FAQ)**: [`docs/COMANDOS.md`](docs/COMANDOS.md) — "quando precisar fazer X, use o comando Y" (Python e dashboard).

> 💚 **Gostou do projeto? Apoie o desenvolvimento:**
> - **PIX:** `a8b68e14-edfe-4450-88f2-c2af4aca2a6c`
> - **Buy Me a Coffee:** <https://buymeacoffee.com/georgehbecker>

---

## 📖 O que é o RigelSLM?

RigelSLM é um **modelo de linguagem pequeno (SLM)** treinado do zero com foco exclusivo no **português do Brasil**. Possui aproximadamente **66 milhões de parâmetros**, sendo leve o suficiente para rodar em CPUs convencionais sem GPU.

O projeto nasceu da necessidade de ter um modelo que entenda a **cultura brasileira**, expressões regionais, história e geografia do país — algo que modelos grandes frequentemente ignoram ou tratam de forma genérica.

O nome **Rigel** vem da estrela mais brilhante da constelação de Órion.  
**SLM** significa *Small Language Model*.

---

## Prova de Conceito — o que este projeto é (e o que não é)

Este repositório é uma **prova de conceito pessoal** movida por uma coisa: **busca pelo conhecimento**. A intenção **nunca foi lançar um produto** — foi **aprender construindo**: entender na prática as ferramentas, as técnicas e, principalmente, **conhecer os problemas mais comuns** que aparecem quando se treina um modelo de linguagem do zero. Cada obstáculo encontrado e sua solução foi documentado ao longo do caminho (ver a seção "Problemas Enfrentados e Soluções") — o valor desta prova de conceito está exatamente aí: no **conhecimento que fica registrado**.

**O que a prova de conceito demonstrou (de ponta a ponta):**

| Etapa | O que foi validado |
| --- | --- |
| Tokenizer | Treinar um tokenizer BPE ByteLevel próprio (vocab 23.830) e diagnosticar incompatibilidades de vocabulário |
| Treino | Transformer decoder (~66M) treinado do zero em CPU, com SFT mascarado (loss só na resposta) e retomada por checkpoint |
| Dados | Pipeline completo: coleta (RSS, HuggingFace, PDFs), sanitização rigorosa PT-BR, deduplicação e organização em lotes |
| Quantização | Conversão real para GGUF (F16, Q8_0, Q4_K_M) e correções no export do tokenizer para o llama.cpp |
| Integração | Ponte GGUF → Ollama, com diagnóstico de erros de arquitetura, norms em F32 e token types |
| Gestão | Dashboard FastAPI com executor multi-atividade, guardião de recursos proporcionais ao hardware e progresso em tempo real (SSE) |

**O que este repositório NÃO inclui (de propósito):**

- Datasets e material de treinamento — ficam fora do Git (grandes, recriáveis pelo pipeline)
- Pesos dos modelos, checkpoints e arquivos GGUF — gerados localmente
- Chaves de API e segredos — sempre via arquivo `.env` local (nunca versionado)

**Estado honesto:** o modelo ainda está em evolução (subtreinado). A prova de conceito não terminou em um produto final — terminou em **conhecimento documentado**: cada erro, causa e correção está registrado nos problemas enfrentados, no changelog e nos módulos do projeto.

### A realidade do treino em CPU (leia antes de tentar)

Treinar um modelo do zero na própria máquina exige **muitos núcleos de CPU, bastante memória RAM e disco SSD** (HD mecânico sofre). E mesmo com uma máquina razoável o processo é **massante**: não é impossível, mas é lento.

O que este projeto tinha à disposição: **~32 GB de RAM, 36 núcleos de CPU, SSD de 223 GB e nenhuma GPU aproveitável**. Mesmo assim, o ritmo real de treino ficou em torno de **274 tokens/s** — cerca de **2 arquivos de 1.000 exemplos a cada 2 horas**. Treinar o acervo inteiro em CPU levaria semanas.

No fim, para acelerar de verdade, o autor **apelou para o Google Colab** (GPU com uso gratuito limitado). A recomendação que fica: **aprenda localmente com lotes pequenos** e rode as rodadas maiores no Colab — <https://colab.research.google.com/>

### Para quem quer trilhar o mesmo caminho (conselhos)

- **Use o VS Code como companheiro de aprendizado** — editor gratuito, com terminal integrado, depuração, controle de versão e IA de apoio (GitHub Copilot) para escrever e revisar código. Site oficial: <https://code.visualstudio.com/>
- **Para experimentar com IA sem gastar muito, comece pela API da DeepSeek** — uma das opções de API mais acessíveis para quem está aprendendo (foi ela que ajudou na geração de dados sintéticos deste projeto). Plataforma: <https://platform.deepseek.com/> — preços: <https://api-docs.deepseek.com/quick_start/pricing>

Mais sobre o autor: <https://ghbecker.com.br>

---

## �🧠 Arquitetura do Modelo

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

## 🗂️ Estrutura do Projeto

```
C:\Rigelllm\
├── dashboard/                 # Interface web (FastAPI + Tailwind + Alpine.js)
│   ├── main.py                # App FastAPI, rotas principais, status do sistema
│   ├── routes/                # Rotas organizadas por funcionalidade
│   │   ├── train.py           # Treino: iniciar, parar, progresso, logs
│   │   ├── chat.py            # Chat: Ollama + Modo Local PyTorch
│   │   ├── rss.py             # RSS: processar feeds, testar, adicionar
│   │   ├── convert.py         # GGUF: conversão .pt → GGUF com progresso
│   │   ├── generate.py        # Dados: gerar via DeepSeek, executar scripts
│   │   ├── debate.py          # Debate/Podcast via DeepSeek com pesquisa web
│   │   ├── debate_local.py    # Debate/Podcast via Ollama (modelo local)
│   │   ├── topicos.py         # Gerenciamento de tópicos (RSS + DeepSeek)
│   │   ├── logs.py            # Logs: listar, visualizar, métricas
│   │   ├── diagnostico.py     # Diagnóstico: contagem real de arquivos
│   │   ├── ollama.py          # Ollama: status, iniciar, parar, reiniciar
│   │   └── organizar.py       # Organização de pastas de dados
│   ├── services/              # Serviços auxiliares
│   │   ├── runner.py          # Execução de scripts em background com log
│   │   ├── monitor.py         # Monitoramento (CPU, RAM, disco, Ollama)
│   │   ├── limpeza.py         # Limpeza de texto, remoção ANSI, espaços
│   │   ├── pesquisa.py        # Busca na web (DuckDuckGo)
│   │   ├── converter_state.py # Estado da conversão GGUF em tempo real
│   │   ├── estrutura_cache.py # 🛡️ Guardião de limites + cache de estrutura
│   │   ├── recursos.py        # ⚙️ Limites proporcionais ao hardware
│   │   ├── treino_local.py    # Treino SFT via subprocesso (bandeiras)
│   │   ├── hf_datasets.py     # Busca/download de datasets HuggingFace
│   │   └── ollama_deploy.py   # Disponibilizar modelo ao Ollama
│   ├── templates/             # Templates HTML (Alpine.js)
│   │   ├── base.html          # Layout base com tema escuro/alegre
│   │   ├── index.html         # Dashboard principal
│   │   ├── chat.html          # Chat com Ollama + modelo local
│   │   ├── treinamento.html   # Controle de treino
│   │   ├── converter.html     # Conversão GGUF com progresso
│   │   ├── gerar_dados.html   # Geração via API DeepSeek
│   │   ├── gerar_local.html   # Geração via Ollama + scripts
│   │   ├── debate.html        # Debate/Podcast via DeepSeek
│   │   ├── debate_local.html  # Debate/Podcast via Ollama
│   │   └── logs.html          # Visualizador de logs
│   └── static/                # Assets
├── modelo/                    # Checkpoints do modelo (.pt)
│   ├── modelo_melhor.pt       # Melhor modelo (val_loss mínimo)
│   ├── modelo.pt              # Último checkpoint
│   └── checkpoint.pt          # Checkpoint intermediário
├── tokenizer/
│   └── tokenizer.json         # Tokenizer BPE ByteLevel treinado
├── dados/
│   ├── processed/             # Acervo final de treino — UMA pasta por tipo (18/08)
│   │   ├── txt/               #  297 subpastas de TXT (≤1000 arq/cada)
│   │   ├── jsonl/             #  112 subpastas: *_sanitizado (pronto) + brutas
│   │   └── parquet/           #  7 subpastas de PARQUET
│   ├── tratados/              # Saída do tratamento automático de datasets brutos
│   ├── sanitizados/           # Staging do TRATAMENTO (sanitização) antes de promover
│   ├── gerados/               # Dados sintéticos (DeepSeek, Ollama, RSS)
│   │   ├── gerados_local/     # Conteúdo gerado via Ollama
│   │   ├── debates/           # Debates e podcasts
│   │   └── feedback_chat/     # Feedback do chat salvo
│   └── raw/                   # Dados brutos originais
├── logs/                      # Logs do sistema
│   ├── conversao.log          # Log de conversões GGUF
│   ├── ollama_create.log      # Log de criação de modelos Ollama
│   ├── dashboard.log          # Log geral do dashboard
│   ├── metricas.json          # Métricas de treino
│   ├── recursos.log           # Rastro do guardião de limites
│   └── estrutura_cache/       # Cache persistente da estrutura (scans)
├── gguf/                      # Modelos convertidos para GGUF
├── docs/                      # Documentação complementar
├── images/                    # Ícones e imagens do dashboard
├── topicos.txt                # Lista de tópicos para geração
├── feeds.txt                  # Fontes RSS configuradas
├── requirements.txt           # Dependências Python
├── config_recursos.json       # 🛡️ Limites proporcionais (gerado na instalação)
├── setup_env.py               # Configuração inicial do ambiente
├── run_dashboard.bat          # 🚀 Dashboard com 1 clique (auto-recuperação)
├── regras_pastas.py           # 🗂️ Fonte de verdade das pastas por tipo (18/08)
├── createjsonl.py             # Gerar/baixar/explodir datasets JSONL
├── treinar_com_jsonl.py       # ✅ Treinador SFT (JSONL messages)
├── saida_manager.py           # Escritor JSONL unificado (geração→JSONL)
├── modelo_backup.py           # 💾 Backups automáticos do modelo
└── converter_txt_jsonl.py     # .txt legados → JSONL SFT

---

## � Pastas e o que guardam

| Pasta | O que guarda |
|---|---|
| `dashboard/` | **Servidor web (FastAPI)** — `main.py` (app + rotas principais), `routes/` (rotas por funcionalidade: train, chat, convert, convert_txt, datasets, executor, tratamento, treino_local, scrap, debate, rss, logs, ollama...), `services/` (lógica de apoio: executor, sanitizacao, treino_global, pesquisa, recursos, estrutura_cache, templates_conteudo...), `templates/` (HTML Alpine.js de cada página), `static/` (assets) |
| `docs/` | Documentação: `changelog.md` (histórico de sessões), diário de ideias, pipeline JSONL, relatório de auditoria, inventário de rotas, `MODULOS/` |
| `estado/` | **Estados persistentes JSON** de cada funcionalidade (treino, sanitização, explosão, executor, datasets, Ollama, scrap, tratamento...) — a "memória do sistema" que sobrevive a reinícios |
| `images/` | Ícones/favicons do dashboard + QR PIX + apoio |
| `llama/` | Binários do **llama.cpp** (conversão/execução local de GGUF) |
| `modelo/` | Modelos treinados: `modelo.pt`, `modelo_melhor.pt`, `checkpoint*.pt`, `backups/`, `versoes.json`, sinal `STOP_TREINO.signal` |
| `scripts/` | ~60 utilitários de diagnóstico/verificação (GGUF, encoding, auditoria, sanitização, testes de geração) + `legado/` |
| `skills/` | Guia de estilo para skills de IA do projeto |
| `tests/` | Testes de qualidade (ex.: `test_dialogos2_quality.py`) |
| `tokenizer/` | `tokenizer.json` — o vocabulário/tokenizador do modelo (**VOCAB 23830** — o correto) |
| `dados/` | Todo o dado: `raw/` (bruto), `processed/` (pronto p/ treino, com `jsonl/` = 112 subpastas), `tratados/` (saída do tratamento automático de brutos), `gerados/` (sintético: jsonl, gerados_local, debates...), `sanitizados/`, `descartados/`, `ultratxt/`, `Celular/` (troca celular↔PC) |
| `colab/` | Notebook pronto para rodar no **Google Colab** (`RigelSLM_Colab_pronto.ipynb`) |
| `gguf/` | Modelos convertidos para GGUF + Modelfiles |
| `logs/` | Logs do sistema (treino, dashboard, conversão, recursos, estrutura_cache, mural do executor...) |

> 🧭 **Comandos de terminal e páginas do dashboard:** [`docs/COMANDOS.md`](docs/COMANDOS.md)

---

## 🎯 Gerenciadores e scripts principais

- **`rigel.py`** — orquestrador geral (setup, treino, dashboard, Ollama).
- **`dashboard/main.py`** — servidor web (o "site" inteiro).
- **`main.py`** — CLI do gerador de dados via API (com limite de custo).
- **`treino.py`** — **base do modelo** (define a arquitetura `RigelSLM`); é importado por `app.py`, `chat.py`, `converter_para_gguf.py`, `treinar_com_jsonl.py` e rotas do dashboard.
- **Bibliotecas reutilizadas**: `config`, `utils`, `state`, `generation`, `validation`, `categories`, `saida_manager`, `sanitizador_ptbr`, `modelo_backup`, `organizar_pastas`, `createjsonl`, `deploy_package`.
- **Scripts standalone/CLI** (executados direto, não importados): `agrupar.py`, `dialogos.py` (substituído pelo v2), `dialogos2.py`, `downdata.py`, `download_datasets.py`, `dividir_pastas.py`, `limpeza.py`, `limpeza_leve_rigel_v2.py`, `log_manager.py`, `preparar_dados.py`, `setup_env.py`, `treinov2.py`, `treinoparquet.py`, `treino_cloud.py`, `treino_colab.py`, `ultra.py`.
- **Chamados como subprocesso pelo dashboard** (não import): `converter_txt_jsonl.py`, `rss_processor.py`, `treinar_com_jsonl.py`, `treino.py`/`treinoparquet.py`/`treino_colab.py`, `setup_env.py`, `dialogos2.py`.

---

## �📜 Descrição de Cada Arquivo .py

### 🧠 Núcleo do Modelo

| Arquivo | Função | O que produz |
|---------|--------|-------------|
| `treino.py` | Define a arquitetura `RigelSLM` (Transformer decoder), pipeline de treino completo, carregamento de dados (TXT, PDF, HTML, XML, CSV, JSONL), checkpointing, salvamento do melhor modelo | Checkpoints `.pt` em `modelo/`, logs em `logs/`, métricas em `metricas.json` |
| `chat.py` | Chat interativo via terminal. Modo conversa com histórico (últimas 3 trocas) e modo `--one-shot` para integração com dashboard. Exibe métricas de treino, barra de maturidade, parâmetros | Respostas de texto na tela. Comandos: `/clear`, `/exit`, `/stats` |
| `converter_para_gguf.py` (v1.0.0) | Converte checkpoint `.pt` para GGUF compatível com Ollama 0.32.5+. Merges como string, 75 tensores estilo Llama (sem biases), output_norm + ffn_up sintéticos. Suporta 13 quantizações | Arquivo `.gguf` em `gguf/` + `Modelfile` para Ollama |
| `treinar_com_jsonl.py` | ✅ Treinador SFT de datasets JSONL (`messages`), loss só no assistant, checkpoint/early-stop/NaN/OOM/Ctrl+C seguro, bandeiras + barra de % + ETA | `modelo/modelo.pt`, `modelo/modelo_melhor.pt`, `modelo/checkpoint_jsonl.pt` |
| `converter_txt_jsonl.py` | Converte .txt legados (Pergunta/Resposta + artigos) para JSONL SFT (`messages`), corrige mojibake, dedup | `dados/gerados/jsonl/<saida>/` |
| `modelo_backup.py` | Backups automáticos/manuais do modelo antes de cada sobrescrita (mantém 20) | `modelo/backups/*.pt` |
| `rigel.py` | Implementação alternativa/experimental do modelo | Variações do RigelSLM |

### 📊 Geração de Dados

| Arquivo | Função | O que produz |
|---------|--------|-------------|
| `dialogos.py` | Geração de dados sintéticos v1 via DeepSeek. Pares pergunta-resposta sobre cultura brasileira | Arquivos `.txt` em `dados/gerados/` (~500 diálogos por execução) |
| `dialogos2.py` | Geração de dados sintéticos v2 com 22 tipos de conteúdo: artigo, conto, poema, entrevista, debate, tutorial, etc. | Arquivos `.txt` nas subpastas de `dados/gerados/` (~200 itens por execução) |
| `rss_processor.py` | Coleta notícias de 27+ feeds RSS brasileiros. Faz scraping, classifica por tamanho (curto/longo/completo), gera resumos 100% local via Ollama (retry + timeout adaptativo, `--modelo-resumo`). Se o resumo falhar, salva como completo (não descarta) | Notícias em `dados/gerados/curtos/`, `longos/`, `completos/` + títulos em `topicos.txt` |
| `preparar_dados.py` | Prepara e qualifica dados brutos: valida encoding, classifica por tipo de conteúdo, remove ruídos | Dados organizados em `dados/processed/` com metadados |
| `agrupar.py` | Agrupa arquivos pequenos em lotes maiores para processamento eficiente | Arquivos agrupados em `dados/gerados/agrupados/` |
| `ultra.py` | Ultra-processamento: sharding, checkpointing, otimização de datasets grandes | Dados otimizados em `dados/processed/` |
| `createjsonl.py` | Gera dataset JSONL SFT (`messages`) com pesquisa web, juiz de qualidade, Regra de Ouro, checkpoint/resume, sharding | `dados/gerados/jsonl/jsonlocal/rigel_YYYYMMDD.jsonl` |
| `saida_manager.py` | Escritor JSONL unificado (sharding 1000/arquivo) — usado por `dialogos2.py`/`rss_processor.py` com `--formato jsonl` | JSONL SFT em `dados/gerados/jsonl/<dataset>/` |

### 🔄 Coleta de Dados

| Arquivo | Função | O que produz |
|---------|--------|-------------|
| `downdata.py` | Download de datasets públicos da internet | Dados brutos em `dados/raw/` |
| `download_datasets.py` | Método alternativo de download de datasets | Dados brutos em `dados/raw/` |

### 🛠️ Utilitários

| Arquivo | Função | O que produz |
|---------|--------|-------------|
| `config.py` | Configurações centralizadas: chave DeepSeek, modelo, caminhos, tokens | Carregado por todos os módulos |
| `state.py` | Gerenciamento de estado entre execuções | Arquivo `estado_global.json` |
| `categories.py` | Definição das categorias de dados e seus prompts | Usado por `generation.py` e `dialogos2.py` |
| `utils.py` | Funções utilitárias: hash, limpeza, salvamento, descarte | Suporte a outros módulos |
| `generation.py` | Funções auxiliares de geração: prompts por categoria, detecção de resposta genérica | Prompts prontos para DeepSeek |
| `validation.py` | Validação de dados gerados: qualidade, formato, consistência | Filtro de qualidade |
| `limpeza.py` | Limpeza pesada: remove duplicatas, corrige encoding, elimina ruídos | Dados limpos em `dados/processed/` |
| `verificador.py` | Verificação de integridade dos dados | Relatório de consistência |
| `log_manager.py` | Gerenciamento centralizado de logs | Arquivos de log rotativos |

### 🌐 Tradução

| Arquivo | Função | O que produz |
|---------|--------|-------------|
| `tradutor.py` | Tradução de textos para português via API | Textos traduzidos |
| `traduza.py` | Método alternativo de tradução local | Textos traduzidos |

### 🖥️ Aplicações

| Arquivo | Função | O que produz |
|---------|--------|-------------|
| `app.py` | Aplicativo legado (Gradio) | Interface web antiga |
| `main.py` | Ponto de entrada legado | Execução de pipeline |
| `setup_env.py` | Configuração inicial do ambiente virtual | `.venv/` configurado |
| `organizar_pastas.py` | Organiza pastas de dados por tipo | Pastas reorganizadas |
| `treino_cloud.py` | Treino em nuvem (Google Colab) | Notebook + checkpoint |
| `treinov2.py` | Versão alternativa do treino | Checkpoints experimentais |

### 📋 Dashboard (rotas e serviços)

| Arquivo | Função | Endpoints |
|---------|--------|-----------|
| `dashboard/main.py` | App FastAPI principal + rotas de geração local | `/api/local-generate/*`, páginas HTML |
| `dashboard/routes/train.py` | Controle de treino: iniciar, parar, progresso | `/api/train/*` |
| `dashboard/routes/chat.py` | Chat via Ollama + fallback local PyTorch | `/api/chat/*`, `/api/chat/local/*` |
| `dashboard/routes/generate.py` | Geração via DeepSeek + scripts Python | `/api/generate/*` |
| `dashboard/routes/convert.py` | Conversão .pt → GGUF com progresso em tempo real | `/api/convert/*` |
| `dashboard/routes/debate.py` | Debate/Podcast via DeepSeek com pesquisa web | `/api/debate/*` |
| `dashboard/routes/debate_local.py` | Debate/Podcast via Ollama (modelo local) | `/api/debate-local/*` |
| `dashboard/routes/topicos.py` | Gerenciamento de tópicos: RSS, DeepSeek, sortear | `/api/topicos/*` |
| `dashboard/routes/rss.py` | Processamento de feeds RSS | `/api/rss/*` |
| `dashboard/routes/ollama.py` | Gerenciamento do servidor Ollama | `/api/ollama/*` |
| `dashboard/routes/logs.py` | Visualização de logs do sistema | `/api/log/*` |
| `dashboard/routes/diagnostico.py` | Diagnóstico e contagem de arquivos | `/api/diagnostico/*` |
| `dashboard/routes/organizar.py` | Organização de pastas de dados | `/api/organizar/*` |
| `dashboard/services/runner.py` | Execução de scripts em background com log | Usado internamente |
| `dashboard/services/monitor.py` | Monitoramento CPU, RAM, disco, Ollama | Usado internamente |
| `dashboard/services/limpeza.py` | Limpeza de texto: emojis, ANSI, espaços concatenados | Usado pelo chat e geração |
| `dashboard/services/converter_state.py` | Estado da conversão GGUF em tempo real | Usado pela rota convert |
| `dashboard/services/pesquisa.py` | Busca na web via DuckDuckGo | Usado pelo chat e debate |
| `dashboard/services/estrutura_cache.py` | 🛡️ Guardião de limites + escaneamento em background com cache e barra de % | Usado por treino/treino_local |
| `dashboard/services/recursos.py` | ⚙️ Detecção de hardware e limites PROPORCIONAIS à máquina | `config_recursos.json` |
| `dashboard/services/treino_local.py` | Treino SFT via subprocesso + bandeiras por arquivo + progresso | `/api/treino_local/*` |
| `dashboard/services/hf_datasets.py` | Busca/download/explosão de datasets HuggingFace | `/api/datasets/*` |
| `dashboard/services/ollama_deploy.py` | Backup→conversão→`ollama create` (legado — o Converter GGUF usa fluxo próprio) | — |

---

## 🖥️ Dashboard (Interface Web)

O dashboard é uma **SPA (Single Page Application)** construída com:
- **Backend:** FastAPI + Uvicorn (porta 8000)
- **Frontend:** Tailwind CSS + Alpine.js (client-side reativo)
- **Monitoramento:** psutil (CPU por núcleo, RAM, disco)
- **Temas:** Escuro (padrão) + **Alegre** (claro), alternáveis com persistência

### Funcionalidades por Aba

| Aba | Função |
|-----|--------|
| **📊 Dashboard** | Visão geral: CPU, RAM, disco, arquivos processados, log ao vivo |
| **📚 Treinamento** | Iniciar/parar treino, selecionar pastas, progresso em tempo real |
| **💬 Chat** | Conversar com o modelo via Ollama **ou** modo local PyTorch (fallback automático) |
| **📡 RSS & Web** | Processar feeds RSS, testar URLs, adicionar novos feeds |
| **🔄 Converter GGUF** | Converter .pt → GGUF com barra de progresso e log ao vivo |
| **📝 Gerar Dados** | Gerar conteúdo via DeepSeek (22 tipos). Botão "+ Novos" tópicos via RSS |
| **🖥️ Gerar Local** | Gerar via Ollama com quantidade, template/style aleatório. Scripts Python |
| **🎙️ Debate/Podcast** | Debate/podcast via DeepSeek com pesquisa web e perfis |
| **🎙️ Debate Local** | Debate/podcast via Ollama (modelo local, sem API) |
| **📋 Logs** | Visualizar logs do sistema em tempo real |

---

## ⚠️ Problemas Enfrentados e Soluções

### 1. VOCAB_SIZE vs Tokenizer Real
- **Problema:** Modelo com `VOCAB_SIZE=32000`, tokenizer com 23830 tokens → slots mortos
- **Solução:** Auto-detectado do `tokenizer.json`. `generate()` zera logits além do vocabulário real

### 2. Repetition Penalty Incorreto
- **Problema:** Logits negativos tinham penalidade invertida (aumentava repetição)
- **Solução:** Penalidade verifica sinal do logit antes de aplicar

### 3. GGUF Incompatível com Ollama (vários problemas)
- **Problema 1:** `invalid array type: 9` ao carregar GGUF no Ollama
  - **Causa:** Ollama versão 0.20.7 não suporta GGUF arrays (type 9) para `tokenizer.ggml.merges`
  - **Solução 1:** Atualizado Ollama de 0.20.7 → **0.32.5**
- **Problema 2:** `cannot find tokenizer merges in model file` após atualizar Ollama
  - **Causa:** GGUF sem `tokenizer.ggml.merges` — removido para evitar erro de array
  - **Solução 2:** Merges serializados como **STRING única** (separada por newline) em vez de ARRAY
- **Problema 3:** `check_tensor_dims: tensor 'token_embd.weight' has wrong shape`
  - **Causa:** Tensor `token_embd.weight` transposto incorretamente (esperado `[embed_dim, vocab_size]`)
  - **Solução 3:** Embedding mantido no formato original sem transposição
- **Problema 4:** `missing tensor 'output_norm.weight'` e `missing tensor 'blk.*.ffn_up.weight'`
  - **Causa:** Arquitetura `llama` do GGUF exige `output_norm.weight` (norm final) e `ffn_up.weight` (3ª projeção FFN SwiGLU). O modelo original (TransformerDecoder do PyTorch) não tem esses tensores
  - **Solução 4:** `output_norm.weight` criado como identidade (valores = 1). `ffn_up.weight` copiado de `ffn_gate` (modelo usa GELU, não SwiGLU)
- **Problema 5:** `done_getting_tensors: wrong number of tensors; expected X, got Y`
  - **Causa:** Biases nos tensores (`attn_norm.bias`, `ffn_gate.bias`, etc.) — Llama original não usa biases
  - **Solução 5:** Todos os biases removidos do mapeamento GGUF. Modelo final com **75 tensores** (estrutura idêntica ao tinyllama/llama.cpp)
- **Problema 6:** `llama-server process has terminated: exit status 1` (erro genérico ao rodar)
  - **Causa:** Accumulado de problemas 1-5 acima
  - **Solução 6:** GGUF agora é gerado pelo `converter_para_gguf.py` (v1.0.0) com: merges como string, 75 tensores sem biases, output_norm + ffn_up sintéticos. Testado com `ollama run` e `ollama ps` confirma modelo ativo
- **Problema 7 (06/08/2026 — RESOLVIDO): GGUF gera vazio/lixo em TODOS os runtimes (llama-server, Ollama, llama-cli)**
  - **Causa:** O `tokenizer.json` é BPE **ByteLevel (estilo GPT-2)** e marca espaço com `Ġ` (U+0120). O `converter_para_gguf.py` convertia `Ġ→▁` (U+2581) achando que o llama.cpp esperava `▁` — **invertido!** Com `tokenizer.ggml.model="gpt2"` o llama.cpp faz byte-encoding GPT-2 (espaço 0x20 → `Ġ`) e espera `Ġ` no vocab E nos merges. A conversão quebrava o BPE (IDs errados → saída vazia, lixo, chars geométricos ▹▾▦ e `▁` colando palavras). Confirmado no código-fonte do llama.cpp (`src/llama-vocab.cpp`: `llm_tokenizer_bpe`, `byte_encode=true`).
  - **Solução 7 (aplicada no `converter_para_gguf.py`, backup: `converter_para_gguf.py.bak_20260806`):**
    1. REMOVIDA a conversão `Ġ→▁` (tokens E merges) — manter `Ġ`;
    2. `tokenizer.ggml.pre = "gpt-2"` (pré-tokenizer correto p/ ByteLevel; antes ausente → aviso "GENERATION QUALITY WILL BE DEGRADED");
    3. `tokenizer.ggml.add_space_prefix = False` (no path BPE o padrão é false; o espaço entra via byte-encoding).
  - **Resultado:** GGUF novo (reconvertido via página `/converter`) tem 23.830 tokens, 18.380 com `Ġ`, ZERO com `▁`; `llama-cli` gera texto (~291 t/s) e **TODOS os modelos `rigelslm:*` respondem no Ollama**. Saída ainda é "frase solta" porque o modelo está ~33% treinado (esperado).

### 4. Palavras Concatenadas nas Respostas
- **Problema:** `"Olá!EusouoRigelSLM.Comopossoteajudar?"`
- **Causa:** Decoder ByteLevel sem `add_prefix_space=True` + tokenizer GGUF como `"llama"`
- **Solução:** `add_prefix_space=True` nos decoders + função `corrigir_espacos_concatenados()` no chat
- ⚠️ **Nota (06/08):** a causa raiz no GGUF era o bug do **Problema 7** (conversão `Ġ→▁`). O fix real é reconverter com o `converter_para_gguf.py` corrigido; `corrigir_espacos_concatenados()` e o `limpar_e_aviso` (com `▁`→espaço) são apenas paliativos no chat para modelos antigos.

### 5. Caracteres ANSI no Conteúdo (`[13D[K`)
- **Problema:** `ollama run` emite códigos de terminal que vazavam para o texto
- **Solução:** Função `limpar_ansi()` que remove sequências de escape

### 6. Conversão sem Feedback Visual
- **Problema:** Usuário clicava "Converter" e via apenas "Conversão iniciada"
- **Solução:** State manager `converter_state.py` + barra de progresso + polling a cada 2s

### 7. Tópicos Dependentes de DeepSeek
- **Problema:** Botão "+ Novos" só funcionava com chave DeepSeek; travava sem ela
- **Solução:** `topicos.py` com busca RSS (27+ feeds brasileiros) + fallback manual

### 8. Geração sem Quantidade
- **Problema:** Só gerava 1 item por vez; sem loop para múltiplos
- **Solução:** Campo `quantidade` (1-999) + randomização de template/estilo por iteração

### 9. Contadores Inconsistentes
- **Problema:** "Arquivos gerados" contava dados de treino, não arquivos gerados
- **Solução:** Card usa `localArquivosSalvos.length` em vez de `dados.total_arquivos`

### 10. Travas com Milhões de Arquivos (17M+)
- **Problema:** Escaneamentos (`rglob`/`glob`) materializavam listas com milhões de arquivos → `MemoryError`, telas travadas
- **Solução:** `estrutura_cache.py` — scan em THREAD com barra de %, cache persistente em disco, `walk_com_limites()` streaming (nunca materializa listas)

### 11. Hardware Varia — Limites "Fixos" Quebravam a Máquina
- **Problema:** Scan consumiu 100% de RAM + 100% de SSD (50 GB de pagefile) mesmo com limites
- **Solução:** `recursos.py` — limites **PROPORCIONAIS** (RAM, CPU, GPU, HD/SSD/NVMe), detectados na instalação e gravados em `config_recursos.json`

### 12. Guardião de Limites (memória, disco, CPU, SSD)
- **Problema:** Scan podia rodar até derrubar o sistema
- **Solução:** caps de arquivos/pastas (`SCAN_MAX_*`), pausas periódicas (`SCAN_PAUSA_*`), aborta se a memória livre cair (`MEM_MIN_LIVRE_*`), não segue junctions/symlinks (anti-loop), recusa iniciar sem memória

### 13. Loop de Reinício do Dashboard + Cascata de Abas no Chrome
- **Problema:** `run_dashboard.bat` abria o servidor, ~12s depois "caía", e a cada reinício abria outra aba → cascata + "rodinha"
- **Causa:** workers órfãos do `--reload` (multiprocessing.spawn) seguravam o socket da porta 8000; o watchdog não conseguia limpar
- **Solução:** `run_dashboard.bat` **v2.3.1** — navegador abre 1x por sessão, monitor único, limpeza de órfãos `spawn_main`, `--reload-dir dashboard`; servidor estável roda sem `--reload`

---

## 🏆 Estabilidade & Guardião de Limites (02/08/2026)

### 🛡️ Guardião de Limites (nada de "mostrar tudo")
O projeto agora **tem limites em tudo que varre o disco**:
- **Caps:** `SCAN_MAX_ARQUIVOS` / `SCAN_MAX_DIRETORIOS` — o scan **aborta graciosamente** ao atingir (`LimiteEstourado`), sem travar;
- **Memória:** `MEM_MIN_LIVRE_MB` / `MEM_MIN_LIVRE_PCT` — **recusa iniciar** scan com memória baixa e **aborta no meio** se cair (evita pagefile gigante);
- **Disco:** `DISCO_MIN_LIVRE_MB` — não grava cache sem disco livre;
- **CPU:** `CPU_MAX_USO_PCT` — o scan "respira" se o processador saturar;
- **SSD:** `SCAN_PAUSA_CADA` / `SCAN_PAUSA_SEG` — pausa periódica (evita 100% do disco);
- **Anti-loop:** nunca desce em junctions/symlinks (`os.path.isjunction`);
- **Streaming:** `walk_com_limites()` nunca materializa listas.

### ⚙️ Limites Proporcionais à Máquina
- `dashboard/services/recursos.py` **detecta o hardware na instalação** (RAM, CPU, GPU via nvidia-smi, tipo de disco) e grava limites em **percentuais** em `config_recursos.json`;
- Precedência: `config_recursos.json` < variáveis de ambiente < cálculo em runtime;
- Comandos: `python -m dashboard.services.recursos` (ver) · `--salvar` (regenerar); rastro em `logs/recursos.log`.

### ⚡ Dashboard Estável
- **Scan 100% em background** com barra de % — nunca mais trava o servidor no request;
- `run_dashboard.bat` **v2.3.1**: navegador abre **1x por sessão**, monitor único, limpeza de órfãos do `--reload`, `--reload-dir dashboard`;
- Servidor estável **sem `--reload`** (processo único, sem workers órfãos segurando a porta).

---

## �️ Qualidade do acervo & backup (18/08/2026)

Novos utilitários automáticos de qualidade e organização do acervo:

| Script | Função | Uso |
|--------|--------|-----|
| `scripts/validar_jsonl_acervo.py` | Valida a integridade do acervo JSONL (JSON válido + relatório por pasta) | `python scripts/validar_jsonl_acervo.py` |
| `scripts/tratar_datasets_brutos.py` | Tratamento AUTOMÁTICO de datasets brutos: detecta formato (messages/text/alpaca/qna), corrige mojibake (via `sanitizador_ptbr`) e converte alpaca→messages | `python scripts/tratar_datasets_brutos.py` |
| `scripts/gerar_relatorio_envio.py` | Gera relatório de envio do acervo JSONL (limpas vs brutas + avisos de duplicata) para backup no Google Drive | `python scripts/gerar_relatorio_envio.py` |

**Estrutura padrão do acervo (18/08 — `regras_pastas.py`):**
- `processed/txt/` · `processed/jsonl/` · `processed/parquet/` — uma pasta por tipo (minúsculas, por causa do Windows case-insensitive).
- Geradores → `dados/gerados/`; **TRATAMENTO** (palavra unificadora: sanitizar+limpar+verificar) → staging `dados/sanitizados/` → **promover** → `processed/<tipo>/`.

**Regras de ouro do acervo (18/08):**
- ✅ Só material `*_sanitizado` é **treino pronto** (0 mojibake real, 782.806 linhas validadas).
- ⚠️ Datasets brutos (ex.: `dominguesm_brwac`, 18 GB com mojibake) NÃO entram no treino: o SFT só aceita `messages` e o pré-treino só pastas com ≥10 `.txt` — eles ficam parados até passar pelo `tratar_datasets_brutos.py`.
- 📦 Fluxo de backup: organizar por tipo (JSONL → PARQUET → TXT) → validar → usuário envia ao Google Drive → liberar área.
- 🧠 Lição: regex de mojibake com `Ã` solto gera falso positivo (SÃO/MÃE/CÃES) — usar só duplo-encoding real.

---

## �🚀 Como Usar

### Dashboard (recomendado)

```powershell
# Iniciar servidor
python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000
# Abrir http://127.0.0.1:8000/

# Ou usar script com auto-recuperação
.\run_dashboard.bat
```

### Treinar o Modelo (SFT com JSONL — recomendado)

```powershell
# Treinar todos os datasets de trabalho
python treinar_com_jsonl.py --dados dados/gerados/jsonl

# Treinar somente os datasets promovidos (validados)
python treinar_com_jsonl.py --dados dados/processed

# Treinar UM arquivo específico
python treinar_com_jsonl.py --dados dados/gerados/jsonl --arquivo adalbertojunior_Guara_00001.jsonl

# Treinar com limite de arquivos
python treinar_com_jsonl.py --dados dados/gerados/jsonl --max-arquivos 20

# Continuar de onde parou
python treinar_com_jsonl.py --dados dados/gerados/jsonl --resume

# FILA de treino: treina todos os .jsonl de uma pasta, UM POR VEZ, salvando o
# modelo e reiniciando o LR entre cada arquivo. Modos: arquivo/completo (até o
# fim), tempo (X horas), pause (para ao achar PAUSA_SEGURA.txt).
python treinar_com_jsonl.py --caminho-pasta dados/gerados/jsonl/meu_dataset --modo-fila arquivo --epocas-por-arquivo 5
python treinar_com_jsonl.py --caminho-pasta dados/gerados/jsonl/meu_dataset --modo-fila tempo --limite-tempo 8 --epocas-por-arquivo 5
python treinar_com_jsonl.py --caminho-pasta dados/gerados/jsonl/meu_dataset --modo-fila arquivo --resume   # retoma de onde parou

# Modelo: carregado automaticamente de modelo/ (checkpoint_jsonl.pt > modelo_melhor.pt > modelo.pt)
# Bandeiras: a cada conclusão o arquivo é marcado em modelo/jsonlogs/ (0x→sem, 1x→branca, 2x→amarela, 3x+→vermelha)
# No dashboard: Treino Local mostra barra de % + ETA + flag de cada arquivo + botões ⏸️ Pausar/▶️ Retomar na fila
```

### Treinadores legados (dados .txt — não usam JSONL)

```powershell
python treino.py                        # treino .txt (pergunta/resposta)
python treino.py --resume --max-arquivos 20000
```

### Gerar / baixar datasets (createjsonl.py)

```powershell
python createjsonl.py --count 500                     # 500 exemplos (CPU: gemma2:2b)
python createjsonl.py --count 500 --gpu               # GPU/Colab (qwen2.5:7b)
python createjsonl.py --count 500 --usar-topicos-txt  # usa topicos.txt (RSS)
python createjsonl.py --count 100 --dry-run           # testa sem salvar
python createjsonl.py --hf-dataset adalbertojunior/Guara  # baixa e explode do HuggingFace
python createjsonl.py --download "https://.../dataset.zip" # baixa de URL e explode
# Saída: dados/gerados/jsonl/jsonlocal/rigel_YYYYMMDD.jsonl (nunca sobrescreve)
```

### Converter .txt legados (pergunta/resposta) para JSONL SFT

Seus arquivos `.txt` antigos (ex.: `Pergunta: ...` / `Resposta: ...` e artigos) podem
ser transformados no formato `messages` — ensinando o modelo a RESPONDER, não só a
prever a próxima letra:

```powershell
# Converter uma pasta inteira (detecta Pergunta/Resposta E artigos)
python converter_txt_jsonl.py --pasta dados/processed --saida txt_convertido

# Só arquivos com marcadores (pula artigos)
python converter_txt_jsonl.py --pasta dados/processed/canarim --saida canarim_sft --apenas-qna

# Teste rápido (limita a 100 arquivos)
python converter_txt_jsonl.py --pasta dados/processed --saida txt_convertido --max-arquivos 100

# O que ele faz: adiciona o system prompt do Rigel, corrige mojibake, dedup,
# e explode em arquivos de 1000 exemplos → dados/gerados/jsonl/<saida>/
# (aparece automaticamente no dashboard → Treino Local)
```

### Chat com o Modelo

```powershell
# Via terminal (modo interativo - PyTorch direto)
python chat.py --temperature 0.8 --max-tokens 200

# Modo one-shot (para chamadas de programa)
python chat.py --one-shot "Qual a capital do Brasil?"

# Via Ollama (após converter para GGUF)
ollama run rigelslm "Qual a capital do Brasil?"

# Via dashboard (recomendado)
# Acesse http://127.0.0.1:8000/chat
```

### Converter para GGUF e usar no Ollama

```powershell
# 1. Gerar GGUF (F32) com o conversor v1.0.0
d:/Projetos/rigelllm/.venv/Scripts/python.exe converter_para_gguf.py --quant F32 --output gguf/rigelslm.gguf --no-modelfile

# 2. Criar Modelfile
echo "FROM D:\Projetos\rigelllm\gguf\rigelslm.gguf" > gguf/Modelfile

# 3. Criar modelo no Ollama
ollama create rigelslm -f gguf/Modelfile

# 4. Testar
ollama run rigelslm "Olá"
```

**Requisitos:** Ollama >= 0.32.5 (versões anteriores não suportam o formato GGUF gerado).

### 🤖 Disponibilizar ao Ollama (no dashboard)

Abra o dashboard → **Converter GGUF** → botão **"Criar no Ollama"** (por GGUF) ou use a **Conversão rápida**:

1. Converte o modelo .pt escolhido para GGUF
2. Cria/atualiza o modelo `rigelslm` no Ollama → pronto: `ollama run rigelslm`

Manual (terminal):

```powershell
python converter_para_gguf.py --model modelo/modelo_melhor.pt --quant Q4_K_M
ollama create rigelslm -f gguf/Modelfile.rigelslm_Q4_K_M
ollama run rigelslm
```

### 💾 Backups do modelo (nunca perca o modelo.pt)

O sistema é cauteloso: antes de **qualquer** sobrescrita de `modelo.pt`/`modelo_melhor.pt`
(treino, restauração, conversão), uma cópia é guardada em `modelo/backups/` com timestamp.

**Via dashboard:** Treino Local → seção "Backups do modelo" → Fazer backup / Restaurar.

**Via backend:**

```powershell
python modelo_backup.py listar                  # ver os backups
python modelo_backup.py criar                   # backup manual agora
python modelo_backup.py restaurar modelo_20260802_034457.pt   # restaurar (guarda o atual antes)
```

**Recuperação rápida (se o modelo ficar ruim):**

1. `python modelo_backup.py listar` → escolha o backup anterior
2. `python modelo_backup.py restaurar <arquivo>`
3. O modelo atual (ruim) é guardado automaticamente em `backups/pre_restauro_*` antes de ser substituído

### Gerar Dados Sintéticos

```powershell
# Via dashboard
# http://127.0.0.1:8000/gerar_dados (DeepSeek)
# http://127.0.0.1:8000/gerar_local (Ollama - geração em lote)

# Via terminal
python dialogos2.py --quantidade 100 --tipo artigo
python dialogos.py --quantidade 500 --tipo auto --limite 5.00
```

---

## 💰 Custo da Geração com DeepSeek

| Tipo | Preço (por 1M tokens) |
|-----|----------------------|
| Entrada (prompt) | $0.14 |
| Saída (resposta) | $0.28 |

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

## 📋 Histórico de Versões

### v1.0.5 (05/08/2026) - Planejada
- 🔜 Próxima versão planejada

### v1.0.4 (04/08/2026) - Planejada
- 🔜 Próxima versão planejada

### v1.0.3 (03/08/2026) - Planejada
- 🔜 Próxima versão planejada

### v1.0.2 (02/08/2026) - Planejada
- 🔜 Próxima versão planejada

### v1.0.1 (01/08/2026) - Lançada
- ✅ **`createjsonl.py`**: nova fonte de tópicos via `--usar-topicos-txt`
  - `topicos.txt` (fonte RSS/dashboard) passa a ser usado como assuntos extras: ~25% dos exemplos (`TOPICOS_TXT_CHANCE`)
  - Filtragem automática de manchetes (`_filtrar_topico_externo`): aspas, `título: subtítulo`, separador ` - `, começo numérico, `, segundo`, verbos de notícia (`VERBOS_MANCHETE`), >90 caracteres e já-perguntas; + sanitização (`TOPICOS_BLOQUEADOS`) e dedup
  - Templates próprios (`TEMPLATES_TOPICOS_EXTERNOS`) + artigo inicial minúsculo na pergunta; categoria virtual `topicos_externos` nos contadores/resumo
  - Validado: **520 tópicos aproveitáveis** do `topicos.txt` atual
- ✅ Correção: `argparse` quebrava com `%` no help do `--usar-topicos-txt` (escapado como `%%`)
- ✅ **Geração de dataset JSONL com `llama3.2:3b`** (substituiu `gemma2:2b`, que descartava 100% por não cumprir a Regra de Ouro)
  - Primeiros exemplos aprovados com **nota 10.0** (regra de ouro + uso de contexto)
  - `--max-tokens 1000` para evitar respostas truncadas
  - ETA estimado ~12h para 500 exemplos na CPU (2 chamadas por exemplo)

### v1.0.0 (31/07/2026) - Última
- ✅ Reinício da numeração de versões (6.5.1 → 1.0.0)
- ✅ Todos os arquivos do projeto padronizados para a versão 1.0.0
- ✅ Histórico de versões reescrito com incrementos planejados (1.0.1, 1.0.2, ...)

### v6.5.0 (29/07/2026)
- ✅ **Debate Local**: nova aba de debate/podcast via Ollama
- ✅ **Gerenciamento de Tópicos**: API própria com RSS + DeepSeek (independe de chave)
- ✅ **Geração em Lote**: campo quantidade (1-999) com loop + random template/estilo
- ✅ **Tema "Alegre"**: tema claro alternável com persistência (localStorage)
- ✅ **Fallback Local**: chat usa modelo PyTorch direto se Ollama falhar
- ✅ **Barra de Progresso GGUF**: percentual, estágio, log ao vivo, polling 2s
- ✅ **Lista de Arquivos**: feedback visual com nome, caminho, tamanho, link clicável
- ✅ **Limpeza ANSI**: remoção de códigos de escape do `ollama run`
- ✅ **Correção de Espaços**: palavras concatenadas corrigidas automaticamente
- ✅ **chat.py melhorado**: métricas de treino, barra de maturidade, comando `/stats`
- ✅ **Salvamento Automático**: arquivos gerados via Ollama salvos em `gerados_local/`
- ✅ **Timeout Aumentado**: 300s para geração de múltiplos itens

### v6.4.6 (25/07/2026)
- ✅ `VOCAB_SIZE` auto-detectado do tokenizer
- ✅ Repetition penalty corrigido para logits negativos
- ✅ Dashboard com FastAPI + Tailwind + Alpine.js
- ✅ Chat com Ollama + modo local
- ✅ Conversão GGUF com suporte a 13 quantizações
- ✅ RSS com 27+ feeds brasileiros

### v6.0.0 (Junho/2026)
- ✅ Primeira versão estável do modelo
- ✅ Tokenizer BPE ByteLevel treinado do zero
- ✅ Pipeline de treino completo
- ✅ Geração de dados sintéticos via DeepSeek
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

O texto completo está em [`LICENSE`](LICENSE).

---

## 🤝 Contribuições

Contribuições são bem-vindas! Abra issues ou envie pull requests no GitHub.

---

**Última atualização:** Agosto de 2026  
**Versão do README:** 3.1

## 💡 Treino Eficiente com Múltiplas Pastas

Em vez de treinar pasta por pasta, use vírgulas para combinar:

```powershell
# Treina com várias pastas de uma vez
python treino.py --dados tucano,ultrachat,blogset,guara,canarim --max-arquivos 5000 --epochs 30
```

Para listar todas as pastas disponíveis:
```powershell
python treino.py --list-pastas
```

Para ver o help completo:
```powershell
python treino.py --help
```