#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
convert_txt.py - Rotas da API de conversão TXT → JSONL (SFT messages).
Versão: 1.0.0 | Data: 06/08/2026

  GET  /api/convert_txt/pastas      - pastas com .txt disponíveis p/ converter
  POST /api/convert_txt/converter   - inicia a conversão (subprocesso)
  GET  /api/convert_txt/progresso   - estado + mensagens em tempo real
  POST /api/convert_txt/parar       - para a conversão em andamento
  GET  /api/convert_txt/semafaro    - estado do semáforo global (treino/conversão)
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dashboard.services import converter_txt
from dashboard.services import treino_global

router = APIRouter(prefix="/api/convert_txt", tags=["Conversão TXT→JSONL"])


class ConverterRequest(BaseModel):
    pasta: str                      # caminho ou nome da pasta com .txt
    saida: str | None = None        # nome do dataset de saída (default rigeljsonl<N>)
    max_exemplos: int | None = None
    max_arquivos: int | None = None
    apenas_qna: bool = False        # só arquivos com Pergunta/Resposta (pula artigos)


@router.get("/pastas")
async def pastas():
    """Pastas com .txt disponíveis para conversão (com contagem e tamanho)."""
    return {"pastas": converter_txt.listar_pastas_txt(),
            "destino": "dados/gerados/jsonl",
            "scan": converter_txt.status_scan_txt(),
            "timestamp": __import__("datetime").datetime.now().isoformat()}


@router.post("/converter")
async def converter(req: ConverterRequest):
    """Inicia a conversão TXT → JSONL. Recusa se já houver treino/conversão."""
    ok, ocupante = treino_global.disponivel()
    if not ok:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "message": (f"❌ {ocupante['rotulo']} em andamento (PID {ocupante['pid']}). "
                        "Só uma operação pesada por vez — termine ou pare antes."),
        })

    r = converter_txt.iniciar_conversao(req.pasta, req.saida,
                                        req.max_exemplos, req.max_arquivos,
                                        req.apenas_qna)
    if not r.get("ok"):
        return JSONResponse(status_code=400, content={"ok": False, "message": r.get("erro", "erro")})

    # Registra no semáforo global (para exibição)
    estado = converter_txt.get_estado()
    treino_global.registrar("conversao_txt", estado.get("pid"), req.pasta)
    return {"ok": True, "message": r.get("mensagem"), "saida": r.get("saida")}


@router.get("/progresso")
async def progresso():
    """Estado da conversão + buffer de mensagens em tempo real."""
    est = converter_txt.get_estado()
    return {
        "rodando": est["rodando"],
        "etapa": est["etapa"],
        "pasta": est["pasta"],
        "saida": est["saida"],
        "mensagem": est["mensagem"],
        "mensagens": est["mensagens"][-100:],
        "inicio": est["inicio"],
        "fim": est["fim"],
        "erro": est["erro"],
        "semafaro": treino_global.get_estado(),
    }


@router.post("/parar")
async def parar():
    """Para a conversão em andamento."""
    return converter_txt.parar_conversao()


@router.get("/semafaro")
async def semafaro():
    """Estado do semáforo global (quem está rodando, se algo está)."""
    return treino_global.get_estado()
