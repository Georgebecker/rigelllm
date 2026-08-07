#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
hf_datasets.py - Serviço de busca e download de datasets JSONL (PT-BR) do HuggingFace
Versão: 1.0.0 | Data: 01/08/2026

- buscar_datasets(query): pesquisa datasets no HuggingFace Hub (API pública, sem
  dependência extra; usa huggingface_hub se disponível).
- baixar_e_explodir(repo_id): baixa via createjsonl.baixar_huggingface e explode para
  dados/gerados/jsonl/<nome>/ (formato lido pelo treinar_com_jsonl.py).
- Estado de progresso em memória (thread-safe) para o dashboard consultar.

NÃO modifica nada existente — apenas reutiliza as funções do createjsonl.py.
"""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
from pathlib import Path

# Garante que a raiz do projeto esteja no path (para importar createjsonl)
PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))

# Pasta onde os datasets explodidos vão parar (mesma do createjsonl)
PASTA_JSONL = PROJETO_ROOT / "dados" / "gerados" / "jsonl"

# Termos padrão de busca (PT-BR / instrução)
TERMOS_PADRAO = ["portuguese instruction", "pt-br", "ptbr", "alpaca pt", "instruct pt-br"]

# Estado global de progresso (thread-safe)
_estado: dict = {
    "rodando": False,
    "repo": None,
    "etapa": "idle",          # idle | baixando | explodindo | concluido | erro
    "mensagem": "",
    "percentual": None,        # 0-100 durante a explosão; None = indeterminado
    "inicio": None,
    "fim": None,
    "total_exemplos": 0,
    "total_arquivos": 0,
    "total_pastas": 0,
    "erro": None,
    "diagnostico": None,        # preenchido quando a explosão gera 0 exemplos
    "tratado_exemplos": 0,       # quantos exemplos saíram limpos da sanitização automática
    "limpos_origens": 0,          # quantas origens (raw/gerados/sanitizados) foram removidas após promover
    "tratamento": None,            # qual tratamento foi aplicado: sanitizar | limpeza_leve | nenhum
    "travado": False,              # True quando o estado persistido indica download órfão (processo morreu)
}
_lock = threading.Lock()

# Persistência: o feedback DEVE sobreviver a --reload (o estado não pode ser só memória)
_PERSISTENCIA = PROJETO_ROOT / "estado" / "datasets_estado.json"


def _persistir_estado() -> None:
    try:
        _PERSISTENCIA.parent.mkdir(parents=True, exist_ok=True)
        _PERSISTENCIA.write_text(
            json.dumps(_estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _carregar_persistido() -> dict:
    try:
        if _PERSISTENCIA.exists():
            return json.loads(_PERSISTENCIA.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _atualizar_estado(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)
        _persistir_estado()


def get_estado() -> dict:
    """Retorna uma cópia do estado atual (thread-safe).

    Se esta instância nunca rodou (idle sem repo) mas há estado persistido de uma
    execução anterior, devolve o persistido — o feedback chega ao usuário mesmo
    depois de um --reload do servidor.

    DETECÇÃO DE ÓRFÃO/TRÁVADO: se o persistido diz "rodando" mas NENHUM thread
    roda nesta instância (estamos idle), o processo anterior morreu no meio
    (crash/reload). Em vez de mostrar "Download em andamento" para sempre,
    converte para etapa='travado' — a página avisa e oferece Limpar + Baixar de novo.
    """
    with _lock:
        if _estado.get("etapa") == "idle" and not _estado.get("repo"):
            persistido = _carregar_persistido()
            if persistido:
                if persistido.get("rodando") or persistido.get("etapa") in ("baixando", "explodindo"):
                    # Nenhum thread roda aqui (in-memory idle) → processo anterior morreu.
                    persistido["rodando"] = False
                    persistido["etapa"] = "travado"
                    persistido["travado"] = True
                    persistido["erro"] = persistido.get("erro") or "processo anterior morreu no meio"
                    persistido["mensagem"] = (
                        f"⚠️ Download órfão: parou no meio do caminho "
                        f"({persistido.get('percentual') or 0}% / {persistido.get('repo')}) — "
                        f"o processo anterior morreu (crash ou reinício). "
                        f"Limpe o estado e baixe novamente.")
                    persistido["fim"] = datetime.now().isoformat()
                    _estado.update(persistido)
                    _persistir_estado()
                    return dict(persistido)
                return persistido
        return dict(_estado)


def _montar_item(ds) -> dict:
    """Normaliza um item de dataset (DatasetInfo do huggingface_hub OU dict da API)
    e extrai metadados úteis das tags: tamanho, formato, idioma, gated."""
    if isinstance(ds, dict):
        d = ds
    else:
        d = {
            "id": getattr(ds, "id", ""),
            "description": getattr(ds, "description", "") or "",
            "downloads": getattr(ds, "downloads", 0) or 0,
            "likes": getattr(ds, "likes", 0) or 0,
            "lastModified": getattr(ds, "last_modified", "") or "",
            "author": getattr(ds, "author", "") or "",
            "gated": bool(getattr(ds, "gated", False)),
            "tags": list(getattr(ds, "tags", None) or []),
        }
    tags = [str(t) for t in (d.get("tags") or [])]
    tamanho = next((t.split(":", 1)[1] for t in tags if t.startswith("size_categories:")), None)
    formato = next((t.split(":", 1)[1] for t in tags if t.startswith("format:")), None)
    idiomas = [t.split(":", 1)[1] for t in tags if t.startswith("language:")]
    return {
        "id": d.get("id", ""),
        "descricao": d.get("description", "") or "",
        "downloads": d.get("downloads", 0) or 0,
        "likes": d.get("likes", 0) or 0,
        "atualizado": d.get("lastModified", "") or "",
        "autor": d.get("author", "") or "",
        "tamanho": tamanho,
        "formato": formato,
        "idioma": idiomas,
        "gated": bool(d.get("gated")),
        "exato": False,
    }


def buscar_datasets(query: str, limite: int = 10) -> list:
    """
    Pesquisa datasets no HuggingFace Hub.
    1) Tenta huggingface_hub.HfApi.list_datasets (busca semântica, se instalado).
    2) Fallback: API pública https://huggingface.co/api/datasets?search=...
    Se o termo parecer um ID de repositório (ex.: "adalbertojunior/Guara"),
    também tenta o dataset EXATO e o coloca no topo (marcado como exato).
    Retorna lista de dicts com metadados (tamanho, idioma, formato, gated...).
    Em falha total, retorna [] (o dashboard mostra "nenhum resultado").
    """
    resultado = []
    tentar_hub = True
    try:
        from huggingface_hub import HfApi  # opcional
    except Exception:
        tentar_hub = False

    if tentar_hub:
        try:
            api = HfApi()
            for ds in api.list_datasets(search=query, limit=limite, sort="downloads"):
                resultado.append(_montar_item(ds))
        except Exception as e:
            print(f"[HF] list_datasets falhou ({e}); usando API pública...")
            resultado = []

    if not resultado:
        import requests
        try:
            resp = requests.get("https://huggingface.co/api/datasets",
                                params={"search": query, "limit": limite},
                                timeout=20,
                                headers={"User-Agent": "Mozilla/5.0 (RigelSLM Dashboard)"})
            resp.raise_for_status()
            resultado = [_montar_item(ds) for ds in resp.json()]
        except Exception as e:
            print(f"[HF] API pública falhou: {e}")
            return []

    # Busca por ID exato (ex.: "adalbertojunior/Guara")
    if "/" in query:
        import requests
        repo = query.strip()
        try:
            resp = requests.get(f"https://huggingface.co/api/datasets/{repo}",
                                timeout=15,
                                headers={"User-Agent": "Mozilla/5.0 (RigelSLM Dashboard)"})
            if resp.status_code == 200:
                item = _montar_item(resp.json())
                item["exato"] = True
                resultado = [item] + [r for r in resultado if r["id"] != item["id"]]
        except Exception as e:
            print(f"[HF] busca por ID exato falhou: {e}")

    return resultado


def tamanho_repo(repo_id: str) -> dict:
    """Tamanho real (MB) + nº de linhas de um dataset via datasets-server da HF."""
    try:
        import requests
        resp = requests.get(
            "https://datasets-server.huggingface.co/size",
            params={"dataset": repo_id}, timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (RigelSLM Dashboard)"})
        if resp.status_code == 200:
            d = resp.json().get("size", {}).get("dataset", {})
            num_bytes = int(d.get("num_bytes_parquet_files")
                            or d.get("num_bytes_original_files") or 0)
            num_rows = int(d.get("num_rows", 0) or 0)
            return {"ok": True, "repo": repo_id,
                    "tamanho_mb": round(num_bytes / 1e6, 1),
                    "num_rows": num_rows}
        return {"ok": False, "repo": repo_id, "erro": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"ok": False, "repo": repo_id, "erro": str(e)}


def limpar() -> dict:
    """Reseta o estado de download/tratamento para idle (esquecer o último)."""
    with _lock:
        _estado.update({
            "rodando": False, "repo": None, "etapa": "idle", "mensagem": "",
            "percentual": None, "inicio": None, "fim": None,
            "total_exemplos": 0, "total_arquivos": 0, "total_pastas": 0,
            "erro": None, "diagnostico": None,
            "tratado_exemplos": 0, "limpos_origens": 0,
            "tratamento": None, "travado": False,
        })
        _persistir_estado()
    return {"ok": True, "mensagem": "Estado de download/tratamento limpo."}


def cancelar(apagar: bool = True) -> dict:
    """Cancela/libera um download travado ou em andamento.

    Reseta o estado para idle (libera o botão Baixar). Se apagar=True (padrão),
    remove a pasta raw/<repo> do download (parcial ou completo) para liberar
    espaço no HD e permitir recomeçar limpo. Usado quando o thread pendura
    (ex.: dataset gigante que travou depois da conversão).
    """
    repo = _estado.get("repo")
    with _lock:
        _estado.update({
            "rodando": False, "repo": None, "etapa": "idle", "mensagem": "",
            "percentual": None, "inicio": None, "fim": None,
            "total_exemplos": 0, "total_arquivos": 0, "total_pastas": 0,
            "erro": None, "diagnostico": None,
            "tratado_exemplos": 0, "limpos_origens": 0,
            "tratamento": None, "travado": False,
        })
        _persistir_estado()
    apagado = False
    if apagar and repo:
        import shutil as _sh
        alvo = PROJETO_ROOT / "dados" / "raw" / repo.replace("/", "_")
        try:
            if alvo.exists():
                if alvo.is_dir():
                    _sh.rmtree(str(alvo))
                else:
                    alvo.unlink()
                apagado = True
        except Exception as e:
            return {"ok": True, "mensagem": "Download cancelado (estado liberado).",
                    "repo": repo, "apagado": False, "erro_ao_apagar": str(e)}
    msg = "Download cancelado (estado liberado)."
    if apagado:
        msg += " Pasta raw apagada (HD liberado)."
    return {"ok": True, "mensagem": msg, "repo": repo, "apagado": apagado}


def baixar_e_explodir(repo_id: str, max_total=None, tratamento: str = "auto") -> dict:
    """
    Baixa um dataset do HuggingFace e explode para dados/gerados/jsonl/<nome>/.

    tratamento: "auto" (padrão) DETECTA o formato e aplica o tratamento certo:
      - parquet  → 🧹 limpeza_leve_rigel_v2.py → rigel_sft/pretrain.parquet em dados/processed
      - jsonl    → 🧼 sanitizacao PT-BR → promove p/ dados/processed/jsonl/
    Pode ser forçado: "sanitizar", "limpeza_leve" ou "nenhum" (só baixar/explodir).
    Após tratar, apaga as origens (raw/gerados/sanitizado) para liberar espaço.

    Reutiliza createjsonl.baixar_huggingface + explodir_dataset.
    Roda em THREAD separada; o progresso fica em get_estado().
    """
    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um download em andamento."}

    def _trabalho():
        _atualizar_estado(rodando=True, repo=repo_id, etapa="baixando",
                          mensagem="Iniciando download...", percentual=None,
                          inicio=datetime.now().isoformat(), fim=None,
                          erro=None, total_exemplos=0, total_arquivos=0, total_pastas=0)
        try:
            import createjsonl as cj
            import time as _time
            # Convenção Rigel: dataset BAIXADO recebe nome próprio do sistema
            # (rigeljsonl_<dia>_<hora>) — NUNCA o nome do repositório externo.
            data_hoje = datetime.now().strftime("%Y%m%d_%H%M")
            nome = f"rigeljsonl_{data_hoje}"
            contador = 2
            while (PROJETO_ROOT / "dados" / "gerados" / "jsonl" / nome).exists():
                nome = f"rigeljsonl_{data_hoje}_{contador}"
                contador += 1

            def _progresso_download(mb, mb_total, pct):
                if pct is not None and mb_total:
                    _atualizar_estado(percentual=pct,
                                      mensagem=f"Baixando... {mb:.0f} MB de {mb_total:.0f} MB ({pct}%)")
                else:
                    _atualizar_estado(mensagem=f"Baixando... {mb:.0f} MB transferidos")

            # Heartbeat: mantém a mensagem viva caso o método de download não reporte %
            _parar_hb = threading.Event()

            def _heartbeat():
                inicio_hb = _time.time()
                while not _parar_hb.is_set():
                    _time.sleep(2)
                    if get_estado().get("etapa") == "baixando" and get_estado().get("percentual") is None:
                        decorrido = int(_time.time() - inicio_hb)
                        _atualizar_estado(mensagem=(
                            f"Baixando do HuggingFace... {decorrido}s decorridos. "
                            f"Datasets grandes (ex.: 1,5 GB) podem levar alguns minutos."))

            threading.Thread(target=_heartbeat, daemon=True).start()
            _atualizar_estado(mensagem="Baixando do HuggingFace (datasets públicos: sem conta)...")
            origem = cj.baixar_huggingface(
                repo_id, str(PROJETO_ROOT / "dados" / "raw"),
                on_progresso=_progresso_download, max_total=max_total)
            _parar_hb.set()
            if not origem:
                _atualizar_estado(etapa="erro",
                                  mensagem="Falha ao baixar do HuggingFace.",
                                  erro="download falhou ou dataset é gated (defina HF_TOKEN)",
                                  percentual=None)
                return

            def _progresso(processados, total):
                pct = round(100 * processados / total) if total and total > 0 else None
                msg = f"Explodindo... {processados} exemplos"
                if pct is not None:
                    msg += f" ({pct}%)"
                _atualizar_estado(percentual=pct, total_exemplos=processados, mensagem=msg)

            _atualizar_estado(etapa="explodindo", percentual=0,
                              mensagem="Explodindo dataset (normaliza + dedup + system prompt)...")
            _diag: dict = {}

            def _on_diagnostico(d):
                _diag.update(d)

            total_ex, total_arq, total_pas = cj.explodir_dataset(
                origem, nome, max_exemplos=max_total,
                max_files=5000, exemplos_por_arquivo=1000,
                on_progresso=_progresso, on_diagnostico=_on_diagnostico)
            if total_ex == 0:
                # Explosão falhou. Se o download tem PARQUET (formato que não vira jsonl
                # no explode) e o tratamento permite → roda limpeza_leve_rigel_v2.py.
                _raw = PROJETO_ROOT / "dados" / "raw" / repo_id.replace("/", "_")
                _tem_parquet = bool(list(_raw.glob("*.parquet"))) if _raw.exists() else False
                if _tem_parquet and tratamento in ("auto", "limpeza_leve"):
                    _atualizar_estado(etapa="tratando", percentual=100,
                                      mensagem="🧹 Parquet detectado — rodando limpeza leve v2 "
                                               "→ rigel_sft/pretrain.parquet em dados/processed...")
                    try:
                        import subprocess as _sp
                        import shutil as _sh
                        _res = _sp.run(
                            [sys.executable, "-u", "limpeza_leve_rigel_v2.py",
                             "--origem", str(_raw),
                             "--saida", str(PROJETO_ROOT / "dados" / "processed")],
                            capture_output=True, text=True, timeout=3600,
                            encoding="utf-8", errors="replace",
                            cwd=str(PROJETO_ROOT))
                        _tratado = 1 if _res.returncode == 0 else 0
                        if _tratado:
                            _limpas = 0
                            for _ori in [
                                PROJETO_ROOT / "dados" / "raw" / repo_id.replace("/", "_"),
                                PROJETO_ROOT / "dados" / "gerados" / "jsonl" / nome,
                            ]:
                                try:
                                    if _ori.exists():
                                        if _ori.is_dir():
                                            _sh.rmtree(str(_ori))
                                        else:
                                            _ori.unlink()
                                        _limpas += 1
                                except Exception:
                                    pass
                            _atualizar_estado(etapa="concluido", percentual=100,
                                              mensagem="✅ Concluído! Parquet tratado (limpeza leve v2) "
                                                       "e origens limpas (HD liberado).",
                                              total_exemplos=0, total_arquivos=0,
                                              total_pastas=total_pas,
                                              tratado_exemplos=1,
                                              tratamento="limpeza_leve",
                                              limpos_origens=_limpas,
                                              fim=datetime.now().isoformat())
                        else:
                            _atualizar_estado(
                                etapa="erro", percentual=None,
                                mensagem="❌ Explosão gerou 0 exemplos",
                                erro=("limpeza leve v2 falhou (código "
                                      f"{_res.returncode}): {(_res.stderr or _res.stdout or '')[-200:]}"),
                                diagnostico=_diag,
                                total_exemplos=0, total_arquivos=0,
                                total_pastas=total_pas,
                                fim=datetime.now().isoformat())
                    except Exception as _e:
                        _atualizar_estado(etapa="erro", percentual=None,
                                          mensagem="❌ Explosão gerou 0 exemplos",
                                          erro=f"limpeza leve v2 falhou: {_e}",
                                          diagnostico=_diag,
                                          total_exemplos=0, total_arquivos=0,
                                          total_pastas=total_pas,
                                          fim=datetime.now().isoformat())
                else:
                    # Falha de explosão: diagnosticar e comunicar com clareza
                    motivo = _diag.get("motivo", "Nenhum exemplo extraído.")
                    sugestao = _diag.get("sugestao", "")
                    _atualizar_estado(etapa="erro", percentual=None,
                                      mensagem="❌ Explosão gerou 0 exemplos",
                                      erro=f"{motivo} {sugestao}".strip(),
                                      diagnostico=_diag,
                                      total_exemplos=0, total_arquivos=0,
                                      total_pastas=total_pas,
                                      fim=datetime.now().isoformat())
            else:
                # ✅ AUTOMAÇÃO (06/08): tratar após download conforme o FORMATO
                # jsonl explodido → 🧼 sanitizar (auto) ou 🧹 limpeza leve (pedido explícito)
                _tratado = 0
                _tratamento_usado = "nenhum"
                import shutil as _sh
                if tratamento != "nenhum":
                    if tratamento == "limpeza_leve":
                        # 🧹 limpeza leve v2 (jsonl explodido → rigel_sft/pretrain.parquet)
                        _tratamento_usado = "limpeza_leve"
                        _atualizar_estado(etapa="tratando", percentual=100,
                                          mensagem="Rodando limpeza leve v2 (jsonl → parquet)...")
                        try:
                            import subprocess as _sp
                            _res = _sp.run(
                                [sys.executable, "-u", "limpeza_leve_rigel_v2.py",
                                 "--origem", str(PASTA_JSONL / nome),
                                 "--saida", str(PROJETO_ROOT / "dados" / "processed")],
                                capture_output=True, text=True, timeout=3600,
                                encoding="utf-8", errors="replace",
                                cwd=str(PROJETO_ROOT))
                            if _res.returncode == 0:
                                _tratado = 1
                            else:
                                _atualizar_estado(
                                    mensagem="⚠️ limpeza leve v2 falhou (código "
                                             f"{_res.returncode}): {(_res.stderr or _res.stdout or '')[-200:]}")
                        except Exception as _e:
                            _atualizar_estado(mensagem=f"⚠️ limpeza leve v2 falhou: {_e}")
                    else:
                        # 🧼 sanitizar PT-BR (auto: jsonl → sanitizar; corrige mojibake, remove não-PT)
                        _tratamento_usado = "sanitizar"
                        _atualizar_estado(etapa="sanitizando", percentual=100,
                                          mensagem="Sanitizando (PT-BR): corrige mojibake, remove não-PT...")
                        try:
                            from dashboard.services import sanitizacao
                            _saida = str(PROJETO_ROOT / "dados" / "sanitizados" / nome)
                            _ini = sanitizacao.iniciar(str(PASTA_JSONL / nome), saida_dir=_saida)
                            if _ini.get("ok"):
                                _espera = 0
                                while _espera < 1800:  # máx 30 min
                                    _time.sleep(2)
                                    _espera += 2
                                    if not sanitizacao.status().get("rodando"):
                                        break
                                _st = sanitizacao.status()
                                _tratado = int(_st.get("total_gravados", 0) or 0)
                                if _tratado > 0:
                                    _atualizar_estado(etapa="promovendo",
                                                      mensagem=f"Promovendo {_tratado} exemplos limpos p/ processed...")
                                    _destino = PROJETO_ROOT / "dados" / "processed" / "jsonl" / nome
                                    _destino.mkdir(parents=True, exist_ok=True)
                                    for _f in Path(_saida).glob("*.jsonl"):
                                        try:
                                            _sh.copy2(str(_f), str(_destino / _f.name))
                                        except Exception:
                                            pass
                            else:
                                _atualizar_estado(mensagem="⚠️ Sanitização não iniciou: "
                                                            f"{_ini.get('erro', '?')}")
                        except Exception as _e:
                            _atualizar_estado(mensagem=f"⚠️ Sanitização automática falhou: {_e}")
                # ✅ LIMPEZA (06/08): libera espaço no HD — apaga as ORIGENS após tratar
                # (raw baixado + pasta explodida provisória + sanitizado intermediário)
                if _tratado > 0:
                    _atualizar_estado(etapa="promovendo",
                                      mensagem="Limpando origens (raw + explodido + sanitizado)...")
                    _limpas = 0
                    for _ori in [
                        PROJETO_ROOT / "dados" / "raw" / repo_id.replace("/", "_"),
                        PROJETO_ROOT / "dados" / "gerados" / "jsonl" / nome,
                        PROJETO_ROOT / "dados" / "sanitizados" / nome,
                    ]:
                        try:
                            if _ori.exists():
                                if _ori.is_dir():
                                    _sh.rmtree(str(_ori))
                                else:
                                    _ori.unlink()
                                _limpas += 1
                        except Exception:
                            pass
                    _atualizar_estado(tratado_exemplos=_tratado,
                                      limpos_origens=_limpas)
                # 📍 Comunicação clara do DESTINO dos dados (regra: dizer ONDE baixou)
                if _tratamento_usado == "sanitizar":
                    _saida_final = str(PROJETO_ROOT / "dados" / "processed" / "jsonl" / nome)
                elif _tratamento_usado == "limpeza_leve":
                    _saida_final = str(PROJETO_ROOT / "dados" / "processed" / "rigel_sft")
                else:
                    _saida_final = str(PASTA_JSONL / nome)
                _atualizar_estado(etapa="concluido", percentual=100,
                                  mensagem=("✅ Concluído! Tratado (" + _tratamento_usado +
                                            "), dados em: " + _saida_final +
                                            " — origens limpas (HD liberado)."
                                            if _tratado > 0 else
                                            "✅ Concluído! Dados em: " + _saida_final),
                                  saida_dir=_saida_final,
                                  total_exemplos=total_ex, total_arquivos=total_arq,
                                  total_pastas=total_pas,
                                  tratado_exemplos=_tratado,
                                  tratamento=_tratamento_usado,
                                  fim=datetime.now().isoformat())
        except Exception as e:
            import traceback
            traceback.print_exc()
            _atualizar_estado(etapa="erro", mensagem=str(e), erro=str(e), percentual=None,
                              fim=datetime.now().isoformat())
        finally:
            _atualizar_estado(rodando=False)

    threading.Thread(target=_trabalho, daemon=True).start()
    return {"ok": True, "mensagem": "Download iniciado em segundo plano."}
