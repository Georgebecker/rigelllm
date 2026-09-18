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

### Treino TXT
- 🔴 **RUIM — TRAVAVA 2x (bug grave "trava sem sentido")**: `treino.py --no-interactive` ficava preso em `input()` mesmo em modo não-interativo:
  1. `"Continuar de onde parou? (s/N):"` (linha ~1112) — processo preso com CPU 0/s e worker 1,1 GB RAM.
  2. `"👉 Digite o número da opção (ou 'reset'):"` em `perguntar_continuar_apos_epocas` (linha ~409) — após completar as épocas.
- ✅ **CORRIGIDO**: ambas as chamadas agora checam `args.no_interactive` — em modo não-interativo não perguntam: checkpoint vira "não continuar" e épocas concluídas finalizam automaticamente.
- ✅ **BOM — Treino TXT end-to-end**: `treino.py --dados dados/processed/Cronicas --max-arquivos 1 --batch-size 4 --no-interactive` completou 20 épocas + early stopping, salvou `modelo/modelo.pt` e **terminou sozinho com EXIT 0** (sem travar).

### Conversão GGUF
- ✅ **BOM — Conversão completa**: `converter_para_gguf.py --model modelo/modelo_melhor.pt --quant Q4_K_M` → 75 tensores mapeados, tokenizer exportado (23.830 tokens, 23.688 merges), base F16 111,55MB em 0,75s, quantização Q4_K_M real via llama-quantize → 36,39MB. "CONVERSÃO CONCLUÍDA".
- ⚠️ **OBS — `--output` ignorado na etapa de quantização**: o GGUF base respeita `--output`, mas o quantizado sempre salva como `rigelslm_Q4_K_M.gguf` (padrão), sobrescrevendo o existente. Menor (a revisar se vale corrigir).

### Chat
- ✅ **BOM — Envio de mensagem via Ollama**: `/api/chat/send` respondeu "A capital do Brasil é Brasília." em 13,8s (llama3.2:3b).
- ✅ **BOM — Salvamento de conversa**: 2 pares salvos (já validado).
- ✅ **BOM — Salvar conversa pelo dashboard (07/08 tarde)**: enviei "Me conte uma curiosidade sobre o Brasil" via chat → streaming completo → cliquei 💾 → `dados/gerados/jsonl/chat_salvos/conversa_20260807_201507.jsonl` (1,6 KB) criado no formato SFT (system+user+assistant) com `topico: geral`.
- ✅ **CORRIGIDO — Erro Alpine `m.fontes.length`**: expressão `m.fontesAbertas ? ... m.fontes.length ...` quebrava quando `fontes` era `undefined` (mensagem sem pesquisa). Agora usa `(m.fontes?.length || 0)` — console limpo após correção.

### Geração Local (página /gerar_local) — BUG GRAVE CORRIGIDO
- 🔴 **RUIM — "Failed to fetch" na geração**: o POST `/api/local-generate/gerar` bloqueava o event loop do uvicorn por 30-44s → healthcheck não respondia → o watchdog do `run_dashboard.bat` matava o servidor ("Failed to fetch", servidor subindo/descendo, processos recriados a cada tentativa).
- 🔍 **CAUSA RAIZ**: o `/gerar` do `main.py` (linha ~626, `local_gerar`) usava **`subprocess.run(["ollama", "run", ...])` SÍNCRONO dentro do handler async** — travava o event loop durante toda a geração. (O `local_generate.py` corrigido nem era usado — o main.py tem implementação própria com subprocess.)
- ✅ **CORRIGIDO**: `proc = await asyncio.to_thread(subprocess.run, ...)` — roda em thread, não bloqueia o loop.
- ✅ **VALIDADO no 8000 (servidor real)**: `/gerar` → **200 em 44s, resposta completa** ("Diálogo: Pessoa A/B sobre teste de geração"), **8000 VIVO após** (watchdog não mata mais).
- ✅ **Teste de bloqueio**: durante a geração, o healthcheck respondeu 12/12 (antes: 3-6/12 com timeout).
- ✅ **CORRIGIDO — Import quebrado em `local_generate.py`**: `from dashboard.services.limpeza import ... verificar_disponivel, PESQUISA_SEMPRE_ATIVA` → esses símbolos estão em `pesquisa.py`. Corrigido para `from dashboard.services.pesquisa import pesquisar, verificar_disponivel, PESQUISA_SEMPRE_ATIVA` + `from dashboard.services.limpeza import limpar_e_aviso`.

### Sistema (API) — BUG CORRIGIDO
- 🔴 **RUIM — `/api/system/details` 500**: `ValueError: Out of range float values are not JSON compliant: inf` (histórico de treino com "melhor loss inf").
- ✅ **CORRIGIDO**: função `_sanitizar_json()` substitui `inf`/`nan` por `None` recursivamente no `get_full_status()`. Validado: `/api/system/details` → **200 em 209ms**.
- 🛡️ **Anti-travamento de stdout**: `main.py` redireciona stdout/stderr para `logs/uvicorn_stdout.log` (worker `--reload` roda com pipe; print() sem drenagem travava) e desliga o access log do uvicorn (a visibilidade real segue no `logs/requests.log`).

### NOVAS FUNCIONALIDADES (07/08 noite — Executor pipeline + geração em massa)
- ✅ **Executor — opção "📦 TODAS as origens pendentes"**: o dropdown agora tem a opção "todos" (além das pastas individuais). O backend (`/api/executor/iniciar` com `origem="todos"`) lança `scripts/executor_pipeline.py` que roda a atividade em TODAS as origens, UMA POR VEZ, sem travar: erros pulam para a próxima, mostra % real e grava mural.
- ✅ **Executor — "🚀 Executar todas as atividades"**: `POST /api/executor/todas-atividades` roda TODAS as atividades (sanitizar → limpeza → verificar → diagnóstico) sobre todas as origens pendentes, sequencial.
- ✅ **Mural de resultados**: `logs/mural_pipeline.json` registra cada pipeline (nome, ok/erros/pulados, itens com comando/origem/status). Página Executor mostra o mural com botão "Limpar mural" (`/api/executor/mural`, `/api/executor/mural/limpar`).
- ✅ **TESTADO**: pipeline `verificar_encoding --origens todos` rodou 80 origens, progresso 100%, mural gravado (erros eram do bug do verificar_encoding — corrigido abaixo).
- ✅ **CORRIGIDO — `verificar_encoding_jsonl.py`**: agora aceita ARQUIVO .jsonl OU PASTA (antes tratava arquivo como pasta → "Pasta não encontrada"). Validado com arquivo individual: "UTF8 ok: True, U+FFFD: 0, mojibake: 0 → Amostra limpa".
- ✅ **UNIFORMIZAÇÃO de templates/estilos (local = API)**: novo módulo `dashboard/services/templates_conteudo.py` = FONTE ÚNICA. **21 tipos** (dicionario, pergunta_resposta, iteracao, artigo, conto, dialogo_profundo, explicacao, resumo, conversa, saudacao, poema, carta, entrevista, debate, tutorial, resenha, relatorio, ensaio, cronica, receita, dica — mesmos IDs da API) e **8 estilos** (neutro, profissional, professor, especialista, casual_jovem, humoristico, poetico, informativo_jornalistico). Rotas `/api/local-generate/templates` e `/estilos` agora usam o módulo (dropdown com 21+8).
- ✅ **GERAÇÃO EM MASSA local**: `scripts/gerar_massa_local.py` + `POST /api/local-generate/gerar-massa` + `GET /api/local-generate/massa-progresso`. Sorteia TODOS os tópicos × repetições × TODOS os templates × TODOS os estilos; faz UM, salva em `_massa/`, faz outro, salva... até a meta; depois **pós-processamento**: filtra qualidade → classifica por tipo → sanitiza → move para `dados/gerados/massa_final/<tipo>/` OU gera JSONL de treino. Progresso real em `logs/massa_progresso.json`.
- ✅ **TESTADO (script)**: `--modelo llama3.2:1b --meta 2 --formato txt` → 2 gerados, 50%→100%, pós-processamento 2 aprovados, arquivos em `massa_final/{iteracao,receita,ensaio}/`.
- ✅ **TESTADO (endpoint)**: `/api/local-generate/gerar-massa` lançou atividade no executor, progresso 100%, exit 0, mural registrado.
- ✅ **UI gerar_local**: seção "⚙️ Geração em MASSA" com modelo/repetições/meta/formato + botão "🏭 Gerar em massa" + barra de percentual real.

### Dashboard (testes de botões pelo navegador, 07/08 tarde)
- ✅ **BOM — Converter GGUF**: cliquei "Converter" (modelo_melhor.pt → Q4_K_M) → "✅ Conversão iniciada" → completou; "Criar no Ollama" → "✅ Modelo criado com sucesso!" (rigelslm, exit 0, manifest escrito).
- ✅ **BOM — Treinamento**: página carrega com dados reais (Época 6/20, Loss 8.4517, Checkpoint ✅); "💾 Salvar configurações" → `config_recursos.json` atualizado (NUCLEOS_USO=16, WORKERS=2, BATCH=16).
- ✅ **BOM — RSS**: "Selecionar todos" marca os 36 feeds; "Limpar" desmarca; "Processar 1" (Agência Brasil) → "✅ 1 feed em 2º plano" → log ativo raspando notícias.
- ✅ **BOM — Gerar Dados**: "⟳ Recarregar" popula centenas de tópicos; "🎲" sorteia ("O subtítulo e a especificação"); "🚀 Gerar via API" corretamente desabilitado (sem DEEPSEEK_API_KEY — não gasta saldo).

### Executor
- ✅ **BOM — Gestor funciona**: inicia atividade (verificar_encoding), roda em subprocesso, captura erro com mensagem clara, estado persistido.
- 🔴 **RUIM — Script `verificar_encoding_jsonl.py`**: recebeu caminho de ARQUIVO mas tratou como PASTA ("Pasta não encontrada: ..._00001.jsonl") → exit 1. Pendência: ajustar o script para aceitar arquivo OU pasta.

### RSS
- ✅ **BOM — RSS em volume funciona**: às 11:39 o dashboard processou 20 notícias (salvou curtos/longos, total 454 arquivos gerados acumulados).
- 🔴 **RUIM — Teste de 2 notícias (17:57)**: o log parou em "Processando as primeiras 2..." e o processo morreu SEM registrar conclusão/erro. **CAUSA CONFIRMADA**: o servidor foi reiniciado (o `run_dashboard.bat` do usuário subiu com `--reload`) no meio do processamento → o `background_tasks` do FastAPI morreu e levou o subprocesso RSS. **Não é bug do RSS em si — é o problema estrutural**: tarefas de fundo via `background_tasks` morrem com o reload. **Solução (pendente)**: tarefas longas devem rodar em subprocesso independente (não dependente da vida do uvicorn).

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
