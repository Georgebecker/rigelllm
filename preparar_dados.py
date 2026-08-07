#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
preparar_dados.py - PREPARAÇÃO DE DADOS PARA TREINO DO RIGELSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
================================================================

ESTRUTURA DE PASTAS:
  dados/gerados/<fonte>/   - dados brutos baixados/extraídos (cada fonte em sua pasta)
  dados/processed/         - dados prontos para treino (após qualificação)

FLUXO RECOMENDADO:
  1. Baixar dados: python preparar_dados.py
  2. Qualificar (validar, limpar, reconstruir): python preparar_dados.py --qualificar
  3. Treinar: python treino.py

COMANDOS:
  --qualificar            Aplica validação, limpeza e reconstrução, e copia para processed
  --fonte <nome>          Especifica uma fonte (ex: tucano, ultrachat, blogset, etc.)
  --reconstruir-palavras  Reconstroi palavras separadas por espaços entre letras
  --limpar-processados    Aplica limpeza profunda (normalização Unicode) em processed
  --validar               Lista arquivos inválidos (estruturalmente)
  --limpar-invalidos      Remove arquivos inválidos
  --skip-download         Pula download, processa apenas arquivos locais
  --corrigir-espacos      (EXPERIMENTAL) tenta separar palavras grudadas
  --ver-logs              Exibe histórico de execuções
"""

import os
import sys
import re
import gzip
import csv
import time
import subprocess
import importlib
import json
import argparse
import unicodedata
import shutil
from datetime import datetime
from urllib.parse import urljoin

from tqdm import tqdm
from datasets import load_dataset, config
from langdetect import detect, DetectorFactory
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
import requests

# ============================================================================
# 0. AUMENTA O TIMEOUT DO DATASETS E O LIMITE DE CAMPO DO CSV
# ============================================================================

config.HTTP_TIMEOUT = 120.0  # Aumenta timeout para 120 segundos
csv.field_size_limit(sys.maxsize)

# ============================================================================
# 1. CONFIGURAÇÃO DE PASTAS
# ============================================================================

PASTA_BASE = "dados"
PASTA_GERADOS = os.path.join(PASTA_BASE, "gerados")
PASTA_PROCESSED = os.path.join(PASTA_BASE, "processed")
PASTA_RAW = os.path.join(PASTA_BASE, "raw")
PASTA_LOGS = "logs"
PASTA_MODELO = "modelo"
PASTA_TOKENIZER = "tokenizer"

# Subpastas para cada fonte (dentro de dados/gerados/)
FONTES = {
    "blogset": "blogset",
    "ultrachat": "ultrachat",
    "tucano": "tucano",
    "guara": "guara",
    "wiki": "wiki",
    "locais": "locais",
    "datasets": "datasets",
}
# Cria todas as pastas
for pasta in [PASTA_BASE, PASTA_RAW, PASTA_PROCESSED, PASTA_LOGS, PASTA_MODELO, PASTA_TOKENIZER]:
    os.makedirs(pasta, exist_ok=True)

for fonte in FONTES.values():
    os.makedirs(os.path.join(PASTA_GERADOS, fonte), exist_ok=True)

# Arquivos de log
LOG_FILE = os.path.join(PASTA_LOGS, "preparar_dados.log")
HISTORICO_FILE = os.path.join(PASTA_LOGS, "preparar_dados_historico.json")
BLACKLIST_PATH = "blacklist.txt"

# ============================================================================
# 2. FUNÇÕES DE LOG E HISTÓRICO
# ============================================================================

def log(msg, end='\n'):
    print(msg, end=end)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(msg + end)

def registrar_historico(execucao):
    historico = []
    if os.path.exists(HISTORICO_FILE):
        with open(HISTORICO_FILE, 'r', encoding='utf-8') as f:
            try:
                historico = json.load(f)
            except:
                historico = []
    historico.append(execucao)
    with open(HISTORICO_FILE, 'w', encoding='utf-8') as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)

    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write(f"📅 {execucao['data_hora']}\n")
        f.write(f"   Acao: {execucao['acao']}\n")
        f.write(f"   Arquivos_validos: {execucao.get('validos', 0)}\n")
        f.write(f"   Arquivos_invalidos: {execucao.get('invalidos', 0)}\n")
        f.write(f"   Arquivos_removidos: {execucao.get('removidos', 0)}\n")
        f.write(f"   Arquivos_limpos: {execucao.get('limpos', 0)}\n")
        f.write(f"   Arquivos_reconstruidos: {execucao.get('reconstruidos', 0)}\n")
        f.write(f"   Arquivos_movidos: {execucao.get('movidos', 0)}\n")
        f.write(f"   Tempo: {execucao.get('tempo_segundos', 0):.2f}s\n")
        f.write("=" * 70 + "\n\n")

def ver_logs():
    if not os.path.exists(HISTORICO_FILE):
        print("📭 Nenhum histórico encontrado.")
        return
    with open(HISTORICO_FILE, 'r', encoding='utf-8') as f:
        historico = json.load(f)
    print(f"\n📋 Histórico de execuções ({len(historico)} registros):\n")
    for i, entry in enumerate(historico, 1):
        print(f"[{i}] {entry['data_hora']} | {entry['acao']} | Válidos: {entry.get('validos', 0)} | Inválidos: {entry.get('invalidos', 0)} | Movidos: {entry.get('movidos', 0)}")
    print(f"\n📄 Log completo em: {LOG_FILE}")
    print(f"📄 Histórico JSON em: {HISTORICO_FILE}")

# ============================================================================
# 3. DEPENDÊNCIAS OPCIONAIS (OCR)
# ============================================================================

try:
    import pdfplumber
    PDFPLUMBER_DISPONIVEL = True
except ImportError:
    PDFPLUMBER_DISPONIVEL = False
    log("ℹ️ pdfplumber não instalado (opcional). pip install pdfplumber")

OCR_DISPONIVEL = False
try:
    import pytesseract
    from PIL import Image
    OCR_DISPONIVEL = True
    if os.name == 'nt':
        possiveis_caminhos = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        encontrado = False
        for caminho in possiveis_caminhos:
            if os.path.exists(caminho):
                pytesseract.pytesseract.tesseract_cmd = caminho
                log(f"✅ Tesseract encontrado em: {caminho}")
                encontrado = True
                break
        if not encontrado:
            log("⚠️ Tesseract não encontrado. Instale de: https://github.com/UB-Mannheim/tesseract/wiki")
    else:
        log("✅ Tesseract disponível (assumindo PATH)")
        OCR_DISPONIVEL = True
except ImportError:
    OCR_DISPONIVEL = False
    log("ℹ️ pytesseract/pillow não instalados. pip install pytesseract pillow")

# ============================================================================
# 4. VERIFICAÇÃO DE DEPENDÊNCIAS
# ============================================================================

def check_and_install(packages):
    missing = []
    for import_name, pypi_name in packages.items():
        try:
            importlib.import_module(import_name)
            log(f"✅ {import_name} já instalado.")
        except ImportError:
            missing.append((import_name, pypi_name))
            log(f"❌ {import_name} não encontrado (pacote: {pypi_name}).")
    if not missing:
        return True
    log("\n⚠️ Pacotes faltando:")
    for import_name, pypi_name in missing:
        log(f"   - {import_name} (pacote: {pypi_name})")
    resposta = input("\nDeseja instalar todos os pacotes faltantes? (S/N): ").strip().lower()
    if resposta != 's':
        log("❌ Instalação cancelada.")
        return False
    for import_name, pypi_name in missing:
        log(f"📦 Instalando {pypi_name}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", pypi_name])
            log(f"✅ {pypi_name} instalado.")
        except subprocess.CalledProcessError as e:
            log(f"❌ Erro ao instalar {pypi_name}: {e}")
            return False
    return True

DEPENDENCIAS = {
    'datasets': 'datasets',
    'langdetect': 'langdetect',
    'tqdm': 'tqdm',
    'bs4': 'beautifulsoup4',
    'fitz': 'pymupdf',
    'lxml': 'lxml',
    'requests': 'requests',
}
if not check_and_install(DEPENDENCIAS):
    sys.exit(1)

# ============================================================================
# 5. BLACKLIST
# ============================================================================

BLACKLIST_PADRAO = """# ============================================================
# BLACKLIST - APENAS PALAVRAS REALMENTE OFENSIVAS
# ============================================================
puta
buceta
caralho
cu
porra
foda
tesão
peitinho
bunda
rabuda
gostosa
novinha
safada
pau
rola
piroca
cacete
boquete
tarado
punheta
macaco
crioulo
nego
negada
judeu
veado
bicha
sapatão
traveco
"""

def carregar_blacklist():
    if not os.path.exists(BLACKLIST_PATH):
        log(f"📝 Criando blacklist padrão em {BLACKLIST_PATH}")
        with open(BLACKLIST_PATH, 'w', encoding='utf-8') as f:
            f.write(BLACKLIST_PADRAO)
    with open(BLACKLIST_PATH, 'r', encoding='utf-8') as f:
        palavras = set()
        for linha in f:
            linha = linha.strip().lower()
            if linha and not linha.startswith('#'):
                palavras.add(linha)
    return palavras

PALAVRAS_PROIBIDAS = carregar_blacklist()
log(f"📋 Blacklist carregada: {len(PALAVRAS_PROIBIDAS)} palavras.")

# ============================================================================
# 6. FUNÇÕES DE PROCESSAMENTO DE TEXTO (ATUALIZADAS)
# ============================================================================

DetectorFactory.seed = 0

def normalizar_texto(texto):
    """Normalização Unicode NFKC e remoção de caracteres de controle."""
    texto = unicodedata.normalize('NFKC', texto)
    texto = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', texto)
    texto = re.sub(r'[ \t]+', ' ', texto)
    return texto.strip()

def limpar_texto(texto):
    """Remove URLs, emails, números de telefone e normaliza."""
    texto = re.sub(r'https?://\S+|www\.\S+', '', texto)
    texto = re.sub(r'\S+@\S+\.\S+', '', texto)
    texto = re.sub(r'\(\d{2}\)\s?\d{4,5}-\d{4}', '', texto)
    texto = normalizar_texto(texto)
    return texto

def extrair_pergunta_resposta(texto):
    """
    Tenta extrair um par pergunta/resposta de vários formatos comuns.
    Retorna (pergunta, resposta) ou (None, None).
    """
    # Remove quebras de linha excessivas
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    linhas = texto.split('\n')
    # Procura padrões: Pergunta: / Resposta:
    pergunta = None
    resposta = None
    # Primeiro tenta "Pergunta:" e "Resposta:"
    match_perg = re.search(r'(?:Pergunta|Perg)\s*[:]\s*(.+?)(?=\s*(?:Resposta|Resp)\s*[:]|$)', texto, re.IGNORECASE | re.DOTALL)
    match_resp = re.search(r'(?:Resposta|Resp)\s*[:]\s*(.+)', texto, re.IGNORECASE | re.DOTALL)
    if match_perg and match_resp:
        pergunta = limpar_texto(match_perg.group(1).strip())
        resposta = limpar_texto(match_resp.group(1).strip())
        if pergunta and resposta:
            return pergunta, resposta

    # Tenta "Usuário:" e "Assistente:"
    match_user = re.search(r'Usu[áa]rio\s*[:]\s*(.+?)(?=\s*Assistente\s*[:]|$)', texto, re.IGNORECASE | re.DOTALL)
    match_assist = re.search(r'Assistente\s*[:]\s*(.+)', texto, re.IGNORECASE | re.DOTALL)
    if match_user and match_assist:
        pergunta = limpar_texto(match_user.group(1).strip())
        resposta = limpar_texto(match_assist.group(1).strip())
        if pergunta and resposta:
            return pergunta, resposta

    # Tenta "Pessoa:" e "Outra:"
    match_pessoa = re.search(r'Pessoa\s*[:]\s*(.+?)(?=\s*Outra\s*[:]|$)', texto, re.IGNORECASE | re.DOTALL)
    match_outra = re.search(r'Outra\s*[:]\s*(.+)', texto, re.IGNORECASE | re.DOTALL)
    if match_pessoa and match_outra:
        pergunta = limpar_texto(match_pessoa.group(1).strip())
        resposta = limpar_texto(match_outra.group(1).strip())
        if pergunta and resposta:
            return pergunta, resposta

    # Se houver múltiplos turnos, pega o primeiro e o segundo como pergunta/resposta
    turnos = re.findall(r'(?:Pessoa|Usu[áa]rio|Assistente|Outra)\s*[:]\s*(.+?)(?=(?:Pessoa|Usu[áa]rio|Assistente|Outra)\s*[:]|$)', texto, re.IGNORECASE | re.DOTALL)
    if len(turnos) >= 2:
        pergunta = limpar_texto(turnos[0].strip())
        resposta = limpar_texto(turnos[1].strip())
        if pergunta and resposta:
            return pergunta, resposta

    # Fallback: se houver "?" no texto, tenta dividir na primeira interrogação
    if '?' in texto:
        partes = texto.split('?', 1)
        if len(partes) == 2 and len(partes[0]) > 5 and len(partes[1]) > 5:
            pergunta = limpar_texto(partes[0] + '?')
            resposta = limpar_texto(partes[1])
            if pergunta and resposta:
                return pergunta, resposta

    return None, None

def filtrar_idioma(texto, idioma_esperado='pt'):
    try:
        amostra = texto[:500]
        if len(amostra) < 20:
            return False, "texto muito curto"
        idioma = detect(amostra)
        if idioma == idioma_esperado:
            return True, f"idioma: {idioma}"
        else:
            return False, f"idioma: {idioma} (esperado pt)"
    except:
        return True, "detecção falhou, assumindo pt"

def filtrar_conteudo_ofensivo(texto, limite=200):
    if not PALAVRAS_PROIBIDAS:
        return True, "sem blacklist"
    texto_lower = texto.lower()
    palavras_encontradas = set()
    for palavra in PALAVRAS_PROIBIDAS:
        if palavra in texto_lower:
            palavras_encontradas.add(palavra)
    total = len(palavras_encontradas)
    if total >= limite:
        return False, f"{total} palavras ofensivas únicas (limite {limite})"
    return True, f"{total} palavras ofensivas únicas"

def avaliar_qualidade_texto(texto):
    palavras = texto.split()
    if len(palavras) < 30:
        return False, f"texto curto: {len(palavras)} palavras (mínimo 30)"
    proporcao = len(set(palavras)) / len(palavras)
    if proporcao < 0.08:
        return False, f"baixa diversidade: {proporcao:.2f} (mínimo 0.08)"
    return True, f"{len(palavras)} palavras, diversidade {proporcao:.2f}"

def avaliar_qualidade_dialogo(pergunta, resposta):
    """Avalia a qualidade de um par pergunta/resposta."""
    palavras_p = pergunta.split()
    palavras_r = resposta.split()
    if len(palavras_p) < 4 or len(palavras_r) < 10:
        return False, f"pergunta ou resposta muito curta (P:{len(palavras_p)}, R:{len(palavras_r)})"
    texto_completo = pergunta + " " + resposta
    palavras = texto_completo.split()
    proporcao = len(set(palavras)) / len(palavras)
    if proporcao < 0.06:
        return False, f"baixa diversidade: {proporcao:.2f} (mínimo 0.06)"
    return True, f"P:{len(palavras_p)} palavras, R:{len(palavras_r)}, diversidade {proporcao:.2f}"

def validar_arquivo_pergunta_resposta(texto):
    """Valida se o texto está no formato Pergunta/Resposta."""
    if "Pergunta:" not in texto or "Resposta:" not in texto:
        return True, "texto corrido"
    partes = texto.split("Resposta:", 1)
    if len(partes) < 2:
        return False, "formato inválido: falta resposta"
    resposta = partes[1].strip()
    if len(resposta) < 8:
        return False, f"resposta muito curta: '{resposta}'"
    if resposta.endswith("...") or "��" in resposta:
        return False, "resposta cortada ou com caracteres estranhos"
    return True, "formato P/R válido"

def processar_texto(texto_bruto, tipo="texto", corrigir_espacos=False, aplicar_reconstrucao=False):
    """
    Processa texto bruto:
      - tipo="texto": retorna texto limpo (string).
      - tipo="dialogo": tenta extrair pergunta/resposta, retorna string formatada.
    Retorna (texto_processado, motivos) onde texto_processado é string.
    """
    motivos = []
    texto = limpar_texto(texto_bruto)
    if not texto:
        return None, ["texto vazio"]

    if aplicar_reconstrucao:
        texto = reconstruir_palavras(texto)
        motivos.append("reconstrução aplicada")
    if corrigir_espacos:
        texto = inserir_espacos(texto)
        motivos.append("correção de espaços aplicada")

    ok, msg = filtrar_idioma(texto)
    if not ok:
        return None, [msg]
    motivos.append(msg)

    ok, msg = filtrar_conteudo_ofensivo(texto, limite=200)
    if not ok:
        return None, [msg]
    motivos.append(msg)

    if tipo == "dialogo":
        pergunta, resposta = extrair_pergunta_resposta(texto)
        if not pergunta or not resposta:
            # Fallback: tenta criar um diálogo artificial
            if '?' in texto:
                partes = texto.split('?', 1)
                if len(partes) == 2 and len(partes[0]) > 5 and len(partes[1]) > 5:
                    pergunta = limpar_texto(partes[0] + '?')
                    resposta = limpar_texto(partes[1])
                else:
                    pergunta = "O que você pode me dizer sobre o assunto?"
                    resposta = texto
            else:
                pergunta = "Fale sobre o seguinte:"
                resposta = texto
        ok, msg = avaliar_qualidade_dialogo(pergunta, resposta)
        if not ok:
            return None, [msg]
        motivos.append(msg)
        # Retorna string formatada
        return f"Pergunta: {pergunta}\nResposta: {resposta}", motivos
    else:
        ok, msg = avaliar_qualidade_texto(texto)
        if not ok:
            return None, [msg]
        motivos.append(msg)
        ok, msg = validar_arquivo_pergunta_resposta(texto)
        if not ok:
            return None, [msg]
        motivos.append(msg)
        return texto, motivos

def reconstruir_palavras(texto):
    """Reconstrói palavras separadas por espaços entre letras."""
    if not texto:
        return texto
    if not hasattr(reconstruir_palavras, "palavras_cache"):
        cache = set()
        for marcador in ["pergunta", "resposta", "pessoa", "outra", "usuario", "assistente"]:
            cache.add(marcador)
        # Adiciona palavras comuns (pequena lista para não depender de categorias)
        palavras_comuns = [
            "amor", "vida", "mundo", "pessoa", "tempo", "casa", "trabalho", "familia",
            "cidade", "país", "brasil", "rio", "mar", "sol", "lua", "estrela", "céu",
            "terra", "água", "fogo", "vento", "árvore", "flor", "animal", "pássaro",
            "peixe", "cachorro", "gato", "cavalo", "mulher", "homem", "criança",
            "amigo", "amiga", "professor", "médico", "engenheiro", "advogado",
            "programador", "cientista", "artista", "músico", "escritor", "poeta",
            "livro", "filme", "música", "pintura", "dança", "teatro", "cinema",
            "escola", "universidade", "biblioteca", "museu", "parque", "jardim",
            "história", "geografia", "ciência", "filosofia", "matemática", "física",
            "química", "biologia", "astronomia", "tecnologia", "internet", "computador",
            "telefone", "carro", "avião", "navio", "trem", "ônibus", "bicicleta",
            "política", "economia", "sociedade", "cultura", "religião", "arte",
            "esporte", "futebol", "basquete", "vôlei", "natação", "corrida",
            "saúde", "alimentação", "exercício", "meditação", "estresse", "felicidade",
            "tristeza", "amizade", "amor", "paixão", "ódio", "medo", "coragem",
            "esperança", "fé", "sonho", "meta", "desafio", "vitória", "derrota",
            "aprendizado", "conhecimento", "sabedoria", "experiência", "memória",
            "pensamento", "sentimento", "emoção", "sensação", "percepção",
            "natureza", "planeta", "clima", "poluição", "sustentabilidade",
            "energia", "fonte", "recurso", "futuro", "passado", "presente"
        ]
        for p in palavras_comuns:
            cache.add(p.lower())
        # Adiciona palavras compostas comuns
        compostas = [
            "inteligência artificial", "mudança climática", "direitos humanos",
            "ciência da computação", "engenharia de software", "ciência de dados",
            "aprendizado de máquina", "processamento de linguagem natural",
            "visão computacional", "robótica", "internet das coisas", "blockchain"
        ]
        for c in compostas:
            cache.add(c.lower().replace(" ", ""))
        reconstruir_palavras.palavras_cache = cache

    palavras_conhecidas = reconstruir_palavras.palavras_cache
    tokens = texto.split()
    if len(tokens) < 2:
        return texto

    resultado = []
    i = 0
    while i < len(tokens):
        if len(tokens[i]) > 1:
            resultado.append(tokens[i])
            i += 1
            continue
        candidata = tokens[i]
        j = i + 1
        while j < len(tokens) and len(tokens[j]) == 1:
            candidata += tokens[j]
            j += 1
        if candidata.lower() in palavras_conhecidas or len(candidata) >= 3:
            resultado.append(candidata)
        else:
            resultado.extend(tokens[i:j])
        i = j
    return " ".join(resultado)

def inserir_espacos(texto):
    if not texto:
        return texto
    texto = re.sub(r'([a-záéíóúàèìòùâêîôûäëïöü])([A-ZÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÄËÏÖÜ])', r'\1 \2', texto)
    palavras_comuns = [
        'é', 'um', 'uma', 'para', 'com', 'de', 'do', 'da', 'dos', 'das',
        'em', 'na', 'no', 'nas', 'nos', 'por', 'que', 'se', 'como',
        'mais', 'mas', 'muito', 'pouco', 'tudo', 'nada', 'sistema',
        'operacional', 'software', 'hardware', 'windows', 'linux',
        'gratuito', 'livre', 'código', 'aberto', 'projeto', 'desenvolvimento'
    ]
    for palavra in palavras_comuns:
        padrao = re.compile(r'([a-záéíóú])({})([a-záéíóú])'.format(palavra), re.IGNORECASE)
        texto = padrao.sub(r'\1 \2 \3', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

# ============================================================================
# 7. FUNÇÕES DE ARQUIVO E VALIDAÇÃO
# ============================================================================

def salvar_texto(texto, prefixo, indice, pasta):
    os.makedirs(pasta, exist_ok=True)
    nome = f"{prefixo}_{indice:06d}.txt"
    caminho = os.path.join(pasta, nome)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(texto)
    return caminho

def salvar_dialogo(pergunta, resposta, prefixo, indice, pasta):
    """Salva um diálogo no formato Pergunta/Resposta."""
    texto = f"Pergunta: {pergunta}\nResposta: {resposta}"
    return salvar_texto(texto, prefixo, indice, pasta)

def listar_arquivos_invalidos(pasta):
    invalidos = []
    if not os.path.exists(pasta):
        return invalidos
    for nome in os.listdir(pasta):
        if not nome.endswith(".txt"):
            continue
        caminho = os.path.join(pasta, nome)
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                texto = f.read()
        except:
            invalidos.append((nome, "erro de leitura"))
            continue
        if not texto or len(texto.strip()) < 20:
            invalidos.append((nome, "texto vazio ou muito curto"))
            continue
        if "Pergunta:" in texto and "Resposta:" not in texto:
            invalidos.append((nome, "tem 'Pergunta:' mas não tem 'Resposta:'"))
            continue
        if "Pergunta:" in texto and "Resposta:" in texto:
            partes = texto.split("Resposta:", 1)
            if len(partes) > 1:
                resposta = partes[1].strip()
                if len(resposta) < 5:
                    invalidos.append((nome, f"resposta muito curta: '{resposta[:20]}...'"))
                    continue
            else:
                invalidos.append((nome, "formato P/R quebrado"))
                continue
    return invalidos

def limpar_arquivos_invalidos(pasta, dry_run=False):
    invalidos = listar_arquivos_invalidos(pasta)
    if not invalidos:
        print(f"✅ Nenhum arquivo inválido encontrado em {pasta}.")
        return 0, 0
    print(f"\n📋 {len(invalidos)} arquivos inválidos encontrados em {pasta}:")
    for nome, motivo in invalidos[:10]:
        print(f"   ⚠️ {nome} – {motivo}")
    if len(invalidos) > 10:
        print(f"   ... e mais {len(invalidos)-10} arquivos.")
    if dry_run:
        print("\n🔍 Modo dry-run: nenhum arquivo foi removido.")
        return 0, len(invalidos)
    resposta = input(f"\n🗑️  Deseja remover todos esses arquivos de {pasta}? (s/N): ").strip().lower()
    if resposta != 's':
        print("✅ Nenhum arquivo removido.")
        return 0, len(invalidos)
    removidos = 0
    for nome, _ in invalidos:
        caminho = os.path.join(pasta, nome)
        try:
            os.remove(caminho)
            removidos += 1
        except:
            pass
    print(f"✅ {removidos} arquivos removidos de {pasta}.")
    return removidos, len(invalidos)

def limpar_arquivos_profundamente(pasta, dry_run=False):
    if not os.path.exists(pasta):
        log(f"⚠️ Pasta {pasta} não existe.")
        return 0
    arquivos = []
    for raiz, _, files in os.walk(pasta):
        for f in files:
            if f.endswith('.txt'):
                arquivos.append(os.path.join(raiz, f))
    if not arquivos:
        log(f"✅ Nenhum arquivo .txt encontrado em {pasta}.")
        return 0
    log(f"\n🧹 Limpando {len(arquivos)} arquivos em {pasta}...")
    if dry_run:
        log("🔍 Modo dry-run: apenas listando.")
        for arq in arquivos[:10]:
            log(f"   {arq}")
        if len(arquivos) > 10:
            log(f"   ... e mais {len(arquivos)-10} arquivos.")
        return 0
    contador = 0
    for caminho in tqdm(arquivos, desc="Limpando"):
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
            texto_limpo = limpar_texto(conteudo)
            with open(caminho, 'w', encoding='utf-8') as f:
                f.write(texto_limpo)
            contador += 1
        except Exception as e:
            log(f"   ❌ Erro ao limpar {caminho}: {e}")
    log(f"✅ {contador} arquivos limpos em {pasta}.")
    return contador

def reconstruir_em_pasta(pasta, dry_run=False):
    if not os.path.exists(pasta):
        log(f"⚠️ Pasta {pasta} não existe.")
        return 0
    arquivos = []
    for raiz, _, files in os.walk(pasta):
        for f in files:
            if f.endswith('.txt'):
                arquivos.append(os.path.join(raiz, f))
    if not arquivos:
        log(f"✅ Nenhum arquivo .txt encontrado em {pasta}.")
        return 0
    log(f"\n🔧 Reconstruindo palavras em {len(arquivos)} arquivos em {pasta}...")
    if dry_run:
        log("🔍 Modo dry-run: apenas listando.")
        for arq in arquivos[:10]:
            log(f"   {arq}")
        if len(arquivos) > 10:
            log(f"   ... e mais {len(arquivos)-10} arquivos.")
        return 0
    contador = 0
    for caminho in tqdm(arquivos, desc="Reconstruindo"):
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
            novo = reconstruir_palavras(conteudo)
            if novo != conteudo:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(novo)
                contador += 1
        except Exception as e:
            log(f"   ❌ Erro ao reconstruir {caminho}: {e}")
    log(f"✅ {contador} arquivos reconstruídos em {pasta}.")
    return contador

# ============================================================================
# 8. QUALIFICAR DADOS (validar, limpar, reconstruir e mover para processed)
# ============================================================================

def qualificar_fonte(fonte, args):
    """Processa uma fonte: aplica validação, limpeza, reconstrução e copia para processed."""
    pasta_origem = os.path.join(PASTA_GERADOS, fonte)
    if not os.path.exists(pasta_origem):
        log(f"⚠️ Pasta {pasta_origem} não existe.")
        return 0

    # Lista todos os .txt da fonte
    arquivos = []
    for raiz, _, files in os.walk(pasta_origem):
        for f in files:
            if f.endswith('.txt'):
                arquivos.append(os.path.join(raiz, f))
    if not arquivos:
        log(f"ℹ️ Nenhum arquivo .txt em {pasta_origem} para qualificar.")
        return 0

    log(f"\n📂 Qualificando fonte '{fonte}' - {len(arquivos)} arquivos...")
    movidos = 0

    # Define o tipo de processamento conforme a fonte (diálogo ou texto)
    fontes_dialogo = ["ultrachat", "tucano", "guara"]
    tipo_padrao = "dialogo" if fonte in fontes_dialogo else "texto"

    for caminho in tqdm(arquivos, desc=f"Qualificando {fonte}"):
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
        except Exception as e:
            log(f"   ❌ Erro ao ler {caminho}: {e}")
            continue

        # Detecta automaticamente se é diálogo (caso o tipo_padrao não seja suficiente)
        tipo = tipo_padrao
        if any(marker in conteudo for marker in ["Pessoa:", "Outra:", "Pergunta:", "Usuário:", "Assistente:"]):
            tipo = "dialogo"

        # Aplica processamento
        resultado, motivos = processar_texto(
            conteudo,
            tipo=tipo,
            corrigir_espacos=args.corrigir_espacos,
            aplicar_reconstrucao=args.reconstruir_palavras
        )
        if resultado is None:
            log(f"   ⏭️ {os.path.basename(caminho)} descartado: {', '.join(motivos)}")
            continue

        # Se for diálogo, formata com "Pergunta:" e "Resposta:"
        if tipo == "dialogo":
            # resultado já é uma string formatada
            texto_saida = resultado
        else:
            texto_saida = resultado

        # Define nome destino (mantém o original se possível)
        nome_base = os.path.basename(caminho)
        if not nome_base.startswith(fonte):
            nome_base = f"{fonte}_{movidos:06d}.txt"

        destino = os.path.join(PASTA_PROCESSED, nome_base)
        if os.path.exists(destino):
            base, ext = os.path.splitext(nome_base)
            cont = 1
            while os.path.exists(os.path.join(PASTA_PROCESSED, f"{base}_{cont:02d}{ext}")):
                cont += 1
            destino = os.path.join(PASTA_PROCESSED, f"{base}_{cont:02d}{ext}")

        with open(destino, 'w', encoding='utf-8') as f:
            f.write(texto_saida)
        movidos += 1

    log(f"✅ {movidos} arquivos de '{fonte}' qualificados e salvos em {PASTA_PROCESSED}.")
    return movidos

# ============================================================================
# 9. FONTES DE DADOS (cada uma salva em sua pasta em gerados/)
# ============================================================================

# --- 9.1 BlogSet-BR (texto corrido) ---
def processar_blogset(corrigir_espacos=False, aplicar_reconstrucao=False):
    possiveis_caminhos = [
        "blogset-br.csv.gz",
        os.path.join(PASTA_RAW, "blogset-br.csv.gz"),
        "blogset-br.csv",
        os.path.join(PASTA_RAW, "blogset-br.csv"),
    ]
    caminho_entrada = None
    for p in possiveis_caminhos:
        if os.path.exists(p):
            caminho_entrada = p
            break
    if not caminho_entrada:
        log("\nℹ️ BlogSet-BR não encontrado. Pulando...")
        return 0

    log(f"\n📦 Processando BlogSet-BR: {caminho_entrada}")
    pasta_destino = os.path.join(PASTA_GERADOS, FONTES["blogset"])
    os.makedirs(pasta_destino, exist_ok=True)

    LIMITE_POSTS = 50000
    POSTS_POR_ARQUIVO = 100
    try:
        if caminho_entrada.endswith('.gz'):
            f_in = gzip.open(caminho_entrada, 'rt', encoding='utf-8')
        else:
            f_in = open(caminho_entrada, 'r', encoding='utf-8')
        leitor = csv.reader(f_in, delimiter=';')
        try:
            next(leitor)
        except StopIteration:
            log("❌ Arquivo vazio")
            f_in.close()
            return 0
        COL_CONTENT = 4
        contador_total = 0
        arquivo_atual = 0
        buffer_texto = []
        for linha in leitor:
            if len(linha) <= COL_CONTENT:
                continue
            conteudo_bruto = linha[COL_CONTENT].strip()
            if len(conteudo_bruto) < 200:
                continue
            texto_limpo, _ = processar_texto(conteudo_bruto, tipo="texto",
                                             corrigir_espacos=corrigir_espacos,
                                             aplicar_reconstrucao=aplicar_reconstrucao)
            if texto_limpo is None:
                continue
            buffer_texto.append(texto_limpo)
            contador_total += 1
            if len(buffer_texto) >= POSTS_POR_ARQUIVO:
                caminho = os.path.join(pasta_destino, f"blog_lote_{arquivo_atual:04d}.txt")
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write('\n\n'.join(buffer_texto))
                log(f"  💾 {caminho} ({len(buffer_texto)} posts)")
                buffer_texto = []
                arquivo_atual += 1
            if LIMITE_POSTS and contador_total >= LIMITE_POSTS:
                break
        if buffer_texto:
            caminho = os.path.join(pasta_destino, f"blog_lote_{arquivo_atual:04d}.txt")
            with open(caminho, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(buffer_texto))
            log(f"  💾 {caminho} ({len(buffer_texto)} posts)")
            arquivo_atual += 1
        f_in.close()
        log(f"✅ BlogSet-BR: {contador_total} posts salvos em {pasta_destino}.")
        return contador_total
    except Exception as e:
        log(f"❌ Erro no BlogSet-BR: {e}")
        return 0

# --- 9.2 Arquivos locais (PDF, HTML, etc.) ---
def extrair_texto_pdf(caminho, contador_pdf, total_pdfs):
    texto = ""
    try:
        doc = fitz.open(caminho)
        for pagina in doc:
            texto += pagina.get_text()
        doc.close()
        if len(texto.strip()) > 10:
            return re.sub(r'\s+', ' ', texto).strip(), "PyMuPDF"
    except:
        pass
    if PDFPLUMBER_DISPONIVEL:
        try:
            with pdfplumber.open(caminho) as pdf:
                for pagina in pdf.pages:
                    pagina_texto = pagina.extract_text()
                    if pagina_texto:
                        texto += pagina_texto + " "
            if len(texto.strip()) > 10:
                return re.sub(r'\s+', ' ', texto).strip(), "pdfplumber"
        except:
            pass
    if OCR_DISPONIVEL and len(texto.strip()) < 10:
        try:
            from PIL import Image
            import io
            doc = fitz.open(caminho)
            for pagina in doc:
                pix = pagina.get_pixmap()
                img_data = pix.tobytes("ppm")
                img = Image.open(io.BytesIO(img_data))
                texto_ocr = pytesseract.image_to_string(img, lang='por')
                if texto_ocr:
                    texto += texto_ocr + " "
            doc.close()
            if len(texto.strip()) > 10:
                return re.sub(r'\s+', ' ', texto).strip(), "OCR"
        except:
            pass
    return "", "nenhum"

def extrair_texto_html(caminho):
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        soup = BeautifulSoup(conteudo, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        return re.sub(r'\s+', ' ', soup.get_text(separator=' ')).strip()
    except:
        return ""

def extrair_texto_xml(caminho):
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(caminho)
        root = tree.getroot()
        texto = ""
        for elem in root.iter():
            if elem.text:
                texto += elem.text + " "
        return re.sub(r'\s+', ' ', texto).strip()
    except:
        return ""

def extrair_texto_txt(caminho):
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return re.sub(r'\s+', ' ', f.read()).strip()
    except:
        return ""

def processar_arquivo_local(caminho):
    ext = os.path.splitext(caminho)[1].lower()
    if ext == '.txt':
        return extrair_texto_txt(caminho), "TXT"
    elif ext == '.pdf':
        return extrair_texto_pdf(caminho, 0, 0)
    elif ext in ['.html', '.htm']:
        return extrair_texto_html(caminho), "HTML"
    elif ext == '.xml':
        return extrair_texto_xml(caminho), "XML"
    else:
        return "", ""

def processar_arquivos_locais(corrigir_espacos=False, aplicar_reconstrucao=False):
    log("\n📂 Processando arquivos locais...")
    pasta_destino = os.path.join(PASTA_GERADOS, FONTES["locais"])
    os.makedirs(pasta_destino, exist_ok=True)

    arquivos = []
    for pasta in [PASTA_RAW, PASTA_BASE]:
        if os.path.exists(pasta):
            for nome in os.listdir(pasta):
                caminho = os.path.join(pasta, nome)
                if os.path.isfile(caminho):
                    ext = os.path.splitext(nome)[1].lower()
                    if ext in ['.txt', '.pdf', '.html', '.htm', '.xml']:
                        arquivos.append(caminho)
    if not arquivos:
        log("   Nenhum arquivo local encontrado.")
        return 0

    log(f"   Encontrados {len(arquivos)} arquivos.")
    contador = 0
    for caminho in arquivos:
        nome = os.path.basename(caminho)
        log(f"   🧹 Processando: {nome}")
        texto_bruto, metodo = processar_arquivo_local(caminho)
        if not texto_bruto:
            log(f"      ⏭️ Falha na extração.")
            continue
        texto_limpo, motivos = processar_texto(texto_bruto, tipo="texto",
                                               corrigir_espacos=corrigir_espacos,
                                               aplicar_reconstrucao=aplicar_reconstrucao)
        if texto_limpo is None:
            log(f"      ❌ Descartado: {', '.join(motivos)}")
            continue
        salvar_texto(texto_limpo, "local", contador, pasta_destino)
        contador += 1
        log(f"      💾 Salvo ({metodo})")
    log(f"   ✅ {contador} arquivos locais salvos em {pasta_destino}.")
    return contador

# ============================================================================
# 9.3 UltrachatBR (diálogo) - CORRIGIDO COM TIMEOUT E RETRY
# ============================================================================

def baixar_ultrachatbr(limite=50000, corrigir_espacos=False, aplicar_reconstrucao=False):
    log("\n📥 Baixando UltrachatBR...")
    pasta_destino = os.path.join(PASTA_GERADOS, FONTES["ultrachat"])
    os.makedirs(pasta_destino, exist_ok=True)

    # Tenta usar hf_transfer se disponível
    try:
        import hf_transfer
        os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
        log("   ✅ hf_transfer ativado para download mais rápido.")
    except ImportError:
        log("   ℹ️ Para acelerar, instale: pip install hf_transfer")

    try:
        # Carrega o dataset com streaming e timeout aumentado
        dataset = load_dataset("recogna-nlp/UltrachatBR", split="train", streaming=True)
        contador = 0
        # Pega o primeiro exemplo para debug
        for i, exemplo in enumerate(dataset):
            if i == 0:
                log(f"   Estrutura do primeiro exemplo: {exemplo.keys()}")
                if 'conversa' in exemplo:
                    log(f"   Primeiro turno: {exemplo['conversa'][0] if exemplo['conversa'] else 'vazio'}")
            if contador >= limite:
                break
            # A chave correta é 'conversa', não 'conversations'
            conversas = exemplo.get('conversa', [])
            if not conversas:
                continue
            texto_bruto = ""
            for turno in conversas:
                if isinstance(turno, dict):
                    # Tenta obter o conteúdo de várias chaves possíveis
                    valor = turno.get('value') or turno.get('content') or turno.get('text')
                    if valor:
                        texto_bruto += str(valor) + " "
            if not texto_bruto.strip():
                continue
            resultado, motivos = processar_texto(texto_bruto, tipo="dialogo",
                                                 corrigir_espacos=corrigir_espacos,
                                                 aplicar_reconstrucao=aplicar_reconstrucao)
            if resultado is None:
                continue
            salvar_texto(resultado, "ultrachat", contador, pasta_destino)
            contador += 1
            if contador % 100 == 0:
                log(f"   Progresso Ultrachat: {contador} diálogos salvos")
        log(f"   ✅ UltrachatBR: {contador} diálogos salvos em {pasta_destino}.")
        return contador
    except Exception as e:
        log(f"   ❌ Erro no UltrachatBR: {e}")
        log("   ⚠️ Tentando novamente em 10 segundos...")
        time.sleep(10)
        try:
            # Tenta novamente com split menor
            dataset = load_dataset("recogna-nlp/UltrachatBR", split="train[:50000]", streaming=False)
            contador = 0
            for exemplo in tqdm(dataset, desc="   Processando (fallback)"):
                if contador >= limite:
                    break
                conversas = exemplo.get('conversa', [])
                if not conversas:
                    continue
                texto_bruto = ""
                for turno in conversas:
                    if isinstance(turno, dict):
                        valor = turno.get('value') or turno.get('content') or turno.get('text')
                        if valor:
                            texto_bruto += str(valor) + " "
                if not texto_bruto.strip():
                    continue
                resultado, motivos = processar_texto(texto_bruto, tipo="dialogo",
                                                     corrigir_espacos=corrigir_espacos,
                                                     aplicar_reconstrucao=aplicar_reconstrucao)
                if resultado is None:
                    continue
                salvar_texto(resultado, "ultrachat", contador, pasta_destino)
                contador += 1
            log(f"   ✅ UltrachatBR (fallback): {contador} diálogos salvos em {pasta_destino}.")
            return contador
        except Exception as e2:
            log(f"   ❌ Erro no fallback do UltrachatBR: {e2}")
            import traceback
            traceback.print_exc()
            return 0

# ============================================================================
# 9.4 Tucano-SFT (diálogo, com reconstrução ativada por padrão)
# ============================================================================

def baixar_tucano_sft(limite=30000, corrigir_espacos=False, aplicar_reconstrucao=True):
    log("\n📥 Baixando Tucano-SFT...")
    pasta_destino = os.path.join(PASTA_GERADOS, FONTES["tucano"])
    os.makedirs(pasta_destino, exist_ok=True)

    try:
        dataset = load_dataset("TucanoBR/Tucano-SFT", split="train", streaming=True)
        contador = 0
        for i, exemplo in enumerate(dataset):
            if i == 0:
                log(f"   Estrutura do primeiro exemplo: {exemplo.keys()}")
                if 'conversations' in exemplo:
                    log(f"   Primeiro turno: {exemplo['conversations'][0] if exemplo['conversations'] else 'vazio'}")
            if contador >= limite:
                break
            conversas = exemplo.get('conversations', [])
            if not conversas:
                continue
            texto_bruto = ""
            for turno in conversas:
                if isinstance(turno, dict):
                    # Tucano-SFT usa 'from' e 'value'
                    valor = turno.get('value')
                    if valor:
                        texto_bruto += str(valor) + " "
            if not texto_bruto.strip():
                continue
            resultado, motivos = processar_texto(texto_bruto, tipo="dialogo",
                                                 corrigir_espacos=corrigir_espacos,
                                                 aplicar_reconstrucao=aplicar_reconstrucao)
            if resultado is None:
                continue
            salvar_texto(resultado, "tucano", contador, pasta_destino)
            contador += 1
            if contador % 100 == 0:
                log(f"   Progresso Tucano: {contador} conversas salvas")
        log(f"   ✅ Tucano-SFT: {contador} conversas salvas em {pasta_destino}.")
        return contador
    except Exception as e:
        log(f"   ❌ Erro no Tucano-SFT: {e}")
        import traceback
        traceback.print_exc()
        return 0

# ============================================================================
# 9.5 Guará (diálogo)
# ============================================================================

def baixar_guara(limite=20000, corrigir_espacos=False, aplicar_reconstrucao=False):
    log("\n📥 Baixando Guará...")
    pasta_destino = os.path.join(PASTA_GERADOS, FONTES["guara"])
    os.makedirs(pasta_destino, exist_ok=True)

    try:
        dataset = load_dataset("adalbertojunior/Guara", split="train", streaming=True)
        contador = 0
        for i, exemplo in enumerate(dataset):
            if i == 0:
                log(f"   Estrutura do primeiro exemplo: {exemplo.keys()}")
                if 'text' in exemplo:
                    log(f"   Amostra do texto: {exemplo['text'][:200]}")
                elif 'conversations' in exemplo:
                    log(f"   Primeiro turno: {exemplo['conversations'][0] if exemplo['conversations'] else 'vazio'}")
            if contador >= limite:
                break
            texto_bruto = ""
            if 'text' in exemplo and exemplo['text']:
                texto_bruto = exemplo['text']
            elif 'conversations' in exemplo:
                for turno in exemplo['conversations']:
                    if isinstance(turno, dict):
                        valor = turno.get('value') or turno.get('content')
                        if valor:
                            texto_bruto += str(valor) + " "
            elif 'content' in exemplo:
                texto_bruto = exemplo['content']
            else:
                # Tenta pegar qualquer campo string grande
                for k, v in exemplo.items():
                    if isinstance(v, str) and len(v) > 50:
                        texto_bruto = v
                        break
            if not texto_bruto.strip():
                continue
            resultado, motivos = processar_texto(texto_bruto, tipo="dialogo",
                                                 corrigir_espacos=corrigir_espacos,
                                                 aplicar_reconstrucao=aplicar_reconstrucao)
            if resultado is None:
                continue
            salvar_texto(resultado, "guara", contador, pasta_destino)
            contador += 1
            if contador % 100 == 0:
                log(f"   Progresso Guará: {contador} textos salvos")
        log(f"   ✅ Guará: {contador} textos salvos em {pasta_destino}.")
        return contador
    except Exception as e:
        log(f"   ❌ Erro no Guará: {e}")
        import traceback
        traceback.print_exc()
        return 0

# ============================================================================
# 9.6 Wikipédia (crawler) - texto corrido
# ============================================================================

def extrair_links_wikipedia(soup, base_url):
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        url = urljoin(base_url, href)
        if not url.startswith("http"):
            continue
        if "pt.wikipedia.org" not in url:
            continue
        if any(x in url for x in ["#", "Especial:", "Ajuda:", "Portal:", "Categoria:", "Discussão:", "Wikipédia:"]):
            continue
        if any(url.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.pdf']):
            continue
        links.append(url)
    return links

def extrair_texto_wikipedia(soup):
    for tag in soup.find_all(['style', 'script', 'nav', 'footer', 'header']):
        tag.decompose()
    elementos = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'])
    textos = []
    for elem in elementos:
        texto = elem.get_text(strip=True)
        if len(texto) > 20:
            textos.append(texto)
    texto_bruto = ' '.join(textos)
    texto_bruto = re.sub(r'\[(editar|carece de fontes|nota \d+)\]', ' ', texto_bruto)
    texto_bruto = re.sub(r'\[\d+\]', ' ', texto_bruto)
    return re.sub(r'\s+', ' ', texto_bruto).strip()

def crawlar_wikipedia(paginas_maximas=500, profundidade_maxima=3, delay=1,
                      corrigir_espacos=False, aplicar_reconstrucao=False):
    log("\n🕸️ Iniciando crawler da Wikipédia...")
    pasta_destino = os.path.join(PASTA_GERADOS, FONTES["wiki"])
    os.makedirs(pasta_destino, exist_ok=True)

    HEADERS = {"User-Agent": "Mozilla/5.0"}
    visitados = set()
    contador = 0
    url_inicial = "https://pt.wikipedia.org/wiki/Brasil"

    def crawl(url, profundidade):
        nonlocal contador
        if url in visitados or contador >= paginas_maximas or profundidade > profundidade_maxima:
            return
        if "pt.wikipedia.org" not in url:
            return
        log(f"   🌐 [{contador}/{paginas_maximas}] Visitando: {url}")
        visitados.add(url)
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")
            html_tag = soup.find("html")
            if html_tag and "pt" not in html_tag.get("lang", ""):
                log("      ⚠️ Não é pt, ignorando.")
                return
            texto_limpo, _ = processar_texto(extrair_texto_wikipedia(soup), tipo="texto",
                                             corrigir_espacos=corrigir_espacos,
                                             aplicar_reconstrucao=aplicar_reconstrucao)
            if texto_limpo:
                salvar_texto(texto_limpo, "wiki", contador, pasta_destino)
                contador += 1
            links = extrair_links_wikipedia(soup, url)
            time.sleep(delay)
            for link in links:
                if contador >= paginas_maximas:
                    break
                crawl(link, profundidade + 1)
        except Exception as e:
            log(f"      ❌ Erro: {e}")

    crawl(url_inicial, 0)
    log(f"   ✅ Wikipédia: {contador} artigos salvos em {pasta_destino}.")
    return contador

# ============================================================================
# 10. FUNÇÃO PRINCIPAL
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Prepara dados para treino do RigelSLM (v1.0.0)")
    parser.add_argument("--qualificar", action="store_true", help="Aplica validação, limpeza e reconstrução, e copia dados válidos para dados/processed/")
    parser.add_argument("--fonte", type=str, choices=list(FONTES.keys()), help="Especifica uma fonte para operações (ex: tucano, ultrachat)")
    parser.add_argument("--validar", action="store_true", help="Lista arquivos inválidos (estruturalmente) em processed/ (ou na fonte se --fonte)")
    parser.add_argument("--limpar-invalidos", action="store_true", help="Remove arquivos inválidos")
    parser.add_argument("--limpar-processados", action="store_true", help="Aplica limpeza profunda (normalização Unicode) em processed/")
    parser.add_argument("--reconstruir-palavras", action="store_true", help="Reconstroi palavras separadas por espaços entre letras (Tucano)")
    parser.add_argument("--corrigir-espacos", action="store_true", help="(EXPERIMENTAL) tenta separar palavras grudadas")
    parser.add_argument("--skip-download", action="store_true", help="Pula download de novos dados (apenas processa locais)")
    parser.add_argument("--ver-logs", action="store_true", help="Exibe histórico de execuções")
    args = parser.parse_args()

    if args.ver_logs:
        ver_logs()
        return

    # Define a pasta alvo para operações de validação/limpeza/reconstrução
    if args.fonte:
        pasta_alvo = os.path.join(PASTA_GERADOS, FONTES[args.fonte])
    else:
        pasta_alvo = PASTA_PROCESSED

    # --- Operações em pastas específicas ---
    if args.validar:
        invalidos = listar_arquivos_invalidos(pasta_alvo)
        if not invalidos:
            print(f"✅ Nenhum arquivo inválido encontrado em {pasta_alvo}.")
        else:
            print(f"\n📋 {len(invalidos)} arquivos inválidos em {pasta_alvo}:")
            for nome, motivo in invalidos[:10]:
                print(f"   ⚠️ {nome} – {motivo}")
            if len(invalidos) > 10:
                print(f"   ... e mais {len(invalidos)-10} arquivos.")
        return

    if args.limpar_invalidos:
        inicio = time.time()
        removidos, _ = limpar_arquivos_invalidos(pasta_alvo, dry_run=False)
        registrar_historico({
            "data_hora": datetime.now().isoformat(),
            "acao": "limpar_invalidos",
            "removidos": removidos,
            "tempo_segundos": round(time.time() - inicio, 2)
        })
        return

    if args.limpar_processados:
        inicio = time.time()
        limpos = limpar_arquivos_profundamente(pasta_alvo, dry_run=False)
        registrar_historico({
            "data_hora": datetime.now().isoformat(),
            "acao": "limpar_processados",
            "limpos": limpos,
            "tempo_segundos": round(time.time() - inicio, 2)
        })
        return

    if args.reconstruir_palavras:
        inicio = time.time()
        reconstruidos = 0
        if args.fonte:
            reconstruidos += reconstruir_em_pasta(pasta_alvo, dry_run=False)
        else:
            for fonte in FONTES.values():
                pasta = os.path.join(PASTA_GERADOS, fonte)
                if os.path.exists(pasta):
                    reconstruidos += reconstruir_em_pasta(pasta, dry_run=False)
            reconstruidos += reconstruir_em_pasta(PASTA_PROCESSED, dry_run=False)
        registrar_historico({
            "data_hora": datetime.now().isoformat(),
            "acao": "reconstruir_palavras",
            "reconstruidos": reconstruidos,
            "tempo_segundos": round(time.time() - inicio, 2)
        })
        return

    # --- Qualificar (mover para processed) ---
    if args.qualificar:
        inicio = time.time()
        total_movidos = 0
        if args.fonte:
            total_movidos += qualificar_fonte(args.fonte, args)
        else:
            for fonte in FONTES.values():
                total_movidos += qualificar_fonte(fonte, args)
        registrar_historico({
            "data_hora": datetime.now().isoformat(),
            "acao": "qualificar",
            "movidos": total_movidos,
            "tempo_segundos": round(time.time() - inicio, 2)
        })
        print(f"\n✅ Qualificação concluída. {total_movidos} arquivos salvos em {PASTA_PROCESSED}.")
        return

    # --- Preparação normal (download + processamento) ---
    if args.skip_download:
        log("⏭️ Pular download, apenas processando locais.")
        processar_arquivos_locais(
            corrigir_espacos=args.corrigir_espacos,
            aplicar_reconstrucao=args.reconstruir_palavras
        )
        return

    log("=" * 70)
    log("🤖 PREPARAÇÃO DE DADOS PARA TREINO - RIGELSLM v1.0.0")
    log(f"📅 Data/hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"📁 Dados serão salvos em: {PASTA_GERADOS}/<fonte>/")
    log("=" * 70)

    if args.corrigir_espacos:
        log("⚠️  --corrigir-espacos ativado (experimental).\n")
    if args.reconstruir_palavras:
        log("🔧 Reconstrução de palavras ATIVADA.\n")

    total = 0
    total += processar_blogset(
        corrigir_espacos=args.corrigir_espacos,
        aplicar_reconstrucao=args.reconstruir_palavras
    )
    total += processar_arquivos_locais(
        corrigir_espacos=args.corrigir_espacos,
        aplicar_reconstrucao=args.reconstruir_palavras
    )
    total += baixar_ultrachatbr(
        limite=50000,
        corrigir_espacos=args.corrigir_espacos,
        aplicar_reconstrucao=args.reconstruir_palavras
    )
    total += baixar_tucano_sft(
        limite=30000,
        corrigir_espacos=args.corrigir_espacos,
        aplicar_reconstrucao=True  # sempre ativado para Tucano
    )
    total += baixar_guara(
        limite=20000,
        corrigir_espacos=args.corrigir_espacos,
        aplicar_reconstrucao=args.reconstruir_palavras
    )

    resposta = input("\nDeseja executar o crawler da Wikipédia? (S/N): ").strip().lower()
    if resposta == 's':
        total += crawlar_wikipedia(
            paginas_maximas=200,
            profundidade_maxima=2,
            delay=1,
            corrigir_espacos=args.corrigir_espacos,
            aplicar_reconstrucao=args.reconstruir_palavras
        )
    else:
        log("⏭️ Crawler ignorado.")

    log("\n" + "=" * 70)
    log("📊 RESUMO")
    log("=" * 70)
    log(f"   Total de arquivos salvos em {PASTA_GERADOS}/: {total}")
    log(f"   Blacklist: {BLACKLIST_PATH} ({len(PALAVRAS_PROIBIDAS)} palavras)")
    log(f"   Correção de espaços: {'ATIVADA' if args.corrigir_espacos else 'DESATIVADA'}")
    log(f"   Reconstrução: {'ATIVADA' if args.reconstruir_palavras else 'DESATIVADA'}")
    log("\n💡 Próximos passos:")
    log("   1. Qualifique os dados: python preparar_dados.py --qualificar")
    log("   2. Treine: python treino.py")
    log("=" * 70)

    registrar_historico({
        "data_hora": datetime.now().isoformat(),
        "acao": "download",
        "arquivos_gerados": total,
        "corrigir_espacos": args.corrigir_espacos,
        "reconstruir_palavras": args.reconstruir_palavras,
        "tempo_segundos": round(time.time() - inicio, 2)
    })

if __name__ == "__main__":
    inicio = time.time()
    main()