#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
treino_local.py - Rotas da API de treino local (CPU/GPU) com bandeiras.
Versão: 1.0.0 | Data: 02/08/2026

  GET  /api/treino_local/datasets          - lista datasets com contagem de bandeiras
  GET  /api/treino_local/arquivos?dataset= - lista arquivos de um dataset com bandeiras
  POST /api/treino_local/iniciar           - inicia treino de um arquivo (subprocesso)
  GET  /api/treino_local/status            - estado + mensagens de treino em tempo real
  POST /api/treino_local/parar             - para o treino em andamento (sem marcar)
  POST /api/treino_local/batch             - inicia FILA de treino (pasta, modo, horas)
  POST /api/treino_local/pausar            - pausa a fila (cria PAUSA_SEGURA.txt)
  POST /api/treino_local/retomar           - retoma a fila pausada (--resume)
"""
from fastapi import APIRouter
from pydantic import BaseModel

from dashboard.services import treino_local
import modelo_backup

router = APIRouter(prefix="/api/treino_local", tags=["Treino Local"])


class IniciarRequest(BaseModel):
    dataset: str
    arquivo: str
    epochs: int | None = None
    max_exemplos: int | None = None
    pular_treinados: int = 0   # pula se já treinado N+ vezes
    forcar: bool = False       # ignora a regra de já treinado


class BatchRequest(BaseModel):
    pasta: str                # nome do dataset (das bases) ou caminho da pasta
    modo: str = "all"         # all|time|pause | aliases: completo/tempo/arquivo
    limite_horas: float | None = None
    resume: bool = False
    epocas_por_arquivo: int = 5   # épocas em cada arquivo da fila
    pular_treinados: int = 0   # pula arquivos já treinados N+ vezes
    forcar: bool = False       # ignora a regra de já treinado


class MoverRequest(BaseModel):
    dataset: str


class PromoverRequest(BaseModel):
    dataset: str
    remover_invalidos: bool = False


class RestaurarRequest(BaseModel):
    arquivo: str


@router.get("/datasets")
async def datasets():
    """Datasets explodidos com contagem de bandeiras (nenhuma/branca/amarela/vermelha).

    Rápido: usa o CACHE persistente em disco (último escaneamento).
    Se não houver cache ainda, dispara um escaneamento em background e
    retorna o que tiver (possivelmente vazio + status de progresso).
    """
    # Se há cache válido, responde na hora (a tela abre instantânea).
    lista = treino_local.listar_datasets(usar_cache=True)
    status = treino_local.status_escaneamento()
    if lista:
        return {"datasets": lista, "scan": status, "cache": True}
    # Sem cache: inicia o escaneamento em thread e responde com progresso.
    inicio = treino_local.iniciar_escaneamento_estrutura()
    return {"datasets": [], "scan": treino_local.status_escaneamento(),
            "cache": False, "iniciado": inicio}


@router.post("/reescanear")
async def reescanear():
    """Dispara (ou relança) o escaneamento da estrutura em segundo plano."""
    return treino_local.iniciar_escaneamento_estrutura()


@router.get("/reescanear/status")
async def reescanear_status():
    """Progresso do escaneamento (para a barra de % no frontend)."""
    return treino_local.status_escaneamento()


@router.get("/arquivos")
async def arquivos(dataset: str):
    """Arquivos de um dataset com a bandeira atual de cada um."""
    return {"dataset": dataset, "arquivos": treino_local.listar_arquivos(dataset)}


@router.post("/iniciar")
async def iniciar(req: IniciarRequest):
    """Inicia o treino de um arquivo (CPU se não houver GPU)."""
    return treino_local.iniciar_treino(req.dataset, req.arquivo,
                                       epochs=req.epochs,
                                       max_exemplos=req.max_exemplos,
                                       pular_treinados=req.pular_treinados,
                                       forcar=req.forcar)


@router.post("/batch")
async def batch(req: BatchRequest):
    """Inicia uma FILA de treinamento: todos os .jsonl de uma pasta, um por vez.

    Modos: 'all'/'completo'/'arquivo' (até acabar) | 'time'/'tempo' (X horas) |
    'pause' (para ao detectar PAUSA_SEGURA.txt). O modelo é salvo entre arquivos,
    o LR é reiniciado por arquivo e o progresso fica em modelo/estado_fila.json
    (retomável com resume=true).
    """
    return treino_local.iniciar_batch(req.pasta, req.modo,
                                      req.limite_horas, req.resume,
                                      pular_treinados=req.pular_treinados,
                                      forcar=req.forcar,
                                      epocas_por_arquivo=req.epocas_por_arquivo)


@router.post("/pausar")
async def pausar():
    """Pausa a fila em andamento (cria PAUSA_SEGURA.txt — a fila termina o
    arquivo atual, salva o modelo e para)."""
    return treino_local.pausar_fila()


@router.post("/retomar")
async def retomar():
    """Retoma a fila pausada (remove o marcador e reinicia com --resume,
    continuando do arquivo onde parou)."""
    return treino_local.retomar_fila()


@router.get("/status")
async def status():
    """Estado atual do treino + buffer de mensagens em tempo real."""
    return treino_local.get_estado()


@router.post("/mover")
async def mover(req: MoverRequest):
    """Move um dataset validado de gerados/jsonl para dados/processed (flags seguem)."""
    return treino_local.mover_para_processed(req.dataset)


@router.post("/promover")
async def promover(req: PromoverRequest):
    """Valida e copia somente os arquivos VÁLIDOS para dados/processed/jsonl/."""
    return treino_local.promover_para_processed(req.dataset,
                                                remover_invalidos=req.remover_invalidos)


@router.post("/parar")
async def parar():
    """Para o treino em andamento (o arquivo NÃO é marcado como treinado)."""
    return treino_local.parar_treino()


# ============================================================================
# 💾 Backups do modelo (nunca perca o modelo.pt)
# ============================================================================

@router.get("/backups")
async def backups():
    """Lista os backups disponíveis em modelo/backups/."""
    return {"backups": modelo_backup.listar_backups()}


@router.post("/backup_criar")
async def backup_criar():
    """Faz um backup manual dos modelos atuais."""
    return modelo_backup.criar_backup(motivo="manual")


@router.post("/backup_restaurar")
async def backup_restaurar(req: RestaurarRequest):
    """Restaura um backup (guarda o modelo atual antes, por segurança)."""
    return modelo_backup.restaurar_backup(req.arquivo)
