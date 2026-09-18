#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tratamento.py — API da Central de Tratamento de Dados (página /tratamento).

Endpoints:
  GET  /api/tratamento/listar   → pastas em dados/raw/ com formato + recomendação
  POST /api/tratamento/tratar   {nomes: [...]} → tratamento em lote (background)
  GET  /api/tratamento/status   → estado do tratamento
  POST /api/tratamento/limpar   → reset do estado
"""
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dashboard.services import tratamento
from dashboard.services import tratamento_acervo

router = APIRouter(prefix="/api/tratamento", tags=["Tratamento"])


class TratarRequest(BaseModel):
    nomes: list[str] = []


class ConverterRequest(BaseModel):
    nome: str = ""


class AcervoRequest(BaseModel):
    origem: str = ""
    simular: bool = True


class AcervoControleRequest(BaseModel):
    origem: str = ""
    simular: bool = True


@router.get("/acervo/origens")
async def listar_origens_acervo():
    return await asyncio.to_thread(tratamento_acervo.listar_origens)


@router.post("/acervo/iniciar")
async def iniciar_tratamento_acervo(req: AcervoRequest):
    if not req.origem.strip():
        return JSONResponse(status_code=400, content={"ok": False, "erro": "Escolha uma origem."})
    try:
        return await asyncio.to_thread(tratamento_acervo.iniciar, req.origem, req.simular)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "erro": str(exc)})


@router.get("/acervo/progresso")
async def progresso_tratamento_acervo():
    return await asyncio.to_thread(tratamento_acervo.progresso)


@router.post("/acervo/revisar")
async def revisar_tratamento_acervo():
    return await asyncio.to_thread(tratamento_acervo.revisar_tratado)


@router.post("/acervo/promover")
async def promover_tratamento_acervo():
    return await asyncio.to_thread(tratamento_acervo.promover_tratado)


@router.post("/acervo/pausar")
async def pausar_tratamento_acervo():
    return await asyncio.to_thread(tratamento_acervo.pausar)


@router.post("/acervo/parar")
async def parar_tratamento_acervo():
    return await asyncio.to_thread(tratamento_acervo.parar)


@router.post("/acervo/retomar")
async def retomar_tratamento_acervo(req: AcervoControleRequest):
    try:
        return await asyncio.to_thread(tratamento_acervo.iniciar, req.origem, req.simular, True)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "erro": str(exc)})


@router.get("/listar")
async def listar():
    return await asyncio.to_thread(tratamento.listar_entrada)


@router.post("/prever")
async def prever(req: TratarRequest):
    """Prévia iterativa: explica o que será feito com cada pasta marcada
    (e o que NÃO pode, com o motivo e o caminho certo) ANTES de iniciar."""
    return await asyncio.to_thread(tratamento.prever, req.nomes)


@router.post("/tratar")
async def tratar(req: TratarRequest):
    return tratamento.tratar(req.nomes)


@router.post("/extrair-pdfs")
async def extrair_pdfs(req: dict | None = None):
    """✨ Extrai TODOS os PDFs de uma pasta (ex.: livros) na PRÓPRIA aba de
    Tratamento: PDF → TXT → JSONL → promovido p/ processed. Não joga o
    usuário para outra página."""
    body = req or {}
    nome = (body.get("nome") or "").strip()
    if not nome:
        return {"ok": False, "erro": "Informe a pasta (ex.: livros)."}
    return await asyncio.to_thread(tratamento.extrair_pdfs_pasta, nome)


@router.get("/status")
async def status():
    return tratamento.get_estado()


@router.post("/limpar")
async def limpar():
    return tratamento.limpar()


@router.post("/converter-jsonl")
async def converter_jsonl(req: ConverterRequest):
    """Converte uma pasta provisória (dados/gerados/jsonl/<nome>) para o
    formato messages (SFT) — botão individual por pasta na aba Tratamento."""
    nome = (req.nome or "").strip()
    if not nome:
        return {"ok": False, "erro": "Informe a pasta (nome)."}
    return await asyncio.to_thread(tratamento.converter_jsonl_pasta, nome)


@router.post("/extrair-txt")
async def extrair_txt(req: ConverterRequest):
    """Extrai o TEXTO (pré-treino) de uma pasta provisória para .txt em
    dados/processed/txt/<nome> (pipeline de PRÉ-TREINO)."""
    nome = (req.nome or "").strip()
    if not nome:
        return {"ok": False, "erro": "Informe a pasta (nome)."}
    return await asyncio.to_thread(tratamento.extrair_txt_pasta, nome)


@router.get("/formatos")
async def formatos():
    """Tabela de formatos x tratamentos (para a UI)."""
    return {
        "jsonl": {"tratamento": "sanitizar", "emoji": "🧼", "destino": "processed/jsonl/<nome>/"},
        "parquet": {"tratamento": "limpeza_leve", "emoji": "🧹", "destino": "processed/ (rigel_sft.parquet)"},
        "csv": {"tratamento": "limpeza_leve", "emoji": "🧹", "destino": "processed/ (rigel_sft.parquet)"},
        "txt": {"tratamento": "limpeza_encoding", "emoji": "🔤", "destino": "processed/txt/<nome>/"},
        "json": {"tratamento": "sanitizar", "emoji": "🧼", "destino": "processed/jsonl/<nome>/"},
        "outro": {"tratamento": "nenhum", "emoji": "⛔", "destino": "—"},
        "vazio": {"tratamento": "nenhum", "emoji": "⛔", "destino": "—"},
    }
