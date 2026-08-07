#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
chat.py - Chat via Ollama + PyTorch local para o Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import json
import httpx
import asyncio
import subprocess
import sys
import os
from datetime import datetime
import uuid
from dashboard.services.pesquisa import pesquisar, pesquisar_com_fontes, verificar_disponivel, PESQUISA_SEMPRE_ATIVA
from dashboard.services.limpeza import limpar_e_aviso, corrigir_espacos_concatenados

router = APIRouter(prefix="/api/chat", tags=["Chat"])

BASE_DIR = Path(__file__).parent.parent.parent
FEEDBACK_DIR = BASE_DIR / "dados" / "gerados" / "feedback_chat"
FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434"
MODELO_RIGEL = "rigelslm"
MODELO_FALLBACK = "llama3.1:8b"
# Contexto do Ollama: modelo treinado com SEQ_LEN=512, mas a posição é
# sinusoidal (extrapola bem), então usamos 2048 p/ caber histórico + pesquisa
# sem estourar o default de 512 do Ollama.
NUM_CTX = 2048


def _eh_rigel(modelo):
    """True se o modelo é o Rigel (aceita 'rigelslm' ou 'rigelslm:latest').

    O `ollama create rigelslm` registra como 'rigelslm:latest', então comparar
    com o nome puro fazia o modelo recriado ser tratado como genérico.
    """
    return bool(modelo) and (modelo == MODELO_RIGEL or modelo.split(":")[0] == MODELO_RIGEL)


# GGUF mais recente disponível (o antigo rigelslm_Q4_K.gguf foi removido)
_GGUF_DIR = BASE_DIR / "gguf"
_GGUF_PATH = _GGUF_DIR / "rigelslm_Q4_K_M.gguf"
if not _GGUF_PATH.exists():
    _GGUF_PATH = _GGUF_DIR / "rigelslm_F16.gguf"
if not _GGUF_PATH.exists():
    _achados = sorted(_GGUF_DIR.glob("*.gguf"))
    if _achados:
        _GGUF_PATH = _achados[0]
GGUF_PATH = _GGUF_PATH
LOCAL_MODEL_PATH = BASE_DIR / "modelo" / "modelo_melhor.pt"
LOCAL_TOKENIZER_PATH = BASE_DIR / "tokenizer" / "tokenizer.json"

# ============================================================================
# llama.cpp (cppllama) — roda o GGUF do rigelslm que o Ollama não decodifica
# ============================================================================
# Pasta dos binários do llama.cpp, COPIADA para dentro do projeto (portátil).
# Sobrescrevível por env:
LLAMA_CPP_DIR = Path(os.getenv("LLAMA_CPP_DIR",
                               str(BASE_DIR / "llama" / "llama-b10199-bin-win-cpu-x64")))
LLAMA_SERVER_EXE = LLAMA_CPP_DIR / "llama-server.exe"
LLAMA_SERVER_PORT = int(os.getenv("LLAMA_SERVER_PORT", "8080"))
LLAMA_SERVER_URL = f"http://127.0.0.1:{LLAMA_SERVER_PORT}"

# GGUF preferido p/ o llama-server: Q8_0 > Q4_K_M > F16
_GGUF_PREFERENCIA = ("rigelslm_Q8_0.gguf", "rigelslm_Q4_K_M.gguf", "rigelslm_F16.gguf")
LLAMA_GGUF_PATH = None
for _nome in _GGUF_PREFERENCIA:
    _cand = _GGUF_DIR / _nome
    if _cand.exists():
        LLAMA_GGUF_PATH = _cand
        break
if LLAMA_GGUF_PATH is None:
    _achados_ll = sorted(_GGUF_DIR.glob("*.gguf"))
    if _achados_ll:
        LLAMA_GGUF_PATH = _achados_ll[0]

_llama_server_proc = {"proc": None, "pid": None}


def matar_llama_server_orfao() -> int:
    """Mata processos órfãos do llama-server.exe (nome EXATO — não toca em
    scripts/outros). Limpa a porta 8080 no início do dashboard e antes de
    subir um novo (evita zumbis acumulados de tentativas antigas)."""
    mortos = 0
    try:
        import psutil
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if (p.info.get("name") or "").lower() == "llama-server.exe":
                    psutil.Process(p.info["pid"]).terminate()
                    mortos += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                           capture_output=True, timeout=5)
    except Exception:
        pass
    return mortos


async def _verificar_llama_server() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{LLAMA_SERVER_URL}/health")
            return r.status_code == 200
    except Exception:
        return False


async def _iniciar_llama_server() -> bool:
    """Sobe o llama-server (binário do usuário) com o GGUF do rigelslm."""
    global _llama_server_proc
    if await _verificar_llama_server():
        return True
    # Limpa órfãos/zumbis que estejam segurando a porta 8080 (tentativas antigas)
    mortos = matar_llama_server_orfao()
    if mortos:
        print(f"[LLAMA] Limpos {mortos} llama-server órfão(s) da porta 8080")
        await asyncio.sleep(1.0)
    if not LLAMA_SERVER_EXE.exists() or LLAMA_GGUF_PATH is None:
        print(f"[LLAMA] indisponível: exe={LLAMA_SERVER_EXE.exists()}, gguf={LLAMA_GGUF_PATH}")
        return False
    cmd = [str(LLAMA_SERVER_EXE), "-m", str(LLAMA_GGUF_PATH),
           "--host", "127.0.0.1", "--port", str(LLAMA_SERVER_PORT),
           "--ctx-size", "2048"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=flags)
        _llama_server_proc = {"proc": proc, "pid": proc.pid}
        print(f"[LLAMA] llama-server iniciado (PID {proc.pid}, {LLAMA_GGUF_PATH.name})")
        for _ in range(60):  # até ~30s p/ carregar o modelo
            await asyncio.sleep(0.5)
            if await _verificar_llama_server():
                return True
        print("[LLAMA] llama-server não respondeu no tempo limite")
        return False
    except Exception as e:
        print(f"[LLAMA] erro ao iniciar: {e}")
        return False


async def _gerar_com_llama_server(mensagem: str, historico: list, temperatura: float = 0.7):
    """Gera via llama-server (API compatível OpenAI). Acumula o texto CRU e
    limpa o TEXTO COMPLETO (mesmo fix de espaços do streaming do Ollama)."""
    system = "Você é o RigelSLM, um assistente de IA treinado localmente."
    messages = [{"role": "system", "content": system}]
    for item in historico[-6:]:
        messages.append({"role": "user", "content": item.get("user", "")})
        if item.get("assistant"):
            messages.append({"role": "assistant", "content": item["assistant"]})
    messages.append({"role": "user", "content": mensagem})

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream(
                "POST", f"{LLAMA_SERVER_URL}/v1/chat/completions",
                json={"model": "rigelslm", "messages": messages, "stream": True,
                      "temperature": temperatura, "max_tokens": 200}
            ) as resp:
                if resp.status_code != 200:
                    corpo = await resp.aread()
                    yield f"\n\nllama-server erro {resp.status_code}: {corpo.decode(errors='replace')[:200]}"
                    return
                buffer = ""
                emitido = ""
                async for linha in resp.aiter_lines():
                    if not linha or not linha.startswith("data:"):
                        continue
                    dados = linha[5:].strip()
                    if dados == "[DONE]":
                        break
                    try:
                        obj = json.loads(dados)
                    except Exception:
                        continue
                    delta = obj.get("choices", [{}])[0].get("delta", {}) or {}
                    chave = delta.get("content")
                    if not chave:
                        continue
                    buffer += chave
                    corrigido = corrigir_espacos_concatenados(
                        limpar_e_aviso(buffer, "Chat Llama"))
                    if len(corrigido) > len(emitido):
                        yield corrigido[len(emitido):]
                        emitido = corrigido
    except Exception as e:
        yield f"\n\n❌ Erro no llama-server: {str(e)[:200]}"

_ollama_cache = {"online": False, "modelo_ativo": None, "time": 0, "manual": False}

# Cache para o modelo local PyTorch
_local_model_cache = {"model": None, "tokenizer": None, "loaded": False, "time": 0}

# Cache para status do buscador
_buscador_cache = {"online": False, "time": 0, "erro": None}

# Modelo preferido persistido — o rigelslm NÃO é priorizado; fica só na lista.
# A escolha do usuário é guardada aqui para sobreviver a reinícios.
_ESTADO_DIR_CHAT = BASE_DIR / "estado"
_MODELO_PREFERIDO_ARQ = _ESTADO_DIR_CHAT / "ollama_modelo_preferido.json"


def _modelo_preferido_salvar(modelo):
    try:
        _MODELO_PREFERIDO_ARQ.parent.mkdir(parents=True, exist_ok=True)
        _MODELO_PREFERIDO_ARQ.write_text(json.dumps({"modelo": modelo}), encoding="utf-8")
    except Exception:
        pass


def _modelo_preferido_carregar():
    try:
        if _MODELO_PREFERIDO_ARQ.exists():
            return json.loads(_MODELO_PREFERIDO_ARQ.read_text(encoding="utf-8")).get("modelo") or ""
    except Exception:
        pass
    return ""

# Buscadores disponíveis
BUSCADORES = {
    "duckduckgo": {
        "nome": "DuckDuckGo",
        "icone": "🦆",
        "descricao": "Gratuito, sem API key",
        "precisa_key": False
    }
}


class Mensagem(BaseModel):
    mensagem: str
    historico: list = []
    usar_pesquisa: bool = False
    search_api: str = "duckduckgo"
    temperatura: float = 0.7


class Feedback(BaseModel):
    mensagem: str
    resposta: str
    feedback: str  # "positivo" ou "negativo"
    fontes: list[str] = []   # fontes usadas na resposta (pesquisa web)
    topico: str = ""         # tema da conversa (opcional, p/ classificar no treino)


class ModeloRequest(BaseModel):
    modelo: str


async def verificar_ollama():
    """Verifica se o Ollama está rodando (cache 15s). Não sobrescreve seleção manual."""
    global _ollama_cache
    now = datetime.now().timestamp()
    if now - _ollama_cache["time"] < 15:
        return _ollama_cache["online"]

    manual = _ollama_cache.get("manual", False)
    modelo_manual = _ollama_cache.get("modelo_ativo") if manual else None

    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code != 200:
                raise Exception("status")
            data = resp.json()
            modelos = [m["name"] for m in data.get("models", [])]
    except Exception:
        _ollama_cache = {"online": False, "modelo_ativo": modelo_manual, "time": now, "manual": manual}
        return False

    # Se o usuário escolheu manualmente, mantém a escolha (se ainda existir)
    if manual and modelo_manual:
        if modelo_manual in modelos:
            _ollama_cache = {"online": True, "modelo_ativo": modelo_manual, "time": now, "manual": True}
            return True
        # Se o modelo manual não existe mais, cai pra auto-detecção
        manual = False

    # Auto-detecção: NÃO prioriza o rigelslm (ele fica só na lista de modelos).
    # Preferência: escolha persistida > fallback > modelos conhecidos > primeiro não-rigel.
    preferido = _modelo_preferido_carregar()
    if preferido and preferido in modelos:
        modelo = preferido
    else:
        modelo = ""
        for cand in [MODELO_FALLBACK, "llama3.2:3b", "llama3.2:1b", "gemma2:2b", "qwen2.5-coder:7b"]:
            if cand in modelos or any(cand in m for m in modelos):
                modelo = cand
                break
        if not modelo:
            naorigel = [m for m in modelos if not _eh_rigel(m)]
            modelo = (naorigel[0] if naorigel else modelos[0]) if modelos else MODELO_FALLBACK

    _ollama_cache = {"online": True, "modelo_ativo": modelo, "time": now, "manual": False}
    return True


async def _verificar_buscador():
    """Verifica se o DuckDuckGo está acessível (cache 60s)."""
    global _buscador_cache
    now = datetime.now().timestamp()
    if now - _buscador_cache["time"] < 60:
        return _buscador_cache["online"]

    try:
        online = await asyncio.to_thread(verificar_disponivel)
        _buscador_cache = {"online": online, "time": now, "erro": None if online else "Falha no teste"}
        return online
    except Exception as e:
        _buscador_cache = {"online": False, "time": now, "erro": str(e)[:100]}
        return False


async def gerar_com_ollama(mensagem: str, historico: list, usar_pesquisa: bool = False, search_api: str = "duckduckgo", temperatura: float = 0.7):
    """Gera resposta usando a API do Ollama com o modelo detectado."""
    global _ollama_cache
    await verificar_ollama()
    modelo = _ollama_cache.get("modelo_ativo") or MODELO_FALLBACK

    nome_exibicao = "RigelSLM" if _eh_rigel(modelo) else modelo
    system_msg = f"Você é o {nome_exibicao}, um assistente de IA."

    # Pesquisa na internet se ativado
    contexto_pesquisa = ""
    fontes_pesquisa: list = []
    if usar_pesquisa or PESQUISA_SEMPRE_ATIVA:
        print(f"[CHAT] 🔍 Pesquisa ativada para: {mensagem[:60]}...")
        contexto_pesquisa_sinc, fontes_pesquisa = await asyncio.to_thread(pesquisar_com_fontes, mensagem, 3)
        if contexto_pesquisa_sinc:
            contexto_pesquisa = f"\n\n--- Resultados da internet (DuckDuckGo) ---\n{contexto_pesquisa_sinc}\n"
            print(f"[CHAT] ✅ Pesquisa OK ({len(contexto_pesquisa)} chars, {len(fontes_pesquisa)} fontes)")
        else:
            fontes_pesquisa = []
            print(f"[CHAT] ⚠️ Pesquisa sem resultados ou falhou")

    messages = [{"role": "system", "content": system_msg}]

    # Adiciona histórico (últimas 6 trocas)
    for item in historico[-6:]:
        messages.append({"role": "user", "content": item.get("user", "")})
        if item.get("assistant"):
            messages.append({"role": "assistant", "content": item["assistant"]})

    # Se há contexto de pesquisa, insere antes da pergunta
    if contexto_pesquisa:
        prompt_final = f"Contexto atual da internet:\n{contexto_pesquisa}\n\nPergunta do usuário: {mensagem}"
    else:
        prompt_final = mensagem
    messages.append({"role": "user", "content": prompt_final})
    print(f"[CHAT] Prompt final (primeiros 200 chars): {prompt_final[:200]}")

    # 🔗 Fontes da pesquisa: token de controle que o frontend extrai do stream
    if fontes_pesquisa:
        yield "@@FONTES@@" + json.dumps(fontes_pesquisa, ensure_ascii=False) + "@@\n"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={"model": modelo, "messages": messages, "stream": True,
                      "options": {"num_ctx": NUM_CTX, "temperature": temperatura}}
            ) as response:
                if response.status_code != 200:
                    erro_body = await response.aread()
                    yield f"\n\nOllama retornou erro {response.status_code}: {erro_body.decode()[:200]}"
                    return
                # Acumula os chunks e corrige os espaços concatenados sobre o
                # TEXTO COMPLETO (por chunk isolado a heurística não funciona).
                buffer = ""
                emitido = ""
                async for linha in response.aiter_lines():
                    if linha.strip():
                        try:
                            dados = json.loads(linha)
                            if "message" in dados:
                                # Acumula o conteúdo CRU. NÃO limpar chunk a chunk:
                                # limpar/.strip() por chunk destrói os espaços entre
                                # palavras que chegam em chunks separados ("Boa",
                                # " noite", "!" → "Boanoite!"). Limpamos o TEXTO
                                # COMPLETO depois.
                                buffer += dados["message"]["content"]
                                corrigido = corrigir_espacos_concatenados(
                                    limpar_e_aviso(buffer, "Chat Ollama"))
                                if len(corrigido) > len(emitido):
                                    yield corrigido[len(emitido):]
                                    emitido = corrigido
                            if "error" in dados:
                                erro_texto = dados['error']
                                if isinstance(erro_texto, str):
                                    erro_texto = limpar_e_aviso(erro_texto, "Chat Ollama Error")
                                yield f"\n\nErro do modelo: {erro_texto}"
                                return
                            if dados.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
    except httpx.TimeoutException:
        yield "\n\nTempo limite excedido (60s). O modelo pode estar ocupado."
    except httpx.ConnectError:
        yield "\n\nNao foi possivel conectar ao Ollama."
    except Exception as e:
        yield f"\n\nErro inesperado: {str(e)[:200]}"


@router.get("/search-status")
async def search_status():
    """Status do serviço de busca na web."""
    online = await _verificar_buscador()
    buscadores = []
    for key, info in BUSCADORES.items():
        buscadores.append({
            "id": key,
            "nome": info["nome"],
            "icone": info["icone"],
            "descricao": info["descricao"],
            "precisa_key": info["precisa_key"]
        })
    return {
        "online": online,
        "erro": _buscador_cache.get("erro"),
        "buscadores": buscadores,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/search-apis")
async def search_apis():
    """Lista APIs de busca disponíveis."""
    online = await _verificar_buscador()
    apis = []
    for key, info in BUSCADORES.items():
        apis.append({
            "id": key,
            "nome": info["nome"],
            "icone": info["icone"],
            "descricao": info["descricao"],
            "online": online,
            "precisa_key": info["precisa_key"]
        })
    return {"apis": apis, "timestamp": datetime.now().isoformat()}


async def _listar_modelos_ollama():
    """Lista modelos do Ollama + o rigelslm via GGUF/llama.cpp (funciona offline)."""
    modelos = []
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                modelos = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass
    # Sempre inclui o rigelslm (servido pelo llama.cpp), mesmo com o Ollama offline
    if LLAMA_GGUF_PATH is not None:
        base = MODELO_RIGEL
        if not any(m == base or m.split(":")[0] == base for m in modelos):
            modelos.append(f"{base}:latest")
    return modelos


async def _detalhe_modelo_ollama(nome):
    """Detalhes (nome real, data, tamanho) do modelo no Ollama, ou None."""
    if not nome:
        return None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                base = nome.split(":")[0]
                for m in resp.json().get("models", []):
                    if m["name"] == nome or m["name"].split(":")[0] == base:
                        tamanho_mb = round(m.get("size", 0) / (1024 * 1024), 1)
                        data_txt = ""
                        mod = m.get("modified_at", "")
                        if mod:
                            try:
                                data_txt = datetime.fromisoformat(mod).strftime("%d/%m/%Y %H:%M")
                            except ValueError:
                                data_txt = mod[:10]
                        return {"nome": m["name"], "data": data_txt, "tamanho_mb": tamanho_mb}
    except Exception:
        pass
    return None


# ─── MODO LOCAL (PyTorch direto, sem Ollama) ───

async def _carregar_modelo_local():
    """Carrega o modelo PyTorch local (lazy, thread separada)."""
    global _local_model_cache
    if _local_model_cache["loaded"]:
        return _local_model_cache["model"], _local_model_cache["tokenizer"]

    if not LOCAL_MODEL_PATH.exists():
        return None, None
    if not LOCAL_TOKENIZER_PATH.exists():
        return None, None

    def _load():
        import torch
        sys.path.insert(0, str(BASE_DIR))
        from treino import RigelSLM, DISPOSITIVO
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(LOCAL_TOKENIZER_PATH))
        model = RigelSLM().to(DISPOSITIVO)

        state = torch.load(str(LOCAL_MODEL_PATH), map_location=DISPOSITIVO)
        model.load_state_dict(state)
        model.eval()
        return model, tokenizer

    try:
        model, tokenizer = await asyncio.to_thread(_load)
        _local_model_cache = {"model": model, "tokenizer": tokenizer, "loaded": True, "time": datetime.now().timestamp()}
        return model, tokenizer
    except Exception as e:
        print(f"[LOCAL MODEL] Erro ao carregar: {e}")
        return None, None


async def _gerar_local(mensagem: str, historico: list, temperatura: float = 0.7):
    """Gera resposta usando o modelo PyTorch local (via thread)."""
    model, tokenizer = await _carregar_modelo_local()
    if model is None:
        yield "❌ Modelo local não disponível. Treine o modelo primeiro."
        return

    # Monta histórico
    history_tuples = []
    for item in historico[-3:]:
        user_msg = item.get("user", "")
        bot_msg = item.get("assistant", "")
        if user_msg and bot_msg:
            history_tuples.append((user_msg, bot_msg))

    def _infer():
        prompt = mensagem
        # Reuse chat.py's gerar_resposta logic inline
        from treino import SEP_TOKEN

        context = ""
        for q, a in history_tuples:
            context += f"Pergunta: {q}\nResposta: {a}\n{SEP_TOKEN}\n"
        context += f"Pergunta: {prompt}\nResposta:"

        resposta = model.generate(
            tokenizer,
            context,
            max_new_tokens=200,
            temperature=temperatura,
            repetition_penalty=1.2,
            top_k=50
        )

        # Pós-processamento
        marker = "Resposta:"
        if marker in resposta:
            partes = resposta.split(marker)
            resposta = partes[-1].strip()
        if prompt in resposta:
            resposta = resposta.replace(prompt, "").strip()
        resposta = resposta.replace(SEP_TOKEN, "").strip()
        resposta = resposta.replace("[BOS]", "").strip()
        resposta = resposta.replace("[EOS]", "").strip()
        return resposta

    try:
        resposta = await asyncio.to_thread(_infer)
        resposta = limpar_e_aviso(resposta, "Chat Local")
        resposta = corrigir_espacos_concatenados(resposta)
        yield resposta
    except Exception as e:
        yield f"❌ Erro na geração local: {str(e)[:200]}"


@router.get("/local/status")
async def local_model_status():
    """Status do modelo local PyTorch."""
    model_path_exists = LOCAL_MODEL_PATH.exists()
    tokenizer_path_exists = LOCAL_TOKENIZER_PATH.exists()
    loaded = _local_model_cache["loaded"]

    model_size = f"{LOCAL_MODEL_PATH.stat().st_size / 1e6:.0f}MB" if model_path_exists else "N/A"
    model_date = datetime.fromtimestamp(LOCAL_MODEL_PATH.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if model_path_exists else "N/A"
    tokenizer_vocab = None
    if tokenizer_path_exists and loaded and _local_model_cache["tokenizer"]:
        try:
            tokenizer_vocab = _local_model_cache["tokenizer"].get_vocab_size()
        except Exception:
            pass

    return {
        "disponivel": model_path_exists and tokenizer_path_exists,
        "carregado": loaded,
        "modelo_path": str(LOCAL_MODEL_PATH),
        "modelo_tamanho": model_size,
        "modelo_data": model_date,
        "tokenizer_vocab": tokenizer_vocab,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/local/send")
async def send_local_message(msg: Mensagem):
    """Envia mensagem para o modelo PyTorch local (sem Ollama)."""
    if not LOCAL_MODEL_PATH.exists():
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": f"Modelo não encontrado em {LOCAL_MODEL_PATH}"}
        )

    return StreamingResponse(
        _gerar_local(msg.mensagem, msg.historico),
        media_type="text/event-stream"
    )


@router.get("/status")
async def chat_status():
    """Status do serviço de chat (Ollama + modelo ativo + lista + local)."""
    global _ollama_cache
    await verificar_ollama()
    modelos_disponiveis = await _listar_modelos_ollama()
    gguf_existe = GGUF_PATH.exists()
    
    # Verifica se o modelo local PyTorch está disponível
    local_modelo_path = LOCAL_MODEL_PATH.exists()
    local_tokenizer_path = LOCAL_TOKENIZER_PATH.exists()
    local_carregado = _local_model_cache["loaded"]
    
    modelo_ativo = _ollama_cache.get("modelo_ativo")
    modelo_detalhe = None
    modelo_base = ""
    if modelo_ativo:
        modelo_detalhe = await _detalhe_modelo_ollama(modelo_ativo)
        if _eh_rigel(modelo_ativo):
            try:
                from dashboard.services.converter_state import get_ollama_last_create
                _last = get_ollama_last_create()
                if _last and _last.get("gguf"):
                    modelo_base = _last["gguf"]
            except Exception:
                pass

    local_detalhe = None
    if LOCAL_MODEL_PATH.exists():
        try:
            _st = LOCAL_MODEL_PATH.stat()
            local_detalhe = {
                "nome": LOCAL_MODEL_PATH.name,
                "tamanho_mb": round(_st.st_size / (1024 * 1024), 1),
                "data": datetime.fromtimestamp(_st.st_mtime).strftime("%d/%m/%Y %H:%M"),
            }
            # Origem do modelo no manifesto (organização)
            _manifesto = BASE_DIR / "modelo" / "versoes.json"
            if _manifesto.exists():
                try:
                    _mv = json.loads(_manifesto.read_text(encoding="utf-8")).get("versoes", [])
                    for _v in _mv:
                        if _v.get("nome") == LOCAL_MODEL_PATH.name:
                            local_detalhe["origem"] = _v.get("treinador", "")
                            _est = _v.get("estado_treino")
                            if _est:
                                local_detalhe["epoch"] = _est.get("epoch")
                                local_detalhe["val_loss"] = _est.get("best_val_loss")
                            break
                except Exception:
                    pass
        except Exception:
            pass

    return {
        "ollama_online": _ollama_cache["online"],
        "modelo_ativo": modelo_ativo,
        "modelo_exibicao": ("RigelSLM" if _eh_rigel(modelo_ativo) else (modelo_ativo or "")),
        "eh_fallback": bool(modelo_ativo and (modelo_ativo == MODELO_FALLBACK or modelo_ativo.split(":")[0] == MODELO_FALLBACK.split(":")[0])),
        "modelo_detalhe": modelo_detalhe,
        "modelo_base": modelo_base,
        "local_detalhe": local_detalhe,
        "modelos_disponiveis": modelos_disponiveis,
        "gguf_existe": gguf_existe,
        "local_disponivel": local_modelo_path and local_tokenizer_path,
        "local_carregado": local_carregado,
        "modelo_rigel": MODELO_RIGEL,
        "modelo_fallback": MODELO_FALLBACK,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/set-model")
async def set_model(req: ModeloRequest):
    """Alterna o modelo ativo manualmente (descarrega o anterior)."""
    global _ollama_cache
    modelo = req.modelo
    modelos = await _listar_modelos_ollama()
    if not modelo:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Nome do modelo é obrigatório"})
    # rigelslm é servido pelo llama.cpp (GGUF) — não precisa existir no Ollama
    if modelo not in modelos and not _eh_rigel(modelo):
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Modelo '{modelo}' não encontrado no Ollama"})

    # Descarrega modelo anterior (keep_alive=0 força descarregar)
    modelo_anterior = _ollama_cache.get("modelo_ativo")
    if modelo_anterior and modelo_anterior != modelo:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{OLLAMA_URL}/api/generate",
                    json={"model": modelo_anterior, "prompt": "", "keep_alive": 0})
        except Exception:
            pass  # falha ao descarregar não é crítica

    _ollama_cache["modelo_ativo"] = modelo
    _ollama_cache["manual"] = True
    _ollama_cache["time"] = 0  # força refresh
    _modelo_preferido_salvar(modelo)  # lembra a escolha entre reinícios
    return {"status": "ok", "modelo_ativo": modelo, "timestamp": datetime.now().isoformat()}


@router.post("/delete-model")
async def delete_model(req: ModeloRequest):
    """Remove um modelo corrompido do Ollama."""
    modelo = req.modelo
    try:
        proc = await asyncio.create_subprocess_exec(
            "ollama", "rm", modelo,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            _ollama_cache["time"] = 0
            _ollama_cache["manual"] = False
            return {"status": "ok", "message": f"Modelo '{modelo}' removido", "timestamp": datetime.now().isoformat()}
        else:
            return JSONResponse(status_code=400, content={"status": "error", "message": stderr.decode().strip()[:200]})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)[:200]})


@router.post("/test")
async def test_modelo():
    """Testa se o modelo ativo responde (envia pergunta simples)."""
    global _ollama_cache
    await verificar_ollama()
    if not _ollama_cache["online"]:
        return JSONResponse(status_code=503, content={"status": "error", "message": "Ollama offline"})

    modelo = _ollama_cache.get("modelo_ativo") or MODELO_FALLBACK
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": modelo, "prompt": "Diga apenas 'OK' e mais nada.", "stream": False, "max_tokens": 10}
            )
            if resp.status_code == 200:
                data = resp.json()
                resposta = data.get("response", "").strip()
                return {
                    "status": "ok",
                    "modelo": modelo,
                    "resposta": resposta[:100],
                    "completo": bool(resposta),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "status": "error",
                    "modelo": modelo,
                    "erro": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    "timestamp": datetime.now().isoformat()
                }
    except Exception as e:
        return {
            "status": "error",
            "modelo": modelo,
            "erro": str(e)[:200],
            "timestamp": datetime.now().isoformat()
        }


@router.post("/send")
async def send_message(msg: Mensagem):
    """Envia mensagem e recebe resposta do modelo.
    
    Tenta primeiro Ollama. Se o modelo rigelslm estiver selecionado e falhar 
    (erro conhecido de compatibilidade GGUF), usa o modelo PyTorch local.
    """
    # Modelo ativo: seleção manual (cache) ou preferido persistido
    modelo_ollama = _ollama_cache.get("modelo_ativo", "") or _modelo_preferido_carregar() or ""

    # Verifica se o modelo local está disponível (é o caminho CONFIÁVEL do rigel:
    # o GGUF via llama-server/Ollama ainda não gera tokens — saída vazia)
    modelo_local, tokenizer_local = await _carregar_modelo_local()
    local_disponivel = modelo_local is not None

    # rigelslm: usa o modelo PyTorch local PRIMEIRO (funciona — testado via chat.py).
    # Só se não houver local, tenta o GGUF via llama-server (cppllama), que roda
    # mesmo com o Ollama offline.
    if _eh_rigel(modelo_ollama):
        if local_disponivel:
            print("[CHAT] 🟢 rigelslm via modelo PyTorch local (funciona)")
            return StreamingResponse(
                _gerar_local(msg.mensagem, msg.historico, msg.temperatura),
                media_type="text/event-stream"
            )
        if await _iniciar_llama_server():
            print("[CHAT] 🟢 rigelslm via llama-server (cppllama)")
            return StreamingResponse(
                _gerar_com_llama_server(msg.mensagem, msg.historico, msg.temperatura),
                media_type="text/event-stream"
            )
        print("[CHAT] ⚠️ sem local nem llama-server p/ rigel — caindo p/ Ollama")

    ollama_ok = await verificar_ollama()

    if not ollama_ok:
        # Ollama offline: tenta fallback local
        if local_disponivel:
            print("[CHAT] ⚠️ Ollama offline, usando modelo local")
            return StreamingResponse(
                _gerar_local(msg.mensagem, msg.historico, msg.temperatura),
                media_type="text/event-stream"
            )
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Nenhum modelo disponível. Inicie o Ollama ou treine o modelo local primeiro."}
        )

    # Testa rapidamente se o modelo do Ollama responde (evita streaming de erro)
    ollama_funciona = True

    if _eh_rigel(modelo_ollama):
        # Fallback: llama-server não subiu; testa o Ollama p/ o rigelslm
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                test_body = {"model": MODELO_RIGEL, "prompt": "test", "stream": False, "options": {"num_predict": 1}}
                resp = await client.post(f"{OLLAMA_URL}/api/generate", json=test_body)
                ollama_funciona = resp.status_code == 200
                if not ollama_funciona:
                    print(f"[CHAT] ⚠️ Ollama rigelslm falhou no teste: {resp.status_code}")
        except Exception as e:
            ollama_funciona = False
            print(f"[CHAT] ⚠️ Ollama rigelslm erro no teste: {e}")

    if not ollama_funciona and local_disponivel:
        # Fallback para modelo local
        print("[CHAT] ⚠️ Usando modelo local como fallback (Ollama incompatível com rigelslm)")
        return StreamingResponse(
            _gerar_local(msg.mensagem, msg.historico, msg.temperatura),
            media_type="text/event-stream"
        )

    # Ollama funcionando: usa normalmente
    return StreamingResponse(
        gerar_com_ollama(msg.mensagem, msg.historico, msg.usar_pesquisa, msg.search_api, msg.temperatura),
        media_type="text/event-stream"
    )


@router.post("/salvar")
async def salvar_conversa(request: Request):
    """Salva uma conversa do chat em arquivo de texto."""
    data = await request.json()
    texto = data.get("texto", "").strip()
    if not texto:
        return {"status": "erro", "mensagem": "Texto vazio"}

    pasta = BASE_DIR / "dados" / "gerados" / "chat_salvos"
    os.makedirs(pasta, exist_ok=True)
    nome = f"conversa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    caminho = os.path.join(str(pasta), nome)

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)

    print(f"[SALVAR] Conversa salva em: {caminho}")
    return {"status": "ok", "mensagem": f"✅ Conversa salva em {caminho}"}


@router.post("/feedback")
async def registrar_feedback(fb: Feedback):
    """Registra feedback positivo/negativo para treino futuro."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo = FEEDBACK_DIR / f"feedback_{timestamp}.json"

    dados = {
        "timestamp": datetime.now().isoformat(),
        "mensagem": fb.mensagem,
        "resposta": fb.resposta,
        "feedback": fb.feedback,
        "fontes": list(fb.fontes or []),
        "topico": (fb.topico or "").strip(),
    }

    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    # Se for negativo, salva também no log para revisão
    if fb.feedback == "negativo":
        log_dir = BASE_DIR / "logs"
        log_file = log_dir / "feedback_negativo.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] NEGATIVO | User: {fb.mensagem} | Modelo: {fb.resposta}\n")

    total_feedback = len(list(FEEDBACK_DIR.glob("feedback_*.json")))
    positivos = len(list(FEEDBACK_DIR.glob("feedback_*positivo*")))

    return {
        "status": "ok",
        "total_feedback": total_feedback,
        "taxa_aprovacao": f"{positivos / total_feedback * 100:.1f}%" if total_feedback > 0 else "0%"
    }


@router.get("/feedback/estatisticas")
async def estatisticas_feedback():
    """Estatísticas dos feedbacks coletados."""
    arquivos = list(FEEDBACK_DIR.glob("feedback_*.json"))
    positivos = sum(1 for a in arquivos if "positivo" in a.name)
    negativos = sum(1 for a in arquivos if "negativo" in a.name)
    total = len(arquivos)

    return {
        "total": total,
        "positivos": positivos,
        "negativos": negativos,
        "taxa_aprovacao": f"{positivos / total * 100:.1f}%" if total > 0 else "0%"
    }


class SalvarConversaRequest(BaseModel):
    mensagens: list[dict]
    topico: str = ""          # tema da conversa (classificação p/ treino)
    personalidade: bool = True  # usa o SYSTEM_PROMPT do Rigel no exemplo


@router.post("/salvar-conversa")
async def salvar_conversa_sft(req: SalvarConversaRequest):
    """Salva a conversa no formato IDEAL p/ treino: jsonl SFT messages.

    Cada par pergunta->resposta vira:
      {"messages": [system(Rigel/personalidade), user, assistant],
       "topico": ..., "fonte": "chat", "data": ...}
    Respostas muito curtas (< 5 palavras) são descartadas (contadas em
    'descartados') — filtro básico de QUALIDADE. O arquivo pode ser tratado
    depois pelo fluxo de sanitização (Tratamento) se quiser.
    """
    from saida_manager import SYSTEM_PROMPT
    chats_dir = BASE_DIR / "dados" / "gerados" / "jsonl" / "chat_salvos"
    chats_dir.mkdir(parents=True, exist_ok=True)
    txt_dir = BASE_DIR / "dados" / "gerados" / "chatssalvos"
    txt_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo_jsonl = chats_dir / f"conversa_{timestamp}.jsonl"
    arquivo_txt = txt_dir / f"conversa_{timestamp}.txt"

    topico = (req.topico or "").strip() or "geral"
    sistema = SYSTEM_PROMPT if req.personalidade else None
    pares = 0
    descartados = 0
    with open(arquivo_jsonl, "w", encoding="utf-8") as f_jsonl, \
         open(arquivo_txt, "w", encoding="utf-8") as f_txt:

        # Loop robusto: aceita "assistant" ou "bot" como papel do modelo.
        # O frontend envia "assistant"; antes só aceitava "bot" e salvava 0 pares.
        n = len(req.mensagens)
        i = 0
        while i < n:
            papel = (req.mensagens[i].get("role") or "").lower()
            if papel == "user":
                pergunta = (req.mensagens[i].get("content") or "").strip()
                # Procura a próxima resposta (assistant/bot), ignorando "system"
                resposta = ""
                j = i + 1
                while j < n:
                    r_papel = (req.mensagens[j].get("role") or "").lower()
                    if r_papel in ("assistant", "bot"):
                        resposta = (req.mensagens[j].get("content") or "").strip()
                        break
                    if r_papel == "user":
                        break  # novo user sem resposta anterior
                    j += 1
                if not pergunta or not resposta or len(resposta.split()) < 5:
                    descartados += 1
                else:
                    ex = {
                        "messages": [
                            {"role": "system", "content": sistema},
                            {"role": "user", "content": pergunta},
                            {"role": "assistant", "content": resposta},
                        ],
                        "topico": topico,
                        "fonte": "chat",
                        "data": datetime.now().isoformat(),
                    }
                    f_jsonl.write(json.dumps(ex, ensure_ascii=False) + "\n")
                    f_txt.write(f"USER: {pergunta}\nASSISTANT: {resposta}\n\n---\n\n")
                    pares += 1
            i += 1

    return {
        "status": "ok",
        "mensagem": (f"Conversa salva: {pares} pares (SFT messages, tópico "
                     f"'{topico}', personalidade {'✓' if req.personalidade else '✗'})"),
        "arquivo": f"dados/gerados/jsonl/chat_salvos/conversa_{timestamp}.jsonl",
        "total_pares": pares,
        "descartados": descartados,
        "topico": topico,
        "personalidade": bool(req.personalidade),
        "timestamp": datetime.now().isoformat()
    }
