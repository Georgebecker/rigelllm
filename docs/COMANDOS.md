# 🧭 Super Menu de Comandos — RigelSLM (FAQ)

> Quando precisar fazer **X**, use o comando **Y**. Este é o guia rápido de
> referência do projeto — vale para terminal (Python) e para o dashboard.

---

## 🎯 Gerenciador principal

| O que é | Qual é |
|---|---|
| **Orquestrador geral** (setup, treino, dashboard, Ollama) | `python rigel.py` |
| **Servidor web** (o dashboard inteiro) | `run_dashboard.bat` (watchdog) ou `uvicorn dashboard.main:app --port 8000` |
| **CLI do gerador de dados** (via API DeepSeek, com limite de custo) | `python main.py` |
| **Teste do modelo no terminal** | `python chat.py` |
| **Teste do modelo na web (Gradio)** | `python app.py` |

---

## ⚙️ Ambiente / Instalação

| Quando precisar | Comando |
|---|---|
| Configurar o ambiente do zero | `setup.bat` (Windows) ou `bash setup.sh` (Linux) |
| Configurar só o Python (venv, CUDA) | `python setup_env.py` |
| Preparar variáveis do projeto | copie `.env.template` → `.env` e preencha |
| Verificar se os serviços estão no ar (ping real) | `python verificador.py` |
| Desativar telemetria | `desativar_telemetria.bat` |
| Iniciar o Ollama | `iniciar_ollama.ps1` ou `ollama serve` |

---

## 📥 Dados: baixar / preparar

| Quando precisar | Comando |
|---|---|
| Baixar e preparar várias fontes p/ `processed` | `python download_datasets.py` |
| Baixar datasets do HuggingFace para `.txt` | `python ultra.py` |
| Baixar dataset específico (ex.: ultrachat) | `python downdata.py` |
| Processar feeds RSS (resumo 100% local via Ollama) | `python rss_processor.py` |
| Preparar/qualificar dados | `python preparar_dados.py` |
| Organizar pastas (limite 5000 arqs/pasta) | `python organizar_pastas.py` |
| Dividir pastas grandes | `python dividir_pastas.py` |
| Agrupar pares Pergunta/Resposta em lotes | `python agrupar.py` |

---

## 🧼 Limpeza / Sanitização / Qualidade

| Quando precisar | Comando |
|---|---|
| **Sanitizar PT-BR (ABNT2)** — portão de qualidade | `python sanitizador_ptbr.py` |
| Corrigir encoding de `.txt` p/ UTF-8 | `python limpeza.py` |
| Limpeza leve de datasets (parquet) | `python limpeza_leve_rigel_v2.py` |
| Verificar as regras de organização | `python regras_ouro.py` |
| Validar qualidade de textos/diálogos | `python validation.py` |

---

## 🔄 Conversão TXT → JSONL (SFT)

| Quando precisar | Comando |
|---|---|
| Converter uma pasta de `.txt` p/ JSONL | `python converter_txt_jsonl.py --pasta dados/processed` |
| Converter limitando exemplos/arquivos | `python converter_txt_jsonl.py --pasta pasta --max-exemplos 10000 --max-arquivos 100` |
| **Pelo dashboard** | Página `/treinamento` → marcar pastas TXT → botão **"🔄 Converter em JSONL"** (sanitiza e copia p/ `processed/jsonl` automaticamente) |

---

## 📚 Geração de dados sintéticos

| Quando precisar | Comando |
|---|---|
| Gerar dados via API (CLI com limite de custo) | `python main.py` |
| Gerar dados sintéticos v2 (intenções cognitivas) | `python dialogos2.py` |
| Gerar datasets JSONL SFT (com pesquisa web + Ollama) | `python createjsonl.py` |
| Gerar em massa local via Ollama (templates) | `python scripts/gerar_massa_local.py --modelo llama3.2:1b --repeticoes 1` |
| Gerar conteúdo via API DeepSeek (núcleo) | `python generation.py` |

---

## 🏋️ Treino

| Quando precisar | Comando |
|---|---|
| **Treino TXT** (causal, base do modelo) | `python treino.py --dados dados/processed --no-interactive` |
| **Treino SFT JSONL** (loss só no assistant) | `python treinar_com_jsonl.py --dados dados/gerados/jsonl` |
| **Treino PARQUET** | `python treinoparquet.py --dados dados/processed --no-interactive` |
| Treino otimizado (épocas por pasta, early stop) | `python treinov2.py` |
| Treino para Colab/GPU (T4) | `python treino_colab.py` |
| Treino auto-ajustado ao ambiente (Colab/AWS/Kaggle) | `python treino_cloud.py` |
| **Pelo dashboard** | Página `/treinamento` → marcar pastas → **▶️ Treinar** |
| Backup de segurança do modelo antes de treinar | automático (`modelo_backup.py`) |

---

## 🧠 Modelo / GGUF / Ollama

| Quando precisar | Comando |
|---|---|
| Converter `.pt` → GGUF (com quantização) | `python converter_para_gguf.py` |
| Fazer backup manual do modelo | `python modelo_backup.py` |
| Ver modelos no Ollama | `ollama list` |
| Rodar o modelo no chat (web) | `python app.py` |
| **Pelo dashboard** | Página `/converter` (GGUF) e `/chat` (modelos) |

---

## 📦 Distribuição

| Quando precisar | Comando |
|---|---|
| Empacotar o projeto num ZIP (sem dados/env) | `python deploy_package.py` |
| Ver o que entraria no pacote (sem criar) | `python deploy_package.py --dry-run` |
| Empacotar para outra pasta | `python deploy_package.py --dest C:\destino` |

---

## 🧪 Diagnóstico / Logs

| Quando precisar | Comando |
|---|---|
| Auditoria completa das rotas/páginas do dashboard | `python scripts/auditar_dashboard.py --base http://127.0.0.1:8000` |
| Verificar encoding de jsonl/pasta | `python scripts/verificar_encoding_jsonl.py caminho` |
| Ver logs do sistema | página `/logs` do dashboard ou `logs/` |
| Ver o changelog das sessões | `docs/changelog.md` |

---

## 🖥️ Páginas do Dashboard (rotas)

| Página | URL | Para que serve |
|---|---|---|
| Home | `/` | Estado real do modelo/treino, hardware, atalhos |
| Chat | `/chat` | Conversar (Ollama ou modelo local), gerenciar modelos |
| Treinamento | `/treinamento` | Selecionar dados e **treinar** (txt/jsonl/parquet) + **converter TXT→JSONL** |
| Converter GGUF | `/converter` | `.pt` → GGUF + criar no Ollama |
| Gerar Dados | `/gerar_dados` | Geração sintética (DeepSeek) |
| Gerar Local | `/gerar_local` | Geração local via Ollama (templates) + **geração em massa** |
| Datasets HF | `/datasets` | Buscar/baixar datasets PT-BR do HuggingFace |
| Scrap | `/scrap` | Extrair conteúdo de sites |
| Tratamento | `/tratamento` | Sanitizar/limpar dados em lote (jsonl→ABNT, parquet→leve) |
| Treino Local | `/treino_local` | Treino com bandeiras por arquivo |
| Google Colab | `/treino_colab` | Gerar notebook configurado p/ Colab |
| Debate/Podcast | `/debate` e `/debate_local` | Debates via DeepSeek ou modelos locais |
| Executor | `/executor` | **Executar todas as atividades** do backend (sanitizar, limpar, converter...) |
| Logs | `/logs` | Visualizar logs com métricas |
| Converter TXT | `/converter_txt` | Conversão TXT→JSONL dedicada |

---

## ❓ Perguntas rápidas (FAQ)

| Pergunta | Resposta |
|---|---|
| O modelo não responde no chat | Verifique o Ollama (`ollama list`) ou use o modo local (`modelo.pt`) |
| O treino TXT trava mostrando menu | Use **`--no-interactive`** SEMPRE (ou inicie pelo dashboard) |
| O dashboard não recarrega mudanças | O `--reload` do uvicorn desta máquina não recarrega → **reinicie o servidor** |
| Quero treinar no Colab | Copie `treino.py`, `treinar_com_jsonl.py`/`treinoparquet.py`, `tokenizer/`, `modelo/` e `dados/processed/jsonl/` para o Drive |
| Os GGUF decodificam vazio no Ollama | Bug conhecido da lib gguf → use o **modelo PyTorch local** (`modelo.pt`) no chat |
| Dados "sujos" vão para o treino? | Nunca — todo dado passa por sanitização (ABNT2) antes de `processed` |
| Como ver o que cada script faz? | Leia o cabeçalho (docstring) do arquivo, ou veja o mapa no `README.md` |
