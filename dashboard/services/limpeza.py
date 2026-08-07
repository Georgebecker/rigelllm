#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
limpeza.py - Utilitários de limpeza de texto para o RigelSLM Dashboard
Remove emojis e caracteres especiais que prejudicam treinamento de IA.
"""
import re


# Regex para capturar a maioria dos emojis Unicode (incluindo combinações)
# Cobre: emoticons, símbolos, bandeiras, skin tones, etc.
RE_EMOJI = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Símbolos & pictograms
    "\U0001F680-\U0001F6FF"  # Transporte & mapas
    "\U0001F1E0-\U0001F1FF"  # Bandeiras (pares)
    "\U0001F900-\U0001F9FF"  # Símbolos suplementares
    "\U0001FA00-\U0001FA6F"  # Símbolos estendidos A
    "\U0001FA70-\U0001FAFF"  # Símbolos estendidos B
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"  # Vários símbolos
    "\U0001F200-\U0001F2FF"  # Ideográficos
    "\U00002600-\U000026FF"  # Misc symbols
    "\U00002934-\U0000293B"  # Setas
    "\U00002B05-\U00002B07"  # Setas
    "\U00003030-\U00003030"  # Símbolos CJK
    "\U0000303D-\U0000303D"  # Símbolos CJK
    "\U0000FE00-\U0000FE0F"  # Variation selectors
    "\U0000200D"             # Zero-width joiner
    "\U0000203C-\U0000203C"  # Double exclamation
    "\U00002049-\U00002049"  # Exclamation question
    "\U000020E3"             # Combining enclosing keycap
    "\U00002B55-\U00002B55"  # Heavy circle
    "\U00002300-\U000023FF"  # Miscellaneous technical
    "\U00002500-\U000025FF"  # Box drawing
    "\U000025A0-\U000025FF"  # Geometric shapes
    "]+", flags=re.UNICODE
)


def limpar_emojis(texto: str) -> str:
    """
    Remove todos os emojis do texto.
    Também remove marcadores como '🔍', '🎙️', '⚠️', '✅', '❌' etc.
    que são usados internamente mas não devem ir para o conteúdo gerado.
    """
    if not texto:
        return texto
    # ⚠️ Primeiro converte o marcador de espaço byte-level (▁ U+2581) em espaço
    # NORMAL. Tokenizers BPE/ByteLevel usam ▁ para representar espaço; como a
    # regex de emojis cobre a faixa U+2500-U+25FF (que inclui o ▁), remover o ▁
    # junto com os emojis JUNTA todas as palavras ("Olá▁boa" → "Oláboa").
    texto = texto.replace("\u2581", " ")
    # Remove emojis
    texto = RE_EMOJI.sub('', texto)
    # Remove múltiplos espaços em branco deixados pela remoção
    texto = re.sub(r'  +', ' ', texto)
    # Remove espaços no início de linhas após remoção de emoji
    texto = re.sub(r'\n +', '\n', texto)
    # Remove linhas que ficaram vazias (só espaços)
    texto = re.sub(r'^\s*$', '', texto, flags=re.MULTILINE)
    return texto.strip()


def limpar_e_aviso(texto: str, origem: str = "") -> str:
    """
    Remove emojis e loga quantos foram removidos.
    """
    if not texto:
        return texto
    antes = len(texto)
    resultado = limpar_emojis(texto)
    removidos = antes - len(resultado)
    if removidos > 0 and origem:
        print(f"[LIMP] {origem}: {removidos} chars de emojis removidos")
    return resultado


# =============================================================================
# CORREÇÃO DE ESPAÇOS CONCATENADOS (tokenizer ByteLevel)
# =============================================================================

# Regex: letra/ponto final/número seguido diretamente por letra maiúscula sem espaço
# Ex: "Olá!Eusou" → "Olá! Eusou", "hoje?Sim" → "hoje? Sim"
RE_CONCAT_PONTO_FINAL = re.compile(r'([.!?]+)([A-ZÁÉÍÓÚÂÊÔÀÃÕÇ])')

# Regex: palavra minúscula seguida diretamente por palavra maiúscula sem espaço
# Ex: "mundoÉ" → "mundo É" (mas isso é raro em português)
RE_CONCAT_MAIUSCULA = re.compile(r'([a-záéíóúâêôàãõç])([A-ZÁÉÍÓÚÂÊÔÀÃÕÇ])')

# Regex: dígito seguido de letra (ex: "1b" → "1 b" é ambíguo, melhor não mexer)
# Regex: fechamento de tag/html seguido de texto
RE_CONCAT_ESPECIAL = re.compile(r'([>\]}\)])([A-Za-zÁÉÍÓÚÂÊÔÀÃÕÇáéíóúâêôàãõç])')

# Regex para limpar sequências ANSI (códigos de escape de terminal)
# Ex: \x1b[13D\x1b[K que o ollama run emite durante streaming
RE_ANSI = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][0-9;]*[a-zA-Z].*?(\x1b\\|$)|\x1b[\[\]()][0-9;]*')


def limpar_ansi(texto: str) -> str:
    """
    Remove códigos de escape ANSI (sequências de terminal) do texto.
    Útil para limpar saídas de 'ollama run' que emitem códigos de cursor.
    """
    if not texto:
        return texto
    texto = RE_ANSI.sub('', texto)
    # Remove carriage returns e outros caracteres de controle (exceto \n, \t, \r)
    texto = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', texto)
    # Remove espaços múltiplos
    texto = re.sub(r'  +', ' ', texto)
    return texto.strip()


def corrigir_espacos_concatenados(texto: str) -> str:
    """
    Corrige palavras que foram geradas sem espaços entre elas,
    problema comum em tokenizers BPE ByteLevel mal configurados no GGUF/Ollama.
    
    Ex: "Olá!EusouoRigelSLM.Comopossoteajudar?" 
         → "Olá! Eu sou o RigelSLM. Como posso te ajudar?"
    
    NOTA: Esta função é uma heurística de segurança. O ideal é corrigir
    a configuração do tokenizer na fonte (GGUF export).
    """
    if not texto:
        return texto

    original = texto

    # 1. Espaço após pontuação final (. ! ?) quando seguida de letra maiúscula
    texto = RE_CONCAT_PONTO_FINAL.sub(r'\1 \2', texto)
    
    # 2. Espaço após fechamento de parênteses/colchetes/aspas
    texto = RE_CONCAT_ESPECIAL.sub(r'\1 \2', texto)
    
    # 3. Palavra minúscula seguida de maiúscula (ex: "mundoÉ" → "mundo É")
    # Cuidado: isso pode separar palavras compostas, mas é raro
    texto = RE_CONCAT_MAIUSCULA.sub(r'\1 \2', texto)
    
    # 4. Corrige espaços duplicados
    texto = re.sub(r'  +', ' ', texto)
    
    # 5. Corrige espaços antes de pontuação
    texto = re.sub(r' ([.!?,:;])', r'\1', texto)
    
    # 6. Remove espaços no início/fim
    texto = texto.strip()
    
    if texto != original:
        print(f"[LIMP] Espaços concatenados corrigidos: {len(original)}→{len(texto)} chars")
    
    return texto
