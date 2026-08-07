#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
executor.py (rotas) — Dashboard como executor de comandos no backend.

Pedido do usuário (05/08): "o dashboard pode e deve ser capaz de rodar comando
no backend, mantendo canal de comunicação, recebendo resultados/informações."

Endpoints:
  POST /api/executor/iniciar        {comando: [...], nome, cwd, resultado_path}
  GET  /api/executor/status         estado + buffer de saída
  POST /api/executor/parar          para o processo
  GET  /api/executor/stream         SSE — streaming ao vivo da saída
  POST /api/executor/limpar         limpa o buffer de log
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/executor", tags=["Executor"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Whitelist de comandos permitidos (SEGURANÇA: o dashboard não roda qualquer coisa).
# Cada entrada: (nome exibido, subpasta permitida, [prefixos de script permitidos])
# Comandos livres são bloqueados; só scripts do projeto são executáveis.
COMANDOS_PERMITIDOS = {
    "sanitizar": {
        "desc": "Sanitizar dataset (PT-BR, gera rigelsanitizadoNN.jsonl)",
        "script": "scripts/gerar_sanitizados.py",
        "origem_tipo": "pasta",       # aceita pasta OU arquivo .jsonl
    },
    "limpeza_leve": {
        "desc": "Limpeza leve (pipeline v2: SFT+Pretrain, .parquet)",
        "script": "limpeza_leve_rigel_v2.py",
        "origem_tipo": "pasta",       # aceita pasta OU arquivo
    },
    "verificar_encoding": {
        "desc": "Verificar encoding/mojibake de um dataset",
        "script": "scripts/verificar_encoding_jsonl.py",
        "origem_tipo": "arquivo",     # espera UM arquivo .jsonl
    },
    "diagnostico_chars": {
        "desc": "Diagnóstico de caracteres removíveis (calibração ABNT2)",
        "script": "scripts/diagnostico_chars.py",
        "origem_tipo": "arquivo",     # espera UM arquivo .jsonl
    },
}


class ExecutarRequest(BaseModel):
    comando: str = ""            # nome do comando permitido (whitelist)
    args: list[str] = []         # argumentos livres (ex.: origem, flags)
    origem: str = ""             # conveniência: path de dataset (validado em dados/)
    nome: str = ""               # rótulo
    resultado_path: str = ""     # onde o script grava o JSON de resultado


@router.post("/iniciar")
async def iniciar(req: ExecutarRequest):
    from dashboard.services import executor
    chave = (req.comando or "").strip().lower()
    if chave not in COMANDOS_PERMITIDOS:
        return JSONResponse(
            {"ok": False, "erro": f"Comando não permitido. Disponível: "
                                  f"{', '.join(COMANDOS_PERMITIDOS)}."},
            status_code=400)

    info = COMANDOS_PERMITIDOS[chave]
    script = str(BASE_DIR / info["script"])
    if not Path(script).exists():
        return {"ok": False, "erro": f"Script não encontrado: {info['script']}"}

    # Monta o comando: [python, script, ...args, ...origem]
    comando = ["python", script]
    origem = (req.origem or "").strip().strip('"').strip("'")
    tipo = info.get("origem_tipo", "pasta")
    if origem:
        # Validação de segurança: origem dentro de dados/
        try:
            p = Path(origem).resolve()
            dados_dir = (BASE_DIR / "dados").resolve()
            if str(p) != str(dados_dir) and not str(p).startswith(str(dados_dir) + "\\"):
                return {"ok": False, "erro": "Origem fora da área de dados (dados/)."}
            # Valida o TIPO esperado (arquivo vs pasta) — prevê erro do script
            if tipo == "arquivo" and p.is_dir():
                # aceita pasta → resolve p/ o 1º .jsonl (conveniência)
                jsons = sorted(p.glob("*.jsonl"))
                if not jsons:
                    return {"ok": False,
                            "erro": f"{info['desc']} — a pasta não tem .jsonl na raiz: {origem}"}
                p = jsons[0]
            if tipo == "pasta" and p.is_file():
                pass  # arquivo único também serve p/ sanitizar
            comando.append(str(p))
        except Exception as e:
            return {"ok": False, "erro": f"Caminho inválido: {e}"}
    elif any(a and not a.startswith("-") for a in req.args):
        pass  # origem veio pelos args livres
    else:
        return {"ok": False, "erro": f"{info['desc']} — informe a origem (pasta/arquivo .jsonl)."}
    for a in req.args:
        if a and not a.startswith("-") and origem and Path(a).exists():
            continue  # evita duplicar origem
        comando.append(a)

    rp = req.resultado_path or None
    nome = req.nome or chave
    return await asyncio.to_thread(
        executor.iniciar, comando, nome=nome,
        cwd=str(BASE_DIR), resultado_path=rp)


@router.get("/status")
async def status(aid: str = ""):
    from dashboard.services import executor
    return executor.status(aid)


@router.get("/origens")
async def origens():
    """Lista origens de sanitização disponíveis (dropdown automático).

    O usuário NÃO digita caminho (celular/TV, regra 05/08): escolhe no
    dropdown. O que já foi sanitizado aparece com flag `sanitizado: true`
    (o frontend pode desabilitar para não repetir).
    """
    from dashboard.services import executor
    return executor.listar_origens()


@router.post("/parar")
async def parar(req: dict | None = None):
    """Para uma atividade (aid) ou todas (se vazio)."""
    from dashboard.services import executor
    body = req or {}
    aid = (body.get("aid") or "").strip() if isinstance(body, dict) else ""
    return executor.parar(aid)


@router.post("/limpar")
async def limpar():
    from dashboard.services import executor
    return executor.limpar_buffer()


@router.post("/limpar-historico")
async def limpar_historico():
    from dashboard.services import executor
    return executor.limpar_historico()


@router.get("/stream")
async def stream(aid: str = ""):
    """SSE — canal de comunicação em tempo real da saída de UMA atividade.

    O frontend lê as linhas do buffer via EventSource; a cada 1s envia as
    linhas novas (se houver) + keep-alive. Ao terminar, envia [FIM].
    """
    from dashboard.services import executor

    async def gerar():
        if not aid:
            # Sem id: envia o resumo (todas as atividades) periodicamente
            yield "data: " + json.dumps({"resumo": _resumo_sem_mensagens(),
                                         "fim": False}) + "\n\n"
            while True:
                await asyncio.sleep(2)
                yield "data: " + json.dumps({"resumo": _resumo_sem_mensagens(),
                                             "fim": False}) + "\n\n"
            return

        enviadas = 0
        while True:
            linhas = executor.stream_linhas(aid)
            if len(linhas) > enviadas:
                novas = linhas[enviadas:]
                enviadas = len(linhas)
                yield "data: " + json.dumps({"linhas": novas, "fim": False}) + "\n\n"
            else:
                est = executor.status(aid)
                if isinstance(est, dict) and est.get("ok") is False:
                    yield "data: " + json.dumps({"linhas": [], "fim": True,
                                                 "status": "inexistente",
                                                 "erro": est.get("erro")}) + "\n\n"
                    break
                if not est.get("rodando"):
                    yield "data: " + json.dumps({
                        "linhas": [], "fim": True,
                        "status": est.get("status"),
                        "exit_code": est.get("exit_code"),
                        "resultado": est.get("resultado"),
                        "erro": est.get("erro"),
                    }) + "\n\n"
                    break
            yield "data: " + json.dumps({"linhas": [], "fim": False}) + "\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(gerar(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _resumo_sem_mensagens() -> dict:
    """Resumo das atividades (sem os buffers grandes) para o SSE global."""
    from dashboard.services import executor
    r = executor.listar()
    for a in r.get("atividades", []):
        a.pop("mensagens", None)
    return r
