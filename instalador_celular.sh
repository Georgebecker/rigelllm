#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
# 📱 INSTALADOR RIGELSLM PARA CELULAR (Android — Termux)
#
# Faz TUDO automaticamente no celular:
#   1. Instala as ferramentas (Python + pip + descompactador unzip)
#   2. Instala as dependências do requirements.txt
#   3. Sobe o servidor web (dashboard) em http://127.0.0.1:8000
#
# USO (dentro do Termux, na pasta do projeto — onde está este arquivo):
#   bash instalador_celular.sh          # instala TUDO (inclui torch ~2GB — demora)
#   bash instalador_celular.sh --leve   # só o dashboard (SEM torch — rápido)
#   bash instalador_celular.sh --server # já instalado: só sobe o servidor
# ============================================================================
set -e

VERMELHO="\033[0;31m"; VERDE="\033[0;32m"; AMARELO="\033[0;33m"; CIANO="\033[0;36m"; RESET="\033[0m"
info()  { echo -e "${CIANO}$1${RESET}"; }
ok()    { echo -e "${VERDE}$1${RESET}"; }
aviso() { echo -e "${AMARELO}$1${RESET}"; }
erro()  { echo -e "${VERMELHO}$1${RESET}"; }

MODO="$1"
cd "$(dirname "$0")"

echo ""
info "=============================================="
info "  📱 RIGELSLM — Instalador para Celular"
info "  (Android / Termux)"
info "=============================================="
echo ""

# ── Verifica se está na pasta do projeto ──────────────────────────────────
if [ ! -f "requirements.txt" ] || [ ! -d "dashboard" ]; then
    erro "❌ Este script deve rodar DENTRO da pasta do projeto (onde estão requirements.txt e dashboard/)."
    exit 1
fi

# ── 1. Ferramentas básicas (Python + pip + descompactador) ────────────────
if [ "$MODO" != "--server" ]; then
    info "⏳ 1/3 Instalando ferramentas (python, pip, unzip)..."
    pkg update -y
    pkg install -y python unzip
    ok "   ✅ Python instalado: $(python --version 2>&1)"
fi

# ── 2. Dependências Python ─────────────────────────────────────────────────
if [ "$MODO" != "--server" ]; then
    info "⏳ 2/3 Instalando dependências..."
    pip install --upgrade pip wheel setuptools
    if [ "$MODO" = "--leve" ]; then
        aviso "   ⚠️ Modo LEVE: só as dependências do dashboard (sem torch)."
        aviso "   ⚠️ O chat local (modelo.pt) e o treino NÃO funcionarão no celular."
        pip install fastapi "uvicorn>=0.30.6" "jinja2>=3.1.4" "python-multipart>=0.0.9" \
                "psutil>=5.9.0" "httpx>=0.24.0" "python-dotenv>=1.0.0" \
                "numpy>=1.24.0" "tqdm>=4.65.0"
    else
        info "   📦 Instalando requirements.txt (pode demorar — torch é grande)..."
        pip install -r requirements.txt
    fi
    ok "   ✅ Dependências instaladas."
fi

# ── 3. Verifica tokenizer/modelo (opcional) ───────────────────────────────
if [ ! -f "tokenizer/tokenizer.json" ]; then
    aviso "⚠️  tokenizer/tokenizer.json não encontrado — o chat local não vai responder."
fi

# ── 4. Sobe o servidor web ─────────────────────────────────────────────────
info "⏳ 3/3 Subindo o dashboard (servidor web leve)..."
echo ""
info "   🌐 Abra no navegador DESTE celular:  http://127.0.0.1:8000"
info "   🌐 De OUTRO aparelho (mesma rede):   http://IP_DESTE_CELULAR:8000"
echo ""
ok "🚀 Servidor iniciando (Ctrl+C para parar)..."
echo ""
exec python -m uvicorn dashboard.main:app --host 0.0.0.0 --port 8000
