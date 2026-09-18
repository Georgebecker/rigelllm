# 📋 Lista de Tarefas — RigelSLM

> Anotado em 13/08/2026 · Atualizado 18/08/2026. Tarefas pendentes para fazer DEPOIS (não agir agora).
> Regra de ouro: 1 processo pesado por vez; verificar/validar SEMPRE antes de commitar.
> ✅ 13/08 17:16 — dolphin CONCLUÍDO (rigel_sft.parquet 691 MB validado). Máquina livre.
> ✅ 18/08 — espaço liberado no D: (109 GB livres): cnmoro (84 GB) + FIPE (1,2 GB) apagados.

---

## ✅ REORGANIZAÇÃO POR TIPO CONCLUÍDA (18/08 — A, B, C)
- ✅ **A — Constantes padronizadas**: novo `regras_pastas.py` (fonte de verdade das pastas por tipo) + treinadores adaptados (`treinoparquet` usa `processed/parquet`, `treino`/`treinov2` usam `processed/txt`, com fallback p/ o antigo).
- ✅ **B — PARQUET migrado**: 7 pastas (`limpo_*`, `parquet_livros`, `rigelparquet`, `scrap`) → `processed/parquet/`; registro atualizado.
- ✅ **C — TXT migrado**: 296 pastas → `processed/txt/`; registro `registro_pastas.json` atualizado (266 caminhos) + caches limpos p/ regenerar.
- ✅ **Escritores ajustados**: `download_datasets` (qualificar→`processed/txt/`), `limpeza_leve_rigel_v2` (saída→`processed/parquet/`, elite→`processed/txt/`), callers `hf_datasets` e `abrir_espaco_hd`.
- ✅ **Testado**: treinoparquet encontra as 7 pastas em `parquet/`; treino usa `txt/`.
- ⏳ **Pendência**: pastas esqueleto vazias na raiz de `processed/` (Auto, Cartas, Conto, Conversa, Ensaios, Entrevista, Explicação, blogset, brwac, corpus_ptbr, datasets3, dnlt, agrupados, canarim_11) → dar fim digno (mover p/ apaguemedepois).

## 🔄 EM ANDAMENTO (18/08/2026) — Backup do acervo p/ Google Drive + tratamento de brutos

### A. Envio do acervo JSONL ao Google Drive
- [ ] Usuário envia as pastas JSONL (relatório: `logs/relatorio_envio_jsonl_20260818.txt`) — 102 limpas (7,8 GB) + brutas como backup
- [ ] Após "terminei de enviar o jsonl" → **liberar área** (apagar do D:)
- [ ] **Fase 2 — PARQUET** (2,92 GB / pastas: `limpo_alpaca`, `limpo_canarim`, `limpo_madras1_v2`, `limpo_wikipedia`, `parquet_livros`, `rigelparquet`) → organizar → validar → enviar → liberar
- [ ] **Fase 3 — TXT** (7,96 GB / ~1,4M arquivos) → organizar por tipo → enviar → liberar (ainda tem material em limpeza/juízo)

### B. Tratamento dos datasets brutos
- [ ] `dominguesm_brwac` (18 GB, formato `text`, **MOJIBAKE real** ~31k na amostra) → rodar `scripts/tratar_datasets_brutos.py`
- [ ] `BrunoN-Dev_ultra-alpaca-ptbr` (1,5 GB, `prompt`/`completion`) → converter p/ `messages` (script criado; teste em andamento)
- [ ] `dominguesm_restore-punctuation` (1 GB, `text` limpo) → tratar/validar p/ pré-treino
- [x] `Montival_fipex-veiculos-brasil` (1,2 GB, tabela FIPE) → **APAGADO** (não serve p/ chat)
- [x] `dados/raw/cnmoro_reasoning-v1-20m-portuguese` (84 GB) → **APAGADO** (liberar espaço p/ dataset de ~98 GB)

### C. Automação pendente
- [ ] **Integrar `sanitizador_ptbr.corrigir_mojibake_inteligente` no fluxo de DOWNLOAD de datasets** (`hf_datasets.py` / `download_datasets.py`) — hoje o download NÃO aplica limpeza automática (regra de ouro do usuário)
- [ ] Rodar o juiz (camada 2) em pasta com muitos suspeitos (`gerados_local` ~594) — só quando o usuário decidir

---

## 1. ⚖️ Juiz de Qualidade (avaliador com `deepseek-r1:7b`)
- ✅ **VALIDADO (13/08):** `deepseek-r1:7b` instalado (4,7 GB) e testado — 5 arquivos → 4 aprovados / 1 suspeito (juiz analisou o suspeito).
- **Sistema "Ajuizar" implementado:** botão ⚖️ Ajuizar no `/gerar_local` + bandeiras ✓ + dropdown de juiz (Nenhum/deepseek) + checkbox "Verificar ao gerar". Roda via Executor com barra de progresso.
- ✅ **TESTADO EM PASTA PEQUENA (13/08 21h):** juiz rodou em `debates` (1 suspeito) — engajou de verdade (relatório com `juiz: deepseek-r1:7b`). **Bug corrigido:** veredito do juiz se perdia quando o modelo escrevia "Aprovaço" (typo) — matcher tolerante `_veredito_aprovado` em `scripts/avaliador_qualidade.py` (testado 9/9). **Bug corrigido:** ajuizar pasta específica via UI não fazia nada (caminho `gerados/gerados/<nome>` duplicado) — corrigido em `dashboard/routes/executor.py` + `_resolver_pasta` em `scripts/ajuizar_pastas.py` (testado E2E via API).
- **Pendência restante:** rodar o juiz (camada 2) numa pasta com muitos suspeitos (ex.: `gerados_local` tem 594 suspeitos). ⚠️ Demora bastante em CPU (horas). Só quando o usuário decidir.
- **Uso:** no painel ⚖️ Ajuizar, escolher "🟢 deepseek-r1:7b" no dropdown e clicar em "Ajuizar pendentes". Ou CLI: `python scripts/ajuizar_pastas.py --pasta <pasta> --juiz`.

## 2. 📚 Aprimorar o PDF/Livros scrap automático
- ✅ **CONCLUÍDO (13/08 22h):** scraper agora roda PELO DASHBOARD (`/pdfs`), não é mais só CLI:
  - Botão 🚀 Rodar scraper (dropdown 30 sites, limite, verificar, profundidade) via Executor, com **confirmações rigorosas** antes de rodar/parar.
  - **Barra de progresso real** (`logs/scrap_progresso.json`), **dedup por conteúdo** (SHA-1, `logs/scrap_hash_registry.json`), **relatório por site** (`logs/scrap_relatorio.json`) exibido em tabela no painel.
  - Testado E2E: baixelivros limite 2 → ok=2/erro=0/pulados=2/dups=0 em 14s; 4 livros no acervo.
  - Pendente opcional: rodar em MASSIVA ("Todos os sites") quando o usuário quiser — cuidado: pode demorar e baixar muito.

## 3. � Desabilitar geração via API em `/gerar_local` (NÃO apagar — regra do usuário)
- **O que é:** DESABILITAR (não apagar, não deletar arquivos) a geração que depende de **chave de API** (DeepSeek) na página `/gerar_local` — hoje o projeto gera via **modelos locais** (Ollama).
- ⚠️ **REGRA ABSOLUTA (13/08): DESABILITAR, NÃO APAGAR, NÃO DELETAR arquivos.** Apenas ocultar/desativar na UI e/ou nas rotas (deixar o código salvo/intacto).
- **Itens a desabilitar** (`dashboard/routes/generate.py` + `dashboard/templates/gerar_local.html`):
  - **Diálogos v1** → `dialogos.py` (pares pergunta-resposta via API DeepSeek — requer chave)
  - **Diálogos v2** → `dialogos2.py` (22 tipos de conteúdo via API DeepSeek — requer chave)
  - **Downdata** → `downdata.py` (baixa datasets públicos — verificar se mantém habilitado, não é geração via API)
  - Rota: `POST /api/generate/...` (`gerar_dialogos`, `gerar_dialogos2`, `gerar_via_api`, `downdata`)
- **Decisão pendente:** confirmar quais itens desabilitar na UI/rotas (manter o `downdata`? manter `dialogos2` com fallback local?). Só deixar o que é LOCAL.

## 5. 🚫 Desabilitar "Geração via DeepSeek" em `/gerar_dados` (NÃO apagar — regra do usuário)
- **O que é:** DESABILITAR (não apagar, não deletar arquivos) a **Geração via DeepSeek** na página `http://127.0.0.1:8000/gerar_dados` — hoje o projeto gera via **modelos locais** (Ollama).
- ⚠️ **REGRA ABSOLUTA (13/08): DESABILITAR, NÃO APAGAR, NÃO DELETAR arquivos.** Apenas ocultar/desativar na UI e/ou na rota (deixar o código salvo/intacto).
- **Local:** página `/gerar_dados` — bloco/sessão "Geração via DeepSeek" (requer chave de API).
- **Ação:** ocultar/desabilitar o bloco na UI (e/ou rota) sem apagar nada.

## 4. 📱 Bolinhas de atividade piscando TODAS no menu (modo mobile)
- **Sintoma:** no modo mobile, TODOS os itens do menu lateral aparecem com a bolinha verde piscando, como se todos tivessem atividade (no desktop só acende a aba certa — Tratamento + Executor).
- **Provável causa:** no mobile o CSS `@media (max-width:768px)` do sidebar faz o nav em `flex-row`; a bolinha `.nav-atv` injetada por JS pode estar ficando visível/animada em todos os links (regra `hidden md:inline-block` + `s.style.display` interagindo com o layout mobile). Verificar no viewport 390px.
- **Regra:** bolinha deve aparecer SÓ no desktop (`hidden md:inline-block`) e SÓ na aba com atividade real.
- **Fazer DEPOIS** — agora o dolphin terminou, dá para mexer em `dashboard/*` sem risco.

---
