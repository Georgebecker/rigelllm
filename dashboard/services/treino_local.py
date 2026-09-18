#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
treino_local.py - Serviço de treino local (CPU/GPU) via subprocesso.
Versão: 1.0.0 | Data: 02/08/2026

- Roda `treinar_com_jsonl.py` em um SUBPROCESSO (sobrevive ao --reload do uvicorn
  e isola o treino do processo do dashboard).
- Captura as mensagens de treino em tempo real (loss, LR, feedback, ETA, resumo).
- Registra em `modelo/jsonlogs/<dataset>.json` quantas vezes cada arquivo explodido
  foi treinado (a pasta modelo viaja pro Google Drive/Colab, mantendo o registro).
- Bandeiras: 0 = nenhuma | 1 = branca | 2 = amarela | 3+ = vermelha.
  A marcação só acontece quando o treino termina COM SUCESSO (código 0).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from dashboard.services.estrutura_cache import (
    escaneador_jsonl, walk_com_limites, LimiteEstourado, memoria_ok,
    MAX_NOMES_CACHE, SCAN_MAX_ARQUIVOS,
)

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))

# Datasets podem estar em gerados/jsonl (recém-explodidos) OU em
# processed/jsonl (já validados/promovidos) OU em processed/scrap
# (extraídos da WWW e processados) — o treino e as bandeiras funcionam
# em todos os lugares.
PASTA_JSONL = PROJETO_ROOT / "dados" / "gerados" / "jsonl"
PASTA_PROCESSED = PROJETO_ROOT / "dados" / "processed"
PASTA_PROCESSED_JSONL = PASTA_PROCESSED / "jsonl"
PASTA_PROCESSED_SCRAP = PASTA_PROCESSED / "scrap"
PASTA_MODELO = PROJETO_ROOT / "modelo"
PASTA_JSONLOGS = PASTA_MODELO / "jsonlogs"

# Bases consideradas no treino: (pasta, rótulo local)
_BASES_TREINO = [
    (PASTA_PROCESSED_JSONL, "processed"),
    (PASTA_PROCESSED_SCRAP, "processed"),
    (PASTA_JSONL, "gerados"),
]

# Marcador de pausa (criado pelo botão ⏸️ Pausar do dashboard) e config do
# último lote (para o botão ▶️ Retomar reiniciar com --resume após pausa).
PAUSA_MARCADOR = PROJETO_ROOT / "PAUSA_SEGURA.txt"
BATCH_CONFIG_PATH = PASTA_MODELO / "batch_config.json"

MAX_MENSAGENS = 600  # buffer de mensagens mantidas em memória
MAX_ERROS_STDERR = 50

# Estado global (thread-safe)
_estado: dict = {
    "rodando": False,
    "pid": None,
    "dataset": None,
    "arquivo": None,
    "dispositivo": "cpu",        # cpu | gpu
    "etapa": "idle",             # idle | treinando | concluido | erro
    "mensagem": "",
    "inicio": None,
    "fim": None,
    "erro": None,
    "mensagens": [],
    "tipo": "single",            # single | batch
    "batch": None,                # info da fila (pasta/modo/limite) quando batch
}
_lock = threading.Lock()
_processo: subprocess.Popen | None = None
_leitor: threading.Thread | None = None
_drenador: threading.Thread | None = None
_parada_solicitada = False


def _atualizar_estado(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)


def get_estado() -> dict:
    with _lock:
        est = dict(_estado)
        est["mensagens"] = list(est["mensagens"])
    # Barra de progresso em arquivo — escrita pelo PRÓPRIO treinador
    # (sobrevive a --reload/restarts do dashboard).
    try:
        _p = PASTA_JSONLOGS / "progresso.json"
        if _p.exists():
            est["progresso"] = json.loads(_p.read_text(encoding="utf-8"))
    except Exception:
        pass
    # Estado da FILA (lote) — modelo/estado_fila.json, escrito pelo treinador.
    try:
        _fila = PASTA_MODELO / "estado_fila.json"
        if _fila.exists():
            est["fila"] = json.loads(_fila.read_text(encoding="utf-8"))
    except Exception:
        pass
    return est


# ============================================================================
# LOGS DE TREINO (bandeiras) — modelo/jsonlogs/<dataset>.json
# ============================================================================

def _caminho_log(dataset: str) -> Path:
    os.makedirs(PASTA_JSONLOGS, exist_ok=True)
    nome = dataset.replace("/", "_").replace("\\", "_") or "dataset"
    return PASTA_JSONLOGS / f"{nome}.json"


def carregar_log(dataset: str) -> dict:
    caminho = _caminho_log(dataset)
    if caminho.exists():
        try:
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"dataset": dataset, "arquivos": {}}


def salvar_log(dataset: str, dados: dict) -> None:
    caminho = _caminho_log(dataset)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def _info_arquivo(dataset: str, arquivo: str) -> dict:
    log = carregar_log(dataset)
    info = log.get("arquivos", {}).get(arquivo, {})
    if isinstance(info, int):  # compatibilidade com formato antigo
        info = {"vezes": info}
    return info if isinstance(info, dict) else {"vezes": 0}


def vezes_treinado(dataset: str, arquivo: str) -> int:
    return int(_info_arquivo(dataset, arquivo).get("vezes", 0))


def flag_arquivo(dataset: str, arquivo: str) -> str:
    """nenhuma | branca | amarela | vermelha"""
    vezes = vezes_treinado(dataset, arquivo)
    if vezes == 0:
        return "nenhuma"
    if vezes == 1:
        return "branca"
    if vezes == 2:
        return "amarela"
    return "vermelha"


def _marcar_treinado(dataset: str, arquivo: str) -> int:
    """Marca o arquivo como treinado (incrementa contagem). Retorna o novo nº de vezes."""
    log = carregar_log(dataset)
    info = log.get("arquivos", {}).get(arquivo, {})
    if isinstance(info, int):
        info = {"vezes": info}
    vezes = int(info.get("vezes", 0)) + 1
    log.setdefault("arquivos", {})[arquivo] = {
        "vezes": vezes,
        "ultima": datetime.now().isoformat(),
    }
    salvar_log(dataset, log)
    return vezes


# ============================================================================
# LISTAGEM (datasets e arquivos com bandeiras)
# ============================================================================

# Extensões de dados que o treino reconhece (nada pode ficar perdido).
_EXTENSOES_TREINO = (".jsonl", ".parquet", ".txt")


def _tem_jsonl(pasta: Path) -> bool:
    """True se existe ao menos 1 .jsonl (streaming, com limites — NUNCA
    materializa a lista inteira como `list(pasta.rglob(...))`)."""
    try:
        for _c in walk_com_limites(pasta, extensoes=(".jsonl",)):
            return True
    except LimiteEstourado:
        return True  # tantos arquivos que com certeza há jsonl
    return False


def _tem_dados(pasta: Path, extensoes=_EXTENSOES_TREINO) -> bool:
    """True se existe ao menos 1 arquivo de dados (jsonl/parquet/txt)."""
    try:
        for _c in walk_com_limites(pasta, extensoes=extensoes):
            return True
    except LimiteEstourado:
        return True
    return False


def _arquivos_jsonl(pasta: Path) -> list[str]:
    """Lista caminhos .jsonl de um dataset com limites (nunca materializa
    tudo em memória; respeita SCAN_MAX_ARQUIVOS)."""
    caminhos: list[str] = []
    try:
        for c in walk_com_limites(pasta, extensoes=(".jsonl",)):
            caminhos.append(c)
            if len(caminhos) >= SCAN_MAX_ARQUIVOS:
                break
    except LimiteEstourado:
        pass
    return caminhos


def _arquivos_dados(pasta: Path, extensoes=_EXTENSOES_TREINO) -> list[str]:
    """Lista caminhos de dados (jsonl/parquet/txt) de um dataset com limites.
    Garante que NENHUM material processado fica invisível ao treino."""
    caminhos: list[str] = []
    try:
        for c in walk_com_limites(pasta, extensoes=extensoes):
            caminhos.append(c)
            if len(caminhos) >= SCAN_MAX_ARQUIVOS:
                break
    except LimiteEstourado:
        pass
    return caminhos


def _pastas_de_datasets() -> list[tuple[str, Path, Path]]:
    """Retorna [(nome_dataset, pasta, base)] escaneando as bases de treino
    (processed/jsonl, processed/scrap, gerados/jsonl). Aceita jsonl, parquet
    e txt — NENHUM material processado fica perdido. Se o mesmo nome existir
    em várias, vale a primeira (processed tem preferência)."""
    locais: list[tuple[str, Path, Path]] = []
    for base, _local in _BASES_TREINO:  # processed primeiro (preferência)
        if not base.exists():
            continue
        for nome in sorted(os.listdir(base)):
            pasta = base / nome
            if not pasta.is_dir():
                continue
            if not _tem_dados(pasta):
                continue
            if any(n == nome for n, _, _ in locais):
                continue
            locais.append((nome, pasta, base))
    return locais


# ============================================================================
# ESCANEAMENTO COM CACHE + PROGRESSO (tela abre instantânea; barra de %)
# ============================================================================

def _localizar_dataset_rapido(nome: str) -> tuple[Path | None, Path | None]:
    """Localiza a pasta de um dataset olhando as bases de treino (O(1), sem
    rglob). Retorna (pasta, base).
    """
    for base, _local in _BASES_TREINO:  # processed primeiro (preferência)
        cand = base / nome
        if cand.is_dir():
            return cand, base
    return None, None


def _scan_estrutura_jsonl(report) -> list[dict]:
    """Varre gerados/jsonl e processed/jsonl reportando progresso.
    Retorna lista de datasets com nomes de arquivos (para bandeiras).
    Com o guardião de limites: streaming, sem rglob materializado, cap de
    nomes no cache (MAX_NOMES_CACHE) e aborta se a memória ficar baixa.
    """
    todos: list[dict] = []
    bases = _BASES_TREINO
    for base, local in bases:
        if not base.exists():
            continue
        itens = sorted(base.iterdir())
        total = len(itens)
        for i, item in enumerate(itens):
            if not item.is_dir():
                continue
            ok, motivo = memoria_ok()
            if not ok:
                report(fase="interrompido", percentual=100, erro=motivo)
                raise LimiteEstourado(motivo)
            nomes: list[str] = []
            contador = 0
            truncado = False

            def _on_dir(raiz_atual, dirs_vistos):
                report(pasta_atual=item.name, itens_processados=i + 1,
                       total_itens=total, encontrados=len(todos))

            try:
                for caminho in walk_com_limites(item, extensoes=_EXTENSOES_TREINO,
                                                on_dir=_on_dir):
                    contador += 1
                    if len(nomes) < MAX_NOMES_CACHE:
                        nomes.append(os.path.basename(caminho))
                    else:
                        truncado = True
            except LimiteEstourado as e:
                report(fase="interrompido", percentual=100, erro=str(e))
                raise
            if contador > 0:
                # respeita preferência: mesmo nome em processed sobrescreve gerados
                if local == "processed":
                    todos = [t for t in todos if t["nome"] != item.name]
                todos.append({
                    "nome": item.name,
                    "local": local,
                    "arquivos": contador,
                    "arquivos_nomes": nomes,
                    "nomes_truncado": truncado,
                })
            if (i + 1) % 10 == 0 or i + 1 == total:
                report(percentual=((i + 1) / total) * 100 if total else 100,
                       fase="varrendo", pasta_atual=item.name,
                       itens_processados=i + 1, total_itens=total,
                       encontrados=len(todos))
    return todos


def iniciar_escaneamento_estrutura() -> dict:
    """Dispara o escaneamento em thread (barra de progresso no frontend)."""
    return escaneador_jsonl.iniciar(_scan_estrutura_jsonl,
                                    descricao="Datasets JSONL")


def status_escaneamento() -> dict:
    return escaneador_jsonl.status()


def listar_datasets(usar_cache: bool = False) -> list:
    """Lista os datasets (gerados/jsonl e processed) com bandeiras por arquivo.
    Se usar_cache=True e houver cache válido em disco, monta a partir dele
    (rápido, sem rglob) — bandeiras lidas dos jsonlogs (barato).
    """
    cache = escaneador_jsonl.carregar_cache() if usar_cache else None
    if cache and cache.get("resultado"):
        itens = []
        for item in cache["resultado"]:
            nome = item["nome"]
            pasta, _base = _localizar_dataset_rapido(nome)
            if pasta is None:
                continue
            nomes = item.get("arquivos_nomes") or []
            # 🧹 Guarda: cache pode estar DESATUALIZADO (arquivos apagados/
            # movidos depois do scan). Nunca mostrar "0 arquivos" para pastas
            # que na verdade têm arquivos — e nunca listar pasta realmente vazia.
            try:
                tem_dados = _tem_dados(pasta) if pasta.is_dir() else False
            except Exception:
                tem_dados = False
            if not tem_dados:
                continue  # pasta realmente vazia → não lista
            if not nomes:
                # Cache sem nomes (antigo/corrompido): conta de verdade, mas
                # com teto (não materializa 12M de arquivos).
                contador = 0
                try:
                    for _c in walk_com_limites(pasta, extensoes=_EXTENSOES_TREINO):
                        contador += 1
                        if contador > SCAN_MAX_ARQUIVOS:
                            break
                except Exception:
                    contador = 0
                if contador == 0:
                    continue
                cont = {"nenhuma": 0, "branca": 0, "amarela": 0, "vermelha": 0}
                itens.append({
                    "nome": nome,
                    "arquivos": contador,
                    "bandeiras": cont,
                    "log": _caminho_log(nome).exists(),
                    "local": item.get("local", "gerados"),
                    "cache_sem_nomes": True,
                })
                continue
            cont = {"nenhuma": 0, "branca": 0, "amarela": 0, "vermelha": 0}
            for nome_arq in nomes:
                cont[flag_arquivo(nome, nome_arq)] += 1
            itens.append({
                "nome": nome,
                "arquivos": len(nomes),
                "bandeiras": cont,
                "log": _caminho_log(nome).exists(),
                "local": item.get("local", "gerados"),
            })
        return itens
    # Sem cache: scan completo (lento) — normalmente o frontend dispara
    # o escaneamento em background ANTES e volta aqui com o cache pronto.
    # (com limites: nunca materializa tudo em memória)
    itens = []
    for nome, pasta, base in _pastas_de_datasets():
        arquivos = _arquivos_dados(pasta)
        cont = {"nenhuma": 0, "branca": 0, "amarela": 0, "vermelha": 0}
        for a in arquivos:
            flag = flag_arquivo(nome, Path(a).name)
            cont[flag] += 1
        local = "processed" if base in (PASTA_PROCESSED_JSONL, PASTA_PROCESSED_SCRAP) else "gerados"
        itens.append({
            "nome": nome,
            "arquivos": len(arquivos),
            "bandeiras": cont,
            "log": _caminho_log(nome).exists(),
            "local": local,
        })
    return itens


def listar_arquivos(dataset: str) -> list:
    # Localização rápida O(1) pelas duas bases — evita o rglob geral
    pasta, _base = _localizar_dataset_rapido(dataset)
    if pasta is None:
        for nome, cand, _base2 in _pastas_de_datasets():
            if nome == dataset:
                pasta = cand
                break
    if pasta is None:
        return []
    itens = []
    for a in _arquivos_jsonl(pasta):
        itens.append({
            "arquivo": Path(a).name,
            "caminho": a,
            "vezes": vezes_treinado(dataset, Path(a).name),
            "flag": flag_arquivo(dataset, Path(a).name),
        })
    return itens


def _validar_arquivo_jsonl(caminho: Path) -> tuple[bool, str]:
    """Valida um arquivo JSONL: JSON válido, formato messages, mínimo de exemplos."""
    try:
        total = 0
        com_erro = 0
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                total += 1
                try:
                    obj = json.loads(linha)
                except Exception:
                    com_erro += 1
                    continue
                if not isinstance(obj, dict):
                    com_erro += 1
                    continue
                msgs = obj.get("messages")
                if not isinstance(msgs, list) or len(msgs) < 2:
                    com_erro += 1
                    continue
                ok_msgs = all(
                    isinstance(m, dict)
                    and str(m.get("role", "")) in ("system", "user", "assistant")
                    and str(m.get("content", "")).strip()
                    for m in msgs
                )
                if not ok_msgs:
                    com_erro += 1
        if total == 0:
            return False, "arquivo vazio"
        if com_erro > 0:
            return False, f"{com_erro}/{total} linhas inválidas"
        return True, f"{total} exemplos válidos"
    except Exception as e:
        return False, f"erro ao ler: {e}"


# 🔎 ÍNDICE DE HASHES anti-overfitting (persistido): mapeia cada dataset
# promovido → hashes de amostras. Assim a detecção de conteúdo repetido é
# RÁPIDA (não relê os 437+ datasets de processed a cada promover).
_INDICE_HASHES = PROJETO_ROOT / "estado" / "indice_hashes.json"
_MAX_AMOSTRAS = 40
_MAX_ARQUIVOS_HASH = 3


def _hash_amostras(pasta: Path, max_amostras: int = _MAX_AMOSTRAS,
                   max_arquivos: int = _MAX_ARQUIVOS_HASH) -> set:
    """Hash de AMOSTRAS de exemplos de um dataset (a pergunta do 1º turno user,
    ou o campo text/pergunta/input). Usado para DETECTAR CONTEÚDO REPETIDO:
    datasets com nomes diferentes mas mesmo conteúdo (risco de overfitting)."""
    hashes: set = set()
    try:
        arqs = _arquivos_jsonl(pasta)[:max_arquivos]
        for arq in arqs:
            try:
                with open(arq, encoding="utf-8", errors="replace") as f:
                    for _i, linha in enumerate(f):
                        if len(hashes) >= max_amostras * len(arqs) or len(hashes) >= 200:
                            break
                        try:
                            obj = json.loads(linha)
                        except Exception:
                            continue
                        if not isinstance(obj, dict):
                            continue
                        msgs = obj.get("messages") or obj.get("conversations") or []
                        pergunta = ""
                        for m in msgs if isinstance(msgs, list) else []:
                            if isinstance(m, dict) and m.get("role") == "user":
                                pergunta = str(m.get("content", ""))
                                break
                        if not pergunta:
                            pergunta = str(obj.get("text") or obj.get("pergunta")
                                           or obj.get("input") or obj.get("instrucao") or "")
                        if pergunta.strip():
                            hashes.add(hashlib.md5(pergunta.strip()[:200].encode("utf-8")).hexdigest())
            except Exception:
                continue
    except Exception:
        pass
    return hashes


def _carregar_indice_hashes() -> dict:
    try:
        if _INDICE_HASHES.exists():
            dados = json.loads(_INDICE_HASHES.read_text(encoding="utf-8"))
            if isinstance(dados, dict) and isinstance(dados.get("datasets"), dict):
                return dados["datasets"]
    except Exception:
        pass
    return {}


def _salvar_indice_hashes(datasets: dict) -> None:
    try:
        _INDICE_HASHES.parent.mkdir(parents=True, exist_ok=True)
        _INDICE_HASHES.write_text(
            json.dumps({"datasets": datasets, "atualizado_em": datetime.now().isoformat()},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def indexar_hashes() -> dict:
    """(Re)constrói o índice de hashes de TODOS os datasets promovidos
    (processed/jsonl). Chamado uma vez ou quando o acervo mudar muito."""
    datasets: dict = {}
    for nome in sorted(os.listdir(PASTA_PROCESSED_JSONL)):
        pasta = PASTA_PROCESSED_JSONL / nome
        if not pasta.is_dir() or not _tem_dados(pasta):
            continue
        h = _hash_amostras(pasta)
        if h:
            datasets[nome] = sorted(h)
    _salvar_indice_hashes(datasets)
    return {"ok": True, "datasets_indexados": len(datasets), "arquivo": str(_INDICE_HASHES)}


def detectar_duplicatas(dataset: str, pasta_origem: Path) -> list:
    """Compara amostras do dataset com o ÍNDICE de hashes dos JÁ PROMOVIDOS.
    Retorna [{dataset, sobreposicao_pct, amostras_iguais}] quando o conteúdo
    é REPETIDO (mesmo material com nome diferente → risco de overfitting).
    Rápido: usa o índice persistido, não relê os arquivos de processed."""
    novos = _hash_amostras(pasta_origem)
    if not novos:
        return []
    indice = _carregar_indice_hashes()
    achados: list = []
    for outro, hashes_outro in indice.items():
        if outro == dataset:
            continue
        outros_h = set(hashes_outro)
        if not outros_h:
            continue
        inter = len(novos & outros_h)
        if inter <= 0:
            continue
        pct = inter / max(1, len(outros_h)) * 100
        if pct >= 30:  # sobreposição alta → mesmo material com outro nome
            achados.append({"dataset": outro,
                            "sobreposicao": round(pct, 1),
                            "amostras_iguais": inter})
    return achados


def promover_para_processed(dataset: str, remover_invalidos: bool = False) -> dict:
    """
    Valida os arquivos do dataset em gerados/jsonl e copia SOMENTE os válidos
    para dados/processed/jsonl/<dataset>/. Opcionalmente remove os inválidos
    da origem. As bandeiras (jsonlogs) continuam valendo.

    🔎 ANTI-OVERFITTING: antes de concluir, compara amostras com os datasets
    já promovidos e avisa se o CONTEÚDO é repetido (mesmo material com nome
    diferente) — o usuário decide se quer mesmo promover.
    """
    # Busca direto em gerados/jsonl/<dataset>: usar _pastas_de_datasets() aqui
    # daria falso 'não encontrado' quando o dataset já está em processed (ele
    # é omitido de gerados por dedup) — bug real visto na extração de livros.
    pasta_origem = PASTA_JSONL / dataset
    if not pasta_origem.is_dir() or not _tem_dados(pasta_origem):
        return {"ok": False,
                "erro": f"Dataset '{dataset}' não encontrado em gerados/jsonl."}

    destino = PASTA_PROCESSED_JSONL / dataset
    if destino.exists():
        # 🧹 Pasta VAZIA (resquício de promoção anterior que não copiou nada)
        # não deve bloquear — apaga e reprocessa.
        try:
            if not any(destino.iterdir()):
                shutil.rmtree(str(destino))
        except Exception:
            pass
    # Se o destino já tem arquivos, faz MERGE (atualiza/adiciona) em vez de
    # bloquear: ex.: livro novo extraído é somado ao acervo já promovido.
    destino.mkdir(parents=True, exist_ok=True)
    ja_no_destino = {f.name for f in destino.iterdir()} if destino.exists() else set()

    arquivos = [Path(a) for a in _arquivos_jsonl(pasta_origem)]
    validos: list[Path] = []
    invalidos: list[tuple[Path, str]] = []
    for a in arquivos:
        ok, motivo = _validar_arquivo_jsonl(a)
        if ok:
            validos.append(a)
        else:
            invalidos.append((a, motivo))

    if not validos:
        return {"ok": False, "erro": "Nenhum arquivo válido para promover.",
                "validos": 0, "invalidos": len(invalidos)}

    copiados = 0
    novos = 0
    for a in validos:
        try:
            shutil.copy2(str(a), str(destino / a.name))
            copiados += 1
            if a.name not in ja_no_destino:
                novos += 1
        except Exception as e:
            invalidos.append((a, f"erro ao copiar: {e}"))

    removidos = 0
    if remover_invalidos:
        for a, _m in invalidos:
            try:
                os.remove(a)
                removidos += 1
            except Exception:
                pass

    # 💉 CARTEIRA DE QUALIDADE: marca que o material foi promovido (validado).
    try:
        from dashboard.services.qualidade import marcar as _marcar_qualidade
        _marcar_qualidade(dataset, "promovido", validos=copiados,
                          invalidos=len(invalidos))
    except Exception:
        pass

    # 🔎 ANTI-OVERFITTING: conteúdo repetido com outro nome?
    duplicatas = detectar_duplicatas(dataset, pasta_origem)
    if duplicatas:
        nomes = ", ".join(d["dataset"] for d in duplicatas)
        try:
            from dashboard.services.qualidade import marcar as _marcar_q2
            _marcar_q2(dataset, "duplicado_de", datasets=nomes)
        except Exception:
            pass
    # Atualiza o ÍNDICE de hashes com este dataset (futuras comparações rápidas)
    try:
        indice = _carregar_indice_hashes()
        h = _hash_amostras(pasta_origem)
        if h:
            indice[dataset] = sorted(h)
            _salvar_indice_hashes(indice)
    except Exception:
        pass

    msg = (f"'{dataset}' promovido: {copiados} arquivos válidos em "
           f"dados/processed/jsonl/{dataset}/ "
           f"({novos} novos, {len(ja_no_destino)} já existiam).")
    if duplicatas:
        msg += (" ⚠️ ATENÇÃO: conteúdo repetido com "
                + ", ".join(f"'{d['dataset']}' (~{d['sobreposicao']}%)" for d in duplicatas)
                + " — treinar os dois juntos pode enviesar o modelo (overfitting).")
    return {
        "ok": True,
        "mensagem": msg,
        "validos": copiados,
        "novos": novos,
        "invalidos": len(invalidos),
        "removidos": removidos,
        "destino": str(destino),
        "duplicatas": duplicatas,
    }


# ============================================================================
# EXECUÇÃO DO TREINO (subprocesso)
# ============================================================================

def _detectar_dispositivo() -> str:
    try:
        import torch
        return "gpu" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _ler_saida(proc: subprocess.Popen) -> None:
    """Lê a saída padrão do treinador e alimenta o buffer de mensagens."""
    assert proc.stdout is not None
    for linha in proc.stdout:
        linha = linha.rstrip("\n")
        if not linha.strip():
            continue
        with _lock:
            _estado["mensagens"].append(linha)
            if len(_estado["mensagens"]) > MAX_MENSAGENS:
                _estado["mensagens"] = _estado["mensagens"][-MAX_MENSAGENS:]
            _estado["mensagem"] = linha


def _drenar_stderr(proc: subprocess.Popen) -> None:
    """Drena o stderr (evita deadlock por buffer cheio). Guarda as últimas linhas."""
    erros: list[str] = []
    assert proc.stderr is not None
    for linha in proc.stderr:
        linha = linha.rstrip("\n")
        if not linha.strip():
            continue
        erros.append(linha)
        if len(erros) > MAX_ERROS_STDERR:
            erros = erros[-MAX_ERROS_STDERR:]
    if erros:
        with _lock:
            _estado["erro_detalhe"] = "\n".join(erros[-10:])


def _monitorar_fim(proc: subprocess.Popen, dataset: str, arquivo: str) -> None:
    """Aguarda o fim do processo e reporta (marca arquivo se for treino single)."""
    global _processo, _leitor, _drenador, _parada_solicitada
    with _lock:
        tipo = _estado.get("tipo", "single")
    codigo = proc.wait()
    with _lock:
        _estado["rodando"] = False
        _estado["pid"] = None
        _processo = None
        _leitor = None
        _drenador = None
        _estado["fim"] = datetime.now().isoformat()
        parada = _parada_solicitada
        _parada_solicitada = False
        _estado["tipo"] = "single"
        _estado["batch"] = None
        if parada:
            _estado["etapa"] = "parado"
            if tipo == "batch":
                _estado["mensagem"] = ("⏹️ Fila parada pelo usuário. "
                                        "Estado salvo (retome com --resume).")
            else:
                _estado["mensagem"] = ("⏹️ Treino parado pelo usuário. "
                                        "Arquivo NÃO foi marcado.")
            _estado["mensagens"].append(_estado["mensagem"])
        elif codigo == 0:
            if tipo == "batch":
                msg = ("✅ Fila de treinamento concluída! "
                       "Modelo salvo entre arquivos.")
                _estado["etapa"] = "concluido"
                _estado["mensagem"] = msg
                _estado["mensagens"].append(msg)
            else:
                # A marcação agora é feita pelo PRÓPRIO treinador ao concluir
                # (sobrevive a --reload/restarts do dashboard). Aqui só lemos.
                vezes = vezes_treinado(dataset, arquivo)
                flag = flag_arquivo(dataset, arquivo)
                msg = (f"✅ Treino concluído! Arquivo '{arquivo}' marcado "
                       f"({vezes}x — bandeira {flag}).")
                _estado["etapa"] = "concluido"
                _estado["mensagem"] = msg
                _estado["mensagens"].append(msg)
        else:
            detalhe = _estado.get("erro_detalhe", "")
            _estado["etapa"] = "erro"
            _estado["erro"] = f"Treino terminou com código {codigo}"
            if tipo == "batch":
                _estado["mensagem"] = (f"❌ Fila terminou com erro (código {codigo}). "
                                        f"Estado salvo — retome com --resume.")
            else:
                _estado["mensagem"] = (f"❌ Treino falhou (código {codigo}). "
                                        f"Arquivo NÃO foi marcado.")
            if detalhe:
                _estado["mensagem"] += f"\n{detalhe}"
            _estado["mensagens"].append(_estado["mensagem"])


def iniciar_treino(dataset: str, arquivo: str, epochs: int | None = None,
                   max_exemplos: int | None = None,
                   pular_treinados: int = 0, forcar: bool = False) -> dict:
    """Inicia o treino do arquivo em subprocesso (CPU ou GPU conforme disponível).
    pular_treinados>0: pula se já treinado N+ vezes. forcar: ignora a regra."""
    global _processo, _leitor, _drenador
    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um treino em andamento. Pare-o primeiro."}
    # Semáforo GLOBAL (qualquer página/rota): só UM treino/conversão por vez.
    try:
        from dashboard.services.treino_global import disponivel as _tg_disponivel
        _ok, _ocupante = _tg_disponivel()
        if not _ok:
            return {"ok": False,
                    "erro": f"{_ocupante['rotulo']} em andamento (PID {_ocupante['pid']}). "
                            "Só UM treino por vez — termine ou pare antes."}
    except Exception:
        pass

    caminho_arquivo = None
    base_encontrada = None
    for _nome, _pasta, _base in _pastas_de_datasets():
        if _nome == dataset:
            base_encontrada = _base
            cand = _pasta / arquivo
            if cand.exists():
                caminho_arquivo = cand
            else:
                achado = list(_pasta.rglob(arquivo))
                if achado:
                    caminho_arquivo = achado[0]
            break
    # Princípio: treino SÓ com dados validados (processed). Gerados = provisório.
    if base_encontrada == PASTA_JSONL:
        return {"ok": False,
                "erro": f"Dataset '{dataset}' está em dados/gerados (provisório). "
                        "Promova para processed antes de treinar."}
    if caminho_arquivo is None:
        return {"ok": False, "erro": f"Arquivo '{arquivo}' não encontrado em '{dataset}'."}
    pasta = caminho_arquivo.parent

    dispositivo = _detectar_dispositivo()
    comando = [
        sys.executable, "-u", "treinar_com_jsonl.py",
        "--dados", str(pasta),
        "--arquivo", str(caminho_arquivo),
        "--no-interactive",
        "--resume",
    ]
    if epochs is not None:
        comando += ["--epochs", str(epochs)]
    if max_exemplos is not None:
        comando += ["--max-exemplos", str(max_exemplos)]
    if pular_treinados and pular_treinados > 0:
        comando += ["--pular-treinados", str(pular_treinados)]
    if forcar:
        comando += ["--force"]

    # 💾 Backup de segurança ANTES do treino (modelos nunca são corrompidos)
    try:
        import modelo_backup
        modelo_backup.criar_backup(motivo="pre_treino")
    except Exception:
        pass

    _atualizar_estado(
        rodando=True, pid=None, dataset=dataset, arquivo=arquivo,
        dispositivo=dispositivo, etapa="treinando", mensagem="Iniciando treino...",
        inicio=datetime.now().isoformat(), fim=None, erro=None, mensagens=[],
    )

    try:
        proc = subprocess.Popen(
            comando,
            cwd=str(PROJETO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        _atualizar_estado(rodando=False, etapa="erro", erro=str(e),
                          mensagem=f"❌ Falha ao iniciar treino: {e}")
        return {"ok": False, "erro": str(e)}
    try:
        from dashboard.services.treino_global import registrar as _tg_registrar
        _tg_registrar("treino_jsonl", proc.pid, arquivo)
    except Exception:
        pass

    _processo = proc
    _atualizar_estado(pid=proc.pid)
    _leitor = threading.Thread(target=_ler_saida, args=(proc,), daemon=True)
    _leitor.start()
    _drenador = threading.Thread(target=_drenar_stderr, args=(proc,), daemon=True)
    _drenador.start()
    threading.Thread(target=_monitorar_fim, args=(proc, dataset, arquivo),
                     daemon=True).start()

    return {"ok": True, "mensagem": f"Treino iniciado ({dispositivo.upper()})."}


def iniciar_batch(pasta: str, modo: str = "all", limite_horas: float | None = None,
                  resume: bool = False, pular_treinados: int = 0,
                  forcar: bool = False, epocas_por_arquivo: int = 5) -> dict:
    """Inicia uma FILA de treinamento: todos os .jsonl de uma pasta, um por vez.
    pular_treinados>0: pula arquivos já treinados N+ vezes. forcar: ignora.
    epocas_por_arquivo: épocas treinadas em cada arquivo da fila.
    O treinador (treinar_com_jsonl.py --modo-fila) salva o modelo e o estado
    (modelo/estado_fila.json) entre cada arquivo — nada se perde em queda."""
    global _processo, _leitor, _drenador
    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um treino em andamento. Pare-o primeiro."}
    # Semáforo GLOBAL (qualquer página/rota): só UM treino/conversão por vez.
    try:
        from dashboard.services.treino_global import disponivel as _tg_disponivel
        _ok, _ocupante = _tg_disponivel()
        if not _ok:
            return {"ok": False,
                    "erro": f"{_ocupante['rotulo']} em andamento (PID {_ocupante['pid']}). "
                            "Só UM treino por vez — termine ou pare antes."}
    except Exception:
        pass

    # Aliases de modo (frontend) -> modo interno do motor.
    _ALIASES_MODOS = {"arquivo": "all", "completo": "all", "tempo": "time"}
    if modo in _ALIASES_MODOS:
        modo = _ALIASES_MODOS[modo]
    if modo not in ("all", "time", "pause"):
        modo = "all"

    # Resolve a pasta: aceita nome de dataset (das bases) ou caminho direto.
    pasta_path = Path(pasta)
    if not pasta_path.is_dir():
        cand, _base = _localizar_dataset_rapido(pasta)
        if cand is None:
            return {"ok": False,
                    "erro": f"Dataset/pasta '{pasta}' não encontrado."}
        pasta_path = cand
    if not _tem_jsonl(pasta_path):
        return {"ok": False, "erro": f"Nenhum .jsonl em '{pasta_path}'."}

    # Princípio: treino SÓ com dados validados (processed). Gerados = provisório.
    if str(pasta_path).startswith(str(PASTA_JSONL)):
        return {"ok": False,
                "erro": f"'{pasta}' está em dados/gerados (provisório). "
                        "Promova para processed antes de treinar."}

    dispositivo = _detectar_dispositivo()
    comando = [
        sys.executable, "-u", "treinar_com_jsonl.py",
        "--caminho-pasta", str(pasta_path),
        "--modo-fila", modo,
        "--epocas-por-arquivo", str(max(1, epocas_por_arquivo or 5)),
        "--no-interactive",
    ]
    if modo == "time" and limite_horas and limite_horas > 0:
        comando += ["--limite-tempo", str(float(limite_horas))]
    if resume:
        comando += ["--resume"]
    if pular_treinados and pular_treinados > 0:
        comando += ["--pular-treinados", str(pular_treinados)]
    if forcar:
        comando += ["--force"]

    _atualizar_estado(
        rodando=True, pid=None, dataset=pasta_path.name, arquivo="(fila)",
        dispositivo=dispositivo, etapa="treinando",
        mensagem="Iniciando fila de treinamento...",
        inicio=datetime.now().isoformat(), fim=None, erro=None, mensagens=[],
        tipo="batch",
        batch={"pasta": str(pasta_path), "modo": modo,
               "limite_horas": limite_horas, "resume": resume,
               "pular_treinados": pular_treinados, "forcar": forcar,
               "epocas_por_arquivo": epocas_por_arquivo},
    )

    # 💾 Backup de segurança ANTES do treino (modelos nunca são corrompidos)
    try:
        import modelo_backup
        modelo_backup.criar_backup(motivo="pre_treino")
    except Exception:
        pass

    # Persiste a config do lote (para o botão ▶️ Retomar após pausa).
    try:
        PASTA_MODELO.mkdir(exist_ok=True)
        BATCH_CONFIG_PATH.write_text(json.dumps({
            "pasta": str(pasta_path), "modo": modo,
            "limite_horas": limite_horas,
            "pular_treinados": pular_treinados, "forcar": forcar,
            "epocas_por_arquivo": epocas_por_arquivo,
            "atualizado_em": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    try:
        proc = subprocess.Popen(
            comando,
            cwd=str(PROJETO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        _atualizar_estado(rodando=False, etapa="erro", erro=str(e),
                          mensagem=f"❌ Falha ao iniciar fila: {e}", tipo="single")
        return {"ok": False, "erro": str(e)}

    _processo = proc
    _atualizar_estado(pid=proc.pid)
    _leitor = threading.Thread(target=_ler_saida, args=(proc,), daemon=True)
    _leitor.start()
    _drenador = threading.Thread(target=_drenar_stderr, args=(proc,), daemon=True)
    _drenador.start()
    threading.Thread(target=_monitorar_fim, args=(proc, pasta_path.name, "(fila)"),
                     daemon=True).start()

    return {"ok": True,
            "mensagem": f"Fila iniciada ({modo.upper()}, {dispositivo.upper()}). "
                         "Modelo salvo entre arquivos; progresso em estado_fila.json."}


def pausar_fila() -> dict:
    """Solicita pausa GRACIOSA da fila: cria o marcador PAUSA_SEGURA.txt.
    A fila termina o arquivo atual, salva o modelo e para (status 'pausado')."""
    if not get_estado()["rodando"]:
        return {"ok": False, "erro": "Nenhuma fila em andamento para pausar."}
    try:
        PAUSA_MARCADOR.write_text(
            f"pausa solicitada pelo dashboard em {datetime.now().isoformat()}",
            encoding="utf-8")
        return {"ok": True,
                "mensagem": "⏸️ Pausa solicitada — a fila termina o arquivo "
                             "atual e pausa (modelo salvo)."}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def retomar_fila() -> dict:
    """Retoma a fila pausada: remove o marcador e reinicia com --resume
    (continua exatamente do arquivo onde parou)."""
    # Remove o marcador de pausa (se ainda existir).
    try:
        if PAUSA_MARCADOR.exists():
            PAUSA_MARCADOR.unlink()
    except Exception:
        pass
    # Config do último lote (persistida pelo iniciar_batch).
    cfg = {}
    try:
        if BATCH_CONFIG_PATH.exists():
            cfg = json.loads(BATCH_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    if not cfg.get("pasta"):
        return {"ok": False, "erro": "Nenhuma fila pausada para retomar."}
    return iniciar_batch(
        cfg["pasta"], modo=cfg.get("modo", "all"),
        limite_horas=cfg.get("limite_horas"),
        resume=True,
        pular_treinados=cfg.get("pular_treinados", 0),
        forcar=cfg.get("forcar", False),
        epocas_por_arquivo=cfg.get("epocas_por_arquivo", 5),
    )


def parar_treino() -> dict:
    """Encerra o treino em andamento (sem marcar o arquivo)."""
    global _processo, _parada_solicitada
    with _lock:
        proc = _processo
    if proc is None:
        return {"ok": False, "erro": "Nenhum treino em andamento."}
    _parada_solicitada = True
    try:
        if os.name == "nt":
            # taskkill /T derruba também os FILHOS — no Windows matar o pai
            # não mata o processo-filho que faz o treino pesado.
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           check=False, capture_output=True)
        else:
            proc.terminate()
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    return {"ok": True, "mensagem": "Parada solicitada! Encerrando treino... "
                                    "(arquivo NÃO será marcado)."}
