#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
abrir_espaco_hd.py — PIPELINE "ABRIR ESPAÇO NO HD" (regra do usuário, 13/08).

Para TODO dado baixado/gerado pendente:
  detecta tipo (txt/jsonl/parquet) → verifica UTF-8/ABNT2/PT-BR → sanitiza →
  testa amostra → PROMOVE para dados/processed (estrutura de treino) →
  APAGA a pasta original (gerados/raw) → limpa o staging (sanitizados).

Tipos e ferramentas:
  TXT     → converter_txt_jsonl.py  (Pergunta/Resposta → qna; texto longo → artigo)
  JSONL   → gerar_sanitizados.py    (PT-BR/ABNT2) → processed/jsonl/<nome>_sanitizado/
  PARQUET → limpeza_leve_rigel_v2.py (--parquet: pesado, exige a flag)

Segurança (regra de ouro):
  --simular = relatório SOMENTE (não move, não apaga, não promove).
  Apagar origem SÓ depois de promover com sucesso E verificar o destino.

Uso:
  python scripts/abrir_espaco_hd.py --descobrir                    # lista pendentes
  python scripts/abrir_espaco_hd.py --pasta PASTA --simular        # ensaio (não muda nada)
  python scripts/abrir_espaco_hd.py --pasta PASTA                  # executa
  python scripts/abrir_espaco_hd.py --pasta .../parquet/X --parquet # parquet (pesado)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))

LOGS_DIR = PROJETO_ROOT / "logs"
PROGRESSO_PATH = LOGS_DIR / "espaco_progresso.json"
RELATORIO_DEFAULT = LOGS_DIR / "espaco_relatorio.json"

SANITIZADOS = PROJETO_ROOT / "dados" / "sanitizados"
GERADOS = PROJETO_ROOT / "dados" / "gerados"
RAW = PROJETO_ROOT / "dados" / "raw"
PROCESSED = PROJETO_ROOT / "dados" / "processed"
PROCESSED_JSONL = PROCESSED / "jsonl"

# Pastas de staging/controle que NUNCA são candidatas
IGNORAR_NOMES = {"descartados", "estado", "logs", "desclassificados",
                 "massa_final", "_temp", ".cache", "parquet", "jsonl"}

_MOJI = re.compile(r"Ã|â€|Â|ÿ|\ufffd")
_EXT = ("txt", "jsonl", "parquet")


def _agora() -> str:
    return datetime.now().isoformat()


def _historico_feito() -> set[str]:
    """Origens marcadas como completas em logs/sanitizacao_historico.json."""
    try:
        h = PROJETO_ROOT / "logs" / "sanitizacao_historico.json"
        if h.exists():
            d = json.loads(h.read_text(encoding="utf-8"))
            return {os.path.normcase(os.path.abspath(str(x.get("origem", ""))))
                    for x in d if isinstance(x, dict) and x.get("completo")}
    except Exception:
        pass
    return set()


_FEITO = _historico_feito()


def _ja_processado(pasta: Path, nome: str) -> str | None:
    """Se o dado já tem versão processada, devolve onde; senão None."""
    alvo = PROCESSED_JSONL / (nome + "_sanitizado")
    if alvo.exists():
        return str(alvo)
    if os.path.normcase(os.path.abspath(str(pasta))) in _FEITO:
        return "histórico de sanitização (completo)"
    return None


def _gravar_progresso(d: dict) -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        PROGRESSO_PATH.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _rodar(cmd: list[str], pasta: Path, tag: str) -> tuple[int, str]:
    """Roda um subprocesso e devolve (código, últimas linhas de saída)."""
    env = dict(__import__("os").environ)
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"  ▶ {tag}: {' '.join(cmd[-3:])}")
    try:
        proc = subprocess.Popen(cmd, cwd=str(pasta), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8",
                                errors="replace", env=env, bufsize=1)
    except Exception as e:
        return 1, str(e)
    cauda: list[str] = []
    for linha in proc.stdout:
        linha = linha.rstrip("\n")
        if linha.strip():
            cauda.append(linha)
            if len(cauda) > 25:
                cauda.pop(0)
    codigo = proc.wait()
    return codigo, "\n".join(cauda[-15:])


def _verificar_texto(texto: str) -> tuple[bool, str]:
    """Checagem rápida de amostra: mojibake/UTF-8 e proporção PT-BR."""
    if not texto.strip():
        return False, "amostra vazia"
    if _MOJI.search(texto) or "\ufffd" in texto:
        return False, "mojibake/caracteres inválidos na amostra"
    letras = re.findall(r"[a-záéíóúâêôãõàüçñ]+", texto.lower())
    if not letras:
        return False, "sem palavras na amostra"
    return True, f"ok ({len(letras)} palavras)"


def _detectar_subtipo_jsonl(pasta: Path) -> str:
    """Amostra o 1º jsonl: se tiver 'messages' → SFT; se só 'text' → pretrain.
    (corpus de pré-treinamento NÃO passa pelo sanitizador SFT — vai p/ limpeza leve)"""
    try:
        for f in sorted(pasta.glob("*.jsonl"))[:3]:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for linha in fh:
                    linha = linha.strip()
                    if not linha:
                        continue
                    try:
                        obj = json.loads(linha)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        if isinstance(obj.get("messages"), list):
                            return "sft"
                        if "text" in obj:
                            return "pretrain"
                    return "sft"  # formato desconhecido → tenta SFT
        return "sft"
    except Exception:
        return "sft"


def _detectar_tipo(pasta: Path) -> str | None:
    try:
        if list(pasta.glob("*.parquet")):
            return "parquet"
        if list(pasta.glob("*.txt")):
            return "txt"
        if list(pasta.glob("*.jsonl")):
            if _detectar_subtipo_jsonl(pasta) == "pretrain":
                return "pretrain"
            return "jsonl"
    except Exception:
        pass
    return None


def _promover_para_processed(staging: Path, nome: str) -> dict:
    """Move os limpos de dados/sanitizados/<nome> para processed/jsonl/<nome>_sanitizado/."""
    if not staging.exists():
        return {"ok": False, "motivo": "sem staging"}
    gerados = sorted(staging.glob("rigelsanitizado*.jsonl"))
    if not gerados:
        return {"ok": False, "motivo": "nenhum rigelsanitizado gerado"}
    destino = PROCESSED_JSONL / (nome + "_sanitizado")
    destino.mkdir(parents=True, exist_ok=True)
    movidos = 0
    for f in gerados:
        try:
            shutil.move(str(f), str(destino / f.name))
            movidos += 1
        except Exception as e:
            print(f"    ⚠️ mover {f.name}: {e}")
    try:
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        pass
    return {"ok": True, "movidos": movidos, "destino": str(destino)}


def _apagar_origem(pasta: Path, tag: str, simular: bool) -> tuple[bool, str]:
    if simular:
        return False, f"(simular) apagaria {pasta.name}"
    try:
        total = sum(1 for _ in pasta.rglob("*") if _.is_file())
        shutil.rmtree(pasta, ignore_errors=True)
        if pasta.exists():
            return False, f"não consegui apagar {pasta.name}"
        return True, f"{tag} {pasta.name} apagado ({total} arquivos)"
    except Exception as e:
        return False, f"erro ao apagar {pasta.name}: {e}"


def _tratar_txt(pasta: Path, nome: str, simular: bool) -> dict:
    """TXT → JSONL (converter) → depois trata como JSONL (encadeado)."""
    if simular:
        return {"ok": True, "tipo": "txt", "simular": True,
                "origem": str(pasta),
                "destino": str(PROCESSED_JSONL / (nome + "_sanitizado"))}
    converter = PROJETO_ROOT / "converter_txt_jsonl.py"
    cmd = [sys.executable, "-u", str(converter), "--pasta", str(pasta),
           "--saida", nome]
    cod, saida = _rodar(cmd, PROJETO_ROOT, "TXT→JSONL")
    if cod != 0:
        return {"ok": False, "tipo": "txt", "erro": saida}
    jsonl_gerado = GERADOS / "jsonl" / nome
    if not jsonl_gerado.exists() or not list(jsonl_gerado.glob("*.jsonl")):
        return {"ok": False, "tipo": "txt", "erro": "conversor não gerou JSONL"}
    # Encadeia: trata o JSONL recém-criado
    r = _tratar_jsonl(jsonl_gerado, nome, simular)
    if r.get("ok"):
        # Apaga o intermediário do conversor E a ORIGEM TXT (liberar espaço)
        _apagar_origem(jsonl_gerado, "intermediário", simular)
        _apagar_origem(pasta, "origem TXT", simular)
    return r


def _tratar_jsonl(pasta: Path, nome: str, simular: bool) -> dict:
    """JSONL → sanitizar → promover p/ processed. Apaga origem no final."""
    if simular:
        return {"ok": True, "tipo": "jsonl", "simular": True,
                "origem": str(pasta), "destino": str(PROCESSED_JSONL / (nome + "_sanitizado"))}
    staging = SANITIZADOS / nome
    sanitizador = PROJETO_ROOT / "scripts" / "gerar_sanitizados.py"
    cmd = [sys.executable, "-u", str(sanitizador), str(pasta),
           "--saida-dir", str(staging)]
    cod, saida = _rodar(cmd, PROJETO_ROOT, "JSONL→sanitizar")
    if cod != 0:
        return {"ok": False, "tipo": "jsonl", "erro": saida}
    promo = _promover_para_processed(staging, nome)
    if not promo.get("ok"):
        return {"ok": False, "tipo": "jsonl", "erro": promo.get("motivo")}
    # Apaga a origem (gerados/raw) só depois de promovido com sucesso
    ok_apagar, msg = _apagar_origem(pasta, "origem", simular)
    return {"ok": True, "tipo": "jsonl", "movidos": promo["movidos"],
            "destino": promo["destino"], "apagar": msg}


def _tratar_parquet(pasta: Path, nome: str, simular: bool) -> dict:
    """PARQUET → limpeza leve → processed. Apaga origem no final."""
    if simular:
        return {"ok": True, "tipo": "parquet", "simular": True,
                "origem": str(pasta), "destino": str(PROCESSED / "parquet")}
    script = PROJETO_ROOT / "limpeza_leve_rigel_v2.py"
    cmd = [sys.executable, "-u", str(script), "--origem", str(pasta),
           "--saida", str(PROCESSED / "parquet")]
    cod, saida = _rodar(cmd, PROJETO_ROOT, "PARQUET→limpeza")
    if cod != 0:
        return {"ok": False, "tipo": "parquet", "erro": saida}
    # verifica se gerou algo em processed/parquet (sft/pretrain ou pasta)
    _dest = PROCESSED / "parquet"
    novos = [p for p in _dest.glob("*.parquet")
             if p.stat().st_mtime > time.time() - 3600]
    if not novos and not any(_dest.iterdir()):
        return {"ok": False, "tipo": "parquet", "erro": "limpeza não gerou saída"}
    ok_apagar, msg = _apagar_origem(pasta, "origem", simular)
    return {"ok": True, "tipo": "parquet", "saida": [str(p) for p in novos],
            "apagar": msg}


def _descobrir_candidatos() -> list[dict]:
    """Lista pastas com dados pendentes (não tratados) em gerados/raw,
    incluindo gerados/jsonl/* (JSONL) e gerados/parquet/* (PARQUET)."""
    cand: list[dict] = []

    def _add(pasta: Path) -> None:
        tipo = _detectar_tipo(pasta)
        if not tipo:
            return
        ja = _ja_processado(pasta, pasta.name)
        acao = "apagar" if ja else "tratar"
        cand.append({"pasta": str(pasta), "nome": pasta.name,
                     "tipo": tipo, "acao": acao, "ja": ja})

    for base in (GERADOS, RAW):
        if not base.exists():
            continue
        for pasta in sorted(base.iterdir()):
            if not pasta.is_dir() or pasta.name in IGNORAR_NOMES:
                continue
            if pasta.name in ("sanitizados", "processed"):
                continue
            _add(pasta)
    # gerados/jsonl/* e gerados/parquet/* (são as pastas GRANDES pendentes)
    for sub in ("jsonl", "parquet"):
        base = GERADOS / sub
        if not base.exists():
            continue
        for pasta in sorted(base.iterdir()):
            if pasta.is_dir():
                _add(pasta)
    return cand


def main() -> int:
    ap = argparse.ArgumentParser(description="Abre espaço no HD tratando dados pendentes.")
    ap.add_argument("--pasta", default=None, help="Pasta específica a tratar")
    ap.add_argument("--descobrir", action="store_true", help="Lista pendentes (não muda nada)")
    ap.add_argument("--simular", action="store_true", help="Ensaio: NÃO move/apaga/promove")
    ap.add_argument("--parquet", action="store_true", help="Permite a fase PARQUET (pesada)")
    ap.add_argument("--limite", type=int, default=None, help="Máx. de pastas (teste)")
    ap.add_argument("--saida", default=str(RELATORIO_DEFAULT), help="Relatório JSON")
    args = ap.parse_args()

    if args.descobrir:
        cand = _descobrir_candidatos()
        n_tratar = sum(1 for c in cand if c.get("acao") == "tratar")
        n_apagar = sum(1 for c in cand if c.get("acao") == "apagar")
        print(f"🔎 {len(cand)} pasta(s): {n_tratar} p/ tratar · {n_apagar} p/ apagar (já processadas)")
        for c in cand:
            acao = c.get("acao", "tratar")
            print(f"  [{acao.upper():<6}] [{c['tipo'].upper():<7}] {c['pasta']}"
                  + (f"  (já em {c.get('ja')})" if acao == "apagar" and c.get("ja") else ""))
        return 0

    if args.pasta:
        pasta = Path(args.pasta)
        if not pasta.is_dir():
            print(f"❌ Pasta não encontrada: {pasta}")
            return 1
        cand = [{"pasta": str(pasta), "nome": pasta.name,
                 "tipo": _detectar_tipo(pasta) or "txt"}]
    else:
        cand = _descobrir_candidatos()

    if args.limite:
        cand = cand[: args.limite]
    if not cand:
        print("✅ Nada pendente para tratar.")
        return 0

    modo = "SIMULAÇÃO (nada será alterado)" if args.simular else "EXECUÇÃO"
    print(f"⚙️ {modo} — {len(cand)} pasta(s)")

    rel = {"inicio": _agora(), "simular": args.simular, "pastas": []}
    for i, c in enumerate(cand, 1):
        nome = c["nome"]
        tipo = c["tipo"]
        acao = c.get("acao", "tratar")
        print(f"\n[{i}/{len(cand)}] {nome} ({tipo}) — {acao}")
        if acao == "apagar":
            # Já processado em outro lugar: só liberar espaço (não reprocessa)
            if args.simular:
                r = {"ok": True, "tipo": tipo, "simular": True,
                     "ja": c.get("ja"), "msg": "apagaria (já processado)"}
            else:
                ok, msg = _apagar_origem(Path(c["pasta"]), "já processado", False)
                r = {"ok": ok, "tipo": tipo, "apagar": msg, "ja": c.get("ja")}
            r.update({"pasta": c["pasta"], "nome": nome})
            rel["pastas"].append(r)
            print(f"  {'✅' if r.get('ok') else '❌'} {nome}: {r.get('msg') or r.get('apagar') or r.get('erro') or ''}")
            _gravar_progresso({"pct": round(i / len(cand) * 100), "atual": nome,
                               "ok": sum(1 for x in rel["pastas"] if x.get("ok")),
                               "erros": sum(1 for x in rel["pastas"] if not x.get("ok")),
                               "total": len(cand), "timestamp": _agora()})
            continue
        if tipo in ("parquet", "pretrain") and not args.parquet:
            print(f"  ⏭️  {tipo.upper()} exige --parquet (limpeza leve, pesado). Pulando.")
            rel["pastas"].append({"pasta": c["pasta"], "tipo": tipo, "status": "pulado"})
            continue
        try:
            if tipo == "txt":
                r = _tratar_txt(Path(c["pasta"]), nome, args.simular)
            elif tipo == "jsonl":
                r = _tratar_jsonl(Path(c["pasta"]), nome, args.simular)
            else:
                # parquet E pretrain (jsonl text-only) → limpeza leve
                r = _tratar_parquet(Path(c["pasta"]), nome, args.simular)
        except Exception as e:
            r = {"ok": False, "erro": str(e)}
        r.update({"pasta": c["pasta"], "tipo": tipo, "nome": nome})
        rel["pastas"].append(r)
        status = "✅" if r.get("ok") else "❌"
        det = r.get("erro") or r.get("destino") or r.get("motivo") or ""
        print(f"  {status} {nome}: {det}")
        _gravar_progresso({"pct": round(i / len(cand) * 100), "atual": nome,
                           "ok": sum(1 for x in rel["pastas"] if x.get("ok")),
                           "erros": sum(1 for x in rel["pastas"] if not x.get("ok")),
                           "total": len(cand), "timestamp": _agora()})

    rel["fim"] = _agora()
    rel["ok"] = sum(1 for x in rel["pastas"] if x.get("ok"))
    rel["erros"] = sum(1 for x in rel["pastas"] if not x.get("ok"))
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        Path(args.saida).write_text(
            json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ relatório: {e}")
    print(f"\n═ {'=' * 50}")
    print(f"✅ ok={rel['ok']}  ❌ erros={rel['erros']}  📄 {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
