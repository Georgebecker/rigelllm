#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
tradutor.py - Filtra e traduz datasets JSON (Alpaca, Dolly, etc.) para pt-BR.
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
Agora com:
- Controle de repetição (estado persistente)
- Padronização de saída (Pergunta/Resposta)
- Cálculo de custos baseado em preços reais da DeepSeek
- Uso do tokenizer local para contagem precisa de tokens

Uso:
    python tradutor.py --arquivo alpaca.json --custo_max 1.00 --delay 2.0

Os arquivos de saída serão:
    - dados/gerados/curtos/curto_*.txt
    - dados/gerados/medios/medio_*.txt
    - dados/gerados/longos/longo_*.txt
"""

import os
import sys
import json
import time
import re
import hashlib
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

# ============================================================================
# 0. CONFIGURAÇÃO
# ============================================================================

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-chat")  # ou deepseek-v4-flash
MAX_TOKENS_TRADUCAO = 500
TEMPERATURE = 0.3
PALAVRAS_POR_TOKEN = 1.3  # fallback se o tokenizer não estiver disponível

# ============================================================================
# 1. PASTAS E ARQUIVOS DE ESTADO
# ============================================================================

PASTA_CURTOS = "dados/gerados/curtos"
PASTA_MEDIOS = "dados/gerados/medios"
PASTA_LONGOS = "dados/gerados/longos"
PASTA_ESTADO = "dados/estado"
ARQUIVO_ESTADO = os.path.join(PASTA_ESTADO, "estado_traducao.json")
NOME_JSON_SAIDA = "datasetfinal.json"

for pasta in [PASTA_CURTOS, PASTA_MEDIOS, PASTA_LONGOS, PASTA_ESTADO]:
    os.makedirs(pasta, exist_ok=True)

if not API_KEY:
    print("❌ ERRO: DEEPSEEK_API_KEY não encontrada no arquivo .env")
    sys.exit(1)

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# ============================================================================
# 2. CARREGAR TOKENIZER LOCAL (para contagem precisa)
# ============================================================================

TOKENIZER_PATH = "tokenizer/"  # onde estão seus arquivos tokenizer.json e tokenizer_config.json
try:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, trust_remote_code=True)
    print("✅ Tokenizer local carregado para contagem de tokens.")
    TOKENIZER_DISPONIVEL = True
except Exception as e:
    print(f"⚠️ Não foi possível carregar o tokenizer local: {e}")
    print("   Usando estimativa por palavras (menos precisa).")
    TOKENIZER_DISPONIVEL = False

# ============================================================================
# 3. PREÇOS DA DEEPSEEK (atualizados)
# ============================================================================

PRECOS = {
    "deepseek-chat": {"in": 0.14, "out": 0.28},       # por 1M tokens
    "deepseek-v4-flash": {"in": 0.07, "out": 0.14},   # por 1M tokens
    "deepseek-reasoner": {"in": 0.55, "out": 2.19},   # R1
}
# Define o modelo usado e seu preço
MODELO_USADO = MODEL_NAME
if MODELO_USADO not in PRECOS:
    MODELO_USADO = "deepseek-chat"  # fallback
PRECO_IN = PRECOS[MODELO_USADO]["in"]
PRECO_OUT = PRECOS[MODELO_USADO]["out"]

# ============================================================================
# 4. FUNÇÕES AUXILIARES
# ============================================================================

def contar_tokens(texto):
    """Conta tokens usando o tokenizer local, ou estimativa por palavras."""
    if not texto:
        return 0
    if TOKENIZER_DISPONIVEL:
        return len(tokenizer.encode(texto))
    else:
        return int(len(texto.split()) * PALAVRAS_POR_TOKEN)

def estimar_custo(texto_entrada, texto_saida=None):
    """
    Estima o custo em dólares para uma requisição.
    Se texto_saida for None, estima apenas entrada (para simulação).
    """
    tokens_in = contar_tokens(texto_entrada)
    if texto_saida:
        tokens_out = contar_tokens(texto_saida)
    else:
        # Estimativa conservadora: saída ~30% da entrada
        tokens_out = int(tokens_in * 0.3)
    custo_in = (tokens_in / 1_000_000) * PRECO_IN
    custo_out = (tokens_out / 1_000_000) * PRECO_OUT
    return round(custo_in + custo_out, 8)

def hash_texto(texto):
    """Gera um hash SHA256 do texto."""
    return hashlib.sha256(texto.encode('utf-8')).hexdigest()

def carregar_estado():
    """Carrega o estado de traduções já realizadas."""
    if os.path.exists(ARQUIVO_ESTADO):
        with open(ARQUIVO_ESTADO, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"processados": [], "custo_total": 0.0}

def salvar_estado(estado):
    """Salva o estado atual."""
    with open(ARQUIVO_ESTADO, 'w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)

def classificar_por_tokens(tokens):
    """Classifica o texto em curto, medio ou longo baseado no número de tokens."""
    if tokens <= 128:
        return "curto", PASTA_CURTOS, "curto"
    elif tokens <= 256:
        return "medio", PASTA_MEDIOS, "medio"
    else:
        return "longo", PASTA_LONGOS, "longo"

def traduzir_texto(texto, max_tokens=MAX_TOKENS_TRADUCAO, tentativas=5):
    """Traduz do inglês para português. Em caso de erro, retorna o original."""
    if not texto or len(texto.strip()) < 1:
        return ""

    prompt = f"""Traduza o seguinte texto do inglês para o português brasileiro.
Mantenha o tom e o estilo original.
Traduza APENAS o texto, sem adicionar comentários ou explicações.

Texto: {texto}

Tradução:"""

    for tentativa in range(tentativas):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMPERATURE,
                max_tokens=max_tokens,
                top_p=0.9
            )
            traducao = response.choices[0].message.content.strip()
            traducao = traducao.strip('"')
            if traducao:
                return traducao
            else:
                # Se veio vazio, tenta novamente
                time.sleep(1)
        except Exception as e:
            print(f"   ⚠️ Erro na tradução (tentativa {tentativa+1}/{tentativas}): {e}")
            if tentativa < tentativas - 1:
                time.sleep(2)
            else:
                return texto  # fallback: mantém original

    return texto

def salvar_item_como_txt(pergunta, resposta, pasta, prefixo):
    """
    Salva pergunta + resposta como um arquivo .txt com nome prefixo_DDMMAAAAHHMM.txt
    """
    if not resposta or len(resposta.strip()) < 1:
        return None

    agora = datetime.now().strftime("%d%m%Y%H%M")
    nome = f"{prefixo}_{agora}.txt"
    caminho = os.path.join(pasta, nome)

    contador = 1
    while os.path.exists(caminho):
        nome = f"{prefixo}_{agora}_{contador:02d}.txt"
        caminho = os.path.join(pasta, nome)
        contador += 1

    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(f"Pergunta: {pergunta}\n")
        f.write(f"Resposta: {resposta}\n")
    return caminho

# ============================================================================
# 5. FUNÇÃO PRINCIPAL
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Traduz dataset JSON (Alpaca) para pt-BR, classificando respostas.",
        epilog="EXEMPLO: python tradutor.py --arquivo alpaca.json --limite 100 --delay 2.0"
    )
    parser.add_argument("--arquivo", type=str, required=True, help="Caminho do arquivo JSON (ex: alpaca.json)")
    parser.add_argument("--custo_max", type=float, default=2.0, help="Limite de gastos em USD (padrão: 2.00)")
    parser.add_argument("--limite", type=int, default=None, help="Número máximo de exemplos (use 100 para testar)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Delay entre requisições (padrão: 1.5s)")
    parser.add_argument("--reset", action="store_true", help="Ignora o estado anterior e processa todos os itens novamente")

    args = parser.parse_args()
    DELAY_SECONDS = args.delay

    # ===== EXIBE CONFIGURAÇÃO =====
    print("\n" + "=" * 70)
    print("📚 TRADUTOR DE DATASETS (ALPACA) - 3 NÍVEIS COM CONTROLE")
    print("=" * 70)
    print(f"   📂 Arquivo: {args.arquivo}")
    print(f"   💰 Limite de custo: ${args.custo_max:.2f}")
    print(f"   🔢 Limite de itens: {args.limite if args.limite else 'Ilimitado (CUIDADO!)'}")
    print(f"   ⏱️  Delay: {DELAY_SECONDS}s")
    print(f"   📁 Curtos (≤128 tokens): {PASTA_CURTOS}")
    print(f"   📁 Médios (129-256): {PASTA_MEDIOS}")
    print(f"   📁 Longos (>256): {PASTA_LONGOS}")
    print(f"   💲 Preço do modelo {MODELO_USADO}: Entrada ${PRECO_IN}/1M, Saída ${PRECO_OUT}/1M")
    print("=" * 70 + "\n")

    # ===== LEITURA DO JSON =====
    try:
        with open(args.arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
    except Exception as e:
        print(f"❌ Erro ao ler {args.arquivo}: {e}")
        sys.exit(1)

    if isinstance(dados, dict) and "data" in dados:
        dados = dados["data"]

    if not isinstance(dados, list):
        print("❌ Formato inesperado: esperava uma lista.")
        sys.exit(1)

    print(f"📄 Total de itens: {len(dados)}")

    # ===== FILTRAGEM INICIAL =====
    print("\n🔍 Filtrando exemplos com output não vazio...")
    itens_filtrados = []
    for item in dados:
        output = item.get("output", "").strip()
        if output:
            itens_filtrados.append(item)

    print(f"   ✅ {len(itens_filtrados)} exemplos válidos (com resposta).")

    if not itens_filtrados:
        print("❌ Nenhum exemplo válido.")
        sys.exit(0)

    if args.limite and args.limite < len(itens_filtrados):
        itens_filtrados = itens_filtrados[:args.limite]
        print(f"   🔢 Limitado a {len(itens_filtrados)} exemplos para teste.")

    # ===== CARREGA ESTADO =====
    estado = carregar_estado()
    if args.reset:
        estado = {"processados": [], "custo_total": 0.0}
        print("🔄 Estado reiniciado (--reset).")

    # ===== SIMULAÇÃO DE CUSTO (ANTES DE COMEÇAR) =====
    print("\n📊 Estimativa de custos para os itens NÃO traduzidos:")
    itens_restantes = []
    custo_estimado_total = 0.0
    for item in itens_filtrados:
        instruction = item.get("instruction", "")
        input_text = item.get("input", "")
        output = item.get("output", "")
        texto_original = f"{instruction} {input_text} {output}"
        h = hash_texto(texto_original)
        if h in estado["processados"]:
            continue  # já traduzido
        itens_restantes.append(item)
        # Estima custo: entrada = instruction+input+output, saída = ~30%
        custo_estimado = estimar_custo(texto_original, None)
        custo_estimado_total += custo_estimado

    print(f"   Itens a traduzir: {len(itens_restantes)}")
    print(f"   Custo estimado total: ${custo_estimado_total:.4f}")
    print(f"   Custo já gasto: ${estado['custo_total']:.4f}")
    print(f"   Limite de gasto: ${args.custo_max:.2f}")

    if custo_estimado_total + estado['custo_total'] > args.custo_max:
        print(f"\n⚠️ ATENÇÃO: Custo estimado ({custo_estimado_total:.4f}) + gasto anterior ({estado['custo_total']:.4f}) excede o limite de ${args.custo_max:.2f}.")
        print("   Considere aumentar o limite ou usar --limite para processar menos itens.")
        resposta = input("   Continuar mesmo assim? (s/N): ").strip().lower()
        if resposta != 's':
            print("❌ Operação cancelada.")
            return

    if not itens_restantes:
        print("✅ Todos os itens já foram traduzidos.")
        return

    print("\n🚀 Iniciando tradução...")
    itens_traduzidos = []
    custo_real = estado['custo_total']
    contagem = {"curto": 0, "medio": 0, "longo": 0}
    inicio = time.time()
    descartados = 0
    max_tokens_ajustado = MAX_TOKENS_TRADUCAO

    with tqdm(total=len(itens_restantes), desc="Traduzindo", unit="item") as pbar:
        for i, item in enumerate(itens_restantes):
            if custo_real >= args.custo_max:
                print(f"\n⏹️ Limite de gastos atingido (${args.custo_max:.2f}). Parando.")
                break

            instruction = item.get("instruction", "").strip()
            input_text = item.get("input", "").strip()
            output = item.get("output", "").strip()

            # ============================================================
            # COMBINA PERGUNTA: instruction + input (se existir)
            # ============================================================
            if input_text:
                pergunta_original = f"{instruction} {input_text}"
            else:
                pergunta_original = instruction

            if not pergunta_original:
                pergunta_original = "Pergunta sem texto"

            # Hash para verificar se já foi traduzido
            texto_original = f"{pergunta_original} {output}"
            h = hash_texto(texto_original)
            if h in estado["processados"]:
                pbar.update(1)
                continue

            # Traduz pergunta e resposta separadamente
            pergunta_pt = traduzir_texto(pergunta_original, max_tokens=max_tokens_ajustado)
            resposta_pt = traduzir_texto(output, max_tokens=max_tokens_ajustado)

            # ============================================================
            # SÓ DESCARTA SE A RESPOSTA FICAR COMPLETAMENTE VAZIA
            # ============================================================
            if not resposta_pt or len(resposta_pt.strip()) < 1:
                descartados += 1
                pbar.update(1)
                continue

            # Se a pergunta traduzida veio vazia, usa a original (mas já tentamos)
            if not pergunta_pt:
                pergunta_pt = pergunta_original

            # ============================================================
            # ATUALIZA ESTADO E SALVA
            # ============================================================
            estado["processados"].append(h)
            # Custo real: estimamos com base no tamanho da entrada e saída
            custo_item = estimar_custo(texto_original, resposta_pt)
            custo_real += custo_item

            # Classifica pelo tamanho da RESPOSTA
            tokens_resposta = contar_tokens(resposta_pt)
            categoria, pasta, prefixo = classificar_por_tokens(tokens_resposta)
            contagem[categoria] += 1

            salvar_item_como_txt(pergunta_pt, resposta_pt, pasta, prefixo)

            # Atualiza barra
            pbar.set_postfix({
                "custo": f"${custo_real:.4f}",
                "curto": contagem["curto"],
                "medio": contagem["medio"],
                "longo": contagem["longo"],
                "desc": descartados
            })
            pbar.update(1)

            # Salva estado periodicamente
            if pbar.n % 5 == 0:
                salvar_estado(estado)

            time.sleep(DELAY_SECONDS)

    fim = time.time()
    tempo_total = fim - inicio

    # ===== SALVA ESTADO FINAL =====
    salvar_estado(estado)

    # ===== SALVAR JSON DE REFERÊNCIA =====
    # (Não salvamos novamente para não duplicar)
    print(f"\n💾 Estado salvo em {ARQUIVO_ESTADO}")

    # ===== RESUMO =====
    print("\n" + "=" * 70)
    print("📊 RESUMO FINAL")
    print("=" * 70)
    print(f"   ✅ Itens traduzidos (novos): {len(itens_restantes) - descartados}")
    print(f"   ⏭️ Descartados (resposta vazia): {descartados}")
    print(f"   📁 Curtos (≤128): {contagem['curto']} em {PASTA_CURTOS}")
    print(f"   📁 Médios (129-256): {contagem['medio']} em {PASTA_MEDIOS}")
    print(f"   📁 Longos (>256): {contagem['longo']} em {PASTA_LONGOS}")
    print(f"   💰 Custo real acumulado: ${custo_real:.4f} (limite: ${args.custo_max:.2f})")
    print(f"   ⏱️  Tempo total: {tempo_total:.2f}s")
    print(f"   📂 Estado salvo em: {ARQUIVO_ESTADO}")
    print("=" * 70)

    print("\n💡 Próximos passos:")
    print("   Os arquivos já estão em dados/gerados/curtos/, medios/ e longos/")
    print("   Execute o treino: python treino.py")

if __name__ == "__main__":
    main()