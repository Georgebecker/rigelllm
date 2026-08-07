#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
datasets.py - Busca e download de datasets JSONL (PT-BR) do HuggingFace
Versão: 1.0.0 | Data: 01/08/2026

Endpoints:
  GET  /api/datasets/buscar?q=...     - Pesquisa datasets no HuggingFace
  POST /api/datasets/baixar           - Baixa e explode um dataset (background)
  GET  /api/datasets/status           - Progresso do download em andamento
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import asyncio
import json

from dashboard.services import hf_datasets

router = APIRouter(prefix="/api/datasets", tags=["Datasets HF"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class BaixarRequest(BaseModel):
    repo_id: str
    max_total: int | None = None
    tratamento: str = "auto"  # auto (detecta formato) | sanitizar | limpeza_leve | nenhum


class CancelarRequest(BaseModel):
    apagar: bool = True  # remove a pasta raw/<repo> (parcial/completo) para liberar espaço


class ApagarRequest(BaseModel):
    repo_id: str = ""
    dataset: str = ""


class ExplodirRequest(BaseModel):
    acao: str = "status"   # iniciar | pausar | retomar | parar | status
    caminho: str = ""
    repo: str = ""
    nome: str = ""


@router.get("/buscar")
async def buscar(q: str = "portuguese instruction", limite: int = 10):
    """Pesquisa datasets no HuggingFace Hub."""
    q = (q or "").strip()
    if not q:
        q = hf_datasets.TERMOS_PADRAO[0]
    resultados = hf_datasets.buscar_datasets(q, limite=max(1, min(50, limite)))
    return {"q": q, "total": len(resultados), "resultados": resultados}


@router.get("/tamanho")
async def tamanho(repo: str = ""):
    """Tamanho real (MB) de um dataset do HuggingFace (datasets-server)."""
    repo = (repo or "").strip()
    if not repo:
        return {"ok": False, "erro": "repo é obrigatório."}
    return await asyncio.to_thread(hf_datasets.tamanho_repo, repo)


@router.post("/limpar")
async def limpar():
    """Esquece o último download/tratamento (reset p/ idle).
    O pipeline 05 (origens limpas) também chama isso automaticamente."""
    return await asyncio.to_thread(hf_datasets.limpar)


@router.post("/cancelar")
async def cancelar(req: CancelarRequest):
    """Cancela/libera um download travado ou em andamento (reset idle).
    apagar=True (padrão) remove a pasta raw/<repo> para liberar espaço e
    permitir recomeçar — libera o botão Baixar mesmo se o thread pendurou."""
    return await asyncio.to_thread(hf_datasets.cancelar, req.apagar)


@router.post("/baixar")
async def baixar(req: BaixarRequest):
    """Baixa e explode um dataset do HuggingFace (em segundo plano).
    tratamento="auto" (padrão) detecta o formato e aplica o tratamento certo:
    parquet→limpeza leve v2, jsonl→sanitizar PT-BR + promoção p/ processed."""
    repo_id = (req.repo_id or "").strip()
    if not repo_id:
        return JSONResponse({"ok": False, "erro": "repo_id é obrigatório."}, status_code=400)
    return hf_datasets.baixar_e_explodir(repo_id, max_total=req.max_total,
                                         tratamento=req.tratamento)


@router.get("/status")
async def status():
    """Retorna o progresso do download em andamento (ou o último resultado)."""
    return hf_datasets.get_estado()


@router.get("/listar")
async def listar():
    """Lista os datasets já explodidos em dados/gerados/jsonl/ (subpastas).

    Só mostra pastas que realmente contêm .jsonl — pastas vazias (explosão
    abortada, 'perdidos', etc.) ficam OCULTAS da listagem.
    """
    base = BASE_DIR / "dados" / "gerados" / "jsonl"
    itens = []
    if base.exists():
        for item in sorted(base.iterdir()):
            if not item.is_dir():
                continue
            arquivos = list(item.glob("**/*.jsonl"))
            if not arquivos:
                continue  # pasta sem nenhum jsonl não aparece
            itens.append({
                "nome": item.name,
                "arquivos": len(arquivos),
                "caminho": str(item.relative_to(BASE_DIR)),
            })
    return {"total": len(itens), "datasets": itens}


@router.get("/baixados")
async def baixados():
    """Lista os datasets baixados (dados/raw)."""
    base = BASE_DIR / "dados" / "raw"
    itens = []
    if base.exists():
        for item in sorted(base.iterdir()):
            if not item.is_dir():
                continue
            tamanho_mb = None
            try:
                tamanho_mb = round(
                    sum(f.stat().st_size for f in item.rglob("*") if f.is_file()) / 1024 / 1024, 1)
            except Exception:
                pass
            tem_jsonl = (item / "dataset.jsonl").exists()
            itens.append({
                "nome": item.name,
                "tamanho_mb": tamanho_mb,
                "tem_jsonl": tem_jsonl,
                "caminho": str(item),
            })
    return {"total": len(itens), "baixados": itens}


@router.post("/explodir")
async def explodir(req: ExplodirRequest):
    """Explosão CONTROLADA de um dataset baixado (raw → gerados).

    Ações: iniciar (estima antes: espaço/tempo na máquina), pausar, retomar, parar.
    Estado + linha do tempo em estado/explosao_estado.json e logs/explosao.log.
    """
    from dashboard.services import explosao_local
    acao = (req.acao or "status").strip().lower()
    if acao == "iniciar":
        caminho = (req.caminho or "").strip()
        if not caminho and req.repo:
            caminho = str(BASE_DIR / "dados" / "raw" / req.repo.replace("/", "_") / "dataset.jsonl")
        if not caminho:
            return {"ok": False, "erro": "Informe caminho (ou repo) para explodir."}
        return await asyncio.to_thread(
            explosao_local.iniciar, caminho, repo=req.repo, nome=req.nome)
    if acao == "pausar":
        return explosao_local.pausar()
    if acao == "retomar":
        return explosao_local.retomar()
    if acao == "parar":
        return explosao_local.parar()
    if acao == "limpar":
        return explosao_local.limpar()
    return explosao_local.status()


@router.get("/explodir/status")
async def explodir_status():
    from dashboard.services import explosao_local
    return explosao_local.status()


class SanitizarRequest(BaseModel):
    acao: str = "status"   # iniciar | parar | status
    origem: str = ""       # pasta ou arquivo .jsonl (validado dentro de dados/)
    saida_dir: str = ""    # opcional (default: dados/sanitizados)
    exemplos_por_arquivo: int = 1000
    max_arquivos: int | None = None


@router.post("/sanitizar")
async def sanitizar(req: SanitizarRequest):
    """Sanitização CONTROLADA (PT-BR): corrige mojibake, remove inválidos,
    descarta não-português e grava rigelsanitizadoNN.jsonl em dados/sanitizados.

    Ações: iniciar | parar | status. Estado + linha do tempo em
    estado/sanitizacao_estado.json e logs/sanitizacao.log.
    """
    from dashboard.services import sanitizacao
    acao = (req.acao or "status").strip().lower()
    if acao == "iniciar":
        origem = (req.origem or "").strip()
        if not origem:
            return {"ok": False, "erro": "Informe a origem (pasta ou arquivo .jsonl)."}
        # Validação de segurança: origem deve estar dentro de dados/
        try:
            p = Path(origem).resolve()
            dados_dir = (BASE_DIR / "dados").resolve()
            if str(p) != str(dados_dir) and not str(p).startswith(str(dados_dir) + "\\"):
                return {"ok": False, "erro": "Origem fora da área de dados (dados/)."}
        except Exception as e:
            return {"ok": False, "erro": f"Caminho inválido: {e}"}
        return await asyncio.to_thread(
            sanitizacao.iniciar, origem, saida_dir=req.saida_dir,
            exemplos_por_arquivo=req.exemplos_por_arquivo,
            max_arquivos=req.max_arquivos)
    if acao == "parar":
        return sanitizacao.parar()
    if acao == "limpar":
        return sanitizacao.limpar()
    return sanitizacao.status()


@router.get("/sanitizar/status")
async def sanitizar_status():
    from dashboard.services import sanitizacao
    return sanitizacao.status()


@router.post("/apagar")
async def apagar(req: ApagarRequest):
    """Apaga os arquivos de um dataset que FALHOU na explosão (não serve p/ treino).

    Procedimento lógico: apaga dados/raw/<repo> (parquet + dataset.jsonl) e a pasta
    explodida vazia em dados/gerados/jsonl/<dataset>. Depois limpa o estado persistido.
    O usuário confirma digitando APAGAR no frontend.
    """
    import shutil
    repo_id = (req.repo_id or "").strip()
    dataset = (req.dataset or "").strip()
    removidos = []
    if repo_id:
        nome_pasta = repo_id.replace("/", "_")
        p_raw = BASE_DIR / "dados" / "raw" / nome_pasta
        if p_raw.exists():
            shutil.rmtree(p_raw, ignore_errors=True)
            removidos.append(f"dados/raw/{nome_pasta}")
    if dataset:
        p_ger = BASE_DIR / "dados" / "gerados" / "jsonl" / dataset
        if p_ger.exists():
            shutil.rmtree(p_ger, ignore_errors=True)
            removidos.append(f"dados/gerados/jsonl/{dataset}")
    # Limpa o estado persistido se for o mesmo repositório
    if hf_datasets.get_estado().get("repo") == repo_id:
        hf_datasets._atualizar_estado(
            rodando=False, repo=None, etapa="idle", mensagem="", percentual=None,
            inicio=None, fim=None, total_exemplos=0, total_arquivos=0,
            total_pastas=0, erro=None, diagnostico=None)
    return {"ok": True, "removidos": removidos, "detalhe": "Arquivos temporários (raw) e pasta explodida removidos do PC."}
