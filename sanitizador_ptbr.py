#!/usr/bin/env python
# -*- coding: utf-8 -*-
# ============================================================================
# sanitizador_ptbr.py — PORTÃO DE QUALIDADE DE DADOS (regra de ouro 05/08)
# ============================================================================
# Ciclo obrigatório p/ TODO dataset baixado: TESTAR -> VERIFICAR -> TRATAR ->
# VISUALIZAR -> PROMOVER. Este módulo é o núcleo do TRATAR: deixa o conteúdo
# 100% português brasileiro (padrão ABNT2), em lotes, com relatório.
#
# O que faz, em ordem:
#   1. corrigir_mojibake_inteligente(): corrige mojibake POR OCORRÊNCIA
#      (Ã©->é, Ã£->ã, â€œ->" ...) — fecha a lacuna do _corrigir_mojibake do
#      createjsonl.py, que tenta a string INTEIRA e falha quando o texto tem
#      aspas/travessão (chars fora do latin-1).
#   2. remover_invalidos(): remove CIRURGICAMENTE caracteres que NÃO existem
#      no português/ABNT2 (Ă İ Ħ ķ U+FFFD etc.) — só o char estranho.
#   3. avaliar_conteudo(): decide OK / corrigido / DESCARTAR (vazio ou com
#      excesso de lixo).
#
# Uso:
#   python sanitizador_ptbr.py --self-test               # demonstração
#   python sanitizador_ptbr.py <arquivo.jsonl>           # 1 arquivo
#   python sanitizador_ptbr.py <pasta> [--saida dir]     # pasta em lotes
#   python sanitizador_ptbr.py <arquivo> --saida saida.jsonl
# ============================================================================

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

# Garante UTF-8 no console (cp1252 do Windows quebra com acentos/emojis)
for _stream in (sys.stdout, sys.stderr):
    _reconf = getattr(_stream, "reconfigure", None)
    if callable(_reconf):
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ============================================================================
# 1. REPERTÓRIO ABNT2 (caracteres VÁLIDOS no português brasileiro)
# ============================================================================
ABNT2_ACEITOS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "áàâãäéèêëíìîïóòôõöúùûüç"
    "ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ"
    "0123456789"
    # ABNT2: underscore (shift+hífen), superscripts ¹²³, ordinal ªº, ¬, §, °, £, ¢
    ".,;:!?()[]{}“”\"''‘’«»‹›-–—…/\\|@#$%&*+=<>~^`°ªº§¬_¹²³"
    " \t\r\n"
    "©®™€$£¥¢"
)

# Padrão de mojibake latin-1: sequência de 2+ caracteres U+0080-U+00FF que,
# re-codificada como latin-1 e decodificada como UTF-8, forma texto válido.
# Pega exatamente os casos C3xx (Ã©=é) e C2xx (Â©=©) sem tocar em acentos
# legítimos isolados (é, ã, ç...) nem em pares inválidos.
_RE_RUN_LATIN1 = re.compile(r"[\u0080-\u00ff]{2,}")

# Padrão de mojibake cp1252: "â€X" = bytes E2 80 XX (aspas "", travessão —,
# apóstrofo ', reticências …, etc.). O € (U+20AC) fica FORA do intervalo
# latin-1, por isso este padrão é tratado separadamente.
_RE_CP1252 = re.compile(
    r"\u00e2\u20ac[\u0080-\u00bf\u0152\u0153\u0160\u0161\u0178\u017d\u017e"
    r"\u02dc\u2018-\u201f\u2020-\u2027\u2030\u2039\u203a\u2122]"
)


def _reparar_cp1252(m: re.Match) -> str:
    """Reconstrói o byte E2 80 XX a partir do 3º char e decodifica como UTF-8."""
    seg = m.group(0)
    if len(seg) < 3:
        return seg
    terceiro = seg[2]
    try:
        if ord(terceiro) <= 0x9F:
            byte3 = ord(terceiro)
        else:
            byte3 = terceiro.encode("cp1252")[0]
        return bytes([0xE2, 0x80, byte3]).decode("utf-8")
    except Exception:
        return seg


# ============================================================================
# 2. CORREÇÃO DE MOJIBAKE POR OCORRÊNCIA
# ============================================================================
def corrigir_mojibake_inteligente(texto: str) -> str:
    """Corrige mojibake por ocorrência (Ã©->é, Ã£->ã, â€œ->", â€™->'...).

    Diferente do _corrigir_mojibake do createjsonl.py (que codifica a string
    INTEIRA como latin-1 e quebra se o texto tem aspas/travessão), aqui cada
    trecho é tratado isoladamente; o que não for UTF-8 válido fica como está
    (e será tratado pelo remover_invalidos se não for ABNT2).
    """
    if not texto:
        return texto
    # 1) cp1252 (aspas/travessão/...): â€œ -> " etc.
    texto = _RE_CP1252.sub(_reparar_cp1252, texto)
    # 2) latin-1 (Ã© -> é, Ã£ -> ã, ...)
    if not _RE_RUN_LATIN1.search(texto):
        return texto

    def _reparar(m: re.Match) -> str:
        chunk = m.group(0)
        try:
            return chunk.encode("latin-1").decode("utf-8", errors="strict")
        except Exception:
            return chunk  # não é mojibake válido; deixa p/ a próxima etapa

    return _RE_RUN_LATIN1.sub(_reparar, texto)


# ============================================================================
# 3. REMOÇÃO CIRÚRGICA DE CARACTERES FORA DO ABNT2
# ============================================================================
def remover_invalidos(texto: str) -> tuple[str, int]:
    """Remove caracteres que NÃO existem no português/ABNT2.

    Remove SÓ o caractere estranho (cirúrgico) — a palavra vizinha permanece.
    Retorna (texto_limpo, quantidade_removida).
    """
    if not texto:
        return texto, 0
    saida: list[str] = []
    removidos = 0
    for ch in texto:
        if ch in ABNT2_ACEITOS:
            saida.append(ch)
        else:
            removidos += 1
    return "".join(saida), removidos


# ============================================================================
# 4. AVALIAÇÃO (OK / corrigido / DESCARTAR)
# ============================================================================
def avaliar_conteudo(conteudo: str, n_removidos: int) -> tuple[str, str]:
    """Decide o destino de um conteúdo após o tratamento.

    Retorna (status, motivo) com status em: ok | corrigido | descartado.
    """
    if not conteudo.strip():
        return "descartado", "conteudo vazio"
    # Proporção de lixo removido sobre o tamanho original
    total_original = len(conteudo) + n_removidos
    razao = n_removidos / max(1, total_original)
    if razao > 0.25:
        return "descartado", f"excesso de caracteres invalidos ({razao:.0%})"
    if n_removidos > 0:
        return "corrigido", f"{n_removidos} char(s) removido(s)"
    return "ok", ""


def _detectar_idioma_sugestao(texto: str) -> str:
    """Retorna sugestão de idioma via langdetect (se instalado) — só informativo."""
    if len(texto) < 80:
        return ""
    try:
        from langdetect import detect
        return detect(texto) or ""
    except Exception:
        return ""


# Scripts NÃO-Latinos: se o texto tiver QUALQUER caractere destes, não é PT-BR
_RE_SCRIPT_NAO_LATINO = re.compile(
    r"[\u0400-\u04FF"      # cirílico (russo, etc.)
    r"\u0600-\u06FF"       # árabe
    r"\u0900-\u097F"       # devanagari
    r"\u0B80-\u0BFF"       # tâmil
    r"\u0E00-\u0E7F"       # tailandês
    r"\u4E00-\u9FFF"       # CJK (chinês/japonês)
    r"\u3040-\u30FF"       # hiragana/katakana
    r"\uAC00-\uD7AF"       # hangul (coreano)
    r"\u0590-\u05FF]"      # hebraico
)


def eh_portugues_br(texto: str) -> bool:
    """Decisão REAL de idioma: True se o texto é português (brasileiro).

    Regras (método, sem falso-positivo agressivo):
      1. Texto curto (< 60 chars) → True (não dá p/ confiar no langdetect;
         a remoção de inválidos já cuidou do lixo óbvio).
      2. Script não-Latino (cirílico/árabe/tâmil/CJK...) → False (certeza).
      3. langdetect: 'pt'/'pt-br' → True; outro idioma → False.
      4. Falha do langdetect → True (não descarta sem evidência).
    """
    if not texto or len(texto.strip()) < 60:
        return True
    if _RE_SCRIPT_NAO_LATINO.search(texto):
        return False
    try:
        from langdetect import detect
        idioma = detect(texto[:1000])
        return idioma in ("pt", "pt-br")
    except Exception:
        return True


# ============================================================================
# 5. SANITIZAÇÃO DE EXEMPLOS / ARQUIVOS
# ============================================================================
def sanitizar_mensagem(m: Any) -> tuple[dict | None, dict]:
    """Sanitiza UMA mensagem (role/content). Retorna (msg_limpa ou None, stats).

    ROBUSTEZ (prever imprevistos):
      - `m` pode NÃO ser dict (ex.: string solta, None, número) → descarta
      - `content` pode ser: str | list | dict | None | número → normaliza
      - `content` pode ser uma LISTA de partes ({type,text} ou str) → junta
      - erro interno de sanitização NUNCA levanta — retorna None + motivo
    """
    stats = {"removidos": 0, "mojibake": 0, "status": "ok", "motivo": "",
             "erro": False}
    # 1) mensagem não é dict (dado inesperado) → descarta com motivo claro
    if not isinstance(m, dict):
        stats.update(status="descartado", motivo="mensagem nao-dict", erro=True)
        return None, stats

    try:
        role = m.get("role", "")
        conteudo = m.get("content")
        if isinstance(conteudo, list):  # some HF datasets: list of {type, text}
            textos = []
            for parte in conteudo:
                if isinstance(parte, dict):
                    textos.append(str(parte.get("text", "")))
                else:
                    textos.append(str(parte))
            conteudo = "\n".join(textos)
        elif isinstance(conteudo, dict):  # raro: content aninhado
            conteudo = str(conteudo.get("text", str(conteudo)))
        conteudo = str(conteudo or "")

        corrigido = corrigir_mojibake_inteligente(conteudo)
        if corrigido != conteudo:
            stats["mojibake"] = 1
        limpo, removidos = remover_invalidos(corrigido)
        status, motivo = avaliar_conteudo(limpo, removidos)
        stats["removidos"] = removidos
        stats["status"] = status
        stats["motivo"] = motivo

        if status == "descartado":
            return None, stats
        nova = dict(m)
        nova["content"] = limpo
        return nova, stats
    except Exception as e:  # último recurso: nunca derruba o lote
        stats.update(status="descartado", motivo=f"erro interno: {e}", erro=True)
        return None, stats


def sanitizar_exemplo(obj: dict, exigir_ptbr: bool = False) -> tuple[dict | None, dict]:
    """Sanitiza UM exemplo ({"messages": [...]}). Retorna (exemplo ou None, stats).

    Se `exigir_ptbr=True`, exemplos que NÃO forem português são DESCARTADOS
    (retorna None) — filtro real de idioma (regra de ouro: conteúdo 100% PT-BR).
    """
    if not isinstance(obj, dict):
        return None, {"status": "descartado", "motivo": "exemplo nao-dict", "erro": True}
    mensagens = obj.get("messages")
    if not isinstance(mensagens, list) or not mensagens:
        return None, {"status": "descartado", "motivo": "sem messages"}

    novas: list[dict] = []
    total_removidos = 0
    mojibake = 0
    for m in mensagens:
        nova, st = sanitizar_mensagem(m)
        if nova is None:
            return None, {"status": "descartado", "motivo": f"mensagem {st['status']}: {st['motivo']}", "erro": st.get("erro", False)}
        novas.append(nova)
        total_removidos += st["removidos"]
        mojibake += st["mojibake"]

    # Idioma (informativo SEMPRE; descarta SÓ se exigir_ptbr)
    amostra = " ".join(str(x.get("content", "")) for x in novas)[:400]
    idioma = _detectar_idioma_sugestao(amostra)
    if exigir_ptbr and not eh_portugues_br(amostra):
        return None, {
            "status": "descartado",
            "motivo": f"idioma não-PT-BR ({idioma or 'detecção falhou/curto'})",
            "idioma": idioma,
        }

    novo = dict(obj)
    novo["messages"] = novas
    return novo, {
        "status": "corrigido" if (total_removidos or mojibake) else "ok",
        "removidos": total_removidos,
        "mojibake": mojibake,
        "idioma": idioma,
    }


def sanitizar_arquivo_jsonl(caminho: str, saida: str | None = None,
                            exigir_ptbr: bool = False) -> dict:
    """Sanitiza um arquivo JSONL inteiro. Escreve o limpo em `saida` (ou devolve
    se `saida` for None e --stdout não usado). Retorna relatório.

    ROBUSTEZ: arquivo inexistente/sem permissão/corrompido NÃO levanta exceção —
    retorna relatório com `erro` preenchido (retrabalho, não crash).
    """
    rel = {
        "arquivo": caminho,
        "total": 0, "ok": 0, "corrigidos": 0, "descartados": 0,
        "chars_removidos": 0, "com_mojibake": 0,
        "nao_pt": 0, "exemplos_nao_pt": [], "erro": "",
    }
    linhas_limpas: list[str] = []
    if not os.path.isfile(caminho):
        rel["erro"] = f"arquivo não encontrado: {caminho}"
        rel["linhas_limpas"] = []
        return rel
    try:
        _abrir = open(caminho, encoding="utf-8", errors="replace")
    except OSError as e:
        rel["erro"] = f"não foi possível abrir: {e}"
        rel["linhas_limpas"] = []
        return rel
    with _abrir:
        for linha in _abrir:
            if not linha.strip():
                continue
            try:
                obj = json.loads(linha)
            except Exception:
                rel["descartados"] += 1
                continue
            novo, st = sanitizar_exemplo(obj, exigir_ptbr=exigir_ptbr)
            rel["total"] += 1
            if novo is None:
                rel["descartados"] += 1
                if st.get("status") == "descartado" and st.get("motivo", "").startswith("idioma"):
                    rel["nao_pt"] += 1
                    if len(rel["exemplos_nao_pt"]) < 3:
                        rel["exemplos_nao_pt"].append(
                            str(obj.get("messages", [{}])[0].get("content", ""))[:80]
                        )
                continue
            rel["chars_removidos"] += st.get("removidos", 0)
            rel["com_mojibake"] += 1 if st.get("mojibake") else 0
            if st.get("status") == "corrigido":
                rel["corrigidos"] += 1
            else:
                rel["ok"] += 1
            if st.get("idioma") and st["idioma"] not in ("pt", "pt-br", "pt-BR"):
                rel["nao_pt"] += 1
                if len(rel["exemplos_nao_pt"]) < 3:
                    rel["exemplos_nao_pt"].append(
                        str(novo["messages"][0].get("content", ""))[:80]
                    )
            linhas_limpas.append(json.dumps(novo, ensure_ascii=False))

    if saida:
        os.makedirs(os.path.dirname(os.path.abspath(saida)) or ".", exist_ok=True)
        with open(saida, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas_limpas) + ("\n" if linhas_limpas else ""))
        rel["saida"] = saida
    rel["linhas_limpas"] = linhas_limpas
    return rel


def sanitizar_pasta(pasta: str, saida_dir: str | None = None,
                    exigir_ptbr: bool = False) -> list[dict]:
    """Sanitiza TODOS os .jsonl de uma pasta (em lotes). Retorna relatórios."""
    if not os.path.isdir(pasta):
        print("Pasta não encontrada:", pasta)
        return []
    jsonls = sorted(f for f in os.listdir(pasta) if f.endswith(".jsonl"))
    if not jsonls:
        print("Nenhum .jsonl em", pasta)
        return []
    if saida_dir:
        os.makedirs(saida_dir, exist_ok=True)
    relatorios = []
    for nome in jsonls:
        origem = os.path.join(pasta, nome)
        destino = os.path.join(saida_dir, nome) if saida_dir else None
        rel = sanitizar_arquivo_jsonl(origem, destino, exigir_ptbr=exigir_ptbr)
        relatorios.append(rel)
        flag = "❌" if rel["descartados"] or rel["chars_removidos"] else "✅"
        print(f"{flag} {nome}: total={rel['total']} ok={rel['ok']} "
              f"corrigidos={rel['corrigidos']} descartados={rel['descartados']} "
              f"chars_removidos={rel['chars_removidos']} mojibake={rel['com_mojibake']}")
    return relatorios


# ============================================================================
# 6. SELF-TEST (demonstração com casos reais)
# ============================================================================
def self_test() -> int:
    casos = [
        ("mojibake simples", "Isso Ã© um teste de frase.",
         "Isso é um teste de frase."),
        ("mojibake + caractere fora do latin1 (lacuna do _corrigir_mojibake)",
         "A frase tinha “aspas” e â€œmojibakeâ€\u009d — travessão — e Ã§ao.",
         "A frase tinha “aspas” e “mojibake” — travessão — e çao."),
        ("U+FFFD", "Aqui tem um caracter invalido � no meio da frase.",
         "Aqui tem um caracter invalido  no meio da frase."),
        ("caracteres fora do ABNT2", "Isto Ă tem Ħ caracteres İ estranhos ķ ē aqui.",
         "Isto  tem  caracteres  estranhos   aqui."),
        ("português normal (não pode mudar!)",
         "Não é à toa que são mães coração câmera âmbito.",
         "Não é à toa que são mães coração câmera âmbito."),
    ]
    erros = 0
    for nome, entrada, esperado in casos:
        corrigido = corrigir_mojibake_inteligente(entrada)
        limpo, removidos = remover_invalidos(corrigido)
        status, motivo = avaliar_conteudo(limpo, removidos)
        ok = limpo == esperado
        if not ok:
            erros += 1
        print(f"{'✅' if ok else '❌'} {nome}")
        print(f"   entrada : {entrada!r}")
        print(f"   limpo   : {limpo!r}")
        print(f"   esperado: {esperado!r}")
        print(f"   removidos={removidos} | status={status} {motivo}\n")
    print("RESULTADO:", "TODOS OK" if erros == 0 else f"{erros} caso(s) falharam")
    return 0 if erros == 0 else 1


# ============================================================================
# 7. MAIN
# ============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Sanitizador PT-BR (portão de qualidade)")
    ap.add_argument("alvo", nargs="?", help="Arquivo .jsonl ou pasta")
    ap.add_argument("--saida", default=None, help="Arquivo/pasta de saída (opcional)")
    ap.add_argument("--pt-br", action="store_true",
                    help="DESCARTA linhas que não forem português (filtro de idioma real)")
    ap.add_argument("--self-test", action="store_true", help="Roda a demonstração")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if not args.alvo:
        ap.print_help()
        return 1

    if os.path.isdir(args.alvo):
        sanitizar_pasta(args.alvo, args.saida, exigir_ptbr=args.pt_br)
        return 0
    if os.path.isfile(args.alvo):
        rel = sanitizar_arquivo_jsonl(args.alvo, args.saida, exigir_ptbr=args.pt_br)
        if not args.saida:
            # imprime amostra antes/depois no console
            with open(args.alvo, encoding="utf-8", errors="replace") as f:
                linhas = [l for l in f if l.strip()][:3]
            print("=== amostra ANTES ===")
            for l in linhas:
                print("  ", l[:150].rstrip())
            print("=== amostra DEPOIS ===")
            for l in rel["linhas_limpas"][:3]:
                print("  ", l[:150])
        print(json.dumps({k: rel[k] for k in rel if k != "linhas_limpas"},
                         ensure_ascii=False, indent=2))
        return 0
    print("Alvo não encontrado:", args.alvo)
    return 1


if __name__ == "__main__":
    sys.exit(main())
