#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
verificador.py - Módulo de diagnóstico e verificação do RigelSLM
Versão: 1.0.0 | Data: 31/07/2026
Responsável por:
  - Verificar serviços (Ollama, Web, APIs)
  - Manter estado persistente (estado_global.json)
  - Registrar histórico de eventos e erros
  - Ping real em serviços (não apenas checar processo)
"""
import os
import sys
import json
import subprocess
import time
import socket
import psutil
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================
PROJETO_DIR = Path(__file__).resolve().parent
ESTADO_GLOBAL_PATH = PROJETO_DIR / "estado_global.json"
LOG_DIR = PROJETO_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
HISTORICO_PATH = LOG_DIR / "historico_verificador.json"

# ============================================================================
# ESTADO GLOBAL PERSISTENTE
# ============================================================================

def _carregar_estado():
    """Carrega o estado global do arquivo JSON."""
    if ESTADO_GLOBAL_PATH.exists():
        try:
            return json.loads(ESTADO_GLOBAL_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return {}
    return {}

def _salvar_estado(estado):
    """Salva o estado global no arquivo JSON."""
    ESTADO_GLOBAL_PATH.write_text(
        json.dumps(estado, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

def iniciar_estado():
    """Inicializa o arquivo de estado global com estrutura padrão."""
    estado = _carregar_estado()
    if not estado:
        estado = {
            "versao": "1.0.0",
            "ultima_inicializacao": datetime.now().isoformat(),
            "ultima_alteracao": None,
            "servicos": {
                "ollama": {"status": "desconhecido", "ultimo_ping": None, "erro": None},
                "dashboard": {"status": "desconhecido", "ultimo_ping": None, "erro": None},
                "deepseek_api": {"status": "desconhecido", "ultimo_ping": None, "erro": None},
                "duckduckgo": {"status": "desconhecido", "ultimo_ping": None, "erro": None}
            },
            "geracao": {
                "ultimo_tipo": None,
                "total_gerados": 0,
                "topicos_usados": [],
                "ultimo_arquivo": None
            },
            "erros_recentes": [],
            "historico_inicializacoes": []
        }
    # Adiciona this initialization ao histórico
    if "historico_inicializacoes" not in estado:
        estado["historico_inicializacoes"] = []
    estado["historico_inicializacoes"].append({
        "data": datetime.now().isoformat(),
        "hostname": socket.gethostname(),
        "pid": os.getpid()
    })
    # Mantém só os últimos 20
    estado["historico_inicializacoes"] = estado["historico_inicializacoes"][-20:]
    estado["ultima_inicializacao"] = datetime.now().isoformat()
    _salvar_estado(estado)
    return estado

def atualizar_servico(servico, status, erro=None):
    """Atualiza o status de um serviço no estado global."""
    estado = _carregar_estado()
    if "servicos" not in estado:
        estado["servicos"] = {}
    estado["servicos"][servico] = {
        "status": status,
        "ultimo_ping": datetime.now().isoformat(),
        "erro": erro
    }
    _salvar_estado(estado)

def registrar_erro(tipo, mensagem, detalhes=None):
    """Registra um erro no estado global e no log."""
    estado = _carregar_estado()
    if "erros_recentes" not in estado:
        estado["erros_recentes"] = []
    erro = {
        "tipo": tipo,
        "mensagem": mensagem,
        "detalhes": detalhes,
        "data": datetime.now().isoformat()
    }
    estado["erros_recentes"].append(erro)
    # Mantém só os últimos 50
    estado["erros_recentes"] = estado["erros_recentes"][-50:]
    _salvar_estado(estado)
    # Também registra no log de erros
    log_path = LOG_DIR / "erros_verificador.log"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{erro['data']}] [{tipo}] {mensagem}")
        if detalhes:
            f.write(f" | {detalhes}")
        f.write("\n")
    return erro

def registrar_geracao(tipo, topico, arquivo):
    """Registra uma geração de conteúdo."""
    estado = _carregar_estado()
    if "geracao" not in estado:
        estado["geracao"] = {"total_gerados": 0, "topicos_usados": [], "ultimo_arquivo": None}
    estado["geracao"]["ultimo_tipo"] = tipo
    estado["geracao"]["total_gerados"] = estado["geracao"].get("total_gerados", 0) + 1
    topicos = estado["geracao"].get("topicos_usados", [])
    if topico not in topicos:
        topicos.append(topico)
    estado["geracao"]["topicos_usados"] = topicos[-100:]  # últimos 100 tópicos
    estado["geracao"]["ultimo_arquivo"] = arquivo
    estado["geracao"]["ultima_data"] = datetime.now().isoformat()
    _salvar_estado(estado)

def obter_estado():
    """Retorna o estado global atual."""
    return _carregar_estado()

# ============================================================================
# VERIFICAÇÕES DE SERVIÇOS (PING REAL)
# ============================================================================

def ping_ollama():
    """
    Ping real no Ollama: tenta conectar na porta 11434 e lista modelos.
    Retorna (True, modelo_ativo) ou (False, mensagem_erro).
    """
    # Teste 1: Socket na porta 11434
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', 11434))
        sock.close()
        if result != 0:
            atualizar_servico("ollama", "offline", "Porta 11434 não responde")
            return False, "Porta 11434 fechada"
    except Exception as e:
        atualizar_servico("ollama", "offline", str(e))
        return False, f"Erro socket: {e}"

    # Teste 2: HTTP request na API do Ollama (ping REAL)
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                modelos = [m["name"] for m in data.get("models", [])]
                modelo_ativo = modelos[0] if modelos else None
                atualizar_servico("ollama", "online")
                return True, modelo_ativo
            else:
                atualizar_servico("ollama", "erro", f"HTTP {resp.status}")
                return False, f"HTTP {resp.status}"
    except Exception as e:
        atualizar_servico("ollama", "offline", str(e))
        return False, f"API não responde: {e}"

def ping_dashboard():
    """
    Ping real no Dashboard: tenta acessar http://127.0.0.1:8000/.
    """
    try:
        import urllib.request
        req = urllib.request.Request("http://127.0.0.1:8000/", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                atualizar_servico("dashboard", "online")
                return True, "Online"
            else:
                atualizar_servico("dashboard", "erro", f"HTTP {resp.status}")
                return False, f"HTTP {resp.status}"
    except Exception as e:
        atualizar_servico("dashboard", "offline", str(e))
        return False, f"Offline: {e}"

def ping_deepseek_api():
    """
    Verifica se a API DeepSeek está configurada e responde.
    """
    try:
        from config import DEEPSEEK_API_KEY, API_BASE_URL
        if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "deepseek-aqui":
            atualizar_servico("deepseek_api", "nao_configurado")
            return False, "API Key não configurada"
        import urllib.request
        req = urllib.request.Request(
            f"{API_BASE_URL}/models",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                atualizar_servico("deepseek_api", "online")
                return True, "Online"
            else:
                atualizar_servico("deepseek_api", "erro", f"HTTP {resp.status}")
                return False, f"HTTP {resp.status}"
    except ImportError:
        atualizar_servico("deepseek_api", "nao_configurado", "config.py não encontrado")
        return False, "Módulo config.py não encontrado"
    except Exception as e:
        atualizar_servico("deepseek_api", "offline", str(e))
        return False, f"Erro: {e}"

def ping_duckduckgo():
    """
    Verifica se DuckDuckGo está acessível.
    """
    try:
        import httpx
        with httpx.Client(timeout=5) as client:
            resp = client.get("https://duckduckgo.com/")
            if resp.status_code == 200:
                atualizar_servico("duckduckgo", "online")
                return True, "Online"
            else:
                atualizar_servico("duckduckgo", "erro", f"HTTP {resp.status_code}")
                return False, f"HTTP {resp.status_code}"
    except ImportError:
        try:
            import urllib.request
            req = urllib.request.Request("https://duckduckgo.com/", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    atualizar_servico("duckduckgo", "online")
                    return True, "Online"
                else:
                    atualizar_servico("duckduckgo", "erro", f"HTTP {resp.status}")
                    return False, f"HTTP {resp.status}"
        except Exception as e:
            atualizar_servico("duckduckgo", "offline", str(e))
            return False, f"Offline: {e}"
    except Exception as e:
        atualizar_servico("duckduckgo", "offline", str(e))
        return False, f"Offline: {e}"

# ============================================================================
# VERIFICAÇÃO COMPLETA
# ============================================================================

def verificar_tudo(registrar_erros=True):
    """
    Executa todas as verificações e retorna um dicionário com resultados.
    Se registrar_erros=True, erros são registrados no estado global.
    """
    print("\n" + "=" * 60)
    print("   🔍 RIGELSLM - VERIFICAÇÃO DE SERVIÇOS")
    print("=" * 60)

    # Inicializa estado
    iniciar_estado()

    resultados = {}

    # 1. Ollama
    print("\n🦙 Ollama...", end=" ")
    try:
        ollama_ok, ollama_info = ping_ollama()
        resultados["ollama"] = {"ok": ollama_ok, "info": ollama_info}
        print(f"{'✅ Online' if ollama_ok else '❌ Offline'}" + (f" ({ollama_info})" if ollama_ok else f" - {ollama_info}"))
        if not ollama_ok and registrar_erros:
            registrar_erro("servico", f"Ollama offline: {ollama_info}")
    except Exception as e:
        resultados["ollama"] = {"ok": False, "info": str(e)}
        print(f"❌ Erro: {e}")

    # 2. Dashboard
    print("🌐 Dashboard...", end=" ")
    try:
        dash_ok, dash_info = ping_dashboard()
        resultados["dashboard"] = {"ok": dash_ok, "info": dash_info}
        print(f"{'✅ Online' if dash_ok else '❌ Offline'}" + (f" - {dash_info}" if not dash_ok else ""))
        if not dash_ok and registrar_erros:
            registrar_erro("servico", f"Dashboard offline: {dash_info}")
    except Exception as e:
        resultados["dashboard"] = {"ok": False, "info": str(e)}
        print(f"❌ Erro: {e}")

    # 3. DeepSeek API
    print("🔑 DeepSeek API...", end=" ")
    try:
        ds_ok, ds_info = ping_deepseek_api()
        resultados["deepseek"] = {"ok": ds_ok, "info": ds_info}
        print(f"{'✅ Online' if ds_ok else '⚠️ ' + ds_info}")
    except Exception as e:
        resultados["deepseek"] = {"ok": False, "info": str(e)}
        print(f"❌ Erro: {e}")

    # 4. DuckDuckGo
    print("🦆 DuckDuckGo...", end=" ")
    try:
        ddg_ok, ddg_info = ping_duckduckgo()
        resultados["duckduckgo"] = {"ok": ddg_ok, "info": ddg_info}
        print(f"{'✅ Online' if ddg_ok else '❌ Offline'}" + (f" - {ddg_info}" if not ddg_ok else ""))
    except Exception as e:
        resultados["duckduckgo"] = {"ok": False, "info": str(e)}
        print(f"❌ Erro: {e}")

    # 5. Disco
    print("💾 Disco...", end=" ")
    try:
        uso = psutil.disk_usage('/')
        pct = uso.percent
        livre_gb = uso.free / (1024**3)
        print(f"{pct}% usado ({livre_gb:.1f} GB livre)")
        if pct > 95:
            registrar_erro("disco", f"Disco quase cheio: {pct}% usado")
        resultados["disco"] = {"ok": pct < 95, "info": f"{pct}% usado, {livre_gb:.1f} GB livre"}
    except Exception as e:
        print(f"❌ Erro: {e}")
        resultados["disco"] = {"ok": False, "info": str(e)}

    # 6. Memória
    print("🧠 Memória...", end=" ")
    try:
        mem = psutil.virtual_memory()
        print(f"{mem.percent}% usado ({mem.available / (1024**3):.1f} GB disponível)")
        if mem.percent > 90:
            registrar_erro("memoria", f"Memória quase cheia: {mem.percent}%")
        resultados["memoria"] = {"ok": mem.percent < 90, "info": f"{mem.percent}% usado"}
    except Exception as e:
        print(f"❌ Erro: {e}")
        resultados["memoria"] = {"ok": False, "info": str(e)}

    # 7. Modelo .pt existe
    print("📦 Modelo .pt...", end=" ")
    modelo_path = PROJETO_DIR / "modelo" / "modelo_melhor.pt"
    if modelo_path.exists():
        tamanho = modelo_path.stat().st_size / (1024**2)
        data = datetime.fromtimestamp(modelo_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        print(f"✅ {tamanho:.0f} MB ({data})")
        resultados["modelo_pt"] = {"ok": True, "info": f"{tamanho:.0f} MB"}
    else:
        print("❌ Não encontrado")
        resultados["modelo_pt"] = {"ok": False, "info": "Não encontrado"}

    print("\n" + "=" * 60)
    print("   📊 VERIFICAÇÃO CONCLUÍDA")
    print("=" * 60)

    # Oferece soluções para serviços offline
    acoes = []
    if not resultados.get("ollama", {}).get("ok"):
        acoes.append("🦙 Ollama offline. Iniciar?")
    if not resultados.get("dashboard", {}).get("ok"):
        acoes.append("🌐 Dashboard offline. Iniciar?")
    if not resultados.get("deepseek", {}).get("ok"):
        acoes.append("🔑 DeepSeek API não configurada. Editar .env?")

    if acoes:
        print(f"\n💡 {len(acoes)} pendência(s) encontrada(s):")
        for i, desc in enumerate(acoes, 1):
            resp = input(f"   {i}. {desc} (S/N): ").strip().lower()
            if resp == 's':
                if "Ollama" in desc:
                    from verificador import iniciar_ollama as io
                    io()
                elif "Dashboard" in desc:
                    from verificador import iniciar_dashboard as idb
                    idb()
                elif "DeepSeek" in desc:
                    print("   📝 Edite o arquivo .env e configure DEEPSEEK_API_KEY")
                    print("   📖 Consulte INSTALL.md para mais detalhes.")

    return resultados

# ============================================================================
# FUNÇÕES PARA INICIAR SERVIÇOS AUTOMATICAMENTE
# ============================================================================

def iniciar_ollama():
    """Tenta iniciar o Ollama serve."""
    try:
        proc = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False
        )
        time.sleep(2)  # Aguarda inicialização
        ok, info = ping_ollama()
        if ok:
            print(f"✅ Ollama iniciado (PID {proc.pid})")
            return True
        else:
            print(f"❌ Ollama não respondeu após iniciar: {info}")
            return False
    except Exception as e:
        print(f"❌ Erro ao iniciar Ollama: {e}")
        return False

def iniciar_dashboard():
    """Tenta iniciar o servidor do dashboard."""
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "dashboard.main:app",
             "--host", "0.0.0.0", "--port", "8000", "--reload"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(PROJETO_DIR)
        )
        time.sleep(3)
        ok, info = ping_dashboard()
        if ok:
            print(f"✅ Dashboard iniciado (PID {proc.pid})")
            return True
        else:
            print(f"❌ Dashboard não respondeu após iniciar: {info}")
            return False
    except Exception as e:
        print(f"❌ Erro ao iniciar Dashboard: {e}")
        return False

# ============================================================================
# PONTO DE ENTRADA (quando chamado diretamente)
# ============================================================================

if __name__ == "__main__":
    verificar_tudo()
