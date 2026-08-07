"""Rota de Diagnóstico - Mostra o estado REAL de cada serviço"""
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
diagnostico.py - Diagnóstico completo do sistema RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
from fastapi import APIRouter
from pathlib import Path
from datetime import datetime
import json
import os
import urllib.request

router = APIRouter(prefix="/api/diagnostico", tags=["Diagnóstico"])

BASE_DIR = Path(__file__).parent.parent.parent


@router.get("/completo")
async def diagnostico_completo():
    """Diagnóstico completo: mostra o que está funcionando ou não."""
    agora = datetime.now()

    # ========== PROCESSADOS ==========
    # ⚠️ NUNCA escanear dados/processed com glob("*.txt") — são ~12,9 MILHÕES de
    # arquivos; isso trava o event loop (rota async) e o dashboard fica mudo
    # ("failed to fetch"). Usa o cache persistido do escaneador em background
    # (logs/estrutura_cache/estrutura_txt.json), que já tem a contagem por pasta.
    total_pastas = 0
    total_arquivos_processed = 0
    pastas_info = []
    try:
        cache_txt = json.loads(
            (BASE_DIR / "logs" / "estrutura_cache" / "estrutura_txt.json")
            .read_text(encoding="utf-8"))
        for p in cache_txt.get("resultado", []):
            arq = int(p.get("arquivos", 0) or 0)
            if arq > 0:
                total_pastas += 1
                total_arquivos_processed += arq
                pastas_info.append({"pasta": p.get("nome"), "arquivos": arq})
    except Exception as _e:
        try:
            with open(BASE_DIR / "logs" / "diag_erro.log", "a", encoding="utf-8") as _f:
                _f.write(f"[{datetime.now().isoformat()}] cache estrutura_txt: {type(_e).__name__}: {_e}\n")
        except Exception:
            pass

    # ========== GERADOS (RSS, diálogos, etc) ==========
    # Contagem LEVE por subpasta (scandir, 1º nível, teto 20k) — sem recursão.
    gerados_stats = {}
    total_gerados = 0
    gerados_dir = BASE_DIR / "dados" / "gerados"
    if gerados_dir.exists():
        try:
            with os.scandir(gerados_dir) as it:
                for item in it:
                    if item.is_dir() and item.name not in ("logs", "estado", "feedback_chat"):
                        qtde = 0
                        try:
                            with os.scandir(item.path) as it2:
                                for _ in it2:
                                    qtde += 1
                                    if qtde > 20000:
                                        break
                        except Exception:
                            pass
                        if qtde > 0:
                            gerados_stats[item.name] = qtde
                            total_gerados += qtde
        except Exception:
            pass

    # ========== MODELOS ==========
    modelo_dir = BASE_DIR / "modelo"
    modelos_pt = []
    if modelo_dir.exists():
        for f in ["modelo.pt", "modelo_melhor.pt", "checkpoint.pt"]:
            p = modelo_dir / f
            if p.exists():
                modelos_pt.append({
                    "arquivo": f,
                    "tamanho_mb": round(p.stat().st_size / (1024 * 1024), 1),
                    "data": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                })

    # ========== GGUF ==========
    gguf_dir = BASE_DIR / "gguf"
    ggufs = []
    if gguf_dir.exists():
        for f in gguf_dir.glob("*.gguf"):
            ggufs.append({
                "arquivo": f.name,
                "tamanho_mb": round(f.stat().st_size / (1024 * 1024), 1)
            })

    # ========== LOGS ==========
    logs_dir = BASE_DIR / "logs"
    logs_info = []
    if logs_dir.exists():
        for f in sorted(logs_dir.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
            logs_info.append({
                "arquivo": f.name,
                "tamanho_kb": round(f.stat().st_size / 1024, 1),
                "ultima_mod": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            })

    # ========== RSS LOG ==========
    rss_log = BASE_DIR / "dados" / "gerados" / "logs" / "rss.log"
    rss_ultimas_linhas = ""
    if rss_log.exists():
        try:
            with open(rss_log, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                rss_ultimas_linhas = "".join(lines[-20:])
        except Exception:
            rss_ultimas_linhas = "[erro ao ler]"

    # ========== PROCESSADOS.TXT (RSS) ==========
    proc_txt = BASE_DIR / "processados.txt"
    total_processados_rss = 0
    if proc_txt.exists():
        try:
            with open(proc_txt, "r", encoding="utf-8") as f:
                total_processados_rss = len([l for l in f.readlines() if l.strip()])
        except Exception:
            pass

    # ========== FEEDS ==========
    feeds_txt = BASE_DIR / "feeds.txt"
    total_feeds = 0
    if feeds_txt.exists():
        try:
            with open(feeds_txt, "r", encoding="utf-8") as f:
                total_feeds = len([l for l in f.readlines() if l.strip() and not l.strip().startswith("#")])
        except Exception:
            pass

    # ========== DEEPSEEK API ==========
    deepseek_ok = False
    deepseek_detalhe = "Não configurada"
    try:
        from config import API_KEY, DEEPSEEK_MODEL, API_BASE_URL
        chave = API_KEY or os.environ.get("DEEPSEEK_API_KEY", "")
        if chave and chave != "deepseek-aqui" and len(chave) > 10:
            deepseek_ok = True
            deepseek_detalhe = f"API Key configurada ({chave[:8]}...{chave[-4:]}, modelo: {DEEPSEEK_MODEL})"
        elif chave:
            deepseek_detalhe = "API Key parece inválida (muito curta ou placeholder)"
        else:
            deepseek_detalhe = "API Key não encontrada no .env"
    except ImportError:
        deepseek_detalhe = "config.py não encontrado"
    except Exception as e:
        deepseek_detalhe = f"Erro: {e}"

    # ========== OLLAMA (teste real) ==========
    ollama_ok = False
    ollama_detalhe = "Offline"
    ollama_modelo = None
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', 11434))
        sock.close()
        if result == 0:
            req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    modelos = [m["name"] for m in data.get("models", [])]
                    ollama_modelo = modelos[0] if modelos else None
                    ollama_ok = True
                    ollama_detalhe = f"Online ({len(modelos)} modelos)"
                    if ollama_modelo:
                        ollama_detalhe += f", ativo: {ollama_modelo}"
    except Exception as e:
        ollama_detalhe = f"Erro: {e}"

    # ========== DISCO ==========
    disco_ok = False
    disco_detalhe = ""
    try:
        import psutil
        uso = psutil.disk_usage('/')
        livre_gb = uso.free / (1024**3)
        pct = uso.percent
        disco_ok = livre_gb > 10
        disco_detalhe = f"{pct:.1f}% usado ({livre_gb:.1f} GB livre)"
        if not disco_ok:
            disco_detalhe += " ⚠️ MENOS DE 10 GB!"
    except Exception as e:
        disco_detalhe = f"Erro: {e}"

    # ========== CHECKPOINT INTEGRIDADE ==========
    # Verificação LEVE: não carrega o tensor (torch.load de 222-665 MB em rota
    # async travava o event loop). Checa tamanho + cabeçalho pickle do .pt.
    checkpoint_ok = False
    checkpoint_detalhe = "Nenhum checkpoint"
    for ckpt in ["modelo_melhor.pt", "checkpoint.pt", "modelo.pt"]:
        ckpt_path = BASE_DIR / "modelo" / ckpt
        if ckpt_path.exists():
            try:
                tam = ckpt_path.stat().st_size
                with open(ckpt_path, "rb") as fh:
                    cab = fh.read(2)
                # pickle (protocol 2+ = 0x80), dict literal ('{'/'(') ou ZIP
                # (torch.save novo salva como PK\x03\x04 = b"P")
                ok_formato = tam > 1024 and cab[:1] in (b"\x80", b"{", b"(", b"P")
                if ok_formato:
                    checkpoint_ok = True
                    checkpoint_detalhe = f"{ckpt}: {round(tam/1024/1024, 1)} MB, cabeçalho OK"
                else:
                    checkpoint_detalhe = f"{ckpt}: formato inesperado ({tam} bytes)"
                break
            except Exception as e:
                checkpoint_detalhe = f"{ckpt}: erro ao ler - {e}"
                break

    # ========== DIAGNÓSTICOS ==========
    diagnosticos = []

    # Diagnóstico: Processados
    if total_arquivos_processed > 0:
        diagnosticos.append({"tipo": "✅", "servico": "Dados processados", "detalhe": f"{total_arquivos_processed} arquivos em {total_pastas} pastas"})
    else:
        diagnosticos.append({"tipo": "❌", "servico": "Dados processados", "detalhe": "Nenhum arquivo processado encontrado"})

    # Diagnóstico: Gerados
    if total_gerados > 0:
        diagnosticos.append({"tipo": "✅", "servico": "Dados gerados", "detalhe": f"{total_gerados} arquivos em {len(gerados_stats)} categorias"})
    else:
        diagnosticos.append({"tipo": "⚠️", "servico": "Dados gerados (RSS/diálogos)", "detalhe": "Nenhum arquivo gerado. Execute RSS ou Geração de Dados primeiro."})

    # Diagnóstico: RSS
    if total_processados_rss > 0 and total_gerados == 0:
        diagnosticos.append({"tipo": "⚠️", "servico": "RSS", "detalhe": f"{total_processados_rss} sites já processados, mas 0 arquivos salvos. Script pode estar falhando."})
    elif total_feeds > 0:
        diagnosticos.append({"tipo": "🔄", "servico": "RSS", "detalhe": f"{total_feeds} feeds configurados, {total_processados_rss} já processados"})
    else:
        diagnosticos.append({"tipo": "❌", "servico": "RSS", "detalhe": "Nenhum feed configurado em feeds.txt"})

    # Diagnóstico: Modelo
    if modelos_pt:
        diagnosticos.append({"tipo": "✅", "servico": "Modelo PyTorch", "detalhe": f"{len(modelos_pt)} modelo(s) disponível(is)"})
    else:
        diagnosticos.append({"tipo": "❌", "servico": "Modelo PyTorch", "detalhe": "Nenhum modelo .pt em modelo/"})

    # Diagnóstico: GGUF
    if ggufs:
        diagnosticos.append({"tipo": "✅", "servico": "GGUF", "detalhe": f"{ggufs[0]['arquivo']} ({ggufs[0]['tamanho_mb']} MB)"})
    else:
        diagnosticos.append({"tipo": "❌", "servico": "GGUF", "detalhe": "Nenhum GGUF convertido"})

    # Diagnóstico: Treino recente
    metricas_path = BASE_DIR / "logs" / "metricas.json"
    if metricas_path.exists():
        try:
            data = json.loads(metricas_path.read_text(encoding="utf-8"))
            historico = data.get("historico", [])
            if historico:
                ultima = historico[-1]
                diagnosticos.append({"tipo": "📊", "servico": "Último treino", "detalhe": f"Época {ultima.get('epoch','?')}, loss {ultima.get('val_loss','?'):.4f}, em {ultima.get('data','?')}"})
            else:
                diagnosticos.append({"tipo": "⚠️", "servico": "Último treino", "detalhe": "Métricas vazias"})
        except Exception:
            diagnosticos.append({"tipo": "⚠️", "servico": "Último treino", "detalhe": "Erro ao ler métricas"})
    else:
        diagnosticos.append({"tipo": "❌", "servico": "Último treino", "detalhe": "Nenhuma métrica de treino encontrada"})

    # Diagnóstico: DeepSeek API
    if deepseek_ok:
        diagnosticos.append({"tipo": "✅", "servico": "DeepSeek API", "detalhe": deepseek_detalhe})
    else:
        diagnosticos.append({"tipo": "⚠️" if "não configurada" in deepseek_detalhe else "❌", "servico": "DeepSeek API", "detalhe": deepseek_detalhe})

    # Diagnóstico: Ollama
    if ollama_ok:
        diagnosticos.append({"tipo": "✅", "servico": "Ollama", "detalhe": ollama_detalhe})
    else:
        diagnosticos.append({"tipo": "❌", "servico": "Ollama", "detalhe": ollama_detalhe})

    # Diagnóstico: Disco
    if disco_ok:
        diagnosticos.append({"tipo": "✅", "servico": "Espaço em disco", "detalhe": disco_detalhe})
    else:
        diagnosticos.append({"tipo": "🔴", "servico": "Espaço em disco", "detalhe": disco_detalhe})

    # Diagnóstico: Checkpoint
    if checkpoint_ok:
        diagnosticos.append({"tipo": "✅", "servico": "Checkpoint", "detalhe": checkpoint_detalhe})
    else:
        diagnosticos.append({"tipo": "❌", "servico": "Checkpoint", "detalhe": checkpoint_detalhe})

    return {
        "timestamp": agora.isoformat(),
        "diagnosticos": diagnosticos,
        "resumo": {
            "arquivos_processed": total_arquivos_processed,
            "pastas_processed": total_pastas,
            "arquivos_gerados": total_gerados,
            "modelos_pt": len(modelos_pt),
            "ggufs": len(ggufs),
            "feeds_configurados": total_feeds,
            "sites_processados_rss": total_processados_rss,
        },
        "logs_recentes": logs_info[:5],
        "rss_ultimo_log": rss_ultimas_linhas[:1000],
    }
