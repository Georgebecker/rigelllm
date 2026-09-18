#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Audita JSONL antes do Colab ou de um treino local.

Somente le os dados: nao sanitiza, move, apaga nem sobrescreve datasets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_DIR = ROOT / "dados" / "processed" / "jsonl"
TOKENIZER_PATH = ROOT / "tokenizer" / "tokenizer.json"
SEQ_LEN = 512
MIN_USER_CHARS = 10
MIN_ASSISTANT_CHARS = 20

from treinar_com_jsonl import normalizar_turnos
from sanitizador_ptbr import corrigir_mojibake_inteligente, remover_invalidos


def _tokenizer() -> Any:
    if not TOKENIZER_PATH.exists():
        return None
    try:
        from tokenizers import Tokenizer
        return Tokenizer.from_file(str(TOKENIZER_PATH))
    except Exception as exc:
        print(f"AVISO: tokenizer nao carregado: {exc}")
        return None


def _arquivos(args: argparse.Namespace) -> list[Path]:
    if args.arquivo:
        caminho = Path(args.arquivo).expanduser()
        if not caminho.is_file() or caminho.suffix.lower() != ".jsonl":
            raise FileNotFoundError(f"arquivo JSONL nao encontrado: {caminho}")
        return [caminho]
    pasta = Path(args.pasta).expanduser() if args.pasta else DEFAULT_DIR
    if not pasta.is_dir():
        raise FileNotFoundError(f"pasta nao encontrada: {pasta}")
    return sorted(p for p in pasta.rglob("*.jsonl") if p.is_file())


def _textos(turnos: list[tuple[str, str]]) -> tuple[str, str]:
    usuario = " ".join(t for role, t in turnos if role == "user")
    assistente = " ".join(t for role, t in turnos if role == "assistant")
    return usuario, assistente


def _base(caminho: Path) -> dict[str, Any]:
    return {"arquivo": str(caminho), "linhas": 0, "json_validos": 0,
            "json_invalidos": 0, "formatos_validos": 0,
            "sem_formato_treino": 0, "validos_treino": 0, "curtos": 0,
            "respostas_curtas": 0, "mojibake": 0, "caracteres_invalidos": 0,
            "acima_seq_len": 0, "duplicatas": 0, "erros": [], "amostras": []}


def analisar_arquivo(caminho: Path, limite: int | None, tokenizer: Any,
                     qtd_amostras: int) -> dict[str, Any]:
    resultado = _base(caminho)
    hashes: set[str] = set()
    try:
        arquivo = caminho.open("r", encoding="utf-8", errors="replace")
    except OSError as exc:
        resultado["erros"].append(f"falha ao abrir: {exc}")
        return resultado
    with arquivo:
        for numero, linha in enumerate(arquivo, 1):
            if limite is not None and numero > limite:
                break
            resultado["linhas"] += 1
            linha = linha.strip()
            if not linha:
                continue
            try:
                obj = json.loads(linha)
            except json.JSONDecodeError as exc:
                resultado["json_invalidos"] += 1
                if len(resultado["erros"]) < 5:
                    resultado["erros"].append(f"linha {numero}: JSON invalido ({exc.msg})")
                continue
            resultado["json_validos"] += 1
            turnos = normalizar_turnos(obj)
            if not turnos:
                resultado["sem_formato_treino"] += 1
                continue
            resultado["formatos_validos"] += 1
            usuario, assistente = _textos(turnos)
            if len(usuario) < MIN_USER_CHARS or len(assistente) < MIN_ASSISTANT_CHARS:
                resultado["curtos"] += 1
            if len(assistente) < MIN_ASSISTANT_CHARS:
                resultado["respostas_curtas"] += 1
            texto = f"{usuario}\n{assistente}"
            corrigido = corrigir_mojibake_inteligente(texto)
            _, removidos = remover_invalidos(corrigido)
            if corrigido != texto:
                resultado["mojibake"] += 1
            resultado["caracteres_invalidos"] += removidos
            digest = hashlib.md5(texto.encode("utf-8", errors="replace")).hexdigest()
            if digest in hashes:
                resultado["duplicatas"] += 1
            hashes.add(digest)
            if tokenizer is not None:
                try:
                    if len(tokenizer.encode(texto).ids) > SEQ_LEN:
                        resultado["acima_seq_len"] += 1
                except Exception as exc:
                    if len(resultado["erros"]) < 5:
                        resultado["erros"].append(f"linha {numero}: tokenizer ({exc})")
            resultado["validos_treino"] += 1
            if len(resultado["amostras"]) < qtd_amostras:
                resultado["amostras"].append({"usuario": usuario[:160],
                                              "assistente": assistente[:160]})
    return resultado


def _total(relatorios: list[dict[str, Any]]) -> dict[str, Any]:
    campos = ("linhas", "json_validos", "json_invalidos", "formatos_validos",
              "sem_formato_treino", "validos_treino", "curtos", "respostas_curtas",
              "mojibake", "caracteres_invalidos", "acima_seq_len", "duplicatas")
    total: dict[str, Any] = {c: sum(int(r[c]) for r in relatorios) for c in campos}
    total["arquivos"] = len(relatorios)
    total["erros"] = [e for r in relatorios for e in r["erros"]][:20]
    total["alertas"] = []
    if total["curtos"]:
        total["alertas"].append("ha exemplos curtos")
    if total["duplicatas"]:
        total["alertas"].append("ha duplicatas")
    if total["acima_seq_len"]:
        total["alertas"].append("ha exemplos maiores que seq_len")
    if total["validos_treino"] < 100:
        total["alertas"].append("poucos exemplos para ensinar o modelo")
    total["aprovado"] = (total["linhas"] > 0 and total["json_invalidos"] == 0
                         and total["validos_treino"] > 0
                         and total["sem_formato_treino"] == 0
                         and total["mojibake"] == 0
                         and total["caracteres_invalidos"] == 0)
    return total


def _pct(parte: int, total: int) -> str:
    return f"{100 * parte / total:.1f}%" if total else "0.0%"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audita JSONL para Colab ou treino local.")
    parser.add_argument("--pasta", help="pasta raiz; padrao: dados/processed/jsonl")
    parser.add_argument("--arquivo", help="analisa apenas um arquivo JSONL")
    parser.add_argument("--completo", action="store_true", help="le todas as linhas")
    parser.add_argument("--linhas", type=int, default=1000,
                        help="linhas por arquivo no modo amostra")
    parser.add_argument("--amostras", type=int, default=0,
                        help="quantas amostras guardar no relatorio JSON")
    parser.add_argument("--salvar", help="salva relatorio JSON neste caminho")
    args = parser.parse_args()
    try:
        arquivos = _arquivos(args)
    except FileNotFoundError as exc:
        print(f"ERRO: {exc}")
        return 1
    if not arquivos:
        print("ERRO: nenhum arquivo .jsonl encontrado")
        return 1
    limite = None if args.completo else max(1, args.linhas)
    tokenizer = _tokenizer()
    relatorios = [analisar_arquivo(p, limite, tokenizer, max(0, args.amostras))
                  for p in arquivos]
    total = _total(relatorios)
    print("=" * 72)
    print("AUDITORIA DE QUALIDADE JSONL")
    print("Somente leitura: nenhum dataset foi alterado.")
    print(f"Arquivos: {total['arquivos']} | Linhas lidas: {total['linhas']}")
    print(f"JSON valido: {total['json_validos']} | JSON invalido: {total['json_invalidos']}")
    print(f"Formato aceito pelo treinador: {total['validos_treino']} ({_pct(total['validos_treino'], total['json_validos'])})")
    print(f"Sem formato de treino: {total['sem_formato_treino']}")
    print(f"Mojibake: {total['mojibake']} | Caracteres invalidos: {total['caracteres_invalidos']}")
    print(f"Duplicatas: {total['duplicatas']} | Acima de {SEQ_LEN} tokens: {total['acima_seq_len']}")
    if total["erros"]:
        print("ERROS:")
        for erro in total["erros"]:
            print(f"- {erro}")
    if total["alertas"]:
        print("ALERTAS: " + "; ".join(total["alertas"]))
    print("RESULTADO: APROVADO" if total["aprovado"] else "RESULTADO: REPROVADO")
    if args.salvar:
        destino = Path(args.salvar)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps({"total": total, "arquivos": relatorios},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Relatorio salvo em: {destino}")
    return 0 if total["aprovado"] else 2


if __name__ == "__main__":
    sys.exit(main())