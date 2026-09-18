# 🎯 PLANO DO TREINO — 15/08/2026

> Regra de ouro: só treinar material VERIFICADO (testar → verificar → tratar → visualizar).
> ⚠️ NUNCA usar material da fila CRU (tem alucinações do llama3.2:3b).

## 📦 Material disponível (verificado 14/08)

| Fonte | Exemplos | Estado | Uso |
|---|---|---|---|
| **Livros (3 PDFs)** — `dados/gerados/jsonl/livros/` | **205** (história-da-literatura 141, a-filha-do-barao 25, o-bom-crioulo 39) | ✅ Verificado (0 mojibake, temas reais) | **PRONTO — usar** |
| Livros TXT extraídos — `dados/gerados/txt_livros/` | 3 arquivos (1,2 MB) | ✅ Limpos | fonte do jsonl |
| Material da FILA — `dados/gerados/gerados_local/` | 1.033 txt (subindo) | ⚠️ **PRECISA AJUIZAR** (alucinações) | SÓ após ajuizar |
| Acervo antigo — `dados/processed/jsonl/` | 5.343 (39,7 GB) | 📦 antigo | não priorizar |

## ⚖️ ANTES de treinar (pendências)
1. **Ajuizar o material da fila** (Executor → ⚖️ Ajuizar) — filtra alucinações
2. **Decidir**: treino local pequeno OU Colab (volume)
3. Se for Colab: empacotar os livros (205) + material ajuizado em um jsonl único

## 🧪 TREINO LOCAL (teste rápido — CPU)
```
python treinar_com_jsonl.py --dados dados/gerados/jsonl/livros \
    --max-exemplos 200 --epochs 1 --batch-size 8 --seq-len 256 --accum 4
```
- ⏱️ ~2-4 min | valida pipeline | loss esperado ~7-9 (1 época só)
- ⚠️ Teste de 12/08: 12,7h para 295 steps → **não** rodar volume grande local

## ☁️ TREINO COLAB (volume — recomendado)
- Enviar `dados/gerados/jsonl/livros/*.jsonl` (205 exemplos) + material ajuizado
- Notebook: `RigelSLM_Colab.ipynb` (T4 ~50-100x mais rápido que CPU local)
- Duração sugerida: 1-2 épocas no material dos livros (continuidade em PT-BR literário)

## ✅ Checklist pós-treino
- [ ] Geração de amostra (modelo responde coerente em PT-BR)
- [ ] Verificar loss caindo
- [ ] Converter p/ GGUF (converter_para_gguf.py) se for usar no Ollama
- [ ] Backup do novo modelo (modelo_backup.criar_backup)
