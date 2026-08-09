#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
converter_txt_jsonl.py - Converte dados legados .txt para JSONL SFT (messages).
Versão: 1.0.0 | Data: 02/08/2026

Transforma os milhares de arquivos .txt de pergunta/resposta (e artigos) em
datasets JSONL no formato do Rigel:

    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}

Isso ensina o modelo a RESPONDER (SFT), não apenas a prever a próxima letra:
o system prompt dá identidade/contexto, user = pergunta, assistant = resposta.

Formatos detectados automaticamente:
  - "Pergunta: X" / "Resposta: Y"            (e variantes: pergunta:, p:, q:, user:, humano:)
  - "Q:" / "A:", "P:" / "R:", "user:" / "assistant:", "human:" / "gpt:"
  - Texto contínuo (artigos) -> vira pergunta "Escreva um texto sobre <tema>"
    (use --apenas-qna para pular artigos)

Uso:
    python converter_txt_jsonl.py --pasta dados/processed                 # vira rigeljsonl1, rigeljsonl2...
    python converter_txt_jsonl.py --pasta pasta --max-exemplos 10000 --max-arquivos 100
    # Convenção Rigel: dados de FORA viram rigeljsonl<N> (nome automático).
    # Só use --saida com nome próprio para dados TIPIFICADOS internos (ex: --saida cartas).

Saída: dados/gerados/jsonl/<saida>/  (aparece automaticamente no Treino Local)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_RAIZ = Path(__file__).resolve().parent
DESTINO_BASE = _RAIZ / "dados" / "gerados" / "jsonl"

# System prompt FIXO do Rigel — fonte única em saida_manager.py
sys.path.insert(0, str(_RAIZ))
from saida_manager import SYSTEM_PROMPT  # noqa: E402

_MARCADOR_Q = re.compile(r"^\s*(?:pergunta|p|q|user|humano|h|usu[áa]rio)\s*[:：]\s*(.*)$", re.I)
_MARCADOR_A = re.compile(r"^\s*(?:resposta|r|a|assistente|bot|gpt|model)\s*[:：]\s*(.*)$", re.I)
# Marcador de resposta SEM âncora de início — p/ pares na MESMA linha ("Pergunta: X Resposta: Y")
_MARCADOR_A_INLINE = re.compile(r"\b(?:resposta|assistente|bot|gpt|model)\s*[:：]\s*", re.I)

_TEMAS_NAO_ARTIGO = ("artigo", "auto", "api", "txt", "gerado", "ultrachat", "dataset")


def _corrigir_mojibake(texto: str) -> str:
    """Corrige UTF-8 lido como cp1252 (ex.: 'VocÃª' -> 'Você'). Seguro: se o
    texto já estiver correto, a decodificação falha e o original é mantido."""
    try:
        return texto.encode("cp1252").decode("utf-8")
    except Exception:
        return texto


def _extrair_pares(texto: str) -> list[tuple[str, str]]:
    """Extrai pares (pergunta, resposta) de texto com marcadores conhecidos."""
    linhas = texto.splitlines()
    pares: list[tuple[str, str]] = []
    q_atual: list[str] = []
    a_atual: list[str] = []
    estado: str | None = None  # None | 'q' | 'a'

    def _flush():
        nonlocal q_atual, a_atual
        q = " ".join(x.strip() for x in q_atual).strip()
        a = " ".join(x.strip() for x in a_atual).strip()
        if q and a:
            pares.append((q, a))
        q_atual, a_atual = [], []

    for linha in linhas:
        # Par na MESMA linha: "Pergunta: X Resposta: Y" (ex.: curtos2, datasets)
        mq = _MARCADOR_Q.match(linha)
        if mq:
            q_parte = mq.group(1)  # tudo após "Pergunta:" (pode conter "Resposta: ...")
            ma_inline = _MARCADOR_A_INLINE.search(q_parte)
            if ma_inline:
                if estado == "a":
                    _flush()
                q_inline = q_parte[:ma_inline.start()].strip()
                a_inline = q_parte[ma_inline.end():].strip()
                if q_inline and a_inline:
                    pares.append((q_inline, a_inline))
                estado = None
                q_atual, a_atual = [], []
                continue
        ma = _MARCADOR_A.match(linha)
        if mq:
            if estado == "a":
                _flush()
            estado = "q"
            q_atual.append(mq.group(1))
        elif ma:
            estado = "a"
            a_atual.append(ma.group(1))
        else:
            if estado == "q":
                q_atual.append(linha)
            elif estado == "a":
                a_atual.append(linha)

    if estado == "a" or (q_atual and a_atual):
        _flush()
    return pares


def _limpar_artigo(texto: str) -> str:
    """Remove preâmbulos/fechamentos de IA ('Claro! Aqui está...', 'Espero que...')."""
    linhas = texto.splitlines()
    while linhas:
        l = linhas[0].strip().lower()
        if not l or l.startswith(("claro!", "aqui está", "aqui esta", "claro que sim",
                                  "com certeza!", "claro, aqui", "sem problema", "vamos lá",
                                  "vamos la")):
            linhas.pop(0)
        else:
            break
    while linhas:
        l = linhas[-1].strip().lower()
        if not l or l.startswith(("espero que", "posso ajustar", "se precisar", "se quiser",
                                  "qualquer coisa", "espero ter", "gostaria de saber se",
                                  "caso precise", "se você quiser", "se voce quiser")):
            linhas.pop()
        else:
            break
    return "\n".join(linhas).strip()


# ⚡ INSTRUÇÕES VARIADAS para artigos: o modelo generaliza quando vê DIFERENTES
# formatos de pedido, não só "Escreva um texto sobre X" repetido 100 mil vezes.
_INSTRUCOES_ARTIGO = (
    "Escreva um texto informativo e completo sobre: {tema}.",
    "Explique com detalhes e clareza o tema: {tema}.",
    "Faça um resumo bem estruturado e informativo sobre: {tema}.",
    "O que você pode me contar sobre: {tema}?",
    "Descreva de forma completa e organizada: {tema}.",
    "Produza um artigo bem escrito, com introdução e desenvolvimento, sobre: {tema}.",
    "Conte, com riqueza de detalhes, tudo o que sabe sobre: {tema}.",
    "Disserte sobre o tema {tema} de maneira aprofundada.",
)


def _artigo_para_qa(texto: str, tema: str) -> tuple[str, str] | None:
    """Converte um texto contínuo (artigo) em (pergunta, resposta).

    A pergunta varia entre instruções diferentes, escolhida de forma
    DETERMINÍSTICA pelo conteúdo: mesmo arquivo → mesma instrução
    (reprodutível), mas arquivos diferentes → instruções variadas
    (o modelo aprende a responder a vários formatos → generaliza melhor)."""
    limpo = _limpar_artigo(texto)
    if len(limpo) < 200:
        return None
    # Melhor contexto: o PRÓPRIO título do artigo (ex.: "# As Eleições no Brasil...")
    m = re.search(r"^#\s+(.+)$", limpo, re.M)
    if m:
        tema_uso = m.group(1).strip().strip("*")
    elif tema and tema.split()[0].lower() not in _TEMAS_NAO_ARTIGO:
        tema_uso = tema
    else:
        tema_uso = "este tema"
    idx = int(hashlib.md5(limpo.encode("utf-8")).hexdigest()[:8], 16) % len(_INSTRUCOES_ARTIGO)
    pergunta = _INSTRUCOES_ARTIGO[idx].format(tema=tema_uso)
    return pergunta, limpo


def _tema_do_arquivo(arquivo: Path, origem: Path) -> str:
    """Deriva um tema do nome do arquivo/pasta (ex.: canarim_000012.txt -> canarim)."""
    base = arquivo.name
    # remove TODOS os sufixos numéricos: _000012_0001, -20260727_195037
    base = re.sub(r"(?:[_-]\d+)+", "", os.path.splitext(base)[0])
    # se virar vazio, usa a pasta mais próxima
    if len(base) < 3:
        try:
            rel = arquivo.relative_to(origem).parts
            pasta = [p for p in rel[:-1] if not p.startswith(".")]
            base = pasta[-1] if pasta else "tema"
        except Exception:
            base = "tema"
    return base.replace("_", " ").replace("-", " ").strip() or "tema"


def _categoria_do_arquivo(arquivo: Path, origem: Path) -> str:
    """Categoria = pasta imediata do arquivo (ex.: canarim, PerguntaseRespostas)."""
    try:
        rel = arquivo.relative_to(origem).parts
        pastas = [p for p in rel[:-1] if not p.startswith(".")]
        if pastas:
            return pastas[0].replace("_", " ").strip()
    except Exception:
        pass
    nome = origem.name.replace("_", " ").strip()
    return nome or "convertido"


def converter_pasta(pasta: str, saida: str, exemplos_por_arquivo: int = 1000,
                    max_exemplos: int | None = None, max_arquivos: int | None = None,
                    apenas_qna: bool = False) -> dict:
    """Converte uma pasta de .txt legados para JSONL SFT explodido.

    STREAMING: escreve em disco conforme processa (arquivos de N exemplos), sem
    segurar tudo na memória — seguro mesmo com milhões de linhas.
    """
    origem = Path(pasta)
    if not origem.exists():
        return {"ok": False, "erro": f"Pasta não encontrada: {origem}"}

    arquivos = sorted(origem.rglob("*.txt"))
    if max_arquivos:
        arquivos = arquivos[:max_arquivos]
    total_txt = len(arquivos)

    destino = DESTINO_BASE / saida
    os.makedirs(destino, exist_ok=True)

    vistos: set[str] = set()   # só os hashes (memória pequena mesmo p/ milhões)
    descartados = 0
    processados = 0
    total = 0
    gerados = 0
    fh = None

    def _fechar():
        nonlocal fh
        if fh:
            try:
                fh.close()
            except Exception:
                pass
            fh = None

    def _abrir():
        nonlocal fh, gerados
        _fechar()
        gerados += 1
        fh = open(destino / f"{saida}_{gerados:04d}.jsonl", "w", encoding="utf-8")

    _abrir()
    try:
        for f in arquivos:
            processados += 1
            try:
                texto = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            tipo = "qna"
            pares = _extrair_pares(texto)
            if not pares and not apenas_qna:
                tema = _tema_do_arquivo(f, origem)
                qa = _artigo_para_qa(texto, tema)
                if qa:
                    pares = [qa]
                    tipo = "artigo"
            if not pares:
                descartados += 1
                continue

            # Metadados completos (rastreio/qualidade) — não interferem no treino
            categoria = _categoria_do_arquivo(f, origem)
            assunto = _tema_do_arquivo(f, origem)
            try:
                fonte_rel = str(f.relative_to(origem))
            except Exception:
                fonte_rel = str(f)
            data_iso = datetime.now().isoformat(timespec="seconds")

            for q, a in pares:
                q2 = _corrigir_mojibake(q).strip()
                a2 = _corrigir_mojibake(a).strip()
                if not q2 or not a2 or len(a2) < 10:
                    descartados += 1
                    continue
                chave = hashlib.md5(q2.lower().encode("utf-8")).hexdigest()
                if chave in vistos:
                    continue
                vistos.add(chave)
                # Abre arquivo novo quando o atual encheu
                if total > 0 and total % exemplos_por_arquivo == 0:
                    _abrir()
                ex = {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": q2},
                        {"role": "assistant", "content": a2},
                    ],
                    "_id": hashlib.md5(f"{q2}|{a2}".encode("utf-8")).hexdigest()[:16],
                    "_fonte": fonte_rel,
                    "_tipo": tipo,
                    "_categoria": categoria,
                    "_assunto": assunto,
                    "_idioma": "pt-BR",
                    "_data": data_iso,
                }
                fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
                total += 1
                if max_exemplos and total >= max_exemplos:
                    break
            if processados % 500 == 0:
                print(f"   ⏳ {processados}/{total_txt} arquivos | {total} exemplos | "
                      f"arquivo {gerados}")
            if max_exemplos and total >= max_exemplos:
                break
    finally:
        _fechar()

    if total == 0:
        # remove o arquivo vazio criado
        try:
            (destino / f"{saida}_0001.jsonl").unlink()
        except Exception:
            pass
        return {"ok": False, "erro": "Nenhum exemplo válido extraído.",
                "txt": total_txt, "processados": processados}

    return {
        "ok": True,
        "mensagem": (f"✅ Convertidos {total_txt} .txt -> {total} exemplos "
                     f"em {gerados} arquivos em {destino}"),
        "txt": total_txt,
        "processados": processados,
        "exemplos": total,
        "descartados": descartados,
        "arquivos_gerados": gerados,
        "destino": str(destino),
    }


def _proximo_nome_rigeljsonl() -> str:
    """Próximo nome sequencial da convenção Rigel: rigeljsonl1, rigeljsonl2, ..."""
    if not DESTINO_BASE.exists():
        return "rigeljsonl1"
    maior = 0
    for p in DESTINO_BASE.iterdir():
        if p.is_dir():
            m = re.match(r"^rigeljsonl(\d+)$", p.name)
            if m:
                maior = max(maior, int(m.group(1)))
    return f"rigeljsonl{maior + 1}"


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Converte .txt legados (pergunta/resposta) para JSONL SFT (messages)")
    parser.add_argument("--pasta", required=True, help="Pasta com os .txt (ex: dados/processed)")
    parser.add_argument("--saida", default=None,
                        help="Nome do dataset de saída. Padrão: rigeljsonl<N> automático "
                             "(convenção Rigel p/ dados externos). Use nome próprio apenas "
                             "para dados TIPIFICADOS internos (ex: cartas, contos).")
    parser.add_argument("--exemplos-por-arquivo", type=int, default=1000)
    parser.add_argument("--max-exemplos", type=int, default=None, help="Limite de exemplos")
    parser.add_argument("--max-arquivos", type=int, default=None, help="Limite de .txt a ler (teste)")
    parser.add_argument("--apenas-qna", action="store_true",
                        help="Só arquivos com marcadores Pergunta/Resposta (pula artigos)")
    args = parser.parse_args()
    saida = args.saida or _proximo_nome_rigeljsonl()

    r = converter_pasta(args.pasta, saida,
                        exemplos_por_arquivo=args.exemplos_por_arquivo,
                        max_exemplos=args.max_exemplos,
                        max_arquivos=args.max_arquivos,
                        apenas_qna=args.apenas_qna)
    if r.get("ok"):
        print(r["mensagem"])
        print(f"   • {r['txt']} arquivos .txt | {r['exemplos']} exemplos | "
              f"{r['descartados']} descartados | {r['arquivos_gerados']} arquivos jsonl")
        print("   ➡️  Aparece no dashboard em Treino Local como dataset "
              f"'{saida}'. Treine com:")
        print(f"      python treinar_com_jsonl.py --dados dados/gerados/jsonl "
              f"--arquivo {saida}_0001.jsonl")
    else:
        print(f"❌ {r.get('erro', 'erro')}")


if __name__ == "__main__":
    _cli()
