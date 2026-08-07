#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
explosao_local.py — Explosão CONTROLADA de datasets baixados (raw → gerados).

Diferente do fluxo automático do download, aqui o usuário decide: estima o
impacto (tamanhos, espaço, tempo na máquina) e pode INICIAR / PAUSAR /
RETOMAR / PARAR. Tudo persistido e registrado.

Estado:   estado/explosao_estado.json     (andamento, eventos, motivos)
Controle: estado/explosao_controle.json   (pausar/parar — lido pela thread)
Log:      logs/explosao.log               (linha do tempo com data/hora)
"""
from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))

_PASTA_ESTADO = PROJETO_ROOT / "estado"
_ARQUIVO_ESTADO = _PASTA_ESTADO / "explosao_estado.json"
_ARQUIVO_CONTROLE = _PASTA_ESTADO / "explosao_controle.json"
_ARQUIVO_LOG = PROJETO_ROOT / "logs" / "explosao.log"

_lock = threading.Lock()
_estado: dict = {
    "rodando": False,
    "status": "idle",        # idle | estimando | preparando | explodindo | pausado | parado | concluido | erro
    "repo": None,
    "nome": None,
    "caminho": None,
    "inicio": None,
    "fim": None,
    "total_exemplos": 0,
    "total_arquivos": 0,
    "total_pastas": 0,
    "estimativa": None,
    "eventos": [],            # linha do tempo: {data, tipo, msg}
    "erro": None,
}

# mtime do arquivo de estado quando este processo sincronizou (harmonia com o disco)
_estado_mtime: float = 0.0


def _persistir() -> None:
    global _estado_mtime
    try:
        _PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
        _ARQUIVO_ESTADO.write_text(
            json.dumps(_estado, ensure_ascii=False, indent=2), encoding="utf-8")
        _estado_mtime = _ARQUIVO_ESTADO.stat().st_mtime
    except Exception:
        pass


def _recarregar_se_mudou() -> None:
    """Harmonia dashboard↔backend: se estado/explosao_estado.json mudou FORA
    deste processo (ex.: explosão/registro por CLI ou script), recarrega do disco
    para o painel sempre refletir o que realmente aconteceu (regra de ouro)."""
    global _estado, _estado_mtime
    try:
        if _ARQUIVO_ESTADO.exists():
            mt = _ARQUIVO_ESTADO.stat().st_mtime
            if mt != _estado_mtime:
                dados = json.loads(_ARQUIVO_ESTADO.read_text(encoding="utf-8"))
                if isinstance(dados, dict):
                    _estado.update(dados)
                _estado_mtime = mt
    except Exception:
        pass


def _log_linha(linha: str) -> None:
    try:
        _ARQUIVO_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_ARQUIVO_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {linha}\n")
    except Exception:
        pass


def _evento(tipo: str, msg: str) -> None:
    with _lock:
        _estado["eventos"] = _estado.get("eventos", [])[-200:]
        _estado["eventos"].append({"data": datetime.now().isoformat(), "tipo": tipo, "msg": msg})
        _persistir()
    _log_linha(f"[{tipo}] {msg}")


def _ler_controle() -> dict:
    try:
        if _ARQUIVO_CONTROLE.exists():
            return json.loads(_ARQUIVO_CONTROLE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _escrever_controle(acao) -> None:
    try:
        _PASTA_ESTADO.mkdir(parents=True, exist_ok=True)
        _ARQUIVO_CONTROLE.write_text(
            json.dumps({"acao": acao, "atualizado_em": datetime.now().isoformat()}),
            encoding="utf-8")
    except Exception:
        pass


def status() -> dict:
    _recarregar_se_mudou()
    with _lock:
        return dict(_estado)


def limpar() -> dict:
    """Reseta o estado da explosão para idle (esquecer o último resultado)."""
    _escrever_controle(None)
    with _lock:
        _estado.update({
            "rodando": False, "status": "idle",
            "repo": None, "nome": None, "caminho": None,
            "inicio": None, "fim": None,
            "total_exemplos": 0, "total_arquivos": 0, "total_pastas": 0,
            "estimativa": None, "eventos": [], "erro": None,
        })
        _persistir()
    return {"ok": True, "mensagem": "Estado de explosão limpo (esquecido)."}


def _deve_continuar():
    """Chamado pelo explodir_dataset a cada exemplo — lê o controle."""
    c = _ler_controle()
    acao = c.get("acao")
    if acao == "parar":
        _evento("parar", "Parada solicitada pelo usuário — interrompendo...")
        return False
    if acao == "pausar":
        with _lock:
            _estado["status"] = "pausado"
        _evento("pausar", "Pausa solicitada pelo usuário — interrompendo no próximo arquivo.")
        return False
    return True


def _amostrar_linhas(caminho, n: int = 10) -> list:
    """Lê até n objetos JSON válidos do início do arquivo (para auto-evolução)."""
    import json as _json
    amostra = []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    obj = _json.loads(linha)
                except Exception:
                    continue
                if isinstance(obj, list):
                    obj = obj[0] if obj else None
                if isinstance(obj, dict):
                    amostra.append(obj)
                    if len(amostra) >= n:
                        break
    except Exception:
        pass
    return amostra


def _trabalho(caminho: str, nome: str, repo: str, max_exemplos=None) -> None:
    try:
        import createjsonl as cj

        _evento("inicio", f"Iniciando explosão de '{repo or nome}' → {nome}")
        _evento("preparando", "Movendo/preparando arquivos e verificando espaço...")

        # Limpa controle residual e marca como explodindo
        _escrever_controle(None)
        with _lock:
            _estado["status"] = "explodindo"
            _estado["rodando"] = True
            _persistir()

        def _on_progresso(processados, total):
            with _lock:
                _estado["total_exemplos"] = processados
            _evento("progresso", f"{processados} exemplos processados")

        def _on_evento(tipo, msg):
            if tipo == "arquivo":
                with _lock:
                    _estado["total_arquivos"] = _estado.get("total_arquivos", 0) + 1
                _evento("arquivo", f"Arquivo criado: {msg}")
            elif tipo == "fim":
                _evento("fim", msg)

        def _on_diagnostico(diag):
            with _lock:
                _estado["diagnostico"] = diag
                _estado["status"] = "erro"
            _evento("erro", f"Não explodiu ({diag.get('tipo')}): {diag.get('motivo')} "
                            f"— Sugestão: {diag.get('sugestao')}")

        # Pré-checagem LEVE (amostra ~100 linhas): se o formato não normaliza
        # (ex.: pre_treino_texto), diagnostica ANTES de ler o arquivo inteiro —
        # evita gastar tempo/SSD lendo 4 GB só para descobrir 0 exemplos.
        diag_pre = None
        try:
            import json as _json
            _lidas = 0
            _achou = False
            with open(caminho, "r", encoding="utf-8") as _f:
                for _linha in _f:
                    _linha = _linha.strip()
                    if not _linha:
                        continue
                    _lidas += 1
                    try:
                        _obj = _json.loads(_linha)
                    except Exception:
                        continue
                    if isinstance(_obj, list):
                        _obj = _obj[0] if _obj else None
                    if not isinstance(_obj, dict):
                        continue
                    if cj.normalizar_exemplo(_obj) or cj.normalizar_exemplo_causal(_obj):
                        _achou = True
                        break
                    if _lidas >= 100:
                        break
            if _lidas == 0:
                diag_pre = {"tipo": "arquivo_vazio", "motivo": "Arquivo vazio.",
                            "sugestao": "Refaça o download."}
            elif not _achou:
                diag_pre = cj._diagnosticar_falha_explosao(caminho)
        except Exception:
            diag_pre = None

        if diag_pre:
            total_ex, total_arq, total_pas = 0, 0, 0
            _on_diagnostico(diag_pre)
        else:
            total_ex, total_arq, total_pas = cj.explodir_dataset(
                caminho, nome, max_exemplos=max_exemplos,
                max_files=5000, exemplos_por_arquivo=1000,
                on_progresso=_on_progresso, on_diagnostico=_on_diagnostico,
                deve_continuar=_deve_continuar, on_evento=_on_evento)

        c = _ler_controle()
        if c.get("acao") == "pausar":
            _escrever_controle(None)
            with _lock:
                _estado["status"] = "pausado"
            _evento("pausado", f"PAUSADO: {total_ex} exemplos, {total_arq} arquivos até aqui. "
                               "Retome quando quiser (pode treinar outro dataset enquanto isso).")
        elif c.get("acao") == "parar":
            _escrever_controle(None)
            with _lock:
                _estado["status"] = "parado"
            _evento("parado", f"PARADO: {total_ex} exemplos, {total_arq} arquivos salvos. "
                              "Os dados já gerados ficam em dados/gerados/jsonl/<nome>/.")
        else:
            with _lock:
                _estado["total_exemplos"] = total_ex
                _estado["total_arquivos"] = total_arq
                _estado["total_pastas"] = total_pas
                if _estado.get("diagnostico"):
                    _estado["status"] = "erro"
                else:
                    _estado["status"] = "concluido"
            if not _estado.get("diagnostico"):
                _evento("concluido", f"Explosão concluída: {total_ex} exemplos, {total_arq} arquivos, "
                                     f"{total_pas} pastas → dados/gerados/jsonl/{nome}/")
    except Exception as e:
        import traceback
        traceback.print_exc()
        with _lock:
            _estado["status"] = "erro"
            _estado["erro"] = str(e)
        _evento("erro", f"Falha na explosão: {e}")
    finally:
        _escrever_controle(None)
        with _lock:
            _estado["rodando"] = False
            _estado["fim"] = datetime.now().isoformat()
            _persistir()


def iniciar(caminho: str, repo: str = "", nome: str = "") -> dict:
    with _lock:
        if _estado.get("rodando"):
            return {"ok": False, "erro": "Já existe uma explosão em andamento. Pause/are ou aguarde."}
    p = Path(caminho)
    # Resolve pasta → dataset.jsonl (ou primeiro .jsonl) SEMPRE que for pasta.
    # (Antes só resolvia dentro de 'if not p.exists()' → a pasta existia e a
    #  explosão tentava abrir a PASTA como arquivo → Permission denied + 0 exemplos.)
    if p.is_dir():
        if (p / "dataset.jsonl").exists():
            p = p / "dataset.jsonl"
        else:
            jsons = sorted(p.glob("*.jsonl"))
            if jsons:
                p = jsons[0]
            else:
                return {"ok": False, "erro": f"Sem arquivo JSONL dentro de: {caminho}"}
    if not p.exists():
        return {"ok": False, "erro": f"Caminho não encontrado: {caminho}"}
    nome = nome or (repo.replace("/", "_") if repo else p.stem)
    with _lock:
        _estado.update({
            "rodando": True, "status": "estimando", "repo": repo or p.parent.name,
            "nome": nome, "caminho": str(p), "inicio": datetime.now().isoformat(),
            "fim": None, "total_exemplos": 0, "total_arquivos": 0, "total_pastas": 0,
            "estimativa": None, "eventos": [], "erro": None, "diagnostico": None,
        })
        _persistir()
    threading.Thread(target=_trabalho, args=(str(p), nome, repo), daemon=True).start()
    return {"ok": True, "mensagem": "Explosão iniciada. Estimei antes de começar — consulte /status."}


def pausar() -> dict:
    _escrever_controle("pausar")
    return {"ok": True, "mensagem": "Pausa solicitada (para no próximo arquivo)."}


def retomar() -> dict:
    _escrever_controle(None)
    with _lock:
        if _estado.get("status") == "pausado":
            _estado["status"] = "explodindo"
            _persistir()
    return {"ok": True, "mensagem": "Retomado."}


def parar() -> dict:
    _escrever_controle("parar")
    return {"ok": True, "mensagem": "Parada solicitada (para no próximo arquivo)."}


def registrar_resultado_externo(nome: str, caminho: str = "", repo: str = "",
                                total_exemplos: int = 0, total_arquivos: int = 0,
                                total_pastas: int = 0,
                                diagnostico: dict | None = None) -> dict:
    """Registra no DASHBOARD o resultado de uma explosão feita FORA do motor
    (ex.: CLI createjsonl.py --process) — REGRA DE OURO: o dashboard informa tudo.

    Atualiza estado/explosao_estado.json para o painel 'Explosão controlada'
    mostrar o resultado sem precisar refazer o trabalho.
    """
    com_resultado = total_exemplos > 0 or total_arquivos > 0
    with _lock:
        _estado["rodando"] = False
        _estado["status"] = "concluido" if com_resultado else ("erro" if diagnostico else "concluido")
        _estado["repo"] = repo or _estado.get("repo") or nome
        _estado["nome"] = nome
        if caminho:
            _estado["caminho"] = caminho
        _estado["fim"] = datetime.now().isoformat()
        if not _estado.get("inicio"):
            _estado["inicio"] = datetime.now().isoformat()
        _estado["total_exemplos"] = total_exemplos
        _estado["total_arquivos"] = total_arquivos
        _estado["total_pastas"] = total_pastas
        _estado["diagnostico"] = diagnostico
        _estado["erro"] = (diagnostico or {}).get("motivo") if diagnostico else None
        _estado.setdefault("eventos", []).append({
            "data": datetime.now().isoformat(), "tipo": "registro_externo",
            "msg": f"Resultado registrado (execução fora do dashboard): {total_exemplos} exemplos, "
                   f"{total_arquivos} arquivos, {total_pastas} pastas."})
        _estado["eventos"] = _estado["eventos"][-40:]
        _persistir()
    _log_linha(f"[registro_externo] {nome}: {total_exemplos} ex, {total_arquivos} arq, {total_pastas} pas")
    return {"ok": True, "status": _estado["status"], "nome": nome,
            "total_exemplos": total_exemplos, "total_arquivos": total_arquivos}
