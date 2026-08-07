# 📔 Diário de Ideias do RigelSLM

> **O que é:** o lugar para anotar tudo que pode ser feito **mais tarde** —
> ideias, coisas para descobrir, arquivos para verificar/limpar.
> **Regra:** nada aqui é urgente nem deve ser executado sem revisão.
> **Como usar:** adicione entradas com `- [ ]` (pendente) e marque `- [x]` quando concluído.
> Última atualização: 04/08/2026

---

## � Notas úteis (anotações do usuário)

- **Colab:** comandos de terminal no notebook SEMPRE começam com `!`
  (ex.: `!python treinar_com_jsonl.py --dados dados/processed --max-arquivos 20 --epochs 5`).
  Sem o `!`, o Colab tenta interpretar como Python e dá erro.

---

## �📝 Ideias para implementar

- [ ] *(Exemplo: "Criar um botão no dashboard que faz X")* — anote aqui suas ideias.
### 🚀 Colab: função otimizada no dashboard pós-treino — ✍️ PENDENTE (04/08)
> Após reescrever o `RigelSLM_Colab.ipynb` (v1.1.0, treino SFT com comandos corretos),
> ficou registrado: o dashboard precisa de uma **função otimizada** para o fluxo
> Colab→local, para não depender de passos manuais depois do treino na nuvem.

- [ ] Botão/função no dashboard para **importar o modelo treinado no Colab**:
      baixar `modelo/modelo_melhor.pt` do Drive e registrar com data/origem no
      manifesto (`modelo/versoes.json`) para o chat/conversor reconhecerem.
- [ ] (Possível) Disparar/verificar o treino no Colab a partir do dashboard
      (status do notebook, botão "importar resultado").
### 🗞️ RSS: processar notícias 100% LOCAL via Ollama (sem API DeepSeek) — ✅ IMPLEMENTADO (02/08)
> Contexto: as notícias são textos **jornalísticos, atualizados diariamente**. Antes
> o `rss_processor.py` resumia SÓ via API DeepSeek; quando a API devolve vazio, o
> item era descartado como `falha_resumo` (numa rodada: 92 ok / 128 descartados).
> **DECISÃO do usuário:** NÃO queria resumo via DeepSeek para textos de RSS — o processo
> deveria ser feito **LOCALMENTE via Ollama**. Feito!

- [x] **Resumo local via Ollama como caminho PRINCIPAL** no `rss_processor.py` v1.1.0:
      usa `/api/chat` do Ollama (com fallback `/api/generate`) para gerar o resumo
      jornalístico (quem/o quê/quando/onde/porquê, 4-7 frases). Sem API DeepSeek no
      fluxo RSS — a chave `DEEPSEEK_API_KEY` nem é mais necessária para rodar.
      ✅ Testado com `llama3.2:3b` (resumo real gerado em pt-BR).
- [x] **Retry 1x** quando o Ollama devolver vazio/erro (`OLLAMA_RETRIES=2` = original + 1 retry).
- [x] **Fallback "salvar como completo"**: se nem o Ollama resumir, o texto bruto vai
      para `completos/` em vez de ser descartado (notícia boa não vira lixo).
      Com Ollama OFFLINE o script avisa no log e salva tudo como completo (nunca descarta).
- [x] **Timeout adaptativo/limites** no Ollama (mesmo padrão do `createjsonl.py`):
      `OLLAMA_TIMEOUT` (120s) → escala x2 a cada tentativa até `OLLAMA_TIMEOUT_MAX` (600s),
      com margem extra em CPU (`OLLAMA_TIMEOUT_CPU_FATOR=1.5`).
- [x] `--modelo-resumo` (CLI/env `MODELO_RESUMO`) para escolher o modelo local.
      Dashboard: seletor de modelo na aba RSS + status "Ollama online/offline"
      (rota `/api/rss/status` agora devolve `modelos_ollama` e `ollama_online`).

### 🎯 Treino: pular arquivos já treinados N vezes — ✅ IMPLEMENTADO (02/08)
> Antes: o `treinar_com_jsonl.py` treinava TUDO que estava na pasta, sem consultar
> quantas vezes cada arquivo já foi treinado. Agora dá para pular os "gastos".

- [x] `--pular-treinados N` no `treinar_com_jsonl.py` (treino único E fila):
      pula arquivos cuja contagem em `modelo/jsonlogs/<dataset>.json` seja >= N
      (N=1 pula tudo já treinado 1x+; N=3 pula só os vermelhos). Mostra no log
      quantos foram pulados (com nome + contagem). ✅ Testado (f1 com 2x pulado
      com limite 2 e 1; f2/f3 mantidos).
- [x] Dashboard: campo "Pular já treinados (N+)" no card da Fila; no treino de um
      arquivo, trava antes se já atingiu o limite. Passado ao subprocesso.
- [x] Rota/serviço: `pular_treinados` em `/api/treino_local/iniciar` e `/batch`.
- [x] `--force`: ignora a regra de "já treinado" e treina TODOS os arquivos
      (sobrepõe o `--pular-treinados`). No dashboard, checkbox "⚡ Forçar
      (ignora já treinados)" no card da Fila; no treino de um arquivo, o bloqueio
      é desativado. Ex.: `!python treinar_com_jsonl.py --dados ... --force`.

### 🚀 Fila de treino (lote): orquestração completa — ✅ IMPLEMENTADO (02/08)
> Revisão da fila: modos, LR por arquivo, pausa/retomar e progresso no dashboard.

- [x] `--epocas-por-arquivo N` (padrão 5): épocas treinadas em CADA arquivo da fila.
- [x] Aliases de modo: `arquivo`/`completo` (até o fim) e `tempo` (horas) — além de
      `all`/`time`/`pause`. Padrão: `arquivo`. (No dashboard: rádios "Arquivo a
      Arquivo", "Tempo Determinado (Horas)", "Completar Fila".)
- [x] **Reset de LR por arquivo**: cada arquivo cria otimizador/scheduler novos e o
      LR é reinicializado EXPLICITAMENTE para `--lr` (log `🔁 LR reinicializado
      para X (novo arquivo da fila)`). O `carregar_modelo()` NÃO restaura o estado
      do otimizador, então o modelo nunca fica estagnado com LR=0 entre arquivos.
      ✅ Testado: 3 resets de LR em 3 arquivos.
- [x] **Botão ⏸️ Pausar / ▶️ Retomar** no dashboard: Pausar cria `PAUSA_SEGURA.txt`
      (a fila termina o arquivo atual e para — funciona em QUALQUER modo); Retomar
      apaga o marcador e reinicia com `--resume` do arquivo onde parou. Endpoints:
      `POST /api/treino_local/pausar` e `/retomar`. ✅ Testado (pausa imediata + resume 3/3).
- [x] **Progresso por época no dashboard**: `estado_fila.json` ganha `epoca_atual`,
      `total_epocas`, `progresso_porcent`, `loss_atual`, `lr_atual` (gravados no
      início de cada época e a cada 30s); ETA estimado no frontend.
- [x] `batch_config.json` persistido (config do último lote) para o Retomar funcionar
      mesmo após restart do dashboard.
- [x] Estado de fila nova zera indicadores antigos (`arquivo_atual`/`indice`/`total`).

---

## 🔍 Coisas para descobrir / verificar

### Arquivos com função incerta (auditoria de 02/08/2026 — SÓ verifiquei, não mexi)
> Verifiquei os cabeçalhos. Nenhuma ação foi tomada ainda.

| Arquivo | Cabeçalho diz | O que eu acho / precisa conferir |
| --- | --- | --- |
| `downdata.py` | "TREINO COMPLETO COM AUTO-RECUPERAÇÃO" | README diz "download de datasets" — **conflito, conferir função real** |
| `dividir_pastas.py` | (sem docstring, só imports) | Descobrir o que faz / se está em uso |
| `processados.txt` | Lista de hashes (SHA1?) | Descobrir **quem usa** e se ainda é necessário |
| `organizar_status.json` | Contém traceback `KeyboardInterrupt` do `organizar_pastas.py` (27/07) | Arquivo de status órfão de uma execução interrompida — conferir se ainda é lido |
| `registro_pastas.json` | Registro do `organizar_pastas.py` (tem `.tmp.driveupload`) | Conferir se ainda é usado pelo organizador |
| `app.py` / `main.py` | Interface web (Gradio) / ponto de entrada do gerador | README marca como **legados** — decidir se mantêm |
| `tradutor.py` / `traduza.py` | Traduz JSON (Alpaca/Dolly) / traduz TXT | Funções sobrepostas? Conferir se ainda usados |
| `sincronizar.ps1` | Sincroniza `dados/gerados` → `dados/processed` | Conferir se ainda é usado (ou se virou obsoleto com o pipeline JSONL) |

### Limpeza futura (com cuidado — NÃO remover sem confirmar)
- [ ] `converter_para_gguf_old.py` — versão antiga do conversor (substituído pela v1.0.0). **Manter até confirmar que nada o usa.**
- [ ] `requirements_old.txt` — requirements antigos congelados (provável lixo).
- [ ] `dialogos2.py.bak` / `rss_processor.py.bak` — backups das correções de 02/08 (manter por segurança por ora).
- [ ] `dashboard/main.py.backup` / `dashboard/main.py.bak_pre_datasets` — backups do dashboard.
- [ ] `desktop.ini` — arquivo do Windows, não é do projeto (não mexer/remover sem confirmação).

---

## 🧠 Pendências técnicas conhecidas (do checklist/memória)

- [ ] Validar **treino do Guará** explodido (941 arquivos) ou um subset (`--max-arquivos`) no `treinar_com_jsonl.py`.
- [ ] Testar "já está rodando" do `run_dashboard.bat` v2.3.x pelo usuário (health-check-first).
- [ ] Limpar parênteses descritivos dos itens de `POVOS_ORIGINARIOS` (ex.: "(já está em PESSOAS)") que vazam para perguntas geradas.
- [ ] Endpoint `/api/log/ultimas` já corrigido? (apareceu 404 antigo no log — verificar se ainda existe chamada errada no front).
- [ ] Modelo ainda com loss alto (~8.26) — precisa mais treino; decidir subset + épocas (benchmark em `checklist.md`).

---

## ✅ Resolvido recentemente (02/08/2026)

- Guardião de limites (memória/disco/CPU/SSD) + limites proporcionais à máquina (`recursos.py` + `config_recursos.json`).
- Scans 100% em background com barra de progresso (nunca mais travam o servidor).
- `run_dashboard.bat` v2.3.1: fim da cascata de abas / loop de reinício (navegador 1x, monitor único, limpeza de órfãos `spawn_main`).
- Backup automático do modelo antes de cada sobrescrita (`modelo_backup.py`).
- **RSS 100% local via Ollama** (`rss_processor.py` v1.1.0): sem DeepSeek no fluxo, retry 1x + timeout adaptativo, fallback "salvar como completo", `--modelo-resumo` + seletor no dashboard. ✅ Testado de ponta a ponta (8 resumos locais gerados numa rodada real).
