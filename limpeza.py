#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
limpeza.py - Corrige a codificação de arquivos .txt, gerando cópias em utf-8.
- Varre recursivamente a pasta de entrada.
- Tenta ler cada arquivo com várias codificações (utf-8, latin-1, cp1252, etc.).
- Se a codificação for diferente de utf-8, converte e salva como utf-8.
- Se já estiver em utf-8, apenas copia (ou ignora, a critério do usuário).
- Gera um log detalhado (limpeza.log) com os arquivos corrigidos.
- Mostra barra de progresso com porcentagem, contagem e pasta atual.
"""

import os
import sys
import glob
import time
import argparse
from tqdm import tqdm

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

ENCODINGS = ['utf-8', 'latin-1', 'cp1252', 'utf-16', 'iso-8859-1']
LOG_FILE = "limpeza.log"
PASTA_ENTRADA_PADRAO = "dados/processed"
PASTA_SAIDA_PADRAO = "dados/processed_corrigido"

# ============================================================================
# FUNÇÃO PARA TENTAR LER UM ARQUIVO COM DIFERENTES CODIFICAÇÕES
# ============================================================================

def ler_com_encoding(caminho):
    """
    Tenta ler o arquivo com cada codificação da lista.
    Retorna (conteúdo, encoding_usado) ou (None, None) se falhar.
    """
    for encoding in ENCODINGS:
        try:
            with open(caminho, 'r', encoding=encoding) as f:
                conteudo = f.read()
            return conteudo, encoding
        except UnicodeDecodeError:
            continue
    return None, None

# ============================================================================
# FUNÇÃO PARA ESCREVER O LOG
# ============================================================================

def escrever_log(msg, modo='a'):
    with open(LOG_FILE, modo, encoding='utf-8') as f:
        f.write(msg + "\n")

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def corrigir_codificacao(pasta_entrada, pasta_saida, copiar_utf8=False):
    """
    Processa todos os arquivos .txt da pasta_entrada (recursivamente),
    corrige a codificação e salva em pasta_saida.
    Se copiar_utf8 for True, copia também os arquivos que já estão em utf-8.
    Caso contrário, apenas corrige os que precisam de conversão.
    """
    os.makedirs(pasta_saida, exist_ok=True)
    
    # Lista recursivamente todos os .txt
    arquivos = glob.glob(os.path.join(pasta_entrada, "**", "*.txt"), recursive=True)
    if not arquivos:
        print(f"❌ Nenhum arquivo .txt encontrado em {pasta_entrada}")
        return

    # Inicializa estatísticas
    stats = {
        "total": len(arquivos),
        "convertidos": 0,
        "ja_utf8": 0,
        "erros": 0,
        "ignorados": 0,
        "por_encoding": {},
        "arquivos_convertidos": []
    }

    # Abre o log (sobrescreve se existir)
    escrever_log("="*70, 'w')
    escrever_log(f"📅 INÍCIO DA LIMPEZA: {time.ctime()}")
    escrever_log(f"📂 Pasta de entrada: {pasta_entrada}")
    escrever_log(f"📁 Pasta de saída:   {pasta_saida}")
    escrever_log("="*70)

    print(f"\n📂 Entrada: {pasta_entrada}")
    print(f"📁 Saída:   {pasta_saida}")
    print(f"📦 {stats['total']} arquivos encontrados")
    if copiar_utf8:
        print("🔁 Modo: copiar TODOS os arquivos (inclusive UTF-8)")
    else:
        print("🔁 Modo: apenas corrigir arquivos com codificação diferente de UTF-8")
    print()

    # Barra de progresso
    pbar = tqdm(arquivos, desc="Processando", unit="arquivo")
    inicio = time.time()

    for caminho in pbar:
        # Calcula caminho relativo para manter estrutura
        rel_path = os.path.relpath(caminho, pasta_entrada)
        destino = os.path.join(pasta_saida, rel_path)
        os.makedirs(os.path.dirname(destino), exist_ok=True)

        # Atualiza a barra com a pasta atual
        pasta_atual = os.path.dirname(rel_path) if os.path.dirname(rel_path) else "raiz"
        pbar.set_description(f"Processando {pasta_atual}")

        # Tenta ler o arquivo
        conteudo, encoding_usado = ler_com_encoding(caminho)

        if conteudo is None:
            stats["erros"] += 1
            escrever_log(f"❌ ERRO: {rel_path} – não foi possível ler com nenhuma codificação")
            pbar.set_postfix({"erros": stats["erros"]})
            continue

        # Contabiliza encoding
        stats["por_encoding"][encoding_usado] = stats["por_encoding"].get(encoding_usado, 0) + 1

        # Decide se deve salvar
        if encoding_usado == 'utf-8':
            stats["ja_utf8"] += 1
            if not copiar_utf8:
                # Ignora (não copia)
                stats["ignorados"] += 1
                continue
            # Se copiar_utf8 for True, copia sem modificar
            try:
                with open(destino, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
            except Exception as e:
                stats["erros"] += 1
                escrever_log(f"❌ ERRO ao copiar {rel_path}: {e}")
                continue
        else:
            # Converte para utf-8
            try:
                with open(destino, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                stats["convertidos"] += 1
                stats["arquivos_convertidos"].append(rel_path)
                escrever_log(f"🔄 CONVERTIDO: {rel_path} (de {encoding_usado} para utf-8)")
            except Exception as e:
                stats["erros"] += 1
                escrever_log(f"❌ ERRO ao salvar {rel_path}: {e}")
                continue

        # Atualiza barra
        pbar.set_postfix({
            "conv": stats["convertidos"],
            "utf8": stats["ja_utf8"],
            "erros": stats["erros"]
        })

    pbar.close()
    fim = time.time()

    # ===== RELATÓRIO FINAL =====
    print("\n" + "="*70)
    print("📊 RELATÓRIO DE LIMPEZA")
    print("="*70)
    print(f"   Total de arquivos:     {stats['total']}")
    print(f"   ✅ Convertidos para UTF-8: {stats['convertidos']}")
    if copiar_utf8:
        print(f"   📂 Copiados (já UTF-8): {stats['ja_utf8']}")
    else:
        print(f"   ⏭️  Ignorados (já UTF-8): {stats['ignorados']}")
    print(f"   ❌ Erros:               {stats['erros']}")
    print(f"   ⏱️  Tempo total:         {fim - inicio:.2f}s")
    print("\n📋 Codificações encontradas:")
    for enc, count in sorted(stats["por_encoding"].items(), key=lambda x: -x[1]):
        print(f"   - {enc}: {count} arquivos")
    print("="*70)
    print(f"📂 Arquivos corrigidos salvos em: {pasta_saida}")
    if stats["convertidos"] > 0:
        print(f"📄 Log detalhado salvo em: {LOG_FILE}")
        print("   (contém a lista de arquivos convertidos)")
    else:
        print("   Nenhum arquivo precisou de conversão.")
    print("="*70)

    # Escreve resumo no log
    escrever_log("\n" + "="*70)
    escrever_log(f"📊 RESUMO FINAL")
    escrever_log(f"   Total: {stats['total']}")
    escrever_log(f"   Convertidos: {stats['convertidos']}")
    escrever_log(f"   Erros: {stats['erros']}")
    escrever_log(f"   Tempo: {fim - inicio:.2f}s")
    escrever_log("="*70)

    if stats["convertidos"] > 0:
        escrever_log("\n📄 ARQUIVOS CONVERTIDOS:")
        for arq in stats["arquivos_convertidos"]:
            escrever_log(f"   - {arq}")
        escrever_log("="*70)

    escrever_log(f"📅 FIM: {time.ctime()}")

# ============================================================================
# PARSER DE ARGUMENTOS
# ============================================================================

def main():
    # Declara LOG_FILE como global ANTES de usá-la
    global LOG_FILE

    parser = argparse.ArgumentParser(
        description="Corrige codificação de arquivos .txt, gerando cópias em utf-8."
    )
    parser.add_argument(
        "--entrada", "-i",
        default=PASTA_ENTRADA_PADRAO,
        help=f"Pasta raiz com os arquivos originais (padrão: {PASTA_ENTRADA_PADRAO})"
    )
    parser.add_argument(
        "--saida", "-o",
        default=PASTA_SAIDA_PADRAO,
        help=f"Pasta onde salvar os arquivos corrigidos (padrão: {PASTA_SAIDA_PADRAO})"
    )
    parser.add_argument(
        "--copiar-utf8", "-c",
        action="store_true",
        help="Copiar também arquivos que já estão em UTF-8 (padrão: ignorar)"
    )
    parser.add_argument(
        "--log", "-l",
        default=LOG_FILE,
        help=f"Arquivo de log (padrão: {LOG_FILE})"
    )
    args = parser.parse_args()

    # Atualiza o arquivo de log
    LOG_FILE = args.log

    entrada = os.path.abspath(args.entrada)
    saida = os.path.abspath(args.saida)

    if not os.path.isdir(entrada):
        print(f"❌ Pasta de entrada '{entrada}' não existe.")
        sys.exit(1)

    corrigir_codificacao(entrada, saida, args.copiar_utf8)

if __name__ == "__main__":
    main()