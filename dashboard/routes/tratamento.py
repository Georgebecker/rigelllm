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

router = APIRouter(prefix="/api/tratamento", tags=["Tratamento"])


class TratarRequest(BaseModel):
    nomes: list[str] = []


@router.get("/listar")
async def listar():
    return await asyncio.to_thread(tratamento.listar_entrada)


@router.post("/tratar")
async def tratar(req: TratarRequest):
    return tratamento.tratar(req.nomes)


@router.get("/status")
async def status():
    return tratamento.get_estado()


@router.post("/limpar")
async def limpar():
    return tratamento.limpar()


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
