"""Tratamento seguro do acervo, separado do pipeline de promoção.

Este serviço nunca escreve em dados/processed e nunca apaga a origem.
A saída fica em dados/tratados/<nome>_tratado/.
"""
from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.tratar_datasets_brutos import _tratar_linha

ROOT = Path(__file__).resolve().parent.parent.parent
BASES_PERMITIDAS = (ROOT / "dados" / "raw", ROOT / "dados" / "gerados",
                    ROOT / "dados" / "processed")
DESTINO_BASE = ROOT / "dados" / "tratados"
ESTADO_PATH = ROOT / "estado" / "tratamento_acervo_estado.json"
_lock = threading.RLock()
_pause_event = threading.Event()
_stop_event = threading.Event()
_revisao_thread: threading.Thread | None = None
_revisao_estado: dict[str, Any] = {
    "rodando": False, "percentual": 0, "linhas": 0, "arquivos": 0,
    "validos": 0, "invalidos": 0, "sem_formato": 0, "erro": None,
}
_estado: dict[str, Any] = {
    "rodando": False, "etapa": "idle", "percentual": 0,
    "origem": "", "destino": "", "mensagem": "", "erro": None,
    "linhas": 0, "aprovados": 0, "descartados": 0, "corrigidos": 0,
    "arquivos": 0, "arquivo_indice": 0, "log": [], "inicio": None, "fim": None,
}


def _persistir() -> None:
    try:
        ESTADO_PATH.parent.mkdir(parents=True, exist_ok=True)
        ESTADO_PATH.write_text(json.dumps(_estado, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _atualizar(**kwargs: Any) -> None:
    with _lock:
        _estado.update(kwargs)
        _persistir()


def _log(mensagem: str) -> None:
    linha = f"[{datetime.now().strftime('%H:%M:%S')}] {mensagem}"
    with _lock:
        _estado["log"] = (_estado.get("log", []) + [linha])[-300:]
        _estado["mensagem"] = mensagem
        _persistir()


def _carregar_estado_persistido() -> None:
    try:
        if ESTADO_PATH.exists():
            salvo = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
            if isinstance(salvo, dict):
                _estado.update(salvo)
    except Exception:
        pass


def _resolver_origem(valor: str) -> Path:
    caminho = Path(valor).expanduser()
    if not caminho.is_absolute():
        caminho = ROOT / caminho
    caminho = caminho.resolve()
    if not caminho.is_dir():
        raise ValueError("A pasta escolhida não existe.")
    if not any(caminho == base or base in caminho.parents for base in BASES_PERMITIDAS):
        raise ValueError("A origem precisa estar em dados/raw, dados/gerados ou dados/processed.")
    return caminho


def listar_origens() -> list[dict[str, Any]]:
    """Lista pastas JSONL disponíveis, sem alterar o acervo."""
    itens: list[dict[str, Any]] = []
    vistos: set[Path] = set()
    for base in BASES_PERMITIDAS:
        if not base.is_dir():
            continue
        for arquivo in base.rglob("*.jsonl"):
            pasta = arquivo.parent.resolve()
            if pasta in vistos:
                continue
            vistos.add(pasta)
            itens.append({
                "nome": str(pasta.relative_to(ROOT)).replace("\\", "/"),
                "caminho": str(pasta),
                "arquivos": len(list(pasta.glob("*.jsonl"))),
                "origem": str(base.relative_to(ROOT)).replace("\\", "/"),
            })
    return sorted(itens, key=lambda item: item["nome"].lower())


def _arquivos_jsonl(origem: Path) -> list[Path]:
    return sorted(p for p in origem.rglob("*.jsonl") if p.is_file())


def _executar_revisao(origem: Path) -> None:
    """Executa a revisão sem bloquear o servidor web."""
    global _revisao_estado
    try:
        arquivos = _arquivos_jsonl(origem)
        total = validos = invalidos = sem_formato = 0
        _revisao_estado.update({"rodando": True, "percentual": 0, "linhas": 0,
                                "arquivos": len(arquivos), "validos": 0,
                                "invalidos": 0, "sem_formato": 0, "erro": None})
        for indice, arquivo in enumerate(arquivos, 1):
            with arquivo.open("r", encoding="utf-8", errors="replace") as entrada:
                for linha in entrada:
                    if not linha.strip():
                        continue
                    total += 1
                    try:
                        objeto = json.loads(linha)
                        novo, _stats = _tratar_linha(objeto)
                        if novo is None:
                            sem_formato += 1
                        else:
                            validos += 1
                    except (json.JSONDecodeError, TypeError, ValueError):
                        invalidos += 1
                    _revisao_estado.update({"linhas": total, "validos": validos,
                                            "invalidos": invalidos, "sem_formato": sem_formato})
            _revisao_estado["percentual"] = round(indice * 100 / max(1, len(arquivos)), 1)
        passou = bool(arquivos and total and validos == total and invalidos == 0 and sem_formato == 0)
        relatorio = {"origem": str(origem), "arquivos": len(arquivos), "linhas": total,
                     "validos": validos, "invalidos": invalidos,
                     "sem_formato": sem_formato, "passou": passou,
                     "atualizado": datetime.now().isoformat()}
        caminho_relatorio = ROOT / "logs" / "revisao_tratado.json"
        caminho_relatorio.parent.mkdir(parents=True, exist_ok=True)
        caminho_relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
        if passou:
            from dashboard.services.qualidade import marcar
            carteira = marcar(origem.name, "ajuizado", relatorio=str(caminho_relatorio),
                              validos=validos, invalidos=invalidos)
            _atualizar(carteira=carteira, revisao=relatorio)
            _log("Revisão de qualidade aprovada; vacina ajuizado recebida.")
        else:
            _atualizar(revisao=relatorio)
        _revisao_estado.update({"rodando": False, "percentual": 100, "relatorio": relatorio})
    except Exception as exc:
        _revisao_estado.update({"rodando": False, "erro": str(exc)})


def revisar_tratado() -> dict[str, Any]:
    """Inicia a auditoria do resultado tratado em segundo plano."""
    _carregar_estado_persistido()
    with _lock:
        destino_registrado = str(_estado.get("destino") or "")
        if not destino_registrado:
            return {"ok": False, "erro": "Nenhum resultado tratado foi selecionado."}
        origem = Path(destino_registrado)
    if not origem.is_dir():
        return {"ok": False, "erro": "Resultado tratado não encontrado."}
    global _revisao_thread
    if _revisao_estado.get("rodando"):
        return {"ok": False, "erro": "A revisão já está em andamento."}
    _revisao_thread = threading.Thread(target=_executar_revisao, args=(origem,), daemon=True)
    _revisao_thread.start()
    return {"ok": True, "mensagem": "Revisão iniciada. Acompanhe o progresso no painel."}


def promover_tratado() -> dict[str, Any]:
    """Copia o resultado tratado para processed somente após ajuizamento."""
    _carregar_estado_persistido()
    with _lock:
        origem = Path(str(_estado.get("destino") or ""))
    if not origem.is_dir():
        return {"ok": False, "erro": "Resultado tratado não encontrado."}
    from dashboard.services.qualidade import status
    carteira_atual = status(origem.name)
    if "ajuizado" not in carteira_atual.get("etapas", {}):
        return {"ok": False, "erro": "Promoção bloqueada: faça a revisão de qualidade primeiro."}
    destino = ROOT / "dados" / "processed" / "jsonl" / origem.name
    arquivos = _arquivos_jsonl(origem)
    if not arquivos:
        return {"ok": False, "erro": "Não há JSONL tratado para promover."}
    destino.mkdir(parents=True, exist_ok=True)
    copiados = 0
    for arquivo in arquivos:
        relativo = arquivo.relative_to(origem)
        saida = destino / relativo
        saida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(arquivo, saida)
        copiados += 1
    from dashboard.services.qualidade import marcar
    carteira = marcar(origem.name, "promovido", destino=str(destino), arquivos=copiados)
    _atualizar(carteira=carteira, promovido=True)
    _log(f"Promoção concluída: {copiados} arquivo(s) copiados para processed/jsonl.")
    return {"ok": True, "mensagem": "Material promovido para treino.",
            "destino": str(destino), "arquivos": copiados, "carteira": carteira}


class _Pausado(Exception):
    pass


class _Parado(Exception):
    pass


def _verificar_controle() -> None:
    if _stop_event.is_set():
        raise _Parado()
    if _pause_event.is_set():
        raise _Pausado()


def _executar(origem: Path, destino: Path | None, simular: bool,
              inicio_arquivo: int = 0) -> None:
    indice_atual = inicio_arquivo
    try:
        arquivos = _arquivos_jsonl(origem)
        if not arquivos:
            raise ValueError("A pasta não contém arquivos JSONL.")
        total_linhas = total_ok = total_desc = total_corr = 0
        _atualizar(rodando=True, etapa="tratando", percentual=round(inicio_arquivo * 100 / len(arquivos), 1),
               origem=str(origem), destino=str(destino or ""), erro=None,
               arquivo_indice=inicio_arquivo, arquivos=len(arquivos), fim=None)
        if destino and not simular:
            destino.mkdir(parents=True, exist_ok=True)
        for indice_zero in range(inicio_arquivo, len(arquivos)):
            _verificar_controle()
            indice_atual = indice_zero
            indice = indice_zero + 1
            arquivo = arquivos[indice_zero]
            relativo = arquivo.relative_to(origem)
            saida = destino / relativo if destino else None
            if saida and not simular:
                saida.parent.mkdir(parents=True, exist_ok=True)
            parcial = saida.with_name(saida.name + ".part") if saida and not simular else None
            arquivo_linhas = 0
            with arquivo.open("r", encoding="utf-8", errors="replace") as entrada:
                saida_handle = parcial.open("w", encoding="utf-8") if parcial else None
                try:
                    for linha in entrada:
                        _verificar_controle()
                        if not linha.strip():
                            continue
                        total_linhas += 1
                        arquivo_linhas += 1
                        try:
                            objeto = json.loads(linha)
                            novo, stats = _tratar_linha(objeto)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            novo, stats = None, {"descartado": "JSON inválido", "removidos": 0, "mojibake": 0}
                        if novo is None:
                            total_desc += 1
                            continue
                        total_ok += 1
                        if stats.get("removidos") or stats.get("mojibake"):
                            total_corr += 1
                        if saida_handle:
                            saida_handle.write(json.dumps(novo, ensure_ascii=False) + "\n")
                finally:
                    if saida_handle:
                        saida_handle.close()
            if parcial:
                parcial.replace(saida)
            percentual = round(indice * 100 / len(arquivos), 1)
            _atualizar(percentual=percentual, arquivo_indice=indice, linhas=total_linhas, aprovados=total_ok,
                       descartados=total_desc, corrigidos=total_corr)
            _log(f"Arquivo {indice}/{len(arquivos)}: {relativo} ({arquivo_linhas} linhas)")
        mensagem = "Simulação concluída." if simular else "Tratamento concluído em dados/tratados."
        if not simular and destino:
            from dashboard.services.qualidade import marcar
            marcar(destino.name, "sanitizado", origem=str(origem))
            carteira = marcar(destino.name, "verificado_encoding", origem=str(origem))
            _atualizar(carteira=carteira)
            _log("Vacinas recebidas: sanitizado e encoding verificado.")
        _atualizar(rodando=False, etapa="concluido", percentual=100, mensagem=mensagem,
                   fim=datetime.now().isoformat())
        _log(mensagem)
    except _Pausado:
        _atualizar(rodando=False, etapa="pausado", mensagem="Tratamento pausado. Você pode retomar depois.",
                   arquivo_indice=indice_atual, fim=datetime.now().isoformat())
        _log("Tratamento pausado; os arquivos concluídos permanecem salvos.")
    except _Parado:
        _atualizar(rodando=False, etapa="parado", mensagem="Tratamento parado. A origem foi preservada.",
                   arquivo_indice=indice_atual, fim=datetime.now().isoformat())
        _log("Tratamento parado; a origem permanece intacta.")
    except Exception as exc:
        _atualizar(rodando=False, etapa="erro", erro=str(exc), mensagem=str(exc),
                   fim=datetime.now().isoformat())
        _log(f"Erro: {exc}")


def iniciar(origem: str, simular: bool = True, retomar: bool = False) -> dict[str, Any]:
    with _lock:
        if _estado.get("rodando"):
            return {"ok": False, "erro": "Já existe um tratamento em andamento."}
        # O dashboard pode ter sido recarregado depois que a thread morreu.
        # O estado em disco não pode bloquear um novo trabalho nesse caso.
        if not retomar:
            try:
                salvo = json.loads(ESTADO_PATH.read_text(encoding="utf-8")) if ESTADO_PATH.exists() else {}
                if isinstance(salvo, dict) and salvo.get("rodando"):
                    _estado.update(salvo)
                    _estado.update({"rodando": False, "etapa": "interrompido",
                                    "mensagem": "O trabalho anterior não está mais ativo. Você pode iniciar novamente.",
                                    "erro": "Estado antigo sem processo ativo."})
                    _persistir()
            except Exception:
                pass
        if retomar:
            origem = str(_estado.get("origem") or origem)
            simular = bool(_estado.get("simular", simular))
            inicio_arquivo = int(_estado.get("arquivo_indice", 0))
        else:
            inicio_arquivo = 0
    caminho = _resolver_origem(origem)
    nome = caminho.name + "_tratado"
    destino = DESTINO_BASE / nome
    _pause_event.clear()
    _stop_event.clear()
    _atualizar(origem=str(caminho), destino=str(destino), simular=simular,
               arquivo_indice=inicio_arquivo)
    thread = threading.Thread(target=_executar, args=(caminho, destino, simular, inicio_arquivo), daemon=True)
    thread.start()
    return {"ok": True, "mensagem": "Tratamento iniciado.", "simular": simular,
            "origem": str(caminho), "destino": str(destino)}


def pausar() -> dict[str, Any]:
    with _lock:
        if not _estado.get("rodando"):
            return {"ok": False, "erro": "Não há tratamento em andamento."}
    _pause_event.set()
    return {"ok": True, "mensagem": "Pausa solicitada."}


def parar() -> dict[str, Any]:
    with _lock:
        if not _estado.get("rodando"):
            return {"ok": False, "erro": "Não há tratamento em andamento."}
    _stop_event.set()
    return {"ok": True, "mensagem": "Parada solicitada."}


def progresso() -> dict[str, Any]:
    with _lock:
        # Nunca apresenta `rodando` do disco como ativo quando esta instância
        # do servidor não possui a thread correspondente.
        if ESTADO_PATH.exists() and not _estado.get("rodando"):
            try:
                salvo = json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
                if isinstance(salvo, dict):
                    if salvo.get("rodando"):
                        salvo.update({"rodando": False, "etapa": "interrompido",
                                      "mensagem": "O trabalho anterior não está mais ativo. Você pode iniciar novamente.",
                                      "erro": "Estado antigo sem processo ativo."})
                        ESTADO_PATH.write_text(json.dumps(salvo, ensure_ascii=False, indent=2), encoding="utf-8")
                    salvo["revisao_progresso"] = dict(_revisao_estado)
                    return dict(salvo)
            except Exception:
                pass
        resposta = dict(_estado)
        resposta["revisao_progresso"] = dict(_revisao_estado)
        return resposta
