#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
traduza.py - Traduz arquivos TXT (Pergunta/Resposta) do inglês para português.
Com RETRY automático, CHECKPOINT e SEM DUPLICATAS.

Uso:
    python traduza.py --pasta "D:/caminho/entrada" --saida "D:/caminho/saida"
    python traduza.py --pasta "..." --saida "..." --teste   (modo teste)
"""

import os
import glob
import argparse
import time
import json
import random
import hashlib
from tqdm import tqdm
from deep_translator import GoogleTranslator

# ================================================================
# ARGUMENTOS
# ================================================================
parser = argparse.ArgumentParser(description="Traduz arquivos TXT com retry e checkpoint")
parser.add_argument("--pasta", type=str, required=True,
                    help="Pasta com os arquivos .txt em inglês")
parser.add_argument("--saida", type=str, required=True,
                    help="Pasta onde salvar os arquivos traduzidos")
parser.add_argument("--teste", action="store_true",
                    help="Processa apenas 1 arquivo e 10 pares (para testar)")
args = parser.parse_args()

pasta_entrada = args.pasta
pasta_saida = args.saida
modo_teste = args.teste

os.makedirs(pasta_saida, exist_ok=True)

# ================================================================
# LISTA ARQUIVOS
# ================================================================
arquivos = sorted(glob.glob(os.path.join(pasta_entrada, "*.txt")))
print(f"📁 Encontrados {len(arquivos)} arquivos .txt")

if not arquivos:
    print("❌ Nenhum arquivo .txt encontrado.")
    exit(1)

if modo_teste:
    arquivos = arquivos[:1]
    print("🔬 MODO TESTE: apenas 1 arquivo e 10 pares")

# ================================================================
# TRADUTOR COM RETRY
# ================================================================
tradutor = GoogleTranslator(source='en', target='pt')

def traduzir_com_retry(texto, max_tentativas=3):
    for tentativa in range(max_tentativas):
        try:
            return tradutor.translate(texto)
        except Exception as e:
            if tentativa == max_tentativas - 1:
                raise
            tempo_espera = (2 ** tentativa) + random.uniform(0, 1)
            print(f"   ⚠️ Falha. Tentando novamente em {tempo_espera:.1f}s...")
            time.sleep(tempo_espera)
    return texto

# ================================================================
# CHECKPOINT
# ================================================================
def carregar_checkpoint(caminho):
    if os.path.exists(caminho):
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"pares_feitos": 0, "concluido": False}

def salvar_checkpoint(caminho, dados):
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=2)

# ================================================================
# EXTRAIR PARES DO ARQUIVO (BLOCO POR BLOCO)
# ================================================================
def extrair_pares(conteudo):
    """Divide o conteúdo em blocos separados por linhas vazias e extrai pergunta/resposta."""
    blocos = conteudo.strip().split('\n\n')
    pares = []
    for bloco in blocos:
        linhas = bloco.strip().split('\n')
        pergunta = None
        resposta = None
        for linha in linhas:
            if linha.startswith("Pergunta:"):
                pergunta = linha.replace("Pergunta:", "").strip()
            elif linha.startswith("Resposta:"):
                resposta = linha.replace("Resposta:", "").strip()
        if pergunta and resposta:
            pares.append((pergunta, resposta))
    return pares

# ================================================================
# TRADUZIR ARQUIVO (COM CHECKPOINT E SEM DUPLICATAS)
# ================================================================
def traduzir_arquivo(caminho_entrada, caminho_saida, limite=0):
    nome_base = os.path.basename(caminho_entrada)
    checkpoint_path = os.path.join(pasta_saida, f".checkpoint_{nome_base}.json")
    checkpoint = carregar_checkpoint(checkpoint_path)

    if checkpoint.get("concluido", False):
        print(f"   ✅ {nome_base} já concluído!")
        return 0, 0, 0

    # Lê o arquivo de entrada
    with open(caminho_entrada, 'r', encoding='utf-8') as f:
        conteudo = f.read()

    pares = extrair_pares(conteudo)
    total_pares = len(pares)
    pares_feitos = checkpoint.get("pares_feitos", 0)

    if pares_feitos >= total_pares:
        salvar_checkpoint(checkpoint_path, {"pares_feitos": total_pares, "concluido": True})
        print(f"   ✅ {nome_base} já estava completo!")
        return 0, 0, 0

    # Se o arquivo de saída já existe, lê os pares já traduzidos para evitar duplicatas
    pares_existentes = set()
    if os.path.exists(caminho_saida):
        with open(caminho_saida, 'r', encoding='utf-8') as f:
            conteudo_saida = f.read()
            # Extrai os pares já salvos
            blocos = conteudo_saida.strip().split('\n\n')
            for bloco in blocos:
                linhas = bloco.strip().split('\n')
                p = None
                r = None
                for linha in linhas:
                    if linha.startswith("Pergunta:"):
                        p = linha.replace("Pergunta:", "").strip()
                    elif linha.startswith("Resposta:"):
                        r = linha.replace("Resposta:", "").strip()
                if p and r:
                    # Cria um hash para identificar o par
                    hash_par = hashlib.md5((p + r).encode('utf-8')).hexdigest()
                    pares_existentes.add(hash_par)

    mantidos = 0
    erros = 0

    with open(caminho_saida, 'a', encoding='utf-8') as f_out:
        # Processa cada par a partir do checkpoint
        for i in range(pares_feitos, total_pares):
            if limite > 0 and mantidos >= limite:
                break

            pergunta, resposta = pares[i]

            # Gera hash para verificar duplicata
            hash_par = hashlib.md5((pergunta + resposta).encode('utf-8')).hexdigest()
            if hash_par in pares_existentes:
                # Se já existe, apenas atualiza o checkpoint e pula
                pares_feitos = i + 1
                continue

            try:
                pergunta_traduzida = traduzir_com_retry(pergunta)
                time.sleep(0.8)
                resposta_traduzida = traduzir_com_retry(resposta)
                time.sleep(0.8)

                f_out.write(f"Pergunta: {pergunta_traduzida}\n")
                f_out.write(f"Resposta: {resposta_traduzida}\n\n")
                f_out.flush()
                mantidos += 1
                pares_existentes.add(hash_par)  # adiciona ao conjunto para evitar duplicatas futuras

                # Salva checkpoint a cada 50 pares
                if mantidos % 50 == 0:
                    salvar_checkpoint(checkpoint_path, {
                        "pares_feitos": i + 1,
                        "concluido": False
                    })

            except Exception as e:
                # Em caso de erro, escreve o original
                f_out.write(f"Pergunta: {pergunta}\n")
                f_out.write(f"Resposta: {resposta}\n\n")
                f_out.flush()
                erros += 1
                print(f"   ❌ Erro: {str(e)[:50]}... (original mantido)")

            # Atualiza checkpoint a cada par (para retomada precisa)
            if (i + 1) % 10 == 0:
                salvar_checkpoint(checkpoint_path, {
                    "pares_feitos": i + 1,
                    "concluido": False
                })

    # Marca como concluído
    salvar_checkpoint(checkpoint_path, {"pares_feitos": total_pares, "concluido": True})
    return mantidos, 0, erros

# ================================================================
# PROCESSAMENTO
# ================================================================
total_mantidos = 0
total_erros = 0

for caminho_entrada in tqdm(arquivos, desc="Traduzindo", unit="arquivo"):
    nome_base = os.path.basename(caminho_entrada)
    caminho_saida = os.path.join(pasta_saida, nome_base)

    limite = 10 if modo_teste else 0
    mantidos, pulados, erros = traduzir_arquivo(caminho_entrada, caminho_saida, limite)

    total_mantidos += mantidos
    total_erros += erros

    print(f"✅ {nome_base}: {mantidos} novos pares traduzidos")

    if modo_teste:
        break

# ================================================================
# RESUMO
# ================================================================
print("\n" + "=" * 70)
print("📊 TRADUÇÃO CONCLUÍDA!")
print("=" * 70)
print(f"   📂 Pasta de entrada:  {pasta_entrada}")
print(f"   📂 Pasta de saída:    {pasta_saida}")
print(f"   ✅ Pares traduzidos:  {total_mantidos:,}")
print(f"   ❌ Erros:             {total_erros:,}")
print("=" * 70)
print("\n💡 Para retomar depois de uma falha, rode o mesmo comando novamente.")
