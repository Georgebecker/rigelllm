#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
rigel.py - Orquestrador do RigelSLM
Versão com LOG VERBOSO, BARRA DE PROGRESSO, Dashboard corrigido e GESTÃO DO OLLAMA.
"""
import os
import sys
import json
import subprocess
import platform
import shutil
import time
import socket
import webbrowser
import re
import threading
import itertools
from datetime import datetime
from pathlib import Path

# ============================================================================
# CORREÇÃO GLOBAL DE CODIFICAÇÃO
# ============================================================================
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================
PROJETO_DIR = Path(__file__).resolve().parent
VENV_ACTIVATE = PROJETO_DIR / ".venv" / "Scripts" / "activate.ps1"
VENV_ACTIVATE_BAT = PROJETO_DIR / ".venv" / "Scripts" / "activate.bat"
ESTADO_GLOBAL = PROJETO_DIR / "estado_global.json"
REGISTRO_PASTAS = PROJETO_DIR / "registro_pastas.json"
LOG_DIR = PROJETO_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
ARQUIVO_LOG_ERROS = LOG_DIR / "erros_dashboard.log"
ARQUIVO_LOG_ATIVIDADE = LOG_DIR / "rigel_activity.log"
REQUIREMENTS_PATH = PROJETO_DIR / "requirements.txt"
REQUIREMENTS_BACKUP = PROJETO_DIR / "requirements.txt.bak"

# ============================================================================
# FUNÇÕES DE LOG
# ============================================================================

def log(msg, nivel="INFO", emoji="📌", arquivo=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"{emoji} [{timestamp}] [{nivel}] {msg}"
    try:
        print(linha)
    except UnicodeEncodeError:
        linha_fallback = f"[{timestamp}] [{nivel}] {msg}"
        print(linha_fallback)
    if arquivo:
        with open(arquivo, 'a', encoding='utf-8') as f:
            f.write(linha + "\n")

def log_erro(msg):
    log(msg, nivel="ERRO", emoji="❌", arquivo=ARQUIVO_LOG_ERROS)

def log_atividade(msg, nivel="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{timestamp}] [{nivel}] {msg}"
    with open(ARQUIVO_LOG_ATIVIDADE, 'a', encoding='utf-8') as f:
        f.write(linha + "\n")

def pausar(mensagem="Pressione Enter para continuar..."):
    input(mensagem)

# ============================================================================
# FUNÇÕES DE PROGRESSO (SPINNER E BARRA)
# ============================================================================

def spinner_animado(stop_event, mensagem="⏳ Processando"):
    simbolos = itertools.cycle(['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'])
    while not stop_event.is_set():
        sys.stdout.write(f'\r{mensagem} {next(simbolos)}')
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write('\r' + ' ' * (len(mensagem) + 2) + '\r')

def barra_progresso(percentual, tamanho=20, cor="▰", vazio="▱"):
    cheios = int(percentual * tamanho / 100)
    vazios = tamanho - cheios
    return cor * cheios + vazio * vazios

# ============================================================================
# EXECUTA COMANDO COM PROGRESSO (CORRIGIDO PARA CP1252 NO WINDOWS)
# ============================================================================
def executar_comando_com_progresso(cmd, descricao="Executando", emoji="⚙️", env=None, registrar_saida=True):
    log_atividade(f"Iniciando comando: {' '.join(cmd)} | Descrição: {descricao}")
    log(f"{descricao}: {' '.join(cmd)}", emoji=emoji)

    if env is None:
        env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    if registrar_saida:
        arquivo_log = LOG_DIR / f"comando_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        with open(arquivo_log, 'w', encoding='utf-8') as flog:
            flog.write(f"Comando: {' '.join(cmd)}\n")
            flog.write(f"Descrição: {descricao}\n")
            flog.write("="*60 + "\n")
    else:
        arquivo_log = None

    stop_spinner = threading.Event()
    spinner_thread = threading.Thread(target=spinner_animado, args=(stop_spinner, f"⏳ {descricao}"))
    spinner_thread.daemon = True
    spinner_thread.start()
    inicio = time.time()

    # CORREÇÃO: usa encoding='cp1252' com errors='ignore' no Windows
    if platform.system() == "Windows":
        encoding = "cp1252"
    else:
        encoding = "utf-8"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        cwd=str(PROJETO_DIR),
        encoding=encoding,
        errors='ignore'   # ignora caracteres que não podem ser decodificados
    )

    for line in process.stdout:
        stop_spinner.set()
        spinner_thread.join(timeout=0.1)
        try:
            print(line, end='')
        except UnicodeEncodeError:
            print(line.encode('ascii', errors='ignore').decode('ascii'), end='')
        if arquivo_log:
            with open(arquivo_log, 'a', encoding='utf-8') as f:
                f.write(line)
        if not stop_spinner.is_set():
            stop_spinner.clear()
            spinner_thread = threading.Thread(target=spinner_animado, args=(stop_spinner, f"⏳ {descricao}"))
            spinner_thread.daemon = True
            spinner_thread.start()

    process.wait()
    stop_spinner.set()
    spinner_thread.join(timeout=0.5)
    duracao = time.time() - inicio

    if process.returncode != 0:
        log_erro(f"❌ Comando falhou com código {process.returncode} (duração: {duracao:.1f}s)")
        log_atividade(f"Comando FALHOU (código {process.returncode}) após {duracao:.1f}s")
        if arquivo_log:
            with open(arquivo_log, 'a', encoding='utf-8') as f:
                f.write(f"\nCódigo de retorno: {process.returncode}\n")
    else:
        log(f"✅ {descricao} concluído com sucesso! (duração: {duracao:.1f}s)", emoji="✅")
        log_atividade(f"Comando concluído com SUCESSO após {duracao:.1f}s")

    sys.stdout.write('\r' + ' ' * 80 + '\r')
    sys.stdout.flush()
    return process.returncode

# ============================================================================
# DEMAIS AUXILIARES
# ============================================================================

def carregar_estado():
    if ESTADO_GLOBAL.exists():
        with open(ESTADO_GLOBAL, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salvar_estado(estado):
    with open(ESTADO_GLOBAL, 'w', encoding='utf-8') as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)

def perguntar_sim_nao(pergunta, padrao="s"):
    opcao = input(f"❓ {pergunta} (s/N): ").strip().lower()
    if opcao == "":
        return padrao.lower() == "s"
    return opcao in ["s", "sim", "y", "yes"]

def porta_livre(porta=8000):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', porta)) != 0

def listar_modelos_ollama():
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, encoding='cp1252', errors='ignore')
        if result.returncode == 0:
            linhas = result.stdout.strip().split('\n')[1:]
            modelos = [linha.split()[0] for linha in linhas if linha.strip()]
            return modelos
        else:
            return []
    except:
        return []

def corrigir_requirements():
    if not REQUIREMENTS_PATH.exists():
        log("⚠️ requirements.txt não encontrado. Pulando correção.", emoji="⚠️")
        return False
    shutil.copy2(REQUIREMENTS_PATH, REQUIREMENTS_BACKUP)
    log_atividade(f"Backup de requirements.txt criado em {REQUIREMENTS_BACKUP}")
    with open(REQUIREMENTS_PATH, 'r', encoding='utf-8') as f:
        conteudo = f.read()
    padrao = r"^torch\s*[<>=]+.*$"
    linhas = conteudo.splitlines()
    alterado = False
    novas_linhas = []
    for linha in linhas:
        if re.match(padrao, linha, re.IGNORECASE):
            nova_linha = "torch>=2.0.0"
            log(f"🔄 Substituindo '{linha}' por '{nova_linha}'", emoji="🔄")
            log_atividade(f"Substituição no requirements: '{linha}' -> '{nova_linha}'")
            novas_linhas.append(nova_linha)
            alterado = True
        else:
            novas_linhas.append(linha)
    if alterado:
        with open(REQUIREMENTS_PATH, 'w', encoding='utf-8') as f:
            f.write("\n".join(novas_linhas))
        log("✅ requirements.txt corrigido.", emoji="✅")
        log_atividade("requirements.txt corrigido (torch sem limite superior)")
        return True
    else:
        log("ℹ️ Nenhuma linha problemática do torch encontrada.", emoji="ℹ️")
        return False

# ============================================================================
# FUNÇÕES DE GERENCIAMENTO DO OLLAMA (NOVO)
# ============================================================================

def matar_ollama():
    """Mata todos os processos do Ollama (Windows)."""
    try:
        result = subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"], capture_output=True, text=True, encoding='cp1252', errors='ignore')
        if result.returncode == 0:
            log("✅ Todos os processos Ollama foram finalizados.", emoji="✅")
            return True
        elif "não encontrado" in result.stderr or "not found" in result.stderr:
            log("ℹ️ Nenhum processo Ollama em execução.", emoji="ℹ️")
            return True
        else:
            log(f"❌ Erro ao matar Ollama: {result.stderr}", nivel="ERRO", emoji="❌")
            return False
    except Exception as e:
        log_erro(f"Erro ao matar Ollama: {e}")
        return False

def limpar_cache_ollama():
    """Remove os arquivos de cache do Ollama (opcional, com confirmação)."""
    cache_dir = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama" / "models"))
    if cache_dir.exists():
        log(f"🗑️ Cache encontrado em: {cache_dir}", emoji="🗑️")
        if perguntar_sim_nao("Deseja limpar o cache do Ollama? (os modelos baixados serão apagados)"):
            try:
                shutil.rmtree(cache_dir)
                log("✅ Cache do Ollama removido.", emoji="✅")
                return True
            except Exception as e:
                log_erro(f"Erro ao limpar cache: {e}")
                return False
    else:
        log("ℹ️ Nenhum cache encontrado.", emoji="ℹ️")
        return True

def iniciar_ollama(aguardar=True, timeout=30):
    """Inicia o Ollama (serve) e aguarda ficar disponível."""
    log("▶️ Iniciando Ollama...", emoji="▶️")
    cmd = ["ollama", "serve"]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0)
    if aguardar:
        import socket
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    s.connect(("127.0.0.1", 11434))
                    log("✅ Ollama iniciado e respondendo na porta 11434.", emoji="✅")
                    return True
            except:
                time.sleep(1)
        log(f"❌ Ollama não respondeu após {timeout}s.", nivel="ERRO", emoji="❌")
        return False
    return True

def carregar_modelo_ollama(modelo):
    """Carrega um modelo no Ollama (força o download se não existir)."""
    if not modelo:
        log("❌ Nenhum modelo especificado.", nivel="ERRO", emoji="❌")
        return False
    log(f"📥 Carregando modelo {modelo}...", emoji="📥")
    cmd = ["ollama", "pull", modelo]
    if executar_comando_com_progresso(cmd, f"Baixando/carregando {modelo}", emoji="📥") != 0:
        log(f"❌ Falha ao carregar modelo {modelo}.", nivel="ERRO", emoji="❌")
        return False
    return True

def reiniciar_ollama_com_modelo(modelo=None):
    """
    Mata o Ollama, limpa o cache (opcional), inicia novamente e carrega um modelo.
    """
    log("🔄 Reiniciando Ollama com modelo...", emoji="🔄")
    if not matar_ollama():
        return False
    time.sleep(2)  # dá um tempo para o processo realmente morrer
    if not iniciar_ollama(aguardar=True, timeout=60):
        return False
    if modelo:
        if not carregar_modelo_ollama(modelo):
            return False
    log("✅ Ollama reiniciado com sucesso!", emoji="✅")
    return True

# ============================================================================
# FUNÇÃO PARA INICIAR O DASHBOARD (COM REINÍCIO AUTOMÁTICO)
# ============================================================================
def iniciar_dashboard(host="127.0.0.1", port=8000):
    candidatos = [
        ("dashboard/routes/api.py", "app"),
        ("dashboard/main.py", "app"),
        ("main.py", "app"),
    ]
    for caminho_arquivo, var_name in candidatos:
        caminho_abs = PROJETO_DIR / caminho_arquivo
        if caminho_abs.exists():
            module_path = str(caminho_abs.relative_to(PROJETO_DIR)).replace("/", ".").replace("\\", ".").replace(".py", "")
            cmd = [
                sys.executable, "-m", "uvicorn",
                f"{module_path}:{var_name}",
                "--host", host,
                "--port", str(port)
            ]
            log(f"🚀 Iniciando Dashboard: {module_path}:{var_name}", emoji="🚀", arquivo=ARQUIVO_LOG_ERROS)
            log_atividade(f"Iniciando Dashboard com: {' '.join(cmd)}")
            print(f"   Acesse: http://{host}:{port}")
            print("   Pressione Ctrl+C para encerrar o servidor.")
            print("   Logs do servidor serão gravados em:", LOG_DIR / "dashboard.log")
            with open(LOG_DIR / "dashboard.log", 'a', encoding='utf-8') as flog:
                flog.write(f"\n{'='*60}\n")
                flog.write(f"Início do servidor em {datetime.now()}\n")
                flog.write(f"Comando: {' '.join(cmd)}\n")
                flog.write(f"{'='*60}\n")
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                # Loop de reinício automático
                while True:
                    try:
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1,
                            cwd=str(PROJETO_DIR),
                            env=env,
                            encoding='cp1252',
                            errors='ignore'
                        )
                        for line in process.stdout:
                            try:
                                print(line, end='')
                            except:
                                pass
                            flog.write(line)
                        process.wait()
                        if process.returncode != 0:
                            log_erro(f"Servidor encerrou com código {process.returncode}. Reiniciando em 5s...")
                            log_atividade(f"Dashboard encerrou com código {process.returncode}. Reiniciando...")
                            time.sleep(5)
                            continue
                        else:
                            break
                    except KeyboardInterrupt:
                        log("⏹️ Servidor interrompido pelo usuário.", emoji="⏹️")
                        break
                    except Exception as e:
                        log_erro(f"Erro inesperado: {e}. Reiniciando em 5s...")
                        time.sleep(5)
                        continue
            return
    log_erro("❌ Nenhum arquivo FastAPI encontrado. Verifique a estrutura.")
    log_atividade("ERRO: Nenhum arquivo FastAPI encontrado para o Dashboard.")
    pausar()

# ============================================================================
# FUNÇÃO PARA EXIBIR COMANDOS OLLAMA
# ============================================================================
def exibir_comandos_ollama():
    while True:
        print("\n" + "="*70)
        print("   📋 COMANDOS OLLAMA")
        print("="*70)
        print("\n🔹 Modelos disponíveis localmente:")
        modelos = listar_modelos_ollama()
        if modelos:
            for i, m in enumerate(modelos, 1):
                print(f"   {i}. {m}")
        else:
            print("   (Nenhum modelo encontrado. Use 'pull' para baixar.)")
        print("\n🔹 Comandos úteis:")
        comandos = [
            ("ollama list", "Lista modelos baixados no disco."),
            ("ollama ps", "Mostra modelos carregados na RAM no momento."),
            ("ollama pull <modelo>", "Baixa um modelo (ex: qwen2.5:14b, llama3.2:1b)."),
            ("ollama run <modelo>", "Abre chat interativo com o modelo."),
            ("ollama run <modelo> --verbose", "Mostra tokens/segundo para testar performance."),
            ("ollama stop <modelo>", "Descarrega o modelo da memória."),
            ("ollama rm <modelo>", "Remove o modelo do disco."),
            ("ollama cp <modelo> <novo_nome>", "Cria uma cópia com outro nome."),
            ("ollama show <modelo>", "Mostra detalhes do modelo (tamanho, parâmetros)."),
        ]
        for cmd, desc in comandos:
            print(f"   • {cmd:30} - {desc}")
        print("\n🔹 Executar um comando:")
        print("  1. Pull (baixar um modelo)")
        print("  2. Run (executar chat interativo)")
        print("  3. Stop (descarregar da memória)")
        print("  4. Show (detalhes do modelo)")
        print("  5. List (atualizar lista)")
        print("  6. Voltar")
        op = input("👉 Escolha uma opção (1-6): ").strip()
        log_atividade(f"Ollama: escolheu opção {op}")
        if op == "1":
            modelo = input("📥 Nome do modelo para baixar (ex: llama3.2:1b): ").strip()
            if modelo:
                executar_comando_com_progresso(["ollama", "pull", modelo], f"Baixando {modelo}", emoji="📥")
                pausar()
        elif op == "2":
            modelo = input("▶️  Nome do modelo para rodar (ex: llama3.2:1b): ").strip()
            if modelo:
                executar_comando_com_progresso(["ollama", "run", modelo], f"Executando {modelo}", emoji="▶️")
                pausar()
        elif op == "3":
            modelo = input("⏹️  Nome do modelo para parar: ").strip()
            if modelo:
                executar_comando_com_progresso(["ollama", "stop", modelo], f"Parando {modelo}", emoji="⏹️")
                pausar()
        elif op == "4":
            modelo = input("🔍 Nome do modelo para detalhes: ").strip()
            if modelo:
                executar_comando_com_progresso(["ollama", "show", modelo], f"Detalhes de {modelo}", emoji="🔍")
                pausar()
        elif op == "5":
            continue
        elif op == "6":
            break
        else:
            print("❌ Opção inválida.")
            pausar()

def configurar_ambiente():
    log_atividade("Iniciando configuração do ambiente (opção 8->3)")
    if REQUIREMENTS_PATH.exists():
        corrigir_requirements()
    else:
        log("⚠️ requirements.txt não encontrado. Pulando correção.", emoji="⚠️")
    if Path("setup_env.py").exists():
        print("🛠️  Iniciando configuração do ambiente...")
        executar_comando_com_progresso(["python", "setup_env.py"], "Configurando ambiente", emoji="🛠️")
        pausar()
    else:
        print("⚠️ setup_env.py não encontrado. Execute manualmente:")
        print("   pip install -r requirements.txt")
        pausar()

# ============================================================================
# MENU PRINCIPAL E SUBMENUS
# ============================================================================

def menu_principal():
    log_atividade("=== INÍCIO DA SESSÃO ===")
    while True:
        print("\n" + "="*70)
        print("   ⭐ RIGELSLM - SISTEMA UNIFICADO")
        print("="*70)
        print("  1. 🧠 Treinar Modelo")
        print("  2. 📥 Preparar Dados (download, qualificação)")
        print("  3. 🧹 Gerenciar Dados (limpeza, agrupamento, validação)")
        print("  4. ✨ Gerar Dados Sintéticos (Diálogos v2, RSS, Tradução)")
        print("  5. 🔄 Converter Modelo para GGUF e Gerenciar Ollama")
        print("  6. 🖥️  Dashboard (FastAPI)")
        print("  7. 📊 Logs e Estatísticas")
        print("  8. 🛠️  Configurações do Ambiente")
        print("  9. 🚪 Sair")
        print("="*70)
        opcao = input("👉 Escolha uma opção: ").strip()
        log_atividade(f"Menu principal: escolheu opção {opcao}")
        if opcao == "1":
            menu_treino()
        elif opcao == "2":
            menu_preparar_dados()
        elif opcao == "3":
            menu_gerenciar_dados()
        elif opcao == "4":
            menu_gerar_dados()
        elif opcao == "5":
            menu_converter_ollama()
        elif opcao == "6":
            menu_dashboard()
        elif opcao == "7":
            menu_logs()
        elif opcao == "8":
            menu_configuracoes()
        elif opcao == "9":
            print("👋 Saindo...")
            log_atividade("=== FIM DA SESSÃO (usuário saiu) ===")
            break
        else:
            print("❌ Opção inválida.")
            pausar()

def menu_treino():
    print("\n--- 🧠 TREINAR MODELO ---")
    estado = carregar_estado()
    print(f"📅 Último treino: {estado.get('ultimo_treino', 'Nunca')}")
    print("Escolha o ambiente:")
    print("  1. 💻 Local (CPU) - Máquina atual")
    print("  2. 🚀 Local (GPU) - se tiver placa NVIDIA")
    print("  3. ☁️  Google Colab - gera script para copiar")
    print("  4. 🔙 Voltar")
    sub = input("👉 Opção: ").strip()
    log_atividade(f"Treino: escolheu subopção {sub}")
    if sub == "1":
        pasta = input("📁 Pasta de dados (default: dados/processed): ") or "dados/processed"
        max_arq = input("📄 Máximo de arquivos (default: 20000): ") or "20000"
        epochs = input("🔄 Épocas (default: 20): ") or "20"
        resume = perguntar_sim_nao("Continuar de checkpoint?")
        cmd = ["python", "treino.py", "--dados", pasta, "--max-arquivos", max_arq, "--epochs", epochs, "--usar-registro"]
        if resume:
            cmd.append("--resume")
        executar_comando_com_progresso(cmd, "Iniciando treino local (CPU)", emoji="🧠")
        estado['ultimo_treino'] = datetime.now().isoformat()
        salvar_estado(estado)
        pausar()
    elif sub == "2":
        if not shutil.which("nvidia-smi"):
            print("⚠️ Nvidia-smi não encontrado. GPU pode não estar disponível.")
        pasta = input("📁 Pasta de dados (default: dados/processed): ") or "dados/processed"
        max_arq = input("📄 Máximo de arquivos (default: 20000): ") or "20000"
        epochs = input("🔄 Épocas (default: 20): ") or "20"
        resume = perguntar_sim_nao("Continuar de checkpoint?")
        cmd = ["python", "treino.py", "--dados", pasta, "--max-arquivos", max_arq, "--epochs", epochs, "--usar-registro", "--precision", "amp"]
        if resume:
            cmd.append("--resume")
        executar_comando_com_progresso(cmd, "Iniciando treino local (GPU)", emoji="🚀")
        estado['ultimo_treino'] = datetime.now().isoformat()
        salvar_estado(estado)
        pausar()
    elif sub == "3":
        print("\n📋 Copie o código abaixo para uma célula do Colab:\n")
        print("""
# Montar Drive
from google.colab import drive
drive.mount('/content/drive')
%cd /content/drive/MyDrive/rigelllm

# Instalar dependências (se necessário)
!pip install -r requirements.txt

# Treinar (ajuste os parâmetros conforme sua necessidade)
!python treino.py --dados dados/processed --max-arquivos 50000 --epochs 30 --usar-registro --resume
""")
        pausar()
    elif sub == "4":
        return

def menu_preparar_dados():
    print("\n--- 📥 PREPARAR DADOS ---")
    print("  1. 🌐 Baixar datasets (Ultrachat, Tucano, Guará, etc.)")
    print("  2. ✅ Qualificar dados (validar, limpar, copiar para processed)")
    print("  3. 📂 Organizar pastas (dividir >5000 arquivos, explodir grandes)")
    print("  4. 📋 Atualizar registro de pastas")
    print("  5. 🔙 Voltar")
    sub = input("👉 Opção: ").strip()
    log_atividade(f"Preparar dados: escolheu {sub}")
    if sub == "1":
        if perguntar_sim_nao("Deseja baixar todos os datasets? (pode levar horas)"):
            executar_comando_com_progresso(["python", "download_datasets.py"], "Baixando datasets", emoji="🌐")
            pausar()
        else:
            print("Fontes disponíveis:")
            fontes = ["blogset", "ultrachat", "tucano", "guara", "gigaverbo", "brwac"]
            for i, f in enumerate(fontes, 1):
                print(f"  {i}. {f}")
            escolha = input("👉 Escolha o número da fonte (ou nome): ").strip()
            if escolha.isdigit():
                idx = int(escolha) - 1
                if 0 <= idx < len(fontes):
                    fonte = fontes[idx]
                else:
                    print("❌ Número inválido.")
                    pausar()
                    return
            else:
                fonte = escolha
            if fonte:
                executar_comando_com_progresso(["python", "download_datasets.py", "--fonte", fonte], f"Baixando {fonte}", emoji="🌐")
                pausar()
    elif sub == "2":
        executar_comando_com_progresso(["python", "preparar_dados.py", "--qualificar"], "Qualificando dados", emoji="✅")
        pausar()
    elif sub == "3":
        executar_comando_com_progresso(["python", "organizar_pastas.py"], "Organizando pastas (limite 5000 arquivos e explode >30MB)", emoji="📂")
        pausar()
    elif sub == "4":
        executar_comando_com_progresso(["python", "organizar_pastas.py", "--apenas-registro"], "Atualizando registro", emoji="📋")
        pausar()
    elif sub == "5":
        return

def menu_gerenciar_dados():
    print("\n--- 🧹 GERENCIAR DADOS ---")
    print("  1. 🔧 Limpeza de codificação (utf-8)")
    print("  2. 📦 Agrupar arquivos pequenos em lotes")
    print("  3. 🔍 Validação de arquivos (listar inválidos)")
    print("  4. 🗑️  Remover arquivos inválidos")
    print("  5. 🔙 Voltar")
    sub = input("👉 Opção: ").strip()
    log_atividade(f"Gerenciar dados: escolheu {sub}")
    if sub == "1":
        entrada = input("📁 Pasta de entrada (default: dados/processed): ") or "dados/processed"
        saida = input("📁 Pasta de saída (default: dados/processed_corrigido): ") or "dados/processed_corrigido"
        executar_comando_com_progresso(["python", "limpeza.py", "--entrada", entrada, "--saida", saida], "Corrigindo codificação", emoji="🔧")
        pausar()
    elif sub == "2":
        entrada = input("📁 Pasta de entrada (default: dados/processed): ") or "dados/processed"
        saida = input("📁 Pasta de saída (default: dados/processed_lotes): ") or "dados/processed_lotes"
        backup = input("💾 Backup (opcional): ") or ""
        pares = input("📄 Pares por lote (default: 500): ") or "500"
        cmd = ["python", "agrupar.py", "--entrada", entrada, "--saida", saida, "--pares", pares]
        if backup:
            cmd.extend(["--backup", backup])
        executar_comando_com_progresso(cmd, "Agrupando arquivos", emoji="📦")
        pausar()
    elif sub == "3":
        executar_comando_com_progresso(["python", "preparar_dados.py", "--validar"], "Validando arquivos", emoji="🔍")
        pausar()
    elif sub == "4":
        if perguntar_sim_nao("Tem certeza que deseja remover arquivos inválidos?"):
            executar_comando_com_progresso(["python", "preparar_dados.py", "--limpar-invalidos"], "Removendo inválidos", emoji="🗑️")
            pausar()
    elif sub == "5":
        return

def menu_gerar_dados():
    print("\n--- ✨ GERAR DADOS SINTÉTICOS ---")
    print("  1. 💬 Diálogos v2 (22 tipos de conteúdo via API) [RECOMENDADO]")
    print("  2. 📰 RSS Processor (notícias)")
    print("  3. 🌐 Tradução de arquivos (inglês->português)")
    print("  4. 🔙 Voltar")
    sub = input("👉 Opção: ").strip()
    log_atividade(f"Gerar dados: escolheu {sub}")
    if sub == "1":
        qtd = input("📄 Quantidade (default: 200): ") or "200"
        print("Tipos disponíveis: auto, dicionario, pergunta_resposta, artigo, conto, dialogo_profundo, explicacao, resumo, conversa, poema, carta, entrevista, debate, tutorial, resenha, relatorio, ensaio, cronica, receita, dica")
        tipo = input("🎯 Tipo (default: auto): ") or "auto"
        executar_comando_com_progresso(["python", "dialogos2.py", "--quantidade", qtd, "--tipo", tipo], "Gerando diálogos v2", emoji="💬")
        pausar()
    elif sub == "2":
        qtd = input("📰 Notícias por feed (default: 10): ") or "10"
        executar_comando_com_progresso(["python", "rss_processor.py", "--quantidade", qtd], "Processando RSS", emoji="📰")
        pausar()
    elif sub == "3":
        entrada = input("📁 Pasta de entrada (arquivos em inglês): ").strip()
        saida = input("📁 Pasta de saída: ").strip()
        if entrada and saida:
            executar_comando_com_progresso(["python", "traduza.py", "--pasta", entrada, "--saida", saida], "Traduzindo", emoji="🌐")
            pausar()
    elif sub == "4":
        return

def menu_converter_ollama():
    print("\n--- 🔄 CONVERSÃO GGUF E OLLAMA ---")
    print("  1. 🔄 Converter modelo .pt para GGUF")
    print("  2. ▶️  Iniciar Ollama (com configuração CPU)")
    print("  3. 📦 Carregar modelo no Ollama (criar Modelfile)")
    print("  4. 📋 Listar modelos Ollama")
    print("  5. 💬 Testar chat com modelo local (chat.py)")
    print("  6. 📋 Comandos Ollama (executar pull, run, etc.)")
    print("  7. 🔙 Voltar")
    print("  8. 🔄 Reiniciar Ollama e carregar modelo (matar + iniciar + carregar)")
    sub = input("👉 Opção: ").strip()
    log_atividade(f"Conversão/Ollama: escolheu {sub}")
    if sub == "1":
        modelo_pt = input("📂 Arquivo .pt (default: modelo/modelo_melhor.pt): ") or "modelo/modelo_melhor.pt"
        print("\n⚙️ Opções de quantização:")
        print("  1. F16     - Sem quantização (maior qualidade, ~40 MB)")
        print("  2. Q8_0    - 8 bits (boa qualidade, ~20 MB)")
        print("  3. Q4_K_M  - 4 bits (recomendado, ótimo equilíbrio, ~15 MB)")
        print("  4. Q5_K_M  - 5 bits (qualidade excelente, ~18 MB)")
        escolha = input("👉 Escolha o número (1-4) [padrão: 3]: ").strip()
        quant_map = {"1": "F16", "2": "Q8_0", "3": "Q4_K_M", "4": "Q5_K_M"}
        quant = quant_map.get(escolha, "Q4_K_M")
        print(f"   ✅ Quantização selecionada: {quant}")
        executar_comando_com_progresso(["python", "converter_para_gguf.py", "--model", modelo_pt, "--quant", quant], "Convertendo para GGUF", emoji="🔄")
        pausar()
    elif sub == "2":
        if platform.system() == "Windows":
            if VENV_ACTIVATE.exists():
                cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(VENV_ACTIVATE), ";", "&", "iniciar_ollama.ps1"]
            else:
                cmd = ["powershell", "-File", "iniciar_ollama.ps1"]
        else:
            cmd = ["ollama", "serve"]
        executar_comando_com_progresso(cmd, "Iniciando Ollama", emoji="▶️")
        pausar()
    elif sub == "3":
        modelos = listar_modelos_ollama()
        if modelos:
            print("Modelos existentes no Ollama:")
            for i, m in enumerate(modelos, 1):
                print(f"  {i}. {m}")
        else:
            print("Nenhum modelo encontrado.")
        nome_modelo = input("🏷️  Nome do novo modelo no Ollama (ex: rigelslm): ").strip()
        if not nome_modelo:
            print("❌ Nome obrigatório.")
            pausar()
            return
        gguf = input("📂 Caminho do GGUF (ex: gguf/rigelslm_Q4_K_M.gguf): ").strip()
        if not gguf or not Path(gguf).exists():
            print("❌ Arquivo GGUF não encontrado.")
            pausar()
            return
        modelfile = f"""FROM {gguf}
TEMPLATE \"\"\"{{{{ .Prompt }}}}\"\"\"
PARAMETER temperature 0.7
PARAMETER top_p 0.9
"""
        with open("Modelfile", "w", encoding='utf-8') as f:
            f.write(modelfile)
        executar_comando_com_progresso(["ollama", "create", nome_modelo, "-f", "Modelfile"], f"Criando modelo {nome_modelo}", emoji="📦")
        os.remove("Modelfile")
        pausar()
    elif sub == "4":
        executar_comando_com_progresso(["ollama", "list"], "Modelos Ollama", emoji="📋")
        pausar()
    elif sub == "5":
        model = input("🤖 Modelo (default: rigelslm): ") or "rigelslm"
        executar_comando_com_progresso(["python", "chat.py", "--model", model], "Teste de chat", emoji="💬")
        pausar()
    elif sub == "6":
        exibir_comandos_ollama()
    elif sub == "7":
        return
    elif sub == "8":
        modelo = input("🤖 Nome do modelo para carregar (ex: llama3.2:1b): ").strip()
        if not modelo:
            print("❌ Nome do modelo obrigatório.")
            pausar()
            return
        reiniciar_ollama_com_modelo(modelo)
        pausar()

def menu_dashboard():
    print("\n--- 🖥️  DASHBOARD ---")
    print("  1. 🚀 Iniciar Dashboard (FastAPI)")
    print("  2. 🌐 Abrir navegador no Dashboard")
    print("  3. ⏹️  Parar Dashboard (forçar encerramento)")
    print("  4. 🔙 Voltar")
    sub = input("👉 Opção: ").strip()
    log_atividade(f"Dashboard: escolheu {sub}")
    if sub == "1":
        if not porta_livre(8000):
            print("⚠️ Porta 8000 já está em uso. Deseja encerrar o processo atual?")
            if perguntar_sim_nao("Encerrar processo na porta 8000?"):
                if platform.system() == "Windows":
                    print("   Executando: netstat -ano | findstr :8000")
                    result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, encoding='cp1252', errors='ignore')
                    if result.stdout:
                        linhas = [line for line in result.stdout.splitlines() if ":8000" in line and "LISTENING" in line]
                        if linhas:
                            for line in linhas:
                                partes = line.split()
                                if len(partes) >= 2:
                                    pid = partes[-1]
                                    print(f"   Matando processo PID {pid}")
                                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                        else:
                            print("   Nenhum processo encontrado na porta 8000.")
                    else:
                        print("   Nenhuma saída do netstat.")
                else:
                    subprocess.run(["fuser", "-k", "8000/tcp"])
                time.sleep(2)
            else:
                print("❌ Não é possível iniciar com porta ocupada.")
                pausar()
                return
        iniciar_dashboard()
        pausar("Servidor encerrado. Pressione Enter para voltar.")
    elif sub == "2":
        url = "http://127.0.0.1:8000"
        if porta_livre(8000):
            print("⚠️ O servidor não está em execução. Inicie-o primeiro (opção 1).")
            pausar()
            return
        try:
            webbrowser.open(url)
            print(f"🌐 Navegador aberto em {url}")
        except Exception as e:
            log_erro(f"Erro ao abrir navegador: {e}")
            log_atividade(f"Erro ao abrir navegador: {e}")
            print(f"🌐 Abra manualmente: {url}")
        pausar()
    elif sub == "3":
        print("⏹️  Parando Dashboard...")
        if platform.system() == "Windows":
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, encoding='cp1252', errors='ignore')
            if result.stdout:
                linhas = [line for line in result.stdout.splitlines() if ":8000" in line and "LISTENING" in line]
                if linhas:
                    for line in linhas:
                        partes = line.split()
                        if len(partes) >= 2:
                            pid = partes[-1]
                            print(f"   Matando processo PID {pid}")
                            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                else:
                    print("   Nenhum processo ouvindo na porta 8000.")
            else:
                print("   Nenhuma saída do netstat.")
        else:
            subprocess.run(["fuser", "-k", "8000/tcp"])
        print("✅ Comando de parada enviado.")
        pausar()
    elif sub == "4":
        return
    else:
        print("❌ Opção inválida.")
        pausar()

def menu_logs():
    print("\n--- 📊 LOGS E ESTATÍSTICAS ---")
    print("  1. 📜 Ver últimas execuções (historico)")
    print("  2. 📈 Ver métricas de treino")
    print("  3. 📂 Ver registro de pastas")
    print("  4. 📁 Ver logs de erro do Dashboard")
    print("  5. 📄 Ver log de atividades (verboso)")
    print("  6. 🔙 Voltar")
    sub = input("👉 Opção: ").strip()
    log_atividade(f"Logs: escolheu {sub}")
    if sub == "1":
        executar_comando_com_progresso(["python", "main.py", "--ver-logs"], "Histórico de execuções", emoji="📜")
        pausar()
    elif sub == "2":
        if Path("logs/metricas.json").exists():
            with open("logs/metricas.json", 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("📭 Nenhuma métrica encontrada.")
        pausar()
    elif sub == "3":
        if REGISTRO_PASTAS.exists():
            with open(REGISTRO_PASTAS, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print("📭 Registro de pastas não encontrado. Execute a organização primeiro.")
        pausar()
    elif sub == "4":
        if ARQUIVO_LOG_ERROS.exists():
            print(f"\n--- Conteúdo de {ARQUIVO_LOG_ERROS} ---")
            with open(ARQUIVO_LOG_ERROS, 'r', encoding='utf-8') as f:
                print(f.read())
        else:
            print("📭 Nenhum erro registrado ainda.")
        pausar()
    elif sub == "5":
        if ARQUIVO_LOG_ATIVIDADE.exists():
            print(f"\n--- Conteúdo de {ARQUIVO_LOG_ATIVIDADE} ---")
            with open(ARQUIVO_LOG_ATIVIDADE, 'r', encoding='utf-8') as f:
                print(f.read())
        else:
            print("📭 Nenhuma atividade registrada ainda.")
        pausar()
    elif sub == "6":
        return

def menu_configuracoes():
    print("\n--- 🛠️  CONFIGURAÇÕES DO AMBIENTE ---")
    print("  1. 🔍 Detectar hardware (CPU/GPU, memória)")
    print("  2. ⚙️ Configurar variáveis de ambiente (threads, memória)")
    print("  3. 📦 Configurar ambiente completo (setup_env.py)")
    print("  4. 🔙 Voltar")
    sub = input("👉 Opção: ").strip()
    log_atividade(f"Configurações: escolheu {sub}")
    if sub == "1":
        try:
            import psutil
            print(f"🖥️  CPU: {psutil.cpu_count()} núcleos ({psutil.cpu_count(logical=True)} lógicos)")
            mem = psutil.virtual_memory()
            print(f"💾 RAM: {mem.total // (1024**3)} GB total, {mem.available // (1024**3)} GB disponível")
        except ImportError:
            print("⚠️ Módulo psutil não instalado. Instale com: pip install psutil")
        if shutil.which("nvidia-smi"):
            print("🚀 GPU NVIDIA detectada.")
            try:
                result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True, encoding='utf-8')
                print(result.stdout.strip())
            except:
                pass
        else:
            print("ℹ️  Nenhuma GPU NVIDIA detectada.")
        pausar()
    elif sub == "2":
        threads = input("🧵 Número de threads para PyTorch (default: 16): ") or "16"
        os.environ["OMP_NUM_THREADS"] = threads
        os.environ["TORCH_NUM_THREADS"] = threads
        print(f"✅ Threads configuradas para {threads}")
        log_atividade(f"Threads configuradas para {threads}")
        pausar()
    elif sub == "3":
        configurar_ambiente()
    elif sub == "4":
        return

# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    if "VIRTUAL_ENV" not in os.environ:
        if VENV_ACTIVATE.exists():
            print("⚠️ Ambiente virtual não ativado. Ative com:")
            print(f"   . {VENV_ACTIVATE}")
        elif VENV_ACTIVATE_BAT.exists():
            print("⚠️ Ambiente virtual não ativado. Ative com:")
            print(f"   {VENV_ACTIVATE_BAT}")
    menu_principal()