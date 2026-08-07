# 🧪 PIPELINE DE TESTES — RigelSLM (07/08/2026)

> Função: registrar TODOS os eventos (bons e ruins) durante a análise visual (mobile),
> execução dos módulos e leitura de logs. Depois cada item é tratado.

## Critérios de análise por página (mobile 375px)
1. **Overflow**: nada sai da linha de visão (scrollWidth == clientWidth)
2. **Botões**: dentro da área, com tooltip (`title`), um ícone só, tocáveis
3. **Rolagem**: menu/cards/abas roláveis sem travar
4. **Carregamento**: spinner vira conteúdo; sem "(sem saída)" eterno
5. **Erros de console**: nenhum erro JS no console
6. **Feedback**: barra de % real em tarefa longa

## Registro (append a cada evento)
`- [BOM|RUIM] Página | O que aconteceu | Evidência`

---

## 1. ANÁLISE VISUAL MOBILE (15 páginas — 375px)

### Resultado da varredura automática
- ✅ **BOM — Overflow = 0 em TODAS as 15 páginas**: `/`, `/datasets`, `/treino_local`, `/chat`, `/converter`, `/treinamento`, `/gerar_local`, `/gerar_dados`, `/executor`, `/scrap`, `/tratamento`, `/rss`, `/logs`, `/debate`, `/converter_txt` — nada sai da linha de visão.
- ✅ **BOM — Home sem erros de console** (9 botões, 27 cards).
- ⚠️ **RUIM — Botões SEM tooltip (viola a regra do usuário)**, por página:
  - `/datasets`: `Buscar` + 4 chips de busca (`# portuguese instruction` etc.)
  - `/treino_local`: `🔍 Ler estrutura`, `Atualizar`, `✅ Promover p/ processed` (3x)
  - `/converter`: `Criar no Ollama` (2x)
  - `/treinamento`: `💾 Salvar configurações`, `🔍 Ler estrutura` (2x), `Todas`, `Limpar`
  - `/gerar_local`: `🎯 Gerar`, `⟳ Recarregar`, `Gerar`
  - `/gerar_dados`: `⟳ Recarregar`, `+ Novos`, `🚀 Gerar via API`
  - `/executor`: `Executar no backend`, `Parar todas`, `Atualizar`
  - `/rss`: `▶️ Processar todos`, `Selecionar todos`, `Limpar`
  - `/logs`: `Atualizar` + itens de seleção de log
  - `/debate`: seletores + `🎙️ Gerar Debate`

### Screenshots por página
(pendente salvar prints em `images/prints/`)

## 2. EXECUÇÃO DOS MÓDULOS

### Download end-to-end (pipeline principal)
- ✅ **BOM — Download completo** (`nelsondiasandre/portuguese-qa-instruct-500`): baixou 400 exemplos em ~14s, explodiu, e o estado chegou a 100% com destino claro.
- 🔴 **RUIM ENCONTRADO — dataset PRÉ-TREINO (`text`)**: a sanitização descartou os 400 (não entende `text`) e o sistema dizia "concluído com dados em X" com pasta inexistente. **CORRIGIDO**: pipeline agora detecta o formato e marca `etapa="aviso"` com mensagem clara ("Dataset PRÉ-TREINO — não serve para SFT; use treino.py ou dataset com messages"). ✅ Validado.
- ⚠️ **OBS — polling intenso**: página `/converter_txt` faz polling de várias rotas a cada ~1s + `GET /openapi.json` em loop — carga desnecessária (a revisar).
- 🧹 Teste limpo: 2 pastas pré-treino em `dados/gerados/jsonl/rigeljsonl_20260807_1750/1753` (apagar ou manter — decisão do usuário).

### Treinamento
- ✅ **BOM — Treino JSONL end-to-end**: `treinar_com_jsonl.py` com 1 arquivo/20 exemplos/1 época concluiu em 0,9 min (5 batches, loss ~7,16, "TREINO SFT CONCLUÍDO", exemplo de geração emitido). Modelo bom (`modelo_melhor.pt`) preservado (o teste só tocou `modelo.pt`, restaurado).
- ✅ **BOM — Feedback de material**: log mostrou `⚠️ Material BAIXO: 1 arquivo(s)...` — aviso funcionando.

### Chat
- ✅ **BOM — Envio de mensagem via Ollama**: `/api/chat/send` respondeu "A capital do Brasil é Brasília." em 13,8s (llama3.2:3b).
- ✅ **BOM — Salvamento de conversa**: 2 pares salvos (já validado).

### Executor
- ✅ **BOM — Gestor funciona**: inicia atividade (verificar_encoding), roda em subprocesso, captura erro com mensagem clara, estado persistido.
- 🔴 **RUIM — Script `verificar_encoding_jsonl.py`**: recebeu caminho de ARQUIVO mas tratou como PASTA ("Pasta não encontrada: ..._00001.jsonl") → exit 1. Pendência: ajustar o script para aceitar arquivo OU pasta.

### RSS
- ✅ **BOM — RSS em volume funciona**: às 11:39 o dashboard processou 20 notícias (salvou curtos/longos, total 454 arquivos gerados acumulados).
- 🔴 **RUIM — Teste de 2 notícias (17:57)**: o log parou em "Processando as primeiras 2..." e o processo morreu SEM registrar conclusão/erro nem salvar arquivos. **Pendência: RSS precisa registrar fim/falha do subprocesso** (senão "morre calado").

### Módulos (API)
- ✅ **BOM — Converter**: `pode_converter=True`, recomendado `modelo_melhor.pt`, 2 GGUF existentes.
- ✅ **BOM — Tópicos**: lista com dezenas de tópicos PT-BR (filosofia, história, tecnologia...).
- ✅ **BOM — Convert status**: lista modelos (modelo_melhor.pt recomendado 222,5 MB; GGUF existentes: rigelslm_f16 111,5 MB + rigelslm_Q4_K_M 36,4 MB).
- ✅ **BOM — Train progresso**: sem treino em andamento (estado correto).
- ✅ **BOM — Tratamento formatos**: matriz completa (jsonl→sanitizar, parquet/csv→limpeza_leve, txt→limpeza_encoding).
- 🔴 **RUIM — Dados painel bloqueado por "memória baixa" FALSO**: com **21,6 GB livres (68%)**, o guardião RECUSOU a varredura porque `MEM_MIN_LIVRE_PCT=70` exige ≥70% (22,4 GB). **Limite agressivo demais** → painel de dados mostra tudo 0 sem explicação. **Corrigir**: ajustar `config_recursos.json` (`MEM_MIN_LIVRE_PCT` para ~30-40%) ou a lógica.

### Serviços básicos
- ✅ **BOM — Ollama**: status `running` (PID 4548) + `POST /api/chat/test` respondeu "OK." com `llama3.2:3b` em ~6s.
- ✅ **BOM — RSS status**: `ollama_online: true`, 7 modelos listados (rigelslm, llama3.2, gemma2, tinyllama, qwen2.5-coder).
- ✅ **BOM — Scrap testar** (`https://pt.wikipedia.org/wiki/Rio_de_Janeiro`): extraiu **22.016 palavras, idioma `pt`, fonte `trafilatura`** em ~10s. Sem U+FFFD. (O mojibake visto no terminal PowerShell é de EXIBIÇÃO do console, não do dado.)
- ⚠️ **OBS — Home mostrou "Ollama: Offline"** num dos carregamentos (mas o status real é running) — verificar timing/estado do frontend.

## 3. ANÁLISE DE LOGS
(em andamento — correlação entre logs e eventos)

### Logs encontrados (logs/)
- `requests.log` (NOVO, middleware) — está registrando tudo ✅
- `dashboard.log` — só registra inícios de operações; NÃO registra erros (corrigido com o middleware)
- `uvicorn.log` — parado desde 07/10 (console não é persistido)
- `explosao.log` — 0,01 MB (corrigido)
- `treino.log`, `treinar_jsonl.log`, `sanitizacao.log`, `rss.log` — ativos conforme operações

### Correlação (bugs → logs)
- "failed to fetch" do usuário = event loop travado (rota bloqueante) → agora o `requests.log` mostra o tempo real de cada rota (ex.: diagnostico 1425ms) → qualquer rota >3s é suspeita.
- Botões sem tooltip catalogados na seção 1 → correção pendente.

## 4. PLANO DE TRATAMENTO
(itens bons/ruins → correção)

### Itens a corrigir (da análise)
1. ✅ **CORRIGIDO — Guardião de memória agressivo**: `MEM_MIN_LIVRE_PCT` 70%→30% em `config_recursos.json` (bloqueava scans com 21 GB livres). Aplicar com reinício do dashboard.
2. ✅ **CORRIGIDO — Botões do `/converter_txt`**: empilham no mobile (266×44px cada, largura total), 1 ícone por botão (Converter tinha fa + emoji ▶️ duplicado).
3. ⏳ **PENDENTE — Tooltips**: adicionar `title` nos ~25 botões sem tooltip catalogados na seção 1 (9 páginas).
4. ⏳ **PENDENTE — Modelo configurável** (começar do zero com tamanho escolhido): tornar `EMBED_DIM`/`NUM_LAYERS`/`NUM_HEADS` configuráveis (hoje fixos em `treino.py:94-98`).
5. ⏳ **PENDENTE — Home "Ollama: Offline" intermitente**: verificar timing do frontend.
