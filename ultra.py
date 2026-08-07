#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ultra.py – Extrai datasets do Hugging Face e salva diretamente em TXT.
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
Com retry automático para erros de rede.
"""

import os
import json
import time
import argparse
import warnings
from tqdm import tqdm
from datasets import load_dataset, config

# Desabilita avisos do Windows e do Hugging Face
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore", category=UserWarning, module="json")
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

config.HTTP_TIMEOUT = 1200.0             # 20 minutos de timeout (aumentado)
SHARD_SIZE = 50000
CHECKPOINT_INTERVAL = 1000
MAX_RETRIES = 5                          # Mais tentativas
RETRY_DELAY = 10                         # Espera mais tempo entre tentativas
AMOSTRAS_DIAGNOSTICO = 3
PASTA_SAIDA = "dados/ultratxt"

# ============================================================================
# DETECÇÃO DE ESTRUTURA (mesma de antes)
# ============================================================================

def extrair_lista_turnos(exemplo):
    chave = 'conversa'
    if chave not in exemplo:
        for k in ['conversations', 'chat', 'dialog', 'turns']:
            if k in exemplo:
                chave = k
                break
        else:
            return None, None

    valor = exemplo[chave]

    if isinstance(valor, list):
        if not valor or not isinstance(valor[0], dict):
            return valor, 'outro'
        keys = list(valor[0].keys())
        if 'humano' in keys and 'assistente' in keys:
            return valor, 'par_por_turno'
        elif 'role' in keys and 'content' in keys:
            return valor, 'turnos_alternados'
        elif 'from' in keys and 'value' in keys:
            return valor, 'turnos_alternados'
        else:
            return valor, 'par_por_turno'

    elif isinstance(valor, str):
        try:
            parsed = json.loads(valor.replace("'", '"'))
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                keys = list(parsed[0].keys())
                if 'humano' in keys and 'assistente' in keys:
                    return parsed, 'par_por_turno'
                elif 'role' in keys and 'content' in keys:
                    return parsed, 'turnos_alternados'
                else:
                    return parsed, 'par_por_turno'
        except (json.JSONDecodeError, TypeError):
            pass

    return None, None

def detectar_estrutura(dataset, num_amostras=3):
    print("\n🔍 Detectando estrutura...")
    estrutura = {
        "tipo_estrutura": None,
        "chave_conversa": 'conversa',
        "papeis_pergunta": [],
        "papeis_resposta": [],
    }

    for i, exemplo in enumerate(dataset):
        if i >= num_amostras:
            break
        print(f"\n   Exemplo {i+1}: chaves = {list(exemplo.keys())}")
        turnos, tipo = extrair_lista_turnos(exemplo)
        if turnos is None:
            print("   ⚠️ Não foi possível extrair turnos.")
            continue
        print(f"   Tipo detectado: {tipo}")
        estrutura["tipo_estrutura"] = tipo

        if tipo == "par_por_turno":
            if isinstance(turnos[0], dict):
                keys = list(turnos[0].keys())
                if 'humano' in keys and 'assistente' in keys:
                    estrutura["papeis_pergunta"] = ['humano']
                    estrutura["papeis_resposta"] = ['assistente']
                elif 'user' in keys and 'assistant' in keys:
                    estrutura["papeis_pergunta"] = ['user']
                    estrutura["papeis_resposta"] = ['assistant']
                else:
                    estrutura["papeis_pergunta"] = [keys[0]]
                    estrutura["papeis_resposta"] = [keys[1]]
                print(f"   ✅ Par por turno: pergunta={estrutura['papeis_pergunta']}, resposta={estrutura['papeis_resposta']}")
                return estrutura

        elif tipo == "turnos_alternados":
            if isinstance(turnos[0], dict):
                if 'role' in turnos[0]:
                    papel_key = 'role'
                    texto_key = 'content'
                elif 'from' in turnos[0]:
                    papel_key = 'from'
                    texto_key = 'value'
                else:
                    continue

                papeis = set()
                for t in turnos[:10]:
                    if papel_key in t:
                        papeis.add(t[papel_key].lower())
                print(f"   Papéis detectados: {papeis}")

                pergunta_papeis = [p for p in papeis if p in ['user', 'human', 'humano']]
                resposta_papeis = [p for p in papeis if p in ['assistant', 'assistente', 'gpt', 'ai']]
                if not pergunta_papeis:
                    pergunta_papeis = ['user']
                if not resposta_papeis:
                    resposta_papeis = ['assistant']

                estrutura["papeis_pergunta"] = pergunta_papeis
                estrutura["papeis_resposta"] = resposta_papeis
                estrutura["papel_key"] = papel_key
                estrutura["texto_key"] = texto_key
                print(f"   ✅ Turnos alternados: pergunta={pergunta_papeis}, resposta={resposta_papeis}")
                return estrutura

    print("   ❌ Nenhuma estrutura reconhecida. Usando fallback.")
    estrutura["tipo_estrutura"] = "fallback"
    return estrutura

# ============================================================================
# CHECKPOINT
# ============================================================================

def caminho_checkpoint(dataset_nome):
    nome_limpo = dataset_nome.replace("/", "_").replace("-", "_")
    return os.path.join(PASTA_SAIDA, f".checkpoint_{nome_limpo}.json")

def carregar_checkpoint(dataset_nome):
    ckpt = caminho_checkpoint(dataset_nome)
    if os.path.exists(ckpt):
        with open(ckpt, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("total_pares", 0), data.get("exemplo_index", 0)
    return 0, 0

def salvar_checkpoint(dataset_nome, total_pares, exemplo_index):
    ckpt = caminho_checkpoint(dataset_nome)
    os.makedirs(os.path.dirname(ckpt), exist_ok=True)
    with open(ckpt, 'w', encoding='utf-8') as f:
        json.dump({"total_pares": total_pares, "exemplo_index": exemplo_index}, f)

# ============================================================================
# EXTRAÇÃO COM RETRY AUTOMÁTICO
# ============================================================================

def extrair_para_txt(nome_dataset, arquivo_base, limite=None, shard_size=SHARD_SIZE, pasta_saida=PASTA_SAIDA):
    os.makedirs(pasta_saida, exist_ok=True)
    base_name = os.path.splitext(arquivo_base)[0]
    ext = ".txt"
    prefixo_global = nome_dataset.split("/")[-1].replace("-", "_")

    print(f"\n{'='*70}")
    print(f"📥 Processando: {nome_dataset} (com retry automático)")
    print(f"   Saída: {pasta_saida}/{base_name}_partXXXXX{ext}")
    print(f"   Tamanho do shard: {shard_size} pares")
    print(f"{'='*70}")

    # --- Carrega dataset com retry ---
    dataset = None
    for tentativa in range(MAX_RETRIES):
        try:
            print(f"🔄 Carregando dataset (tentativa {tentativa+1}/{MAX_RETRIES})...")
            dataset = load_dataset(nome_dataset, split="train", streaming=True)
            # Testa a conexão pegando o primeiro exemplo
            for _ in dataset.take(1):
                pass
            print("✅ Dataset carregado com sucesso.")
            break
        except Exception as e:
            print(f"❌ Erro ao carregar dataset: {e}")
            if tentativa == MAX_RETRIES - 1:
                return 0
            print(f"⏳ Aguardando {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

    if dataset is None:
        return 0

    # --- Detecta estrutura ---
    estrutura = detectar_estrutura(dataset, AMOSTRAS_DIAGNOSTICO)
    print(f"\n📋 Estrutura: {estrutura}")
    tipo = estrutura.get("tipo_estrutura")
    if tipo is None:
        print("❌ Estrutura não detectada. Abortando.")
        return 0

    # --- Recupera checkpoint ---
    total_pares, exemplo_index = carregar_checkpoint(nome_dataset)
    print(f"🔄 Checkpoint: {total_pares} pares já salvos, retomando do exemplo {exemplo_index}.")

    # --- Prepara arquivo ---
    part_num = total_pares // shard_size
    contador_shard = total_pares % shard_size
    caminho_shard = os.path.join(pasta_saida, f"{base_name}_part{part_num:05d}{ext}")
    modo = 'a' if os.path.exists(caminho_shard) else 'w'
    f_out = open(caminho_shard, modo, encoding='utf-8')
    if modo == 'a':
        print(f"📄 Continuando shard: {caminho_shard}")
    else:
        print(f"📄 Novo shard: {caminho_shard}")

    contador_total = total_pares
    exemplo_atual = 0
    erro_ocorrido = False

    # --- Loop com retry automático ---
    tentativas_extra = 0
    while True:
        try:
            pbar = tqdm(desc=f"Extraindo {prefixo_global}", unit="pares", initial=contador_total)

            for exemplo in dataset:
                if limite and contador_total >= limite:
                    break
                exemplo_atual += 1
                if exemplo_atual <= exemplo_index:
                    continue

                turnos, _ = extrair_lista_turnos(exemplo)
                if not turnos:
                    continue

                if tipo == "par_por_turno":
                    for turno in turnos:
                        if not isinstance(turno, dict):
                            continue
                        pergunta = None
                        resposta = None
                        for chave_pergunta in estrutura["papeis_pergunta"]:
                            if chave_pergunta in turno:
                                pergunta = turno[chave_pergunta].strip()
                                break
                        for chave_resposta in estrutura["papeis_resposta"]:
                            if chave_resposta in turno:
                                resposta = turno[chave_resposta].strip()
                                break
                        if pergunta and resposta:
                            f_out.write(f"Pergunta: {pergunta}\nResposta: {resposta}\n\n")
                            contador_total += 1
                            contador_shard += 1
                            pbar.update(1)

                            if contador_shard >= shard_size:
                                f_out.close()
                                part_num += 1
                                contador_shard = 0
                                caminho_shard = os.path.join(pasta_saida, f"{base_name}_part{part_num:05d}{ext}")
                                f_out = open(caminho_shard, 'w', encoding='utf-8')
                                print(f"📄 Novo shard: {caminho_shard}")

                            if contador_total % CHECKPOINT_INTERVAL == 0:
                                salvar_checkpoint(nome_dataset, contador_total, exemplo_atual)

                elif tipo == "turnos_alternados":
                    papel_key = estrutura.get("papel_key", "role")
                    texto_key = estrutura.get("texto_key", "content")
                    papeis_pergunta = estrutura["papeis_pergunta"]
                    papeis_resposta = estrutura["papeis_resposta"]

                    pergunta = None
                    for turno in turnos:
                        if not isinstance(turno, dict):
                            continue
                        papel = turno.get(papel_key, '').lower()
                        texto = turno.get(texto_key, '').strip()
                        if not texto:
                            continue
                        if papel in papeis_pergunta:
                            pergunta = texto
                        elif papel in papeis_resposta and pergunta:
                            resposta = texto
                            if pergunta and resposta:
                                f_out.write(f"Pergunta: {pergunta}\nResposta: {resposta}\n\n")
                                contador_total += 1
                                contador_shard += 1
                                pbar.update(1)

                                if contador_shard >= shard_size:
                                    f_out.close()
                                    part_num += 1
                                    contador_shard = 0
                                    caminho_shard = os.path.join(pasta_saida, f"{base_name}_part{part_num:05d}{ext}")
                                    f_out = open(caminho_shard, 'w', encoding='utf-8')
                                    print(f"📄 Novo shard: {caminho_shard}")

                                if contador_total % CHECKPOINT_INTERVAL == 0:
                                    salvar_checkpoint(nome_dataset, contador_total, exemplo_atual)
                            pergunta = None

                else:  # fallback
                    texto_completo = ""
                    for turno in turnos:
                        if isinstance(turno, dict):
                            for v in turno.values():
                                if isinstance(v, str):
                                    texto_completo += v + " "
                        elif isinstance(turno, str):
                            texto_completo += turno + " "
                    if '?' in texto_completo:
                        partes = texto_completo.split('?', 1)
                        if len(partes) == 2:
                            pergunta = partes[0].strip() + '?'
                            resposta = partes[1].strip()
                            if pergunta and resposta:
                                f_out.write(f"Pergunta: {pergunta}\nResposta: {resposta}\n\n")
                                contador_total += 1
                                contador_shard += 1
                                pbar.update(1)

                                if contador_shard >= shard_size:
                                    f_out.close()
                                    part_num += 1
                                    contador_shard = 0
                                    caminho_shard = os.path.join(pasta_saida, f"{base_name}_part{part_num:05d}{ext}")
                                    f_out = open(caminho_shard, 'w', encoding='utf-8')
                                    print(f"📄 Novo shard: {caminho_shard}")

                                if contador_total % CHECKPOINT_INTERVAL == 0:
                                    salvar_checkpoint(nome_dataset, contador_total, exemplo_atual)

            pbar.close()
            salvar_checkpoint(nome_dataset, contador_total, exemplo_atual)
            break  # Sai do while se terminou sem erros

        except Exception as e:
            print(f"\n⚠️ Erro de rede/processamento: {e}")
            if f_out and not f_out.closed:
                f_out.close()
            tentativas_extra += 1
            if tentativas_extra > MAX_RETRIES:
                print("❌ Número máximo de tentativas excedido. Abortando.")
                erro_ocorrido = True
                break
            print(f"🔄 Salvando checkpoint e reiniciando iterador (tentativa {tentativas_extra}/{MAX_RETRIES})...")
            salvar_checkpoint(nome_dataset, contador_total, exemplo_atual)
            print(f"⏳ Aguardando {RETRY_DELAY}s antes de recarregar...")
            time.sleep(RETRY_DELAY)

            # Recarrega o dataset a partir do checkpoint
            for tentativa in range(MAX_RETRIES):
                try:
                    print(f"🔄 Recarregando dataset (tentativa {tentativa+1}/{MAX_RETRIES})...")
                    dataset = load_dataset(nome_dataset, split="train", streaming=True)
                    # Avança até o último exemplo processado
                    # Nota: isso depende do iterador; vamos apenas reiniciar e pular os já processados
                    # Mas como temos exemplo_index, o loop vai pular os já salvos.
                    break
                except Exception as e2:
                    print(f"❌ Erro ao recarregar: {e2}")
                    if tentativa == MAX_RETRIES - 1:
                        raise
                    time.sleep(RETRY_DELAY)

    # Fecha o arquivo se ainda estiver aberto
    if f_out and not f_out.closed:
        f_out.close()

    if not erro_ocorrido:
        print(f"\n✅ {prefixo_global}: {contador_total} pares salvos em {part_num+1} shard(s)")
    return contador_total

# ============================================================================
# MAIN
# ============================================================================

def main():
    global SHARD_SIZE, CHECKPOINT_INTERVAL, PASTA_SAIDA

    parser = argparse.ArgumentParser()
    parser.add_argument("--limite", type=int, default=None)
    parser.add_argument("--shard-size", type=int, default=SHARD_SIZE)
    parser.add_argument("--checkpoint-interval", type=int, default=CHECKPOINT_INTERVAL)
    parser.add_argument("--pasta-saida", type=str, default=PASTA_SAIDA)

    args = parser.parse_args()
    SHARD_SIZE = args.shard_size
    CHECKPOINT_INTERVAL = args.checkpoint_interval
    PASTA_SAIDA = args.pasta_saida

    datasets = [
        ("recogna-nlp/UltrachatBR", "ultrachat_bruto_raw"),
        ("CEIA-POSITIVO/ultrachat_br_clustred_balanced_v1", "ultrachat_ceia_raw"),
        ("Fazzioni/ultrachat_br_clustred_balanced_thinking", "ultrachat_fazzioni_raw"),
    ]

    total_geral = 0
    for nome, base in datasets:
        total = extrair_para_txt(nome, base, limite=args.limite, pasta_saida=PASTA_SAIDA)
        total_geral += total

    print("\n" + "=" * 70)
    print("📊 EXTRAÇÃO CONCLUÍDA")
    print("=" * 70)
    print(f"   Total de pares salvos: {total_geral}")
    print(f"   📂 Pasta: {PASTA_SAIDA}/")

if __name__ == "__main__":
    main()