#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
revisao.py — SERVIÇO DE REVISÃO DOS SUSPEITOS (página /revisar).

Pedido do usuário (17/08/2026): "onde eu vejo estes suspeitos? ...sim crie
mais uma página" — uma página onde o usuário vê cada texto marcado como
SUSPEITO pelo ajuizador, lê o conteúdo e decide: ✅ aprovar (vai pro treino)
ou ❌ descartar (fora do treino).

O que faz:
  - LÊ o relatório mais recente (logs/ajuizar_relatorio.json) e lista os
    arquivos classificados como "suspeito" por pasta, com caminho real.
  - Lista POR PASTA (agrupado) com contadores.
  - APROVAR: move o arquivo para dados/processed/<pasta>_aprovado/ (vira
    material de treino).
  - DESCARTAR: move para dados/gerados/desclassificados/<pasta>/ (fora do
    treino — regra: nunca apagar, só arquivar).
  - TUDO registrado em logs/revisao.log (persistente).
  - Nunca apaga nada; nunca sobrescreve.

Uso (dashboard):
  from dashboard.services.revisao import listar_suspeitos, aprovar, descartar
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
RELATORIO = PROJETO_ROOT / "logs" / "ajuizar_relatorio.json"
LOG = PROJETO_ROOT / "logs" / "revisao.log"
GERADOS = PROJETO_ROOT / "dados" / "gerados"
DESCLASSIFICADOS = PROJETO_ROOT / "dados" / "gerados" / "desclassificados"
PROCESSED = PROJETO_ROOT / "dados" / "processed"
# Registro persistente de decisões (aprovado/descartado) — o relatório de
# ajuizamento é ESTÁTICO e continua listando o arquivo; este registro faz o
# item SUMIR da lista depois de resolvido (sem fantasma "arquivo não
# encontrado").
DECISOES = PROJETO_ROOT / "estado" / "revisao_decisoes.json"


def _carregar_decisoes() -> dict:
    try:
        if DECISOES.exists():
            d = json.loads(DECISOES.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def _salvar_decisoes(d: dict) -> None:
    try:
        DECISOES.parent.mkdir(parents=True, exist_ok=True)
        DECISOES.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except Exception:
        pass


def _chave_decisao(pasta: str, arquivo: str) -> str:
    return f"{pasta}|{arquivo}"


def _registrar(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except Exception:
        pass


def _ler_relatorio() -> list[dict]:
    """Lê o relatório de ajuizamento (lista de pastas). Nunca falha."""
    try:
        if RELATORIO.exists():
            d = json.loads(RELATORIO.read_text(encoding="utf-8"))
            return d.get("pastas", []) if isinstance(d, dict) else (d or [])
    except Exception:
        pass
    return []


def _resolver_pasta(nome_pasta: str) -> Path | None:
    """Resolve o caminho real da pasta a partir do nome relativo a dados/gerados.

    Aceita: 'curtos', 'massa_final\\explicacao', 'gerados_local'.
    """
    nome = (nome_pasta or "").strip().replace("\\", "/")
    if not nome:
        return None
    # Tenta direto em dados/gerados
    cand = GERADOS / nome
    if cand.is_dir():
        return cand
    # Tenta sem o prefixo 'gerados/'
    if nome.startswith("gerados/"):
        cand2 = GERADOS / nome.split("/", 1)[1]
        if cand2.is_dir():
            return cand2
    return None


def _localizar_arquivo(pasta: Path, nome_arquivo: str) -> Path | None:
    """Procura o arquivo DENTRO da pasta (recursivo), pelo nome.

    O relatório de ajuizamento guarda só o NOME do arquivo — mas o ajuizador
    varre subpastas (ex.: gerados_local/_massa/processados/). Então montar o
    caminho na raiz da pasta não funciona. Busca recursiva resolve.
    """
    nome = (nome_arquivo or "").strip()
    if not nome:
        return None
    try:
        # busca direta primeiro (mais barato)
        direto = pasta / nome
        if direto.is_file():
            return direto
        for f in pasta.rglob(nome):
            if f.is_file():
                return f
    except Exception:
        pass
    return None


def listar_suspeitos() -> dict:
    """Lista os arquivos SUSPEITOS por pasta, com caminho e resumo.

    CORREÇÃO 17/08: itens já decididos (aprovado/descartado) ou que não
    existem mais são EXCLUÍDOS da lista — o relatório estático de ajuizamento
    continuaria mostrando "arquivo não encontrado" depois de resolver.
    """
    decisoes = _carregar_decisoes()
    pastas = []
    total_suspeitos = 0
    resolvidos = 0
    for p in _ler_relatorio():
        nome = p.get("pasta", "")
        arquivos = p.get("arquivos", []) or []
        suspeitos = [a for a in arquivos if a.get("classe") == "suspeito"]
        if not suspeitos:
            continue
        caminho_pasta = _resolver_pasta(nome)
        itens = []
        for a in suspeitos:
            nome_arq = a.get("arquivo", "")
            # já decidido? some da lista
            if _chave_decisao(nome, nome_arq) in decisoes:
                resolvidos += 1
                continue
            caminho_arq = _localizar_arquivo(caminho_pasta, nome_arq) if caminho_pasta else None
            existe = bool(caminho_arq and caminho_arq.is_file())
            # arquivo sumiu (movido por outro caminho) → não lista fantasma
            if not existe:
                resolvidos += 1
                continue
            itens.append({
                "arquivo": nome_arq,
                "classe": "suspeito",
                "juiz": bool(a.get("juiz") and a.get("juiz", {}).get("ok")),
                "caminho": str(caminho_arq) if caminho_arq else "",
                "existe": True,
            })
        if not itens:
            continue
        total_suspeitos += len(itens)
        pastas.append({
            "pasta": nome,
            "caminho": str(caminho_pasta) if caminho_pasta else "",
            "total": len(itens),
            "aprovados": p.get("aprovados", 0),
            "lixos": p.get("lixos", 0),
            "itens": itens,
        })
    pastas.sort(key=lambda x: -x["total"])
    return {
        "total": total_suspeitos,
        "resolvidos": resolvidos,
        "pastas": pastas,
        "relatorio": str(RELATORIO),
        "atualizado": datetime.now().isoformat(timespec="seconds"),
    }


def _conteudo_arquivo(caminho: str, max_caracteres: int = 3000) -> dict:
    """Lê o conteúdo do arquivo (primeiros N caracteres) com segurança."""
    try:
        p = Path(caminho)
        if not p.is_file():
            return {"ok": False, "erro": "Arquivo não encontrado."}
        texto = p.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "nome": p.name, "palavras": len(texto.split()),
                "caracteres": len(texto), "texto": texto[:max_caracteres],
                "truncado": len(texto) > max_caracteres}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def _mover_arquivo(origem: Path, destino_dir: Path) -> tuple[bool, str]:
    """Move o arquivo (nunca sobrescreve nem apaga)."""
    try:
        destino_dir.mkdir(parents=True, exist_ok=True)
        alvo = destino_dir / origem.name
        if alvo.exists():
            return False, "destino já existe (não sobrescrevi)"
        shutil.move(str(origem), str(alvo))
        return True, str(alvo)
    except Exception as e:
        return False, str(e)


def aprovar(pasta: str, arquivo: str) -> dict:
    """✅ Aprova um suspeito: move para dados/processed/<pasta>_aprovado/."""
    return _decidir(pasta, arquivo, acao="aprovar")


def aprovar_todos() -> dict:
    """✅ Aprova TODOS os suspeitos pendentes de uma vez (botão verde com
    confirmação na UI). Cada um vai para processed/<pasta>_aprovado/ e a
    decisão é registrada — eles saem da lista e NÃO vão para o juiz."""
    decisoes = _carregar_decisoes()
    aprovados = 0
    erros = 0
    for p in listar_suspeitos().get("pastas", []):
        caminho_pasta = _resolver_pasta(p["pasta"])
        if not caminho_pasta:
            continue
        destino_dir = PROCESSED / f"{caminho_pasta.name}_aprovado"
        for it in p.get("itens", []):
            if not (it.get("existe") and it.get("caminho")):
                continue
            chave = _chave_decisao(p["pasta"], it["arquivo"])
            if chave in decisoes:
                continue
            origem = Path(it["caminho"])
            ok, msg = _mover_arquivo(origem, destino_dir)
            if ok:
                decisoes[chave] = {
                    "acao": "aprovar",
                    "data": datetime.now().isoformat(timespec="seconds"),
                    "destino": msg,
                }
                _registrar(f"✅ Aprovado (todos): {p['pasta']}/{it['arquivo']} → {msg}")
                aprovados += 1
            else:
                erros += 1
    _salvar_decisoes(decisoes)
    return {
        "ok": True,
        "aprovados": aprovados,
        "erros": erros,
        "mensagem": (f"✅ {aprovados} texto(s) aprovado(s) para o treino! "
                      "Eles não passam pelo juiz."
                      + (f" ({erros} com erro)" if erros else "")),
    }


def descartar(pasta: str, arquivo: str) -> dict:
    """❌ Descarta um suspeito: move para dados/gerados/desclassificados/<pasta>/."""
    return _decidir(pasta, arquivo, acao="descartar")


def _decidir(pasta: str, arquivo: str, acao: str) -> dict:
    caminho_pasta = _resolver_pasta(pasta)
    if not caminho_pasta:
        return {"ok": False, "erro": f"Pasta não encontrada: {pasta}"}
    origem = _localizar_arquivo(caminho_pasta, arquivo)
    if not origem or not origem.is_file():
        return {"ok": False, "erro": f"Arquivo não encontrado: {arquivo}"}

    if acao == "aprovar":
        destino_dir = PROCESSED / f"{caminho_pasta.name}_aprovado"
    else:  # descartar
        destino_dir = DESCLASSIFICADOS / caminho_pasta.name

    ok, msg = _mover_arquivo(origem, destino_dir)
    if ok:
        # registra a decisão para o item SUMIR da lista (correção 17/08)
        decisoes = _carregar_decisoes()
        decisoes[_chave_decisao(pasta, arquivo)] = {
            "acao": acao, "data": datetime.now().isoformat(timespec="seconds"),
            "destino": msg,
        }
        _salvar_decisoes(decisoes)
        _registrar(f"{'✅ Aprovado' if acao=='aprovar' else '❌ Descartado'}: "
                   f"{pasta}/{arquivo} → {msg}")
        return {"ok": True, "acao": acao, "destino": msg,
                "mensagem": "Pronto! Texto "
                            + ("aprovado para o treino ✅" if acao == "aprovar"
                               else "arquivado fora do treino (não foi apagado)")}
    return {"ok": False, "erro": msg or "Falha ao mover o arquivo."}
