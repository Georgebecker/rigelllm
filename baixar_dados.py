import requests
from bs4 import BeautifulSoup
import os
import time
from urllib.parse import urljoin

PASTA_DADOS = "dados"
os.makedirs(PASTA_DADOS, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}

#==============================
#CONFIGURAÇÕES
#==============================

MAX_PAGINAS = 999
MAX_PROFUNDIDADE = 3
DELAY = 1

visitados = set()
contador_arquivo = 0

# ==============================
# LIMPAR TEXTO
# ==============================

def limpar_texto(texto):
    texto = texto.replace("\n", " ")
    texto = texto.replace("\xa0", " ")
    return texto.strip()

# ==============================
# EXTRAIR TEXTO
# ==============================

def extrair_texto(soup):
    paragrafos = soup.find_all("p")
    textos = []

    for p in paragrafos:
        t = p.get_text().strip()
        if len(t) > 50:
            textos.append(t)

    return limpar_texto("\n".join(textos))

# ==============================
# SALVAR TEXTO
# ==============================

def salvar_texto(texto):
    global contador_arquivo

    if contador_arquivo >= MAX_PAGINAS:
        return

    if len(texto) < 500:
        print("⚠️ Texto pequeno ignorado")
        return

    caminho = os.path.join(PASTA_DADOS, f"crawl_{contador_arquivo}.txt")

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)

    print(f"✔ [{contador_arquivo}/{MAX_PAGINAS}] Salvo: {caminho} ({len(texto)} chars)")

    contador_arquivo += 1

# ==============================
# EXTRAIR LINKS (SÓ PORTUGUÊS)
# ==============================

def extrair_links(soup, base_url):
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        url = urljoin(base_url, href)

        if not url.startswith("http"):
            continue

        if "pt.wikipedia.org" not in url:
            continue

        # evita páginas inúteis
        if any(x in url for x in ["#", "Especial:", "Ajuda:", "Portal:", "Categoria:"]):
            continue

        links.append(url)

    return links

# ==============================
# CRAWLER
# ==============================

def crawl(url, profundidade):

    global contador_arquivo

    if url in visitados:
        return

    if len(visitados) >= MAX_PAGINAS:
        return

    if profundidade > MAX_PROFUNDIDADE:
        return

    if "pt.wikipedia.org" not in url:
        return

    print(f"\n🌐 [{len(visitados)}/{MAX_PAGINAS}] Visitando: {url}")
    visitados.add(url)

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        # 🔴 CORREÇÃO DE IDENTAÇÃO AQUI
        html_tag = soup.find("html")
        lang = html_tag.get("lang") if html_tag else None

        if not lang or "pt" not in str(lang):
            print("⚠️ Página não está em português, ignorando")
            return

        texto = extrair_texto(soup)
        salvar_texto(texto)

        links = extrair_links(soup, url)

        time.sleep(DELAY)

        for link in links:
            if len(visitados) >= MAX_PAGINAS:
                break

            crawl(link, profundidade + 1)

    except Exception as e:
        print(f"❌ Erro: {e}")

# ==============================
# EXECUÇÃO
# ==============================

if __name__ == "__main__":

    URL_INICIAL = "https://pt.wikipedia.org/wiki/Brasil"

    print("\n=== INICIANDO CRAWLER PT-BR ===\n")

    crawl(URL_INICIAL, 0)

    print("\n=== FINALIZADO ===\n")