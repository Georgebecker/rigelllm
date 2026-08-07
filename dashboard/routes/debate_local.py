#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
debate_local.py - Debate/Podcast via Ollama (modelo local)
Versão: 1.0.0 | Data: 31/07/2026
Gera debates e podcasts usando modelos locais do Ollama, sem depender de API externa.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import json
import httpx
import asyncio
from datetime import datetime
from typing import List, Optional

router = APIRouter(prefix="/api/debate-local", tags=["Debate Local"])

BASE_DIR = Path(__file__).parent.parent.parent

# Perfis disponíveis para debate/podcast
PERFIS = [
    {"id": "Jornalista", "nome": "Jornalista", "descricao": "Analisa fatos com imparcialidade e profundidade", "embasamento": "alto"},
    {"id": "Filósofo", "nome": "Filósofo", "descricao": "Reflete sobre questões éticas e existenciais", "embasamento": "medio"},
    {"id": "Cientista", "nome": "Cientista", "descricao": "Baseia argumentos em dados e evidências", "embasamento": "alto"},
    {"id": "Jovem Estudante", "nome": "Jovem Estudante", "descricao": "Pergunta e curiosidade sobre o tema", "embasamento": "baixo"},
    {"id": "Professor", "nome": "Professor", "descricao": "Explica conceitos de forma didática", "embasamento": "alto"},
    {"id": "Ativista", "nome": "Ativista", "descricao": "Defende causas com paixão e engajamento", "embasamento": "medio"},
    {"id": "Historiador", "nome": "Historiador", "descricao": "Contextualiza fatos historicamente", "embasamento": "alto"},
]


class DebateRequest(BaseModel):
    modo: str = "debate"  # "debate" ou "podcast"
    perfil: str = "Jornalista"
    convidados: List[str] = ["Cientista"]
    tema: str = ""
    turnos: int = 2
    pesquisar: bool = True
    modelo: str = "rigelslm"


@router.get("/perfis")
async def listar_perfis():
    """Lista perfis disponíveis para debate/podcast."""
    return {"perfis": PERFIS}


@router.post("/gerar")
async def gerar_debate_local(req: DebateRequest):
    """Gera debate ou podcast usando o modelo Ollama selecionado."""
    tema = req.tema or "Inteligência Artificial"
    modo = req.modo
    turnos = max(1, min(req.turnos, 6))

    # Monta o prompt baseado no modo
    if modo == "debate":
        perfil_info = next((p for p in PERFIS if p["id"] == req.perfil), PERFIS[0])
        prompt = f"""Você é um gerador de debates. Gere um DEBATE em português brasileiro sobre o tema: {tema}

Formato: Dois debatedores ({perfil_info['nome']} A e {perfil_info['nome']} B) trocam argumentos sobre o tema.

{perfil_info['descricao']}

Cada debatedor deve ter {turnos} falas alternadas. Formato:
{perfil_info['nome']} A: [fala]
{perfil_info['nome']} B: [fala]

Total: {turnos * 2} falas. Seja factual e evite opiniões vazias."""
    else:
        # Podcast
        convidados_nomes = []
        for cid in req.convidados[:3]:
            cinfo = next((p for p in PERFIS if p["id"] == cid), None)
            if cinfo:
                convidados_nomes.append(cinfo["nome"])
        conv_str = ", ".join(convidados_nomes)

        prompt = f"""Você é um gerador de podcasts. Gere um PODCAST em português brasileiro sobre o tema: {tema}

Formato: Um apresentador (🎙️ Podcaster) entrevista convidados especialistas.

Convidados: {conv_str}

O apresentador faz perguntas e os convidados respondem. Cada participante tem {turnos} falas.
Formato:
🎙️ Podcaster: [pergunta ou comentário]
[Convidado]: [resposta]

Total: {turnos * (1 + len(req.convidados[:3]))} falas. Seja natural e informativo."""

    try:
        # Chama o Ollama
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": req.modelo,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.8,
                    "top_k": 40,
                    "num_predict": 2000,
                }
            }
            resp = await client.post("http://localhost:11434/api/generate", json=payload)

            if resp.status_code != 200:
                return JSONResponse(
                    status_code=500,
                    content={"status": "erro", "mensagem": f"Ollama retornou erro {resp.status_code}"}
                )

            data = resp.json()
            texto = data.get("response", "").strip()

            if not texto:
                return JSONResponse(
                    status_code=500,
                    content={"status": "erro", "mensagem": "Modelo não gerou resposta"}
                )

            # Salva o resultado
            pasta = BASE_DIR / "dados" / "gerados" / "debates"
            pasta.mkdir(parents=True, exist_ok=True)
            nome_arquivo = f"{'debate' if modo=='debate' else 'podcast'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            caminho = pasta / nome_arquivo
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(texto)

            label = "Debate" if modo == "debate" else "Podcast"
            return {
                "status": "ok",
                "mensagem": f"✅ {label} gerado por {req.modelo} em {caminho.name}",
                "texto": texto,
                "arquivo": str(caminho),
                "tamanho_kb": round(len(texto) / 1024, 1),
                "modelo": req.modelo,
            }

    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={"status": "erro", "mensagem": "❌ Não foi possível conectar ao Ollama. Ele está rodando?"}
        )
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"status": "erro", "mensagem": "❌ Tempo limite excedido. O modelo pode estar sobrecarregado."}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "erro", "mensagem": f"❌ Erro: {str(e)[:200]}"}
        )
