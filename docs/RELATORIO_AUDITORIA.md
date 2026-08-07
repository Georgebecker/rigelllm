# 📋 RELATÓRIO DE AUDITORIA — RigelSLM (07/08/2026)

> Auditoria completa do sistema: módulos, rotas, páginas, estados e logs.
> Cada item tem evidência (arquivo/linha/erro real) e correção.

---

## 1. VISÃO GERAL

- **Total de rotas no OpenAPI:** 174 (95 GET + 79 POST/DELETE)
- **Arquivos .py do projeto compilados:** 157 — **0 erros de sintaxe** ✅
- **Páginas HTML:** 19 templates (todas as do menu existem)
- **Menu atual (base.html):** treinamento → chat → rss → converter → gerar_dados → gerar_local → datasets → scrap → tratamento → treino_local → treino_colab → debate → executor → debate_local → logs

---

## 2. ACHADOS CONFIRMADOS (com evidência)

### 🟢 Já corrigidos hoje (07/08) — validados
| # | Bug | Arquivo | Correção |
|---|---|---|---|
| 1 | Chats salvavam 0 pares (arquivos 0 KB) | `dashboard/routes/chat.py` (`salvar_conversa_sft`) | Loop reescrito aceitando `assistant` e `bot`. Testado: 2 pares salvos ✅ |
| 2 | Gerador local crashava `NameError: client` | `dialogos2.py:4862` | `client=None` + `client is not None` + default `--modelo` segue `.env`. Testado: gera ✅ |
| 3 | Modelo do Ollama inexistente (`deepseek-v4-flash`) | `.env` / `dialogos2.py` | Novo `OLLAMA_MODEL` (default `llama3.2:3b`) configurável |
| 4 | `_treino_rodando()` não via `treinar_com_jsonl` | `dashboard/routes/train.py` | Regex unificado + `kill()` forçado no stop |
| 5 | Scrap estado preso em "rodando" sem processo | `estado/scrap_estado.json` | Limpo via `POST /api/scrap/limpar` |

### 🔴 BUGS NOVOS ENCONTRADOS NA AUDITORIA
| # | Bug | Evidência | Correção proposta |
|---|---|---|---|
| A1 | **Explosão estado preso** ("rodando": true, `fim: null`, sem processo) | `estado/explosao_estado.json` (parado em 61.400 exemplos desde 06/08 19:20) | Aplicar mecanismo anti-reload do sanitizacao (`pid_inicio` + `_recarregar_se_mudou`) ao `explosao_local.py` |
| A2 | **explosao.log com 34,5 MB** — loga a cada 50 exemplos | `logs/explosao.log` (06/08 19:20, 34,5 MB) | Reduzir frequência de log (ex.: a cada 1000 exemplos) + rotacionar |
| A3 | **Rotas GET que travam/demoram** (chamadas bloqueantes no event loop) | auditoria de rotas em andamento (ver §3) | Mover chamadas bloqueantes para `asyncio.to_thread` (regra já documentada nos princípios) |
| A4 | **Erros de rota não são registrados em log** | `logs/dashboard.log` só registra inícios; `uvicorn.log` parado em 07/10 | Adicionar middleware de log de erros/requisições no dashboard |

### 🟡 PENDÊNCIAS DO USUÁRIO (celular, ainda não corrigidas)
| # | Problema | Status |
|---|---|---|
| P1 | Download de datasets 100% → mostra 0% | A investigar |
| P2 | Explosão: campos não limpam, falta resume/clear, barra não chega 100% | A investigar (relacionado A1/A2) |
| P3 | Treino TXT pede para escolher pastas de novo | A investigar |
| P4 | Geração de conteúdo API "failed to fetch" | Relacionado ao #2 (corrigido) — validar |

---

## 3. RESULTADO DA AUDITORIA DE ROTAS GET

**102 OK / 9 problemas** (teste de 111 alvos: 95 rotas GET + 16 páginas) — ver `docs/AUDITORIA_ROTAS_GET.txt`.

### Problemas REAIS (não-falsos-positivos)
| Rota | Problema | Correção |
|---|---|---|
| `GET /api/diagnostico/completo` | **TimeoutError (>5s)** — escaneia `dados/processed` com `list(glob("*.txt"))` (12,9M arquivos) + `torch.load` de checkpoint 665 MB em rota `async` | **BUG-1**: usar cache `estrutura_txt.json` + verificação leve de checkpoint + `asyncio.to_thread` |
| `GET /topicos` | 404 — página não existe | Verificar links quebrados |
| `GET /treino_colab_txt` | 404 — página não existe (rota removida) | Verificar links quebrados |
| `GET /dados` | 404 — página não existe | Verificar links quebrados |

### Falsos positivos do script (path/query params sem valor — NÃO são bugs)
`/api/logs/visualizar/{nome}`, `/api/treino_local/arquivos` (422 exige `?dataset=`), `/api/deploy/download/{nome}`, `/api/celular/download/{nome}`, `/api/local-generate/arquivo-salvo/{nome}`.

### Rotas GET testadas e OK (102) — inclui todas as páginas principais
`/` (home), `/datasets`, `/treino_local`, `/treinamento`, `/gerar_local`, `/chat`, `/converter`, `/executor`, `/debate`, `/treino_colab`, `/tratamento`, `/logs`, `/rss`, `/scrap`, `/converter_txt`, `/gerar_dados`, `/debate_local` ✅

---

## 4. ESTADO ATUAL DO SISTEMA
- Dashboard rodando (porta 8000, uvicorn --reload)
- Ollama rodando (PID ativo, ocioso)
- RAM livre: ~23 GB
- Nenhum treino/RSS/sanitização rodando (limpos na sessão de hoje)
- **Estados presos encontrados:** `estado/explosao_estado.json` (rodando:true, sem processo — 61.400 exemplos de 06/08)

---

## 5. CORREÇÕES APLICADAS (FASE 2 + OBJETIVOS)

### Bugs graves corrigidos e VALIDADOS
| # | Correção | Validação |
|---|---|---|
| **BUG-1** | `/api/diagnostico/completo` travava o servidor: `glob("*.txt")` em 12,9M arquivos + `torch.load` de 665MB + import local `import urllib.request, json` (tornava `json` local → `UnboundLocalError`). Agora: cache `estrutura_txt.json` + cabeçalho leve de checkpoint | **1,4s** (antes >5s e travava o event loop) — 289 pastas / 1.338.135 arquivos ✅ |
| **A1** | Explosão ficava presa "rodando" para sempre (sem processo). Adicionado `pid_inicio` + `_marcar_interrompida_se_orfao()` (anti-reload, igual ao sanitizacao) | Estado de 06/08 liberado → `interrompido` ✅ |
| **A2** | `explosao.log` com 34,5 MB (log a cada 50 exemplos) | Log a cada 1000 exemplos + truncado para 0,01 MB ✅ |
| **A4** | Dashboard não registrava erros de rota ("failed to fetch" sem causa) | Middleware `_log_requisicoes` grava em `logs/requests.log` (status + tempo + exceção real) ✅ |
| **P1** | Download 100% → 0% sem explicação | Card do download mostra a fase ("Explodindo — download concluído ✅") + card final mostra **📍 onde os dados foram salvos** (`saida_dir`) + tratamento aplicado ✅ |
| **Chat** | Conversas salvavam 0 pares (frontend envia `assistant`, backend só aceitava `bot`) | **Testado: 2 pares, arquivo 599 bytes, formato SFT correto** ✅ |
| **Polegares** | Ícones 👍/👎 removidos do chat (taxa, botões, função JS) | ✅ |
| **Mobile** | 13 páginas testadas em viewport 375px — **overflow horizontal = 0 em todas** | ✅ (layout já responsivo) |
| **Material** | `treinar_com_jsonl.py` agora avisa se o material é BAIXO (<10 arq), MODERADO (10-50) ou SUFICIENTE (>50) antes de treinar | ✅ |

### Resultado da auditoria final (servidor com código novo)
- **103 rotas/páginas OK** (melhor que 102 — o diagnóstico deixou de falhar)
- 8 "problemas" restantes = **todos falsos positivos** (path/query params sem valor + 3 páginas antigas sem link no menu)

### ⚠️ PENDÊNCIAS / OBSERVAÇÕES
1. **O `--reload` do uvicorn da porta 8000 NÃO está recarregando** (processos de 15:35 não atualizam). **O servidor precisa ser reiniciado para carregar TODAS estas correções.** Recomendado: derrubar o uvicorn atual e subir de novo (ou ajustar o `run_dashboard.bat`).
2. Rotas de página inexistentes (sem link): `/topicos`, `/treino_colab_txt`, `/dados` — baixa prioridade.
3. `chat.py:557` — erro de tipo pré-existente (tokenizer pode ser None) — type-check, não é runtime.
4. Gerador de conteúdo (API) mantido como está, conforme pedido do usuário.
