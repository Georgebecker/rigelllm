# -*- coding: utf-8 -*-
"""
sanitizar_suspeitos.py — SANITIZAÇÃO GERAL dos suspeitos ANTES do juiz.

Pedido do usuário (18/08/2026): passar TODAS as ferramentas de depuração de
dados (códigos ANSI perdidos, mojibake, caracteres fora do ABNT, espaços em
branco/concatenados, emojis) ANTES de enviar para o juiz analisar. O juiz só
entra depois que o texto está limpo.

- limpar_texto(): aplica TODAS as correções em ordem, reutilizando as
  ferramentas existentes (dashboard.services.limpeza + sanitizador_ptbr).
- diagnosticar_texto(): diz se o texto tem ANSI/mojibake/fora-ABNT/etc.
  (sem alterar nada).
- sanitizar_pendentes(): varre os suspeitos pendentes, limpa cada arquivo
  NO LUGAR (o painel /revisar passa a mostrar o texto limpo) e reporta.
- Controle de pausa/parada COMPARTILHADO com o juiz (estado/juiz_controle.json)
  — os botões ⏸️ ▶️ ⏹️ do painel valem para as duas tarefas.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))

from dashboard.services.limpeza import (  # noqa: E402
    limpar_ansi, limpar_emojis, corrigir_espacos_concatenados,
)
from sanitizador_ptbr import (  # noqa: E402
    corrigir_mojibake_inteligente, remover_invalidos,
)

CONTROLE = PROJETO_ROOT / "estado" / "juiz_controle.json"
PROGRESSO = PROJETO_ROOT / "logs" / "sanitizar_progresso.json"


# ============================================================================
# Controle de pausa/parada (compartilhado com o juiz)
# ============================================================================
def controle() -> dict:
    """Lê o arquivo de controle (pausado/parar). Nunca falha."""
    try:
        if CONTROLE.exists():
            d = json.loads(CONTROLE.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def set_controle(**kwargs) -> None:
    """Grava chaves no controle (ex.: pausado=True, parar=True)."""
    try:
        CONTROLE.parent.mkdir(parents=True, exist_ok=True)
        d = controle()
        d.update(kwargs)
        d["atualizado"] = datetime.now().isoformat(timespec="seconds")
        CONTROLE.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except Exception:
        pass


# ============================================================================
# Limpeza em cadeia (todas as ferramentas)
# ============================================================================
# Padrão de REDESENHO do terminal: fragmento + ESC[nD ESC[K + palavra completa.
# Ex.: "in\x1b[2D\x1b[Kinfraestrutura" → o terminal digitou "in", voltou 2 e
# reescreveu "infraestrutura". Se só removermos o ESC, sobra "ininfraestrutura".
_RE_REDRAW_ANSI = re.compile(
    r"([A-Za-zÀ-ÖØ-öø-ÿ]{2,})(\x1b\[[0-9;]*D\x1b\[K)([A-Za-zÀ-ÖØ-öø-ÿ]+)"
)


def _corrigir_redesenho_ansi(texto: str) -> str:
    """Remove o fragmento duplicado do padrão de redesenho do terminal."""
    if "\x1b" not in texto:
        return texto

    def _rep(m: re.Match) -> str:
        frag, esc, palavra = m.group(1), m.group(2), m.group(3)
        if palavra.lower().startswith(frag.lower()):
            return palavra      # redesenho: fica só a palavra completa
        return frag + esc + palavra  # não é redesenho: preserva p/ limpar_ansi

    return _RE_REDRAW_ANSI.sub(_rep, texto)


# Padrão "CORTADA+INTEIRA": linha termina com fragmento de palavra e a linha
# seguinte começa com a palavra completa (ex.: "explorad⏎explorado", "se⏎se").
# Mesma heurística do avaliador de qualidade (scripts/avaliador_qualidade.py) —
# mas aqui usada para CONSERTAR, não só detectar. Fragmentos de 1 letra ficam
# de fora (risco de falso positivo tipo "e⏎economia").
_RE_FRAG_FIM_LINHA = re.compile(r"([a-záéíóúâêôãõàüçñ]{2,})$", re.IGNORECASE)
_RE_INICIO_PALAVRA = re.compile(r"^[a-záéíóúâêôãõàüçñ]+", re.IGNORECASE)


def _corrigir_cortada_linha(texto: str) -> str:
    """Junta linhas com o padrão 'cortada+inteira' (fragmento duplicado).

    Casos tratados:
      - fragmento é PREFIXO da palavra seguinte ("explorad⏎explorado")
      - palavra REPETIDA no início da linha seguinte ("se⏎se", "no⏎no")

    Processa linha a linha e SEMPRE re-checa o fim da última linha junta
    (depois de juntar, o fim pode conter um novo fragmento a comparar).
    """
    linhas = texto.splitlines()
    if len(linhas) < 2:
        return texto
    resultado = [linhas[0]]
    for prox in linhas[1:]:
        atual = resultado[-1].rstrip()
        p = prox.lstrip()
        m = _RE_FRAG_FIM_LINHA.search(atual)
        juntou = False
        if m:
            frag = m.group(1)
            mw = _RE_INICIO_PALAVRA.search(p)
            if mw:
                w = mw.group(0)
                if len(w) >= len(frag) and w.lower().startswith(frag.lower()):
                    antes = atual[: m.start()].rstrip()
                    resultado[-1] = (antes + " " + p).rstrip()
                    juntou = True
        if not juntou:
            resultado.append(prox)
    return "\n".join(resultado)


def limpar_texto(texto: str) -> tuple[str, dict]:
    """Aplica TODAS as ferramentas de limpeza em ordem.

    Retorna (texto_limpo, stats) com stats = {ansi, mojibake, abnt, emojis,
    espacos, controle} (contagens/flags). Reutiliza o que já existe no projeto.
    """
    stats = {"ansi": 0, "mojibake": 0, "abnt": 0, "emojis": 0,
             "espacos": 0, "controle": 0}
    if not texto:
        return texto, stats

    # 1) redesenho do terminal (fragmento + ESC[nD ESC[K + palavra)
    texto = _corrigir_redesenho_ansi(texto)

    # 2) "cortada+inteira": palavra quebrada no fim da linha + repetida na
    #    próxima (ex.: "explorad⏎explorado") — artefato clássico de geração
    #    capturada do terminal. Junta e remove o fragmento duplicado.
    texto = _corrigir_cortada_linha(texto)

    # 3) códigos ANSI perdidos (OBRIGATÓRIO antes do ABNT — senão sobram
    #    pedaços como '[2D' '[K' que são letras normais para o ABNT)
    novo = limpar_ansi(texto)
    stats["ansi"] = 1 if novo != texto else 0
    texto = novo

    # 2) mojibake (Ã© -> é, â€œ -> ")
    novo = corrigir_mojibake_inteligente(texto)
    stats["mojibake"] = 1 if novo != texto else 0
    texto = novo

    # 3) caracteres fora do ABNT2 (não existem no português brasileiro)
    texto, n_abnt = remover_invalidos(texto)
    stats["abnt"] = n_abnt

    # 4) emojis
    novo = limpar_emojis(texto)
    stats["emojis"] = 1 if novo != texto else 0
    texto = novo

    # 5) palavras grudadas (problema comum do tokenizer BPE)
    novo = corrigir_espacos_concatenados(texto)
    stats["espacos"] = 1 if novo != texto else 0
    texto = novo

    # 6) caracteres de controle + espaços múltiplos
    novo = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
    stats["controle"] = 1 if novo != texto else 0
    texto = re.sub(r"[ \t]{2,}", " ", novo).strip()

    return texto, stats


def diagnosticar_texto(texto: str) -> dict:
    """Roda os testes e diz se o texto está limpo (sem alterar nada)."""
    _, stats = limpar_texto(texto)
    limpo = (not stats["ansi"] and not stats["mojibake"] and not stats["abnt"]
             and not stats["emojis"] and not stats["espacos"]
             and not stats["controle"])
    return {
        "limpo": bool(limpo),
        "caracteres": len(texto),
        "palavras": len(texto.split()),
        "ansi": bool(stats["ansi"]),
        "mojibake": bool(stats["mojibake"]),
        "fora_abnt": stats["abnt"],
        "emojis": bool(stats["emojis"]),
        "espacos_concatenados": bool(stats["espacos"]),
        "controle": bool(stats["controle"]),
    }


# ============================================================================
# Sanitização em massa dos pendentes
# ============================================================================
def _progresso(d: dict) -> None:
    try:
        PROGRESSO.parent.mkdir(parents=True, exist_ok=True)
        PROGRESSO.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def sanitizar_pendentes() -> dict:
    """Varre os suspeitos pendentes e limpa cada arquivo NO LUGAR.

    Aplica todas as ferramentas (ANSI/mojibake/ABNT/espaços/emojis) e
    reescreve o arquivo limpo — o juiz e o painel passam a ver texto limpo.
    Respeita pausa/parada via estado/juiz_controle.json. Nunca apaga nada.
    """
    from dashboard.services.revisao import listar_suspeitos, _registrar

    pendentes = []
    for p in listar_suspeitos().get("pastas", []):
        for it in p.get("itens", []):
            if it.get("existe") and it.get("caminho"):
                pendentes.append({"pasta": p["pasta"], "arquivo": it["arquivo"],
                                  "caminho": it["caminho"]})

    resumo = {"limpos": 0, "ja_ok": 0, "erros": 0, "ansi": 0, "abnt": 0}
    for i, item in enumerate(pendentes, 1):
        # ⏸️ pausa / ⏹️ parada (botões do painel)
        while controle().get("pausado") and not controle().get("parar"):
            time.sleep(2)
        if controle().get("parar"):
            set_controle(parar=False)
            break
        try:
            p = Path(item["caminho"])
            texto = p.read_text(encoding="utf-8", errors="replace")
            limpo, stats = limpar_texto(texto)
            if limpo != texto:
                p.write_text(limpo, encoding="utf-8")
                resumo["limpos"] += 1
                resumo["ansi"] += 1 if stats["ansi"] else 0
                resumo["abnt"] += stats["abnt"]
                _registrar(f"🧹 Limpo: {item['pasta']}/{item['arquivo']} "
                           f"(ansi={stats['ansi']} abnt={stats['abnt']} "
                           f"mojibake={stats['mojibake']})")
            else:
                resumo["ja_ok"] += 1
        except Exception:
            resumo["erros"] += 1
        _progresso({"pct": round(100 * i / max(1, len(pendentes)), 1),
                    "atual": item["arquivo"], "i": i,
                    "total": len(pendentes), **resumo,
                    "atualizado": datetime.now().isoformat()})

    _progresso({"pct": 100, "fim": True, **resumo,
                "atualizado": datetime.now().isoformat()})
    return {"ok": True, **resumo, "total": len(pendentes)}
