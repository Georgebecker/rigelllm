## [SESSÃO 20/08/2026] TRATAMENTO SEGURO DO ACERVO
- **Correção de estado travado**: depois de um lote grande (cnmoro, 150 arquivos), o estado persistido podia continuar `rodando=true` mesmo sem thread/processo vivo. O frontend ficava bloqueado, enquanto os botões respondiam "não há tratamento". Agora o backend reconcilia esse estado stale como `interrompido`, preserva o percentual/arquivo e libera um novo início ou retomada.
- **Teste real**: iniciar/parar em pasta pequena respondeu corretamente; estado final `parado`, origem preservada.
- **Ordem obrigatória das vacinas**: tratamento real agora marca `sanitizado` e `verificado_encoding`; simulação não marca nada. `ajuizado` é bloqueado pela API e pela carteira quando essas duas etapas faltam. `promovido` continua sendo a última etapa.
- **Cartão no painel seguro**: o frontend mostra as quatro vacinas e o estado atual do resultado tratado.
- **Controles de execução**: o painel seguro agora oferece **Pausar**, **Parar** e **Retomar**. O progresso é salvo por arquivo; ao retomar, o arquivo incompleto é refeito e os arquivos concluídos não são repetidos. A origem continua intacta.
- **Novo serviço `dashboard/services/tratamento_acervo.py`**: lê JSONL em streaming, reaproveita o tratamento existente e grava somente em `dados/tratados/<nome>_tratado/`. Nunca altera ou apaga `dados/processed` nem a origem.
- **Novas rotas** em `dashboard/routes/tratamento.py`: listar origens, iniciar em modo simulação/tratamento e consultar progresso persistido.
- **Frontend `/tratamento`**: novo painel para escolher a origem, simular antes de gravar, acompanhar percentual, aprovados, corrigidos, descartados e log técnico.
- **Teste real pela API**: `dados/processed/jsonl/txt_sanitizado` → simulação concluída com 49 linhas, 49 aprovadas e 0 descartadas; nenhuma saída foi criada e a origem permaneceu intacta.

## [SESSÃO 19/08/2026, 2ª] 🎓 ABA TREINAMENTO FUNCIONANDO — "poder escolher com o que treinar" (múltiplas pastas + tipos)
- **🐛 CAUSA RAIZ do "log estranho" / "não funciona na prática"**: o dashboard enviava `--dados pasta1,pasta2,...` (várias pastas com vírgula) para o `treino.py`, mas ele tratava a string INTEIRA como UM caminho → `os.path.exists("A,B,C")` = False → "❌ Nenhum arquivo suportado". FIX: `_resolver_pastas_dados()` + `_listar_arquivos_varias()` no `treino.py` (divide por vírgula/`;`, resolve cada pasta em `dados/processed/txt`/`dados/processed`, lista arquivos de TODAS sem duplicar) — mesmo padrão do `treinar_com_jsonl.py`. O `StreamingTextDataset` também aceita vírgulas.
- **🐛 TREINOPARQUET idem**: `--dados` com várias pastas também quebrava. FIX: resolução de múltiplas pastas no `main()` e no `StreamingTextDataset` (bases `dados/processed/parquet`/`dados/processed`).
- **🐛 DASHBOARD parquet ignorava a seleção**: o backend montava SEMPRE `--dados dados/processed` (base inteira — treinava cnmoro 33GB mesmo marcando 1 pasta). FIX: agora usa as pastas marcadas (via cache do `escaneador_parquet`), com fallback p/ a base se nada marcado.
- **🚫 REGRA DO USUÁRIO: `dados/processed` é a fonte de treino (por tipo) e NUNCA apagar/convertida**: removido o botão "🔄 Converter TXT → JSONL" da aba Treinamento (ele convertia pastas de `processed/txt`). A aba agora é SÓ para escolher tipo + pastas + Treinar.
- **✅ TESTADO REAL pelo frontend (3 tipos, pasta pequena, log em `logs/treino.log`)**: TXT (`txt/Resenhas`, 1 arq) → `treino.py` rodou, tokenizer + modelo 58M carregados, Epoch 1; JSONL (`txt_sanitizado`, 1 arq, 49 exemplos) → `treinar_com_jsonl.py` rodou Epoch 1/5; PARQUET (`scrap`, 26 arqs) → `treinoparquet.py` carregou 24 treino/2 val, batch com 1153 tokens únicos, retomou Epoch 16/20. Todos parados com ⏹️ Parar.- **🐛 CAUSA RAIZ do "modelo não aprende"**: o scheduler (warmup + cosine decay) estimava o tamanho da época com um CHUTE (`chunks_por_arquivo = 10` → `total_steps = 3120`), mas a época REAL tinha ~13.471 passos. Resultado: o cosine derrubava o LR de 2e-5 para 0.000000 no 1º quarto da 1ª época e o modelo treinava o resto no escuro (loss presa ~6.7).
- **🎚️ SCHEDULER DE LR DESABILITADO**: agora o LR fica CONSTANTE no valor de `--learning-rate`/`--lr` (novo argumento adicionado; ex.: `--learning-rate 2e-5`). Se quiser decay no futuro, é preciso MEDIR o tamanho real da época antes — nunca chutar.
- **🐛 Resume não restaurava o Adam**: o checkpoint salvava `optimizer_state_dict` mas nunca carregava → cada restart do `while true` perdia o momentum. FIX: otimizador criado antes do checkpoint e estado restaurado no resume (com fallback seguro p/ checkpoints antigos).
- **🐛 "Melhor validação 0.0000"**: a validação usava os arquivos MENORES (quase só padding → loss ~0 enganoso). FIX: validação agora usa arquivos de TAMANHO MÉDIO (janela central da lista ordenada por nº de linhas). Valor inválido (~0) no checkpoint é resetado p/ refazer a validação.
- **✅ Testado REAL**: `--help` importa sem erro; teste funcional confirmou restauração do Adam (`load_state_dict`) e o novo split de validação (janela central, sem sobreposição).
- **📌 Uso**: `python treinoparquet.py --dados dados/processed/parquet --no-interactive --learning-rate 2e-5 ...` — o LR agora fica em 2e-5 e não cai mais para 0.
- **🔍 Diagnóstico de batch** no início do treino (`_diagnostico_batch`): imprime formato, % de padding, tokens únicos e amostra decodificada — prova visual de que os dados não estão vazios/padding demais (regra "ver antes de treinar"). Testado com batch real: `(1,4) | 4 tokens | padding 25.0%`.
- **🛡️ Validação robusta a inf/nan**: valores não finitos (overflow fp16/AMP) são descartados por batch em vez de corromper o "melhor modelo" e o early stopping (era a fonte do "validação: inf").
- **🧹 Limpeza simples de dados**: diálogos com pergunta+resposta < 30 caracteres e textos < 50 caracteres são pulados (chunk quase só padding = lixo de treino). Constantes `MIN_DIALOGO_CHARS`/`MIN_TEXTO_CHARS` ajustáveis.
- **✅ Auditoria (sem mudança, já estava correto)**: o shift do target (`target=batch[:,1:]` / `logits=logits[:,:-1,:]`) e a máscara causal (`torch.triu(..., diagonal=1).bool()`) estavam corretos — sem off-by-one, sem máscara errada.
- **🐛 TREINAR_COM_JSONL — mesmo padrão de correção (19/08)**: (1) `carregar_modelo` agora retorna o estado do Adam e ele é restaurado no resume (antes cada restart perdia o momentum); (2) validação (`avaliar`) descarta loss `inf`/`nan` por batch; (3) erro de tipo pré-existente corrigido (`eta_segundos: float | None`). O scheduler do JSONL NÃO foi mexido — ele usa contagem REAL de batches (`len(SFTDataset)`), então o cosine decay é correto e não mata o LR como no treinoparquet.
- **📊 DASHBOARD — "Onde está o material para treinar" (novo)**: na Central (bloco 3. Treinar), seção que classifica TODAS as pastas de `dados/processed/jsonl/` em **Prontas para treinar conversas** (verde, formato `messages` válido) vs **Não servem** (laranja, com motivo). Backend: `painel_dados.classificar_pastas_sft()` (leve, sem torch, amostra 100 linhas × 2 arquivos, respeita guardião de memória) + rota `GET /api/dados/sft-prontos`. Testado real: 401 pastas → 396 prontas, 5 não servem (brwac, restore-punctuation, cnmoro, ultra-alpaca, rigel20260818 vazio).
- **📊 DASHBOARD — correções de frontend + cache (19/08, 2ª parte)**: (1) a seção ficava presa em "verificando..." porque a varredura rodava do ZERO a cada poll automático — agora tem CACHE de 5 min (`?forcar=1` no botão atualizar refaz); (2) falha deixava a tela sem explicação — agora mostra mensagem de erro visível e honesta; (3) classificador passou a encontrar `.jsonl` em SUBPASTAS (recursivo, com limite cedo) — o mini-backup `rigel20260818_064347` (100% messages) era marcado "vazio" por isso; (4) seção validada na página real: "Prontas para treinar conversas (397 pastas)"; (5) **BANNER de resposta direta**: "Tudo pronto: N pastas já estão no formato correto para treinar" (verde) ou "N ainda NÃO estão no formato correto e precisam de conversão" (laranja) — o dashboard agora DIZ o status sem o usuário perguntar.
- **🗂️ MOVIMENTAÇÃO (a pedido do usuário)**: as 4 pastas que NÃO servem para SFT saíram de `dados/processed/jsonl/` → `dados/gerados/jsonl/` (para o sistema reprocessar pelo funil): `dominguesm_brwac` (18GB), `dominguesm_restore-punctuation-ptbr-dataset`, `cnmoro_reasoning-v1-20m-portuguese`, `BrunoN-Dev_ultra-alpaca-ptbr`. `processed/jsonl` ficou com 397 pastas, TODAS "pronto" (100%). Nada foi apagado.
- **⚠️ CLARIFICAÇÃO cnmoro (19/08)**: o TRABALHO REAL do usuário no cnmoro está em **`dados/processed/parquet/cnmoro/` — 709 parquet `*_tratado` em formato `messages`** (resultado do `scripts/tratar_parquet_grande.py`, 18/08) — INTACTO e no lugar certo (parquet). O que foi movido p/ gerados foi um `dataset.jsonl` BRUTO (2,5 GB, formato `prompt/thought/answer` — NÃO tratado) que estava em `processed/jsonl`. O classificador SFT do dashboard só olha jsonl — por isso marcou o jsonl bruto como "não serve"; o cnmoro tratado (parquet) nunca foi tocado.
- **✅ CNMORO JSONL CONVERTIDO p/ SFT (19/08)**: novo `scripts/converter_cnmoro_jsonl.py` converte `prompt/thought/answer` → `messages` (descarta `thought`, limpa mojibake, dedup md5, streaming, progresso real em `logs/converter_cnmoro_progresso.json`). Resultado: `dados/processed/jsonl/cnmoro_sanitizado/` = **150 arquivos / 300.000 exemplos, 100% formato `messages`** (300/300 na amostra válidos, 0 descartados, ~65s). O `dataset.jsonl` bruto segue em `dados/gerados/jsonl/cnmoro_reasoning-v1-20m-portuguese/` (não apagado).
- **📌 DECISÃO DO USUÁRIO (19/08)**: manter o `dataset.jsonl` bruto do cnmoro em `dados/gerados/jsonl/` como RESERVA (opção 1). O funil vai mostrá-lo como "provisório" — esperado; não reprocessar.
- **🐛 TREINAMENTO — pastas PARQUET não apareciam (19/08)**: o `_scan_parquet` usava `_scan_raso` (nível 1 de `dados/processed`), então mostrava só "parquet · 1 arq" (o `rigel_sft.parquet` solto) e NÃO descia para `parquet/cnmoro/` nem `parquet/scrap/`. FIX: escaneia a base `dados/processed/parquet` recursivamente (subpastas + soltos na base; fallback p/ layout antigo). Testado real: 3 pastas — `cnmoro` 709, `scrap` 26, `parquet (soltos na base)` 1 (total 736).
- **🐛 TRATAMENTO — mensagem "A extração caiu" não limpava (19/08)**: (1) a mensagem era anexada ao log a cada consulta do painel quando o processo morria — agora anexa UMA vez por episódio (idempotente, testado); (2) o botão "Parar" (que limpa) só aparecia com `rodando` — após a queda vira `interrompido`, então não dava para limpar sem clicar em "Continuar" (que re-rodava). FIX: novo botão **"Limpar aviso"** visível no estado interrompido/erro — zera o log/estado sem rodar nada (o que já foi tratado fica salvo).
- **📁 ABA TRATAMENTO — agora verifica `dados/gerados` (19/08)**: nova seção **"Provisórios em dados/gerados"** lista as pastas de `gerados/jsonl` com formato/tamanho e **botão "Converter" por pasta** para as conversíveis (messages/prompt+answer/instruction+output/pergunta+resposta/completion). As de só texto/pré-treino (ex.: brwac, restore-punctuation) ficam marcadas como "só texto/pré-treino" (sem botão — não viram conversa). Rota `POST /api/tratamento/converter-jsonl`, roda em subprocesso com log em tempo real.
- **🧼 TRATAMENTO = CONJUNTO (ajustar/aproveitar/eliminar/sanitizar)**: novo `scripts/converter_jsonl_messages.py` reutiliza o sanitizador do projeto (`corrigir_mojibake_inteligente` + `remover_invalidos` + `avaliar_conteudo`) — corrige mojibake real, remove caracteres fora do PT-BR (ABNT2), **ELIMINA exemplos com excesso de lixo (>25% de inválidos)** e aproveita o resto. Testado real no ultra-alpaca (prompt serializado + completion): 3.000 linhas → 2.998 convertidas, 2 descartadas, saída 100% limpa (0 mojibake/`�`).
- **💉 CARTEIRA DE QUALIDADE — "parcial" mesmo em processed (19/08)**: o tratamento NUNCA carimbava `sanitizado`/`verificado_encoding`/`promovido` na carteira (só o ajuizador carimbava `ajuizado`) → pastas em processed apareciam "🔄 Parcial". FIX: (1) o tratamento/conversão agora **carimba a carteira** ao promover; (2) **backfill** das 9 pastas já em processed (Dicionário, api_gerados, completos, curtos, debates, gerados_local, longos, massa_final, txt_livros) → carteira passou de 1 pronta/15 parciais para **10 prontas/6 parciais** (as 6 restantes genuinamente faltam etapa, ex.: chat_salvos não passou pelo ajuizador).
- **🔒 REGRA DE ORDEM DA CARTEIRA (19/08, usuário)**: ajuizado SÓ depois do tratamento. Em `qualidade.marcar()`, carimbar `ajuizado` carimba junto os pré-requisitos `sanitizado` + `verificado_encoding` — a carteira nunca mais mostra "ajuizado" sem o tratamento. Testado: marcar ajuizado → etapas = [ajuizado, sanitizado, verificado_encoding]; + promovido → "pronta".
- **🔘 CARTEIRA COM AÇÃO (19/08, usuário)**: pastas "🔄 Parcial" agora têm botão — **"⚖️ Revisar"** (quando falta a revisão do juiz → vai para `/revisar`) ou **"🧼 Tratar"** (quando falta tratamento/promoção → roda o tratamento). O aviso deixou de ser passivo: dá para completar a etapa que falta e a situação muda.
- **💉 CARTÃO DE VACINA nas provisórias (19/08, usuário)**: cada pasta de `dados/gerados/jsonl` agora mostra o cartão de vacina (4 etapas: sanitizado/verificado/ajuizado/promovido — ✓ feito · faltando) + **botão da próxima etapa**: **Converter** (vira conversa, `converter_jsonl_messages.py`) ou **Extrair p/ TXT** (pré-treino, novo `converter_jsonl_txt.py` → `processed/txt/<nome>`). Rota `POST /api/tratamento/extrair-txt`. Auditoria: os 7 provisórios estavam TODOS crus (0 carimbos) — agora cada um tem ação. Testado: extração restore-punctuation 3.000 linhas → 2.977 textos, 23 lixo eliminados.

## [SESSÃO 18/08/2026 — tarde] 🗂️ REORGANIZAÇÃO do acervo por TIPO (A, B, C) + palavra "Tratamento"
- **🗂️ Novo padrão de pastas (minúsculas, Windows case-insensitive)**: `processed/txt/` · `processed/jsonl/` · `processed/parquet/`. Fonte de verdade: novo `regras_pastas.py`.
- **A — Constantes padronizadas**: `treinoparquet.py` (seed corrigido: removido `scrap` da lista fixa, adicionado `parquet_livros`; base efetiva `processed/parquet`), `treino.py`/`treinov2.py` (`_base_txt_efetiva()` → `processed/txt` com fallback), `treinar_com_jsonl.py`.
- **B — PARQUET migrado** (10 arquivos): 6 pastas (`limpo_alpaca`, `limpo_canarim`, `limpo_madras1_v2`, `limpo_wikipedia`, `parquet_livros`, `rigelparquet`) + `scrap` (26 parquet, pasta mista) → `processed/parquet/`. Registro `registro_pastas_treino.json` atualizado via novo `scripts/atualizar_registro_pastas.py`.
- **C — TXT migrado**: 296 pastas → `processed/txt/` (~1,39M arquivos). `registro_pastas.json` atualizado (266 caminhos migrados, 289 entradas-fantasma removidas); caches de estrutura limpos p/ regenerar.
- **✍️ Escritores ajustados à estrutura nova**: `download_datasets.py` (qualificar → `processed/txt/`), `limpeza_leve_rigel_v2.py` (`--saida` default `processed/parquet`, `--elite-dir` default `processed/txt`), callers `dashboard/services/hf_datasets.py` e `scripts/abrir_espaco_hd.py` (parquet → `processed/parquet`).
- **🔤 Palavra unificadora dos serviços de limpeza/qualidade (escolha do usuário): "TRATAMENTO"** — cobre sanitizar + limpar + verificar + validar. Fluxo: gerar/baixar → `gerados/` → TRATAMENTO (staging `sanitizados/`) → promover → `processed/<tipo>/`.
- **✅ Testado real**: `treinoparquet._pastas_com_parquet('dados/processed/parquet')` → 7 pastas; `treino._base_txt_efetiva()` → `processed/txt`.
- **📋 Pendência registrada**: pastas esqueleto vazias na raiz de `processed/` (14) → mover p/ `apaguemedepois`.

## [SESSÃO 18/08/2026 — manhã] 💾 Liberação de espaço + auditoria de qualidade do acervo + backup ao Google Drive
- **💾 Espaço no disco D: liberado**: `dados/raw/cnmoro_reasoning-v1-20m-portuguese` (84 GB, parquet bruto, não processado) **APAGADO a pedido do usuário** (confirmou "apagar de vez") → D: 32 → 108 GB. Depois a tabela `Montival_fipex-veiculos-brasil` (1,2 GB, dado tabular que não serve p/ chat) também apagada → 109 GB livres.
- **✅ AUDITORIA DE QUALIDADE do acervo (responde "treinei com lixo?"): NÃO.** Evidências: 102 pastas `*_sanitizado` = 0 mojibake real, 782.806 linhas JSON válidas (novo `scripts/validar_jsonl_acervo.py`). TXT de pré-treino (canarim/curtos/datasets) = 0 mojibake na amostra. O SFT (`treinar_com_jsonl.py`) só aceita `messages` e DESCARTA `text`; o pré-treino (`treinov2.py`) só pega pastas com ≥10 `.txt` (jsonl não entra). Logo, o material sujo (brwac 18 GB) ficou PARADO e nunca alimentou o modelo.
- **🧠 LIÇÃO registrada: regex de mojibake com `Ã` solto dá FALSO POSITIVO** (SÃO/MÃE/CÃES são legítimos em PT-BR). Usar só duplo-encoding real: `Ã£|Ã©|Ãª|Ã§|Ã³|Ã¡|Ã­|Ã¼|Ã´|Ã¢|Ãµ|â€|â€œ|â€\u009d|\ufffd`. O primeiro teste (com `Ã` solto) acusou 2.310 mojibakes nas _sanitizado — tudo falso; refeito, deu 0.
- **🆕 Novos scripts automáticos** (regra "nada de executar tudo no CLI"): `scripts/validar_jsonl_acervo.py` (integridade), `scripts/gerar_relatorio_envio.py` (relatório de envio p/ Google Drive, salva em `logs/relatorio_envio_jsonl_20260818.txt`), `scripts/tratar_datasets_brutos.py` (tratamento automático: detecta formato messages/text/alpaca/qna, corrige mojibake via `sanitizador_ptbr`, converte alpaca→messages; saída em `dados/tratados/`; relatório + progresso persistidos).
- **🗑️ Limpeza**: `dados/sanitizados/rigelsanitizado04.jsonl` (0 bytes) removido. `dados/sanitizados` ficou só com 3 arquivos válidos (messages).
- **🔍 Achados da auditoria**: `rss` = duplicata EXATA de `rss_sanitizado` (mesmo MD5); `rigeljsonl_20260802_0136` (bruto) = mesma massa do `_sanitizado` (nomes renomeados); `rigel20260818_064347` (4,6 MB) = mini-backup de aprovados criado hoje 06:43 (deixado intacto).
- **📦 dolphin**: `dados/gerados/parquet/adalbertojunior_dolphin_portuguese/` = `dataset.jsonl` (307 MB) + `dolphin_pt.parquet` (865 MB) + `.cache/huggingface` — download cru do HF, NÃO processado (marcado `[TRATAR][PARQUET]` no `abrir_espaco_hd.py`); precisa limpeza leve.
- **📋 Fluxo de backup combinado**: JSONL → PARQUET → TXT (organizar → validar → usuário envia ao Google Drive → liberar área por fase).
- **📚 Docs atualizadas**: `regras_ouro.py` (docstring corrigida: limites TXT=1000/JSONL=5000/PARQUET=5000 + regras 6-7 de tratamento automático e validação), `README.md`, `agent.md` (regras de ouro do usuário + estado do acervo), `listadetarefas.md` (pendências 18/08).

## [SESSÃO 18/08/2026 — madrugada] 🔧 TREINOPARQUET v1.2.0 — correções críticas + qualidade (a noite do treino)
- **🚨 CRÍTICO — crash no FIM do treino**: o código usava `args.usar_registro` que NÃO existia no argparse → `AttributeError` depois das épocas, ANTES de salvar o modelo final (o treino do Colab ia completar 20 épocas e PERDER tudo). FIX: registro dedicado agora é atualizado pelo próprio treinador (`_atualizar_registro_treino`, schema `registro_pastas_treino.json` — NÃO usa mais `organizar_pastas.incrementar_treino`, que corromperia o arquivo).
- **🐛 Contagem "34 vs 79"**: o log mostrava "2000 de 34 disponíveis" mas depois "72 treino + 7 validação" (79 arquivos) — registro desatualizado. FIX: conta no sistema real, recursivo (`_contar_parquet`), e avisa quando `--max-arquivos` é maior que o disponível (usa todos).
- **🐛 `num_workers > 1` duplicava dados**: `IterableDataset` + `DataLoader` com workers >1 faz cada worker ler o dataset INTEIRO → dados repetidos N× por época. FIX: sharding por worker (`get_worker_info()` → `arquivos[worker_id::n_workers]`).
- **🐛 Validação com os arquivos MAIORES**: o comentário dizia "menores" mas o código sorteava os maiores para validação (perdendo o melhor dado de treino). FIX: val pega os MENORES + guard p/ conjuntos minúsculos (1 arquivo → sem validação em vez de crash; 2-3 → 1 p/ val).
- **🐛 `_chunk_repetitivo` filtro novo descartava TUDO**: verificação de padding olhava o FIM do chunk (onde ficam os PADs) em vez do começo → todo texto curto legítimo era filtrado → 0 batches. FIX: conteúdo deve estar no COMEÇO (padding só no fim); teste focado confirmou 0 → 5 chunks.
- **🛡️ Guard de "0 batches"**: época sem nenhum batch agora ABORTA com mensagem clara (antes: loss 0.0000 enganoso + "melhor modelo" salvo do nada = desperdício de Colab).
- **🛡️ `_processar_parquet` robusto**: aceita `conversation`/`conversations`/`chat`, formato de mensagens ANINHADO `[[turno,...]]`, e cai para `text` quando messages não rende nada.
- **🛡️ Sem "melhor modelo" sem validação**: quando `val_steps == 0`, não avalia/salva melhor modelo (aviso honesto em vez de loss 0.0).
- **🛡️ Checkpoint com retry** (`salvar_modelo_seguro`) — Drive do Colab instável não derruba mais o treino.
- **📈 Qualidade (regra de ouro anti-lixo)**: dedup de chunks idênticos (hash limitado 100k) + filtro anti-repetição (8+ tokens consecutivos iguais) + aviso de MEMORIZAÇÃO (val ~0 com treino alto = decorou, não aprendeu) + amostra ANTES do treino (linha de base).
- **🆕 Novos argumentos**: `--seed` (reproduzibilidade), `--checkpoint`, `--modelo`, `--melhor-modelo`, `--tokenizer` (caminhos personalizáveis, útil no Colab/testes).
- **✅ Testado DE VERDADE** (regra de ouro): mini-dataset PT-BR em pasta temporária (5 parquet: 3 texto + 2 diálogo) → treino completo 1 época: 4 treino/1 validação, 2 batches, loss 10.15, melhor modelo + modelo final salvos, registro incrementado (vezes_treinada 2), TREINO CONCLUÍDO sem crash. Pasta de teste removida.

## [SESSÃO 17/08/2026 — tarde (4ª parte)] 🚫 REGRA DE OURO ANTI-FAKE + 🔎 verificação de fatos com busca
- **🚫 REGRA DE OURO (do usuário): "O RigelSLM NÃO pode ser treinado com fake news, lixo, ou respostas idiotas NUNCA."** — registrada na memória + integrada ao `regras_ouro.py` (novo `verificar_qualidade()`: reporta pastas de geração com .txt NÃO revisados, ignorando descarte).
- **🔎 Novo `scripts/verificar_fatos.py`**: extrai afirmações factuais (números/datas/nomes) do texto e busca cada uma no DuckDuckGo → veredito ✅ confirmado / ⚠️ não encontrado / 🔌 sem busca. Pega "resposta fake" que o juiz (que só analisa padrões) não pega.
- **Rota**: `GET /api/revisao/verificar?pasta=&arquivo=` (em thread, não bloqueia). **Front**: botão "🔎 Verificar fatos" em cada card da /revisar + painel roxo com veredito por afirmação + fonte.
- **✅ Testado REAL**: texto do IBGE (3/3 fatos confirmados com fontes), texto médico de histoplasmose (confirmado, Wikipédia), e o botão na UI (painel mostrou "✅ Fatos confirmados na internet" com as fontes).

## [SESSÃO 17/08/2026 — tarde (3ª parte)] ⚖️ Botão "Verificar com o Juiz" + 🐛 rastro fantasma corrigido
- **⚖️ Botão "Verificar todos" na /revisar**: roda o juiz deepseek-r1:7b em TODOS os suspeitos pendentes (via processo independente, sobrevive ao --reload). Separados automaticamente: ✅ aprovados sobem para o treino (`processed/<pasta>_aprovado/`), ❌ lixo arquivado (`desclassificados/`), 🟡 só os que o juiz confirmar como suspeitos ficam para o usuário. Pré-checagens: RAM ≥ 6 GB + modelo instalado. Barra de progresso + contadores (polling 3s). Novo `scripts/juizar_suspeitos.py` + rotas `POST /api/revisao/juizar` e `GET /api/revisao/juizar/progresso`.
- **🐛 RASTRO FANTASMA corrigido**: depois de aprovar/descartar, o relatório estático de ajuizamento continuava listando o arquivo → "arquivo não encontrado" na lista. FIX: registro persistente em `estado/revisao_decisoes.json`; `listar_suspeitos()` exclui itens já decididos e os que não existem mais. Resultado: 1.597 → 1.581 pendentes, **0 fantasmas**. Decisões antigas do usuário (pré-registro) foram registradas retroativamente.
- ⚠️ **Teste acidental revertido**: um teste do juiz (`--limite 3`) aprovou 1 arquivo real por engano — arquivo restaurado e decisão removida do registro. Lição: NUNCA rodar o juiz em teste sem avisar (ele move arquivos reais).

## [SESSÃO 17/08/2026 — tarde (2ª parte)] 🔍 Página de Revisão de suspeitos + 🧹 Sumário de livros removido
- **🔍 NOVA PÁGINA `/revisar` — "Revisar textos"**: lista os textos marcados como SUSPEITOS pelo ajuizador, agrupados por pasta. O usuário lê cada um (modal "Ler") e decide ✅ Aprovar (move para `dados/processed/<pasta>_aprovado/` = vai pro treino) ou ❌ Descartar (move para `dados/gerados/desclassificados/<pasta>/` = fica fora, NUNCA apaga). Paginação 40/carregar ("Mostrar mais 40"). Novo `dashboard/services/revisao.py` + `dashboard/routes/revisao.py` + link no menu "Mais opções" + busca de atalho.
- **🐛 Corrigido**: relatório de ajuizamento guarda só o NOME do arquivo, mas o ajuizador varre SUBPASTAS (ex.: `gerados_local/_massa/processados/`) → `_localizar_arquivo()` busca recursivamente por nome (666/666 localizados; antes 0).
- **🧹 Sumário de livros NÃO é material de treino** (pedido do usuário): `scripts/livro_para_jsonl.py` ganhou `_remover_sumario()` (remove bloco SUMÁRIO/ÍNDICE do início) + `_parece_sumario()` reforçado. Padrão real dos PDFs = pontos com ESPAÇOS (`TÍTULO . . . . . 04`). Testado: a-filha-do-barao (-1259), contos-populares (-7656), historia-literatura (-66); sem falso positivo (contrabandista/o-bom-crioulo intactos). TXT atualizados + JSONL de livros regenerado e sincronizado para processed (0 sumário em tudo, incluindo sanitizado).

## [SESSÃO 17/08/2026 — tarde] 🐛 CAUSA RAIZ da recursão `_sanitizado` (462 pastas duplicadas!) + proteção do treinador + 📰 Boletim do Rigel
- **🐛 CAUSA RAIZ encontrada (recursão infinita de sanitização)**: `scripts/executor_pipeline.py` → `_descobrir_origens('pasta')` varre `dados/processed/jsonl/**/*.jsonl` e tratava QUALQUER pasta com .jsonl como ORIGEM. O pipeline `--comandos tudo` sanitiza → promove para `processed/jsonl/<origem>_sanitizado/` → na rodada seguinte essa SAÍDA virava nova origem → `_sanitizado_sanitizado...` → loop. Resultado: **462 pastas recursivas, 5.337 arquivos, ~14,8 GB de duplicatas IDÊNTICAS** (MD5 igual entre níveis).
- **🔧 FIX anti-recursão** (2 camadas): (1) `_descobrir_origens` pula pastas com `_sanitizado` no nome; (2) `_rodar_um` pula comando `sanitizar` em pasta `*_sanitizado` (cobre origens fixas manuais). Validado: 358 origens descobertas, 0 com `_sanitizado`.
- **🐛 Treinador crashava com traceback feio**: treinar com as pastas recursivas → "1 exemplo válido" → `ValueError: num_samples should be a positive integer` (conjunto de treino vazio). **FIX em `treinar_com_jsonl.py`**: quando `len(train_indices) == 0` → mensagem clara "Conjunto de TREINO vazio..." + exit 1 (sem traceback).
- **🐛 BOM UTF-8 derrubava o dataset**: arquivos salvos com BOM (PowerShell/Notepad) davam "0 exemplos válidos" mesmo com conteúdo bom. **FIX**: `SFTDataset` lê com `utf-8-sig` + strip de `\ufeff` por linha. Testado real: arquivo com BOM passou de 0 → 1 exemplo válido.
- **🗑️ Limpeza (regra de ouro — nunca apagar direto)**: 361 pastas duplicadas de `processed/jsonl` + 3 staging de `dados/sanitizados` movidas para `D:\Projetos\apaguemedepois\rigelllm_recursao_sanitizada_20260817\` (usuário apaga com calma). Nível 1 (`*_sanitizado` simples) = saída legítima da sanitização, MANTIDO.
- **⏹️ Pipeline "TODAS as atividades" (atv-090615-bd88) parado** — era ele que rodava a recursão; fila de geração #145, dashboard, supervisor, monitor e RSS preservados.
- **📰 NOVIDADE — `scripts/boletim_rigel.py`**: relatório automático em LINGUAGEM LEIGA que lê logs/estados e conta o que aconteceu (treino, geração, erros, saúde disco/RAM/CPU/Ollama, pendências, pastas prontas). Uso: `python scripts/boletim_rigel.py` (ou `--salvar` grava `logs/boletim_rigel.md`, `--json` devolve estruturado). Nunca falha (ignora arquivos ausentes). Testado e salvo.
- **Cache**: `estrutura_jsonl.json` apagado para regenerar (dashboard não lista mais as pastas removidas).

## [SESSÃO 15/08/2026 — noite (sessão autônoma)] 🚫 ANTI-OVERFITTING: promover detecta conteúdo repetido + botões nos Datasets explodidos + /tratamento com "Já tratados"
- **🚫 ANTI-OVERFITTING no "✅ Promover"** (pedido do usuário: "datasets com nomes diferentes mas mesmo conteúdo = overfitting sem saber"): `dashboard/services/treino_local.py` ganhou `_hash_amostras()` (hash MD5 das perguntas/1º turno user, amostras) e `detectar_duplicatas()` — compara amostras do dataset com os já promovidos e AVISA quando o conteúdo é repetido (sobreposição ≥30%).
- **🎯 ACHADO REAL**: `livros` tem 3 duplicatas com 100% de sobreposição — `livros_sanitizado`, `livros_sanitizado_sanitizado`, `livros_sanitizado_sanitizado_sanitizado` (o mesmo material foi sanitizado repetidamente com nomes diferentes). Promover `livros` agora avisa isso e marca `duplicado_de` na carteira. **Treinar livros + os 3 sanitizados juntos = overfitting REAL.**
- **⚡ PERFORMANCE: dedup 47s → 0.02s** (2300x). Antes o dedup relia AMOSTRAS de todos os 437 datasets de `processed` a cada promover (travava a rota e o terminal). Agora há um **índice de hashes persistido** em `estado/indice_hashes.json` (435 datasets indexados) — a comparação lê só o dataset novo + o JSON do índice. `indexar_hashes()` reconstrói; o promover adiciona o dataset ao índice após copiar.
- **🔘 Botões de ação nos "Datasets explodidos" (/datasets)**: cada item agora tem "🧼 Sanitizar" (origem = `dados/gerados/jsonl/<nome>`) e "✅ Promover" (valida + move + verifica repetição), além da flag da carteira (💉 label + situação). Antes a lista não tinha NENHUM botão.
- **🔀 Promover = merge (não bloqueia)**: se o destino já tem arquivos, copia/sobrescreve (merge) em vez de bloquear — livro novo soma ao acervo. Pasta destino vazia (resquício) é apagada e reprocessada.
- **🧼 Painel Sanitizar com SELECT de origem**: o botão "Sanitizar" do painel não dependia mais do "Analisar" — agora há um `<select>` com as pastas de origem disponíveis (a origem escolhida tem prioridade).
- **✅ /tratamento com seção "Já tratados (carteira de qualidade)"**: mostra a carteira mesmo quando `dados/raw` está vazio — lista as pastas em `dados/processed/` com as 4 vacinas (✅/⏳) e situação. Antes a página ficava VAZIA ("é aqui que deveria haver uma lista do que foi tratado").
- **🧹 Limpeza do rastro `adalbertojunior_crawlPT-edu`**: dataset com formato de texto corrido (`{id,source,text,score}`, sem `messages`) dava 100% descarte no sanitizador — não era bug, era incompatibilidade de formato + conteúdo de baixa qualidade (apostas, PT-PT). Pasta com arquivo 0 bytes apagada + `sanitizacao.limpar()`.
- **✅ Testado E2E (navegador + API real)**: rota `POST /api/treino_local/promover` responde em <1s com `duplicatas: [3 de livros, 100%]`; botão "✅ Promover" do `chat_salvos` na UI promoveu (etapa `promovido` marcada, material em `dados/processed/jsonl/chat_salvos`, sem duplicatas).

## [SESSÃO 15/08/2026 — madrugada] 🐛 CAUSA RAIZ do congelamento: DEADLOCK de lock + extração em processo independente + botão Continuar
- **🐛 CAUSA RAIZ ENCONTRADA (era um deadlock, NÃO era a linguagem, NÃO era a máquina)**: `dashboard/services/qualidade.py` usava `threading.Lock()` (NÃO reentrante) e `marcar()` chamava `status()` DENTRO do próprio `with _lock:` → a thread TRAVA para sempre. A extração de PDF ficava presa em 27% após converter o 1º PDF; antes, o reload do uvicorn "escondia" o deadlock matando a thread daemon (parecia "voltar a idle"). **FIX: `threading.RLock()`**. Testado: `marcar` responde instantâneo (antes travava).
- **🔧 Extração de PDF agora roda como PROCESSO INDEPENDENTE** (`scripts/extrair_pdfs_lote.py` via `subprocess.Popen`), não thread daemon — sobrevive ao `--reload` do uvicorn (que mata threads daemon). Estado tem `pid`; serviço `get_estado()` detecta processo morto e marca "interrompido" (nunca fica "rodando" sem dono).
- **▶️ Botão CONTINUAR** no painel de tratamento: quando a extração cai (interrompido/erro), o usuário retoma com 1 clique — o script PULA os PDFs que já têm TXT+JSONL ("⏭️ Já tinha TXT + JSONL — pulando"), não re-extrai.
- **📊 Percentual + LOG em tempo real na extração**: barra avança por subetapa (ler PDF → extrair texto → converter JSONL), log STREAMING do subprocesso (chars/palavras/exemplos/saídas) no painel, tempo decorrido correndo. Regra de ouro "ver acontecendo" atendida.
- **🔒 Blindagem do script**: captura `BaseException` (nunca morre em silêncio), rastro em `logs/extrair_pdfs_lote.log`, `atexit` grava estado final se o processo cair.
- **🐛 Outro bug corrigido**: `promover_para_processed` usava `_pastas_de_datasets()` que deduplica nomes (dataset já em processed era OMITIDO de gerados) → erro falso "Dataset não encontrado em gerados/jsonl" ao re-promover. FIX: busca direta em `PASTA_JSONL/dataset`; script trata destino já existente como "✅ já promovido".
- **Testado E2E no navegador (ambiente real)**: extração iniciada pelo botão, % 7→27→100, log streaming, PDFs apagados após virar TXT+JSONL, estado concluído, botão Continuar aparece ao detectar queda, livros com 5 arquivos visíveis no treino (nada perdido).
- **🏭 KANBAN nas pendências (pedido do usuário: "o status caminha com o material e dá baixa de cada setor")**: cada pendência tem `etapa` (tratar/treinar) e a Central mostra SÓ as pendências do setor em cada bloco. `tratar_livros` virou DINÂMICA na API `/api/pendencias`: se há material cru em `dados/raw` → "aguardando limpeza"; se não (livros já viraram TXT+JSONL, PDFs apagados) → "✅ Material limpo e pronto" (dá baixa sozinha). `plano_treino` movido para o bloco 3 (Treinar). Corrigido erro de JS `qualidade.itens` (guard `?.`).
- **🐛 Esclarecido (não era bug)**: os "red alerts" (🔴) dos livros no Treino Local são contador de REUSO (treinado 3x+), não alerta de qualidade — limpeza/ajuizamento são medidos pela carteira de vacinação (💉), reuso pelo jsonlog. Mensagem no tooltip: "Já treinado 3x — prefira outros arquivos".
- **💉 Carteira de qualidade VISÍVEL na Central** (pedido do usuário: "como eu sei onde já foi tratado?"): cada pasta mostra as 4 vacinas com ✅/⏳ + data + tooltip leigo (🧼 Limpeza PT-BR · 🔤 Encoding · ⚖️ Revisão · 🚀 Promovido). Corrigido registro de `livros` (faltava `verificado_encoding` — execuções antigas travavam no deadlock antes de gravar) → agora "✅ Pronto para treino".
- **🔧 Guards `?.` na prévia do /tratamento** (previa.mensagem/itens/trataveis/nao_trataveis podiam ser null no carregamento → erro no console).
- **📂 NOVA PÁGINA `/carteira` — "Pastas prontas"**: lista as pastas com status (✅/🔄/🥩), as 4 vacinas com data, o CAMINHO físico e botões "📋 Copiar caminho" e "📂 Abrir pasta" (abre no Explorer/gerenciador via `POST /api/carteira/abrir` → `os.startfile`/`xdg-open`) — para copiar os textos para o Google Drive. Filtros por status. Link no card "📚 Textos prontos p/ treino" da Central e no menu "Mais opções".
- **📚 Contagem de livros corrigida na Central**: `/api/pdfs` agora retorna `resumo` (aguardando/tratados_txt/tratados_jsonl/tratados) — o card mostra "5 já tratado(s)" em vez de "0 baixado(s)" (os PDFs foram tratados e apagados, mas o material virou TXT+JSONL — nada se perde).
- **🎯 Mensagem do plano de treino atualizada** (texto do usuário): "O treino rápido deve ser feito preferencialmente com GPU, na sua falta pode usar COLAB, caso queira deixar rodando o treinamento na CPU use o treino Local (mais demorado e custo de energia)."
- **🐛 Bug pré-existente corrigido**: `/api/pendencias` — ajuizar_fila dinâmica usava variável `nome` indefinida na compreensão (caía sempre no except; agora usa `_nome_pasta(p_)` e funciona de verdade).
- **🧠 Modelo padrão da geração NUNCA é o rigel (pedido do usuário)**: `/api/local-generate/modelos` ordena (gerais primeiro: llama3.2:3b, gemma2:2b, qwen2.5:3b...; rigel e deepseek por último). No FRONT (gerar_local + debate_local) a lista é reordenada e o padrão escolhido é sempre um modelo conversacional geral — rigel só se for escolhido; deepseek só para ajuizar/limpar. Testado: `llama3.2:3b` [selected].
- **🔓 Scripts Python (geração via API) REATIVADOS com confirmação CONFIRMO**: botões Diálogos v1 e v2 reabilitados; ao clicar abre modal obrigatório onde o usuário digita "CONFIRMO" para liberar. `/dialogos2` reativado no backend (chama `dialogos2.py` via subprocess com `--modelo deepseek`, `--formato`, `--pasta-jsonl`); checagem de chave antes de rodar. Texto "🔓 Requer chave de API DeepSeek + confirmação CONFIRMO na tela." nos dois cards.
- **🛠️ Seção Preparação e Limpeza reexplicada (as descrições estavam erradas)**: Preparar Dados = valida/limpa/copia p/ `dados/processed` (não é "classificar"); Agrupar = junta .txt P/R em lotes de 500 com backup dos originais; Ultra = BAIXA datasets do Hugging Face p/ `dados/ultratxt` (não é "limpeza avançada"). Adicionada nota de acompanhamento com link para Registros (`/logs`) e as pastas de resultado de cada serviço.
- **⚠️ OBSERVAÇÃO**: o `--reload` do uvicorn não está recarregando o backend (2 processos na porta 8000); as mudanças de backend (ordenação no servidor, /dialogos2) valem após reiniciar o dashboard (run_dashboard.bat). O front já resolve o modelo padrão sem depender disso.

## [SESSÃO 15/08/2026 — noite] 🧭 "Nada se perde" — treino olha TODAS as bases (jsonl/parquet/txt)
- **Bug grave corrigido**: o treino_local só olhava `dados/processed/jsonl` + `dados/gerados/jsonl`. Os 20 scraps de `dados/processed/scrap/` (jsonl E parquet) ficavam PERDIDOS — invisíveis ao treino ("para bonito?").
- **FIX**: `treino_local.py` — `_BASES_TREINO` inclui `processed/scrap`; aceita jsonl+parquet+txt (`_EXTENSOES_TREINO`); funções generalizadas (`_tem_dados`, `_arquivos_dados`) em `_pastas_de_datasets`, `_scan_estrutura_jsonl`, `listar_datasets`. Testado: 20/20 scraps aparecem (total 754 datasets).
- **💉 Carteira de qualidade no treinador**: `treinar_com_jsonl.py` verifica a carteira (sanitizado/verificado/ajuizado/promovido) antes de treinar e AVISA se material está cru (🥩 com o que falta). Flag `--sem-carteira` para ignorar (teste).
- **🔧 Scrap renomeado**: "Copiar sites" → "Extrair dados da WWW" (menu, Central, título da página).
- **🔧 Sites zerados**: `/api/pdfs/scrap-relatorio` marca `zerado` (0 ok + 0 links); `POST /api/pdfs/remover-site-zerado` remove da lista com registro em logs/sites_removidos.log (botão na UI pendente).

## [SESSÃO 15/08/2026 — fim de tarde] 🧹 Limpeza de logs + 📋 Registro de treino + 📚 Livros promovidos automaticamente
- **🧹 CRÍTICA DO USUÁRIO: "você não lida bem com arquivos de log"** → corrigido:
  - Causa raiz: cache `logs/estrutura_cache/estrutura_jsonl.json` VELHO/CORROMPIDO (690 itens TODOS sem nomes) → Treino Local mostrava "0 arquivos" em tudo. Apagado + `listar_datasets()` agora filtra pastas sem .jsonl real e conta de verdade quando cache sem nomes (nunca mostra "0 arquivos" p/ pasta cheia).
  - `supervisor.py` nova `limpeza_geral()` (1x/dia): apaga buffers executor antigos (>15), trunca logs >20MB, apaga caches de scan >2 dias, apaga pastas VAZIAS em dados/gerados/jsonl + sanitizados. Testado (5 buffers + 1 cache + 5 pastas).
- **📋 REGISTRO DE TREINO** (novo): `modelo/registro_treino.json` gravado pelo treinador ao concluir (`_salvar_registro_treino` em treinar_com_jsonl.py): origem (local/colab), epochs, best_val_loss, nivel_modelo_pct, datasets+arquivos. Arg `--origem colab`; rota /treino_colab (jsonl) injeta. Endpoint `GET /api/registro-treino`. Bloco "📋 Último treino" na página /treino_local (selo ☁️ Colab / 💻 local). Trazido junto com o modelo.
- **📚 LIVROS PROMOVIDOS AUTOMATICAMENTE** (fluxo ponta-a-ponta, sem sair da página): `/api/pdfs/extrair` agora chama `promover_para_processed("livros")` após gerar o JSONL → material vai direto p/ `dados/processed/jsonl/livros/`. Ajustado `promover_para_processed` para não bloquear em pasta destino VAZIA. Testado: 5 livros promovidos, bandeiras (1⚫,1🟡,3🔴), aparecem no dropdown de processed do Treino Local.
- **📭 Pastas vazias fora da lista de tratamento**: `listar_entrada()` separa `vazias`; frontend mostra nota ("pasta scrap fica vazia quando copiador não encontra conteúdo") e NÃO deixa marcar pasta vazia.

## [SESSÃO 15/08/2026 — tarde] 🏠 Central (página única) + 🧼 Tratamento ITERATIVO + 🗣️ Linguagem leiga
- **🔤 Encoding PDFs corrigido**: rota /api/pdfs/extrair rodava subprocesso sem PYTHONIOENCODING → filho (cp1252) escrevia "Saída" e o pai (UTF-8) lia "Sa�da". Corrigido com env_py["PYTHONIOENCODING"]="utf-8" nos dois subprocess.run.
- **🧼 Botão "Tratar marcados" agora mostra o PLANO antes** (nada de confirm cego): chama /api/tratamento/prever, exibe o painel de prévia (o que pode/⛔ o que não pode com motivo) e só então a ação "▶ Tratar as N que podem". Usuário nunca mais pergunta "por que não aparece X" — a própria tela explica.
- **🏠 CENTRAL (nova HOME `/`)**: página única com 4 blocos do pipeline (📥 Coletar → 🧼 Tratar → 🧠 Treinar → 💬 Usar), cada um com status real + botão de ação em linguagem leiga. Antiga home em `/visao_geral`. Menu lateral enxuto: **Central · Chat · Mais opções** (colapsável, 16 links internos). Endpoint novo `GET /api/pacote-colab` (conta exemplos de dados/gerados/colab/rigel_colab.jsonl).
- **🧼 TRATAMENTO ITERATIVO** (pedido do usuário: "o usuário não pode ser adivinha dos processos"): novo botão "🔍 Ver o que será feito (N)" → `POST /api/tratamento/prever` mostra o **Plano de tratamento**: cada pasta explicada (✅/⛔) com o MOTIVO em linguagem leiga + botão p/ o caminho certo (ex.: PDF → "Ir para Livros/PDFs"). Botão "▶ Tratar só as que podem". Rejeição nunca mais muda.
- **🗣️ REGRA DE OURO LINGUAGEM LEIGA** (memória permanente): todo texto visível em linguagem de gente; detalhes técnicos atrás de `<details>`; pendências reescritas ("Registros do sistema limpos", "Livros aguardando limpeza", "Falta decidir o treino").
- **🔧 Outros**: spam de 'Limites carregados' corrigido (cache em memória, loga 1x); card do executor mostra RESULTADO real (✅ 494 aprovados) em vez do comando cru (escondido em "ver comando técnico"); pendências com botões EXECUTAR/navegar; pendência ajuizar_fila dinâmica.
- **Testado E2E**: Central renderiza com dados reais; botões navegam; prévia explica livros(⛔PDF→/pdfs)+scrap(⛔vazio)+txt(✅); tratamento real com barra de progresso 100%; backup geral em D:\backup\rigelllm_20260815 (sem dados/).

## [SESSÃO 14/08/2026 — 03h20] 🖥️ jsonl→parquet agora no FRONTEND (painel Executor)
- **Resposta à pergunta do usuário**: SIM, já existia forma no frontend — o painel **Executor** tinha o comando "🧹 Limpeza leve v2" (`limpeza_leve` → `rigel_sft.parquet`, mas com limpeza PT-BR/dedup/qualidade).
- **➕ NOVO no Executor**: comando **"📦 Converter jsonl→parquet (direto, sem limpeza)"** (`converter_parquet` na whitelist → `scripts/converter_jsonl_parquet.py`). Escolhe a pasta/arquivo com .jsonl no dropdown (origem dentro de dados/) → gera `dados/processed/parquet_massa/massa_sft.parquet` + `massa_pretrain.parquet` (schema padrão). Excluído do modo "TODAS" (não é pipeline por origem).
- **UI `/executor`**: opção nova no dropdown + tooltips nos selects de comando/origem + rótulo "PASTA/ARQUIVO com .jsonl" p/ limpeza_leve e converter_parquet.
- **Testado E2E via API**: 2 exemplos de teste → status concluído, `massa_sft.parquet` 2 linhas + pretrain 2 linhas; dropdown validado na página. Artefatos de teste removidos.

## [SESSÃO 14/08/2026 — 01h20] 🖥️ Executor: qualificação de dados UNIVERSAL (txt/json/parquet) + multi-pasta + Testar antes + TXT elite 20%
- **📋 Plano implementado (pedido do usuário)**: menu do Executor com nomes coerentes + descrição (o que faz, entrada, saída); origens casam com as pastas disponíveis; qualificação vale p/ txt/json/parquet; retenção de TXT elite 20%; modos arquivo/pasta/várias pastas; testar antes.
- **🔍 Menu do Executor reorganizado** (inspeção 1º, transformação depois), cada um com descrição sob o select:
  1. 🔍 Verificar encoding/mojibake (não altera) · 2. 📊 Diagnóstico de caracteres ABNT2 (não altera) · 3. 🧼 Sanitizar PT-BR → JSONL · 4. 🧹 Limpeza leve → PARQUET (dedup+PT-BR+qualidade) · 5. 📦 Converter direto → PARQUET (sem limpeza)
- **🌐 Scripts universais**: `verificar_encoding_jsonl.py` e `diagnostico_chars.py` agora aceitam **txt/json/jsonl/parquet** (pasta ou arquivo). Parquet: extrai colunas string; json/jsonl: diagnostica só o CONTEÚDO (não a sintaxe). Testado: mojibake detectado em .txt, parquet/jsonl analisados.
- **📁 `listar_origens` universal**: inclui pastas com TXT e PARQUET (raso, limitado) além de jsonl; cada item com `formatos`; nomes limpos; **orçamento de tempo (~6s)** — nunca trava o painel (a varredura antiga com `glob("**")` sem limite pendurava o endpoint com 2 uvicorns no ar).
- **🔁 Multi-pasta**: origem com `;` → rota manda p/ o `executor_pipeline` (uma por vez, em série). `converter_parquet` adicionado ao pipeline; `_montar_cmd` passa a PASTA aos scripts universais (não exige .jsonl).
- **🔍 Botão "Testar antes (não altera)"** na UI: roda `verificar_encoding` na origem selecionada (read-only) antes de executar.
- **🧹 Retenção de TXT elite 20%** (regra do usuário — não converter 100%, não apagar 100%): `limpeza_leve_rigel_v2.py` ganhou `--elite-pct` (default 20) + `--elite-dir` (default `dados/processed/txt_elite`). Os TXT que passam TODAS as bandeiras são pontuados (TTR+extensão) e os 20% melhores ficam como `.txt` (com `_manifesto.json`); o resto converte p/ parquet. Testado: 5 txt → 2 retidos / 3 convertidos.
- **🛡️ Regra respeitada**: material criado pelo sistema já no padrão NÃO é apagado. Testado E2E: origens 4,6s (421 itens), multi-pasta 2 OK, elite via Executor ok, página validada (423 origens, filtro txt/json/parquet, checkbox multi, botão Testar).
- ⚠️ O timeout de `/origens` na sessão anterior era **conflito de 2 uvicorns na porta 8000** (não o scan) — usuário reiniciou via `run_dashboard.bat`; servidor voltou (0,1s). Regra do fluxo do dashboard mantida.

## [SESSÃO 14/08/2026 — 00h40] ♻️ Regra "reciclar vs descartar" + lote antigo arquivado (decisão por evidência)
- **♻️ NOVA REGRA DE OURO (memória do usuário)**: "se puder reciclar, recicle" — dado gerado que pode ser salvo AJUSTANDO às condições atuais deve ser salvo; MAS se o modelo for PREJUDICADO como material de treino (prompts sem sentido, texto truncado/repetitivo, artefatos, idioma misturado) → NÃO pode ficar como treino: arquivar fora do pipeline e CRIAR material novo. Não acumular sem propósito (espaço/tempo não são infinitos). Decisão por EVIDÊNCIA.
- **🔍 Evidência do lote antigo (948 exemplos, 08-10/08)**: amostras mostraram user = "Escreva sobre o tema: <nome de arquivo gerado>" (prompt lixo) + conteúdo truncado/repetitivo ("essênc essência", "contand contand", "do qu que") + inglês ("ISBN late lately"). → **Prejudicaria o modelo** (SFT com prompts sem sentido).
- **🗄️ Ação**: lote **arquivado em `dados/arquivo/massa_antiga_20260808_10/`** (jsonl_originais 65 + jsonl_padrao 65 + parquet_direto 2) com `README_por_que_arquivado.txt` — NADA apagado, fora do pipeline de treino. `massa_final` limpo (0 jsonl soltos), `processed/jsonl` sem resíduos. **Não rodar limpeza_leve neles** (os prompts continuariam lixo).
- ✅ `scripts/padronizar_jsonl.py` e `scripts/converter_jsonl_parquet.py` continuam disponíveis (reutilizáveis) para os dados NOVOS.

## [SESSÃO 14/08/2026 — 00h15] 📦 Jsonl antigos padronizados + jsonl → parquet (schema de treino)
- **🔍 Auditoria dos 65 jsonl de `massa_final`**: TODOS fora do padrão (0 com `_id`, 0 com `system`; estrutura antiga `messages[user,assistant]` + `tipo/estilo/categoria/fonte/data`).
- **🆕 `scripts/padronizar_jsonl.py`** (reutilizável, nunca apaga): eleva jsonl ao schema padrão — `messages` com `system` (do tipo ou padrão), `_id` (md5), `_fonte`, `_tipo` (qna se user tem "?"), `_categoria`, `_assunto` (derivado; "tema geral" se o nome não guarda o tema), `_estilo`, `_idioma` pt-BR, `_data`, `_nota`. Escreve `_padrao` ao lado (ou `--sobrescrever` com .bak). **Rodado: 948 exemplos padronizados, 0 inválidas.**
- **🆕 `scripts/converter_jsonl_parquet.py`** (reutilizável): jsonl → parquet com o schema de treino (mesmo do `limpeza_leve`/`scrap`): `rigel_sft.parquet` (coluna `messages` = list<struct<role,content>>) + `rigel_pretrain.parquet` (coluna `text`). **Rodado: 948 linhas SFT + 948 pretrain em `dados/processed/parquet_massa/`** (schema verificado lendo de volta). Conversor suporta `conversations/chat` também.
- ✅ **Possibilidade confirmada**: o caminho OFICIAL jsonl→parquet também existe via `limpeza_leve_rigel_v2.py --origem <pasta>` (faz limpeza PT-BR/dedup/qualidade antes de gravar `rigel_sft.parquet`).
- ⚠️ Originals dos jsonl mantidos (regra: não apagar); os `_padrao` ficam ao lado.

## [SESSÃO 13/08/2026 — 23h50] 📦 Formato JSONL agora no schema PADRÃO do Rigel (campos completos)
- **🐛 Problema (pergunta do usuário)**: ao gerar `--formato jsonl`, o `gerar_massa_local.py` escrevia campos FORA do padrão (`tipo/estilo/categoria/fonte/data`, sem underscore) e `messages` SEM o role `system` — descumpria a regra de campos completos (`esquema_jsonl.md`).
- **✅ Fix em `scripts/gerar_massa_local.py`**:
  - `messages` agora tem `system` (prompt do tipo, ex.: "Você é um dicionarista...") + `user` + `assistant`.
  - Metadados completos: `_id` (md5 pergunta|resposta, 16 chars), `_fonte` (geracao_local_massa/<arquivo>), `_tipo` ("qna" se tem pergunta, senão "artigo"), `_categoria`, `_assunto` (assunto REAL — novo marcador `#ASSUNTO:` gravado na geração), `_estilo`, `_idioma` (pt-BR), `_data`, `_nota` (4).
  - Testado E2E real (3 itens, categoria objeto): chaves `['_assunto','_categoria','_data','_estilo','_fonte','_id','_idioma','_nota','_tipo','messages']`, roles system/user/assistant, `_assunto` = "furadeira de impacto" etc. Artefatos de teste removidos (não poluem treino).
- ⚠️ Os ~65 jsonl antigos em `massa_final` (gerados antes) podem ter o schema antigo — conferir antes de usar; os NOVOS saem no padrão.

## [SESSÃO 13/08/2026 — 23h30] 🎯 Pergunta × TIPO de resposta alinhados (fila parada e revisada)
- **⏹️ Fila parada + ordem #4 removida** (era a única lançada ANTES da correção das perguntas — 10 itens com código antigo). As **34 ordens restantes continuam aguardando** e vão gerar com o código NOVO (perguntas são geradas na execução, não ficam salvas na ordem).
- **🆕 Compatibilidade pergunta × TIPO de resposta** (pedido do usuário: "ajuste outras perguntas para outros tipos de respostas"):
  - `_tipos_compatíveis(natureza, tipos)` em `gerador_categorias.py`: tipos restritos só entram se a natureza combinar — `receita`→alimento, `tutorial`→ferramenta/objeto/ação/profissão, `entrevista`→pessoa/obra, `resenha`→obra/objeto/conceito, `relatorio`→lugar/animal/doença/evento... Criativos/gerais valem p/ tudo. NUNCA retorna vazio.
  - `_PREFIXO_POR_TIPO`: a PERGUNTA agora se alinha ao formato — `receita`→"Como preparar X?", `tutorial`→"Como usar/fazer X?", `entrevista`→"Quem é X?", `dicionario`→"O que é X?".
  - `montar_pergunta(categoria, assunto, tipo_id="")` aceita o tipo e prioriza prefixos compatíveis.
  - `gerar_massa_local.py`: no modo categoria/rss filtra os TIPOS pela natureza do assunto E realinha a pergunta ao tipo escolhido (e atualiza o tema exibido).
  - **🐛 Fix detecção de ferramenta**: sufixo agora é verificado em QUALQUER palavra (`processador de alimentos`→ferramenta, antes caía em "Como conservar") + termos de eletrodomésticos (liquidificador, cafeteira, geladeira...). Tutorial não sugere mais "conservar/preparar".
- **Testado REAL**: estatística 300-400 gerações p/ chave Philips, processador de alimentos, feijoada e dengue → **0 pares errados** (ferramenta nunca recebe receita/conservar/limpar; alimento recebe receita; doença recebe relatório). **E2E no Ollama** (tinyllama, categoria objeto): perguntas salvas corretas e alinhadas ao tipo ("Qual a finalidade de plaina de madeira?", "O que é tinta guache escolar?", "Como funciona interruptor?"). Artefatos de teste limpos.
- ⚠️ A fila está **parada** (34 ordens aguardando) — o usuário decide quando ▶️ Iniciar.

## [SESSÃO 13/08/2026 — 23h] 🎯 Perguntas certas p/ o tipo de assunto (gerador de categorias)
- **🐛 Problema (pedido do usuário)**: a fila de geração às vezes cria PERGUNTA ERRADA para o assunto — ex.: "Como conservar uma chave philips?" quando o certo é "O que é / Para que serve" (é uma ferramenta para parafusos). O gerador sorteava o prefixo **sem saber o TIPO do assunto**.
- **✅ Fix em `dashboard/services/gerador_categorias.py`** (vale p/ fonte `categorias`, `misto`, `rss` e prévia):
  - `_natureza_assunto()` — detecta a natureza: ferramenta/objeto (heurística de termos + sufixos `-dor/-deira/-te`), alimento, animal, lugar, pessoa, sentimento, ação, doença, obra, profissão, genérico.
  - `_RISCO_PREFIXO_POR_NATUREZA` — prefixos que só fazem sentido p/ certos tipos ("como conservar"→alimento/objeto/sentimento, "como preparar"→alimento/ação, "como tratar"→doença, "como se reproduz"→animal, etc.).
  - `_prefixos_compatíveis()` — filtra os prefixos da categoria pela natureza do assunto; **NUNCA retorna vazio** (fallback p/ perguntas de definição: "O que é / Para que serve / Como funciona" — válidas p/ qualquer assunto).
  - `montar_pergunta()` e `gerar_perguntas_relacionadas()` agora usam só prefixos compatíveis.
- **Testado REAL**: `chave Philips` → pool sem "Como conservar/limpar/armazenar" (só funcionais); `feijoada` mantém "Como preparar/armazenar"; `ansiedade` mantém "Como lidar/desenvolver"; `dengue` mantém "Como tratar/prevenir". **500 perguntas p/ chave Philips → ZERO erradas** (distribuição saudável). Prévia no `/gerar_local` confirmada no servidor ao vivo.

## [SESSÃO 13/08/2026 — 22h] 📚 Objetivo #2: Scrap de livros no dashboard + 📱 Baixar GGUF no celular
- **📚 Scraper de livros agora roda PELO DASHBOARD** (`/pdfs`) — não é mais só CLI:
  - `scrap_livros_pdf.py`: **progresso real** (`logs/scrap_progresso.json` a cada item: site X/N, %, ok/erro/pulados/dups, decorrido); **dedup por conteúdo** (SHA-1, `logs/scrap_hash_registry.json` — mesmo livro baixado de 2 sites vira 1 só); **relatório por site** (`logs/scrap_relatorio.json`); contador `dups`; `_pos_processar` (filtro PT-BR + hash); `slug_dominio` agora aceita domínio puro (sem http://).
  - **🐛 Fix filtro `--site`**: casava URL inteira contra slug do domínio (nunca acertava) e, ao filtrar por URL exata de PDF, NÃO esvaziava a lista de sites abertos → processava o escolhido + TODOS os abertos. Corrigido: URL exata → esvazia a outra lista; domínio → casa por slug.
  - Executor whitelist `scrap_livros` (origem = site, args = `--limite/--verificar/--profundidade`; **excluído do modo pipeline "todos"** — o próprio script já varre as listas).
  - `pdfs.py`: `GET /api/pdfs/sites` (dropdown automático), `GET /api/pdfs/scrap-progresso`, `GET /api/pdfs/scrap-relatorio`.
  - **UI `/pdfs`**: seção 🚀 Rodar scraper — dropdown com 30 sites (2 grupos: PDFs + abertos), limite, 🔎 verificar, profundidade; **confirmações RIGOROSAS** antes de rodar (aviso forte no modo "todos") e antes de parar; barra de progresso real; tabela 📊 relatório por site; detecta parada/erro do executor (poll).
  - **Testado E2E REAL**: baixelivros com limite 2 → **ok=2, erro=0, pulados=2, dups=0, pct 100 em 14s**; 4 livros no acervo (`ansia-eterna`, `historia-da-literatura-brasileira`, `o-relogio-de-ouro`, `uma-senhora`); relatório + 7 hashes gravados; página validada (30 sites, 7 arquivos, console limpo).
- **📱 Baixar modelo no celular (NOVO)** — pedido do usuário:
  - `convert.py`: `GET /api/convert/download/{nome}` (GGUF por FileResponse, path-safe) + `GET /api/convert/qr/{nome}` (QR PNG com URL da rede local via pacote `qrcode` instalado) + `/status` enriquecido (`ip_rede`, `url_base`, `url` por GGUF).
  - **UI `/converter`**: seção "📱 Baixar modelo no celular" — link 📥 Baixar por arquivo, **QR code** para escanear, e instruções Termux/llama.cpp (compilar + `llama-cli -m <gguf>`).
  - **Testado**: download 36 MB OK (magic `GGUF`), QR PNG OK (URL `http://192.168.3.150:8000/...`), página valida (3 GGUFs, QR visível, console limpo).
- ⚖️ Extras: `_veredito_aprovado` no `avaliador_qualidade.py` (matcher tolerante — juiz que escreve "Aprovaço" não perde o veredito; testado 9/9) e fix do ajuizar de pasta única (ver sessão anterior, testado E2E).

## [SESSÃO 13/08/2026 — 20h45] 🔧 treinoparquet.py: restauradas as 4 pastas + auto-atualização
- **🐛 Problema**: o usuário removeu a lista `PASTAS_TREINO` (as 4 pastas com .parquet: `limpo_alpaca`, `limpo_canarim`, `limpo_wikipedia`, `limpo_madras1_v2`) enquanto editava p/ auto-atualizar. O auto-detect voltava vazio porque o `REGISTRO_PATH` apontava pro `registro_pastas.json` **compartilhado** com o `organizar_pastas` (schema diferente — não tinha as limpo_*).
- **✅ Fix**: restaurada `PASTAS_TREINO` (seed com as 4 pastas — recuperadas do git, "backup" existia!) + reescrito `_resolver_pastas_treino_com_registro`:
  - SEMPRE parte das pastas conhecidas (seed) que existem;
  - usa registro **dedicado** `registro_pastas_treino.json` (NÃO corrompe o `registro_pastas.json` do organizar — verificado intacto, 568 pastas);
  - **AUTO-ATUALIZAÇÃO**: escaneia e ADICIONA qualquer pasta nova com .parquet (self-update) — forçada com `--atualizar-registro` ou quando falta pasta conhecida;
  - fallback [base] só se nada for encontrado.
- **Testado real**: scan achou **6 pastas** com .parquet e gravou o registro dedicado; segunda chamada sem scan usa seed+registro (rápido). Zero erros.
- **➕ Seed atualizado p/ 6 pastas** (pedido do usuário): as 4 limpo_* + `rigelparquet` (4 parquet) + `scrap` (26 parquet) — agora constam na `PASTAS_TREINO`.
- ⚠️ lição: conferir o git ANTES de concluir "não tenho backup" — o repositório tinha a versão com as 4 pastas.

## [SESSÃO 13/08/2026 — 20h30] 🛡️ Fila v2 ROBUSTA (pausa, recuperação, guarda, diagnóstico, travamento)
- **⏸️ Pausar / ▶️ Continuar / ⏹️ Parar persistentes**: `pausar()` seta `pausado` no estado + mata o worker; ordens não processadas continuam 'aguardando' (pode **desligar o PC e retomar amanhã** — o estado fica em `estado/fila_geracao.json`). `continuar()` limpa pausa e re-inicia.
- **🔄 Recuperação de órfãs**: ordem 'rodando' de execução anterior (parou/desligou/travou) volta a 'aguardando' — no worker e nas rotas (`recuperar_orfas()`), com guarda `_fila_worker_rodando()` para não resetar a ordem em execução.
- **🛡️ Guarda de recursos**: antes de cada ordem, checa memória/disco via `estrutura_cache` (config_recursos.json) — se insuficiente, espera até 10 min; se continuar ruim, encerra e a ordem volta a aguardar (não trava, não queima SSD).
- **🚨 Travamento tratado**: cada ordem roda como **SUBPROCESSO** vigiado (`taskkill /T` para matar a árvore): stall (sem progresso por 4 min) → mata e reinicia (até 2x); timeout total (meta × tempo + folga) → trata; reinícios esgotados → ordem vira 'erro' com diagnóstico no log.
- **🔁 Fallback com TROCA DE PERGUNTA**: se no modo categoria/rss o modelo não responde, o `gerar_massa_local` **troca a pergunta** por um prompt simples (`Escreva sobre {assunto}`) e conta `retries` no progresso.
- **🎛️ Comprimento controlado (parâmetros da Rigel)**: `_gerar_um` agora usa a **API do Ollama** com `num_predict` = `max_tokens` do template + `temperature` (nem muito longo, nem muito curto); fallback p/ `ollama run`. Novo `--timeout` por item.
- **⚠️ Diagnóstico de erro alto**: taxa de erro ≥40% → log com as causas prováveis (modelo incapaz / timeout curto / pergunta não encaixa / RSS sem categoria); ≥20% → aviso.
- **📜 Log**: `logs/fila.log` (append) + log por ordem (expansível no painel, via `GET /fila/ordem/{id}`) + barra com retries.
- **🗑️ Limpar fila toda** (`limpar-tudo`, mantém a rodando) + **⏳ estimativa** (`estimativa_seg` por template, mostrada no painel).
- **Testado E2E real** (tinyllama): 2 ordens → pausa durante execução → recuperação de órfã → continuar → **3 ordens concluídas / 0 erros** ✅. Rota `/fila/iniciar` agora **recusa** se já há worker vivo (evita duplo processamento).

## [SESSÃO 13/08/2026 — 19h30] 🐛 Fix categorias/prévia + 🧾 FILA DE GERAÇÃO (pipeline em série)
- **🐛 CAUSA RAIZ "categorias não abrem / prévia não funciona"**: os endpoints `/api/local-generate/*` estão TODOS definidos direto no `dashboard/main.py` (o router `dashboard/routes/local_generate.py` é código morto, NUNCA incluído no app). As rotas novas de categorias/RSS que eu tinha colocado no router nunca registravam → 404 mesmo após reiniciar. **Fix: movidas para `main.py`** (`GET /categorias`, `/categorias/amostra`, `/rss-titulos`) + removidas do router morto. Validado: HTTP 200, 34 categorias / 9.065 assuntos / 167 títulos RSS.
- **🧾 NOVO: Fila de Geração (pipeline em série — nunca paralelo)** — pedido do usuário:
  - `dashboard/services/fila_geracao.py` — estado `estado/fila_geracao.json` (ordens com modelo/templates/estilos/fonte/categorias/rss_limite/meta/formato/ajuizar/status), progresso `logs/fila_progresso.json`.
  - `scripts/executar_fila_geracao.py` — worker em SÉRIE: processa UMA ordem por vez (via `gerar_massa_local.main()`), re-lê a fila entre ordens (ordens adicionadas DURANTE a execução entram), ajuíza ao concluir se marcado (txt + template específico), encerra quando a fila esvazia. Sobrevive a reload (roda via Executor, nome "Fila de geração").
  - Rotas em `main.py`: `GET /fila` · `POST /fila/adicionar` · `/fila/remover` · `/fila/limpar` · `/fila/iniciar` (Executor) · `/fila/parar` (mata a atividade) · `GET /fila/progresso`.
  - **UI `/gerar_local`**: a antiga "Geração em MASSA" virou **"🧾 Fila de Geração"** — monte ordens (modelo + template 🎲 específico + estilo 🎲 + fonte tópicos/categorias/misto/rss + categoria + quantidade 1-2000 + formato + ⚖️ ajuizar), veja a lista de ordens com status (⏳/🔄/✅/❌), botões ▶️ Iniciar / ⏹️ Parar / 🧹 Limpar, e barra de progresso real (fila X/N + % + ⏱️ decorrido + 🕐 restam + ⏳ média). Mantidos os botões ⚖️ Ajuizar + painel.
  - **Lista gigante de tópicos da "Geração via Ollama" agora é COLAPSÁVEL** (fechada por padrão, botão "📚 Ver tópicos sugeridos").
  - **Testado REAL**: worker processou 3 ordens em série (10 perguntas → 5 artigos → 3 receitas) com gml simulado, capturou ordem nova adicionada durante, progresso correto; endpoints validados via TestClient. **E2E no servidor AO VIVO**: fila → executor → worker → Ollama (tinyllama) → pós-processamento → arquivo em `massa_final` ✅ (status concluido, gerados=1, erro=0). Tudo limpo depois.
- ⚠️ Servidor precisa reiniciar (`run_dashboard.bat`) p/ carregar tudo. **Obs: o servidor do usuário já recarregou — categorias (34/9.065), rss (167) e fila operando no ar.**

## [SESSÃO 13/08/2026 — madrugada/19h] 🗂️ categories.py no gerador LOCAL (4 partes + seletor)
- **Novo módulo `dashboard/services/gerador_categorias.py`** — transforma o `categories.py` (34 categorias, **9.065 assuntos**) em FONTE DE TEMAS para o gerador local:
  - `sortear_par()` / `montar_pergunta()` (prefixos + templates + perguntas combinadas) / `montar_prompt_por_pergunta()` (pergunta + formato do tipo + instruções da categoria + estilo) / `obter_instrucoes()` (guia factual por categoria) / `detectar_categoria()` (fuzzy, acerta títulos RSS) / `gerar_perguntas_relacionadas()` (título RSS → perguntas da categoria) / `listar_categorias()` / `contar_assuntos()` / `amostra_perguntas()` / `carregar_titulos_rss()` (cache 6h em `logs/rss_titulos_cache.json`, 167 títulos).
- **`scripts/gerar_massa_local.py`**: novo `--fonte topicos|categorias|misto|rss` + `--categorias` + `--rss_limite`. Nos modos categoria/rss, o tema vira **PERGUNTA contextualizada** e o arquivo salva com marcador `#PERGUNTA:` (vira o `user` no JSONL → par SFT de qualidade) + categoria no nome do arquivo/metadados. Progresso enriquecido: `categoria`, `assunto`, `fonte`, `decorrido_s`, `previsao_s`, `media_s`, `restantes`. Fallback rss→categorias se sem títulos.
- **Rotas novas** (`dashboard/routes/local_generate.py`): `GET /api/local-generate/categorias`, `GET /categorias/amostra`, `GET /rss-titulos`. `POST /api/local-generate/gerar-massa` (`dashboard/main.py`) agora aceita `fonte/categorias/rss_limite`.
- **UI `/gerar_local`**: seletor "🗂️ Fonte de temas" (📚 Tópicos | 🗂️ Categorias | 🔀 Misto | 📰 RSS), dropdown de categoria com contagem, input de limite RSS, botão "Prévia" (sorteia exemplos de perguntas), prévia de títulos RSS, e barra de progresso com **⏱️ decorrido + 🕐 restam ~ + ⏳ média s/item + 🗂️ categoria atual**.
- **Testado REAL (sem queimar GPU)**: módulo autoteste (detecção de categoria acertando "Impressão 3D"→ciencia_tecnologia, "Dengue"→sintomas_doencas, "Caetano Veloso"→musica); integração `--fonte categorias` (4 itens, marcador + categoria no nome, progresso enriquecido) e `--fonte rss` (167 títulos). Rotas validadas no router via import direto.
- ⚠️ **Servidor precisa reiniciar** p/ carregar as rotas novas (o worker atual é de 14:42; `--reload` não trocou — conflito com o watchdog). Usuário vai reiniciar via `run_dashboard.bat`.

## [SESSÃO 13/08/2026 — noite] ⚖️ Sistema "Ajuizar" + bandeiras ✓ de verificação + dolphin concluído
- **🐬 DOLPHIN CONCLUÍDO (17:16)**: `limpeza_leve_rigel_v2.py` processou **860.607 lidas → 670.687 SFT** (78%) / 172.033 descartados (29.261 não-PT, 54.857 qualidade, 87.914 duplicados). Gerou `dados/processed/rigel_sft.parquet` (**691 MB, 670.687 linhas, coluna `messages`**) + `limpeza_relatorio.json`. **Validado** (UTF-8/PT-BR correto, sem mojibake — console do Windows exibe mal, é falso alarme). Pronto p/ treino no **Colab** (decisão do usuário: NÃO treinar local).
- **⚖️ NOVO: Sistema "Ajuizar" (bandeiras ✓ de qualidade)** — pedido do usuário ("não tem bandeira verdinha de verificadas"):
  - `dashboard/services/avaliacao.py` — registra pastas **verificadas** em `estado/avaliacao_pastas.json`; `listar_pastas()` (🟢 verificada / 🟡 pendente), `marcar_verificada()`, `desmarcar()`.
  - `scripts/ajuizar_pastas.py` — pipeline: varre pastas de geração pendentes, roda camada 1 (gates) + camada 2 opcional (`--juiz` deepseek-r1:7b) e **marca bandeira ✓ ao concluir 100%**. Progresso em `logs/ajuizar_progresso.json`, relatório em `logs/ajuizar_relatorio.json`.
  - Rotas: `POST /api/executor/iniciar` aceita `avaliar_qualidade` (whitelist, `--pasta` opcional + `--juiz`); `GET /api/executor/avaliacao/pastas`, `GET /api/executor/avaliacao/progresso`, `POST /api/executor/avaliacao/desmarcar`.
  - UI `/gerar_local`: botão **"⚖️ Ajuizar (N pendentes)"** na linha da geração em massa + painel com lista de pastas/bandeiras, **dropdown de juiz** (Nenhum/deepseek), **checkbox "Verificar ao gerar (~2x mais lento)"** (desligado por padrão) e barra de progresso real.
  - **Testado REAL**: ajuizou 6 pastas (1.232 txt) → 615 aprovados / 610 suspeitos / 7 lixo; bandeiras ✓ marcadas (pendentes 6→0). `gerados_local` tem 594 suspeitos (43%) — candidatos p/ juiz deepseek.
- **⚖️ Juiz de Qualidade VALIDADO** (`avaliador_qualidade.py --juiz`): `deepseek-r1:7b` instalado (4,7 GB) e funcionando. Teste: 5 arquivos → 4 aprovados / 1 suspeito (juiz analisou o suspeito). ⚠️ Rodar com `$env:PYTHONIOENCODING='utf-8'` (emoji quebra no cp1252).
- **📱 Fix bolinhas mobile**: causa raiz = `@media (max-width:768px) .sidebar nav a span { display:inline !important }` deixava TODAS as bolinhas visíveis no mobile. Fix: regra mais específica `.sidebar nav a .nav-atv { display:none !important }` no media query. Validado: mobile 0 visíveis / desktop 17 (funcionando).
- **🛡️ Watchdog `run_dashboard.bat` ROBUSTO**: timeout 5s→**30s**, monitor 5s→10s, **removeu `taskkill /T`** (não mata mais os filhos do executor), e abre navegador no **IP da rede** (`URL_PUBLICA` auto-detectado, ex.: 192.168.3.150) em vez de 127.0.0.1. Causa raiz das mortes do dolphin era o watchdog matando a árvore por lentidão >5s.
- **🗂️ `listadetarefas.md` criado** (raiz) — 5 tarefas pendentes: 1 Juiz Qualidade (✅ testado), 2 PDF/Livros scrap, 3 🚫 desabilitar geração via API em `/gerar_local` (**NÃO apagar**), 4 ✅ bolinhas mobile, 5 🚫 desabilitar "Geração via DeepSeek" em `/gerar_dados` (**NÃO apagar**).
- **🧠 Aprendizado registrado na memória**: mapa de sanitizadores por tipo (JSONL→gerar_sanitizados, PARQUET→limpeza_leve, TXT→limpeza, JSON/CSV→createjsonl, qualidade .txt→avaliador_qualidade), como o avaliador roda, e decisão de treino no Colab.

## [SESSÃO 13/08/2026 — tarde] 🟢 Bolinha de atividade no menu + Reiniciar no Executor + dolphin respawnado
- **🔵 Bolinha de ATIVIDADE ativa no menu lateral** (`base.html`, SOMENTE desktop): igual à bolinha de "Ollama: Online"/"Busca: Online". Acende **verde piscando** ao lado da aba onde há processo rodando no executor (mapa por palavras-chave: Treinamento/Treino Local=treino, Tratamento=sanitiz/limpeza, Gerar Dados=ollama, Datasets=download, Executor=sempre, etc.) e **âmbar** quando há atividade `aguardando` decisão. Tooltip com o nome da(s) atividade(s) + contador "Atividades: N" no rodapé. Poll a cada 8s via `/api/executor/status`.
- **💀 Detecção de processo MORTO (estado fantasma)**: `_detectar_processos_mortos()` no executor — atividade marcada `rodando`/`rodando_externo` cujo PID não existe mais vira **status `morto`** + mensagem + log (`listar()`/`status()` chamam a varredura). Corrige o caso do dolphin que morria em silêncio e o painel continuava dizendo "rodando".
- **🔄 Botão "Reiniciar" no Executor**: nova rota `POST /api/executor/reiniciar` + função `reiniciar(aid)` — recomeça atividade morta/interrompida/erro com o **mesmo comando registrado** (`comando_lista`), zera o contador de reinícios, passa pelo guardião e cria nova atividade registrada (recomeço previsto/tratado DENTRO do sistema — pedido do usuário).
- **🛡️ Subprocessos desanexados no Windows**: `iniciar()` e `_reiniciar_apos_reload()` agora usam `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` — o filho não é cancelado junto com o uvicorn/watchdog (regra: atividade roda em PARALELO ao servidor).
- **🐬 Dolphin respawnado (3ª rodada)**: após cair 6x pelos reloads das edições, usei o fluxo do sistema (`/continuar` → zera contador, respawn) — **PID 22812+21660 rodando** (~1.5GB), progresso avançando (1000 lidos em 30s às 14:09). ⚠️ **NÃO editar `dashboard/*` enquanto o dolphin roda** (cada edição → reload → mata o filho via watchdog `taskkill /T`).
- **🐛 `config_recursos.json`** estava de volta com `CPU_MAX_USO_PCT: 70` (algo regenerou) → corrigido para **90.0**.
- **🧪 Testes reais**: detecção de morta ✅, reiniciar (cria nova atividade, zera contador, recusa rodando) ✅, bolinha acendendo em 4 abas + rodapé "Atividades: 1" ✅ (validado via Playwright).

## [SESSÃO 13/08/2026] 🗑️ "Abrir espaço no HD" + guardião CPU + header mobile
- **🗑️ Novo pipeline `scripts/abrir_espaco_hd.py`** (botão "Abrir espaço no HD" no Executor): varre `dados/gerados`+`raw`, detecta tipo (TXT/JSONL/parquet/pretrain), trata (converte TXT→JSONL qna/artigo, sanitiza SFT, limpeza leve p/ parquet/pretrain), **promove p/ processed e apaga a origem** + limpa staging. Modo `--simular` (ensaio sem apagar) + `--descobrir`. Rota `POST /api/executor/espaco` (roda como atividade do executor, sobrevive a reload, barra de progresso via `logs/espaco_progresso.json`).
- **🧠 Detecção de corpus `text`-only (pré-treinamento)**: JSONL sem `messages` (só `text`) NÃO vai para o sanitizador SFT (que descartaria tudo — lição do crawlPT-edu: 379.285 lidas/descartadas) — vai para a **limpeza leve** (`limpeza_leve_rigel_v2.py`).
- **⚙️ Guardião CPU 70 → 90%** (`config_recursos.json`; máquina 36 núcleos; o scan/pipeline passava de 70% e bloqueava). ⚠️ O valor é lido na importação — precisa reload do dashboard p/ valer.
- **🧪 Teste `dolphin_portuguese`** via limpeza leve: 501 lidos → **430 SFT** (86%) | 17 não-PT | 33 qualidade | 15 duplicados, em ~26s (500 docs). Dataset completo = 860.607 linhas (CPU/langdetect ≈ 10-12h — decidir: background, fasttext ou não processar).
- **📱 Header mobile** (`base.html`): linha 1 = logo RigelSLM (esquerda) + 💚 PIX/BMC (direita), linha 2 = menu horizontal. Desktop inalterado.
- **🐛 Simular não deve executar**: `_tratar_txt` agora retorna cedo em `--simular` (antes rodava o conversor de verdade).
- **🗑️ crawlPT-edu apagado (75,66 GB)**: corpus de pré-treinamento não utilizado → disco livre 25 → **101 GB**.
- **🧹 Dolphin em processamento**: `limpeza_leve` rodando em background (via Executor, sobrevive a reload, barra de progresso) — 860.607 linhas, ~10-12h (langdetect). Gera `rigel_sft.parquet`/`rigel_pretrain.parquet` em processed.
- **🐛 Fix `--origem` para limpeza_leve**: a rota `/api/executor/iniciar` e o `executor_pipeline.py` passavam a origem POSICIONAL, mas `limpeza_leve_rigel_v2.py` exige `--origem` → falhava (exit 2). Corrigido nos dois lugares.

## [SESSÃO 10/08/2026] 🔄 Executor: auto-restart de verdade (6x) + pergunta p/ continuar
- **🐋 Assinatura do agente no rodapé** (`base.html`): trocado o ícone de check inline pela **baleia do DeepSeek** (`/images/icons8-deepseek-48.svg`) ao lado de "Co Editado com agente Deepseek Flash".
- **🐛 CAUSA RAIZ — auto-restart NUNCA funcionou no Windows**: `_reiniciar_apos_reload` usava `shlex.split(comando)` (modo POSIX) que DESTRÓI barras invertidas (`D:\Projetos\rigelllm\...` → `D:Projetosrigelllm...`) → `Popen` falhava com `[WinError 2]` ("Falha ao reiniciar após reload" nas atividades antigas). **Fix**: `shlex.split(comando, posix=False)` preserva os caminhos do Windows. Validado com teste funcional real (spawn OK).
- **🔢 Auto-restart 2 → 6 tentativas** (`MAX_REINICIOS_RELOAD = 6`).
- **❓ Ao cair 6x seguidas**: atividade entra em estado `aguardando` (não morre em silêncio) e mostra aviso "caiu 6 vezes — ▶️ Continuar p/ tentar +6 ou Parar". Novo endpoint `POST /api/executor/continuar` + botão Continuar no painel `/executor` (zera o contador e re-spawna).
- **💾 Persistência**: `_reiniciar_apos_reload` e `_recuperar_apos_reload` agora gravam `executor_estado.json` (antes o estado "rodando" ficava órfão no disco após restart).
- **🐛 Re-spawn quebrava argumentos com espaços**: `shlex.split` re-dividia `--nome TODAS as atividades` em 3 args → `unrecognized arguments`. **Fix**: `iniciar()` agora persiste `comando_lista` (args EXATOS) e `_reiniciar_apos_reload` usa a lista (fallback p/ shlex posix=False). Validado com teste (arg com espaços chega inteiro).
- **🧹 Botão "Limpar histórico"** no painel `/executor` (rota `POST /api/executor/limpar-historico` já existia) — remove atividades antigas concluídas/erro/interrompidas, mantém as rodando.
- **🚚 PROMOÇÃO AUTOMÁTICA no pipeline** (`executor_pipeline.py`): sanitizar agora escreve em staging por origem (`dados/sanitizados/<origem>/`) e, ao concluir com sucesso, **move os limpos para `processed/jsonl/<origem>_sanitizado/` e apaga o staging** (HD liberado — regra do usuário). Testado isoladamente.
- **📦 Migração 10/08**: os 836 `rigelsanitizado*` da `rigeljsonl_20260802_0136` (pipeline que caiu em 89%) foram promovidos manualmente para `processed/jsonl/rigeljsonl_20260802_0136_sanitizado/` e `dados/sanitizados` (raiz) zerada.
- **ℹ️ Diagnóstico 10/08**: restart do uvicorn (13:22, watchdog/`run_dashboard.bat`) matou o gerenciador do executor e TODOS os filhos (pipeline "TODAS as atividades" + dialogos2). Sanitização parou em 836/941 (~89%). Massa: 948 exemplos SEGUROS em `dados/gerados/massa_final/` (65 JSONL incrementais — o design incremental salvou os dados).

## [SESSÃO 08/08/2026] 🚀 Geração em massa funcionando + rigelslm no chat
- **🐛 Geração em massa morria em silêncio**: o subprocesso morria quando o servidor reiniciava (--reload/watchdog) e o frontend ficava "Gerando..." para sempre. Fixes: (1) **executor re-spawna automaticamente** atividade morta por reload (até 2 tentativas — `_reiniciar_apos_reload`); (2) script grava **progresso inicial** (0%) e `fim`; (3) frontend mostra a barra **desde o início** e **detecta a morte** da atividade (para o "Gerando..."); (4) **pós-processamento incremental**: jsonl gerado a cada 10 itens (antes só no final — com meta 644 eram horas sem ver resultado). Commits `28215a6`, `a9d532b`.
- **🐛 Chat: seleção do `rigelslm:latest` não persistia** ("o menu se recria"): o `verificar_ollama()` descartava a escolha porque o rigelslm não existe no Ollama (roda via llama.cpp/modelo local). Fix: mantém a escolha manual/persistida quando `_eh_rigel()`. Commit `9180668`.
- **🐛 Menu do chat dependia do GGUF**: com os GGUFs removidos, o rigelslm sumiria do menu. Fix: inclui `rigelslm:latest` quando o **modelo local PyTorch** (`modelo/modelo.pt`) existe. Commit `cb1d485`.
- **📌 GGUFs removidos pelo usuário** (decodificavam vazio no Ollama — bug conhecido). O rigelslm agora é servido pelo **modelo PyTorch local**.
- ⚠️ O `--reload` do uvicorn da porta 8000 NÃO recarrega código — reiniciar o servidor para ativar mudanças.

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