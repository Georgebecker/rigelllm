# 🧪 Roteiro de Testes — RigelSLM (pipeline JSONL + dashboard)

> Data: 02/08/2026 · Versão: 1.0.0
> Teste aos poucos, em ordem. Cada item diz **o quê**, **onde**, e **onde encontrar o resultado**.

---

## 📌 Símbolos
- 🖥️ **Terminal** = PowerShell na raiz `d:\Projetos\rigelllm`
- 🌐 **Dashboard** = `http://127.0.0.1:8000` (subir com `python -m uvicorn dashboard.main:app --host 127.0.0.1 --port 8000 --reload`)
- 📂 **Pasta** = Windows Explorer

---

## 1️⃣ Geração → JSONL (o pipeline novo)

| # | O quê testar | Onde | Como | Resultado esperado (onde encontrar) |
|---|--------------|------|------|--------------------------------------|
| 1.1 | Gerar diálogos JSONL (saudação, sem custo) | 🖥️ Terminal | `python dialogos2.py --tipo saudacao --quantidade 3 --formato jsonl --pasta-jsonl teste_saud` | Mensagem `✅ 3 saudações salvas em dados\gerados\jsonl\teste_saud/` · arquivo em `dados/gerados/jsonl/teste_saud/teste_saud_0001.jsonl` |
| 1.2 | Conferir o formato do exemplo | 🖥️ Terminal | `Get-Content "dados/gerados/jsonl/teste_saud/teste_saud_0001.jsonl" -TotalCount 1` | JSON com `"messages"`: roles `system`, `user`, `assistant` |
| 1.3 | Gerar artigo via Ollama (sem custo DeepSeek) | 🖥️ Terminal | `python dialogos2.py --tipo artigo --quantidade 1 --formato jsonl --modelo ollama --pasta-jsonl teste_artigo` | Arquivo em `dados/gerados/jsonl/teste_artigo/` com pergunta derivada ("Escreva um artigo...") |
| 1.4 | Gerar via dashboard (seletor 📦 JSONL) | 🌐 Dashboard → **Gerar Local** | Card "Diálogos v2" → seletor **📦 JSONL** → Gerar | Nota verde + saída em `dados/gerados/jsonl/dialogos2/` (aparece no Treino Local) |
| 1.5 | RSS → JSONL | 🖥️ Terminal | `python rss_processor.py --quantidade 3 --formato jsonl --pasta-jsonl teste_rss` | JSONL em `dados/gerados/jsonl/teste_rss/` (user=título, assistant=resumo) |

## 2️⃣ Conversão de TXT legados → JSONL

| # | O quê testar | Onde | Como | Resultado esperado (onde encontrar) |
|---|--------------|------|------|--------------------------------------|
| 2.1 | Converter uma pasta pequena | 🖥️ Terminal | `python converter_txt_jsonl.py --pasta dados/processed/canarim --saida canarim_sft --apenas-qna` | JSONL em `dados/gerados/jsonl/canarim_sft/` com pares Pergunta/Resposta |
| 2.2 | Converter com limite (seguro) | 🖥️ Terminal | `python converter_txt_jsonl.py --pasta dados/processed/Artigo --saida artigos_sft --max-arquivos 2` | Poucos arquivos (limite) em `dados/gerados/jsonl/artigos_sft/`, artigos usam o título como pergunta |

## 3️⃣ Validação / Promoção (separação TXT/JSONL)

| # | O quê testar | Onde | Como | Resultado esperado (onde encontrar) |
|---|--------------|------|------|--------------------------------------|
| 3.1 | Dataset aparece na lista | 🌐 Dashboard → **Treino Local** | Abrir a página | Lista mostra `teste_saud`, `canarim_sft` etc. (via cache, abre na hora) |
| 3.2 | Barra "Ler estrutura" | 🌐 Dashboard → **Treino Local** | Botão **🔍 Ler estrutura** | Barra de % com pasta atual; ao concluir, lista atualiza. **Nunca mais trava a página** |
| 3.3 | Promover p/ processed | 🌐 Dashboard → **Treino Local** | Selecionar dataset → **✅ Promover p/ processed** | `dados/processed/jsonl/<nome>/` com **só arquivos válidos**; origem mantém/remove inválidos |
| 3.4 | Separar TXT/JSONL | 📂 Pasta | Conferir `dados/gerados/jsonl/` e `dados/processed/jsonl/` | **Nenhum** `.txt` dentro dessas pastas |

## 4️⃣ Treino SFT

| # | O quê testar | Onde | Como | Resultado esperado (onde encontrar) |
|---|--------------|------|------|--------------------------------------|
| 4.1 | Treinar 1 arquivo pequeno | 🖥️ Terminal | `python treinar_com_jsonl.py --dados dados/gerados/jsonl/teste_saud --max-arquivos 1` | Loss descendo, barra de % no dashboard (se aberto), modelo em `modelo/modelo_melhor.pt` |
| 4.2 | Barra de progresso do treino | 🌐 Dashboard → **Treino Local** | Iniciar treino de um arquivo | Barra verde com %, época/passo/loss/LR/ETA em `modelo/jsonlogs/progresso.json` |
| 4.3 | Parar treino | 🌐 Dashboard → **Treino Local** → 🖥️ Console → ⏹️ Parar | Clicar Parar durante treino | `taskkill /T` mata o processo; arquivo **NÃO** marcado |
| 4.4 | Marcador de treinado | 🌐 Dashboard → **Treino Local** | Após treino concluir | Arquivo marcado (branca/amarela/vermelha) em `modelo/jsonlogs/<dataset>.json` |
| 4.5 | Retomar (`--resume`) | 🖥️ Terminal | `python treinar_com_jsonl.py --dados ... --resume` | Continua do `modelo/checkpoint_jsonl.pt` |

## 5️⃣ Backup e Ollama

| # | O quê testar | Onde | Como | Resultado esperado (onde encontrar) |
|---|--------------|------|------|--------------------------------------|
| 5.1 | Fazer backup | 🌐 Dashboard → **Treino Local** → 💾 Backups → 📦 Fazer backup agora | 1 clique | `modelo/backups/<nome>_YYYYMMDD_HHMMSS.pt` |
| 5.2 | Restaurar (zona de perigo) | 🌐 Dashboard → **Treino Local** → 💾 Backups → Recuperar | Escolher backup + digitar **RESTAURAR** | Modelo restaurado; atual guardado como `pre_restauro_*` |
| 5.3 | Disponibilizar ao Ollama | 🌐 Dashboard → **Converter GGUF** → **Criar no Ollama** | Botão **Criar no Ollama** (ou conversão rápida) | `ollama run rigelslm` responde |

## 6️⃣ Desempenho / Estabilidade (após tudo)

| # | O quê testar | Onde | Como | Resultado esperado |
|---|--------------|------|------|--------------------|
| 6.1 | Aba Treino Local abre rápido | 🌐 Dashboard | Abrir `/treino_local` | Abre **instantânea** (dados do cache), mesmo com 17M de .txt no disco |
| 6.2 | Aba Treinamento abre rápido | 🌐 Dashboard | Abrir `/treinamento` | Abre na hora (cache); botão "Ler estrutura" mostra barra % (2–3 min em background) |
| 6.3 | Pylance não trava | VS Code | Editar um `.py` | Sem barrinha infinita (exclusões em `.vscode/settings.json`) |
| 6.4 | Nada mistura TXT/JSONL | 📂 Pasta | Rodar gerador txt e conferir | TXT em `dados/gerados/curtos/` etc.; JSONL sempre em `*/jsonl/*` |

---

## ⚠️ Armadilhas conhecidas

- **Nunca** `list(glob(...))` em `dados/` — são 17M de arquivos → `MemoryError`. Use `os.walk` incremental.
- **Não edite `.py` durante um treino** com `--reload` ativo — mata o subprocesso do treino.
- `teste_artigo` via `--modelo ollama` pode sair vazio se o Ollama não responder (a pasta vazia é limpa sozinha — normal).
- Emojis no terminal Windows: todos os scripts já usam `reconfigure(utf-8)`.
