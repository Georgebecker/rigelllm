#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
# converter_jsonl_messages.py — converte datasets JSONL para o formato messages
# (SFT) — vários esquemas de entrada para UM formato de saída.
# Data: 19/08/2026
# ============================================================================
# Entradas aceitas (uma por linha):
#   {"messages": [...]}                     -> passa direto (já pronto)
#   {"prompt": ..., "thought": ..., "answer": ...}   -> user=prompt, assistant=answer (descarta thought)
#   {"instruction": ..., "output": ...}     -> alpaca -> user/assistant
#   {"pergunta": ..., "resposta": ...}      -> user/assistant
#   {"question": ..., "answer": ...}        -> user/assistant
#   {"text": ...}                           -> PRÉ-TREINO: não vira conversa (descartado)
#
# Saída: {"messages": [{"role":"user","content":...},{"role":"assistant","content":...}]}
# - Limpa mojibake real (duplo-encoding; NUNCA "Ã" solto — falso positivo).
# - Dedup por md5 (conjunto limitado p/ memória constante).
# - Streaming (lê linha, escreve linha) + progresso REAL persistido em
#   logs/converter_jsonl_progresso.json.
# - Saída em lotes de EXEMPLOS_POR_ARQUIVO em <saida>/<nome>_<NNNNN>.jsonl.
#
# Uso:
#   python scripts/converter_jsonl_messages.py \
#       --origem <pasta-ou-arquivo.jsonl> \
#       --saida  <pasta-destino>
# ============================================================================
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# Reutiliza o sanitizador do projeto (regra de ouro: tratamento = conjunto de
# ajustar/aproveitar/eliminar/sanitizar)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sanitizador_ptbr import (  # noqa: E402
    corrigir_mojibake_inteligente,
    remover_invalidos,
    avaliar_conteudo,
)

MAX_DEDUP = 1_000_000
EXEMPLOS_POR_ARQUIVO = 2000
MIN_CAMPO_CHARS = 5
LOG_PROGRESSO = os.path.join("logs", "converter_jsonl_progresso.json")


def _tratar_texto(texto: str):
    """Tratamento completo de UM campo: corrige mojibake, remove caracteres
    que não existem no PT-BR (ABNT2) e ELIMINA se virar lixo (excesso de
    caracteres inválidos ou vazio). Retorna texto limpo ou None (descartar)."""
    if not texto:
        return None
    corrigido = corrigir_mojibake_inteligente(str(texto))
    limpo, n_removidos = remover_invalidos(corrigido)
    status, _motivo = avaliar_conteudo(limpo, n_removidos)
    if status == "descartado":
        return None
    final = " ".join(limpo.split()).strip()
    return final or None


def _extrair_pergunta(prompt_val) -> str:
    """Prompt pode ser texto puro OU uma lista serializada de mensagens
    (ex.: \"[{'role': 'user', 'content': '...'}]\" — formato ultra-alpaca)."""
    txt = str(prompt_val or "").strip()
    if txt.startswith("["):
        try:
            import ast
            lista = ast.literal_eval(txt)
            if isinstance(lista, list):
                partes = []
                for m in lista:
                    if isinstance(m, dict):
                        role = str(m.get("role") or m.get("from") or "").lower()
                        content = m.get("content") or m.get("value")
                        if content and role in ("user", "human", "h", "system"):
                            partes.append(str(content).strip())
                if partes:
                    return " ".join(partes).strip()
        except Exception:
            pass
        try:
            lista2 = json.loads(txt)
            if isinstance(lista2, list):
                partes = [str(m.get("content") or "") for m in lista2
                          if isinstance(m, dict)
                          and str(m.get("role") or "").lower() in ("user", "human", "system")]
                if partes:
                    return " ".join(partes).strip()
        except Exception:
            pass
    return txt


def _converter_linha(obj: dict, vistos: set):
    """Devolve {'messages': [...]} a partir de qualquer esquema aceito.
    None se não dá para virar conversa (lixo, duplicado ou texto puro)."""
    if not isinstance(obj, dict):
        return None
    msgs = obj.get("messages")
    if isinstance(msgs, list) and msgs:
        # já em messages: aproveita, mas garante user/assistant com conteúdo
        turnos = []
        for m in msgs:
            if isinstance(m, dict):
                role = str(m.get("role") or m.get("from") or "").strip().lower()
                conteudo_limpo = _tratar_texto(m.get("content") or m.get("value") or "")
                if conteudo_limpo and role in ("user", "human", "h", "assistant", "gpt", "a", "bot", "ia"):
                    if role in ("human", "h"):
                        role = "user"
                    elif role in ("gpt", "a", "bot", "ia"):
                        role = "assistant"
                    turnos.append({"role": role, "content": conteudo_limpo})
        if any(t["role"] == "user" for t in turnos) and any(t["role"] == "assistant" for t in turnos):
            return _dedup({"messages": turnos}, vistos)
        return None
    # Esquemas de pergunta/resposta (inclui 'completion' e prompt serializado)
    pergunta = (obj.get("prompt") or obj.get("instruction")
                or obj.get("pergunta") or obj.get("question"))
    resposta = (obj.get("answer") or obj.get("output") or obj.get("resposta")
                or obj.get("completion"))
    pergunta = _tratar_texto(_extrair_pergunta(pergunta))
    resposta = _tratar_texto(str(resposta or ""))
    if not pergunta or not resposta:
        return None
    if len(pergunta) < MIN_CAMPO_CHARS or len(resposta) < MIN_CAMPO_CHARS:
        return None
    return _dedup({"messages": [
        {"role": "user", "content": pergunta},
        {"role": "assistant", "content": resposta},
    ]}, vistos)


def _dedup(entry: dict, vistos: set):
    prompt = str(entry["messages"][0]["content"])
    answer = str(entry["messages"][-1]["content"])
    chave = hashlib.md5((prompt + "\x01" + answer).encode("utf-8", "replace")).hexdigest()
    if chave in vistos:
        return None
    if len(vistos) < MAX_DEDUP:
        vistos.add(chave)
    return entry


def _progresso(**kw) -> None:
    kw["atualizado_em"] = time.strftime("%H:%M:%S")
    try:
        os.makedirs("logs", exist_ok=True)
        with open(LOG_PROGRESSO, "w", encoding="utf-8") as f:
            json.dump(kw, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origem", required=True, help="pasta OU arquivo .jsonl")
    ap.add_argument("--saida", required=True, help="pasta de saída")
    ap.add_argument("--max-linhas", type=int, default=0, help="limita p/ teste")
    args = ap.parse_args()

    origem = Path(args.origem)
    saida = Path(args.saida)
    if not origem.exists():
        print(f"ERRO: origem não encontrada: {origem}")
        return 1
    saida.mkdir(parents=True, exist_ok=True)

    if origem.is_dir():
        arquivos = sorted(p for p in origem.rglob("*")
                          if p.is_file() and p.suffix.lower() in (".jsonl", ".json"))
    else:
        arquivos = [origem]
    if not arquivos:
        print("Nenhum arquivo .jsonl/.json encontrado.")
        return 1
    print(f"Arquivos de origem: {len(arquivos)}")

    vistos: set = set()
    lidas = validas = invalidas = 0
    arquivo_atual = 0
    buff: list = []
    t0 = time.time()

    def _flush(ultimo: bool = False) -> None:
        nonlocal arquivo_atual, buff
        if not buff:
            return
        arquivo_atual += 1
        destino = saida / f"convertido_{arquivo_atual:05d}.jsonl"
        with open(destino, "w", encoding="utf-8") as f:
            f.write("\n".join(buff) + "\n")
        buff = []

    for arq in arquivos:
        with open(arq, encoding="utf-8", errors="replace") as f:
            for linha in f:
                lidas += 1
                if args.max_linhas and lidas > args.max_linhas:
                    break
                linha = linha.strip()
                if not linha:
                    invalidas += 1
                    continue
                try:
                    obj = json.loads(linha)
                except Exception:
                    invalidas += 1
                    continue
                novo = _converter_linha(obj, vistos)
                if novo is None:
                    invalidas += 1
                    continue
                validas += 1
                buff.append(json.dumps(novo, ensure_ascii=False))
                if len(buff) >= EXEMPLOS_POR_ARQUIVO:
                    _flush()
                if lidas % 100_000 == 0:
                    print(f"  {lidas:,} lidas | válidas: {validas:,} | descartadas: {invalidas:,} | {time.time() - t0:.0f}s")
                    _progresso(lidas=lidas, validas=validas, invalidas=invalidas)
        if args.max_linhas and lidas > args.max_linhas:
            break

    _flush(ultimo=True)
    print("=" * 60)
    print(f"CONCLUÍDO: {lidas:,} lidas | {validas:,} convertidas | {invalidas:,} descartadas")
    print(f"Saída: {arquivo_atual} arquivo(s) em {saida}")
    _progresso(lidas=lidas, validas=validas, invalidas=invalidas, concluido=True,
               saida=str(saida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
