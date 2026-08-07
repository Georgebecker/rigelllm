#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scrap.py — API do scraper de sites (página /scrap).

Endpoints:
  POST /api/scrap/testar      {url}  → teste de qualidade SEM salvar
  POST /api/scrap/processar   {url, formato, nome?} → pipeline completo (background)
  GET  /api/scrap/status            → estado do processamento
  POST /api/scrap/limpar            → reset do estado (esquecer painel)
  GET  /api/scrap/listar            → pastas em dados/processed/scrap/
"""
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dashboard.services import scrap

router = APIRouter(prefix="/api/scrap", tags=["Scrap"])


class TestarRequest(BaseModel):
    url: str


class ProcessarRequest(BaseModel):
    url: str
    formato: str = "jsonl"   # jsonl | txt | parquet
    nome: str | None = None
    modo: str = "quantidade"   # quantidade (até max_materias) | profundidade
    preferencia: str = "nenhuma"  # novas | complexas | nenhuma
    profundidade: int = 1     # teto de segurança (quantidade) ou objetivo (profundidade)
    max_materias: int = 20    # objetivo (quantidade, até 100) ou teto (profundidade)


@router.post("/testar")
async def testar(req: TestarRequest):
    url = (req.url or "").strip()
    if not url:
        return JSONResponse({"ok": False, "erro": "Informe a URL do site."}, status_code=400)
    return await asyncio.to_thread(scrap.testar_url, url)


@router.post("/processar")
async def processar(req: ProcessarRequest):
    url = (req.url or "").strip()
    if not url:
        return JSONResponse({"ok": False, "erro": "Informe a URL do site."}, status_code=400)
    return scrap.processar(url, formato=req.formato, nome=req.nome,
                           modo=req.modo, preferencia=req.preferencia,
                           profundidade=req.profundidade, max_materias=req.max_materias)


@router.get("/status")
async def status():
    return scrap.get_estado()


@router.post("/limpar")
async def limpar():
    return scrap.limpar()


@router.get("/listar")
async def listar():
    return await asyncio.to_thread(scrap.listar)
