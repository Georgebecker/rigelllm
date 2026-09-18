#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gerar_massa_local.py — GERAÇÃO EM MASSA local (Ollama).

O que faz (pedido do usuário 07/08):
  1. Usa TODOS os tópicos (topicos.txt) × N repetições × TODOS os templates ×
     TODOS os estilos (fonte única: dashboard/services/templates_conteudo.py).
  2. Gera UM POR UM via `ollama run`, salva em pasta TEMPORÁRIA
     (dados/gerados/gerados_local/_massa/) — a quantidade não é empecilho:
     faz um, salva, faz outro, salva... até atingir a meta.
  3. Mostra percentual REAL (progresso persistido p/ o painel).
  4. Depois de gerar, aplica o pipeline pós-geração: FILTRA qualidade →
     CLASSIFICA por tipo → SANITIZA (PT-BR) → move para a pasta certa
     OU converte para .jsonl de treino.

Uso:
  python scripts/gerar_massa_local.py --modelo llama3.2:3b \
      [--repeticoes 2] [--meta 50] [--templates todos|dicionario,artigo] \
      [--estilos todos|neutro,humoristico] [--formato txt|jsonl] \
      [--fonte topicos|categorias|misto|rss] [--categorias todas|a,b] [--rss_limite N] \
      [--pasta_tmp dados/gerados/gerados_local/_massa] [--pos true]

FONTES DE TEMA (13/08/2026):
  topicos    → sorteia do topicos.txt (comportamento original).
  categorias → usa categories.py: categoria + assunto + prefixo/template → PERGUNTA
               contextualizada (35+ categorias, ~9 mil assuntos, instruções por área).
  misto      → 50% tópicos + 50% categorias.
  rss        → títulos RSS (cache 6h) → detecta a categoria → gera perguntas relacionadas
               aproveitando categories.py (fallback p/ categorias se não houver títulos).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from dashboard.services.templates_conteudo import (
        TIPOS_CONTEUDO, ESTILOS_ESCRITA, ORDEM_TIPOS, ORDEM_ESTILOS)
except Exception as e:
    print(f"⚠️ Não foi possível importar templates_conteudo: {e}")
    sys.exit(1)

PROGRESSO_PATH = PROJETO_ROOT / "logs" / "massa_progresso.json"
MURAL_PATH = PROJETO_ROOT / "logs" / "mural_pipeline.json"

PALAVRAS_TITULO = [
    "guia", "história", "reflexão", "análise", "conversa", "estudo",
    "resumo", "visão", "jornada", "segredos", "dicas", "tudo sobre",
    "manual", "o poder de", "descobrindo", "explorando", "pequena",
    "verdade", "arte de", "caminhos",
]


def _agora() -> str:
    return datetime.now().isoformat()


def _gravar_progresso(d: dict) -> None:
    try:
        PROGRESSO_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROGRESSO_PATH.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _carregar_topicos() -> list[str]:
    p = PROJETO_ROOT / "topicos.txt"
    if not p.exists():
        return []
    try:
        return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    except Exception:
        return []


def _titulo_randomico(tema: str) -> str:
    """Título aleatório a partir do tema (o usuário pediu 'títulos randomicos')."""
    palavra = random.choice(PALAVRAS_TITULO)
    prefixos = [f"{palavra} — ", f"O {palavra} de ", f"{palavra.title()}: "]
    return random.choice(prefixos) + tema


def _montar_prompt(tipo_id: str, estilo_id: str, tema: str) -> str:
    tipo = TIPOS_CONTEUDO[tipo_id]
    estilo = ESTILOS_ESCRITA[estilo_id]
    base = tipo["prompt"].format(tema=tema)
    if estilo.get("instrucao"):
        base = f"{base}\n\nEstilo: {estilo['instrucao']}"
    return base


# ============================================================================
# FONTES DE TEMA (topicos | categorias | misto | rss) — 13/08/2026
# ============================================================================
_CATEGORIAS_IDS_CACHE = None


def _todas_categorias_ids() -> list[str]:
    global _CATEGORIAS_IDS_CACHE
    if _CATEGORIAS_IDS_CACHE is None:
        try:
            from categories import CATEGORIAS_LISTAS as _CL
            _CATEGORIAS_IDS_CACHE = list(_CL.keys())
        except Exception:
            _CATEGORIAS_IDS_CACHE = []
    return _CATEGORIAS_IDS_CACHE


def _extrair_categoria_do_nome(nome: str) -> str:
    """Extrai categoria do nome (massa_<tipo>_<estilo>_<cat>_<ts>_<n>.txt)."""
    stem = f"_{nome}_"
    for c in _todas_categorias_ids():
        if f"_{c}_" in stem:
            return c
    return ""


def _categorias_ids(selecao: str):
    """Converte 'todas' → None (todas) ou 'a,b' → lista de ids válidos."""
    if not selecao or selecao.strip().lower() in ("todas", "todos", ""):
        return None
    ids = [c.strip() for c in selecao.split(",") if c.strip()]
    return ids or None


def _contar_base(categorias_ids) -> int:
    """Total de assuntos da seleção de categorias (p/ calcular a meta)."""
    try:
        from dashboard.services.gerador_categorias import contar_assuntos
        return contar_assuntos(categorias_ids)
    except Exception:
        return 1000


def _tema_de_categoria(categorias_ids) -> dict:
    """Sorteia categoria+assunto e monta pergunta contextualizada (categories.py)."""
    try:
        from dashboard.services.gerador_categorias import sortear_par, montar_pergunta
        categoria, assunto = sortear_par(categorias_ids)
        if not categoria or not assunto:
            return {"tema": "assunto geral", "tipo": "categoria", "categoria": "",
                    "assunto": "", "pergunta": "", "titulo_rss": ""}
        pergunta = montar_pergunta(categoria, assunto) or assunto
        return {"tema": pergunta, "tipo": "categoria", "categoria": categoria,
                "assunto": assunto, "pergunta": pergunta, "titulo_rss": ""}
    except Exception as e:
        print(f"    ⚠️ sortear_par falhou: {e}")
        return {"tema": random.choice(["cultura brasileira", "ciência", "história do Brasil"]),
                "tipo": "categoria", "categoria": "", "assunto": "",
                "pergunta": "", "titulo_rss": ""}


def _tema_de_rss(titulo: str) -> dict:
    """Detecta categoria do título RSS e gera perguntas relacionadas."""
    try:
        from dashboard.services.gerador_categorias import gerar_perguntas_relacionadas, _limpar_titulo
        rel = gerar_perguntas_relacionadas(titulo, n=3)
        if rel:
            r = rel[0]
            return {"tema": r["pergunta"], "tipo": "rss", "categoria": r["categoria"],
                    "assunto": r["assunto"], "pergunta": r["pergunta"], "titulo_rss": titulo}
        tema = _limpar_titulo(titulo)
        return {"tema": tema, "tipo": "rss", "categoria": "", "assunto": "",
                "pergunta": "", "titulo_rss": titulo}
    except Exception:
        return {"tema": titulo, "tipo": "rss", "categoria": "", "assunto": "",
                "pergunta": "", "titulo_rss": titulo}


def _proximo_tema(fonte: str, categorias_ids, topicos: list[str], rss_titulos: list[str]) -> dict:
    """Gera o próximo tema conforme a fonte selecionada (nunca quebra)."""
    if fonte == "categorias":
        return _tema_de_categoria(categorias_ids)
    if fonte == "misto":
        if topicos and random.random() < 0.5:
            tema = random.choice(topicos)
            return {"tema": tema, "tipo": "topico", "categoria": "", "assunto": tema,
                    "pergunta": "", "titulo_rss": ""}
        return _tema_de_categoria(categorias_ids)
    if fonte == "rss":
        if rss_titulos:
            return _tema_de_rss(random.choice(rss_titulos))
        print("    ⚠️ Sem títulos RSS — usando categorias como fallback.")
        return _tema_de_categoria(categorias_ids)
    # topico (padrão)
    tema = random.choice(topicos) if topicos else "tema geral"
    return {"tema": tema, "tipo": "topico", "categoria": "", "assunto": tema,
            "pergunta": "", "titulo_rss": ""}


def _gerar_um(modelo: str, prompt: str, timeout: int = 300,
              num_predict: int | None = None, temperatura: float | None = None) -> str:
    """Gera via API local do Ollama (controle de COMPRIMENTO com num_predict =
    parâmetros da Rigel — nem muito longo, nem muito curto). Fallback p/ `ollama run`."""
    # 1) API HTTP (permite num_predict/temperature)
    try:
        import httpx
        payload = {"model": modelo, "prompt": prompt, "stream": False}
        opts = {}
        if num_predict:
            opts["num_predict"] = int(num_predict)
        if temperatura is not None:
            opts["temperature"] = float(temperatura)
        if opts:
            payload["options"] = opts
        r = httpx.post("http://127.0.0.1:11434/api/generate", json=payload,
                       timeout=timeout)
        if r.status_code == 200:
            texto = (r.json().get("response") or "").strip()
            if texto:
                return texto
    except Exception:
        pass
    # 2) fallback CLI
    cmd = ["ollama", "run", modelo, prompt]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return ""
    if proc.returncode != 0:
        print(f"    ⚠️ ollama falhou (código {proc.returncode}): {proc.stderr[:150]}")
        return ""
    return (proc.stdout or "").strip()


def _filtrar_qualidade(texto: str) -> tuple[bool, str]:
    """Filtro de qualidade: (aprovado, motivo). Descarta lixo/repetição."""
    if not texto or len(texto) < 30:
        return False, "texto curto demais ou vazio"
    # Repetição de palavra (> 40% da frase inicial é a mesma palavra)
    palavras = texto.split()
    if palavras:
        mais_comum = max((palavras.count(p) for p in set(palavras)), default=0)
        if mais_comum / len(palavras) > 0.4:
            return False, "repetição excessiva"
    # Repetição de sentença (a mesma frase 3+ vezes)
    frases = [f.strip() for f in texto.replace("! ", ". ").replace("? ", ". ").split(". ") if f.strip()]
    contagem = {}
    for f in frases:
        contagem[f] = contagem.get(f, 0) + 1
    if contagem and max(contagem.values()) >= 3:
        return False, "frase repetida 3+ vezes"
    return True, ""


def _sanitizar(texto: str) -> str:
    """Sanitização leve: ANSI, emojis básicos e espaços concatenados."""
    try:
        from dashboard.services.limpeza import limpar_ansi, limpar_emojis, corrigir_espacos_concatenados
        texto = limpar_ansi(texto)
        texto = limpar_emojis(texto)
        texto = corrigir_espacos_concatenados(texto)
    except Exception:
        pass
    return texto.strip()


def _pos_processar(pasta_tmp: Path, formato: str) -> dict:
    """Filtra/classifica/sanitiza os gerados → pasta por tipo ou jsonl."""
    print("\n═══════════ PIPELINE PÓS-GERAÇÃO ═══════════")
    resumo = {"total": 0, "aprovados": 0, "descartados": 0, "por_tipo": {}}
    if not pasta_tmp.exists():
        return resumo

    destino_base = PROJETO_ROOT / "dados" / "gerados" / "massa_final"
    destino_base.mkdir(parents=True, exist_ok=True)
    linhas_jsonl = []

    for arq in sorted(pasta_tmp.glob("*.txt")):
        resumo["total"] += 1
        try:
            texto = arq.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # metadados no nome: massa_<tipo>_<estilo>_[<categoria>_]<ts>_<n>.txt
        # procura no nome INTEIRO (estilos com underscore como casual_jovem)
        tipo_id = next((t for t in TIPOS_CONTEUDO if f"_{t}_" in f"_{arq.stem}_"), "artigo")
        estilo_id = next((e for e in ESTILOS_ESCRITA if f"_{e}_" in f"_{arq.stem}_"), "neutro")
        categoria_id = _extrair_categoria_do_nome(arq.stem)

        # Marcadores (fonte categorias/rss): a 1ª linha guarda a PERGUNTA e a
        # 2ª o ASSUNTO (p/ campos completos no jsonl — regra do usuário).
        pergunta_marker = ""
        assunto_marker = ""
        linhas = texto.splitlines()
        if linhas and linhas[0].startswith("#PERGUNTA:"):
            pergunta_marker = linhas[0][len("#PERGUNTA:"):].strip()
            linhas = linhas[1:]
        if linhas and linhas[0].startswith("#ASSUNTO:"):
            assunto_marker = linhas[0][len("#ASSUNTO:"):].strip()
            linhas = linhas[1:]
        texto = "\n".join(linhas).strip()

        ok, motivo = _filtrar_qualidade(texto)
        if not ok:
            resumo["descartados"] += 1
            print(f"    🗑️ DESCARTADO ({motivo}): {arq.name}")
            try:
                arq.unlink()
            except Exception:
                pass
            continue

        texto_limpo = _sanitizar(texto)
        resumo["aprovados"] += 1
        resumo["por_tipo"][tipo_id] = resumo["por_tipo"].get(tipo_id, 0) + 1

        if formato == "jsonl":
            user_content = pergunta_marker or f"Escreva sobre o tema: {_extrair_tema(arq.stem)}"
            # 📦 Schema PADRÃO do Rigel (esquema_jsonl.md): messages com system +
            # metadados completos (_id, _fonte, _tipo, _categoria, _assunto...).
            _sistema = (TIPOS_CONTEUDO.get(tipo_id) or {}).get("system") or (
                "Você é um assistente em português brasileiro que responde de "
                "forma clara, completa e bem fundamentada.")
            linhas_jsonl.append({
                "messages": [
                    {"role": "system", "content": _sistema},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": texto_limpo},
                ],
                "_id": hashlib.md5(
                    f"{user_content}|{texto_limpo}".encode("utf-8")).hexdigest()[:16],
                "_fonte": f"geracao_local_massa/{arq.name}",
                "_tipo": "qna" if pergunta_marker else "artigo",
                "_categoria": categoria_id or "",
                "_assunto": assunto_marker or pergunta_marker or _extrair_tema(arq.stem),
                "_estilo": estilo_id,
                "_idioma": "pt-BR",
                "_data": _agora(),
                "_nota": 4,
            })
            # Move o txt processado p/ subpasta: o próximo ciclo incremental
            # NÃO reprocessa os já aprovados (senão duplicaria no jsonl).
            try:
                _proc_dir = pasta_tmp / "processados"
                _proc_dir.mkdir(parents=True, exist_ok=True)
                arq.rename(_proc_dir / arq.name)
            except Exception:
                pass
        else:
            # Manda para a pasta do tipo (classificação)
            pasta_tipo = destino_base / tipo_id
            pasta_tipo.mkdir(parents=True, exist_ok=True)
            try:
                novo = pasta_tipo / arq.name
                arq.rename(novo)
            except Exception:
                pass
        print(f"    ✅ APROVADO [{tipo_id}/{estilo_id}]: {arq.name}")

    if formato == "jsonl" and linhas_jsonl:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        jsonl_path = destino_base / f"massa_local_{ts}.jsonl"
        try:
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for linha in linhas_jsonl:
                    f.write(json.dumps(linha, ensure_ascii=False) + "\n")
            print(f"    📦 JSONL gerado: {jsonl_path} ({len(linhas_jsonl)} exemplos)")
            resumo["jsonl"] = str(jsonl_path)
            resumo["jsonl_exemplos"] = len(linhas_jsonl)
        except Exception as e:
            print(f"    ⚠️ Falha ao gravar jsonl: {e}")

    print(f"🏁 Pós-processamento: {resumo['aprovados']} aprovados · "
          f"{resumo['descartados']} descartados · {resumo['total']} total")
    return resumo


def _extrair_tema(nome: str) -> str:
    # remove prefixos de título aleatório (palavras comuns + ' — ' / ': ')
    import re
    nome_limpo = re.sub(r"^([\wÀ-ú ]+?[—:])\s*", "", nome)
    return nome_limpo or "tema geral"


def main() -> int:
    ap = argparse.ArgumentParser(description="Geração em massa local (Ollama)")
    ap.add_argument("--modelo", default="llama3.2:3b")
    ap.add_argument("--repeticoes", type=int, default=1, help="Vezes por tópico")
    ap.add_argument("--meta", type=int, default=0, help="Meta total (0 = sem limite)")
    ap.add_argument("--templates", default="todos", help="todos | lista,separada")
    ap.add_argument("--estilos", default="todos", help="todos | lista,separada")
    ap.add_argument("--formato", default="txt", choices=["txt", "jsonl"])
    ap.add_argument("--pasta_tmp", default="dados/gerados/gerados_local/_massa")
    ap.add_argument("--pos", default="true", help="roda pós-processamento ao final")
    ap.add_argument("--nome", default="Geração em massa")
    ap.add_argument("--fonte", default="topicos",
                    choices=["topicos", "categorias", "misto", "rss"],
                    help="Fonte de temas: topicos | categorias (categories.py) | misto | rss")
    ap.add_argument("--categorias", default="todas",
                    help="todas | lista,separada (só p/ categorias/misto)")
    ap.add_argument("--rss_limite", type=int, default=0,
                    help="Limite de títulos RSS (0 = todos) p/ --fonte rss")
    ap.add_argument("--timeout", type=int, default=300,
                    help="Timeout por item (segundos) na chamada ao Ollama")
    args = ap.parse_args()

    if args.templates.strip().lower() == "todos":
        templates = ORDEM_TIPOS
    else:
        templates = [t.strip() for t in args.templates.split(",") if t.strip() in TIPOS_CONTEUDO]
    if args.estilos.strip().lower() == "todos":
        estilos = ORDEM_ESTILOS
    else:
        estilos = [e.strip() for e in args.estilos.split(",") if e.strip() in ESTILOS_ESCRITA]
    if not templates or not estilos:
        print("❌ Sem templates/estilos válidos.")
        return 1

    topicos = _carregar_topicos()
    if not topicos and args.fonte.strip().lower() == "topicos":
        print("❌ topicos.txt vazio/ausente (e fonte=topicos).")
        return 1

    fonte = args.fonte.strip().lower()

    # Títulos RSS (modo rss): cache 6h ou fetch ao vivo; fallback p/ categorias.
    rss_titulos: list[str] = []
    if fonte == "rss":
        try:
            from dashboard.services.gerador_categorias import carregar_titulos_rss
            rss_titulos = carregar_titulos_rss(limite=(args.rss_limite or None))
        except Exception as e:
            print(f"⚠️ Não foi possível carregar títulos RSS: {e}")
        print(f"📰 Títulos RSS carregados: {len(rss_titulos)}")
        if not rss_titulos:
            print("⚠️ Sem títulos RSS — usando categorias como fallback.")
            fonte = "categorias"

    categorias_ids = _categorias_ids(args.categorias)

    # Total de combinações conforme a fonte (p/ meta e barra de progresso)
    if fonte == "categorias":
        base_total = _contar_base(categorias_ids)
    elif fonte == "rss":
        base_total = len(rss_titulos) or _contar_base(categorias_ids)
    elif fonte == "misto":
        base_total = len(topicos) + _contar_base(categorias_ids)
    else:
        base_total = len(topicos)
    total_combos = base_total * args.repeticoes
    meta = args.meta if args.meta > 0 else total_combos
    meta = min(meta, total_combos)
    print(f"🧠 Modelo: {args.modelo}")
    print(f"🗂️ Fonte: {fonte} | Templates: {len(templates)} | Estilos: {len(estilos)} | Meta: {meta}")
    if fonte in ("categorias", "misto"):
        print(f"🗂️ Categorias: {args.categorias} ({_contar_base(categorias_ids)} assuntos)")
    elif fonte == "rss":
        print(f"📰 Títulos: {len(rss_titulos)} × {args.repeticoes}x")

    pasta_tmp = PROJETO_ROOT / args.pasta_tmp
    pasta_tmp.mkdir(parents=True, exist_ok=True)
    ts_base = datetime.now().strftime("%Y%m%d_%H%M%S")

    gerados = 0
    erros = 0
    retries = 0
    inicio = time.time()

    # Progresso inicial: a barra aparece JÁ (0%) em vez de ficar invisível
    # até a primeira geração terminar (que demora com modelos grandes).
    _gravar_progresso({
        "pct": 0, "gerados": 0, "erros": 0,
        "atual": f"preparando primeira geração ({fonte})...", "meta": meta,
        "categoria": "", "assunto": "", "fonte": fonte,
        "restantes": meta, "decorrido_s": 0, "previsao_s": 0, "media_s": 0,
        "timestamp": _agora(),
    })

    # Gera um por um até atingir a meta (faz um, salva, faz outro, salva...)
    for i in range(meta):
        ctx = _proximo_tema(fonte, categorias_ids, topicos, rss_titulos)
        tema = ctx.get("tema") or "tema geral"
        # 🎯 Compatibilidade tipo×assunto + pergunta alinhada ao tipo (13/08):
        # no modo categoria/rss filtramos os TIPOS de resposta pela natureza do
        # assunto (ex.: "receita" NÃO cai em "chave philips") e realinhamos a
        # pergunta ao tipo (receita → "Como preparar X?").
        eh_pergunta = ctx.get("tipo") in ("categoria", "rss") and ctx.get("assunto")
        templates_loop = templates
        if eh_pergunta:
            try:
                from dashboard.services.gerador_categorias import (
                    _natureza_assunto, _tipos_compatíveis)
                natureza = _natureza_assunto(ctx.get("assunto", ""),
                                             ctx.get("categoria", ""))
                templates_loop = _tipos_compatíveis(natureza, templates) or templates
            except Exception:
                templates_loop = templates
        tipo = random.choice(templates_loop)
        estilo = random.choice(estilos)
        if eh_pergunta and ctx.get("pergunta"):
            try:
                from dashboard.services.gerador_categorias import montar_pergunta
                p2 = montar_pergunta(ctx.get("categoria", ""), ctx.get("assunto", ""),
                                     tipo_id=tipo)
                if p2:
                    ctx["pergunta"] = p2
                    if ctx.get("tipo") == "categoria":
                        ctx["tema"] = p2  # tema exibido/logado acompanha a pergunta
            except Exception:
                pass
        tema = ctx.get("tema") or tema  # tema atualizado (após realinhar a pergunta)
        tipo_info = TIPOS_CONTEUDO.get(tipo, {})
        num_predict = tipo_info.get("max_tokens")     # comprimento (parâmetros da Rigel)
        temperatura = tipo_info.get("temp")
        if ctx.get("tipo") in ("categoria", "rss") and ctx.get("pergunta"):
            # Prompt contextualizado: pergunta + formato do tipo + instruções da
            # categoria + estilo (o coração do aproveitamento do categories.py)
            try:
                from dashboard.services.gerador_categorias import montar_prompt_por_pergunta
                prompt = montar_prompt_por_pergunta(
                    ctx.get("categoria", ""), ctx.get("assunto", ""),
                    ctx.get("pergunta", ""), tipo, estilo)
            except Exception:
                prompt = _montar_prompt(tipo, estilo, tema)
        else:
            titulo = _titulo_randomico(tema)
            prompt = _montar_prompt(tipo, estilo, titulo)
        cat_rotulo = ctx.get("categoria") or ""
        rotulo = f"{tipo}/{estilo}" + (f" [{cat_rotulo}]" if cat_rotulo else "")
        print(f"\n[{i+1}/{meta}] {rotulo}: {tema[:60]}...")
        texto = ""
        try:
            texto = _gerar_um(args.modelo, prompt, timeout=args.timeout,
                              num_predict=num_predict, temperatura=temperatura)
        except subprocess.TimeoutExpired:
            print("    ⚠️ timeout — pulando")
        # 🔁 FALLBACK: se falhou no modo pergunta (categorias/rss), TROCA a pergunta
        # por um prompt mais simples — o modelo pode não encaixar a pergunta.
        if not texto and ctx.get("tipo") in ("categoria", "rss") and ctx.get("pergunta"):
            prompt_simples = _montar_prompt(tipo, estilo, ctx.get("assunto") or tema)
            print("    ↻ pergunta não respondeu — retentando com prompt simples...")
            try:
                texto = _gerar_um(args.modelo, prompt_simples, timeout=args.timeout,
                                  num_predict=num_predict, temperatura=temperatura)
            except subprocess.TimeoutExpired:
                texto = ""
            if texto:
                retries += 1
                print(f"    ✅ retry simples OK (retries={retries})")
        if not texto:
            erros += 1
            continue
        # Nome com categoria p/ o pós-processamento rastrear a origem
        nome_parts = ["massa", tipo, estilo]
        if cat_rotulo:
            nome_parts.append(cat_rotulo)
        nome_parts += [ts_base, str(i + 1)]
        nome = "_".join(nome_parts) + ".txt"
        conteudo_arquivo = texto
        if ctx.get("pergunta"):
            # Marcadores: #PERGUNTA (vira o "user" no jsonl) + #ASSUNTO (tema,
            # p/ os campos completos do schema — regra do usuário)
            marcadores = [f"#PERGUNTA: {ctx['pergunta']}"]
            if ctx.get("assunto"):
                marcadores.append(f"#ASSUNTO: {ctx['assunto']}")
            conteudo_arquivo = "\n".join(marcadores) + "\n" + texto
        try:
            (pasta_tmp / nome).write_text(conteudo_arquivo, encoding="utf-8")
            gerados += 1
        except Exception as e:
            print(f"    ⚠️ não salvou: {e}")
            erros += 1
        pct = round((i + 1) / meta * 100)
        decorrido = time.time() - inicio
        media = decorrido / (i + 1)
        previsao = media * (meta - (i + 1))
        _gravar_progresso({
            "pct": pct, "gerados": gerados, "erros": erros,
            "atual": f"{tipo}/{estilo}: {tema[:50]}",
            "categoria": ctx.get("categoria", ""),
            "assunto": ctx.get("assunto", ""),
            "fonte": fonte, "meta": meta, "restantes": meta - (i + 1),
            "retries": retries,
            "decorrido_s": round(decorrido), "previsao_s": round(previsao),
            "media_s": round(media, 1),
            "timestamp": _agora(),
        })
        print(f"    ▸ {pct}% ({i+1}/{meta}) | salvos={gerados} erros={erros} | "
              f"⏱️ {decorrido:.0f}s | restam ~{previsao:.0f}s")

        # ⚡ Pós-processamento INCREMENTAL (jsonl): a cada 10 itens processa os
        # txt pendentes e gera jsonl — o usuário vê resultado DURANTE a geração
        # (com meta 644, o jsonl só sairia no final = horas).
        if args.formato == "jsonl" and (i + 1) % 10 == 0:
            try:
                _pos_processar(pasta_tmp, "jsonl")
            except Exception as e:
                print(f"    ⚠️ pós incremental falhou: {e}")

    decorrido = round(time.time() - inicio)
    print(f"\n🏁 Geração concluída: {gerados} gerados · {erros} erros · em {decorrido}s")
    _gravar_progresso({
        "pct": 100, "gerados": gerados, "erros": erros,
        "atual": "concluído — pós-processamento", "meta": meta, "fim": True,
        "categoria": "", "assunto": "", "fonte": fonte,
        "restantes": 0, "decorrido_s": decorrido, "previsao_s": 0,
        "media_s": round(decorrido / meta, 1) if meta else 0,
        "retries": retries,
        "timestamp": _agora(),
    })

    # Pipeline pós-geração
    pos = args.pos.strip().lower() in ("true", "1", "yes")
    resumo = {}
    if pos and gerados:
        resumo = _pos_processar(pasta_tmp, args.formato)

    # Mural
    try:
        MURAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        mural = []
        if MURAL_PATH.exists():
            try:
                mural = json.loads(MURAL_PATH.read_text(encoding="utf-8"))
                mural = mural if isinstance(mural, list) else []
            except Exception:
                mural = []
        mural.append({
            "id": f"massa-{int(time.time())}",
            "nome": args.nome,
            "inicio": _agora(),
            "fim": _agora(),
            "comandos": [f"gerar_massa({args.modelo})", "pos_processamento"],
            "ok": gerados, "erros": erros, "pulados": 0, "total": meta,
            "itens": [{"comando": "massa", "origem": f"{pasta_tmp.name}",
                       "status": "ok" if gerados else "erro",
                       "erro": resumo.get("descarte_motivo")}],
        })
        MURAL_PATH.write_text(json.dumps(mural, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    except Exception:
        pass

    _gravar_progresso({"pct": 100, "fim": True, "gerados": gerados,
                       "erros": erros, "timestamp": _agora(),
                       "categoria": "", "assunto": "", "fonte": fonte,
                       "restantes": 0, "decorrido_s": decorrido,
                       "previsao_s": 0,
                       "media_s": round(decorrido / meta, 1) if meta else 0,
                       "retries": retries})
    return 0


if __name__ == "__main__":
    sys.exit(main())
