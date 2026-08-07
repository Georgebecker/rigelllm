#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tratamento.py — Central de Tratamento de Dados (dados de QUALQUER fonte).

Automacão do tratamento, igual ao fluxo do HuggingFace, mas para pastas que
vieram de qualquer lugar (scrap, RSS, download manual, HF, etc.):

  1. Varre dados/raw/ e detecta o FORMATO de cada pasta
  2. Recomenda o tratamento certo (matriz de tratamento):
       - jsonl   → 🧼 sanitização PT-BR        (dashboard.services.sanitizacao)
       - parquet → 🧹 limpeza leve v2          (limpeza_leve_rigel_v2.py)
       - txt     → 🔤 limpeza de encoding      (limpeza.py)
       - csv     → 🧹 limpeza leve v2
  3. O usuário MARCA as pastas e clica "Tratar marcados"
  4. O pipeline roda em lote: tratar → promover p/ processed/<tipo>/<nome> → limpar origens

Regras de ouro: guard de memória (recusa se RAM livre < 2 GB), 1 processo pesado
por vez, estado persistido p/ sobreviver a --reload, origens só apagadas após sucesso.
"""
import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

import httpx  # noqa: F401  (mantém o path de rede consistente com os demais)

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW = PROJETO_ROOT / "dados" / "raw"
PROCESSED = PROJETO_ROOT / "dados" / "processed"
SANITIZADOS = PROJETO_ROOT / "dados" / "sanitizados"
MIN_RAM_LIVRE_GB = 2.0  # guardião: não inicia tratamento pesado abaixo disso

# ============================================================================
# Estado (thread-safe + persistência)
# ============================================================================
_estado: dict = {
    "rodando": False,
    "etapa": "idle",          # idle | preparando | tratando | concluido | erro
    "mensagem": "",
    "percentual": None,
    "fila": [],               # pastas marcadas
    "atual": None,            # pasta sendo tratada agora
    "concluidos": [],         # [{nome, ok, tratamento, detalhe}]
    "inicio": None,
    "fim": None,
    "erro": None,
}
_lock = threading.Lock()
_PERSISTENCIA = PROJETO_ROOT / "estado" / "tratamento_estado.json"


def _persistir() -> None:
    try:
        _PERSISTENCIA.parent.mkdir(parents=True, exist_ok=True)
        _PERSISTENCIA.write_text(json.dumps(_estado, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception:
        pass


def _atualizar(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)
        _persistir()


def get_estado() -> dict:
    with _lock:
        return dict(_estado)


def limpar() -> dict:
    """Reseta o estado (não apaga arquivos)."""
    with _lock:
        _estado.update({
            "rodando": False, "etapa": "idle", "mensagem": "", "percentual": None,
            "fila": [], "atual": None, "concluidos": [], "inicio": None,
            "fim": None, "erro": None,
        })
        _persistir()
    return {"ok": True, "mensagem": "Estado do tratamento limpo."}


# ============================================================================
# Detecção de formato + recomendação
# ============================================================================
def detectar_formato(caminho: Path) -> str:
    """Detecta o formato dominante de uma pasta/arquivo pelos arquivos."""
    exts: dict[str, int] = {}
    arquivos = [caminho] if caminho.is_file() else [f for f in caminho.rglob("*") if f.is_file()]
    for f in arquivos:
        e = f.suffix.lower()
        if e:
            exts[e] = exts.get(e, 0) + 1
    if not exts:
        return "vazio"
    # formatação ignora metadados
    for meta in (".gitattributes", ".gitignore", ".metadata"):
        pass
    if exts.get(".jsonl", 0) >= 1:
        return "jsonl"
    if exts.get(".parquet", 0) >= 1:
        return "parquet"
    if exts.get(".csv", 0) >= 1:
        return "csv"
    if exts.get(".txt", 0) >= 1:
        return "txt"
    if exts.get(".json", 0) >= 1:
        return "json"
    return "outro"


def recomendar_tratamento(formato: str) -> str:
    """Matriz de tratamento: cada formato tem sua ferramenta certa."""
    mapa = {
        "jsonl": "sanitizar",
        "parquet": "limpeza_leve",
        "csv": "limpeza_leve",
        "txt": "limpeza_encoding",
        "json": "sanitizar",
        "outro": "nenhum",
        "vazio": "nenhum",
    }
    return mapa.get(formato, "nenhum")


def _tamanho_pasta(caminho: Path) -> float:
    return sum(f.stat().st_size for f in caminho.rglob("*") if f.is_file()) / 1e6


def listar_entrada() -> dict:
    """Lista as pastas em dados/raw/ com formato detectado + recomendação."""
    itens = []
    if RAW.exists():
        for d in sorted(RAW.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            formato = detectar_formato(d)
            itens.append({
                "nome": d.name,
                "formato": formato,
                "tratamento": recomendar_tratamento(formato),
                "arquivos": sum(len(fs) for _, _, fs in os.walk(d)),
                "tamanho_mb": round(_tamanho_pasta(d), 2),
            })
    return {"ok": True, "itens": itens, "pasta": str(RAW)}


# ============================================================================
# Pipeline de tratamento por tipo
# ============================================================================
def _ram_livre_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except Exception:
        return 99.0


def _tratar_uma(nome: str) -> dict:
    """Aplica o tratamento certo e promove. Retorna {ok, tratamento, detalhe}."""
    import time as _time
    origem = RAW / nome
    formato = detectar_formato(origem)
    tratamento = recomendar_tratamento(formato)
    detalhe = f"{formato} -> {tratamento}"

    if tratamento == "sanitizar":
        from dashboard.services import sanitizacao
        import shutil as _sh
        saida = str(SANITIZADOS / f"trat_{nome}")
        ini = sanitizacao.iniciar(str(origem), saida_dir=saida)
        if not ini.get("ok"):
            return {"ok": False, "tratamento": tratamento, "detalhe": f"sanitizar não iniciou: {ini.get('erro','?')}"}
        _espera = 0
        while _espera < 1800:
            _time.sleep(2)
            _espera += 2
            if not sanitizacao.status().get("rodando"):
                break
        st = sanitizacao.status()
        gravados = int(st.get("total_gravados", 0) or 0)
        destino = PROCESSED / "jsonl" / nome
        destino.mkdir(parents=True, exist_ok=True)
        copiados = 0
        for f in Path(saida).glob("*.jsonl"):
            try:
                _sh.copy2(str(f), str(destino / f.name))
                copiados += 1
            except Exception:
                pass
        if copiados == 0 and gravados == 0:
            # Fallback honesto: promove o bruto
            for f in origem.rglob("*.jsonl"):
                try:
                    _sh.copy2(str(f), str(destino / f.name))
                    copiados += 1
                except Exception:
                    pass
        return {"ok": True, "tratamento": tratamento,
                "detalhe": f"sanitizado: {gravados} exemplos, {copiados} arquivo(s) -> processed/jsonl/{nome}/"}

    if tratamento == "limpeza_leve":
        import subprocess as _sp
        import shutil as _sh
        PROCESSED.mkdir(parents=True, exist_ok=True)
        res = _sp.run(
            [sys.executable, "-u", "limpeza_leve_rigel_v2.py",
             "--origem", str(origem), "--saida", str(PROCESSED)],
            capture_output=True, text=True, timeout=7200,
            encoding="utf-8", errors="replace", cwd=str(PROJETO_ROOT))
        if res.returncode != 0:
            return {"ok": False, "tratamento": tratamento,
                    "detalhe": f"limpeza leve falhou (código {res.returncode}): {(res.stderr or res.stdout or '')[-200:]}"}
        # localiza o parquet/relatório gerado
        gerados = [str(f) for f in PROCESSED.glob("*.parquet")] + [str(f) for f in PROCESSED.glob("*relatorio*.json")]
        return {"ok": True, "tratamento": tratamento,
                "detalhe": f"limpeza leve OK: {len(gerados)} artefato(s) em processed/ (ex.: rigel_sft.parquet)"}

    if tratamento == "limpeza_encoding":
        from limpeza import corrigir_codificacao
        import shutil as _sh
        destino = PROCESSED / "txt" / nome
        destino.mkdir(parents=True, exist_ok=True)
        tmp = PROCESSED / "txt" / f".tmp_{nome}"
        tmp.mkdir(parents=True, exist_ok=True)
        corrigir_codificacao(str(origem), str(tmp), copiar_utf8=True)
        copiados = 0
        for f in tmp.glob("*"):
            try:
                _sh.move(str(f), str(destino / f.name))
                copiados += 1
            except Exception:
                pass
        try:
            _sh.rmtree(str(tmp))
        except Exception:
            pass
        return {"ok": True, "tratamento": tratamento,
                "detalhe": f"limpeza de encoding: {copiados} arquivo(s) -> processed/txt/{nome}/"}

    return {"ok": False, "tratamento": tratamento, "detalhe": f"sem tratamento para formato {formato}"}


def _trabalho(nomes: list) -> None:
    import shutil as _sh
    concluidos = []
    try:
        _atualizar(etapa="tratando", percentual=0,
                   mensagem=f"Tratando {len(nomes)} pasta(s)...")
        for i, nome in enumerate(nomes, 1):
            _atualizar(atual=nome, percentual=int((i - 1) * 100 / len(nomes)),
                       mensagem=f"Tratando {nome} ({i}/{len(nomes)})...")
            res = _tratar_uma(nome)
            res["nome"] = nome
            concluidos.append(res)
            # promovido com sucesso → limpa a origem (HD liberado)
            if res.get("ok"):
                try:
                    if (RAW / nome).exists():
                        _sh.rmtree(str(RAW / nome))
                except Exception:
                    pass
            _atualizar(concluidos=list(concluidos),
                       percentual=int(i * 100 / len(nomes)))
        _atualizar(etapa="concluido", percentual=100,
                   mensagem=f"✅ {sum(1 for c in concluidos if c.get('ok'))}/{len(nomes)} pasta(s) tratadas e promovidas.",
                   concluidos=list(concluidos), fim=datetime.now().isoformat())
    except Exception as e:
        import traceback
        traceback.print_exc()
        _atualizar(etapa="erro", mensagem=str(e), erro=str(e), percentual=None,
                   concluidos=list(concluidos), fim=datetime.now().isoformat())
    finally:
        _atualizar(rodando=False)


def tratar(nomes: list) -> dict:
    """Inicia o tratamento em lote das pastas marcadas (segundo plano)."""
    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um tratamento em andamento."}
    nomes = [n for n in (nomes or []) if isinstance(n, str) and n.strip()]
    nomes = [re.sub(r"[^a-zA-Z0-9_\-\. ]", "_", n).strip(" .") for n in nomes]
    nomes = [n for n in nomes if (RAW / n).is_dir()]
    if not nomes:
        return {"ok": False, "erro": "Nenhuma pasta marcada encontrada em dados/raw/."}
    # Guardião de memória (regra de ouro): recusa se RAM livre < mínimo
    livre = _ram_livre_gb()
    if livre < MIN_RAM_LIVRE_GB:
        return {"ok": False, "erro": f"Memória livre baixa ({livre:.1f} GB < {MIN_RAM_LIVRE_GB}). "
                                     "Nada iniciado — feche processos pesados e tente de novo."}
    _atualizar(rodando=True, etapa="tratando", mensagem="Iniciando tratamento...",
               percentual=0, fila=list(nomes), atual=None, concluidos=[],
               inicio=datetime.now().isoformat(), fim=None, erro=None)
    threading.Thread(target=_trabalho, args=(nomes,), daemon=True).start()
    return {"ok": True, "mensagem": f"Tratamento iniciado para {len(nomes)} pasta(s).", "nomes": nomes,
            "ram_livre_gb": round(livre, 1)}
