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
    "converter_parquet": {
        "desc": "📦 Converter jsonl → parquet (direto, schema SFT/pretrain)",
        "script": "scripts/converter_jsonl_parquet.py",
        "origem_tipo": "pasta",       # pasta com .jsonl ou arquivo
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
    "avaliar_qualidade": {
        "desc": "⚖️ Ajuizar — avalia qualidade das pastas pendentes (bandeira ✓)",
        "script": "scripts/ajuizar_pastas.py",
        "origem_tipo": "pasta",       # --pasta (opcional; sem = todas pendentes)
    },
    "juizar": {
        "desc": "⚖️ Juiz deepseek nos suspeitos — separa bons (treino) de lixo",
        "script": "scripts/juizar_suspeitos.py",
        "origem_tipo": "pasta",       # --pasta (opcional; sem = todos suspeitos)
    },
    "scrap_livros": {
        "desc": "📚 Scrap de livros/PDFs (PT-BR) — baixa dos sites das listas",
        "script": "scrap_livros_pdf.py",
        "origem_tipo": "pasta",       # origem = URL do site (ou vazio = TODAS as listas)
    },
    "auditar_acervo": {
        "desc": "Auditoria do acervo (TXT/PARQUET — mojibake, status por pasta)",
        "script": "scripts/auditar_acervo.py",
        "origem_tipo": "pasta",       # varre o acervo sozinho (não usa origem)
    },
    "registrar_pastas": {
        "desc": "Registra as pastas de treino por tipo (txt/jsonl/parquet) e lista o que enviar ao Drive",
        "script": "scripts/registrar_pastas.py",
        "origem_tipo": "pasta",       # não usa origem — varre o acervo e atualiza o registro
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

    # ==== MODO "TODOS" ==== (roda a atividade em TODAS as origens pendentes,
    # uma por vez, via pipeline — não tranca, pula erros, mostra % e mural)
    # EXCEÇÃO: scrap_livros NÃO usa pipeline — o próprio script já varre as
    # listas de sites quando não recebe --site.
    origem = (req.origem or "").strip().strip('"').strip("'")
    # 🆕 MULTI-PASTA: lista separada por ';' → pipeline (uma por vez, em série)
    if ";" in origem and chave not in ("scrap_livros",):
        caminhos = [c.strip() for c in origem.split(";") if c.strip()]
        if caminhos:
            pipeline_script = str(BASE_DIR / "scripts" / "executor_pipeline.py")
            comando = ["python", pipeline_script,
                       "--comandos", chave,
                       "--origens", ";".join(caminhos),
                       "--nome", f"{chave} ({len(caminhos)} pastas)",
                       "--mural", str(BASE_DIR / "logs" / "mural_pipeline.json")]
            return await asyncio.to_thread(
                executor.iniciar, comando,
                nome=f"{chave} (multi-pasta)", cwd=str(BASE_DIR))
    if origem.lower() in ("todos", "todas", "*") and chave not in ("scrap_livros", "converter_parquet"):
        pipeline_script = str(BASE_DIR / "scripts" / "executor_pipeline.py")
        comando = ["python", pipeline_script,
                   "--comandos", chave,
                   "--origens", "todos",
                   "--nome", f"{chave} (TODAS as origens)",
                   "--mural", str(BASE_DIR / "logs" / "mural_pipeline.json")]
        return await asyncio.to_thread(
            executor.iniciar, comando, nome=f"{chave} (todas)",
            cwd=str(BASE_DIR))

    # Monta o comando: [python, script, ...args, ...origem]
    comando = ["python", script]
    tipo = info.get("origem_tipo", "pasta")
    if chave == "avaliar_qualidade":
        if not origem or origem.lower() in ("todos", "todas", "*"):
            return {"ok": False,
                    "erro": "Escolha uma pasta já tratada antes de iniciar o ajuizamento."}
        from dashboard.services.qualidade import pode_ajuizar
        pasta_carteira = Path(origem).name
        pronto, faltam = pode_ajuizar(pasta_carteira)
        if not pronto:
            return {"ok": False,
                    "erro": "Ajuizamento bloqueado: faltam as vacinas "
                           + ", ".join(faltam) + "."}
        # ⚖️ Ajuizar: --pasta é OPCIONAL (sem origem = TODAS as pendentes).
        # A origem pode vir como NOME da pasta (ex.: "debates", relativo a
        # dados/gerados/) ou como caminho. Resolve com segurança.
        if origem and origem.lower() not in ("todos", "todas", "*"):
            dados_dir = (BASE_DIR / "dados").resolve()
            # Nome simples (ex.: "debates") → resolve dentro de dados/gerados/
            if not (":" in origem or origem.startswith("\\") or origem.startswith("/")):
                p = (dados_dir / "gerados" / origem).resolve()
            else:
                p = Path(origem).resolve()
            if not (str(p) == str(dados_dir) or str(p).startswith(str(dados_dir) + "\\")):
                return {"ok": False, "erro": "Origem fora da área de dados (dados/)."}
            try:
                rel = p.relative_to(dados_dir)
                # Contrato do ajuizar: --pasta é relativo a dados/gerados/.
                # (Antes passávamos "gerados\<nome>" e o script montava
                #  dados/gerados/gerados/<nome> → pasta não encontrada.)
                try:
                    rel_ger = p.relative_to(dados_dir / "gerados")
                    comando += ["--pasta", str(rel_ger)]
                except Exception:
                    comando += ["--pasta", str(rel)]
            except Exception:
                comando += ["--pasta", str(p)]
        for a in req.args:
            if a and a.lower() in ("--juiz", "-j"):
                comando.append("--juiz")
        return await asyncio.to_thread(
            executor.iniciar, comando, nome=req.nome or "Ajuizar qualidade",
            cwd=str(BASE_DIR))
    if chave == "juizar":
        # ⚖️ Juiz deepseek nos suspeitos pendentes. --pasta é opcional
        # (sem origem = TODOS os suspeitos). Roda com --seco (não pede
        # confirmação no subprocesso — o botão do painel já é a confirmação).
        comando.append("--seco")
        if origem and origem.lower() not in ("todos", "todas", "*"):
            dados_dir = (BASE_DIR / "dados").resolve()
            if not (":" in origem or origem.startswith("\\") or origem.startswith("/")):
                p = (dados_dir / "gerados" / origem).resolve()
            else:
                p = Path(origem).resolve()
            if not (str(p) == str(dados_dir) or str(p).startswith(str(dados_dir) + "\\")):
                return {"ok": False, "erro": "Origem fora da área de dados (dados/)."}
            try:
                rel = p.relative_to(dados_dir)
                try:
                    rel_ger = p.relative_to(dados_dir / "gerados")
                    comando += ["--pasta", str(rel_ger)]
                except Exception:
                    comando += ["--pasta", str(rel)]
            except Exception:
                comando += ["--pasta", str(p)]
        for a in req.args:
            if a and a.startswith("--"):
                comando.append(a)
        return await asyncio.to_thread(
            executor.iniciar, comando, nome=req.nome or "Juiz deepseek",
            cwd=str(BASE_DIR))
    if chave == "scrap_livros":
        # 📚 Scrap de livros: origem = URL do site (ou 'todos' = TODAS as
        # listas, o próprio script varre sites_pdfs.txt + sites_abertos.txt).
        # args livres: --limite N, --verificar, --profundidade N, --delay N.
        if origem and origem.lower() not in ("todos", "todas", "*"):
            comando += ["--site", origem]
        for a in req.args:
            if a:
                comando.append(a)
        return await asyncio.to_thread(
            executor.iniciar, comando, nome=req.nome or "Scrap de livros",
            cwd=str(BASE_DIR))
    if chave == "auditar_acervo":
        # 🔍 Auditoria do acervo (TXT/PARQUET): NÃO usa origem — varre o
        # acervo sozinho e gera relatório (logs/auditoria_acervo.txt/.json).
        for a in req.args:
            if a:
                comando.append(a)
        return await asyncio.to_thread(
            executor.iniciar, comando, nome=req.nome or "Auditar acervo",
            cwd=str(BASE_DIR))
    if chave == "registrar_pastas":
        # Registra pastas por tipo: NÃO usa origem — varre o acervo,
        # atualiza registro_pastas_treino.json e lista o que enviar ao Drive.
        for a in req.args:
            if a:
                comando.append(a)
        return await asyncio.to_thread(
            executor.iniciar, comando, nome=req.nome or "Registrar pastas por tipo",
            cwd=str(BASE_DIR))

    if origem:
        # Validação de segurança: origem dentro de dados/
        try:
            p = Path(origem).resolve()
            dados_dir = (BASE_DIR / "dados").resolve()
            if str(p) != str(dados_dir) and not str(p).startswith(str(dados_dir) + "\\"):
                return {"ok": False, "erro": "Origem fora da área de dados (dados/)."}
            # Valida o TIPO esperado (arquivo vs pasta) — prevê erro do script
            if tipo == "arquivo" and p.is_dir():
                if chave in ("verificar_encoding", "diagnostico_chars"):
                    pass  # scripts universais aceitam PASTA (txt/json/parquet)
                else:
                    # aceita pasta → resolve p/ o 1º .jsonl (conveniência)
                    jsons = sorted(p.glob("*.jsonl"))
                    if not jsons:
                        return {"ok": False,
                                "erro": f"{info['desc']} — a pasta não tem .jsonl na raiz: {origem}"}
                    p = jsons[0]
            if tipo == "pasta" and p.is_file():
                pass  # arquivo único também serve p/ sanitizar
            if chave in ("limpeza_leve", "converter_parquet"):
                comando += ["--origem", str(p)]  # script exige --origem (não posicional)
            else:
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


@router.post("/todas-atividades")
async def todas_atividades(req: dict | None = None):
    """Executa TODAS as atividades (sanitizar → limpeza → verificar →
    diagnostico) sobre TODAS as origens pendentes, UMA POR VEZ (pipeline).
    Não tranca: erros pulam para a próxima origem; progresso real + mural."""
    from dashboard.services import executor
    body = req or {}
    nome = (body.get("nome") or "TODAS as atividades")
    pipeline_script = str(BASE_DIR / "scripts" / "executor_pipeline.py")
    comando = ["python", pipeline_script,
               "--comandos", "tudo",
               "--origens", "todos",
               "--nome", nome,
               "--mural", str(BASE_DIR / "logs" / "mural_pipeline.json")]
    return await asyncio.to_thread(
        executor.iniciar, comando, nome=nome, cwd=str(BASE_DIR))


@router.get("/mural")
async def mural():
    """Lê o mural de resultados do pipeline (logs/mural_pipeline.json)."""
    from dashboard.services import executor
    return executor.ler_mural()


@router.post("/mural/limpar")
async def mural_limpar():
    """Limpa o mural de resultados."""
    from dashboard.services import executor
    return executor.limpar_mural()


@router.get("/status")
async def status(aid: str = ""):
    from dashboard.services import executor
    return executor.status(aid)


@router.get("/avaliacao/pastas")
async def avaliacao_pastas():
    """⚖️ Lista pastas de geração com .txt + bandeira ✓ de verificação."""
    from dashboard.services.avaliacao import listar_pastas
    return listar_pastas()


@router.get("/avaliacao/progresso")
async def avaliacao_progresso():
    """⚖️ Progresso do ajuizamento em andamento."""
    try:
        from pathlib import Path as _P
        caminho = _P(__file__).resolve().parent.parent.parent / "logs" / "ajuizar_progresso.json"
        if caminho.exists():
            import json
            return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"pct": 0, "pasta": None}


@router.post("/avaliacao/desmarcar")
async def avaliacao_desmarcar(req: dict | None = None):
    """⚖️ Remove a bandeira ✓ de uma pasta (p/ re-avaliar)."""
    from dashboard.services.avaliacao import desmarcar
    body = req or {}
    nome = (body.get("pasta") or "").strip() if isinstance(body, dict) else ""
    if not nome:
        return {"ok": False, "erro": "Informe a pasta."}
    return desmarcar(nome)


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


@router.post("/continuar")
async def continuar(req: dict | None = None):
    """Continua por mais 6 tentativas uma atividade que caiu o máximo de
    vezes após reinícios do servidor (status 'aguardando')."""
    from dashboard.services import executor
    body = req or {}
    aid = (body.get("aid") or "").strip() if isinstance(body, dict) else ""
    return executor.continuar_apos_reload(aid)


@router.post("/reiniciar")
async def reiniciar(req: dict | None = None):
    """🔄 Recomeça uma atividade que MORREU ou foi interrompida (mesmo comando,
    nova atividade registrada). Ação prevista/registrada DENTRO do sistema —
    o usuário trata pelo painel /executor."""
    from dashboard.services import executor
    body = req or {}
    aid = (body.get("aid") or "").strip() if isinstance(body, dict) else ""
    return executor.reiniciar(aid)


@router.post("/espaco")
async def espaco(req: dict | None = None):
    """🗑️ Abre espaço no HD: trata dados pendentes (TXT→JSONL, JSONL, PARQUET
    opcional), promove p/ processed e APAGA as origens. Roda como atividade
    do executor (sobrevive a reload, barra de progresso real)."""
    from dashboard.services import executor
    body = req or {}
    script = str(BASE_DIR / "scripts" / "abrir_espaco_hd.py")
    cmd = ["python", script]
    if body.get("simular"):
        cmd.append("--simular")
    if body.get("parquet"):
        cmd.append("--parquet")
    cmd += ["--saida", str(BASE_DIR / "logs" / "espaco_relatorio.json")]
    return await asyncio.to_thread(
        executor.iniciar, cmd, nome="Abrir espaço no HD", cwd=str(BASE_DIR))


@router.post("/limpar")
async def limpar():
    from dashboard.services import executor
    return executor.limpar_buffer()


@router.get("/buffer")
async def buffer_atividade(aid: str = "", linhas: int = 40):
    """Lê a saída de UMA atividade do buffer em DISCO (mesmo após concluir).

    Usado para atividades CONCLUÍDAS/ERRO: o SSE fecha ao terminar, mas o
    resultado real (ex.: '✅ 494 aprovados') continua no buffer em disco.
    Sem o aid, devolve os resumos de todas as atividades.
    """
    from dashboard.services import executor
    if not aid:
        return executor.listar()
    return executor.ler_buffer_disco(aid, linhas=linhas)


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
