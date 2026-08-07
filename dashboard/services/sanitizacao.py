#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
sanitizacao.py — SANITIZAÇÃO CONTROLADA de datasets (PT-BR, somente linhas boas).

Roda o portão de qualidade (sanitizador_ptbr.py + gerar_sanitizados.py) em
segundo plano, com estado persistido, controle (iniciar/parar) e linha do
tempo — mesma arquitetura da explosão controlada (explosao_local.py).

O que faz, por exemplo:
  1. Lê exemplos JSONL (messages) de uma ORIGEM (pasta ou arquivo).
  2. Corrige mojibake, remove caracteres fora do ABNT2, descarta lixo.
  3. Filtra idioma: SOMENTE português brasileiro (exigir_ptbr=True).
  4. Deduplica por pergunta do usuário.
  5. Escreve em dados/sanitizados/rigelsanitizadoNN.jsonl (verificação pós-escrita).
  6. Persiste relatório em logs/sanitizacao_relatorio.json (o sistema consulta).

Estado:   estado/sanitizacao_estado.json    (andamento, eventos, motivos)
Controle: estado/sanitizacao_controle.json  (parar — lido pela thread)
Log:      logs/sanitizacao.log              (linha do tempo com data/hora)
Relatório: logs/sanitizacao_relatorio.json  (resultado persistido p/ consulta)
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
_ARQUIVO_ESTADO = _PASTA_ESTADO / "sanitizacao_estado.json"
_ARQUIVO_CONTROLE = _PASTA_ESTADO / "sanitizacao_controle.json"
_ARQUIVO_LOG = PROJETO_ROOT / "logs" / "sanitizacao.log"
_RELATORIO_LOG = PROJETO_ROOT / "logs" / "sanitizacao_relatorio.json"
_SAIDA_PADRAO = PROJETO_ROOT / "dados" / "sanitizados"

_lock = threading.Lock()
# Referência da thread de sanitização (para detectar thread morta após --reload)
_thread_atual: threading.Thread | None = None
_estado: dict = {
    "rodando": False,
    "status": "idle",        # idle | preparando | sanitizando | parado | concluido | erro | interrompido
    "origem": None,
    "saida_dir": str(_SAIDA_PADRAO),
    "exemplos_por_arquivo": 1000,
    "inicio": None,
    "fim": None,
    "total_lidas": 0,
    "total_ok": 0,
    "total_corrigidos": 0,
    "total_descartados": 0,
    "total_nao_pt": 0,
    "total_duplicados": 0,
    "total_gravados": 0,
    "arquivos_origem": 0,
    "arquivo_atual": None,
    "eventos": [],            # linha do tempo: {data, tipo, msg}
    "erro": None,
    "pid_inicio": None,       # PID do processo que iniciou a sanitização (p/ detectar reload)
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
    """Harmonia dashboard↔backend: se estado/sanitizacao_estado.json mudou FORA
    deste processo (ex.: sanitização/registro por CLI), recarrega do disco para
    o painel sempre refletir o que realmente aconteceu (regra de ouro)."""
    global _estado, _estado_mtime, _thread_atual
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
    # PREVENÇÃO (prever o imprevisível): se o estado diz "rodando" mas a thread
    # deste processo não existe (morreu no --reload) → marca como interrompido,
    # libera a trava. Nada fica preso para sempre.
    if _estado.get("rodando"):
        viva = _thread_atual is not None and _thread_atual.is_alive()
        # Thread viva só conta se o PID que iniciou é o mesmo deste processo
        pid_ok = _estado.get("pid_inicio") is None or _estado.get("pid_inicio") == os.getpid()
        if (not viva) and (not pid_ok or _thread_atual is None):
            with _lock:
                _estado["rodando"] = False
                _estado["status"] = "interrompido"
                _estado["erro"] = ("Sanitização interrompida (servidor reiniciou — "
                                   "thread de fundo morreu). Retome ou reinicie.")
                _estado["fim"] = datetime.now().isoformat()
                _persistir()
            _evento("interrompido", "Servidor reiniciou e interrompeu a sanitização em "
                                    "andamento. Estado liberado — pode reiniciar.")


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


def _deve_continuar():
    """Chamado pela thread de sanitização a cada arquivo — lê o controle."""
    c = _ler_controle()
    if c.get("acao") == "parar":
        _evento("parado", "Parada solicitada pelo usuário — interrompendo...")
        return False
    return True


def _trabalho(origem: str, saida_dir: str, exemplos_por_arquivo: int,
              max_arquivos: int | None) -> None:
    try:
        from scripts.gerar_sanitizados import (
            _validar_origem, _listar_jsonl, _verificar_espaco,
            _processar_arquivo, _gravar_relatorio,
            _EscritorStreaming, PREFIXO_SAIDA, EXTENSAO,
        )
        # Garante que scripts/ está no path (import acima já o faz via módulo)
    except Exception as e:
        # Fallback: import direto por caminho (caso 'scripts' não seja pacote)
        try:
            import importlib.util
            _script = PROJETO_ROOT / "scripts" / "gerar_sanitizados.py"
            _spec = importlib.util.spec_from_file_location("gerar_sanitizados_mod", _script)
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _validar_origem = _mod._validar_origem
            _listar_jsonl = _mod._listar_jsonl
            _verificar_espaco = _mod._verificar_espaco
            _processar_arquivo = _mod._processar_arquivo
            _gravar_relatorio = _mod._gravar_relatorio
            _EscritorStreaming = _mod._EscritorStreaming
            PREFIXO_SAIDA = _mod.PREFIXO_SAIDA
            EXTENSAO = _mod.EXTENSAO
        except Exception as e2:
            with _lock:
                _estado["status"] = "erro"
                _estado["erro"] = f"Falha ao carregar gerar_sanitizados: {e} / {e2}"
            _evento("erro", f"Falha ao carregar módulo de sanitização: {e2}")
            return

    try:
        _evento("inicio", f"Iniciando sanitização de '{origem}' → {saida_dir}")
        _evento("preparando", "Validando origem e verificando espaço...")

        # 1) Valida origem
        ok, msg = _validar_origem(origem)
        if not ok:
            with _lock:
                _estado["status"] = "erro"
                _estado["erro"] = msg
            _evento("erro", msg)
            return
        arqs, aviso, _total_real = _listar_jsonl(origem, max_arquivos)
        if aviso:
            _evento("aviso", aviso)
        if not arqs:
            with _lock:
                _estado["status"] = "erro"
                _estado["erro"] = "Nenhum .jsonl para processar."
            _evento("erro", "Nenhum .jsonl para processar.")
            return

        # 2) Espaço
        ok, msg = _verificar_espaco(saida_dir, len(arqs))
        if not ok:
            with _lock:
                _estado["status"] = "erro"
                _estado["erro"] = msg
            _evento("erro", msg)
            return
        _evento("aviso", msg)

        # 3) Estado de trabalho
        _escrever_controle(None)
        with _lock:
            _estado["status"] = "sanitizando"
            _estado["rodando"] = True
            _estado["arquivos_origem"] = len(arqs)
            _estado["total_lidas"] = 0
            _estado["total_ok"] = 0
            _estado["total_corrigidos"] = 0
            _estado["total_descartados"] = 0
            _estado["total_nao_pt"] = 0
            _estado["total_duplicados"] = 0
            _estado["total_gravados"] = 0
            _estado["arquivo_atual"] = None
            _persistir()

        # 4) Processa (usa as mesmas funções do CLI — conhecimento replicado)
        contadores = {"lidas": 0, "ok": 0, "corrigidos": 0, "descartados": 0,
                      "nao_pt": 0, "duplicados": 0, "sem_messages": 0,
                      "gravados_stream": 0, "arquivos_com_erro": []}
        vistos: set = set()
        escritor = _EscritorStreaming(saida_dir, exemplos_por_arquivo)
        for i, arq in enumerate(arqs, 1):
            if not _deve_continuar():
                break
            with _lock:
                _estado["arquivo_atual"] = os.path.basename(arq)
            _processar_arquivo(arq, vistos, contadores, exigir_ptbr=True,
                               escritor=escritor, total_arquivos=len(arqs), indice=i)
            with _lock:
                _estado["total_lidas"] = contadores["lidas"]
                _estado["total_ok"] = contadores["ok"]
                _estado["total_corrigidos"] = contadores["corrigidos"]
                _estado["total_descartados"] = contadores["descartados"]
                _estado["total_nao_pt"] = contadores["nao_pt"]
                _estado["total_duplicados"] = contadores["duplicados"]
            if i % 25 == 0 or i == len(arqs):
                _evento("progresso", f"{i}/{len(arqs)} arquivos | "
                                     f"ok={contadores['ok'] + contadores['corrigidos']} "
                                     f"descartados={contadores['descartados']}")

        # 5) Parado?
        c = _ler_controle()
        if c.get("acao") == "parar":
            _escrever_controle(None)
            with _lock:
                _estado["status"] = "parado"
            _evento("parado", "PARADO: o que já foi gravado em streaming fica salvo.")
            return

        # 6) Fecha o escritor (grava o lote final)
        gravados, erros = escritor.fechar()

        # 7) Relatório persistido (o sistema consulta)
        taxa_descarte = contadores["descartados"] / max(1, contadores["lidas"])
        relatorio = {
            "gerado_em": datetime.now().isoformat(),
            "origem": origem,
            "saida_dir": saida_dir,
            "contadores": {k: v for k, v in contadores.items() if k != "exemplos_ok"},
            "gravados": gravados,
            "erros_escrita": erros,
            "aviso_descarte_alto": taxa_descarte > 0.50,
            "taxa_descarte": round(taxa_descarte, 3),
        }
        _gravar_relatorio(relatorio)

        with _lock:
            _estado["total_gravados"] = gravados
            _estado["status"] = "concluido" if not erros else "erro"
            if erros:
                _estado["erro"] = "; ".join(erros[:5])
            else:
                _estado["erro"] = None
        if not erros:
            _evento("concluido", f"Sanitização concluída: {gravados} exemplos em "
                                 f"{saida_dir} (rigelsanitizadoNN.jsonl)")
        else:
            _evento("erro", f"Concluído com erros de escrita: {erros[:3]}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        with _lock:
            _estado["status"] = "erro"
            _estado["erro"] = str(e)
        _evento("erro", f"Falha na sanitização: {e}")
    finally:
        _escrever_controle(None)
        with _lock:
            _estado["rodando"] = False
            _estado["fim"] = datetime.now().isoformat()
            _persistir()


def iniciar(origem: str, saida_dir: str = "", exemplos_por_arquivo: int = 1000,
            max_arquivos: int | None = None) -> dict:
    """Inicia a sanitização em background. Retorna {ok, mensagem}."""
    global _thread_atual
    with _lock:
        if _estado.get("rodando"):
            return {"ok": False, "erro": "Já existe uma sanitização em andamento. "
                                         "Pare-a ou aguarde."}
    origem = (origem or "").strip().strip('"').strip("'")
    if not origem:
        return {"ok": False, "erro": "Informe a origem (pasta ou arquivo .jsonl)."}
    p = Path(origem)
    if not p.exists():
        return {"ok": False, "erro": f"Caminho não encontrado: {origem}"}
    saida_dir = saida_dir or str(_SAIDA_PADRAO)
    with _lock:
        _estado.update({
            "rodando": True, "status": "preparando", "origem": origem,
            "saida_dir": saida_dir, "exemplos_por_arquivo": exemplos_por_arquivo,
            "inicio": datetime.now().isoformat(), "fim": None,
            "total_lidas": 0, "total_ok": 0, "total_corrigidos": 0,
            "total_descartados": 0, "total_nao_pt": 0, "total_duplicados": 0,
            "total_gravados": 0, "arquivos_origem": 0, "arquivo_atual": None,
            "eventos": [], "erro": None,
            "pid_inicio": os.getpid(),  # p/ detectar thread morta após --reload
        })
        _persistir()
    _thread_atual = threading.Thread(target=_trabalho,
                                     args=(origem, saida_dir, exemplos_por_arquivo, max_arquivos),
                                     daemon=True)
    _thread_atual.start()
    return {"ok": True, "mensagem": "Sanitização iniciada em segundo plano."}


def parar() -> dict:
    _escrever_controle("parar")
    return {"ok": True, "mensagem": "Parada solicitada (para no próximo arquivo)."}


def limpar() -> dict:
    """Reseta o estado da sanitização para idle (esquecer o último resultado)."""
    _escrever_controle(None)
    with _lock:
        _estado.update({
            "rodando": False, "status": "idle", "origem": None,
            "saida_dir": str(_SAIDA_PADRAO), "inicio": None, "fim": None,
            "total_lidas": 0, "total_ok": 0, "total_corrigidos": 0,
            "total_descartados": 0, "total_nao_pt": 0, "total_duplicados": 0,
            "total_gravados": 0, "arquivos_origem": 0, "arquivo_atual": None,
            "eventos": [], "erro": None,
        })
        _persistir()
    return {"ok": True, "mensagem": "Estado de sanitização limpo (esquecido)."}


def registrar_resultado_externo(origem: str, saida_dir: str = "",
                                gravados: int = 0, descartados: int = 0,
                                nao_pt: int = 0) -> dict:
    """Registra no DASHBOARD o resultado de uma sanitização feita FORA do motor
    (ex.: CLI gerar_sanitizados.py) — REGRA DE OURO: o dashboard informa tudo.

    Atualiza estado/sanitizacao_estado.json para o painel mostrar o resultado
    sem precisar refazer o trabalho.
    """
    with _lock:
        _estado["rodando"] = False
        _estado["status"] = "concluido" if gravados > 0 else "erro"
        _estado["origem"] = origem or _estado.get("origem")
        _estado["saida_dir"] = saida_dir or _estado.get("saida_dir") or str(_SAIDA_PADRAO)
        _estado["total_gravados"] = gravados
        _estado["total_descartados"] = descartados
        _estado["total_nao_pt"] = nao_pt
        _estado["fim"] = datetime.now().isoformat()
        _persistir()
    _evento("registro_externo", f"Resultado externo registrado: {gravados} gravados, "
                                f"{descartados} descartados, {nao_pt} não-PT.")
    return {"ok": True, "mensagem": "Resultado externo registrado no dashboard."}
