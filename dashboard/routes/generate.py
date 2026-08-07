#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
generate.py - Geração de dados sintéticos para o Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import subprocess
import asyncio
from datetime import datetime

from dashboard.services.runner import stream_subprocess_to_log
from dashboard.services.limpeza import limpar_e_aviso

router = APIRouter(prefix="/api/generate", tags=["Geração de Dados"])

BASE_DIR = Path(__file__).parent.parent.parent
GERADOS_DIR = BASE_DIR / "dados" / "gerados"
LOGS_DIR = BASE_DIR / "logs"


class ScriptRequest(BaseModel):
    script: str


class DialogosRequest(BaseModel):
    quantidade: int = 100
    tipo: str = "auto"
    tema: str = ""
    formato: str = "txt"            # "txt" | "jsonl" (SFT messages)
    pasta_jsonl: str | None = None   # nome do dataset JSONL (default: dialogos2)


class DialogosV1Request(BaseModel):
    quantidade: int = 100


class GerarAPIRequest(BaseModel):
    tipo: str = "auto"
    tema: str = ""
    quantidade: int = 1


class GerarDebateRequest(BaseModel):
    tema: str = ""
    perfis: list[str] = ["Jornalista", "Cientista"]
    quantidade_turnos: int = 2
    pesquisar: bool = True


# Perfis para debate/podcast
PERFIS_DEBATE = {
    "Jornalista": {
        "id": "Jornalista",
        "nome": "📰 Jornalista",
        "descricao": "Linguagem direta, fatos, citações",
        "estilo": "formal e direto, baseado em fatos e dados concretos. Cite fontes quando possível.",
        "tamanho": "médio (80-150 palavras)",
        "embasamento": "alto"
    },
    "Filósofo": {
        "id": "Filósofo",
        "nome": "🧠 Filósofo",
        "descricao": "Reflexivo, conceitual, argumentos lógicos",
        "estilo": "reflexivo e conceitual, com argumentos lógicos e questionamentos profundos",
        "tamanho": "médio (80-150 palavras)",
        "embasamento": "médio"
    },
    "Cientista": {
        "id": "Cientista",
        "nome": "🔬 Cientista",
        "descricao": "Técnico, dados, referências",
        "estilo": "técnico e objetivo, com dados estatísticos, evidências científicas e referências",
        "tamanho": "longo (100-200 palavras)",
        "embasamento": "alto"
    },
    "Jovem": {
        "id": "Jovem",
        "nome": "🧑‍🎓 Jovem Estudante",
        "descricao": "Coloquial, opiniões, perguntas",
        "estilo": "coloquial e informal, com opiniões sinceras e perguntas curiosas. Use gírias leves.",
        "tamanho": "curto (40-80 palavras)",
        "embasamento": "baixo"
    },
    "Professor": {
        "id": "Professor",
        "nome": "👨‍🏫 Professor",
        "descricao": "Didático, exemplos, contextualização",
        "estilo": "didático e explicativo, com exemplos práticos e contextualização histórica",
        "tamanho": "longo (100-200 palavras)",
        "embasamento": "alto"
    },
    "Ativista": {
        "id": "Ativista",
        "nome": "✊ Ativista",
        "descricao": "Engajado, dados sociais, propostas",
        "estilo": "engajado e persuasivo, com dados sociais, exemplos reais e propostas de ação",
        "tamanho": "médio (80-150 palavras)",
        "embasamento": "médio"
    },
    "Historiador": {
        "id": "Historiador",
        "nome": "📜 Historiador",
        "descricao": "Contexto histórico, comparações",
        "estilo": "contextualizado historicamente, com comparações entre épocas e análise de tendências",
        "tamanho": "longo (100-200 palavras)",
        "embasamento": "alto"
    },
}


def contar_arquivos_gerados():
    """Conta todos os arquivos gerados por categoria (rápido, sem glob)."""
    stats = {}
    if not GERADOS_DIR.exists():
        return stats
    try:
        for nome in os.listdir(str(GERADOS_DIR)):
            pasta = GERADOS_DIR / nome
            if pasta.is_dir() and nome not in ("logs", "estado", "feedback_chat"):
                try:
                    qtde = len(os.listdir(str(pasta)))
                except (PermissionError, OSError):
                    qtde = 0
                if qtde > 0:
                    stats[nome] = qtde
    except Exception:
        pass
    return stats


def _log_comando(comando: str):
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "dashboard.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] {comando}\n")


@router.get("/deepseek-status")
async def deepseek_status():
    """Verifica rapidamente se a chave DeepSeek está configurada (sem diagnóstico completo)."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR))
        from config import API_KEY
        chave = API_KEY or os.environ.get("DEEPSEEK_API_KEY", "")
        ok = bool(chave and chave != "deepseek-aqui" and len(chave) > 10)
        return {"ok": ok, "key_prefix": chave[:8] + "..." if ok else ""}
    except Exception as e:
        return {"ok": False, "erro": str(e)[:100]}


@router.get("/status")
async def generate_status():
    """Status dos dados gerados."""
    # Conta pastas processadas
    processed_dir = BASE_DIR / "dados" / "processed"
    pastas_processed = 0
    if processed_dir.exists():
        for item in processed_dir.iterdir():
            if item.is_dir():
                pastas_processed += 1

    return {
        "arquivos_por_categoria": contar_arquivos_gerados(),
        "total_arquivos": sum(contar_arquivos_gerados().values()),
        "pastas_processed": pastas_processed,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/dialogos")
async def gerar_dialogos(
    req: DialogosV1Request,
    background_tasks: BackgroundTasks,
):
    """Gera diálogos sintéticos (dialogos.py v1)."""
    quantidade = req.quantidade
    cmd = ["python", "dialogos.py", "--quantidade", str(quantidade)]
    _log_comando(f"Gerando dialogos v1: {' '.join(cmd)}")
    log_path = LOGS_DIR / "dialogos.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": f"Geração de {quantidade} diálogos (v1) iniciada"}


@router.post("/dialogos2")
async def gerar_dialogos2(
    req: DialogosRequest,
    background_tasks: BackgroundTasks,
):
    """Gera diálogos sintéticos (dialogos2.py v2 com múltiplos tipos)."""
    quantidade = req.quantidade
    tipo = req.tipo
    formato = req.formato if req.formato in ("txt", "jsonl") else "txt"
    cmd = ["python", "dialogos2.py", "--quantidade", str(quantidade)]
    if tipo and tipo != "auto":
        cmd.extend(["--tipo", tipo])
    if formato == "jsonl":
        cmd.extend(["--formato", "jsonl"])
        if req.pasta_jsonl:
            cmd.extend(["--pasta-jsonl", req.pasta_jsonl])
    _log_comando(f"Gerando dialogos v2 ({formato}): {' '.join(cmd)}")
    log_path = LOGS_DIR / "dialogos.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started",
            "message": f"Geração de {quantidade} diálogos (v2) em {formato} iniciada"}


@router.post("/gerar-api")
async def gerar_via_api(req: GerarAPIRequest):
    """
    Gera conteúdo via DeepSeek API diretamente (sem subprocess).
    Retorna o texto gerado imediatamente.
    """
    try:
        # Importa config (já tem cliente DeepSeek configurado)
        import sys as _sys
        _sys.path.insert(0, str(BASE_DIR))
        from config import client, MODEL_NAME
    except ImportError as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": f"Erro ao carregar config.py: {e}"})

    if not client.api_key or client.api_key == "deepseek-aqui":
        return JSONResponse(status_code=400, content={"status": "error", "message": "DeepSeek API key não configurada no .env"})

    # Determina o tipo e monta o prompt
    tipo = req.tipo or "auto"
    tema = req.tema or "assunto livre"
    quantidade = min(max(req.quantidade, 1), 50)  # Limita entre 1 e 50 por chamada síncrona

    # Templates de prompt por tipo
    PROMPTS = {
        "auto": "Crie um texto diversificado e informativo em português brasileiro sobre: {tema}",
        "dicionario": "Crie uma definição clara e concisa em português brasileiro para: {tema}",
        "pergunta_resposta": "Crie uma pergunta interessante seguida de uma resposta detalhada em português brasileiro sobre: {tema}",
        "iteracao": "Crie um diálogo natural de 5 a 8 turnos em português brasileiro entre duas pessoas discutindo: {tema}",
        "artigo": "Escreva um artigo bem estruturado em português brasileiro sobre: {tema}. Inclua introdução, desenvolvimento e conclusão.",
        "conto": "Escreva um conto curto e envolvente em português brasileiro inspirado em: {tema}",
        "dialogo_profundo": "Crie um diálogo profundo de 10 a 15 turnos em português brasileiro explorando: {tema}",
        "explicacao": "Explique de forma detalhada e didática em português brasileiro: {tema}",
        "resumo": "Faça um resumo claro e conciso em português brasileiro sobre: {tema}",
        "conversa": "Crie uma conversa natural em português brasileiro sobre: {tema}",
        "poema": "Escreva um poema original em português brasileiro sobre: {tema}",
        "carta": "Escreva uma carta em português brasileiro sobre: {tema}",
        "entrevista": "Crie uma entrevista de 5 a 8 perguntas em português brasileiro sobre: {tema}",
        "debate": "Crie um debate com argumentos a favor e contra em português brasileiro sobre: {tema}",
        "tutorial": "Escreva um tutorial passo a passo em português brasileiro explicando: {tema}",
        "resenha": "Escreva uma resenha crítica em português brasileiro sobre: {tema}",
        "relatorio": "Elabore um relatório técnico em português brasileiro sobre: {tema}",
        "ensaio": "Escreva um ensaio reflexivo em português brasileiro sobre: {tema}",
        "cronica": "Escreva uma crônica literária em português brasileiro sobre: {tema}",
        "receita": "Crie uma receita detalhada em português brasileiro para: {tema}",
        "dica": "Escreva uma dica prática e útil em português brasileiro sobre: {tema}",
    }

    prompt_template = PROMPTS.get(tipo, PROMPTS["auto"])
    prompt_texto = prompt_template.format(tema=tema)

    system_msg = "Você é um assistente especializado em gerar conteúdo em português brasileiro para treinamento de modelos de linguagem. Gere textos criativos, bem escritos e gramaticalmente corretos."

    resultados = []
    erros = []

    for i in range(quantidade):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt_texto},
                ],
                temperature=0.7 + (i * 0.05),  # varia leve para não repetir
                max_tokens=2000,
                timeout=60
            )
            texto = response.choices[0].message.content.strip()
            if texto:
                texto = limpar_e_aviso(texto, f"DeepSeek API ({tipo})")
                resultados.append(texto)
        except Exception as e:
            erros.append(f"Item {i+1}: {str(e)[:100]}")
            print(f"[GERAR-API] Erro no item {i+1}: {e}")

    if not resultados:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": f"Nenhum texto gerado. Erros: {'; '.join(erros[:3])}"
        })

    # Salva os resultados
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta_destino = GERADOS_DIR / "api_gerados"
    pasta_destino.mkdir(parents=True, exist_ok=True)

    caminhos = []
    for i, texto in enumerate(resultados):
        nome = f"api_{timestamp}_{i+1:04d}.txt"
        arquivo = pasta_destino / nome
        with open(arquivo, "w", encoding="utf-8") as f:
            f.write(texto)
        caminhos.append(str(arquivo))

    print(f"[GERAR-API] {len(resultados)} texto(s) gerado(s) em {pasta_destino}")

    return {
        "status": "ok",
        "mensagem": f"✅ {len(resultados)} texto(s) gerado(s) com sucesso!",
        "textos": resultados if quantidade <= 3 else resultados[:1],  # Retorna no máximo 1 se for muitos
        "total_gerados": len(resultados),
        "erros": len(erros),
        "caminhos": caminhos[:3],  # Mostra apenas os primeiros caminhos
        "timestamp": datetime.now().isoformat()
    }


@router.get("/perfis-debate")
async def listar_perfis_debate():
    """Retorna a lista de perfis disponíveis para debate/podcast."""
    return {"perfis": list(PERFIS_DEBATE.values())}


@router.post("/gerar-debate")
async def gerar_debate(req: GerarDebateRequest):
    """
    Gera um debate/podcast via DeepSeek com múltiplos perfis e base factual.
    Usa pesquisa na web para embasar as falas de cada participante.
    """
    import sys as _sys
    _sys.path.insert(0, str(BASE_DIR))
    from config import client, MODEL_NAME
    import random

    if not client.api_key or client.api_key == "deepseek-aqui":
        return JSONResponse(status_code=400, content={"status": "error", "message": "DeepSeek API key não configurada"})

    tema = req.tema or "um tema da atualidade"
    perfis_selecionados = [p for p in req.perfis if p in PERFIS_DEBATE]
    if not perfis_selecionados:
        perfis_selecionados = ["Jornalista", "Cientista"]

    turnos = min(max(req.quantidade_turnos, 1), 6)
    usar_pesquisa = req.pesquisar

    print(f"[DEBATE] Tema: {tema} | Perfis: {perfis_selecionados} | Turnos: {turnos} | Pesquisa: {usar_pesquisa}")

    # 1. Pesquisa web para cada perfil (se ativado)
    pesquisas_por_perfil = {}
    try:
        from dashboard.services.pesquisa import pesquisar
        if usar_pesquisa:
            for perfil in perfis_selecionados:
                print(f"[DEBATE] 🔍 Pesquisando para perfil '{perfil}' sobre: {tema[:50]}...")
                resultado = await asyncio.to_thread(pesquisar, f"{tema} {perfil}", 4)
                if resultado:
                    pesquisas_por_perfil[perfil] = resultado
                    print(f"[DEBATE] ✅ Pesquisa para {perfil}: {len(resultado)} chars")
                else:
                    pesquisas_por_perfil[perfil] = ""
                    print(f"[DEBATE] ⚠️ Sem resultados para {perfil}")
        else:
            print("[DEBATE] Pesquisa desativada pelo usuário")
    except Exception as e:
        print(f"[DEBATE] ERRO na pesquisa: {e}")

    aviso_pesquisa = ""
    if not pesquisas_por_perfil and usar_pesquisa:
        aviso_pesquisa = "\n⚠️ Gerado sem pesquisa externa. Pode conter informações desatualizadas."

    # 2. Gera falas para cada perfil
    falas = []
    fontes_consultadas = set()

    for turno in range(turnos):
        for perfil_id in perfis_selecionados:
            perfil = PERFIS_DEBATE[perfil_id]
            contexto_pesquisa = pesquisas_por_perfil.get(perfil_id, "")

            # Monta o prompt para este perfil neste turno
            system_msg = (
                f"Você é {perfil['nome']}. {perfil['descricao']}.\n"
                f"Estilo: {perfil['estilo']}.\n"
                f"Tamanho da fala: {perfil['tamanho']}.\n"
                f"Participe de um debate/podcast sobre: {tema}.\n"
                f"Turno {turno + 1} de {turnos}."
            )

            instrucao_adicional = ""
            if contexto_pesquisa:
                instrucao_adicional = (
                    f"\n\nBaseie sua fala nas seguintes informações reais (NÃO invente dados):\n"
                    f"{contexto_pesquisa}\n\n"
                    f"Use APENAS informações deste contexto. Se não houver informação suficiente, "
                    f"diga: 'Não tenho informações suficientes para responder com base em fatos sobre este tópico.'\n"
                    f"NÃO crie números, datas ou nomes que não estejam no contexto acima."
                )
                # Extrai trechos para a seção de fontes
                for linha in contexto_pesquisa.split('\n'):
                    linha = linha.strip()
                    if linha and not linha.startswith('-') and len(linha) > 30:
                        fontes_consultadas.add(linha[:100])
            else:
                instrucao_adicional = (
                    f"\n\nATENÇÃO: Você NÃO tem acesso a informações atualizadas sobre este tópico. "
                    f"Seja honesto sobre suas limitações e evite inventar dados específicos."
                )

            user_msg = (
                f"Considerando o contexto acima, escreva sua fala como {perfil['nome']} "
                f"no debate sobre '{tema}'. "
                f"Siga o estilo: {perfil['estilo']}. "
                f"Tamanho: {perfil['tamanho']}."
            )

            try:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_msg + instrucao_adicional},
                        {"role": "user", "content": user_msg},
                    ],
                    temperature=0.7,
                    max_tokens=500,
                    timeout=30
                )
                fala = response.choices[0].message.content.strip()

                # Validação básica: se citou números/datas sem pesquisa, marca como suspeito
                if not contexto_pesquisa:
                    import re
                    numeros = re.findall(r'\d{4}|\d+%|\d+,\d+|\d+\.\d+', fala)
                    if numeros:
                        print(f"[DEBATE] ⚠️ Fala de {perfil_id} contém números sem pesquisa: {numeros[:3]}")
                        fala += "\n\n⚠️ (Nota: esta fala contém dados que não puderam ser verificados por falta de pesquisa externa.)"

                falas.append({
                    "perfil": perfil_id,
                    "perfil_nome": perfil['nome'],
                    "fala": fala,
                    "turno": turno + 1,
                    "tem_pesquisa": bool(contexto_pesquisa)
                })
                print(f"[DEBATE] ✅ Fala de {perfil_id} (turno {turno+1}): {len(fala)} chars")

            except Exception as e:
                print(f"[DEBATE] ❌ Erro ao gerar fala de {perfil_id}: {e}")
                falas.append({
                    "perfil": perfil_id,
                    "perfil_nome": perfil['nome'],
                    "fala": f"[Fala não pôde ser gerada: {str(e)[:100]}]",
                    "turno": turno + 1,
                    "tem_pesquisa": False
                })

    # 3. Monta resultado formatado
    linhas_resultado = []
    linhas_resultado.append(f"{'='*60}")
    linhas_resultado.append(f"🎙️ DEBATE / PODCAST")
    linhas_resultado.append(f"{'='*60}")
    linhas_resultado.append(f"Tema: {tema}")
    linhas_resultado.append(f"Participantes: {', '.join(PERFIS_DEBATE[p]['nome'] for p in perfis_selecionados)}")
    linhas_resultado.append(f"Turnos: {turnos}")
    if aviso_pesquisa:
        linhas_resultado.append(aviso_pesquisa.strip())
    linhas_resultado.append("")
    linhas_resultado.append("---")

    # Organiza falas por turno
    from itertools import groupby
    falas_por_turno = {}
    for f in falas:
        t = f['turno']
        if t not in falas_por_turno:
            falas_por_turno[t] = []
        falas_por_turno[t].append(f)

    for turno_num in sorted(falas_por_turno.keys()):
        linhas_resultado.append(f"\n## 🎬 Turno {turno_num}")
        for fala_data in falas_por_turno[turno_num]:
            pesquisa_icon = "🔍" if fala_data['tem_pesquisa'] else "⚠️"
            linhas_resultado.append(f"\n{pesquisa_icon} {fala_data['perfil_nome']}:")
            linhas_resultado.append(fala_data['fala'])
            linhas_resultado.append("")

    # Fontes consultadas
    if fontes_consultadas:
        linhas_resultado.append("\n---\n📚 Fontes consultadas:")
        for fonte in list(fontes_consultadas)[:10]:
            linhas_resultado.append(f"- {fonte}")

    resultado = "\n".join(linhas_resultado)

    # 4. Salva o debate em arquivo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta_debates = GERADOS_DIR / "debates"
    pasta_debates.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"debate_{timestamp}.txt"
    caminho = pasta_debates / nome_arquivo
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(resultado)

    print(f"[DEBATE] 💾 Salvo em: {caminho}")
    print(f"[DEBATE] Total falas: {len(falas)} | Pesquisas: {len(pesquisas_por_perfil)} perfis")

    return {
        "status": "ok",
        "mensagem": f"✅ Debate gerado com {len(falas)} falas de {len(perfis_selecionados)} perfil(is)!",
        "titulo": f"🎙️ Debate: {tema[:60]}",
        "resultado": resultado,
        "falas": falas,
        "total_falas": len(falas),
        "perfis_usados": perfis_selecionados,
        "pesquisas_realizadas": len(pesquisas_por_perfil),
        "aviso_pesquisa": bool(aviso_pesquisa),
        "caminho": str(caminho),
        "timestamp": datetime.now().isoformat()
    }


@router.post("/downdata")
async def baixar_dados(
    background_tasks: BackgroundTasks,
):
    """Baixa datasets públicos (downdata.py)."""
    cmd = ["python", "downdata.py"]
    _log_comando(f"Baixando datasets: {' '.join(cmd)}")
    log_path = LOGS_DIR / "downdata.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": "Download de datasets iniciado"}


@router.post("/download_datasets")
async def download_datasets(
    background_tasks: BackgroundTasks,
):
    """Baixa datasets (download_datasets.py)."""
    cmd = ["python", "download_datasets.py"]
    _log_comando(f"Download datasets: {' '.join(cmd)}")
    log_path = LOGS_DIR / "download_datasets.log"
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": "Download de datasets (alternativo) iniciado"}


@router.post("/executar")
async def executar_script(
    req: ScriptRequest,
    background_tasks: BackgroundTasks,
):
    """Executa um script Python local (preparar_dados.py, agrupar.py, ultra.py)."""
    script_path = BASE_DIR / req.script
    if not script_path.exists():
        return JSONResponse(status_code=400, content={"status": "error", "message": f"Script {req.script} não encontrado"})

    # Define argumentos padrão conforme o script
    nome = req.script.lower()
    if "agrupar" in nome:
        cmd = ["python", req.script,
               "--entrada", str(GERADOS_DIR),
               "--saida", str(GERADOS_DIR / "agrupados"),
               "--pares", "500"]
        _log_comando(f"Agrupando arquivos pequenos de {GERADOS_DIR} -> {GERADOS_DIR/'agrupados'}")
    elif "preparar" in nome:
        cmd = ["python", req.script, "--qualificar"]
        _log_comando(f"Preparando dados: qualificar + copiar para dados/processed")
    elif "ultra" in nome:
        cmd = ["python", req.script,
               "--shard-size", "5000",
               "--checkpoint-interval", "100"]
        _log_comando(f"Executando ultra-processamento")
    else:
        cmd = ["python", req.script]
        _log_comando(f"Executando script local: {' '.join(cmd)}")

    log_path = LOGS_DIR / "scripts.log"
    # Escreve o comando no log ANTES de executar
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] >>> CMD: {' '.join(cmd)}\n")
    background_tasks.add_task(stream_subprocess_to_log, cmd, BASE_DIR, log_path)
    return {"status": "started", "message": f"✅ {req.script} iniciado", "comando": ' '.join(cmd)}
