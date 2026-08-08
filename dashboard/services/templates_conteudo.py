#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
templates_conteudo.py — FONTE ÚNICA de templates e estilos de geração.

Uniformiza a geração LOCAL (Ollama) e a geração por API (DeepSeek/dialogos2):
se um template existe num lugar, existe no outro (mesma lista de IDs).
A diferença é só o MOTOR: um usa a API, o outro usa um servidor/modelo local.

TIPOS_CONTEUDO: dict id -> {nome, descricao, prompt, system, max_tokens, temp}
ESTILOS_ESCRITA: dict id -> {nome, descricao, instrucao}

Templates alinhados com dialogos2.py (21 tipos + modo "automatico").
"""
from __future__ import annotations

# ============================================================================
# TIPOS DE CONTEÚDO — alinhado com a geração por API (dialogos2.py)
# ============================================================================
TIPOS_CONTEUDO: dict[str, dict] = {
    "dicionario": {
        "nome": "📚 Dicionário",
        "descricao": "Pergunta + resposta curta (definição clara).",
        "prompt": "Explique o significado e dê um exemplo de: {tema}. Formato: Pergunta: ... / Resposta: ...",
        "system": "Você é um dicionarista em português brasileiro. Explique conceitos de forma clara e concisa, com um exemplo prático.",
        "max_tokens": 512,
        "temp": 0.7,
    },
    "pergunta_resposta": {
        "nome": "❓ Pergunta/Resposta",
        "descricao": "Pergunta + resposta longa e bem explicada.",
        "prompt": "Crie uma pergunta interessante seguida de uma resposta completa e bem explicada sobre: {tema}. Formato: Pergunta: ... / Resposta: ...",
        "system": "Você é um educador em português brasileiro criando material didático de qualidade.",
        "max_tokens": 1024,
        "temp": 0.7,
    },
    "iteracao": {
        "nome": "🔄 Iteração",
        "descricao": "Diálogo de 5-8 turnos explorando um tema.",
        "prompt": "Crie um diálogo natural de 5 a 8 turnos entre duas pessoas explorando: {tema}. Use nomes e linguagem cotidiana.",
        "system": "Você é um roteirista de diálogos em português brasileiro. Diálogos naturais e com profundidade.",
        "max_tokens": 768,
        "temp": 0.8,
    },
    "artigo": {
        "nome": "📰 Artigo",
        "descricao": "Artigo estruturado de 500-900 palavras.",
        "prompt": "Escreva um artigo bem estruturado sobre: {tema}. Inclua introdução, desenvolvimento com subtítulos e conclusão. Entre 500 e 900 palavras.",
        "system": "Você é um redator profissional em português brasileiro. Artigos claros, ricos e bem organizados.",
        "max_tokens": 1024,
        "temp": 0.7,
    },
    "conto": {
        "nome": "📖 Conto",
        "descricao": "História curta e envolvente de 400-700 palavras.",
        "prompt": "Escreva um conto envolvente sobre: {tema}. Com personagens, cenário e desfecho. Entre 400 e 700 palavras.",
        "system": "Você é um contista brasileiro. Histórias curtas com começo, meio e fim cativantes.",
        "max_tokens": 1024,
        "temp": 0.8,
    },
    "dialogo_profundo": {
        "nome": "💬 Diálogo Profundo",
        "descricao": "Diálogo de 10-15 turnos com profundidade.",
        "prompt": "Crie um diálogo profundo de 10 a 15 turnos em português brasileiro explorando: {tema}. Personagens com opiniões e emoções.",
        "system": "Você é um escritor de diálogos profundos em português brasileiro. Conversas ricas, com camadas.",
        "max_tokens": 1024,
        "temp": 0.8,
    },
    "explicacao": {
        "nome": "🔍 Explicação",
        "descricao": "Explicação detalhada de 350-600 palavras.",
        "prompt": "Explique de forma detalhada e acessível: {tema}. Inclua contexto, exemplos práticos e uma conclusão. Entre 350 e 600 palavras.",
        "system": "Você é um explicador didático em português brasileiro. Clareza acima de tudo.",
        "max_tokens": 1024,
        "temp": 0.7,
    },
    "resumo": {
        "nome": "📌 Resumo",
        "descricao": "Síntese concisa de 200-400 palavras.",
        "prompt": "Faça um resumo conciso e bem organizado sobre: {tema}. Entre 200 e 400 palavras.",
        "system": "Você é um especialista em resumos em português brasileiro. Capture apenas o essencial.",
        "max_tokens": 768,
        "temp": 0.5,
    },
    "conversa": {
        "nome": "🗣️ Conversa",
        "descricao": "Diálogo casual de no mínimo 250 palavras.",
        "prompt": "Crie uma conversa casual e natural entre duas pessoas sobre: {tema}. No mínimo 250 palavras no total.",
        "system": "Você é um escritor de conversas naturais em português brasileiro, com jeitinho cotidiano.",
        "max_tokens": 1024,
        "temp": 0.8,
    },
    "saudacao": {
        "nome": "👋 Saudação",
        "descricao": "Saída pronta e calorosa (sem custo de API).",
        "prompt": "Escreva uma saudação calorosa e natural para: {tema}. Curta e direta.",
        "system": "Você escreve saudações brasileiras acolhedoras e naturais.",
        "max_tokens": 256,
        "temp": 0.7,
    },
    "poema": {
        "nome": "🎭 Poema",
        "descricao": "Poema de 10-20 versos.",
        "prompt": "Escreva um poema de 10 a 20 versos sobre: {tema}. Com ritmo e imagens.",
        "system": "Você é um poeta brasileiro. Poemas expressivos com ritmo e sensibilidade.",
        "max_tokens": 512,
        "temp": 0.9,
    },
    "carta": {
        "nome": "✉️ Carta",
        "descricao": "Carta formal ou informal.",
        "prompt": "Escreva uma carta sobre: {tema}. Escolha tom formal ou informal adequado ao assunto.",
        "system": "Você é um escritor de cartas em português brasileiro. Cartas sinceras e bem escritas.",
        "max_tokens": 768,
        "temp": 0.7,
    },
    "entrevista": {
        "nome": "🎤 Entrevista",
        "descricao": "Entrevista com 5-8 perguntas e respostas.",
        "prompt": "Crie uma entrevista fictícia com 5 a 8 perguntas e respostas sobre: {tema}. Formato: Pergunta: ... / Resposta: ...",
        "system": "Você é um jornalista brasileiro conduzindo entrevistas reveladoras.",
        "max_tokens": 1024,
        "temp": 0.7,
    },
    "debate": {
        "nome": "⚖️ Debate",
        "descricao": "Prós e contras de um tema.",
        "prompt": "Apresente um debate equilibrado sobre: {tema}. Liste argumentos a favor e contra, com conclusão.",
        "system": "Você é um debatedor equilibrado em português brasileiro. Dois lados com justiça.",
        "max_tokens": 768,
        "temp": 0.7,
    },
    "tutorial": {
        "nome": "📋 Tutorial",
        "descricao": "Passo a passo objetivo.",
        "prompt": "Crie um tutorial passo a passo explicando como: {tema}. Liste cada passo numerado e seja objetivo.",
        "system": "Você é um instrutor técnico em português brasileiro. Tutoriais claros e objetivos.",
        "max_tokens": 768,
        "temp": 0.6,
    },
    "resenha": {
        "nome": "⭐ Resenha",
        "descricao": "Crítica e análise de uma obra/tema.",
        "prompt": "Escreva uma resenha crítica sobre: {tema}. Com opinião fundamentada, pontos fortes e fracos.",
        "system": "Você é um crítico literário brasileiro. Resenhas com opinião fundamentada.",
        "max_tokens": 768,
        "temp": 0.7,
    },
    "relatorio": {
        "nome": "📊 Relatório",
        "descricao": "Relatório técnico estruturado.",
        "prompt": "Elabore um relatório técnico sobre: {tema}. Com seções claras (objetivo, desenvolvimento, conclusão).",
        "system": "Você é um analista técnico em português brasileiro. Relatórios precisos e bem estruturados.",
        "max_tokens": 1024,
        "temp": 0.6,
    },
    "ensaio": {
        "nome": "📝 Ensaio",
        "descricao": "Texto reflexivo e argumentativo.",
        "prompt": "Escreva um ensaio reflexivo sobre: {tema}. Com argumentação pessoal e profundidade.",
        "system": "Você é um ensaísta brasileiro. Textos reflexivos com voz própria.",
        "max_tokens": 1024,
        "temp": 0.8,
    },
    "cronica": {
        "nome": "☕ Crônica",
        "descricao": "Texto literário curto sobre o cotidiano.",
        "prompt": "Escreva uma crônica sobre: {tema}. Texto literário curto com tom leve e observação do cotidiano.",
        "system": "Você é um cronista brasileiro. Textos com humor, leveza e olhar atento.",
        "max_tokens": 768,
        "temp": 0.8,
    },
    "receita": {
        "nome": "🍳 Receita",
        "descricao": "Receita culinária passo a passo.",
        "prompt": "Escreva uma receita culinária para: {tema}. Com ingredientes e modo de preparo passo a passo.",
        "system": "Você é um chef brasileiro. Receitas claras, saborosas e práticas.",
        "max_tokens": 512,
        "temp": 0.7,
    },
    "dica": {
        "nome": "💡 Dica",
        "descricao": "Conselho rápido e prático.",
        "prompt": "Escreva uma dica prática e objetiva sobre: {tema}. Curta e acionável.",
        "system": "Você é um conselheiro prático em português brasileiro. Dicas curtas e úteis.",
        "max_tokens": 256,
        "temp": 0.7,
    },
}

# Ordem canônica (mesma da geração por API)
ORDEM_TIPOS = [
    "dicionario", "pergunta_resposta", "iteracao", "artigo", "conto",
    "dialogo_profundo", "explicacao", "resumo", "conversa", "saudacao",
    "poema", "carta", "entrevista", "debate", "tutorial", "resenha",
    "relatorio", "ensaio", "cronica", "receita", "dica",
]

# ============================================================================
# ESTILOS DE ESCRITA — uniformizados (mesma lista nos dois motores)
# ============================================================================
ESTILOS_ESCRITA: dict[str, dict] = {
    "neutro": {
        "nome": "➖ Neutro (padrão)",
        "descricao": "Estilo padrão do template, sem modificações.",
        "instrucao": "",
    },
    "profissional": {
        "nome": "💼 Profissional",
        "descricao": "Linguagem formal, técnica e corporativa.",
        "instrucao": "Use linguagem formal, técnica e profissional. Evite gírias, abreviações ou tom casual. Seja preciso e objetivo, como em um ambiente corporativo sério.",
    },
    "professor": {
        "nome": "👨‍🏫 Professor",
        "descricao": "Tom didático, como um professor explicando.",
        "instrucao": "Adote um tom didático e acolhedor, como um professor explicando para seus alunos. Explique conceitos de forma clara, use exemplos práticos e faça perguntas retóricas para engajar.",
    },
    "especialista": {
        "nome": "🔬 Especialista",
        "descricao": "Autoridade técnica, vocabulário avançado.",
        "instrucao": "Use linguagem técnica e aprofundada, como um especialista no assunto. Empregue terminologia específica da área, dados e referências.",
    },
    "casual_jovem": {
        "nome": "🗣️ Conversa entre Jovens",
        "descricao": "Linguagem descontraída com gírias leves.",
        "instrucao": "Use linguagem descontraída e informal, como uma conversa entre jovens. Pode usar gírias leves (tipo 'mano', 'curtir', 'demais'), abreviações casuais e um tom animado.",
    },
    "humoristico": {
        "nome": "😂 Bem-Humorado",
        "descricao": "Tom leve, divertido e com pitadas de humor.",
        "instrucao": "Use um tom leve, bem-humorado e divertido. Inclua piadas sutis, trocadilhos e um toque de irreverência. Mantenha o respeito.",
    },
    "poetico": {
        "nome": "📜 Poético / Literário",
        "descricao": "Linguagem rebuscada, metafórica e literária.",
        "instrucao": "Use linguagem poética, metafórica e rica em imagens. Abuse de figuras de linguagem, descrições sensoriais e um ritmo de escrita cadenciado.",
    },
    "informativo_jornalistico": {
        "nome": "📰 Jornalístico",
        "descricao": "Tom imparcial, factual e direto.",
        "instrucao": "Use tom imparcial e factual, como uma reportagem jornalística. Seja direto: quem, o quê, quando, onde, por quê. Evite opinião pessoal.",
    },
}

ORDEM_ESTILOS = ["neutro", "profissional", "professor", "especialista",
                 "casual_jovem", "humoristico", "poetico", "informativo_jornalistico"]


def listar_tipos() -> list[dict]:
    """Lista os tipos em ordem canônica (sem o campo 'prompt' interno)."""
    return [
        {"id": tid, "nome": TIPOS_CONTEUDO[tid]["nome"],
         "descricao": TIPOS_CONTEUDO[tid]["descricao"],
         "max_tokens": TIPOS_CONTEUDO[tid]["max_tokens"],
         "temperatura": TIPOS_CONTEUDO[tid]["temp"]}
        for tid in ORDEM_TIPOS
    ]


def listar_estilos() -> list[dict]:
    return [
        {"id": sid, "nome": ESTILOS_ESCRITA[sid]["nome"],
         "descricao": ESTILOS_ESCRITA[sid]["descricao"]}
        for sid in ORDEM_ESTILOS
    ]
