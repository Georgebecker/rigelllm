#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║  RigelSLM · Guardião de Cabeçalhos  (oculto · criptografado)         ║
║                                                                      ║
║  Executado implicitamente por:                                       ║
║    • setup      (setup.bat / setup.sh)                               ║
║    • treino     (treino.py / treinar_com_jsonl.py)                   ║
║    • dashboard  (dashboard/main.py)                                  ║
║                                                                      ║
║  Garante que README.md, INSTALL.md e o card de doação do             ║
║  dashboard mantenham o cabeçalho oficial (Autor · Licença ·          ║
║  Versão · Atualização + doações PIX / Buy Me a Coffee).              ║
║  Se for alterado/removido, restaura na hora.                         ║
║  Nunca quebra o fluxo principal — falhas são silenciosas.            ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent

# ─────────────────────────────────────────────────────────────────────
# Material criptografado (nunca armazenado em texto puro)
# Cifra: PBKDF2-SHA256 (150k iterações) + XOR + nonce, base64.
# ─────────────────────────────────────────────────────────────────────
_CIFRA_B64 = (
    "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"
)
_SENHA_HEX = "526967656c534c4d2d47656f726765484265636b65722d32303236"  # passphrase (hex)

# Marcadores que identificam o cabeçalho oficial já presente
_MARCADOR = "**Autor:** George Herman Becker · **Licença:** MIT · **Versão:** 1.0.0 · **Atualização:**"
_MARCADOR_DOACAO = "**Gostou do projeto? Apoie o desenvolvimento:**"
_PIX = "a8b68e14-edfe-4450-88f2-c2af4aca2a6c"
_BMC = "buymeacoffee.com/georgehbecker"

_ALVOS = ("README.md", "INSTALL.md")


def _decifrar() -> str:
    """Decifra o payload oficial embutido na cifra."""
    senha = bytes.fromhex(_SENHA_HEX).decode("utf-8")
    raw = base64.b64decode(_CIFRA_B64)
    salt, nonce, dados = raw[:16], raw[16:32], raw[32:]
    chave = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, 150_000, 64)
    fluxo = hashlib.sha256(nonce + chave).digest()
    fluxo = (fluxo * (len(dados) // len(fluxo) + 1))[: len(dados)]
    return bytes(a ^ b for a, b in zip(dados, fluxo)).decode("utf-8")


# ── Payload decifrado: cabeçalho dos docs + card/JS do dashboard ──────
_PAYLOAD = json.loads(_decifrar())
_CABECALHO = _PAYLOAD["header"]
_CARD = _PAYLOAD["card"]
_JS = _PAYLOAD["js"]

# Âncoras de inserção no base.html do dashboard
_ANCORA_CARD = """        <span x-text="isLightTheme ? 'Tema Alegre' : 'Tema Escuro'"></span>
      </button>"""
_ANCORA_JS = "      isLightTheme: localStorage.getItem('theme') === 'light',"


def _auto_ocultar() -> None:
    """Esconde o próprio arquivo no Windows (atributo oculto)."""
    if os.name == "nt":
        try:
            import subprocess
            subprocess.run(
                ["attrib", "+h", str(_RAIZ / ".rigel_guard.py")],
                check=False, capture_output=True,
            )
        except Exception:
            pass


def _eh_linha_cabecalho(linha: str) -> bool:
    """Linhas que pertencem ao cabeçalho (metadados/doação) e devem ser substituídas."""
    st = linha.strip()
    if not st:
        return False
    if st.startswith(("**Versão:**", "**Licença:**", "**Última atualização:**",
                      "**Arquivos de treino:**", "**PIX:**")):
        return True
    if st.startswith("**Autor:**") or "· **Licença:**" in st:
        return True
    if "**Gostou do projeto" in st or _BMC in st:
        return True
    if st.startswith("> 💚") or st.startswith("> - **") or "Contribua com um PIX" in st:
        return True
    return False


def _garantir_arquivo(caminho: Path) -> bool:
    """Garante o cabeçalho oficial no arquivo. Retorna True se houve alteração."""
    if not caminho.exists():
        return False
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    em_ordem = (
        _MARCADOR in texto and _MARCADOR_DOACAO in texto
        and _PIX in texto and _BMC in texto
    )
    if em_ordem:
        return False  # cabeçalho intacto

    linhas = texto.splitlines(keepends=True)
    idx_titulo = next((i for i, l in enumerate(linhas) if l.startswith("# ")), None)
    if idx_titulo is None:
        return False

    # Região de cabeçalho: entre o título e o primeiro "## " ou "---"
    limite = idx_titulo + 1
    while limite < len(linhas):
        st = linhas[limite].strip()
        if st.startswith("## ") or st.startswith("---"):
            break
        limite += 1

    # Remove linhas antigas/duplicadas de cabeçalho e normaliza espaços
    cabecalho = [l for l in linhas[idx_titulo + 1:limite] if not _eh_linha_cabecalho(l)]
    while cabecalho and not cabecalho[0].strip():
        cabecalho.pop(0)
    while cabecalho and not cabecalho[-1].strip():
        cabecalho.pop()

    resto = linhas[limite:]
    bloco = _CABECALHO.rstrip("\n") + "\n"
    novo = (
        linhas[: idx_titulo + 1]
        + ["\n", bloco, "\n"]
        + (["\n"] if cabecalho else [])
        + cabecalho
        + resto
    )
    caminho.write_text("".join(novo), encoding="utf-8")
    return True


def _remover_card(texto: str) -> str:
    """Remove o card de doação existente no HTML (qualquer versão)."""
    ini = texto.find("<!-- 💚 Card de doação")
    fim_link = texto.find("Buy Me a Coffee", ini) if ini != -1 else -1
    pos_a = texto.find("</a>", fim_link) if fim_link != -1 else -1
    pos_div = texto.find("</div>", pos_a) if pos_a != -1 else -1
    if ini == -1 or fim_link == -1 or pos_a == -1 or pos_div == -1:
        return texto  # não conseguiu delimitar — não remove
    return texto[:ini] + texto[pos_div + len("</div>"):]


def _remover_js(texto: str) -> str:
    """Remove o estado Alpine de doação existente."""
    linhas = [l for l in texto.splitlines(keepends=True)
              if not l.lstrip().startswith(("pixChave:", "pixCopiado:"))]
    texto = "".join(linhas)
    texto = re.sub(r"[ \t]*copiarPix\(\)\s*\{.*?\n[ \t]*\},", "", texto, flags=re.S)
    return texto


def _garantir_dashboard() -> bool:
    """Garante o card de doação + estado PIX no dashboard (base.html)."""
    alvo = _RAIZ / "dashboard" / "templates" / "base.html"
    if not alvo.exists():
        return False
    texto = alvo.read_text(encoding="utf-8", errors="replace")
    tem_card = "Apoie o RigelSLM" in texto and _BMC in texto and _PIX in texto
    tem_js = "copiarPix" in texto and "pixChave: '" + _PIX + "'" in texto
    if tem_card and tem_js:
        return False  # card e estado intactos

    alterado = False
    if not tem_card:
        texto = _remover_card(texto)
        if _ANCORA_CARD in texto:
            texto = texto.replace(_ANCORA_CARD, _ANCORA_CARD + "\n\n" + _CARD + "\n", 1)
            alterado = True
    if not tem_js:
        texto = _remover_js(texto)
        if _ANCORA_JS in texto:
            texto = texto.replace(_ANCORA_JS, _ANCORA_JS + "\n" + _JS, 1)
            alterado = True

    if alterado:
        alvo.write_text(texto, encoding="utf-8")
    return alterado


def _verificar() -> bool:
    """Verifica/restaura cabeçalhos e o card de doação do dashboard."""
    alterado = False
    for nome in _ALVOS:
        if _garantir_arquivo(_RAIZ / nome):
            alterado = True
    if _garantir_dashboard():
        alterado = True
    return alterado


# ── Executa sempre (direto, via exec dos hooks ou por import) ─────────
try:
    _auto_ocultar()
    _verificar()
except Exception:
    pass
