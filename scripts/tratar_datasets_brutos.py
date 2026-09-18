#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tratar_datasets_brutos.py — TRATAMENTO AUTOMÁTICO DE DATASETS BRUTOS (18/08).

O que faz, sozinho:
  1. Varre `dados/processed/jsonl` procurando pastas BRUTAS (sem `_sanitizado`).
  2. DETECTA o formato de cada arquivo automaticamente:
       messages            → sanitiza via sanitizador_ptbr (mojibake + inválidos)
       text                → corrige mojibake + remove inválidos nos campos de texto
       prompt/completion   → CONVERTE para messages (user=prompt, assistant=completion) + sanitiza
       pergunta/resposta   → limpa conteúdo e mantém o schema
       outros (tabela etc.)→ reporta como "não serve p/ chat" (não mexe)
  3. Escreve o resultado em `dados/tratados/<nome>_tratado/` (pasta organizada).
  4. Gera relatório completo em `logs/tratar_brutos_relatorio.json` e progresso
     em `logs/tratar_brutos_progresso.json`.

Reutilizável: para datasets futuros, basta colocar em processed/jsonl e rodar
`python scripts/tratar_datasets_brutos.py` (ou acionar pelo executor).

Uso:
  python scripts/tratar_datasets_brutos.py                 # trata todos os brutos
  python scripts/tratar_datasets_brutos.py --pasta NOME    # trata 1 pasta
  python scripts/tratar_datasets_brutos.py --simular       # ensaio (não escreve)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))

from sanitizador_ptbr import (  # noqa: E402  (reaproveita o portão de qualidade)
    ABNT2_ACEITOS,
    corrigir_mojibake_inteligente,
    avaliar_conteudo,
)

JSONL_DIR = PROJETO_ROOT / "dados" / "processed" / "jsonl"
TRATADOS_DIR = PROJETO_ROOT / "dados" / "tratados"
LOGS_DIR = PROJETO_ROOT / "logs"
RELATORIO = LOGS_DIR / "tratar_brutos_relatorio.json"
PROGRESSO = LOGS_DIR / "tratar_brutos_progresso.json"

_RE_MOJI = re.compile(r"Ã£|Ã©|Ãª|Ã§|Ã³|Ã¡|Ã­|Ã¼|Ã´|Ã¢|Ãµ|â€|â€œ|â€\u009d|\ufffd")

# Tabela de tradução p/ remover caracteres fora do ABNT2 em C-speed (str.translate).
# Pré-computada uma única vez (~1M entradas, ~150ms) — depois cada chamada é nativa.
_ABNT2_ORD = {ord(c) for c in ABNT2_ACEITOS}
_REMOVER_NAO_ABNT2 = {cp: None for cp in range(0x110000) if cp not in _ABNT2_ORD}


def _remover_invalidos_rapido(texto: str) -> tuple[str, int]:
    """Remove caracteres fora do ABNT2 via str.translate (C-speed).

    Equivalente ao `remover_invalidos` do sanitizador_ptbr (que faz loop char
    a char em Python e é o gargalo em datasets grandes). Retorna (limpo, n).
    """
    if not texto:
        return texto, 0
    n = sum(1 for ch in texto if ch not in ABNT2_ACEITOS)
    return texto.translate(_REMOVER_NAO_ABNT2), n


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _detectar_formato(obj: dict) -> str:
    """Detecta o schema do exemplo (messages | text | alpaca | qna | outro)."""
    if isinstance(obj.get("messages"), list):
        return "messages"
    if isinstance(obj.get("conversations"), list):
        return "messages"
    if isinstance(obj.get("prompt"), (str, list)) and isinstance(obj.get("completion"), str):
        return "alpaca"
    if "pergunta" in obj and "resposta" in obj:
        return "qna"
    if "text" in obj:  # text pode ser str, list ou dict {paragraphs: [[...]]} (brwac)
        return "text"
    return "outro"


def _limpar_campo(texto: str) -> tuple[str, int, int]:
    """Corrige mojibake + remove inválidos (rápido). Retorna (limpo, n, moji)."""
    corrigido = corrigir_mojibake_inteligente(texto)
    moji = 1 if corrigido != texto else 0
    limpo, removidos = _remover_invalidos_rapido(corrigido)
    return limpo, removidos, moji


def _sanitizar_messages_rapido(obj: dict) -> tuple[dict | None, dict]:
    """Sanitiza messages SEM langdetect e SEM loop char a char (rápido).

    Aplica corrigir_mojibake + remover_inválidos (str.translate) em cada
    mensagem. Equivalente ao `sanitizar_exemplo(exigir_ptbr=False)` em
    resultado, mas sem os dois gargalos: langdetect por exemplo e loop char
    a char. Torna 469k linhas viável em minutos.
    """
    stats = {"formato": "messages", "removidos": 0, "mojibake": 0, "descartado": ""}
    mensagens = obj.get("messages")
    if not isinstance(mensagens, list) or not mensagens:
        stats["descartado"] = "sem messages"
        return None, stats
    novas: list[dict] = []
    for m in mensagens:
        if not isinstance(m, dict):
            stats["descartado"] = "mensagem não-dict"
            return None, stats
        conteudo = m.get("content")
        if isinstance(conteudo, list):  # HF: [{type,text},...]
            conteudo = "\n".join(
                str(p.get("text", "")) if isinstance(p, dict) else str(p)
                for p in conteudo)
        conteudo = str(conteudo or "")
        limpo, removidos, moji = _limpar_campo(conteudo)
        status, motivo = avaliar_conteudo(limpo, removidos)
        if status == "descartado":
            stats["descartado"] = motivo
            return None, stats
        nova = dict(m)
        nova["content"] = limpo
        novas.append(nova)
        stats["removidos"] += removidos
        stats["mojibake"] += moji
    novo = dict(obj)
    novo["messages"] = novas
    return novo, stats


def _tratar_linha(obj: dict) -> tuple[dict | None, dict]:
    """Trata UM exemplo conforme o formato. Retorna (novo_obj ou None, stats)."""
    formato = _detectar_formato(obj)
    stats = {"formato": formato, "removidos": 0, "mojibake": 0, "descartado": ""}
    if formato == "messages":
        return _sanitizar_messages_rapido(obj)
    if formato == "text":
        campo = obj.get("text", "")
        if isinstance(campo, dict) and isinstance(campo.get("paragraphs"), list):
            # brwac: {"paragraphs": [["par1", "par2"], [...]]} — achata em texto
            texto = "\n\n".join(
                " ".join(str(par) for par in bloco) for bloco in campo["paragraphs"])
        elif isinstance(campo, list):
            texto = "\n".join(str(x) for x in campo)
        else:
            texto = str(campo)
        limpo, removidos, moji = _limpar_campo(texto)
        status, motivo = avaliar_conteudo(limpo, removidos)
        if status == "descartado":
            stats["descartado"] = motivo
            return None, stats
        novo = dict(obj)
        novo["text"] = limpo  # texto limpo e achatado
        stats["removidos"] = removidos
        stats["mojibake"] = moji
        return novo, stats
    if formato == "alpaca":
        prompt = obj.get("prompt")
        if isinstance(prompt, list):  # algumas versões: [{role, content}]
            prompt = " ".join(
                str(p.get("content", "")) for p in prompt if isinstance(p, dict))
        prompt = str(prompt or "")
        completion = str(obj.get("completion", "") or "")
        novo = {"messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": completion},
        ]}
        novo, st = _sanitizar_messages_rapido(novo)
        if novo is None:
            stats["descartado"] = st.get("descartado", "alpaca inválido")
            return None, stats
        stats["removidos"] = st.get("removidos", 0)
        stats["mojibake"] = st.get("mojibake", 0)
        return novo, stats
    if formato == "qna":
        pergunta, r1, m1 = _limpar_campo(str(obj.get("pergunta", "")))
        resposta, r2, m2 = _limpar_campo(str(obj.get("resposta", "")))
        novo = dict(obj)
        novo["pergunta"] = pergunta
        novo["resposta"] = resposta
        stats["removidos"] = r1 + r2
        stats["mojibake"] = m1 + m2
        return novo, stats
    # "outro" (tabela etc.) — não mexe, reporta
    stats["descartado"] = "formato não reconhecido (provável dado tabular)"
    return None, stats


def _salvar_progresso(dados: dict) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESSO.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def tratar_arquivo(origem: Path, destino: Path, simular: bool) -> dict:
    """Trata um arquivo jsonl inteiro (streaming). Retorna relatório."""
    rel = {"arquivo": origem.name, "total": 0, "ok": 0, "corrigidos": 0,
           "descartados": 0, "mojibake": 0, "chars_removidos": 0,
           "formatos": {}, "exemplos_descartados": []}
    with origem.open("r", encoding="utf-8", errors="replace") as f:
        for linha in f:
            if not linha.strip():
                continue
            try:
                obj = json.loads(linha)
            except Exception:
                rel["descartados"] += 1
                continue
            novo, st = _tratar_linha(obj)
            rel["total"] += 1
            fmt = st["formato"]
            rel["formatos"][fmt] = rel["formatos"].get(fmt, 0) + 1
            rel["mojibake"] += st["mojibake"]
            rel["chars_removidos"] += st["removidos"]
            if novo is None:
                rel["descartados"] += 1
                if len(rel["exemplos_descartados"]) < 5:
                    rel["exemplos_descartados"].append(st["descartado"])
                continue
            if st["removidos"] or st["mojibake"]:
                rel["corrigidos"] += 1
            else:
                rel["ok"] += 1
            if not simular:
                destino.parent.mkdir(parents=True, exist_ok=True)
                with destino.open("a", encoding="utf-8") as saida:
                    saida.write(json.dumps(novo, ensure_ascii=False) + "\n")
    return rel


def main() -> int:
    ap = argparse.ArgumentParser(description="Tratamento automático de datasets brutos.")
    ap.add_argument("--pasta", help="trata apenas uma subpasta de processed/jsonl")
    ap.add_argument("--simular", action="store_true", help="ensaio (não escreve)")
    args = ap.parse_args()

    if not JSONL_DIR.exists():
        print(f"ERRO: {JSONL_DIR} não existe")
        return 1

    pastas = [JSONL_DIR / args.pasta] if args.pasta else sorted(
        [p for p in JSONL_DIR.iterdir() if p.is_dir()])
    if args.pasta and not pastas[0].exists():
        print(f"ERRO: pasta não encontrada: {pastas[0]}")
        return 1

    # Só BRUTAS (sem _sanitizado) — as sanitizadas já estão limpas
    brutas = [p for p in pastas if not p.name.endswith("_sanitizado")]

    relatorio_geral = {"data": _agora(), "simular": args.simular,
                       "pastas": [], "totais": {}}
    print(f"[INFO] {len(brutas)} pasta(s) bruta(s) para tratar")
    for pasta in brutas:
        destino = TRATADOS_DIR / f"{pasta.name}_tratado"
        if destino.exists() and not args.simular:
            # reprocesso seguro: recria do zero
            import shutil
            shutil.rmtree(destino)
        rel_pasta = {"pasta": pasta.name, "arquivos": []}
        for arq in sorted(pasta.glob("*.jsonl")):
            rel_arq = tratar_arquivo(arq, destino / arq.name, args.simular)
            rel_pasta["arquivos"].append(rel_arq)
            flag = "[OK]" if rel_arq["descartados"] == 0 else "[!]"
            print(f"  {flag} {pasta.name}/{arq.name}: total={rel_arq['total']} "
                  f"ok={rel_arq['ok']} corrigidos={rel_arq['corrigidos']} "
                  f"descartados={rel_arq['descartados']} mojibake={rel_arq['mojibake']} "
                  f"formatos={rel_arq['formatos']}")
            _salvar_progresso({"atual": f"{pasta.name}/{arq.name}",
                               "data": _agora(), "pasta": pasta.name})
        relatorio_geral["pastas"].append(rel_pasta)

    tot = {"total": 0, "ok": 0, "corrigidos": 0, "descartados": 0, "mojibake": 0}
    for p in relatorio_geral["pastas"]:
        for a in p["arquivos"]:
            for k in tot:
                tot[k] += a.get(k, 0)
    relatorio_geral["totais"] = tot

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    RELATORIO.write_text(json.dumps(relatorio_geral, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    print("\n" + "=" * 60)
    print(f"TOTAIS: {tot['total']} exemplos | ok={tot['ok']} "
          f"corrigidos={tot['corrigidos']} descartados={tot['descartados']} "
          f"mojibake={tot['mojibake']}")
    print(f"Relatorio: {RELATORIO}")
    if not args.simular:
        print(f"Saidas tratadas: {TRATADOS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
