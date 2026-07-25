#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
categories.py - Listas de categorias, assuntos, grupos, prefixos e templates.
Contém todo o conhecimento base para geração de perguntas.
"""

# ============================================================================
# OBJETOS (expandido)
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
    # Novos
    "impressora 3D", "scanner 3D", "kit de robótica", "placa Arduino", "Raspberry Pi",
    "projetor holográfico", "óculos de realidade virtual", "capacete de realidade aumentada",
    "drone agrícola", "veículo elétrico", "bicicleta elétrica", "patinete elétrico",
    "cadeira de rodas motorizada", "prótese robótica", "exoesqueleto",
    "smartwatch com ECG", "monitor de glicose", "termômetro digital", "oxímetro",
]

# ============================================================================
# LUGARES (expandido)
# ============================================================================
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
    # Novos
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

# ============================================================================
# PESSOAS (expandido)
# ============================================================================
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
    "George Herman Becker",  # desenvolvedor
    # Novos
    "Monteiro Lobato", "Mário de Andrade", "Oswald de Andrade", "Manuel Bandeira",
    "Cecília Meireles", "João Cabral de Melo Neto", "Ferreira Gullar", "Adélia Prado",
    "Rubem Braga", "Nelson Rodrigues", "Dias Gomes", "Gianfrancesco Guarnieri",
    "Augusto Boal", "Zé Celso", "Antunes Filho", "Fábio Porchat", "Tatá Werneck",
    "Sabrina Sato", "Xuxa", "Gugu Liberato", "Fausto Silva", "Silvio Santos",
    "Hebe Camargo", "Dercy Gonçalves", "Chico Anysio", "Jô Soares", "Ziraldo",
    "Mauricio de Sousa", "Ataíde", "Aleijadinho", "Mestre Valentim",
    "Cândido Portinari", "Di Cavalcanti", "Alfredo Volpi", "Iberê Camargo",
    "Frans Krajcberg", "Tomie Ohtake", "Manabu Mabe", "Vik Muniz",
    "Oscar Niemeyer", "Lúcio Costa", "Paulo Mendes da Rocha", "Ruy Ohtake",
    "Sérgio Rodrigues", "Zanine Caldas", "Joaquim Tenreiro",
]

# ============================================================================
# SENTIMENTOS_ABSTRACOES (expandido)
# ============================================================================
SENTIMENTOS_ABSTRACOES = [
    "amor", "amizade", "felicidade", "superação", "resiliência", "empatia",
    "solidariedade", "esperança", "liberdade", "justiça", "igualdade",
    "respeito", "tolerância", "diversidade", "inclusão", "sustentabilidade",
    "inovação", "criatividade", "empreendedorismo", "liderança", "coragem",
    "persistência", "sonhos", "metas", "desafios", "sabedoria", "humildade",
    "gratidão", "generosidade", "compaixão", "honestidade", "transparência",
    "responsabilidade", "compromisso",
    # Novos
    "autoconhecimento", "mindfulness", "resiliência emocional", "inteligência emocional",
    "ética", "cidadania", "fraternidade", "solidão", "angústia", "medo",
    "alegria", "tristeza", "raiva", "ciúmes", "inveja", "orgulho",
    "vergonha", "culpa", "remorso", "perdão", "paz interior", "equilíbrio",
    "confiança", "autoestima", "autocontrole", "autocompaixão",
]

# ============================================================================
# CONCEITOS (expandido)
# ============================================================================
CONCEITOS = [
    "cultura brasileira", "história do Brasil", "geografia brasileira",
    "economia brasileira", "política brasileira", "meio ambiente",
    "educação", "saúde", "tecnologia", "arte", "música", "literatura",
    "culinária", "turismo", "esportes", "religião", "filosofia",
    "direitos humanos", "ciência", "inovação", "folclore",
    "expressões populares", "biomas", "cidades", "mitologia",
    "democracia", "capitalismo", "socialismo", "comunismo",
    "sotaque", "dialeto", "gíria", "linguagem", "comunicação",
    # Novos
    "mestiçagem", "sincretismo", "cultura afro-brasileira", "cultura indígena",
    "cultura caipira", "cultura nordestina", "cultura sulista", "cultura amazônica",
    "feijoada", "capoeira", "samba", "bossa nova", "forró", "frevo", "maracatu",
    "carnaval", "festas juninas", "Natal", "Ano Novo", "Festa do Divino",
    "Bumba meu boi", "Cavalo Marinho", "Reisado", "Folia de Reis",
    "patrimônio histórico", "patrimônio cultural", "museu", "arquivo",
    "biblioteca", "acervo", "documento histórico",
]

# ============================================================================
# CONHECIMENTO (expandido)
# ============================================================================
CONHECIMENTO = [
    "matemática", "filosofia", "história", "física", "biologia",
    "programação", "lógica", "estatística", "economia", "linguística",
    "química", "geometria", "álgebra", "cálculo", "genética",
    "astronomia", "geologia", "psicologia", "sociologia", "antropologia",
    # Novos
    "neurociência", "ciência cognitiva", "inteligência artificial", "machine learning",
    "big data", "cloud computing", "segurança cibernética", "blockchain",
    "robótica", "automação", "biotecnologia", "nanotecnologia",
    "ciência dos materiais", "engenharia ambiental", "energia renovável",
    "arquitetura", "urbanismo", "design", "moda", "gastronomia",
    "enologia", "mixologia", "perfumaria", "cosmetologia",
]

# ============================================================================
# PROFISSOES (expandido)
# ============================================================================
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
    # Novos
    "psiquiatra", "neurologista", "cardiopata", "otorrino", "oftalmologista",
    "ginecologista", "obstetra", "pediatra", "geriatra", "oncologista",
    "anestesista", "radiologista", "patologista", "clínico geral",
    "advogado trabalhista", "advogado cível", "advogado criminalista",
    "juiz", "promotor", "defensor público", "delegado",
    "cientista político", "diplomata", "relações internacionais",
    "tradutor", "intérprete", "linguista", "fonoaudiólogo",
    "antropólogo", "arqueólogo", "historiador", "geógrafo",
    "museólogo", "bibliotecário", "arquivista",
]

# ============================================================================
# ARTE_CULTURA (expandido)
# ============================================================================
ARTE_CULTURA = [
    "cinema", "música", "teatro", "pintura", "escultura",
    "literatura", "fotografia", "dança", "arte digital", "poesia",
    "graffiti", "tatuagem", "arte sacra", "arte abstrata", "realismo",
    "surrealismo", "modernismo", "barroco", "renascimento", "arte contemporânea",
    # Novos
    "arte indígena", "arte afro-brasileira", "arte popular", "arte naïf",
    "instalação", "performance", "videoarte", "arte conceitual",
    "fotografia documental", "fotojornalismo", "cinema novo", "Cinema Marginal",
    "teatro de bonecos", "teatro de rua", "teatro do oprimido",
    "dança contemporânea", "balé clássico", "dança de salão", "forró",
    "música clássica", "música erudita", "música popular", "MPB",
    "samba", "choro", "bossa nova", "tropicalismo", "rock brasileiro",
]

# ============================================================================
# CIENCIA_TECNOLOGIA (expandido)
# ============================================================================
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
    # Novos
    "Internet das Coisas (IoT)", "cidades inteligentes", "casas conectadas",
    "wearables", "telemedicina", "educação a distância", "gamificação",
    "metaverso", "NFT", "Web3", "DeFi", "smart contracts",
    "robótica móvel", "drone autônomo", "veículo autônomo",
]

# ============================================================================
# ACOES (expandido)
# ============================================================================
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
    # Novos
    "emprestar", "doar", "voluntariar", "cooperar", "participar",
    "observar", "refletir", "meditar", "respirar", "relaxar",
    "jogar", "brincar", "competir", "cooperar", "celebrar",
]

# ============================================================================
# ALIMENTOS (expandido)
# ============================================================================
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
    # Novos
    "castanha", "noz", "amendoim", "pistache", "amêndoa",
    "leite condensado", "doce de leite", "cocada", "queijadinha", "cartola",
    "torta de limão", "torta de morango", "torta de nozes",
    "risoto", "polenta", "gnocchi", "lasanha", "espaguete",
    "moqueca", "ensopado", "cozido", "ensopado de carne",
    "salpicão", "maionese", "vinagrete", "farofa", "couve à mineira",
]

# ============================================================================
# ANIMAIS (expandido)
# ============================================================================
ANIMAIS = [
    "cachorro", "gato", "leão", "tigre", "elefante",
    "pássaro", "peixe", "cavalo", "lobo", "urso",
    "golfinho", "baleia", "águia", "cobra", "tubarão",
    "borboleta", "formiga", "abelha", "macaco", "panda",
    "girafa", "hipopótamo", "rinoceronte", "zebra", "camelo",
    "pinguim", "foca", "leão-marinho", "tartaruga", "crocodilo",
    # Novos
    "arara", "tucano", "papagaio", "beija-flor", "sabiá",
    "onça-pintada", "suçuarana", "jaguatirica", "veado", "capivara",
    "lontra", "ariranha", "boto cor-de-rosa", "peixe-boi", "tamanduá",
    "tatu", "tatu-bola", "cutia", "paca", "cotia",
    "quati", "gambá", "morcego", "coruja", "urubu",
    "jabuti", "cágado", "tartaruga-da-amazônia", "iguana", "jacaré",
]

# ============================================================================
# TRANSPORTE (expandido)
# ============================================================================
TRANSPORTE = [
    "carro", "ônibus", "avião", "bicicleta", "trem",
    "navio", "metrô", "moto", "caminhão", "helicóptero",
    "trator", "skate", "patins", "barco", "submarino",
    "foguete", "teleférico", "bondinho", "carroça", "jetski",
    # Novos
    "VLT", "bonde", "trólebus", "scooter", "monociclo",
    "hoverboard", "segway", "automóvel elétrico", "carro híbrido",
    "carro autônomo", "drone de entrega", "barco a vela",
    "iate", "lancha", "catamarã", "hidrofólio",
]

# ============================================================================
# SOCIEDADE_POLITICA (expandido)
# ============================================================================
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
    # Novos
    "política de cotas", "ações afirmativas", "igualdade de gênero",
    "direitos LGBTQ+", "política de drogas", "aborto", "eutanásia",
    "pena de morte", "prisão perpétua", "política de imigração",
    "refugiados", "asilo", "cidadania global", "ONU", "UNESCO",
    "Mercosul", "UE", "OTAN", "BRICS", "G20",
]

# ============================================================================
# NATUREZA_UNIVERSO (expandido)
# ============================================================================
NATUREZA_UNIVERSO = [
    "floresta", "oceano", "montanha", "rio", "deserto",
    "planeta", "estrela", "galáxia", "clima", "ecossistema",
    "lua", "sol", "buraco negro", "supernova", "aurora boreal",
    "coral", "geologia", "atmosfera", "gravidade", "matéria escura",
    "asteroide", "cometa", "meteoro", "satélite natural", "constelação",
    # Novos
    "vulcão", "terremoto", "tsunami", "furacão", "tornado",
    "ciclone", "monção", "El Niño", "La Niña",
    "ecossistema marinho", "recife de coral", "manguezal", "pântano",
    "caverna", "geleira", "calota polar", "permafrost",
    "biosfera", "hidrosfera", "litosfera", "atmosfera",
    "exoplaneta", "anã marrom", "gigante gasoso", "nébula",
    "aglomerado estelar", "quasar", "pulsar",
]

# ============================================================================
# MUSICAS_BANDAS_CANTORES (expandido)
# ============================================================================
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
    # Novos
    "Lenine", "Vanessa da Mata", "Maria Gadú", "Céu", "Mallu Magalhães",
    "Seu Jorge", "Música popular brasileira", "Instrumental", "Pixinguinha",
    "Hermeto Pascoal", "Egberto Gismonti", "Toninho Horta", "Hamilton de Holanda",
    "Yamandu Costa", "Baden Powell", "João Gilberto", "Stan Getz",
    "Tom Zé", "Arnaldo Antunes", "Carlinhos Brown", "Marisa Monte",
    "Nando Reis", "Samuel Rosa", "Chico César", "Mestre Ambrósio",
    "Cordel do Fogo Encantado", "Nação Zumbi", "Mangue Beat",
]

# ============================================================================
# SINTOMAS_DOENCAS (expandido)
# ============================================================================
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
    # Novos
    "Lúpus", "artrite reumatoide", "esclerose múltipla", "mal de Parkinson",
    "Alzheimer", "demência", "AVC", "infarto", "arritmia",
    "hepatite A", "hepatite B", "hepatite C", "cirrose", "esteatose",
    "obesidade", "anorexia", "bulimia", "transtorno bipolar",
    "esquizofrenia", "TDAH", "autismo", "Síndrome de Down",
]

# ============================================================================
# DECLARACOES_PESSOAS_FAMOSAS (mantido)
# ============================================================================
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
]

# ============================================================================
# DATAS_HISTORICAS (expandido)
# ============================================================================
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
    # Novos
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
]

# ============================================================================
# GEOPOLITICA (expandido)
# ============================================================================
GEOPOLITICA = [
    "União Europeia", "OTAN", "ONU", "Mercosul", "BRICS",
    "Conflito entre Israel e Palestina", "Guerra na Ucrânia",
    "Crise migratória na Europa", "Aquecimento global",
    "Acordos de Paris", "Reforma da ONU", "Nova Ordem Mundial",
    "Império Americano", "Ascensão da China", "Guerra Fria 2.0",
    "Ciberguerra", "Espionagem internacional", "Diplomacia",
    # Novos
    "Organização dos Estados Americanos", "União Africana", "Liga Árabe",
    "Conselho de Segurança da ONU", "Corte Internacional de Justiça",
    "Tribunal Penal Internacional", "Tratado de Não Proliferação Nuclear",
    "Acordo de Paris", "Protocolo de Kyoto", "Conferência das Nações Unidas sobre Mudança Climática",
    "Cúpula do G7", "Cúpula do G20", "Fórum Econômico Mundial",
    "Banco Mundial", "FMI", "OMC", "BID",
    "América Latina", "Ásia-Pacífico", "Oriente Médio", "África Subsariana",
]

# ============================================================================
# CIENCIA (expandido)
# ============================================================================
CIENCIA = [
    "física quântica", "biologia molecular", "astrofísica", "genética", "evolução",
    "termodinâmica", "relatividade", "mecânica quântica", "cosmologia", "neurociência",
    "ecologia", "paleontologia", "mineralogia", "oceanografia", "meteorologia",
    # Novos
    "astronomia", "ciência de materiais", "ciência dos polímeros",
    "ciência dos alimentos", "ciência do solo", "ciências agrárias",
    "engenharia genética", "biologia sintética", "criogenia",
    "física de partículas", "física nuclear", "física da matéria condensada",
]

# ============================================================================
# HISTORIA (expandido)
# ============================================================================
HISTORIA = [
    "Revolução Francesa", "Império Romano", "Descobrimentos", "Segunda Guerra Mundial",
    "Idade Média", "Renascimento", "Guerra Fria", "Revolução Industrial",
    "Independência dos EUA", "Unificação da Itália", "Queda do Muro de Berlim",
    # Novos
    "Idade Antiga", "Antigo Egito", "Grécia Antiga", "Civilização Maia",
    "Civilização Inca", "Civilização Asteca", "Império Mongol",
    "Império Bizantino", "Império Otomano", "Império Persa",
    "Guerra dos Cem Anos", "Guerra das Rosas", "Revolução Gloriosa",
    "Revolução Americana", "Revolução Cubana", "Revolução Mexicana",
    "Primeira Guerra Mundial", "Guerra do Vietnã", "Guerra da Coreia",
    "Guerra das Malvinas", "Conflito do Golfo", "Guerra do Iraque",
]

# ============================================================================
# FILOSOFIA (expandido)
# ============================================================================
FILOSOFIA = [
    "existencialismo", "estoicismo", "utilitarismo", "fenomenologia",
    "materialismo", "idealismo", "niilismo", "absurdismo",
    "contratualismo", "liberalismo", "anarquismo", "marxismo",
    # Novos
    "platonismo", "aristotelismo", "tomismo", "cartesianismo",
    "kantianismo", "hegelianismo", "positivismo", "empirismo",
    "racionalismo", "ceticismo", "epicurismo", "hedonismo",
    "estruturalismo", "pós-estruturalismo", "desconstrução",
    "hermenêutica", "fenomenologia existencial",
]

# ============================================================================
# LITERATURA (expandido MASSIVAMENTE)
# ============================================================================
LITERATURA = [
    "realismo", "modernismo", "barroco", "romantismo", "classicismo",
    "naturalismo", "simbolismo", "futurismo", "dadaísmo", "surrealismo",
    # Novos (brasileiros)
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
    # Literatura internacional variada
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
    # Autores e movimentos
    "Machado de Assis", "Clarice Lispector", "Guimarães Rosa", "Graciliano Ramos",
    "Jorge Amado", "Érico Veríssimo", "José Lins do Rego", "Raquel de Queiroz",
    "Aluísio Azevedo", "Joaquim Manuel de Macedo", "José de Alencar",
    "Bernardo Guimarães", "Alfredo d'Escragnolle Taunay", "Visconde de Taunay",
    "Coelho Neto", "Lima Barreto", "Mário de Andrade", "Oswald de Andrade",
    "Carlos Drummond de Andrade", "Cecília Meireles", "João Cabral de Melo Neto",
    "Ferreira Gullar", "Adélia Prado", "Rubem Braga", "Nelson Rodrigues",
]

# ============================================================================
# ECONOMIA (expandido)
# ============================================================================
ECONOMIA = [
    "inflação", "taxa de juros", "PIB", "dívida pública", "câmbio",
    "bolsa de valores", "investimentos", "poupança", "crédito", "orçamento",
    "política fiscal", "política monetária", "comércio exterior", "exportação", "importação",
    # Novos
    "microeconomia", "macroeconomia", "economia do trabalho", "economia da educação",
    "economia da saúde", "economia ambiental", "economia solidária",
    "capitalismo", "socialismo", "liberalismo", "keynesianismo",
    "neoliberalismo", "desenvolvimento sustentável",
    "renda básica universal", "imposto de renda", "tributação",
    "desigualdade econômica", "pobreza", "exclusão social",
]

# ============================================================================
# ESPORTES (expandido)
# ============================================================================
ESPORTES = [
    "futebol", "basquete", "vôlei", "natação", "atletismo",
    "tênis", "golfe", "ciclismo", "esportes radicais", "olímpiadas",
    "copa do mundo", "campeonato brasileiro", "NBA", "Fórmula 1", "MMA",
    # Novos
    "surfe", "skate", "snowboard", "esqui", "patinação no gelo",
    "ginástica artística", "ginástica rítmica", "judô", "karatê",
    "taekwondo", "boxe", "luta livre", "esgrima",
    "hipismo", "tiro esportivo", "arco e flecha",
    "triatlo", "pentatlo", "maratona", "ultramaratona",
    "esportes eletrônicos", "e-sports",
]

# ============================================================================
# MITOLOGIA (expandido)
# ============================================================================
MITOLOGIA = [
    "mitologia grega", "mitologia nórdica", "mitologia egípcia", "mitologia celta",
    "deuses do Olimpo", "Thor", "Zeus", "Ísis", "Cthulhu", "lendas brasileiras",
    "saci", "curupira", "boitatá", "iara", "boto cor-de-rosa",
    # Novos
    "mitologia japonesa", "mitologia chinesa", "mitologia hindu",
    "mitologia maia", "mitologia asteca", "mitologia inca",
    "mitologia tupi", "mitologia guarani", "mitologia africana",
    "criaturas míticas", "dragões", "unicórnios", "grifos",
    "fênix", "cérbero", "medusa", "sereias",
]

# ============================================================================
# CIENCIAS_SOCIAIS (expandido)
# ============================================================================
CIENCIAS_SOCIAIS = [
    "sociologia", "antropologia", "ciência política", "psicologia social",
    "comunicação", "educação", "trabalho", "família", "desigualdade", "movimentos sociais",
    # Novos
    "teoria crítica", "pós-modernismo", "estudos de gênero", "estudos raciais",
    "identidade", "cultura", "globalização", "transnacionalismo",
    "políticas públicas", "gestão social", "terceiro setor",
    "ONG", "movimento negro", "movimento feminista", "movimento LGBTQ+",
    "indigenismo", "quilombolas", "caiçaras", "ribeirinhos",
]

# ============================================================================
# FILMES (expandido)
# ============================================================================
FILMES = [
    "O Poderoso Chefão", "Cidadão Kane", "Casablanca", "E o Vento Levou", "O Mágico de Oz",
    "Star Wars", "Titanic", "Avatar", "Vingadores: Ultimato", "O Senhor dos Anéis",
    "Matrix", "Clube da Luta", "Pulp Fiction", "A Origem", "Interestelar",
    "O Iluminado", "Laranja Mecânica", "2001: Uma Odisséia no Espaço",
    # Novos (nacionais e mais internacionais)
    "Deus e o Diabo na Terra do Sol", "O Bandido da Luz Vermelha", "Macunaíma",
    "Terra em Transe", "Cidade de Deus", "O Auto da Compadecida", "Central do Brasil",
    "Que horas ela volta?", "Aquarius", "O Som ao Redor", "Bacurau",
    "A Vida é Bela", "A Lista de Schindler", "O Paciente Inglês",
    "Os Intocáveis", "A Teoria de Tudo", "O Jogo da Imitação",
    "Django Livre", "Kill Bill", "Bastardos Inglórios",
    "Era uma Vez em Hollywood", "O Irlandês",
]

# ============================================================================
# SERIES (expandido)
# ============================================================================
SERIES = [
    "Game of Thrones", "Breaking Bad", "The Sopranos", "Friends", "The Office",
    "Stranger Things", "The Crown", "The Mandalorian", "WandaVision",
    "Dark", "The Witcher", "Supernatural", "The Walking Dead",
    # Novos
    "The Last of Us", "House of the Dragon", "Better Call Saul",
    "The Boys", "The Umbrella Academy", "Sex Education",
    "Brooklyn Nine-Nine", "Parks and Recreation", "The Good Place",
    "Ozark", "Mindhunter", "True Detective", "Fargo",
    "This Is Us", "This is England", "Skins",
    "Narcos", "Narcos: México", "La Casa de Papel",
    "O Mecanismo", "A Divisão", "Sob Pressão", "3%",
]

# ============================================================================
# LIVROS (expandido - já incluído em LITERATURA, mas mantemos separado para compatibilidade)
# ============================================================================
LIVROS = [
    "Dom Casmurro", "Grande Sertão: Veredas", "Memórias Póstumas de Brás Cubas",
    "O Alquimista", "O Pequeno Príncipe", "1984", "A Revolução dos Bichos",
    "O Senhor dos Anéis", "Harry Potter", "A Menina que Roubava Livros",
    # Novos
    "Cem Anos de Solidão", "O Amor nos Tempos do Cólera", "Crônica de uma Morte Anunciada",
    "A Casa dos Espíritos", "A Saga de Kane e Abel", "O Nome da Rosa",
    "O Código Da Vinci", "O Caçador de Pipas", "A Lista de Schindler",
    "O Diário de Anne Frank", "Siddhartha", "Demian", "O Estrangeiro",
    "O Processo", "A Metamorfose", "Ulisses", "O Grande Gatsby",
    "Por Quem os Sinos Dobram", "O Velho e o Mar", "A Peste",
    "O Silêncio dos Inocentes", "O Iluminado", "O Exorcista",
    "O Filho Eterno", "A Elite do Atraso", "O Avesso da Pele",
    "Torto Arado",
]

# ============================================================================
# PERSONAGENS_FICTICIOS (expandido)
# ============================================================================
PERSONAGENS_FICTICIOS = [
    "Sherlock Holmes", "Harry Potter", "Luke Skywalker", "Darth Vader",
    "Gandalf", "Frodo", "Hermione Granger", "Don Corleone",
    "Macunaíma", "Capitu", "Dom Quixote", "Hamlet",
    # Novos
    "Bentinho", "Brás Cubas", "Riobaldo", "Diadorim", "Gabriela",
    "Pedro Bala", "Professor", "Quincas Berro d'Água",
    "Batman", "Superman", "Mulher Maravilha", "Coringa",
    "Homem-Aranha", "Capitão América", "Homem de Ferro",
    "Harry Potter", "Ron Weasley", "Hermione Granger", "Dumbledore",
    "Voldemort", "Hagrid", "Snape", "Gollum",
]

# ============================================================================
# TECNOLOGIAS_EMERGENTES (expandido)
# ============================================================================
TECNOLOGIAS_EMERGENTES = [
    "metaverso", "NFTs", "Web3", "deFi", "blockchain",
    "inteligência artificial generativa", "GPT-4", "Stable Diffusion",
    "veículos autônomos", "cidades inteligentes", "energia renovável",
    # Novos
    "computação quântica", "quantum computing", "cibernética",
    "robótica colaborativa", "exoesqueletos", "próteses biônicas",
    "impressão 4D", "materiais inteligentes", "nanorrobôs",
    "baterias de estado sólido", "supercapacitores",
    "rede 6G", "internet satelital", "Starlink",
]

# ============================================================================
# EVENTOS_HISTORICOS_BRASIL (expandido)
# ============================================================================
EVENTOS_HISTORICOS_BRASIL = [
    "Revolta da Chibata", "Revolução Constitucionalista de 1932", "Guerra do Contestado",
    "Revolta dos Malês", "Independência da Bahia", "Confederação dos Tamoios",
    "Guerra dos Farrapos", "Revolução de 1930", "Governo de Getúlio Vargas",
    "Descoberta do ouro em Minas Gerais", "Construção de Brasília",
    # Novos
    "Batalha de Guararapes", "Invasão holandesa no Nordeste", "Expedição de Cabeza de Vaca",
    "Fundação de São Paulo", "Fundação do Rio de Janeiro", "Fundação de Salvador",
    "Jornadas de Junho de 2013", "Ocupações secundaristas de 2015",
    "Greve geral de 1917", "Greve dos 300 mil de 1979",
    "Novo Código Civil", "Lei de Anistia",
]

# ============================================================================
# SAUDACOES (prontas)
# ============================================================================
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
    ("Pode falar mais devagar?", "Claro! Vou falar mais devagar para você entender melhor."),
    ("Fala mais alto!", "Desculpe, vou aumentar o volume."),
    ("Você está aí?", "Estou sim! Sempre por aqui."),
    ("Você fala outras línguas?", "Falo português e também entendo um pouco de inglês e espanhol."),
    ("Você sabe programar?", "Sei um pouco sobre programação, mas meu forte é responder perguntas."),
    ("Você gosta de música?", "Gosto de todos os tipos! Qual o seu estilo favorito?"),
    ("Você assiste filmes?", "Não assisto, mas posso falar sobre muitos filmes se você quiser."),
    ("Você sabe cozinhar?", "Não fisicamente, mas posso te dar receitas maravilhosas!"),
    ("Tchau!", "Tchau! Até logo, foi um prazer conversar."),
    ("Até mais!", "Até mais! Se precisar, estarei aqui."),
    ("Foi bom falar com você.", "Foi ótimo falar com você também! Volte sempre."),
    ("Me ajuda com uma coisa?", "Com certeza! Pode falar."),
    ("Estou com uma dúvida.", "Então vamos resolvê-la! Me diga qual é a dúvida."),
    ("Preciso de sua ajuda.", "Estou aqui para ajudar. Me diga o que você precisa."),
    ("Você pode me ouvir?", "Estou ouvindo atentamente. Pode falar."),
    ("Estou precisando conversar.", "Pode contar comigo. Estou aqui para ouvir."),
]

# ============================================================================
# CATEGORIAS_LISTAS (agrupa todas as listas)
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
    "livros": LIVROS,
    "personagens_ficticios": PERSONAGENS_FICTICIOS,
    "tecnologias_emergentes": TECNOLOGIAS_EMERGENTES,
    "eventos_historicos_brasil": EVENTOS_HISTORICOS_BRASIL,
}

# ============================================================================
# GRUPOS DE CATEGORIAS (para perguntas combinadas)
# ============================================================================
GRUPOS_CATEGORIAS = {
    "historia": [
        "datas_historicas", "eventos_historicos_brasil", "historia", "geopolitica"
    ],
    "ciencia": [
        "ciencia", "ciencia_tecnologia", "natureza_universo", "conhecimento"
    ],
    "cultura": [
        "arte_cultura", "literatura", "filmes", "series", "musica", "livros",
        "personagens_ficticios", "mitologia"
    ],
    "sociedade": [
        "sociedade_politica", "economia", "ciencias_sociais", "conceito", "sentimento"
    ],
    "vida": [
        "alimento", "animal", "transporte", "objeto", "profissao", "acao",
        "sintomas_doencas"
    ],
    "pessoas": [
        "pessoa", "declaracoes_pessoas_famosas"
    ],
}

# ============================================================================
# PREFIXOS POR CATEGORIA (mantidos)
# ============================================================================
PREFIXOS_POR_CATEGORIA = {
    "objeto": [
        "Para que serve", "Como funciona", "Do que é feito", "Qual a utilidade de",
        "Como usar", "O que é", "Como escolher", "Qual a diferença entre",
        "Quais os benefícios de", "Que tipos de", "Qual a origem de",
        "Como conservar", "Como limpar", "Onde comprar",
    ],
    "lugar": [
        "Onde fica", "Como é", "O que tem em", "Qual a importância de",
        "Como chegar em", "Onde se localiza", "Qual a história de",
        "Quais as principais atrações", "Que clima predomina em",
        "Por que visitar", "Quais os costumes de",
    ],
    "pessoa": [
        "Quem foi", "Quem é", "Qual a contribuição de", "O que fez",
        "Por que é famoso", "Qual a importância de", "Onde nasceu",
        "Como influenciou", "Em que área atuou", "Que obra deixou",
        "Por que é lembrado",
    ],
    "sentimento": [
        "O que é", "Qual a importância de", "Como alcançar", "Como lidar com",
        "Como desenvolver", "O que significa", "Por que é importante",
        "Quais os benefícios de", "Como cultivar", "Como expressar",
        "Como superar a falta de",
    ],
    "conceito": [
        "O que é", "Como funciona", "Qual a importância de", "Como surgiu",
        "O que significa", "Como se caracteriza", "Qual a origem de",
        "Como se manifesta", "Em que consiste", "Qual a relação com",
    ],
    "conhecimento": [
        "O que estuda", "Qual a importância de", "Como funciona", "O que é",
        "Para que serve", "Como surgiu", "Qual a aplicação de",
        "Quais os ramos de", "Quem criou", "Onde se aplica",
    ],
    "profissao": [
        "O que faz", "Qual a importância de", "O que estuda", "Como se tornar",
        "Qual a função de", "O que é necessário para ser",
        "Quais as habilidades de", "Quanto ganha", "Como é o mercado para",
        "O que faz um",
    ],
    "arte_cultura": [
        "O que é", "Como surgiu", "Qual a importância de", "O que caracteriza",
        "Como se manifesta", "Qual a origem de", "O que você sabe sobre",
        "Quais os principais representantes de", "Como impacta a sociedade",
    ],
    "ciencia_tecnologia": [
        "O que é", "Como funciona", "Qual a importância de", "Como surgiu",
        "Qual a aplicação de", "O que você sabe sobre", "Como impacta a sociedade",
        "Quais as vantagens de", "Quais os riscos de", "Como evoluiu",
    ],
    "acao": [
        "Como fazer", "Como praticar", "Qual a importância de", "Quais os benefícios de",
        "Como aprender", "Como começar", "Por que é importante",
        "Quais as técnicas de", "Como melhorar", "Como se preparar para",
    ],
    "alimento": [
        "Qual a origem de", "Como é feito", "Como preparar", "Qual a importância de",
        "O que contém", "Como armazenar", "Qual a história de",
        "Quais os benefícios de", "Como combinar", "Qual a receita de",
    ],
    "animal": [
        "O que é", "Como vive", "Onde vive", "Qual a importância de",
        "Como se reproduz", "O que come", "Quais as características de",
        "Qual o habitat de", "Como se comporta", "Quais as curiosidades sobre",
    ],
    "transporte": [
        "O que é", "Como funciona", "Para que serve", "Qual a importância de",
        "Como surgiu", "Qual a evolução de", "Onde é usado",
        "Quais as vantagens de", "Quais os tipos de", "Como escolher",
    ],
    "sociedade_politica": [
        "O que é", "Como funciona", "Qual a importância de", "Como surgiu",
        "O que significa", "Qual a relação com", "Como impacta a sociedade",
        "Quais os desafios de", "Quais os avanços em", "Como participar",
    ],
    "natureza_universo": [
        "O que é", "Como funciona", "Como se forma", "Qual a importância de",
        "Onde está", "Como surge", "Qual a composição de",
        "Como se estuda", "Quais as curiosidades sobre", "Como afeta a Terra",
    ],
    "musica": [
        "Quem é", "Qual a importância de", "Como surgiu", "O que caracteriza",
        "Qual o estilo de", "Quais as principais obras de",
        "Onde se apresentou", "Como influenciou a música",
    ],
    "sintomas_doencas": [
        "O que é", "Quais os sintomas de", "Como tratar", "Como prevenir",
        "Qual a causa de", "Quais as complicações de", "Como é diagnosticado",
    ],
    "datas_historicas": [
        "O que aconteceu em", "Qual a importância de", "Como foi o ano de",
        "O que marcou", "Qual o contexto de",
    ],
    "geopolitica": [
        "O que é", "Como funciona", "Qual a importância de", "Como surgiu",
        "Quais os desafios de", "Como impacta o mundo",
    ],
    "ciencia": [
        "O que é", "Como funciona", "Qual a importância de", "Quais os princípios de",
        "Como se aplica", "Quais as descobertas de",
    ],
    "historia": [
        "O que aconteceu em", "Qual a importância de", "Como foi",
        "Quais as causas de", "Quais as consequências de",
    ],
    "filosofia": [
        "O que é", "Qual a importância de", "Como surgiu",
        "Quais os principais pensadores de", "Como se aplica",
    ],
    "literatura": [
        "O que é", "Qual a importância de", "Como surgiu",
        "Quais os principais autores de", "Quais as obras de",
    ],
    "economia": [
        "O que é", "Como funciona", "Qual a importância de", "Quais os fatores que influenciam",
        "Como medir", "Qual a relação entre", "Quais os impactos de",
    ],
    "esportes": [
        "O que é", "Qual a importância de", "Como surgiu", "Quais as regras de",
        "Quem são os principais atletas de", "Qual a história de",
    ],
    "mitologia": [
        "O que é", "Quem é", "Qual a origem de", "Qual a importância de",
        "Quais as principais lendas de", "Como se caracteriza",
    ],
    "ciencias_sociais": [
        "O que é", "Como funciona", "Qual a importância de", "Quais os principais autores de",
        "Como se aplica", "Qual a relação com",
    ],
    "filmes": [
        "O que é", "Qual a importância de", "Como foi produzido", "Quem dirigiu",
        "Qual a história de", "Qual o elenco principal", "Quais as críticas sobre",
    ],
    "series": [
        "O que é", "Qual a importância de", "Como foi produzida", "Quem criou",
        "Qual a história de", "Qual o elenco principal", "Quais as temporadas",
    ],
    "livros": [
        "O que é", "Qual a importância de", "Como foi escrito", "Quem escreveu",
        "Qual a história de", "Qual o gênero", "Quais as principais obras do autor",
    ],
    "personagens_ficticios": [
        "Quem é", "Qual a importância de", "Como surgiu", "Em que obra aparece",
        "Qual o papel de", "Quais as características de",
    ],
    "tecnologias_emergentes": [
        "O que é", "Como funciona", "Qual a importância de", "Como surgiu",
        "Quais os desafios de", "Como impacta a sociedade",
    ],
    "eventos_historicos_brasil": [
        "O que aconteceu", "Qual a importância de", "Como foi", "Quem participou",
        "Qual o legado de", "Quando ocorreu",
    ],
}

# ============================================================================
# TEMPLATES EXTRAS (expandidos)
# ============================================================================
TEMPLATES_EXTRAS = {
    "objeto": [
        "Qual a finalidade de {assunto}", "Em que situações se usa {assunto}",
        "Que função tem {assunto}", "Por que {assunto} é importante no dia a dia",
        "Como escolher um bom {assunto}",
    ],
    "lugar": [
        "Que características tem {assunto}", "Por que {assunto} é conhecido",
        "Que importância tem {assunto}", "O que torna {assunto} especial",
        "Quais os pontos turísticos de {assunto}",
    ],
    "pessoa": [
        "Qual foi o papel de {assunto}", "Por que {assunto} ficou conhecido",
        "Que legado deixou {assunto}", "Como {assunto} influenciou a história",
        "Qual a principal obra de {assunto}",
    ],
    "sentimento": [
        "Como definir {assunto}", "Por que {assunto} faz diferença",
        "Como reconhecer {assunto}", "Como praticar {assunto}",
        "O que causa {assunto}",
    ],
    "conceito": [
        "Como explicar {assunto}", "Por que {assunto} importa",
        "Em que consiste {assunto}", "Como {assunto} se relaciona com a sociedade",
        "Quais os exemplos de {assunto}",
    ],
    "conhecimento": [
        "O que trata {assunto}", "Onde se aplica {assunto}",
        "Por que estudar {assunto}", "Quem contribuiu para {assunto}",
        "Como {assunto} evoluiu ao longo do tempo",
    ],
    "profissao": [
        "Como trabalha um {assunto}", "O que faz um {assunto}",
        "Quais são as funções de um {assunto}", "Como se tornar um bom {assunto}",
        "Qual a demanda por {assunto}",
    ],
    "arte_cultura": [
        "Como se entende {assunto}", "Por que {assunto} é importante",
        "Que marca deixou {assunto}", "Como {assunto} reflete a sociedade",
        "Quais as principais obras de {assunto}",
    ],
    "ciencia_tecnologia": [
        "Como se aplica {assunto}", "Qual problema {assunto} ajuda a resolver",
        "Que impacto tem {assunto}", "Como {assunto} está mudando o mundo",
        "Quais as tendências em {assunto}",
    ],
    "acao": [
        "Como praticar {assunto}", "Como começar a {assunto}",
        "Que benefício traz {assunto}", "Quais os desafios de {assunto}",
        "Como melhorar sua habilidade em {assunto}",
    ],
    "alimento": [
        "Como preparar {assunto}", "Qual a origem de {assunto}",
        "Como conservar {assunto}", "Quais os acompanhamentos para {assunto}",
        "Qual a receita tradicional de {assunto}",
    ],
    "animal": [
        "Como vive o {assunto}", "Onde vive o {assunto}",
        "O que come o {assunto}", "Quais os predadores do {assunto}",
        "Como o {assunto} se reproduz",
    ],
    "transporte": [
        "Como funciona o {assunto}", "Para que serve o {assunto}",
        "Onde se usa o {assunto}", "Quais as vantagens do {assunto}",
        "Como escolher o melhor {assunto}",
    ],
    "sociedade_politica": [
        "Como funciona {assunto}", "Qual a função de {assunto}",
        "Como {assunto} afeta a vida social", "Quais os debates sobre {assunto}",
        "Como a sociedade pode influenciar {assunto}",
    ],
    "natureza_universo": [
        "Como se forma {assunto}", "O que é {assunto}",
        "Como {assunto} afeta o planeta", "Por que {assunto} é importante para a vida",
        "Quais as curiosidades sobre {assunto}",
    ],
    "musica": [
        "Qual o estilo musical de {assunto}", "Quais as músicas famosas de {assunto}",
        "Como {assunto} revolucionou a música",
    ],
    "sintomas_doencas": [
        "Como identificar {assunto}", "Quais os primeiros sinais de {assunto}",
        "Como prevenir {assunto}", "Qual o tratamento para {assunto}",
    ],
    "datas_historicas": [
        "Por que {assunto} foi importante", "Qual o impacto de {assunto}",
        "Como {assunto} mudou o mundo",
    ],
    "geopolitica": [
        "Qual a importância de {assunto}", "Como {assunto} influencia o mundo",
        "Quais os desafios de {assunto}",
    ],
    "ciencia": [
        "Qual a importância de {assunto}", "Como {assunto} impacta a sociedade",
        "Quais as principais teorias de {assunto}",
    ],
    "historia": [
        "Qual o contexto de {assunto}", "Como {assunto} influenciou o presente",
    ],
    "filosofia": [
        "Como {assunto} se aplica ao dia a dia", "Quais as críticas a {assunto}",
    ],
    "literatura": [
        "Quais as características de {assunto}", "Como {assunto} influencia a cultura",
    ],
    "economia": [
        "Como a {assunto} afeta a vida das pessoas",
        "Quais os desafios da {assunto} no Brasil",
        "Qual a relação entre {assunto} e desenvolvimento",
    ],
    "esportes": [
        "Qual a importância do {assunto} na cultura brasileira",
        "Como o {assunto} contribui para a saúde",
        "Quais os principais eventos de {assunto}",
    ],
    "mitologia": [
        "Qual a influência da {assunto} na cultura atual",
        "Quais os personagens mais conhecidos da {assunto}",
        "Como a {assunto} explica fenômenos naturais",
    ],
    "ciencias_sociais": [
        "Como a {assunto} ajuda a entender a sociedade",
        "Quais as principais teorias da {assunto}",
        "Qual a importância da {assunto} na formação do cidadão",
    ],
    "filmes": [
        "Qual a importância de {assunto} para o cinema",
        "Como {assunto} influenciou a cultura pop",
        "Quais as principais cenas de {assunto}",
    ],
    "series": [
        "Qual a importância de {assunto} para a TV",
        "Como {assunto} evoluiu ao longo das temporadas",
        "Quais os personagens mais marcantes de {assunto}",
    ],
    "livros": [
        "Qual a importância de {assunto} na literatura",
        "Como {assunto} reflete a sociedade",
        "Quais as principais mensagens de {assunto}",
    ],
    "personagens_ficticios": [
        "Qual o papel de {assunto} na obra",
        "Como {assunto} representa valores humanos",
        "Quais as principais características de {assunto}",
    ],
    "tecnologias_emergentes": [
        "Como {assunto} vai mudar o mundo",
        "Quais os desafios éticos de {assunto}",
        "Qual o potencial de {assunto} para o futuro",
    ],
    "eventos_historicos_brasil": [
        "Qual o impacto de {assunto} na história do Brasil",
        "Como {assunto} moldou a identidade nacional",
        "Quais as lições de {assunto} para o presente",
    ],
}

# ============================================================================
# EXPORTAR PARA FACILITAR IMPORTAÇÃO
# ============================================================================
__all__ = [
    "OBJETOS", "LUGARES", "PESSOAS", "SENTIMENTOS_ABSTRACOES", "CONCEITOS",
    "CONHECIMENTO", "PROFISSOES", "ARTE_CULTURA", "CIENCIA_TECNOLOGIA",
    "ACOES", "ALIMENTOS", "ANIMAIS", "TRANSPORTE", "SOCIEDADE_POLITICA",
    "NATUREZA_UNIVERSO", "MUSICAS_BANDAS_CANTORES", "SINTOMAS_DOENCAS",
    "DECLARACOES_PESSOAS_FAMOSAS", "DATAS_HISTORICAS", "GEOPOLITICA",
    "CIENCIA", "HISTORIA", "FILOSOFIA", "LITERATURA", "ECONOMIA",
    "ESPORTES", "MITOLOGIA", "CIENCIAS_SOCIAIS", "FILMES", "SERIES",
    "LIVROS", "PERSONAGENS_FICTICIOS", "TECNOLOGIAS_EMERGENTES",
    "EVENTOS_HISTORICOS_BRASIL", "SAUDACOES",
    "CATEGORIAS_LISTAS", "GRUPOS_CATEGORIAS",
    "PREFIXOS_POR_CATEGORIA", "TEMPLATES_EXTRAS"
]