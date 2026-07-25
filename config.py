#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
config.py - Configurações globais, variáveis de ambiente e cliente da API
"""
import os
import sys
import httpx
from dotenv import load_dotenv
from openai import OpenAI

# ----------------------------------------------------------------------------
# Pastas (mantidas da v2.0)
# ----------------------------------------------------------------------------
PASTA_SAIDA = "dados/gerados"
PASTA_DADOS_CURTOS = os.path.join(PASTA_SAIDA, "curtos")
PASTA_DADOS_LONGOS = os.path.join(PASTA_SAIDA, "longos")
PASTA_LOGS = os.path.join(PASTA_SAIDA, "logs")
PASTA_DESCARTES = os.path.join(PASTA_SAIDA, "descartados")
PASTA_ESTADO = os.path.join(PASTA_SAIDA, "estado")

# Criar pastas se não existirem
for pasta in [PASTA_SAIDA, PASTA_DADOS_CURTOS, PASTA_DADOS_LONGOS,
              PASTA_LOGS, PASTA_DESCARTES, PASTA_ESTADO]:
    os.makedirs(pasta, exist_ok=True)

# Caminhos para arquivos de estado e logs
ARQUIVO_GASTOS = os.path.join(PASTA_LOGS, "gastos.json")
ARQUIVO_LOG = os.path.join(PASTA_LOGS, "dialogos.log")
ARQUIVO_HISTORICO = os.path.join(PASTA_LOGS, "dialogos_historico.json")
ARQUIVO_HISTORICO_TEMAS = os.path.join(PASTA_ESTADO, "historico_temas.json")
ARQUIVO_HISTORICO_RESPOSTAS = os.path.join(PASTA_ESTADO, "historico_respostas.json")
ARQUIVO_CONTAGEM_CATEGORIAS = os.path.join(PASTA_ESTADO, "contagem_categorias.json")
ARQUIVO_CONTAGEM_ASSUNTOS = os.path.join(PASTA_ESTADO, "contagem_assuntos.json")
ARQUIVO_METADADOS = os.path.join(PASTA_ESTADO, "metadados_gerados.json")
ARQUIVO_ESTADO_DIALOGOS = os.path.join(PASTA_ESTADO, "estado_dialogos.json")
ARQUIVO_HISTORICO_TOPICOS = os.path.join(PASTA_ESTADO, "topicos_usados.txt")

# Arquivo de tópicos externos (padrão)
ARQUIVO_TOPICOS_EXTERNOS = "topicos.txt"

# ----------------------------------------------------------------------------
# Tokens e limites (mantidos da v2.0)
# ----------------------------------------------------------------------------
TOKENS_BASE_DICIONARIO = 256
TOKENS_ESCALONADOS_DICIONARIO = [256, 384, 512]

TOKENS_BASE_PERGUNTA_RESPOSTA = 768
TOKENS_ESCALONADOS_PERGUNTA_RESPOSTA = [768, 1024, 1280]

TOKENS_BASE_CONVERSA = 768
TOKENS_ESCALONADOS_CONVERSA = [768, 1024, 1280]

TOKENS_BASE_ITERACAO = 512
TOKENS_ESCALONADOS_ITERACAO = [512, 768, 1024]

TOKENS_BASE_ARTIGO = 768
TOKENS_ESCALONADOS_ARTIGO = [768, 1024, 1280]

TOKENS_BASE_CONTO = 768
TOKENS_ESCALONADOS_CONTO = [768, 1024, 1280]

TOKENS_BASE_DIALOGO_PROFUNDO = 768
TOKENS_ESCALONADOS_DIALOGO_PROFUNDO = [768, 1024, 1280]

TOKENS_BASE_EXPLICACAO = 768
TOKENS_ESCALONADOS_EXPLICACAO = [768, 1024, 1280]

TOKENS_BASE_RESUMO = 512
TOKENS_ESCALONADOS_RESUMO = [512, 768, 1024]

LIMITE_TOKENS_CURTOS = 128
LIMITE_PALAVRAS_CURTOS = 24
LIMITE_PALAVRAS_LONGOS = 80
MAX_ITENS_REPETICAO_RECENTE = 1000

# Limites padrão (podem ser sobrescritos por .env ou argumentos)
MAX_COST_USD = 5.00
DELAY_SECONDS = 2.0

# Dicionário de configuração por tipo (facilita o escalonamento)
TIPO_CONFIG = {
    "dicionario": {"tokens": TOKENS_ESCALONADOS_DICIONARIO, "temps": [0.5, 0.7, 0.9]},
    "pergunta_resposta": {"tokens": TOKENS_ESCALONADOS_PERGUNTA_RESPOSTA, "temps": [0.7, 0.8, 0.9]},
    "iteracao": {"tokens": TOKENS_ESCALONADOS_ITERACAO, "temps": [0.7, 0.8, 0.9]},
    "artigo": {"tokens": TOKENS_ESCALONADOS_ARTIGO, "temps": [0.7, 0.8, 0.9]},
    "conto": {"tokens": TOKENS_ESCALONADOS_CONTO, "temps": [0.7, 0.8, 0.9]},
    "dialogo_profundo": {"tokens": TOKENS_ESCALONADOS_DIALOGO_PROFUNDO, "temps": [0.7, 0.8, 0.9]},
    "explicacao": {"tokens": TOKENS_ESCALONADOS_EXPLICACAO, "temps": [0.7, 0.8, 0.9]},
    "resumo": {"tokens": TOKENS_ESCALONADOS_RESUMO, "temps": [0.4, 0.6, 0.8]},
    "conversa": {"tokens": TOKENS_ESCALONADOS_CONVERSA, "temps": [0.7, 0.8, 0.9]},
}


def get_tipo_config(tipo: str) -> dict:
    """Retorna a configuração para um tipo específico."""
    return TIPO_CONFIG.get(tipo, TIPO_CONFIG["dicionario"])


# ----------------------------------------------------------------------------
# Carregar .env e configurar cliente da API
# ----------------------------------------------------------------------------
load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-flash")

if not API_KEY:
    print("❌ ERRO: DEEPSEEK_API_KEY não encontrada no arquivo .env")
    sys.exit(1)

# Cria cliente com timeout maior para evitar erros de rede
client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.deepseek.com/v1",
    timeout=httpx.Timeout(120.0, connect=15.0)
)


# ----------------------------------------------------------------------------
# Funções para atualizar configuração via argumentos
# ----------------------------------------------------------------------------
def atualizar_config(args) -> None:
    """Atualiza variáveis globais com valores passados por linha de comando."""
    global MAX_COST_USD, DELAY_SECONDS
    if hasattr(args, 'limite') and args.limite is not None:
        MAX_COST_USD = args.limite
    if hasattr(args, 'delay') and args.delay is not None:
        DELAY_SECONDS = args.delay


# ----------------------------------------------------------------------------
# Controle de gastos (mantido da v2.0)
# ----------------------------------------------------------------------------
def carregar_gastos():
    """Carrega o histórico de gastos do arquivo JSON."""
    if os.path.exists(ARQUIVO_GASTOS):
        with open(ARQUIVO_GASTOS, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return {"total_gasto": 0.0, "historico": []}
    return {"total_gasto": 0.0, "historico": []}


def salvar_gastos(dados):
    """Salva o histórico de gastos em arquivo JSON."""
    with open(ARQUIVO_GASTOS, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def registrar_gasto(custo, tokens_entrada, tokens_saida, tema, tipo):
    """Registra um gasto e retorna o total acumulado."""
    dados = carregar_gastos()
    dados["total_gasto"] += custo
    dados["historico"].append({
        "data": datetime.now().isoformat(),
        "tema": tema,
        "tipo": tipo,
        "tokens_entrada": tokens_entrada,
        "tokens_saida": tokens_saida,
        "custo_usd": round(custo, 6),
        "custo_acumulado": round(dados["total_gasto"], 6)
    })
    salvar_gastos(dados)
    return dados["total_gasto"]


def verificar_limite():
    """Verifica se o limite de gastos foi atingido."""
    dados = carregar_gastos()
    if dados["total_gasto"] >= MAX_COST_USD:
        print(f"⚠️ Limite de gastos atingido: ${MAX_COST_USD:.2f}")
        return False
    return True


# Importações para evitar erro de referência circular (json e datetime usados acima)
import json
from datetime import datetime

# ----------------------------------------------------------------------------
# Exportar símbolos principais para facilitar importação
# ----------------------------------------------------------------------------
__all__ = [
    "PASTA_SAIDA", "PASTA_DADOS_CURTOS", "PASTA_DADOS_LONGOS",
    "PASTA_LOGS", "PASTA_DESCARTES", "PASTA_ESTADO",
    "ARQUIVO_GASTOS", "ARQUIVO_LOG", "ARQUIVO_HISTORICO",
    "ARQUIVO_HISTORICO_TEMAS", "ARQUIVO_HISTORICO_RESPOSTAS",
    "ARQUIVO_CONTAGEM_CATEGORIAS", "ARQUIVO_CONTAGEM_ASSUNTOS",
    "ARQUIVO_METADADOS", "ARQUIVO_ESTADO_DIALOGOS",
    "ARQUIVO_HISTORICO_TOPICOS", "ARQUIVO_TOPICOS_EXTERNOS",
    "TOKENS_BASE_DICIONARIO", "TOKENS_ESCALONADOS_DICIONARIO",
    "TOKENS_BASE_PERGUNTA_RESPOSTA", "TOKENS_ESCALONADOS_PERGUNTA_RESPOSTA",
    "TOKENS_BASE_CONVERSA", "TOKENS_ESCALONADOS_CONVERSA",
    "TOKENS_BASE_ITERACAO", "TOKENS_ESCALONADOS_ITERACAO",
    "TOKENS_BASE_ARTIGO", "TOKENS_ESCALONADOS_ARTIGO",
    "TOKENS_BASE_CONTO", "TOKENS_ESCALONADOS_CONTO",
    "TOKENS_BASE_DIALOGO_PROFUNDO", "TOKENS_ESCALONADOS_DIALOGO_PROFUNDO",
    "TOKENS_BASE_EXPLICACAO", "TOKENS_ESCALONADOS_EXPLICACAO",
    "TOKENS_BASE_RESUMO", "TOKENS_ESCALONADOS_RESUMO",
    "LIMITE_TOKENS_CURTOS", "LIMITE_PALAVRAS_CURTOS", "LIMITE_PALAVRAS_LONGOS",
    "MAX_ITENS_REPETICAO_RECENTE", "MAX_COST_USD", "DELAY_SECONDS",
    "TIPO_CONFIG", "get_tipo_config",
    "client", "MODEL_NAME", "API_KEY",
    "atualizar_config",
    "carregar_gastos", "salvar_gastos", "registrar_gasto", "verificar_limite"
]