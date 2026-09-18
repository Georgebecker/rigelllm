#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
boletim.py - Rotas do 📰 Boletim do Rigel (relatório em linguagem leiga).

  GET  /api/boletim             - boletim completo (JSON, seções em texto)
  GET  /api/boletim/resumo      - mini-resumo para o card da página inicial

Reutiliza o conhecimento de scripts/boletim_rigel.py (importa as MESMAS
funções — nada duplicado). Nunca falha: se algo estiver ausente, a seção
simplesmente não aparece.
"""
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJETO_ROOT / "scripts"))

router = APIRouter(prefix="/api/boletim", tags=["Boletim do Rigel"])


def _boletim():
    """Importa o script do boletim e monta os dados (fallback seguro)."""
    try:
        import boletim_rigel  # scripts/boletim_rigel.py
        dados = boletim_rigel._montar()
        return dados
    except Exception:
        return {
            "gerado_em": None,
            "secoes": {
                "treino": [],
                "geracao": [],
                "erros": [],
                "saude": [],
                "pendencias": [],
                "pastas": [],
            },
        }


@router.get("")
async def boletim():
    """Boletim completo (todas as seções em texto)."""
    dados = _boletim()
    return JSONResponse(dados)


@router.get("/resumo")
async def resumo():
    """Mini-resumo para o card piscante da página inicial."""
    dados = _boletim()
    secoes = dados.get("secoes", {})

    # Linhas-chave de cada seção (primeira de cada, se existir)
    def primeira(chave):
        for linha in secoes.get(chave, []):
            if linha.strip():
                return linha
        return ""

    treino = primeira("treino")
    geracao = primeira("geracao")
    erros = primeira("erros")
    saude = primeira("saude")
    pendencias = [l for l in secoes.get("pendencias", []) if l.strip()]
    pendentes = len([p for p in pendencias if p.startswith("   •")])

    # Sinais simples para o card
    tem_erro = any("⚠️" in l or "🔴" in l or "erro" in l.lower()
                   for l in secoes.get("erros", []))
    gerando = "em andamento" in geracao.lower() or "rodando" in geracao.lower()
    treinou = "concluído" in treino.lower() or "épocas" in treino.lower()

    return JSONResponse({
        "gerado_em": dados.get("gerado_em"),
        "treino": treino,
        "geracao": geracao,
        "erros": erros,
        "saude": saude,
        "pendentes": pendentes,
        "sinais": {
            "tem_erro": tem_erro,
            "gerando": gerando,
            "treinou": treinou,
        },
    })
