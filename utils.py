#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
utils.py - Funções utilitárias para o gerador de dados sintéticos
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
import os
import json
import hashlib
import re
from datetime import datetime
from typing import List, Any, Dict, Optional


# ----------------------------------------------------------------------------
# Manipulação de JSON
# ----------------------------------------------------------------------------
def carregar_json(caminho: str, padrao: Any) -> Any:
    """Carrega um arquivo JSON, retornando um valor padrão se não existir ou for inválido."""
    if not os.path.exists(caminho):
        return padrao
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return padrao


def salvar_json(caminho: str, dados: Any) -> None:
    """Salva dados em um arquivo JSON, criando diretórios se necessário."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------
# Texto e hash
# ----------------------------------------------------------------------------
def normalizar_chave(texto: str) -> str:
    """Normaliza texto para uso como chave (minúsculo, sem pontuação, espaços simples)."""
    texto = texto.lower().strip()
    texto = re.sub(r"[^\w\sáàâãéêíóôõúçñ-]", "", texto, flags=re.UNICODE)
    texto = re.sub(r"\s+", " ", texto)
    return texto


def hash_texto(texto: str) -> str:
    """Retorna o hash SHA256 da versão normalizada do texto."""
    return hashlib.sha256(normalizar_chave(texto).encode('utf-8')).hexdigest()


def limpar_texto(texto: str) -> str:
    """Remove URLs, e-mails, caracteres de controle e espaços extras."""
    if not texto:
        return ""
    texto = re.sub(r"https?://\S+|www\.\S+", "", texto)
    texto = re.sub(r"\S+@\S+\.\S+", "", texto)
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


# ----------------------------------------------------------------------------
# Tópicos externos (arquivo .txt com um tópico por linha)
# ----------------------------------------------------------------------------
def carregar_topicos_externos(caminho_arquivo: str = "topicos.txt") -> List[str]:
    """
    Carrega tópicos de um arquivo de texto, um por linha.
    Ignora linhas vazias e espaços em branco.
    Retorna uma lista de strings.
    """
    if not os.path.exists(caminho_arquivo):
        return []
    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
        linhas = [linha.strip() for linha in f if linha.strip()]
    return linhas


def remover_topico_usado(caminho_arquivo: str, topico: str) -> None:
    """
    Remove uma linha específica do arquivo de tópicos.
    Útil para evitar repetição após o uso do tópico.
    """
    if not os.path.exists(caminho_arquivo):
        return
    with open(caminho_arquivo, 'r', encoding='utf-8') as f:
        linhas = f.readlines()
    with open(caminho_arquivo, 'w', encoding='utf-8') as f:
        for linha in linhas:
            if linha.strip() != topico:
                f.write(linha)


def topico_ja_usado(caminho_historico: str, topico: str) -> bool:
    """Verifica se um tópico já foi usado (baseado em um arquivo de histórico)."""
    if not os.path.exists(caminho_historico):
        return False
    with open(caminho_historico, 'r', encoding='utf-8') as f:
        usados = [linha.strip() for linha in f if linha.strip()]
    return topico in usados


def registrar_topico_usado(caminho_historico: str, topico: str) -> None:
    """Registra um tópico como usado (append em arquivo de histórico)."""
    os.makedirs(os.path.dirname(caminho_historico), exist_ok=True)
    with open(caminho_historico, 'a', encoding='utf-8') as f:
        f.write(topico + "\n")


def get_status_topicos(caminho_topicos: str, caminho_historico: str) -> Dict[str, Any]:
    """
    Retorna um dicionário com o status dos tópicos:
    - total: número total de tópicos no arquivo
    - usados: número de tópicos já usados
    - restantes: número de tópicos ainda não usados
    - proximo: próximo tópico a ser usado (ou None)
    - todos_usados: booleano
    """
    topicos = carregar_topicos_externos(caminho_topicos)
    total = len(topicos)

    if total == 0:
        return {
            "total": 0,
            "usados": 0,
            "restantes": 0,
            "proximo": None,
            "todos_usados": True,
            "topicos": []
        }

    # Carrega histórico de usados
    usados = []
    if os.path.exists(caminho_historico):
        with open(caminho_historico, 'r', encoding='utf-8') as f:
            usados = [linha.strip() for linha in f if linha.strip()]

    # Filtra os não usados (mantendo a ordem original)
    nao_usados = [t for t in topicos if t not in usados]

    return {
        "total": total,
        "usados": len(usados),
        "restantes": len(nao_usados),
        "proximo": nao_usados[0] if nao_usados else None,
        "todos_usados": len(nao_usados) == 0,
        "topicos": topicos,
        "usados_lista": usados,
        "nao_usados": nao_usados
    }


def exibir_status_topicos(caminho_topicos: str, caminho_historico: str) -> None:
    """
    Exibe um relatório formatado com o status dos tópicos.
    """
    status = get_status_topicos(caminho_topicos, caminho_historico)

    print("\n" + "=" * 70)
    print("📋 STATUS DOS TÓPICOS EXTERNOS")
    print("=" * 70)
    print(f"   📂 Arquivo: {caminho_topicos}")
    print(f"   📂 Histórico: {caminho_historico}")
    print(f"   Total de tópicos: {status['total']}")
    print(f"   ✅ Já usados: {status['usados']}")
    print(f"   ⏳ Restantes: {status['restantes']}")
    print(f"   🔹 Próximo tópico: {status['proximo'] if status['proximo'] else '(todos já usados)'}")

    if status['restantes'] > 0 and status['total'] > 0:
        progresso = (status['usados'] / status['total']) * 100
        barra = int(progresso / 5) * "█" + "░" * (20 - int(progresso / 5))
        print(f"   📊 Progresso: [{barra}] {progresso:.1f}%")

    if status['todos_usados']:
        print("   🎯 Todos os tópicos foram usados! O sistema usará categorias internas.")

    # Mostra os próximos 5 tópicos
    if status['nao_usados']:
        print("\n   📌 Próximos tópicos:")
        for i, t in enumerate(status['nao_usados'][:5]):
            print(f"      {i+1}. {t}")
        if len(status['nao_usados']) > 5:
            print(f"      ... e mais {len(status['nao_usados']) - 5} tópicos.")

    print("=" * 70)


# ----------------------------------------------------------------------------
# Salvamento de textos gerados
# ----------------------------------------------------------------------------
def salvar_texto(texto: str, prefixo: str, indice: int, pasta: str) -> str:
    """Salva um texto em um arquivo .txt com numeração."""
    os.makedirs(pasta, exist_ok=True)
    nome = f"{prefixo}_{indice:06d}.txt"
    caminho = os.path.join(pasta, nome)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(texto)
    return caminho


def salvar_descarte(texto: str, prefixo: str, motivo: str, indice: int, pasta_descartes: str) -> str:
    """Salva um texto descartado junto com o motivo."""
    os.makedirs(pasta_descartes, exist_ok=True)
    nome = f"{prefixo}_descarte_{indice:06d}.txt"
    caminho = os.path.join(pasta_descartes, nome)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(f"MOTIVO DO DESCARTE: {motivo}\n\n--- TEXTO GERADO ---\n\n{texto if texto else '(vazio)'}")
    return caminho


def salvar_metadados(metadados: Dict, arquivo_metadados: str) -> None:
    """Adiciona um registro de metadados a um arquivo JSON."""
    historico = carregar_json(arquivo_metadados, [])
    historico.append(metadados)
    salvar_json(arquivo_metadados, historico)


# ----------------------------------------------------------------------------
# Exibição de categorias (para --listar-temas)
# ----------------------------------------------------------------------------
def exibir_categoria(titulo: str, lista: List[str], max_itens: int = 12) -> None:
    """Exibe uma lista de itens de forma organizada."""
    print(f"\n{titulo}")
    for item in lista[:max_itens]:
        print(f"   - {item}")
    if len(lista) > max_itens:
        print(f"   ... e mais {len(lista)-max_itens} itens")