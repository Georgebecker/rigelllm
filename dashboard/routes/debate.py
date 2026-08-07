#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
debate.py - Geração de Debates e Podcasts com base factual via DeepSeek
Modos:
  - Debate: dois participantes do MESMO perfil (ex: dois cientistas)
  - Podcast: apresentador fixo "Podcaster" + convidados selecionados
"""
from dashboard.services.limpeza import limpar_e_aviso
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import asyncio
import re
from datetime import datetime

router = APIRouter(prefix="/api/debate", tags=["Debate & Podcast"])

BASE_DIR = Path(__file__).parent.parent.parent
GERADOS_DIR = BASE_DIR / "dados" / "gerados"

# ═══════════════════════════════════════════════
# PERFIS
# ═══════════════════════════════════════════════

PERFIS = {
    "Jornalista": {
        "nome": "📰 Jornalista",
        "descricao": "Linguagem direta, fatos, citações",
        "estilo": "formal e direto, baseado em fatos e dados concretos. Cite fontes.",
        "tamanho": "médio (80-150 palavras)",
        "embasamento": "alto"
    },
    "Filosofo": {
        "nome": "🧠 Filósofo",
        "descricao": "Reflexivo, conceitual, argumentos lógicos",
        "estilo": "reflexivo e conceitual, com argumentos lógicos e questionamentos profundos",
        "tamanho": "médio (80-150 palavras)",
        "embasamento": "médio"
    },
    "Cientista": {
        "nome": "🔬 Cientista",
        "descricao": "Técnico, dados, referências",
        "estilo": "técnico e objetivo, com dados estatísticos, evidências científicas e referências",
        "tamanho": "longo (100-200 palavras)",
        "embasamento": "alto"
    },
    "Jovem": {
        "nome": "🧑‍🎓 Jovem Estudante",
        "descricao": "Coloquial, opiniões, perguntas",
        "estilo": "coloquial e informal, com opiniões sinceras e perguntas curiosas. Use gírias leves.",
        "tamanho": "curto (40-80 palavras)",
        "embasamento": "baixo"
    },
    "Professor": {
        "nome": "👨‍🏫 Professor",
        "descricao": "Didático, exemplos, contextualização",
        "estilo": "didático e explicativo, com exemplos práticos e contextualização histórica",
        "tamanho": "longo (100-200 palavras)",
        "embasamento": "alto"
    },
    "Ativista": {
        "nome": "✊ Ativista",
        "descricao": "Engajado, dados sociais, propostas",
        "estilo": "engajado e persuasivo, com dados sociais, exemplos reais e propostas de ação",
        "tamanho": "médio (80-150 palavras)",
        "embasamento": "médio"
    },
    "Historiador": {
        "nome": "📜 Historiador",
        "descricao": "Contexto histórico, comparações",
        "estilo": "contextualizado historicamente, com comparações entre épocas e análise de tendências",
        "tamanho": "longo (100-200 palavras)",
        "embasamento": "alto"
    },
}

# Perfil fixo do Podcaster
PODCASTER = {
    "nome": "🎙️ Podcaster",
    "estilo": "neutro, curioso e aberto. Faça perguntas claras e incentive os convidados a se aprofundarem. Seja um facilitador da conversa.",
    "tamanho": "curto (20-40 palavras para perguntas)"
}


class GerarDebateRequest(BaseModel):
    modo: str = "debate"  # "debate" ou "podcast"
    perfil: str = "Jornalista"  # para debate = perfil único
    convidados: list[str] = ["Cientista"]  # para podcast = lista de perfis
    tema: str = ""
    turnos: int = 2
    pesquisar: bool = True


@router.get("/perfis")
async def listar_perfis():
    """Retorna a lista de perfis disponíveis com IDs."""
    lista = []
    for key, val in PERFIS.items():
        lista.append({
            "id": key,
            "nome": val["nome"],
            "descricao": val["descricao"],
            "estilo": val["estilo"],
            "tamanho": val["tamanho"],
            "embasamento": val["embasamento"]
        })
    return {"perfis": lista}


@router.post("/gerar")
async def gerar_debate(req: GerarDebateRequest):
    """
    Gera debate ou podcast via DeepSeek com base factual.
    - Debate: dois participantes do mesmo perfil, alternando falas
    - Podcast: apresentador fixo + convidados selecionados
    """
    import sys as _sys
    _sys.path.insert(0, str(BASE_DIR))
    from config import client, MODEL_NAME

    if not client.api_key or client.api_key == "deepseek-aqui":
        return JSONResponse(status_code=400, content={
            "status": "error",
            "message": "DeepSeek API key não configurada no .env"
        })

    tema = req.tema or "um tema da atualidade"
    modo = req.modo if req.modo in ("debate", "podcast") else "debate"
    turnos = min(max(req.turnos, 1), 6)
    usar_pesquisa = req.pesquisar

    print(f"[DEBATE] Modo: {modo} | Tema: {tema} | Turnos: {turnos} | Pesquisa: {usar_pesquisa}")

    # ─── Validações ───
    if modo == "debate":
        if req.perfil not in PERFIS:
            return JSONResponse(status_code=400, content={
                "status": "error", "message": f"Perfil '{req.perfil}' inválido"
            })
        participantes_info = [req.perfil, req.perfil]  # mesmo perfil, duas instâncias
        print(f"[DEBATE] Perfil único: {req.perfil}")

    else:  # podcast
        if not req.convidados:
            return JSONResponse(status_code=400, content={
                "status": "error", "message": "Selecione pelo menos um convidado para o podcast."
            })
        convidados_validos = [p for p in req.convidados if p in PERFIS]
        if not convidados_validos:
            return JSONResponse(status_code=400, content={
                "status": "error", "message": "Nenhum perfil de convidado válido selecionado."
            })
        # Podcaster + convidados
        participantes_info = ["Podcaster"] + convidados_validos
        print(f"[DEBATE] Podcast: Podcaster + {convidados_validos}")

    # ─── 1. Pesquisa web ───
    pesquisas = {}
    try:
        from dashboard.services.pesquisa import pesquisar as pesquisar_svc
        if usar_pesquisa:
            # Perfis únicos para pesquisa
            perfis_para_pesquisar = set()
            if modo == "debate":
                perfis_para_pesquisar.add(req.perfil)
            else:
                for p in convidados_validos:
                    perfis_para_pesquisar.add(p)

            for perfil_id in perfis_para_pesquisar:
                print(f"[DEBATE] 🔍 Pesquisando para '{perfil_id}' sobre: {tema[:50]}...")
                resultado = await asyncio.to_thread(pesquisar_svc, f"{tema} {PERFIS[perfil_id]['nome']}", 4)
                if resultado:
                    pesquisas[perfil_id] = resultado
                    print(f"[DEBATE] ✅ Pesquisa {perfil_id}: {len(resultado)} chars")
                else:
                    pesquisas[perfil_id] = ""
                    print(f"[DEBATE] ⚠️ Sem resultados para {perfil_id}")
        else:
            print("[DEBATE] Pesquisa desativada pelo usuário")
    except Exception as e:
        print(f"[DEBATE] ERRO na pesquisa: {e}")

    sem_pesquisa = usar_pesquisa and not any(pesquisas.values())
    aviso = "\n⚠️ Gerado sem pesquisa externa. Pode conter informações desatualizadas." if sem_pesquisa else ""

    # ─── 2. Geração das falas ───
    falas = []
    fontes_coletadas = set()

    if modo == "debate":
        # Debate: duas instâncias do mesmo perfil, alternando
        perfil_id = req.perfil
        perfil = PERFIS[perfil_id]
        contexto = pesquisas.get(perfil_id, "")

        nomes_debatedores = [f"{perfil['nome']} (A)", f"{perfil['nome']} (B)"]

        for turno in range(turnos):
            for idx in range(2):
                debatedor = nomes_debatedores[idx]
                lado = "A" if idx == 0 else "B"
                oponente = nomes_debatedores[1 - idx]

                # Constrói prompt
                system_extra = ""
                if contexto:
                    system_extra = (
                        f"\n\nBaseie sua fala nas seguintes informações reais (NÃO invente dados):\n"
                        f"{contexto}\n\n"
                        f"Use APENAS fatos do contexto. Se não houver info suficiente, admita."
                    )
                    for linha in contexto.split('\n'):
                        linha = linha.strip()
                        if linha and len(linha) > 30:
                            fontes_coletadas.add(linha[:120])
                else:
                    system_extra = "\n\nATENÇÃO: Você não tem acesso a informações atualizadas. Evite inventar dados."

                system_msg = (
                    f"Você é {debatedor}, um(a) {perfil['nome'].lower()}. {perfil['descricao']}.\n"
                    f"Estilo: {perfil['estilo']}.\n"
                    f"Você está em um DEBATE com {oponente} sobre: {tema}.\n"
                    f"Turno {turno + 1} de {turnos}. Cada fala deve ter {perfil['tamanho']}.{system_extra}"
                )

                user_msg = (
                    f"Considerando o contexto acima, escreva sua fala como {debatedor} "
                    f"no debate com {oponente} sobre '{tema}'. "
                    f"Você PODE discordar de {oponente} e apresentar argumentos contrários, "
                    f"mas sempre com base em fatos. Se for o primeiro turno, faça uma abertura."
                )

                # Chama DeepSeek
                try:
                    response = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": user_msg},
                        ],
                        temperature=0.75 + (idx * 0.05),
                        max_tokens=500,
                        timeout=30
                    )
                    fala = response.choices[0].message.content.strip()
                    fala = limpar_e_aviso(fala, f"Debate {debatedor}")

                    # Valida dados não verificados
                    if not contexto:
                        nums = re.findall(r'\d{4}|\d+%|\d+,\d+', fala)
                        if nums:
                            fala += "\n(Nota: dados nao verificados por falta de pesquisa externa.)"

                    falas.append({
                        "participante": debatedor,
                        "fala": fala,
                        "turno": turno + 1,
                        "tem_pesquisa": bool(contexto)
                    })
                    print(f"[DEBATE] ✅ {debatedor} (turno {turno+1}): {len(fala)} chars")

                except Exception as e:
                    print(f"[DEBATE] ❌ Erro {debatedor}: {e}")
                    falas.append({
                        "participante": debatedor,
                        "fala": f"[Erro ao gerar fala: {str(e)[:100]}]",
                        "turno": turno + 1,
                        "tem_pesquisa": False
                    })

    else:
        # Podcast: Podcaster (fixo) + convidados
        convidados_que_falam = convidados_validos
        nomes_convidados = [PERFIS[p]["nome"] for p in convidados_que_falam]

        for turno in range(turnos):
            # Fala do Podcaster
            contexto_pod = ""
            system_pod = (
                f"Você é {PODCASTER['nome']}, um apresentador de podcast. {PODCASTER['estilo']}\n"
                f"Você está apresentando um podcast sobre: {tema}.\n"
                f"Turno {turno + 1} de {turnos}. Faça perguntas pertinentes aos convidados.\n"
                f"Seus convidados hoje: {', '.join(nomes_convidados)}."
            )

            try:
                resp = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "system", "content": system_pod},
                              {"role": "user", "content": f"Escreva sua fala de abertura ou pergunta como {PODCASTER['nome']} para o turno {turno+1} do podcast sobre '{tema}'. Dirija-se a um ou mais convidados."}],
                    temperature=0.7, max_tokens=300, timeout=30
                )
                fala_pod = resp.choices[0].message.content.strip()
                fala_pod = limpar_e_aviso(fala_pod, "Podcaster")
                falas.append({
                    "participante": PODCASTER['nome'],
                    "fala": fala_pod,
                    "turno": turno + 1,
                    "tem_pesquisa": False
                })
                print(f"[DEBATE] ✅ Podcaster (turno {turno+1}): {len(fala_pod)} chars")
            except Exception as e:
                print(f"[DEBATE] ❌ Erro Podcaster: {e}")

            # Falas dos convidados
            for conv_id in convidados_que_falam:
                conv = PERFIS[conv_id]
                contexto_conv = pesquisas.get(conv_id, "")
                extra_conv = ""
                if contexto_conv:
                    extra_conv = f"\n\nBaseie sua resposta nas seguintes informações reais:\n{contexto_conv}"
                    for linha in contexto_conv.split('\n'):
                        linha = linha.strip()
                        if linha and len(linha) > 30:
                            fontes_coletadas.add(linha[:120])
                else:
                    extra_conv = "\n\nATENÇÃO: Você não tem acesso a informações atualizadas. Evite inventar."

                system_conv = (
                    f"Você é {conv['nome']}, convidado(a) de um podcast. {conv['descricao']}.\n"
                    f"Estilo: {conv['estilo']}. Responda às perguntas do apresentador com clareza.{extra_conv}"
                )

                try:
                    resp = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[{"role": "system", "content": system_conv},
                                  {"role": "user", "content": f"Responda à pergunta do apresentador sobre '{tema}' como {conv['nome']}. Sua fala deve ter {conv['tamanho']}."}],
                        temperature=0.7, max_tokens=500, timeout=30
                    )
                    fala_conv = resp.choices[0].message.content.strip()
                    fala_conv = limpar_e_aviso(fala_conv, f"Podcast {conv['nome']}")
                    if not contexto_conv:
                        nums = re.findall(r'\d{4}|\d+%|\d+,\d+', fala_conv)
                        if nums:
                            fala_conv += "\n(Nota: dados nao verificados por falta de pesquisa externa.)"
                    falas.append({
                        "participante": conv['nome'],
                        "fala": fala_conv,
                        "turno": turno + 1,
                        "tem_pesquisa": bool(contexto_conv)
                    })
                    print(f"[DEBATE] ✅ {conv['nome']} (turno {turno+1}): {len(fala_conv)} chars")
                except Exception as e:
                    print(f"[DEBATE] ❌ Erro {conv['nome']}: {e}")

    # ─── 3. Monta resultado ───
    linhas = []
    if modo == "debate":
        linhas.append("=" * 60)
        linhas.append("🎙️  DEBATE")
        linhas.append("=" * 60)
        linhas.append(f"Tema: {tema}")
        linhas.append(f"Participantes: {PERFIS[req.perfil]['nome']} (A) e {PERFIS[req.perfil]['nome']} (B)")
        linhas.append(f"Turnos: {turnos}")
        if aviso:
            linhas.append(aviso.strip())
        linhas.append("")
        linhas.append("---")

        for turno_num in range(1, turnos + 1):
            linhas.append(f"\n## 🎬 Turno {turno_num}")
            for f in falas:
                if f['turno'] == turno_num:
                    icone = "🔍" if f['tem_pesquisa'] else "💬"
                    linhas.append(f"\n{icone} {f['participante']}:")
                    linhas.append(f['fala'])
                    linhas.append("")
    else:
        linhas.append("=" * 60)
        linhas.append("🎙️  PODCAST")
        linhas.append("=" * 60)
        linhas.append(f"Tema: {tema}")
        linhas.append(f"Apresentador: {PODCASTER['nome']}")
        linhas.append(f"Convidados: {', '.join(nomes_convidados)}")
        linhas.append(f"Turnos: {turnos}")
        if aviso:
            linhas.append(aviso.strip())
        linhas.append("")
        linhas.append("---")

        for turno_num in range(1, turnos + 1):
            linhas.append(f"\n## 🎬 Turno {turno_num}")
            for f in falas:
                if f['turno'] == turno_num:
                    icone = "🔍" if f['tem_pesquisa'] else "🎙️"
                    linhas.append(f"\n{icone} {f['participante']}:")
                    linhas.append(f['fala'])
                    linhas.append("")

    # Fontes consultadas
    if fontes_coletadas:
        linhas.append("\n---\n📚 Fontes consultadas:")
        for fonte in list(fontes_coletadas)[:10]:
            linhas.append(f"- {fonte}")

    resultado = "\n".join(linhas)

    # Limpeza final (redundante, mas garante)
    resultado = limpar_e_aviso(resultado, "Resultado final")

    # ─── 4. Salva ───
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pasta = GERADOS_DIR / "debates"
    pasta.mkdir(parents=True, exist_ok=True)
    nome_arq = f"{modo}_{timestamp}.txt"
    caminho = pasta / nome_arq
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(resultado)

    print(f"[DEBATE] 💾 Salvo: {caminho}")
    print(f"[DEBATE] Total falas: {len(falas)}")

    return {
        "status": "ok",
        "mensagem": f"✅ {modo.capitalize()} gerado com {len(falas)} falas!",
        "titulo": f"🎙️ {'Debate' if modo == 'debate' else 'Podcast'}: {tema[:50]}",
        "resultado": resultado,
        "falas": falas,
        "total_falas": len(falas),
        "modo": modo,
        "aviso_pesquisa": sem_pesquisa,
        "caminho": str(caminho),
        "timestamp": datetime.now().isoformat()
    }
