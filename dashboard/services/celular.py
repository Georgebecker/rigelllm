#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
celular.py — Exportação/Importação de matéria-prima (celular ↔ PC).

Fluxo (usuário):
  1. O celular roda a MESMA estrutura RigelSLM (instalada via deploy).
     Scrap, chat, RSS e geradores produzem conteúdo em dados/.
  2. No dashboard do CELULAR: "Exportar dados" gera rigel_export_<ts>.zip
     SÓ com o que VOCÊ gerou (scrap, chat salvos, rss, feedback, diálogos)
     — sem datasets baixados, sem o modelo, sem a pasta dados inteira;
     leve o suficiente para ir por Google Drive.
  3. No celular, salva o zip no Google Drive. No PC, abre o Drive, baixa e
     joga o zip em dados/Celular/ (pasta comum aos dois).
  4. No dashboard do PC: "Importar de dados/Celular" lê os zips/arquivos
     soltos, distribui cada um na pasta certa e arquiva o zip em
     dados/Celular/importados/ (evita re-importar). Registro em
     dados/Celular/import_log.json.

Regras:
  - Export inclui SÓ o que o usuário gerou (scrap, chat_salvos, rss,
    feedback, dialogos) — nunca datasets baixados de processed/gerados,
    nem modelo/, tokenizer/, dados/descartados/, caches, binários grandes.
  - Import distribui por extensão: .jsonl → gerados (validar/promover no
    treino local), .txt → raw (tratar na página Tratamento), .parquet →
    processed. Assim o pipeline de qualidade existente valida tudo.
"""
from __future__ import annotations

import os
import re
import shutil
import threading
import time
import zipfile
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
BASE_DADOS = RAIZ / "dados"
PASTA_CELULAR = BASE_DADOS / "Celular"
PASTA_IMPORTADOS = PASTA_CELULAR / "importados"
DIST = RAIZ / "dist"
LOG_IMPORT = PASTA_CELULAR / "import_log.json"

# Extensões de treino que entram no export (e no import por arquivo solto)
EXTS_TREINO = (".jsonl", ".txt", ".parquet")
# Pastas que NUNCA entram no export (peso/ruído)
EXCLUIR_DIRS = {"__pycache__", ".cache", "descartados", "importados",
                "_importando", "dominguesm_restore-punctuation-ptbr-dataset"}
# Arquivo único acima deste tamanho é ignorado no export (evita binário gigante)
MAX_ARQ_MB = 200

# Estado global (thread-safe)
_estado: dict = {
    "rodando": False,
    "operacao": None,     # exportar | importar
    "etapa": "idle",      # idle | trabalhando | concluido | erro
    "mensagem": "",
    "inicio": None,
    "fim": None,
    "erro": None,
    "ultimo_import": None,
}
_lock = threading.Lock()


def _atualizar(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)


def get_estado() -> dict:
    with _lock:
        est = dict(_estado)
    est["exportacoes"] = listar_exportacoes()
    est["pendentes"] = _verificar_pendentes()
    return est


# ============================================================================
# EXPORT (gerado no celular — matéria-prima utilizável)
# ============================================================================

def _coletar_treinaveis() -> list[tuple[Path, str]]:
    """[(origem, relativo)] do que o USUÁRIO GEROU (colaborativo).

    NÃO inclui processed/gerados gerais (datasets baixados) nem a pasta
    'dados' como prefixo — só as fontes de criação: scrap, chat salvos,
    rss, feedback e diálogos. Quem quiser mais dados baixa/raspa/cria.
    """
    arquivos: list[tuple[Path, str]] = []

    def _add(raiz: Path, prefixo: str, extras: tuple[str, ...] = ()) -> None:
        if not raiz.exists():
            return
        for dirpath, dirnames, filenames in os.walk(raiz):
            dirnames[:] = [d for d in dirnames if d not in EXCLUIR_DIRS]
            for nome in filenames:
                if not (nome.endswith(EXTS_TREINO) or nome.endswith(extras)):
                    continue
                p = Path(dirpath) / nome
                try:
                    if p.stat().st_size > MAX_ARQ_MB * 1024 * 1024:
                        continue
                except OSError:
                    continue
                rel = (Path(prefixo) / p.relative_to(raiz)).as_posix()
                arquivos.append((p, rel))

    # Fontes geradas pelo usuário (colaborativo) — sem prefixo 'dados/'
    _add(BASE_DADOS / "processed" / "scrap", "processed/scrap")      # raspagens
    _add(BASE_DADOS / "raw" / "scrap", "raw/scrap")                  # staging do scrap
    _add(BASE_DADOS / "gerados" / "jsonl" / "chat_salvos", "gerados/chat_salvos")  # chat SFT
    _add(BASE_DADOS / "gerados" / "jsonl" / "rss", "gerados/rss")  # RSS
    _add(BASE_DADOS / "gerados" / "feedback_chat", "gerados/feedback_chat", extras=(".json",))  # feedback 👍/👎
    # diálogos (dialogos*, dialogos2*...) em gerados/jsonl
    for d in sorted((BASE_DADOS / "gerados" / "jsonl").glob("dialogos*")):
        if d.is_dir():
            _add(d, f"gerados/{d.name}")
    return arquivos


def _gerar_manifesto(arquivos: list[tuple[Path, str]]) -> str:
    linhas = [
        "RIGELSLM - EXPORTACAO COLABORATIVA (celular -> PC)",
        f"Gerado em: {datetime.now().isoformat()}",
        f"Total de arquivos: {len(arquivos)}",
        "",
        "O QUE ESTA DENTRO (so o que VOCE gerou):",
        "  - processed/scrap/      (suas raspagens)",
        "  - gerados/chat_salvos/  (conversas salvas SFT)",
        "  - gerados/rss/          (artigos de RSS)",
        "  - gerados/feedback_chat/(feedback 👍/👎 com fontes)",
        "  - gerados/dialogos*/    (dialogos gerados)",
        "",
        "NAO INCLUI (de proposito):",
        "  - datasets baixados (processed/gerados gerais)",
        "  - modelo, tokenizer, dados/raw pesado",
        "",
        "COMO IMPORTAR NO PC:",
        "  1. Salve este zip no Google Drive (ou envie por qualquer meio).",
        "  2. No PC, baixe e jogue o zip em:  dados/Celular/",
        "  3. No dashboard do PC: secao 'Celular <-> PC' -> 'Importar de dados/Celular'.",
        "  4. Depois valide/promova em Treino Local (jsonl) ou Tratamento (txt).",
    ]
    return "\n".join(linhas)


def _exportar_trabalho() -> None:
    _inicio = time.time()
    try:
        _atualizar(mensagem="Coletando arquivos de treino...")
        arquivos = _coletar_treinaveis()
        if not arquivos:
            raise RuntimeError("Nenhum arquivo de treino encontrado para exportar.")

        DIST.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = DIST / f"rigel_export_{ts}.zip"

        total_mb = sum(p.stat().st_size for p, _ in arquivos) / 1e6
        _atualizar(mensagem=f"Compactando {len(arquivos)} arquivos ({total_mb:.0f} MB)...")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for src, rel in arquivos:
                z.write(src, rel)
            z.writestr("MANIFESTO.txt", _gerar_manifesto(arquivos))

        _atualizar(
            rodando=False, operacao=None, etapa="concluido",
            mensagem=(f"✅ Exportação pronta: {zip_path.name} "
                      f"({zip_path.stat().st_size / 1e6:.1f} MB, {len(arquivos)} arquivos) "
                      f"em {time.time() - _inicio:.0f}s"),
            fim=datetime.now().isoformat(),
        )
    except Exception as e:  # noqa: BLE001
        _atualizar(rodando=False, operacao=None, etapa="erro",
                   mensagem=f"❌ Falha no export: {e}", erro=str(e)[:300],
                   fim=datetime.now().isoformat())


def exportar() -> dict:
    """Dispara o export em thread. Retorna estado inicial."""
    with _lock:
        if _estado["rodando"]:
            return {"ok": False, "mensagem": "Já existe uma operação em andamento."}
        _estado.update(rodando=True, operacao="exportar", etapa="trabalhando",
                       mensagem="Iniciando exportação...", inicio=datetime.now().isoformat(),
                       fim=None, erro=None)
    threading.Thread(target=_exportar_trabalho, daemon=True).start()
    return {"ok": True, "mensagem": "Exportação iniciada."}


def listar_exportacoes() -> list[dict]:
    if not DIST.exists():
        return []
    versoes = []
    for p in sorted(DIST.glob("rigel_export_*.zip"), reverse=True):
        try:
            versoes.append({
                "nome": p.name,
                "tamanho_mb": round(p.stat().st_size / 1e6, 1),
                "data": datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M"),
                "url": f"/api/celular/download/{p.name}",
            })
        except OSError:
            continue
    return versoes


def remover_exportacao(nome: str) -> dict:
    nome = Path(nome).name
    if not nome.startswith("rigel_export_") or not nome.endswith(".zip"):
        return {"ok": False, "mensagem": "Nome inválido."}
    p = DIST / nome
    if not p.exists():
        return {"ok": False, "mensagem": "Não encontrado."}
    try:
        p.unlink()
        return {"ok": True, "mensagem": f"Removido {nome}."}
    except OSError as e:
        return {"ok": False, "mensagem": f"Erro: {e}"}


# ============================================================================
# IMPORT (no PC — pasta comum dados/Celular)
# ============================================================================

def _verificar_pendentes() -> dict:
    """O que está aguardando importação em dados/Celular/."""
    if not PASTA_CELULAR.exists():
        return {"zips": [], "soltos": [], "caminho": str(PASTA_CELULAR)}
    zips, soltos = [], []
    for p in sorted(PASTA_CELULAR.iterdir()):
        if p.is_dir():
            continue
        if p.suffix.lower() == ".zip":
            try:
                zips.append({"nome": p.name, "tamanho_mb": round(p.stat().st_size / 1e6, 1)})
            except OSError:
                pass
        elif p.suffix.lower() in EXTS_TREINO:
            try:
                soltos.append({"nome": p.name, "tamanho_mb": round(p.stat().st_size / 1e6, 2)})
            except OSError:
                pass
    return {"zips": zips, "soltos": soltos, "caminho": str(PASTA_CELULAR)}


def _destino_por_ext(ext: str) -> Path:
    """Pasta de destino conforme o tipo (o pipeline de qualidade valida depois)."""
    if ext == ".jsonl":
        return BASE_DADOS / "gerados" / f"celular_importado_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if ext == ".parquet":
        return BASE_DADOS / "processed" / f"celular_importado_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return BASE_DADOS / "raw" / f"celular_importado_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def _importar_zip(zip_path: Path, log: list) -> int:
    """Extrai com segurança e distribui os arquivos de treino. Retorna nº importado."""
    _importados = 0
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = PASTA_CELULAR / f"_importando_{ts}"
    try:
        tmp.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                nome = info.filename
                # proteção contra path traversal
                alvo = (tmp / nome).resolve()
                if not str(alvo).startswith(str(tmp.resolve())):
                    continue
                if info.is_dir():
                    alvo.mkdir(parents=True, exist_ok=True)
                    continue
                alvo.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(alvo, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        # distribui por extensão
        for dirpath, _, filenames in os.walk(tmp):
            for nome in filenames:
                ext = Path(nome).suffix.lower()
                if ext not in EXTS_TREINO:
                    continue
                origem = Path(dirpath) / nome
                destino = _destino_por_ext(ext)
                destino.mkdir(parents=True, exist_ok=True)
                # nome único (evita colisão de arquivos com mesmo nome)
                final = destino / f"{ts}_{nome}"
                n = 2
                while final.exists():
                    final = destino / f"{ts}_{n}_{nome}"
                    n += 1
                shutil.move(str(origem), str(final))
                _importados += 1
        log.append({"arquivo": zip_path.name, "tipo": "zip", "importados": _importados})
        # arquiva o zip (histórico, não re-importa)
        PASTA_IMPORTADOS.mkdir(parents=True, exist_ok=True)
        shutil.move(str(zip_path), str(PASTA_IMPORTADOS / zip_path.name))
        return _importados
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _importar_soltos(log: list) -> int:
    """Importa arquivos soltos (jsonl/txt/parquet) jogados direto em dados/Celular/."""
    _importados = 0
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for p in sorted(PASTA_CELULAR.iterdir()):
        if not p.is_file() or p.suffix.lower() not in EXTS_TREINO:
            continue
        destino = _destino_por_ext(p.suffix.lower())
        destino.mkdir(parents=True, exist_ok=True)
        final = destino / f"{ts}_{p.name}"
        n = 2
        while final.exists():
            final = destino / f"{ts}_{n}_{p.name}"
            n += 1
        shutil.move(str(p), str(final))
        _importados += 1
    if _importados:
        log.append({"arquivo": "(soltos)", "tipo": "soltos", "importados": _importados})
    return _importados


def _registrar_log(log: list) -> None:
    entradas = []
    if LOG_IMPORT.exists():
        try:
            import json
            entradas = json.loads(LOG_IMPORT.read_text(encoding="utf-8"))
        except Exception:
            entradas = []
    entradas.append({"quando": datetime.now().isoformat(), "itens": log})
    LOG_IMPORT.parent.mkdir(parents=True, exist_ok=True)
    LOG_IMPORT.write_text(
        __import__("json").dumps(entradas, ensure_ascii=False, indent=2), encoding="utf-8")


def _importar_trabalho() -> None:
    _inicio = time.time()
    try:
        PASTA_CELULAR.mkdir(parents=True, exist_ok=True)
        _atualizar(mensagem="Verificando dados/Celular...")
        pend = _verificar_pendentes()
        zips = pend["zips"]
        soltos = pend["soltos"]
        if not zips and not soltos:
            _atualizar(rodando=False, operacao=None, etapa="concluido",
                       mensagem="Nada para importar em dados/Celular/.",
                       fim=datetime.now().isoformat())
            return

        log: list = []
        total = 0
        for z in zips:
            _atualizar(mensagem=f"Importando {z['nome']}...")
            total += _importar_zip(PASTA_CELULAR / z["nome"], log)
        total += _importar_soltos(log)
        _registrar_log(log)
        _atualizar(
            rodando=False, operacao=None, etapa="concluido",
            mensagem=(f"✅ Importados {total} arquivo(s) de treino "
                      f"({len(zips)} zip(s), {len(soltos)} solto(s)) "
                      f"em {time.time() - _inicio:.0f}s. "
                      f"Valide em Treino Local (jsonl) / Tratamento (txt)."),
            fim=datetime.now().isoformat(), ultimo_import=log,
        )
    except Exception as e:  # noqa: BLE001
        _atualizar(rodando=False, operacao=None, etapa="erro",
                   mensagem=f"❌ Falha no import: {e}", erro=str(e)[:300],
                   fim=datetime.now().isoformat())


def importar() -> dict:
    with _lock:
        if _estado["rodando"]:
            return {"ok": False, "mensagem": "Já existe uma operação em andamento."}
        _estado.update(rodando=True, operacao="importar", etapa="trabalhando",
                       mensagem="Iniciando importação...", inicio=datetime.now().isoformat(),
                       fim=None, erro=None)
    threading.Thread(target=_importar_trabalho, daemon=True).start()
    return {"ok": True, "mensagem": "Importação iniciada."}
