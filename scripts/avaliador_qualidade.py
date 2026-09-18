#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
avaliador_qualidade.py — AVALIADOR DE QUALIDADE de textos gerados (PT-BR).

Estratégia em camadas (regra do usuário, 11/08/2026):
  1ª GATES DETERMINÍSTICOS (grátis, sem modelo):
     - repetição de palavras adjacentes ("criada criada", "como como")
     - padrão "cortada+inteira" (palavra cortada no fim da linha + palavra
       inteira repetida no início da próxima — artefato clássico de geração)
     - diversidade lexical (type-token ratio)
     - bigramas repetidos (loop de texto)
     - marcadores de geração "enrolada" ("é como se estivessem dizendo"...)
     → classifica: aprovado / suspeito / lixo
  2ª JUIZ LOCAL (opcional, --juiz): modelo de raciocínio (deepseek-r1:7b)
     analisa SÓ os "suspeitos" e lista afirmações factuais questionáveis.

⚡ NUNCA apaga nada — só classifica e gera relatório (JSON + console).
Com --mover: aprovados → dados/processed/<pasta>_aprovado/ (prontos p/ converter),
lixo → dados/gerados/desclassificados/<pasta>/ (fora do treino), suspeitos ficam
na pasta original para revisão. Progresso real em logs/avaliacao_progresso.json.

Uso:
  python scripts/avaliador_qualidade.py --pasta dados/gerados/gerados_local
  python scripts/avaliador_qualidade.py --pasta dados/gerados/gerados_local --mover
  python scripts/avaliador_qualidade.py --pasta dados/gerados/completos --juiz --mover
  python scripts/avaliador_qualidade.py --pasta ... --limite 10 --juiz
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))

LOGS_DIR = PROJETO_ROOT / "logs"
PROGRESSO_PATH = LOGS_DIR / "avaliacao_progresso.json"
RELATORIO_DEFAULT = LOGS_DIR / "avaliacao_relatorio.json"

# ── Limiares (ajustáveis) ────────────────────────────────────────────────
REP_ADJ_ALTO = 0.03       # fração de palavras repetidas adjacentes → sinal forte
CORTADA_INTEIRA_ALTO = 3  # nº de ocorrências do padrão cortada+inteira
TTR_MIN = 0.40            # abaixo disso → texto repetitivo/empobrecido
BIGRAMA_REP_ALTO = 0.10   # fração de bigramas repetidos (loop)
MIN_PALAVRAS = 30         # abaixo disso = texto curto demais (baixo valor)
MARCADORES = [
    "é como se estivessem dizendo", "é como se estivesse dizendo",
    "olha só", "olha lá", "vamos tentar descobrir", "eu sou incrível",
    "eu sou melhor agora", "eu entendi", "não sabe o que isso significa",
]

# ── Camada 2: juiz local (raciocínio) ────────────────────────────────────
MODELO_JUIZ = "deepseek-r1:7b"
JUIZ_URL = "http://127.0.0.1:11434/api/generate"
JUIZ_TIMEOUT = 600          # segundos por arquivo (CPU é lento)
MEMORIA_MIN_JUIZ_GB = 6.0   # não carrega o modelo se RAM livre < isto
PROMPT_JUIZ = (
    "Você é um revisor rigoroso de qualidade de texto em português brasileiro.\n"
    "Analise o texto abaixo e:\n"
    "1) Liste as afirmações factuais que parecem FALSAS, exageradas ou impossíveis (se houver).\n"
    "2) Aponte trechos sem sentido, contraditórios ou que pareçam alucinação.\n"
    "Se o texto parecer plausível e coerente, responda apenas: APROVADO\n"
    "Se houver problemas, responda: SUSPEITO + lista resumida dos problemas.\n\n"
    "TEXTO:\n"
)

_PALAVRA = re.compile(r"[a-záéíóúâêôãõàüçñ]+", re.IGNORECASE)
_FRAG_FIM_LINHA = re.compile(r"([a-záéíóúâêôãõàüçñ]{3,})$", re.IGNORECASE)


def _tokenizar(texto: str) -> list[str]:
    return [w.lower() for w in _PALAVRA.findall(texto)]


def _metricas(texto: str) -> dict:
    """Calcula as métricas determinísticas do texto."""
    palavras = _tokenizar(texto)
    n = len(palavras)

    # 1) repetição de palavras ADJACENTES (criada criada)
    rep_adj = sum(1 for i in range(1, n) if palavras[i] == palavras[i - 1])
    rep_adj_frac = rep_adj / n if n else 0

    # 2) padrão "cortada+inteira" (fim de linha cortado + palavra inteira na próxima)
    cortada = 0
    linhas = texto.splitlines()
    for i in range(len(linhas) - 1):
        m = _FRAG_FIM_LINHA.search(linhas[i].rstrip())
        if not m:
            continue
        frag = m.group(1).lower()
        ini = _PALAVRA.search(linhas[i + 1])
        if not ini:
            continue
        w = ini.group(0).lower()
        if len(w) > len(frag) and w.startswith(frag):
            cortada += 1

    # 3) diversidade lexical (type-token ratio)
    ttr = len(set(palavras)) / n if n else 0

    # 4) bigramas repetidos (loop)
    if n >= 2:
        bigrams = [f"{palavras[i]} {palavras[i+1]}" for i in range(n - 1)]
        repetidos = len(bigrams) - len(set(bigrams))
        bigrama_rep_frac = repetidos / len(bigrams)
    else:
        bigrama_rep_frac = 0.0

    # 5) marcadores de geração "enrolada"
    low = texto.lower()
    marcadores = sum(1 for m in MARCADORES if m in low)

    return {
        "palavras": n,
        "rep_adj": rep_adj,
        "rep_adj_frac": round(rep_adj_frac, 4),
        "cortada_inteira": cortada,
        "ttr": round(ttr, 3),
        "bigrama_rep_frac": round(bigrama_rep_frac, 4),
        "marcadores": marcadores,
    }


def _pontuar(m: dict) -> int:
    """Soma os pontos de qualidade (mais = pior)."""
    p = 0
    if m["rep_adj_frac"] >= REP_ADJ_ALTO:
        p += 2
    elif m["rep_adj"] > 0:
        p += 1
    if m["cortada_inteira"] >= CORTADA_INTEIRA_ALTO:
        p += 2
    elif m["cortada_inteira"] > 0:
        p += 1
    if m["ttr"] < TTR_MIN:
        p += 1
    if m["bigrama_rep_frac"] >= BIGRAMA_REP_ALTO:
        p += 1
    if m["marcadores"] >= 3:
        p += 1
    if m["palavras"] < MIN_PALAVRAS:
        p += 1
    if m["rep_adj_frac"] >= REP_ADJ_ALTO and m["cortada_inteira"] >= CORTADA_INTEIRA_ALTO:
        p += 1  # os dois sintomas juntos = geração claramente doente
    return p


def _classificar(pontos: int) -> str:
    if pontos >= 5:
        return "lixo"
    if pontos >= 2:
        return "suspeito"
    return "aprovado"


def _memoria_ok() -> tuple[bool, float]:
    try:
        import psutil
        liv = psutil.virtual_memory().available / 1e9
        return liv >= MEMORIA_MIN_JUIZ_GB, liv
    except Exception:
        return True, -1.0


def _modelo_instalado(modelo: str) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as r:
            dados = json.loads(r.read().decode("utf-8", "replace"))
        return any(t.get("name", "").startswith(modelo) for t in dados.get("models", []))
    except Exception:
        return False


def _veredito_aprovado(saida: str) -> bool:
    """Interpreta a resposta do juiz de forma TOLERANTE a variações/erros
    de digitação do modelo (ex.: 'Aprovaço' em vez de 'Aprovado' — visto no
    teste real com deepseek-r1:7b em 13/08/2026).

    Regras:
      - 'suspeit...' na resposta → NÃO aprovado (sinal explícito de problema).
      - negação ('não aprovado' / 'nao aprovado') → NÃO aprovado.
      - caso contrário, aceita qualquer variação do radical
        'aprovad*' / 'aprovaç*' (aprovado, aprovada, aprovaço, ...).
    """
    low = saida.lower()
    if "suspeit" in low:
        return False
    if "não aprov" in low or "nao aprov" in low:
        return False
    return bool(re.search(r"aprovad|aprovaç", low))


def _juiz_ollama(texto: str, modelo: str) -> dict:
    """Chama o modelo de raciocínio local. Nunca lança (erro → registra)."""
    try:
        import urllib.request
        payload = {
            "model": modelo,
            "prompt": PROMPT_JUIZ + texto[:6000],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 700},
        }
        req = urllib.request.Request(
            JUIZ_URL, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=JUIZ_TIMEOUT) as r:
            resp = json.loads(r.read().decode("utf-8", "replace"))
        saida = (resp.get("response") or "").strip()
        aprovado = _veredito_aprovado(saida)
        return {"ok": True, "resposta": saida[:800], "aprovado": aprovado}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def _mover_arquivo(origem: Path, destino_dir: Path) -> tuple[bool, str]:
    """Move o arquivo para o destino. Nunca sobrescreve nem apaga nada."""
    try:
        import shutil
        destino_dir.mkdir(parents=True, exist_ok=True)
        alvo = destino_dir / origem.name
        if alvo.exists():
            return False, "destino já existe (não sobrescrevi)"
        shutil.move(str(origem), str(alvo))
        return True, ""
    except Exception as e:
        return False, str(e)


def _gravar_progresso(dados: dict) -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        PROGRESSO_PATH.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _agora() -> str:
    return datetime.now().isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description="Avalia qualidade de textos gerados (PT-BR).")
    ap.add_argument("--pasta", required=True, help="Pasta com os .txt a avaliar")
    ap.add_argument("--saida", default=str(RELATORIO_DEFAULT), help="Arquivo JSON do relatório")
    ap.add_argument("--juiz", action="store_true",
                    help="Camada 2: usa o modelo local de raciocínio nos 'suspeitos'")
    ap.add_argument("--modelo", default=MODELO_JUIZ, help="Modelo do juiz (Ollama)")
    ap.add_argument("--limite", type=int, default=None, help="Máx. de arquivos (teste)")
    ap.add_argument("--mover", action="store_true",
                    help="Move: aprovado → processed, lixo → desclassificados (suspeito fica)")
    ap.add_argument("--destino-aprovados", default="dados/processed",
                    help="Pasta base dos aprovados (default: dados/processed)")
    ap.add_argument("--destino-lixo", default="dados/gerados/desclassificados",
                    help="Pasta base do lixo (default: dados/gerados/desclassificados)")
    args = ap.parse_args()

    pasta = Path(args.pasta)
    if not pasta.is_dir():
        print(f"❌ Pasta não encontrada: {pasta}")
        return 1
    arqs = sorted(pasta.glob("*.txt"))
    if not arqs:
        print("❌ Nenhum .txt na pasta.")
        return 1
    if args.limite:
        arqs = arqs[: args.limite]

    usar_juiz = args.juiz
    modelo_ok = False
    if usar_juiz:
        ok, liv = _memoria_ok()
        if not ok:
            print(f"⚠️ RAM livre {liv:.1f} GB < {MEMORIA_MIN_JUIZ_GB} GB — juiz DESLIGADO "
                  f"(regra do guardião).")
            usar_juiz = False
        elif not _modelo_instalado(args.modelo):
            print(f"⚠️ Modelo '{args.modelo}' não encontrado no Ollama. "
                  f"Rode: ollama pull {args.modelo} — juiz DESLIGADO.")
            usar_juiz = False
        else:
            modelo_ok = True

    print(f"🔎 Avaliando {len(arqs)} arquivos em {pasta} "
          f"(camada 1 sempre; camada 2 {'ON' if usar_juiz else 'OFF'})")

    resultado = {
        "pasta": str(pasta), "total": len(arqs), "inicio": _agora(),
        "modelo_juiz": args.modelo if usar_juiz else None,
        "mover": args.mover,
        "aprovados": 0, "suspeitos": 0, "lixos": 0, "movidos": {},
        "arquivos": [],
    }

    for i, f in enumerate(arqs, 1):
        try:
            texto = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  ⚠️ {f.name}: erro de leitura ({e})")
            continue
        m = _metricas(texto)
        pontos = _pontuar(m)
        classe = _classificar(pontos)
        juiz = None
        if usar_juiz and classe == "suspeito":
            juiz = _juiz_ollama(texto, args.modelo)
            if juiz.get("ok"):
                if juiz.get("aprovado"):
                    classe = "aprovado"
                else:
                    classe = "lixo" if pontos >= 4 else "suspeito"

        if classe == "aprovado":
            resultado["aprovados"] += 1
        elif classe == "suspeito":
            resultado["suspeitos"] += 1
        else:
            resultado["lixos"] += 1

        # 🚚 MOVER (só com --mover): aprovado → processed, lixo → desclassificados
        movido = None
        if args.mover:
            if classe == "aprovado":
                destino = Path(args.destino_aprovados) / (pasta.name + "_aprovado")
            elif classe == "lixo":
                destino = Path(args.destino_lixo) / pasta.name
            else:
                destino = None  # suspeito fica p/ revisão
            if destino is not None:
                ok, err = _mover_arquivo(f, destino)
                movido = {"ok": ok, "destino": str(destino), "erro": err or None}
                if ok:
                    resultado["movidos"][classe] = resultado["movidos"].get(classe, 0) + 1

        resultado["arquivos"].append({
            "arquivo": f.name, "palavras": m["palavras"],
            "metricas": m, "pontos": pontos, "classificacao": classe,
            "juiz": juiz, "movido": movido,
        })
        print(f"  [{i}/{len(arqs)}] {classe.upper():<9} {f.name} "
              f"(pontos={pontos}, cortada={m['cortada_inteira']}, rep={m['rep_adj']}, ttr={m['ttr']})"
              + (f" → {Path(movido['destino']).name}" if movido and movido.get("ok") else ""))
        _gravar_progresso({"pct": round(i / len(arqs) * 100), "atual": f.name,
                           "ok": resultado["aprovados"], "suspeitos": resultado["suspeitos"],
                           "lixos": resultado["lixos"], "total": len(arqs),
                           "timestamp": _agora()})

    resultado["fim"] = _agora()
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        Path(args.saida).write_text(
            json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Não consegui gravar relatório: {e}")

    print("\n" + "═" * 50)
    print(f"✅ APROVADOS: {resultado['aprovados']}  "
          f"🔄 SUSPEITOS: {resultado['suspeitos']}  "
          f"🗑️ LIXO: {resultado['lixos']}")
    if args.mover and resultado["movidos"]:
        print(f"🚚 Movidos: {resultado['movidos']}")
        print(f"   aprovados → {Path(args.destino_aprovados)/ (pasta.name + '_aprovado')}")
        print(f"   lixo → {Path(args.destino_lixo) / pasta.name}")
    print(f"📄 Relatório: {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
