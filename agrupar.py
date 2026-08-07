#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
agrupar.py - AGRUPADOR INTELIGENTE COM MOVIMENTAÇÃO E BACKUP
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
====================================================================
Uso:
    python agrupar.py --entrada dados/processed --saida dados/processed_lotes --backup D:/backup/rigelllm/processed --pares 500

Características:
    - Varre recursivamente todas as subpastas.
    - Lê arquivos .txt no formato Pergunta/Resposta.
    - Agrupa em lotes de N pares.
    - Move os originais para backup (liberando espaço).
    - Verboso: mostra cada ação.
    - Checkpoint automático para retomada.
    - Relatório final com contagens e comandos sugeridos.
"""

import os
import sys
import glob
import time
import json
import shutil
import argparse
from tqdm import tqdm
from pathlib import Path

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================
CHECKPOINT_FILE = "agrupar_checkpoint.json"
LOTE_PREFIXO = "lote"
VERBOSE = True  # sempre verdadeiro

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def log(msg, nivel="INFO"):
    """Exibe mensagem com timestamp e nível."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [{nivel}] {msg}")

def carregar_checkpoint():
    """Carrega o checkpoint (lista de arquivos já processados).
    Se o JSON estiver corrompido, faz backup e recria vazio."""
    if not os.path.exists(CHECKPOINT_FILE):
        return set()
    try:
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            dados = json.load(f)
            if not isinstance(dados, list):
                raise ValueError("Formato inválido")
            return set(dados)
    except (json.JSONDecodeError, ValueError, Exception) as e:
        log(f"⚠️ Checkpoint corrompido ({e}). Criando backup...", "WARN")
        backup = CHECKPOINT_FILE + ".bak." + time.strftime("%Y%m%d_%H%M%S")
        try:
            os.rename(CHECKPOINT_FILE, backup)
            log(f"   ✅ Backup salvo: {backup}", "WARN")
        except:
            log(f"   ❌ Não foi possível salvar backup", "ERRO")
        # Pergunta ao usuário se deseja recriar ou ignorar
        try:
            resp = input(f"   Checkpoint corrompido. Recriar vazio? (S/n): ").strip().lower()
            if resp in ('n', 'nao', 'não'):
                log("   ⏸️  Usuário optou por não recriar. Retornando vazio.", "INFO")
                return set()
        except:
            pass
        log("   ✅ Checkpoint recriado (vazio).", "INFO")
        return set()

def salvar_checkpoint(processados):
    """Salva o checkpoint."""
    try:
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(processados), f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"❌ Erro ao salvar checkpoint: {e}", "ERRO")

def extrair_pares(conteudo):
    """
    Extrai pares Pergunta/Resposta de um arquivo.
    Retorna uma lista de strings, cada uma com o par formatado.
    Se o arquivo já estiver no formato P/R, retorna o conteúdo inteiro.
    Se houver múltiplos pares no mesmo arquivo (separados por \n\n), retorna cada um.
    """
    if not conteudo:
        return []
    # Divide por \n\n para separar blocos
    blocos = conteudo.strip().split('\n\n')
    pares = []
    for bloco in blocos:
        bloco = bloco.strip()
        if not bloco:
            continue
        if "Pergunta:" in bloco and "Resposta:" in bloco:
            pares.append(bloco)
        else:
            # Tenta detectar se é um único bloco com P/R
            # Pode ser que o arquivo seja apenas um par sem separador
            if "Pergunta:" in bloco and "Resposta:" in bloco:
                pares.append(bloco)
            else:
                # Se não tiver marcadores, tenta extrair com regex? Para simplificar, ignoramos.
                log(f"⚠️ Arquivo sem formato P/R: {bloco[:50]}...", "AVISO")
                continue
    return pares

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Agrupa arquivos .txt em lotes, movendo os originais para backup."
    )
    parser.add_argument("--entrada", "-i", required=True,
                        help="Pasta raiz com os arquivos individuais (ex: dados/processed)")
    parser.add_argument("--saida", "-o", required=True,
                        help="Pasta onde salvar os lotes agrupados (ex: dados/processed_lotes)")
    parser.add_argument("--backup", "-b", default=None,
                        help="Pasta onde mover os arquivos originais após processamento (ex: D:/backup/processed). Se não informado, mantém os originais.")
    parser.add_argument("--pares", "-p", type=int, default=500,
                        help="Número de pares por lote (padrão: 500)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Apenas simula, não move nem escreve nada")
    parser.add_argument("--no-move", action="store_true",
                        help="Não move os originais (apenas agrupa, mantém originais)")
    args = parser.parse_args()

    entrada = os.path.abspath(args.entrada)
    saida = os.path.abspath(args.saida)
    backup = os.path.abspath(args.backup) if args.backup else None
    pares_por_lote = args.pares
    dry_run = args.dry_run
    no_move = args.no_move

    # Se backup não informado e no_move não ativo, avisar
    if not backup and not no_move:
        log("⚠️ --backup não informado e --no-move não ativado. Os originais serão mantidos (não movidos).", "AVISO")
        no_move = True

    log("=" * 70)
    log("🚀 INICIANDO AGRUPADOR INTELIGENTE v1.0.0")
    log(f"📂 Entrada: {entrada}")
    log(f"📁 Saída:   {saida}")
    log(f"🗂️ Backup:  {backup if backup else '(não usado)'}")
    log(f"📦 Pares por lote: {pares_por_lote}")
    log(f"🔍 Modo dry-run: {'SIM' if dry_run else 'NÃO'}")
    log(f"🔁 Manter originais: {'SIM' if no_move else 'NÃO (serão movidos para backup)'}")
    log("=" * 70)

    if dry_run:
        log("🔍 MODO DRY-RUN: nenhuma alteração será feita.", "AVISO")
        input("Pressione Enter para continuar a simulação...")

    # Cria pastas necessárias
    if not dry_run:
        log(f"📁 Criando pasta de saída: {saida}")
        os.makedirs(saida, exist_ok=True)
        if backup:
            log(f"📁 Criando pasta de backup: {backup}")
            os.makedirs(backup, exist_ok=True)

    # Lista todos os arquivos .txt recursivamente
    log("📂 Listando arquivos .txt em subpastas...")
    arquivos = glob.glob(os.path.join(entrada, "**", "*.txt"), recursive=True)
    if not arquivos:
        log("❌ Nenhum arquivo .txt encontrado.")
        return

    log(f"📄 Total de arquivos encontrados: {len(arquivos)}")

    # Carrega checkpoint
    processados = carregar_checkpoint()
    arquivos_restantes = [a for a in arquivos if a not in processados]
    log(f"📌 Arquivos já processados (checkpoint): {len(processados)}")
    log(f"📌 Arquivos a processar: {len(arquivos_restantes)}")

    if not arquivos_restantes:
        log("✅ Todos os arquivos já foram processados.")
        return

    # Buffer para acumular pares
    buffer_pares = []
    lote_id = 0
    total_pares = 0
    arquivos_movidos = 0
    pastas_criadas = set()

    log(f"\n🚀 Iniciando agrupamento (lotes de {pares_por_lote} pares)...")
    inicio = time.time()

    # Cria uma barra de progresso com informações detalhadas
    pbar = tqdm(arquivos_restantes, desc="Processando", unit="arquivo")

    for caminho in pbar:
        # Exibe o caminho atual
        pbar.set_postfix({"arquivo": os.path.basename(caminho)})

        # Lê o arquivo
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                conteudo = f.read()
        except Exception as e:
            log(f"⚠️ Erro ao ler {caminho}: {e}", "ERRO")
            # Marca como processado para não tentar novamente
            processados.add(caminho)
            salvar_checkpoint(processados)
            continue

        # Extrai pares
        pares = extrair_pares(conteudo)
        if not pares:
            log(f"⚠️ Ignorando {caminho}: sem formato Pergunta/Resposta", "AVISO")
            # Move para backup mesmo assim (pode ser lixo)
            if not dry_run and not no_move and backup:
                try:
                    rel_path = os.path.relpath(caminho, entrada)
                    destino = os.path.join(backup, rel_path)
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    shutil.move(caminho, destino)
                    arquivos_movidos += 1
                    log(f"   🗂️ Movido (ignorado) para backup: {rel_path}")
                except Exception as e:
                    log(f"⚠️ Erro ao mover {caminho}: {e}", "ERRO")
            processados.add(caminho)
            salvar_checkpoint(processados)
            continue

        # Acumula pares
        for par in pares:
            buffer_pares.append(par)
            total_pares += 1

            # Se atingiu o limite, escreve o lote
            if len(buffer_pares) >= pares_por_lote:
                nome_lote = f"{LOTE_PREFIXO}_{lote_id:06d}.txt"
                caminho_lote = os.path.join(saida, nome_lote)
                if not dry_run:
                    with open(caminho_lote, 'w', encoding='utf-8') as f:
                        f.write("\n\n".join(buffer_pares))
                    log(f"   💾 Lote {lote_id+1} salvo: {caminho_lote} ({len(buffer_pares)} pares)")
                else:
                    log(f"   🔍 DRY-RUN: salvaria lote {lote_id+1} com {len(buffer_pares)} pares")
                buffer_pares = []
                lote_id += 1
                pbar.set_postfix({"lotes": lote_id, "pares": total_pares})

        # Após processar o arquivo, move-o para backup (se não for dry-run e não no_move)
        if not dry_run and not no_move and backup:
            try:
                rel_path = os.path.relpath(caminho, entrada)
                destino = os.path.join(backup, rel_path)
                # Cria a estrutura de pastas no backup
                os.makedirs(os.path.dirname(destino), exist_ok=True)
                shutil.move(caminho, destino)
                arquivos_movidos += 1
                # Log a cada 50 arquivos para não poluir
                if arquivos_movidos % 50 == 0:
                    log(f"   🗂️ {arquivos_movidos} arquivos movidos para backup")
            except Exception as e:
                log(f"⚠️ Erro ao mover {caminho} para backup: {e}", "ERRO")

        # Marca como processado
        processados.add(caminho)
        # Salva checkpoint a cada 100 arquivos
        if len(processados) % 100 == 0:
            salvar_checkpoint(processados)
            log(f"   📝 Checkpoint salvo: {len(processados)} arquivos processados")

    # Escreve o último lote se houver pares sobrando
    if buffer_pares:
        nome_lote = f"{LOTE_PREFIXO}_{lote_id:06d}.txt"
        caminho_lote = os.path.join(saida, nome_lote)
        if not dry_run:
            with open(caminho_lote, 'w', encoding='utf-8') as f:
                f.write("\n\n".join(buffer_pares))
            log(f"   💾 Último lote salvo: {caminho_lote} ({len(buffer_pares)} pares)")
        else:
            log(f"   🔍 DRY-RUN: salvaria último lote com {len(buffer_pares)} pares")
        lote_id += 1

    # Salva checkpoint final
    salvar_checkpoint(processados)
    log(f"📝 Checkpoint final salvo.")

    fim = time.time()
    tempo = fim - inicio

    # ===== RELATÓRIO FINAL =====
    # Contagem de arquivos na pasta de saída
    arquivos_saida = glob.glob(os.path.join(saida, "*.txt"))
    tamanho_saida = sum(os.path.getsize(f) for f in arquivos_saida) / (1024**2)  # MB

    # Contagem original (se ainda existir)
    arquivos_restantes_contagem = len(glob.glob(os.path.join(entrada, "**", "*.txt"), recursive=True))

    print("\n" + "=" * 70)
    print("📊 RELATÓRIO FINAL")
    print("=" * 70)
    print(f"   ✅ Arquivos processados: {len(processados)}")
    print(f"   📦 Lotes gerados: {lote_id}")
    print(f"   📝 Total de pares: {total_pares}")
    print(f"   🗂️  Arquivos movidos para backup: {arquivos_movidos}")
    print(f"   ⏱️  Tempo total: {tempo:.2f}s")
    print(f"\n📂 Pasta de saída: {saida}")
    print(f"   - Arquivos na saída: {len(arquivos_saida)}")
    print(f"   - Tamanho total: {tamanho_saida:.2f} MB")
    if not no_move and backup:
        print(f"\n🗂️  Backup em: {backup}")
        print(f"   - Arquivos movidos: {arquivos_movidos}")
    if arquivos_restantes_contagem > 0:
        print(f"\n⚠️  Atenção: ainda existem {arquivos_restantes_contagem} arquivos .txt em {entrada}.")
        print("   Eles podem ser de outras subpastas não processadas ou novos arquivos.")
    print("=" * 70)

    # ===== SUGESTÃO DE COMANDOS =====
    print("\n💡 COMANDOS PARA O COLAB (copie e cole):")
    print("-" * 70)
    print(f"# Monte o Drive e entre na pasta do projeto")
    print(f"from google.colab import drive")
    print(f"drive.mount('/content/drive')")
    print(f"!cd /content/drive/MyDrive/rigelllm")
    print()
    print(f"# Comando para treinar com os lotes (substitua 'processed_lotes' pelo nome da sua pasta de saída)")
    print(f"!cd /content/drive/MyDrive/rigelllm && python treino.py --dados {os.path.basename(saida)} --resume --save-every 50")
    print()
    print(f"# Se quiser treinar com um número limitado de arquivos (para testes):")
    print(f"!cd /content/drive/MyDrive/rigelllm && python treino.py --dados {os.path.basename(saida)} --max-arquivos 20000 --resume --save-every 50")
    print("-" * 70)
    print("\n✅ Pronto! Agora você pode rodar o treino no Colab sem timeout.")

if __name__ == "__main__":
    main()