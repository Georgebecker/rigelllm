#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
local_generate.py - Geração local com Ollama (templates) para o Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
import json
import httpx
import asyncio
from datetime import datetime
import uuid
import time

router = APIRouter(prefix="/api/local-generate", tags=["Geração Local"])

BASE_DIR = Path(__file__).parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
OLLAMA_URL = "http://localhost:11434"

# ─── Serviço de Pesquisa Web ───
from dashboard.services.pesquisa import pesquisar, verificar_disponivel, PESQUISA_SEMPRE_ATIVA
from dashboard.services.limpeza import limpar_e_aviso
_ddgs_available = verificar_disponivel()


@router.get("/pesquisa-status")
def pesquisa_status():
    """Retorna se a pesquisa web está disponível."""
    return {"disponivel": verificar_disponivel()}


# ─── Fonte de temas: categories.py (categorias/amostra) + RSS ───

@router.get("/categorias")
def listar_categorias_gerador():
    """Lista as categorias do categories.py com contagem de assuntos (seletor)."""
    try:
        from dashboard.services.gerador_categorias import listar_categorias, contar_assuntos
        return {"categorias": listar_categorias(), "total": contar_assuntos()}
    except Exception as e:
        return JSONResponse({"erro": str(e)}, status_code=500)


@router.get("/categorias/amostra")
def amostra_categorias_gerador(categoria: str = "", n: int = 5):
    """Amostra de perguntas de uma categoria (prévia no dashboard)."""
    try:
        from dashboard.services.gerador_categorias import amostra_perguntas, listar_categorias
        n = max(1, min(int(n or 5), 20))
        if categoria:
            return {"categoria": categoria, "perguntas": amostra_perguntas(categoria, n)}
        # sem categoria: amostra de várias categorias
        out = []
        for c in listar_categorias()[:8]:
            for p in amostra_perguntas(c["id"], 2):
                out.append(p)
        return {"categoria": "", "perguntas": out}
    except Exception as e:
        return JSONResponse({"erro": str(e)}, status_code=500)


@router.get("/rss-titulos")
def listar_titulos_rss(limite: int = 50, forcar: bool = False):
    """Títulos RSS disponíveis (cache 6h ou fetch ao vivo) p/ o modo 📰."""
    try:
        from dashboard.services.gerador_categorias import carregar_titulos_rss
        titulos = carregar_titulos_rss(limite=None, forcar=bool(forcar))
        return {"titulos": titulos[:limite] if limite else titulos, "total": len(titulos)}
    except Exception as e:
        return JSONResponse({"erro": str(e)}, status_code=500)


# ─── Auto-Filtro de Qualidade ───

PALAVRAS_INVENTADAS = [
    "como IA", "como inteligência artificial", "enquanto IA", "sou uma IA", "sou um assistente",
    "como assistente", "como modelo de linguagem", "enquanto modelo", "não tenho opinião",
    "não posso afirmar", "não tenho certeza", "de acordo com minha base", "conforme meu treinamento",
]
PALAVRAS_EXAGERO = [
    "revolucionário", "mudou tudo", "completamente novo", "nunca antes visto",
    "absolutamente", "perfeito", "incrível", "fantástico", "milagroso",
    "o melhor de todos", "totalmente", "extremamente",
]
PALAVRAS_NAO_FACTUAIS = [
    "provavelmente", "talvez", "possivelmente", "pode ser que",
    "acredita-se que", "dizem que", "reza a lenda",
]


def _auto_avaliar_qualidade(texto: str) -> dict:
    """Avalia a qualidade do texto gerado e retorna se deve ser aprovado ou rejeitado."""
    resultado = {
        "aprovado": True,
        "motivos": [],
        "score": 100,
        "tamanho_chars": len(texto),
        "tamanho_palavras": len(texto.split()),
    }

    texto_lower = texto.lower()

    # 1. Verifica se o texto parece inventado (fala sobre si mesmo como IA)
    for palavra in PALAVRAS_INVENTADAS:
        if palavra in texto_lower:
            resultado["aprovado"] = False
            resultado["motivos"].append(f"💬 Auto-referência como IA: '{palavra}'")
            resultado["score"] -= 30
            break

    # 2. Verifica exageros
    exageros_encontrados = [p for p in PALAVRAS_EXAGERO if p in texto_lower]
    if exageros_encontrados:
        resultado["motivos"].append(f"⚠️ Exagero detectado: {', '.join(exageros_encontrados[:3])}")
        resultado["score"] -= 15 * len(exageros_encontrados)

    # 3. Verifica linguagem não factual / duvidosa
    duvidosos = [p for p in PALAVRAS_NAO_FACTUAIS if p in texto_lower]
    if duvidosos:
        resultado["motivos"].append(f"❓ Linguagem duvidosa: {', '.join(duvidosos[:3])}")
        resultado["score"] -= 10 * len(duvidosos)

    # 4. Verifica se é muito curto (provavelmente falhou)
    if resultado["tamanho_palavras"] < 5:
        resultado["aprovado"] = False
        resultado["motivos"].append("📏 Texto muito curto (menos de 5 palavras)")
        resultado["score"] -= 50

    # 5. Verifica se é muito longo para o esperado (possível looping)
    if resultado["tamanho_palavras"] > 500:
        resultado["motivos"].append("📏 Texto muito longo (>500 palavras)")
        resultado["score"] -= 10

    # 6. Verifica repetições excessivas
    palavras = texto_lower.split()
    if len(palavras) > 20:
        repeticoes = len(palavras) - len(set(palavras))
        taxa_repeticao = repeticoes / len(palavras)
        if taxa_repeticao > 0.4:
            resultado["aprovado"] = False
            resultado["motivos"].append(f"🔄 Repetição excessiva ({taxa_repeticao:.0%} das palavras repetidas)")
            resultado["score"] -= 40

    # 7. Verifica se tem marcação de diálogo quebrada
    if resultado["tamanho_palavras"] > 10:
        qtd_aspas = texto.count('"') + texto.count("'") + texto.count("“") + texto.count("\u201d")
        if qtd_aspas % 2 != 0:
            resultado["motivos"].append("🔧 Pontuação inconsistente (aspas não fechadas)")
            resultado["score"] -= 10

    # Define score final
    resultado["score"] = max(0, min(100, resultado["score"]))

    return resultado

# ─── Estilos de Escrita ───

ESTILOS_ESCRITA = {
    "neutro": {
        "nome": "➖ Neutro (padrão)",
        "descricao": "Estilo padrão do template, sem modificações.",
        "instrucao": "",
    },
    "profissional": {
        "nome": "💼 Profissional",
        "descricao": "Linguagem formal, técnica e corporativa. Ideal para documentos, relatórios e comunicação empresarial.",
        "instrucao": "Use linguagem formal, técnica e profissional. Evite gírias, abreviações ou tom casual. Seja preciso e objetivo, como em um ambiente corporativo sério.",
    },
    "professor": {
        "nome": "👨‍🏫 Professor",
        "descricao": "Tom didático e explicativo, como um professor explicando para alunos. Ideal para materiais educativos.",
        "instrucao": "Adote um tom didático e acolhedor, como um professor explicando para seus alunos. Explique conceitos de forma clara, use exemplos práticos e faça perguntas retóricas para engajar.",
    },
    "especialista": {
        "nome": "🔬 Especialista",
        "descricao": "Tom de autoridade técnica, com vocabulário avançado e aprofundado. Ideal para conteúdos técnicos.",
        "instrucao": "Use linguagem técnica e aprofundada, como um especialista no assunto. Empregue terminologia específica da área, dados e referências. Assuma que o leitor tem conhecimento prévio.",
    },
    "casual_jovem": {
        "nome": "🗣️ Conversa entre Jovens",
        "descricao": "Linguagem descontraída, gírias leves e tom informal. Ideal para redes sociais e conversas entre amigos.",
        "instrucao": "Use linguagem descontraída e informal, como uma conversa entre jovens. Pode usar gírias leves (tipo 'mano', 'curtir', 'demais'), abreviações casuais e um tom animado. Evite formalidades.",
    },
    "humoristico": {
        "nome": "😂 Bem-Humorado",
        "descricao": "Tom leve, divertido e com pitadas de humor. Ideal para entretenimento e conteúdo descontraído.",
        "instrucao": "Use um tom leve, bem-humorado e divertido. Inclua piadas sutis, trocadilhos e um toque de irreverência. Mantenha o respeito mas não tenha medo de ser engraçado.",
    },
    "poetico": {
        "nome": "📜 Poético / Literário",
        "descricao": "Linguagem rebuscada, metafórica e literária. Ideal para textos criativos e reflexivos.",
        "instrucao": "Use linguagem poética, metafórica e rica em imagens. Abuse de figuras de linguagem, descrições sensoriais e um ritmo de escrita mais cadenciado. Seja belo e expressivo.",
    },
    "informativo_jornalistico": {
        "nome": "📰 Jornalístico",
        "descricao": "Tom imparcial, factual e direto, como uma notícia de jornal. Ideal para informar sem opinião.",
        "instrucao": "Use tom imparcial e factual, como uma reportagem jornalística. Seja direto, responda: quem, o quê, quando, onde, por quê. Evite opinião pessoal e mantenha a neutralidade.",
    },
}

# ─── Templates de Prompt ───

PROMPT_TEMPLATES = {
    "dialogo_curto": {
        "nome": "💬 Diálogo Curto",
        "descricao": "Gera um diálogo curto (2-4 trocas) entre duas pessoas sobre um tema.",
        "system": "Você é um gerador de diálogos naturais em português brasileiro. Crie diálogos curtos, realistas e com linguagem cotidiana. Máximo de 4 trocas por diálogo.",
        "prompt": "Crie um diálogo curto e natural em português brasileiro entre duas pessoas falando sobre: {tema}. Apenas o diálogo, sem explicações.",
        "temperatura": 0.8,
        "max_tokens": 300,
    },
    "resposta_curta": {
        "nome": "⚡ Resposta Curta",
        "descricao": "Resposta direta e concisa (1-2 frases) sobre qualquer assunto.",
        "system": "Você responde de forma direta, clara e extremamente concisa. Máximo de 2 frases. Use português brasileiro.",
        "prompt": "Responda de forma curta e direta: {tema}",
        "temperatura": 0.5,
        "max_tokens": 150,
    },
    "pergunta_resposta": {
        "nome": "❓ Pergunta e Resposta",
        "descricao": "Gera um par pergunta-resposta educativo sobre um tópico.",
        "system": "Você é um educador criando material didático em português brasileiro. Gere uma pergunta interessante seguida de uma resposta completa e bem explicada.",
        "prompt": "Crie uma pergunta e resposta educativa sobre: {tema}. Formato:\nPergunta: ...\nResposta: ...",
        "temperatura": 0.7,
        "max_tokens": 500,
    },
    "artigo_curto": {
        "nome": "📝 Artigo Curto",
        "descricao": "Mini artigo explicativo de 3-5 parágrafos sobre um tema.",
        "system": "Você é um redator técnico em português brasileiro. Escreva mini artigos claros, bem estruturados e informativos.",
        "prompt": "Escreva um mini artigo de 3 a 5 parágrafos sobre: {tema}. Inclua introdução, desenvolvimento e conclusão.",
        "temperatura": 0.7,
        "max_tokens": 800,
    },
    "tutorial_passo": {
        "nome": "📋 Tutorial Passo a Passo",
        "descricao": "Instruções passo a passo para realizar uma tarefa.",
        "system": "Você é um instrutor técnico em português brasileiro. Crie tutoriais passo a passo claros e objetivos.",
        "prompt": "Crie um tutorial passo a passo explicando como: {tema}. Liste cada passo numerado e seja objetivo.",
        "temperatura": 0.6,
        "max_tokens": 600,
    },
    "resumo": {
        "nome": "📌 Resumo de Texto",
        "descricao": "Resume um texto ou ideia em poucas linhas.",
        "system": "Você é um assistente de resumo em português brasileiro. Seja conciso e capture apenas os pontos essenciais.",
        "prompt": "Faça um resumo objetivo do seguinte texto/ideia: {tema}",
        "temperatura": 0.4,
        "max_tokens": 300,
    },
    "traducao": {
        "nome": "🌍 Tradução",
        "descricao": "Traduz um texto do português para outro idioma ou vice-versa.",
        "system": "Você é um tradutor profissional. Traduza o texto mantendo o significado original e o tom adequado.",
        "prompt": "Traduza o seguinte texto para {idioma_destino}: {tema}",
        "temperatura": 0.3,
        "max_tokens": 500,
    },
    "pesquisa_explicativa": {
        "nome": "🔍 Resposta com Pesquisa",
        "descricao": "Resposta detalhada e bem explicada como se houvesse pesquisa envolvida.",
        "system": "Você é um pesquisador explicando conceitos de forma acessível em português brasileiro. Estruture com: contexto, explicação principal, exemplos e conclusão.",
        "prompt": "Explique detalhadamente o seguinte tópico como se tivesse pesquisado sobre ele: {tema}. Inclua contexto, explicação principal, exemplos práticos e uma conclusão.",
        "temperatura": 0.7,
        "max_tokens": 1000,
    },
    "poema_curto": {
        "nome": "📜 Poema Curto",
        "descricao": "Poema de 4 a 8 versos sobre um tema livre.",
        "system": "Você é um poeta em português brasileiro. Crie poemas curtos e expressivos.",
        "prompt": "Escreva um poema curto (4 a 8 versos) sobre: {tema}",
        "temperatura": 0.9,
        "max_tokens": 200,
    },
    "historia_curta": {
        "nome": "📖 História Curta",
        "descricao": "Microconto ou história muito curta (até 150 palavras).",
        "system": "Você é um escritor de microcontos em português brasileiro. Crie histórias completas mas extremamente concisas. Máximo 150 palavras.",
        "prompt": "Escreva uma história muito curta (máximo 150 palavras) sobre: {tema}",
        "temperatura": 0.8,
        "max_tokens": 300,
    },
    "ideias_criativas": {
        "nome": "💡 Geração de Ideias",
        "descricao": "Gera uma lista de ideias criativas sobre um tema.",
        "system": "Você é um consultor criativo em português brasileiro. Gere ideias originais e variadas.",
        "prompt": "Gere 5 ideias criativas relacionadas a: {tema}. Liste cada ideia com um breve descritivo.",
        "temperatura": 0.9,
        "max_tokens": 500,
    },
}

# ─── Modelos de requisição ───

class GerarRequest(BaseModel):
    template_id: str
    tema: str
    modelo: str = ""
    estilo: str = "neutro"
    idioma_destino: str = "inglês"
    quantidade: int = 1
    auto_filtrar: bool = False
    pesquisar_web: bool = False


class GerarLoteRequest(BaseModel):
    topicos: list[str]
    template_id: str = "dialogo_curto"
    modelo: str = ""
    estilo: str = "neutro"
    auto_filtrar: bool = True
    pesquisar_web: bool = False


class PararRequest(BaseModel):
    task_id: str


class SalvarTextoRequest(BaseModel):
    nome: str
    conteudo: str
    pasta: str = "gerados_local"


# Cache de tarefas em andamento
_tasks_in_progress: dict = {}


# ─── Endpoints ───

@router.get("/estilos")
def listar_estilos():
    """Lista todos os estilos de escrita disponíveis."""
    return {
        "estilos": [
            {
                "id": eid,
                "nome": e["nome"],
                "descricao": e["descricao"],
            }
            for eid, e in ESTILOS_ESCRITA.items()
        ]
    }


@router.get("/templates")
def listar_templates():
    """Lista todos os templates de prompt disponíveis."""
    return {
        "templates": [
            {
                "id": tid,
                "nome": t["nome"],
                "descricao": t["descricao"],
                "temperatura": t["temperatura"],
                "max_tokens": t["max_tokens"],
            }
            for tid, t in PROMPT_TEMPLATES.items()
        ]
    }


# Modelos conversacionais gerais têm PRIORIDADE na lista de geração — o
# padrão (primeiro) NUNCA é o modelo treinado do Rigel nem o DeepSeek
# (o DeepSeek é para ajuizar/limpar; o Rigel é o resultado do treino).
_MODELOS_PREFERIDOS = [
    "llama3.2:3b", "gemma2:2b", "qwen2.5:3b", "llama3.2:1b",
    "phi3:mini", "tinyllama:1.1b", "llama3.2", "gemma2",
]


def _ordenar_modelos_para_geracao(modelos: list) -> list:
    """Ordena: gerais (preferidos) primeiro, outros no meio, rigel/deepseek
    por último — o padrão da geração nunca é o modelo treinado do Rigel."""
    def _chave(m: str):
        nome = (m or "").lower()
        base = nome.split(":")[0].strip()
        if "rigel" in nome or "deepseek" in nome:
            return (2, nome)  # fim da lista
        for i, pref in enumerate(_MODELOS_PREFERIDOS):
            pbase = pref.split(":")[0].lower()
            if nome == pref or (base == pbase and nome.startswith(pref)):
                return (0, i)  # gerais primeiro, na ordem preferida
        return (1, nome)  # outros no meio
    return sorted(modelos, key=_chave)


@router.get("/modelos")
async def listar_modelos():
    """Lista modelos disponíveis no Ollama, ordenados para geração: os
    conversacionais gerais vêm primeiro (padrão); rigel/deepseek ficam
    por último (são para outras tarefas — ajuizar/limpar/treinar)."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                modelos = [m["name"] for m in data.get("models", [])]
                return {"modelos": _ordenar_modelos_para_geracao(modelos), "online": True}
    except Exception:
        pass
    return {"modelos": [], "online": False}


@router.get("/topicos")
def listar_topicos():
    """Lista os tópicos disponíveis no arquivo topicos.txt."""
    topicos_path = BASE_DIR / "topicos.txt"
    if not topicos_path.exists():
        return {"topicos": [], "total": 0}
    linhas = topicos_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    topicos = [l.strip().strip('"') for l in linhas if l.strip()]
    return {"topicos": topicos, "total": len(topicos)}


@router.get("/arquivos-salvos")
def listar_arquivos_salvos():
    """Lista os arquivos salvos na pasta de geração local."""
    pasta = BASE_DIR / "dados" / "gerados" / "gerados_local"
    arquivos = []
    if pasta.exists():
        for f in sorted(pasta.glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True):
            from datetime import datetime
            arquivos.append({
                "nome": f.name,
                "tamanho_kb": round(f.stat().st_size / 1024, 1),
                "data": datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "template": f.name.split("_")[0] if "_" in f.name else "—",
            })
    return {"arquivos": arquivos, "total": len(arquivos)}


@router.get("/arquivo-salvo/{nome_arquivo}")
def ler_arquivo_salvo(nome_arquivo: str):
    """Lê o conteúdo de um arquivo salvo."""
    pasta = BASE_DIR / "dados" / "gerados" / "gerados_local"
    arquivo = pasta / nome_arquivo
    if not arquivo.exists() or not arquivo.is_file():
        return {"erro": "Arquivo não encontrado"}
    try:
        conteudo = arquivo.read_text(encoding="utf-8", errors="ignore")
        return {"nome": nome_arquivo, "conteudo": conteudo}
    except Exception as e:
        return {"erro": str(e)}


@router.post("/gerar-lote")
async def gerar_conteudo_lote(req: GerarLoteRequest):
    """Gera conteúdo em lote para múltiplos tópicos com auto-filtro."""
    if req.template_id not in PROMPT_TEMPLATES:
        raise HTTPException(400, f"Template '{req.template_id}' não encontrado.")

    template = PROMPT_TEMPLATES[req.template_id]
    estilo_config = ESTILOS_ESCRITA.get(req.estilo)

    system_msg = template["system"]
    if estilo_config and estilo_config["instrucao"]:
        system_msg += " " + estilo_config["instrucao"]

    modelo = req.modelo
    if not modelo:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{OLLAMA_URL}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    if models:
                        modelo = models[0]
        except Exception:
            pass

    if not modelo:
        return JSONResponse(
            {"erro": "Nenhum modelo Ollama disponível."},
            status_code=400,
        )

    task_id = str(uuid.uuid4())
    # Registra tarefa em andamento
    _tasks_in_progress[task_id] = {"status": "gerando", "modelo": modelo, "created_at": time.time(), "last_heartbeat": time.time()}

    return StreamingResponse(
        _gerar_lote_com_filtro(
            modelo=modelo,
            system=system_msg,
            template=template,
            topicos=req.topicos,
            auto_filtrar=req.auto_filtrar,
            pesquisar_web=req.pesquisar_web,
            task_id=task_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/estatisticas-filtro")
def estatisticas_filtro():
    """Retorna estatísticas do filtro de qualidade."""
    stats_path = BASE_DIR / "dados" / "gerados" / "gerados_local" / "_filtro_stats.json"
    if stats_path.exists():
        try:
            return json.loads(stats_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"total_gerados": 0, "aprovados": 0, "rejeitados": 0, "historico": []}


@router.post("/salvar-texto")
async def salvar_texto(req: SalvarTextoRequest):
    """Salva o texto gerado em um arquivo."""
    pasta_destino = BASE_DIR / "dados" / "gerados" / req.pasta
    pasta_destino.mkdir(parents=True, exist_ok=True)
    arquivo = pasta_destino / req.nome
    try:
        arquivo.write_text(req.conteudo, encoding="utf-8")
        LOGS_DIR.mkdir(exist_ok=True)
        log_file = LOGS_DIR / "dashboard.log"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] Texto salvo: {req.pasta}/{req.nome}\n")
        return {"ok": True, "arquivo": str(arquivo)}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@router.post("/gerar")
async def gerar_conteudo(req: GerarRequest):
    """Gera conteúdo usando Ollama com o template escolhido."""
    if req.template_id not in PROMPT_TEMPLATES:
        raise HTTPException(400, f"Template '{req.template_id}' não encontrado.")

    template = PROMPT_TEMPLATES[req.template_id]

    # Se nenhum modelo foi especificado, tenta detectar
    modelo = req.modelo
    if not modelo:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{OLLAMA_URL}/api/tags")
                if resp.status_code == 200:
                    data = resp.json()
                    models = [m["name"] for m in data.get("models", [])]
                    if models:
                        modelo = models[0]
        except Exception:
            pass

    if not modelo:
        return {"erro": "Nenhum modelo Ollama disponível. Instale um com 'ollama pull <modelo>'."}

    # Aplica estilo de escrita
    estilo_config = ESTILOS_ESCRITA.get(req.estilo)
    if estilo_config and estilo_config["instrucao"]:
        system_msg = template["system"] + " " + estilo_config["instrucao"]
    else:
        system_msg = template["system"]

    # 🔍 Pesquisa web se ativado
    if req.pesquisar_web or PESQUISA_SEMPRE_ATIVA:
        print(f"[GERAR_LOCAL] 🔍 Pesquisa web para: {req.tema[:50]}...")
        contexto_pesquisa = await asyncio.to_thread(pesquisar, req.tema, 5)
        if contexto_pesquisa:
            system_msg += f"\n\nUse as seguintes informações reais da web para embasar o texto:\n{contexto_pesquisa}\nBaseie-se nestes fatos. Se não houver info suficiente, apenas escreva sem inventar."
            print(f"[GERAR_LOCAL] ✅ Pesquisa OK — {len(contexto_pesquisa)} chars de contexto")

    # Monta o prompt
    prompt_texto = template["prompt"].format(
        tema=req.tema,
        idioma_destino=req.idioma_destino,
    )

    max_tokens = template["max_tokens"]
    temperatura = template["temperatura"]

    # Se quantidade > 1, gera múltiplas vezes
    if req.quantidade > 1:
        return StreamingResponse(
            _gerar_multiplos(modelo, system_msg, prompt_texto, temperatura, max_tokens, req.quantidade, req.auto_filtrar),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )

    task_id = str(uuid.uuid4())
    _tasks_in_progress[task_id] = {"status": "gerando", "modelo": modelo}

    return StreamingResponse(
        _gerar_stream(modelo, system_msg, prompt_texto, temperatura, max_tokens, task_id),
        media_type="text/event-stream"
    )


@router.post("/parar")
async def parar_geracao(req: PararRequest):
    """Marca uma tarefa para parar."""
    if req.task_id in _tasks_in_progress:
        _tasks_in_progress[req.task_id]["status"] = "parando"
        return {"ok": True}
    return {"ok": False, "erro": "Tarefa não encontrada"}


# ─── Funções auxiliares ───

async def _gerar_stream(modelo: str, system: str, prompt: str, temp: float, max_tokens: int, task_id: str = ""):
    """Gera conteúdo em streaming via Ollama."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    yield f"data: {json.dumps({'type': 'meta', 'modelo': modelo, 'template': system})}\n\n"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": modelo,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": temp,
                        "num_predict": max_tokens,
                    }
                }
            ) as response:
                if response.status_code != 200:
                    erro = await response.aread()
                    yield f"data: {json.dumps({'type': 'erro', 'conteudo': f'Erro {response.status_code}: {erro.decode()[:300]}'})}\n\n"
                    return

                texto_completo = ""
                async for linha in response.aiter_lines():
                    if not linha.strip():
                        continue

                    # Verifica se deve parar
                    if task_id and _tasks_in_progress.get(task_id, {}).get("status") == "parando":
                        yield f"data: {json.dumps({'type': 'parado', 'conteudo': texto_completo})}\n\n"
                        return

                    try:
                        dados = json.loads(linha)
                        if "message" in dados and "content" in dados["message"]:
                            content = dados["message"]["content"]
                            texto_completo += content
                            yield f"data: {json.dumps({'type': 'chunk', 'conteudo': content})}\n\n"
                        if dados.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

                texto_completo = limpar_e_aviso(texto_completo, "Geração Local Stream")
                yield f"data: {json.dumps({'type': 'done', 'conteudo': texto_completo})}\n\n"

    except httpx.TimeoutException:
        yield f"data: {json.dumps({'type': 'erro', 'conteudo': 'Tempo limite excedido (120s).'})}\n\n"
    except httpx.ConnectError:
        yield f"data: {json.dumps({'type': 'erro', 'conteudo': 'Nao foi possivel conectar ao Ollama.'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'erro', 'conteudo': f'Erro: {str(e)[:200]}'})}\n\n"
    finally:
        if task_id and task_id in _tasks_in_progress:
            _tasks_in_progress.pop(task_id, None)


async def _gerar_lote_com_filtro(modelo: str, system: str, template: dict, topicos: list[str], auto_filtrar: bool, pesquisar_web: bool = False, task_id: str = ''):
    """Gera conteúdo para cada tópico em lote, aplicando auto-filtro e pesquisa web opcional."""
    total = len(topicos)
    inicio_global = time.time()
    yield f"data: {json.dumps({'type': 'lote_meta', 'total': total, 'modelo': modelo, 'auto_filtrar': auto_filtrar, 'pesquisar_web': pesquisar_web, 'task_id': task_id})}\n\n"

    stats_path = BASE_DIR / "dados" / "gerados" / "gerados_local" / "_filtro_stats.json"
    stats = {"total_gerados": 0, "aprovados": 0, "rejeitados": 0, "rejeitados_detalhes": []}
    if stats_path.exists():
        try:
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    for idx, topico in enumerate(topicos):
        inicio_item = time.time()
        item_pesquisa = ""
        yield f"data: {json.dumps({'type': 'lote_item_inicio', 'indice': idx + 1, 'total': total, 'topico': topico, 'elapsed': round(time.time() - inicio_global)})}\n\n"

        # 🔍 Pesquisa web real (se ativada)
        if pesquisar_web and _ddgs_available:
            yield f"data: {json.dumps({'type': 'lote_item_pesquisando', 'indice': idx + 1, 'topico': topico})}\n\n"
            item_pesquisa_sinc = await asyncio.to_thread(pesquisar, topico, 5)
            item_pesquisa = item_pesquisa_sinc or ""
            if item_pesquisa:
                yield f"data: {json.dumps({'type': 'lote_item_pesquisa_pronta', 'indice': idx + 1, 'resultados': item_pesquisa[:200]})}\n\n"

        # Monta prompt com ou sem pesquisa
        prompt_texto = template["prompt"].format(tema=topico, idioma_destino="inglês")

        if pesquisar_web and item_pesquisa:
            system_com_pesquisa = system + f"\n\nUse as seguintes informações reais da web para responder:\n{item_pesquisa}\n\nBaseie sua resposta nestes fatos reais. Não invente informações. Se os resultados não cobrirem o tópico, admita que não há informação suficiente."
            messages = [
                {"role": "system", "content": system_com_pesquisa},
                {"role": "user", "content": prompt_texto},
            ]
        else:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt_texto},
            ]

        temp = template["temperatura"]
        max_tokens = template["max_tokens"]
        texto_gerado = ""

        try:
            # Envia heartbeat inicial com timestamp
            yield f"data: {json.dumps({'type': 'lote_heartbeat', 'indice': idx + 1, 'total': total, 'topico': topico[:60], 'elapsed': round(time.time() - inicio_global)})}\n\n"

            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": modelo,
                        "messages": messages,
                        "stream": True,
                        "options": {"temperature": temp, "num_predict": max_tokens},
                    }
                ) as response:
                    if response.status_code != 200:
                        yield f"data: {json.dumps({'type': 'lote_item_erro', 'indice': idx + 1, 'topico': topico})}\n\n"
                        continue

                    # Itera aiter_lines mas envia heartbeat se ficar sem resposta por N segundos
                    aiter = response.aiter_lines().__aiter__()
                    heartbeat_interval = 3.0
                    while True:
                        # Verifica se o cliente pediu para parar
                        if task_id and _tasks_in_progress.get(task_id, {}).get('status') == 'parando':
                            yield f"data: {json.dumps({'type': 'lote_parado', 'indice': idx + 1, 'topico': topico})}\n\n"
                            # limpa e retorna
                            try:
                                _tasks_in_progress.pop(task_id, None)
                            except Exception:
                                pass
                            return

                        # tenta ler a próxima linha com timeout
                        line_task = asyncio.create_task(aiter.__anext__())
                        done, pending = await asyncio.wait({line_task}, timeout=heartbeat_interval)
                        if line_task in done:
                            try:
                                linha = line_task.result()
                            except StopAsyncIteration:
                                break
                            if not linha.strip():
                                continue
                            try:
                                dados = json.loads(linha)
                                if "message" in dados and "content" in dados["message"]:
                                    texto_gerado += dados["message"]["content"]
                                if dados.get("done"):
                                    break
                            except json.JSONDecodeError:
                                continue
                        else:
                            # timeout -> enviar heartbeat para o cliente
                            try:
                                line_task.cancel()
                            except Exception:
                                pass
                            # atualização de heartbeat no estado da tarefa
                            if task_id and task_id in _tasks_in_progress:
                                _tasks_in_progress[task_id]['last_heartbeat'] = time.time()
                            yield f"data: {json.dumps({'type': 'lote_heartbeat', 'indice': idx + 1, 'total': total, 'topico': topico[:60], 'elapsed': round(time.time() - inicio_global)})}\n\n"

            # Remove emojis do texto gerado (prejudicam treinamento)
            texto_gerado = limpar_e_aviso(texto_gerado, f"Geração Local ({topico[:30]})")

            tempo_item = time.time() - inicio_item
            stats["total_gerados"] += 1

            # Aplica auto-filtro
            if auto_filtrar and texto_gerado.strip():
                avaliacao = _auto_avaliar_qualidade(texto_gerado)
                if not avaliacao["aprovado"]:
                    stats["rejeitados"] += 1
                    stats.setdefault("rejeitados_detalhes", []).append({
                        "topico": topico,
                        "motivos": avaliacao["motivos"],
                        "score": avaliacao["score"],
                    })
                    yield f"data: {json.dumps({
                        'type': 'lote_item_rejeitado',
                        'indice': idx + 1,
                        'topico': topico,
                        'motivos': avaliacao['motivos'],
                        'score': avaliacao['score'],
                        'conteudo': texto_gerado,
                        'tempo_seg': round(tempo_item, 1),
                    })}\n\n"
                    # Salva rejeitados em pasta separada
                    _salvar_como_rejeitado(topico, texto_gerado, avaliacao)
                else:
                    stats["aprovados"] += 1
                    yield f"data: {json.dumps({
                        'type': 'lote_item_aprovado',
                        'indice': idx + 1,
                        'topico': topico,
                        'score': avaliacao['score'],
                        'conteudo': texto_gerado,
                        'tempo_seg': round(tempo_item, 1),
                    })}\n\n"
            else:
                stats["aprovados"] += 1
                yield f"data: {json.dumps({
                    'type': 'lote_item_aprovado',
                    'indice': idx + 1,
                    'topico': topico,
                    'conteudo': texto_gerado,
                    'tempo_seg': round(tempo_item, 1),
                })}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'lote_item_erro', 'indice': idx + 1, 'topico': topico, 'erro': str(e)[:100]})}\n\n"
            continue

    # Salva estatísticas
    try:
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    # Limpa tarefa em andamento
    if task_id and task_id in _tasks_in_progress:
        try:
            _tasks_in_progress.pop(task_id, None)
        except Exception:
            pass

    tempo_total = round(time.time() - inicio_global, 1)
    yield f"data: {json.dumps({'type': 'lote_fim', 'total': total, 'aprovados': stats['aprovados'], 'rejeitados': stats['rejeitados'], 'tempo_total': tempo_total})}\n\n"


def _salvar_como_rejeitado(topico: str, conteudo: str, avaliacao: dict):
    """Salva conteúdo rejeitado em pasta separada para revisão."""
    pasta = BASE_DIR / "dados" / "gerados" / "gerados_local" / "_rejeitados"
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"rejeitado_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.txt"
    cabecalho = f"=== REJEITADO (score: {avaliacao['score']}) ===\nTópico: {topico}\nMotivos: {', '.join(avaliacao['motivos'])}\n{'='*40}\n\n"
    (pasta / nome).write_text(cabecalho + conteudo, encoding="utf-8")


async def _gerar_multiplos(modelo: str, system: str, prompt: str, temp: float, max_tokens: int, quantidade: int, auto_filtrar: bool = False):
    """Gera múltiplos conteúdos em lote."""
    yield f"data: {json.dumps({'type': 'meta', 'modelo': modelo, 'quantidade': quantidade, 'auto_filtrar': auto_filtrar})}\n\n"

    stats_path = BASE_DIR / "dados" / "gerados" / "gerados_local" / "_filtro_stats.json"
    stats = {"total_gerados": 0, "aprovados": 0, "rejeitados": 0, "rejeitados_detalhes": []}
    if stats_path.exists():
        try:
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    for i in range(quantidade):
        yield f"data: {json.dumps({'type': 'item_inicio', 'indice': i + 1})}\n\n"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": modelo,
                        "messages": messages,
                        "stream": True,
                        "options": {
                            "temperature": temp,
                            "num_predict": max_tokens,
                        }
                    }
                ) as response:
                    if response.status_code != 200:
                        yield f"data: {json.dumps({'type': 'item_erro', 'indice': i + 1})}\n\n"
                        continue

                    texto = ""
                    async for linha in response.aiter_lines():
                        if not linha.strip():
                            continue
                        try:
                            dados = json.loads(linha)
                            if "message" in dados and "content" in dados["message"]:
                                texto += dados["message"]["content"]
                            if dados.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue

            stats["total_gerados"] += 1

            # Aplica auto-filtro se ativado
            if auto_filtrar and texto.strip():
                avaliacao = _auto_avaliar_qualidade(texto)
                if not avaliacao["aprovado"]:
                    stats["rejeitados"] += 1
                    stats.setdefault("rejeitados_detalhes", []).append({
                        "topico": prompt[:80],
                        "motivos": avaliacao["motivos"],
                        "score": avaliacao["score"],
                    })
                    _salvar_como_rejeitado(prompt[:80], texto, avaliacao)
                    yield f"data: {json.dumps({'type': 'item_rejeitado', 'indice': i + 1, 'motivos': avaliacao['motivos'], 'score': avaliacao['score'], 'conteudo': texto})}\n\n"
                    continue
                else:
                    yield f"data: {json.dumps({'type': 'item_pronto', 'indice': i + 1, 'conteudo': texto, 'score': avaliacao['score']})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'item_pronto', 'indice': i + 1, 'conteudo': texto})}\n\n"

        except Exception:
            yield f"data: {json.dumps({'type': 'item_erro', 'indice': i + 1})}\n\n"

    # Salva estatísticas
    try:
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    yield f"data: {json.dumps({'type': 'batch_done', 'aprovados': stats['aprovados'], 'rejeitados': stats['rejeitados'], 'total': stats['total_gerados']})}\n\n"
