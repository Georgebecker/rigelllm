## [SESSÃO 07/08/2026 — FASE 2/OBJETIVOS — continuação] 🚀 Executor pipeline + geração em massa + fixes do servidor
- **🐛 BUG CRÍTICO — `/api/local-generate/gerar` derrubava o servidor**: `subprocess.run(["ollama", "run", ...])` síncrono dentro de handler async bloqueava o event loop 30-44s → healthcheck não respondia → watchdog do `run_dashboard.bat` matava o servidor ("Failed to fetch", sobe-desce). **Fix**: `await asyncio.to_thread(subprocess.run, ...)`. Validado: 200 em 44s no 8000, servidor vivo após, healthcheck 12/12 durante streaming.
- **🐛 `/api/system/details` 500**: "Out of range float values are not JSON compliant: inf" (loss `inf` no histórico). **Fix**: `_sanitizar_json()` substitui `inf`/`nan` por `None` recursivamente. Validado: 200 em 209ms.
- **🐛 Bug Alpine `chat.html`**: `m.fontes.length` com `undefined` quebrava a página → `(m.fontes?.length || 0)`.
- **🐛 Import `local_generate.py`**: `verificar_disponivel`/`PESQUISA_SEMPRE_ATIVA` vinham de `limpeza.py` (não existem lá) → agora de `pesquisa.py`; `limpar_e_aviso` de `limpeza.py`.
- **🛡️ Anti-travamento stdout do uvicorn**: `sys.stdout/stderr` redirecionados para `logs/uvicorn_stdout.log` + access log desligado (o `--reload` travava com muitos prints).
- **🚀 Executor pipeline**: opção "📦 TODAS as origens pendentes" + botão "Executar todas as atividades" + mural de resultados (`logs/mural_pipeline.json`); `scripts/executor_pipeline.py` roda as atividades em sequência com progresso real e pula erros.
- **🎨 Uniformização templates/estilos**: fonte única `dashboard/services/templates_conteudo.py` (21 tipos + 8 estilos) para local e API.
- **⚡ Geração em massa local**: `scripts/gerar_massa_local.py` (Ollama, tópicos × repetições × templates × estilos) com pós-processamento (filtra → classifica por tipo → sanitiza → `dados/gerados/gerados_local/_massa/`).
- **🔧 `verificar_encoding_jsonl.py`**: aceita arquivo OU pasta + resumo correto + UTF-8 no console.
- **🐛 `treino.py` travava em `--no-interactive`**: 2 `input()` bloqueando (continuação de checkpoint + menu pós-épocas) → guards `no_interactive` (finaliza automaticamente). Validado: 20 épocas EXIT 0.
- **🐛 `treinoparquet.py` congelava no Colab (Google Drive)**: contagem e loop principal faziam `os.walk` de `dados/processed` INTEIRO (289+ pastas) → no Drive montado cada pasta é chamada de rede → parecia travado (log parava após "Pastas de treino encontradas"). **Fix**: `_listar_apenas_pastas_treino()` varre só as pastas `limpo_*` resolvidas (fallback de base inteira preservado). Validado localmente + usuário confirmou funcionando no Colab (commit `a698451`).

## [SESSÃO 07/08/2026 — FASE 2/OBJETIVOS] 🔍 Auditoria completa + correções estruturais
> Auditoria: 174 rotas, 157 módulos compilados (0 erros), 103 rotas/páginas OK. Foco: parar travamentos, feedback real, pipeline funcional.

- **🐛 BUG GRAVE — `/api/diagnostico/completo` travava o servidor inteiro**: escaneava `dados/processed` com `glob("*.txt")` (12,9M arquivos) + `torch.load` de checkpoint 665 MB + import local `import urllib.request, json` que tornava `json` variável local (`UnboundLocalError`). **Fix**: usa cache `estrutura_txt.json` (289 pastas/1,3M arqs) + verificação leve de cabeçalho do checkpoint. **Antes: travava o event loop ("failed to fetch") | Depois: 1,4s.** (Regra documentada: rotas async NUNCA fazem scan síncrono de milhões de arquivos.)
- **🛡️ Explosão anti-reload (estado nunca mais preso)**: `explosao_local.py` ganhou `pid_inicio` + `_marcar_interrompida_se_orfao()` (mesmo mecanismo do sanitizacao) — se o servidor reiniciar no meio, o estado é marcado `interrompido` e liberado. Estado preso de 06/08 (61.400 ex) liberado.
- **🧹 `explosao.log` 34,5 MB → 0,01 MB**: progresso logado a cada 1000 exemplos (era 50) + truncado.
- **📜 Middleware de log de requisições**: `dashboard/main.py` registra TODAS as chamadas `/api` (status + tempo) e **erros reais com exceção** em `logs/requests.log` — fim do "failed to fetch" sem causa.
- **📍 Pipeline de download com destino claro**: estado concluído agora inclui `saida_dir` (onde os dados foram salvos) + frontend mostra o caminho e o tratamento aplicado no card final.
- **💬 Chat**: salvamento de conversas validado end-to-end (2 pares, arquivo 599 bytes, SFT messages) + **ícones 👍/👎 removidos** (taxa, botões e função JS).
- **📱 Mobile verificado**: 13 páginas testadas em viewport 375px — **overflow horizontal 0 em todas** (layout responsivo OK).
- **📊 Feedback de material no treino**: `treinar_com_jsonl.py` avisa se o material é BAIXO (<10 arqs), MODERADO (10-50) ou SUFICIENTE (>50) antes de treinar.
- **🔧 Script de auditoria reutilizável**: `scripts/auditar_dashboard.py` (testa rotas GET + páginas, salva relatório incremental).
- ⚠️ **PENDENTE**: `--reload` do uvicorn da porta 8000 não recarrega — **servidor precisa reiniciar para carregar estas correções**.
- Docs: `docs/RELATORIO_AUDITORIA.md`, `docs/ROTAS_INVENTARIO.txt`, `docs/AUDITORIA_ROTAS_GET.txt`.

## [SESSÃO 07/08/2026] 🔧 Correções pós-testes do celular + diagnóstico do sistema
> Diagnóstico completo dos testes noturnos (celular) e correções de bugs confirmados nos logs.

- **🐛 Chat salvava 0 pares (arquivos 0 KB)**: `salvar_conversa_sft` só aceitava `role:"bot"`, mas o frontend envia `role:"assistant"` → loop nunca casava. Loop reescrito (robusto): aceita `assistant` **ou** `bot`, ignora `system` no meio, conta descartados corretamente. Validado: 2 pares salvos (assistant + bot).
- **🐛 Gerador local (`dialogos2.py`) crashava com `NameError: client`**: `.env` tem `USE_OLLAMA=True` (então `client` nunca era criado) mas o default do `--modelo` era `"deepseek"` → redefinia `USE_OLLAMA=False` → linha 4862 tentava usar `client` inexistente. Correções: `client = None` por padrão, condição `client is not None`, default do `--modelo` segue o `.env`, e `global USE_OLLAMA` movido para o topo de `main()` (CPython rejeita `global` duplicado com uso no meio).
- **🧩 Modelo do Ollama separado no gerador**: `.env` usa `MODEL_NAME=deepseek-v4-flash` (API DeepSeek) que **não existe** no Ollama local → gerador caía em fallback. Nova variável `OLLAMA_MODEL` (default `llama3.2:3b`, configurável) usada só no `ollama_generate`.
- **🐛 Treino: botão Parar não parava / status errado**: `_treino_rodando()` não detectava `treinar_com_jsonl.py` (status mostrava parado com treino vivo) e o stop dos órfãos usava só `terminate()`. Unificado o padrão de detecção + `kill()` forçado após 1s no stop.
- **🧹 Estado do scrap preso em "rodando"** (sem processo): limpo via `POST /api/scrap/limpar` (estado agora `idle`).
- **🛑 Processos encerrados nesta sessão**: treino jsonl órfão (PID 11284, ETA ~20 dias, ~16 GB RAM) e RSS travado desde 06/08 05:26 (PID 8232). RAM livre voltou de ~7,7 GB → ~23,8 GB.
- **⚠️ Pendências anotadas**: download datasets 100%→0%, explosão (log 36 MB, falta resume/clear), treino TXT re-selecionar pastas, e erro de tipo pré-existente em `chat.py:557` (`tokenizer` pode ser `None`).

## [SESSÃO 06/08/2026 — FINAL] 🧠 Gerenciamento de modelos do chat (serviço "de gente grande")
> Consolidado do trabalho de modelos no chat — busca HF, download robusto, quantização, GGUF sharded, log.

- **🧠 Verificação de arquitetura ANTES de baixar (novo)**: lê só o cabeçalho do GGUF (512 KB via HTTP Range) e confere `general.architecture`. **Aborta SEM baixar** se a arquitetura for desconhecida/`?` (não confirmada) ou não suportada (ex.: **`dflash`** do DeepSeek-V4-Flash, que o Ollama 0.32.5 **não suporta**). Conjunto em `arq_suportadas` (edite se atualizar o Ollama).
- **🐛 Bug crítico do parse GGUF corrigido (2º download de 11 GB evitado daqui pra frente)**: (1) offset do primeiro KV era `20`, o correto é **24** (magic 4 + versão 4 + tensores 8 + kvs 8) → a leitura caía nos bytes errados e retornava `'?'`; (2) `'?'` NÃO bloqueava (o `if` só pegava arquitetura conhecida-não-suportada) → o download passava mesmo sem confirmar. Agora `'?'` **bloqueia** (mensagem: "não foi possível CONFIRMAR a arquitetura — por segurança, não vou baixar"). Parse também suporta **arrays (tipo 9)** corretamente. Validado real: SmolLM2→`llama`, Llama-3.2-3B→`llama`, DeepSeek→`dflash` (abortado em 2 s no servidor).
- **🧹 Limpeza (Opção C — não usar `dflash`)**: apagados 10,9 GB (GGUF baixado) + **10,9 GB de blob órfão** que o `ollama create` falho deixou em `D:\LLMs\blobs` (verificado: nenhum manifest o referenciava). Disco D voltou a ~164 GB livres.
- **🛠️ Correções de robustez no sharded**: (1) `retomar()` re-despacha para `baixar_sharded` quando o repo era sharded (antes tentava `ollama pull gguf:...` → 400 `invalid model name`); (2) na falha do `create`, o arquivo NÃO é mais apagado — retry **reutiliza arquivo ≥99% do tamanho** (não re-baixa 11 GB); (3) `rmtree` da pasta só em **sucesso**; (4) nome do modelo `{base}:{quant.lower()}` (ex.: `deepseek-v4-flash-0731:q8_0`); (5) erro do create agora inclui a arquitetura.

- **🔎 Pesquisar modelos no HuggingFace (GGUF)**: painel colapsável no chat com busca + tabela (nome, downloads, curtidas, quantização com **tamanho MB + RAM necessária**, ⭐ Q4_K_M recomendado) e **filtro inteligente por RAM** (orçamento = **70% da RAM total** da máquina via psutil; fator 1,6×; esconde o que não roda — protege celular/notebook de superaquecimento). GGUFs divididos em partes são somados por quantização.
- **📥 Download robusto (não some mais)**: barra de progresso **global sempre visível** (% + contador de MB), **persistido** (`estado/ollama_pull_estado.json`) — se o servidor reiniciar, marca **interrompido** e oferece **Retomar** (o Ollama continua de onde parou). Erro não fecha a página: banner com **Tentar novamente**. Erros capturam a saída real do ollama.
- **🧩 GGUF sharded**: badge `⚠️ sharded` + botão **"Baixar+juntar"** — baixa o arquivo único OU todas as partes do HF → junta com `llama-gguf-split --merge` → cria no Ollama. (O `ollama pull hf.co/` falha em repos sharded — issue ollama #5245.)
- **⚙️ Quantizar modelo instalado** (frame colapsável abaixo da pesquisa): reduz Q8_0→Q4_K_M etc. com `llama-quantize --allow-requantize` → `ollama create`. Testado real: 1,3 GB → 807 MB (−38%) em 16s.
- **🗑️ Apagar modelo** (do disco, com confirmação), **📁 caminho do Ollama**, **🔎 baixar qualquer modelo** por campo livre.
- **📜 Log de ações**: `logs/modelos_acoes.log` registra download/remoção/quantização/merge (início, conclusão com MB/tempo, erros) + visualizador na página.
- **DeepSeek-V4-Flash-0731**: repo sharded (~671B, partes de ~50 GB), mas o **Q8_0 é arquivo único de ~11 GB** — baixável com "Baixar+juntar" (RAM ~17 GB).
- API: `modelos`, `pull`, `pull/status`, `retomar`, `pull/limpar`, `remover`, `caminho`, `buscar_modelo`, `baixar_sharded`, `quantizar`, `quantizar/opcoes`, `quantizar/status`, `acoes`.

## [SESSÃO 06/08/2026] Melhorias completas — tokenizer GGUF, treino_colab 3 modos, executor, logs, pipeline download+tratamento
### 🏠 Página inicial — estado REAL do modelo/treino (nova cara do projeto)
- **Card 🧠 Modelo enriquecido**: ✅ Pronto/❌ Ausente + nome (`modelo_melhor.pt`) + data + **tamanho (MB)** + **checkpoint mais recente** (`checkpoint_jsonl.pt` com data/tamanho). Antes mostrava só "✅ Pronto" + data.
- **Novo card 🎯 Treinamento ao vivo**: mostra 🟢 Rodando / ✅ Concluído / ❌ Erro / ⏸️ Parado + dataset + **barra de progresso** (lê `progresso.json` via `treino_local.get_estado()`) + mensagem atual. Se treinando, o card do Modelo também acende "🟢 Treinando agora...".
- **📈 Últimas épocas corrigidas**: antes lia só `logs/metricas.json` (TXT antigo, sempre desatualizado). Agora o `/api/system/details` agrega **`metricas_jsonl.json` (SFT, prioridade) + `metricas.json` (TXT)** e a home mostra Época + **Train/Val loss** + timestamp + fonte (SFT/TXT) — refletindo o treino real mais recente (ex.: épocas de hoje 06/08).
- **🧠 Nível do modelo (0-100%)**: barra de maturidade no card do Modelo com a **mesma fórmula do `chat.py`** (`calcular_barra_maturidade`: loss ≤ 0.5 → 100%, loss ≥ 10 → 5%, interpolação linear no meio). Fonte: `modelo/estado_treino_jsonl.json` (prioridade) ou min do histórico — hoje mostra **33% · melhor val_loss 6.8754 · época 5** (idêntico ao chat.py).
- **Botão de atualizar corrigido**: antes o ícone nunca girava (flag `loading` declarada mas nunca setada). Agora `loading=true` no início do poll e `false` no fim → o ícone `fa-rotate` gira durante a atualização + `title`/`aria-label` (tooltip).
- **📈 Últimas épocas com colunas separadas**: Train e Val deixaram de "se grudar" — agora há grade com cabeçalho (ÉPOCA | TRAIN | VAL | DATA) e valores alinhados à direita.

### 📦 Backup / Distribuição (novo, na home)
- **Seção "📦 Backup / Distribuição"** abaixo do Log/Épocas: botão "Criar backup" gera o pacote distribuível reutilizando o `deploy_package.py` (código + modelo, sem dados/checkpoints) em thread, com barra/ícone girando.
- **Máx. 2 versões**: `dist/rigelslm_dist_<timestamp>.zip`, rotação automática (a mais antiga é apagada) — validado com 3 gerações → só 2 ficaram.
- **Download pelo celular**: link 📥 com `Content-Disposition: attachment` + `Accept-Ranges` (download retomável) — testado: funciona em navegador mobile. Basta acessar `http://<IP>:8000` na mesma rede Wi-Fi (o uvicorn sobe em `0.0.0.0`).
- **Regra de instalação (responsabilidade do usuário)**: aviso na seção — extraia o ZIP em pasta **NOVA/Vazia**; não extrair por cima de instalação existente (como programas do Windows que exigem desinstalar antes de reinstalar).
- API: `GET /api/deploy/status` · `POST /api/deploy/criar` · `GET /api/deploy/download/{nome}` · `POST /api/deploy/remover` (`dashboard/services/deploy.py` + `dashboard/routes/deploy.py`).

### 💾 Treino Local — backup redimensionado
- **Recuperação escondida de propósito**: antes era um bloco vermelho enorme em destaque; agora é um link discreto "Recuperar backup (avançado — só para emergências)" no fim da seção, que abre o painel de perigo (continua exigindo digitar `RESTAURAR`).
- **Máx. 2 backups** (1 de `modelo.pt` + 1 de `modelo_melhor.pt`): nota na UI + seletor mostra só os 2 mais recentes (política de retenção do `modelo_backup.py`).
- **Aviso estilo Windows**: dentro do painel, "assim como programas do Windows exigem desinstalar antes de reinstalar, não restaure por cima de um estado que você quer preservar — a responsabilidade é sua".

### 📲 Celular ↔ PC — exportação colaborativa (novo, na home)
- **Exportar dados** gera `rigel_export_<ts>.zip` **só com o que VOCÊ gerou** (scrap, chat salvos, RSS, feedback 👍/👎, diálogos) — **sem** datasets baixados, **sem** a pasta `dados` inteira, **sem** modelo. Testado: 0,3 MB vs. GBs. Ideal para Google Drive.
- **Importar de `dados/Celular`**: pasta comum aos dois aparelhos. Baixa o zip no PC, solta em `dados/Celular/`, clica em Importar → distribui por tipo (jsonl→gerados p/ validar/promover no Treino Local, txt→raw p/ Tratamento, parquet→processed), arquiva o zip em `importados/` e registra em `import_log.json`. Testado com ciclo completo (export→import→distribuição).
- Fluxo: celular roda a estrutura nativamente (gera dados com scrap/chat/rss) → exporta → salva no Google Drive → baixa no PC → solta em `dados/Celular` → importa e treina no PC (hardware melhor).
- API: `GET /api/celular/status` · `POST /api/celular/exportar` · `GET /api/celular/download/{nome}` · `GET /api/celular/importar/verificar` · `POST /api/celular/importar` (`dashboard/services/celular.py`).

### 📥 Chat — baixar modelos SLM pré-definidos (novo)
- Se **não houver nenhum modelo** instalado no Ollama, a página do chat mostra um **dropdown curado de modelos conversacionais (SLM)** com nome + tamanho, descrição e **finalidade em badges** (chat, geração de textos, conversação, resumo RSS, debates, podcast) + botão Baixar com barra de progresso.
- Lista curada (só conversacionais úteis): `llama3.2:3b` (★ melhor PT-BR, RSS/debates/podcast), `gemma2:2b`, `qwen2.5:3b`, `llama3.2:1b` (leve p/ celular), `phi3:mini` (raciocínio/texto), `tinyllama:1.1b` (ultra leve).
- Backend: `GET /api/ollama/modelos` (instalados + sugeridos), `POST /api/ollama/pull?modelo=...` (thread com progresso), `GET /api/ollama/pull/status`. Testado real: `qwen2.5:0.5b` baixado em 9s (30→99→100%) e instalado.
- **🗑️ Apagar modelo**: botão lixeira ao lado do seletor — remove o modelo do Ollama (`ollama rm`) e do disco, com confirmação. Testado real: `qwen2.5:0.5b` removido (12→11 modelos).
- **📁 Caminho do Ollama**: a página mostra a pasta dos modelos (`GET /api/ollama/caminho` — env `OLLAMA_MODELS` ou padrão `~/.ollama/models`).
- **🔎 Baixar QUALQUER modelo**: campo livre (ex.: `qwen2.5:7b`, `mistral:7b`) — o `ollama pull` baixa do registro do Ollama, que é hospedado no HuggingFace (mesma fonte dos datasets, simples e eficiente, sem precisar de UI complexa de HF).
- **🔎 Pesquisar modelos no HuggingFace (novo, colapsável)**: painel no chat com campo de busca + botão Pesquisar — lista modelos **GGUF** do HF com nome, downloads/curtidas, e para cada um um seletor de **quantização** mostrando **tamanho (MB) e RAM necessária (~tamanho×1,5)**. Botão Baixar instala via `ollama pull hf.co/<repo>:<quant>`.
- **🛡️ Filtro inteligente por RAM**: detecta a RAM da máquina (psutil) e **só mostra modelos/quantizações que cabem** (teto 95% da RAM) — protege celular/notebook de baixar modelo que não roda nem estoura o HD. GGUFs divididos em partes são **somados por quantização** (tamanho real, não só uma parte).
- **✨ Seletor limpo**: no máx. **6 quantizações por modelo** (prioridade: Q4_K_M ⭐ recomendada → populares Q4_K_S/Q5_K_M/Q6/Q8_0 → menores), com nota "N/N quants" quando há mais compatíveis. **Quantizações de 1-2 bits (Q1/Q2/IQ1/IQ2) são filtradas** — rodam mas são inúteis p/ conversar (ex.: um 70B não aparece numa máquina de 32 GB).
- **Após baixar**: limpa a pesquisa, minimiza o painel e continua o chat. API: `GET /api/ollama/buscar_modelo?q=...`.

### ⚙️ Quantizar modelo instalado (novo, no chat) — reduz p/ caber na RAM
- Botão ⚙️ ao lado do seletor: escolhe uma **quantização menor** (Q8_0/Q6_K/Q5/Q4/Q3/IQ4) e quantiza localmente com **`llama-quantize --allow-requantize`** → cria novo modelo via `ollama create` (ex.: `llama3.2:1b-q4km`).
- **RAM por hardware (psutil) + conservador**: orçamento = **70% da RAM total** (evita superaquecimento/travamento; folga p/ sistema + contexto). Fator RAM = 1,6×.
- **Só oferece quantizações menores que a atual** e que cabem no orçamento; avisa quando o modelo já é quantizado (requantização perde um pouco de qualidade — ideal é baixar F16/Q8_0 e quantizar aqui).
- **Testado real**: `llama3.2:1b` (Q8_0, 1,3 GB) → `Q4_K_M` **807 MB (−38%)** em 16s, criado e listado no Ollama. API: `GET /api/ollama/quantizar/opcoes` · `POST /api/ollama/quantizar` · `GET /api/ollama/quantizar/status`.
- **UI**: a quantização virou um **frame colapsável igual à pesquisa** (toggle com chevron, minimizar/fechar) e fica **abaixo da pesquisa de modelos** — o chat continua sendo o principal; modelos são ferramentas para testar/usar nos outros módulos.
- **📥 Feedback de download (corrigido)**: a barra de progresso só aparecia quando não havia modelos — agora há um **painel de progresso global sempre visível** durante QUALQUER download (lista/HF/campo livre): % + **contador de MB** (ex.: `215MB / 397MB`) + barra + mensagem. Testado real: `qwen2.5:0.5b` 8%→54%→100% com `32MB/397MB`.
- **📜 Log de ações dos modelos (novo)**: arquivo `logs/modelos_acoes.log` registra **cada download, remoção e quantização** (início, conclusão com MB/tempo, erros) com timestamp — rastro para tratar problemas. Visualizador colapsável na página do chat (`GET /api/ollama/acoes`).

### 🧩 GGUF dividido (sharded) — download que NÃO some mais
- **Causa do "download fechou" encontrada**: o `ollama pull hf.co/...` **falha em 1s** para repos com GGUF dividido (erro 400 "sharded GGUF", issue ollama #5245) e a página fechava sem mostrar o erro.
- **Corrigido**: (1) a pesquisa marca `⚠️ sharded` e o botão vira **"Baixar+juntar"** — baixa o arquivo único OU todas as partes do HuggingFace direto (com % e MB) → junta com `llama-gguf-split --merge` quando preciso → cria no Ollama (`POST /api/ollama/baixar_sharded`). (2) **não fecha mais a pesquisa em erro** — mostra banner com **"Tentar novamente"**. (3) **download persistido** (`estado/ollama_pull_estado.json`) — se o servidor reiniciar, marca "interrompido" e oferece **Retomar** (o Ollama continua de onde parou). (4) corrigido deadlock de lock na persistência. (5) erro do `ollama pull` agora **captura a saída real** (causa exata no log).
- **DeepSeek-V4-Flash-0731**: o repo é sharded (outras quants têm partes de ~50 GB — o modelo é ~671B), mas o **Q8_0 é um arquivo único de ~11 GB** — cabe na sua máquina (RAM ~17 GB). Use "Baixar+juntar" → Q8_0.
- GGUF e modelos llama **já não entram** no pacote de distribuição (deploy): `gguf/` é criada vazia e modelos do Ollama vivem fora do projeto — baixados na máquina de destino com esses botões.
- **Backend**: `get_full_status()` agora retorna `modelo_info` (modelo + checkpoints), `treino_info` (estado ao vivo) e `metricas` (histórico agregado).
- Layout: 6 cards em grid (Modelo com destaque borda verde, Treinamento, CPU, RAM, Disco, Dados) — mobile-first (2 col no celular).
### � Chat — salvar SFT + feedback 👍/👎 + fontes da pesquisa
- **Salvar conversa agora no formato IDEAL**: jsonl SFT `messages` (system/user/assistant) com **personalidade** (SYSTEM_PROMPT do Rigel), **tópico** (campo "Tema da conversa") e metadata (fonte/data) → `dados/gerados/jsonl/chat_salvos/conversa_<ts>.jsonl` (antes era TXT cru). Respostas < 5 palavras são descartadas (filtro de qualidade básico).
- **Botões 👍/👎 por resposta** (chat): salvam feedback com `fontes` + `topico` em `dados/gerados/feedback_chat/feedback_<ts>.json` — ajuda a decidir treinar ou não aquela resposta.
- **Fontes da pesquisa web**: `pesquisa.pesquisar_com_fontes()` retorna (texto, URLs); o chat mostra "🔗 Ver fontes (N)" clicável na resposta; as fontes entram no feedback e no jsonl (cruzar p/ detectar "invenção").
- **Taxa de aprovação visível no chat**: badge "👍 X%" (via `/api/chat/feedback/estatisticas`), atualiza após cada feedback.
- **Patinho 🦆**: ícone na barra de status do dashboard (junto de "Busca: Online/Offline") e no chat (sem texto "DuckDuckGo").
- Botões do chat ficaram só com ícone + tooltip (regra do usuário: 1 ícone + `title` em tudo); responsividade mobile do input/botões corrigida.

### �📡 RSS — fix de perda de dados + automação do modelo de resumo
- **BUG CRÍTICO corrigido**: o jsonl do RSS saía VAZIO (0 bytes) apesar de "Salvo:" no log. Causa: `EscritorJsonl` só dava flush no `close()` (via atexit) — se o processo era encerrado antes, os dados do buffer se perdiam. **Fix**: método `EscritorJsonl.flush()` + `flush()` após CADA gravação no `rss_processor.py` (dados nunca mais se perdem).
- **Teste de modelos locais p/ resumo PT-BR** (mesmo prompt do `gerar_resumo`): `llama3.2:3b` ✅ 120 palavras/52s (segue regras, coerente) · `bode-alpaca-pt-br` ⚠️ 43 palavras (ignora mínimo de 100) · `rigelslm:q8_0` ❌ vazio. **Conclusão: `llama3.2:3b` já era o melhor** — mantido como padrão.
- **Automação**: `selecionar_modelo_resumo()` (testa candidatos se "auto") + **fallback automático** no `gerar_resumo_ollama`: se o modelo configurado falhar, tenta os candidatos (`llama3.2:3b` → `bode-alpaca-pt-br` → `llama3.2:1b`) — sempre usa um modelo que funciona.
- Validado: run real de 1 artigo (Agência Brasil) → jsonl com 1 exemplo SFT (1.813 bytes) gravado corretamente.

### 🌐 Scrap — nova página de extração de sites (NOVA, renomeada de "Wiki Scrap")
- **Crawler por SITE** (requisito 06/08): modo **quantidade** (até 100 matérias) OU **profundidade** (níveis de links internos) + **preferência** de seleção: 📰 mais recentes (data) / 🧠 mais complexas (mais longas) / 🌱 natural. Estatísticas por site: páginas, profundidade, limite, coletados, limite_atingido.
- **Infra de parquet p/ treino**: `rigel_sft.parquet` (coluna `messages` ChatML — schema IDÊNTICO ao limpeza_leve) + `rigel_pretrain.parquet` (coluna `text`). jsonl SFT com **tópico** + txt. Validado com pyarrow (schema correto).
- **Marca na listagem**: cada scrap mostra 🧼 Sanitizado / 📦 Parquet / 🔤 Limpeza / ⚪ Bruto + tamanho total e por arquivo/subpasta (`/api/scrap/listar`).
- Fix: `extrair_url(html=...)` (crawler) — antes `resp` indefinido quando html era passado.
- Rename completo Wiki Scrap → Scrap (página `/scrap`, API `/api/scrap/*`, dados `dados/processed/scrap/`); antigos em `D:\Projetos\apaguemedepois\scrap_rename_20260806\`.
- **Rename completo Wiki Scrap → Scrap** (não é só wiki — é um scraper geral): página `/scrap` (menu "Scrap"), API `/api/scrap/*`, serviço `dashboard/services/scrap.py`, template `dashboard/templates/scrap.html`, dados em `dados/processed/scrap/` (e `dados/raw/scrap/`), estado `estado/scrap_estado.json`.
- Antigos (wiki.py/wiki_scrap.py/wiki.html) movidos p/ `D:\Projetos\apaguemedepois\scrap_rename_20260806\`; dados existentes MIGRADOS (não apagados): `processed/wiki` → `processed/scrap`.
- Página `/scrap`: digita a URL → extrai **título + conteúdo** → salva como **jsonl (SFT messages, treinável)** ou **txt** → **tratamento automático** → `dados/processed/scrap/<nome>/`.
- **Pipelines prontos pesquisados/validados**: `trafilatura` (padrão-ouro, já instalado v2.2) → fallback `justext` → fallback `BeautifulSoup`; fetch com `httpx` (headers de navegador); detecção de idioma por stopwords (sem dependência pesada).
- **Modo teste**: `POST /api/scrap/testar` avalia QUALIDADE (score 0-100, palavras, idioma, extrator, amostra) SEM salvar.
- Pipeline completo: extrair → salvar raw/scrap → jsonl→**sanitização PT-BR** / txt→**limpeza de encoding** → promover p/ processed/scrap → **limpar origens**.
- Botão "Cancelar" no painel (reset do estado, libera para recomeçar).
- Arquivos: `dashboard/services/scrap.py` (estado persistido em `estado/scrap_estado.json`), `dashboard/routes/scrap.py`, `dashboard/templates/scrap.html`.
- Validado com testes reais: Wikipedia IA (jsonl→sanitizado, 8.103 palavras), Rio de Janeiro (txt→limpeza, 22.016 palavras), Brasil (159 KB); UI ao vivo com score 80/100.

### 🤗 Datasets — seletor de tratamento + cancelar download
- Checkbox "Tratar após baixar" → **seletor**: 🎯 Automático (detecta formato: jsonl→sanitizar, parquet→limpeza leve v2) · 🧼 Sanitizar · 🧹 Limpeza leve · ⛔ Nenhum.
- `baixar_e_explodir(tratamento="auto")`: parquet (explode 0) → roda `limpeza_leve_rigel_v2.py` direto no raw; estado registra `tratamento` + `limpos_origens`.
- **Botão "🗑️ Cancelar download"** no painel (download travado não bloqueava mais o Baixar): `POST /api/datasets/cancelar` reseta estado + apaga pasta raw parcial.

### 🧠 GGUF — tokenizer corrigido (README #3.7)
- Bug: `converter_para_gguf.py` convertia `Ġ`(U+0120)→`▁`(U+2581) no tokenizer ByteLevel → GGUF gerava vazio/lixo em TODOS os runtimes (llama-server/Ollama/llama-cli).
- Fix (backup `converter_para_gguf.py.bak_20260806`): manter `Ġ`; `tokenizer.ggml.pre="gpt-2"`; `add_space_prefix=false`.
- Resultado: reconvertido via `/converter` (Q8_0 59,7 MB); `llama-cli` gera (~291 t/s); **todos os `rigelslm:*` respondem no Ollama**. Documentado no README.md e INSTALL.md.

### 🎯 Treino Colab — 3 modos (texto/jsonl/parquet)
- `dashboard/routes/treino_colab.py`: seletor de modo; cada um gera sua célula de comando própria (treino.py / treinar_com_jsonl.py / treino_colab.py).
- Aba `treino_colab_txt` REMOVIDA (redundante) — backup em `D:\Projetos\apaguemedepois\`.
- Menu lateral: "Colab Jsonl" → **"Google Colab"** com ícone G (fa-brands fa-google).
- Fix de null (resultado/fila) no template.

### ⚙️ Executor
- Fix: `x-if` em `<span>` → `x-show`; logs contidos na caixa (`break-words` + `whitespace-pre-wrap`).

### 📋 Logs
- Fix bug do `visualizar()` (sempre buscava dashboard.log → agora busca o arquivo certo, texto/JSON).
- Botão "🔄 Atualizar" (re-varre a pasta: removidos somem, novos aparecem).
- 32 logs de lixo movidos p/ `D:\Projetos\apaguemedepois\logs_limpos_20260806`.

### 🤗 Datasets — download com tratamento automático
- Checkbox "🧼 Tratar após baixar" (LIGADA por padrão): baixar → explodir → **sanitizar PT-BR** → **promover p/ processed** (treinável na hora) → **limpar origens** (raw+gerados+sanitizados → HD liberado).
- `sanitizacao.py` CORRIGIDO (estava QUEBRADO: `_gravar_tudo` → `_EscritorStreaming`; `_listar_jsonl` agora retorna 3 valores; gravação via `escritor.fechar()`). Validado: 687 exemplos.
- Tamanho em MB nos resultados (`/api/datasets/tamanho` via datasets-server, campo `num_bytes_parquet_files`).
- Botões "🧹 Esquecer" nos painéis + `limpar()` nos 3 serviços (`explosao_local`, `sanitizacao`, `hf_datasets`) + `POST /api/datasets/limpar`; **dashboard se limpa sozinho após o passo 5**.
- Fix de null guards (explosao/sanitizar).

### 🧭 Treino Local
- Fix: `fila` null → `{}` + guards `?.` (erros de console eliminados).

### 📌 Matriz de tratamento (NÃO confundir)
- **JSONL messages** → 🧼 Sanitizar (`gerar_sanitizados.py`/`sanitizacao.py`) — corrigido e validado.
- **PARQUET** (Madras) → 🧹 `limpeza_leve_rigel_v2.py` (+ `ver_progresso_limpeza.py` p/ progresso) — NÃO usar sanitizar.
- **TXT** → `limpeza.py` (só corretor de encoding).
- Registro completo: memória do repositório `pipeline_tratamento.md`.

---

## [TAREFA PENDENTE — 06/08/2026] Revisão GERAL backend + frontend

> **Pedido do usuário (05/08/2026):** "anote que teremos que rever todas os arquivos do backend e do frontend."

### A fazer
- Revisar TODOS os arquivos do backend (`dashboard/routes/*`, `dashboard/services/*`, scripts da raiz) e do frontend (`dashboard/templates/*`, `dashboard/static/*`).
- Contexto: muitas mudanças acumuladas (executor, sanitização, dropdown, explosão, guardião) — rever consistência, erros latentes, dead code, imports quebrados.
- Relacionado: pipeline de dados sujos → prompt COMPLETO registrado em `docs/PROMPT_LIMPEZA_LEVE_V2.md` (implementado em `limpeza_leve_rigel_v2.py`).

---

## [TAREFA PENDENTE — 06/08/2026] Ferramenta de STOP geral dos servidores llama

> **Pedido do usuário (05/08/2026, madrugada):** "implementar uma ferramenta de stop geral dos servidores llama, em situações como esta, quero um botão ao lado dos serviços que usam o llama com um botão de Parar, enviar um sinal de stop. sei lá por que eles ficam renascendo com atividade, não é só estar online, ele fica online e fica fazendo serviços..."

### 🎯 Escopo
- **Botão "Parar"** no dashboard, ao lado dos serviços que usam o llama (rss_processor, chat, resumos, etc.), que envia **sinal de STOP real** ao Ollama/llama-server.
- **STOP geral**: um botão que descarrega TODOS os modelos do Ollama de uma vez (`ollama stop <modelo>` para cada) e/ou para o `ollama serve` se necessário.
- **Entender o renascimento**: os llama-servers são filhos do `ollama serve` — matar o processo (taskkill) NÃO resolve porque o Ollama recria (keep-alive ~4 min + clientes ativos continuam pedindo). O correto é `ollama stop <modelo>` (descarrega de verdade) ou parar o CLIENTE que segura o modelo.
- **Guardião**: detectar `llama-server.exe`/`ollama.exe` ativos com CPU alta e avisar/recusar iniciar tarefas pesadas quando houver inferência em andamento (crítica do usuário: "por que não consegue verificar se tem memória se tem 2 servidor llama").

### 📌 Lição técnica (05/08)
- `taskkill` no llama-server **não funciona** — o Ollama recria. Usar `ollama stop <modelo>`.
- `ollama ps` mostra modelos carregados + keep-alive (UNTIL). `ollama stop <nome>` descarrega.
- Modelos carregados consomem CPU **mesmo sem cliente ativo** (mantidos quentes).
- Guardião deveria detectar `llama-server.exe`/`ollama.exe` ativos (CPU alta) e avisar/recusar tarefas pesadas.

---

## [TAREFA PENDENTE — 06/08/2026] Erros na página de Datasets

> **Pedido do usuário (05/08/2026):** "tem muito erro também na página dataset" (adiado para amanhã por pedido do usuário).

### A fazer amanhã
- Investigar erros na página `/datasets` (dashboard/routes/datasets.py + dashboard/templates/datasets.html).
- Observação já vista: `/api/executor/origens` lista origens DUPLICADAS (ex.: jsonlocal 2x, rigeljsonl43 2x, Madras1 2x) — verificar agrupamento por pasta pai em `listar_origens()`.

---

## [1.0.0] - 2026-07-31

### 🚀 Adicionado
- **Reinício da numeração de versões** — todos os arquivos do projeto padronizados para **1.0.0**.
- **Histórico de versões reescrito** no `README.md` com incrementos planejados (1.0.1, 1.0.2, ...).
- Cabeçalhos de todos os arquivos `.py` atualizados para `Versão: 1.0.0 | Data: 31/07/2026`.

### 🔧 Atualizado
- `README.md`, `docs/PROFILE.md`, `INSTALL.md` e `skills/python/style_guide.md` com a nova versão 1.0.0.
- `estado_global.json` e `verificador.py` com a nova versão do projeto.

---

## [6.4.6] - 2026-07-25

### 🖥️ Dashboard
- Análise completa de todos os arquivos da pasta `dashboard/` (10 rotas, 2 serviços, 1 template).
- Removidos arquivos redundantes `dashboard/index.html` e `dashboard/indexbackup.html` (cópias não utilizadas do `dashboard/templates/index.html`).
- Criado log de análise em `logs/analise_dashboard_20260725.md`.
- Identificados problemas: duplicação de endpoints `/api/local-generate/*`, stub não utilizados, dependência de CDN para CSS.
- Identificada necessidade de fallback automático DeepSeek → Modo Local quando API falha.

### 📚 Documentação
- Atualizado `docs/CHANGELOG.md` com versão 6.4.6.
- Atualizado `docs/PROFILE.md` (versão, data, contagem de arquivos).
- Atualizado `README.md` (versão, data, contagem de arquivos).
- Padronizados cabeçalhos de todos os arquivos `.py` com versão, data e contagem de arquivos de treino.
- Arquivos de treino disponíveis: **1.089** arquivos `.txt` em `dados/processed/`.

## [6.4.5] - 2026-07-15

### 📚 Documentação
- Criado `docs/CHANGELOG.md` para registrar todas as versões do projeto.
- Criado `docs/PROFILE.md` com o perfil do projeto (padrões, regras, estrutura).
- Criado `.agent.md` atualizado com todas as instruções para o agente de IA.
- Adicionadas pastas `skills/` e `scripts/` para organizar habilidades reutilizáveis e scripts utilitários.