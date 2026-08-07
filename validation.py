#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
validation.py - Validação de qualidade de textos e diálogos gerados.
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
Contém funções para verificar e limpar arquivos inválidos já gerados.
"""
import os
import re
from collections import Counter
from typing import Tuple, Optional, List

from utils import limpar_texto, normalizar_chave


# ----------------------------------------------------------------------------
# Constantes de validação
# ----------------------------------------------------------------------------
VAGAS = {
    "sim", "não", "nao", "talvez", "ok", "claro", "verdade", "mentira",
    "não sei", "nao sei", "não sei responder", "talvez sim", "talvez não",
    "depende"
}

FRASES_FRACAS = {
    "como ia", "sou uma ia", "não tenho certeza", "não posso", "não sei",
    "não tenho informação", "a resposta é", "resposta:", "pergunta:",
    "espero ter ajudado", "qualquer dúvida", "estou aqui para ajudar",
    "fique à vontade", "precisa de mais alguma coisa"
}

PADROES_INVALIDOS = [
    r'<[^>]+>',                     # HTML
    r'```[\s\S]*?```',              # Markdown code blocks
    r'`[^`]+`',                     # Inline code
    r'\{.*\}',                      # JSON/objetos
    r'<\\?[a-zA-Z]+[^>]*>',         # XML-like
    r'[#*_]{3,}',                   # Markdown headers/emphasis
    r'\[.*\]\(.*\)',                # Markdown links
    r'[\u2600-\u27BF]',             # Emojis (aproximado)
    r'https?://\S+',                # URLs
]

PALAVRAS_REPETIDAS_LIMITE = 0.4  # Proporção máxima de repetição de palavras


# ----------------------------------------------------------------------------
# Detectores auxiliares
# ----------------------------------------------------------------------------
def detectar_truncamento(texto: str, finish_reason: Optional[str] = None) -> bool:
    """Detecta se um texto foi truncado (terminação abrupta ou motivo de finalização)."""
    if finish_reason in {"length", "max_tokens"}:
        return True
    texto = texto.strip()
    if not texto or texto.endswith("...") or len(texto) < 5:
        return True
    return False


def detectar_html_markdown(texto: str) -> bool:
    """Verifica se o texto contém HTML, Markdown, JSON ou outros formatos inválidos."""
    for padrao in PADROES_INVALIDOS:
        if re.search(padrao, texto, re.IGNORECASE | re.DOTALL):
            return True
    return False


def detectar_lista_excessiva(texto: str) -> bool:
    """Verifica se o texto tem uma quantidade excessiva de listas (marcadores)."""
    linhas = texto.split('\n')
    count_lista = 0
    for linha in linhas:
        if re.match(r'^[\s]*[-*•]\s+', linha.strip()) or re.match(r'^[\s]*\d+[\.\)]\s+', linha.strip()):
            count_lista += 1
    linhas_validas = [l for l in linhas if l.strip()]
    if not linhas_validas:
        return False
    return (count_lista / len(linhas_validas)) > 0.5


def detectar_repeticao_excessiva(texto: str) -> bool:
    """Verifica se uma palavra se repete excessivamente no texto."""
    palavras = texto.split()
    if len(palavras) < 10:
        return False
    freq = Counter(palavras)
    max_freq = max(freq.values())
    return (max_freq / len(palavras)) > PALAVRAS_REPETIDAS_LIMITE


def detectar_resposta_genérica(texto: str) -> bool:
    """Detecta respostas genéricas como 'depende' ou 'não tenho informações'."""
    texto_lower = texto.lower()
    genericos = [
        "depende de vários fatores", "cada caso é um caso", "é importante considerar",
        "não existe resposta certa", "tudo depende", "é relativo",
        "não tenho informações suficientes", "não posso afirmar com certeza"
    ]
    for g in genericos:
        if g in texto_lower:
            return True
    return False


def detectar_muleta_ia(texto: str) -> bool:
    """Detecta frases típicas de assistentes de IA que devem ser evitadas."""
    muletas = [
        "como assistente", "sou uma inteligência artificial", "como modelo de linguagem",
        "não tenho opinião própria", "não tenho sentimentos", "não posso sentir",
        "sou um programa", "não tenho consciência", "não sou humano",
        "não possuo emoções", "não tenho crenças"
    ]
    texto_lower = texto.lower()
    for m in muletas:
        if m in texto_lower:
            return True
    return False


# ----------------------------------------------------------------------------
# Validação principal de qualidade
# ----------------------------------------------------------------------------
def avaliar_qualidade(
    texto: str,
    tipo: str = "dicionario",
    finish_reason: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Avalia a qualidade geral de um texto gerado.

    Args:
        texto: O texto a ser avaliado.
        tipo: Tipo de texto ('dicionario', 'pergunta_resposta', 'artigo', etc.).
        finish_reason: Motivo de finalização da API (pode indicar truncamento).

    Returns:
        Tuple (bool, str): (True se aprovado, motivo da rejeição se False).
    """
    if texto is None:
        return False, "texto é None"

    texto = limpar_texto(texto)
    if not texto:
        return False, "texto vazio"

    texto_norm = normalizar_chave(texto)
    palavras = texto_norm.split()

    # 1. Verificar truncamento
    if detectar_truncamento(texto, finish_reason):
        return False, "resposta truncada"

    # 2. Verificar se é uma resposta vaga (apenas "sim", "não", etc.)
    if texto_norm in VAGAS:
        return False, f"resposta vaga: '{texto[:60]}'"

    # 3. Verificar frases fracas/muletas
    for trecho in FRASES_FRACAS:
        if trecho in texto_norm:
            return False, f"resposta fraca: '{texto[:60]}'"

    # 4. Verificar caracteres estranhos
    if "��" in texto:
        return False, "caracteres estranhos (encoding)"

    # 5. Verificar HTML/Markdown/JSON/código
    if detectar_html_markdown(texto):
        return False, "contém HTML/Markdown/JSON/XML/código"

    # 6. Verificar listas excessivas
    if detectar_lista_excessiva(texto):
        return False, "lista excessiva (muitos marcadores)"

    # 7. Verificar repetição excessiva de palavras
    if detectar_repeticao_excessiva(texto):
        return False, "repetição excessiva de palavras"

    # 8. Verificar resposta genérica ("depende", etc.)
    if detectar_resposta_genérica(texto):
        return False, "resposta genérica (ex: 'depende')"

    # 9. Verificar muletas de IA
    if detectar_muleta_ia(texto):
        return False, "contém frases típicas de IA (ex: 'como assistente')"

    # 10. Verificar comprimento conforme o tipo
    if tipo in ["dicionario", "saudacao"]:
        if len(palavras) < 3:
            return False, f"muito curta: {len(palavras)} palavras"
        if len(palavras) > 80:
            return False, f"muito longa: {len(palavras)} palavras"
    elif tipo in ["pergunta_resposta", "iteracao", "artigo", "conto",
                  "dialogo_profundo", "explicacao", "resumo"]:
        if len(palavras) < 50:
            return False, f"texto muito curto: {len(palavras)} palavras"
        if len(palavras) > 1000:
            return False, f"texto muito longo: {len(palavras)} palavras"
    elif tipo == "conversa":
        if len(palavras) < 40:
            return False, f"conversa curta: {len(palavras)} palavras"

    return True, "OK"


# ----------------------------------------------------------------------------
# Validação específica para diálogos
# ----------------------------------------------------------------------------
def validar_dialogo(texto: str, tipo: str = "dialogo_profundo") -> Tuple[bool, str]:
    """
    Valida se um diálogo está no formato correto (Pessoa:/Outra:)
    e tem qualidade mínima (número de turnos, tamanho das falas).

    Args:
        texto: O texto do diálogo a ser validado.
        tipo: Tipo de diálogo ('iteracao', 'dialogo_profundo', 'conversa').

    Returns:
        Tuple (bool, str): (True se aprovado, motivo da rejeição se False).
    """
    if not texto:
        return False, "texto vazio"

    # Remove formatação (negrito, itálico) para facilitar a análise
    texto_limpo = re.sub(r'\*\*', '', texto)
    texto_limpo = re.sub(r'__', '', texto_limpo)

    # Verifica presença dos marcadores obrigatórios
    if "Pessoa:" not in texto_limpo or "Outra:" not in texto_limpo:
        return False, "faltam marcadores 'Pessoa:' ou 'Outra:'"

    # Conta turnos (alternâncias entre Pessoa e Outra)
    turnos = re.findall(r'(?:Pessoa|Outra)\s*:', texto_limpo, re.IGNORECASE)

    # Define o número mínimo de turnos conforme o tipo
    if tipo == "dialogo_profundo":
        min_turnos = 8
    elif tipo == "iteracao":
        min_turnos = 4
    else:  # conversa
        min_turnos = 4

    if len(turnos) < min_turnos:
        return False, f"poucos turnos ({len(turnos)}/{min_turnos})"

    # Verifica se cada fala tem pelo menos 5 palavras (mínimo)
    falas = re.split(r'(?:Pessoa|Outra)\s*:', texto_limpo)[1:]
    palavras_por_fala = [len(f.split()) for f in falas if f.strip()]

    if not palavras_por_fala or min(palavras_por_fala) < 5:
        return False, "fala muito curta (menos de 5 palavras)"

    # Verifica tamanho total mínimo do diálogo
    if len(texto_limpo.split()) < 80:
        return False, "texto muito curto (menos de 80 palavras)"

    return True, "OK"


def padronizar_formato(texto: str) -> str:
    """
    Padroniza o formato de um diálogo, removendo marcações extras
    e garantindo o uso consistente de 'Pessoa:' e 'Outra:'.
    """
    if not texto:
        return texto

    # Remove negrito/itálico
    texto = re.sub(r'\*\*', '', texto)
    texto = re.sub(r'__', '', texto)

    # Substitui variações para o padrão
    texto = re.sub(r'\*\s*Pessoa\s*\*?\s*:', 'Pessoa:', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\*\s*Outra\s*\*?\s*:', 'Outra:', texto, flags=re.IGNORECASE)

    # Remove espaços extras
    texto = re.sub(r'\s+', ' ', texto).strip()

    # Reorganiza linhas (garante que cada linha comece com Pessoa: ou Outra:)
    linhas = texto.split('\n')
    linhas_corrigidas = []
    for linha in linhas:
        linha = linha.strip()
        if linha and not linha.startswith(('Pessoa:', 'Outra:')):
            # Se a linha não começar com o marcador, mantém como continuação da fala anterior
            pass
        linhas_corrigidas.append(linha)

    return '\n'.join(linhas_corrigidas)


# ============================================================================
# FUNÇÕES PARA VALIDAÇÃO/LIMPEZA DE ARQUIVOS EXISTENTES
# (extraídas da versão original 2.0)
# ============================================================================
def listar_arquivos_invalidos(pasta: str) -> List[Tuple[str, str]]:
    """
    Lista arquivos inválidos em uma pasta, retornando (caminho, motivo).
    Verifica:
      - Respostas muito curtas (para dicionário)
      - Texto muito curto (para outros tipos)
    """
    invalidos = []
    if not os.path.exists(pasta):
        return invalidos

    for raiz, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            if not nome.endswith(".txt"):
                continue
            caminho = os.path.join(raiz, nome)
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    texto = f.read()
            except Exception:
                continue

            # Verifica formato Pergunta/Resposta
            if "Pergunta:" in texto and "Resposta:" in texto:
                partes = texto.split("Resposta:", 1)
                if len(partes) > 1 and len(partes[1].strip()) < 5:
                    invalidos.append((caminho, "resposta muito curta"))
            # Diálogos (Pessoa/Outra) são aceitos
            elif "Pessoa:" in texto and "Outra:" in texto:
                pass
            else:
                # Outros textos: verifica comprimento mínimo
                if len(texto.strip()) < 100:
                    invalidos.append((caminho, "texto muito curto (menos de 100 caracteres)"))

    return invalidos


def limpar_arquivos_invalidos(pasta: str, dry_run: bool = False) -> None:
    """
    Lista e opcionalmente remove arquivos inválidos.
    Se dry_run=True, apenas lista sem remover.
    """
    invalidos = listar_arquivos_invalidos(pasta)
    if not invalidos:
        print(f"✅ Nenhum arquivo inválido encontrado em {pasta}.")
        return

    print(f"\n📋 {len(invalidos)} arquivos inválidos encontrados em {pasta}:")
    for caminho, motivo in invalidos[:10]:
        print(f"   ⚠️ {os.path.basename(caminho)} – {motivo}")
    if len(invalidos) > 10:
        print(f"   ... e mais {len(invalidos)-10} arquivos.")

    if dry_run:
        print("\n🔍 Modo de validação (dry-run): nenhum arquivo foi removido.")
        return

    resposta = input("\n🗑️  Deseja remover todos esses arquivos? (s/N): ").strip().lower()
    if resposta == 's':
        removidos = 0
        for caminho, _ in invalidos:
            try:
                os.remove(caminho)
                removidos += 1
            except Exception:
                pass
        print(f"✅ {removidos} arquivos removidos.")
    else:
        print("✅ Nenhum arquivo removido.")


# ----------------------------------------------------------------------------
# Exportar símbolos principais
# ----------------------------------------------------------------------------
__all__ = [
    "avaliar_qualidade",
    "validar_dialogo",
    "padronizar_formato",
    "listar_arquivos_invalidos",
    "limpar_arquivos_invalidos",
    "detectar_truncamento",
    "detectar_html_markdown",
    "detectar_lista_excessiva",
    "detectar_repeticao_excessiva",
    "detectar_resposta_genérica",
    "detectar_muleta_ia"
]