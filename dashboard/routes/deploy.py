#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
deploy.py — API de backup/distribuição (seção do dashboard).

Endpoints:
  GET  /api/deploy/status               → estado + versões (nome, tamanho, data, url)
  POST /api/deploy/criar                → gera novo backup (thread, máx. 2 versões)
  GET  /api/deploy/download/{nome}      → baixa o ZIP (funciona no celular)
  POST /api/deploy/remover              → remove uma versão
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from dashboard.services import deploy

router = APIRouter(prefix="/api/deploy", tags=["Deploy"])


class RemoverRequest(BaseModel):
    nome: str


@router.get("/status")
async def status():
    return deploy.get_estado()


@router.post("/criar")
async def criar():
    return deploy.criar_backup()


@router.get("/download/{nome}")
async def download(nome: str):
    """Serve o ZIP para download. Header de anexo → baixa direto no celular."""
    nome = nome.replace("\\", "/").split("/")[-1]
    if not nome.startswith("rigelslm_dist_") or not nome.endswith(".zip"):
        return JSONResponse({"ok": False, "erro": "Arquivo inválido."}, status_code=400)
    p = deploy.DESTINO / nome
    if not p.exists():
        return JSONResponse({"ok": False, "erro": "Arquivo não encontrado."}, status_code=404)
    return FileResponse(
        path=str(p),
        media_type="application/zip",
        filename=nome,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/remover")
async def remover(req: RemoverRequest):
    return deploy.remover_versao(req.nome)
