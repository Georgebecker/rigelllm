#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ollama_modelos.py — Download de modelos Ollama SLM pré-definidos (página /chat).

Lista os modelos instalados (GET /api/tags do Ollama) e baixa modelos
pequenos (SLM) com `ollama pull`, rodando em thread e reportando progresso
percentual para a página. Quando não há nenhum modelo no chat, a página
oferece 3 modelos mais usados para baixar com um clique.

Endpoints (routes/ollama.py):
  GET  /api/ollama/modelos       → modelos instalados
  POST /api/ollama/pull          → inicia o download (thread)
  GET  /api/ollama/pull/status   → progresso do download
"""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import threading
from pathlib import Path
import time
import urllib.parse
import urllib.request
from datetime import datetime

OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
RAIZ = Path(__file__).resolve().parent.parent.parent

# Lista curada de SLMs CONVERSACIONAIS (chat/texto) — a página mostra um
# dropdown com nome, tamanho e finalidade (chat, textos, RSS, debates, podcast).
MODELOS_SUGERIDOS = [
    {
        "id": "llama3.2:3b",
        "tamanho": "~2,0 GB",
        "finalidade": ["chat", "conversação", "resumo RSS", "debates", "podcast"],
        "desc": "Meta — o melhor conversador e resumidor em PT-BR testado aqui. Recomendado.",
    },
    {
        "id": "gemma2:2b",
        "tamanho": "~1,6 GB",
        "finalidade": ["chat", "geração de textos", "conversação"],
        "desc": "Google — leve e rápido, bom para chat e textos no geral.",
    },
    {
        "id": "qwen2.5:3b",
        "tamanho": "~1,9 GB",
        "finalidade": ["chat", "geração de textos", "resumo RSS", "debates"],
        "desc": "Alibaba — versátil: conversa, gera e resume bem.",
    },
    {
        "id": "llama3.2:1b",
        "tamanho": "~1,3 GB",
        "finalidade": ["chat", "conversação"],
        "desc": "Meta — bem leve (ideal para celular), conversa simples.",
    },
    {
        "id": "phi3:mini",
        "tamanho": "~2,2 GB",
        "finalidade": ["geração de textos", "raciocínio", "debates técnicos"],
        "desc": "Microsoft — forte em raciocínio/texto (PT-BR mais fraco).",
    },
    {
        "id": "tinyllama:1.1b",
        "tamanho": "~600 MB",
        "finalidade": ["chat", "conversação"],
        "desc": "Ultra leve — roda em celular fraco, chat básico.",
    },
]

# Estado do pull (thread-safe)
_estado: dict = {
    "baixando": False,
    "modelo": None,
    "percentual": 0,
    "progresso_bytes": "",   # ex.: "615MB / 1.3GB" quando o ollama reporta
    "mensagem": "",
    "etapa": "idle",   # idle | baixando | concluido | erro | interrompido
    "inicio": None,
    "fim": None,
    "erro": None,
    "sharded_repo": None,    # p/ retomar GGUF sharded (baixa direto do HF)
    "sharded_quant": None,
}
_lock = threading.Lock()

# 📜 Log de ações/erros dos modelos (baixar, remover, quantizar) — rastro p/ tratamento
LOG_ACOES = RAIZ / "logs" / "modelos_acoes.log"
# Persistência do download: sobrevive a --reload/reinício (p/ retomar)
_PERSIST = RAIZ / "estado" / "ollama_pull_estado.json"


def _log_acao(acao: str, modelo: str, ok: bool, detalhe: str = "") -> None:
    """Registra uma ação/erro no log (logs/modelos_acoes.log)."""
    try:
        LOG_ACOES.parent.mkdir(parents=True, exist_ok=True)
        status = "OK  " if ok else "ERRO"
        linha = f"[{datetime.now().isoformat(timespec='seconds')}] {status} | {acao} | {modelo} | {detalhe}"
        with open(LOG_ACOES, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def acoes_recentes(n: int = 40) -> list:
    """Últimas linhas do log de ações (para exibir no dashboard)."""
    try:
        if not LOG_ACOES.exists():
            return []
        linhas = LOG_ACOES.read_text(encoding="utf-8", errors="replace").splitlines()
        return linhas[-max(1, n):]
    except Exception:
        return []


_last_persist = 0.0


def _atualizar(**kwargs) -> None:
    """Atualiza o estado do pull e PERSISTE (sobrevive a --reload/reinício).
    Grava no máx. 1×/s durante o download e sempre nos estados finais."""
    global _last_persist
    with _lock:
        _estado.update(kwargs)
        agora = time.time()
        if (_estado.get("etapa") in ("concluido", "erro", "interrompido")
                or agora - _last_persist >= 1.0):
            _last_persist = agora
            _persistir()


def _persistir() -> None:
    """Grava o estado. SEMPRE chamada já segurando `_lock` (Lock não é
    reentrante — re-adquirir aqui causaria deadlock)."""
    try:
        _PERSIST.parent.mkdir(parents=True, exist_ok=True)
        _PERSIST.write_text(json.dumps(_estado, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    except Exception:
        pass


def _carregar() -> None:
    """Restaura o estado do pull de uma execução anterior. Se dizia 'baixando',
    o processo anterior morreu → marca como interrompido (retomável)."""
    try:
        if not _PERSIST.exists():
            return
        d = json.loads(_PERSIST.read_text(encoding="utf-8"))
        if not isinstance(d, dict):
            return
        if d.get("baixando"):
            d.update(baixando=False, etapa="interrompido",
                     mensagem=("⏸️ Download interrompido (servidor reiniciou). "
                               "Clique em Retomar — o Ollama continua de onde parou."),
                     progresso_bytes=d.get("progresso_bytes") or "")
        with _lock:
            _estado.update({k: v for k, v in d.items() if k in _estado})
    except Exception:
        pass


def get_estado() -> dict:
    with _lock:
        return dict(_estado)


def retomar() -> dict:
    """Retoma o último download.
    - GGUF sharded (baixa do HF): re-despacha baixar_sharded (reutiliza arquivo já baixado).
    - `ollama pull`: o Ollama continua de onde parou.
    """
    with _lock:
        sharded_repo = _estado.get("sharded_repo") or ""
        sharded_quant = _estado.get("sharded_quant") or "Q8_0"
        modelo = _estado.get("modelo") or ""
        if not modelo and not sharded_repo:
            return {"ok": False, "mensagem": "Nenhum download para retomar."}
    if _estado.get("baixando"):
        return {"ok": False, "mensagem": "Já existe um download em andamento."}
    if sharded_repo:
        return baixar_sharded(sharded_repo, sharded_quant)
    return baixar(modelo)


def limpar_pull() -> dict:
    """Esquece o último download (estado idle) — não apaga arquivos parciais."""
    with _lock:
        _estado.update(baixando=False, modelo=None, percentual=0, progresso_bytes="",
                       mensagem="", etapa="idle", inicio=None, fim=None, erro=None,
                       sharded_repo=None, sharded_quant=None)
        _persistir()
    return {"ok": True, "mensagem": "Estado do download limpo."}


# Restaura o estado de um processo anterior (marca interrompido se estava baixando)
_carregar()


def listar_modelos() -> list[str]:
    """Modelos instalados no Ollama (via API /api/tags)."""
    try:
        req = urllib.request.Request(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def _parse_progresso(linha: str) -> int | None:
    """Extrai percentual (0-100) de uma linha do `ollama pull`."""
    m = re.search(r"(\d{1,3})\s*%", linha)
    if m:
        try:
            return max(0, min(100, int(m.group(1))))
        except ValueError:
            return None
    return None


def _ultimas_linhas(texto: str, n: int = 8) -> str:
    """Limpa códigos ANSI (spinners) e devolve as últimas linhas úteis do erro."""
    try:
        limpo = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07", "", texto or "")
        linhas = [l.strip() for l in limpo.splitlines() if l.strip()]
        return " | ".join(linhas[-n:])
    except Exception:
        return (texto or "")[:300]


def caminho_modelos() -> str:
    """Pasta onde o Ollama guarda os modelos (env OLLAMA_MODELS ou padrão ~/.ollama/models)."""
    try:
        env = os.environ.get("OLLAMA_MODELS", "").strip()
        if env:
            return env
        home = os.path.expanduser("~")
        for cand in (os.path.join(home, ".ollama", "models"),
                     os.path.join(home, ".ollama")):
            if os.path.isdir(cand):
                return cand
    except Exception:
        pass
    return "~/.ollama/models"


def remover(modelo: str) -> dict:
    """Remove um modelo do Ollama (da lista e do disco) — `ollama rm <modelo>`."""
    modelo = modelo.strip()
    if not modelo:
        return {"ok": False, "mensagem": "Informe o modelo a remover."}
    try:
        proc = subprocess.run(
            ["ollama", "rm", modelo], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if proc.returncode == 0:
            _log_acao("remover", modelo, True, "removido do disco")
            return {"ok": True, "mensagem": f"🗑️ {modelo} removido do disco."}
        err = (proc.stderr or proc.stdout or "").strip()
        _log_acao("remover", modelo, False, err[:200])
        return {"ok": False, "mensagem": f"Falha ao remover {modelo}: {err[:200]}"}
    except FileNotFoundError:
        return {"ok": False, "mensagem": "Comando 'ollama' não encontrado."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "mensagem": f"Erro ao remover {modelo}: {e}"}


# ============================================================================
# 🔎 Busca de modelos no HuggingFace (GGUF) com filtro inteligente por RAM
# ============================================================================

# Quantizações GGUF conhecidas (para rotular os arquivos e dar bom padrão)
_RE_QUANT = re.compile(
    r"(Q\d(?:_K_[A-Z]|_K_S|_K_M|_K_L|_\d)?|IQ\d+_[A-Z]+|F16|F32|BF16|FP8)", re.IGNORECASE)
# RAM necessária ≈ tamanho do GGUF × fator (modelo + contexto do Ollama).
# 1,6× = conservador (evita superaquecimento/travamentos). Mais otimista = 1,2×.
FATOR_RAM = 1.6
# Orçamento: só oferecer modelos/quantizações que precisem de até X% da RAM
# TOTAL da máquina (detectada por hardware via psutil). Conservador (70%) deixa
# folga para o sistema + contexto + evitar aquecer/travar. 0.95 = arriscado.
TETO_RAM_PCT = 0.7
# Máx. de quantizações mostradas por modelo no seletor (evita dropdown gigante)
MAX_QUANTS = 6
# Ordem de preferência das quantizações (padrão-ouro + populares)
PREFERIDAS = ["Q4_K_M", "Q4_K_S", "Q5_K_M", "Q5_K_S", "Q6_K", "Q8_0",
              "Q6", "Q3_K_M", "Q3_K_S", "IQ4_XS", "Q4_0", "Q5_0", "F16", "BF16", "F32"]
HF_API = "https://huggingface.co/api/models"


def _limitar_quants(quants: list) -> list:
    """Limita a MAX_QUANTS quantizações por modelo (seletor legível).

    Prioridade: recomendada (Q4_K_M) → populares (PREFERIDAS) → menores.
    Sempre ordenadas por tamanho (menor → maior).
    """
    if len(quants) <= MAX_QUANTS:
        return quants
    por_quant = {q["quant"]: q for q in quants}
    ordem: list[str] = []
    rec = por_quant.get("Q4_K_M")
    if rec:
        ordem.append("Q4_K_M")
    for pref in PREFERIDAS:
        if len(ordem) >= MAX_QUANTS:
            break
        if pref in por_quant and pref not in ordem:
            ordem.append(pref)
    for q in quants:  # completa com os menores
        if len(ordem) >= MAX_QUANTS:
            break
        if q["quant"] not in ordem:
            ordem.append(q["quant"])
    final = [por_quant[k] for k in ordem if k in por_quant]
    final.sort(key=lambda q: q["tamanho_mb"])
    return final


def _ram_total_gb() -> float:
    """RAM TOTAL da máquina (detectada por hardware — não é fixa de 32 GB).
    Cada aparelho reporta a dele; o orçamento p/ modelos é TETO_RAM_PCT dela."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 16.0


def orcamento_ram_gb() -> float:
    """O que o usuário pode alocar p/ modelo com folga (conservador)."""
    return round(_ram_total_gb() * TETO_RAM_PCT, 1)


def _extrair_quants(siblings: list) -> list[dict]:
    """De uma lista de siblings (com tamanho), devolve os arquivos .gguf agrupados
    por QUANTIZAÇÃO. GGUFs divididos em partes (model-00001-of-00008...) são
    somados — mostra o TAMANHO TOTAL do modelo naquela quant, não só de uma parte."""
    grupos: dict[str, dict] = {}
    for s in siblings:
        nome = s.get("rfilename") or ""
        if not nome.endswith(".gguf"):
            continue
        tamanho = s.get("size") or 0
        if not tamanho:
            continue
        m = _RE_QUANT.search(nome)
        quant = m.group(1).upper() if m else "GGUF"
        g = grupos.setdefault(quant, {"quant": quant, "arquivo": nome,
                                      "tamanho_mb": 0.0, "partes": 0})
        g["tamanho_mb"] += tamanho / 1e6
        g["partes"] += 1
        if g["partes"] == 1:
            g["arquivo"] = nome
    if not grupos:
        return []
    quants = list(grupos.values())
    for g in quants:
        g["tamanho_mb"] = round(g["tamanho_mb"], 1)
        g["ram_gb"] = round(g["tamanho_mb"] / 1e3 * FATOR_RAM, 1)
        g["recomendado"] = g["quant"] == "Q4_K_M"
    # ordena do menor para o maior
    quants.sort(key=lambda q: q["tamanho_mb"])
    return quants


def buscar_modelos(q: str, limite: int = 10) -> dict:
    """Busca modelos GGUF no HuggingFace, calcula tamanho e RAM necessária,
    e devolve SÓ as quantizações que cabem na RAM da máquina (protege o usuário
    de baixar modelo que não vai rodar — e não estoura o HD)."""
    q = (q or "").strip()
    if not q:
        return {"ok": False, "erro": "Informe o que buscar."}
    orcamento = orcamento_ram_gb()
    limite = max(1, min(20, int(limite)))
    try:
        url = (f"{HF_API}?search={urllib.parse.quote(q)}&filter=gguf"
               f"&sort=downloads&direction=-1&limit={limite}")
        req = urllib.request.Request(url, headers={"User-Agent": "RigelSLM/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            repos = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "erro": f"Falha ao consultar o HuggingFace: {e}"}

    # Detalhe de cada repo (blobs=true traz os tamanhos) em paralelo
    def _detalhe(repo: dict) -> dict | None:
        try:
            rid = repo.get("id")
            req = urllib.request.Request(
                f"{HF_API}/{rid}?blobs=true", headers={"User-Agent": "RigelSLM/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read().decode("utf-8"))
            quants = _extrair_quants(d.get("siblings") or [])
            if not quants:
                return None
            # só as quantizações que cabem no orçamento conservador de RAM, sem
            # qualidade 1-2 bits (Q1/Q2/IQ1/IQ2 rodam mas são inúteis p/ conversar),
            # limitadas p/ seletor legível
            quants_ok = _limitar_quants(
                [q for q in quants
                 if q["ram_gb"] <= orcamento
                 and not q["quant"].startswith(("Q1", "Q2", "IQ1", "IQ2"))])
            if not quants_ok:
                return None  # NÃO mostra modelo que a máquina não roda
            tags = repo.get("tags") or []
            params = next((t for t in tags if re.fullmatch(r"\d+[.]?\d*[bB]", t)), None)
            # GGUF sharded = qualquer arquivo com padrão -00001-of-000NN.gguf.
            # Se o repo tem sharded, o `ollama pull hf.co/` falha (erro 400) mesmo
            # para as quants de arquivo único → botão "Baixar+juntar".
            sharded = any(
                re.search(r"-\d{5}-of-\d{5}\.", (s.get("rfilename") or ""))
                for s in (d.get("siblings") or []))
            return {
                "id": rid,
                "downloads": repo.get("downloads", 0),
                "likes": repo.get("likes", 0),
                "params": params or "",
                "pipeline": repo.get("pipeline_tag") or "",
                "quants": quants_ok,
                "quants_total": len(quants),
                "sharded": sharded,
            }
        except Exception:
            return None

    import concurrent.futures as _cf
    resultados = []
    with _cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(_detalhe, repos, timeout=45):
            if r:
                resultados.append(r)
    resultados.sort(key=lambda x: x["downloads"], reverse=True)
    return {
        "ok": True,
        "q": q,
        "ram_total_gb": round(_ram_total_gb(), 1),
        "orcamento_gb": orcamento,
        "ocultados_incompativeis": limite - len(resultados),
        "resultados": resultados,
    }


def baixar(modelo: str) -> dict:
    """Dispara `ollama pull <modelo>` em thread. Retorna estado inicial."""
    modelo = modelo.strip()
    if not modelo or ":" not in modelo:
        return {"ok": False, "mensagem": "Informe o modelo no formato nome:tag (ex.: llama3.2:3b)."}
    with _lock:
        if _estado["baixando"]:
            return {"ok": False, "mensagem": f"Já está baixando {_estado['modelo']}."}
        _estado.update(baixando=True, modelo=modelo, percentual=0, progresso_bytes="",
                       mensagem=f"Iniciando download de {modelo}...", etapa="baixando",
                       inicio=datetime.now().isoformat(), fim=None, erro=None)
    _log_acao("download", modelo, True, "iniciado")
    threading.Thread(target=_pull_trabalho, args=(modelo,), daemon=True).start()
    return {"ok": True, "mensagem": f"Download de {modelo} iniciado."}


def _pull_trabalho(modelo: str) -> None:
    _inicio = time.time()
    _ultimas: list[str] = []
    try:
        proc = subprocess.Popen(
            ["ollama", "pull", modelo],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        assert proc.stdout is not None
        for linha in proc.stdout:
            linha = linha.strip()
            if linha:
                _ultimas.append(linha)
                if len(_ultimas) > 8:
                    _ultimas.pop(0)
            m_bytes = re.search(
                r"(\d+(?:\.\d+)?)\s*([KMG]i?B)\s*/\s*(\d+(?:\.\d+)?)\s*([KMG]i?B)", linha)
            if m_bytes:
                _atualizar(progresso_bytes=(
                    f"{m_bytes.group(1)}{m_bytes.group(2)} / {m_bytes.group(3)}{m_bytes.group(4)}"))
            pct = _parse_progresso(linha)
            if pct is not None:
                _atualizar(percentual=pct,
                           mensagem=f"Baixando {modelo}... {pct}%")
            elif linha and "downloading" not in linha.lower():
                _atualizar(mensagem=linha[-160:])
        proc.wait()
        if proc.returncode == 0:
            _atualizar(baixando=False, etapa="concluido", percentual=100,
                       mensagem=(f"✅ {modelo} instalado em "
                                 f"{time.time() - _inicio:.0f}s."),
                       fim=datetime.now().isoformat())
            _log_acao("download", modelo, True,
                       f"concluído ({_estado.get('progresso_bytes') or ''}, {time.time()-_inicio:.0f}s)")
        else:
            raise RuntimeError(f"ollama pull falhou (código {proc.returncode})")
    except Exception as e:  # noqa: BLE001
        # captura as últimas linhas da saída do ollama (causa real do erro)
        detalhe = str(e)[:180]
        linhas = [x for x in _ultimas if x.strip()][-5:]
        if linhas:
            detalhe += " | " + " | ".join(linhas)[-350:]
        _atualizar(baixando=False, etapa="erro",
                   mensagem=f"❌ Falha ao baixar {modelo}: {detalhe}",
                   erro=detalhe[:300], fim=datetime.now().isoformat())
        _log_acao("download", modelo, False, detalhe[:300])


# ============================================================================
# ⚙️ Quantizar um modelo JÁ INSTALADO (llama-quantize → ollama create)
#    Baixou um modelo grande? Quantize localmente p/ uma versão menor que
#    cabe na RAM conservadora da máquina (sem superaquecer/travar).
# ============================================================================

PASTA_QUANT = RAIZ / "gguf" / "quantizados"
# Tamanho aproximado de cada quantização (relativo ao F16 = 1.0)
QUANT_RATIO = {
    "F32": 2.0, "F16": 1.0, "BF16": 1.0, "Q8_0": 0.60, "Q6_K": 0.49,
    "Q5_K_M": 0.42, "Q5_K_S": 0.40, "Q5_0": 0.40, "Q4_K_M": 0.34,
    "Q4_K_S": 0.32, "Q4_0": 0.31, "IQ4_XS": 0.30, "Q3_K_M": 0.27, "Q3_K_S": 0.26,
}
QUANTS_OFERTA = ["Q8_0", "Q6_K", "Q5_K_M", "Q5_K_S", "Q4_K_M", "Q4_K_S", "IQ4_XS", "Q3_K_M", "Q3_K_S"]

_quant_estado: dict = {
    "rodando": False, "modelo": None, "quant": None, "etapa": "idle",
    "mensagem": "", "percentual": 0, "inicio": None, "fim": None,
    "erro": None, "novo_nome": None,
}
_quant_lock = threading.Lock()


def _atualizar_quant(**kwargs) -> None:
    with _quant_lock:
        _quant_estado.update(kwargs)


def get_quant_estado() -> dict:
    with _quant_lock:
        return dict(_quant_estado)


def _manifesto_modelo(modelo: str):
    """Retorna (blob_gguf: Path, tamanho_bytes) do modelo Ollama (via manifest)."""
    nome, _, tag = modelo.strip().partition(":")
    tag = tag or "latest"
    if "/" not in nome:
        nome = f"library/{nome}"
    models_dir = os.environ.get("OLLAMA_MODELS", "").strip() or str(Path.home() / ".ollama" / "models")
    mani = Path(models_dir) / "manifests" / "registry.ollama.ai" / nome / tag
    if not mani.exists():
        return None
    d = json.loads(mani.read_text(encoding="utf-8"))
    for l in d.get("layers", []):
        if l.get("mediaType") == "application/vnd.ollama.image.model":
            digest = (l.get("digest") or "").replace(":", "-")
            blob = Path(models_dir) / "blobs" / digest
            if blob.exists():
                return blob, l.get("size") or blob.stat().st_size
    return None


def _quant_atual(modelo: str) -> str:
    try:
        r = subprocess.run(["ollama", "show", modelo], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        for linha in (r.stdout or "").splitlines():
            linha = linha.strip()
            if linha.lower().startswith("quantization"):
                return linha.split()[-1].upper()
    except Exception:
        pass
    return "F16"


def opcoes_quantizacao(modelo: str) -> dict:
    """Quantizações possíveis: menores que a atual E que cabem na RAM conservadora."""
    modelo = modelo.strip()
    if not modelo:
        return {"ok": False, "erro": "Selecione um modelo primeiro."}
    info = _manifesto_modelo(modelo)
    if not info:
        return {"ok": False, "erro": "GGUF do modelo não encontrado no Ollama."}
    _, size = info
    atual = _quant_atual(modelo)
    ratio_atual = QUANT_RATIO.get(atual, 1.0)
    orcamento = orcamento_ram_gb()
    opcoes = []
    for q in QUANTS_OFERTA:
        ratio = QUANT_RATIO.get(q)
        if ratio is None or ratio >= ratio_atual - 1e-9:
            continue  # só quantizações MENORES que a atual
        est_gb = size / 1e9 * ratio / ratio_atual
        if est_gb * FATOR_RAM > orcamento:
            continue  # não cabe no orçamento conservador de RAM
        opcoes.append({
            "quant": q,
            "tamanho_mb": round(size / 1e6 * ratio / ratio_atual, 1),
            "ram_gb": round(est_gb * FATOR_RAM, 1),
        })
    opcoes.sort(key=lambda o: o["tamanho_mb"])
    return {
        "ok": True, "modelo": modelo, "quant_atual": atual,
        "tamanho_atual_mb": round(size / 1e6, 1),
        "orcamento_gb": orcamento,
        "opcoes": opcoes,
    }


def quantizar(modelo: str, quant: str) -> dict:
    """Quantiza um modelo instalado em thread e cria o novo modelo no Ollama."""
    modelo, quant = modelo.strip(), quant.strip().upper()
    if not modelo or not quant:
        return {"ok": False, "mensagem": "Informe modelo e quantização."}
    with _quant_lock:
        if _quant_estado["rodando"]:
            return {"ok": False, "mensagem": f"Já está quantizando {_quant_estado['modelo']}."}
        _quant_estado.update(rodando=True, modelo=modelo, quant=quant, etapa="trabalhando",
                             mensagem=f"Preparando {modelo} → {quant}...", percentual=0,
                             inicio=datetime.now().isoformat(), fim=None, erro=None, novo_nome=None)
    _log_acao("quantizar", modelo, True, f"iniciado → {quant}")
    threading.Thread(target=_quant_trabalho, args=(modelo, quant), daemon=True).start()
    return {"ok": True, "mensagem": f"Quantização de {modelo} para {quant} iniciada."}


def _quant_trabalho(modelo: str, quant: str) -> None:
    _CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        info = _manifesto_modelo(modelo)
        if not info:
            raise RuntimeError("GGUF do modelo não encontrado (manifest).")
        blob, _ = info
        nome, _, tag = modelo.partition(":")
        tag = tag or "latest"
        novo = f"{nome}:{tag}-q{quant.replace('_', '').lower()}"
        PASTA_QUANT.mkdir(parents=True, exist_ok=True)
        base = re.sub(r"[^A-Za-z0-9_.-]", "_", nome.replace("/", "_"))[:40]
        out = PASTA_QUANT / f"{base}_{tag}_{quant}.gguf"

        _atualizar_quant(mensagem=f"Quantizando {quant} (llama-quantize)...", percentual=3)
        # --allow-requantize: permite reduzir um modelo já quantizado (ex.: Q8_0 → Q4_K_M)
        proc = subprocess.Popen(
            ["llama-quantize", "--allow-requantize", str(blob), str(out), quant],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=_CREATE_NO_WINDOW,
        )
        assert proc.stdout is not None
        for linha in proc.stdout:
            m = re.search(r"(\d+)\s*/\s*(\d+)", linha)
            if m:
                pct = int(m.group(1)) / max(1, int(m.group(2))) * 100
                _atualizar_quant(percentual=round(pct),
                                 mensagem=f"Quantizando {quant}... {round(pct)}%")
        proc.wait()
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"llama-quantize falhou (código {proc.returncode}).")

        _atualizar_quant(mensagem="Criando modelo no Ollama (ollama create)...", percentual=96)
        modelfile = PASTA_QUANT / f"{base}_{tag}_{quant}.Modelfile"
        modelfile.write_text(f"FROM {out}\n", encoding="utf-8")
        cr = subprocess.run(["ollama", "create", novo, "-f", str(modelfile)],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=600)
        # limpa os temporários (o ollama create copia o GGUF p/ o store)
        try:
            out.unlink(missing_ok=True)
            modelfile.unlink(missing_ok=True)
        except Exception:
            pass
        if cr.returncode != 0:
            raise RuntimeError(f"ollama create falhou: {(cr.stderr or cr.stdout or '')[:200]}")
        _atualizar_quant(rodando=False, etapa="concluido", percentual=100,
                         mensagem=f"✅ Criado {novo} ({quant} — menor que {modelo}).",
                         novo_nome=novo, fim=datetime.now().isoformat())
        _log_acao("quantizar", modelo, True, f"criado {novo} ({quant})")
    except Exception as e:  # noqa: BLE001
        _atualizar_quant(rodando=False, etapa="erro",
                         mensagem=f"❌ Falha na quantização: {e}",
                         erro=str(e)[:300], fim=datetime.now().isoformat())
        _log_acao("quantizar", modelo, False, str(e)[:200])


# ============================================================================
# 🧩 GGUF SHARDED (dividido em partes) — o `ollama pull hf.co/` NÃO suporta
#    (erro 400 "sharded GGUF", issue ollama #5245). Solução: baixar TODAS as
#    partes do HuggingFace → juntar com llama-gguf-split --merge → ollama create.
# ============================================================================

_GGUF_TAM = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}


def _pular_valor_gguf(buf: bytes, off: int, tipo: int) -> int:
    """Devolve o offset APÓS o valor KV (suporta string e array)."""
    if tipo == 8:  # string: [len u64][bytes]
        n = struct.unpack_from("<Q", buf, off)[0]
        return off + 8 + n
    if tipo == 9:  # array: [elem_type u32][count u64] + count × elem
        et = struct.unpack_from("<I", buf, off)[0]
        cnt = struct.unpack_from("<Q", buf, off + 4)[0]
        off += 12
        for _ in range(min(cnt, 2_000_000)):
            if et == 8:
                n = struct.unpack_from("<Q", buf, off)[0]
                off += 8 + n
            else:
                off += _GGUF_TAM.get(et, 8)
        return off
    return off + _GGUF_TAM.get(tipo, 0)


def _ler_arquitetura_gguf(url: str) -> str:
    """Baixa SÓ o cabeçalho (512 KB) e lê `general.architecture` do GGUF.
    Avisa ANTES de baixar GBs (ex.: arquitetura nova que o Ollama instalado
    não suporta — o create falharia depois de gastar o download)."""
    for _tentativa in range(2):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "RigelSLM/1.0", "Range": "bytes=0-524287"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if data[:4] != b"GGUF":
                return "?"

            def _ler_str(buf: bytes, off: int):
                n = struct.unpack_from("<Q", buf, off)[0]
                return buf[off + 8: off + 8 + n].decode("utf-8", "replace"), off + 8 + n

            n_kv = struct.unpack_from("<Q", data, 12)[0]
            off = 24  # magic(4) + versão(4) + tensores(8) + kvs(8)
            for _ in range(min(n_kv, 500)):
                chave, off = _ler_str(data, off)
                tipo = struct.unpack_from("<I", data, off)[0]
                off += 4
                if chave == "general.architecture":
                    val, _ = _ler_str(data, off)
                    return val
                novo_off = _pular_valor_gguf(data, off, tipo)
                if novo_off <= off or novo_off > len(data) - 16:
                    return "?"
                off = novo_off
            return "?"
        except Exception:
            continue
    return "?"


def _baixar_arquivo_stream(url: str, destino: Path, base_bytes: int,
                           total_bytes: int, rotulo: str) -> int:
    """Baixa com progresso (chunks de 1 MB), atualizando o estado global do pull."""
    req = urllib.request.Request(url, headers={"User-Agent": "RigelSLM/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(destino, "wb") as f:
        while True:
            bloco = r.read(1024 * 1024)
            if not bloco:
                break
            f.write(bloco)
            base_bytes += len(bloco)
            if total_bytes:
                pct = round(base_bytes / total_bytes * 100)
                _atualizar(percentual=pct,
                           progresso_bytes=f"{base_bytes / 1e6:.0f}MB / {total_bytes / 1e6:.0f}MB",
                           mensagem=f"Baixando {rotulo}... {pct}%")
    return base_bytes


def baixar_sharded(repo: str, quant: str) -> dict:
    """Dispara o download das partes + merge + create (GGUF dividido)."""
    repo, quant = repo.strip(), quant.strip().upper()
    if not repo or not quant:
        return {"ok": False, "mensagem": "Informe repo e quantização."}
    with _lock:
        if _estado["baixando"]:
            return {"ok": False, "mensagem": f"Já está baixando {_estado['modelo']}."}
        _estado.update(baixando=True, modelo=f"gguf:{repo}:{quant}", percentual=0,
                       progresso_bytes="", mensagem="Verificando arquivos do GGUF...",
                       etapa="baixando", inicio=datetime.now().isoformat(), fim=None, erro=None,
                       sharded_repo=repo, sharded_quant=quant)
    _log_acao("baixar-sharded", repo, True, f"iniciado {quant}")
    threading.Thread(target=_sharded_trabalho, args=(repo, quant), daemon=True).start()
    return {"ok": True, "mensagem": f"Download de {repo} ({quant}) iniciado — será instalado no Ollama."}


def _sharded_trabalho(repo: str, quant: str) -> None:
    _CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    pasta = RAIZ / "gguf" / "baixados" / re.sub(r"[^A-Za-z0-9_.-]", "_", repo)
    try:
        # 1) lista os arquivos .gguf do repo (com tamanho)
        req = urllib.request.Request(f"{HF_API}/{repo}?blobs=true",
                                     headers={"User-Agent": "RigelSLM/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            detail = json.loads(r.read().decode("utf-8"))
        siblings = detail.get("siblings") or []
        shard_re = re.compile(r"-\d{5}-of-\d{5}\.")

        def _quant_de(nome: str) -> str:
            m = _RE_QUANT.search(nome)
            return m.group(1).upper() if m else ""

        # 2) partes: shards desta quant OU (se a quant é arquivo único) o arquivo
        shards = [s for s in siblings
                  if s.get("rfilename", "").endswith(".gguf") and s.get("size")
                  and shard_re.search(s.get("rfilename", ""))
                  and _quant_de(s["rfilename"]) == quant]
        if len(shards) > 1:
            shards.sort(key=lambda s: s["rfilename"])
            partes = shards
            precisa_merge = True
        else:
            # a quant escolhida é UM arquivo (repo tem shards de outras quants)
            partes = [s for s in siblings
                      if s.get("rfilename", "").endswith(".gguf") and s.get("size")
                      and not shard_re.search(s.get("rfilename", ""))
                      and _quant_de(s["rfilename"]) == quant]
            precisa_merge = False
        if not partes:
            raise RuntimeError(f"Nenhum arquivo {quant}.gguf encontrado no repositório.")
        total_bytes = sum(s.get("size") or 0 for s in partes)

        # 2.5) arquitetura no cabeçalho (512 KB) — NÃO baixa GBs se não confirmar
        arch = _ler_arquitetura_gguf(
            f"https://huggingface.co/{repo}/resolve/main/{partes[0]['rfilename']}")
        # arquiteturas comuns suportadas pelo Ollama (edite aqui se atualizar o Ollama)
        arq_suportadas = {
            "llama", "llama2", "llama3", "qwen2", "qwen2moe", "gemma", "gemma2",
            "gemma3", "mistral", "mixtral", "phi2", "phi3", "deepseek2", "deepseek3",
            "gpt2", "falcon", "starcoder2", "command-r", "minicpm3", "olmo", "grok",
        }
        if arch == "?":
            raise RuntimeError(
                "não foi possível CONFIRMAR a arquitetura do modelo (leitura do cabeçalho "
                "falhou) — por segurança, NÃO vou baixar. Tente novamente ou escolha outro "
                "modelo.")
        if arch not in arq_suportadas:
            raise RuntimeError(
                f"arquitetura '{arch}' provavelmente NÃO é suportada pelo seu Ollama — "
                f"o 'create' falharia depois de baixar. Atualize o Ollama, escolha outro "
                f"modelo/quantização, ou baixe o GGUF e use com llama.cpp.")
        _atualizar(mensagem=f"GGUF {quant} · arquitetura '{arch}'. Baixando...", percentual=0)

        # 3) baixar as partes — REUTILIZA arquivo já existente (retry não rebaixa 11 GB)
        pasta.mkdir(parents=True, exist_ok=True)
        baixado = 0
        for i, s in enumerate(partes, 1):
            nome_arq = s["rfilename"].split("/")[-1]
            destino = pasta / nome_arq
            if destino.exists() and destino.stat().st_size >= (s.get("size") or 0) * 0.99:
                baixado += s.get("size") or 0
                _atualizar(mensagem=f"Parte {i}/{len(partes)} já baixada (reaproveitando)...",
                           percentual=round(baixado / total_bytes * 100) if total_bytes else 0)
                continue
            url = f"https://huggingface.co/{repo}/resolve/main/{s['rfilename']}"
            baixado = _baixar_arquivo_stream(
                url, destino, baixado, total_bytes,
                f"parte {i}/{len(partes)} ({nome_arq})")

        # 4) juntar se for sharded (o primeiro shard referencia os demais)
        if precisa_merge:
            primeiro = pasta / partes[0]["rfilename"].split("/")[-1]
            merged = pasta / f"merged_{quant}.gguf"
            _atualizar(mensagem="Juntando as partes (llama-gguf-split --merge)...", percentual=99)
            mr = subprocess.run(["llama-gguf-split", "--merge", str(primeiro), str(merged)],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=3600)
            if mr.returncode != 0 or not merged.exists():
                raise RuntimeError(f"merge falhou: {_ultimas_linhas(mr.stderr or mr.stdout)}")
            fonte = merged
        else:
            fonte = pasta / partes[0]["rfilename"].split("/")[-1]

        # 5) criar no Ollama (nome: <repo>:q8_0, ex.: deepseek-v4-flash-0731:q8_0)
        nome_base = re.sub(r"-GGUF$", "", repo.split("/")[-1]).lower()
        nome_base = re.sub(r"[^a-z0-9_.-]", "-", nome_base)
        novo = f"{nome_base}:{quant.lower()}"
        _atualizar(mensagem=f"Criando modelo {novo} no Ollama...", percentual=100)
        modelfile = pasta / "Modelfile"
        modelfile.write_text(f"FROM {fonte}\n", encoding="utf-8")
        cr = subprocess.run(["ollama", "create", novo, "-f", str(modelfile)],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=1800)
        if cr.returncode != 0:
            raise RuntimeError(
                f"ollama create falhou (arquitetura '{arch}'): "
                f"{_ultimas_linhas(cr.stderr or cr.stdout)}")
        # SÓ limpa os temporários no SUCESSO (o create copiou p/ o store)
        try:
            shutil.rmtree(pasta, ignore_errors=True)
        except Exception:
            pass
        _atualizar(baixando=False, etapa="concluido", percentual=100,
                   mensagem=(f"✅ {novo} instalado ({quant}, "
                             f"{len(partes)} arquivo(s){' juntado(s)' if precisa_merge else ''})."),
                   fim=datetime.now().isoformat())
        _log_acao("baixar-sharded", repo, True,
                  f"criado {novo} ({quant}, {len(partes)} arquivo(s))")
    except Exception as e:  # noqa: BLE001
        # MANTÉM o arquivo baixado (não apaga) — retry reutiliza sem rebaixar
        _atualizar(baixando=False, etapa="erro",
                   mensagem=f"❌ Falha no GGUF dividido: {e}",
                   erro=str(e)[:600], fim=datetime.now().isoformat())
        _log_acao("baixar-sharded", repo, False, str(e)[:400])
