#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
saida_manager.py - Escrita centralizada de JSONL SFT (messages) para os geradores.
Versão: 1.0.0 | Data: 02/08/2026

Centraliza a saída JSONL dos geradores (dialogos2.py, rss_processor.py, futuros):

  - SYSTEM_PROMPT canônico do Rigel (mesmo do createjsonl.py)
  - gerar_messages(pergunta, resposta, sistema=None) -> {"messages": [...]}
  - EscritorJsonl: sharding automático (arquivos de N exemplos) em
    dados/gerados/jsonl/<dataset>/  (mesma área do pipeline -> Treino Local)

Campos extras de rastreamento: _categoria, _assunto, _nota.

Uso pelos geradores:
    from saida_manager import EscritorJsonl
    esc = EscritorJsonl("dialogos2", exemplos_por_arquivo=1000)
    esc.salvar(pergunta=..., resposta=..., categoria=..., assunto=..., nota=...)
    esc.close()   # ou atexit
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent
DESTINO_BASE = _RAIZ / "dados" / "gerados" / "jsonl"

# ⭐ FONTE ÚNICA do System Prompt do Rigel.
# createjsonl.py e converter_txt_jsonl.py importam daqui (não duplicar).
SYSTEM_PROMPT = (
    "Você é o Rigel, um assistente virtual brasileiro. "
    "Fale em português brasileiro padrão, com naturalidade e calor humano. "
    "Quando o usuário cumprimentar ou fizer conversa rápida (ex: 'oi', 'tudo bem?', 'e aí?', "
    "'bom dia'), responda de forma CURTA e casual com saudações brasileiras naturais "
    "(ex: 'Oi! Tudo bem por aqui, e com você?', 'E aí! Beleza?', 'Bom dia!'), SEM recitar sua "
    "descrição e SEM se apresentar de forma robótica. Identifique-se como Rigel apenas quando "
    "perguntado diretamente. "
    "NUNCA termine respostas informativas com perguntas genéricas como 'Posso ajudar com algo "
    "mais?'."
)


def gerar_messages(pergunta: str, resposta: str, sistema: str | None = None) -> dict:
    """Monta o exemplo no formato padrão do Rigel (com metadados de rastreio)."""
    return {
        "messages": [
            {"role": "system", "content": sistema or SYSTEM_PROMPT},
            {"role": "user", "content": pergunta},
            {"role": "assistant", "content": resposta},
        ],
        "_id": hashlib.md5(f"{pergunta}|{resposta}".encode("utf-8")).hexdigest()[:16],
        "_idioma": "pt-BR",
        "_data": datetime.now().isoformat(timespec="seconds"),
    }


class EscritorJsonl:
    """Escreve exemplos JSONL com sharding em dados/gerados/jsonl/<dataset>/."""

    def __init__(self, dataset: str, exemplos_por_arquivo: int = 1000,
                 sistema: str | None = None):
        self.dataset = str(dataset or "dataset").replace("/", "_").replace("\\", "_")
        self.exemplos_por_arquivo = max(1, int(exemplos_por_arquivo or 1000))
        self.sistema = sistema or SYSTEM_PROMPT
        self.pasta = DESTINO_BASE / self.dataset
        os.makedirs(self.pasta, exist_ok=True)
        self._fh = None
        self._arquivo_atual = 0
        self._no_arquivo = 0
        self.total = 0
        self._caminho_atual: Path | None = None

    @property
    def caminho_atual(self) -> str | None:
        """Caminho do shard JSONL que está sendo escrito agora."""
        return str(self._caminho_atual) if self._caminho_atual else None

    def _abrir(self) -> None:
        self._fechar()
        self._arquivo_atual += 1
        self._no_arquivo = 0
        caminho = self.pasta / f"{self.dataset}_{self._arquivo_atual:04d}.jsonl"
        self._caminho_atual = caminho
        self._fh = open(caminho, "w", encoding="utf-8")

    def _fechar(self) -> None:
        if self._fh:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None

    def salvar(self, pergunta: str, resposta: str, categoria=None,
               assunto=None, nota=None, fonte=None) -> bool:
        """Escreve um exemplo. Retorna True se foi escrito."""
        if not pergunta or not resposta:
            return False
        if self._fh is None:
            self._abrir()
        ex = gerar_messages(pergunta, resposta, self.sistema)
        ex["_fonte"] = fonte or self.dataset
        if categoria is not None:
            ex["_categoria"] = categoria
        if assunto is not None:
            ex["_assunto"] = assunto
        if nota is not None:
            ex["_nota"] = nota
        self._fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
        self.total += 1
        self._no_arquivo += 1
        if self._no_arquivo >= self.exemplos_por_arquivo:
            self._abrir()  # próximo shard (removido no close se ficar vazio)
        return True

    def flush(self) -> None:
        """Grava o buffer no disco AGORA (evita perda se o processo morrer sem close)."""
        if self._fh:
            try:
                self._fh.flush()
            except Exception:
                pass

    def close(self) -> int:
        """Fecha arquivos e remove shards vazios. Retorna total de exemplos."""
        self._fechar()
        try:
            if self.total == 0:
                primeiro = self.pasta / f"{self.dataset}_0001.jsonl"
                if primeiro.exists():
                    primeiro.unlink()
            else:
                ultimo = self.pasta / f"{self.dataset}_{self._arquivo_atual:04d}.jsonl"
                if ultimo.exists() and ultimo.stat().st_size == 0:
                    ultimo.unlink()
        except Exception:
            pass
        return self.total

    def __enter__(self) -> "EscritorJsonl":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False
