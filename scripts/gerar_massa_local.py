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
      [--pasta_tmp dados/gerados/gerados_local/_massa] [--pos true]
"""
from __future__ import annotations

import argparse
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


def _gerar_um(modelo: str, prompt: str, timeout: int = 300) -> str:
    """Roda `ollama run` e retorna o texto gerado (ou '' em falha)."""
    cmd = ["ollama", "run", modelo, prompt]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=env)
    if proc.returncode != 0:
        print(f"    ⚠️ ollama falhou (código {proc.returncode}): {proc.stderr[:150]}")
        return ""
    texto = (proc.stdout or "").strip()
    return texto


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
        # metadados no nome: massa_<tipo>_<estilo>_<ts>_<n>.txt
        # procura no nome INTEIRO (estilos com underscore como casual_jovem)
        tipo_id = next((t for t in TIPOS_CONTEUDO if f"_{t}_" in f"_{arq.stem}_"), "artigo")
        estilo_id = next((e for e in ESTILOS_ESCRITA if f"_{e}_" in f"_{arq.stem}_"), "neutro")

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
            linhas_jsonl.append({
                "messages": [
                    {"role": "user", "content": f"Escreva sobre o tema: {_extrair_tema(arq.stem)}"},
                    {"role": "assistant", "content": texto_limpo},
                ],
                "tipo": tipo_id,
                "estilo": estilo_id,
                "fonte": "geracao_local_massa",
                "data": _agora(),
            })
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
    if not topicos:
        print("❌ topicos.txt vazio/ausente.")
        return 1

    total_combos = len(topicos) * args.repeticoes
    meta = args.meta if args.meta > 0 else total_combos
    meta = min(meta, total_combos)
    print(f"🧠 Modelo: {args.modelo}")
    print(f"📚 Tópicos: {len(topicos)} × {args.repeticoes}x | Templates: {len(templates)} "
          f"| Estilos: {len(estilos)} | Meta: {meta}")

    pasta_tmp = PROJETO_ROOT / args.pasta_tmp
    pasta_tmp.mkdir(parents=True, exist_ok=True)
    ts_base = datetime.now().strftime("%Y%m%d_%H%M%S")

    gerados = 0
    erros = 0
    inicio = time.time()

    # Progresso inicial: a barra aparece JÁ (0%) em vez de ficar invisível
    # até a primeira geração terminar (que demora com modelos grandes).
    _gravar_progresso({
        "pct": 0, "gerados": 0, "erros": 0,
        "atual": "preparando primeira geração...", "meta": meta,
        "timestamp": _agora(),
    })

    # Gera um por um até atingir a meta (faz um, salva, faz outro, salva...)
    for i in range(meta):
        tema = random.choice(topicos)
        tipo = random.choice(templates)
        estilo = random.choice(estilos)
        titulo = _titulo_randomico(tema)
        prompt = _montar_prompt(tipo, estilo, titulo)
        print(f"\n[{i+1}/{meta}] {tipo}/{estilo}: {titulo[:70]}...")
        try:
            texto = _gerar_um(args.modelo, prompt)
        except subprocess.TimeoutExpired:
            print("    ⚠️ timeout (300s) — pulando")
            erros += 1
            continue
        if not texto:
            erros += 1
            continue
        nome = f"massa_{tipo}_{estilo}_{ts_base}_{i+1}.txt"
        try:
            (pasta_tmp / nome).write_text(texto, encoding="utf-8")
            gerados += 1
        except Exception as e:
            print(f"    ⚠️ não salvou: {e}")
            erros += 1
        pct = round((i + 1) / meta * 100)
        _gravar_progresso({
            "pct": pct, "gerados": gerados, "erros": erros,
            "atual": f"{tipo}/{estilo}: {titulo[:50]}", "meta": meta,
            "timestamp": _agora(),
        })
        print(f"    ▸ {pct}% ({i+1}/{meta}) | salvos={gerados} erros={erros}")

    decorrido = round(time.time() - inicio)
    print(f"\n🏁 Geração concluída: {gerados} gerados · {erros} erros · em {decorrido}s")
    _gravar_progresso({
        "pct": 100, "gerados": gerados, "erros": erros,
        "atual": "concluído — pós-processamento", "meta": meta, "fim": True,
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
                       "erros": erros, "timestamp": _agora()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
