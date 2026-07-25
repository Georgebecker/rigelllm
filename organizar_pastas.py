#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
organizar_pastas.py - Organiza pastas de dados com limite de 5000 arquivos
e explode arquivos grandes (>30MB) em partes menores.
Uso: python organizar_pastas.py [--limite 5000] [--tamanho-max 30] [--registro registro_pastas.json] [--apenas-registro]
"""
import os
import sys
import json
import shutil
import argparse
import hashlib
import re
from pathlib import Path
from tqdm import tqdm
from datetime import datetime

# ============================================================================
# CONFIGURAÇÕES (podem ser sobrescritas por argumentos)
# ============================================================================
PASTA_BASE = "dados/processed"
PASTA_ORIGINAIS_GRANDES = "dados/originais_grandes"
REGISTRO_PADRAO = "registro_pastas.json"
LIMITE_ARQUIVOS = 5000
TAMANHO_MAX_MB = 30
PARES_POR_ARQUIVO = 10

# ============================================================================
# FUNÇÕES REUTILIZADAS (adaptadas de preparar_dados.py e utils.py)
# ============================================================================

def hash_texto(texto):
    """Retorna o hash SHA256 da versão normalizada do texto."""
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()

def normalizar_chave(texto):
    texto = texto.lower().strip()
    texto = re.sub(r"[^\w\sáàâãéêíóôõúçñ-]", "", texto, flags=re.UNICODE)
    texto = re.sub(r"\s+", " ", texto)
    return texto

def extrair_pares(conteudo):
    """
    Extrai pares Pergunta/Resposta de um bloco de texto.
    Retorna lista de strings no formato "Pergunta: ...\nResposta: ..."
    """
    pares = []
    # Divide por linhas em branco (separador comum)
    blocos = re.split(r'\n\s*\n', conteudo.strip())
    for bloco in blocos:
        bloco = bloco.strip()
        if not bloco:
            continue
        # Tenta capturar "Pergunta:" e "Resposta:" com regex robusto
        match_perg = re.search(r'(?:Pergunta|Perg)\s*[:]\s*(.+?)(?=\s*(?:Resposta|Resp)\s*[:]|$)', bloco, re.IGNORECASE | re.DOTALL)
        match_resp = re.search(r'(?:Resposta|Resp)\s*[:]\s*(.+)', bloco, re.IGNORECASE | re.DOTALL)
        if match_perg and match_resp:
            pergunta = match_perg.group(1).strip()
            resposta = match_resp.group(1).strip()
            if pergunta and resposta:
                pares.append(f"Pergunta: {pergunta}\nResposta: {resposta}")
        else:
            # Se não encontrar marcadores, mantém o bloco como está (pode ser texto corrido)
            # Mas vamos tentar separar por "?" para criar um par artificial
            if '?' in bloco:
                partes = bloco.split('?', 1)
                if len(partes) == 2 and len(partes[0]) > 5 and len(partes[1]) > 5:
                    pergunta = partes[0].strip() + '?'
                    resposta = partes[1].strip()
                    pares.append(f"Pergunta: {pergunta}\nResposta: {resposta}")
                else:
                    pares.append(bloco)
            else:
                pares.append(bloco)
    return pares

# ============================================================================
# FUNÇÕES PRINCIPAIS
# ============================================================================

def contar_arquivos(pasta):
    if not os.path.exists(pasta):
        return 0
    return len([f for f in os.listdir(pasta) if f.endswith('.txt')])

def listar_arquivos(pasta):
    if not os.path.exists(pasta):
        return []
    return [os.path.join(pasta, f) for f in os.listdir(pasta) if f.endswith('.txt')]

def tamanho_arquivo_mb(caminho):
    return os.path.getsize(caminho) / (1024 * 1024)

def dividir_pasta(pasta, limite=LIMITE_ARQUIVOS):
    """
    Divide uma pasta em subpastas com no máximo `limite` arquivos.
    Move os arquivos para as novas subpastas.
    Retorna lista de caminhos das subpastas criadas.
    """
    arquivos = listar_arquivos(pasta)
    if len(arquivos) <= limite:
        return []

    log(f"Dividindo pasta {pasta} com {len(arquivos)} arquivos em lotes de {limite}.")
    num_subpastas = (len(arquivos) + limite - 1) // limite
    subpastas_criadas = []
    nome_base = os.path.basename(pasta)
    dir_pai = os.path.dirname(pasta)

    for i in range(num_subpastas):
        subpasta = os.path.join(dir_pai, f"{nome_base}_{i+1}")
        os.makedirs(subpasta, exist_ok=True)
        subpastas_criadas.append(subpasta)
        inicio = i * limite
        fim = min((i+1) * limite, len(arquivos))
        batch = arquivos[inicio:fim]
        for arq in batch:
            shutil.move(arq, os.path.join(subpasta, os.path.basename(arq)))
        log(f"  Criada {subpasta} com {len(batch)} arquivos.")

    # A pasta original fica vazia; podemos removê-la (opcional)
    # Por segurança, não removemos automaticamente.
    return subpastas_criadas

def explodir_arquivos_grandes(pasta, tamanho_max_mb=TAMANHO_MAX_MB, pares_por_arq=PARES_POR_ARQUIVO):
    """
    Varre a pasta e subpastas, identifica arquivos > tamanho_max_mb,
    extrai pares e os divide em arquivos menores.
    Move os originais para PASTA_ORIGINAIS_GRANDES.
    """
    if not os.path.exists(pasta):
        return

    arquivos_grandes = []
    for raiz, _, arquivos in os.walk(pasta):
        for arq in arquivos:
            if not arq.endswith('.txt'):
                continue
            caminho = os.path.join(raiz, arq)
            if tamanho_arquivo_mb(caminho) > tamanho_max_mb:
                arquivos_grandes.append(caminho)

    if not arquivos_grandes:
        return

    log(f"Encontrados {len(arquivos_grandes)} arquivos grandes em {pasta}.")
    os.makedirs(PASTA_ORIGINAIS_GRANDES, exist_ok=True)

    for caminho in tqdm(arquivos_grandes, desc="Explodindo arquivos"):
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
        except Exception as e:
            log(f"Erro ao ler {caminho}: {e}", "ERRO")
            continue

        pares = extrair_pares(conteudo)
        if not pares:
            log(f"Nenhum par extraído de {caminho}, movendo para originais.")
            destino = os.path.join(PASTA_ORIGINAIS_GRANDES, os.path.relpath(caminho, PASTA_BASE))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.move(caminho, destino)
            continue

        # Divide em lotes de pares_por_arq
        num_arquivos = (len(pares) + pares_por_arq - 1) // pares_por_arq
        base_nome = os.path.splitext(os.path.basename(caminho))[0]
        dir_destino = os.path.dirname(caminho)

        for i in range(num_arquivos):
            inicio = i * pares_por_arq
            fim = min((i+1) * pares_por_arq, len(pares))
            lote = pares[inicio:fim]
            novo_nome = f"{base_nome}_parte_{i+1:03d}.txt"
            novo_caminho = os.path.join(dir_destino, novo_nome)
            with open(novo_caminho, 'w', encoding='utf-8') as f:
                f.write("\n\n".join(lote))
            log(f"  Criado {novo_caminho} com {len(lote)} pares.")

        # Move o original para a pasta de originais grandes
        destino = os.path.join(PASTA_ORIGINAIS_GRANDES, os.path.relpath(caminho, PASTA_BASE))
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.move(caminho, destino)
        log(f"  Original movido para {destino}")

def atualizar_registro(registro_path=REGISTRO_PADRAO):
    """Varre PASTA_BASE e atualiza o registro com os metadados atuais."""
    log("Atualizando registro...")
    if os.path.exists(registro_path):
        with open(registro_path, 'r', encoding='utf-8') as f:
            registro = json.load(f)
    else:
        registro = {"pastas": {}, "total_arquivos": 0, "total_pastas": 0, "ultima_atualizacao": ""}

    # Percorre apenas o primeiro nível de pastas
    pastas = [p for p in os.listdir(PASTA_BASE) if os.path.isdir(os.path.join(PASTA_BASE, p))]
    total_arquivos = 0
    for nome in pastas:
        caminho = os.path.join(PASTA_BASE, nome)
        # Conta arquivos recursivamente
        qtd = 0
        for _, _, arquivos in os.walk(caminho):
            qtd += len([a for a in arquivos if a.endswith('.txt')])
        subpastas = [d for d in os.listdir(caminho) if os.path.isdir(os.path.join(caminho, d))]
        # Calcula tamanho total (em MB)
        tamanho_mb = 0
        for raiz, _, arquivos in os.walk(caminho):
            for arq in arquivos:
                if arq.endswith('.txt'):
                    tamanho_mb += os.path.getsize(os.path.join(raiz, arq)) / (1024*1024)

        # Preserva dados anteriores (vezes_treinada, ultimo_treino)
        pasta_info = registro["pastas"].get(nome, {})
        pasta_info.update({
            "caminho": caminho,
            "subpastas": subpastas,
            "arquivos": qtd,
            "tamanho_total_mb": round(tamanho_mb, 2),
            "vezes_treinada": pasta_info.get("vezes_treinada", 0),
            "ultimo_treino": pasta_info.get("ultimo_treino", "")
        })
        registro["pastas"][nome] = pasta_info
        total_arquivos += qtd

    registro["total_arquivos"] = total_arquivos
    registro["total_pastas"] = len(pastas)
    registro["ultima_atualizacao"] = datetime.now().isoformat()

    with open(registro_path, 'w', encoding='utf-8') as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)
    log(f"Registro salvo em {registro_path}")

def incrementar_treino(pastas_usadas, registro_path=REGISTRO_PADRAO):
    """Incrementa o contador de vezes treinada para as pastas fornecidas."""
    if not os.path.exists(registro_path):
        log("Registro não encontrado. Execute --apenas-registro primeiro.", "AVISO")
        return
    with open(registro_path, 'r', encoding='utf-8') as f:
        registro = json.load(f)
    for nome in pastas_usadas:
        if nome in registro["pastas"]:
            registro["pastas"][nome]["vezes_treinada"] += 1
            registro["pastas"][nome]["ultimo_treino"] = datetime.now().isoformat()
        else:
            log(f"Pasta '{nome}' não encontrada no registro.", "AVISO")
    with open(registro_path, 'w', encoding='utf-8') as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)

# ============================================================================
# LOG E MAIN
# ============================================================================

def log(msg, nivel="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{nivel}] {msg}")

def main():
    parser = argparse.ArgumentParser(description="Organiza pastas de dados para o RigelSLM")
    parser.add_argument("--limite", type=int, default=LIMITE_ARQUIVOS,
                        help=f"Número máximo de arquivos por pasta (padrão: {LIMITE_ARQUIVOS})")
    parser.add_argument("--tamanho-max", type=float, default=TAMANHO_MAX_MB,
                        help=f"Tamanho máximo em MB para considerar arquivo grande (padrão: {TAMANHO_MAX_MB})")
    parser.add_argument("--registro", type=str, default=REGISTRO_PADRAO,
                        help="Arquivo de registro (padrão: registro_pastas.json)")
    parser.add_argument("--apenas-registro", action="store_true",
                        help="Apenas atualiza o registro sem reorganizar")
    args = parser.parse_args()

    if not os.path.exists(PASTA_BASE):
        log(f"Pasta base {PASTA_BASE} não encontrada.", "ERRO")
        sys.exit(1)

    if not args.apenas_registro:
        log("Iniciando organização das pastas...")
        # 1. Dividir pastas com muitos arquivos (apenas pastas de primeiro nível)
        for nome in os.listdir(PASTA_BASE):
            caminho = os.path.join(PASTA_BASE, nome)
            if os.path.isdir(caminho):
                # Evita dividir subpastas que já foram criadas pelo próprio script
                if not any(os.path.isdir(os.path.join(caminho, d)) for d in os.listdir(caminho) if d not in ['.', '..']):
                    dividir_pasta(caminho, args.limite)

        # 2. Explodir arquivos grandes em todas as subpastas
        for nome in os.listdir(PASTA_BASE):
            caminho = os.path.join(PASTA_BASE, nome)
            if os.path.isdir(caminho):
                explodir_arquivos_grandes(caminho, args.tamanho_max)

        log("Organização concluída.")

    # 3. Atualizar registro (sempre)
    atualizar_registro(args.registro)

if __name__ == "__main__":
    main()