#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
train.py - Treinamento do modelo para o Dashboard RigelSLM
Versão: 1.0.0 | Data: 31/07/2026 | Arquivos de treino: 1.089
"""
from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pathlib import Path
import subprocess
from subprocess import Popen, PIPE, STDOUT
import json
import os
import re
from datetime import datetime
from dashboard.services.monitor import ler_ultimas_linhas
from dashboard.services.runner import stream_subprocess_to_log
from dashboard.services.estrutura_cache import (
    escaneador_jsonl, escaneador_txt, escaneador_parquet,
    walk_com_limites, LimiteEstourado, memoria_ok,
)

router = APIRouter(prefix="/api/train", tags=["Treinamento"])

BASE_DIR = Path(__file__).parent.parent.parent
PROCESSED_DIR = BASE_DIR / "dados" / "processed"
MODEL_DIR = BASE_DIR / "modelo"
METRICAS_PATH = BASE_DIR / "logs" / "metricas.json"
ESTADO_PATH = MODEL_DIR / "estado_treino.json"
TREINO_LOG_PATH = BASE_DIR / "logs" / "treino.log"

# Cache para evitar lentidão
_train_cache = {"status": None, "time": 0, "pastas_cache": None, "pastas_time": 0}

# Processo de treino ativo (para poder matar)
_train_process = {"proc": None, "pid": None, "started_at": None}


def _contar_txt_incremental(pasta: Path, report, i: int, total: int,
                            encontrados: int) -> tuple[int, bool]:
    """Conta .txt recursivamente com o GUARDIÃO DE LIMITES:
    - streaming (nunca materializa listas — evita MemoryError em milhões de
      arquivos, ex: exploded*);
    - não segue symlinks/junctions (evita loops);
    - pausa a cada N itens (não satura o SSD) e aborta se a memória baixar;
    - reporta progresso por diretório visitado (barra continua viva).
    Retorna (qtde, cap_atingido): se uma pasta SOZINHA estourar o cap de
    arquivos (ex.: dataset explodido com milhões de arquivos), NÃO aborta o
    scan — marca cap_atingido=True e segue para as próximas pastas."""
    qtde = 0
    cap = False

    def _on_dir(raiz_atual, dirs_vistos):
        report(pasta_atual=Path(raiz_atual).name,
               itens_processados=i + 1, total_itens=total,
               encontrados=encontrados + (1 if qtde > 0 else 0))

    try:
        for _caminho in walk_com_limites(pasta, extensoes=(".txt",), on_dir=_on_dir):
            qtde += 1
    except LimiteEstourado:
        # Pasta gigante (> SCAN_MAX_ARQUIVOS arquivos): registra parcial e segue
        cap = True
    return qtde, cap


def _scan_estrutura_txt(report) -> list[dict]:
    """Varre dados/processed reportando progresso. Retorna pastas com .txt.
    Aborta (LimiteEstourado) se a memória ficar baixa ou estourar os caps."""
    if not PROCESSED_DIR.exists():
        return []
    itens = sorted(PROCESSED_DIR.iterdir())
    total = len(itens)
    pastas = []
    for i, item in enumerate(itens):
        if not item.is_dir():
            continue
        ok, motivo = memoria_ok()
        if not ok:
            report(fase="interrompido", percentual=100, erro=motivo)
            raise LimiteEstourado(motivo)
        try:
            qtde, cap = _contar_txt_incremental(item, report, i, total, len(pastas))
        except LimiteEstourado as e:
            report(fase="interrompido", percentual=100, erro=str(e))
            raise
        if qtde > 0 or cap:
            entrada = {"nome": item.name, "arquivos": qtde,
                       "caminho": "dados/processed/" + item.name}
            if cap:
                entrada["cap_atingido"] = True
            pastas.append(entrada)
        report(percentual=((i + 1) / total) * 100 if total else 100,
               fase="varrendo", pasta_atual=item.name,
               itens_processados=i + 1, total_itens=total,
               encontrados=len(pastas))
    return pastas


def _contar_incremental(pasta: Path, ext: str, report, i: int, total: int,
                        encontrados: int) -> tuple[int, bool]:
    """Conta arquivos com extensão `ext` recursivamente (guardas de limites)."""
    qtde = 0
    cap = False

    def _on_dir(raiz_atual, dirs_vistos):
        report(pasta_atual=Path(raiz_atual).name,
               itens_processados=i + 1, total_itens=total,
               encontrados=encontrados + (1 if qtde > 0 else 0))

    try:
        for _caminho in walk_com_limites(pasta, extensoes=(ext,), on_dir=_on_dir):
            qtde += 1
    except LimiteEstourado:
        cap = True
    return qtde, cap


def _scan_estrutura(base_dir: Path, ext: str, report) -> list[dict]:
    """Varre base_dir e lista subpastas que contêm arquivos com extensão ext."""
    if not base_dir.exists():
        return []
    itens = sorted(base_dir.iterdir())
    total = len(itens)
    pastas = []
    for i, item in enumerate(itens):
        if not item.is_dir():
            continue
        ok, motivo = memoria_ok()
        if not ok:
            report(fase="interrompido", percentual=100, erro=motivo)
            raise LimiteEstourado(motivo)
        try:
            qtde, cap = _contar_incremental(item, ext, report, i, total, len(pastas))
        except LimiteEstourado as e:
            report(fase="interrompido", percentual=100, erro=str(e))
            raise
        if qtde > 0 or cap:
            entrada = {"nome": item.name, "arquivos": qtde}
            try:
                entrada["caminho"] = str(base_dir.relative_to(BASE_DIR) / item.name).replace("\\", "/")
            except Exception:
                entrada["caminho"] = str(item)
            if cap:
                entrada["cap_atingido"] = True
            pastas.append(entrada)
        report(percentual=((i + 1) / total) * 100 if total else 100,
               fase="varrendo", pasta_atual=item.name,
               itens_processados=i + 1, total_itens=total,
               encontrados=len(pastas))
    return pastas


def _scan_raso(base_dir: Path, ext: str, report) -> list[dict]:
    """Varre APENAS o nível 1 de base_dir: conta arquivos com `ext` direto em
    cada subpasta (rápido — NÃO desce nos milhões de .txt).

    Não reporta pasta por pasta (não mostra nomes de pastas de txt na barra):
    é rápido demais para precisar de progresso; reporta só no final.
    """
    if not base_dir.exists():
        return []
    pastas = []
    for item in sorted(base_dir.iterdir()):
        if not item.is_dir():
            continue
        qtde = 0
        try:
            for f in os.scandir(item):
                if f.is_file() and f.name.lower().endswith(ext):
                    qtde += 1
        except Exception:
            pass
        if qtde > 0:
            entrada = {"nome": item.name, "arquivos": qtde}
            try:
                entrada["caminho"] = str(base_dir.relative_to(BASE_DIR) / item.name).replace("\\", "/")
            except Exception:
                entrada["caminho"] = str(item)
            pastas.append(entrada)
    pastas.sort(key=lambda x: x["nome"])
    report(percentual=100, fase="varrendo", pasta_atual="",
           itens_processados=len(pastas), total_itens=len(pastas),
           encontrados=len(pastas))
    return pastas


def _detectar_formato_jsonl(pasta: Path) -> str:
    """Detecta o formato de uma pasta .jsonl pela 1ª linha do 1º arquivo
    (barato: 1 leitura por pasta). 'sft' = messages/conversations/chat/pergunta;
    'pretrain' = text/outro (NÃO treina como SFT)."""
    try:
        import gzip
        arquivos = sorted(pasta.glob("*.jsonl")) + sorted(pasta.glob("*.jsonl.gz"))
        if not arquivos:
            return "pretrain"
        abrir = (gzip.open(arquivos[0], "rt", encoding="utf-8")
                 if str(arquivos[0]).lower().endswith(".gz")
                 else open(arquivos[0], "r", encoding="utf-8"))
        with abrir as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    obj = json.loads(linha)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    for chave in ("messages", "conversations", "chat"):
                        if isinstance(obj.get(chave), list):
                            return "sft"
                    if "pergunta" in obj or "resposta" in obj:
                        return "sft"
                return "pretrain"
    except Exception:
        return "pretrain"
    return "pretrain"


def _scan_jsonl(report):
    """Pastas com .jsonl: dados/gerados/jsonl (explodidos) + dados/processed/jsonl
    (validados/promovidos — que é onde ficam os datasets prontos). Marca o
    formato (sft/pretrain) de cada pasta lendo a 1ª linha do 1º arquivo —
    assim o usuário não marca pasta pretrain por engano no treino SFT.
    Se o mesmo nome existir nos dois, vale o de processed (já validado)."""
    mapa = {}
    for base in (BASE_DIR / "dados" / "gerados" / "jsonl",
                 BASE_DIR / "dados" / "processed" / "jsonl"):
        for p in _scan_estrutura(base, ".jsonl", report):
            p["formato"] = _detectar_formato_jsonl(base / p["nome"])
            mapa[p["nome"]] = p
    return sorted(mapa.values(), key=lambda x: x["nome"])


def _scan_parquet(report):
    """Pastas com .parquet em dados/processed — scan RASO (nível 1).
    Os parquet ficam direto nas pastas (ex.: limpo_*/rigel_*.parquet), então
    não precisa varrer os milhões de .txt — é instantâneo e não martela o SSD."""
    return _scan_raso(PROCESSED_DIR, ".parquet", report)


_ESCANEADORES = {
    "txt": escaneador_txt,
    "jsonl": escaneador_jsonl,
    "parquet": escaneador_parquet,
}

_SCANS = {
    "txt": _scan_estrutura_txt,
    "jsonl": _scan_jsonl,
    "parquet": _scan_parquet,
}


def _escaneador_por_tipo(tipo: str):
    return _ESCANEADORES.get((tipo or "txt").lower(), escaneador_txt)


def _scan_por_tipo(tipo: str):
    return _SCANS.get((tipo or "txt").lower(), _scan_estrutura_txt)


def _pastas_do_cache(esc) -> list:
    cache = esc.carregar_cache()
    return cache.get("resultado") if cache else []


def _info_hardware() -> dict:
    """Hardware local + limites (regra 70%) + uso atual + memória do treino.
    (para exibir na página de treinamento e dar a régua de limites)"""
    try:
        import psutil
        import shutil
        from dashboard.services.recursos import (
            carregar_limites, margem_nucleos, nucleos_recomendados)
    except Exception:
        return {}
    try:
        lim = carregar_limites()
    except Exception:
        lim = {}
    hw = {}
    try:
        hw = json.loads((BASE_DIR / "config_recursos.json").read_text(encoding="utf-8")).get("hardware", {})
    except Exception:
        pass
    disco_livre = None
    try:
        disco_livre = round(shutil.disk_usage(str(BASE_DIR)).free / 1e9, 1)
    except Exception:
        pass
    # Processo de treino ativo: PID + memória real (RSS)
    treino_pid, treino_mem = None, None
    for pid in _processos_treino_ativos():
        try:
            pr = psutil.Process(pid)
            treino_pid = pid
            treino_mem = round(pr.memory_info().rss / 1e6, 1)
            break
        except Exception:
            continue
    # Tamanho dos dados parquet (entrada — o que vai p/ memória em streaming)
    tam_parquet_mb = 0.0
    for pa in _pastas_do_cache(escaneador_parquet):
        d = PROCESSED_DIR / pa["nome"]
        try:
            for f in d.glob("*.parquet"):
                tam_parquet_mb += f.stat().st_size / 1e6
        except Exception:
            pass
    ram = psutil.virtual_memory()
    return {
        "hardware": {
            "cpu_logicos": psutil.cpu_count(logical=True),
            "cpu_fisicos": psutil.cpu_count(logical=False),
            "ram_total_gb": round(ram.total / 1e9, 1),
            "gpu": bool(hw.get("gpu")),
            "gpu_nome": hw.get("gpu_nome") or "",
            "disco_tipo": hw.get("disco_tipo") or "",
            "disco_livre_gb": disco_livre,
        },
        "limites": {
            k: lim.get(k) for k in ("CPU_MAX_USO_PCT", "MEM_MIN_LIVRE_PCT",
                                    "MEM_MIN_LIVRE_MB", "DISCO_MIN_LIVRE_PCT",
                                    "DISCO_MIN_LIVRE_MB", "SCAN_MAX_ARQUIVOS",
                                    "NUCLEOS_USO", "WORKERS_TREINO", "BATCH_TREINO")
        },
        "parametros": {
            "nucleos_total": psutil.cpu_count(logical=True),
            "nucleos_usar": nucleos_recomendados(psutil.cpu_count(logical=True)),
            "margem": margem_nucleos(psutil.cpu_count(logical=True)),
            **{k: v for k, v in _parametros_treino().items()},
        },
        "uso": {
            "cpu_atual_pct": psutil.cpu_percent(interval=None),
            "ram_usada_pct": ram.percent,
            "ram_livre_pct": round(100 - ram.percent, 1),
            "treino_pid": treino_pid,
            "treino_memoria_mb": treino_mem,
            "dados_parquet_mb": round(tam_parquet_mb, 1),
        },
    }


def listar_pastas_disponiveis(forcar=False):
    """Lista pastas com cache persistente em disco. Se forcar=True, ignora cache
    e dispara escaneamento em background (frontend mostra barra de %).
    """
    cache = escaneador_txt.carregar_cache()
    if not forcar and cache and cache.get("resultado"):
        pastas = cache["resultado"]
        _train_cache["pastas_cache"] = pastas
        _train_cache["pastas_time"] = datetime.now().timestamp()
        return pastas
    if not forcar and _train_cache["pastas_cache"] and (datetime.now().timestamp() - _train_cache["pastas_time"] <= 60):
        return _train_cache["pastas_cache"]
    if forcar:
        # Background: retorna o que tiver (ou cache antigo) e dispara o scan
        escaneador_txt.iniciar(_scan_estrutura_txt, descricao="Pastas TXT")
        return cache.get("resultado") if cache else []
    if not PROCESSED_DIR.exists():
        return []
    # NUNCA escanear de forma síncrona no request (bloqueava o servidor e
    # martelava o SSD). Sem cache: dispara em BACKGROUND — o front já faz
    # polling do /reescanear/status e mostra a barra de progresso.
    if escaneador_txt.status().get("rodando"):
        return cache.get("resultado") if cache else []
    escaneador_txt.iniciar(_scan_estrutura_txt, descricao="Pastas TXT")
    return cache.get("resultado") if cache else []


def iniciar_escaneamento_txt() -> dict:
    return escaneador_txt.iniciar(_scan_estrutura_txt, descricao="Pastas TXT")


def status_escaneamento_txt() -> dict:
    return escaneador_txt.status()


class TreinoRequest(BaseModel):
    pastas: list[str] | None = None
    max_arquivos: int = 20000
    resume: bool = False
    epochs: int = 20
    tipo: str = "txt"   # txt | jsonl | parquet


class LimitesRequest(BaseModel):
    cpu_max_pct: float | None = None        # 1-70 (teto 70, só baixa)
    mem_min_livre_pct: float | None = None  # 1-70 (% de RAM livre mínima)
    nucleos: int | None = None              # núcleos/threads a usar (None = auto com margem)
    workers: int | None = None              # workers do DataLoader (memória)
    batch: int | None = None                # batch size (memória)


def _parametros_treino() -> dict:
    """Parâmetros de recursos do treino lidos do config_recursos.json:
    threads (núcleos a usar, com margem), workers e batch (controle de memória)."""
    try:
        from dashboard.services.recursos import carregar_limites, nucleos_recomendados
        lim = carregar_limites()
    except Exception:
        lim = {}
    total = os.cpu_count() or 1
    nucleos = lim.get("NUCLEOS_USO")
    try:
        nucleos = int(nucleos) if nucleos else nucleos_recomendados(total)
    except Exception:
        nucleos = nucleos_recomendados(total)
    threads = max(1, min(total, int(nucleos)))
    workers = max(1, min(4, int(lim.get("WORKERS_TREINO") or 2)))
    batch = max(1, min(32, int(lim.get("BATCH_TREINO") or 8)))
    return {"threads": threads, "workers": workers, "batch": batch}


def _stream_process_to_log(cmd, cwd=None, log_path: Path = TREINO_LOG_PATH, env=None):
    """Executa o comando e escreve stdout/stderr em tempo real no arquivo de log."""
    global _train_process
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8", errors="ignore") as f:
        f.write(f"[{datetime.now().isoformat()}] >>> CMD: {' '.join(cmd)}\n")
        try:
            proc = Popen(cmd, cwd=str(cwd) if cwd else None, stdout=PIPE, stderr=STDOUT,
                         text=True, encoding="utf-8", errors="replace", env=env)
            _train_process["proc"] = proc
            _train_process["pid"] = proc.pid
            _train_process["started_at"] = datetime.now().isoformat()
            f.write(f"[{datetime.now().isoformat()}] PID: {proc.pid}\n")
            f.flush()
            if proc.stdout:
                for linha in proc.stdout:
                    f.write(linha)
                    f.flush()
            proc.wait()
            f.write(f"[{datetime.now().isoformat()}] <<< Processo finalizado com código {proc.returncode}\n")
            f.flush()
        except Exception as e:
            f.write(f"[{datetime.now().isoformat()}] ERRO ao executar comando: {e}\n")
            f.flush()
        finally:
            _train_process["proc"] = None
            _train_process["pid"] = None


def carregar_metricas():
    if METRICAS_PATH.exists():
        try:
            data = json.loads(METRICAS_PATH.read_text(encoding="utf-8"))
            return data.get("historico", [])
        except Exception:
            return []
    return []


def carregar_estado():
    if ESTADO_PATH.exists():
        try:
            return json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _treino_rodando() -> bool:
    """True se existe um processo de treino (treino*.py) VIVO na máquina.

    Sem isto, a página mostra 'Em andamento' com dados de um log ANTIGO
    (ex.: época 18/19 parada há dias) — o treino não está rodando de verdade.
    """
    proc = _train_process.get("proc")
    if proc is not None and proc.poll() is None:
        return True
    try:
        import psutil
    except Exception:
        return False
    try:
        for p in psutil.process_iter(["cmdline"]):
            try:
                cmd = " ".join(p.info["cmdline"] or [])
                # Mesmo padrão do _processos_treino_ativos (inclui treinar_com_jsonl)
                if re.search(r"(?:^|[\s\\/])(?:treino|treinoparquet|treino_colab|treinar_com_jsonl)\.py", cmd):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def extrair_progresso_treino(log_texto: str) -> dict:
    """Extrai época atual, batch, loss do log de treino."""
    progresso = {"em_andamento": False, "epoch_atual": None, "total_epochs": None,
                  "batch_atual": None, "loss_atual": None, "percentual": 0}
    if not log_texto:
        return progresso

    # Procura padrões como "Epoch 5/20" ou "Batch 123/500"
    for linha in reversed(log_texto.splitlines()):
        ep = re.search(r"Epoch\s*(\d+)\s*/\s*(\d+)", linha, re.IGNORECASE)
        if ep:
            progresso["epoch_atual"] = int(ep.group(1))
            progresso["total_epochs"] = int(ep.group(2))
            progresso["em_andamento"] = True
            if progresso["total_epochs"]:
                progresso["percentual"] = round(progresso["epoch_atual"] / progresso["total_epochs"] * 100, 1)
        bt = re.search(r"Batch\s*(\d+)\s*/\s*(\d+)", linha, re.IGNORECASE)
        if bt:
            progresso["batch_atual"] = int(bt.group(1))
        loss = re.search(r"(?:loss|loss:)\s*([\d.]+)", linha, re.IGNORECASE)
        if loss and not progresso.get("loss_atual"):
            progresso["loss_atual"] = float(loss.group(1))

    # Verifica se o processo ainda está rodando (últimas linhas têm timestamps recentes)
    # Detecta mensagens de finalização de treino no log (português/inglês)
    termino = re.search(r"(TREINO CONCLU|TREINO COMPLET|TRAIN (FINISHED|COMPLETED)|TREINO CONCLU\w+|TREINO COMPLETO|TREINO CONCLUIDO)", log_texto, re.IGNORECASE)
    if termino:
        progresso["em_andamento"] = False
        progresso["percentual"] = 100
        # tenta preencher epoch_atual com total_epochs se encontrado antes
        if progresso.get("total_epochs") and not progresso.get("epoch_atual"):
            progresso["epoch_atual"] = progresso["total_epochs"]
    else:
        if progresso["em_andamento"]:
            # Só mostra "Em andamento" se houver processo de treino VIVO.
            # Log antigo com "Epoch X/Y" sem processo rodando = execução passada.
            if not _treino_rodando():
                progresso["em_andamento"] = False
                progresso["parado"] = True
            linhas_recentes = [l for l in log_texto.splitlines() if l.strip()][-5:]
            if linhas_recentes:
                progresso["ultimas_linhas"] = linhas_recentes[-3:]
    return progresso


@router.get("/status")
async def train_status():
    """Status com dados do cache (rápido). Use /recontar para atualizar."""
    global _train_cache
    agora = datetime.now().timestamp()

    # Retorna cache se disponível e com menos de 10s
    if _train_cache["status"] and (agora - _train_cache["time"] <= 10):
        return _train_cache["status"]

    pastas_txt = listar_pastas_disponiveis(forcar=False)
    pastas_jsonl = _pastas_do_cache(escaneador_jsonl)
    pastas_parquet = _pastas_do_cache(escaneador_parquet)
    metricas = carregar_metricas()
    estado = carregar_estado()
    log_texto = ler_ultimas_linhas(TREINO_LOG_PATH, 100)
    progresso = extrair_progresso_treino(log_texto)

    # Estado real do treino: prioriza modelo/estado_treino.json; se não
    # existir, deriva de logs/metricas.json (histórico real de épocas/loss).
    ultima_epoch = estado.get("epoch", 0) or 0
    melhor_loss = estado.get("best_val_loss")
    melhor_loss_epoch = estado.get("melhor_epoch")
    if metricas:
        if melhor_loss is None:
            melhor = min(metricas, key=lambda h: h.get("val_loss", float("inf")))
            if isinstance(melhor.get("val_loss"), (int, float)):
                melhor_loss = melhor["val_loss"]
                melhor_loss_epoch = melhor.get("epoch")
        if not ultima_epoch:
            ultima_epoch = max((h.get("epoch", 0) for h in metricas), default=0)

    result = {
        "pastas_txt": pastas_txt,
        "total_arquivos_txt": sum(p["arquivos"] for p in pastas_txt),
        "total_pastas_txt": len(pastas_txt),
        "pastas_jsonl": pastas_jsonl,
        "total_arquivos_jsonl": sum(p["arquivos"] for p in pastas_jsonl),
        "total_pastas_jsonl": len(pastas_jsonl),
        "pastas_parquet": pastas_parquet,
        "total_arquivos_parquet": sum(p["arquivos"] for p in pastas_parquet),
        "total_pastas_parquet": len(pastas_parquet),
        "pastas_disponiveis": pastas_txt,   # compat
        "modelo_existe": (MODEL_DIR / "modelo_melhor.pt").exists() or (MODEL_DIR / "modelo.pt").exists(),
        "checkpoint_existe": (MODEL_DIR / "checkpoint.pt").exists(),
        "ultima_epoch": ultima_epoch,
        "melhor_loss": melhor_loss,
        "melhor_loss_epoch": melhor_loss_epoch,
        "historico_metricas": metricas[-15:],
        "progresso": progresso,
        "scan_txt": escaneador_txt.status(),
        "scan_jsonl": escaneador_jsonl.status(),
        "scan_parquet": escaneador_parquet.status(),
        "recursos": _info_hardware(),
        "cache": {"valido": True, "gerado_em": datetime.fromtimestamp(_train_cache["time"]).isoformat() if _train_cache["time"] else None},
        "timestamp": datetime.now().isoformat()
    }

    _train_cache["status"] = result
    _train_cache["time"] = agora
    return result


@router.post("/recontar")
async def recontar_pastas():
    """Recontagem forçada em BACKGROUND (não bloqueia). Retorna imediatamente
    com o cache atual + status; o frontend acompanha a barra de %."""
    escaneador_txt.iniciar(_scan_estrutura_txt, descricao="Pastas TXT")
    pastas = escaneador_txt.carregar_cache()
    pastas = pastas.get("resultado") if pastas else []
    total_arqs = sum(p["arquivos"] for p in pastas)
    return {
        "status": "iniciado",
        "pastas_disponiveis": pastas,
        "total_arquivos": total_arqs,
        "total_pastas": len(pastas),
        "scan": escaneador_txt.status(),
        "mensagem": "Recontagem iniciada em segundo plano (veja a barra de progresso).",
        "timestamp": datetime.now().isoformat()
    }


@router.post("/reescanear")
async def reescanear(tipo: str = "txt"):
    """Dispara (ou relança) o escaneamento de pastas em segundo plano.
    tipo: txt | jsonl | parquet"""
    return _escaneador_por_tipo(tipo).iniciar(
        _scan_por_tipo(tipo), descricao=f"Pastas {tipo.upper()}")


@router.get("/reescanear/status")
async def reescanear_status(tipo: str = "txt"):
    """Progresso do escaneamento (barra de %). tipo: txt | jsonl | parquet."""
    return _escaneador_por_tipo(tipo).status()


@router.post("/start")
async def start_training(
    req: TreinoRequest,
    background_tasks: BackgroundTasks,
):
    tipo = (req.tipo or "txt").strip().lower()
    pastas = req.pastas or []
    prm = _parametros_treino()

    # SEMÁFORO GLOBAL: SÓ UM treino (ou conversão) por vez, em QUALQUER página.
    # Detecta processos vivos (sobrevive a --reload e pega órfãos).
    try:
        from dashboard.services.treino_global import disponivel as _tg_disponivel
        _ok, _ocupante = _tg_disponivel()
    except Exception:
        _ok, _ocupante = True, None
    if not _ok:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "message": (f"❌ {_ocupante['rotulo']} em andamento (PID {_ocupante['pid']}). "
                        "Só UM treino por vez — termine ou pare antes.")})

    # GUARDIÃO DE MEMÓRIA: não inicia treino se a RAM livre já estiver abaixo
    # do mínimo configurado (ex.: 50% usada → sobra mín 50%). Iniciar agora só
    # pioraria — travaria a máquina em vez de treinar.
    try:
        from dashboard.services.recursos import carregar_limites as _cl
        import psutil as _ps
        _min = float(_cl().get("MEM_MIN_LIVRE_PCT") or 50.0)
        _sobra = 100 - _ps.virtual_memory().percent
    except Exception:
        _sobra, _min = 999.0, 50.0
    if _sobra < _min:
        return JSONResponse(status_code=409, content={
            "ok": False,
            "message": (f"❌ Memória livre {_sobra:.0f}% < mínima {_min:.0f}% — "
                        "não vou iniciar treino (travaria a máquina). Feche "
                        "programas ou reduza workers/batch nas configurações.")})

    # Limita núcleos/threads por env para QUALQUER treinador (txt não tem --threads)
    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(prm["threads"])
    env["MKL_NUM_THREADS"] = str(prm["threads"])

    if tipo == "jsonl":
        # Treinador SFT JSONL (treinar_com_jsonl.py) — CPU ou GPU.
        # --dados aceita VÁRIAS pastas separadas por vírgula (o treinador
        # resolve cada uma; pastas inexistentes são ignoradas com aviso).
        mapa = {p["nome"]: p.get("caminho", p["nome"]) for p in _pastas_do_cache(escaneador_jsonl)}
        alvos = list(dict.fromkeys(mapa.get(n, n) for n in pastas))  # sem duplicatas
        cmd = ["python", "treinar_com_jsonl.py", "--no-interactive",
               "--max-arquivos", str(req.max_arquivos),
               "--threads", str(prm["threads"]),
               "--num-workers", str(prm["workers"]),
               "--batch-size", str(prm["batch"])]
        if alvos:
            cmd += ["--dados", ",".join(alvos)]
        if req.resume:
            cmd += ["--resume"]
    elif tipo == "parquet":
        # Treinador PARQUET (treinoparquet.py) — resolve as pastas limpo_*
        # dentro do --dados (base), então usamos dados/processed.
        cmd = ["python", "treinoparquet.py", "--no-interactive",
               "--threads", str(prm["threads"]),
               "--num-workers", str(prm["workers"]),
               "--batch-size", str(prm["batch"])]
        cmd += ["--dados", str(PROCESSED_DIR.relative_to(BASE_DIR))]
        if req.resume:
            cmd += ["--resume"]
    else:
        # Treinador TXT (treino.py) — tem --num-workers/--batch-size; threads
        # via env (OMP_NUM_THREADS), pois o treino.py não tem --threads.
        mapa = {p["nome"]: p.get("caminho", p["nome"]) for p in listar_pastas_disponiveis(forcar=False)}
        alvos = [mapa.get(n, n) for n in pastas]
        cmd = ["python", "treino.py", "--max-arquivos", str(req.max_arquivos),
               "--num-workers", str(prm["workers"]),
               "--batch-size", str(prm["batch"])]
        if alvos:
            cmd += ["--dados", ",".join(alvos)]
        if req.resume:
            cmd += ["--resume"]

    # 💾 BACKUP DE SEGURANÇA ANTES DO TREINO: modelo.pt/modelo_melhor.pt nunca
    # podem ser corrompidos por um treino ruim. O backup é deduplicado
    # (não copia se idêntico) e a pasta tem teto de 1 GB.
    try:
        import modelo_backup
        _bk = modelo_backup.criar_backup(motivo="pre_treino")
        _bk_msg = f" | backup: {_bk.get('novos', 0)} arquivo(s)" if _bk.get("ok") else ""
    except Exception:
        _bk_msg = ""

    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "dashboard.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] Iniciando treino {tipo}: {' '.join(cmd)}\n")

    # Registra no semáforo global (exibição + histórico)
    try:
        from dashboard.services.treino_global import registrar as _tg_registrar
        _tg_registrar(f"treino_{tipo}", None, ", ".join(pastas)[:120])
    except Exception:
        pass

    # Executa o treino em background e streama a saída para o log de treino
    background_tasks.add_task(_stream_process_to_log, cmd, BASE_DIR, TREINO_LOG_PATH, env)
    return {"status": "started",
            "message": f"Treinamento {tipo.upper()} iniciado: {len(alvos)} pasta(s) · máx {req.max_arquivos} arqs | threads {prm['threads']} | workers {prm['workers']} | batch {prm['batch']}{_bk_msg}",
            "timestamp": datetime.now().isoformat()}


def _processos_treino_ativos() -> list:
    """PIDs de QUALQUER processo de treino vivo (treino.py, treinoparquet.py,
    treinar_com_jsonl.py). Serve para matar também processos ÓRFÃOS — treinos
    iniciados antes de um --reload do uvicorn não ficam em _train_process."""
    pids = []
    try:
        import psutil
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = " ".join(p.info["cmdline"] or [])
                if re.search(r"(?:^|[\s\\/])(?:treino|treinoparquet|treino_colab|treinar_com_jsonl)\.py", cmd):
                    pids.append(p.info["pid"])
            except Exception:
                continue
    except Exception:
        pass
    return pids


@router.post("/stop")
async def stop_training():
    global _train_process
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    # 1. Cria sinal de parada (para o treino.py verificar se implementado)
    stop_file = BASE_DIR / "modelo" / "STOP_TREINO.signal"
    try:
        stop_file.write_text(datetime.now().isoformat())
    except Exception:
        pass

    morto = False
    mortos = []

    # 2. Mata o processo rastreado por este servidor
    proc = _train_process.get("proc")
    pid = _train_process.get("pid")
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            import time as _t
            _t.sleep(1)
            if proc.poll() is None:
                proc.kill()  # Força kill se não morreu
            morto = True
            mortos.append(pid)
        except Exception:
            pass

    # 3. Mata QUALQUER processo de treino vivo (inclusive órfãos de antes do reload)
    import psutil
    import time as _t
    for p in _processos_treino_ativos():
        try:
            pr = psutil.Process(p)
            if pr.pid != os.getpid():
                pr.terminate()
                _t.sleep(1)
                try:
                    if pr.is_running():
                        pr.kill()  # Força kill no Windows se não morreu
                except psutil.NoSuchProcess:
                    pass  # já morreu com o terminate
                mortos.append(p)
                morto = True
        except psutil.NoSuchProcess:
            continue
        except Exception:
            pass

    _train_process["proc"] = None
    _train_process["pid"] = None

    with open(log_dir / "dashboard.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().isoformat()}] STOP: processos mortos={mortos}\n")

    return {
        "status": "stopping",
        "processo_morto": morto,
        "pids": mortos,
        "message": ("Treino parado (processos: " + str(mortos) + ")" if morto
                    else "Nenhum processo de treino encontrado"),
    }


@router.post("/logs/limpar")
async def limpar_logs_treino():
    """Apaga o conteúdo do log de treino (logs/treino.log)."""
    try:
        if TREINO_LOG_PATH.exists():
            TREINO_LOG_PATH.write_text("", encoding="utf-8")
        return {"ok": True, "mensagem": "Log de treino limpo."}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@router.post("/limites")
async def salvar_limites(req: LimitesRequest):
    """Régua dos limites do guardião. REGRA 70%: nunca sobe acima de 70 —
    só pode baixar (ex.: 20%). Grava em config_recursos.json."""
    cfg_path = BASE_DIR / "config_recursos.json"
    try:
        dados = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        dados = {}
    lim = dados.setdefault("limites", {})
    msgs = []
    if req.cpu_max_pct is not None:
        v = max(1.0, min(70.0, float(req.cpu_max_pct)))
        lim["CPU_MAX_USO_PCT"] = v
        msgs.append(f"CPU máx {v:g}%")
    if req.mem_min_livre_pct is not None:
        v = max(1.0, min(70.0, float(req.mem_min_livre_pct)))
        lim["MEM_MIN_LIVRE_PCT"] = v
        msgs.append(f"RAM livre mín {v:g}%")
    if req.nucleos is not None:
        if int(req.nucleos) <= 0:
            # 0 = Auto: limpa o valor explícito e volta à regra da margem
            lim["NUCLEOS_USO"] = None
            msgs.append("Núcleos Auto (margem)")
        else:
            v = max(1, min(int(os.cpu_count() or 36), int(req.nucleos)))
            lim["NUCLEOS_USO"] = v
            msgs.append(f"Núcleos {v}")
    if req.workers is not None:
        v = max(1, min(4, int(req.workers)))
        lim["WORKERS_TREINO"] = v
        msgs.append(f"Workers {v}")
    if req.batch is not None:
        v = max(1, min(32, int(req.batch)))
        lim["BATCH_TREINO"] = v
        msgs.append(f"Batch {v}")
    if not msgs:
        return {"ok": False, "erro": "Informe cpu_max_pct, mem_min_livre_pct, nucleos, workers e/ou batch."}
    try:
        cfg_path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return {"ok": False, "erro": f"Falha ao salvar: {e}"}
    # Invalida o cache do /status (10s) para o frontend ver os novos limites já
    _train_cache["status"] = None
    _train_cache["time"] = 0
    return {"ok": True, "mensagem": "Limites salvos: " + ", ".join(msgs)
            + " (valem p/ novos scans; reinicie o dashboard p/ aplicar nos scans ativos)."}


@router.get("/progresso")
async def progresso_treino():
    """Apenas o progresso atual (para polling frequente)."""
    log_texto = ler_ultimas_linhas(TREINO_LOG_PATH, 80)
    progresso = extrair_progresso_treino(log_texto)
    return {"progresso": progresso, "timestamp": datetime.now().isoformat()}


@router.get("/logs")
async def treino_logs():
    """Últimas linhas do log de treino."""
    return {"conteudo": ler_ultimas_linhas(TREINO_LOG_PATH, 60)}
