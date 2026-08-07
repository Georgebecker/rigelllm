# PROMPT — Pipeline de Limpeza Leve `limpeza_leve_rigel_v2.py`

> **Origem:** Prompt elaborado com o usuário (05/08/2026) para resolver o problema dos datasets sujos e treinamento.
> **Status:** Implementado em `limpeza_leve_rigel_v2.py` (raiz) — com testes reais no `dominguesm_alpaca-data-pt-br`.
> **Registrado em:** `docs/PROMPT_LIMPEZA_LEVE_V2.md` (este arquivo) para não se perder no meio do caminho.

---

## PROMPT ORIGINAL (verbatim)

Você é um Engenheiro de Dados especializado em pipelines para SLMs. Uma análise técnica revisou o escopo original e detectou lacunas críticas em um pipeline anterior. Sua tarefa é criar um script `limpeza_leve_rigel_v2.py` corrigindo todas as lacunas apontadas, seguindo os requisitos abaixo.

## 1. OBJETIVO E RESTRIÇÕES
- O script deve rodar no PC local ou no Colab, com foco em uso eficiente de CPU/GPU e baixo consumo de RAM.
- **Não use `datatrove`**, `unstructured`, ou orquestradores pesados. Use apenas `ftfy`, `beautifulsoup4`, `fasttext` (modelo `lid.176.bin`), `datasketch`, e a biblioteca `datasets` do Hugging Face.
- Saída final deve ser um arquivo `.parquet` otimizado, sem estrutura de chat artificial.

## 2. CORREÇÕES CRÍTICAS OBRIGATÓRIAS (NÃO IGNORE)

**2.1 Deduplicação (Obrigatória):**
- Implemente **dedup exato** usando `hashlib.md5` do texto normalizado antes de qualquer outra etapa.
- Implemente **dedup aproximado (MinHash)** usando a biblioteca `datasketch` (com limiar de similaridade > 0.8). Esta biblioteca é leve (~5MB) e não exige a complexidade do `datatrove`.

**2.2 Filtro de Qualidade Heurística (Filtros C4/Gopher simplificados):**
- Após remover HTML e URLs, descarte documentos com:
  - Menos de 20 palavras (documento muito curto).
  - Proporção de linhas duplicadas dentro do documento > 30% (menus/rodapés de sites).
  - Proporção de símbolos incomuns (ex: `#`, `*`, `_`, `<>`, `{}`, `[]`, `|`) superior a 10% do texto.

**2.3 Ordem Eficiente do Pipeline (Economia de Processamento):**
- A ordem do pipeline deve ser: **Filtro de idioma (fastText) → Limpeza de texto (ftfy + bs4 + URLs) → Filtro de qualidade → Deduplicação**.
- Faça o filtro de idioma primeiro. Se um documento for em russo/chines, ele será descartado antes de gastarmos tempo removendo HTML e corrigindo codificação.

**2.4 Remoção Explícita de URLs (Além do bs4):**
- `BeautifulSoup` remove tags HTML, mas não remove URLs soltas no meio do texto. Aplique uma regex explícita: `re.sub(r'https?://\S+|www\.\S+', '', texto)` antes ou depois do `bs4`.

**2.5 Tratamento da Variante PT-BR vs PT-PT:**
- Documente a limitação: `fasttext lid.176` distingue `pt` como uma única língua, mas **não** distingue PT-BR de PT-PT.
- Se for necessário filtrar PT-PT, implemente uma função heurística opcional que procura palavras típicas de Portugal (ex: "autocarro", "comboio", "bairro" vs "bairro" no Brasil, "tu" com conjugação). Caso contrário, aceite o texto como português, mas documente essa limitação.

**2.6 Restrição Crucial: NÃO crie diálogos artificiais para texto corrido:**
- **Texto corrido (sem marcadores de pergunta/resposta):** Deve ser salvo em um formato de "texto puro" dentro do arquivo Parquet (ex: campo `text`). **NUNCA** force um parágrafo aleatório a virar um par `{"role": "user"}` com o mesmo conteúdo de `{"role": "assistant"}`. Isso ensina o modelo a ecoar o prompt.
- **Texto com estrutura de QA (`Pergunta:` / `Resposta:` ou roles `user` / `assistant`):** Deve ser salvo no formato ChatML `messages` (system, user, assistant).
- **Saída Final:** O script deve gerar uma pasta com dois arquivos (ou um arquivo Parquet dividido em duas seções):
  1. `dados/processed/rigel_sft.parquet` (Apenas exemplos com estrutura de ChatML para SFT).
  2. `dados/processed/rigel_pretrain.parquet` (Apenas texto puro corrido para Pré-Treinamento Contínuo).

**2.7 Uso correto de `datasets.IterableDataset`:**
- Para descartar documentos que falham no filtro de idioma ou qualidade, utilize o método **`.filter()`** (que suporta `batched=True` no modo streaming), e NÃO tente descartar usando dentro do `.map()`.

## 3. ESTRUTURA DO PIPELINE (A FUNÇÃO PRINCIPAL)

[Seção 3 não foi totalmente fornecida pelo usuário na mensagem — implementado conforme seções 1, 2 e 4.]

## 4. ENTREGÁVEL FINAL
- Crie o script `limpeza_leve_rigel_v2.py` com todos os passos acima.
- Inclua um bloco de comentários no topo com as instruções de instalação: `pip install ftfy beautifulsoup4 fasttext datasketch datasets`.
- O script deve lidar com grandes volumes de arquivos sem estourar a RAM.

---

## ✅ IMPLEMENTAÇÃO (05/08/2026) — o que foi feito

| Requisito | Status | Notas |
|---|---|---|
| 1. Objetivo/Restrições | ✅ | Streaming, RAM constante, sem datatrove |
| 2.1 Dedup exato (md5) | ✅ | `_dedup_exato_chave` + `_Deduplicador` |
| 2.1 Dedup aproximado (MinHash) | ✅ | `datasketch.MinHashLSH`, limiar 0.8 |
| 2.2 Filtro qualidade C4/Gopher | ✅ | `<20 palavras`, linhas dup >30%, símbolos >10% |
| 2.3 Ordem (idioma→limpeza→qualidade→dedup) | ✅ | `_processar_documento` segue a ordem |
| 2.4 Remoção explícita de URLs | ✅ | `_RE_URL` + bs4 |
| 2.5 PT-BR vs PT-PT | ✅ (documentado) | langdetect 'pt'; heurística PT-PT em `_PT_PT_HINTS` (opcional) |
| 2.6 Sem diálogo artificial | ✅ | `_classificar_documento` — texto corrido → `text`; QA → `messages` |
| 2.7 IterableDataset.filter | ⚠️ adaptado | Usamos gerador streaming próprio (mais leve p/ .jsonl/.parquet do Rigel); `.filter()` não se aplica a arquivos locais — documentado |
| 4. Entregável + instalação | ✅ | Comentário de instalação no topo |

### Testes reais executados (05/08)
- **Amostra sintética** (6 docs): SFT=3, Pretrain=2, dedup=1 — schema `messages` correto.
- **`dominguesm_alpaca-data-pt-br`** (6.000 docs de 51.759): 4.242 SFT limpos (70% aprox.) em 38s.
- **Correções aplicadas:** (1) reconhecer formato instrução (Alpaca/Canarim) → ChatML; (2) não duplicar dataset.jsonl+parquet; (3) salvar em lotes parciais + mesclar (não sobrescrever); (4) schema pyarrow explícito para `messages`.

### Próximos passos (06/08+)
- [ ] Integrar no dashboard (aba Executor, com barra de progresso)
- [ ] Orquestrador: fila dos 5 datasets (alpaca → canarim → wikipedia → Madras1 v2 → Madras1 v1), 1 por vez
- [ ] Rodar alpaca COMPLETO (51.759 docs) e mostrar resultado
- [ ] Validar com arquivos menores antes dos grandes (regra do usuário)
- [ ] Decidir formato de treino: parquet → jsonl para `treinar_com_jsonl.py`, ou adaptar treinador
