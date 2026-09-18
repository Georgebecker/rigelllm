# ☁️ LISTA DE COMANDOS PARA O COLAB (15/08/2026)

> Treino do RigelSLM no Google Colab (T4 ~50-100x mais rápido que CPU local).
> **Pacote PRONTO**: `dados/gerados/colab/rigel_colab.jsonl` (612 exemplos = 344 fila aprovada + 268 livros, 0 mojibake, 2,7 MB).

## 0.5) Conferir GPU (1ª célula — SEMPRE rodar antes de treinar)
> Confirma que o Colab te deu uma GPU de verdade (se não tiver, o treino vai
> ser lentíssimo em CPU). Se aparecer "Not connected to a GPU", use
> Ambiente → Alterar tipo de runtime → T4 GPU e rode de novo.
```python
gpu_info = !nvidia-smi
gpu_info = '\n'.join(gpu_info)
if gpu_info.find('failed') >= 0:
  print('Not connected to a GPU')
else:
  print(gpu_info)
```

## 0) Preparar no PC (JÁ FEITO 15/08)
```bash
# Pacote único pronto:
#   dados/gerados/colab/rigel_colab.jsonl  (612 exemplos)
# Regenerar (se mudar material):
python scripts/preparar_colab.py
```

## 1) Upload para o Colab
- Enviar: `dados/gerados/jsonl/livros/*.jsonl` (todos os 4 livros) para a pasta `data/` no Colab
- Enviar: `tokenizer/tokenizer.json` e `modelo/modelo_melhor.pt` (base do treino)

## 2) Instalar dependências (1ª célula)
```python
!pip install torch --index-url https://download.pytorch.org/whl/cu121 2>/dev/null | tail -1
!pip install transformers tokenizers tqdm 2>/dev/null | tail -1
```

## 3) Carregar tokenizer + base
```python
from tokenizers import Tokenizer
tok = Tokenizer.from_file("/content/tokenizer.json")
print("tokens:", tok.get_vocab_size())
```

## 4) Treinar (SFT com o pacote — loss só no assistant)
> ⚠️ O treinador espera uma PASTA com jsonl — mova o pacote para uma pasta:
```python
!mkdir -p data/train && mv data/rigel_colab.jsonl data/train/
!python treinar_com_jsonl.py --dados data/train --epochs 3 \
    --batch-size 32 --seq-len 512 --accum 8 --lr 0.0001 --no-interactive
```

## 5) Validar com geração de amostra
```python
!python treinar_com_jsonl.py --test data/livros --no-interactive
# ou via chat local depois de converter p/ GGUF
```

## 6) Salvar/baixar o modelo treinado
```python
# modelo_melhor.pt é salvo automaticamente; baixar do Colab para modelo/
```

## 7) Converter para GGUF (usar no Ollama)
```bash
# No PC (após baixar o modelo):
python converter_para_gguf.py --model modelo/modelo_melhor.pt --quant Q4_K_M
ollama create rigelslm -f gguf/Modelfile
```

## ⚠️ Notas
- O Colab (T4) treina ~50-100x mais rápido: 268 exemplos ≈ poucos minutos
- Se usar GPU, remova `--threads`/`--num-workers` (o treinador detecta GPU)
- Registro/log: o treinador grava `logs/treinar_jsonl.log` + `logs/metricas_jsonl.json`
  (no Colab, salvar o log para baixar — `!cp logs/treinar_jsonl.log /content/treinar_jsonl.log`)
- NUNCA treinar material da fila cru (alucinações) — só após ajuizar
