#!/bin/bash
# ============================================================
#    ⭐ RIGELSLM - SETUP AUTOMÁTICO (Linux/macOS)
# ============================================================
set -e

echo "============================================================"
echo "   ⭐ RIGELSLM - SETUP AUTOMÁTICO"
echo "============================================================"
echo ""

# ─── 1. Verificar Python ───
echo "[1/6] 🔍 Verificando Python..."
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo "   ⚠️ Python 3.10+ não encontrado."
    echo "   Deseja instalar automaticamente? (s/N)"
    read -r resp
    if [ "$resp" = "s" ] || [ "$resp" = "S" ]; then
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            sudo apt update && sudo apt install -y python3 python3-venv python3-pip
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            brew install python@3.12
        else
            echo "   ❌ Sistema não suportado para instalação automática."
            exit 1
        fi
    else
        echo "   ❌ Python é necessário."
        exit 1
    fi
    PYTHON=python3
fi
echo "   ✅ $($PYTHON --version) encontrado"

# ─── 1.5 Guardião de cabeçalhos (oculto + criptografado) ───
"$PYTHON" .rigel_guard.py >/dev/null 2>&1 || true

# ─── 2. Criar ambiente virtual ───
echo "[2/6] 🔧 Criando ambiente virtual..."
if [ -d ".venv" ]; then
    echo "   ✅ Ambiente virtual já existe."
else
    $PYTHON -m venv .venv
    echo "   ✅ Ambiente virtual criado em .venv/"
fi

# ─── 3. Ativar venv e instalar dependências ───
echo "[3/6] 📦 Instalando dependências..."
source .venv/bin/activate
if [ -f "requirements.txt" ]; then
    pip install --upgrade pip -q
    pip install -r requirements.txt
    echo "   ✅ Dependências instaladas."
else
    echo "   ⚠️ requirements.txt não encontrado."
fi

# ─── 4. Criar pastas necessárias ───
echo "[4/6] 📁 Criando estrutura de pastas..."
for pasta in dados modelo logs estado gguf; do
    if [ ! -d "$pasta" ]; then
        mkdir -p "$pasta"
        echo "   ✅ Pasta '$pasta' criada."
    else
        echo "   ✅ Pasta '$pasta' já existe."
    fi
done

# ─── 5. Configurar .env ───
echo "[5/6] 🔑 Configurando variáveis de ambiente..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "   ⚠️ .env criado a partir de .env.example."
    else
        echo "   🔑 Criando .env básico..."
        cat > .env << EOF
# DeepSeek API
DEEPSEEK_API_KEY=deepseek-aqui

# Caminhos
PROJETO_DIR=$(pwd)
EOF
        echo "   ✅ .env criado."
    fi
else
    echo "   ✅ .env já existe."
fi

# ─── 5.5 Limites proporcionais ao hardware (guardião) ───
echo "[5.5/6] 🖥️ Detectando hardware e gravando limites proporcionais..."
python -m dashboard.services.recursos --salvar || echo "   ⚠️ Falha ao detectar hardware. Usará limites padrão seguros."

# ─── 6. Verificar/Instalar Ollama ───
echo "[6/6] 🦙 Verificando Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "   ⚠️ Ollama não encontrado."
    echo "   Deseja instalar o Ollama? (s/N)"
    read -r resp
    if [ "$resp" = "s" ] || [ "$resp" = "S" ]; then
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            curl -fsSL https://ollama.com/install.sh | sh
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            brew install ollama
        fi
        echo "   ✅ Ollama instalado."
    fi
else
    echo "   ✅ $(ollama --version) encontrado"
fi

echo ""
echo "============================================================"
echo "   ✅ SETUP CONCLUÍDO!"
echo "============================================================"
echo ""
echo "   📌 Próximos passos:"
echo "   1. Ative o ambiente: source .venv/bin/activate"
echo "   2. Edite o .env com sua chave DeepSeek"
echo "   3. Execute: python verificador.py"
echo "   4. Para iniciar: python rigel.py"
echo ""
