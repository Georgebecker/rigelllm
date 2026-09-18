#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gerador_categorias.py — Transforma o categories.py em FONTE DE TEMAS para a
geração LOCAL (Ollama). Criado em 13/08/2026.

O que faz:
  1. sortear_par()          → sorteia (categoria, assunto) das 35+ listas curadas.
  2. montar_pergunta()      → monta uma PERGUNTA natural usando PREFIXOS_POR_CATEGORIA
                              e TEMPLATES_EXTRAS (com variação e perguntas combinadas).
  3. montar_prompt_por_pergunta() → prompt completo (pergunta + formato do tipo +
                              instruções da categoria + estilo) p/ o Ollama.
  4. obter_instrucoes()     → bloco de contexto específico por categoria.
  5. detectar_categoria()   → detecta a categoria de um texto/título (RSS).
  6. gerar_perguntas_relacionadas() → dado um título RSS, gera perguntas relacionadas
                              aproveitando as listas de categories.py.
  7. listar_categorias() / contar_assuntos() / amostra_perguntas() → p/ o dashboard.
  8. carregar_titulos_rss() → títulos RSS (cache 6h ou fetch ao vivo) p/ o modo 📰.

Usado por: scripts/gerar_massa_local.py (--fonte categorias|misto|rss),
dashboard/routes/local_generate.py (endpoints de prévia) e gerar_local.html.

REGRAS DE OURO (memória do projeto):
  - Nada é apagado: só LÊ categories.py e gera conteúdo novo.
  - 100% português brasileiro; conteúdo factual guiado por instruções.
  - PREVÊ problemas sozinho (try/except em tudo, fallback para tópicos).
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))

try:
    from categories import (
        CATEGORIAS_LISTAS,
        PREFIXOS_POR_CATEGORIA,
        TEMPLATES_EXTRAS,
        GRUPOS_CATEGORIAS,
    )
except Exception as _e:  # nunca derruba o dashboard se categories falhar
    CATEGORIAS_LISTAS = {}
    PREFIXOS_POR_CATEGORIA = {}
    TEMPLATES_EXTRAS = {}
    GRUPOS_CATEGORIAS = {}

RSS_CACHE = PROJETO_ROOT / "logs" / "rss_titulos_cache.json"
FEEDS_PATH = PROJETO_ROOT / "feeds.txt"
_RSS_TTL_SEG = 6 * 3600  # cache de títulos RSS válido por 6h

# ============================================================================
# METADADOS DAS CATEGORIAS (nome amigável + emoji p/ o dashboard)
# ============================================================================
CATEGORIAS_META: dict[str, dict] = {
    "objeto":                {"nome": "Objetos", "emoji": "🔧", "descricao": "Utensílios, ferramentas e coisas do cotidiano."},
    "lugar":                 {"nome": "Lugares", "emoji": "🗺️", "descricao": "Cidades, regiões, pontos turísticos e históricos."},
    "pessoa":                {"nome": "Pessoas", "emoji": "👤", "descricao": "Biografias, personalidades e contribuições."},
    "sentimento":            {"nome": "Sentimentos", "emoji": "💭", "descricao": "Emoções, valores e abstrações."},
    "conceito":              {"nome": "Conceitos", "emoji": "🧠", "descricao": "Ideias, definições e abstrações."},
    "conhecimento":          {"nome": "Conhecimento", "emoji": "📚", "descricao": "Áreas do saber, campos de estudo."},
    "profissao":             {"nome": "Profissões", "emoji": "💼", "descricao": "Oficios, carreiras e funções."},
    "arte_cultura":          {"nome": "Arte e Cultura", "emoji": "🎭", "descricao": "Manifestações artísticas e culturais."},
    "ciencia_tecnologia":    {"nome": "Ciência e Tecnologia", "emoji": "🔬", "descricao": "Invenções, inovações e saberes."},
    "acao":                  {"nome": "Ações", "emoji": "🏃", "descricao": "Verbos e ações do cotidiano brasileiro."},
    "alimento":              {"nome": "Alimentos", "emoji": "🍲", "descricao": "Diversidade da mesa brasileira."},
    "animal":                {"nome": "Animais", "emoji": "🦜", "descricao": "Fauna brasileira e cultural."},
    "transporte":            {"nome": "Transporte", "emoji": "🚌", "descricao": "Meios de locomoção e memória regional."},
    "sociedade_politica":    {"nome": "Sociedade e Política", "emoji": "🏛️", "descricao": "Estado, poder e resistência."},
    "natureza_universo":     {"nome": "Natureza e Universo", "emoji": "🌍", "descricao": "Biomas, fenômenos, astros e minerais."},
    "musica":                {"nome": "Música e Cantores", "emoji": "🎵", "descricao": "Gêneros, bandas e artistas brasileiros."},
    "sintomas_doencas":      {"nome": "Saúde e Doenças", "emoji": "🩺", "descricao": "Sintomas, doenças e saúde pública."},
    "datas_historicas":      {"nome": "Datas Históricas", "emoji": "📅", "descricao": "Marcos, lutas e conquistas."},
    "geopolitica":           {"nome": "Geopolítica", "emoji": "🌐", "descricao": "Relações internacionais e conceitos."},
    "ciencia":               {"nome": "Ciência", "emoji": "🧪", "descricao": "Física, biologia, química e mais."},
    "historia":              {"nome": "História", "emoji": "🏺", "descricao": "Períodos, civilizações e guerras."},
    "filosofia":             {"nome": "Filosofia", "emoji": "🤔", "descricao": "Correntes e pensadores."},
    "literatura":            {"nome": "Literatura", "emoji": "📖", "descricao": "Obras, autores e movimentos."},
    "economia":              {"nome": "Economia", "emoji": "📈", "descricao": "Conceitos, políticas e setores."},
    "esportes":              {"nome": "Esportes", "emoji": "⚽", "descricao": "Modalidades e eventos."},
    "mitologia":             {"nome": "Mitologia", "emoji": "🐉", "descricao": "Lendas brasileiras e mundiais."},
    "ciencias_sociais":      {"nome": "Ciências Sociais", "emoji": "👥", "descricao": "Teorias e abordagens sociais."},
    "filmes":                {"nome": "Filmes", "emoji": "🎬", "descricao": "Nacionais e internacionais."},
    "series":                {"nome": "Séries", "emoji": "📺", "descricao": "TV e streaming."},
    "livros":                {"nome": "Livros", "emoji": "📕", "descricao": "Obras literárias."},
    "personagens_ficticios": {"nome": "Personagens Fictícios", "emoji": "🦸", "descricao": "Literatura, cinema e cultura pop."},
    "tecnologias_emergentes": {"nome": "Tecnologias Emergentes", "emoji": "🚀", "descricao": "Inovações e fronteiras."},
    "eventos_historicos_brasil": {"nome": "Eventos do Brasil", "emoji": "🇧🇷", "descricao": "Revoltas e marcos nacionais."},
    "povos_originarios":     {"nome": "Povos Originários", "emoji": "🪶", "descricao": "Línguas, mitos e saberes."},
}

# ============================================================================
# INSTRUÇÕES POR TIPO DE CONTEÚDO (para responder à pergunta de forma variada)
# ============================================================================
INSTRUCAO_TIPO: dict[str, str] = {
    "dicionario": "Responda de forma curta e direta (máximo 2-3 frases), como um verbete de dicionário. Não repita a pergunta.",
    "pergunta_resposta": "Responda de forma completa e bem explicada, com exemplos concretos. Não repita a pergunta literalmente.",
    "iteracao": "Crie um diálogo natural de 5 a 8 turnos entre duas pessoas sobre essa pergunta, com nomes e linguagem cotidiana.",
    "artigo": "Escreva um artigo bem estruturado (introdução, desenvolvimento com subtítulos e conclusão), entre 500 e 900 palavras, respondendo à pergunta.",
    "conto": "Escreva um conto envolvente (400 a 700 palavras) que aborde o tema da pergunta de forma indireta e criativa.",
    "dialogo_profundo": "Crie um diálogo profundo de 10 a 15 turnos explorando a pergunta, com personagens que têm opiniões e emoções.",
    "explicacao": "Explique de forma detalhada e acessível, incluindo contexto, exemplos práticos e conclusão (350 a 600 palavras).",
    "resumo": "Faça um resumo conciso e bem organizado (200 a 400 palavras) respondendo à pergunta.",
    "conversa": "Crie uma conversa casual e natural entre duas pessoas sobre a pergunta (no mínimo 250 palavras).",
    "saudacao": "Responda de forma calorosa e breve, como quem cumprimenta e já responde a pergunta em poucas frases.",
    "poema": "Escreva um poema (12 a 30 versos) que responda ou dialogue com a pergunta de forma lírica.",
    "carta": "Escreva uma carta pessoal (200 a 400 palavras) de alguém respondendo a essa pergunta a um amigo.",
    "entrevista": "Crie uma entrevista (perguntas do entrevistador + respostas do entrevistado) sobre o tema da pergunta.",
    "debate": "Crie um debate entre duas pessoas com opiniões diferentes sobre a pergunta, com argumentos e réplicas.",
    "tutorial": "Escreva um tutorial passo a passo (passos numerados) que responda à pergunta na prática.",
    "resenha": "Escreva uma resenha crítica (250 a 450 palavras) relacionada ao tema da pergunta.",
    "relatorio": "Escreva um relatório formal estruturado com seções e conclusão respondendo à pergunta.",
    "ensaio": "Escreva um ensaio reflexivo (400 a 700 palavras) explorando a pergunta com argumentos e profundidade.",
    "cronica": "Escreva uma crônica leve e bem-humorada (200 a 400 palavras) que parta da pergunta.",
    "receita": "Escreva uma receita prática e detalhada (ingredientes + modo de preparo) relacionada ao tema.",
    "dica": "Escreva dicas práticas e úteis (lista numerada) respondendo à pergunta.",
}


def _agora() -> str:
    return datetime.now().isoformat()


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def _normalizar_pergunta(p: str) -> str:
    p = _normalizar(p)
    if not p.endswith("?"):
        p += "?"
    return p[0].upper() + p[1:] if p else p


def _item_limpo(item) -> str:
    """Extrai string de um item (aceita str ou tupla/listas como DECLARACOES)."""
    if isinstance(item, (tuple, list)):
        item = item[0] if item else ""
    return str(item).strip()


# ============================================================================
# RESOLUÇÃO DE CATEGORIAS
# ============================================================================
def _resolver_categorias(categorias=None) -> list[str]:
    """Normaliza a seleção de categorias (str 'a,b', lista, ou None = todas)."""
    if not categorias:
        return list(CATEGORIAS_LISTAS.keys())
    if isinstance(categorias, str):
        cats = [c.strip() for c in categorias.split(",") if c.strip()]
    else:
        cats = list(categorias)
    validas = [c for c in cats if c in CATEGORIAS_LISTAS]
    return validas or list(CATEGORIAS_LISTAS.keys())


def listar_categorias() -> list[dict]:
    """Lista todas as categorias com contagem + exemplos (para o dashboard)."""
    out = []
    for cid, lista in CATEGORIAS_LISTAS.items():
        meta = CATEGORIAS_META.get(cid, {})
        n = len(lista)
        exemplos = [_item_limpo(x) for x in lista[:3]]
        out.append({
            "id": cid,
            "nome": meta.get("nome", cid),
            "emoji": meta.get("emoji", "🗂️"),
            "descricao": meta.get("descricao", ""),
            "itens": n,
            "exemplos": exemplos,
        })
    out.sort(key=lambda c: -c["itens"])
    return out


def contar_assuntos(categorias=None) -> int:
    """Total de assuntos disponíveis nas categorias selecionadas."""
    total = 0
    for c in _resolver_categorias(categorias):
        total += len(CATEGORIAS_LISTAS.get(c) or [])
    return total


# ============================================================================
# SORTEIO + PERGUNTAS
# ============================================================================
def _sorteia_outro_assunto(categoria: str, atual: str) -> Optional[str]:
    """Sorteia outro assunto da mesma categoria (para perguntas combinadas)."""
    lista = CATEGORIAS_LISTAS.get(categoria) or []
    if len(lista) < 2:
        return None
    atual_l = str(atual).lower()
    for _ in range(10):
        item = _item_limpo(random.choice(lista))
        if item and item.lower() != atual_l:
            return item
    return None


def sortear_par(categorias=None) -> tuple[Optional[str], Optional[str]]:
    """Sorteia (categoria, assunto). categorias=None = qualquer uma."""
    cats = _resolver_categorias(categorias)
    if not cats:
        return None, None
    categoria = random.choice(cats)
    lista = CATEGORIAS_LISTAS.get(categoria) or []
    if not lista:
        return categoria, None
    return categoria, _item_limpo(random.choice(lista))


# ============================================================================
# COMPATIBILIDADE PERGUNTA × ASSUNTO (evita perguntas erradas p/ o tipo)
# Pedido do usuário (13/08): o gerador às vezes cria pergunta errada para a
# resposta — ex.: "Como conservar uma chave philips?" quando o certo é
# "O que é / Para que serve". Alguns prefixos só fazem sentido para certos
# TIPOS de assunto (ferramenta, alimento, sentimento, ação, doença...).
# ============================================================================
# stem do prefixo (minúsculo) → naturezas permitidas
_RISCO_PREFIXO_POR_NATUREZA: dict[str, set[str]] = {
    "como conservar":    {"alimento", "objeto", "conceito", "sentimento", "lugar"},
    "como limpar":       {"alimento", "objeto", "transporte", "lugar"},
    "como armazenar":    {"alimento", "objeto"},
    "como guardar":      {"alimento", "objeto"},
    "como preparar":     {"alimento", "acao"},
    "como cozinhar":     {"alimento"},
    "como combinar":     {"alimento"},
    "como cultivar":     {"alimento", "sentimento", "conceito"},
    "como alcançar":     {"sentimento", "conceito"},
    "como lidar com":    {"sentimento", "conceito"},
    "como superar":      {"sentimento", "conceito"},
    "como desenvolver":  {"sentimento", "conceito", "profissao"},
    "como expressar":    {"sentimento", "conceito"},
    "como se tornar":    {"profissao"},
    "como melhorar":     {"acao", "conceito", "profissao"},
    "como aprender":     {"acao", "conceito", "conhecimento"},
    "como começar":      {"acao", "conceito", "profissao"},
    "como praticar":     {"acao", "sentimento", "conceito"},
    "como se preparar":  {"acao", "profissao"},
    "como fazer":        {"alimento", "acao", "conceito"},
    "como usar":         {"objeto", "ferramenta", "transporte"},
    "como escolher":     {"objeto", "ferramenta", "transporte"},
    "como se reproduz":  {"animal"},
    "o que come":        {"animal"},
    "qual o habitat":    {"animal"},
    "como vive":         {"animal"},
    "onde vive":         {"animal"},
    "como se comporta":  {"animal"},
    "como tratar":       {"doenca"},
    "como prevenir":     {"doenca"},
    "como é diagnosticado": {"doenca"},
    "como identificar":  {"doenca", "sentimento"},
    "quanto ganha":      {"profissao"},
    "como é o mercado para": {"profissao"},
    "qual a receita":    {"alimento"},
    "como acompanha":    {"alimento"},
}

# Natureza "clara" já definida pela própria categoria (prefixos curados ok)
_NATUREZA_CLARA: dict[str, str] = {
    "alimento": "alimento",
    "animal": "animal",
    "lugar": "lugar",
    "pessoa": "pessoa",
    "sentimento": "sentimento",
    "acao": "acao",
    "sintomas_doencas": "doenca",
    "profissao": "profissao",
    "livros": "obra",
    "filmes": "obra",
    "series": "obra",
    "musica": "obra",
}

_FERRAMENTA_TERMOS = {
    "chave", "martelo", "serrote", "alicate", "furadeira", "broca",
    "parafuso", "lixa", "esmeril", "morsa", "formão", "cinzel",
    "plaina", "grosa", "talhadeira", "espátula", "ponteira", "martelete",
    "torno", "solda", "canivete", "tesoura", "estilete", "saca-rolhas",
    "trena", "grampo", "pé de cabra", "sargentinho", "bit", "chave de fenda",
    # eletrodomésticos/aparelhos (também são "ferramentas" — querem pergunta funcional)
    "processador", "liquidificador", "cafeteira", "torradeira", "fritadeira",
    "sanduicheira", "geladeira", "fogão", "forno", "micro-ondas", "panela",
    "airfryer", "batedeira", "espremedor", "ventilador", "aspirador",
}
_FERRAMENTA_SUFIXOS = ("dor", "deira", "adeira", "te")


def _e_ferramenta(assunto: str) -> bool:
    """Heurística: o assunto parece uma FERRAMENTA/APARELHO?
    Verifica termos conhecidos E sufixos em QUALQUER palavra do nome
    (ex.: 'processador de alimentos' → 'processador' termina em -dor)."""
    a = (assunto or "").lower().strip()
    if not a:
        return False
    for termo in _FERRAMENTA_TERMOS:
        if termo in a:
            return True
    palavras = re.split(r"[\s\-]+", a)
    for w in palavras:
        w = w.strip(".,;:()")
        if len(w) >= 5 and w.endswith(("dor", "deira", "adeira")):
            return True
        if len(w) >= 6 and w.endswith("te"):  # martelete, soquete... (evita 'ponte')
            return True
    return False


def _natureza_assunto(assunto: str, categoria: str) -> str:
    """Estima a natureza do assunto p/ filtrar perguntas compatíveis."""
    cat = (categoria or "").lower().strip()
    if cat in _NATUREZA_CLARA:
        return _NATUREZA_CLARA[cat]
    if cat in ("objeto", "transporte", "ciencia_tecnologia",
               "tecnologias_emergentes"):
        return "ferramenta" if _e_ferramenta(assunto) else "objeto"
    return "generico"


def _prefixos_compatíveis(categoria: str, assunto: str) -> list[str]:
    """Prefixos da categoria compatíveis com a natureza do assunto.
    NUNCA retorna vazio: se nada sobrar, fallback p/ perguntas de definição
    ("O que é / Para que serve / Como funciona") — válidas p/ qualquer assunto."""
    prefixos = list(PREFIXOS_POR_CATEGORIA.get(categoria) or [])
    natureza = _natureza_assunto(assunto, categoria)
    if natureza == "generico":
        return prefixos  # categoria curada e sem natureza específica: mantém
    compativeis = []
    for p in prefixos:
        stem = (p or "").lower().strip()
        permitidas = _RISCO_PREFIXO_POR_NATUREZA.get(stem)
        if permitidas is None or natureza in permitidas:
            compativeis.append(p)
    if compativeis:
        return compativeis
    # Fallback: perguntas de definição funcionam para QUALQUER substantivo
    seguros = [p for p in prefixos if (p or "").lower().strip() in {
        "o que é", "o que significa", "para que serve", "como funciona",
        "qual a importância de", "o que estuda", "quem foi", "quem é",
        "o que faz", "o que aconteceu", "quem são", "o que é",
    }]
    return seguros or ["O que é"]


# ============================================================================
# COMPATIBILIDADE PERGUNTA × TIPO DE RESPOSTA (formato do texto)
# Pedido do usuário (13/08): a pergunta deve combinar com o TIPO de resposta.
# Ex.: tipo "receita" com assunto "chave philips" não faz sentido; e para o
# tipo "receita" a pergunta certa é "Como preparar X?", não "O que é X?".
# ============================================================================
# Tipos de resposta que valem para QUALQUER assunto (criativos/gerais)
_TIPOS_GERAIS = {
    "dicionario", "pergunta_resposta", "explicacao", "resumo", "artigo", "dica",
    "saudacao", "poema", "conto", "cronica", "ensaio", "carta",
    "iteracao", "conversa", "dialogo_profundo", "debate",
}
# Tipos restritos: só entram quando a natureza do assunto combina
_TIPOS_POR_NATUREZA = {
    "alimento":   {"receita", "tutorial", "resenha"},
    "ferramenta": {"tutorial"},
    "objeto":     {"tutorial", "resenha"},
    "transporte": {"tutorial"},
    "pessoa":     {"entrevista", "relatorio"},
    "obra":       {"resenha", "entrevista", "relatorio"},
    "lugar":      {"relatorio", "entrevista", "resenha"},
    "animal":     {"relatorio"},
    "doenca":     {"relatorio", "tutorial", "resenha"},
    "acao":       {"tutorial", "entrevista"},
    "profissao":  {"entrevista", "tutorial", "relatorio"},
    "sentimento": {"ensaio", "debate", "carta"},
    "conceito":   {"debate", "ensaio", "resenha", "relatorio"},
}


def _tipos_compatíveis(natureza: str, tipos: list[str]) -> list[str]:
    """Filtra os tipos de resposta compatíveis com a natureza do assunto.
    Tipos criativos/gerais valem p/ qualquer assunto; os restritos (receita,
    tutorial, entrevista, resenha, relatorio...) só entram quando a natureza
    combina. NUNCA retorna vazio: fallback p/ os tipos gerais da seleção."""
    if not tipos:
        todos = set(_TIPOS_GERAIS)
        for v in _TIPOS_POR_NATUREZA.values():
            todos |= v
        return sorted(todos)
    if natureza in ("generico", ""):
        return tipos
    permitidos = set(_TIPOS_GERAIS) | set(_TIPOS_POR_NATUREZA.get(natureza, set()))
    compativeis = [t for t in tipos if t in permitidos]
    if compativeis:
        return compativeis
    gerais = [t for t in tipos if t in _TIPOS_GERAIS]
    return gerais or tipos[:1]


# Prefixo preferido da pergunta por tipo de resposta (alinha pergunta ↔ formato)
_PREFIXO_POR_TIPO: dict[str, list[str] | None] = {
    "receita":        ["Como preparar", "Qual a receita de", "Como fazer", "Qual a origem de"],
    "tutorial":       ["Como fazer", "Como usar", "Como escolher", "Como montar", "Como instalar"],
    "dicionario":     ["O que é", "O que significa", "Para que serve"],
    "resenha":        ["O que é", "Qual a importância de", "Qual a história de", "Qual a finalidade de"],
    "entrevista":     ["Quem é", "Quem foi", "Qual a contribuição de", "O que é", "Qual a história de"],
    "relatorio":      ["Qual a importância de", "O que aconteceu", "Como funciona", "O que é", "Como surgiu"],
    "ensaio":         ["O que é", "O que significa", "Qual a importância de"],
    "debate":         ["O que é", "Qual a importância de", "Como funciona", "Quais os benefícios de"],
    "dica":           ["Como usar", "Como escolher", "Como conservar", "Como fazer", "Para que serve"],
    "saudacao":       ["O que é", "Para que serve", "Como funciona"],
    "conversa":       ["O que é", "Como funciona", "Qual a importância de"],
    "iteracao":       ["O que é", "Como funciona", "Qual a importância de"],
    "dialogo_profundo": ["O que é", "Qual a importância de", "Como funciona"],
    "artigo": None, "explicacao": None, "resumo": None,
    "pergunta_resposta": None, "poema": None, "conto": None,
    "cronica": None, "carta": None,
}


def montar_pergunta(categoria: str, assunto: str, tipo_id: str = "") -> Optional[str]:
    """Monta uma pergunta natural usando prefixos/templates da categoria,
    FILTRADOS pela natureza do assunto e — se tipo_id vier — ALINHADOS ao tipo
    de resposta (ex.: receita → "Como preparar X?"; tutorial → "Como usar X?").
    Fallbacks: prefixo compatível → template → "O que é X?"."""
    if not categoria or not assunto:
        return None
    prefixos = _prefixos_compatíveis(categoria, assunto)
    templates = TEMPLATES_EXTRAS.get(categoria) or []
    if not prefixos and not templates:
        return _normalizar_pergunta(f"O que é {assunto}?")
    # Alinha a pergunta ao tipo de resposta quando há preferência (ex.: receita)
    preferidos = _PREFIXO_POR_TIPO.get(tipo_id or "") if tipo_id else None
    if preferidos:
        casados = [p for p in prefixos
                   if any(p.lower().startswith(pref.lower()) for pref in preferidos)]
        if casados:
            prefixos = casados
    # ~15%: pergunta combinada (2 assuntos) — riqueza de variação
    if random.random() < 0.15:
        outro = _sorteia_outro_assunto(categoria, assunto)
        if outro and prefixos:
            prefixo = random.choice(prefixos)
            return _normalizar_pergunta(f"{prefixo} {assunto} e {outro}?")
    # ~55%: prefixo direto
    if prefixos and random.random() < 0.55:
        prefixo = random.choice(prefixos)
        return _normalizar_pergunta(f"{prefixo} {assunto}?")
    # resto: template extra da categoria
    if templates:
        tpl = random.choice(templates)
        return _normalizar_pergunta(tpl.format(assunto=assunto))
    return _normalizar_pergunta(f"O que é {assunto}?")


def amostra_perguntas(categoria: str, n: int = 5) -> list[dict]:
    """Amostra de assuntos + perguntas de uma categoria (prévia no dashboard)."""
    lista = CATEGORIAS_LISTAS.get(categoria) or []
    if not lista:
        return []
    amostra = random.sample(lista, min(max(1, n), len(lista)))
    out = []
    for item in amostra:
        assunto = _item_limpo(item)
        out.append({
            "categoria": categoria,
            "assunto": assunto,
            "pergunta": montar_pergunta(categoria, assunto),
        })
    return out


# ============================================================================
# INSTRUÇÕES POR CATEGORIA (guiam a IA p/ respostas factuais)
# ============================================================================
def obter_instrucoes(categoria: str, assunto: str) -> str:
    if not categoria or not assunto:
        return ""
    cat = categoria.lower().strip()
    a = assunto
    if cat in ("livros", "literatura"):
        return (f"Sobre a obra '{a}', responda de forma detalhada: quem é o autor e o ano de "
                "publicação; o enredo principal sem spoilers; os temas centrais; a importância "
                "ou influência na literatura; os personagens principais.")
    if cat in ("filmes", "series"):
        return (f"Sobre {a}, responda de forma detalhada: quem dirigiu/criou e o ano de "
                "lançamento; o elenco principal; o enredo resumido; os temas principais e o "
                "impacto cultural; prêmios ou indicações importantes.")
    if cat in ("pessoa",):
        return (f"Sobre {a}, responda de forma detalhada: quem foi, nacionalidade e período de "
                "vida; a principal contribuição ou obra; o contexto histórico; o legado e a "
                "importância atual.")
    if cat in ("eventos_historicos_brasil", "historia", "datas_historicas", "geopolitica"):
        return (f"Sobre {a}, responda de forma detalhada: quando e onde aconteceu; as causas e "
                "os participantes; as principais consequências e impactos; a importância histórica.")
    if cat in ("ciencia_tecnologia", "tecnologias_emergentes", "ciencia", "conhecimento", "objeto"):
        return (f"Sobre {a}, responda de forma detalhada e acessível: o que é e como funciona; "
                "criador ou marcos de desenvolvimento; as principais aplicações práticas; os "
                "impactos positivos e negativos para a sociedade.")
    if cat in ("lugar",):
        return (f"Sobre {a}, responda de forma detalhada: onde fica e as principais características "
                "geográficas; história ou curiosidades; pontos turísticos ou aspectos culturais; "
                "a importância econômica ou ecológica.")
    if cat in ("alimento",):
        return (f"Sobre {a}, responda de forma detalhada: origem ou história; como é preparado ou "
                "consumido tradicionalmente; benefícios nutricionais ou curiosidades; variação "
                "regional ou receita famosa.")
    if cat in ("animal",):
        return (f"Sobre {a}, responda de forma detalhada: classificação e habitat; hábitos de "
                "vida; alimentação e reprodução; importância ecológica ou relação com os humanos.")
    if cat in ("arte_cultura", "musica", "mitologia", "povos_originarios"):
        return (f"Sobre {a}, responda de forma detalhada: o que é e sua origem; os principais "
                "representantes ou manifestações; a importância cultural; a influência na "
                "sociedade brasileira.")
    if cat in ("sintomas_doencas",):
        return (f"Sobre {a}, responda de forma clara e objetiva: o que é; os principais sintomas; "
                "formas de prevenção e tratamento; quando procurar ajuda. Não dê diagnóstico "
                "médico definitivo — incentive procurar um profissional de saúde.")
    if cat in ("sociedade_politica", "economia", "ciencias_sociais", "conceito", "sentimento"):
        return (f"Sobre {a}, responda de forma detalhada e equilibrada: o que é e como funciona; "
                "contexto e importância; os principais debates ou desafios; a relação com a vida "
                "das pessoas.")
    if cat in ("natureza_universo",):
        return (f"Sobre {a}, responda de forma detalhada: o que é e como se forma ou funciona; "
                "onde é encontrado; a importância para o planeta; curiosidades.")
    if cat in ("profissao", "acao", "transporte"):
        return (f"Sobre {a}, responda de forma prática e detalhada: o que é ou do que se trata; "
                "como funciona na prática; dicas úteis e exemplos do cotidiano brasileiro.")
    return ""


def montar_prompt_por_pergunta(categoria: str, assunto: str, pergunta: str,
                               tipo_id: str = "pergunta_resposta",
                               estilo_id: str = "neutro") -> str:
    """Monta o prompt COMPLETO para o Ollama responder à pergunta com contexto."""
    try:
        from dashboard.services.templates_conteudo import ESTILOS_ESCRITA
    except Exception:
        ESTILOS_ESCRITA = {}
    estilo = (ESTILOS_ESCRITA or {}).get(estilo_id) or {}
    if not pergunta:
        pergunta = montar_pergunta(categoria, assunto) or assunto or "tema geral"
    blocos = [
        "Responda à seguinte pergunta em português brasileiro de forma natural, "
        f"bem fundamentada e com exemplos concretos:\n\nPergunta: {pergunta}"
    ]
    inst_tipo = INSTRUCAO_TIPO.get(tipo_id, "")
    if inst_tipo:
        blocos.append(f"Formato do texto: {inst_tipo}")
    inst_cat = obter_instrucoes(categoria, assunto)
    if inst_cat:
        blocos.append(f"Contexto: {inst_cat}")
    if estilo.get("instrucao"):
        blocos.append(f"Estilo: {estilo['instrucao']}")
    return "\n\n".join(b for b in blocos if b)


# ============================================================================
# DETECÇÃO DE CATEGORIA (para títulos RSS)
# ============================================================================
def _item_presente(item: str, texto_low: str) -> bool:
    item_s = item.lower().strip()
    if not item_s:
        return False
    if len(item_s) < 4:
        # palavra curta → exige palavra inteira (evita 'rio' dentro de 'periódico')
        return (f" {item_s} " in f" {texto_low} "
                or texto_low.startswith(item_s + " ")
                or texto_low.endswith(" " + item_s))
    return item_s in texto_low


def detectar_categoria(texto: str, top: int = 3) -> list[tuple[str, str, int]]:
    """Detecta as categorias mais prováveis de um texto/título.
    Retorna [(categoria, item_encontrado, hits)] ordenado por hits (maior 1º)."""
    if not texto:
        return []
    t = texto.lower()
    resultados: list[tuple[str, str, int]] = []
    for cat, lista in CATEGORIAS_LISTAS.items():
        hits = 0
        item_achado: Optional[str] = None
        for item in lista:
            item_s = _item_limpo(item)
            if not item_s or len(item_s) < 3:
                continue
            if _item_presente(item_s, t):
                hits += 1
                if item_achado is None:
                    item_achado = item_s
        if hits:
            resultados.append((cat, item_achado or "", hits))
    resultados.sort(key=lambda x: -x[2])
    return resultados[:top]


def _limpar_titulo(titulo: str) -> str:
    """Limpa um título RSS para virar tema (remove sufixos tipo '— X' e pontuação)."""
    t = _normalizar(titulo)
    t = re.sub(r"\s*[—–|]\s*.*$", "", t)  # remove ' — site' / ' | site'
    t = re.sub(r"\s+$", "", t)
    return t or "tema geral"


def gerar_perguntas_relacionadas(titulo: str, n: int = 3) -> list[dict]:
    """Dado um título RSS, detecta a categoria e gera perguntas relacionadas
    usando PREFIXOS_POR_CATEGORIA + TEMPLATES_EXTRAS (aproveita categories.py)."""
    if not titulo:
        return []
    detect = detectar_categoria(titulo)
    if not detect:
        return []
    cat, item, _hits = detect[0]
    assunto = item or _limpar_titulo(titulo)
    # Prefixos compatíveis com a natureza do assunto (evita pergunta errada)
    prefixos = _prefixos_compatíveis(cat, assunto)
    templates = TEMPLATES_EXTRAS.get(cat) or []
    pool = list(prefixos) + list(templates)
    random.shuffle(pool)
    perguntas: list[dict] = []
    for p in pool:
        if len(perguntas) >= n:
            break
        if "{" in p:
            pergunta = p.format(assunto=assunto)
        else:
            pergunta = f"{p} {assunto}?"
        pergunta = _normalizar_pergunta(pergunta)
        perguntas.append({"pergunta": pergunta, "categoria": cat, "assunto": assunto})
    # garante pelo menos 1 pergunta
    if not perguntas:
        perguntas.append({"pergunta": _normalizar_pergunta(f"O que é {assunto}?"),
                          "categoria": cat, "assunto": assunto})
    return perguntas


# ============================================================================
# TÍTULOS RSS (cache 6h + fetch ao vivo)
# ============================================================================
def _ler_feeds() -> list[str]:
    if not FEEDS_PATH.exists():
        return []
    out = []
    try:
        for linha in FEEDS_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and linha.lower().startswith("http"):
                out.append(linha)
    except Exception:
        return []
    return out


def _buscar_titulos_feeds(max_fontes: int = 8) -> list[str]:
    import xml.etree.ElementTree as ET
    feeds = _ler_feeds()[:max_fontes]
    titulos: list[str] = []
    for url in feeds:
        try:
            import httpx
            r = httpx.get(url, timeout=6, follow_redirects=True)
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                t = item.findtext("title")
                if t and t.strip():
                    titulos.append(t.strip())
        except Exception:
            continue
    # dedup preservando ordem
    vistos: set[str] = set()
    unicos: list[str] = []
    for t in titulos:
        chave = t.lower()
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(t)
    return unicos


def carregar_titulos_rss(limite: Optional[int] = None, forcar: bool = False,
                         max_fontes: int = 8) -> list[str]:
    """Carrega títulos RSS (cache de 6h ou fetch ao vivo). Nunca levanta erro."""
    if not forcar and RSS_CACHE.exists():
        try:
            idade = time.time() - RSS_CACHE.stat().st_mtime
            dados = json.loads(RSS_CACHE.read_text(encoding="utf-8"))
            if idade < _RSS_TTL_SEG and dados.get("titulos"):
                titulos = dados["titulos"]
                return titulos[:limite] if limite else titulos
        except Exception:
            pass
    titulos = _buscar_titulos_feeds(max_fontes=max_fontes)
    try:
        RSS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        RSS_CACHE.write_text(
            json.dumps({"data": _agora(), "titulos": titulos}, ensure_ascii=False),
            encoding="utf-8")
    except Exception:
        pass
    return titulos[:limite] if limite else titulos


# ============================================================================
# UTILITÁRIO DE AUTOTESTE (python -m dashboard.services.gerador_categorias)
# ============================================================================
if __name__ == "__main__":
    print(f"📊 Categorias: {len(CATEGORIAS_LISTAS)} | "
          f"Assuntos totais: {contar_assuntos()}")
    for _ in range(5):
        c, a = sortear_par()
        p = montar_pergunta(c, a)
        print(f"  [{c}] {p}")
    print("� Compatibilidade pergunta×assunto (não deve sobrar 'Como conservar' p/ ferramenta):")
    for c, a in [("objeto", "chave Philips"), ("objeto", "furadeira de impacto"),
                 ("objeto", "liquidificador"), ("alimento", "feijoada"),
                 ("sentimento", "ansiedade"), ("sintomas_doencas", "dengue")]:
        print(f"  [{c}] {a} → {_prefixos_compatíveis(c, a)}")
    print("�🔍 Detecção de categoria (títulos RSS de exemplo):")
    for t in ["Impressão 3D revoluciona a construção civil no Brasil",
              "Dengue: casos sobem 40% no verão, alerta Ministério da Saúde",
              "Caetano Veloso lança novo álbum e emociona fãs"]:
        print(f"  • {t!r} → {detectar_categoria(t)}")
    print("📰 Títulos RSS (cache):", len(carregar_titulos_rss(limite=None, forcar=False)))
