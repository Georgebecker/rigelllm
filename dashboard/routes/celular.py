#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
celular.py — API de exportação/importação celular ↔ PC.

Endpoints:
  GET  /api/celular/status              → estado + exportações + pendentes em dados/Celular
  POST /api/celular/exportar            → gera rigel_export_<ts>.zip (matéria-prima p/ treino)
  GET  /api/celular/download/{nome}     → baixa a exportação (Google Drive / celular)
  POST /api/celular/remover_exportacao  → apaga uma exportação
  GET  /api/celular/importar/verificar  → lista zips/arquivos aguardando em dados/Celular
  POST /api/celular/importar            → importa tudo de dados/Celular (thread)
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from dashboard.services import celular

router = APIRouter(prefix="/api/celular", tags=["Celular"])


class RemoverExportRequest(BaseModel):
    nome: str


@router.get("/status")
async def status():
    return celular.get_estado()


@router.post("/exportar")
async def exportar():
    return celular.exportar()


@router.get("/download/{nome}")
async def download(nome: str):
    nome = nome.replace("\\", "/").split("/")[-1]
    if not nome.startswith("rigel_export_") or not nome.endswith(".zip"):
        return JSONResponse({"ok": False, "erro": "Arquivo inválido."}, status_code=400)
    p = celular.DIST / nome
    if not p.exists():
        return JSONResponse({"ok": False, "erro": "Exportação não encontrada."}, status_code=404)
    return FileResponse(
        path=str(p), media_type="application/zip", filename=nome,
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.post("/remover_exportacao")
async def remover_exportacao(req: RemoverExportRequest):
    return celular.remover_exportacao(req.nome)


@router.get("/importar/verificar")
async def verificar():
    return celular._verificar_pendentes()


@router.post("/importar")
async def importar():
    return celular.importar()
