"""Rota de Chat - Comunicação com modelo via Ollama (GGUF) ou PyTorch local."""
from fastapi import APIRouter, HTTPException
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

router = APIRouter(prefix="/api/chat", tags=["Chat"])

BASE_DIR = Path(__file__).parent.parent.parent
FEEDBACK_DIR = BASE_DIR / "dados" / "gerados" / "feedback_chat"
FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434"
MODELO_RIGEL = "rigelslm"
MODELO_FALLBACK = "llama3.1:8b"
GGUF_PATH = BASE_DIR / "gguf" / "rigelslm_Q4_K.gguf"
LOCAL_MODEL_PATH = BASE_DIR / "modelo" / "modelo_melhor.pt"
LOCAL_TOKENIZER_PATH = BASE_DIR / "tokenizer" / "tokenizer.json"

_ollama_cache = {"online": False, "modelo_ativo": None, "time": 0, "manual": False}

# Cache para o modelo local PyTorch
_local_model_cache = {"model": None, "tokenizer": None, "loaded": False, "time": 0}


class Mensagem(BaseModel):
    mensagem: str
    historico: list = []


class Feedback(BaseModel):
    mensagem: str
    resposta: str
    feedback: str  # "positivo" ou "negativo"


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

    # Auto-detecção: rigelslm > fallback > primeiro disponível
    modelo = None
    if MODELO_RIGEL in modelos or any(MODELO_RIGEL in m for m in modelos):
        modelo = MODELO_RIGEL
    elif MODELO_FALLBACK in modelos or any(MODELO_FALLBACK in m for m in modelos):
        modelo = MODELO_FALLBACK
    elif modelos:
        modelo = modelos[0]
    else:
        modelo = MODELO_FALLBACK

    _ollama_cache = {"online": True, "modelo_ativo": modelo, "time": now, "manual": False}
    return True


async def gerar_com_ollama(mensagem: str, historico: list):
    """Gera resposta usando a API do Ollama com o modelo detectado."""
    global _ollama_cache
    await verificar_ollama()
    modelo = _ollama_cache.get("modelo_ativo") or MODELO_FALLBACK

    nome_exibicao = "RigelSLM" if modelo == MODELO_RIGEL else modelo
    system_msg = f"Você é o {nome_exibicao}, um assistente de IA."

    messages = [{"role": "system", "content": system_msg}]

    # Adiciona histórico (últimas 6 trocas)
    for item in historico[-6:]:
        messages.append({"role": "user", "content": item.get("user", "")})
        if item.get("assistant"):
            messages.append({"role": "assistant", "content": item["assistant"]})

    messages.append({"role": "user", "content": mensagem})

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={"model": modelo, "messages": messages, "stream": True}
            ) as response:
                if response.status_code != 200:
                    erro_body = await response.aread()
                    yield f"\n\n❌ Ollama retornou erro {response.status_code}: {erro_body.decode()[:200]}"
                    return
                async for linha in response.aiter_lines():
                    if linha.strip():
                        try:
                            dados = json.loads(linha)
                            if "message" in dados:
                                yield dados["message"]["content"]
                            if "error" in dados:
                                yield f"\n\n❌ Erro do modelo: {dados['error']}"
                                return
                            if dados.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
    except httpx.TimeoutException:
        yield "\n\n❌ Tempo limite excedido (60s). O modelo pode estar ocupado."
    except httpx.ConnectError:
        yield "\n\n❌ Não foi possível conectar ao Ollama."
    except Exception as e:
        yield f"\n\n❌ Erro inesperado: {str(e)[:200]}"


async def _listar_modelos_ollama():
    """Lista todos os modelos disponíveis no Ollama."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


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


async def _gerar_local(mensagem: str, historico: list):
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
            temperature=0.8,
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
    """Status do serviço de chat (Ollama + modelo ativo + lista)."""
    global _ollama_cache
    await verificar_ollama()
    modelos_disponiveis = await _listar_modelos_ollama()
    gguf_existe = GGUF_PATH.exists()
    return {
        "ollama_online": _ollama_cache["online"],
        "modelo_ativo": _ollama_cache.get("modelo_ativo"),
        "modelos_disponiveis": modelos_disponiveis,
        "gguf_existe": gguf_existe,
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
    if modelo not in modelos:
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
    """Envia mensagem e recebe resposta do modelo."""
    ollama_ok = await verificar_ollama()

    if not ollama_ok:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "message": "Ollama não está rodando. Inicie com 'ollama serve'."}
        )

    return StreamingResponse(
        gerar_com_ollama(msg.mensagem, msg.historico),
        media_type="text/event-stream"
    )


@router.post("/feedback")
async def registrar_feedback(fb: Feedback):
    """Registra feedback positivo/negativo para treino futuro."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo = FEEDBACK_DIR / f"feedback_{timestamp}.json"

    dados = {
        "timestamp": datetime.now().isoformat(),
        "mensagem": fb.mensagem,
        "resposta": fb.resposta,
        "feedback": fb.feedback
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


@router.post("/salvar-conversa")
async def salvar_conversa(req: SalvarConversaRequest):
    """Salva a conversa atual em formato JSONL."""
    chats_dir = BASE_DIR / "dados" / "gerados" / "chatssalvos"
    chats_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo_jsonl = chats_dir / f"conversa_{timestamp}.jsonl"
    arquivo_txt = chats_dir / f"conversa_{timestamp}.txt"

    pares = 0
    with open(arquivo_jsonl, "w", encoding="utf-8") as f_jsonl, \
         open(arquivo_txt, "w", encoding="utf-8") as f_txt:

        for i in range(0, len(req.mensagens) - 1, 2):
            if req.mensagens[i]["role"] == "user" and req.mensagens[i+1]["role"] == "bot":
                pergunta = req.mensagens[i]["content"]
                resposta = req.mensagens[i+1]["content"]
                par = {
                    "pergunta": pergunta,
                    "resposta": resposta,
                    "timestamp": timestamp
                }
                f_jsonl.write(json.dumps(par, ensure_ascii=False) + "\n")
                f_txt.write(f"USER: {pergunta}\nASSISTANT: {resposta}\n\n---\n\n")
                pares += 1

    return {
        "status": "ok",
        "mensagem": f"Conversa salva: {pares} pares pergunta->resposta",
        "arquivo": f"chatssalvos/conversa_{timestamp}.jsonl",
        "total_pares": pares,
        "timestamp": datetime.now().isoformat()
    }
