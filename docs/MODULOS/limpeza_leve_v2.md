# MÓDULO: `limpeza_leve_rigel_v2.py` — Pipeline de Limpeza Leve de Datasets

> **Papel no sistema:** é o módulo BASE de limpeza/tratamento de dados do RigelSLM.
> Qualquer dataset baixado (sujo) passa por aqui antes de virar dado de treino.
> **Modo de trabalho (regra do usuário 05/08):** testar nos MENORES → mostrar
> resultado → registrar como foi feito → repetir → virar módulo base.

---

## 1. PARA QUE SERVE (em 1 frase)

Transforma datasets **sujos** (HTML, mojibake, URLs, lixo, não-português, duplicados,
diálogo artificial) em dados **limpos e prontos para treinar** o Rigel — separando
**SFT** (diálogos ChatML) de **Pretrain** (texto corrido), em streaming (RAM constante).

## 2. COMO FUNCIONA (o fluxo, na ordem certa)

```
Entrada (jsonl/json/txt/parquet)
   │
   ▼
[1] FILTRO DE IDIOMA ............ fasttext lid.176 (fallback: langdetect) → descarta não-pt ANTES de gastar CPU
   ▼
[2] LIMPEZA ..................... ftfy (mojibake) + BeautifulSoup (HTML) + regex (URLs)
   ▼
[3] FILTRO DE QUALIDADE ......... C4/Gopher simplificado: <20 palavras | linhas dup >30% | símbolos >10%
   ▼
[4] DEDUPLICAÇÃO ................ md5 exato + MinHash aproximado (datasketch, limiar 0.8)
   ▼
[5] CLASSIFICAÇÃO ............... QA estruturado → rigel_sft.parquet (messages)  |  texto corrido → rigel_pretrain.parquet (text)
   ▼
Saída: rigel_sft.parquet + rigel_pretrain.parquet + limpeza_relatorio.json
```

**REGRAS DE OURO embutidas:**
- **NUNCA criar diálogo artificial** — texto corrido NUNCA vira par user/assistant (ensina o modelo a ecoar).
- **Streaming do início ao fim** — RAM constante, mesmo com milhões de arquivos.
- **Ordem certa** — idioma primeiro (não gasta CPU limpando texto que será descartado).
- **Progresso visível** — barra de % no terminal a cada 500 documentos (regra 05/08).

## 3. FORMATOS SUPORTADOS (entrada)

| Formato | Como lê |
|---|---|
| `.jsonl` | linha por linha (NDJSON) |
| `.json` | objeto único ou lista |
| `.txt` | texto puro |
| `.parquet` | batches (pyarrow) |
| Pasta | recursivo (`rglob`) |

**Fix 05/08:** pasta com `dataset.jsonl` + `train.parquet` (mesmo conteúdo, comum em
downloads HF) → prioriza o `.parquet` e NÃO processa o `.jsonl` redundante.

## 4. FORMATOS DE ESTRUTURA RECONHECIDOS

| Estrutura | Campos | Vira |
|---|---|---|
| ChatML | `messages`/`conversations`/`chat` (lista ou string JSON) | SFT |
| Instrução (Alpaca/Canarim) | `instruction`(+`input`) → `output`/`completion`/`answer` | SFT (novo 05/08) |
| Texto corrido | `text`/`content` | Pretrain |
| Marcadores | `Pergunta:`/`Resposta:` no texto | SFT |

## 5. COMO USAR (CLI)

```bash
# Instalar dependências (1x)
pip install ftfy beautifulsoup4 fasttext datasketch datasets

# Teste rápido (amostra)
python limpeza_leve_rigel_v2.py --origem dados/raw/<dataset> --saida dados/processed/<nome> --max-docs 6000

# Completo
python limpeza_leve_rigel_v2.py --origem dados/raw/<dataset> --saida dados/processed/<nome> --lote 5000
```

**Parâmetros:** `--origem` (obrigatório) · `--saida` · `--max-docs` (teste) ·
`--sem-ptbr` · `--lote` (tamanho do lote de escrita) · `--lid-model` (caminho lid.176.bin)

## 6. PROBLEMAS ENCONTRADOS E COMO RESOLVI (registro — não repetir!)

| # | Problema | Sintoma | Causa raiz | Solução aplicada |
|---|---|---|---|---|
| 1 | **Formato instrução não reconhecido** | `dominguesm_alpaca-data-pt-br` dava ERRO na explosão; pipeline descartava tudo | O detector só olhava `messages`/`conversations`; não via `instruction/input/output` | `_tem_estrutura_qa` + `_extrair_messages` agora reconhecem instrução → ChatML |
| 2 | **SFT=0 (documentos com messages perdidos)** | documentos com `messages` retornavam "sem_texto" | `_classificar_documento` exigia campo `text`/`content` ANTES de checar QA | Reordenado: checa estrutura QA primeiro |
| 3 | **Parquet só guardava o último lote** | 38.996 contados, mas arquivo final com 996 linhas | Cada flush SOBRESCREVIA o mesmo arquivo | Novo `_EscritorParquet`: grava `.partNNN.parquet` e MESCLA no final |
| 4 | **Schema achatado no parquet** | `messages` virava 1 linha por mensagem (role/content) | `datasets.Dataset.from_list` v5 achata dicts aninhados | `_salvar_lote_parquet` com pyarrow e schema EXPLÍCITO (`list<struct<role,content>>`) |
| 5 | **fasttext não instala no Windows** | `pip install fasttext` pede MSVC C++ (não instalado) | pacote exige compilação | Fallback automático p/ `langdetect` (mais lento, mas funciona); `fasttext-wheel` também falha no Py3.14 |
| 6 | **Duplicação dataset.jsonl+parquet** | alpaca leu 103.518 (2x o tamanho real) | pasta tinha os 2 formatos com os mesmos dados | `_ler_documentos` prioriza parquet quando há `dataset.jsonl` |

## 7. COMO INTEGRAR (no sistema maior)

- **Dashboard (aba Executor):** adicionar comando `limpeza_leve` na whitelist do
  `dashboard/routes/executor.py` (script = `limpeza_leve_rigel_v2.py`), com origem = pasta
  de `dados/raw/` (dropdown já lista as origens).
- **Progresso no painel:** o script imprime `⏳ %` no stdout → o executor (subprocesso `-u`)
  já captura via SSE. Falta: gravar `logs/limpeza_progresso.json` como o sanitizador faz.
- **Treinamento:** parquet → jsonl (converter p/ `treinar_com_jsonl.py`) OU adaptar o
  treinador para ler parquet. DECISÃO PENDENTE.
- **Orquestrador:** script que roda a fila dos datasets (alpaca → canarim → wikipedia →
  Madras1 v2 → Madras1 v1), UM POR VEZ (respeita recursos), com relatório acumulado.

## 8. COMO MELHORAR (ideias futuras)

- [ ] Instalar `fasttext` (ou usar `pyfasttext`/binário) para filtro de idioma mais rápido
- [ ] Dedup global entre lotes (hoje o LSH recomeça a cada execução)
- [ ] Heurística PT-PT (palavras de Portugal) ativada por flag
- [ ] Modo `--resume` (não reprocessar o que já foi limpo)
- [ ] Estatísticas de amostra no relatório (exemplos de cada categoria descartada)
- [ ] Cache de hashes em disco (para datasets gigantes como Madras1 50 GB)
- [ ] Integração com `regras_ouro.py` (validar organização das saídas)

## 9. TESTES EXECUTADOS (evidência real)

| Data | Origem | Docs lidos | SFT | Pretrain | Não-PT | Qualidade | Dup | Tempo |
|---|---|---|---|---|---|---|---|---|
| 05/08 | amostra sintética (6 docs) | 6 | 3 | 2 | 0 | 0 | 1 | 0.1s |
| 05/08 | alpaca (amostra 6k) | 6.001 | 4.242 | 0 | 134 | 1.624 | 0 | 38s |
| 05/08 | alpaca (parcial, antes da correção) | 103.518 | 38.996* | 0 | 2.023 | 23.602 | 38.896 | 599s |
| **05/08** | **alpaca COMPLETO** | **51.759** | **38.942** | 0 | **1.011** | **11.792** | **13** | **343,9s** |
| **05/08** | **Canarim COMPLETO** | **317.932** | **163.208** | 0 | **8.450** | **41.137** | **105.081** | **4.050s** |
| **05/08** | **Wikipedia COMPLETO** | **53.704** | **42.656** | 0 | **803** | **5.698** | **4.547** | **446,7s** |

\* contagem correta, mas arquivo final estava truncado (bug #3 — corrigido).
\** **Resultado completo do alpaca (18:23, 05/08):** 75,2% de aproveitamento, 0 erros.
   Saída: `dados/processed/limpo_alpaca/rigel_sft.parquet` (38.942 exemplos ChatML).
   Relatório: `dados/processed/limpo_alpaca/limpeza_relatorio.json`.
\*** **Resultado completo do Canarim (05/08, 4.050s ~67min):** 51,3% aproveitamento,
   33% duplicados (105.081 — dedup exato 83.568 + MinHash 21.513), 0 erros.
   Saída: `dados/processed/limpo_canarim/rigel_sft.parquet` (163.208 exemplos, 36,5 MB).
   Relatório: `dados/processed/limpo_canarim/limpeza_relatorio.json`.
\**** **Resultado completo do Wikipedia (05/08, 446,7s):** 79,4% aproveitamento, 0 erros.
   Processado o formato `messages/` (o dataset tinha 3 formatos redundantes do mesmo
   conteúdo: alpaca/messages/prompt_completion — processamos só messages).
   Saída: `dados/processed/limpo_wikipedia/rigel_sft.parquet` (42.656 exemplos).
   Relatório: `dados/processed/limpo_wikipedia/limpeza_relatorio.json`.
   **Acumulado: 244.806 SFT limpos (alpaca 38.942 + canarim 163.208 + wikipedia 42.656).**

## 10. ARQUIVOS RELACIONADOS

- `limpeza_leve_rigel_v2.py` — o módulo
- `docs/PROMPT_LIMPEZA_LEVE_V2.md` — o prompt original (verbatim)
- `dados/processed/limpo_alpaca/` — saída do teste no alpaca
- `scripts/ver_parquet*.py` — verificadores de schema/conteúdo
- `sanitizador_ptbr.py` — módulo irmão (portão de qualidade PT-BR, usado na explosão)
