#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
generation.py - Núcleo de geração de conteúdo.
Com prompts contextualizados por categoria (livros, filmes, pessoas, etc.)
"""
import random
import time
import re
from typing import Optional, Tuple, List

from config import (
    client,
    MODEL_NAME,
    DELAY_SECONDS,
    verificar_limite,
    registrar_gasto,
    PASTA_DADOS_CURTOS,
    PASTA_DADOS_LONGOS,
    TIPO_CONFIG,
)
from categories import (
    CATEGORIAS_LISTAS,
    GRUPOS_CATEGORIAS,
    PREFIXOS_POR_CATEGORIA,
)
from state import StateManager
from validation import avaliar_qualidade, validar_dialogo, padronizar_formato
from utils import (
    carregar_topicos_externos,
    limpar_texto,
    salvar_texto,
    salvar_descarte,
    hash_texto,
    exibir_categoria,
)


# ============================================================================
# INSTRUÇÕES ESPECÍFICAS POR CATEGORIA
# ============================================================================
def obter_instrucoes_especificas(categoria: str, assunto: str) -> str:
    """
    Retorna um bloco de instruções direcionadas com base na categoria do assunto.
    Isso guia a IA a produzir respostas factuais e específicas, evitando genéricos.
    """
    if not categoria or not assunto:
        return ""

    cat = categoria.lower().strip()

    # ---- LIVROS ----
    if cat in ["livros", "literatura"]:
        return f"""Sobre o livro '{assunto}', responda de forma detalhada:
- Quem é o autor e em que ano foi publicado?
- Qual é o enredo principal (sem spoilers excessivos)?
- Quais são os temas centrais e a mensagem da obra?
- Qual a importância ou influência deste livro na literatura?
- Quem são os personagens principais?"""

    # ---- FILMES ----
    elif cat in ["filmes", "series"]:
        return f"""Sobre o filme/série '{assunto}', responda de forma detalhada:
- Quem dirigiu/criou e em que ano foi lançado?
- Qual é o elenco principal?
- Qual é o enredo resumido?
- Quais são os temas principais e o impacto cultural?
- Recebeu prêmios ou indicações importantes?"""

    # ---- PESSOAS ----
    elif cat in ["pessoa", "pessoas"]:
        return f"""Sobre a pessoa '{assunto}', responda de forma detalhada:
- Quem foi, qual sua nacionalidade e quando viveu (nascimento e morte)?
- Qual foi sua principal contribuição ou obra?
- Qual o contexto histórico em que atuou?
- Qual seu legado e importância atual?"""

    # ---- EVENTOS HISTÓRICOS ----
    elif cat in ["eventos_historicos_brasil", "historia", "datas_historicas", "geopolitica"]:
        return f"""Sobre o evento histórico '{assunto}', responda de forma detalhada:
- Quando e onde aconteceu?
- Quais foram as causas e os participantes envolvidos?
- Quais foram as principais consequências e impactos?
- Qual a importância deste evento para a história?"""

    # ---- TECNOLOGIA E CIÊNCIA ----
    elif cat in ["ciencia_tecnologia", "tecnologias_emergentes", "ciencia", "conhecimento", "objeto"]:
        return f"""Sobre o tema tecnológico/científico '{assunto}', responda de forma detalhada:
- O que é e como funciona (de forma acessível)?
- Quem foi o criador ou quais são os marcos de desenvolvimento?
- Quais são suas principais aplicações práticas?
- Que impactos (positivos ou negativos) traz para a sociedade?"""

    # ---- LUGARES ----
    elif cat in ["lugar", "lugares"]:
        return f"""Sobre o lugar '{assunto}', responda de forma detalhada:
- Onde fica e quais são suas principais características geográficas?
- Qual é a história ou curiosidade sobre este local?
- Quais são os pontos turísticos ou aspectos culturais marcantes?
- Qual a importância econômica ou ecológica deste lugar?"""

    # ---- ALIMENTOS E CULINÁRIA ----
    elif cat in ["alimento", "alimentos"]:
        return f"""Sobre o alimento '{assunto}', responda de forma detalhada:
- Qual é a origem ou história deste alimento?
- Como é preparado ou consumido tradicionalmente?
- Quais são seus benefícios nutricionais ou curiosidades?
- Existe alguma variação regional ou receita famosa?"""

    # ---- ANIMAIS ----
    elif cat in ["animal", "animais"]:
        return f"""Sobre o animal '{assunto}', responda de forma detalhada:
- Qual é sua classificação (espécie, habitat)?
- Onde vive e quais são seus hábitos?
- O que come e como se reproduz?
- Qual sua importância ecológica ou relação com os humanos?"""

    # ---- ARTE E CULTURA ----
    elif cat in ["arte_cultura", "musica", "mitologia"]:
        return f"""Sobre o tema artístico/cultural '{assunto}', responda de forma detalhada:
- Qual é a origem ou contexto histórico deste tema?
- Quais são suas principais características ou elementos?
- Quem são os representantes ou obras mais famosas?
- Qual a importância ou influência cultural?"""

    # ---- ECONOMIA E SOCIEDADE ----
    elif cat in ["economia", "sociedade_politica", "ciencias_sociais", "conceito"]:
        return f"""Sobre o conceito ou tema social/econômico '{assunto}', responda de forma detalhada:
- Qual é a definição ou significado central?
- Como surgiu e quais são os principais teóricos ou marcos?
- Quais são os desafios ou debates atuais sobre este tema?
- Como impacta a vida das pessoas ou a sociedade?"""

    # ---- ESPORTES ----
    elif cat in ["esportes", "acao"]:
        return f"""Sobre o esporte ou atividade '{assunto}', responda de forma detalhada:
- Qual é a origem ou história deste esporte?
- Quais são as regras básicas ou modalidades?
- Quem são os principais atletas ou equipes?
- Qual a importância cultural ou social?"""

    # ---- DEMAIS CATEGORIAS (fallback) ----
    else:
        return f"""Sobre o tema '{assunto}', responda de forma detalhada:
- Defina ou explique o que é este assunto.
- Qual a sua importância ou aplicação prática?
- Quais são os fatos ou curiosidades mais relevantes?
- Como este tema se relaciona com o mundo atual?"""


# ============================================================================
# PROMPTS MELHORADOS – com injunções contextuais
# ============================================================================
def gerar_prompt_pergunta_resposta(tema: str, categoria: str = "", assunto: str = "") -> str:
    instrucoes = obter_instrucoes_especificas(categoria, assunto) if categoria and assunto else ""
    base = f"""Responda à seguinte pergunta em português brasileiro com um texto informativo, bem fundamentado e com exemplos concretos.
Seja direto, evite rodeios e **NÃO** use frases genéricas como "é muito relevante" ou "envolve diversos aspectos".
Se não souber um detalhe específico, forneça uma resposta geral baseada no que sabe, mas sempre com conteúdo factual.

Pergunta: {tema}

"""
    if instrucoes:
        base += f"Instruções específicas:\n{instrucoes}\n\n"
    base += "Sua resposta deve ser um texto corrido, em parágrafos, com no mínimo 150 palavras. Use linguagem formal e inclua dados ou referências históricas sempre que pertinente.\n\nResposta:"
    return base


def gerar_prompt_artigo(tema: str, categoria: str = "", assunto: str = "") -> str:
    instrucoes = obter_instrucoes_especificas(categoria, assunto) if categoria and assunto else ""
    base = f"""Escreva um artigo em português brasileiro sobre o tema: {tema}.

O artigo deve ter introdução, desenvolvimento e conclusão. Seja objetivo, factual e evite opiniões pessoais.
**NÃO** use frases genéricas como "é muito relevante" ou "envolve diversos aspectos".
Use parágrafos curtos e linguagem acessível. Mínimo de 250 palavras.

"""
    if instrucoes:
        base += f"Instruções específicas para este artigo:\n{instrucoes}\n\n"
    base += "Artigo:"
    return base


def gerar_prompt_explicacao(tema: str, categoria: str = "", assunto: str = "") -> str:
    instrucoes = obter_instrucoes_especificas(categoria, assunto) if categoria and assunto else ""
    base = f"""Explique o conceito de {tema} de forma clara e detalhada em português brasileiro.

Use exemplos práticos, analogias e uma estrutura lógica. O texto deve ser didático, como se fosse para um leigo.
**NÃO** use frases genéricas como "é muito relevante". Mínimo de 150 palavras.

"""
    if instrucoes:
        base += f"Instruções específicas:\n{instrucoes}\n\n"
    base += "Explicação:"
    return base


def gerar_prompt_resumo(tema: str, categoria: str = "", assunto: str = "") -> str:
    instrucoes = obter_instrucoes_especificas(categoria, assunto) if categoria and assunto else ""
    base = f"""Faça um resumo conciso e informativo sobre {tema} em português brasileiro.

Destaque os pontos principais de forma objetiva. **NÃO** use frases genéricas. Máximo de 150 palavras.

"""
    if instrucoes:
        base += f"Instruções específicas:\n{instrucoes}\n\n"
    base += "Resumo:"
    return base


def gerar_prompt_dicionario(pergunta: str, categoria: str = "", assunto: str = "") -> str:
    return f"""Responda à pergunta em português brasileiro com uma resposta curta e direta (máximo 2 frases, cerca de 20 palavras). Seja objetivo, não repita a pergunta. **NÃO** use frases genéricas como "é muito relevante".

Pergunta: {pergunta}
Resposta:"""


def gerar_prompt_iteracao(tema: str, categoria: str = "", assunto: str = "") -> str:
    return f"""Crie um diálogo de 4 a 6 turnos em português brasileiro sobre: {tema}.

As falas devem ser naturais, com perguntas e respostas coerentes. **NÃO** use frases genéricas ou introduções vazias. Formato:
Pessoa: [fala]
Outra: [fala]
..."""


def gerar_prompt_dialogo_profundo(tema: str, categoria: str = "", assunto: str = "") -> str:
    return f"""Crie um diálogo profundo de 8 a 12 turnos em português brasileiro sobre: {tema}.

A conversa deve explorar diferentes ângulos do tema, com perguntas de acompanhamento e respostas reflexivas. **NÃO** use frases genéricas. Formato:
Pessoa: [fala]
Outra: [fala]
..."""


def gerar_prompt_conversa(tema: str, categoria: str = "", assunto: str = "") -> str:
    return f"""Crie uma conversa natural e descontraída em português brasileiro sobre: {tema}.

Mínimo de 5 turnos, com expressões coloquiais. **NÃO** use frases genéricas. Formato:
Pessoa 1: [fala]
Pessoa 2: [fala]
..."""


def gerar_prompt_conto(tema: str, categoria: str = "", assunto: str = "") -> str:
    return f"""Crie um conto curto em português brasileiro inspirado no tema: {tema}.

O conto deve ter personagens, um enredo com começo, meio e fim, e uma mensagem ou reflexão. Seja criativo, mas mantenha a coerência. Mínimo de 150 palavras. **NÃO** use frases genéricas ou introdutórias vazias.

Conto:"""


def gerar_prompt(tema: str, tipo: str, categoria: str = "", assunto: str = "", pergunta: Optional[str] = None) -> str:
    if tipo == "conversa":
        return gerar_prompt_conversa(tema, categoria, assunto)
    elif tipo == "pergunta_resposta":
        return gerar_prompt_pergunta_resposta(tema, categoria, assunto)
    elif tipo == "iteracao":
        return gerar_prompt_iteracao(tema, categoria, assunto)
    elif tipo == "artigo":
        return gerar_prompt_artigo(tema, categoria, assunto)
    elif tipo == "conto":
        return gerar_prompt_conto(tema, categoria, assunto)
    elif tipo == "dialogo_profundo":
        return gerar_prompt_dialogo_profundo(tema, categoria, assunto)
    elif tipo == "explicacao":
        return gerar_prompt_explicacao(tema, categoria, assunto)
    elif tipo == "resumo":
        return gerar_prompt_resumo(tema, categoria, assunto)
    elif tipo == "dicionario" and pergunta:
        return gerar_prompt_dicionario(pergunta, categoria, assunto)
    return ""


# ============================================================================
# DETECÇÃO DE RESPOSTA GENÉRICA (DeepSeek)
# ============================================================================
def detectar_resposta_generica(texto: str) -> bool:
    """
    Detecta se a resposta contém a famosa enrolação do DeepSeek.
    Retorna True se for genérica.
    """
    if not texto:
        return True

    padroes = [
        r"envolve diversos aspectos importantes",
        r"contexto histórico e social",
        r"implicações práticas são significativas",
        r"é essencial refletir sobre",
        r"afeta o dia a dia das pessoas",
        r"Lembre-se de que você está conversando com o RigelSLM",
        r"desenvolvido por George Herman Becker",
        r"tema .* é muito relevante",
        r"em primeiro lugar, devemos considerar",
        r"em segundo lugar",
        r"por fim, é essencial",
        r"não tenho informações suficientes",
    ]
    texto_lower = texto.lower()
    for padrao in padroes:
        if re.search(padrao, texto_lower, re.IGNORECASE):
            return True
    # Se o texto tem menos de 30 palavras e não tem conteúdo específico
    if len(texto.split()) < 30 and ("?" not in texto and "!" not in texto):
        return True
    return False


# ============================================================================
# GERAÇÃO DE PERGUNTAS (mantido)
# ============================================================================
_indice_topico_externo = 0
_topicos_externos_cache = None


def _recarregar_topicos_externos() -> List[str]:
    global _topicos_externos_cache
    _topicos_externos_cache = carregar_topicos_externos("topicos.txt")
    return _topicos_externos_cache


def _get_proximo_topico_externo(state: StateManager) -> Optional[str]:
    global _indice_topico_externo, _topicos_externos_cache
    if _topicos_externos_cache is None:
        _recarregar_topicos_externos()
    if not _topicos_externos_cache:
        return None
    for i in range(_indice_topico_externo, len(_topicos_externos_cache)):
        topico = _topicos_externos_cache[i]
        if not state.topico_externo_ja_usado(topico):
            _indice_topico_externo = i + 1
            return topico
    return None


def escolher_categoria_balanceada(state: StateManager) -> str:
    categorias = list(CATEGORIAS_LISTAS.keys())
    if not categorias:
        return random.choice(list(PREFIXOS_POR_CATEGORIA.keys()))
    menor_contagem = min(state.get_contagem_categoria(cat) for cat in categorias)
    candidatas = [cat for cat in categorias if state.get_contagem_categoria(cat) == menor_contagem]
    return random.choice(candidatas)


def escolher_assunto(categoria: str, state: StateManager) -> str:
    lista = CATEGORIAS_LISTAS.get(categoria, [])
    if not lista:
        return "tema"
    candidatos = sorted(lista, key=lambda item: state.get_contagem_assunto(item))
    menor = state.get_contagem_assunto(candidatos[0])
    melhores = [item for item in candidatos if state.get_contagem_assunto(item) == menor]
    return random.choice(melhores)


def escolher_categoria_do_grupo(grupo: str) -> str:
    categorias = GRUPOS_CATEGORIAS.get(grupo, [])
    if not categorias:
        return random.choice(list(CATEGORIAS_LISTAS.keys()))
    return random.choice(categorias)


def gerar_pergunta_combinada(assunto1: str, assunto2: str) -> str:
    templates = [
        "Qual a relação entre {a1} e {a2}?",
        "Como {a1} influencia {a2}?",
        "Quais as diferenças entre {a1} e {a2}?",
        "O que {a1} tem em comum com {a2}?",
        "Explique a importância de {a1} no contexto de {a2}.",
        "Como a evolução de {a1} afetou {a2}?",
        "Compare {a1} e {a2}.",
        "Qual o papel de {a1} na história de {a2}?",
        "De que forma {a1} se relaciona com {a2}?",
        "O que podemos aprender com a relação entre {a1} e {a2}?",
        "Como {a1} e {a2} se complementam?",
        "Por que {a1} é considerado importante para {a2}?",
        "Que impacto {a1} teve sobre {a2}?",
        "Em que medida {a1} é semelhante a {a2}?",
        "Como {a1} pode ser usado para entender {a2}?",
    ]
    template = random.choice(templates)
    pergunta = template.format(a1=assunto1, a2=assunto2)
    if not pergunta.endswith("?"):
        pergunta += "?"
    return pergunta


def gerar_pergunta_simples(state: StateManager) -> Optional[Tuple[str, str, str]]:
    categoria = escolher_categoria_balanceada(state)
    assunto = escolher_assunto(categoria, state)
    prefixos = PREFIXOS_POR_CATEGORIA.get(categoria, ["O que é"])
    prefixo = random.choice(prefixos)

    if prefixo in ("Qual a diferença entre", "Como escolher", "Compare"):
        outro = escolher_assunto(categoria, state)
        tent = 0
        while outro == assunto and tent < 10:
            outro = escolher_assunto(categoria, state)
            tent += 1
        pergunta = f"{prefixo} {assunto} e {outro}?"
    else:
        pergunta = f"{prefixo} {assunto}?"

    pergunta = pergunta[0].upper() + pergunta[1:]
    if not pergunta.endswith("?"):
        pergunta += "?"
    pergunta = re.sub(r"\s+", " ", pergunta).strip()

    if len(pergunta.split()) < 4 or state.tema_ja_usado(pergunta):
        return None
    return pergunta, categoria, assunto


def gerar_pergunta_sobre_topico(topico: str) -> str:
    templates = [
        f"Explique o que é {topico}.",
        f"Qual a importância de {topico}?",
        f"Como {topico} impacta a sociedade?",
        f"Quais são os principais fatos sobre {topico}?",
        f"Descreva a história por trás de {topico}.",
        f"O que você sabe sobre {topico}?",
        f"Por que {topico} é relevante atualmente?",
        f"Quais as controvérsias envolvendo {topico}?",
        f"Quem são os principais envolvidos em {topico}?",
        f"O que aconteceu em {topico}?",
        f"Quais os desdobramentos de {topico}?",
    ]
    return random.choice(templates)


def gerar_pergunta_dinamica_v5(state: StateManager) -> Tuple[str, str, str]:
    topico_externo = _get_proximo_topico_externo(state)
    if topico_externo:
        state.registrar_topico_externo_usado(topico_externo)
        pergunta = gerar_pergunta_sobre_topico(topico_externo)
        return pergunta, "externo", topico_externo

    for _ in range(40):
        if random.random() < 0.30:
            grupo = random.choice(list(GRUPOS_CATEGORIAS.keys()))
            cat1 = escolher_categoria_do_grupo(grupo)
            cat2 = escolher_categoria_do_grupo(grupo)
            assunto1 = escolher_assunto(cat1, state)
            assunto2 = escolher_assunto(cat2, state)
            tentativas = 0
            while assunto2 == assunto1 and tentativas < 20:
                assunto2 = escolher_assunto(cat2, state)
                tentativas += 1
            if assunto1 != assunto2:
                pergunta = gerar_pergunta_combinada(assunto1, assunto2)
                if not state.tema_ja_usado(pergunta):
                    return pergunta, "combinada", f"{assunto1}|{assunto2}"
        resultado = gerar_pergunta_simples(state)
        if resultado:
            return resultado

    return "O que é tecnologia?", "conceito", "tecnologia"


# ============================================================================
# EXTRAÇÃO E FALLBACK
# ============================================================================
def extrair_resposta(texto: str) -> Tuple[str, str]:
    if not texto:
        return "", ""
    texto = limpar_texto(texto)
    if "Pergunta:" in texto and "Resposta:" in texto:
        partes = texto.split("Resposta:", 1)
        if len(partes) > 1:
            resp = partes[1].strip()
            pergunta_parte = texto.split("Pergunta:", 1)
            pergunta_extra = pergunta_parte[1].split("Resposta:", 1)[0].strip() if len(pergunta_parte) > 1 else ""
            return resp, pergunta_extra
    if "Resposta:" in texto:
        return texto.split("Resposta:", 1)[1].strip(), ""
    if texto.startswith("Resposta:"):
        return texto[9:].strip(), ""
    return texto.strip(), ""


def gerar_fallback(tipo: str, pergunta: Optional[str], tema: str) -> Tuple[str, float, int, int, Optional[str], Optional[str], Optional[str]]:
    # Fallback enxuto, sem enrolação
    if tipo == "pergunta_resposta":
        return f"{tema} – Resumo breve: informações limitadas disponíveis.", 0.0, 0, 0, None, "fallback", None
    elif tipo == "artigo":
        return f"Artigo sobre {tema}. Conteúdo não disponível.", 0.0, 0, 0, None, "fallback", None
    elif tipo == "conto":
        return f"Uma história sobre {tema}.", 0.0, 0, 0, None, "fallback", None
    elif tipo == "explicacao":
        return f"{tema} – visão geral do conceito.", 0.0, 0, 0, None, "fallback", None
    elif tipo == "dicionario" and pergunta:
        return f"Pergunta: {pergunta}\nResposta: Informação indisponível no momento.", 0.0, 0, 0, None, "fallback", None
    else:
        return f"Diálogo sobre {tema}.", 0.0, 0, 0, None, "fallback", None


# ============================================================================
# GERAÇÃO PRINCIPAL (COM PROMPT CONTEXTUALIZADO)
# ============================================================================
def gerar_dialogo(
    tema: str,
    tipo: str,
    state: StateManager,
    categoria: str = "",
    assunto: str = "",
    pergunta: Optional[str] = None,
    tentativas_max: int = 5,
) -> Tuple[Optional[str], float, int, int, Optional[str], Optional[str], Optional[str]]:
    config = TIPO_CONFIG.get(tipo, TIPO_CONFIG["dicionario"])
    tokens = config["tokens"]
    temps = config["temps"]

    for tentativa in range(tentativas_max):
        max_tokens = tokens[min(tentativa, len(tokens) - 1)]
        temperature = temps[min(tentativa, len(temps) - 1)]

        prompt = gerar_prompt(tema, tipo, categoria, assunto, pergunta)
        if not prompt:
            continue

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.9
            )
            texto = response.choices[0].message.content or ""
            finish_reason = response.choices[0].finish_reason
            tokens_entrada = getattr(response.usage, "prompt_tokens", 0)
            tokens_saida = getattr(response.usage, "completion_tokens", 0)
            custo = (tokens_entrada / 1e6) * 0.14 + (tokens_saida / 1e6) * 0.28

            if not texto.strip():
                continue

            # --- DETECTA RESPOSTA GENÉRICA ---
            if detectar_resposta_generica(texto):
                print(f"   ⚠️ Resposta genérica na tentativa {tentativa+1}, tentando novamente...")
                time.sleep(1)
                continue

            # --- VALIDAÇÃO ESPECÍFICA ---
            if tipo in ["iteracao", "dialogo_profundo", "conversa"]:
                texto = padronizar_formato(texto)
                valido, motivo = validar_dialogo(texto, tipo)
                if not valido:
                    continue

            if tipo == "dicionario":
                resposta, pergunta_extra = extrair_resposta(texto)
                resposta = limpar_texto(resposta)
                if not resposta or detectar_resposta_generica(resposta):
                    continue
                valido, motivo = avaliar_qualidade(resposta, tipo, finish_reason)
                if not valido:
                    continue
                pergunta_final = pergunta_extra or pergunta or "Pergunta"
                texto_final = f"Pergunta: {pergunta_final}\nResposta: {resposta}"
                return texto_final, custo, tokens_entrada, tokens_saida, None, None, finish_reason

            # --- VALIDAÇÃO GERAL ---
            valido, motivo = avaliar_qualidade(texto, tipo, finish_reason)
            if not valido:
                if "muito curto" in motivo and len(texto.split()) > 30:
                    return texto, custo, tokens_entrada, tokens_saida, None, None, finish_reason
                continue

            return texto, custo, tokens_entrada, tokens_saida, None, None, finish_reason

        except Exception as e:
            print(f"   ⚠️ Erro na tentativa {tentativa+1}: {e}")
            time.sleep(2 ** (tentativa + 1))

    return gerar_fallback(tipo, pergunta, tema)


# ============================================================================
# GERAÇÃO DE LOTE
# ============================================================================
def gerar_lote(tipo: str, quantidade: int, prefixo: str, state: StateManager, delay: float = DELAY_SECONDS) -> Tuple[int, int, float]:
    from tqdm import tqdm
    total_gerados = 0
    total_descartes = 0
    gasto_execucao = 0.0
    motivos = {}

    print(f"\n🚀 Gerando {quantidade} itens do tipo '{tipo}'...")

    with tqdm(total=quantidade, desc=f"Gerando {tipo}") as pbar:
        while total_gerados < quantidade:
            if not verificar_limite():
                break

            pergunta, categoria, assunto = gerar_pergunta_dinamica_v5(state)
            tema = f"{categoria}: {assunto}"

            texto, custo, tokens_in, tokens_out, _, _, _ = gerar_dialogo(
                tema=tema,
                tipo=tipo,
                state=state,
                categoria=categoria,
                assunto=assunto,
                pergunta=pergunta,
                tentativas_max=5
            )

            if texto is None:
                total_descartes += 1
                motivos["falha_total"] = motivos.get("falha_total", 0) + 1
                pbar.update(1)
                time.sleep(delay * 0.5)
                continue

            # Segurança extra: detecta genérico novamente
            if detectar_resposta_generica(texto):
                total_descartes += 1
                motivos["generica"] = motivos.get("generica", 0) + 1
                pbar.update(1)
                time.sleep(delay * 0.5)
                continue

            # Verifica duplicata
            h = hash_texto(texto)
            if state.dialogo_ja_processado(h):
                total_descartes += 1
                motivos["duplicado"] = motivos.get("duplicado", 0) + 1
                pbar.update(1)
                time.sleep(delay * 0.5)
                continue

            # Define pasta
            palavras = len(texto.split())
            pasta = PASTA_DADOS_LONGOS if palavras >= 150 else PASTA_DADOS_CURTOS

            # Salva
            salvar_texto(texto, prefixo, total_gerados, pasta)

            # Registra estado
            state.registrar_item(
                pergunta=pergunta,
                resposta=texto,
                categoria=categoria,
                assunto=assunto,
                texto_hash=h,
                custo=custo
            )

            if custo > 0:
                registrar_gasto(custo, tokens_in, tokens_out, tema, tipo)
                gasto_execucao += custo

            total_gerados += 1
            pbar.update(1)
            pbar.set_postfix({
                "ok": total_gerados,
                "desc": total_descartes,
                "custo": f"${state.get_total_gasto():.4f}"
            })
            time.sleep(delay)

    if motivos:
        print("\n📋 Motivos de descarte:")
        for motivo, count in motivos.items():
            print(f"   - {motivo}: {count}")

    return total_gerados, total_descartes, gasto_execucao


def listar_temas() -> None:
    for cat, lista in CATEGORIAS_LISTAS.items():
        exibir_categoria(f"🔹 {cat.upper()}:", lista)


# ============================================================================
# EXPORT
# ============================================================================
__all__ = [
    "gerar_pergunta_dinamica_v5",
    "gerar_dialogo",
    "gerar_lote",
    "listar_temas",
]