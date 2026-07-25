#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
rss_processor.py - Lê feeds RSS, classifica por tamanho, gera resumos e evita duplicatas.
Correções: timeouts aumentados, nomes de arquivo baseados em hash, delay ajustado.
Uso: python rss_processor.py --quantidade 10
"""

import os
import sys
import re
import time
import argparse
import hashlib
import httpx
import tempfile
import subprocess
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import xml.etree.ElementTree as ET

# ============================================================================
# BIBLIOTECAS EXTERNAS
# ============================================================================
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm
from bs4 import BeautifulSoup

# ============================================================================
# 1. CONFIGURAÇÃO DE PASTAS
# ============================================================================
PASTA_SAIDA = "dados/gerados"
PASTA_DADOS_CURTOS = os.path.join(PASTA_SAIDA, "curtos")       # < 500 palavras
PASTA_DADOS_LONGOS = os.path.join(PASTA_SAIDA, "longos")        # 500-1200 palavras
PASTA_DADOS_COMPLETOS = os.path.join(PASTA_SAIDA, "completos")  # > 1200 palavras (raw)
PASTA_DADOS_RESUMIDOS = os.path.join(PASTA_SAIDA, "resumidos")  # resumos dos completos
PASTA_LOGS = os.path.join(PASTA_SAIDA, "logs")
PASTA_DESCARTES = os.path.join(PASTA_SAIDA, "descartados")
ARQUIVO_LOG = os.path.join(PASTA_LOGS, "rss.log")
TOPICOS_PATH = "topicos.txt"
FEEDS_PATH = "feeds.txt"
PROCESSADOS_PATH = "processados.txt"

# Cria todas as pastas necessárias
for pasta in [PASTA_DADOS_CURTOS, PASTA_DADOS_LONGOS, PASTA_DADOS_COMPLETOS,
              PASTA_DADOS_RESUMIDOS, PASTA_LOGS, PASTA_DESCARTES]:
    os.makedirs(pasta, exist_ok=True)

# ============================================================================
# 2. CARREGAR VARIÁVEIS DE AMBIENTE E CONFIGURAR API
# ============================================================================
load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-flash")
MAX_COST_USD = float(os.getenv("MAX_COST_USD", "5.0"))
DELAY_SECONDS = float(os.getenv("DELAY_SECONDS", "4.0"))  # aumentado para evitar travamentos

if not API_KEY:
    print("❌ ERRO: DEEPSEEK_API_KEY não encontrada no arquivo .env")
    sys.exit(1)

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com/v1",
    timeout=httpx.Timeout(120.0, connect=15.0)
)

# ============================================================================
# 3. HEADERS PARA SIMULAR NAVEGADOR
# ============================================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

# ============================================================================
# 4. FUNÇÕES DE UTILIDADE
# ============================================================================
def limpar_texto(texto: str) -> str:
    """Remove URLs, emails, caracteres de controle e normaliza espaços."""
    texto = re.sub(r"https?://\S+|www\.\S+", "", texto)
    texto = re.sub(r"\S+@\S+\.\S+", "", texto)
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def normalizar_chave(texto: str) -> str:
    texto = texto.lower().strip()
    texto = re.sub(r"[^\w\sáàâãéêíóôõúçñ-]", "", texto, flags=re.UNICODE)
    texto = re.sub(r"\s+", " ", texto)
    return texto

def hash_texto(texto: str) -> str:
    return hashlib.sha256(normalizar_chave(texto).encode('utf-8')).hexdigest()

def salvar_descarte(texto: str, prefixo: str, motivo: str, indice: int) -> str:
    nome = f"{prefixo}_descarte_{indice:06d}.txt"
    caminho = os.path.join(PASTA_DESCARTES, nome)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(f"MOTIVO DO DESCARTE: {motivo}\n\n--- TEXTO ---\n\n{texto}")
    return caminho

def log(msg: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linha = f"[{timestamp}] {msg}"
    print(linha)
    with open(ARQUIVO_LOG, 'a', encoding='utf-8') as f:
        f.write(linha + "\n")

# ============================================================================
# 5. CONTROLE DE DUPLICATAS
# ============================================================================
def carregar_processados() -> set:
    if not os.path.exists(PROCESSADOS_PATH):
        return set()
    with open(PROCESSADOS_PATH, 'r', encoding='utf-8') as f:
        return set([linha.strip() for linha in f if linha.strip()])

def salvar_processados(processados: set) -> None:
    with open(PROCESSADOS_PATH, 'w', encoding='utf-8') as f:
        for h in sorted(processados):
            f.write(h + "\n")

# ============================================================================
# 6. LEITURA DE RSS (COM 4 ESTRATÉGIAS)
# ============================================================================
def parse_rss(feed_url: str) -> List[Dict]:
    estrategias = [
        ("httpx com headers completos", lambda: _baixar_com_httpx(feed_url)),
        ("httpx com User-Agent alternativo", lambda: _baixar_com_httpx_alt(feed_url)),
        ("requests com sessão", lambda: _baixar_com_requests(feed_url)),
        ("curl via subprocess", lambda: _baixar_com_curl(feed_url)),
    ]
    
    for nome_estrategia, funcao in estrategias:
        log(f"🔍 Tentando estratégia: {nome_estrategia}")
        try:
            content = funcao()
            if content:
                try:
                    root = ET.fromstring(content)
                    channel = root.find("channel")
                    if channel is not None:
                        items = []
                        for item in channel.findall("item"):
                            title = item.find("title")
                            link = item.find("link")
                            description = item.find("description")
                            pub_date = item.find("pubDate")
                            items.append({
                                "title": title.text.strip() if title is not None else "",
                                "link": link.text.strip() if link is not None else "",
                                "description": description.text.strip() if description is not None else "",
                                "pub_date": pub_date.text.strip() if pub_date is not None else ""
                            })
                        if items:
                            log(f"✅ RSS obtido com sucesso! {len(items)} itens.")
                            return items
                except ET.ParseError as e:
                    log(f"⚠️ Erro ao parsear XML: {e}. Tentando próxima estratégia...")
                    continue
        except Exception as e:
            log(f"⚠️ Estratégia falhou: {e}")
            continue
    
    log(f"❌ Todas as estratégias falharam para {feed_url}")
    return []

def _baixar_com_httpx(url: str) -> Optional[str]:
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.text

def _baixar_com_httpx_alt(url: str) -> Optional[str]:
    headers_alt = HEADERS.copy()
    headers_alt["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0"
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = client.get(url, headers=headers_alt)
        response.raise_for_status()
        return response.text

def _baixar_com_requests(url: str) -> Optional[str]:
    try:
        import requests
        session = requests.Session()
        session.headers.update(HEADERS)
        response = session.get(url, timeout=120)
        response.raise_for_status()
        return response.text
    except ImportError:
        log("⚠️ requests não instalado. Pulando esta estratégia.")
        return None

def _baixar_com_curl(url: str) -> Optional[str]:
    try:
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.xml', delete=False) as tmp:
            tmp_path = tmp.name
        cmd = [
            "curl", "-L", "-s", "-H", f"User-Agent: {HEADERS['User-Agent']}",
            "-H", f"Accept: {HEADERS['Accept']}",
            "-o", tmp_path, url
        ]
        subprocess.run(cmd, check=True, timeout=120)
        with open(tmp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        os.unlink(tmp_path)
        return content
    except Exception as e:
        log(f"⚠️ curl falhou: {e}")
        return None

# ============================================================================
# 7. SCRAPING (EXTRAÇÃO DE TEXTO DA PÁGINA)
# ============================================================================
def extrair_texto_pagina(url: str) -> Optional[str]:
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get(url, headers=HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove elementos irrelevantes
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'noscript', 'iframe']):
            tag.decompose()
        
        # Seletores em ordem de prioridade
        seletores = [
            '.content-v1', '.entry-content', '.post-content', '.content',
            'article', 'main'
        ]
        
        content = None
        for seletor in seletores:
            if seletor.startswith('.'):
                elemento = soup.find('div', class_=seletor[1:])
            else:
                elemento = soup.find(seletor)
            if elemento:
                texto_bruto = elemento.get_text(separator=' ')
                if texto_bruto and len(texto_bruto.split()) > 100:
                    content = texto_bruto
                    log(f"   ✅ Seletor encontrado: {seletor}")
                    break
        
        # Fallback: pega todos os parágrafos do body
        if not content and soup.body:
            paragrafos = soup.body.find_all('p')
            if paragrafos:
                content = ' '.join([p.get_text(separator=' ') for p in paragrafos])
            else:
                content = soup.body.get_text(separator=' ')
        
        if not content:
            return None
        
        # Limpeza de lixo (assinaturas, chamadas para doação, etc.)
        content = re.sub(r'A grande mídia esconde.*?nossa única força é você\.', '', content, flags=re.IGNORECASE)
        content = re.sub(r'Faça sua doação.*?ICL', '', content, flags=re.IGNORECASE)
        content = re.sub(r'Por \w+ \w+ e \w+ \w+', '', content)
        content = re.sub(r'\(Folhapress\)', '', content)
        content = re.sub(r'\s+', ' ', content).strip()
        
        # Limita a 3000 palavras para evitar estouro
        palavras = content.split()
        if len(palavras) > 3000:
            content = ' '.join(palavras[:3000])
        
        return content
    except Exception as e:
        log(f"⚠️ Erro ao fazer scraping de {url}: {e}")
        return None

# ============================================================================
# 8. GERAÇÃO DE RESUMO (API)
# ============================================================================
def gerar_resumo(titulo: str, texto_completo: str, descricao_fallback: str = "") -> Optional[str]:
    if not titulo:
        return None
    
    if not texto_completo or len(texto_completo.split()) < 50:
        texto_completo = descricao_fallback
        if not texto_completo:
            return None
        log(f"ℹ️ Usando descrição como fallback para: {titulo}")
    
    texto_limpo = limpar_texto(texto_completo)
    if len(texto_limpo.split()) > 1500:
        texto_limpo = ' '.join(texto_limpo.split()[:1500])
    
    if len(texto_limpo.split()) < 20:
        prompt = f"""Crie um resumo informativo e detalhado (120-180 palavras) sobre a notícia abaixo.

Título: {titulo}
Descrição: {texto_limpo}

REGRAS:
1. Use os dados disponíveis para criar um texto coerente e relevante.
2. Inclua contexto, motivos e consequências quando possível.
3. Seja jornalístico e objetivo.
4. O resumo DEVE TER NO MÍNIMO 120 palavras.
5. NÃO use Markdown, HTML, listas ou emojis.
6. NÃO use frases como "espero ter ajudado" ou "como assistente".
7. Escreva APENAS o resumo, sem comentários adicionais.

Resumo (mínimo 120 palavras):"""
    else:
        prompt = f"""Resuma a seguinte notícia em português brasileiro de forma clara e objetiva.

Título: {titulo}

Texto completo da notícia:
{texto_limpo}

REGRAS:
1. O resumo deve ter entre 4 e 7 frases (mínimo 100 palavras, máximo 250 palavras).
2. Destaque os pontos mais importantes, como quem, o quê, quando, onde e porquê.
3. Seja direto, informativo e evite repetições.
4. O resumo DEVE SER COMPLETO e concluir a informação.
5. NÃO use Markdown, HTML, listas ou emojis.
6. NÃO use frases como "espero ter ajudado" ou "como assistente".
7. NÃO mencione que é uma inteligência artificial.
8. Escreva APENAS o resumo, sem comentários adicionais.

Resumo (mínimo 100 palavras):"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=700,
            top_p=0.9
        )
        texto = response.choices[0].message.content if response.choices else ""
        if not texto:
            return None
        texto = limpar_texto(texto)
        if len(texto.split()) < 5:
            return None
        return texto
    except Exception as e:
        log(f"⚠️ Erro ao gerar resumo: {e}")
        return None

# ============================================================================
# 9. GERAR NOME DE ARQUIVO (BASEADO EM HASH DO TÍTULO)
# ============================================================================
def gerar_nome_arquivo(titulo: str, data: str, indice: int) -> str:
    """
    Gera um nome único baseado na data, um hash curto do título e um contador.
    Exemplo: news02072026_a3f2.txt
    """
    hash_curto = hashlib.sha256(titulo.encode('utf-8')).hexdigest()[:4]
    letra = chr(ord('a') + (indice % 26))
    return f"news{data}_{hash_curto}{letra}.txt"

# ============================================================================
# 10. CLASSIFICAR E SALVAR (COM NOMES ÚNICOS)
# ============================================================================
def salvar_texto_classificado(titulo: str, texto_bruto: str, data_atual: str, indice_global: int) -> Tuple[Optional[str], Optional[str], Optional[int]]:
    palavras = len(texto_bruto.split())
    tipo = ""
    
    if palavras < 500:
        pasta = PASTA_DADOS_CURTOS
        tipo = "curto"
        resumo = gerar_resumo(titulo, texto_bruto, "")
        if resumo is None:
            return None, None, None
        conteudo = f"Pergunta: {titulo}\nResposta: {resumo}"
    elif palavras < 1200:
        pasta = PASTA_DADOS_LONGOS
        tipo = "longo"
        resumo = gerar_resumo(titulo, texto_bruto, "")
        if resumo is None:
            return None, None, None
        conteudo = f"Pergunta: {titulo}\nResposta: {resumo}"
    else:
        pasta = PASTA_DADOS_COMPLETOS
        tipo = "completo"
        conteudo = f"Pergunta: {titulo}\n\nTexto completo:\n{texto_bruto}"
    
    # Gera nome com hash do título
    nome_base = gerar_nome_arquivo(titulo, data_atual, indice_global)
    caminho = os.path.join(pasta, nome_base)
    
    # Evita sobrescrever: tenta até 100 variações
    contador = 0
    while os.path.exists(caminho) and contador < 100:
        letra = chr(ord('a') + ((indice_global + contador) % 26))
        nome_base = gerar_nome_arquivo(titulo, data_atual, indice_global + contador)
        caminho = os.path.join(pasta, nome_base)
        contador += 1
    
    if contador >= 100:
        log(f"❌ Não foi possível gerar nome único para: {titulo}")
        return None, None, None
    
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(conteudo)
    
    return caminho, tipo, palavras

# ============================================================================
# 11. LER LISTA DE FEEDS (do arquivo feeds.txt)
# ============================================================================
def ler_feeds(arquivo: str) -> List[str]:
    if not os.path.exists(arquivo):
        log(f"⚠️ Arquivo {arquivo} não encontrado. Usando feed padrão.")
        return ["https://iclnoticias.com.br/feed/"]
    
    feeds = []
    with open(arquivo, 'r', encoding='utf-8') as f:
        for linha in f:
            linha = linha.strip()
            if linha and not linha.startswith('#'):
                feeds.append(linha)
    
    if not feeds:
        log(f"⚠️ Nenhum feed encontrado em {arquivo}. Usando feed padrão.")
        return ["https://iclnoticias.com.br/feed/"]
    
    return feeds

# ============================================================================
# 12. RESUMIR ARQUIVOS COMPLETOS (opcional)
# ============================================================================
def resumir_arquivos_completos() -> None:
    if not os.path.exists(PASTA_DADOS_COMPLETOS):
        log("📭 Pasta 'completos' não encontrada.")
        return
    
    arquivos = [f for f in os.listdir(PASTA_DADOS_COMPLETOS) if f.endswith('.txt')]
    if not arquivos:
        log("📭 Nenhum arquivo completo para resumir.")
        return
    
    print(f"\n📄 {len(arquivos)} arquivos completos encontrados.")
    resposta = input("🔍 Deseja resumir os textos completos agora? (s/N): ").strip().lower()
    if resposta != 's':
        print("❌ Resumo cancelado.")
        return
    
    log("📡 INICIANDO RESUMO DOS TEXTOS COMPLETOS")
    total_gerados = 0
    total_falhas = 0
    
    for arquivo in tqdm(arquivos, desc="Resumindo completos"):
        caminho_origem = os.path.join(PASTA_DADOS_COMPLETOS, arquivo)
        try:
            with open(caminho_origem, 'r', encoding='utf-8') as f:
                conteudo = f.read()
            
            match = re.search(r'Pergunta:\s*(.+?)\n\nTexto completo:\s*(.+)', conteudo, re.DOTALL)
            if not match:
                log(f"⚠️ Formato inválido: {arquivo}")
                total_falhas += 1
                continue
            
            titulo = match.group(1).strip()
            texto = match.group(2).strip()
            
            resumo = gerar_resumo(titulo, texto, "")
            if resumo is None:
                log(f"⚠️ Falha ao resumir: {arquivo}")
                total_falhas += 1
                continue
            
            nome_saida = f"resumo_{arquivo}"
            caminho_saida = os.path.join(PASTA_DADOS_RESUMIDOS, nome_saida)
            with open(caminho_saida, 'w', encoding='utf-8') as f:
                f.write(f"Pergunta: {titulo}\nResposta: {resumo}")
            
            total_gerados += 1
            log(f"✅ Resumo salvo: {caminho_saida}")
            time.sleep(DELAY_SECONDS)
            
        except Exception as e:
            log(f"⚠️ Erro ao processar {arquivo}: {e}")
            total_falhas += 1
    
    print(f"\n📊 Resumo dos completos: {total_gerados} gerados, {total_falhas} falhas.")
    log(f"📊 Resumo dos completos: {total_gerados} gerados, {total_falhas} falhas.")

# ============================================================================
# 13. FUNÇÃO PRINCIPAL
# ============================================================================
def main():
    parser = argparse.ArgumentParser(description="Processa RSS de uma lista de feeds, classifica por tamanho e gera resumos")
    parser.add_argument("--quantidade", type=int, default=10, help="Número de notícias por feed")
    parser.add_argument("--prefixo", type=str, default="rss", help="Prefixo para descartes")
    parser.add_argument("--delay", type=float, default=DELAY_SECONDS, help="Delay entre requisições")
    parser.add_argument("--feeds", type=str, default=FEEDS_PATH, help="Arquivo com lista de feeds")
    parser.add_argument("--skip-resumir", action="store_true", help="Pula a pergunta para resumir completos")
    args = parser.parse_args()

    log("=" * 70)
    log("📡 RSS PROCESSOR v3.1 - CLASSIFICAÇÃO AUTOMÁTICA COM CONTROLE DE DUPLICATAS")
    log(f"   Arquivo de feeds: {args.feeds}")
    log(f"   Quantidade por feed: {args.quantidade}")
    log(f"   Delay: {args.delay}s")
    log("=" * 70)

    feeds = ler_feeds(args.feeds)
    log(f"📋 {len(feeds)} feeds carregados.")

    processados = carregar_processados()
    log(f"📋 {len(processados)} títulos já processados.")

    total_gerados = 0
    total_descartes = 0
    total_completos = 0
    total_pulados = 0
    estatisticas = {"curto": 0, "longo": 0, "completo": 0}

    if os.path.exists(TOPICOS_PATH):
        with open(TOPICOS_PATH, 'r', encoding='utf-8') as f:
            topicos_existentes = set([linha.strip() for linha in f if linha.strip()])
    else:
        topicos_existentes = set()

    data_atual = datetime.now().strftime("%d%m%Y")
    indice_global = 0

    for feed_idx, feed_url in enumerate(feeds):
        log(f"\n📡 Processando feed {feed_idx+1}/{len(feeds)}: {feed_url}")
        
        noticias = parse_rss(feed_url)
        if not noticias:
            log(f"❌ Nenhuma notícia encontrada em {feed_url}")
            continue

        log(f"📰 {len(noticias)} notícias encontradas. Processando as primeiras {args.quantidade}...")
        noticias = noticias[:args.quantidade]

        with tqdm(total=len(noticias), desc=f"Feed {feed_idx+1}") as pbar:
            for i, noticia in enumerate(noticias):
                titulo = noticia["title"]
                link = noticia["link"]
                descricao = noticia["description"]
                
                if not titulo:
                    pbar.update(1)
                    continue

                hash_titulo = hashlib.sha256(titulo.encode('utf-8')).hexdigest()
                if hash_titulo in processados:
                    log(f"⏭️ Pulando (já processado): {titulo[:50]}...")
                    total_pulados += 1
                    pbar.update(1)
                    continue

                if titulo not in topicos_existentes:
                    topicos_existentes.add(titulo)

                texto_extraido = None
                if link:
                    log(f"📄 Raspando: {link}")
                    texto_extraido = extrair_texto_pagina(link)
                    if texto_extraido:
                        palavras = len(texto_extraido.split())
                        log(f"   ✅ Texto extraído: {palavras} palavras")
                    else:
                        log(f"   ⚠️ Falha ao extrair, usando descrição como fallback")
                        texto_extraido = descricao

                if not texto_extraido:
                    total_descartes += 1
                    salvar_descarte(
                        f"Título: {titulo}\nLink: {link}\nDescrição: {descricao}",
                        args.prefixo, "sem_conteudo", i
                    )
                    pbar.update(1)
                    continue

                caminho, tipo, palavras = salvar_texto_classificado(titulo, texto_extraido, data_atual, indice_global)
                if caminho is None:
                    total_descartes += 1
                    salvar_descarte(
                        f"Título: {titulo}\nTexto extraído: {texto_extraido}",
                        args.prefixo, "falha_resumo", i
                    )
                    pbar.update(1)
                    continue

                processados.add(hash_titulo)
                salvar_processados(processados)

                if tipo == "completo":
                    total_completos += 1
                    log(f"📦 Salvo como COMPLETO: {caminho} ({palavras} palavras)")
                else:
                    total_gerados += 1
                    log(f"✅ Salvo: {caminho} ({tipo}, {palavras} palavras)")

                estatisticas[tipo] = estatisticas.get(tipo, 0) + 1
                indice_global += 1
                pbar.update(1)

                time.sleep(args.delay)

        log(f"📊 Feed {feed_idx+1} - Gerados: {total_gerados}, Completos: {total_completos}, Descartados: {total_descartes}, Pulados: {total_pulados}")

    with open(TOPICOS_PATH, 'w', encoding='utf-8') as f:
        for topico in sorted(topicos_existentes):
            f.write(topico + "\n")
    log(f"✅ {len(topicos_existentes)} tópicos salvos em {TOPICOS_PATH}")

    salvar_processados(processados)
    log(f"✅ {len(processados)} títulos marcados como processados.")

    log("\n" + "=" * 70)
    log("📊 RESUMO FINAL")
    log("=" * 70)
    log(f"   ✅ Resumos gerados: {total_gerados}")
    log(f"   📦 Completos (raw): {total_completos}")
    log(f"   ❌ Descartados: {total_descartes}")
    log(f"   ⏭️ Pulados (duplicatas): {total_pulados}")
    log(f"   📂 Curtos: {PASTA_DADOS_CURTOS}")
    log(f"   📂 Longos: {PASTA_DADOS_LONGOS}")
    log(f"   📂 Completos: {PASTA_DADOS_COMPLETOS}")
    log(f"   📂 Descartados: {PASTA_DESCARTES}")
    log(f"   📝 Log: {ARQUIVO_LOG}")
    log("=" * 70)

    print("\n📁 **PASTAS UTILIZADAS:**")
    print(f"   Curtos (< 500 palavras): {os.path.abspath(PASTA_DADOS_CURTOS)}")
    print(f"   Longos (500-1200 palavras): {os.path.abspath(PASTA_DADOS_LONGOS)}")
    print(f"   Completos (> 1200 palavras): {os.path.abspath(PASTA_DADOS_COMPLETOS)}")
    print(f"   Descartados: {os.path.abspath(PASTA_DESCARTES)}")
    print(f"   Tópicos: {os.path.abspath(TOPICOS_PATH)}")
    print(f"   Processados: {os.path.abspath(PROCESSADOS_PATH)}")

    if total_completos > 0 and not args.skip_resumir:
        resumir_arquivos_completos()

if __name__ == "__main__":
    main()