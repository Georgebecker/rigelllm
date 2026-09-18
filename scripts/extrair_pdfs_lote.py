#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
extrair_pdfs_lote.py — Extração de PDF em lote como PROCESSO INDEPENDENTE.

Por que existe: a extração rodava numa thread do uvicorn e MORRIA quando o
servidor recarregava (--reload). Agora roda como subprocesso separado — mesmo
que o dashboard reinicie, o trabalho continua e o log/percentual seguem sendo
gravados no mesmo arquivo de estado (estado/tratamento_estado.json).

Fluxo por PDF: PDF → TXT (extrair_livro_pdf.py) → JSONL (livro_para_jsonl.py)
→ promoção p/ processed → apaga o PDF (vira TXT+JSONL, libera HD).

Uso: python scripts/extrair_pdfs_lote.py --pasta <nome>
"""
import argparse
import atexit
import json
import os
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJETO_ROOT / "dados" / "raw"
_ESTADO_ARQ = PROJETO_ROOT / "estado" / "tratamento_estado.json"
_LOG_ARQ = PROJETO_ROOT / "logs" / "extrair_pdfs_lote.log"
_lock = threading.Lock()

# Garante que dá para importar os módulos do dashboard (qualidade, treino_local)
if str(PROJETO_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJETO_ROOT))


def _persistir(estado: dict) -> None:
    try:
        _ESTADO_ARQ.parent.mkdir(parents=True, exist_ok=True)
        _ESTADO_ARQ.write_text(json.dumps(estado, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass


def _atualizar(estado: dict, **kwargs) -> None:
    with _lock:
        estado.update(kwargs)
        _persistir(estado)


def _log(estado: dict, msg: str) -> None:
    """Anexa uma linha ao log EM TEMPO REAL (regra de ouro: ver acontecendo)."""
    linha = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with _lock:
        estado.setdefault("log", []).append(linha)
        estado["log"] = estado["log"][-400:]
        _persistir(estado)


def _log_arquivo(msg: str) -> None:
    """Grava em logs/extrair_pdfs_lote.log — QUALQUER morte deixa rastro."""
    try:
        _LOG_ARQ.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_ARQ, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", required=True, help="Pasta em dados/raw/ com os PDFs (ex.: livros)")
    args = ap.parse_args()
    nome = args.pasta

    # Carrega o estado atual (para preservar log anterior, se houver)
    estado = {"rodando": False, "etapa": "idle", "mensagem": "", "percentual": None,
              "fila": [], "atual": None, "concluidos": [], "log": [],
              "inicio": None, "fim": None, "erro": None, "pid": None}
    if _ESTADO_ARQ.exists():
        try:
            estado.update(json.loads(_ESTADO_ARQ.read_text(encoding="utf-8")))
        except Exception:
            pass

    _log_arquivo(f"=== INÍCIO extração pasta '{nome}' | pid={os.getpid()} ===")

    # 🔒 Rede de segurança: se o processo morrer por qualquer motivo, o estado
    # nunca fica "rodando" para sempre — vira interrompido (o dashboard mostra
    # o botão Continuar).
    def _finalizar_se_morto():
        try:
            if estado.get("rodando"):
                with _lock:
                    estado["rodando"] = False
                    estado["etapa"] = "interrompido"
                    estado.setdefault("log", []).append(
                        f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Extração caiu. Use 'Continuar'.")
                    _persistir(estado)
        except Exception:
            pass
    atexit.register(_finalizar_se_morto)

    origem = RAW / nome
    if not origem.is_dir():
        _log(estado, f"❌ Pasta '{nome}' não encontrada em dados/raw/.")
        _atualizar(estado, etapa="erro", rodando=False, fim=datetime.now().isoformat())
        return 1
    pdfs = sorted([p for p in origem.rglob("*.pdf") if p.is_file()])
    if not pdfs:
        _log(estado, f"⚠️ Não há PDFs em '{nome}'.")
        _atualizar(estado, etapa="concluido", percentual=100,
                   mensagem="Nenhum PDF para extrair.", rodando=False,
                   fim=datetime.now().isoformat())
        return 0

    script_extrair = PROJETO_ROOT / "scripts" / "extrair_livro_pdf.py"
    script_jsonl = PROJETO_ROOT / "scripts" / "livro_para_jsonl.py"
    if not script_extrair.exists() or not script_jsonl.exists():
        _log(estado, "❌ Scripts de extração não encontrados.")
        _atualizar(estado, etapa="erro", rodando=False, fim=datetime.now().isoformat())
        return 1

    env_py = dict(os.environ)
    env_py["PYTHONIOENCODING"] = "utf-8"

    _atualizar(estado, rodando=True, etapa="extraindo", percentual=0,
               mensagem=f"Extraindo {len(pdfs)} PDF(s) de '{nome}'...",
               fila=[nome], atual=nome, concluidos=[], log=[],
               inicio=datetime.now().isoformat(), fim=None, erro=None, pid=os.getpid())
    _log(estado, f"🚀 Extração de {len(pdfs)} PDF(s) de '{nome}' iniciada")

    def _rodar_ao_vivo(cmd: list, label: str) -> tuple:
        """Roda o subprocesso STREAMANDO a saída para o log (nada escondido)."""
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                env=env_py, bufsize=1)
        saida = []
        if proc.stdout:
            for linha in proc.stdout:
                linha = linha.rstrip()
                if linha.strip():
                    saida.append(linha)
                    _log(estado, f"{label}: {linha.strip()[:160]}")
        proc.wait()
        return proc.returncode, "\n".join(saida)

    concluidos = []
    ok_total = 0
    try:
        for i, pdf in enumerate(pdfs, 1):
            base = (i - 1) * 100 / len(pdfs)
            span = 100 / len(pdfs)
            try:
                _atualizar(estado, atual=pdf.name,
                           percentual=int(base + span * 0.05),
                           mensagem=f"[{i}/{len(pdfs)}] ✨ {pdf.name} — lendo PDF...")
                _log(estado, f"📄 [{i}/{len(pdfs)}] {pdf.name} ({pdf.stat().st_size/1e6:.1f} MB)")
                txt_saida = PROJETO_ROOT / "dados" / "gerados" / "txt_livros" / (pdf.stem + ".txt")
                jsonl_saida = PROJETO_ROOT / "dados" / "gerados" / "jsonl" / "livros" / (pdf.stem + ".jsonl")
                # ⏭️ Já extraído antes? Pula (Continuar é rápido, não re-extrai)
                if txt_saida.exists() and jsonl_saida.exists() and \
                   txt_saida.stat().st_size > 0 and jsonl_saida.stat().st_size > 0:
                    ok_total += 1
                    concluidos.append({"nome": pdf.name, "ok": True,
                                       "detalhe": "já tinha TXT + JSONL (pulado)"})
                    _log(estado, "   ⏭️ Já tinha TXT + JSONL — pulando (não re-extrai)")
                    _atualizar(estado, concluidos=list(concluidos),
                               percentual=int(base + span))
                    continue
                _atualizar(estado, mensagem=f"[{i}/{len(pdfs)}] {pdf.name} — extraindo texto...",
                           percentual=int(base + span * 0.15))
                _log(estado, "   ⏳ extraindo texto (pdfplumber)...")
                cod1, saida1 = _rodar_ao_vivo(
                    [sys.executable, str(script_extrair), "--pdf", str(pdf),
                     "--saida", str(txt_saida)], "   extração")
                if cod1 != 0:
                    concluidos.append({"nome": pdf.name, "ok": False,
                                       "detalhe": f"extração falhou: {saida1[-160:]}"})
                    _log(estado, f"   ❌ extração falhou: {saida1[-120:]}")
                    _atualizar(estado, concluidos=list(concluidos),
                               percentual=int(base + span))
                    continue
                _atualizar(estado, mensagem=f"[{i}/{len(pdfs)}] {pdf.name} — convertendo p/ JSONL...",
                           percentual=int(base + span * 0.55))
                _log(estado, "   ⏳ convertendo TXT → JSONL...")
                cod2, saida2 = _rodar_ao_vivo(
                    [sys.executable, str(script_jsonl), "--txt", str(txt_saida),
                     "--saida", str(jsonl_saida)], "   conversão")
                ok2 = cod2 == 0
                if ok2:
                    try:
                        from dashboard.services.qualidade import marcar as _mq
                        _mq("livros", "sanitizado", fonte="extração_pdf")
                        _mq("livros", "verificado_encoding", fonte="extração_pdf")
                    except Exception:
                        pass
                    ok_total += 1
                    _log(estado, "   ✅ TXT + JSONL gerados")
                else:
                    _log(estado, f"   ❌ conversão falhou: {saida2[-120:]}")
                concluidos.append({"nome": pdf.name, "ok": ok2,
                                   "detalhe": ("gerou TXT + JSONL" if ok2
                                               else f"conversão falhou: {saida2[-120:]}")})
                _atualizar(estado, concluidos=list(concluidos),
                           percentual=int(base + span))
            except BaseException as e:
                _log_arquivo(f"ERRO no PDF {pdf.name}:\n{traceback.format_exc()}")
                concluidos.append({"nome": pdf.name, "ok": False,
                                   "detalhe": f"{type(e).__name__}: {str(e)[:150]}"})
                _log(estado, f"   ❌ erro: {type(e).__name__}: {str(e)[:150]}")

        # 🚀 Promoção automática p/ processed (valida + faz merge — atualiza o
        # acervo: se já havia livros lá, soma/atualiza os novos)
        promovido = None
        if ok_total > 0:
            _log(estado, "🚀 Promovendo para processed (validando + merge)...")
            try:
                from dashboard.services import treino_local as _tl
                promovido = _tl.promover_para_processed("livros",
                                                        remover_invalidos=False)
            except Exception as e:
                promovido = {"ok": False, "erro": str(e)}

        msg = f"✅ {ok_total}/{len(pdfs)} PDF(s) extraídos" + \
              (f" · promovidos: {promovido.get('validos', 0)}"
               if promovido and promovido.get("ok") else "") + \
              (f" ⚠️ {promovido.get('erro')}"
               if promovido and not promovido.get("ok") else "")
        _log(estado, "🏁 " + msg)
        _atualizar(estado, etapa="concluido", percentual=100, mensagem=msg,
                   concluidos=list(concluidos), fim=datetime.now().isoformat())

        # apaga o PDF extraído (vira txt+jsonl, libera HD) — regra do usuário
        for pdf in pdfs:
            try:
                pdf.unlink()
                _log(estado, f"🗑️ PDF apagado (vira TXT+JSONL): {pdf.name}")
            except Exception:
                pass
        _atualizar(estado, rodando=False, pid=None)
        return 0
    except BaseException as e:
        _log_arquivo(f"ERRO GERAL:\n{traceback.format_exc()}")
        _log(estado, f"❌ erro geral: {type(e).__name__}: {str(e)[:200]}")
        _atualizar(estado, etapa="erro", mensagem=str(e), erro=str(e), rodando=False,
                   pid=None, fim=datetime.now().isoformat())
        return 1


if __name__ == "__main__":
    sys.exit(main())
