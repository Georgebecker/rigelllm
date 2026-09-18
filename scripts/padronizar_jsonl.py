#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
padronizar_jsonl.py — ELEVA jsonl antigos/parciais ao SCHEMA PADRÃO do Rigel.

Regra do usuário (esquema_jsonl.md): exemplos com metadados MAIS COMPLETOS.
O gerador de massa antigo (pré-14/08) gravava:
    {messages: [user, assistant], tipo, estilo, categoria, fonte, data}
Este script transforma para o padrão:
    {messages: [system, user, assistant],
     _id, _fonte, _tipo, _categoria, _assunto, _estilo, _idioma, _data, _nota}

NUNCA apaga nada: lê o original e escreve um novo (sufixo `_padrao` no mesmo
lugar, ou na pasta de destino). Reutilizável: aceita 1 arquivo ou pasta.

Uso:
  python scripts/padronizar_jsonl.py [--origem dados/gerados/massa_final]
      [--destino ""]          # vazio = mesmo lugar, nome com _padrao
      [--sobrescrever]        # escreve POR CIMA do arquivo (com .bak antes)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))

try:
    from dashboard.services.templates_conteudo import TIPOS_CONTEUDO
except Exception:
    TIPOS_CONTEUDO = {}

SYSTEM_PADRAO = (
    "Você é um assistente em português brasileiro que responde de forma clara, "
    "completa e bem fundamentada."
)


def _id_de(pergunta: str, resposta: str) -> str:
    return hashlib.md5(f"{pergunta}|{resposta}".encode("utf-8")).hexdigest()[:16]


def _sistema_do_tipo(tipo_id: str) -> str:
    if tipo_id:
        sist = (TIPOS_CONTEUDO.get(tipo_id) or {}).get("system")
        if sist:
            return sist
    return SYSTEM_PADRAO


def _assunto_do_user(user: str) -> str:
    """Deriva um assunto do user content (heurística honesta)."""
    u = (user or "").strip()
    for pref in ("Escreva sobre o tema:", "Conte sobre:", "Fale sobre:"):
        if u.lower().startswith(pref.lower()):
            u = u[len(pref):].strip()
            break
    # Nome de arquivo gerado (massa_<tipo>_<estilo>_<ts>_<n>) não guarda tema real
    if u.startswith("massa_"):
        return "tema geral"
    return u or "tema geral"


def padronizar_exemplo(ex: dict, nome_arquivo: str) -> dict | None:
    """Eleva UM exemplo ao schema padrão. Retorna None se inválido."""
    msgs = ex.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return None
    # roles atuais
    roles = [m.get("role") for m in msgs if isinstance(m, dict)]
    user = next((m.get("content", "") for m in msgs if isinstance(m, dict)
                 and m.get("role") in ("user", "human", "humano")), "")
    assistant = next((m.get("content", "") for m in msgs if isinstance(m, dict)
                      and m.get("role") in ("assistant", "gpt", "modelo")), "")
    if not user or not assistant:
        return None
    # system: usa o que já existe ou o do tipo/geral
    system = next((m.get("content", "") for m in msgs if isinstance(m, dict)
                   and m.get("role") == "system"), "")
    if not system:
        system = _sistema_do_tipo(str(ex.get("tipo") or ex.get("_tipo") or ""))

    tipo = str(ex.get("tipo") or ex.get("_tipo") or "artigo").strip()
    # se o user parece pergunta (tem '?'), classifica como qna
    if tipo in ("", "artigo") and "?" in user:
        tipo = "qna"

    data = str(ex.get("data") or ex.get("_data") or
               datetime.now().isoformat(timespec="seconds"))

    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "_id": _id_de(user, assistant),
        "_fonte": str(ex.get("fonte") or ex.get("_fonte")
                      or f"padronizado/{nome_arquivo}"),
        "_tipo": tipo,
        "_categoria": str(ex.get("categoria") or ex.get("_categoria") or ""),
        "_assunto": str(ex.get("_assunto") or _assunto_do_user(user)),
        "_estilo": str(ex.get("estilo") or ex.get("_estilo") or ""),
        "_idioma": "pt-BR",
        "_data": data,
        "_nota": int(ex.get("_nota") or 4),
    }


def padronizar_arquivo(origem: Path, destino: Path, sobrescrever: bool) -> dict:
    """Padroniza um jsonl. Retorna {lidas, ok, invalidas, destino}."""
    linhas = origem.read_text(encoding="utf-8").splitlines()
    saidas: list[str] = []
    invalidas = 0
    for l in linhas:
        if not l.strip():
            continue
        try:
            ex = json.loads(l)
        except Exception:
            invalidas += 1
            continue
        novo = padronizar_exemplo(ex, origem.name)
        if novo is None:
            invalidas += 1
            continue
        saidas.append(json.dumps(novo, ensure_ascii=False))
    if not saidas:
        return {"lidas": len(linhas), "ok": 0, "invalidas": invalidas,
                "destino": ""}
    # backup se for sobrescrever
    if sobrescrever and destino.exists():
        try:
            shutil.copy2(destino, str(destino) + ".bak")
        except Exception:
            pass
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(saidas) + "\n", encoding="utf-8")
    return {"lidas": len(linhas), "ok": len(saidas), "invalidas": invalidas,
            "destino": str(destino)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Padroniza jsonl p/ o schema do Rigel")
    ap.add_argument("--origem", default="dados/gerados/massa_final",
                    help="Pasta ou arquivo .jsonl")
    ap.add_argument("--destino", default="",
                    help="Pasta de saída (vazio = mesmo lugar, sufixo _padrao)")
    ap.add_argument("--sobrescrever", action="store_true",
                    help="Escreve por cima do arquivo (com .bak antes)")
    args = ap.parse_args()

    origem = Path(args.origem)
    if origem.is_file():
        arquivos = [origem]
    elif origem.is_dir():
        arquivos = sorted(origem.glob("*.jsonl"))
    else:
        print(f"❌ Origem não encontrada: {origem}")
        return 1
    if not arquivos:
        print("✅ Nenhum .jsonl na origem.")
        return 0

    destino_base = Path(args.destino) if args.destino else None
    totais = {"lidas": 0, "ok": 0, "invalidas": 0}
    for arq in arquivos:
        if destino_base is not None:
            destino = destino_base / arq.name.replace(".jsonl", "_padrao.jsonl")
        else:
            destino = arq.with_name(arq.stem + "_padrao.jsonl")
        res = padronizar_arquivo(arq, destino, args.sobrescrever)
        for k in totais:
            totais[k] += res[k]
        if res["ok"]:
            print(f"  ✅ {arq.name}: {res['ok']}/{res['lidas']} exemplos → {res['destino']}")
        else:
            print(f"  ⚠️ {arq.name}: {res['invalidas']} inválidas (nada gravado)")
    print(f"\n🏁 Total: {totais['ok']} exemplos padronizados | "
          f"{totais['invalidas']} inválidas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
