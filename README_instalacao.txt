============================================================
 RIGELSLM - GUIA RAPIDO DE INSTALACAO
============================================================

1) Descompacte este ZIP em uma pasta de sua escolha.

2) Rode o instalador:
   - Windows: dê 2 cliques em executemeprimeiro.bat
   - Linux  : ./setup.sh

3) O instalador vai:
   - Verificar Python 3.11+ (e indicar o download se faltar)
   - Criar o ambiente virtual (.venv)
   - Instalar as dependencias (requirements.txt)
   - Ajustar os limites de recursos a SUA maquina
   - Verificar o Ollama (opcional)
   - Criar o .env a partir do .env.template
   - Iniciar o dashboard e abrir o navegador

4) Dashboard: http://127.0.0.1:8000

5) Para abrir depois (Windows): de 2 cliques em run_dashboard.bat

6) Para gerar dados pela API DeepSeek:
   - Edite o arquivo .env e defina DEEPSEEK_API_KEY
   - Chave gratuita/paga em https://platform.deepseek.com/

------------------------------------------------------------
DUAS OPCOES DE GERACAO DE CONTEUDO:
  1. API DeepSeek  -> alta qualidade, custo por token
  2. Ollama local  -> sem custo, qualidade depende do modelo

------------------------------------------------------------
SOLUCAO DE PROBLEMAS:
  - Python nao encontrado: baixe em https://www.python.org/downloads/
    e marque "Add Python to PATH".
  - Porta 8000 ocupada: feche outros servidores ou mude a porta
    (ex.: python -m uvicorn dashboard.main:app --port 8001).
  - Erro de dependencias: rode o instalador de novo (ele repete
    a instalacao automaticamente).
  - Memoria/disco: os limites sao ajustados ao hardware da maquina
    na instalacao (config_recursos.json) - nao force a maquina.

------------------------------------------------------------
REQUISITOS MINIMOS (orientativos):
  - Windows 10/11 ou Linux
  - Python 3.11+
  - 8 GB de RAM (recomendado 16 GB)
  - ~5 GB de disco livre (modelo + dependencias)
============================================================
