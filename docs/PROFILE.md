# Perfil do Projeto RigelSLM

**Versão:** 1.0.0  
**Última atualização:** 31 de Julho de 2026  
**Arquivos de treino:** 1.089  
**Autor:** George Herman Becker  

---

## 1. Objetivo Principal

RigelSLM é um modelo de linguagem pequeno (SLM) treinado do zero para o português brasileiro. O projeto visa criar um modelo leve, eficiente e culturalmente alinhado com o Brasil.

---

## 2. Stack e Tecnologias

| Área | Tecnologia |
|------|------------|
| **Linguagem principal** | Python 3.12 |
| **Framework de ML** | PyTorch 2.0+ (com CUDA e AMP) |
| **Tokenização** | `tokenizers` (BPE) |
| **Deploy** | GGUF + Ollama (para inferência local) |
| **Plataforma de treino** | Google Colab (GPU Tesla T4) |
| **Plataforma de preparação** | Windows Server (Dual Xeon E5-2699 v3, 48 GB RAM) |
| **Interface** | FastAPI + Uvicorn (dashboard) |
| **Frontend** | Tailwind CSS + Alpine.js (SPA) |

---

## 3. Regras de Código (Python)

### Estilo
- **Indentação:** 4 espaços.
- **Nomenclatura:** `snake_case` para funções e variáveis. `PascalCase` para classes.
- **Imports:** Organizar em ordem: bibliotecas padrão → bibliotecas externas → módulos internos.
- **Docstrings:** Usar formato Google para todas as funções e classes.
- **Type Hints:** SEMPRE usar type hints para parâmetros e retornos.

### Estrutura
- Cada arquivo `.py` deve ter um cabeçalho com versão e descrição.
- O cabeçalho deve ser atualizado sempre que o arquivo for modificado.
- Usar `argparse` para scripts principais (ex: `treino.py`).

### Tratamento de Erros
- Usar `try/except` com logs específicos.
- Nunca silenciar exceções sem registro.

---

## 4. Estrutura do Projeto

| Pasta | Conteúdo |
|-------|----------|
| `dados/` | Datasets e arquivos de treino. **NÃO versionar no Git.** |
| `modelo/` | Checkpoints e modelos salvos. **NÃO versionar no Git.** |
| `tokenizer/` | Tokenizador treinado. **Versionar no Git.** |
| `logs/` | Logs do sistema. **NÃO versionar no Git.** |
| `gguf/` | Modelos convertidos para GGUF. **NÃO versionar no Git.** |
| `dashboard/` | Código da interface web (FastAPI). **Versionar no Git.** |
| `src/` | Código-fonte principal (módulos reutilizáveis). **Versionar no Git.** |
| `tests/` | Testes unitários. **Versionar no Git.** |
| `docs/` | Documentação centralizada. **Versionar no Git.** |
| `skills/` | Prompts e regras para assistentes. **Versionar no Git.** |
| `scripts/` | Scripts utilitários. **Versionar no Git.** |

---

## 5. Regras de Versionamento

### Arquivos
- **Cabeçalho:** Sempre atualizar a versão no cabeçalho de cada arquivo modificado.
- **Versão:** Usar formato `vX.Y.Z` (major.minor.patch).
- **Changelog:** Manter um `CHANGELOG.md` em `docs/` com todas as alterações.

### Git
- **Commits:** Usar mensagens no formato `[tipo] descrição` (ex: `[feat] Adiciona suporte a batch size 16`).
- **Branches:** `main` para produção, `dev` para desenvolvimento, `feature/*` para novas funcionalidades.
- **Pull Requests:** Sempre revisar o código antes de merge.

---

## 6. Gerenciamento de Configurações

- **APIs:** Usar `.env` para chaves de API. **NUNCA versionar `.env`.**
- **Paths:** Usar `os.path.join()` para garantir compatibilidade entre sistemas.
- **Argumentos:** SEMPRE passar argumentos via `argparse` para scripts principais.
- **Variáveis globais:** Centralizar em `config.py`.

---

## 7. Histórico de Problemas e Soluções

| Problema | Solução |
|----------|---------|
| **Checkpoint corrompido** | Manter checkpoints nomeados (`checkpoint_epXX_batchXXXXX.pt`). Usar `ln -sf` para substituir `checkpoint.pt` por um checkpoint anterior. |
| **Timeout do Google Drive** | Usar `--max-arquivos` para limitar a listagem. Agrupar arquivos em lotes com `agrupar.py`. |
| **DataLoader workers mortos** | Definir `num_workers=1` e `timeout=0` no DataLoader. Usar `multiprocessing_context='fork'`. |
| **OOM (Out Of Memory)** | Reduzir `batch_size`, `seq_len` ou usar `--precision fp32` (sem AMP). |
| **VOCAB_SIZE incompatível** | Detectar automaticamente do `tokenizer.json`. |

---

## 8. Fluxo de Trabalho Recomendado

### Treino no Colab
1. Monte o Drive: `drive.mount('/content/drive')`.
2. Entre na pasta: `cd /content/drive/MyDrive/rigelllm`.
3. Treine com: `python treino.py --dados dados/processed_lotes --resume --save-every 50`.

### Preparação de Dados Local
1. Agrupe arquivos: `python agrupar.py --entrada dados/processed --saida dados/processed_lotes --backup D:/backup/rigelllm/processed --pares 500`.

### Conversão para GGUF
1. Execute: `python converter_para_gguf.py`.
2. Selecione a quantização (recomendado: Q4_K_M).

### Chat com o Modelo
1. Modo interativo: `python chat.py --temperature 0.8 --max-tokens 200`.
2. Modo one-shot: `python chat.py --one-shot "Qual a capital do Brasil?"`.

---

## 9. Lembrete para Assistentes

- **Sempre pergunte** antes de fazer alterações estruturais.
- **Nunca entregue código incompleto.** Se for interrompido, avise e salve o progresso.
- **Sempre atualize o cabeçalho** dos arquivos modificados.
- **Use type hints e docstrings** em todo novo código.
- **Consulte o `PROFILE.md`** antes de sugerir soluções.

---

**Fim do Perfil**