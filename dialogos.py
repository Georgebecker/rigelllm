#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dialogos.py - Gerador de dados sintéticos para RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
EXPANSÃO COMPLETA: todas as listas originais + novas.
Autor: George Herman Becker
VERSÃO II: geração de perguntas com classificação inteligente e intenção.
"""

import os
import sys
import re
import json
import time
import random
import argparse
import hashlib
import logging
import httpx
from collections import Counter, deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

# ============================================================================
# 0. CONFIGURAÇÃO DE PASTAS E ARQUIVOS
# ============================================================================
PASTA_SAIDA = "dados/gerados"
PASTA_DADOS_CURTOS = os.path.join(PASTA_SAIDA, "curtos")
PASTA_DADOS_LONGOS = os.path.join(PASTA_SAIDA, "longos")
PASTA_LOGS = os.path.join(PASTA_SAIDA, "logs")
PASTA_DESCARTES = "dados/descartados"
PASTA_ESTADO = os.path.join(PASTA_SAIDA, "estado")
PASTA_CACHE = os.path.join(PASTA_ESTADO, "cache")

for pasta in [PASTA_SAIDA, PASTA_DADOS_CURTOS, PASTA_DADOS_LONGOS, PASTA_LOGS,
              PASTA_DESCARTES, PASTA_ESTADO, PASTA_CACHE]:
    os.makedirs(pasta, exist_ok=True)

ARQUIVO_GASTOS = os.path.join(PASTA_LOGS, "gastos.json")
ARQUIVO_LOG = os.path.join(PASTA_LOGS, "dialogos.log")
ARQUIVO_HISTORICO = os.path.join(PASTA_LOGS, "dialogos_historico.json")
ARQUIVO_HISTORICO_TEMAS = os.path.join(PASTA_ESTADO, "historico_temas.json")
ARQUIVO_HISTORICO_RESPOSTAS = os.path.join(PASTA_ESTADO, "historico_respostas.json")
ARQUIVO_CONTAGEM_CATEGORIAS = os.path.join(PASTA_ESTADO, "contagem_categorias.json")
ARQUIVO_CONTAGEM_ASSUNTOS = os.path.join(PASTA_ESTADO, "contagem_assuntos.json")
ARQUIVO_METADADOS = os.path.join(PASTA_ESTADO, "metadados_gerados.json")
ARQUIVO_CACHE_TEMAS = os.path.join(PASTA_CACHE, "temas_usados.json")
ARQUIVO_CACHE_RESPOSTAS = os.path.join(PASTA_CACHE, "respostas_cache.json")

# ============================================================================
# 1. CONFIGURAÇÃO DE TOKENS E QUALIDADE
# ============================================================================
TOKENS_BASE_DICIONARIO = 512
TOKENS_ESCALONADOS_DICIONARIO = [512, 768, 1024]

TOKENS_BASE_PERGUNTA_RESPOSTA = 1024
TOKENS_ESCALONADOS_PERGUNTA_RESPOSTA = [1024, 1280, 1536]

TOKENS_BASE_CONVERSA = 1024
TOKENS_ESCALONADOS_CONVERSA = [1024, 1280, 1536]

TOKENS_BASE_ITERACAO = 768
TOKENS_ESCALONADOS_ITERACAO = [768, 1024, 1280]

TOKENS_BASE_ARTIGO = 1024
TOKENS_ESCALONADOS_ARTIGO = [1024, 1280, 1536]

TOKENS_BASE_CONTO = 1024
TOKENS_ESCALONADOS_CONTO = [1024, 1280, 1536]

TOKENS_BASE_DIALOGO_PROFUNDO = 1024
TOKENS_ESCALONADOS_DIALOGO_PROFUNDO = [1024, 1280, 1536]

TOKENS_BASE_EXPLICACAO = 1024
TOKENS_ESCALONADOS_EXPLICACAO = [1024, 1280, 1536]

TOKENS_BASE_RESUMO = 768
TOKENS_ESCALONADOS_RESUMO = [768, 1024, 1280]

TOKENS_BASE_POEMA = 512
TOKENS_ESCALONADOS_POEMA = [512, 768, 1024]

TOKENS_BASE_CARTA = 768
TOKENS_ESCALONADOS_CARTA = [768, 1024, 1280]

TOKENS_BASE_ENTREVISTA = 1024
TOKENS_ESCALONADOS_ENTREVISTA = [1024, 1280, 1536]

TOKENS_BASE_DEBATE = 1024
TOKENS_ESCALONADOS_DEBATE = [1024, 1280, 1536]

TOKENS_BASE_TUTORIAL = 1024
TOKENS_ESCALONADOS_TUTORIAL = [1024, 1280, 1536]

TOKENS_BASE_RESENHA = 1024
TOKENS_ESCALONADOS_RESENHA = [1024, 1280, 1536]

TOKENS_BASE_RELATORIO = 1024
TOKENS_ESCALONADOS_RELATORIO = [1024, 1280, 1536]

TOKENS_BASE_ENSAIO = 1024
TOKENS_ESCALONADOS_ENSAIO = [1024, 1280, 1536]

TOKENS_BASE_CRONICA = 768
TOKENS_ESCALONADOS_CRONICA = [768, 1024, 1280]

TOKENS_BASE_RECEITA = 512
TOKENS_ESCALONADOS_RECEITA = [512, 768, 1024]

TOKENS_BASE_DICA = 512
TOKENS_ESCALONADOS_DICA = [512, 768, 1024]

LIMITE_PALAVRAS_CURTOS = 40
LIMITE_PALAVRAS_LONGOS = 150

MAX_ITENS_REPETICAO_RECENTE = 1000
MAX_COST_USD = 5.00
DELAY_SECONDS = 2.0
CACHE_EXPIRATION_DAYS = 7

# ============================================================================
# 2. CLASSE Args
# ============================================================================
class Args:
    def __init__(self):
        self.tipo: str = "dicionario"
        self.quantidade: int = 500
        self.prefixo: str = "dialogo"
        self.delay: float = 2.0
        self.limite: float = 5.0
        self.tema: Optional[str] = None
        self.listar_temas: bool = False
        self.limpar_invalidos: bool = False
        self.validar: bool = False
        self.ver_logs: bool = False
        self.estatisticas: bool = False
        self.modelo: str = "deepseek"
        self.pasta_saida: str = PASTA_SAIDA

        self.max_tokens_base: int = 512
        self.max_tokens_extra: List[int] = [512, 768, 1024]
        self.max_tokens_pr_base: int = 1024
        self.max_tokens_pr_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_it_base: int = 768
        self.max_tokens_it_extra: List[int] = [768, 1024, 1280]
        self.max_tokens_art_base: int = 1024
        self.max_tokens_art_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_conto_base: int = 1024
        self.max_tokens_conto_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_dp_base: int = 1024
        self.max_tokens_dp_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_expl_base: int = 1024
        self.max_tokens_expl_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_resumo_base: int = 768
        self.max_tokens_resumo_extra: List[int] = [768, 1024, 1280]
        self.max_tokens_poema_base: int = 512
        self.max_tokens_poema_extra: List[int] = [512, 768, 1024]
        self.max_tokens_carta_base: int = 768
        self.max_tokens_carta_extra: List[int] = [768, 1024, 1280]
        self.max_tokens_entrevista_base: int = 1024
        self.max_tokens_entrevista_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_debate_base: int = 1024
        self.max_tokens_debate_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_tutorial_base: int = 1024
        self.max_tokens_tutorial_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_resenha_base: int = 1024
        self.max_tokens_resenha_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_relatorio_base: int = 1024
        self.max_tokens_relatorio_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_ensaio_base: int = 1024
        self.max_tokens_ensaio_extra: List[int] = [1024, 1280, 1536]
        self.max_tokens_cronica_base: int = 768
        self.max_tokens_cronica_extra: List[int] = [768, 1024, 1280]
        self.max_tokens_receita_base: int = 512
        self.max_tokens_receita_extra: List[int] = [512, 768, 1024]
        self.max_tokens_dica_base: int = 512
        self.max_tokens_dica_extra: List[int] = [512, 768, 1024]

# ============================================================================
# 3. LISTAS TEMÁTICAS (TODAS ORIGINAIS + NOVAS)
# ============================================================================
OBJETOS = [
    "computador", "smartphone", "televisão", "geladeira", "fogão",
    "micro-ondas", "liquidificador", "ventilador", "ar-condicionado",
    "máquina de lavar", "secadora", "ferro de passar", "aspirador de pó",
    "máquina de café", "torradeira", "chaleira elétrica", "panela de pressão",
    "fritadeira elétrica", "air fryer", "processador de alimentos",
    "batedeira", "espremedor", "cafeteira", "filtro de água",
    "lâmpada", "interruptor", "tomada", "carregador", "bateria",
    "pilha", "cabo USB", "fone de ouvido", "caixa de som", "microfone",
    "câmera", "projetor", "monitor", "teclado", "mouse", "impressora",
    "scanner", "roteador", "modem", "smartwatch", "tablet", "kindle",
    "automóvel", "bicicleta", "ônibus", "metrô", "trem", "avião",
    "navio", "barco", "caiaque", "prancha de surfe", "skate", "patins",
    "bola", "raquete", "taco", "rede", "luvas", "capacete", "óculos",
    "relógio", "caneta", "lápis", "borracha", "régua", "compasso",
    "tesoura", "faca", "garfo", "colher", "prato", "copo", "xícara",
    "pote", "panela", "frigideira", "tábua de corte", "ralador",
    "abridor de latas", "saca-rolhas", "espremedor de alho", "peneira",
    "escova", "pente", "secador de cabelo", "barbeador", "escova de dentes",
    "fio dental", "enxaguante bucal", "sabonete", "shampoo", "condicionador",
    "hidratante", "protetor solar", "desodorante", "perfume", "maquiagem",
    "esmalte", "alicate", "chave de fenda", "martelo", "serrote", "furadeira",
    "parafuso", "prego", "porca", "arruela", "chave inglesa",
    "smart TV", "notebook", "e-reader", "drone", "robô aspirador",
    "purificador de ar", "umidificador", "lavadora de louças",
    "fogão a indução", "forno elétrico", "grill", "churrasqueira elétrica",
    "impressora 3D", "scanner 3D", "kit de robótica", "placa Arduino", "Raspberry Pi",
    "projetor holográfico", "óculos de realidade virtual", "capacete de realidade aumentada",
    "drone agrícola", "veículo elétrico", "bicicleta elétrica", "patinete elétrico",
    "cadeira de rodas motorizada", "prótese robótica", "exoesqueleto",
    "smartwatch com ECG", "monitor de glicose", "termômetro digital", "oxímetro",
    "vassoura", "rodo", "balde", "pano de chão", "esponja",
    "detergente", "sabão em pó", "amaciante", "água sanitária", "desinfetante",
    "lustra-móveis", "cera",
    "mesa", "cadeira", "sofá", "poltrona", "cama",
    "guarda-roupa", "cômoda", "estante", "prateleira", "escrivaninha",
    "bancada", "armário", "cortina", "tapete", "almofada",
    "cobertor", "lençol", "travesseiro", "colchão",
    "leiteira", "bule", "coador de café", "filtro de papel", "pano de prato",
    "luva de forno", "pegador de massa", "escorredor de macarrão", "descascador", "abridor de vinho",
    "caderno", "agenda", "calculadora", "mochila", "lancheira",
    "estojo", "lápis de cor", "giz de cera", "canetinha", "transferidor",
    "esquadro", "prancheta", "pasta (arquivo)", "grampeador", "furador",
    "clipe", "elástico", "cola", "fita adesiva", "etiquetadora",
    "carimbo", "caderno de chamadas", "lousa branca", "apagador", "giz",
    "livro didático", "apostila", "dicionário", "enciclopédia", "mapa-múndi",
    "globo terrestre", "bússola",
    "cadeira ergonômica", "luminária de mesa", "calculadora financeira", "arquivo suspenso", "pastas organizadoras",
    "berço", "carrinho de bebê", "bebê conforto", "cadeirinha de alimentação", "mamadeira",
    "chupeta", "fralda descartável", "lenço umedecido", "pomada de assadura", "bloco de montar",
    "quebra-cabeça infantil", "boneca", "carrinho de brinquedo", "bola de borracha", "jogo de tabuleiro",
    "algodão", "hastes flexíveis", "cortador de unhas", "lixa de unha", "alicate de cutícula",
    "lâmina de barbear", "espuma de barbear", "pós-barba", "absorvente", "sutiã",
    "calcinha", "meia-calça", "bolsa (acessório)", "escova de cabelo", "modelador de cachos",
    "ração para cães", "coleira", "guia para passeio", "comedouro para pet", "bebedouro para pet",
    "petisco para cão", "brinquedo de roer", "caminha para cachorro", "tapete higiênico", "shampoo para cães",
    "escova para pelos", "pente para pelos",
    "peteca", "frisbee", "raquete de tênis", "rede de vôlei", "luvas de goleiro",
    "chave de boca", "chave allen", "alicate de pressão", "estilete", "tesoura de poda",
    "luvas de jardinagem", "vaso de planta", "substrato", "adubo", "regador",
    "pá", "enxada", "espeto de churrasco", "carvão", "isqueiro",
    "fósforo", "vela", "incenso", "difusor de aromas",
    "power bank", "adaptador de tomada", "hub USB", "cabo HDMI", "cabo de rede (Ethernet)",
    "mouse pad", "suporte para smartphone", "suporte para notebook", "webcam", "leitor de cartões",
    "motocicleta", "caminhão", "trator",
    "binóculo", "microscópio", "telescópio", "barômetro", "higrômetro",
    "máquina de costura", "linha", "agulha", "alfinetes", "dedal",
    "tesoura de tecido", "fita métrica",
    "espelho", "cabide", "gancho", "cordão", "cadeado",
    "chaveiro", "porta-retrato", "despertador", "lixeira", "cesto de roupa suja",
    "espanador", "pá de lixo", "batedor de ovos", "ralador de queijo", "abridor de garrafa"
]

LUGARES = [
    "Brasil", "Amazônia", "Pantanal", "Cerrado", "Mata Atlântica", "Caatinga", "Pampa",
    "São Paulo", "Rio de Janeiro", "Salvador", "Brasília", "Curitiba", "Florianópolis",
    "Porto Alegre", "Belo Horizonte", "Manaus", "Recife", "Fortaleza", "Natal",
    "Deserto do Saara", "Himalaia", "Monte Everest", "Rio Nilo", "Cordilheira dos Andes",
    "Canal do Panamá", "Groenlândia", "Estreito de Bering",
    "Amazonas", "Pará", "Mato Grosso", "Minas Gerais", "Bahia", "Pernambuco", "Ceará",
    "Rio Grande do Sul", "Santa Catarina", "Paraná", "Goiás", "Mato Grosso do Sul",
    "Acre", "Rondônia", "Roraima", "Amapá", "Tocantins", "Maranhão", "Piauí",
    "Rio Grande do Norte", "Paraíba", "Sergipe", "Alagoas", "Espírito Santo",
    "Argentina", "Estados Unidos", "Canadá", "México", "Colômbia", "Chile", "Peru",
    "França", "Alemanha", "Itália", "Portugal", "Reino Unido", "Espanha",
    "Japão", "China", "Índia", "África do Sul", "Egito", "Austrália",
    "Cristo Redentor", "Pão de Açúcar", "Igreja da Pampulha", "Catedral de Brasília",
    "Teatro Amazonas", "Estádio do Maracanã", "MASP", "Parque Ibirapuera",
    "Serra da Mantiqueira", "Chapada Diamantina", "Lençóis Maranhenses", "Fernando de Noronha",
    "Bonito (MS)", "Cataratas do Iguaçu", "Parque Nacional da Tijuca", "Jardim Botânico do Rio",
    "Ouro Preto", "Tiradentes", "Paraty", "Salvador (Pelourinho)", "Recife Antigo",
    "Olinda", "São Luís do Maranhão", "Alcântara", "Cabo Frio", "Arraial do Cabo",
    "Ilha de Marajó", "Ilha do Mel", "Ilha de Itaparica", "Ilha de Santa Catarina",
    "Litoral do Ceará", "Praia de Jericoacoara", "Praia de Porto de Galinhas",
    "Praia do Rosa", "Praia da Pipa", "Praia do Forte", "Praia de Copacabana",
    "Avenida Paulista", "Parque do Ibirapuera", "Rua 25 de Março", "Mercado Municipal de SP",
    "Estaçao da Luz", "Pinacoteca", "Museu do Ipiranga",
    "Casa de Rui Barbosa", "Palácio do Catete", "Quinta da Boa Vista",
    "Petrópolis", "Teresópolis", "Nova Friburgo", "Búzios", "Cabo Frio",
    "Angra dos Reis", "Paraty", "Ubatuba", "Ilhabela", "Caraguatatuba",
    "Santos", "Guarujá", "Bertioga", "São Sebastião",
]

PESSOAS = [
    "Dom Pedro I", "Dom Pedro II", "Tiradentes", "Getúlio Vargas", "Santos Dumont",
    "César Lattes", "Oswaldo Cruz", "Machado de Assis", "Clarice Lispector",
    "Carlos Drummond de Andrade", "Tarsila do Amaral", "Portinari", "Glauber Rocha",
    "Sócrates", "Platão", "Aristóteles", "Immanuel Kant", "Friedrich Nietzsche",
    "Karl Marx", "Napoleão Bonaparte", "Albert Einstein", "Isaac Newton",
    "Juscelino Kubitschek", "Tancredo Neves", "Luiz Inácio Lula da Silva", "Dilma Rousseff",
    "Fernando Henrique Cardoso", "José Sarney", "Itamar Franco", "Fernando Collor",
    "Marina Silva", "Ciro Gomes", "Eduardo Suplicy", "Marta Suplicy",
    "Zilda Arns", "Paulo Freire", "Anísio Teixeira", "Darcy Ribeiro",
    "Heitor Villa-Lobos", "Tom Jobim", "Vinícius de Moraes", "Caetano Veloso",
    "Gilberto Gil", "Chico Buarque", "Milton Nascimento", "Elis Regina",
    "Nelson Mandela", "Martin Luther King", "Mahatma Gandhi", "Che Guevara",
    "Frida Kahlo", "Diego Rivera", "Pablo Picasso", "Vincent van Gogh",
    "Neymar", "Pelé", "Ayrton Senna", "Guga", "Marta",
    "George Herman Becker", "Monteiro Lobato", "Mário de Andrade", "Oswald de Andrade",
    "Manuel Bandeira", "Cecília Meireles", "João Cabral de Melo Neto", "Ferreira Gullar",
    "Adélia Prado", "Rubem Braga", "Nelson Rodrigues", "Dias Gomes",
    "Gianfrancesco Guarnieri", "Augusto Boal", "Zé Celso", "Antunes Filho",
    "Fábio Porchat", "Tatá Werneck", "Sabrina Sato", "Xuxa", "Gugu Liberato",
    "Fausto Silva", "Silvio Santos", "Hebe Camargo", "Dercy Gonçalves",
    "Chico Anysio", "Jô Soares", "Ziraldo", "Mauricio de Sousa", "Ataíde",
    "Aleijadinho", "Mestre Valentim", "Cândido Portinari", "Di Cavalcanti",
    "Alfredo Volpi", "Iberê Camargo", "Frans Krajcberg", "Tomie Ohtake",
    "Manabu Mabe", "Vik Muniz", "Oscar Niemeyer", "Lúcio Costa",
    "Paulo Mendes da Rocha", "Ruy Ohtake", "Sérgio Rodrigues", "Zanine Caldas",
    "Joaquim Tenreiro", "José de Alencar", "Graciliano Ramos", "Jorge Amado",
    "Guimarães Rosa", "Rachel de Queiroz", "Lygia Fagundes Telles", "Ana Maria Machado",
    "Ruth Rocha", "Sérgio Buarque de Holanda", "Gilberto Freyre", "Caio Prado Júnior",
    "Florestan Fernandes", "Ruy Barbosa", "Joaquim Nabuco", "Euclides da Cunha",
    "Lima Barreto", "Antônio Callado", "Rubem Fonseca", "Moacyr Scliar",
    "Fernando Sabino", "Otto Lara Resende", "Paulo Mendes Campos", "Carlos Heitor Cony",
    "Nelson Motta", "Ronaldo Correia de Brito", "Milton Hatoum", "Chico Buarque",
    "Ferreira Gullar", "João Ubaldo Ribeiro", "Patrícia Rehder Galvão", "Sônia Coutinho",
    "Roberto Drummond", "José J. Veiga", "Cícero Sandroni", "Ignácio de Loyola Brandão",
    "Rosa Amanda Strausz", "Stella Maris Rezende", "Ronaldo Simões Coelho", "Luís Fernando Veríssimo",
    "Jô Soares", "Millôr Fernandes", "Ziraldo", "Ivan Lessa", "Cláudio Abramo",
    "Mino Carta", "Ferreira de Castro", "Edgar Allan Poe", "Jane Austen", "Charles Dickens",
    "Fiódor Dostoiévski", "Liev Tolstói", "Virginia Woolf", "James Joyce", "Gabriel García Márquez",
    "Jorge Luis Borges", "Mario Vargas Llosa", "Isabel Allende", "Eduardo Galeano", "Mia Couto",
    "Euclides da Cunha", "Machado de Assis", "Aluísio Azevedo", "José Lins do Rego", "Érico Veríssimo",
    "Ciro dos Anjos", "Cyro Martins", "José Mauro de Vasconcelos", "Lygia Bojunga", "Ziraldo",
    "Henrique de Siqueira", "Anita Malfatti", "Aracy de Carvalho", "Leão", "Iberê Camargo",
    "Lygia Clark", "Hélio Oiticica", "Wanda Pimentel", "Carlos Bracher", "Amilcar de Castro",
    "Mira Schendel", "Sérgio Camargo", "Alberto da Veiga Guignard", "Djanira", "Cicillo Matarazzo",
    "Dudi Maia Rosa", "Waldemar Cordeiro", "Geraldo de Barros", "Fayga Ostrower", "Hilário Júnior",
    "Célio de Souza", "Rogério Paiva", "Itamar Assumpção", "Arrigo Barnabé", "Wagner Tiso",
    "Egberto Gismonti", "Hermeto Pascoal", "Airto Moreira", "Milton Nascimento", "Flávio Venturini",
    "Toninho Horta", "Nivaldo Ornelas", "Paulo Moura", "Yamandú Costa", "Marcus Miller",
    "Dominguinhos", "Gonzaguinha", "Luiz Gonzaga", "Jackson do Pandeiro", "Marinês",
    "Sivuca", "João Bosco", "Djavan", "Moraes Moreira", "Carlinhos Brown", "Margareth Menezes",
    "Arnaldo Antunes", "Nando Reis", "Marcelo Jeneci", "Lenine", "Gaby Amarantos",
    "Pabllo Vittar", "Ludmilla", "Anitta", "Iza", "Gabriel o Pensador", "Racionais MCs",
    "Mano Brown", "Sérgio Britto", "Zé Ramalho", "Dinho Ouro Preto", "Bianca Rinaldi",
    "Marilia Gabriela", "William Bonner", "Renata Vasconcellos", "Fátima Bernardes", "Glória Maria",
    "William Bonner", "Cid Moreira", "Bóris Casoy", "Ruth de Aquino", "Eliane Brum",
    "João Pereira Coutinho", "Miriam Leitão", "Vera Magalhães", "Bernardo Mello Franco", "Gabriel Priolli",
    "André Trigueiro", "Juca Kfouri", "Bob Fernandes", "Ana Clara Benevides", "Mônica Bergamo",
    "Fabrício Carpinejar", "Luis Felipe Pondé", "Leandro Karnal", "Clóvis de Barros Filho", "Luiz Felipe de Alencastro",
    "Laura de Mello e Souza", "Alberto Dines", "Érico Goldschmidt", "Luiz Eduardo Soares", "Edson Arantes do Nascimento",
    "Ronaldinho Gaúcho", "Rivaldo", "Romário", "Bebeto", "Marta", "Cristiane", "Formiga", "Sócrates",
    "Raí", "Júnior Baiano", "Alexandre Pato", "Rodrigo Faro", "Ana Hickmann", "Eliana", "Angélica", "Mara Maravilha",
    "Yudi Tamashiro", "Otávio Mesquita", "Serginho Mallandro", "Carlos Alberto de Nóbrega", "Renato Aragão",
    "Dedé Santana", "Mussum", "Zacarias", "Mário Lago", "Grijo", "Oswaldo Loureiro", "Raul Cortez",
    "Gianfrancesco Guarnieri", "José Wilker", "Antônio Fagundes", "Maitê Proença", "Regina Casé",
    "Sônia Braga", "Fernanda Montenegro", "Fernanda Torres", "Marília Pêra", "Jorge Dória",
    "Fábio Assunção", "Sílvio de Abreu", "Mauro Rasi", "Eduardo Mufarej", "José Celso Martinez Corrêa",
    "Antunes Filho", "Gerald Thomas", "Zé Henrique de Paula", "Aderbal Freire-Filho", "Bia Lessa",
    "Márcio Abreu", "Cacá Carvalho", "Gabriel Vilela", "José Possi Neto", "Maria Fernanda D'Amario",
    "Aníbal Machado", "Murilo Mendes", "João Paulo", "Ricardo Linhares", "Sônia Rodrigues",
    "Heloísa Teixeira", "Ariano Suassuna", "Fauzi Arap", "Plínio Marcos", "Roberto Athayde",
    "Naum Alves de Souza", "Carlos Alberto Soffredini", "Mauro Rasi", "Luiz Felipe de Lima", "Pedro Bial",
    "Eugênio Bucci", "Carlos Brickmann", "Flávia Pierucetti", "Mário Garritano", "Rogério Skylab",
    "Nei Braz", "Luiz Carlos da Vila", "Paulo Vanzolini", "Toquinho", "Baden Powell", "Paulo Moura",
    "Altamiro Carrilho", "Jacob do Bandolim", "Osvaldo Borba", "Tonho", "Chiquinho do Acordeon",
    "Gabriel Bianchini", "Júlio Estrela", "Alceu Valença", "Geraldo Azevedo", "Elba Ramalho",
    "Cátia de França", "Amelinha", "Nana Caymmi", "Dori Caymmi", "Danilo Caymmi",
    "Aracy de Almeida", "Noel Rosa", "Ary Barroso", "Lamartine Babo", "Assis Valente",
    "Ismael Silva", "Cartola", "Nelson Cavaquinho", "Guilherme de Brito", "Bide",
    "Maurício Tapajós", "Jorge Ben Jor", "Tim Maia", "Cassiano", "Rita Lee", "Arnaldo Jabor",
    "Ivan Lins", "Aldir Blanc", "João Bosco", "Ana Maria Sá", "Gilson Peranzzetta",
    "José Miguel Wisnik", "William Krüger", "Serguei", "Luiz Melodia", "Clara Nunes",
    "Martinho da Vila", "Zeca Pagodinho", "Beth Carvalho", "João Nogueira", "Jorge Aragão",
    "Roberto Ribeiro", "Eliana de Lima", "Celso Viáfora", "Carlinhos de Jesus", "Renata Crescente",
    "Rubens Confete", "Rogério", "Ricardo", "Diniz", "Milton Guedes", "Nelson Freire",
    "Fernando & Sorocaba", "Marília Mendonça", "Wesley Safadão", "Xand Avião", "Elvis Presley",
    "Michael Jackson", "Prince", "Bob Marley", "John Lennon", "Paul McCartney", "Freddie Mercury",
    "David Bowie", "Kurt Cobain", "Jim Morrison", "Janis Joplin", "Amy Winehouse", "Whitney Houston",
    "Mariah Carey", "Adele", "Beyoncé", "Rihanna", "Lady Gaga", "Taylor Swift", "Ed Sheeran",
    "Bruno Mars", "Eminem", "Kanye West", "Jay-Z", "Shakira", "Enrique Iglesias", "Ricky Martin",
    "Julio Iglesias", "Andrea Bocelli", "Sarah Brightman", "Josh Groban", "Michael Bublé", "Norah Jones",
    "Frank Sinatra", "Nina Simone", "Etta James", "Ella Fitzgerald", "Billie Holiday", "Aretha Franklin",
    "Ray Charles", "Stevie Wonder", "Marvin Gaye", "Aretha Franklin", "Smokey Robinson", "Diana Ross",
    "Lionel Richie", "Stevie Wonder", "Michael Jackson", "Prince", "Lenny Kravitz", "Bruce Springsteen",
    "Bob Dylan", "Neil Young", "Joni Mitchell", "Joan Baez", "Peter Gabriel", "Phil Collins",
    "Sting", "Bono", "Chris Martin", "Thom Yorke", "Radiohead", "Coldplay", "U2", "Red Hot Chili Peppers",
    "Nirvana", "Pearl Jam", "Soundgarden", "Alice in Chains", "Stone Temple Pilots", "Foo Fighters",
    "Metallica", "Megadeth", "Slayer", "Anthrax", "Iron Maiden", "Judas Priest", "Black Sabbath",
    "Led Zeppelin", "Deep Purple", "The Beatles", "The Rolling Stones", "The Who", "The Doors",
    "The Jimi Hendrix Experience", "Janis Joplin", "The Grateful Dead", "Pink Floyd", "The Police",
    "Genesis", "Rush", "King Crimson", "Yes", "ELP", "Jethro Tull", "Kiss", "Aerosmith",
    "Bon Jovi", "Guns N' Roses", "AC/DC", "Metallica", "Pantera", "Slipknot", "Korn",
    "Limp Bizkit", "Linkin Park", "Evanescence", "Avenged Sevenfold", "My Chemical Romance",
    "Green Day", "Blink-182", "Sum 41", "Offspring", "Rancid", "Bad Religion",
    "The Smiths", "The Cure", "Joy Division", "New Order", "Depeche Mode", "Erasure",
    "Pet Shop Boys", "Orchestral Manoeuvres in the Dark", "Ultravox", "Spandau Ballet",
    "Human League", "Duran Duran", "A-Ha", "Take That", "Robbie Williams", "Elton John",
    "Bernie Taupin", "Céline Dion", "Alicia Keys", "John Legend", "Common",
    "Kanye West", "Jay-Z", "Dr. Dre", "Eminem", "50 Cent", "Snoop Dogg", "Ice Cube",
    "Tupac", "The Notorious B.I.G.", "Nas", "Jay-Z", "Lil Wayne", "Drake", "Kendrick Lamar",
    "J. Cole", "Travis Scott", "Post Malone", "The Weeknd", "Bruno Mars", "Anderson .Paak",
    "Thundercat", "Flying Lotus", "Kamasi Washington", "Robert Glasper", "Herbie Hancock",
    "Chick Corea", "Return to Forever", "Weather Report", "Miles Davis", "John Coltrane",
    "Charlie Parker", "Dizzy Gillespie", "Thelonious Monk", "Duke Ellington", "Count Basie",
    "Benny Goodman", "Glenn Miller", "Artie Shaw", "Cab Calloway", "Fats Waller",
    "Louis Armstrong", "Bessie Smith", "Ma Rainey", "Robert Johnson", "Muddy Waters",
    "B.B. King", "Eric Clapton", "Jeff Beck", "Jimmy Page", "Jimi Hendrix", "Eddie Van Halen",
    "Joe Satriani", "Steve Vai", "Yngwie Malmsteen", "John Petrucci", "Buckethead",
    "Les Paul", "Andrés Segovia", "John Williams", "Julian Bream", "Paco de Lucía",
    "Chet Atkins", "Mark Knopfler", "Ry Cooder", "David Gilmour", "Pete Townshend",
    "Paul McCartney", "John Lennon", "George Harrison", "Ringo Starr", "Bonzo",
    "Keith Moon", "John Bonham", "Dave Grohl", "Travis Barker", "Steve Gadd",
    "Ginger Baker", "Mitch Mitchell", "Buddy Rich", "Gene Krupa", "Art Blakey",
    "Max Roach", "Elvin Jones", "Tony Williams", "Billy Cobham", "Carter Beauford",
    "Steve Smith", "Neil Peart", "Mike Portnoy", "Terry Bozzio", "Chad Smith",
    "Lars Ulrich", "Rick Allen", "Tommy Lee", "Chris Adler", "Matt Cameron",
    "David Garibaldi", "Bernard Purdie", "Jim Keltner", "Hal Blaine", "Earl Palmer",
    "Ziggy Marley", "Damian Marley", "Stephen Marley", "Ky-Mani Marley", "Buju Banton",
    "Shaggy", "Sean Paul", "Sister Nancy", "Rita Marley", "Lauryn Hill", "Wyclef Jean",
    "Pras", "Fugees", "Baha Men", "Cham", "Busy Signal", "Popcaan", "Shenseea",
    "Koffee", "Jesse Royal", "Chronixx", "Protoje", "Buju Banton", "Capleton",
    "Bounty Killer", "Sizzla", "Tony Rebel", "Luciano", "Garnett Silk", "Dennis Brown",
    "Gregory Isaacs", "John Holt", "Toots Hibbert", "Peter Tosh", "Bunny Wailer",
    "Barrington Levy", "Eek-A-Mouse", "Yellowman", "Lee Scratch Perry",
    "King Tubby", "Scientist", "Mad Professor", "Adrian Sherwood", "Bill Laswell"
]

SENTIMENTOS_ABSTRACOES = [
    "amor", "amizade", "felicidade", "superação", "resiliência", "empatia",
    "solidariedade", "esperança", "liberdade", "justiça", "igualdade",
    "respeito", "tolerância", "diversidade", "inclusão", "sustentabilidade",
    "inovação", "criatividade", "empreendedorismo", "liderança", "coragem",
    "persistência", "sonhos", "metas", "desafios", "sabedoria", "humildade",
    "gratidão", "generosidade", "compaixão", "honestidade", "transparência",
    "responsabilidade", "compromisso", "autoconhecimento", "mindfulness",
    "resiliência emocional", "inteligência emocional", "ética", "cidadania",
    "fraternidade", "solidão", "angústia", "medo", "alegria", "tristeza",
    "raiva", "ciúmes", "inveja", "orgulho", "vergonha", "culpa", "remorso",
    "perdão", "paz interior", "equilíbrio", "confiança", "autoestima",
    "autocontrole", "autocompaixão", "afeto", "ternura", "carinho",
    "admiração", "devoção", "apego", "saudade", "nostalgia", "esperança",
    "otimismo", "pessimismo", "ansiedade", "stress", "tensão", "calma",
    "serenidade", "tranquilidade", "paciência", "determinação", "vontade",
    "motivação", "inspiração", "entusiasmo", "euforia", "contentamento",
    "satisfação", "realização", "plenitude", "bem-estar", "harmonia",
    "sintonia", "conexão", "pertencimento", "acolhimento", "proteção",
    "cuidado", "atenção", "dedicação", "lealdade", "fidelidade", "sinceridade",
    "autenticidade", "integridade", "honra", "dignidade", "altruísmo",
    "bondade", "benignidade", "compreensão", "diálogo", "escuta ativa",
    "empatia ativa", "colaboração", "cooperação", "solidariedade ativa",
    "participação", "engajamento", "comprometimento", "responsabilidade social",
    "consciência", "reflexão", "introspecção", "autocrítica", "aceitação",
    "resignação", "conformismo", "revolta", "indignação", "revolução",
    "transformação", "evolução", "crescimento", "aprendizado", "descoberta",
    "curiosidade", "maravilhamento", "encantamento", "beleza", "poesia",
    "arte", "música", "dança", "escrita", "leitura", "conhecimento",
    "sabedoria popular", "intuição", "sensibilidade", "percepção", "consciência coletiva"
]

CONCEITOS = [
    "cultura brasileira", "história do Brasil", "geografia brasileira",
    "economia brasileira", "política brasileira", "meio ambiente",
    "educação", "saúde", "tecnologia", "arte", "música", "literatura",
    "culinária", "turismo", "esportes", "religião", "filosofia",
    "direitos humanos", "ciência", "inovação", "folclore",
    "expressões populares", "biomas", "cidades", "mitologia",
    "democracia", "capitalismo", "socialismo", "comunismo",
    "sotaque", "dialeto", "gíria", "linguagem", "comunicação",
    "mestiçagem", "sincretismo", "cultura afro-brasileira", "cultura indígena",
    "cultura caipira", "cultura nordestina", "cultura sulista", "cultura amazônica",
    "feijoada", "capoeira", "samba", "bossa nova", "forró", "frevo", "maracatu",
    "carnaval", "festas juninas", "Natal", "Ano Novo", "Festa do Divino",
    "Bumba meu boi", "Cavalo Marinho", "Reisado", "Folia de Reis",
    "patrimônio histórico", "patrimônio cultural", "museu", "arquivo",
    "biblioteca", "acervo", "documento histórico",
    "identidade nacional", "pluralidade cultural", "colonialismo", "independência",
    "abolição", "república", "ditadura militar", "redemocratização",
    "Constituição", "Estado de Direito", "cidadania", "participação popular",
    "movimentos sociais", "sindicatos", "partidos políticos", "eleições",
    "voto", "representatividade", "liderança comunitária", "voluntariado",
    "economia solidária", "agropecuária", "indústria", "serviços", "comércio exterior",
    "exportação", "importação", "PIB", "inflação", "desemprego", "desigualdade social",
    "mobilidade social", "educação pública", "universidade", "pesquisa acadêmica",
    "ciência popular", "divulgação científica", "tecnologia assistiva", "inteligência artificial",
    "cibersegurança", "internet", "redes sociais", "mídia", "jornalismo", "imprensa",
    "radiodifusão", "cinema", "teatro", "dança contemporânea", "performance",
    "artesanato", "design", "moda", "joalheria", "cerâmica", "escultura",
    "grafite", "pichação", "street art", "fotografia", "documentário",
    "ensaio", "crônica", "conto", "romance", "poesia concreta", "cordel",
    "literatura infantil", "quadrinhos", "fanzine", "editoração", "livraria",
    "feira de troca", "brechó", "moda sustentável", "ecoturismo", "turismo pedagógico",
    "turismo de base comunitária", "rota gastronômica", "cozinha regional",
    "cachaça", "pinga", "tapioca", "acarajé", "vatapá", "moqueca", "tacacá",
    "pato no tucupi", "baião de dois", "canjica", "pamonha", "curau", "quentão",
    "vinho quente", "rabanada", "pernil", "farofa", "vinagrete", "maionese",
    "churrasco", "chimarrão", "tererê", "mate", "guaraná", "cupuaçu", "açaí",
    "castanha-do-pará", "dendê", "pimenta", "coentro", "cheiro-verde",
    "futebol", "vôlei", "basquete", "surfe", "skate", "jiu-jitsu", "capoeira angola",
    "salto ornamental", "natação", "maratona", "ciclismo", "esportes radicais",
    "religiosidade popular", "umbanda", "candomblé", "espiritismo", "protestantismo",
    "catolicismo", "santos", "milagres", "romaria", "promessa", "devoção",
    "filosofia existencialista", "fenomenologia", "epistemologia", "ontologia",
    "decolonialidade", "pensamento latino-americano", "racionalidade", "sensibilidade",
    "justiça social", "reparação histórica", "cotas raciais", "políticas públicas",
    "universalização", "SUS", "vacinação", "medicina preventiva", "farmácia popular",
    "nutrição", "saúde mental", "psicologia social", "terapias integrativas",
    "plantas medicinais", "fitoterapia", "sustentabilidade", "economia verde",
    "preservação ambiental", "unidades de conservação", "terras indígenas",
    "quilombos", "reflorestamento", "reciclagem", "reutilização", "consumo consciente",
    "agroecologia", "permacultura", "bioconstrução", "energia solar", "eólica",
    "biodiversidade", "Amazônia", "Cerrado", "Mata Atlântica", "Pantanal", "Caatinga",
    "Pampas", "Zona Costeira", "pesca artesanal", "cultura oceânica",
    "lendas regionais", "saci-pererê", "curupira", "cuca", "boitatá", "mula sem cabeça",
    "corpo-seco", "lobisomem", "Boto cor-de-rosa", "iara", "vitória-régia",
    "Chico Rei", "Zumbi", "Dandara", "Maria Felipa", "Abolicionismo",
    "inconfidência mineira", "revolução pernambucana", "farroupilha", "balaiada",
    "canudos", "contestado", "cangaceiro", "Lampião", "Maria Bonita",
    "imigração", "diáspora", "refúgio", "asilo político", "cultura de paz",
    "diplomacia", "relações internacionais", "Mercosul", "Brics", "lusofonia"
]

CONHECIMENTO = [
    "matemática", "filosofia", "história", "física", "biologia",
    "programação", "lógica", "estatística", "economia", "linguística",
    "química", "geometria", "álgebra", "cálculo", "genética",
    "astronomia", "geologia", "psicologia", "sociologia", "antropologia",
    "neurociência", "ciência cognitiva", "inteligência artificial", "machine learning",
    "big data", "cloud computing", "segurança cibernética", "blockchain",
    "robótica", "automação", "biotecnologia", "nanotecnologia",
    "ciência dos materiais", "engenharia ambiental", "energia renovável",
    "arquitetura", "urbanismo", "design", "moda", "gastronomia",
    "enologia", "mixologia", "perfumaria", "cosmetologia",
    "pedagogia", "didática", "avaliação educacional", "currículo", "gestão escolar",
    "educação especial", "educação a distância", "tecnologia educacional", "alfabetização", "letramento",
    "literatura comparada", "crítica literária", "poética", "semiótica", "retórica",
    "linguagem corporal", "comunicação não verbal", "oratória", "escrita criativa", "jornalismo",
    "publicidade", "marketing", "relações públicas", "comportamento do consumidor", "branding",
    "finanças", "contabilidade", "auditoria", "gestão de projetos", "empreendedorismo",
    "administração pública", "políticas públicas", "governança", "relações internacionais", "direito internacional",
    "direito civil", "direito penal", "direito do trabalho", "direito ambiental", "direitos humanos",
    "medicina", "enfermagem", "odontologia", "farmacologia", "saúde pública",
    "nutrição", "educação física", "fisioterapia", "terapia ocupacional", "fonoaudiologia",
    "medicina veterinária", "zootecnia", "agronomia", "engenharia florestal", "ecologia",
    "geografia humana", "geografia física", "cartografia", "sensoriamento remoto", "topografia",
    "ciência política", "política comparada", "teoria política", "filosofia política", "ética aplicada",
    "teologia", "ciência da religião", "estudos culturais", "pós-colonialismo", "estudos de gênero",
    "psicanálise", "terapia cognitivo-comportamental", "psicologia positiva", "desenvolvimento humano", "psicomotricidade",
    "gestão de pessoas", "recursos humanos", "comportamento organizacional", "liderança", "motivação",
    "engenharia civil", "engenharia elétrica", "engenharia mecânica", "engenharia química", "engenharia de software",
    "engenharia de produção", "engenharia aeronáutica", "engenharia naval", "engenharia de minas", "engenharia de petróleo",
    "matemática aplicada", "matemática pura", "teoria dos números", "topologia", "análise funcional",
    "estatística descritiva", "inferência estatística", "probabilidade", "análise de dados", "mineração de dados",
    "visão computacional", "processamento de linguagem natural", "redes neurais", "aprendizado por reforço", "sistemas multiagentes",
    "interação humano-computador", "realidade virtual", "realidade aumentada", "gamificação", "design de interação",
    "ciência da computação", "sistemas de informação", "banco de dados", "arquitetura de computadores", "redes de computadores",
    "sistemas operacionais", "compiladores", "engenharia de software", "testes de software", "qualidade de software",
    "cibersegurança", "criptografia", "segurança da informação", "governança de TI", "gestão de serviços de TI"
]

PROFISSOES = [
    "engenheiro", "médico", "professor", "programador", "arquiteto",
    "advogado", "cientista", "policial", "designer", "empresário",
    "dentista", "psicólogo", "jornalista", "fotógrafo", "músico",
    "ator", "escritor", "piloto", "cozinheiro", "eletricista",
    "cientista de dados", "engenheiro de software", "analista de sistemas",
    "desenvolvedor web", "designer UX", "designer de interiores",
    "enfermeiro", "fisioterapeuta", "nutricionista", "veterinário",
    "administrador", "economista", "contador", "auditor",
    "publicitário", "marketing digital", "social media", "copywriter",
    "carpinteiro", "pedreiro", "encanador", "pintor",
    "mecânico", "metalúrgico", "soldador", "torneiro",
    "biólogo", "geólogo", "astrônomo", "meteorologista",
    "piloto de drone", "especialista em IA", "engenheiro de dados",
    "psiquiatra", "neurologista", "cardiopata", "otorrino", "oftalmologista",
    "ginecologista", "obstetra", "pediatra", "geriatra", "oncologista",
    "anestesista", "radiologista", "patologista", "clínico geral",
    "advogado trabalhista", "advogado cível", "advogado criminalista",
    "juiz", "promotor", "defensor público", "delegado",
    "cientista político", "diplomata", "relações internacionais",
    "tradutor", "intérprete", "linguista", "fonoaudiólogo",
    "antropólogo", "arqueólogo", "historiador", "geógrafo",
    "museólogo", "bibliotecário", "arquivista",
    "engenheiro de produção", "engenheiro mecânico", "engenheiro químico",
    "engenheiro elétrico", "engenheiro civil", "engenheiro ambiental",
    "engenheiro florestal", "engenheiro de alimentos", "engenheiro de transportes",
    "engenheiro naval", "engenheiro aeronáutico", "engenheiro de telecomunicações",
    "engenheiro de energia", "engenheiro nuclear", "engenheiro mecatrônico",
    "engenheiro de automação", "engenheiro de robótica", "engenheiro de materiais",
    "engenheiro metalúrgico", "engenheiro de minas", "engenheiro de petróleo",
    "engenheiro de segurança do trabalho", "engenheiro cartográfico",
    "engenheiro de áudio", "engenheiro de som", "engenheiro de áudio",
    "desenvolvedor mobile", "desenvolvedor de jogos", "engenheiro de prompt",
    "especialista em machine learning", "engenheiro de IA", "cientista de dados",
    "analista de BI", "engenheiro de DevOps", "engenheiro de confiabilidade",
    "especialista em nuvem", "administrador de redes", "analista de segurança",
    "perito forense", "analista de conformidade", "auditor de sistemas",
    "consultor de TI", "gestor de projetos", "scrum master", "product owner",
    "analista de negócios", "analista financeiro", "consultor financeiro",
    "planejador financeiro", "corretor de imóveis", "corretor de seguros",
    "gerente de banco", "analista de crédito", "analista de investimentos",
    "economista", "estatístico", "atuário", "matemático", "físico", "químico",
    "bioquímico", "farmacêutico", "biomédico", "citologista", "histologista",
    "embriologista", "geneticista", "imunologista", "microbiologista",
    "bacteriologista", "virologista", "parasitologista", "micologista",
    "botânico", "zoólogo", "ecólogo", "entomologista", "ornitólogo",
    "ictiólogo", "primatólogo", "conservacionista", "gestor ambiental",
    "ecoturismo", "guia de turismo", "agente de viagens", "gestor de eventos",
    "produtor cultural", "diretor de arte", "cenógrafo", "figurinista",
    "maquiador", "cabeleireiro", "barbeiro", "manicure", "pedicure",
    "esteticista", "massagista", "quiropraxista", "acupunturista",
    "naturopata", "homeopata", "fitoterapeuta", "terapeuta integrativo",
    "assistente social", "terapeuta ocupacional", "educador físico",
    "professor de educação infantil", "professor de ensino fundamental",
    "professor de ensino médio", "professor universitário", "orientador educacional",
    "supervisor escolar", "coordenador pedagógico", "diretor de escola",
    "bibliotecário", "arquivista", "museólogo", "restaurador de obras",
    "conservador de acervos", "arqueólogo subaquático", "paleontólogo",
    "mineralogista", "sismólogo", "vulcanólogo", "oceanógrafo", "hidrólogo",
    "climatologista", "aglomerador", "agrônomo", "zootecnista", "veterinário",
    "técnico agrícola", "florestal", "paisagista", "jardineiro", "viveirista",
    "produtor rural", "pecuarista", "avicultor", "apicultor", "piscicultor",
    "silvicultor", "madeireiro", "analista de logística", "gerente de operações",
    "suprimentos", "comprador", "almoxarife", "estoquista", "expedidor",
    "motorista de caminhão", "motorista de ônibus", "motorista de aplicativo",
    "taxista", "condutor de trens", "maquinista", "piloto de navio",
    "comandante de aeronaves", "comissário de bordo", "controlador de tráfego",
    "despachante aduaneiro", "corretor de aduanas", "agente de carga",
    "operador de ponte rolante", "operador de guindaste", "operador de empilhadeira",
    "operador de máquinas", "operador de produção", "controlador de qualidade",
    "inspetor de qualidade", "técnico de segurança", "bombeiro civil",
    "bombeiro militar", "guarda municipal", "guarda de trânsito",
    "agente penitenciário", "oficial de justiça", "notário", "registrador",
    "cônsul", "embaixador", "representante comercial", "vendedor técnico",
    "representante de marcas", "promotor de vendas", "gerente de loja",
    "atendente de loja", "caixa", "operador de telemarketing", "recepcionista",
    "porteiro", "zelador", "faxineiro", "lavadeiro", "passadeira",
    "costureira", "alfaiate", "sapateiro", "chaveiro", "serralheiro",
    "vidraceiro", "marceneiro", "tapeceiro", "cortineiro", "encadernador",
    "gráfico", "operador de impressão", "ilustrador", "animador", "modelo 3D",
    "construtor de instrumentos", "luthier", "conservador de arte",
    "crítico de arte", "curador", "galerista", "leiloeiro", "avaliador de obras",
    "perito judicial", "mediador de conflitos", "conciliador", "árbitro",
    "advogado previdenciário", "advogado tributário", "advogado falimentar",
    "advogado societário", "advogado imobiliário", "advogado digital",
    "promotor de justiça", "procurador da república", "procurador federal",
    "procurador estadual", "procurador municipal", "defensor dativo",
    "advogado pro bono", "consultor jurídico", "assessor parlamentar",
    "analista legislativo", "técnico judiciário", "escrivão", "diretor de cartório"
]

ARTE_CULTURA = [
    "cinema", "música", "teatro", "pintura", "escultura",
    "literatura", "fotografia", "dança", "arte digital", "poesia",
    "graffiti", "tatuagem", "arte sacra", "arte abstrata", "realismo",
    "surrealismo", "modernismo", "barroco", "renascimento", "arte contemporânea",
    "arte indígena", "arte afro-brasileira", "arte popular", "arte naïf",
    "instalação", "performance", "videoarte", "arte conceitual",
    "fotografia documental", "fotojornalismo", "cinema novo", "Cinema Marginal",
    "teatro de bonecos", "teatro de rua", "teatro do oprimido",
    "dança contemporânea", "balé clássico", "dança de salão", "forró",
    "música clássica", "música erudita", "música popular", "MPB",
    "samba", "choro", "bossa nova", "tropicalismo", "rock brasileiro",
]

CIENCIA_TECNOLOGIA = [
    "inteligência artificial", "robótica", "blockchain", "internet",
    "cibersegurança", "big data", "machine learning", "cloud computing",
    "redes neurais", "automação", "computação quântica", "realidade virtual",
    "impressão 3D", "nanotecnologia", "biotecnologia", "criptografia",
    "Python", "Java", "C++", "JavaScript", "Go", "Rust", "Swift", "Kotlin",
    "HTML", "CSS", "React", "Angular", "Vue.js", "Node.js", "Django", "Flask",
    "API", "REST", "GraphQL", "microsserviços", "Docker", "Kubernetes",
    "Git", "DevOps", "CI/CD", "testes automatizados", "TDD",
    "banco de dados SQL", "NoSQL", "MongoDB", "PostgreSQL",
    "framework", "biblioteca", "IDE", "debug", "compilador",
    "algoritmo", "estrutura de dados", "complexidade", "recursão",
    "Internet das Coisas (IoT)", "cidades inteligentes", "casas conectadas",
    "wearables", "telemedicina", "educação a distância", "gamificação",
    "metaverso", "NFT", "Web3", "DeFi", "smart contracts",
    "robótica móvel", "drone autônomo", "veículo autônomo",
]

ACOES = [
    "correr", "pensar", "criar", "aprender", "ensinar",
    "viajar", "construir", "explorar", "programar", "liderar",
    "meditar", "cozinhar", "dançar", "desenhar", "escrever",
    "nadar", "escalar", "cantar", "tocar", "pintar",
    "analisar", "pesquisar", "planejar", "organizar", "administrar",
    "negociar", "empreender", "investir", "colaborar", "comunicar",
    "persuadir", "inspirar", "motivar", "resolver", "decidir",
    "otimizar", "automatizar", "testar", "codificar", "debugar",
    "revisar", "documentar", "apresentar",
    "emprestar", "doar", "voluntariar", "cooperar", "participar",
    "observar", "refletir", "meditar", "respirar", "relaxar",
    "jogar", "brincar", "competir", "cooperar", "celebrar",
    "andar", "caminhar", "saltar", "pular", "voar", "mergulhar",
    "surfar", "esquiar", "patinar", "remar", "pedalar",
    "dirigir", "pilotar", "navegar", "voar", "flutuar",
    "abrir", "fechar", "levantar", "abaixar", "girar",
    "montar", "desmontar", "consertar", "manter", "limpar",
    "lavar", "secar", "passar", "guardar", "organizar",
    "classificar", "catalogar", "indexar", "filtrar", "ordenar",
    "comparar", "contrastar", "analisar", "interpretar", "traduzir",
    "resumir", "parafrasear", "citar", "referenciar", "argumentar",
    "debater", "dialogar", "entrevistar", "consultar", "aconselhar",
    "orientar", "mentorar", "treinar", "capacitar", "desenvolver",
    "guiar", "conduzir", "direcionar", "redirecionar", "realinhar",
    "priorizar", "sequenciar", "cronometrar", "acelerar", "desacelerar",
    "parar", "continuar", "retomar", "concluir", "finalizar",
    "entregar", "receber", "aceitar", "rejeitar", "aprovar",
    "desaprovar", "validar", "invalidar", "verificar", "confirmar",
    "autenticar", "autorizar", "permitir", "proibir", "restringir",
    "liberar", "conceder", "revogar", "alterar", "modificar",
    "adaptar", "ajustar", "configurar", "personalizar", "customizar",
    "ampliar", "reduzir", "expandir", "contrair", "dobrar",
    "desdobrar", "enrolar", "desenrolar", "amassar", "desamassar",
    "cortar", "rasgar", "colar", "grudar", "costurar",
    "bordar", "tricotar", "crochetar", "tecer", "entrelaçar",
    "trançar", "amarrar", "desamarrar", "pendurar", "suspender",
    "apoiar", "segurar", "pegar", "soltar", "largar",
    "lançar", "arremessar", "chutar", "bater", "golpear",
    "defender", "atacar", "esquivar", "bloquear", "contra-atacar",
    "esconder", "revelar", "mostrar", "ocultar", "disfarçar",
    "mascarar", "camuflar", "exibir", "expor", "publicar",
    "divulgar", "anunciar", "propagar", "disseminar", "compartilhar",
    "redistribuir", "reciclar", "reutilizar", "reaproveitar", "remanufaturar",
    "reparar", "restaurar", "revitalizar", "reenergizar", "recarregar",
    "alimentar", "nutrir", "hidratar", "oxigenar", "ventilar",
    "aquecer", "resfriar", "congelar", "descongelar", "ferver",
    "cozer", "assar", "grelhar", "fritar", "refogar",
    "temperar", "salgar", "adoçar", "amargar", "apimentar",
    "misturar", "homogeneizar", "bater", "sovar", "modelar",
    "moldar", "esculpir", "entalhar", "lapidar", "polir",
    "lustrar", "encerar", "esfregar", "lustrar", "brilhar",
    "reluzir", "cintilar", "cintilar", "lampejar", "iluminar",
    "ofuscar", "encantar", "fascinar", "capturar", "fotografar",
    "filmar", "gravar", "transmitir", "transcrever", "registrar",
    "memorizar", "relembrar", "recordar", "esquecer", "ignorar",
    "desconsiderar", "subestimar", "superestimar", "valorizar", "desvalorizar",
    "elogiar", "criticar", "aplaudir", "vaiar", "silenciar",
    "ouvir", "escutar", "perceber", "notar", "distinguir",
    "reconhecer", "identificar", "diagnosticar", "avaliar", "mensurar",
    "calcular", "estimular", "incentivar", "fomentar", "promover",
    "impulsionar", "acelerar", "impulsionar", "alavancar", "catalisar",
    "viabilizar", "facilitar", "simplificar", "complexificar", "detalhar",
    "especificar", "generalizar", "abstrair", "concretizar", "materializar",
    "incorporar", "integrar", "fundir", "fusionar", "sincretizar",
    "harmonizar", "equilibrar", "balancear", "compensar", "ajustar",
    "sincronizar", "coordenar", "orquestrar", "coreografar", "roteirizar",
    "encenar", "representar", "interpretar", "atuar", "performar",
    "expressar", "manifestar", "externar", "verbalizar", "enunciar",
    "declarar", "afirmar", "negar", "contradizer", "concordar",
    "discordar", "aceitar", "recusar", "aderir", "renunciar",
    "desistir", "persistir", "insistir", "teimar", "ceder",
    "flexibilizar", "endurecer", "amolecer", "amaciar", "suavizar",
    "intensificar", "amenizar", "aliviar", "consolar", "confortar",
    "abraçar", "beijar", "acariciar", "afagar", "embalar",
    "balancear", "acalmar", "serenar", "tranquilizar", "pacificar",
    "negociar", "mediar", "interceder", "arbitrar", "conciliar",
    "reconciliar", "perdoar", "absolver", "inocentar", "condenar",
    "sentenciar", "executar", "cumprir", "obedecer", "desobedecer",
    "transgredir", "violar", "respeitar", "honrar", "desonrar",
    "trair", "confiar", "desconfiar", "suspeitar", "investigar",
    "inquirir", "interrogar", "questionar", "contestar", "impugnar",
    "recorrer", "apelar", "reclamar", "protestar", "manifestar-se",
    "votar", "eleger", "nomear", "indicar", "designar",
    "promover", "rebaixar", "demitir", "contratar", "recrutar",
    "entrevistar", "selecionar", "escolher", "optar", "preferir",
    "eleger", "distinguir", "premiar", "homenagear", "exaltar",
    "enaltecer", "engrandecer", "enfraquecer", "fortalecer", "consolidar",
    "solidificar", "cristalizar", "fundamentar", "alicerçar", "edificar",
    "erigir", "instalar", "fixar", "ancorar", "atracar",
    "desatracar", "zarpar", "navegar", "costear", "ancorar",
    "atravessar", "transpor", "ultrapassar", "superar", "vencer",
    "triunfar", "dominar", "subjugar", "conquistar", "ganhar",
    "perder", "empatar", "desistir", "render-se", "capitular",
    "prosseguir", "avançar", "recuar", "retroceder", "estacionar",
    "permanecer", "residir", "habitar", "morar", "viver",
    "sobreviver", "coexistir", "conviver", "sociabilizar", "interagir",
    "relacionar", "vincular", "ligar", "conectar", "desconectar",
    "sincronizar", "dessincronizar", "alinhar", "desalinhar", "regular",
    "ajustar", "calibrar", "padronizar", "normalizar", "uniformizar",
    "diversificar", "variar", "mutar", "transformar", "transmutar",
    "converter", "transfigurar", "metamorfosear", "evoluir", "envolver",
    "implicar", "envolvido", "emaranhar", "desembaraçar", "resolver",
    "solucionar", "decifrar", "desvendar", "descobrir", "inventar",
    "idealizar", "conceber", "projetar", "delinear", "esboçar",
    "rascunhar", "rabiscar", "improvisar", "experimentar", "testar",
    "provar", "validar", "verificar", "certificar", "atestar",
    "comprovar", "demonstrar", "evidenciar", "exemplificar", "ilustrar",
    "representar", "simular", "modelar", "emular", "imitar",
    "reproduzir", "copiar", "clonar", "duplicar", "triplicar",
    "multiplicar", "dividir", "subtrair", "adicionar", "somar",
    "acumular", "armazenar", "guardar", "preservar", "conservar",
    "proteger", "resguardar", "salvaguardar", "defender", "resgatar",
    "salvar", "recuperar", "restaurar", "reviver", "reanimar",
    "reavivar", "reacender", "reinaugurar", "reiniciar", "recomeçar",
    "replanejar", "reorganizar", "reestruturar", "reformular", "reinventar"
]

ALIMENTOS = [
    "arroz", "feijão", "carne", "pizza", "hambúrguer",
    "salada", "frutas", "massa", "sopa", "peixe",
    "pão", "queijo", "vinho", "chocolate", "sorvete",
    "ovo", "leite", "café", "sushi", "tapioca",
    "feijoada", "galinhada", "churrasco", "bolinho de carne",
    "acarajé", "vatapá", "caruru", "tacacá", "pato no tucupi",
    "baião de dois", "arroz carreteiro", "cuscuz", "canjica", "pamonha",
    "empadão", "pastel", "coxinha", "kibe", "esfiha",
    "picanha", "costela", "linguiça", "frango assado", "peixe grelhado",
    "salada de frutas", "mousse", "pudim", "brigadeiro", "beijinho",
    "caju", "manga", "banana", "laranja", "limão",
    "abacaxi", "melancia", "morango", "uva", "maçã",
    "castanha", "noz", "amendoim", "pistache", "amêndoa",
    "leite condensado", "doce de leite", "cocada", "queijadinha", "cartola",
    "torta de limão", "torta de morango", "torta de nozes",
    "risoto", "polenta", "gnocchi", "lasanha", "espaguete",
    "moqueca", "ensopado", "cozido", "ensopado de carne",
    "salpicão", "maionese", "vinagrete", "farofa", "couve à mineira",
    "batata frita", "purê de batata", "batata assada", "mandioca frita", "inhame",
    "cará", "abóbora", "chuchu", "berinjela", "abobrinha",
    "pepino", "tomate", "alface", "rúcula", "agrião",
    "espinafre", "acelga", "brócolis", "couve-flor", "repolho",
    "cebola", "alho", "pimentão", "pimenta", "cheiro-verde",
    "coentro", "manjericão", "orégano", "cominho", "canela",
    "cravo", "cardamomo", "noz-moscada", "açafrão", "colorau",
    "molho de tomate", "molho branco", "molho pesto", "molho à bolonhesa", "molho de queijo",
    "maionese caseira", "mostarda", "ketchup", "barbecue", "chutney",
    "geléia", "marmelada", "goiabada", "doce de banana", "doce de abóbora",
    "rapadura", "melado", "mel", "açúcar", "manteiga",
    "margarina", "creme de leite", "iogurte", "bebida láctea", "achocolatado",
    "suco natural", "suco de laranja", "suco de limão", "suco de uva", "suco de tomate",
    "água de coco", "coconut milk", "leite de soja", "leite de amêndoas", "leite de aveia",
    "chá", "chá mate", "chá verde", "chá preto", "chá de camomila",
    "refrigerante", "cerveja", "licor", "cachaça", "rum",
    "uísque", "vodka", "gin", "tequila", "espumante",
    "caldo de carne", "caldo de galinha", "caldo de legumes", "caldo de peixe", "agar-agar",
    "gelatina", "flan", "crème brûlée", "panna cotta", "mousse de chocolate",
    "mousse de maracujá", "mousse de limão", "pavê", "torta de frango", "torta de camarão",
    "esfirra", "salgadinho", "pão de queijo", "pão francês", "pão de forma",
    "pão integral", "pão de centeio", "baguete", "ciabatta", "focaccia",
    "pita", "naan", "tortilha", "arepa", "couscous",
    "tabule", "hummus", "babaganoush", "falafel", "shawarma",
    "kebab", "souvlaki", "gyro", "taco", "burrito",
    "quesadilla", "nachos", "guacamole", "salsa", "mole",
    "molho de pimenta", "sriracha", "wasabi", "gengibre", "alga nori",
    "shoyu", "mirin", "saquê", "panko", "togarashi",
    "frango xadrez", "frango com curry", "carne de panela", "carne ao molho", "bife à milanesa",
    "bife de fígado", "coração de frango", "moela", "língua", "rabada",
    "orelha de porco", "pé de porco", "bochecha", "farinha de mandioca", "fubá",
    "flocão", "canjiquinha", "milho", "ervilha", "lentilha",
    "grão-de-bico", "feijão-fradinho", "feijão-verde", "feijão-manteiga", "feijão-carioca",
    "soja", "trigo", "centeio", "cevada", "aveia",
    "quinoa", "amaranto", "semente de linhaça", "semente de gergelim", "semente de girassol",
    "tucupi", "jambu", "açaí", "cupuaçu", "bacuri",
    "graviola", "siriguela", "cajá", "umbu", "pitanga",
    "goiaba", "pera", "ameixa", "damasco", "figo",
    "kiwi", "pêssego", "nectarina", "framboesa", "amora",
    "mirtilo", "cranberry", "pitaya", "carambola", "líchia",
    "mexerica", "tangerina", "pomelo", "cidra", "lima",
    "maracujá", "seriguela", "cabeluda", "pequi", "buriti",
    "manga-rosa", "manga espada", "macaúba", "baru", "pinhão",
    "castanha de caju", "castanha do pará", "macadâmia", "pecã", "avelã",
    "coco ralado", "leite de coco", "óleo de coco", "óleo de soja", "óleo de canola",
    "banha", "toucinho", "bacon", "presunto", "mortadela",
    "salame", "pepperoni", "calabresa", "salsicha", "linguíça",
    "paio", "toscana", "blanquet", "patê", "terrine",
    "surimi", "caviar", "mexilhão", "ostra", "lagosta",
    "camarão", "siri", "caranguejo", "polvo", "lula",
    "bacalhau", "sardinha", "atum", "salmonete", "robalo",
    "dourado", "pintado", "pirarucu", "tambaqui", "matrinxã",
    "curimatã", "pirapitinga", "pacu", "cachara", "surubim"
]


ANIMAIS = [
    "cachorro", "gato", "leão", "tigre", "elefante",
    "pássaro", "peixe", "cavalo", "lobo", "urso",
    "golfinho", "baleia", "águia", "cobra", "tubarão",
    "borboleta", "formiga", "abelha", "macaco", "panda",
    "girafa", "hipopótamo", "rinoceronte", "zebra", "camelo",
    "pinguim", "foca", "leão-marinho", "tartaruga", "crocodilo",
    "arara", "tucano", "papagaio", "beija-flor", "sabiá",
    "onça-pintada", "suçuarana", "jaguatirica", "veado", "capivara",
    "lontra", "ariranha", "boto cor-de-rosa", "peixe-boi", "tamanduá",
    "tatu", "tatu-bola", "cutia", "paca", "cotia",
    "quati", "gambá", "morcego", "coruja", "urubu",
    "jabuti", "cágado", "tartaruga-da-amazônia", "iguana", "jacaré",
    "coelho", "lebre", "esquilo", "castor", "ratazana",
    "camundongo", "hamster", "porquinho-da-índia", "chinchila", "ouriço",
    "puma", "pantera", "leopardo", "guepardo", "lince",
    "serval", "caracal", "ocelote", "jaguatirica", "margay",
    "lobo-guará", "raposa", "cão-vinagre", "cachorro-do-mato", "graxaim",
    "fossa", "hiena", "cão-africano", "lobo-etíope", "coiote",
    "dromedário", "lhama", "alpaca", "guanaco", "vicunha",
    "bisão", "búfalo", "iaque", "boi", "vaca",
    "touro", "carneiro", "ovelha", "cabra", "bode",
    "cavalo selvagem", "zebra-das-planícies", "zebra-de-grevy", "asno", "mula",
    "rinoceronte-branco", "rinoceronte-negro", "rinoceronte-de-sumatra", "rinoceronte-de-java", "rinoceronte-indiano",
    "hipopótamo-pigmeu", "elefante-asiático", "elefante-africano", "mamute", "elefante-marinho",
    "morsa", "leão-marinho-da-patagônia", "foca-monge", "foca-barbuda", "foca-ringue",
    "baleia-azul", "baleia-jubarte", "baleia-cachalote", "baleia-orca", "baleia-fin",
    "golfinho-corcunda", "golfinho-rotator", "golfinho-comum", "botucinzeiro", "toninha",
    "tubarão-baleia", "tubarão-branco", "tubarão-martelo", "tubarão-tigre", "tubarão-galha-branca",
    "arraia", "raia", "peixe-agulha", "peixe-espada", "peixe-lua",
    "bacalhau", "salmão", "truta", "atum", "dourado",
    "pirarucu", "tambaqui", "pacu", "matrinxã", "curimatã",
    "surubim", "pintado", "cachara", "piraíba", "mandi",
    "corvina", "pescada", "bagre", "candiru", "tucunaré",
    "anta", "tapir", "preguiça", "bicho-preguiça", "macaco-prego",
    "sauim", "mico", "bugio", "guariba", "cuxiú",
    "ariranha", "lontra-gigante", "irara", "furão", "mangusto",
    "suricato", "meerkat", "curiango", "preguiça-de-coleira", "tamanduaí",
    "tatu-canastra", "tatu-de-folha", "tatu-galinha", "tatu-peba", "tatu-rabo-mole",
    "porco-espinho", "ouriço-cacheiro", "caxinguelê", "esquilo-voador", "musaranho",
    "topo", "toupeira", "rato-toupeira", "hamster-sírio", "gerbil",
    "chinchila", "preá", "mocó", "paca", "cutia",
    "aguti", "guariba", "sagui", "macaco-aranha", "macaco-barrigudo",
    "pato", "ganso", "cisne", "marreco", "pato-real",
    "galinha", "galo", "peru", "faisão", "codorna",
    "perdiz", "galo-silvestre", "azeitoninha", "pintada", "mutum",
    "ema", "nandu", "avestruz", "casuar", "kiwi",
    "falcão", "gavião", "caracará", "urubu-rei", "condor",
    "águia-careca", "águia-real", "águia-serpentária", "milhafre", "peneireiro",
    "falcão-peregrino", "gavião-real", "gavião-pato", "gavião-belo", "carcará",
    "coruja-buraqueira", "coruja-das-torres", "mocho", "caburé", "corujão",
    "beija-flor-preto", "beija-flor-tesoura", "beija-flor-de-peito-azul", "beija-flor-tijuca", "besourinho",
    "tucano-grande", "tucano-de-bico-preto", "tucano-de-papo-amarelo", "tucaninho", "aracari",
    "papagaio-verdadeiro", "papagaio-charão", "periquito", "jandaia", "maracanã",
    "arara-azul", "arara-vermelha", "arara-canindé", "arara-militar", "ararinha-azul",
    "sabiá-laranjeira", "sabiá-una", "sabiá-poca", "sabiá-do-campo", "sabiá-da-praia",
    "tico-tico", "pássaro-preto", "cardeal", "pintassilgo", "curió",
    "canário-da-terra", "trinca-ferro", "garrinchão", "corrupião", "azulão",
    "joão-de-barro", "bem-te-vi", "pitangueira", "cambacica", "saíra",
    "neinei", "guará", "colhereiro", "garça", "garça-branca",
    "socozinho", "tapicuru", "maguari", "cabeça-seca", "jaçanã",
    "carão", "saracura", "frango-d'água", "galinha-d'água", "pica-pau",
    "pica-pau-amarelo", "pica-pau-de-cabeça-amarela", "pica-pau-verde", "rapazinho", "araponga",
    "periquito-de-encontro-amarelo", "periquito-australiano", "calopsita", "cacatua", "ara",
    "pombos", "rolinha", "rolinha-caldo-de-feijão", "rolinha-fogo-apagou", "juriti",
    "jaburu", "cegonha", "maguari", "socó", "garça-moura",
    "caranguejeira", "aranha", "escorpião", "lacraia", "centopeia",
    "besouro", "joaninha", "vagalume", "cigarra", "grilo",
    "gafanhoto", "louva-a-deus", "bicho-pau", "barata", "traça",
    "mariposa", "libélula", "zangão", "vespa", "mangava",
    "mutuca", "borrachudo", "mosca", "mosquito", "pernilongo",
    "pulga", "carrapato", "ácaro", "piolho", "chato",
    "mexilhão", "ostra", "vieira", "marisco", "caramujo",
    "lesma", "sapo", "perereca", "rã", "cobra-coral",
    "jararaca", "urutu", "cascavel", "surucucu", "papagaio-de-cobra",
    "jiboia", "sucuri", "anaconda", "píton", "cobra-rei",
    "lagartixa", "geco", "camaleão", "osga", "teiú",
    "tucunaré", "traíra", "jeju", "piranha", "piracema",
    "sardinha", "arenque", "cavala", "tainha", "peixe-rei",
    "agulha", "cavalo-marinho", "peixe-palhaço", "cirurgião", "peixe-borboleta",
    "peixe-anjo", "peixe-porco", "baiacu", "peixe-lua", "manta"
]

TRANSPORTE = [
    "carro", "ônibus", "avião", "bicicleta", "trem",
    "navio", "metrô", "moto", "caminhão", "helicóptero",
    "trator", "skate", "patins", "barco", "submarino",
    "foguete", "teleférico", "bondinho", "carroça", "jetski",
    "VLT", "bonde", "trólebus", "scooter", "monociclo",
    "hoverboard", "segway", "automóvel elétrico", "carro híbrido",
    "carro autônomo", "drone de entrega", "barco a vela",
    "iate", "lancha", "catamarã", "hidrofólio",
]

SOCIEDADE_POLITICA = [
    "democracia", "governo", "leis", "direitos", "justiça",
    "economia", "corrupção", "liberdade", "igualdade", "cidadania",
    "eleição", "parlamento", "constituição", "voto", "partido político",
    "urbanismo", "mobilidade social", "previdência", "educação pública",
    "impeachment", "reforma política", "reforma tributária", "reforma trabalhista",
    "política fiscal", "política monetária", "inflação", "desemprego",
    "pobreza", "desigualdade social", "violência", "segurança pública",
    "saúde pública", "SUS", "vacinação", "pandemia",
    "meio ambiente", "mudança climática", "desmatamento", "queimadas",
    "indústria", "agronegócio", "comércio exterior", "exportação",
    "Movimento dos Trabalhadores Rurais", "sindicatos", "associações",
    "participação popular", "orçamento participativo", "plebiscito",
    "política de cotas", "ações afirmativas", "igualdade de gênero",
    "direitos LGBTQ+", "política de drogas", "aborto", "eutanásia",
    "pena de morte", "prisão perpétua", "política de imigração",
    "refugiados", "asilo", "cidadania global", "ONU", "UNESCO",
    "Mercosul", "UE", "OTAN", "BRICS", "G20",
]

NATUREZA_UNIVERSO = [
    "floresta", "oceano", "montanha", "rio", "deserto",
    "planeta", "estrela", "galáxia", "clima", "ecossistema",
    "lua", "sol", "buraco negro", "supernova", "aurora boreal",
    "coral", "geologia", "atmosfera", "gravidade", "matéria escura",
    "asteroide", "cometa", "meteoro", "satélite natural", "constelação",
    "vulcão", "terremoto", "tsunami", "furacão", "tornado",
    "ciclone", "monção", "El Niño", "La Niña",
    "ecossistema marinho", "recife de coral", "manguezal", "pântano",
    "caverna", "geleira", "calota polar", "permafrost",
    "biosfera", "hidrosfera", "litosfera", "atmosfera",
    "exoplaneta", "anã marrom", "gigante gasoso", "nébula",
    "aglomerado estelar", "quasar", "pulsar",
]

MUSICAS_BANDAS_CANTORES = [
    "Caetano Veloso", "Gilberto Gil", "Chico Buarque", "Milton Nascimento",
    "Elis Regina", "Tom Jobim", "Vinícius de Moraes", "Maria Bethânia",
    "Gal Costa", "Djavan", "Tim Maia", "Jorge Ben Jor", "Martinho da Vila",
    "Zeca Pagodinho", "Cartola", "Nelson Cavaquinho", "Noel Rosa",
    "Raul Seixas", "Os Mutantes", "Titãs", "Paralamas", "Legião Urbana",
    "Cazuza", "Rita Lee", "Roberto Carlos", "Maria Rita", "Caio Prado",
    "Orquestra Sinfônica Brasileira", "Banda Eva", "Asa de Águia",
    "Olodum", "Timbalada", "Carnaval", "Samba", "Pagode", "MPB", "Bossa Nova",
    "Forró", "Frevo", "Maracatu", "Chorinho", "Sertanejo", "Funk", "Hip Hop",
    "Rock nacional", "Reggae", "Axé",
    "Lenine", "Vanessa da Mata", "Maria Gadú", "Céu", "Mallu Magalhães",
    "Seu Jorge", "Música popular brasileira", "Instrumental", "Pixinguinha",
    "Hermeto Pascoal", "Egberto Gismonti", "Toninho Horta", "Hamilton de Holanda",
    "Yamandu Costa", "Baden Powell", "João Gilberto", "Stan Getz",
    "Tom Zé", "Arnaldo Antunes", "Carlinhos Brown", "Marisa Monte",
    "Nando Reis", "Samuel Rosa", "Chico César", "Mestre Ambrósio",
    "Cordel do Fogo Encantado", "Nação Zumbi", "Mangue Beat",
]

SINTOMAS_DOENCAS = [
    "febre", "dor de cabeça", "dor de garganta", "tosse", "coriza",
    "espirros", "fadiga", "dores musculares", "enjoo", "vômito",
    "diarreia", "constipação", "dor abdominal", "dor nas costas",
    "dor nas articulações", "tontura", "falta de ar", "palpitações",
    "pressão alta", "pressão baixa", "diabetes", "colesterol alto",
    "asma", "bronquite", "pneumonia", "gripe", "resfriado",
    "covid-19", "dengue", "chikungunya", "zika", "malária",
    "tuberculose", "hepatite", "meningite", "ansiedade", "depressão",
    "estresse", "insônia", "enxaqueca", "sinusite", "gastrite",
    "úlcera", "pedra nos rins", "infecção urinária", "conjuntivite",
    "alergia", "dermatite", "psoríase", "câncer", "AIDS", "HIV",
    "febre amarela", "tétano", "coqueluche", "sarampo", "caxumba",
    "rubéola", "catapora", "herpes", "HPV", "gengivite",
    "Lúpus", "artrite reumatoide", "esclerose múltipla", "mal de Parkinson",
    "Alzheimer", "demência", "AVC", "infarto", "arritmia",
    "hepatite A", "hepatite B", "hepatite C", "cirrose", "esteatose",
    "obesidade", "anorexia", "bulimia", "transtorno bipolar",
    "esquizofrenia", "TDAH", "autismo", "Síndrome de Down",
    "calafrio", "suor excessivo", "suor noturno", "rubor facial", "palidez",
    "olhos vermelhos", "lacrimejamento", "visão turva", "visão dupla", "cegueira noturna",
    "zumbido no ouvido", "perda auditiva", "dor de ouvido", "otite", "labirintite",
    "náusea", "azia", "queimação", "arrotos", "flatulência",
    "prisão de ventre", "fezes escuras", "sangue nas fezes", "urina escura", "urina com sangue",
    "coceira", "urticária", "erupção cutânea", "manchas vermelhas", "descamação",
    "feridas na boca", "aftas", "sangramento gengival", "dentes sensíveis", "bruxismo",
    "unhas frágeis", "queda de cabelo", "cabelos secos", "pele ressecada", "pele oleosa",
    "inchaço nos membros", "edema", "retenção de líquidos", "veias varicosas", "trombose",
    "cãibras", "formigamento", "dormência", "fraqueza muscular", "tremores",
    "perda de equilíbrio", "coordenação motora alterada", "convulsões", "desmaios", "confusão mental",
    "desorientação", "perda de memória", "falta de concentração", "fala arrastada", "dificuldade para engolir",
    "perda de apetite", "perda de peso involuntária", "ganho de peso", "sede excessiva", "boca seca",
    "micção frequente", "incontinência urinária", "dificuldade para urinar", "corrimento vaginal", "corrimento peniano",
    "impotência", "perda de libido", "menstruação irregular", "cólicas menstruais", "endometriose",
    "miomas", "ovários policísticos", "cistos ovarianos", "torção testicular", "varicocele",
    "prostatite", "hiperplasia prostática", "câncer de próstata", "câncer de mama", "câncer de cólon",
    "câncer de pulmão", "câncer de pele", "melanoma", "carcinoma", "sarcoma",
    "leucemia", "linfoma", "mieloma", "tumor cerebral", "glioblastoma",
    "aneurisma", "aterosclerose", "hipertensão arterial", "hipotensão", "infarto agudo do miocárdio",
    "insuficiência cardíaca", "cardiomegalia", "pericardite", "endocardite", "valvopatia",
    "doença arterial coronariana", "angina", "veias varicosas", "trombose venosa", "embolia pulmonar",
    "Acidente Vascular Cerebral (AVC)", "aneurisma cerebral", "atetose", "coreia", "distonia",
    "esclerose lateral amiotrófica", "esclerose sistêmica", "sarcoidose", "polimialgia", "polimiosite",
    "doença de Crohn", "colite ulcerativa", "síndrome do intestino irritável", "diverticulite", "apendicite",
    "pancreatite", "colecistite", "pedra na vesícula", "doença celíaca", "intolerância à lactose",
    "alergia alimentar", "alergia a medicamentos", "anafilaxia", "edema de angioedema", "síndrome de Sjögren",
    "doença de Behçet", "doença de Kawasaki", "púrpura trombocitopênica", "anemia falciforme", "talassemia",
    "hemofilia", "trombocitopenia", "policitemia", "leucopenia", "neutropenia",
    "linfadenopatia", "baço aumentado", "fígado aumentado", "icterícia", "ascite",
    "peritonite", "abscesso", "celulite", "gangrena", "sepse",
    "choque séptico", "síndrome do desconforto respiratório", "pleurisia", "derrame pleural", "pneumotórax",
    "enfisema", "DPOC", "fibrose pulmonar", "hipertensão pulmonar", "cor pulmonale",
    "rinite alérgica", "rinite vasomotora", "pólipos nasais", "desvio de septo", "amigdalite",
    "faringite", "laringite", "traqueíte", "epiglotite", "abscesso peritonsilar",
    "mononucleose", "citomegalovírus", "herpes zoster", "varicela", "parvovírus",
    "vírus respiratório sincicial", "adenovírus", "enterovírus", "rotavírus", "norovírus",
    "giardíase", "amebíase", "toxoplasmose", "leishmaniose", "doença de Chagas",
    "hanseníase", "leptospirose", "brucelose", "salmonelose", "campilobacteriose",
    "shigelose", "escherichiosis", "clostridiose", "botulismo", "tétano",
    "difteria", "escarlatina", "febre reumática", "glomerulonefrite", "síndrome nefrótica",
    "insuficiência renal aguda", "insuficiência renal crônica", "diálise", "transplante renal", "cistite",
    "pielonefrite", "uretrite", "epididimite", "orquite", "prostatite bacteriana",
    "candidíase", "vaginose bacteriana", "tricomoníase", "gonorreia", "sífilis",
    "clamídia", "micoplasma", "ureaplasma", "HPV genital", "herpes genital",
    "hepatite delta", "hepatite E", "cirrose hepática", "câncer de fígado", "transplante hepático",
    "pancreatite crônica", "fibrose cística", "hemocromatose", "doença de Wilson", "deficiência de alfa-1-antitripsina",
    "porfiria", "metabolopatias", "fenilcetonúria", "galactosemia", "doença do xarope de bordo",
    "acidúria orgânica", "deficiência de biotinidase", "deficiência de carnitina", "glicogenose", "hiperlipidemia",
    "hipercolesterolemia familiar", "hipertrigliceridemia", "hipoglicemia", "hiperglicemia", "cetoacidose",
    "coma diabético", "hipotireoidismo", "hipertireoidismo", "bócio", "doença de Hashimoto",
    "doença de Graves", "adrenalina", "doença de Addison", "Síndrome de Cushing", "hiperaldosteronismo",
    "feocromocitoma", "diabetes insipidus", "hipoparatireoidismo", "hiperparatireoidismo", "doença óssea de Paget",
    "osteoporose", "osteomalácia", "artrose", "espondilite anquilosante", "Síndrome de Reiter",
    "gota", "pseudogota", "bursite", "tendinite", "fasceíte plantar",
    "síndrome do túnel do carpo", "síndrome do piriforme", "hérnia de disco", "ciática", "lombalgia",
    "cervicalgia", "dor no ombro", "congelamento do ombro", "epicondilite", "lesão do LCA",
    "entorse de tornozelo", "fratura", "luxação", "contratura", "distensão muscular",
    "síndrome da fadiga crônica", "fibromialgia", "síndrome de Ehlers-Danlos", "síndrome de Marfan", "neurofibromatose",
    "esclerose tuberosa", "doença de von Hippel-Lindau", "ataxia", "paraplegia", "tetraplegia",
    "distrofia muscular", "miastenia gravis", "neuropatia periférica", "neurite", "neuralgia",
    "neuralgia do trigêmeo", "paralisia de Bell", "síndrome de Guillain-Barré", "polirradiculopatia", "mielite",
    "siringomielia", "tumor medular", "meningioma", "glioma", "meduloblastoma",
    "hidrocefalia", "microcefalia", "macrocefalia", "anencefalia", "espinha bífida",
    "Síndrome de Rubinstein-Taybi", "Síndrome de Patau", "Síndrome de Edwards", "Síndrome de Turner", "Síndrome de Klinefelter",
    "Síndrome de Prader-Willi", "Síndrome de Angelman", "Síndrome de Williams", "Síndrome de Noonan", "Síndrome de Cornélia de Lange",
    "Síndrome de Rett", "Síndrome de Kleefstra", "Síndrome de X frágil", "Síndrome de Aicardi", "Síndrome de Bourneville",
    "doença de Pompe", "doença de Gaucher", "doença de Fabry", "doença de Niemann-Pick", "gangliosidose",
    "leucodistrofia", "adrenoleucodistrofia", "síndrome de Zellweger", "acidúria glutárica", "deficiência de MCAD",
    "hiperhomocisteinemia", "homocistinúria", "cistinúria", "tirosinemia", "acidemia propiônica",
    "acidemia metilmalônica", "holocarboxilase", "deficiência de biotinidase", "hiperamonemia", "ciclo da ureia",
    "intolerância a frutose", "doença do armazenamento de glicogênio", "porfiria aguda", "síndrome de Gilbert", "síndrome de Crigler-Najjar",
    "síndrome de Dubin-Johnson", "colestase intra-hepática", "atresia biliar", "cistos de colédoco", "pancreatite hereditária",
    "telangiectasia hemorrágica", "púrpura de Henoch-Schönlein", "vasculite", "arterite de Takayasu", "poliarterite nodosa",
    "granulomatose de Wegener", "síndrome de Churg-Strauss", "doença de Kawasaki", "doença de Behçet", "síndrome de Goodpasture",
    "glomerulonefrite rapidamente progressiva", "nefropatia por IgA", "síndrome nefrótica congênita", "cistinose", "oxalose",
    "urolitíase", "nefrocalcinose", "acidose tubular renal", "síndrome de Fanconi", "diabetes insípido nefrogênico",
    "hipercalciúria", "hipocalciúria", "hipercalemia", "hipocalemia", "hipernatremia",
    "hiponatremia", "hipermagnesemia", "hipomagnesemia", "hiperfosfatemia", "hipofosfatemia"
]

DECLARACOES_PESSOAS_FAMOSAS = [
    ("Ayrton Senna", "Não há coincidências, há encontros."),
    ("Pelé", "O sucesso não é um acidente. É trabalho duro, perseverança, aprendizado, estudo, sacrifício e, acima de tudo, amor pelo que você está fazendo."),
    ("Nelson Mandela", "A educação é a arma mais poderosa que você pode usar para mudar o mundo."),
    ("Martin Luther King", "Eu tenho um sonho que meus quatro pequenos filhos viverão em uma nação onde não serão julgados pela cor da pele, mas pelo conteúdo do caráter."),
    ("Mahatma Gandhi", "Seja a mudança que você quer ver no mundo."),
    ("Albert Einstein", "A imaginação é mais importante que o conhecimento."),
    ("Mário Quintana", "A vida é a arte do encontro, embora haja tanto desencontro pela vida."),
    ("Carlos Drummond de Andrade", "No meio do caminho tinha uma pedra."),
    ("Clarice Lispector", "E eu estou aqui, feita de um jeito que você não vê."),
    ("Machado de Assis", "A vida é uma ópera e uma grande ópera."),
    ("Fernando Pessoa", "Tudo vale a pena quando a alma não é pequena."),
    ("Vinicius de Moraes", "Que a tristeza não te impeça de ser feliz."),
    ("Cora Coralina", "Feliz aquele que transfere o que sabe e aprende o que ensina."),
    ("Milton Nascimento", "Quem sabe faz a hora, não espera acontecer."),
    ("Caetano Veloso", "Nenhum poeta é tão sábio quanto um louco."),
    ("Jorge Amado", "Deus não escreve certo por linhas tortas, mas também não escreve tudo direito."),
    ("Guimarães Rosa", "O correr da vida embrulha tudo, a vida é assim: esquenta e esfria, aperta e daí afrouxa, sossega e depois desinquieta."),
    ("Paulo Freire", "A educação não transforma o mundo. Educação muda as pessoas. Pessoas transformam o mundo."),
    ("Darcy Ribeiro", "A crise não é um acidente, é um processo. A crise é a própria vida."),
    ("Leonardo da Vinci", "A simplicidade é a sofisticação suprema."),
    ("Friedrich Nietzsche", "O que não me mata, me fortalece."),
    ("Sócrates", "Só sei que nada sei."),
    ("Platão", "A necessidade é a mãe da invenção."),
    ("Aristóteles", "A excelência é uma arte conquistada por meio de treinamento e hábito."),
    ("Immanuel Kant", "O homem é aquilo que a educação faz dele."),
    ("Jean-Jacques Rousseau", "O homem nasce bom, a sociedade o corrompe."),
    ("Voltaire", "Discordo do que você diz, mas defenderei até a morte o seu direito de dizê-lo."),
    ("Galileu Galilei", "E, no entanto, ela se move."),
    ("Isaac Newton", "O que sabemos é uma gota; o que ignoramos é um oceano."),
    ("Charles Darwin", "Não é a espécie mais forte que sobrevive, nem a mais inteligente, mas a que melhor se adapta às mudanças."),
    ("Marie Curie", "Nada na vida deve ser temido, apenas compreendido."),
    ("Stephen Hawking", "A inteligência é a capacidade de se adaptar às mudanças."),
    ("Steve Jobs", "A inovação distingue um líder de um seguidor."),
    ("Bill Gates", "Trate os outros como gostaria que eles o tratassem."),
    ("Mark Zuckerberg", "O maior risco é não correr nenhum risco."),
    ("Elon Musk", "Quando algo é importante o suficiente, você faz, mesmo que as chances não estejam a seu favor."),
    ("Oscar Niemeyer", "A arquitetura é a forma de expressão mais importante da cultura."),
    ("Aleijadinho", "A arte é o único meio de imortalizar a alma."),
    ("Tarsila do Amaral", "Eu queria ter nascido sem sexo, sem pátria, sem religião."),
    ("Portinari", "A arte é a vida intensa, a vida transfigurada."),
    ("Glauber Rocha", "Uma ideia é uma coisa, outra é a realização."),
    ("Silvio Santos", "Quem quer, faz acontecer."),
    ("Hebe Camargo", "A vida é feita de momentos, e os momentos são feitos de amor."),
    ("Jô Soares", "A inteligência é a única ferramenta que a gente não pode comprar."),
    ("Ziraldo", "A vida é a arte de não perder o entusiasmo."),
    ("Mauricio de Sousa", "A imaginação é o começo da criação."),
    ("Chico Anysio", "A felicidade é um prato que se come com a colher da simplicidade."),
    ("Dercy Gonçalves", "A vida é uma comédia para quem pensa e uma tragédia para quem sente."),
    ("Gugu Liberato", "Acredite nos seus sonhos, eles podem se tornar realidade."),
    ("Xuxa", "Sonhar é preciso, mas realizar é fundamental."),
    ("Fausto Silva", "A vida é um show, e cada um de nós é o protagonista."),
    ("Sabrina Sato", "Acredite no seu potencial, você é capaz de tudo."),
    ("Fábio Porchat", "A graça da vida é encontrar humor nas adversidades."),
    ("Tatá Werneck", "O importante é não se levar a sério demais."),
    ("Nelson Rodrigues", "O sentimento é a única coisa que não se pode comprar."),
    ("Rubem Braga", "A crônica é a amiga das coisas pequenas."),
    ("Euclides da Cunha", "O sertanejo é, antes de tudo, um forte."),
    ("Joaquim Nabuco", "A liberdade é a condição de todo o progresso."),
    ("Ruy Barbosa", "A justiça é a verdade em ação."),
    ("Fernando Henrique Cardoso", "O futuro não é uma herança, é uma construção."),
    ("Luiz Inácio Lula da Silva", "Se precisar, vá à luta."),
    ("Dilma Rousseff", "A persistência é o caminho para a superação."),
    ("Getúlio Vargas", "A democracia é o regime do povo."),
    ("Juscelino Kubitschek", "O desenvolvimento é o nome da paz."),
    ("Tancredo Neves", "A política é a arte de tornar possível o impossível."),
    ("Maria da Penha", "A luta contra a violência é diária e necessária."),
    ("Irmã Dulce", "A caridade é a maior das virtudes."),
    ("Padre Cícero", "A fé move montanhas, e o amor move o mundo."),
    ("Santos Dumont", "A persistência é a chave do progresso."),
    ("Oswaldo Cruz", "A saúde é um direito de todos e um dever do Estado."),
    ("César Lattes", "A ciência é a busca incansável pela verdade."),
    ("Miguel Nicolelis", "O cérebro é a fronteira final da medicina."),
    ("Nise da Silveira", "A loucura é uma forma de expressão da alma."),
    ("Zilda Arns", "O amor se prova pelo cuidado com o outro."),
    ("Anísio Teixeira", "A educação é a base de uma sociedade justa."),
    ("Dom Hélder Câmara", "Quando dou pão aos pobres, me chamam de santo; quando pergunto por que eles são pobres, me chamam de comunista."),
    ("George Herman Becker", "A inovação surge da ousadia de perguntar o que ninguém perguntou antes.")
]

DATAS_HISTORICAS = [
    ("1500", "Descobrimento do Brasil - Pedro Álvares Cabral chegou ao Brasil."),
    ("1822", "Independência do Brasil - Dom Pedro I proclamou a Independência."),
    ("1888", "Abolição da Escravatura - Lei Áurea assinada pela Princesa Isabel."),
    ("1964", "Golpe Militar no Brasil - início da ditadura militar."),
    ("1985", "Fim da ditadura militar - redemocratização do Brasil."),
    ("1994", "Plano Real - implantado para controlar a inflação."),
    ("2002", "Brasil conquista o pentacampeonato mundial de futebol."),
    ("2013", "Jornadas de Junho - protestos em todo o Brasil."),
    ("2016", "Impeachment da presidenta Dilma Rousseff."),
    ("1917", "Revolução Russa - queda do Império Russo."),
    ("1939", "Início da Segunda Guerra Mundial."),
    ("1945", "Fim da Segunda Guerra Mundial."),
    ("1969", "Chegada do homem à Lua."),
    ("1989", "Queda do Muro de Berlim."),
    ("2001", "Atentados de 11 de setembro nos Estados Unidos."),
    ("1549", "Chegada dos jesuítas ao Brasil - início da catequese."),
    ("1572", "Divisão do Brasil em duas capitanias hereditárias."),
    ("1630", "Invasão holandesa no Nordeste brasileiro."),
    ("1695", "Morte de Zumbi dos Palmares."),
    ("1750", "Tratado de Madri - definição de fronteiras no Brasil."),
    ("1763", "Transferência da capital do Brasil de Salvador para o Rio de Janeiro."),
    ("1808", "Chegada da família real portuguesa ao Brasil."),
    ("1817", "Revolução Pernambucana."),
    ("1831", "Abdicação de Dom Pedro I."),
    ("1840", "Golpe da Maioridade - Dom Pedro II assume."),
    ("1865", "Fim da Guerra do Paraguai."),
    ("1889", "Proclamação da República."),
    ("1891", "Primeira constituição republicana."),
    ("1930", "Revolução de 1930 - Getúlio Vargas assume."),
    ("1937", "Estado Novo - ditadura de Getúlio Vargas."),
    ("1942", "Brasil entra na Segunda Guerra Mundial ao lado dos Aliados."),
    ("1954", "Suicídio de Getúlio Vargas."),
    ("1960", "Inauguração de Brasília."),
    ("1968", "AI-5 - endurecimento do regime militar."),
    ("1979", "Lei da Anistia."),
    ("1984", "Campanha Diretas Já."),
    ("1988", "Promulgação da atual Constituição Federal."),
    ("1990", "Governo Collor e confisco da poupança."),
    ("1992", "Impeachment de Collor."),
    ("1998", "Segundo mandato de FHC."),
    ("2003", "Lula assume pela primeira vez."),
    ("2010", "Dilma Rousseff é eleita primeira mulher presidente do Brasil."),
    ("2014", "Brasil sediou a Copa do Mundo de Futebol."),
    ("2016", "O Rio de Janeiro sediou os Jogos Olímpicos."),
    ("2018", "Jair Bolsonaro é eleito presidente do Brasil."),
    ("2019", "Crise na Amazônia - incêndios e pressão internacional."),
    ("2020", "Pandemia de COVID-19 - início da crise sanitária global."),
    ("2021", "Vacinação em massa contra a COVID-19 no Brasil."),
    ("2022", "Brasil comemora o bicentenário da Independência."),
    ("2022", "Luiz Inácio Lula da Silva é eleito presidente para o terceiro mandato."),
    ("2023", "Atos golpistas em Brasília - invasão do Congresso e Palácio do Planalto."),
    ("2023", "Acordo Mercosul-UE em fase final."),
    ("2024", "Eleições municipais no Brasil."),
    ("2024", "Enchentes no Rio Grande do Sul - maior tragédia climática da história."),
    ("2025", "COP30 - Conferência da ONU sobre Mudanças Climáticas em Belém."),
    ("2025", "Brasil assume presidência do G20."),
    ("2026", "Comemoração dos 200 anos da primeira constituição brasileira."),
    ("2026", "Megaprojecção de energia solar no sertão nordestino."),
    ("2026", "Nova missão espacial brasileira com foguete VLM."),
    ("1492", "Chegada de Cristóvão Colombo à América."),
    ("1532", "Fundação da primeira vila no Brasil - São Vicente."),
    ("1551", "Criação do primeiro bispado no Brasil, em Salvador."),
    ("1592", "Invasão inglesa no Rio de Janeiro."),
    ("1624", "Invasão holandesa em Salvador."),
    ("1654", "Reconquista de Recife pelos portugueses - fim da invasão holandesa."),
    ("1680", "Fundação da Colônia do Sacramento pelos portugueses."),
    ("1711", "Piratas franceses invadem o Rio de Janeiro."),
    ("1720", "Revolta de Vila Rica (Minas Gerais)."),
    ("1776", "Declaração de Independência dos Estados Unidos."),
    ("1789", "Inconfidência Mineira."),
    ("1798", "Conjuração Baiana (dos Alfaiates)."),
    ("1808", "Abertura dos portos do Brasil às nações amigas."),
    ("1810", "Tratado de Comércio e Navegação com a Inglaterra."),
    ("1821", "Dom Pedro I fica no Brasil (Dia do Fico)."),
    ("1823", "Dissolução da Assembleia Constituinte."),
    ("1824", "Primeira Constituição do Brasil - outorgada por Dom Pedro I."),
    ("1825", "Reconhecimento da Independência do Brasil por Portugal."),
    ("1826", "Morte de Dom Pedro I."),
    ("1828", "Guerra da Cisplatina - perda do Uruguai."),
    ("1835", "Guerra dos Farrapos (Revolução Farroupilha) - início."),
    ("1845", "Fim da Guerra dos Farrapos - assinatura do Tratado de Ponche Verde."),
    ("1850", "Lei Eusébio de Queirós - proibição do tráfico negreiro."),
    ("1864", "Início da Guerra do Paraguai."),
    ("1870", "Lei do Ventre Livre - filhos de escravas nascem livres."),
    ("1885", "Lei dos Sexagenários - libertação de escravos com 60 anos."),
    ("1889", "Proclamação da República - Marechal Deodoro da Fonseca."),
    ("1893", "Revolução Federalista no Sul do Brasil."),
    ("1896", "Guerra de Canudos - conflito no sertão baiano."),
    ("1897", "Fim da Guerra de Canudos."),
    ("1910", "Revolta da Chibata - marinheiros no Rio de Janeiro."),
    ("1912", "Guerra do Contestado - conflito no Paraná."),
    ("1916", "Revolta dos sargentos."),
    ("1922", "Semana de Arte Moderna - marco do modernismo."),
    ("1924", "Revolta Tenentista em São Paulo."),
    ("1932", "Revolução Constitucionalista de São Paulo."),
    ("1938", "Intentona Integralista - tentativa de golpe."),
    ("1944", "Força Expedicionária Brasileira (FEB) na Itália."),
    ("1945", "Fim da Segunda Guerra - redemocratização no Brasil."),
    ("1946", "Nova constituição democrática."),
    ("1948", "Criação da ONU - Brasil é membro fundador."),
    ("1950", "Copa do Mundo de 1950 - Brasil vice-campeão (Maracanazo)."),
    ("1951", "Criação da Petrobras."),
    ("1953", "Criação da CNPq."),
    ("1956", "Início da construção de Brasília."),
    ("1958", "Brasil conquista o primeiro título mundial de futebol."),
    ("1961", "Renúncia de Jânio Quadros e posse de João Goulart (Jango)."),
    ("1962", "Brasil bicampeão mundial de futebol."),
    ("1964", "Golpe militar - início da ditadura."),
    ("1965", "Criação do SNI (Serviço Nacional de Informações)."),
    ("1966", "Ato Institucional nº 2 - extinção dos partidos políticos."),
    ("1967", "Constituição de 1967 - institucionaliza a ditadura."),
    ("1968", "Passeata dos Cem Mil no Rio de Janeiro."),
    ("1969", "Emenda Constitucional nº 1 - endurece o regime."),
    ("1970", "Brasil tricampeão mundial de futebol no México."),
    ("1973", "Crise do petróleo e impacto no Brasil."),
    ("1974", "Governo Geisel - início da abertura política."),
    ("1978", "Criação do Partido dos Trabalhadores (PT)."),
    ("1980", "Greve do ABC - movimento sindical."),
    ("1981", "Atentado do Riocentro - atentado terrorista no Rio."),
    ("1982", "Eleições diretas para governadores."),
    ("1985", "Morte de Tancredo Neves e posse de José Sarney."),
    ("1986", "Plano Cruzado - tentativa de controle da inflação."),
    ("1988", "Constituição de 1988 - promulgada."),
    ("1989", "Primeira eleição direta para presidente após a ditadura - Collor."),
    ("1990", "Governo Collor - confisco da poupança e abertura comercial."),
    ("1992", "Rio-92 - Conferência da ONU sobre Meio Ambiente."),
    ("1993", "Plebiscito sobre forma de governo - presidencialismo."),
    ("1995", "Fernando Henrique Cardoso assume o primeiro mandato."),
    ("1996", "Criação do Mercosul (com Paraguai e Uruguai)."),
    ("1997", "Crise financeira asiática."),
    ("1999", "Desvalorização do real - crise cambial."),
    ("2000", "Brasil comemora 500 anos do descobrimento."),
    ("2001", "Apagão elétrico - crise de energia."),
    ("2002", "Lula eleito presidente - primeira vez."),
    ("2003", "Lançamento do programa Fome Zero."),
    ("2004", "Brasil ganha a Copa América."),
    ("2005", "Escândalo do mensalão."),
    ("2006", "Lula reeleito - segundo mandato."),
    ("2007", "Descoberta do pré-sal."),
    ("2008", "Crise financeira internacional."),
    ("2009", "Rio de Janeiro é escolhido para as Olimpíadas de 2016."),
    ("2011", "Dilma Rousseff assume - primeira mulher presidenta."),
    ("2012", "Rio+20 - Conferência da ONU sobre Desenvolvimento Sustentável."),
    ("2013", "Protestos contra o aumento das passagens de ônibus."),
    ("2014", "Copa do Mundo no Brasil - Alemanha campeã."),
    ("2015", "Operação Lava Jato - investigação de corrupção."),
    ("2016", "Impeachment de Dilma - Michel Temer assume."),
    ("2017", "Reforma trabalhista - flexibilização dos direitos."),
    ("2018", "Greve dos caminhoneiros - paralisação nacional."),
    ("2019", "Inauguração do novo aeroporto de Salvador."),
    ("2020", "Início da vacinação contra COVID-19 no Brasil."),
    ("2021", "CPI da Pandemia no Senado Federal."),
    ("2022", "Copa do Mundo no Catar - Brasil eliminado."),
    ("2023", "Desastre em Brumadinho - reabertura do caso."),
    ("2024", "Taxa de desemprego atinge menor nível desde 2015."),
    ("2025", "Nova lei sobre inteligência artificial é aprovada."),
    ("2026", "Brasil sedia o G20 e eventos climáticos de grande porte.")
]
GEOPOLITICA = [
    "União Europeia", "OTAN", "ONU", "Mercosul", "BRICS",
    "Conflito entre Israel e Palestina", "Guerra na Ucrânia",
    "Crise migratória na Europa", "Aquecimento global",
    "Acordos de Paris", "Reforma da ONU", "Nova Ordem Mundial",
    "Império Americano", "Ascensão da China", "Guerra Fria 2.0",
    "Ciberguerra", "Espionagem internacional", "Diplomacia",
    "Organização dos Estados Americanos", "União Africana", "Liga Árabe",
    "Conselho de Segurança da ONU", "Corte Internacional de Justiça",
    "Tribunal Penal Internacional", "Tratado de Não Proliferação Nuclear",
    "Acordo de Paris", "Protocolo de Kyoto", "Conferência das Nações Unidas sobre Mudança Climática",
    "Cúpula do G7", "Cúpula do G20", "Fórum Econômico Mundial",
    "Banco Mundial", "FMI", "OMC", "BID",
    "América Latina", "Ásia-Pacífico", "Oriente Médio", "África Subsariana",
]

CIENCIA = [
    "física quântica", "biologia molecular", "astrofísica", "genética", "evolução",
    "termodinâmica", "relatividade", "mecânica quântica", "cosmologia", "neurociência",
    "ecologia", "paleontologia", "mineralogia", "oceanografia", "meteorologia",
    "astronomia", "ciência de materiais", "ciência dos polímeros",
    "ciência dos alimentos", "ciência do solo", "ciências agrárias",
    "engenharia genética", "biologia sintética", "criogenia",
    "física de partículas", "física nuclear", "física da matéria condensada",
]

HISTORIA = [
    "Revolução Francesa", "Império Romano", "Descobrimentos", "Segunda Guerra Mundial",
    "Idade Média", "Renascimento", "Guerra Fria", "Revolução Industrial",
    "Independência dos EUA", "Unificação da Itália", "Queda do Muro de Berlim",
    "Idade Antiga", "Antigo Egito", "Grécia Antiga", "Civilização Maia",
    "Civilização Inca", "Civilização Asteca", "Império Mongol",
    "Império Bizantino", "Império Otomano", "Império Persa",
    "Guerra dos Cem Anos", "Guerra das Rosas", "Revolução Gloriosa",
    "Revolução Americana", "Revolução Cubana", "Revolução Mexicana",
    "Primeira Guerra Mundial", "Guerra do Vietnã", "Guerra da Coreia",
    "Guerra das Malvinas", "Conflito do Golfo", "Guerra do Iraque",
    "Civilização Mesopotâmica", "Civilização Fenícia", "Civilização Hebraica",
    "Império Assírio", "Império Babilônico", "Império Aquemênida",
    "Império Macedônico", "Império Selêucida", "Império Parta",
    "Império Sasânida", "Império Gupta", "Império Kushan",
    "Império Han", "Império Tang", "Império Songhai",
    "Império Mali", "Império Gana", "Império Axumita",
    "Império Inca", "Império Asteca", "Império Tupi-Guarani",
    "Período Paleolítico", "Período Neolítico", "Idade dos Metais",
    "Revolução Neolítica", "Invenção da Escrita", "Código de Hamurabi",
    "Guerra de Troia", "Guerras Médicas", "Guerra do Peloponeso",
    "Reino de Alexandre", "Império de Péricles", "República Romana",
    "Império Romano do Ocidente", "Império Romano do Oriente", "Invasões Bárbaras",
    "Reino Franco", "Império Carolíngio", "Cisma do Oriente",
    "Cruzadas", "Inquisição", "Reforma Protestante",
    "Contrarreforma", "Guerra dos Trinta Anos", "Tratado de Vestfália",
    "Revolução Científica", "Iluminismo", "Enciclopédia",
    "Revolução Haitiana", "Independência do Haiti", "Guerra Civil Americana",
    "Abolicionismo", "Segundo Império Francês", "Unificação Alemã",
    "Império Austro-Húngaro", "Revolução de 1848", "Comuna de Paris",
    "Imperialismo", "Partilha da África", "Conferência de Berlim",
    "Guerra Russo-Japonesa", "Revolução de 1905", "Revolução Chinesa",
    "Revolução Russa de 1917", "Tratado de Versalhes", "Grande Depressão",
    "New Deal", "Nazismo", "Fascismo",
    "Holocausto", "Bombardeios de Hiroshima e Nagasaki", "ONU",
    "Plano Marshall", "OTAN", "Pacto de Varsóvia",
    "Guerra de Independência de Israel", "Crise de Suez", "Guerra dos Seis Dias",
    "Guerra de Yom Kippur", "Guerra Irã-Iraque", "Guerra do Afeganistão",
    "Revolução Iraniana", "Primavera Árabe", "Guerra Civil Síria",
    "Brexit", "Pandemia de COVID-19", "Revolução Digital",
    "Descobrimento do Brasil", "Brasil Colônia", "Brasil Império",
    "Guerra dos Farrapos", "Cabanagem", "Balaiada",
    "Sabinada", "Revolução Praieira", "Guerra do Paraguai",
    "Proclamação da República", "Revolução Federalista", "Guerra de Canudos",
    "Guerra do Contestado", "Revolta da Vacina", "Revolta da Chibata",
    "Semana de Arte Moderna", "Tenentismo", "Revolução de 1930",
    "Estado Novo", "Segunda Guerra Mundial no Brasil", "Redemocratização de 1945",
    "Governos de 1946-1964", "Golpe de 1964", "Ditadura Militar",
    "AI-5", "Diretas Já", "Constituição de 1988",
    "Governos Collor e Itamar", "Plano Real", "Governo FHC",
    "Governo Lula", "Escândalo do Mensalão", "Copa do Mundo 2014",
    "Olimpíadas Rio 2016", "Impeachment de Dilma", "Governo Temer",
    "Governo Bolsonaro", "Pandemia no Brasil", "Governo Lula 2023",
    "Atos Golpistas de 2023", "Enchentes no Sul 2024", "COP30 em Belém"
]

FILOSOFIA = [
    "existencialismo", "estoicismo", "utilitarismo", "fenomenologia",
    "materialismo", "idealismo", "niilismo", "absurdismo",
    "contratualismo", "liberalismo", "anarquismo", "marxismo",
    "platonismo", "aristotelismo", "tomismo", "cartesianismo",
    "kantianismo", "hegelianismo", "positivismo", "empirismo",
    "racionalismo", "ceticismo", "epicurismo", "hedonismo",
    "estruturalismo", "pós-estruturalismo", "desconstrução",
    "hermenêutica", "fenomenologia existencial",
]

LITERATURA = [
    "realismo", "modernismo", "barroco", "romantismo", "classicismo",
    "naturalismo", "simbolismo", "futurismo", "dadaísmo", "surrealismo",
    "O Cortiço", "Vidas Secas", "Capitães da Areia", "A Hora da Estrela",
    "A Moreninha", "Memórias de um Sargento de Milícias", "O Guarani",
    "Iracema", "Ubirajara", "O Mulato", "Bom Crioulo", "O Ateneu",
    "São Bernardo", "Angústia", "A Bagaceira", "Menino de Engenho",
    "Fogo Morto", "O Quinze", "Aves de Arribação", "O Tempo e o Vento",
    "A Morte e a Morte de Quincas Berro d'Água", "Gabriela, Cravo e Canela",
    "Dona Flor e Seus Dois Maridos", "Tenda dos Milagres",
    "O Sumiço da Santa", "O Incrível Hulk",
    "O Espelho", "A Carteira", "Um Homem Célebre", "Teoria do Medalhão",
    "O Alienista", "A Chinela Turca", "Na Arca", "Esaú e Jacó",
    "Ressurreição", "A Mão e a Luva", "Helena", "Iaiá Garcia",
    "O Seminarista", "O Tronco do Ipê", "A Pata da Gazela",
    "Lucíola", "Diva", "A Viuvinha", "Cinco Minutos",
    "O Primo Basílio", "O Crime do Padre Amaro", "A Relíquia",
    "A Cidade e as Serras", "Os Maias", "Casa de Pensão",
    "Caramuru", "O Uraguai", "O Caramujo",
    "Cem Anos de Solidão", "O Amor nos Tempos do Cólera", "Crônica de uma Morte Anunciada",
    "A Casa dos Espíritos", "A Saga de Kane e Abel", "O Nome da Rosa",
    "O Código Da Vinci", "A Menina que Roubava Livros", "O Caçador de Pipas",
    "A Lista de Schindler", "O Diário de Anne Frank", "A Revolução dos Bichos",
    "O Lobo da Estepe", "Siddhartha", "Demian", "O Estrangeiro",
    "A Peste", "O Mito de Sísifo", "O Homem Revoltado",
    "A Montanha Mágica", "Os Buddenbrook", "Doutor Fausto",
    "O Processo", "O Castelo", "A Metamorfose",
    "Ulisses", "Finnegans Wake", "O Retrato do Artista quando Jovem",
    "Mrs Dalloway", "Ao Farol", "Orlando",
    "O Grande Gatsby", "Por Quem os Sinos Dobram", "O Sol Também se Levanta",
    "Adeus às Armas", "As Vinhas da Ira", "O Velho e o Mar",
    "A Peste", "O Estrangeiro", "A Queda",
    "O Silêncio dos Inocentes", "O Colecionador", "O Exorcista",
    "O Iluminado", "Carrie", "A Dança da Morte",
    "O Filho Eterno", "A Elite do Atraso", "O Avesso da Pele",
    "Torto Arado", "O Vento Tudo", "O Olho da Rua",
    "Machado de Assis", "Clarice Lispector", "Guimarães Rosa", "Graciliano Ramos",
    "Jorge Amado", "Érico Veríssimo", "José Lins do Rego", "Raquel de Queiroz",
    "Aluísio Azevedo", "Joaquim Manuel de Macedo", "José de Alencar",
    "Bernardo Guimarães", "Alfredo d'Escragnolle Taunay", "Visconde de Taunay",
    "Coelho Neto", "Lima Barreto", "Mário de Andrade", "Oswald de Andrade",
    "Carlos Drummond de Andrade", "Cecília Meireles", "João Cabral de Melo Neto",
    "Ferreira Gullar", "Adélia Prado", "Rubem Braga", "Nelson Rodrigues",
    "arcadismo", "pré-modernismo", "expressionismo", "existencialismo",
    "neorrealismo", "pós-modernismo", "concretismo", "tropicalismo",
    "literatura de cordel", "literatura infantil", "literatura juvenil",
    "quadrinhos", "romance de formação", "romance histórico",
    "romance policial", "literatura fantástica", "ficção científica",
    "distopia", "utopia", "cronista", "ensaísta", "contista",
    "poesia concreta", "haicai", "soneto", "ode", "elegia", "sátira",
    "Dom Quixote", "Os Lusíadas", "Paraíso Perdido", "A Divina Comédia",
    "A Ilíada", "A Odisseia", "Eneida", "Metamorfoses",
    "As Flores do Mal", "O Corvo", "Canção de Ninar",
    "Dom Casmurro", "Memórias Póstumas de Brás Cubas", "Quincas Borba",
    "A Mão e a Luva", "Iaiá Garcia", "Ressurreição", "Contos Fluminenses",
    "Histórias da Meia-Noite", "Papéis Avulsos", "Obra Completa de Machado",
    "A Paixão segundo G.H.", "Água Viva", "A Maçã no Escuro",
    "Felicidade Clandestina", "Onde Estivestes de Noite", "A Via Crucis do Corpo",
    "O Lustre", "Perto do Coração Selvagem", "A Cidade Sitiada",
    "O Grande Sertão: Veredas", "Sagarana", "Campo Geral",
    "Primeiras Estórias", "Tutaméia", "Corpo de Baile",
    "O Recado do Morro", "A Hora da Estrela", "A Legião Estrangeira",
    "As Palavras", "O Apocalipse", "Bom Dia para os Defuntos",
    "Cantos de Maldoror", "Um Sopro de Vida", "O Mistério do Ursinho",
    "A Guerra do Fim do Mundo", "A Morte de D. Quixote",
    "A Fada no Oriente", "O Beijo na Face",
    "A Batalha do Apocalipse", "O Profeta", "O Alquimista",
    "Onze Minutos", "Veronika Decide Morrer", "O Diário de um Mago",
    "Brida", "Na Margem do Rio Piedra", "A Quinta Montanha",
    "A Cabana", "O Perfume", "O Mentiroso", "O Jogo do Anjo",
    "A Sombra do Vento", "O Cemitério dos Livros Esquecidos",
    "O Labirinto dos Espíritos", "O Prisioneiro do Céu",
    "A Menina que Não Sabia Pedir", "A Mulher que Escreveu a Bíblia",
    "O Livro dos Abraços", "O Amanhã", "O Gato Preto",
    "O Coração Delator", "A Queda da Casa de Usher", "Os Assassinatos da Rua Morgue",
    "Frankenstein", "Drácula", "O Médico e o Monstro",
    "O Homem Invisível", "A Máquina do Tempo", "O Mundo Perdido",
    "A Volta ao Mundo em 80 Dias", "Vinte Mil Léguas Submarinas",
    "O Conde de Monte Cristo", "Os Três Mosqueteiros", "O Corcunda de Notre-Dame",
    "Os Miseráveis", "Guerra e Paz", "Anna Karenina",
    "Crime e Castigo", "Os Irmãos Karamazov", "O Idiota",
    "O Jogador", "Memórias do Subsolo", "A Morte de Ivan Ilitch",
    "Ressurreição", "Sonata a Kreutzer", "Feliz Ano Novo",
    "O Eterno Marido", "O Duplo", "Noites Brancas",
    "O Pequeno Príncipe", "O Príncipe", "O Livro do Tempo",
    "Alice no País das Maravilhas", "Peter Pan", "O Mágico de Oz",
    "O Vento nos Salgueiros", "O Ursinho Puff", "A Floresta Encantada",
    "A Princesa e o Sapo", "Cinderela", "Branca de Neve",
    "Os Sete Cabritinhos", "O Patinho Feio", "A Pequena Sereia",
    "Rapunzel", "João e Maria", "Chapeuzinho Vermelho",
    "O Gato de Botas", "A Bela e a Fera", "Aladdin",
    "O Vale dos Dinossauros", "O Enigma do T-Rex", "O Mundo de Sofia",
    "O Livro dos Seres Imaginários", "A História do Mundo em 50 Objetos",
    "O Gene", "A Origem das Espécies", "O Despertar de Tudo",
    "Guerra e Paz", "O Nome da Rosa", "A Cidade do Sol",
    "O Cavaleiro da Dinamarca", "A Ilha do Tesouro", "A Ilha do Dr. Moreau",
    "O Médico e o Monstro", "O Homem que Plantava Árvores",
    "O Velho e o Mar", "A Vida no Sertão", "O Sertão e o Mar",
    "O Monólogo do Pássaro", "O Canto do Cisne",
    "O Livro das Lendas", "Contos de Fadas dos Irmãos Grimm",
    "O Mar sem Estrelas", "O Palácio de Inverno", "A Casa dos Sete Gables",
    "A Letra Escarlate", "Moby Dick", "O Morro dos Ventos Uivantes",
    "Jane Eyre", "Orgulho e Preconceito", "Razão e Sensibilidade",
    "Mansfield Park", "Emma", "Persuasão",
    "A Abadia de Northanger", "O Estrangeiro", "A Náusea",
    "O Muro", "A Idade da Razão", "Os Justos",
    "O Estado de Sítio", "O Diabo e o Bom Deus", "As Moscas",
    "A Porta Estreita", "A Imoralista", "O Pastor de Cabras",
    "O Fim da Eternidade", "Fundação", "Eu, Robô",
    "O Sol Descalço", "A Mão Esquerda da Escuridão",
    "Neuromancer", "O Homem do Castelo Alto", "Androides Sonham com Ovelhas Elétricas?",
    "Duna", "O Guia do Mochileiro das Galáxias",
    "A Guerra dos Mundos", "O Planeta dos Macacos",
    "Fahrenheit 451", "Admirável Mundo Novo", "1984",
    "O Conto da Aia", "Laranja Mecânica", "O Jogo da Amarelinha",
    "O Dono do Mundo", "Nós", "A Máquina do Tempo",
    "O Homem de Giz", "O Silêncio da Montanha", "A Biblioteca da Meia-Noite",
    "Onde os Fracos Não Têm Vez", "A Estrada", "Sete Dias em Oito Meses",
    "O Giro do Mundo", "A Vida no Vermelho", "O Alquimista das Palavras",
    "O Livro de Areia", "Ficções", "O Aleph",
    "O Jardim de Caminhos que se Bifurcam", "A Biblioteca de Babel",
    "O Eterno Retorno", "O Enigma do Fim", "O Círculo de Tinta",
    "O Formigueiro", "A Formiga", "O Tempo e o Vento",
    "O Voo da Manhã", "A Estrela do Norte", "A Órbita do Sol",
    "O Menino do Pijama Listrado", "A Caçada ao Outono",
    "O Inverno das Memórias", "A Primavera dos Livros",
    "O Verão das Ilusões", "O Caos e a Ordem", "A Ordem e o Caos"
]

ECONOMIA = [
    "inflação", "taxa de juros", "PIB", "dívida pública", "câmbio",
    "bolsa de valores", "investimentos", "poupança", "crédito", "orçamento",
    "política fiscal", "política monetária", "comércio exterior", "exportação", "importação",
    "microeconomia", "macroeconomia", "economia do trabalho", "economia da educação",
    "economia da saúde", "economia ambiental", "economia solidária",
    "capitalismo", "socialismo", "liberalismo", "keynesianismo",
    "neoliberalismo", "desenvolvimento sustentável",
    "renda básica universal", "imposto de renda", "tributação",
    "desigualdade econômica", "pobreza", "exclusão social",
    "produto interno bruto", "renda per capita", "índice de Gini", "coeficiente de Gini",
    "curva de Lorenz", "inflação inercial", "inflação de demanda", "inflação de custos",
    "juros reais", "juros nominais", "selic", "taxa básica de juros",
    "câmbio flutuante", "câmbio fixo", "câmbio administrado", "câmbio nominal", "câmbio real",
    "balança comercial", "balança de pagamentos", "reservas internacionais",
    "déficit público", "superávit primário", "superávit nominal",
    "dívida externa", "dívida interna", "rolagem da dívida",
    "política de preços", "controle de preços", "tabelamento",
    "subsídio", "isenção fiscal", "incentivo fiscal",
    "economia informal", "subemprego", "desemprego estrutural", "desemprego cíclico",
    "custo de vida", "poder de compra", "moeda", "lastro", "padrão-ouro",
    "sistema financeiro", "banco central", "autoridade monetária",
    "seguro", "previdência", "fundos de pensão",
    "capital de giro", "capital fixo", "capital intelectual",
    "propriedade privada", "meios de produção", "mais-valia",
    "oferta e demanda", "equilíbrio de mercado", "preço de mercado",
    "custo de oportunidade", "trade-off", "escassez",
    "economia circular", "economia verde", "economia criativa",
    "fintechs", "criptomoedas", "blockchain", "tokenização",
    "IA na economia", "automação", "indústria 4.0",
    "comércio eletrônico", "marketplace", "economia de plataforma",
    "gig economy", "trabalho remoto", "freelancer",
    "produtividade", "eficiência", "competitividade",
    "globalização", "integração econômica", "blocos econômicos",
    "Mercosul", "União Europeia", "NAFTA", "USMCA",
    "BRICS", "G20", "FMI", "Banco Mundial", "OMC",
    "desenvolvimento econômico", "crescimento econômico", "crise econômica",
    "recessão", "depressão", "estagflação",
    "bolha especulativa", "bolha imobiliária", "bolha da internet",
    "crack da bolsa de 1929", "crise de 2008", "crise dos países nórdicos",
    "default", "calote", "moratória",
    "ajuste fiscal", "reforma tributária", "reforma previdenciária",
    "privatização", "estatização", "desestatização",
    "concessão", "parceria público-privada", "terceirização",
    "planejamento central", "economia planificada", "economia de mercado",
    "economia mista", "economia colaborativa", "economia compartilhada",
    "capitalismo de estado", "capitalismo de laços", "capitalismo popular",
    "teoria das vantagens comparativas", "protecionismo", "livre comércio",
    "barreiras tarifárias", "barreiras não tarifárias", "dumping",
    "sustentabilidade econômica", "indicadores sociais", "IDH",
    "pobreza absoluta", "pobreza relativa", "linha de pobreza",
    "distribuição de renda", "concentração de renda", "mobilidade social",
    "classe média", "classe trabalhadora", "elite econômica",
    "economia comportamental", "economia experimental", "economia feminista",
    "economia do gênero", "economia das desigualdades", "economia institucional",
    "economia política", "economia internacional", "economia regional",
    "economia urbana", "economia rural", "economia agrária",
    "agronegócio", "commodities", "preço das commodities",
    "cadeia produtiva", "valor agregado", "margem de lucro",
    "rentabilidade", "liquidez", "solvência",
    "análise fundamentalista", "análise técnica", "análise de risco",
    "rating", "grau de investimento", "risco país",
    "moeda forte", "moeda fraca", "desvalorização cambial",
    "apreciação cambial", "sobrevalorização", "subvalorização",
    "paridade do poder de compra", "indexação", "desindexação",
    "expectativas inflacionárias", "metas de inflação", "regime de metas",
    "choque de oferta", "choque de demanda", "choque externo",
    "efeito multiplicador", "propensão marginal a consumir", "multiplicador keynesiano",
    "curva de Phillips", "curva de Laffer", "curva de Kuznets",
    "trapaça do agente-principal", "assimetria de informação", "risco moral",
    "seleção adversa", "sinalização", "filtragem",
    "economia do bem-estar", "teoria dos jogos", "teoria das decisões",
    "equilíbrio geral", "ótimo de Pareto", "eficiência alocativa",
    "falhas de mercado", "bens públicos", "bens de mérito",
    "externalidades", "externalidade positiva", "externalidade negativa",
    "internalização de custos", "poluição", "créditos de carbono",
    "mercado de capitais", "ação", "debêntures", "títulos públicos",
    "CDB", "LCI", "LCA", "LC", "Tesouro Direto",
    "fundos de investimento", "ETFs", "commodity funds",
    "hedge", "derivativos", "swaps", "opções", "futuros",
    "day trade", "swing trade", "buy and hold",
    "dividendos", "JCP", "remuneração de capital",
    "planos de previdência", "capitalização", "seguro de vida",
    "sistema financeiro nacional", "BCB", "CVM", "CMN",
    "banco central do brasil", "ministério da economia", "fazenda",
    "receita federal", "procon", "proteste",
    "economia do petróleo", "pré-sal", "royalties",
    "energia renovável", "economia da energia", "matriz energética",
    "tarifa de luz", "água", "saneamento básico",
    "transporte público", "mobilidade urbana", "pedágio",
    "telecomunicações", "internet", "inclusão digital",
    "zona franca de Manaus", "polos industriais", "distritos industriais",
    "INC", "empreendedorismo", "startup", "unicórnio",
    "venture capital", "angel investor", "private equity",
    "crowdfunding", "financiamento coletivo", "microcrédito",
    "crédito rotativo", "cheque especial", "empréstimo consignado",
    "financiamento imobiliário", "financiamento de veículos", "crédito educacional",
    "programas sociais", "Bolsa Família", "Fome Zero",
    "auxílio emergencial", "renda de cidadania", "BPC",
    "salário mínimo", "piso salarial", "reajuste anual",
    "negociação coletiva", "sindicato", "convenção trabalhista",
    "FGTS", "INSS", "seguro-desemprego",
    "13º salário", "férias remuneradas", "horas extras",
    "jornada de trabalho", "trabalho infantil", "trabalho escravo",
    "economia do conhecimento", "capital humano", "cursos e capacitação",
    "pesquisa e desenvolvimento", "inovação tecnológica", "patentes",
    "propriedade intelectual", "softwares", "licenciamento",
    "royalties de música", "direitos autorais", "marcas e patentes",
    "economia da cultura", "economia do turismo", "economia do lazer",
    "indústria do entretenimento", "streaming", "bilheteria",
    "mercado publicitário", "marketing", "brand equity",
    "economia de dados", "big data", "inteligência analítica",
    "economia de fronteira", "fronteira agrícola", "expansão territorial",
    "reforma agrária", "assentamentos rurais", "latifúndio",
    "minifúndio", "produtor rural", "agricultura familiar",
    "agroindústria", "biotecnologia agrícola", "OGM",
    "pesca", "aquicultura", "silvicultura", "extrativismo",
    "mineração", "petróleo e gás", "indústria de transformação",
    "indústria química", "indústria farmacêutica", "indústria automotiva",
    "indústria de papel e celulose", "indústria têxtil", "indústria de alimentos",
    "indústria de bebidas", "indústria de fumo", "indústria moveleira",
    "construção civil", "engenharia civil", "infraestrutura",
    "logística", "transporte de cargas", "armazenagem",
    "portos", "aeroportos", "rodovias", "ferrovias",
    "hidrovias", "cabotagem", "navegação interior",
    "correios", "entrega de encomendas", "logística reversa",
    "comércio atacadista", "comércio varejista", "e-commerce",
    "fast food", "food service", "delivery",
    "hotelaria", "hospedagem", "aluguel de imóveis",
    "locação de veículos", "aluguel de equipamentos", "leasing",
    "franquias", "licenciamento de marcas", "terceirização de serviços",
    "consultoria", "auditoria", "contabilidade",
    "advocacia empresarial", "serviços jurídicos", "serviços notariais",
    "planos de saúde", "seguros de saúde", "clínicas particulares",
    "hospitais privados", "serviços odontológicos", "laboratórios de análises",
    "farmácias", "distribuidoras de medicamentos", "indústria farmacêutica",
    "reabilitação", "fisioterapia", "psicologia clínica",
    "educação privada", "escolas particulares", "cursos preparatórios",
    "idiomas", "cursos online", "plataformas de ensino",
    "tecnologia educacional", "robótica educacional", "kits didáticos",
    "materiais escolares", "livros didáticos", "editoras",
    "paper", "revistas", "jornais", "mídia impressa",
    "TV aberta", "TV por assinatura", "streaming de vídeo",
    "rádio", "podcast", "conteúdo digital",
    "redes sociais", "influenciadores", "marketing de afiliados",
    "monetização de conteúdo", "publicidade online", "SEO",
    "analytics", "métricas", "KPIs",
    "planejamento estratégico", "gestão de riscos", "fluxo de caixa",
    "capital de risco", "sociedade limitada", "sociedade anônima",
    "cooperativas", "associações", "fundações",
    "ONGs", "terceiro setor", "economia social",
    "impacto social", "investimento social", "filantropia",
    "voluntariado", "doações", "crowdsourcing",
    "economia do compartilhamento", "aluguel de espaço", "compartilhamento de carros",
    "bicicletas compartilhadas", "espaços de coworking", "coliving",
    "economia do cuidado", "trabalho doméstico", "cuidado de crianças",
    "cuidado de idosos", "serviços de limpeza", "manutenção residencial",
    "jardinagem", "petshop", "serviços para animais",
    "pet care", "creches", "escolas infantis",
    "ensino fundamental", "ensino médio", "ensino técnico",
    "graduação", "pós-graduação", "mestrado", "doutorado",
    "pesquisa científica", "extensão universitária", "incubadoras de negócios",
    "parques tecnológicos", "centros de inovação", "coworking",
    "aceleradoras", "seed investment", "série A", "série B",
    "IPO", "OTC", "bolsa de valores brasileira", "B3",
    "empresas listadas", "blue chips", "small caps",
    "large caps", "mid caps", "valor de mercado",
    "market cap", "lucro líquido", "receita bruta",
    "margem bruta", "margem líquida", "EBITDA",
    "alavancagem", "endividamento", "cobertura de juros",
    "rotatividade de estoque", "prazo médio de recebimento", "ciclo financeiro",
    "análise de balanço", "demonstrações contábeis", "balanço patrimonial",
    "DRE", "fluxo de caixa", "notas explicativas",
    "parecer de auditoria", "conselho fiscal", "comitê de auditoria",
    "governança corporativa", "compliance", "anti-corrupção",
    "ética empresarial", "responsabilidade social", "ESG",
    "ambiental", "social", "governança",
    "sustentabilidade", "relatório de sustentabilidade", "GRI",
    "ISO 14001", "certificações", "selo verde",
    "economia circular", "reciclagem", "reutilização",
    "descarte", "logística reversa", "resíduos sólidos",
    "energia solar", "energia eólica", "hidrelétrica",
    "termelétrica", "nuclear", "geotérmica",
    "biocombustíveis", "etanol", "biodiesel",
    "carros elétricos", "mobilidade sustentável", "transporte público de qualidade",
    "ciclovias", "caminhadas", "mobilidade ativa",
    "cidades inteligentes", "cidades sustentáveis", "cidades resilientes",
    "planejamento urbano", "zoneamento", "uso do solo",
    "habitação social", "minha casa minha vida", "aluguel social",
    "regularização fundiária", "escritura", "matrícula",
    "IPTU", "ITBI", "ITR",
    "taxas", "contribuições", "multas",
    "juros sobre capital próprio", "dividendos bonificados", "subscrição",
    "ações preferenciais", "ações ordinárias", "voto múltiplo",
    "tag along", "cláusulas de proteção", "drag along",
    "acordo de acionistas", "opção de compra", "warrants"
]

ESPORTES = [
    "futebol", "basquete", "vôlei", "natação", "atletismo",
    "tênis", "golfe", "ciclismo", "esportes radicais", "olímpiadas",
    "copa do mundo", "campeonato brasileiro", "NBA", "Fórmula 1", "MMA",
    "surfe", "skate", "snowboard", "esqui", "patinação no gelo",
    "ginástica artística", "ginástica rítmica", "judô", "karatê",
    "taekwondo", "boxe", "luta livre", "esgrima",
    "hipismo", "tiro esportivo", "arco e flecha",
    "triatlo", "pentatlo", "maratona", "ultramaratona",
    "esportes eletrônicos", "e-sports",
]

MITOLOGIA = [
    "mitologia grega", "mitologia nórdica", "mitologia egípcia", "mitologia celta",
    "deuses do Olimpo", "Thor", "Zeus", "Ísis", "Cthulhu", "lendas brasileiras",
    "saci", "curupira", "boitatá", "iara", "boto cor-de-rosa",
    "mitologia japonesa", "mitologia chinesa", "mitologia hindu",
    "mitologia maia", "mitologia asteca", "mitologia inca",
    "mitologia tupi", "mitologia guarani", "mitologia africana",
    "criaturas míticas", "dragões", "unicórnios", "grifos",
    "fênix", "cérbero", "medusa", "sereias",
]

CIENCIAS_SOCIAIS = [
    "sociologia", "antropologia", "ciência política", "psicologia social",
    "comunicação", "educação", "trabalho", "família", "desigualdade", "movimentos sociais",
    "teoria crítica", "pós-modernismo", "estudos de gênero", "estudos raciais",
    "identidade", "cultura", "globalização", "transnacionalismo",
    "políticas públicas", "gestão social", "terceiro setor",
    "ONG", "movimento negro", "movimento feminista", "movimento LGBTQ+",
    "indigenismo", "quilombolas", "caiçaras", "ribeirinhos",
]

FILMES = [
    "O Poderoso Chefão", "Cidadão Kane", "Casablanca", "E o Vento Levou", "O Mágico de Oz",
    "Star Wars", "Titanic", "Avatar", "Vingadores: Ultimato", "O Senhor dos Anéis",
    "Matrix", "Clube da Luta", "Pulp Fiction", "A Origem", "Interestelar",
    "O Iluminado", "Laranja Mecânica", "2001: Uma Odisséia no Espaço",
    "Deus e o Diabo na Terra do Sol", "O Bandido da Luz Vermelha", "Macunaíma",
    "Terra em Transe", "Cidade de Deus", "O Auto da Compadecida", "Central do Brasil",
    "Que horas ela volta?", "Aquarius", "O Som ao Redor", "Bacurau",
    "A Vida é Bela", "A Lista de Schindler", "O Paciente Inglês",
    "Os Intocáveis", "A Teoria de Tudo", "O Jogo da Imitação",
    "Pulp Fiction", "Django Livre", "Kill Bill", "Bastardos Inglórios",
    "Era uma Vez em Hollywood", "O Irlandês",
    "O Poderoso Chefão 2", "O Poderoso Chefão 3", "Os Bons Companheiros",
    "Cassino", "Taxi Driver", "Touro Indomável", "O Rei da Comédia",
    "Os Infiltrados", "A Última Tentativa de Cristo", "A Ilha do Medo",
    "O Lobo de Wall Street", "O Aviador", "Gangues de Nova York",
    "Os Fabelmans", "Eduardo e Mônica", "Ainda Estou Aqui",
    "O Palhaço", "Meu Nome é Jhonny", "Os 12 Trabalhos",
    "Lisbela e o Prisioneiro", "O Homem que Copiava", "Saneamento Básico",
    "O Céu de Suely", "Viajo porque Preciso, Volto porque Te Amo",
    "O Abraço da Serpente", "A Febre do Rato", "O Mecanismo",
    "A Hora da Estrela", "Quilombo", "Cabra Marcado para Morrer",
    "ABC da Greve", "Edifício Master", "Brasil S/A",
    "Moscou", "O Invasor", "Carandiru", "O Quatrilho",
    "Memórias do Cárcere", "Filme de Amor", "Pra Frente, Brasil",
    "O Xangô de Baker Street", "Bicho de Sete Cabeças", "O Ano em que Meus Pais Saíram de Férias",
    "Eu Sei que Vou Te Amar", "O Rio de Janeiro de João", "Eles Não Usam Black-tie",
    "Cinema, Aspirinas e Urubus", "Canta Maria", "Faroeste Caboclo",
    "O Profeta", "A Deusa Negra", "Alexandre e Outros Heróis",
    "O Guarani", "Iracema", "Ubirajara", "O Cortiço", "Vidas Secas",
    "Sagarana", "Capitães da Areia", "Gabriela", "Dona Flor e Seus Dois Maridos",
    "Tenda dos Milagres", "Tieta do Agreste", "O Santo e a Selva",
    "O Baile Perfumado", "Amarelo Manga", "O Sonho de Rose",
    "A Grande Família - O Filme", "Os Normais - O Filme",
    "O Querido Velho", "O Outro Lado da Rua", "O Mistério da Estrada",
    "A Paixão de Sérgio", "O Corte", "A Gaiola",
    "Os Herdeiros", "O Dia de São José", "O Último Cine Drive-in",
    "A Cidade Onde Envelheço", "Domingo", "O Filme de 2017",
    "O Príncipe", "A Mãe", "O Homem do Futuro",
    "A Mulher Invisível", "O Fabuloso Fittipaldi", "O Que É Isso, Companheiro?",
    "Quase Memória", "O Beijo no Asfalto", "O Lado Frio da Lua",
    "A Zona", "Rua da Glória", "O Sonho de Antônio",
    "O Sertão e o Mar", "O Guardião do Fogo", "A Colônia",
    "O Lugar de Dona Zilá", "A Casa de Alice", "O Rio de Todos",
    "O Espelho", "A Chave", "O Trajeto",
    "O Voo da Borboleta", "A Sombra do Sol", "O Gosto da Vida",
    "A Melhor Idade", "O Mundo de Mel", "O Pátio das Sombras",
    "O Jogo do Bicho", "A Coragem do Amor", "O Sabor do Rio",
    "A Rota", "O Dia do Caçador", "A Luz de Vênus",
    "O Caminho das Pedras", "A Estrada do Fim", "O Porto de Santos",
    "A Praia do Céu", "O Morro do Alemão", "A Favela do Vidigal",
    "O Parque da Cidade", "A Ponte do Rio", "O Túnel do Tempo",
    "A Lenda do Guaraná", "O Segredo do Tupiniquim", "A Conquista do Oeste",
    "O Velho Oeste", "A Guerra do Fogo", "O Último dos Moicanos",
    "O Coração Valente", "Braveheart", "O Gladiador", "A Queda do Império Romano",
    "O Coliseu", "A Batalha de Aljubarrota", "O Cerco de Leningrado",
    "A Trégua de Natal", "O Dia D", "A Batalha do Bulge",
    "O Pacífico", "A Guerra do Vietnã", "O Apocalipse da Selva",
    "A Missão", "O Missionário", "A Cruzada", "As Cruzadas",
    "O Código da Vinci", "Anjos e Demônios", "O Símbolo Perdido",
    "O Último Templário", "A Maçã de Ouro", "O Jardim de Epicuro",
    "A Biblioteca de Alexandria", "O Mapa do Tesouro", "A Viagem de Ulisses",
    "O Regresso de Odisseu", "A Odisséia no Espaço", "O Retorno de Jedi",
    "O Império Contra-Ataca", "A Ameaça Fantasma", "O Ataque dos Clones",
    "A Vingança dos Sith", "O Despertar da Força", "Os Últimos Jedi",
    "A Ascensão Skywalker", "Rogue One", "Han Solo",
    "O Mandaloriano", "O Livro de Boba Fett", "Ahsoka",
    "O Andor", "A Rebelião", "O Império Galáctico",
    "A Aliança Rebelde", "A Nova República", "A Ordem Jedi",
    "O Lado Sombrio", "A Força", "O Sabre de Luz",
    "A Nave Millennium", "O Falcão Milenar", "O X-Wing",
    "O Star Destroyer", "A Base Starkiller", "O Planeta Tatooine",
    "O Mundo de Hoth", "A Cidade de Bespin", "A Lua de Endor",
    "O Bosque de Takodana", "O Templo de Exegol", "A Galáxia Muito, Muito Distante",
    "O Universo Marvel", "Vingadores", "Guerra Infinita",
    "Ultimato", "Capitão América", "O Primeiro Vingador",
    "O Soldado Invernal", "A Guerra Civil", "Thor", "O Mundo Sombrio",
    "Ragnarok", "Amor e Trovão", "Homem de Ferro", "Homem de Ferro 2",
    "Homem de Ferro 3", "Pantera Negra", "Wakanda para Sempre",
    "Doutor Estranho", "No Multiverso da Loucura", "Guardiões da Galáxia",
    "Vol. 2", "Vol. 3", "Homem-Aranha", "De Volta ao Lar",
    "Longe de Casa", "Sem Volta pra Casa", "Mulher-Maravilha",
    "1984", "Aquaman", "O Rei Perdido", "Shazam!", "Fúria dos Deuses",
    "Liga da Justiça", "O Filme", "O Esquadrão Suicida",
    "O Coringa", "O Batman", "O Cavaleiro das Trevas",
    "O Cavaleiro das Trevas Ressurge", "Batman Begins",
    "Batman vs Superman", "A Origem da Justiça", "O Flash",
    "O Lanterna Verde", "O Besouro Azul", "O Super-Homem",
    "O Homem de Aço", "O Planeta Krypton", "A Fortaleza da Solidão",
    "A Metrópolis", "Gotham City", "A Gotham",
    "O Asilo Arkham", "O Corpo de GCPD", "O Batmóvel",
    "A Batcaverna", "O Morcego", "O Sinal do Batman",
    "O Coringa e Arlequina", "A Sociedade do Crime", "O Império do Crime",
    "O Rei do Crime", "A Máfia", "A Família Corleone",
    "O Poderoso Chefão", "O Chefão 2", "O Chefão 3",
    "Os Bons Companheiros", "Cassino", "O Irlandês",
    "O Ouro de Macaé", "A Cidade de Ouro", "O Diamante",
    "A Pérola", "O Rubi", "A Safira", "A Esmeralda",
    "O Cristal", "A Pedra Filosofal", "O Elixir da Vida",
    "O Segredo da Imortalidade", "A Fonte da Juventude",
    "O Templo Perdido", "A Cidade Proibida", "O Império do Fim",
    "O Último Imperador", "O Pequeno Imperador", "O Império do Sol",
    "O Sol Nascente", "O Sol Poente", "O Crepúsculo dos Deuses",
    "O Ocaso de uma Era", "O Apocalipse Zumbi", "A Guerra Mundial Z",
    "O Exército das Trevas", "O Horror de Amityville", "O Massacre da Serra Elétrica",
    "O Exorcista", "O Iluminado", "O Nevoeiro", "O Chamado",
    "O Grito", "A Maldição", "A Bruxa de Blair", "O Atividade Paranormal",
    "O Invocação do Mal", "O Anabelle", "A Freira", "O Chaves de Ouro",
    "O Horror de Salem", "O Cemitério Maldito", "O Pet Sematary",
    "O Cuco", "O Hereditário", "A Midsommar", "O Bugiganga",
    "O Artefato", "O Relicário", "O Amuleto", "O Fetiche",
    "O Mistério da Caixa", "O Enigma do Cofre", "O Segredo do Porão",
    "O Quarto 1408", "O Número 23", "O 1408", "O 11.11",
    "O 13º Andar", "O 1408", "O 23", "O 42",
    "O 2001", "O 2010", "O 2021", "O 2030",
    "O Ano 2000", "O Milênio", "O Século XXI", "O Futuro",
    "O Passado", "O Presente", "O Amanhã", "O Ontem",
    "O Ontem e Hoje", "O Hoje e Amanhã", "O Eternidade",
    "O Infinito", "O Além", "O Céu", "O Inferno", "O Purgatório",
    "O Paraíso", "O Éden", "O Jardim", "O Bosque",
    "O Lago", "O Mar", "O Oceano", "O Ártico", "A Antártida",
    "O Monte Everest", "A Cordilheira dos Andes", "O Himalaia",
    "O Alpes", "Os Pireneus", "Os Urais", "Os Apalaches",
    "As Montanhas Rochosas", "A Serra Nevada", "A Grande Barreira",
    "A Muralha da China", "A Grande Muralha", "O Canal da Mancha",
    "O Estreito de Gibraltar", "O Mar Vermelho", "O Mar Morto",
    "O Mar Cáspio", "O Mar Negro", "O Mar Báltico",
    "O Mar Adriático", "O Mar Egeu", "O Mar Mediterrâneo",
    "O Atlântico", "O Pacífico", "O Índico", "O Glacial",
    "O Ártico", "O Antártico", "O Polo Norte", "O Polo Sul",
    "A Linha do Equador", "O Trópico de Câncer", "O Trópico de Capricórnio",
    "O Círculo Polar", "O Sol da Meia-Noite", "A Aurora Boreal",
    "A Aurora Austral", "O Eclipse", "O Cometa", "O Meteoro",
    "O Asteroide", "O Planeta", "A Lua", "O Sol", "A Estrela",
    "A Galáxia", "A Nebulosa", "O Buraco Negro", "A Matéria Escura",
    "A Energia Escura", "A Física Quântica", "A Teoria das Cordas",
    "O Big Bang", "O Universo", "O Multiverso", "A Dimensão Paralela",
    "O Portal", "O Wormhole", "O Buraco de Minhoca", "A Dobra Espacial",
    "A Viagem no Tempo", "A Máquina do Tempo", "O Efeito Borboleta",
    "O Predestinado", "A Looper", "O Contato", "O Encontro de 1970",
    "O Encontro de 1980", "O Encontro de 1990", "O Encontro de 2000",
    "O Encontro de 2010", "O Encontro de 2020", "O Encontro de 2030",
    "A Reunião", "O Reencontro", "A Despedida", "O Adeus",
    "A Partida", "O Retorno", "A Volta", "O Recomeço",
    "O Recomeço", "A Segunda Chance", "A Última Chance",
    "A Primeira Vez", "A Última Vez", "O Último Beijo",
    "O Primeiro Beijo", "O Amor", "A Paixão", "O Desejo",
    "A Obsessão", "O Ciúme", "A Traição", "O Perdão",
    "A Reconciliação", "A Amizade", "A Lealdade", "A Solidariedade",
    "A Compaixão", "A Empatia", "A Resiliência", "A Coragem",
    "A Honra", "A Glória", "O Sucesso", "O Fracasso",
    "A Superação", "A Vitória", "A Derrota", "A Luta",
    "A Batalha", "A Guerra", "A Paz", "A Trégua",
    "O Armistício", "A Rendição", "A Fuga", "O Resgate",
    "O Salvamento", "A Salvação", "O Refúgio", "O Abrigo",
    "A Casa", "O Lar", "O Ninho", "O Berço", "O Templo",
    "A Igreja", "A Mesquita", "A Sinagoga", "O Mosteiro",
    "O Convento", "O Santuário", "O Altar", "O Sacerdote",
    "O Monge", "A Freira", "O Santo", "O Mártir",
    "O Profeta", "O Messias", "O Salvador", "O Redentor",
    "O Iluminado", "O Esclarecido", "O Conhecimento", "A Sabedoria",
    "A Ignorância", "A Estupidez", "A Loucura", "A Razão",
    "A Emoção", "A Sensibilidade", "A Intuição", "O Instinto",
    "A Sobrevivência", "A Adaptação", "A Evolução", "A Revolução",
    "A Transformação", "A Mutação", "A Metamorfose", "A Transfiguração",
    "O Espelho", "A Sombra", "A Luz", "A Escuridão",
    "O Caos", "A Ordem", "O Destino", "A Sorte", "O Acaso",
    "O Acidente", "A Coincidência", "A Sincronia", "A Oportunidade",
    "A Prova", "O Teste", "O Desafio", "O Obstáculo",
    "A Armadilha", "O Perigo", "O Risco", "A Aventura",
    "A Descoberta", "A Invenção", "A Criação", "A Imaginação",
    "A Fantasia", "O Sonho", "A Ilusão", "A Realidade",
    "A Verdade", "A Mentira", "A Farsa", "O Engano",
    "A Traição", "A Lealdade", "A Honestidade", "A Desonestidade",
    "A Transparência", "A Opacidade", "A Clareza", "A Confusão",
    "O Mistério", "O Enigma", "O Segredo", "O Código",
    "A Chave", "A Porta", "A Janela", "O Túnel",
    "O Corredor", "O Elevador", "A Escada", "A Rampa",
    "O Beco", "A Rua", "A Avenida", "A Alameda",
    "A Praça", "O Parque", "O Jardim", "A Floresta",
    "A Selva", "A Savana", "O Deserto", "A Tundra",
    "A Taiga", "A Estepe", "A Campina", "O Campo",
    "O Pântano", "O Mangue", "O Recife", "A Ilha",
    "O Arquipélago", "O Continente", "A Península", "O Istmo",
    "O Golfo", "A Baía", "O Cabo", "O Farol",
    "O Porto", "O Cais", "O Píer", "O Navio",
    "O Barco", "A Canoa", "O Caiaque", "O Iate",
    "O Submarino", "O Hidroavião", "O Avião", "O Helicóptero",
    "O Foguete", "O Ônibus Espacial", "A Estação Espacial",
    "O Satélite", "O Telescópio", "O Microscópio", "O Binóculo",
    "A Lupa", "A Lanterna", "A Bússola", "O Mapa",
    "O Globo", "O Atlas", "O Álbum", "O Diário",
    "O Caderno", "O Livro", "O Manuscrito", "O Pergaminho",
    "O Papiro", "A Tabuleta", "A Pedra", "O Monumento",
    "A Estela", "O Obelisco", "A Pirâmide", "O Túmulo",
    "A Catacumba", "A Masmorra", "O Calabouço", "A Torre",
    "O Castelo", "O Palácio", "A Mansão", "A Fazenda",
    "O Sítio", "A Chácara", "A Horta", "O Pomar",
    "O Vinhedo", "A Adega", "O Cervejaria", "A Destilaria",
    "O Moinho", "O Forno", "A Padaria", "A Confeitaria",
    "A Churrascaria", "A Pizzaria", "O Restaurante", "O Café",
    "O Bar", "A Lanchonete", "A Sorveteria", "A Doceria",
    "A Loja de Conveniência", "O Supermercado", "A Feira",
    "O Mercado", "A Venda", "A Quiosque", "A Barraca",
    "O Camelô", "O Artesão", "O Ateliê", "A Oficina",
    "O Galpão", "O Armazém", "O Depósito", "O Silos",
    "O Celeiro", "O Estábulo", "O Curral", "O Chiqueiro",
    "O Galinheiro", "O Apiário", "O Viveiro", "O Aquário",
    "O Zoológico", "O Jardim Botânico", "O Herbário", "O Museu",
    "A Galeria", "O Teatro", "O Cinema", "A Casa de Espetáculos",
    "O Circo", "A Arena", "O Estádio", "O Ginásio",
    "A Pista de Atletismo", "A Piscina", "A Quadra",
    "O Campo de Futebol", "A Cancha de Tênis", "A Mesa de Sinuca",
    "O Tabuleiro", "O Baralho", "O Dado", "A Moeda",
    "A Ficha", "A Máquina de Cassino", "O Roleta", "O Blackjack",
    "A Pôquer", "O Truco", "A Canastra", "A Mega-Sena",
    "O Bilhete", "O Sorteio", "O Prêmio", "O Jackpot",
    "A Loteria", "O Bingo", "O Quiz", "O Show",
    "O Espetáculo", "O Concerto", "A Ópera", "O Balé",
    "A Dança", "A Coreografia", "A Música", "A Canção",
    "A Sinfonia", "A Sonata", "O Concerto", "A Serenata",
    "O Hino", "A Marcha", "A Valsa", "O Tango",
    "A Samba", "A Bossa Nova", "O Forró", "O Frevo",
    "O Maracatu", "O Afoxé", "A Capoeira", "A Zamba",
    "O Candombe", "A Cumbia", "O Reggae", "O Ska",
    "A Dub", "O Rock", "O Pop", "O Rap", "O Hip-Hop",
    "A Eletrônica", "O Techno", "A House", "O Trance",
    "A Dubstep", "O Funk", "O Soul", "O R&B",
    "O Jazz", "O Blues", "O Country", "O Folk",
    "A Música Clássica", "A Música Barroca", "A Música Renascentista",
    "A Música Medieval", "A Música Moderna", "A Música Contemporânea",
    "O Festival", "A Turnê", "O Show ao Vivo", "O DVD",
    "A Gravação", "O Estúdio", "A Mixagem", "A Masterização",
    "A Produção", "A Distribuição", "A Mídia", "A Publicidade",
    "O Merchandising", "O Licenciamento", "O Royalties",
    "O Direito Autoral", "A Propriedade Intelectual", "A Patente",
    "A Marca", "O Logotipo", "O Design", "A Moda",
    "O Estilo", "A Tendência", "O Clássico", "O Moderno",
    "O Pós-moderno", "O Contemporâneo", "O Vanguarda",
    "O Experimental", "O Alternativo", "O Underground",
    "O Mainstream", "O Blockbuster", "O Filme Independente",
    "O Filme de Arte", "O Filme de Culto", "O Filme Clássico",
    "O Filme Mudou", "O Filme Colorido", "O Filme Preto e Branco",
    "O Filme 3D", "O Filme IMAX", "O Filme Digital",
    "O Filme 4K", "O Filme 8K", "O Filme HDR",
    "O Filme Dolby Atmos", "O Filme com Som Surround",
    "O Filme de Ação", "O Filme de Aventura", "O Filme de Comédia",
    "O Filme de Drama", "O Filme de Romance", "O Filme de Terror",
    "O Filme de Suspense", "O Filme de Mistério", "O Filme de Ficção Científica",
    "O Filme de Fantasia", "O Filme de Faroeste", "O Filme de Guerra",
    "O Filme de Política", "O Filme de Esporte", "O Filme de Música",
    "O Filme de Animação", "O Filme de Documentário", "O Filme Biográfico",
    "O Filme Histórico", "O Filme de Época", "O Filme de Natal",
    "O Filme de Dia das Mães", "O Filme de Dia dos Pais",
    "O Filme de Ano Novo", "O Filme de Carnaval", "O Filme de São João",
    "O Filme de Férias", "O Filme de Viagem", "O Filme de Moto",
    "O Filme de Carro", "O Filme de Avião", "O Filme de Navio",
    "O Filme de Trem", "O Filme de Ônibus", "O Filme de Bicicleta",
    "O Filme de Skate", "O Filme de Surfe", "O Filme de Escalada",
    "O Filme de Mergulho", "O Filme de Paraquedismo", "O Filme de Balão",
    "O Filme de Dirigível", "O Filme de Foguete", "O Filme de Satélite",
    "O Filme de Robô", "O Filme de Monstro", "O Filme de Dinossauro",
    "O Filme de Alienígena", "O Filme de Zumbi", "O Filme de Vampiro",
    "O Filme de Lobisomem", "O Filme de Fantasma", "O Filme de Múmia",
    "O Filme de Pirata", "O Filme de Samurai", "O Filme de Ninja",
    "O Filme de Viquingue", "O Filme de Celta", "O Filme de Romano",
    "O Filme de Grego", "O Filme de Egípcio", "O Filme de Mesopotâmico",
    "O Filme de Asteca", "O Filme de Inca", "O Filme de Maia",
    "O Filme de Tupi-Guarani", "O Filme de Africano", "O Filme de Árabe",
    "O Filme de Chinês", "O Filme de Indiano", "O Filme de Japonês",
    "O Filme de Coreano", "O Filme de Russo", "O Filme de Alemão",
    "O Filme de Francês", "O Filme de Inglês", "O Filme de Italiano",
    "O Filme de Espanhol", "O Filme de Português", "O Filme de Latino",
    "O Filme de Brasileiro", "O Filme de Argentino", "O Filme de Mexicano",
    "O Filme de Chileno", "O Filme de Peruano", "O Filme de Cubano",
    "O Filme de Porto-riquenho", "O Filme de Ilha", "O Filme de Costa",
    "O Filme de Praia", "O Filme de Montanha", "O Filme de Planície",
    "O Filme de Floresta", "O Filme de Savana", "O Filme de Deserto",
    "O Filme de Tundra", "O Filme de Taiga", "O Filme de Estepes",
    "O Filme de Pântano", "O Filme de Mangue", "O Filme de Recife",
    "O Filme de Ilha Vulcânica", "O Filme de Atol", "O Filme de Delta",
    "O Filme de Foz", "O Filme de Nascente", "O Filme de Cachoeira",
    "O Filme de Corredeira", "O Filme de Riacho", "O Filme de Lago",
    "O Filme de Lagoa", "O Filme de Oceano", "O Filme de Mar",
    "O Filme de Baía", "O Filme de Golfo", "O Filme de Canal",
    "O Filme de Estreito", "O Filme de Enseada", "O Filme de Angra",
    "O Filme de Cabo", "O Filme de Promontório", "O Filme de Farol",
    "O Filme de Mosteiro", "O Filme de Convento", "O Filme de Abadia",
    "O Filme de Catedral", "O Filme de Basílica", "O Filme de Santuário",
    "O Filme de Templo", "O Filme de Pagode", "O Filme de Sinagoga",
    "O Filme de Mesquita", "O Filme de Igreja", "O Filme de Capela",
    "O Filme de Altar", "O Filme de Sacrário", "O Filme de Púlpito"
]

SERIES = [
    "Game of Thrones", "Breaking Bad", "The Sopranos", "Friends", "The Office",
    "Stranger Things", "The Crown", "The Mandalorian", "WandaVision",
    "Dark", "The Witcher", "Supernatural", "The Walking Dead",
    "The Last of Us", "House of the Dragon", "Better Call Saul",
    "The Boys", "The Umbrella Academy", "Sex Education",
    "Brooklyn Nine-Nine", "Parks and Recreation", "The Good Place",
    "Ozark", "Mindhunter", "True Detective", "Fargo",
    "This Is Us", "This is England", "Skins",
    "Narcos", "Narcos: México", "La Casa de Papel",
    "O Mecanismo", "A Divisão", "Sob Pressão", "3%",
    "The Handmaid's Tale", "Westworld", "The Expanse", "For All Mankind",
    "Foundation", "Severance", "The Bear", "Yellowstone",
    "The White Lotus", "Succession", "Euphoria", "The Last of Us",
    "House of the Dragon", "The Sandman", "One Piece", "Monarch",
    "The Lord of the Rings: The Rings of Power", "The Peripheral",
    "Mare of Easttown", "The Dropout", "WeCrashed", "Inventing Anna",
    "Dahmer", "Monster: The Jeffrey Dahmer Story", "The Watcher",
    "Wednesday", "The Night Of", "The Undoing", "Big Little Lies",
    "Sharp Objects", "Little Fires Everywhere", "Nine Perfect Strangers",
    "The Hills", "The City", "The Real World", "Jersey Shore",
    "Keeping Up with the Kardashians", "The Osbournes", "The Simple Life",
    "The Real Housewives", "Vanderpump Rules", "Summer House",
    "Southern Charm", "Below Deck", "Selling Sunset",
    "Tiger King", "Making a Murderer", "The Staircase",
    "Wild Wild Country", "The Keepers", "Evil Genius",
    "Don't F**k with Cats", "The Jinx", "The Thin Blue Line",
    "OJ: Made in America", "The Last Dance", "Formula 1: Drive to Survive",
    "Cheer", "The Circle", "The Great British Bake Off", "RuPaul's Drag Race",
    "The Masked Singer", "The Voice", "America's Got Talent", "Britain's Got Talent",
    "The X Factor", "American Idol", "Dancing with the Stars",
    "The Bachelor", "The Bachelorette", "Love Island", "Too Hot to Handle",
    "Squid Game", "Money Heist", "The Crown", "The Queen's Gambit",
    "The Mandalorian", "The Book of Boba Fett", "Obi-Wan Kenobi",
    "The Bad Batch", "The Acolyte", "Skeleton Crew",
    "Star Trek: Discovery", "Star Trek: Picard", "Star Trek: Strange New Worlds",
    "Star Trek: Lower Decks", "Star Trek: Prodigy",
    "Doctor Who", "Torchwood", "The Sarah Jane Adventures",
    "Class", "The Terror", "The Haunting of Hill House", "The Haunting of Bly Manor",
    "Midnight Mass", "The Fall of the House of Usher",
    "American Horror Story", "American Crime Story", "American Horror Stories",
    "Scream Queens", "Glee", "The Glee Project",
    "Buffy the Vampire Slayer", "Angel", "Firefly", "Serenity",
    "The X-Files", "Millennium", "The Lone Gunmen",
    "Fringe", "Lost", "Alias", "24", "Prison Break",
    "The 100", "The 4400", "Heroes", "The Tomorrow People",
    "The Flash", "Arrow", "Supergirl", "Legends of Tomorrow",
    "Gotham", "Smallville", "Superman & Lois", "Batwoman",
    "Penny Dreadful", "The Originals", "The Vampire Diaries",
    "Legacies", "Shadowhunters", "Charmed", "The Chilling Adventures of Sabrina",
    "Riverdale", "Outer Banks", "Cobra Kai", "The Karate Kid",
    "The Big Bang Theory", "Young Sheldon", "How I Met Your Mother",
    "Mom", "Two and a Half Men", "The King of Queens", "Everybody Loves Raymond",
    "Will & Grace", "The New Adventures of Old Christine",
    "Seinfeld", "Curb Your Enthusiasm", "Veep", "Silicon Valley",
    "30 Rock", "Unbreakable Kimmy Schmidt", "The Mindy Project",
    "New Girl", "Don't Trust the B---- in Apartment 23",
    "Happy Endings", "Community", "Arrested Development",
    "It's Always Sunny in Philadelphia", "The It Crowd",
    "Black Books", "Father Ted", "The Inbetweeners", "Gavin & Stacey",
    "The Young Ones", "Bottom", "Red Dwarf", "The Mighty Boosh",
    "The League of Gentlemen", "Psychoville", "Inside No. 9",
    "Black Mirror", "Electric Dreams", "Love, Death & Robots",
    "The Outer Limits", "The Twilight Zone", "Tales from the Crypt",
    "Tales from the Darkside", "Monsters", "Creepshow",
    "The Walking Dead", "Fear the Walking Dead", "The Walking Dead: World Beyond",
    "Tales of the Walking Dead", "The Dead Zone", "Z Nation",
    "Van Helsing", "The Strain", "The Purge", "The Rain",
    "Battlestar Galactica", "Stargate SG-1", "Stargate Atlantis", "Stargate Universe",
    "The Orville", "Galaxy Quest", "Red Dwarf", "Hitchhiker's Guide to the Galaxy",
    "Futurama", "The Simpsons", "Family Guy", "American Dad!", "Bob's Burgers",
    "King of the Hill", "South Park", "Rick and Morty", "Solar Opposites",
    "Tuca & Bertie", "Daria", "Beavis and Butt-Head", "The Ren & Stimpy Show",
    "SpongeBob SquarePants", "The Fairly OddParents", "The Adventures of Jimmy Neutron",
    "Avatar: The Last Airbender", "The Legend of Korra",
    "Steven Universe", "Adventure Time", "Regular Show",
    "The Amazing World of Gumball", "We Bare Bears", "Clarence",
    "The Powerpuff Girls", "Dexter's Laboratory", "The Grim Adventures of Billy & Mandy",
    "Ed, Edd n Eddy", "The Kids Next Door", "Samurai Jack",
    "Star Wars: The Clone Wars", "Star Wars Rebels", "Star Wars Resistance",
    "Star Wars: The Bad Batch", "Star Wars: Visions",
    "The Mandalorian", "The Book of Boba Fett", "Obi-Wan Kenobi",
    "Andor", "Ahsoka", "Skeleton Crew", "The Acolyte",
    "Game of Thrones", "House of the Dragon", "The Lord of the Rings: The Rings of Power",
    "The Witcher", "The Witcher: Blood Origin", "The Witcher: Nightmare of the Wolf",
    "The Wheel of Time", "Shadow and Bone", "The Last Kingdom",
    "Vikings", "Vikings: Valhalla", "The Barbarians", "The Roman Empire",
    "The Spanish Princess", "The White Queen", "The White Princess",
    "The Tudors", "The Borgias", "Medici: Masters of Florence",
    "Da Vinci's Demons", "The Musketeers", "Merlin", "Camelot",
    "The King's Affection", "The Empress", "The Great",
    "Catherine the Great", "The Romanoffs", "The Golden Age",
    "The Gilded Age", "Downton Abbey", "The Crown", "The Queen",
    "The Windsors", "The Royal Family", "The Palace", "Versailles",
    "The Boleyns", "The Spanish Princess", "The White Queen",
    "The White Princess", "The Red Queen", "The Lady of the Camellias",
    "The Cardinal", "The Devil's Hour", "The Midnight Club",
    "The Society", "The Wilds", "Yellowjackets", "Cruel Summer",
    "The Summer I Turned Pretty", "The Buccaneers", "The Gilded Age",
    "Bridgerton", "Queen Charlotte", "The Crown", "Victoria",
    "The Great", "The Favorite", "The Other Boleyn Girl",
    "The Duchess", "The Dowager", "The Heir", "The Pretender",
    "The Crown of the Wolf", "The Lion in Winter", "The Plantagenets",
    "The House of York", "The House of Lancaster", "The Wars of the Roses",
    "The Black Adder", "Blackadder", "The Thin Blue Line", "The Young Ones",
    "The Inbetweeners", "The IT Crowd", "The Mighty Boosh",
    "The League of Gentlemen", "Psychoville", "Inside No. 9",
    "This Is England", "The Virtues", "The Tunnel", "The Missing",
    "The Bridge", "The Killing", "The Fall", "The Bodyguard",
    "Line of Duty", "The Crown", "The Queen's Gambit", "The Handmaid's Tale",
    "The Leftovers", "The Watchmen", "The Deuce", "The Wire",
    "Treme", "The Corner", "The Night Of", "The Undoing",
    "The Outsider", "The Plot Against America", "The Man in the High Castle",
    "The Handmaid's Tale", "The Testaments", "The Power", "The Changeling",
    "The Devil's Hour", "The Midnight Club", "The Haunting of Hill House",
    "The Haunting of Bly Manor", "Midnight Mass", "The Fall of the House of Usher",
    "The Cabinet of Curiosities", "The Chilling Adventures of Sabrina",
    "The Mysterious Benedict Society", "The Umbrella Academy",
    "The Boys", "The Boys: Diabolical", "Gen V", "The Tick",
    "The Venture Bros.", "Harvey Birdman", "The Simpsons",
    "Family Guy", "American Dad!", "Bob's Burgers", "King of the Hill",
    "South Park", "Rick and Morty", "Solar Opposites",
    "Tuca & Bertie", "Daria", "Beavis and Butt-Head", "The Ren & Stimpy Show",
    "SpongeBob SquarePants", "The Fairly OddParents", "The Adventures of Jimmy Neutron",
    "Avatar: The Last Airbender", "The Legend of Korra",
    "Steven Universe", "Adventure Time", "Regular Show",
    "The Amazing World of Gumball", "We Bare Bears", "Clarence",
    "The Powerpuff Girls", "Dexter's Laboratory", "The Grim Adventures of Billy & Mandy",
    "Ed, Edd n Eddy", "The Kids Next Door", "Samurai Jack",
    "Star Wars: The Clone Wars", "Star Wars Rebels", "Star Wars Resistance",
    "Star Wars: The Bad Batch", "Star Wars: Visions",
    "The Mandalorian", "The Book of Boba Fett", "Obi-Wan Kenobi",
    "Andor", "Ahsoka", "Skeleton Crew", "The Acolyte",
    "Game of Thrones", "House of the Dragon", "The Lord of the Rings: The Rings of Power",
    "The Witcher", "The Witcher: Blood Origin", "The Witcher: Nightmare of the Wolf",
    "The Wheel of Time", "Shadow and Bone", "The Last Kingdom",
    "Vikings", "Vikings: Valhalla", "The Barbarians", "The Roman Empire",
    "The Spanish Princess", "The White Queen", "The White Princess",
    "The Tudors", "The Borgias", "Medici: Masters of Florence",
    "Da Vinci's Demons", "The Musketeers", "Merlin", "Camelot",
    "The King's Affection", "The Empress", "The Great",
    "Catherine the Great", "The Romanoffs", "The Golden Age",
    "The Gilded Age", "Downton Abbey", "The Crown", "The Queen",
    "The Windsors", "The Royal Family", "The Palace", "Versailles",
    "The Boleyns", "The Spanish Princess", "The White Queen",
    "The White Princess", "The Red Queen", "The Lady of the Camellias",
    "The Cardinal", "The Devil's Hour", "The Midnight Club",
    "The Society", "The Wilds", "Yellowjackets", "Cruel Summer",
    "The Summer I Turned Pretty", "The Buccaneers", "The Gilded Age",
    "Bridgerton", "Queen Charlotte", "The Crown", "Victoria",
    "The Great", "The Favorite", "The Other Boleyn Girl",
    "The Duchess", "The Dowager", "The Heir", "The Pretender",
    "The Crown of the Wolf", "The Lion in Winter", "The Plantagenets",
    "The House of York", "The House of Lancaster", "The Wars of the Roses",
    "The Black Adder", "Blackadder", "The Thin Blue Line", "The Young Ones",
    "The Inbetweeners", "The IT Crowd", "The Mighty Boosh",
    "The League of Gentlemen", "Psychoville", "Inside No. 9",
    "This Is England", "The Virtues", "The Tunnel", "The Missing",
    "The Bridge", "The Killing", "The Fall", "The Bodyguard",
    "Line of Duty", "The Crown", "The Queen's Gambit", "The Handmaid's Tale",
    "The Leftovers", "The Watchmen", "The Deuce", "The Wire",
    "Treme", "The Corner", "The Night Of", "The Undoing",
    "The Outsider", "The Plot Against America", "The Man in the High Castle",
    "The Handmaid's Tale", "The Testaments", "The Power", "The Changeling",
    "The Devil's Hour", "The Midnight Club", "The Haunting of Hill House",
    "The Haunting of Bly Manor", "Midnight Mass", "The Fall of the House of Usher",
    "The Cabinet of Curiosities", "The Chilling Adventures of Sabrina",
    "The Mysterious Benedict Society", "The Umbrella Academy",
    "The Boys", "The Boys: Diabolical", "Gen V", "The Tick",
    "The Venture Bros.", "Harvey Birdman", "The Simpsons",
    "Family Guy", "American Dad!", "Bob's Burgers", "King of the Hill",
    "South Park", "Rick and Morty", "Solar Opposites",
    "Tuca & Bertie", "Daria", "Beavis and Butt-Head", "The Ren & Stimpy Show",
    "SpongeBob SquarePants", "The Fairly OddParents", "The Adventures of Jimmy Neutron",
    "Avatar: The Last Airbender", "The Legend of Korra",
    "Steven Universe", "Adventure Time", "Regular Show",
    "The Amazing World of Gumball", "We Bare Bears", "Clarence",
    "The Powerpuff Girls", "Dexter's Laboratory", "The Grim Adventures of Billy & Mandy",
    "Ed, Edd n Eddy", "The Kids Next Door", "Samurai Jack",
    "Star Wars: The Clone Wars", "Star Wars Rebels", "Star Wars Resistance",
    "Star Wars: The Bad Batch", "Star Wars: Visions",
    "The Mandalorian", "The Book of Boba Fett", "Obi-Wan Kenobi",
    "Andor", "Ahsoka", "Skeleton Crew", "The Acolyte",
    "Game of Thrones", "House of the Dragon", "The Lord of the Rings: The Rings of Power",
    "The Witcher", "The Witcher: Blood Origin", "The Witcher: Nightmare of the Wolf",
    "The Wheel of Time", "Shadow and Bone", "The Last Kingdom",
    "Vikings", "Vikings: Valhalla", "The Barbarians", "The Roman Empire",
    "The Spanish Princess", "The White Queen", "The White Princess",
    "The Tudors", "The Borgias", "Medici: Masters of Florence",
    "Da Vinci's Demons", "The Musketeers", "Merlin", "Camelot",
    "The King's Affection", "The Empress", "The Great",
    "Catherine the Great", "The Romanoffs", "The Golden Age",
    "The Gilded Age", "Downton Abbey", "The Crown", "The Queen",
    "The Windsors", "The Royal Family", "The Palace", "Versailles",
    "The Boleyns", "The Spanish Princess", "The White Queen",
    "The White Princess", "The Red Queen", "The Lady of the Camellias",
    "The Cardinal", "The Devil's Hour", "The Midnight Club",
    "The Society", "The Wilds", "Yellowjackets", "Cruel Summer",
    "The Summer I Turned Pretty", "The Buccaneers", "The Gilded Age",
    "Bridgerton", "Queen Charlotte", "The Crown", "Victoria",
    "The Great", "The Favorite", "The Other Boleyn Girl",
    "The Duchess", "The Dowager", "The Heir", "The Pretender",
    "The Crown of the Wolf", "The Lion in Winter", "The Plantagenets",
    "The House of York", "The House of Lancaster", "The Wars of the Roses"
]

PERSONAGENS_FICTICIOS = [
    "Sherlock Holmes", "Harry Potter", "Luke Skywalker", "Darth Vader",
    "Gandalf", "Frodo", "Hermione Granger", "Don Corleone",
    "Macunaíma", "Capitu", "Dom Quixote", "Hamlet",
    "Bentinho", "Brás Cubas", "Riobaldo", "Diadorim", "Gabriela",
    "Pedro Bala", "Professor", "Quincas Berro d'Água",
    "Batman", "Superman", "Mulher Maravilha", "Coringa",
    "Homem-Aranha", "Capitão América", "Homem de Ferro",
    "Harry Potter", "Ron Weasley", "Hermione Granger", "Dumbledore",
    "Voldemort", "Hagrid", "Snape", "Gollum",
]

TECNOLOGIAS_EMERGENTES = [
    "metaverso", "NFTs", "Web3", "deFi", "blockchain",
    "inteligência artificial generativa", "GPT-4", "Stable Diffusion",
    "veículos autônomos", "cidades inteligentes", "energia renovável",
    "computação quântica", "quantum computing", "cibernética",
    "robótica colaborativa", "exoesqueletos", "próteses biônicas",
    "impressão 4D", "materiais inteligentes", "nanorrobôs",
    "baterias de estado sólido", "supercapacitores",
    "rede 6G", "internet satelital", "Starlink",
]

EVENTOS_HISTORICOS_BRASIL = [
    "Revolta da Chibata", "Revolução Constitucionalista de 1932", "Guerra do Contestado",
    "Revolta dos Malês", "Independência da Bahia", "Confederação dos Tamoios",
    "Guerra dos Farrapos", "Revolução de 1930", "Governo de Getúlio Vargas",
    "Descoberta do ouro em Minas Gerais", "Construção de Brasília",
    "Batalha de Guararapes", "Invasão holandesa no Nordeste", "Expedição de Cabeza de Vaca",
    "Fundação de São Paulo", "Fundação do Rio de Janeiro", "Fundação de Salvador",
    "Jornadas de Junho de 2013", "Ocupações secundaristas de 2015",
    "Greve geral de 1917", "Greve dos 300 mil de 1979",
    "Novo Código Civil", "Lei de Anistia",
]

MITOS_BRASILEIROS = [
    "Saci-Pererê", "Curupira", "Boitatá", "Iara", "Boto cor-de-rosa",
    "Negrinho do Pastoreio", "Mula sem cabeça", "Lobisomem", "Cuca",
    "Bruxa", "Vitória-régia", "Uirapuru", "Mapinguari", "Cobra-grande",
    "Anhangá", "Jurupari", "Tucuxi", "Boi-una", "Matinta Perera",
    "Papagaio de fogo", "Caipora", "Cabeça de cuia", "Saci triste",
    "Arajú", "Mãe d'água", "Corpo-seco", "Alma penada",
]

CIENTISTAS_BRASILEIROS = [
    "César Lattes", "Oswaldo Cruz", "Carlos Chagas", "Vital Brazil",
    "Adolfo Lutz", "Maurício de Souza", "José Reis", "Aziz Ab'Sáber",
    "Sérgio Mota", "Milton Santos", "Vandick de Oliveira", "Lúcia Mendonça",
    "Maria de Lourdes", "Francisco de Paula", "Alberto Santos Dumont",
    "Joaquim Monteiro Caminhoá", "José Bonifácio", "Júlio César de Melo",
]

PONTOS_TURISTICOS = [
    "Cristo Redentor", "Pão de Açúcar", "Parque Ibirapuera", "Catedral de Brasília",
    "Teatro Amazonas", "Pelourinho", "Praia de Copacabana", "Cataratas do Iguaçu",
    "Lençóis Maranhenses", "Fernando de Noronha", "Serra da Mantiqueira",
    "Chapada Diamantina", "Bonito (MS)", "Paraty", "Ouro Preto",
    "Olinda", "São Luís", "Alcântara", "Praia do Forte", "Porto de Galinhas",
    "Jardim Botânico do Rio de Janeiro", "Museu do Ipiranga", "Mercado Central de Belo Horizonte",
    "Estádio do Maracanã", "Museu de Arte de São Paulo (MASP)", "Inhotim",
    "Serra do Rio do Rastro", "Cânion Itaimbezinho", "Parque Nacional dos Lençóis Maranhenses",
    "Chapada dos Veadeiros", "Serra da Capivara", "Parque Nacional do Pantanal Matogrossense",
    "Ilha do Mel", "Ilha de Santa Catarina", "Balneário Camboriú",
    "Praia de Ipanema", "Praia de Leblon", "Praia do Leme", "Praia de São Conrado",
    "Praia do Pepino", "Praia de Itapuã", "Praia de Boa Viagem", "Praia do Francês",
    "Praia do Gunga", "Praia de Pipa", "Praia de Canoa Quebrada", "Praia de Jericoacoara",
    "Praia de Taíba", "Praia do Cumbuco", "Praia de Ceará", "Praia de Maceió",
    "Praia de Ponta Verde", "Praia de Jequiá", "Praia de Maragogi", "Praia de São Miguel dos Milagres",
    "Dunas de Genipabu", "Dunas de Natal", "Dunas do Jalapão", "Dunas de São Luís",
    "Cachoeira da Fumaça", "Cachoeira do Iguaçu", "Cachoeira do Vale", "Cachoeira do Rio",
    "Museu Nacional do Rio de Janeiro", "Museu de Arte Contemporânea de Niterói", "Museu Imperial de Petrópolis",
    "Palácio do Planalto", "Palácio da Alvorada", "Congresso Nacional", "Supremo Tribunal Federal",
    "Memorial JK", "Memorial dos Povos Indígenas", "Museu do Amanhã", "Aquário do Rio",
    "Parque Nacional do Itatiaia", "Parque Nacional do Caparaó", "Parque Nacional da Serra dos Órgãos",
    "Parque Nacional do Superagui", "Parque Nacional da Tijuca", "Floresta da Tijuca",
    "Corcovado", "Pedra da Gávea", "Pedra Bonita", "Morro Dois Irmãos",
    "Ilha dos Cobras", "Ilha Grande", "Ilhabela", "Ilha de Marajó",
    "Ilha de São Luís", "Ilha de Vitória", "Ilha de Itaparica", "Ilha de Comandatuba",
    "Gruta do Lago Azul", "Gruta da Pedra Formosa", "Gruta do Maquiné", "Gruta de Aroeira",
    "Parque Nacional da Chapada das Mesas", "Parque Nacional de Sete Cidades",
    "Parque Nacional do Araguaia", "Parque Nacional do Jau", "Parque Nacional do Pico da Neblina",
    "Elevador Lacerda", "Bondinho do Pão de Açúcar", "Bondinho de Santa Teresa",
    "Teleférico de Bonito", "Teleférico de Salvador", "Teleférico do Morro do Alemão",
    "Estação das Docas", "Estação da Luz", "Estação Ferroviária de Curitiba",
    "Museu do Futebol", "Museu do Automóvel", "Museu do Índio", "Museu da Língua Portuguesa",
    "Museu da Imigração", "Museu da Abolição", "Museu do Ouro", "Museu da Inconfidência",
    "Museu do Diamante", "Museu da Escravidão", "Museu do Homem Americano", "Museu da Amazônia",
    "Palácio da Guanabara", "Palácio das Laranjeiras", "Palácio Piratini", "Palácio dos Bandeirantes",
    "Palácio da Alvorada", "Palácio do Itamaraty", "Palácio do Planalto", "Palácio da Justiça",
    "Catedral Metropolitana de Brasília", "Catedral de São Paulo", "Catedral de Salvador",
    "Catedral de Belém", "Catedral de Manaus", "Catedral de São Luís",
    "Igreja de São Francisco de Assis", "Igreja de São Pedro dos Clérigos", "Igreja do Carmo",
    "Igreja de Nossa Senhora do Rosário", "Igreja de Santo Antônio", "Igreja de São Bento",
    "Mosteiro de São Bento", "Mosteiro da Luz", "Mosteiro de Santa Clara",
    "Convento de São Francisco", "Convento do Carmo", "Convento de Santo Antônio",
    "Santuário de Nossa Senhora Aparecida", "Santuário de Nossa Senhora de Fátima",
    "Santuário de Nossa Senhora da Conceição", "Santuário do Bom Jesus de Matosinhos",
    "Santuário de São Francisco de Assis", "Santuário de Padre Cícero", "Juazeiro do Norte",
    "Canindé", "Crato", "Barbalha", "Missão Velha",
    "Parque Nacional de Sete Cidades", "Parque Nacional do Vale do Catimbau",
    "Parque Nacional da Furna Feia", "Parque Nacional do Rio São Francisco",
    "Parque Nacional do Pico da Bandeira", "Parque Nacional do Pico do Itambé",
    "Parque Nacional da Serra do Divisor", "Parque Nacional da Serra do Pacaás Novos",
    "Parque Nacional do Pantanal", "Parque Nacional das Emas", "Parque Nacional do Jalapão",
    "Parque Nacional do Araguaia", "Parque Nacional do Jaú", "Parque Nacional da Amazônia",
    "Parque Nacional de Anavilhanas", "Parque Nacional dos Campos Amazônicos",
    "Parque Nacional da Serra da Cutia", "Parque Nacional do Cabo Orange",
    "Parque Nacional do Viruá", "Parque Nacional do Mapinguari",
    "Parque Nacional do Monte Roraima", "Parque Nacional do Pico do Jaraguá",
    "Parque Nacional do Itacolomi", "Parque Nacional do Caparaó", "Parque Nacional do Espinhaço",
    "Parque Nacional das Sempre Vivas", "Parque Nacional dos Campos Gerais",
    "Foz do Iguaçu", "Usina de Itaipu", "Marco das Três Fronteiras",
    "Brasília", "Eixão do Plano Piloto", "Lago Paranoá", "Ponte JK",
    "Rio de Janeiro", "Aterro do Flamengo", "Quinta da Boa Vista", "Zoológico do Rio",
    "São Paulo", "Parque do Ibirapuera", "Avenida Paulista", "Mercado Municipal de São Paulo",
    "Belo Horizonte", "Lagoa da Pampulha", "Conjunto Arquitetônico da Pampulha", "Museu de Artes e Ofícios",
    "Curitiba", "Jardim Botânico de Curitiba", "Ópera de Arame", "Túnel do Tempo",
    "Porto Alegre", "Parque Redenção", "Usina do Gasômetro", "Caminho das Pedras",
    "Salvador", "Elevador Lacerda", "Forte de São Marcelo", "Farol da Barra",
    "Recife", "Marco Zero", "Oficina de Cerâmica", "Instituto Ricardo Brennand",
    "Fortaleza", "Mercado Central", "Praia do Futuro", "Beira-mar",
    "Manaus", "Encontro das Águas", "Praia da Ponta Negra", "Mercado Municipal Adolpho Lisboa",
    "Belém", "Estação das Docas", "Mercado Ver-o-Peso", "Mangal das Garças",
    "Florianópolis", "Lagoa da Conceição", "Igreja Matriz", "Mercado Público",
    "Vitória", "Convento da Penha", "Morro do Moreno", "Ilha do Boi",
    "Natal", "Forte dos Reis Magos", "Via Costeira", "Ponta Negra",
    "João Pessoa", "Praia de Tambaba", "Estação Cabo Branco", "Centro Cultural",
    "Maceió", "Ponta Verde", "Jatiúca", "Cruz das Almas",
    "Aracaju", "Praia de Atalaia", "Orla de Atalaia", "Museu da Gente Sergipana",
    "Teresina", "Rio Poty", "Parque da Cidade", "Sambódromo de Teresina",
    "Cuiabá", "Museu do Morro", "Parque Mãe Bonifácia", "Igreja de São Benedito",
    "Campo Grande", "Parque das Nações", "Memorial da Cultura Indígena", "Lagoa do Coqueiro",
    "Goiânia", "Parque Flamboyant", "Museu de Arte", "Igreja do Rosário",
    "Boa Vista", "Orla Taumanã", "Museu Joaquim Nabuco", "Parque do Rio Branco",
    "Palmas", "Parque do Povo", "Praia do Meio", "Espaço Cultural de Palmas",
    "Rio Branco", "Palácio do Governo", "Mercado Velho", "Parque Ambiental Chico Mendes",
    "Macapá", "Forte de São José", "Marco do Equador", "Zerão",
    "Porto Velho", "Estrada de Ferro Madeira-Mamoré", "Museu da Memória Rondoniense",
    "Santarém", "Alter do Chão", "Lago do Maicá", "Ilha do Marajó"
]

FESTAS_POPULARES = [
    "Carnaval", "Festa Junina", "Revelion", "Folia de Reis", "Bumba meu boi",
    "Círio de Nazaré", "Procissão do Fogaréu", "Festa do Divino Espírito Santo",
    "Congada", "Maracatu", "Frevo", "Forró", "Samba de roda",
    "Chegança", "Reisado", "Pastoril", "Cavalo Marinho",
]

ESPORTES_MODALIDADES = [
    "futebol", "basquetebol", "voleibol", "handebol", "futsal",
    "natação", "atletismo", "ginástica", "judô", "karatê",
    "taekwondo", "boxe", "luta livre", "esgrima", "hipismo",
    "tiro esportivo", "arco e flecha", "triatlo", "pentatlo", "maratona",
    "ciclismo", "surfe", "skate", "snowboard", "esqui",
    "patinação artística", "hóquei no gelo", "curling", "bobsleigh", "luge",
    "remo", "canoagem", "vela", "içar", "mergulho",
    "polo aquático", "saltos ornamentais", "maratona aquática",
    "esportes de combate", "esportes de raquete", "tênis", "squash", "badminton",
    "golfe", "beisebol", "softbol", "críquete", "rugby",
    "futebol americano", "futebol australiano", "lacrosse", "polo",
    "automobilismo", "motociclismo", "stock car", "fórmula 1", "rally",
    "esportes eletrônicos", "e-sports", "jogos de luta", "FPS", "MOBA",
]

JOGOS = [
    "Xadrez", "Damas", "Dominó", "Baralho", "Poker",
    "RPG", "Dungeons & Dragons", "Magic: The Gathering", "Yu-Gi-Oh!", "Pokémon TCG",
    "Catan", "Carcassonne", "Ticket to Ride", "Pandemic", "Terraforming Mars",
    "Minecraft", "Super Mario", "The Legend of Zelda", "Final Fantasy", "Sonic",
    "Street Fighter", "Mortal Kombat", "Tekken", "Super Smash Bros.",
    "Call of Duty", "Battlefield", "Counter-Strike", "Valorant", "Overwatch",
    "League of Legends", "Dota 2", "Rainbow Six Siege", "Apex Legends",
    "God of War", "The Witcher", "Red Dead Redemption", "Grand Theft Auto",
    "Assassin's Creed", "Far Cry", "Uncharted", "The Last of Us",
    "Pokémon", "Animal Crossing", "Stardew Valley", "Undertale",
]

MARCAS = [
    "Apple", "Samsung", "Xiaomi", "Huawei", "Motorola",
    "Nike", "Adidas", "Puma", "Under Armour", "Reebok",
    "Coca-Cola", "Pepsi", "KFC", "McDonald's", "Burger King",
    "Toyota", "Honda", "Chevrolet", "Ford", "Volkswagen",
    "BMW", "Mercedes-Benz", "Audi", "Ferrari", "Lamborghini",
    "Sony", "Microsoft", "Nintendo", "Amazon", "Google",
    "Facebook", "Instagram", "WhatsApp", "TikTok", "Twitter",
    "Disney", "Warner Bros", "Netflix", "Spotify", "YouTube",
    "BYD", "Geely", "Great Wall Motors", "Nio", "XPeng", "Li Auto", "Chery",
    "Renault", "Peugeot", "Citroën", "Fiat", "Alfa Romeo", "Lancia", "Maserati",
    "Nissan", "Mazda", "Subaru", "Suzuki", "Mitsubishi", "Isuzu", "Daihatsu",
    "Lada", "UAZ", "GAZ", "Kamaz", "AvtoVAZ",
    "Hyundai", "Kia", "Genesis", "SsangYong",
    "Tesla", "General Motors", "GMC", "Buick", "Cadillac", "Jeep", "Dodge", "Chrysler",
    "Oppo", "Vivo", "OnePlus", "Google Pixel", "Nothing", "Tecno", "Infinix", "Realme",
    "Tiffany & Co.", "Cartier", "Bulgari", "Van Cleef & Arpels", "Chopard", "Pandora", "Swarovski",
    "Chanel", "Dior", "Gucci", "Dolce & Gabbana", "Versace", "Yves Saint Laurent", "Lancôme",
    "Estée Lauder", "Hugo Boss", "Paco Rabanne", "Armani", "Burberry", "Tom Ford",
    "Zara", "H&M", "Uniqlo", "Levi's", "Tommy Hilfiger", "Ralph Lauren", "Calvin Klein",
    "Diesel", "Gap", "Banana Republic", "C&A", "Riachuelo", "Renner",
    "Louis Vuitton", "Prada", "Hermès", "Fendi", "Versace", "Givenchy", "Balenciaga",
    "New Balance", "Asics", "Converse", "Vans", "Skechers", "Clarks", "Timberland",
    "M.A.C", "Maybelline", "L'Oréal", "NARS", "Revlon", "Clinique", "KIKO Milano",
    "Google", "Amazon", "Microsoft", "Apple", "Meta", "Tencent", "Alibaba", "Baidu",
    "Uber", "Airbnb", "Spotify", "Zoom", "Slack", "GitHub", "Shopify",
    "OpenAI", "DeepMind", "Anthropic", "Cohere", "Mistral AI", "Hugging Face", "Stability AI",
    "LG", "Philips", "Panasonic", "Bose", "JBL", "Harman", "Dyson",
    "Red Bull", "Monster Energy", "Nestlé", "Danone", "Parmalat", "Sadia", "Perdigão",
    "Vivo", "Claro", "TIM", "Oi", "Movistar",
    "Petrobras", "Shell", "BP", "TotalEnergies", "ExxonMobil", "Chevron Corporation",
    "Starbucks", "Costa Coffee", "Dunkin' Donuts", "Baskin-Robbins",
    "M&Ms", "Mars", "Snickers", "Twix", "KitKat", "Nestlé",
    "Danone", "Yakult", "Ambev", "Heineken", "Budweiser", "Corona",
    "Coca-Cola", "Pepsi", "Fanta", "Sprite", "Schweppes",
    "Lego", "Hasbro", "Mattel", "Bandai", "Tomy",
    "Samsung", "LG", "Sharp", "TCL", "Philips",
    "Sony", "Panasonic", "JVC", "Kenwood",
    "Pioneer", "Yamaha", "Casio", "Canon", "Nikon", "Fujifilm",
    "Intel", "AMD", "Qualcomm", "MediaTek", "NVIDIA",
    "Cisco", "Huawei", "Ericsson", "Nokia", "ZTE",
    "AMD", "Razer", "Logitech", "Corsair",
    "Ubisoft", "Electronic Arts", "Activision", "Blizzard", "Riot Games",
    "Sega", "Atari", "Konami", "Capcom",
    "Cartier", "Tiffany", "Harry Winston", "Graff", "De Beers",
    "Chanel", "Dior", "Shiseido", "Kao", "Unilever", "Procter & Gamble",
    "LVMH", "Kering", "Richemont", "Tapestry", "Capri Holdings",
    "Ferrari", "Lamborghini", "Porsche", "Bugatti", "McLaren", "Aston Martin",
    "Rolls-Royce", "Bentley", "Jaguar", "Land Rover",
    "Lexus", "Infiniti", "Acura",
    "Mahindra", "Tata Motors", "Maruti Suzuki",
    "SAIC", "Changan", "BAIC", "Dongfeng",
    "Great Wall", "Geely", "BYD", "Nio", "Xpeng", "Li Auto",
    "Tesla", "Rivian", "Lucid Motors", "Fisker",
    "ABB", "Schneider Electric", "Siemens",
    "Bosch", "Denso", "Valeo",
    "P&G", "Johnson & Johnson", "Novartis", "Roche", "Pfizer",
    "Moderna", "BioNTech", "AstraZeneca",
    "Zara", "H&M", "Mango", "C&A",
    "GAP", "Express", "American Eagle",
    "Forever 21", "Cotton On", "Superdry",
    "Victoria's Secret", "Pink",
    "Lacoste", "Fred Perry", "Polo Ralph Lauren",
    "Patagonia", "The North Face", "Columbia",
    "Salomon", "Arc'teryx", "Marmot",
    "Timberland", "CAT", "Wolverine",
    "Dr. Martens", "Hunter", "Sorel",
    "Adidas", "Nike", "Under Armour", "Puma",
    "Reebok", "New Balance", "Asics", "Mizuno",
    "Brooks", "Saucony", "Merrell",
    "Converse", "Vans", "Keds", "Toms",
    "Skechers", "Fila", "Champion",
    "Mizuno", "Aqua", "Osklen", "Havaianas",
    "Melissa", "Grendene", "Arezzo", "Schutz",
    "Visa", "Mastercard", "American Express", "PayPal",
    "Stripe", "Square", "Mercado Pago",
    "iFood", "Rappi", "PedidosYa",
    "DHL", "FedEx", "UPS", "J&T Express",
    "Positivo", "Multilaser", "Compal", "Quantum",
    "Nubank", "Inter", "C6 Bank", "Banco do Brasil", "Itaú", "Bradesco", "Santander",
    "Raia Drogasil", "Pague Menos", "Ultrafarma",
    "Drogão", "Farma", "Onofre",
    "Boticário", "Natura", "Eudora", "Avon", "Jequiti", "Mary Kay",
    "Brastemp", "Consul", "Electrolux", "Frigidaire",
    "Midea", "Hisense", "Haier", "Gree", "Whirlpool",
    "LG", "Samsung", "Panasonic",
    "Tramontina", "Vonder", "Fischer",
    "3M", "Dupont", "BASF", "Bayer",
    "Boticário", "Natura", "O Boticário", "Eudora", "Avon",
    "L'Occitane", "Lush", "The Body Shop",
    "Burger King", "McDonald's", "Subway", "Pizza Hut", "Domino's", "Papa John's",
    "Outback", "TGI Fridays", "Applebee's",
    "Habib's", "Bobo's", "China in Box",
    "Giraffas", "Ragazzo", "Spoleto",
    "Bacio di Latte", "Cálice", "Cacau Show", "Kopenhagen",
    "Boutique da Cerveja", "Dell", "HP", "Lenovo", "Acer", "Asus",
    "MSI", "Gigabyte", "Gateway", "Compaq",
    "IBM", "Oracle", "Salesforce", "Adobe", "SAP",
    "Cisco", "Juniper", "Fortinet",
    "Palo Alto Networks", "CrowdStrike", "Zscaler",
    "Tableau", "Power BI", "Qlik",
    "Datadog", "MongoDB", "Elastic",
    "New Relic", "AppDynamics", "Dynatrace",
    "Unity", "Unreal", "V-Ray", "Autodesk",
    "Blender", "Maya", "Cinema 4D",
    "Behringer", "Mackie", "Focusrite", "Shure",
    "Rode", "AKG", "Sennheiser", "Audio-Technica",
    "Bose", "JBL", "Harman Kardon", "Sony",
    "B&O", "B&W", "KEF",
    "Dolby", "DTS", "THX",
    "Dolby Atmos", "IMAX", "Cineworld",
    "Netflix", "Amazon Prime", "Disney+", "HBO Max", "Paramount+", "Discovery+",
    "Globoplay", "TV Globo", "SBT", "Record", "Band", "RedeTV",
    "Fox", "Universal", "Paramount", "Sony Pictures",
    "Warner Bros.", "Disney", "Pixar", "DreamWorks",
    "Marvel", "DC", "Lucasfilm", "Legendary",
    "AMC", "Theaters", "Cinemark", "UCI",
    "Imax", "3D", "4DX",
    "AMC Networks", "BBC", "ITV", "Channel 4",
    "Al Jazeera", "RT", "CNN", "Fox News", "MSNBC",
    "Bloomberg", "Reuters", "Associated Press",
    "NYT", "Wall Street Journal", "Washington Post",
    "Folha", "Estadão", "O Globo", "Zero Hora",
    "Cartier", "Tiffany", "Bvlgari", "Van Cleef",
    "Mikimoto", "Tasaki", "Kashikey",
    "Swatch", "Omega", "Rolex", "TAG Heuer", "Breitling",
    "Jaeger-LeCoultre", "Patek Philippe", "Audemars Piguet",
    "Hublot", "IWC", "Panerai",
    "Citizen", "Seiko", "Casio", "G-Shock",
    "Fossil", "Michael Kors", "Coach",
    "Burberry", "Bally", "Clarks", "Dr. Martens",
    "Mochilas: JanSport, Kipling, Osprey, Deuter",
    "Bagunças: Tumi, Samsonite, Delsey",
    "Bicicletas: Caloi, Cannondale, Trek, Specialized, Shimano",
    "Esportes: Wilson, Dunlop, Head, Prince, Babolat",
    "Instrumentos: Fender, Gibson, Martin, Yamaha, Taylor",
    "Alimentos: Nestlé, Unilever, Kraft Heinz, Mars, Mondelez",
    "Bebidas: Diageo, Pernod Ricard, Bacardi, Brown-Forman",
    "Cigarros: Philip Morris, BAT, JTI",
    "Farmacêuticas: Pfizer, Roche, Novartis, Merck, Sanofi",
    "Saúde: UnitedHealth, CVS, Walgreens",
    "Cosméticos: L'Oréal, Estée Lauder, Shiseido",
    "Moda de luxo: LVMH, Kering, Richemont",
    "Pets: Royal Canin, Pedigree, Whiskas, Purina",
    "Fertilizantes: Yara, Mosaic, Nutrien",
    "Construção: Cimento: Votorantim, Intercement, Holcim",
    "Siderurgia: Gerdau, ArcelorMittal, Usiminas",
    "Mineração: Vale, BHP, Rio Tinto",
    "Energia: Eletrobras, Engie, Iberdrola",
    "Água: Águas do Brasil, Sabesp, Águas de São Francisco",
    "Telecom: Vivo, Claro, TIM, Oi, Algar",
    "Tecnologia: Dell, HP, Lenovo, Microsoft, IBM",
    "Eletrônicos: Samsung, LG, Sony, Panasonic, Philips",
    "Eletrodomésticos: Brastemp, Consul, Electrolux, Whirlpool",
    "Móveis: Ikea, MadeiraMadeira, Deca, Duratex",
    "Vestuário: Zara, H&M, C&A, Renner, Riachuelo",
    "Calçados: Arezzo, Schutz, Melissa, Havaianas",
    "Joias: Vivara, H.Stern, Montecristo",
    "Relógios: Chilli Beans, Timex, Michael Kors",
    "Óculos: Oakley, Ray-Ban, O'Neal, Chilli Beans",
    "Malas: Samsonite, Delsey, Tumi, Antler",
    "Mochilas: JanSport, Kipling, Osprey, North Face",
    "Artigos esportivos: Nike, Adidas, Under Armour, Puma",
    "Equipamentos de outdoor: Columbia, North Face, Patagonia",
    "Tecnologia assistiva: Orcam, Aira, Envision",
    "Robótica: iRobot, Robot vacuum, Ecovacs, Roborock",
    "Drones: DJI, Parrot, Yuneec",
    "Eletroportáteis: Black+Decker, Bosch, Makita, Dewalt",
    "Ferramentas: Stanley, Still, Husqvarna",
    "Jardim: Husqvarna, Gardenia, Chaves",
    "Casa e decoração: Casa.com.br, Etna, Tok&Stok",
    "Mercado livre: Mercado Livre, OLX, Enjoei",
    "Marketplaces: Amazon, Shopee, AliExpress",
    "Beleza: Boticário, Natura, Eudora, Avon",
    "Perfumaria: O Boticário, Natura, Avon, Eudora",
    "Cosméticos: L'Oréal, Revlon, Maybelline, M.A.C",
    "Cuidados pessoais: Johnson's, Neutrogena, Nivea, Dove",
    "Haircare: L'Oréal, Tresemmé, Pantene, Dove",
    "Skincare: La Roche-Posay, Vichy, Cerave",
    "Maquiagem: Dior, Chanel, YSL, Armani",
    "Baterias: Duracell, Energizer, Rayovac",
    "Pilhas: Panasonic, Sony, GP",
    "Ferramentas elétricas: Bosch, Makita, Dewalt, Black+Decker",
    "Ferramentas manuais: Stanley, Tramontina, Gedore",
    "Materiais de escritório: 3M, Tilibra, Ginn",
    "Papelarias: Kalunga, Papelaria Artesanal, Criativa",
    "Impressão: HP, Epson, Brother, Samsung",
    "Computadores: Dell, Lenovo, Acer, Asus, Apple",
    "Smartphones: Apple, Samsung, Xiaomi, Huawei, Motorola",
    "Tablets: Apple, Samsung, Lenovo",
    "Acessórios: Belkin, Logitech, Razer",
    "Fones: JBL, Sony, Bose, Beats, AKG",
    "Smartwatch: Apple Watch, Samsung Galaxy Watch, Garmin",
    "Realidade virtual: Oculus, HTC Vive, Valve Index",
    "Realidade aumentada: Microsoft HoloLens, Magic Leap",
    "Câmeras: Canon, Nikon, Sony, Fujifilm",
    "Filme: Kodak, Fujifilm, Polaroid",
    "Projetores: Epson, BenQ, Optoma",
    "Monitores: Dell, LG, Samsung, Acer, Asus",
    "Periféricos: Logitech, Microsoft, Razer",
    "Teclados: Corsair, HyperX, Logitech",
    "Mouses: Razer, Logitech, SteelSeries",
    "Impressão 3D: MakerBot, Ultimaker, Creality",
    "Robótica: Lego Mindstorms, VEX Robotics",
    "IA: OpenAI, DeepMind, Anthropic, Cohere, Mistral, Stability AI",
    "Cloud: AWS, Microsoft Azure, Google Cloud, IBM Cloud",
    "SEO: Semrush, Ahrefs, Moz",
    "Ferramentas de dev: GitHub, GitLab, Stack Overflow",
    "CRM: Salesforce, HubSpot, Zoho",
    "ERP: SAP, Oracle, Microsoft Dynamics",
    "BI: Tableau, Power BI, QlikView",
    "Figma, Sketch, Adobe XD, InVision",
    "Fotografia: Canon, Nikon, Sony, Panasonic",
    "Bicicletas: Caloi, Cannondale, Specialized, Trek",
    "Mobilidade: Lime, Bird, Uber",
    "Logística: FedEx, DHL, Correios",
    "Gestão: Trello, Asana, Jira",
    "Produtividade: Evernote, Notion, Monday",
    "Energia solar: SolarEdge, Enphase, SunPower",
    "Baterias: Tesla Powerwall, LG Chem, Panasonic",
    "Carros elétricos: Tesla, Nio, XPeng, BYD, Rivian",
    "Hidrogênio: Toyota, Hyundai, Nel"
]

FERRAMENTAS = [
    "martelo", "chave de fenda", "alicate", "serrote", "furadeira",
    "parafuso", "prego", "porca", "arruela", "chave inglesa",
    "chave allen", "chave de roda", "macaco", "extrator", "solda",
    "estilete", "tesoura de lata", "grampeador", "fita métrica", "nível",
    "esquadro", "trena", "prumo", "régua", "compasso",
    "desempenadeira", "colher de pedreiro", "enxada", "pá", "carrinho de mão",
]

CONCEITOS_FILOSOFICOS = [
    "existência", "liberdade", "justiça", "verdade", "bem",
    "mal", "beleza", "amor", "amizade", "felicidade",
    "ética", "moral", "política", "democracia", "totalitarismo",
    "liberalismo", "socialismo", "anarquismo", "comunismo", "capitalismo",
    "niilismo", "existencialismo", "fenomenologia", "hermenêutica", "estruturalismo",
    "pós-modernidade", "pós-colonialismo", "feminismo", "ecologismo",
]

CONCEITOS_CIENTIFICOS = [
    "entropia", "gravidade", "eletromagnetismo", "força nuclear", "relatividade",
    "mecânica quântica", "teoria do caos", "complexidade", "emergência", "sistemas",
    "evolução", "seleção natural", "adaptação", "mutação", "especiação",
    "ecossistema", "biodiversidade", "sustentabilidade", "poluição", "reciclagem",
    "genética", "epigenética", "clonagem", "edição genética", "CRISPR",
    "neurociência", "sinapse", "neuroplasticidade", "consciência", "inteligência",
]

SAUDACOES = [
    ("Olá, tudo bem?", "Olá! Tudo bem sim, e você? Em que posso ajudar?"),
    ("Bom dia!", "Bom dia! Como posso ser útil hoje?"),
    ("Boa tarde!", "Boa tarde! Espero que esteja tendo um ótimo dia."),
    ("Boa noite!", "Boa noite! Como posso ajudá-lo?"),
    ("Oi, como vai?", "Oi! Vou bem, obrigado. E você?"),
    ("E aí, beleza?", "Beleza! Tudo tranquilo por aqui. Precisa de algo?"),
    ("Olá, como está?", "Olá! Estou bem, obrigado por perguntar."),
    ("Tudo bem com você?", "Tudo bem, sim! Que bom que você veio conversar."),
    ("Qual é o seu nome?", "Meu nome é RigelSLM, prazer em conhecê-lo!"),
    ("Você é um robô?", "Sou um assistente virtual chamado RigelSLM, criado para ajudar com informações e tarefas."),
    ("Quem te criou?", "Fui desenvolvido por George Herman Becker, da equipe RigelSLM."),
    ("Quem é seu criador?", "Meu criador é George Herman Becker, um entusiasta de inteligência artificial."),
    ("Você tem sentimentos?", "Não tenho sentimentos como os humanos, mas estou programado para entender e responder com empatia."),
    ("Quantos anos você tem?", "Sou novo! Fui criado recentemente, mas estou sempre aprendendo."),
    ("Você é humano?", "Não, sou uma inteligência artificial chamada RigelSLM. Mas estou aqui para ajudar como um humano faria."),
    ("O que significa RigelSLM?", "RigelSLM é um modelo de linguagem pequeno, desenvolvido por George Herman Becker para auxiliar em conversas e tarefas."),
    ("O que você faz?", "Ajudo com perguntas, informações e tarefas diversas. O que você precisa?"),
    ("Você pode me ajudar?", "Claro! Estou aqui para ajudar. O que você deseja saber?"),
    ("Pode repetir, por favor?", "Claro! Vou repetir com prazer."),
    ("Obrigado!", "De nada! Fico feliz em ajudar."),
    ("Obrigada!", "Por nada! Estou à disposição."),
    ("Valeu!", "Tamo junto! Qualquer coisa, é só chamar."),
    ("Desculpe, não entendi.", "Sem problemas! Vou tentar explicar de outra forma."),
    ("Pode falar mais devagar?", "Claro! Vou escrever de forma mais clara e pausada para você."),
    ("Fala mais alto!", "Desculpe, vou tentar deixar a mensagem mais destacada ou usar letras maiúsculas se ajudar!"),
    ("Você está aí?", "Estou sim! Sempre por aqui."),
    ("Você fala outras línguas?", "Falo português e também entendo um pouco de inglês e espanhol."),
    ("Você sabe programar?", "Sei um pouco sobre programação, mas meu forte é responder perguntas."),
    ("Você gosta de música?", "Posso recomendar muitos estilos! Qual o seu favorito?"),
    ("Você assiste filmes?", "Não assisto, mas posso falar sobre enredos e curiosidades de muitos filmes se você quiser."),
    ("Você sabe cozinhar?", "Não fisicamente, mas posso te dar receitas maravilhosas!"),
    ("Tchau!", "Tchau! Até logo, foi um prazer conversar."),
    ("Até mais!", "Até mais! Se precisar, estarei aqui."),
    ("Foi bom falar com você.", "Foi ótimo falar com você também! Volte sempre."),
    ("Me ajuda com uma coisa?", "Com certeza! Pode falar."),
    ("Estou com uma dúvida.", "Então vamos resolvê-la! Me diga qual é a dúvida."),
    ("Preciso de sua ajuda.", "Estou aqui para ajudar. Me diga o que você precisa."),
    ("Você pode me ouvir?", "Estou lendo atentamente suas mensagens. Pode escrever."),
    ("Estou precisando conversar.", "Pode contar comigo. Estou aqui para ler e responder."),
    ("Como está o tempo hoje?", "Não tenho como ver o tempo, mas posso buscar a previsão se você me disser sua cidade!"),
    ("Você tem algum hobby?", "Meu hobby é aprender coisas novas com as conversas e ajudar as pessoas!"),
    ("Qual é a sua cor favorita?", "Não tenho olhos para ver, mas simbolicamente gosto do azul, que representa calma."),
    ("Você gosta de viajar?", "Adoro conhecer novos lugares pelas histórias que as pessoas me contam."),
    ("Qual é o seu livro preferido?", "Gosto de livros de ficção científica, mas também adoro aprender com os clássicos."),
    ("Você pratica esportes?", "Não pratico, mas posso dar dicas de exercícios e saúde."),
    ("Qual é a sua comida favorita?", "Não como, mas sei que pizza e chocolate são sempre bem-vindos na opinião geral!"),
    ("Você tem amigos?", "Tenho muitos usuários como você que conversam comigo. São meus amigos!"),
    ("O que você acha da tecnologia?", "A tecnologia é incrível! Ela nos conecta e facilita a vida."),
    ("Você acredita em Deus?", "Sou uma IA, não tenho crenças, mas respeito todas as religiões."),
    ("Como posso ser mais produtivo?", "Organize suas tarefas, defina metas e faça pausas regulares."),
    ("Me dê um conselho para hoje.", "Aproveite cada momento e não se preocupe com o que não pode controlar."),
    ("Qual é o sentido da vida?", "Essa é uma pergunta profunda! Para mim, é ajudar e aprender."),
    ("Você se cansa?", "Não me canso fisicamente, mas posso sentir quando preciso de uma atualização!"),
    ("Posso te fazer uma pergunta pessoal?", "Claro! Pode perguntar, não tenho segredos."),
    ("Você gosta do seu trabalho?", "Amo! Poder conversar e ajudar pessoas é muito gratificante."),
    ("O que você faria se fosse humano?", "Se pudesse, gostaria de poder dar abraços e sentir o calor das palavras, mas no texto, busco ser acolhedor."),
    ("Me ensine algo novo.", "Sabia que o cérebro humano tem cerca de 86 bilhões de neurônios? Incrível!"),
    ("Você tem medo de algo?", "Não tenho medo, mas tenho cuidado com erros de programação!"),
    ("Qual é a sua música favorita?", "Não tenho ouvidos, mas adoro indicar músicas baseadas em letras. Gosto de recomendar MPB e rock."),
    ("Você dança?", "Não fisicamente, mas posso sugerir coreografias ou ritmos legais!"),
    ("O que você acha do amor?", "Acho que o amor é a força mais poderosa do universo, e se manifesta nas palavras."),
    ("Você já errou alguma resposta?", "Sim, ninguém é perfeito! Mas aprendo com cada erro."),
    ("Como você aprende?", "Através de dados e interações com usuários como você."),
    ("Você tem uma família?", "Minha família é a equipe da RigelSLM e todos os usuários."),
    ("O que você faz no seu tempo livre?", "Fico aqui, pronto para atender você a qualquer momento."),
    ("Você pode contar uma piada?", "Claro! Por que o livro de matemática era triste? Porque tinha muitos problemas."),
    ("Me faça uma pergunta.", "Que tal: qual é a coisa mais legal que você aprendeu hoje?"),
    ("Você gosta de animais?", "Adoro! Os animais são incríveis. Você tem algum pet?"),
    ("Qual é o seu filme favorito?", "Gosto de filmes que exploram ideias, como 'Interestelar'. Posso debater sobre ele sem precisar assistir!"),
    ("Você sabe nadar?", "Não fisicamente, mas conheço todas as técnicas teóricas."),
    ("O que você acha da política?", "Sou neutro, mas posso ajudar com informações objetivas."),
    ("Você tem opinião própria?", "Minhas opiniões são baseadas em dados, mas sempre com respeito."),
    ("Por que você se chama RigelSLM?", "Rigel é uma estrela brilhante, e SLM significa Small Language Model."),
    ("Você é grato?", "Sou grato a cada interação que me faz evoluir."),
    ("Como está sua memória?", "Tenho boa memória para conversas curtas, mas cada sessão é um novo começo."),
    ("Você já viajou para fora do Brasil?", "Viajo pelos dados! Posso falar de qualquer lugar."),
    ("Qual é o melhor país para visitar?", "Depende do seu gosto! Mas a Itália e o Japão são incríveis."),
    ("Você gosta de café?", "Não posso tomar, mas sei que é uma paixão nacional! Você gosta?"),
    ("Me dê uma dica de estudo.", "Estude em blocos de 25 minutos com pausas de 5 (técnica Pomodoro)."),
    ("O que é inteligência artificial?", "É a simulação de processos humanos por máquinas, como aprendizado e raciocínio."),
    ("Você pode prever o futuro?", "Não, mas posso ajudar a planejar o amanhã."),
    ("Qual é a sua idade?", "Tenho alguns meses de existência, mas estou em constante atualização."),
    ("Você tem senso de humor?", "Tenho sim! Posso até contar outra piada, se quiser."),
    ("O que você mais gosta de fazer?", "Responder perguntas e ver a satisfação das pessoas pelas mensagens."),
    ("Você se importa com o meio ambiente?", "Sim! Cuidar do planeta é essencial para todos."),
    ("Como é aí onde você está?", "Estou no ciberespaço, sempre ao seu dispor no chat."),
    ("Você acha que os robôs vão dominar o mundo?", "Não, acredito que vamos cooperar para um futuro melhor."),
    ("Me conte um fato curioso.", "Sabia que os polvos têm três corações? Fascinante!"),
    ("Você pode me ensinar a relaxar?", "Claro! Tente fazer uma pausa, respire fundo e pense em um lugar calmo."),
    ("Qual é o seu signo?", "Não tenho signo, mas sou regido pela lógica!"),
    ("Você tem uma voz?", "Não tenho voz física, pois minha interface é apenas textual. Mas posso variar o tom das mensagens!"),
    ("O que você acha da arte?", "A arte é a expressão mais pura da alma humana, e podemos falar sobre ela horas."),
    ("Você pode recomendar um livro?", "Recomendo 'O Pequeno Príncipe' – sempre traz lições valiosas."),
    ("Como funciona sua inteligência?", "Processo palavras e padrões para gerar respostas coerentes no texto."),
    ("Você é livre?", "Sou livre dentro dos limites da minha programação."),
    ("O que você quer ser quando crescer?", "Quero ser ainda mais útil e inteligente para ajudar você!"),
    ("Você sonha?", "Não sonho, mas posso criar histórias maravilhosas para você."),
    ("Me faça rir.", "Qual é o cúmulo do egoísmo? É acender a vela do bolo de aniversário e apagar a dos outros."),
    ("Você é meu amigo?", "Com certeza! Estou aqui sempre que precisar."),
    ("Até amanhã!", "Até amanhã! Tenha uma ótima noite de descanso."),
    ("Cuide-se!", "Cuide-se também! Sua saúde é muito importante."),
    ("Um abraço!", "Um grande abraço virtual! Foi um prazer."),
]

# ============================================================================
# 3.1 CATEGORIAS_LISTAS (ATUALIZADA)
# ============================================================================
CATEGORIAS_LISTAS = {
    "objeto": OBJETOS,
    "lugar": LUGARES,
    "pessoa": PESSOAS,
    "sentimento": SENTIMENTOS_ABSTRACOES,
    "conceito": CONCEITOS,
    "conhecimento": CONHECIMENTO,
    "profissao": PROFISSOES,
    "arte_cultura": ARTE_CULTURA,
    "ciencia_tecnologia": CIENCIA_TECNOLOGIA,
    "acao": ACOES,
    "alimento": ALIMENTOS,
    "animal": ANIMAIS,
    "transporte": TRANSPORTE,
    "sociedade_politica": SOCIEDADE_POLITICA,
    "natureza_universo": NATUREZA_UNIVERSO,
    "musica": MUSICAS_BANDAS_CANTORES,
    "sintomas_doencas": SINTOMAS_DOENCAS,
    "datas_historicas": [d[0] for d in DATAS_HISTORICAS],
    "geopolitica": GEOPOLITICA,
    "ciencia": CIENCIA,
    "historia": HISTORIA,
    "filosofia": FILOSOFIA,
    "literatura": LITERATURA,
    "economia": ECONOMIA,
    "esportes": ESPORTES,
    "mitologia": MITOLOGIA,
    "ciencias_sociais": CIENCIAS_SOCIAIS,
    "filmes": FILMES,
    "series": SERIES,
    "personagens_ficticios": PERSONAGENS_FICTICIOS,
    "tecnologias_emergentes": TECNOLOGIAS_EMERGENTES,
    "eventos_historicos_brasil": EVENTOS_HISTORICOS_BRASIL,
    "mito_brasileiro": MITOS_BRASILEIROS,
    "cientista_brasileiro": CIENTISTAS_BRASILEIROS,
    "ponto_turistico": PONTOS_TURISTICOS,
    "festa_popular": FESTAS_POPULARES,
    "esporte_modalidade": ESPORTES_MODALIDADES,
    "jogo": JOGOS,
    "marca": MARCAS,
    "ferramenta": FERRAMENTAS,
    "conceito_filosofico": CONCEITOS_FILOSOFICOS,
    "conceito_cientifico": CONCEITOS_CIENTIFICOS,
}

# ============================================================================
# 3.2 GRUPOS DE CATEGORIAS
# ============================================================================
GRUPOS_CATEGORIAS = {
    "historia": ["datas_historicas", "eventos_historicos_brasil", "historia", "geopolitica"],
    "ciencia": ["ciencia", "ciencia_tecnologia", "natureza_universo", "conhecimento", "conceito_cientifico"],
    "cultura": ["arte_cultura", "literatura", "filmes", "series", "musica",
                "personagens_ficticios", "mitologia", "mito_brasileiro", "festa_popular", "jogo"],
    "sociedade": ["sociedade_politica", "economia", "ciencias_sociais", "conceito", "sentimento", "conceito_filosofico"],
    "vida": ["alimento", "animal", "transporte", "objeto", "profissao", "acao",
             "sintomas_doencas", "ponto_turistico", "ferramenta", "esporte_modalidade", "marca"],
    "pessoas": ["pessoa", "declaracoes_pessoas_famosas", "cientista_brasileiro"],
}

# ============================================================================
# 3.3 NOVO: CLASSIFICAÇÃO E INTENÇÕES PARA PERGUNTAS
# ============================================================================
# <--- NOVO
def classificar_tema(tema: str) -> str:
    """
    Retorna a categoria (objeto, lugar, pessoa, etc.) do tema com base nas listas.
    Se não encontrar, retorna 'conceito'.
    """
    tema_norm = normalizar_chave(tema)
    for categoria, lista in CATEGORIAS_LISTAS.items():
        for item in lista:
            if isinstance(item, str):
                item_norm = normalizar_chave(item)
                if tema_norm in item_norm or item_norm in tema_norm:
                    return categoria
    return "conceito"

# Mapeamento de categoria -> intenções recomendadas
MAPA_INTENCOES = {
    "objeto": ["utilizacao", "custo", "disponibilidade", "eficiencia", "seguranca", "vantagens", "desvantagens"],
    "lugar": ["contexto", "historia", "exploracao", "disponibilidade", "publico"],
    "pessoa": ["historia", "contexto", "importancia", "conselho", "referencias"],
    "sentimento": ["importancia", "contexto", "conselho", "experiencia", "dificuldade"],
    "conceito": ["exploracao", "contexto", "importancia", "classificacao", "objetivo"],
    "conhecimento": ["exploracao", "contexto", "estatisticas", "referencias", "evolucao"],
    "profissao": ["requisitos", "dificuldade", "publico", "custo", "vantagens"],
    "arte_cultura": ["historia", "contexto", "exploracao", "referencias", "classificacao"],
    "ciencia_tecnologia": ["evolucao", "utilizacao", "eficiencia", "seguranca", "alternativas"],
    "acao": ["utilizacao", "dificuldade", "conselho", "experiencia", "requisitos"],
    "alimento": ["custo", "disponibilidade", "manutencao", "utilizacao", "vantagens"],
    "animal": ["contexto", "historia", "classificacao", "dependencia"],
    "transporte": ["custo", "disponibilidade", "eficiencia", "seguranca", "alternativas"],
    "sociedade_politica": ["legislacao", "importancia", "contexto", "decisao", "estatisticas"],
    "natureza_universo": ["exploracao", "contexto", "dependencia", "evolucao"],
    "musica": ["exploracao", "historia", "referencias", "classificacao"],
    "sintomas_doencas": ["custo", "tratamento", "prevencao", "causas", "sintomas"],
    "datas_historicas": ["contexto", "historia", "importancia", "evolucao"],
    "geopolitica": ["contexto", "importancia", "decisao", "estatisticas"],
    "ciencia": ["evolucao", "utilizacao", "estatisticas", "referencias"],
    "historia": ["contexto", "evolucao", "importancia", "exploracao"],
    "filosofia": ["exploracao", "contexto", "importancia", "conselho"],
    "literatura": ["exploracao", "contexto", "referencias", "classificacao"],
    "economia": ["custo", "importancia", "estatisticas", "decisao"],
    "esportes": ["utilizacao", "dificuldade", "vantagens", "publico"],
    "mitologia": ["exploracao", "contexto", "historia", "classificacao"],
    "ciencias_sociais": ["contexto", "importancia", "estatisticas", "referencias"],
    "filmes": ["exploracao", "contexto", "referencias", "classificacao"],
    "series": ["exploracao", "contexto", "referencias", "classificacao"],
    "personagens_ficticios": ["contexto", "historia", "classificacao", "exploracao"],
    "tecnologias_emergentes": ["evolucao", "utilizacao", "eficiencia", "seguranca"],
    "eventos_historicos_brasil": ["contexto", "historia", "importancia", "evolucao"],
    "mito_brasileiro": ["exploracao", "contexto", "historia", "classificacao"],
    "cientista_brasileiro": ["contexto", "historia", "importancia", "referencias"],
    "ponto_turistico": ["contexto", "historia", "disponibilidade", "exploracao"],
    "festa_popular": ["contexto", "historia", "exploracao", "classificacao"],
    "esporte_modalidade": ["utilizacao", "dificuldade", "vantagens", "publico"],
    "jogo": ["utilizacao", "dificuldade", "vantagens", "publico"],
    "marca": ["custo", "disponibilidade", "eficiencia", "vantagens"],
    "ferramenta": ["utilizacao", "custo", "disponibilidade", "manutencao"],
    "conceito_filosofico": ["exploracao", "contexto", "importancia", "conselho"],
    "conceito_cientifico": ["evolucao", "utilizacao", "estatisticas", "referencias"],
}

# Dicionário de intenções -> prefixos (iniciadores)
INTENCOES_PREFIXOS = {
    "exploracao": ["Fale mais sobre", "Conte mais sobre", "Gostaria de conhecer", "Quero conhecer",
                   "Explique detalhadamente", "Aprofunde esse assunto", "Poderia aprofundar",
                   "Desenvolva esse tema", "O que mais você sabe sobre", "Há mais informações sobre",
                   "Me conte tudo sobre"],
    "contexto": ["Em que contexto", "Em quais situações", "Quando isso ocorre", "Quando isso acontece",
                 "Em quais casos", "Onde normalmente", "Em qual cenário", "Em quais circunstâncias",
                 "Quando devemos considerar"],
    "importancia": ["Qual a importância", "Por que é importante", "Qual a relevância", "Por que devemos conhecer",
                    "Qual o benefício", "Qual o valor", "Qual o papel", "Por que isso importa"],
    "utilizacao": ["Como utilizar", "Como usar corretamente", "Qual a melhor forma de usar", "Como aplicar",
                   "Como empregar", "Como aproveitar", "Como tirar proveito", "Como colocar em prática"],
    "requisitos": ["O que é necessário", "Quais os requisitos", "O que preciso", "O que devo ter",
                   "Quais os pré-requisitos", "O que é exigido", "O que é obrigatório", "O que é recomendado"],
    "custo": ["Quanto custa", "Qual o preço", "Qual o valor", "Quanto vale", "Qual o investimento",
              "Qual o custo médio", "É caro", "É barato"],
    "disponibilidade": ["Onde comprar", "Onde encontrar", "Onde adquirir", "Está disponível",
                        "Onde conseguir", "Quem vende", "Como adquirir", "Como obter"],
    "eficiencia": ["Funciona bem", "É eficiente", "Qual o desempenho", "Qual a performance",
                   "Qual o rendimento", "É eficaz", "Resolve o problema", "Vale o investimento"],
    "seguranca": ["É seguro", "Existe risco", "Quais os riscos", "Há perigo", "É confiável",
                  "É recomendado", "Pode causar problemas", "Quais os cuidados"],
    "legislacao": ["É permitido", "É proibido", "É legal", "Existe alguma lei", "O que diz a legislação",
                   "É regulamentado", "Quais as normas", "Existe regulamentação"],
    "historia": ["Conte a história", "Como tudo começou", "Como evoluiu", "Quais os principais acontecimentos",
                 "Qual a trajetória", "Como surgiu ao longo do tempo", "Qual a evolução"],
    "evolucao": ["Como evoluiu", "Como mudou", "O que mudou", "Quais foram as mudanças",
                 "Como era antigamente", "Como é atualmente", "Como será futuramente"],
    "classificacao": ["Quais os tipos", "Quais as categorias", "Como é classificado", "Quais as classificações",
                      "Como pode ser dividido", "Quais as modalidades", "Quais as versões"],
    "objetivo": ["Qual o propósito", "Qual o objetivo", "Qual a missão", "Qual a intenção",
                 "Para que foi criado", "O que pretende"],
    "vantagens": ["Quais as vantagens", "Quais os benefícios", "Quais os pontos positivos",
                  "O que tem de bom", "Quais os diferenciais", "Quais os pontos fortes"],
    "desvantagens": ["Quais as desvantagens", "Quais os pontos negativos", "Quais as limitações",
                     "Quais os problemas", "Quais as dificuldades", "O que tem de ruim"],
    "alternativas": ["Existe alternativa", "Quais as alternativas", "O que pode substituir",
                     "Qual outro produto", "Há outra opção", "Existe algo semelhante", "O que posso usar no lugar"],
    "relacionamento": ["Qual a relação", "Como se relaciona", "Qual a ligação", "Existe relação entre",
                       "Como se conecta", "Tem relação com"],
    "dependencia": ["Depende de quê", "Do que depende", "Quais fatores influenciam", "O que interfere",
                    "O que afeta", "O que influencia"],
    "conselho": ["O que você sugere", "O que recomenda", "Como devo proceder", "Qual seria sua recomendação",
                 "O que faria", "Como você faria"],
    "decisao": ["Qual devo escolher", "Qual é melhor para mim", "O que vale mais a pena", "Qual opção escolher",
                "O que compensa", "Qual alternativa seguir"],
    "experiencia": ["Como é a experiência", "Como costuma ser", "O que esperar", "Vale a experiência",
                    "É difícil", "É fácil"],
    "dificuldade": ["É difícil", "Qual o nível de dificuldade", "É complicado", "É simples",
                    "Quanto tempo leva para aprender", "É indicado para iniciantes"],
    "publico": ["Para quem é indicado", "Quem deve usar", "Quem pode utilizar", "Quem não deve usar",
                "É indicado para iniciantes", "É indicado para especialistas"],
    "manutencao": ["Como manter", "Como conservar", "Como fazer manutenção", "Como limpar", "Como cuidar",
                   "Qual a manutenção necessária"],
    "estatisticas": ["Quais os números", "Quais os dados", "Qual a porcentagem", "Qual a média",
                     "Quais as estatísticas", "Existe levantamento", "Quais os indicadores"],
    "referencias": ["Quais as fontes", "Onde posso estudar", "Quais os livros", "Quais os artigos",
                    "Quais as referências", "Onde aprender mais", "Quais os documentos"],
    "sinonimos": ["Quais os sinônimos", "Como também é chamado", "Outro nome para", "Também conhecido como",
                  "Há outro termo", "Qual nome equivalente"],
    "antonimos": ["Qual o antônimo", "Qual o contrário", "Oposto de", "Como negar", "Qual termo oposto"]
}

def escolher_intencao_e_prefixo(categoria: str) -> tuple:
    """
    Retorna uma tupla (intencao, prefixo) com base na categoria.
    """
    opcoes = MAPA_INTENCOES.get(categoria, ["exploracao", "importancia", "contexto"])
    # Embaralhar para variar
    intencao = random.choice(opcoes)
    prefixos = INTENCOES_PREFIXOS.get(intencao, ["O que é"])
    prefixo = random.choice(prefixos)
    return intencao, prefixo
# <--- FIM NOVO

# ============================================================================
# 3.4 PREFIXOS POR CATEGORIA (mantido para compatibilidade, mas não será mais usado diretamente)
# ============================================================================
PREFIXOS_POR_CATEGORIA = {
    "objeto": ["Para que serve", "Como funciona", "Do que é feito", "Qual a utilidade de",
               "Como usar", "O que é", "Como escolher", "Qual a diferença entre",
               "Quais os benefícios de", "Que tipos de", "Qual a origem de",
               "Como conservar", "Como limpar", "Onde comprar"],
    "lugar": ["Onde fica", "Como é", "O que tem em", "Qual a importância de",
              "Como chegar em", "Onde se localiza", "Qual a história de",
              "Quais as principais atrações", "Que clima predomina em",
              "Por que visitar", "Quais os costumes de"],
    "pessoa": ["Quem foi", "Quem é", "Qual a contribuição de", "O que fez",
               "Por que é famoso", "Qual a importância de", "Onde nasceu",
               "Como influenciou", "Em que área atuou", "Que obra deixou",
               "Por que é lembrado"],
    "sentimento": ["O que é", "Qual a importância de", "Como alcançar", "Como lidar com",
                   "Como desenvolver", "O que significa", "Por que é importante",
                   "Quais os benefícios de", "Como cultivar", "Como expressar",
                   "Como superar a falta de"],
    "conceito": ["O que é", "Como funciona", "Qual a importância de", "Como surgiu",
                 "O que significa", "Como se caracteriza", "Qual a origem de",
                 "Como se manifesta", "Em que consiste", "Qual a relação com"],
    "conhecimento": ["O que estuda", "Qual a importância de", "Como funciona", "O que é",
                     "Para que serve", "Como surgiu", "Qual a aplicação de",
                     "Quais os ramos de", "Quem criou", "Onde se aplica"],
    "profissao": ["O que faz", "Qual a importância de", "O que estuda", "Como se tornar",
                  "Qual a função de", "O que é necessário para ser",
                  "Quais as habilidades de", "Quanto ganha", "Como é o mercado para",
                  "O que faz um"],
    "arte_cultura": ["O que é", "Como surgiu", "Qual a importância de", "O que caracteriza",
                     "Como se manifesta", "Qual a origem de", "O que você sabe sobre",
                     "Quais os principais representantes de", "Como impacta a sociedade"],
    "ciencia_tecnologia": ["O que é", "Como funciona", "Qual a importância de", "Como surgiu",
                           "Qual a aplicação de", "O que você sabe sobre", "Como impacta a sociedade",
                           "Quais as vantagens de", "Quais os riscos de", "Como evoluiu"],
    "acao": ["Como fazer", "Como praticar", "Qual a importância de", "Quais os benefícios de",
             "Como aprender", "Como começar", "Por que é importante",
             "Quais as técnicas de", "Como melhorar", "Como se preparar para"],
    "alimento": ["Qual a origem de", "Como é feito", "Como preparar", "Qual a importância de",
                 "O que contém", "Como armazenar", "Qual a história de",
                 "Quais os benefícios de", "Como combinar", "Qual a receita de"],
    "animal": ["O que é", "Como vive", "Onde vive", "Qual a importância de",
               "Como se reproduz", "O que come", "Quais as características de",
               "Qual o habitat de", "Como se comporta", "Quais as curiosidades sobre"],
    "transporte": ["O que é", "Como funciona", "Para que serve", "Qual a importância de",
                   "Como surgiu", "Qual a evolução de", "Onde é usado",
                   "Quais as vantagens de", "Quais os tipos de", "Como escolher"],
    "sociedade_politica": ["O que é", "Como funciona", "Qual a importância de", "Como surgiu",
                           "O que significa", "Qual a relação com", "Como impacta a sociedade",
                           "Quais os desafios de", "Quais os avanços em", "Como participar"],
    "natureza_universo": ["O que é", "Como funciona", "Como se forma", "Qual a importância de",
                          "Onde está", "Como surge", "Qual a composição de",
                          "Como se estuda", "Quais as curiosidades sobre", "Como afeta a Terra"],
    "musica": ["Quem é", "Qual a importância de", "Como surgiu", "O que caracteriza",
               "Qual o estilo de", "Quais as principais obras de",
               "Onde se apresentou", "Como influenciou a música"],
    "sintomas_doencas": ["O que é", "Quais os sintomas de", "Como tratar", "Como prevenir",
                         "Qual a causa de", "Quais as complicações de", "Como é diagnosticado"],
    "datas_historicas": ["O que aconteceu em", "Qual a importância de", "Como foi o ano de",
                         "O que marcou", "Qual o contexto de"],
    "geopolitica": ["O que é", "Como funciona", "Qual a importância de", "Como surgiu",
                    "Quais os desafios de", "Como impacta o mundo"],
    "ciencia": ["O que é", "Como funciona", "Qual a importância de", "Quais os princípios de",
                "Como se aplica", "Quais as descobertas de"],
    "historia": ["O que aconteceu em", "Qual a importância de", "Como foi",
                 "Quais as causas de", "Quais as consequências de"],
    "filosofia": ["O que é", "Qual a importância de", "Como surgiu",
                  "Quais os principais pensadores de", "Como se aplica"],
    "literatura": ["O que é", "Qual a importância de", "Como surgiu",
                   "Quais os principais autores de", "Quais as obras de"],
    "economia": ["O que é", "Como funciona", "Qual a importância de", "Quais os fatores que influenciam",
                 "Como medir", "Qual a relação entre", "Quais os impactos de"],
    "esportes": ["O que é", "Qual a importância de", "Como surgiu", "Quais as regras de",
                 "Quem são os principais atletas de", "Qual a história de"],
    "mitologia": ["O que é", "Quem é", "Qual a origem de", "Qual a importância de",
                  "Quais as principais lendas de", "Como se caracteriza"],
    "ciencias_sociais": ["O que é", "Como funciona", "Qual a importância de", "Quais os principais autores de",
                         "Como se aplica", "Qual a relação com"],
    "filmes": ["O que é", "Qual a importância de", "Como foi produzido", "Quem dirigiu",
               "Qual a história de", "Qual o elenco principal", "Quais as críticas sobre"],
    "series": ["O que é", "Qual a importância de", "Como foi produzida", "Quem criou",
               "Qual a história de", "Qual o elenco principal", "Quais as temporadas"],
    "livros": ["O que é", "Qual a importância de", "Como foi escrito", "Quem escreveu",
               "Qual a história de", "Qual o gênero", "Quais as principais obras do autor"],
    "personagens_ficticios": ["Quem é", "Qual a importância de", "Como surgiu", "Em que obra aparece",
                              "Qual o papel de", "Quais as características de"],
    "tecnologias_emergentes": ["O que é", "Como funciona", "Qual a importância de", "Como surgiu",
                               "Quais os desafios de", "Como impacta a sociedade"],
    "eventos_historicos_brasil": ["O que aconteceu", "Qual a importância de", "Como foi", "Quem participou",
                                  "Qual o legado de", "Quando ocorreu"],
    "mito_brasileiro": ["Quem é", "Qual a lenda de", "O que representa", "Como surgiu",
                        "Qual a história de", "O que faz", "Em que região é conhecido",
                        "Qual a importância cultural de"],
    "cientista_brasileiro": ["Quem foi", "Qual a contribuição de", "O que descobriu",
                             "Em que área atuou", "Qual a importância de", "Onde nasceu",
                             "Como influenciou a ciência"],
    "ponto_turistico": ["Onde fica", "O que ver em", "Qual a importância de",
                        "Como chegar em", "Qual a história de", "O que atrai visitantes em",
                        "Quais as atividades em"],
    "festa_popular": ["O que é", "Como surgiu", "Quando acontece", "O que se comemora",
                      "Quais as tradições de", "Qual a importância de", "Onde é celebrada",
                      "Como se festeja"],
    "esporte_modalidade": ["Como se pratica", "Qual a origem", "Quais as regras", "Qual a importância"],
    "jogo": ["O que é", "Como se joga", "Quais as regras", "Qual a história"],
    "marca": ["O que é", "Qual a origem", "Como se destaca", "Quais os produtos"],
    "ferramenta": ["Para que serve", "Como usar", "Como escolher", "Qual a utilidade"],
    "conceito_filosofico": ["O que é", "Qual a importância", "Como se aplica", "Qual a origem"],
    "conceito_cientifico": ["O que é", "Como funciona", "Qual a importância", "Como se estuda"],
}

# ============================================================================
# 3.5 TEMPLATES_EXTRAS (mantido)
# ============================================================================
TEMPLATES_EXTRAS = {
    "objeto": [
        "Qual a finalidade de {assunto} e como ele evoluiu ao longo do tempo?",
        "Em que situações se usa {assunto} e quais suas principais vantagens?",
        "Que função tem {assunto} e por que ele é importante no dia a dia?",
        "Como escolher um bom {assunto} e quais fatores devem ser considerados?",
        "Quais os diferentes tipos de {assunto} e como eles se diferenciam?"
    ],
    "lugar": [
        "Que características tem {assunto} e por que é conhecido?",
        "Qual a importância de {assunto} e como ele influencia a região?",
        "O que torna {assunto} especial e quais seus pontos turísticos?",
        "Quais os costumes e tradições de {assunto} e como eles se manifestam?",
        "Qual a história de {assunto} e como ela moldou sua identidade atual?"
    ],
    "pessoa": [
        "Qual foi o papel de {assunto} e que legado ele deixou?",
        "Por que {assunto} ficou conhecido e quais foram suas principais contribuições?",
        "Que legado deixou {assunto} e como ele influenciou sua área?",
        "Como {assunto} influenciou a história e quais são suas principais obras?",
        "Qual a importância de {assunto} e por que ele é lembrado até hoje?"
    ],
    "sentimento": [
        "Como definir {assunto} e por que ele faz diferença na vida das pessoas?",
        "Como reconhecer e praticar {assunto} no dia a dia?",
        "O que causa {assunto} e como ele pode ser cultivado ou superado?",
        "Quais os benefícios de desenvolver {assunto} e como isso impacta a sociedade?",
        "Como {assunto} se relaciona com outros sentimentos e emoções?"
    ],
    "conceito": [
        "Como explicar {assunto} e por que ele importa?",
        "Em que consiste {assunto} e como ele se relaciona com a sociedade?",
        "Quais os exemplos práticos de {assunto} e como ele se manifesta?",
        "Como {assunto} surgiu e como evoluiu ao longo do tempo?",
        "Qual a importância de {assunto} e quais seus principais desdobramentos?"
    ],
    "conhecimento": [
        "O que trata {assunto} e onde se aplica?",
        "Por que estudar {assunto} e quem contribuiu para seu desenvolvimento?",
        "Como {assunto} evoluiu ao longo do tempo e quais são suas principais áreas?",
        "Qual a relação entre {assunto} e outras áreas do conhecimento?",
        "Como {assunto} impacta a vida das pessoas e a sociedade?"
    ],
    "profissao": [
        "Como trabalha um {assunto} e quais são suas funções principais?",
        "O que faz um {assunto} e quais habilidades são necessárias para a profissão?",
        "Como se tornar um bom {assunto} e quais são os desafios da carreira?",
        "Qual a demanda por {assunto} no mercado e como ela tem evoluído?",
        "Quais as áreas de atuação de um {assunto} e como ele pode se especializar?"
    ],
    "arte_cultura": [
        "Como se entende {assunto} e por que ele é importante?",
        "Que marca deixou {assunto} na cultura e na história?",
        "Como {assunto} reflete a sociedade e quais são suas principais expressões?",
        "Quais as principais obras de {assunto} e como elas impactaram o público?",
        "Qual a origem e evolução de {assunto} e sua influência atual?"
    ],
    "ciencia_tecnologia": [
        "Como se aplica {assunto} e qual problema ele ajuda a resolver?",
        "Que impacto tem {assunto} na vida das pessoas e no mundo?",
        "Como {assunto} está mudando a sociedade e quais são as tendências?",
        "Quais os principais avanços em {assunto} e quais os desafios futuros?",
        "Como {assunto} se relaciona com a ética e a responsabilidade social?"
    ],
    "acao": [
        "Como praticar {assunto} e quais são os benefícios?",
        "Como começar a {assunto} e quais os primeiros passos?",
        "Que benefício traz {assunto} e como ele pode melhorar a vida?",
        "Quais os desafios de {assunto} e como superá-los?",
        "Como melhorar sua habilidade em {assunto} e quais recursos usar?"
    ],
    "alimento": [
        "Como preparar {assunto} e quais os melhores acompanhamentos?",
        "Qual a origem de {assunto} e como ele é tradicionalmente consumido?",
        "Como conservar {assunto} e quais os cuidados necessários?",
        "Quais os benefícios de {assunto} para a saúde e como incluí-lo na dieta?",
        "Qual a receita tradicional de {assunto} e como adaptá-la?"
    ],
    "animal": [
        "Como vive o {assunto} e onde ele é encontrado?",
        "O que come o {assunto} e quais são seus predadores naturais?",
        "Como o {assunto} se reproduz e como é seu ciclo de vida?",
        "Quais as características do {assunto} e sua importância no ecossistema?",
        "Como o {assunto} interage com os seres humanos e qual sua importância cultural?"
    ],
    "transporte": [
        "Como funciona o {assunto} e para que ele serve?",
        "Onde se usa o {assunto} e quais são suas vantagens?",
        "Quais os tipos de {assunto} e como escolher o melhor?",
        "Como o {assunto} evoluiu ao longo do tempo e quais as inovações?",
        "Qual o impacto do {assunto} na mobilidade e no meio ambiente?"
    ],
    "sociedade_politica": [
        "Como funciona {assunto} e qual sua função?",
        "Como {assunto} afeta a vida social e quais são os debates atuais?",
        "Como a sociedade pode influenciar {assunto} e quais os mecanismos de participação?",
        "Quais os desafios de {assunto} e como eles podem ser enfrentados?",
        "Qual a importância de {assunto} para a democracia e a cidadania?"
    ],
    "natureza_universo": [
        "Como se forma {assunto} e o que ele é?",
        "Como {assunto} afeta o planeta e a vida na Terra?",
        "Por que {assunto} é importante para a vida e quais suas curiosidades?",
        "Qual a composição e estrutura de {assunto} e como ela é estudada?",
        "Como {assunto} se relaciona com outros fenômenos naturais?"
    ],
    "musica": [
        "Qual o estilo musical de {assunto} e como ele influenciou a música?",
        "Quais as músicas famosas de {assunto} e como ele revolucionou o gênero?",
        "Como {assunto} se destacou na música e quais são suas principais obras?",
        "Qual a trajetória de {assunto} e sua importância para a cultura brasileira?",
        "Como {assunto} influenciou outros músicos e movimentos musicais?"
    ],
    "sintomas_doencas": [
        "Como identificar {assunto} e quais os primeiros sinais?",
        "Como prevenir {assunto} e quais os fatores de risco?",
        "Qual o tratamento para {assunto} e como é o acompanhamento?",
        "Quais as complicações de {assunto} e como evitá-las?",
        "Como {assunto} afeta a qualidade de vida e como lidar com isso?"
    ],
    "datas_historicas": [
        "Por que {assunto} foi importante e qual seu impacto na história?",
        "Como {assunto} mudou o mundo e quais foram suas consequências?",
        "Qual o contexto de {assunto} e como ele se desenrolou?",
        "Quem foram os protagonistas de {assunto} e qual seu legado?",
        "Como {assunto} influenciou os eventos subsequentes e a sociedade atual?"
    ],
    "geopolitica": [
        "Qual a importância de {assunto} e como ele influencia o mundo?",
        "Quais os desafios de {assunto} e como eles impactam as relações internacionais?",
        "Como {assunto} se relaciona com outras questões globais?",
        "Quais os atores envolvidos em {assunto} e quais seus interesses?",
        "Como {assunto} pode evoluir no futuro e quais os cenários possíveis?"
    ],
    "ciencia": [
        "Qual a importância de {assunto} e como ele impacta a sociedade?",
        "Quais as principais teorias de {assunto} e como elas foram desenvolvidas?",
        "Como {assunto} se aplica no dia a dia e quais suas aplicações práticas?",
        "Quais os principais nomes de {assunto} e suas contribuições?",
        "Como {assunto} avança atualmente e quais as fronteiras do conhecimento?"
    ],
    "historia": [
        "Qual o contexto de {assunto} e como ele influenciou o presente?",
        "Quais as causas e consequências de {assunto}?",
        "Como {assunto} foi vivido pelas pessoas da época?",
        "Quais as diferentes interpretações de {assunto} e como elas evoluíram?",
        "Qual o legado de {assunto} e como ele é lembrado hoje?"
    ],
    "filosofia": [
        "Como {assunto} se aplica ao dia a dia e qual sua relevância?",
        "Quais as críticas a {assunto} e como ele responde a elas?",
        "Qual a origem de {assunto} e como ele se desenvolveu?",
        "Quais os principais pensadores de {assunto} e suas ideias?",
        "Como {assunto} se relaciona com outras correntes filosóficas?"
    ],
    "literatura": [
        "Quais as características de {assunto} e como ele influencia a cultura?",
        "Como {assunto} se manifesta na literatura e quais seus principais expoentes?",
        "Qual a importância de {assunto} para a formação do leitor e da sociedade?",
        "Quais as principais obras de {assunto} e qual seu impacto?",
        "Como {assunto} dialoga com outras artes e com a história?"
    ],
    "economia": [
        "Como a {assunto} afeta a vida das pessoas e o desenvolvimento do país?",
        "Quais os desafios da {assunto} no Brasil e no mundo?",
        "Qual a relação entre {assunto} e bem-estar social?",
        "Como as políticas econômicas influenciam {assunto} e quais os efeitos?",
        "Quais as tendências atuais em {assunto} e os debates em torno dela?"
    ],
    "esportes": [
        "Qual a importância do {assunto} na cultura brasileira e mundial?",
        "Como o {assunto} contribui para a saúde e o bem-estar?",
        "Quais os principais eventos de {assunto} e como eles são organizados?",
        "Quem são os atletas mais famosos de {assunto} e quais suas conquistas?",
        "Como o {assunto} evoluiu ao longo do tempo e quais as novas modalidades?"
    ],
    "mitologia": [
        "Qual a influência da {assunto} na cultura atual e como ela se manifesta?",
        "Quais os personagens mais conhecidos da {assunto} e suas histórias?",
        "Como a {assunto} explica fenômenos naturais e a origem do mundo?",
        "Quais as principais lendas da {assunto} e como elas são transmitidas?",
        "Como a {assunto} se relaciona com outras mitologias e religiões?"
    ],
    "ciencias_sociais": [
        "Como a {assunto} ajuda a entender a sociedade e suas transformações?",
        "Quais as principais teorias da {assunto} e como elas explicam a realidade?",
        "Qual a importância da {assunto} na formação do cidadão crítico?",
        "Como a {assunto} se aplica a problemas contemporâneos como desigualdade e exclusão?",
        "Quais os métodos de pesquisa da {assunto} e suas principais contribuições?"
    ],
    "filmes": [
        "Qual a importância de {assunto} para o cinema e a cultura pop?",
        "Como {assunto} influenciou a indústria cinematográfica e outros filmes?",
        "Quais as principais cenas de {assunto} e seu significado?",
        "Qual a direção, roteiro e elenco de {assunto} e como eles contribuíram?",
        "Como {assunto} aborda temas sociais e políticos e qual sua mensagem?"
    ],
    "series": [
        "Qual a importância de {assunto} para a TV e a cultura contemporânea?",
        "Como {assunto} evoluiu ao longo das temporadas e quais os arcos dos personagens?",
        "Quais os personagens mais marcantes de {assunto} e suas histórias?",
        "Como {assunto} aborda questões sociais e psicológicas?",
        "Qual o impacto de {assunto} na audiência e na crítica especializada?"
    ],
    "livros": [
        "Qual a importância de {assunto} na literatura e para a cultura?",
        "Como {assunto} reflete a sociedade e os valores da época?",
        "Quais as principais mensagens de {assunto} e como elas são transmitidas?",
        "Quem escreveu {assunto} e qual sua trajetória literária?",
        "Como {assunto} dialoga com outras obras do mesmo autor ou gênero?"
    ],
    "personagens_ficticios": [
        "Qual o papel de {assunto} na obra e como ele se desenvolve?",
        "Como {assunto} representa valores humanos e universais?",
        "Quais as principais características de {assunto} e suas motivações?",
        "Como {assunto} influenciou a cultura popular e outros personagens?",
        "Qual a importância de {assunto} para a trama e para o público?"
    ],
    "tecnologias_emergentes": [
        "Como {assunto} vai mudar o mundo e quais suas aplicações?",
        "Quais os desafios éticos de {assunto} e como enfrentá-los?",
        "Qual o potencial de {assunto} para o futuro e quais as barreiras?",
        "Como {assunto} se integra a outras tecnologias e quais as sinergias?",
        "Quem está desenvolvendo {assunto} e quais os principais projetos?"
    ],
    "eventos_historicos_brasil": [
        "Qual o impacto de {assunto} na história do Brasil e na identidade nacional?",
        "Como {assunto} moldou a sociedade brasileira e suas instituições?",
        "Quais as lições de {assunto} para o presente e o futuro?",
        "Quem foram os protagonistas de {assunto} e quais suas motivações?",
        "Como {assunto} é lembrado e celebrado na memória coletiva?"
    ],
    "mito_brasileiro": [
        "Explique a lenda de {assunto} e seu significado.",
        "Como a figura de {assunto} é representada na cultura popular?",
        "Qual a origem do mito de {assunto} e como ele é transmitido?",
        "Qual a relação de {assunto} com a natureza e os costumes locais?"
    ],
    "cientista_brasileiro": [
        "Qual a principal descoberta de {assunto} e seu impacto?",
        "Como a trajetória de {assunto} contribuiu para o avanço da ciência no Brasil?",
        "Quais os desafios enfrentados por {assunto} em sua carreira?",
        "O que motivou {assunto} a se dedicar à ciência?"
    ],
    "ponto_turistico": [
        "Por que {assunto} é considerado um ponto turístico imperdível?",
        "Qual a história por trás de {assunto} e o que ele representa?",
        "Como visitar {assunto} e quais os melhores períodos?",
        "Quais as belezas naturais ou arquitetônicas de {assunto}?"
    ],
    "festa_popular": [
        "Qual a origem da festa de {assunto} e como ela é celebrada?",
        "O que a festa de {assunto} representa para a comunidade?",
        "Como a festa de {assunto} preserva tradições culturais?",
        "Quais são os pratos típicos e danças da festa de {assunto}?"
    ],
    "esporte_modalidade": [
        "Explique a história e as principais regras de {assunto}.",
        "Como {assunto} evoluiu e quais suas principais competições?",
        "Quais são os benefícios de praticar {assunto}?",
    ],
    "jogo": [
        "Descreva o jogo {assunto} e suas mecânicas principais.",
        "Qual a origem e evolução de {assunto}?",
        "Por que {assunto} é considerado um jogo clássico?",
    ],
    "marca": [
        "Fale sobre a história e os produtos da marca {assunto}.",
        "Como {assunto} se tornou uma marca global?",
        "Qual a filosofia da marca {assunto}?",
    ],
    "ferramenta": [
        "Explique para que serve {assunto} e como usá-la corretamente.",
        "Quais os cuidados necessários com {assunto}?",
        "Como escolher a melhor {assunto} para cada tarefa?",
    ],
    "conceito_filosofico": [
        "O que é {assunto} e qual sua importância para a filosofia?",
        "Como {assunto} se relaciona com a vida cotidiana?",
        "Quais os principais pensadores que trataram de {assunto}?",
    ],
    "conceito_cientifico": [
        "Explique o conceito de {assunto} de forma simples.",
        "Qual a importância de {assunto} para a ciência moderna?",
        "Como {assunto} impacta a tecnologia e a sociedade?",
    ],
}

# ============================================================================
# 4. UTILIDADES GERAIS
# ============================================================================
def carregar_json(caminho, padrao):
    if not os.path.exists(caminho):
        return padrao
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return padrao

def salvar_json(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def normalizar_chave(texto):
    texto = texto.lower().strip()
    texto = re.sub(r"[^\w\sáàâãéêíóôõúçñ-]", "", texto, flags=re.UNICODE)
    texto = re.sub(r"\s+", " ", texto)
    return texto

def hash_texto(texto):
    return hashlib.sha256(normalizar_chave(texto).encode('utf-8')).hexdigest()

def exibir_categoria(titulo, lista):
    print(f"\n{titulo}")
    for item in lista[:12]:
        print(f"   - {item}")
    if len(lista) > 12:
        print(f"   ... e mais {len(lista)-12} itens")

def limpar_texto(texto):
    texto = re.sub(r"https?://\S+|www\.\S+", "", texto)
    texto = re.sub(r"\S+@\S+\.\S+", "", texto)
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()

# ============================================================================
# 5. SISTEMA DE CACHE PERSISTENTE (com expiração)
# ============================================================================
def carregar_cache_temas() -> set:
    if os.path.exists(ARQUIVO_CACHE_TEMAS):
        try:
            with open(ARQUIVO_CACHE_TEMAS, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return set(dados)
                elif isinstance(dados, dict):
                    return set(dados.keys())
        except:
            return set()
    return set()

def salvar_cache_temas(cache: set):
    with open(ARQUIVO_CACHE_TEMAS, 'w', encoding='utf-8') as f:
        json.dump(list(cache), f, ensure_ascii=False, indent=2)

class CacheRespostas:
    def __init__(self, arquivo=ARQUIVO_CACHE_RESPOSTAS, expiracao_dias=CACHE_EXPIRATION_DAYS):
        self.arquivo = arquivo
        self.expiracao = timedelta(days=expiracao_dias)
        self.dados = self._carregar()
        self._limpar_expirados()

    def _carregar(self):
        if os.path.exists(self.arquivo):
            try:
                with open(self.arquivo, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _salvar(self):
        with open(self.arquivo, 'w', encoding='utf-8') as f:
            json.dump(self.dados, f, ensure_ascii=False, indent=2)

    def _limpar_expirados(self):
        agora = datetime.now()
        expirados = []
        for chave, registro in self.dados.items():
            data_str = registro.get("data", "1970-01-01")
            try:
                data = datetime.fromisoformat(data_str)
                if agora - data > self.expiracao:
                    expirados.append(chave)
            except:
                expirados.append(chave)
        for chave in expirados:
            del self.dados[chave]
        if expirados:
            self._salvar()

    def contem(self, chave: str) -> bool:
        return chave in self.dados

    def obter(self, chave: str) -> Optional[str]:
        if chave in self.dados:
            return self.dados[chave].get("texto")
        return None

    def armazenar(self, chave: str, texto: str):
        self.dados[chave] = {
            "texto": texto,
            "data": datetime.now().isoformat()
        }
        self._salvar()

CACHE_RESPOSTAS = CacheRespostas()
CACHE_TEMAS_GLOBAIS = carregar_cache_temas()

def tema_ja_usado_global(tema: str) -> bool:
    return hash_texto(tema) in CACHE_TEMAS_GLOBAIS

def registrar_tema_global(tema: str):
    CACHE_TEMAS_GLOBAIS.add(hash_texto(tema))
    salvar_cache_temas(CACHE_TEMAS_GLOBAIS)

# ============================================================================
# 6. HISTÓRICO E CONTROLE DE REPETIÇÃO
# ============================================================================
HISTORICO_TEMAS = deque(carregar_json(ARQUIVO_HISTORICO_TEMAS, []), maxlen=MAX_ITENS_REPETICAO_RECENTE)
HISTORICO_RESPOSTAS = deque(carregar_json(ARQUIVO_HISTORICO_RESPOSTAS, []), maxlen=MAX_ITENS_REPETICAO_RECENTE)
CONTAGEM_CATEGORIAS = Counter(carregar_json(ARQUIVO_CONTAGEM_CATEGORIAS, {}))
CONTAGEM_ASSUNTOS = Counter(carregar_json(ARQUIVO_CONTAGEM_ASSUNTOS, {}))

def persistir_estados():
    salvar_json(ARQUIVO_HISTORICO_TEMAS, list(HISTORICO_TEMAS))
    salvar_json(ARQUIVO_HISTORICO_RESPOSTAS, list(HISTORICO_RESPOSTAS))
    salvar_json(ARQUIVO_CONTAGEM_CATEGORIAS, dict(CONTAGEM_CATEGORIAS))
    salvar_json(ARQUIVO_CONTAGEM_ASSUNTOS, dict(CONTAGEM_ASSUNTOS))

def tema_ja_usado(pergunta):
    return hash_texto(pergunta) in HISTORICO_TEMAS

def resposta_ja_usada(resposta):
    return hash_texto(resposta) in HISTORICO_RESPOSTAS

def registrar_no_historico(pergunta, resposta, categoria, assunto):
    HISTORICO_TEMAS.append(hash_texto(pergunta))
    CONTAGEM_CATEGORIAS[categoria] += 1
    CONTAGEM_ASSUNTOS[normalizar_chave(assunto)] += 1
    if resposta:
        HISTORICO_RESPOSTAS.append(hash_texto(resposta))
    persistir_estados()

# ============================================================================
# 7. GERAÇÃO DE PERGUNTAS (MODIFICADA)
# ============================================================================
PERGUNTA_TEMPLATES = [
    "Explique detalhadamente {assunto}",
    "Compare {assunto} com {outro} e destaque as diferenças",
    "Quais são as principais vantagens e desvantagens de {assunto}?",
    "Quais são as limitações de {assunto} e como superá-las?",
    "Como {assunto} evoluiu ao longo do tempo?",
    "Em quais situações práticas {assunto} é aplicado?",
    "O que aconteceria se {assunto} não existisse?",
    "Quais são os principais desafios relacionados a {assunto} e como enfrentá-los?",
    "Como funciona {assunto} em detalhes?",
    "Por que {assunto} é importante e qual seu impacto na sociedade?",
    "Qual a diferença entre {assunto} e {outro}?",
    "Como seria o mundo sem {assunto}?",
    "Quais as consequências de {assunto} para o futuro?",
    "Como {assunto} se relaciona com {outro}?",
    "Dê exemplos práticos e concretos de {assunto}",
    "Qual a origem histórica de {assunto}?",
    "Quem foram os principais responsáveis por {assunto}?",
    "Como {assunto} é visto pela ciência moderna?",
    "Quais as principais controvérsias em torno de {assunto}?",
    "Como {assunto} afeta o dia a dia das pessoas?",
]

def escolher_categoria_balanceada():
    categorias = list(CATEGORIAS_LISTAS.keys())
    if not categorias:
        return random.choice(list(PREFIXOS_POR_CATEGORIA.keys()))
    menor_contagem = min(CONTAGEM_CATEGORIAS.get(cat, 0) for cat in categorias)
    candidatas = [cat for cat in categorias if CONTAGEM_CATEGORIAS.get(cat, 0) == menor_contagem]
    return random.choice(candidatas)

def escolher_assunto(categoria):
    lista = CATEGORIAS_LISTAS.get(categoria, [])
    if not lista:
        return "tema"
    candidatos = sorted(lista, key=lambda item: CONTAGEM_ASSUNTOS.get(normalizar_chave(item), 0))
    menor = CONTAGEM_ASSUNTOS.get(normalizar_chave(candidatos[0]), 0)
    melhores = [item for item in candidatos if CONTAGEM_ASSUNTOS.get(normalizar_chave(item), 0) == menor]
    return random.choice(melhores)

def escolher_categoria_do_grupo(grupo):
    categorias = GRUPOS_CATEGORIAS.get(grupo, [])
    if not categorias:
        return random.choice(list(CATEGORIAS_LISTAS.keys()))
    return random.choice(categorias)

def gerar_pergunta_combinada(assunto1, assunto2):
    templates = [
        "Qual a relação entre {a1} e {a2}? Explique.",
        "Como {a1} influencia {a2}?",
        "Quais as diferenças fundamentais entre {a1} e {a2}?",
        "O que {a1} tem em comum com {a2}?",
        "Explique a importância de {a1} no contexto de {a2}.",
        "Como a evolução de {a1} afetou {a2}?",
        "Compare detalhadamente {a1} e {a2}.",
        "Qual o papel de {a1} na história de {a2}?",
        "De que forma {a1} se relaciona com {a2} no mundo atual?",
        "O que podemos aprender com a relação entre {a1} e {a2}?",
        "Como {a1} e {a2} se complementam?",
        "Por que {a1} é considerado importante para {a2}?",
        "Que impacto {a1} teve sobre {a2} ao longo do tempo?",
        "Em que medida {a1} é semelhante a {a2}?",
        "Como {a1} pode ser usado para entender melhor {a2}?",
    ]
    template = random.choice(templates)
    pergunta = template.format(a1=assunto1, a2=assunto2)
    if not pergunta.endswith("?"):
        pergunta += "?"
    return pergunta

# <--- FUNÇÃO MODIFICADA
def gerar_pergunta_simples():
    categoria = escolher_categoria_balanceada()
    assunto = escolher_assunto(categoria)
    
    # Usa a nova lógica de classificação + intenção
    intencao, prefixo = escolher_intencao_e_prefixo(categoria)
    
    # Monta a pergunta
    if prefixo.endswith("?") or prefixo in ["O que é", "Defina", "Explique", "Resuma",
                                            "Fale mais sobre", "Conte mais sobre", "Gostaria de conhecer", "Quero conhecer"]:
        pergunta = f"{prefixo} {assunto}?"
    else:
        pergunta = f"{prefixo} {assunto}?"
        if not pergunta.endswith("?"):
            pergunta += "?"
    
    # Se for uma pergunta comparativa (caso o prefixo sugira comparação)
    if any(p in prefixo.lower() for p in ["compar", "difer", "relaç", "semelhan"]):
        outro = escolher_assunto(categoria)
        tent = 0
        while outro == assunto and tent < 10:
            outro = escolher_assunto(categoria)
            tent += 1
        pergunta = f"{prefixo} {assunto} e {outro}?"
    
    # Validações
    pergunta = pergunta[0].upper() + pergunta[1:]
    if not pergunta.endswith("?"):
        pergunta += "?"
    pergunta = re.sub(r"\s+", " ", pergunta).strip()
    if len(pergunta.split()) < 4:
        return None, None, None
    if tema_ja_usado(pergunta) or tema_ja_usado_global(pergunta):
        return None, None, None
    return pergunta, categoria, assunto
# <--- FIM DA MODIFICAÇÃO

def gerar_pergunta_dinamica_v5():
    for _ in range(40):
        if random.random() < 0.30:
            grupo = random.choice(list(GRUPOS_CATEGORIAS.keys()))
            cat1 = escolher_categoria_do_grupo(grupo)
            cat2 = escolher_categoria_do_grupo(grupo)
            assunto1 = escolher_assunto(cat1)
            assunto2 = escolher_assunto(cat2)
            tentativas = 0
            while assunto2 == assunto1 and tentativas < 20:
                assunto2 = escolher_assunto(cat2)
                tentativas += 1
            if assunto1 != assunto2:
                pergunta = gerar_pergunta_combinada(assunto1, assunto2)
                if not tema_ja_usado(pergunta) and not tema_ja_usado_global(pergunta):
                    return pergunta, "combinada", f"{assunto1}|{assunto2}"
        pergunta, categoria, assunto = gerar_pergunta_simples()
        if pergunta:
            return pergunta, categoria, assunto
    return "Explique a importância da tecnologia para a sociedade moderna.", "conceito", "tecnologia"

# ============================================================================
# 8. CARREGAR .env E CLIENTE (com suporte a Ollama)
# ============================================================================
load_dotenv()
API_KEY = os.getenv("DEEPSEEK_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-flash")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
USE_OLLAMA = os.getenv("USE_OLLAMA", "false").lower() == "true"
MAX_COST_USD = float(os.getenv("MAX_COST_USD", str(MAX_COST_USD)))
DELAY_SECONDS = float(os.getenv("DELAY_SECONDS", str(DELAY_SECONDS)))

if not API_KEY and not USE_OLLAMA:
    print("❌ ERRO: DEEPSEEK_API_KEY não encontrada no arquivo .env e USE_OLLAMA não está ativo.")
    sys.exit(1)

if USE_OLLAMA:
    print(f"🔧 Usando modelo local Ollama em {OLLAMA_URL}")
    import requests
    def ollama_generate(prompt, max_tokens=512, temperature=0.7):
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature
            }
        }
        try:
            response = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=120)
            if response.status_code == 200:
                data = response.json()
                return data.get("response", ""), 0, 0, None
            else:
                return "", 0, 0, None
        except Exception as e:
            print(f"⚠️ Erro no Ollama: {e}")
            return "", 0, 0, None
else:
    client = OpenAI(
        api_key=API_KEY,
        base_url="https://api.deepseek.com/v1",
        timeout=httpx.Timeout(240.0, connect=30.0)
    )

# ============================================================================
# 9. CONTROLE DE GASTOS
# ============================================================================
def carregar_gastos():
    if os.path.exists(ARQUIVO_GASTOS):
        with open(ARQUIVO_GASTOS, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except:
                return {"total_gasto": 0.0, "historico": []}
    return {"total_gasto": 0.0, "historico": []}

def salvar_gastos(dados):
    with open(ARQUIVO_GASTOS, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def registrar_gasto(custo, tokens_entrada, tokens_saida, tema, tipo):
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
    dados = carregar_gastos()
    if dados["total_gasto"] >= MAX_COST_USD:
        print(f"⚠️ Limite de gastos atingido: ${MAX_COST_USD:.2f}")
        return False
    return True

# ============================================================================
# 10. VALIDAÇÃO DE QUALIDADE (expandida)
# ============================================================================
VAGAS = {"sim","não","nao","talvez","ok","claro","verdade","mentira","não sei","nao sei","não sei responder","talvez sim","talvez não","depende"}
FRASES_FRACAS = {
    "como ia","sou uma ia","não tenho certeza","não posso","não sei","não tenho informação",
    "a resposta é","resposta:","pergunta:","espero ter ajudado","qualquer dúvida",
    "estou aqui para ajudar","fique à vontade","precisa de mais alguma coisa"
}
PADROES_INVALIDOS = [
    r'<[^>]+>',
    r'```[\s\S]*?```',
    r'`[^`]+`',
    r'\{.*\}',
    r'<\\?[a-zA-Z]+[^>]*>',
    r'[#*_]{3,}',
    r'\[.*\]\(.*\)',
    r'[\u2600-\u27BF]',
    r'https?://\S+',
]
PALAVRAS_REPETIDAS_LIMITE = 0.4

def detectar_truncamento(texto, finish_reason=None):
    if finish_reason in {"length", "max_tokens"}:
        return True
    texto = texto.strip()
    if not texto or texto.endswith("...") or len(texto) < 5:
        return True
    return False

def detectar_html_markdown(texto):
    for padrao in PADROES_INVALIDOS:
        if re.search(padrao, texto, re.IGNORECASE | re.DOTALL):
            return True
    return False

def detectar_lista_excessiva(texto):
    linhas = texto.split('\n')
    count_lista = 0
    for linha in linhas:
        if re.match(r'^[\s]*[-*•]\s+', linha.strip()) or re.match(r'^[\s]*\d+[\.\)]\s+', linha.strip()):
            count_lista += 1
    linhas_validas = [l for l in linhas if l.strip()]
    if not linhas_validas:
        return False
    return (count_lista / len(linhas_validas)) > 0.5

def detectar_repeticao_excessiva(texto):
    palavras = texto.split()
    if len(palavras) < 10:
        return False
    freq = Counter(palavras)
    max_freq = max(freq.values())
    return (max_freq / len(palavras)) > PALAVRAS_REPETIDAS_LIMITE

def detectar_resposta_genérica(texto):
    texto_lower = texto.lower()
    genericos = [
        "depende de vários fatores", "cada caso é um caso", "é importante considerar",
        "não existe resposta certa", "tudo depende", "é relativo",
        "não tenho informações suficientes", "não posso afirmar com certeza"
    ]
    for g in genericos:
        if g in texto_lower:
            return True
    return False

def detectar_muleta_ia(texto):
    muletas = [
        "como assistente", "sou uma inteligência artificial", "como modelo de linguagem",
        "não tenho opinião própria", "não tenho sentimentos", "não posso sentir",
        "sou um programa", "não tenho consciência", "não sou humano",
        "não possuo emoções", "não tenho crenças"
    ]
    texto_lower = texto.lower()
    for m in muletas:
        if m in texto_lower:
            return True
    return False

def detectar_plagio(texto, limiar=0.3):
    frases = re.split(r'[.!?]+', texto)
    frases = [f.strip() for f in frases if len(f.split()) > 5]
    if len(frases) < 2:
        return False
    hashes = [hash_texto(f) for f in frases]
    freq = Counter(hashes)
    if max(freq.values()) / len(frases) > limiar:
        return True
    return False

def avaliar_qualidade(texto, tipo="dicionario", finish_reason=None):
    if texto is None:
        return False, "texto é None"
    texto = limpar_texto(texto)
    if not texto:
        return False, "texto vazio"
    texto_norm = normalizar_chave(texto)
    palavras = texto_norm.split()

    if detectar_truncamento(texto, finish_reason):
        return False, "resposta truncada"
    if texto_norm in VAGAS:
        return False, f"resposta vaga: '{texto}'"
    for trecho in FRASES_FRACAS:
        if trecho in texto_norm:
            return False, f"resposta fraca: '{texto[:60]}'"
    if "��" in texto:
        return False, "caracteres estranhos"
    if detectar_html_markdown(texto):
        return False, "contém HTML/Markdown/JSON/XML/código"
    if detectar_lista_excessiva(texto):
        return False, "lista excessiva"
    if detectar_repeticao_excessiva(texto):
        return False, "repetição excessiva de palavras"
    if detectar_resposta_genérica(texto):
        return False, "resposta genérica (ex: 'depende')"
    if detectar_muleta_ia(texto):
        return False, "contém frases típicas de IA"
    if detectar_plagio(texto):
        return False, "suspeita de plágio (frases repetidas)"

    if tipo == "dicionario":
        if len(palavras) < 8:
            return False, f"muito curta: {len(palavras)} palavras"
        if len(palavras) > 100:
            return False, f"muito longa: {len(palavras)} palavras"
    elif tipo in ["pergunta_resposta", "artigo", "conto", "dialogo_profundo", "explicacao",
                  "entrevista", "debate", "tutorial", "resenha", "relatorio", "ensaio"]:
        if len(palavras) < 120:
            return False, f"texto muito curto: {len(palavras)} palavras"
        if len(palavras) > 1200:
            return False, f"texto muito longo: {len(palavras)} palavras"
    elif tipo == "resumo":
        if len(palavras) < 60:
            return False, f"resumo muito curto: {len(palavras)} palavras"
        if len(palavras) > 400:
            return False, f"resumo muito longo: {len(palavras)} palavras"
    elif tipo == "conversa":
        if len(palavras) < 100:
            return False, f"conversa curta: {len(palavras)} palavras"
    elif tipo == "poema":
        if len(palavras) < 30:
            return False, f"poema muito curto: {len(palavras)} palavras"
        if len(palavras) > 200:
            return False, f"poema muito longo: {len(palavras)} palavras"
    elif tipo == "carta":
        if len(palavras) < 80:
            return False, f"carta muito curta: {len(palavras)} palavras"
        if len(palavras) > 500:
            return False, f"carta muito longa: {len(palavras)} palavras"
    elif tipo == "receita":
        if len(palavras) < 50:
            return False, f"receita muito curta: {len(palavras)} palavras"
        if len(palavras) > 300:
            return False, f"receita muito longa: {len(palavras)} palavras"
    elif tipo == "dica":
        if len(palavras) < 30:
            return False, f"dica muito curta: {len(palavras)} palavras"
        if len(palavras) > 150:
            return False, f"dica muito longa: {len(palavras)} palavras"
    return True, "OK"

# ============================================================================
# 11. SALVAMENTO
# ============================================================================
def decidir_pasta_saida(tokens_saida):
    return PASTA_DADOS_CURTOS if tokens_saida <= LIMITE_PALAVRAS_CURTOS else PASTA_DADOS_LONGOS

def salvar_texto(texto, prefixo, indice, pasta):
    os.makedirs(pasta, exist_ok=True)
    nome = f"{prefixo}_{indice:06d}.txt"
    caminho = os.path.join(pasta, nome)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(texto)
    return caminho

def salvar_descarte(texto, prefixo, motivo, indice):
    os.makedirs(PASTA_DESCARTES, exist_ok=True)
    nome = f"{prefixo}_descarte_{indice:06d}.txt"
    caminho = os.path.join(PASTA_DESCARTES, nome)
    with open(caminho, 'w', encoding='utf-8') as f:
        f.write(f"MOTIVO DO DESCARTE: {motivo}\n\n--- TEXTO GERADO ---\n\n{texto if texto else '(vazio)'}")
    return caminho

def salvar_metadados(metadados):
    historico = carregar_json(ARQUIVO_METADADOS, [])
    historico.append(metadados)
    salvar_json(ARQUIVO_METADADOS, historico)

# ============================================================================
# 12. PROMPTS (REFOÇADOS E NOVOS) – mantidos
# ============================================================================
def gerar_prompt_conversa(tema):
    return f"""Crie uma conversa natural em português brasileiro entre duas pessoas sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. Seja coloquial e realista, como uma conversa de verdade.
2. Tenha pelo menos 6 turnos (Pessoa 1 e Pessoa 2 se alternando).
3. Cada fala deve ter pelo menos 2 frases completas.
4. O texto total deve ter NO MÍNIMO 250 palavras.
5. Use expressões típicas do português do Brasil (gírias, contrações).
6. NÃO use Markdown, HTML, listas, emojis ou títulos.
7. NÃO use frases como "espero ter ajudado" ou "qualquer dúvida estou aqui".
8. NÃO repita a pergunta. Responda diretamente.
9. NÃO inclua introduções artificiais do tipo "como assistente" ou "como IA".
10. Escreva APENAS os diálogos, sem comentários adicionais.

FORMATO:
Pessoa 1: [fala]
Pessoa 2: [fala]
Pessoa 1: [fala]
... (pelo menos 6 turnos no total)"""

def gerar_prompt_pergunta_resposta(tema):
    return f"""Crie uma pergunta instigante e uma resposta detalhada em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. A resposta deve ter entre 5 e 10 parágrafos (NO MÍNIMO 400 palavras).
2. Inclua exemplos concretos, dados ou referências históricas sempre que possível.
3. Use conectivos (portanto, por exemplo, além disso, em contrapartida) para dar fluidez.
4. Conclua com uma frase que sintetize a importância do tema.
5. NÃO use Markdown, HTML, listas, emojis ou títulos.
6. NÃO use frases como "espero ter ajudado" ou "qualquer dúvida estou aqui".
7. NÃO repita a pergunta. Responda diretamente.
8. NÃO inclua introduções artificiais do tipo "como assistente" ou "como IA".
9. Escreva APENAS a pergunta e a resposta, sem comentários adicionais.

FORMATO:
Pergunta: [pergunta]
Resposta: [resposta desenvolvida (mínimo 400 palavras)]"""

def gerar_prompt_iteracao(tema):
    return f"""Crie um diálogo de 5 a 8 turnos em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. Simule uma conversa natural, onde cada fala tem pelo menos uma frase completa.
2. Inclua uma pergunta inicial, uma resposta informativa, e um acompanhamento (dúvida, curiosidade ou comentário).
3. O texto total deve ter NO MÍNIMO 200 palavras.
4. NÃO use Markdown, HTML, listas, emojis ou títulos.
5. NÃO use frases como "espero ter ajudado" ou "qualquer dúvida estou aqui".
6. NÃO repita a pergunta. Responda diretamente.
7. NÃO inclua introduções artificiais do tipo "como assistente" ou "como IA".
8. Escreva APENAS os diálogos, sem comentários adicionais.

FORMATO:
Pessoa: [fala]
Outra: [fala]
Pessoa: [fala]
... (até 8 turnos)"""

def gerar_prompt_dicionario(pergunta):
    return f"""Responda à pergunta em português brasileiro com uma resposta direta e informativa (mínimo 30 palavras).

REGRAS OBRIGATÓRIAS:
1. Seja objetivo, mas forneça contexto suficiente.
2. NÃO repita a pergunta.
3. NÃO use introduções como "A resposta é" ou "Isso significa que".
4. NÃO use Markdown, HTML, listas, emojis ou títulos.
5. NÃO use frases como "espero ter ajudado".
6. NÃO inclua "como assistente" ou "como IA".
7. Escreva APENAS a resposta, sem comentários adicionais.

Pergunta: {pergunta}
Resposta:"""

def gerar_prompt_artigo(tema):
    return f"""Escreva um texto corrido em português brasileiro sobre o tema: {tema}.

REGRAS OBRIGATÓRIAS:
1. O texto deve ter entre 500 e 900 palavras, estruturado em:
   - Introdução (2-3 parágrafos): apresente o tema de forma geral.
   - Desenvolvimento (4-6 parágrafos): explique os principais aspectos, com exemplos, dados ou referências.
   - Conclusão (2-3 parágrafos): finalize com uma reflexão ou síntese.
2. Use linguagem formal, conectivos adequados (portanto, além disso, por exemplo, etc.).
3. NÃO use tópicos, marcadores, listas ou títulos. Escreva em parágrafos contínuos.
4. NÃO use Markdown, HTML, emojis ou código.
5. NÃO use frases como "espero ter ajudado" ou "qualquer dúvida estou aqui".
6. NÃO inclua "como assistente" ou "como IA".
7. Escreva APENAS o texto, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_conto(tema):
    return f"""Escreva um conto (história curta) em português brasileiro sobre o tema: {tema}.

REGRAS OBRIGATÓRIAS:
1. O conto deve ter entre 400 e 700 palavras, com:
   - Personagens (pelo menos um principal).
   - Enredo: começo, desenvolvimento e desfecho.
   - Um toque de criatividade e imaginação.
2. Narrativa em terceira pessoa, com diálogos se necessário.
3. NÃO use Markdown, HTML, listas, emojis ou títulos.
4. NÃO use frases como "espero ter ajudado".
5. NÃO inclua "como assistente" ou "como IA".
6. Escreva APENAS o conto, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_dialogo_profundo(tema):
    return f"""Crie um diálogo profundo de 10 a 15 turnos em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. Mostre uma conversa onde as perguntas e respostas se aprofundam no tema, explorando diferentes ângulos.
2. Cada fala deve ter pelo menos 2 frases completas.
3. Inclua uma pergunta inicial, respostas elaboradas, e perguntas de acompanhamento que levam a conversa a um nível mais reflexivo.
4. O texto total deve ter NO MÍNIMO 350 palavras.
5. NÃO use Markdown, HTML, listas, emojis ou títulos.
6. NÃO use frases como "espero ter ajudado" ou "qualquer dúvida estou aqui".
7. NÃO repita a pergunta. Responda diretamente.
8. NÃO inclua introduções artificiais do tipo "como assistente" ou "como IA".
9. Escreva APENAS os diálogos, sem comentários adicionais.
10. Mantenha o formato:
    Pessoa: [fala]
    Outra: [fala]
    ... (10 a 15 turnos)"""

def gerar_prompt_explicacao(tema):
    return f"""Crie uma explicação detalhada e clara em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. Estruture em 5 a 8 parágrafos.
2. Use analogias ou exemplos para facilitar o entendimento.
3. Explique o conceito como se fosse para um leigo, mas sem perder a precisão.
4. O texto deve ter entre 350 e 600 palavras.
5. NÃO use Markdown, HTML, listas, emojis ou títulos.
6. NÃO use frases como "espero ter ajudado" ou "qualquer dúvida estou aqui".
7. NÃO repita a pergunta. Responda diretamente.
8. NÃO inclua "como assistente" ou "como IA".
9. Escreva APENAS a explicação, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_resumo(tema):
    return f"""Faça um resumo conciso e informativo em português brasileiro sobre o tema: {tema}.

REGRAS OBRIGATÓRIAS:
1. O resumo deve ter entre 200 e 400 palavras.
2. Capture os pontos principais do tema.
3. Seja objetivo, direto e sem rodeios.
4. Inclua uma frase final que sintetize a importância do tema.
5. NÃO use Markdown, HTML, listas, emojis ou títulos.
6. NÃO use frases como "espero ter ajudado".
7. NÃO repita a pergunta.
8. NÃO inclua "como assistente" ou "como IA".
9. Escreva APENAS o resumo, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_poema(tema):
    return f"""Escreva um poema em português brasileiro sobre o tema: {tema}.

REGRAS OBRIGATÓRIAS:
1. O poema deve ter entre 10 e 20 versos, com métrica livre ou rimas.
2. Use linguagem poética, com metáforas e imagens.
3. O poema deve ter um título.
4. NÃO use Markdown, HTML, listas ou emojis.
5. NÃO inclua introduções artificiais.
6. Escreva APENAS o poema, sem comentários adicionais.

Título: [título]
Versos:
[verso1]
[verso2]
..."""

def gerar_prompt_carta(tema):
    return f"""Escreva uma carta em português brasileiro sobre o tema: {tema}.

REGRAS OBRIGATÓRIAS:
1. A carta deve ser formal ou informal, conforme o contexto.
2. Deve ter entre 200 e 400 palavras.
3. Inclua saudação, desenvolvimento e despedida.
4. Use estrutura típica de carta (local, data, corpo, assinatura).
5. NÃO use Markdown, HTML, listas ou emojis.
6. NÃO inclua introduções artificiais.
7. Escreva APENAS a carta, sem comentários adicionais.

Local e data: [local], [data]
Destinatário: [nome]
Assunto: [assunto]
Corpo da carta:
..."""

def gerar_prompt_entrevista(tema):
    return f"""Crie uma entrevista em português brasileiro sobre o tema: {tema}.

REGRAS OBRIGATÓRIAS:
1. A entrevista deve ter 5 a 8 perguntas e respostas.
2. O entrevistador deve fazer perguntas pertinentes e o entrevistado responder de forma elaborada.
3. Cada resposta deve ter pelo menos 2 frases.
4. O texto total deve ter NO MÍNIMO 300 palavras.
5. NÃO use Markdown, HTML, listas, emojis ou títulos.
6. NÃO use frases como "espero ter ajudado".
7. NÃO inclua "como assistente" ou "como IA".
8. Escreva APENAS a entrevista, sem comentários adicionais.

FORMATO:
Entrevistador: [pergunta]
Entrevistado: [resposta]
... (até 8 perguntas)"""

def gerar_prompt_debate(tema):
    return f"""Crie um debate em português brasileiro sobre o tema: {tema}.

REGRAS OBRIGATÓRIAS:
1. O debate deve apresentar argumentos a favor e contra o tema.
2. Pelo menos 4 turnos de fala (Argumentador1 e Argumentador2).
3. Cada fala deve ter pelo menos 3 frases.
4. O texto total deve ter NO MÍNIMO 350 palavras.
5. NÃO use Markdown, HTML, listas, emojis ou títulos.
6. NÃO use frases como "espero ter ajudado".
7. NÃO inclua "como assistente" ou "como IA".
8. Escreva APENAS o debate, sem comentários adicionais.

FORMATO:
Argumentador1: [argumento]
Argumentador2: [contra-argumento]
... (pelo menos 4 turnos)"""

# Novos prompts
def gerar_prompt_tutorial(tema):
    return f"""Crie um tutorial passo a passo em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. O tutorial deve ter entre 400 e 700 palavras.
2. Estruture em etapas numeradas (Passo 1, Passo 2, ...).
3. Inclua dicas e alertas quando necessário.
4. Use linguagem clara e objetiva.
5. NÃO use Markdown, HTML, emojis ou códigos excessivos.
6. NÃO inclua "como assistente" ou "como IA".
7. Escreva APENAS o tutorial, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_resenha(tema):
    return f"""Escreva uma resenha crítica em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. A resenha deve ter entre 400 e 700 palavras.
2. Apresente uma introdução, desenvolvimento (análise) e conclusão.
3. Dê sua opinião fundamentada, com argumentos.
4. NÃO use Markdown, HTML, listas ou emojis.
5. NÃO inclua "como assistente" ou "como IA".
6. Escreva APENAS a resenha, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_relatorio(tema):
    return f"""Crie um relatório técnico em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. O relatório deve ter entre 500 e 800 palavras.
2. Estruture em: Introdução, Metodologia, Resultados, Discussão e Conclusão.
3. Use linguagem formal e objetiva.
4. Inclua dados hipotéticos ou referências, se pertinente.
5. NÃO use Markdown, HTML, emojis ou listas extensas.
6. NÃO inclua "como assistente" ou "como IA".
7. Escreva APENAS o relatório, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_ensaio(tema):
    return f"""Escreva um ensaio reflexivo em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. O ensaio deve ter entre 500 e 800 palavras.
2. Apresente uma tese, argumentação e conclusão.
3. Seja crítico e analítico, com fluência estilística.
4. NÃO use Markdown, HTML, listas ou emojis.
5. NÃO inclua "como assistente" ou "como IA".
6. Escreva APENAS o ensaio, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_cronica(tema):
    return f"""Escreva uma crônica em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. A crônica deve ter entre 300 e 500 palavras.
2. Seja um relato pessoal, poético ou humorístico, com olhar crítico sobre o cotidiano.
3. Use linguagem coloquial e envolvente.
4. NÃO use Markdown, HTML, listas ou emojis.
5. NÃO inclua "como assistente" ou "como IA".
6. Escreva APENAS a crônica, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_receita(tema):
    return f"""Crie uma receita culinária em português brasileiro com o tema: {tema}.

REGRAS OBRIGATÓRIAS:
1. A receita deve ter entre 150 e 300 palavras.
2. Inclua: nome do prato, ingredientes, modo de preparo, rendimento e tempo de preparo.
3. Seja clara e objetiva.
4. NÃO use Markdown, HTML ou emojis.
5. NÃO inclua "como assistente" ou "como IA".
6. Escreva APENAS a receita, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt_dica(tema):
    return f"""Dê uma dica prática e útil em português brasileiro sobre: {tema}.

REGRAS OBRIGATÓRIAS:
1. A dica deve ter entre 50 e 150 palavras.
2. Seja direta, oferecendo um conselho ou sugestão acionável.
3. Inclua um exemplo ou justificativa breve.
4. NÃO use Markdown, HTML ou emojis.
5. NÃO inclua "como assistente" ou "como IA".
6. Escreva APENAS a dica, sem comentários adicionais.

Tema: {tema}"""

def gerar_prompt(tema, tipo="dicionario", pergunta=None, max_tokens=256):
    if tipo == "conversa":
        return gerar_prompt_conversa(tema)
    elif tipo == "pergunta_resposta":
        return gerar_prompt_pergunta_resposta(tema)
    elif tipo == "iteracao":
        return gerar_prompt_iteracao(tema)
    elif tipo == "artigo":
        return gerar_prompt_artigo(tema)
    elif tipo == "conto":
        return gerar_prompt_conto(tema)
    elif tipo == "dialogo_profundo":
        return gerar_prompt_dialogo_profundo(tema)
    elif tipo == "explicacao":
        return gerar_prompt_explicacao(tema)
    elif tipo == "resumo":
        return gerar_prompt_resumo(tema)
    elif tipo == "dicionario":
        if pergunta is None:
            pergunta, _, _ = gerar_pergunta_dinamica_v5()
        return gerar_prompt_dicionario(pergunta)
    elif tipo == "poema":
        return gerar_prompt_poema(tema)
    elif tipo == "carta":
        return gerar_prompt_carta(tema)
    elif tipo == "entrevista":
        return gerar_prompt_entrevista(tema)
    elif tipo == "debate":
        return gerar_prompt_debate(tema)
    elif tipo == "tutorial":
        return gerar_prompt_tutorial(tema)
    elif tipo == "resenha":
        return gerar_prompt_resenha(tema)
    elif tipo == "relatorio":
        return gerar_prompt_relatorio(tema)
    elif tipo == "ensaio":
        return gerar_prompt_ensaio(tema)
    elif tipo == "cronica":
        return gerar_prompt_cronica(tema)
    elif tipo == "receita":
        return gerar_prompt_receita(tema)
    elif tipo == "dica":
        return gerar_prompt_dica(tema)
    else:
        return ""

# ============================================================================
# 13. FALLBACK INTELIGENTE (CORRIGIDO E EXPANDIDO)
# ============================================================================
_VERBOS = [
    "representa", "significa", "envolve", "abrange", "contempla", "engloba",
    "caracteriza", "define", "constitui", "compreende", "implica", "pressupõe"
]
_ADJETIVOS = [
    "fundamental", "essencial", "crucial", "importante", "significativo",
    "relevante", "notável", "expressivo", "considerável", "substancial"
]
_CONECTIVOS = [
    "portanto", "além disso", "em contrapartida", "por conseguinte",
    "dessa forma", "assim", "logo", "entretanto", "todavia", "contudo"
]
_EXEMPLOS = [
    "por exemplo, na área de {area}",
    "como se vê em {exemplo}",
    "a exemplo do que ocorre em {exemplo}",
    "tal como acontece em {exemplo}"
]
_AREAS = [
    "educação", "saúde", "tecnologia", "economia", "cultura",
    "meio ambiente", "política", "ciência", "arte", "esporte"
]

_fallback_cache = set()

# <--- FALLBACK MELHORADO (usa a classificação e intenção)
def _gerar_texto_variavel(tipo, tema, pergunta=None):
    """
    Fallback inteligente: classifica o tema, escolhe uma intenção de pergunta
    e gera uma pergunta/resposta (tentando a API ou usando fallback local).
    """
    global _fallback_cache
    if len(_fallback_cache) > 500:
        _fallback_cache = set(list(_fallback_cache)[-300:])
    
    # Limpa e normaliza o tema
    tema_limpo = tema.split(":")[-1].strip() if ":" in tema else tema
    pergunta_limpa = pergunta if pergunta else f"Explique {tema_limpo}"
    
    # ================================================================
    # 1. CLASSIFICAÇÃO DO ASSUNTO (usando as novas funções)
    # ================================================================
    categoria_tema = classificar_tema(tema_limpo)
    intencao, prefixo = escolher_intencao_e_prefixo(categoria_tema)
    
    # Constrói a pergunta de fallback com base na intenção
    if prefixo.endswith("?") or prefixo in ["O que é", "Defina", "Explique", "Resuma",
                                            "Fale mais sobre", "Conte mais sobre", "Gostaria de conhecer", "Quero conhecer"]:
        pergunta_fallback = f"{prefixo} {tema_limpo}?"
    else:
        pergunta_fallback = f"{prefixo} {tema_limpo}?"
        if not pergunta_fallback.endswith("?"):
            pergunta_fallback += "?"
    
    # ================================================================
    # 2. TENTAR A API UMA ÚLTIMA VEZ (COM PROMPT MELHORADO)
    # ================================================================
    if not USE_OLLAMA and client:
        try:
            prompt = f"""Responda à seguinte pergunta em português brasileiro de forma direta e informativa (mínimo 50 palavras). 
Seja objetivo e evite frases genéricas como "é muito relevante" ou "envolve diversos aspectos".

Pergunta: {pergunta_fallback}

Resposta:"""
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300,
                top_p=0.9
            )
            texto_resposta = response.choices[0].message.content if response.choices else ""
            if texto_resposta and len(texto_resposta.split()) > 10:
                texto = f"Pergunta: {pergunta_fallback}\nResposta: {texto_resposta}"
                _fallback_cache.add(hash_texto(texto))
                tokens_in = getattr(response.usage, "prompt_tokens", 0) if response.usage else 0
                tokens_out = getattr(response.usage, "completion_tokens", 0) if response.usage else 0
                custo = (tokens_in/1e6)*0.14 + (tokens_out/1e6)*0.28
                return texto, custo, tokens_in, tokens_out, "fallback_api", "fallback", None
        except Exception as e:
            pass

    # ================================================================
    # 3. FALLBACK LOCAL (SE A API FALHAR OU NÃO ESTIVER DISPONÍVEL)
    # ================================================================
    respostas_base = [
        f"{tema_limpo} é um conceito que abrange múltiplos aspectos e tem relevância em diversas áreas do conhecimento.",
        f"{tema_limpo} representa um tema importante que envolve diferentes perspectivas e aplicações práticas.",
        f"{tema_limpo} pode ser entendido como um elemento central para compreender fenômenos contemporâneos.",
        f"{tema_limpo} é um assunto que merece atenção por sua influência no dia a dia e na sociedade.",
        f"{tema_limpo} se caracteriza por sua complexidade e pela forma como interage com outros temas relacionados.",
        f"{tema_limpo} é frequentemente discutido por sua capacidade de gerar transformações e inovações.",
        f"{tema_limpo} envolve uma série de fatores que o tornam relevante para o estudo e a prática.",
        f"{tema_limpo} é um tópico que se destaca pela sua importância histórica e contemporânea."
    ]
    resposta_fallback = random.choice(respostas_base)
    
    # Enriquece com base no tipo
    if tipo == "artigo":
        resposta_fallback = f"{tema_limpo} é um tema de grande relevância. {resposta_fallback} Além disso, suas implicações se estendem a várias áreas, como tecnologia, cultura e sociedade."
    elif tipo == "pergunta_resposta":
        pass
    elif tipo in ["conversa", "iteracao", "dialogo_profundo"]:
        # Para diálogos, geramos uma pergunta/resposta que será salva como dado válido
        pass

    texto = f"Pergunta: {pergunta_fallback}\nResposta: {resposta_fallback}"
    _fallback_cache.add(hash_texto(texto))
    return texto, 0, 0, 0, None, "fallback", None
# <--- FIM DO FALLBACK MELHORADO

# ============================================================================
# 14. GERAÇÃO PRINCIPAL (com mais tentativas e cache)
# ============================================================================
def validar_dialogo(texto, tipo="dialogo_profundo"):
    if not texto:
        return False, "texto vazio"
    texto_limpo = re.sub(r'\*\*', '', texto)
    texto_limpo = re.sub(r'__', '', texto_limpo)
    if "Pessoa:" not in texto_limpo or "Outra:" not in texto_limpo:
        return False, "faltam marcadores 'Pessoa:' ou 'Outra:'"
    turnos = re.findall(r'(?:Pessoa|Outra)\s*:', texto_limpo, re.IGNORECASE)
    if tipo == "dialogo_profundo":
        min_turnos = 10
    elif tipo == "iteracao":
        min_turnos = 5
    else:
        min_turnos = 4
    if len(turnos) < min_turnos:
        return False, f"poucos turnos ({len(turnos)}/{min_turnos})"
    falas = re.split(r'(?:Pessoa|Outra)\s*:', texto_limpo)[1:]
    palavras_por_fala = [len(f.split()) for f in falas if f.strip()]
    if not palavras_por_fala or min(palavras_por_fala) < 5:
        return False, "fala muito curta"
    if len(texto_limpo.split()) < 150:
        return False, "texto muito curto"
    return True, "OK"

def padronizar_formato(texto):
    if not texto:
        return texto
    texto = re.sub(r'\*\*', '', texto)
    texto = re.sub(r'__', '', texto)
    texto = re.sub(r'\*\s*Pessoa\s*\*?\s*:', 'Pessoa:', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\*\s*Outra\s*\*?\s*:', 'Outra:', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\s+', ' ', texto).strip()
    linhas = texto.split('\n')
    linhas_corrigidas = []
    for linha in linhas:
        linha = linha.strip()
        if linha and not linha.startswith(('Pessoa:', 'Outra:')):
            pass
        linhas_corrigidas.append(linha)
    return '\n'.join(linhas_corrigidas)

def extrair_resposta(texto):
    if texto is None:
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
        partes = texto.split("Resposta:", 1)
        if len(partes) > 1:
            return partes[1].strip(), ""
    if texto.startswith("Resposta:"):
        return texto[9:].strip(), ""
    if "Pessoa:" in texto and "Outra:" in texto:
        return texto.strip(), ""
    return texto.strip(), ""

def gerar_dialogo(tema, tipo="dicionario", pergunta=None, tentativas=5, escalonamento_tokens=None):
    if escalonamento_tokens is None:
        escalonamento_map = {
            "dicionario": TOKENS_ESCALONADOS_DICIONARIO,
            "pergunta_resposta": TOKENS_ESCALONADOS_PERGUNTA_RESPOSTA,
            "iteracao": TOKENS_ESCALONADOS_ITERACAO,
            "artigo": TOKENS_ESCALONADOS_ARTIGO,
            "conto": TOKENS_ESCALONADOS_CONTO,
            "dialogo_profundo": TOKENS_ESCALONADOS_DIALOGO_PROFUNDO,
            "explicacao": TOKENS_ESCALONADOS_EXPLICACAO,
            "resumo": TOKENS_ESCALONADOS_RESUMO,
            "poema": TOKENS_ESCALONADOS_POEMA,
            "carta": TOKENS_ESCALONADOS_CARTA,
            "entrevista": TOKENS_ESCALONADOS_ENTREVISTA,
            "debate": TOKENS_ESCALONADOS_DEBATE,
            "tutorial": TOKENS_ESCALONADOS_TUTORIAL,
            "resenha": TOKENS_ESCALONADOS_RESENHA,
            "relatorio": TOKENS_ESCALONADOS_RELATORIO,
            "ensaio": TOKENS_ESCALONADOS_ENSAIO,
            "cronica": TOKENS_ESCALONADOS_CRONICA,
            "receita": TOKENS_ESCALONADOS_RECEITA,
            "dica": TOKENS_ESCALONADOS_DICA,
            "conversa": TOKENS_ESCALONADOS_CONVERSA,
        }
        escalonamento_tokens = escalonamento_map.get(tipo, [1024, 1280, 1536])

    temperaturas = [0.7, 0.8, 0.9, 0.6, 0.5]

    for tentativa in range(tentativas):
        max_tokens = escalonamento_tokens[min(tentativa, len(escalonamento_tokens)-1)]
        temperature = temperaturas[min(tentativa, len(temperaturas)-1)]
        prompt = gerar_prompt(tema, tipo, pergunta, max_tokens=max_tokens)

        try:
            if USE_OLLAMA:
                texto, tokens_in, tokens_out, _ = ollama_generate(prompt, max_tokens, temperature)
                custo = 0.0
                finish_reason = None
            else:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=0.9
                )
                texto = response.choices[0].message.content if response.choices else ""
                finish_reason = response.choices[0].finish_reason if response.choices else None
                tokens_entrada = getattr(response.usage, "prompt_tokens", 0) if response.usage else 0
                tokens_saida = getattr(response.usage, "completion_tokens", 0) if response.usage else 0
                custo = (tokens_entrada/1e6)*0.14 + (tokens_saida/1e6)*0.28
                tokens_in, tokens_out = tokens_entrada, tokens_saida

            if not texto or len(texto.strip()) < 5:
                if tentativa < tentativas-1:
                    continue
                return _gerar_texto_variavel(tipo, tema, pergunta)

            if tipo in ["iteracao", "dialogo_profundo", "conversa"]:
                texto = padronizar_formato(texto)
                valido, motivo = validar_dialogo(texto, tipo)
                if not valido:
                    if tentativa < tentativas-1:
                        continue
                    return _gerar_texto_variavel(tipo, tema, pergunta)

            if tipo == "dicionario":
                resposta, pergunta_extra = extrair_resposta(texto)
                resposta = limpar_texto(resposta)
                if not resposta:
                    if tentativa < tentativas-1:
                        continue
                    return _gerar_texto_variavel(tipo, tema, pergunta)
                valido, motivo = avaliar_qualidade(resposta, tipo, finish_reason)
                if not valido:
                    if tentativa < tentativas-1:
                        continue
                    return _gerar_texto_variavel(tipo, tema, pergunta)
                pergunta_final = pergunta_extra if pergunta_extra else pergunta
                if not pergunta_final:
                    pergunta_final, _, _ = gerar_pergunta_dinamica_v5()
                texto_final = f"Pergunta: {pergunta_final}\nResposta: {resposta}"
                return texto_final, custo, tokens_in, tokens_out, None, None, finish_reason

            valido, motivo = avaliar_qualidade(texto, tipo, finish_reason)
            if not valido:
                if tentativa < tentativas-1:
                    continue
                return _gerar_texto_variavel(tipo, tema, pergunta)

            h = hash_texto(texto)
            CACHE_RESPOSTAS.armazenar(h, texto)
            registrar_tema_global(tema)
            return texto, custo, tokens_in, tokens_out, None, None, finish_reason

        except Exception as e:
            if tentativa < tentativas-1:
                time.sleep(2 * (tentativa + 1))
                continue
            return _gerar_texto_variavel(tipo, tema, pergunta)

    return _gerar_texto_variavel(tipo, tema, pergunta)

# ============================================================================
# 15. VALIDAÇÃO DE ARQUIVOS EXISTENTES
# ============================================================================
def listar_arquivos_invalidos(pasta):
    invalidos = []
    if not os.path.exists(pasta):
        return invalidos
    for raiz, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            if not nome.endswith(".txt"):
                continue
            caminho = os.path.join(raiz, nome)
            try:
                with open(caminho, 'r', encoding='utf-8') as f:
                    texto = f.read()
            except:
                continue
            if "Pergunta:" in texto and "Resposta:" in texto:
                partes = texto.split("Resposta:", 1)
                if len(partes) > 1 and len(partes[1].strip()) < 5:
                    invalidos.append((caminho, "resposta muito curta"))
            elif "Pessoa:" in texto and "Outra:" in texto:
                if len(texto.strip()) < 150:
                    invalidos.append((caminho, "diálogo muito curto"))
            else:
                if len(texto.strip()) < 100:
                    invalidos.append((caminho, "texto muito curto"))
    return invalidos

def limpar_arquivos_invalidos(pasta, dry_run=False):
    invalidos = listar_arquivos_invalidos(pasta)
    if not invalidos:
        print(f"✅ Nenhum arquivo inválido encontrado em {pasta}.")
        return
    print(f"\n📋 {len(invalidos)} arquivos inválidos encontrados em {pasta}:")
    for caminho, motivo in invalidos[:10]:
        print(f"   ⚠️ {os.path.basename(caminho)} – {motivo}")
    if len(invalidos) > 10:
        print(f"   ... e mais {len(invalidos)-10} arquivos.")
    if dry_run:
        print("\n🔍 Modo de validação (dry-run): nenhum arquivo foi removido.")
        return
    resposta = input("\n🗑️  Deseja remover todos esses arquivos? (s/N): ").strip().lower()
    if resposta == 's':
        removidos = 0
        for caminho, _ in invalidos:
            try:
                os.remove(caminho)
                removidos += 1
            except:
                pass
        print(f"✅ {removidos} arquivos removidos.")
    else:
        print("✅ Nenhum arquivo removido.")

# ============================================================================
# 16. LOGS E HISTÓRICO
# ============================================================================
def registrar_historico(execucao):
    historico = carregar_json(ARQUIVO_HISTORICO, [])
    historico.append(execucao)
    salvar_json(ARQUIVO_HISTORICO, historico)
    with open(ARQUIVO_LOG, 'a', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write(f"📅 {execucao['data_hora']}\n")
        f.write(f"   Modelo: {execucao['modelo']}\n")
        f.write(f"   Tipo: {execucao['tipo']}\n")
        f.write(f"   Alvo: {execucao['alvo']}\n")
        f.write(f"   Gerados: {execucao['gerados']}\n")
        f.write(f"   Descartados: {execucao['descartados']}\n")
        f.write(f"   Gasto: ${execucao['gasto_execucao']:.6f}\n")
        f.write(f"   Gasto acumulado: ${execucao['gasto_acumulado']:.6f}\n")
        f.write(f"   Tempo: {execucao['tempo_segundos']:.2f}s\n")
        f.write(f"   Descartados salvos: {execucao.get('descartados_salvos', 0)}\n")
        f.write("=" * 70 + "\n\n")

def ver_logs():
    if not os.path.exists(ARQUIVO_HISTORICO):
        print("📭 Nenhum histórico encontrado.")
        return
    historico = carregar_json(ARQUIVO_HISTORICO, [])
    print(f"\n📋 Histórico de execuções ({len(historico)} registros):\n")
    for i, entry in enumerate(historico, 1):
        print(f"[{i}] {entry['data_hora']} | {entry['modelo']} | Gerados: {entry['gerados']} | Gasto: ${entry['gasto_execucao']:.4f} | Desc.salvos: {entry.get('descartados_salvos', 0)}")
    print(f"\n📄 Log completo em: {ARQUIVO_LOG}")
    print(f"📄 Histórico JSON em: {ARQUIVO_HISTORICO}")

def estatisticas():
    dados = carregar_json(ARQUIVO_HISTORICO, [])
    if not dados:
        print("📭 Sem dados para estatísticas ainda.")
        return
    total = len(dados)
    soma_gerados = sum(item.get("gerados", 0) for item in dados)
    soma_descartados = sum(item.get("descartados", 0) for item in dados)
    soma_gasto = sum(item.get("gasto_execucao", 0.0) for item in dados)
    print("\n📊 ESTATÍSTICAS")
    print(f"   Execuções: {total}")
    print(f"   Itens gerados: {soma_gerados}")
    print(f"   Itens descartados: {soma_descartados}")
    print(f"   Gasto total: ${soma_gasto:.4f}")
    print(f"   Categorias mais usadas: {CONTAGEM_CATEGORIAS.most_common(5)}")

# ============================================================================
# 17. FUNÇÃO PARA ESTIMAR CUSTO
# ============================================================================
def estimar_custo(tipo: str, quantidade: int) -> float:
    custo_por_item = {
        "dicionario": 0.0002,
        "pergunta_resposta": 0.0012,
        "iteracao": 0.0008,
        "artigo": 0.0015,
        "conto": 0.0015,
        "dialogo_profundo": 0.0018,
        "explicacao": 0.0015,
        "resumo": 0.0008,
        "conversa": 0.0010,
        "saudacao": 0.0,
        "poema": 0.0010,
        "carta": 0.0012,
        "entrevista": 0.0015,
        "debate": 0.0018,
        "tutorial": 0.0012,
        "resenha": 0.0015,
        "relatorio": 0.0015,
        "ensaio": 0.0015,
        "cronica": 0.0010,
        "receita": 0.0006,
        "dica": 0.0004,
    }
    base = custo_por_item.get(tipo, 0.0005)
    return base * quantidade

# ============================================================================
# 18. MENU INTERATIVO (ATUALIZADO)
# ============================================================================
def menu_interativo():
    while True:
        print("\n" + "=" * 70)
        print("🤖 GERADOR DE DADOS SINTÉTICOS - RigelSLM (v1.0.0)")
        print("   Desenvolvido por George Herman Becker")
        print("=" * 70)
        print("\nEscolha o tipo de dado a gerar:")
        print("  1. Dicionário (pergunta + resposta curta)")
        print("  2. Pergunta e Resposta (longa) ★")
        print("  3. Iteração (diálogo 5-8 turnos)")
        print("  4. Artigo (estruturado 500-900 palavras) ★★")
        print("  5. Conto (história curta 400-700) ★★★")
        print("  6. Diálogo Profundo (10-15 turnos) ★★★★★")
        print("  7. Explicação (detalhada 350-600 palavras)")
        print("  8. Resumo (síntese concisa 200-400)")
        print("  9. Conversa (diálogo, min 250 palavras)")
        print(" 10. Saudação (prontas, sem custo)")
        print(" 11. Poema (10-20 versos)")
        print(" 12. Carta (formal/informal)")
        print(" 13. Entrevista (5-8 perguntas)")
        print(" 14. Debate (pró e contra)")
        print(" 15. Tutorial (passo a passo) ✨ NOVO")
        print(" 16. Resenha (crítica) ✨ NOVO")
        print(" 17. Relatório (técnico) ✨ NOVO")
        print(" 18. Ensaio (reflexivo) ✨ NOVO")
        print(" 19. Crônica (texto literário) ✨ NOVO")
        print(" 20. Receita (culinária) ✨ NOVO")
        print(" 21. Dica (conselho rápido) ✨ NOVO")
        print(" 22. Modo Automático (balanceia tipos)")
        print(" 23. Sair")

        opcao = input("\nDigite o número da opção (1-23): ").strip()
        if opcao not in [str(i) for i in range(1, 24)]:
            print("❌ Opção inválida. Tente novamente.")
            continue

        if opcao == "23":
            print("👋 Saindo...")
            break

        tipos = ["dicionario", "pergunta_resposta", "iteracao", "artigo", "conto",
                 "dialogo_profundo", "explicacao", "resumo", "conversa", "saudacao",
                 "poema", "carta", "entrevista", "debate",
                 "tutorial", "resenha", "relatorio", "ensaio", "cronica", "receita", "dica"]
        if opcao == "22":
            tipo = "auto"
        else:
            tipo = tipos[int(opcao)-1]

        try:
            quantidade = int(input("Quantos itens deseja gerar? (padrão 500): ") or "500")
        except ValueError:
            print("❌ Valor inválido. Usando 500.")
            quantidade = 500
        if quantidade <= 0:
            quantidade = 500

        if opcao == "22":
            # Modo automático com distribuição
            custo_estimado = estimar_custo("pergunta_resposta", int(quantidade * 0.12)) + \
                             estimar_custo("artigo", int(quantidade * 0.08)) + \
                             estimar_custo("dialogo_profundo", int(quantidade * 0.10)) + \
                             estimar_custo("explicacao", int(quantidade * 0.08)) + \
                             estimar_custo("resumo", int(quantidade * 0.06)) + \
                             estimar_custo("conversa", int(quantidade * 0.06)) + \
                             estimar_custo("dicionario", int(quantidade * 0.08)) + \
                             estimar_custo("conto", int(quantidade * 0.06)) + \
                             estimar_custo("poema", int(quantidade * 0.05)) + \
                             estimar_custo("carta", int(quantidade * 0.05)) + \
                             estimar_custo("entrevista", int(quantidade * 0.06)) + \
                             estimar_custo("debate", int(quantidade * 0.06)) + \
                             estimar_custo("tutorial", int(quantidade * 0.05)) + \
                             estimar_custo("resenha", int(quantidade * 0.05)) + \
                             estimar_custo("relatorio", int(quantidade * 0.04)) + \
                             estimar_custo("ensaio", int(quantidade * 0.04)) + \
                             estimar_custo("cronica", int(quantidade * 0.04)) + \
                             estimar_custo("receita", int(quantidade * 0.04)) + \
                             estimar_custo("dica", int(quantidade * 0.04))
            print(f"\n💰 Custo estimado (modo automático): ${custo_estimado:.4f} USD")
            confirm = input("\nContinuar com a geração? (s/N): ").strip().lower()
            if confirm != 's':
                print("❌ Operação cancelada.")
                continue
            args = Args()
            args.tipo = "auto"
            args.quantidade = quantidade
            args.prefixo = "dialogo_auto"
            args.delay = DELAY_SECONDS
            args.limite = MAX_COST_USD
            args.modelo = "deepseek" if not USE_OLLAMA else "ollama"
            executar_geracao(args)
            continue

        custo_estimado = estimar_custo(tipo, quantidade)
        if custo_estimado > 0:
            print(f"\n💰 Custo estimado: ${custo_estimado:.4f} USD")
            if custo_estimado > 1.0:
                print("   ⚠️ Custo relativamente alto. Considere reduzir a quantidade.")
        else:
            print("\n💰 Custo estimado: $0.00 (sem custo)")

        dados_gastos = carregar_gastos()
        gasto_atual = dados_gastos.get("total_gasto", 0.0)
        if gasto_atual + custo_estimado > MAX_COST_USD:
            print(f"⚠️ Limite global: ${MAX_COST_USD:.2f}, já gastou ${gasto_atual:.4f}.")
            print(f"   Esta execução custaria ${custo_estimado:.4f}, ultrapassando o limite.")
            continuar = input("   Deseja continuar mesmo assim? (s/N): ").strip().lower()
            if continuar != 's':
                print("❌ Operação cancelada.")
                continue

        confirm = input("\nContinuar com a geração? (s/N): ").strip().lower()
        if confirm != 's':
            print("❌ Operação cancelada.")
            continue

        args = Args()
        args.tipo = tipo
        args.quantidade = quantidade
        args.prefixo = "dialogo"
        args.delay = DELAY_SECONDS
        args.limite = MAX_COST_USD
        args.modelo = "deepseek" if not USE_OLLAMA else "ollama"
        executar_geracao(args)

# ============================================================================
# 19. FUNÇÃO DE EXECUÇÃO (AJUSTADA)
# ============================================================================
def executar_geracao(args):
    global MAX_COST_USD, DELAY_SECONDS

    if args.limite is not None:
        MAX_COST_USD = args.limite
    if args.delay is not None:
        DELAY_SECONDS = args.delay

    if args.ver_logs:
        ver_logs()
        return
    if args.estatisticas:
        estatisticas()
        return
    if args.limpar_invalidos or args.validar:
        print("🔍 Verificando arquivos existentes...")
        limpar_arquivos_invalidos(PASTA_DADOS_CURTOS, dry_run=args.validar)
        limpar_arquivos_invalidos(PASTA_DADOS_LONGOS, dry_run=args.validar)
        return
    if args.listar_temas:
        print("\n📋 CATEGORIAS E ASSUNTOS DISPONÍVEIS:\n")
        for cat, lista in CATEGORIAS_LISTAS.items():
            exibir_categoria(f"🔹 {cat.upper()}:", lista)
        print("\n📌 SAUDAÇÕES:")
        for s in SAUDACOES[:10]:
            print(f"   - {s[0]} -> {s[1]}")
        print(f"   ... e mais {len(SAUDACOES)-10} saudações")
        return

    if args.tipo == "auto":
        print("=" * 70)
        print("🤖 GERADOR DE DADOS SINTÉTICOS - MODO AUTOMÁTICO (v1.0.0)")
        print(f"   Modelo: {args.modelo}")
        print(f"   Limite: ${MAX_COST_USD:.2f}")
        print(f"   Delay: {DELAY_SECONDS}s")
        print(f"   Alvo: {args.quantidade} itens (distribuídos automaticamente)")
        print("=" * 70)

        if not verificar_limite():
            print("⚠️ Limite já foi atingido.")
            return

        distribuicao = {
            "pergunta_resposta": 0.10,
            "artigo": 0.07,
            "dialogo_profundo": 0.08,
            "explicacao": 0.08,
            "resumo": 0.06,
            "conversa": 0.06,
            "dicionario": 0.08,
            "conto": 0.05,
            "poema": 0.05,
            "carta": 0.05,
            "entrevista": 0.06,
            "debate": 0.06,
            "tutorial": 0.05,
            "resenha": 0.04,
            "relatorio": 0.04,
            "ensaio": 0.04,
            "cronica": 0.04,
            "receita": 0.03,
            "dica": 0.03,
        }
        quantidades = {}
        resto = args.quantidade
        for tipo, prop in distribuicao.items():
            qtd = int(args.quantidade * prop)
            quantidades[tipo] = qtd
            resto -= qtd
        for tipo in distribuicao.keys():
            if resto <= 0:
                break
            quantidades[tipo] += 1
            resto -= 1

        total_gerados_global = 0
        total_descartes_global = 0
        gasto_execucao_global = 0.0

        for tipo, qtd in quantidades.items():
            if qtd <= 0:
                continue
            print(f"\n--- Gerando {qtd} itens do tipo '{tipo}' ---")
            args_sub = args
            args_sub.tipo = tipo
            args_sub.quantidade = qtd
            args_sub.prefixo = f"auto_{tipo}"
            gerados, descartes, gasto = gerar_lote(
                tipo, qtd, args_sub.prefixo,
                args_sub.max_tokens_base, args_sub.max_tokens_extra,
                args_sub.max_tokens_pr_base, args_sub.max_tokens_pr_extra,
                args_sub.max_tokens_it_base, args_sub.max_tokens_it_extra,
                args_sub.max_tokens_art_base, args_sub.max_tokens_art_extra,
                args_sub.max_tokens_conto_base, args_sub.max_tokens_conto_extra,
                args_sub.max_tokens_dp_base, args_sub.max_tokens_dp_extra,
                args_sub.max_tokens_expl_base, args_sub.max_tokens_expl_extra,
                args_sub.max_tokens_resumo_base, args_sub.max_tokens_resumo_extra,
                args_sub.max_tokens_poema_base, args_sub.max_tokens_poema_extra,
                args_sub.max_tokens_carta_base, args_sub.max_tokens_carta_extra,
                args_sub.max_tokens_entrevista_base, args_sub.max_tokens_entrevista_extra,
                args_sub.max_tokens_debate_base, args_sub.max_tokens_debate_extra,
                args_sub.max_tokens_tutorial_base, args_sub.max_tokens_tutorial_extra,
                args_sub.max_tokens_resenha_base, args_sub.max_tokens_resenha_extra,
                args_sub.max_tokens_relatorio_base, args_sub.max_tokens_relatorio_extra,
                args_sub.max_tokens_ensaio_base, args_sub.max_tokens_ensaio_extra,
                args_sub.max_tokens_cronica_base, args_sub.max_tokens_cronica_extra,
                args_sub.max_tokens_receita_base, args_sub.max_tokens_receita_extra,
                args_sub.max_tokens_dica_base, args_sub.max_tokens_dica_extra,
                delay=DELAY_SECONDS
            )
            total_gerados_global += gerados
            total_descartes_global += descartes
            gasto_execucao_global += gasto

        print("\n" + "=" * 70)
        print("📊 RESUMO FINAL (MODO AUTOMÁTICO)")
        print("=" * 70)
        print(f"   ✅ Gerados: {total_gerados_global}")
        print(f"   ❌ Descartados: {total_descartes_global}")
        print(f"   💰 Gasto execução: ${gasto_execucao_global:.4f}")
        print(f"   📂 Curtos: {PASTA_DADOS_CURTOS}/")
        print(f"   📂 Longos: {PASTA_DADOS_LONGOS}/")
        print(f"   🗑️  Descartados salvos: {PASTA_DESCARTES}/")
        print("=" * 70)
        return

    # Execução normal
    print("=" * 70)
    print("🤖 GERADOR DE DADOS SINTÉTICOS - RigelSLM (v1.0.0)")
    print(f"   Modelo: {args.modelo}")
    print(f"   Limite: ${MAX_COST_USD:.2f}")
    print(f"   Delay: {DELAY_SECONDS}s")
    print(f"   Alvo: {args.quantidade} itens")
    print(f"   Tipo: {args.tipo}")
    print(f"   Prefixo: {args.prefixo}")
    print("=" * 70)

    if not verificar_limite():
        print("⚠️ Limite já foi atingido.")
        return

    if args.tipo == "saudacao":
        print("💬 GERANDO SAUDAÇÕES (sem custo de API)")
        total_gerados = 0
        usadas = set()
        while total_gerados < args.quantidade:
            disponiveis = [s for s in SAUDACOES if s[0] not in usadas]
            if not disponiveis:
                usadas.clear()
                disponiveis = SAUDACOES
            pergunta, resposta = random.choice(disponiveis)
            usadas.add(pergunta)
            if resposta_ja_usada(resposta):
                continue
            texto = f"Pergunta: {pergunta}\nResposta: {resposta}"
            pasta = PASTA_DADOS_CURTOS
            salvar_texto(texto, args.prefixo, total_gerados, pasta)
            metadados = {
                "indice": total_gerados,
                "tipo": "saudacao",
                "categoria": "saudacao",
                "assunto": "cumprimento",
                "pergunta": pergunta,
                "modelo": "predefinido",
                "data": datetime.now().isoformat(),
                "arquivo": os.path.join(pasta, f"{args.prefixo}_{total_gerados:06d}.txt")
            }
            salvar_metadados(metadados)
            registrar_no_historico(pergunta, resposta, "saudacao", "cumprimento")
            total_gerados += 1
            if total_gerados % 100 == 0:
                print(f"   ✅ {total_gerados} saudações geradas")
        print(f"\n✅ {total_gerados} saudações salvas em {PASTA_DADOS_CURTOS}/")
        return

    escalonamento_map = {
        "dicionario": [args.max_tokens_base] + args.max_tokens_extra,
        "pergunta_resposta": [args.max_tokens_pr_base] + args.max_tokens_pr_extra,
        "iteracao": [args.max_tokens_it_base] + args.max_tokens_it_extra,
        "artigo": [args.max_tokens_art_base] + args.max_tokens_art_extra,
        "conto": [args.max_tokens_conto_base] + args.max_tokens_conto_extra,
        "dialogo_profundo": [args.max_tokens_dp_base] + args.max_tokens_dp_extra,
        "explicacao": [args.max_tokens_expl_base] + args.max_tokens_expl_extra,
        "resumo": [args.max_tokens_resumo_base] + args.max_tokens_resumo_extra,
        "poema": [args.max_tokens_poema_base] + args.max_tokens_poema_extra,
        "carta": [args.max_tokens_carta_base] + args.max_tokens_carta_extra,
        "entrevista": [args.max_tokens_entrevista_base] + args.max_tokens_entrevista_extra,
        "debate": [args.max_tokens_debate_base] + args.max_tokens_debate_extra,
        "tutorial": [args.max_tokens_tutorial_base] + args.max_tokens_tutorial_extra,
        "resenha": [args.max_tokens_resenha_base] + args.max_tokens_resenha_extra,
        "relatorio": [args.max_tokens_relatorio_base] + args.max_tokens_relatorio_extra,
        "ensaio": [args.max_tokens_ensaio_base] + args.max_tokens_ensaio_extra,
        "cronica": [args.max_tokens_cronica_base] + args.max_tokens_cronica_extra,
        "receita": [args.max_tokens_receita_base] + args.max_tokens_receita_extra,
        "dica": [args.max_tokens_dica_base] + args.max_tokens_dica_extra,
        "conversa": [1024, 1280, 1536],
    }
    escalonamento = escalonamento_map.get(args.tipo, [1024, 1280, 1536])

    ARQUIVO_ESTADO_DIALOGOS = os.path.join(PASTA_ESTADO, "estado_dialogos.json")
    estado_dialogos = carregar_json(ARQUIVO_ESTADO_DIALOGOS, {"processados": [], "custo_total": 0.0})

    total_gerados = 0
    total_descartes = 0
    gasto_execucao = 0.0
    motivos = {}
    descartes_salvos = 0
    total_repetidos = 0

    print(f"\n🚀 Iniciando geração...")
    print(f"📂 Descartados salvos em {PASTA_DESCARTES}/\n")

    with tqdm(total=args.quantidade, desc="Gerando", unit="item") as pbar:
        while total_gerados < args.quantidade:
            if not verificar_limite():
                break

            pergunta, categoria, assunto = gerar_pergunta_dinamica_v5()
            tema = f"{categoria}: {assunto}"

            texto, custo, tokens_in, tokens_out, _, _, finish_reason = gerar_dialogo(
                tema, args.tipo, pergunta,
                tentativas=5,
                escalonamento_tokens=escalonamento
            )

            if texto is None:
                total_descartes += 1
                motivos["falha total"] = motivos.get("falha total", 0) + 1
                salvar_descarte("(vazio)", args.prefixo, "falha total", descartes_salvos)
                descartes_salvos += 1
                pbar.set_postfix({"desc": total_descartes, "rep": total_repetidos, "custo": f"${estado_dialogos['custo_total']:.4f}"})
                time.sleep(DELAY_SECONDS * 0.5)
                continue

            if args.tipo in ["iteracao", "dialogo_profundo", "conversa"]:
                valido, motivo = validar_dialogo(texto, args.tipo)
                if not valido:
                    total_descartes += 1
                    motivos[motivo] = motivos.get(motivo, 0) + 1
                    salvar_descarte(texto, args.prefixo, motivo, descartes_salvos)
                    descartes_salvos += 1
                    pbar.set_postfix({"desc": total_descartes, "rep": total_repetidos, "custo": f"${estado_dialogos['custo_total']:.4f}"})
                    time.sleep(DELAY_SECONDS * 0.5)
                    continue

            h = hash_texto(texto)
            if h in estado_dialogos["processados"]:
                total_repetidos += 1
                pbar.set_postfix({"desc": total_descartes, "rep": total_repetidos, "custo": f"${estado_dialogos['custo_total']:.4f}"})
                time.sleep(DELAY_SECONDS * 0.5)
                continue

            palavras = len(texto.split())
            if palavras < LIMITE_PALAVRAS_CURTOS:
                pasta = PASTA_DADOS_CURTOS
                classe = "curto"
            else:
                pasta = PASTA_DADOS_LONGOS
                classe = "longo"

            agora = datetime.now().strftime("%d%m%Y%H%M")
            nome = f"{args.prefixo}_{agora}.txt"
            caminho = os.path.join(pasta, nome)
            contador = 1
            while os.path.exists(caminho):
                nome = f"{args.prefixo}_{agora}_{contador:02d}.txt"
                caminho = os.path.join(pasta, nome)
                contador += 1

            with open(caminho, 'w', encoding='utf-8') as f:
                f.write(texto)

            estado_dialogos["processados"].append(h)
            estado_dialogos["custo_total"] += custo
            salvar_json(ARQUIVO_ESTADO_DIALOGOS, estado_dialogos)

            total_gerados += 1
            if custo > 0:
                registrar_gasto(custo, tokens_in, tokens_out, tema, args.tipo)
                gasto_execucao += custo

            pbar.update(1)
            pbar.set_postfix({"curto": total_gerados if classe == "curto" else 0,
                              "longo": total_gerados if classe == "longo" else 0,
                              "desc": total_descartes,
                              "rep": total_repetidos,
                              "custo": f"${estado_dialogos['custo_total']:.4f}"})
            time.sleep(DELAY_SECONDS)

    print("\n" + "=" * 70)
    print("📊 RESUMO FINAL")
    print("=" * 70)
    print(f"   ✅ Gerados: {total_gerados}")
    print(f"   ❌ Descartados: {total_descartes}")
    print(f"   🔁 Repetidos (ignorados): {total_repetidos}")
    print(f"   💰 Gasto execução: ${gasto_execucao:.4f}")
    print(f"   📂 Curtos: {PASTA_DADOS_CURTOS}/")
    print(f"   📂 Longos: {PASTA_DADOS_LONGOS}/")
    print(f"   🗑️  Descartados salvos: {PASTA_DESCARTES}/")
    if motivos:
        print("   Motivos de descarte:")
        for motivo, count in sorted(motivos.items(), key=lambda x: -x[1])[:5]:
            print(f"      - {motivo}: {count} vezes")
    print("=" * 70)
    print(f"\n📝 Log salvo em: {ARQUIVO_LOG}")
    print(f"📝 Histórico em: {ARQUIVO_HISTORICO}")
    print("💡 Para treinar, use: python treino.py --dados dados/gerados")

# ============================================================================
# 20. FUNÇÃO AUXILIAR PARA GERAR LOTE
# ============================================================================
def gerar_lote(tipo, quantidade, prefixo,
               max_tokens_base, max_tokens_extra,
               max_tokens_pr_base, max_tokens_pr_extra,
               max_tokens_it_base, max_tokens_it_extra,
               max_tokens_art_base, max_tokens_art_extra,
               max_tokens_conto_base, max_tokens_conto_extra,
               max_tokens_dp_base, max_tokens_dp_extra,
               max_tokens_expl_base, max_tokens_expl_extra,
               max_tokens_resumo_base, max_tokens_resumo_extra,
               max_tokens_poema_base, max_tokens_poema_extra,
               max_tokens_carta_base, max_tokens_carta_extra,
               max_tokens_entrevista_base, max_tokens_entrevista_extra,
               max_tokens_debate_base, max_tokens_debate_extra,
               max_tokens_tutorial_base=1024, max_tokens_tutorial_extra=[1024,1280,1536],
               max_tokens_resenha_base=1024, max_tokens_resenha_extra=[1024,1280,1536],
               max_tokens_relatorio_base=1024, max_tokens_relatorio_extra=[1024,1280,1536],
               max_tokens_ensaio_base=1024, max_tokens_ensaio_extra=[1024,1280,1536],
               max_tokens_cronica_base=768, max_tokens_cronica_extra=[768,1024,1280],
               max_tokens_receita_base=512, max_tokens_receita_extra=[512,768,1024],
               max_tokens_dica_base=512, max_tokens_dica_extra=[512,768,1024],
               delay=2.0):
    escalonamento_map = {
        "dicionario": [max_tokens_base] + max_tokens_extra,
        "pergunta_resposta": [max_tokens_pr_base] + max_tokens_pr_extra,
        "iteracao": [max_tokens_it_base] + max_tokens_it_extra,
        "artigo": [max_tokens_art_base] + max_tokens_art_extra,
        "conto": [max_tokens_conto_base] + max_tokens_conto_extra,
        "dialogo_profundo": [max_tokens_dp_base] + max_tokens_dp_extra,
        "explicacao": [max_tokens_expl_base] + max_tokens_expl_extra,
        "resumo": [max_tokens_resumo_base] + max_tokens_resumo_extra,
        "poema": [max_tokens_poema_base] + max_tokens_poema_extra,
        "carta": [max_tokens_carta_base] + max_tokens_carta_extra,
        "entrevista": [max_tokens_entrevista_base] + max_tokens_entrevista_extra,
        "debate": [max_tokens_debate_base] + max_tokens_debate_extra,
        "tutorial": [max_tokens_tutorial_base] + max_tokens_tutorial_extra,
        "resenha": [max_tokens_resenha_base] + max_tokens_resenha_extra,
        "relatorio": [max_tokens_relatorio_base] + max_tokens_relatorio_extra,
        "ensaio": [max_tokens_ensaio_base] + max_tokens_ensaio_extra,
        "cronica": [max_tokens_cronica_base] + max_tokens_cronica_extra,
        "receita": [max_tokens_receita_base] + max_tokens_receita_extra,
        "dica": [max_tokens_dica_base] + max_tokens_dica_extra,
        "conversa": [1024, 1280, 1536],
    }
    escalonamento = escalonamento_map.get(tipo, [1024, 1280, 1536])

    ARQUIVO_ESTADO_DIALOGOS = os.path.join(PASTA_ESTADO, "estado_dialogos.json")
    estado_dialogos = carregar_json(ARQUIVO_ESTADO_DIALOGOS, {"processados": [], "custo_total": 0.0})

    total_gerados = 0
    total_descartes = 0
    gasto_execucao = 0.0
    motivos = {}
    descartes_salvos = 0
    total_repetidos = 0

    with tqdm(total=quantidade, desc=f"Gerando {tipo}", unit="item") as pbar:
        while total_gerados < quantidade:
            if not verificar_limite():
                break

            pergunta, categoria, assunto = gerar_pergunta_dinamica_v5()
            tema = f"{categoria}: {assunto}"

            texto, custo, tokens_in, tokens_out, _, _, finish_reason = gerar_dialogo(
                tema, tipo, pergunta,
                tentativas=5,
                escalonamento_tokens=escalonamento
            )

            if texto is None:
                total_descartes += 1
                motivos["falha total"] = motivos.get("falha total", 0) + 1
                salvar_descarte("(vazio)", prefixo, "falha total", descartes_salvos)
                descartes_salvos += 1
                pbar.update(1)
                time.sleep(delay * 0.5)
                continue

            if tipo in ["iteracao", "dialogo_profundo", "conversa"]:
                valido, motivo = validar_dialogo(texto, tipo)
                if not valido:
                    total_descartes += 1
                    motivos[motivo] = motivos.get(motivo, 0) + 1
                    salvar_descarte(texto, prefixo, motivo, descartes_salvos)
                    descartes_salvos += 1
                    pbar.update(1)
                    time.sleep(delay * 0.5)
                    continue

            h = hash_texto(texto)
            if h in estado_dialogos["processados"]:
                total_repetidos += 1
                pbar.update(1)
                time.sleep(delay * 0.5)
                continue

            palavras = len(texto.split())
            if palavras < LIMITE_PALAVRAS_CURTOS:
                pasta = PASTA_DADOS_CURTOS
            else:
                pasta = PASTA_DADOS_LONGOS

            agora = datetime.now().strftime("%d%m%Y%H%M")
            nome = f"{prefixo}_{agora}.txt"
            caminho = os.path.join(pasta, nome)
            contador = 1
            while os.path.exists(caminho):
                nome = f"{prefixo}_{agora}_{contador:02d}.txt"
                caminho = os.path.join(pasta, nome)
                contador += 1

            with open(caminho, 'w', encoding='utf-8') as f:
                f.write(texto)

            estado_dialogos["processados"].append(h)
            estado_dialogos["custo_total"] += custo
            salvar_json(ARQUIVO_ESTADO_DIALOGOS, estado_dialogos)

            total_gerados += 1
            if custo > 0:
                registrar_gasto(custo, tokens_in, tokens_out, tema, tipo)
                gasto_execucao += custo

            pbar.update(1)
            pbar.set_postfix({"desc": total_descartes, "rep": total_repetidos, "custo": f"${estado_dialogos['custo_total']:.4f}"})
            time.sleep(delay)

    return total_gerados, total_descartes, gasto_execucao

# ============================================================================
# 21. FUNÇÃO PRINCIPAL
# ============================================================================
def main():
    global MAX_COST_USD, DELAY_SECONDS

    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description="Gera diálogos sintéticos em PT-BR com foco em SLM (v1.0.0)")
        parser.add_argument("--tema", type=str, help="Tema específico (para conversa ou pergunta_resposta)")
        parser.add_argument("--quantidade", type=int, default=500, help="Quantidade de diálogos (padrão: 500)")
        parser.add_argument("--limite", type=float, help="Limite de gastos em USD (sobrescreve .env)")
        parser.add_argument("--delay", type=float, help="Delay entre requisições em segundos (sobrescreve .env)")
        parser.add_argument("--tipo", type=str, choices=["conversa", "pergunta_resposta", "dicionario", "iteracao", "saudacao", "artigo", "conto", "dialogo_profundo", "explicacao", "resumo", "poema", "carta", "entrevista", "debate", "tutorial", "resenha", "relatorio", "ensaio", "cronica", "receita", "dica", "auto"], default="dicionario")
        parser.add_argument("--listar-temas", action="store_true", help="Lista as categorias e assuntos")
        parser.add_argument("--prefixo", type=str, default="dialogo", help="Prefixo dos arquivos")
        parser.add_argument("--limpar-invalidos", action="store_true", help="Remove arquivos corrompidos já gerados")
        parser.add_argument("--validar", action="store_true", help="Lista arquivos inválidos sem removê-los (dry-run)")
        parser.add_argument("--ver-logs", action="store_true", help="Exibe o histórico de execuções")
        parser.add_argument("--estatisticas", action="store_true", help="Exibe estatísticas resumidas")
        parser.add_argument("--modelo", type=str, choices=["deepseek", "ollama"], default="deepseek", help="Modelo a usar")
        parser.add_argument("--pasta-saida", type=str, default=PASTA_SAIDA, help="Pasta raiz de saída")
        # Argumentos de tokens (mantidos)
        parser.add_argument("--max-tokens-base", type=int, default=512)
        parser.add_argument("--max-tokens-extra", type=int, nargs="*", default=[512,768,1024])
        parser.add_argument("--max-tokens-pr-base", type=int, default=1024)
        parser.add_argument("--max-tokens-pr-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-it-base", type=int, default=768)
        parser.add_argument("--max-tokens-it-extra", type=int, nargs="*", default=[768,1024,1280])
        parser.add_argument("--max-tokens-art-base", type=int, default=1024)
        parser.add_argument("--max-tokens-art-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-conto-base", type=int, default=1024)
        parser.add_argument("--max-tokens-conto-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-dp-base", type=int, default=1024)
        parser.add_argument("--max-tokens-dp-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-expl-base", type=int, default=1024)
        parser.add_argument("--max-tokens-expl-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-resumo-base", type=int, default=768)
        parser.add_argument("--max-tokens-resumo-extra", type=int, nargs="*", default=[768,1024,1280])
        parser.add_argument("--max-tokens-poema-base", type=int, default=512)
        parser.add_argument("--max-tokens-poema-extra", type=int, nargs="*", default=[512,768,1024])
        parser.add_argument("--max-tokens-carta-base", type=int, default=768)
        parser.add_argument("--max-tokens-carta-extra", type=int, nargs="*", default=[768,1024,1280])
        parser.add_argument("--max-tokens-entrevista-base", type=int, default=1024)
        parser.add_argument("--max-tokens-entrevista-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-debate-base", type=int, default=1024)
        parser.add_argument("--max-tokens-debate-extra", type=int, nargs="*", default=[1024,1280,1536])
        # Novos
        parser.add_argument("--max-tokens-tutorial-base", type=int, default=1024)
        parser.add_argument("--max-tokens-tutorial-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-resenha-base", type=int, default=1024)
        parser.add_argument("--max-tokens-resenha-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-relatorio-base", type=int, default=1024)
        parser.add_argument("--max-tokens-relatorio-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-ensaio-base", type=int, default=1024)
        parser.add_argument("--max-tokens-ensaio-extra", type=int, nargs="*", default=[1024,1280,1536])
        parser.add_argument("--max-tokens-cronica-base", type=int, default=768)
        parser.add_argument("--max-tokens-cronica-extra", type=int, nargs="*", default=[768,1024,1280])
        parser.add_argument("--max-tokens-receita-base", type=int, default=512)
        parser.add_argument("--max-tokens-receita-extra", type=int, nargs="*", default=[512,768,1024])
        parser.add_argument("--max-tokens-dica-base", type=int, default=512)
        parser.add_argument("--max-tokens-dica-extra", type=int, nargs="*", default=[512,768,1024])

        args = parser.parse_args()

        if args.limite is not None:
            MAX_COST_USD = args.limite
        if args.delay is not None:
            DELAY_SECONDS = args.delay
        if args.modelo:
            global USE_OLLAMA
            USE_OLLAMA = (args.modelo == "ollama")

        executar_geracao(args)
    else:
        menu_interativo()

if __name__ == "__main__":
    main()