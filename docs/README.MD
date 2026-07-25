# Documentação do RigelSLM

Este diretório contém toda a documentação do projeto.

C:\Rigelllm
├── .vscode/ # Configurações do VS Code
├── .venv/ # Ambiente virtual
├── dados/ # Dados brutos e processados## Estrutura de Diretórios



C:\Rigelllm\
├── .vscode/          # Configurações do VS Code
├── .venv/            # Ambiente virtual
├── dados/            # Dados brutos e processados
│   ├── processed/    # Dados prontos para treino (2.16M+ arquivos)
│   ├── processed_lotes/ # Dados agrupados (recomendado)
│   ├── gerados/      # Dados sintéticos
│   └── raw/          # Dados brutos (originais)
├── modelo/           # Checkpoints e modelos treinados
│   ├── checkpoint.pt # Último checkpoint (sempre atualizado)
│   ├── checkpoint_epXX_batchXXXXX.pt # Checkpoints nomeados (backup)
│   ├── checkpoint_epXX_final.pt # Checkpoint ao final de cada época
│   ├── modelo_melhor.pt # Melhor modelo (validação)
│   └── modelo.pt     # Modelo final
├── tokenizer/        # Tokenizador (tokenizer.json)
├── logs/             # Logs do sistema
├── gguf/             # Modelos convertidos para GGUF
├── dashboard/        # Interface web (FastAPI)
├── docs/             # Documentação centralizada
│   ├── PROFILE.md    # Perfil do projeto (manual do assistente)
│   └── CHANGELOG.md  # Este arquivo
├── skills/           # Habilidades reutilizáveis (prompts, guias)
├── scripts/          # Scripts utilitários
├── .env              # Variáveis de ambiente (chaves API)
├── .gitignore        # Arquivos ignorados pelo Git
├── requirements.txt  # Dependências Python
├── README.md         # Documentação principal
├── treino.py         # Script principal de treino
├── chat.py           # Chat interativo
├── app.py            # Interface web (Gradio)
├── agrupar.py        # Agrupador de arquivos
├── converter_para_gguf.py # Conversor para GGUF
├── config.py         # Configurações centralizadas
├── dialogos.py       # Geração de dados sintéticos v1
├── dialogos2.py      # Geração de dados sintéticos v2
└── ... (outros arquivos .py)

Dependências Principais
torch >= 2.0.0

tokenizers >= 0.13.0

openai >= 1.0.0

httpx >= 0.24.0

fastapi >= 0.104.0

uvicorn >= 0.24.0

psutil >= 5.9.0

gguf >= 0.3.0

gradio >= 4.0.0 