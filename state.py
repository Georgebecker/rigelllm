#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
state.py - Gerenciamento de estado persistente do gerador.
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
Mantém histórico de temas/respostas, contagens, controle de repetição e tópicos externos usados.
"""
import os
from collections import Counter, deque
from typing import List, Optional

from config import (
    ARQUIVO_HISTORICO_TEMAS,
    ARQUIVO_HISTORICO_RESPOSTAS,
    ARQUIVO_CONTAGEM_CATEGORIAS,
    ARQUIVO_CONTAGEM_ASSUNTOS,
    ARQUIVO_ESTADO_DIALOGOS,
    ARQUIVO_HISTORICO_TOPICOS,
    MAX_ITENS_REPETICAO_RECENTE,
)
from utils import carregar_json, salvar_json, hash_texto, normalizar_chave


class StateManager:
    """
    Gerencia todo o estado persistente do gerador:
    - Histórico de perguntas e respostas já usadas (para evitar repetição).
    - Contagem de uso por categoria e por assunto (para balanceamento).
    - Estado de diálogos já processados (hash do texto completo).
    - Histórico de tópicos externos já utilizados.
    """

    def __init__(self):
        # Carrega todos os estados do disco
        self._carregar_estados()

        # Histórico de tópicos externos usados (arquivo de texto, um por linha)
        self.historico_topicos = self._carregar_topicos_usados()

    def _carregar_estados(self) -> None:
        """Carrega todos os arquivos de estado do disco."""
        self.historico_temas = deque(
            carregar_json(ARQUIVO_HISTORICO_TEMAS, []),
            maxlen=MAX_ITENS_REPETICAO_RECENTE
        )
        self.historico_respostas = deque(
            carregar_json(ARQUIVO_HISTORICO_RESPOSTAS, []),
            maxlen=MAX_ITENS_REPETICAO_RECENTE
        )
        self.contagem_categorias = Counter(
            carregar_json(ARQUIVO_CONTAGEM_CATEGORIAS, {})
        )
        self.contagem_assuntos = Counter(
            carregar_json(ARQUIVO_CONTAGEM_ASSUNTOS, {})
        )
        self.estado_dialogos = carregar_json(
            ARQUIVO_ESTADO_DIALOGOS,
            {"processados": [], "custo_total": 0.0}
        )

    def _carregar_topicos_usados(self) -> List[str]:
        """Carrega o histórico de tópicos externos usados do arquivo de texto."""
        if not os.path.exists(ARQUIVO_HISTORICO_TOPICOS):
            return []
        with open(ARQUIVO_HISTORICO_TOPICOS, 'r', encoding='utf-8') as f:
            return [linha.strip() for linha in f if linha.strip()]

    def _salvar_topicos_usados(self) -> None:
        """Salva o histórico de tópicos externos usados no arquivo de texto."""
        os.makedirs(os.path.dirname(ARQUIVO_HISTORICO_TOPICOS), exist_ok=True)
        with open(ARQUIVO_HISTORICO_TOPICOS, 'w', encoding='utf-8') as f:
            for topico in self.historico_topicos:
                f.write(topico + "\n")

    # ------------------------------------------------------------------------
    # Verificação de duplicatas
    # ------------------------------------------------------------------------
    def tema_ja_usado(self, pergunta: str) -> bool:
        """Verifica se uma pergunta já foi usada."""
        return hash_texto(pergunta) in self.historico_temas

    def resposta_ja_usada(self, resposta: str) -> bool:
        """Verifica se uma resposta já foi usada."""
        return hash_texto(resposta) in self.historico_respostas

    def dialogo_ja_processado(self, texto_hash: str) -> bool:
        """Verifica se um diálogo (hash do texto completo) já foi processado."""
        return texto_hash in self.estado_dialogos["processados"]

    def topico_externo_ja_usado(self, topico: str) -> bool:
        """Verifica se um tópico externo já foi usado."""
        return topico in self.historico_topicos

    # ------------------------------------------------------------------------
    # Registro de novos itens
    # ------------------------------------------------------------------------
    def registrar_item(
        self,
        pergunta: str,
        resposta: str,
        categoria: str,
        assunto: str,
        texto_hash: Optional[str] = None,
        custo: float = 0.0
    ) -> None:
        """
        Registra um novo item gerado, atualizando todos os contadores e históricos.
        """
        # Registra a pergunta
        self.historico_temas.append(hash_texto(pergunta))

        # Registra a resposta (se houver)
        if resposta:
            self.historico_respostas.append(hash_texto(resposta))

        # Atualiza contagens de categoria e assunto
        self.contagem_categorias[categoria] += 1
        self.contagem_assuntos[normalizar_chave(assunto)] += 1

        # Registra no estado de diálogos (hash do texto completo e custo)
        if texto_hash:
            self.estado_dialogos["processados"].append(texto_hash)
        self.estado_dialogos["custo_total"] += custo

        # Persiste todos os estados
        self.persistir()

    def registrar_topico_externo_usado(self, topico: str) -> None:
        """Registra um tópico externo como usado."""
        if topico not in self.historico_topicos:
            self.historico_topicos.append(topico)
            self._salvar_topicos_usados()

    # ------------------------------------------------------------------------
    # Consultas de contagem
    # ------------------------------------------------------------------------
    def get_contagem_categoria(self, categoria: str) -> int:
        """Retorna a quantidade de vezes que uma categoria foi usada."""
        return self.contagem_categorias.get(categoria, 0)

    def get_contagem_assunto(self, assunto: str) -> int:
        """Retorna a quantidade de vezes que um assunto foi usado."""
        return self.contagem_assuntos.get(normalizar_chave(assunto), 0)

    def get_total_gasto(self) -> float:
        """Retorna o total gasto até o momento."""
        return self.estado_dialogos["custo_total"]

    def get_categorias_mais_usadas(self, n: int = 5) -> List[tuple]:
        """Retorna as n categorias mais usadas."""
        return self.contagem_categorias.most_common(n)

    def get_assuntos_mais_usados(self, n: int = 5) -> List[tuple]:
        """Retorna os n assuntos mais usados."""
        return self.contagem_assuntos.most_common(n)

    # ------------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------------
    def persistir(self) -> None:
        """Salva todos os estados em disco."""
        salvar_json(ARQUIVO_HISTORICO_TEMAS, list(self.historico_temas))
        salvar_json(ARQUIVO_HISTORICO_RESPOSTAS, list(self.historico_respostas))
        salvar_json(ARQUIVO_CONTAGEM_CATEGORIAS, dict(self.contagem_categorias))
        salvar_json(ARQUIVO_CONTAGEM_ASSUNTOS, dict(self.contagem_assuntos))
        salvar_json(ARQUIVO_ESTADO_DIALOGOS, self.estado_dialogos)
        # Tópicos usados são salvos separadamente a cada adição, mas por segurança também salvamos aqui
        self._salvar_topicos_usados()

    def reset(self) -> None:
        """Reseta todos os estados (cuidado: destrói dados persistentes)."""
        self.historico_temas.clear()
        self.historico_respostas.clear()
        self.contagem_categorias.clear()
        self.contagem_assuntos.clear()
        self.estado_dialogos = {"processados": [], "custo_total": 0.0}
        self.historico_topicos.clear()
        self.persistir()


# ============================================================================
# EXPORTAR A CLASSE
# ============================================================================
__all__ = ["StateManager"]