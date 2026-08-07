#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dados.py - Rotas do painel de dados (funil até processed).
Versão: 1.0.0 | Data: 06/08/2026

  GET  /api/dados/painel            - estado do funil (dispara varredura se nunca rodou)
  POST /api/dados/painel/varredura  - força nova varredura em background
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from dashboard.services import painel_dados

router = APIRouter(prefix="/api/dados", tags=["Dados / Funil"])


@router.get("/painel")
async def painel():
    """Estado do funil de dados. Se nunca varreu, dispara em background."""
    est = painel_dados.get_estado()
    if not est["varrido"] and not est["varrendo"]:
        painel_dados.iniciar_varredura()
        est = painel_dados.get_estado()
    return est


@router.post("/painel/varredura")
async def varredura():
    """Força uma nova varredura (background, com barra de %)."""
    return painel_dados.iniciar_varredura()
