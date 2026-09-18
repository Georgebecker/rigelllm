#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
executor_pipeline.py — PIPELINE DE ATIVIDADES do Executor (dashboard).

O que faz:
  Roda VÁRIAS atividades (sanitizar, limpeza_leve, verificar_encoding,
  diagnostico_chars) sobre VÁRIAS origens (pastas/arquivos), UMA POR VEZ,
  sem travar. Para cada item:
    - roda o script da atividade em subprocesso (saída em tempo real)
    - mostra percentual real (progresso persistido p/ o painel)
    - se der erro, PULA para o próximo item (não tranca)
    - contabiliza ok / erros / pulados
  Ao final, grava um MURAL de resultados (logs/mural_pipeline.json) que a
  página pode exibir e limpar.

Uso (chamado pelo executor):
  python executor_pipeline.py --comandos sanitizar,limpeza_leve \
      --origens "caminho1;caminho2;..." [--nome "Rótulo"] [--mural logs/mural_pipeline.json]
  --origens "todos"  → usa TODAS as origens pendentes descobertas
  --comandos "tudo"  → usa TODOS os comandos conhecidos (sanitizar → limpeza → verificar → diagnostico)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJETO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJETO_ROOT))

# Comandos conhecidos: nome → script e tipo de origem esperado
COMANDOS = {
    "sanitizar": {
        "desc": "🧼 Sanitizar PT-BR",
        "script": "scripts/gerar_sanitizados.py",
        "tipo": "pasta",
    },
    "limpeza_leve": {
        "desc": "🧹 Limpeza leve v2",
        "script": "limpeza_leve_rigel_v2.py",
        "tipo": "pasta",
    },
    "verificar_encoding": {
        "desc": "🔎 Verificar encoding",
        "script": "scripts/verificar_encoding_jsonl.py",
        "tipo": "arquivo",
    },
    "diagnostico_chars": {
        "desc": "📊 Diagnóstico caracteres",
        "script": "scripts/diagnostico_chars.py",
        "tipo": "arquivo",
    },
    "converter_parquet": {
        "desc": "📦 Converter jsonl→parquet",
        "script": "scripts/converter_jsonl_parquet.py",
        "tipo": "pasta",
    },
}

PROGRESSO_PATH = PROJETO_ROOT / "logs" / "pipeline_progresso.json"
MURAL_PATH = PROJETO_ROOT / "logs" / "mural_pipeline.json"
HISTORICO_SANITIZACAO = PROJETO_ROOT / "logs" / "sanitizacao_historico.json"


def _agora() -> str:
    return datetime.now().isoformat()


def _gravar_progresso(dados: dict) -> None:
    """Persiste o progresso real (o painel lê a barra de percentual)."""
    try:
        PROGRESSO_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROGRESSO_PATH.write_text(
            json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _carregar_historico_sanitizacao() -> list[dict]:
    try:
        if HISTORICO_SANITIZACAO.exists():
            d = json.loads(HISTORICO_SANITIZACAO.read_text(encoding="utf-8"))
            return d if isinstance(d, list) else []
    except Exception:
        pass
    return []


def _pasta_nao_sft(pasta) -> bool:
    """True se os .jsonl da pasta NÃO têm formato 'messages' (SFT) na amostra.
    O sanitizador SFT descartaria 100% desse material → pular. Amostra até 3
    arquivos / 2 linhas cada (barato). Cobre text, text aninhado, alpaca, etc.
    Conservador: se não conseguir ler nenhum exemplo, retorna False (não pula)."""
    achou_exemplo = False
    achou_messages = False
    try:
        import json as _json
        for arq in sorted(pasta.glob("*.jsonl"))[:3]:
            with open(arq, encoding="utf-8", errors="replace") as f:
                for _ in range(2):
                    linha = f.readline().strip()
                    if not linha:
                        break
                    try:
                        ex = _json.loads(linha)
                    except Exception:
                        continue
                    achou_exemplo = True
                    if any(k in ex for k in ("messages", "conversations", "chat")):
                        achou_messages = True
                        break
            if achou_messages:
                break
    except Exception:
        pass
    return achou_exemplo and not achou_messages


def _descobrir_origens(tipo: str, pular_texto: bool = False) -> list[Path]:
    """Descobre origens pendentes (com .jsonl) para o tipo esperado.

    sanitizar/limpeza → pastas com .jsonl (pendentes = ainda não sanitizadas)
    verificar/diagnostico → arquivos .jsonl individuais (limitado aos novos)
    pular_texto=True (sanitizar) → pula pastas de formato 'text' (pré-treino),
    que o SFT descartaria 100% (evita tempo perdido descartando tudo).
    """
    feitas = set()
    for h in _carregar_historico_sanitizacao():
        if h.get("completo"):
            feitas.add(os.path.abspath(h.get("origem", "")))

    alvos = [
        PROJETO_ROOT / "dados" / "processed" / "jsonl",
        PROJETO_ROOT / "dados" / "gerados" / "jsonl",
        PROJETO_ROOT / "dados" / "raw",
    ]
    arquivos: list[Path] = []
    for base in alvos:
        if not base.exists():
            continue
        try:
            arquivos.extend(base.glob("**/*.jsonl"))
        except Exception:
            continue
    try:
        arquivos.extend((PROJETO_ROOT / "dados").glob("*.jsonl"))
    except Exception:
        pass

    if tipo == "arquivo":
        # arquivos individuais: limita aos que não têm historico e não repetem
        vistos: set[str] = set()
        saida: list[Path] = []
        for p in arquivos:
            chave = str(p)
            if chave in vistos:
                continue
            vistos.add(chave)
            if len(saida) >= 80:
                break
            saida.append(p)
        return saida

    # tipo pasta: agrupa por pasta-pai, pendentes primeiro
    agrupadas: dict[str, Path] = {}
    for p in arquivos:
        agrupadas.setdefault(str(p.parent), p.parent)
    pastas = []
    for chave, pasta in agrupadas.items():
        if os.path.abspath(chave) in feitas:
            continue
        # 🔒 ANTI-RECURSÃO (correção 17/08): pastas *_sanitizado são SAÍDA da
        # sanitização, nunca origem. Sem este filtro, cada rodada do pipeline
        # "tudo" re-sanitizava a própria saída e criava pastas infinitas
        # (_sanitizado_sanitizado_sanitizado... = 462 pastas duplicadas).
        if "_sanitizado" in pasta.name:
            continue
        # 🔒 ANTI RE-SANITIZAÇÃO (18/08): se a origem JÁ TEM *_sanitizado
        # correspondente em processed/jsonl, pula (já foi tratada antes).
        # Sem isso, "sanitizar todos" reprocessava 98 origens já prontas.
        if (PROJETO_ROOT / "dados" / "processed" / "jsonl"
                / f"{pasta.name}_sanitizado").is_dir():
            continue
        # 18/08: pasta SEM formato 'messages' não serve para SFT — pular em
        # vez de processar e descartar 100% (ex.: dominguesm_restore, brwac,
        # ultra-alpaca). Decisão: limpeza leve p/ pré-treino ou arquivar.
        if pular_texto and _pasta_nao_sft(pasta):
            print(f"   [sanitizar] {pasta.name}: sem formato 'messages' "
                  "(pre-treino/alpaca) — pulado (limpeza leve ou arquivar)")
            continue
        pastas.append(pasta)
    pastas.sort(key=lambda x: x.name.lower())
    return pastas


def _montar_cmd(comando: str, origem: Path) -> list[str]:
    """Monta o comando do script da atividade para a origem."""
    info = COMANDOS[comando]
    script = PROJETO_ROOT / info["script"]
    cmd = [sys.executable, "-u", str(script)]
    if info["tipo"] == "arquivo":
        alvo = origem
        if origem.is_dir():
            if comando in ("verificar_encoding", "diagnostico_chars"):
                pass  # scripts universais aceitam a PASTA (txt/json/parquet)
            else:
                jsons = sorted(origem.glob("*.jsonl"))
                if not jsons:
                    return []
                alvo = jsons[0]
        cmd.append(str(alvo))
    else:
        if comando == "limpeza_leve":
            cmd += ["--origem", str(origem)]  # script exige --origem (não posicional)
        else:
            cmd.append(str(origem))
    if comando == "sanitizar":
        # staging POR ORIGEM (evita colisão de rigelsanitizadoNN entre origens
        # e permite promover+limpar automaticamente ao final de cada uma)
        staging = PROJETO_ROOT / "dados" / "sanitizados" / origem.name
        cmd += ["--saida-dir", str(staging)]
    return cmd


def _rodar_um(comando: str, origem: Path, saida: dict) -> None:
    """Roda UMA atividade sobre UMA origem. Nunca lança (erro → registra)."""
    item = {
        "comando": comando,
        "origem": str(origem),
        "inicio": _agora(),
        "fim": None,
        "status": "rodando",
        "exit_code": None,
        "erro": None,
        "linhas_tail": [],
    }
    saida["itens"].append(item)
    try:
        # 🔒 ANTI-RECURSÃO (correção 17/08): nunca re-sanitizar saída de
        # sanitização, mesmo quando a origem foi passada manualmente.
        if comando == "sanitizar" and "_sanitizado" in Path(origem).name:
            item["status"] = "pulado"
            item["erro"] = "Pasta é saída de sanitização (*_sanitizado) — pulando para não duplicar."
            print(f"⚠️ [PULADO] {comando}: {origem.name} — já é saída de sanitização")
            return
        cmd = _montar_cmd(comando, origem)
        if not cmd:
            item["status"] = "pulado"
            item["erro"] = "Sem arquivo .jsonl na pasta (pulando)."
            print(f"⚠️ [PULADO] {comando}: {origem.name} — sem .jsonl na raiz")
            return
        print(f"\n🚀 [{comando}] {origem.name} → {' '.join(cmd[-1:])}")
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen(
            cmd, cwd=str(PROJETO_ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
            env=env, bufsize=1)
        # Streama a saída em tempo real (o painel vê acontecendo)
        for linha in proc.stdout:
            linha = linha.rstrip("\n")
            if not linha.strip():
                continue
            print(f"    {linha}")
            item["linhas_tail"].append(linha)
            if len(item["linhas_tail"]) > 40:
                item["linhas_tail"] = item["linhas_tail"][-40:]
        codigo = proc.wait()
        item["exit_code"] = codigo
        item["fim"] = _agora()
        if codigo == 0:
            item["status"] = "ok"
            saida["ok"] += 1
            print(f"✅ [{comando}] {origem.name} OK")
        else:
            item["status"] = "erro"
            saida["erros"] += 1
            print(f"❌ [{comando}] {origem.name} código {codigo} — pulando p/ próximo")
    except Exception as e:
        item["status"] = "erro"
        item["erro"] = str(e)
        saida["erros"] += 1
        print(f"❌ [{comando}] {origem.name} EXCEÇÃO: {e} — pulando p/ próximo")


def _promover_sanitizados(origem: Path) -> dict:
    """Promove os limpos de dados/sanitizados/<origem> para
    processed/jsonl/<origem>_sanitizado/ e apaga o staging (HD liberado —
    regra do usuário: limpos viram treináveis e a pasta staging é limpa)."""
    staging = PROJETO_ROOT / "dados" / "sanitizados" / origem.name
    if not staging.exists():
        return {"ok": False, "motivo": f"sem staging {staging.name}"}
    gerados = sorted(staging.glob("rigelsanitizado*.jsonl"))
    if not gerados:
        return {"ok": False, "motivo": "nenhum rigelsanitizado gerado"}
    destino = PROJETO_ROOT / "dados" / "processed" / "jsonl" / (origem.name + "_sanitizado")
    destino.mkdir(parents=True, exist_ok=True)
    movidos = 0
    for f in gerados:
        try:
            shutil.move(str(f), str(destino / f.name))
            movidos += 1
        except Exception as e:
            print(f"    ⚠️ erro ao mover {f.name}: {e}")
    try:
        shutil.rmtree(staging, ignore_errors=True)
    except Exception:
        pass
    return {"ok": True, "movidos": movidos, "destino": str(destino)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline de atividades do Executor")
    ap.add_argument("--comandos", default="tudo",
                    help="Lista separada por vírgula, ou 'tudo'")
    ap.add_argument("--origens", default="todos",
                    help="Lista separada por ';' de caminhos, ou 'todos'")
    ap.add_argument("--nome", default="Pipeline")
    ap.add_argument("--mural", default=str(MURAL_PATH))
    args = ap.parse_args()

    # Comandos
    if args.comandos.strip().lower() == "tudo":
        comandos = list(COMANDOS.keys())
    else:
        comandos = [c.strip().lower() for c in args.comandos.split(",")
                    if c.strip() in COMANDOS]
    if not comandos:
        print("❌ Nenhum comando válido.")
        return 1

    # Origens
    if args.origens.strip().lower() == "todos":
        # Descobre por comando (pasta vs arquivo) — usa a lista da PRIMEIRA
        # atividade como base e re-descobre por tipo de cada uma
        origens_por_tipo: dict[str, list[Path]] = {}
    else:
        caminhos = [p.strip().strip('"').strip("'") for p in args.origens.split(";")]
        origens_por_tipo = {"_fixas": [Path(c) for c in caminhos if c]}

    saida = {
        "nome": args.nome,
        "inicio": _agora(),
        "fim": None,
        "comandos": comandos,
        "total_itens": 0,
        "ok": 0,
        "erros": 0,
        "pulados": 0,
        "itens": [],
        "mural_path": args.mural,
    }

    total_planejado = 0
    for comando in comandos:
        info = COMANDOS[comando]
        if "origens_por_tipo" in locals() and "_fixas" in origens_por_tipo:
            origens = origens_por_tipo["_fixas"]
        else:
            origens = origens_por_tipo.setdefault(
                info["tipo"], _descobrir_origens(
                    info["tipo"], pular_texto=(comando == "sanitizar")))
        for _ in origens:
            total_planejado += 1

    # Roda um por vez
    indice = 0
    for comando in comandos:
        info = COMANDOS[comando]
        if "origens_por_tipo" in locals() and "_fixas" in origens_por_tipo:
            origens = origens_por_tipo["_fixas"]
        else:
            origens = origens_por_tipo.setdefault(
                info["tipo"], _descobrir_origens(
                    info["tipo"], pular_texto=(comando == "sanitizar")))
        print(f"\n═══════════ COMANDO: {info['desc']} ({len(origens)} origem(s)) ═══════════")
        for origem in origens:
            indice += 1
            _rodar_um(comando, origem, saida)
            # 🚚 PROMOÇÃO AUTOMÁTICA: sanitizar → mover limpos p/ processed/jsonl
            # e limpar o staging (HD liberado — regra do usuário)
            if comando == "sanitizar" and saida["itens"] and \
                    saida["itens"][-1].get("status") == "ok":
                promo = _promover_sanitizados(origem)
                if promo.get("ok"):
                    print(f"   🚚 {promo['movidos']} limpos promovidos → "
                          f"{promo['destino']} (staging limpo)")
                else:
                    print(f"   ⚠️ promoção: {promo.get('motivo')}")
            pct = round(indice / max(1, total_planejado) * 100)
            _gravar_progresso({
                "pct": pct,
                "atual": f"{comando}: {origem.name}",
                "ok": saida["ok"],
                "erros": saida["erros"],
                "pulados": saida["pulados"],
                "total": total_planejado,
                "indice": indice,
                "timestamp": _agora(),
            })
            print(f"   ▸ progresso {pct}% ({indice}/{total_planejado}) | "
                  f"ok={saida['ok']} erros={saida['erros']}")

    saida["fim"] = _agora()
    saida["total_itens"] = len(saida["itens"])
    saida["pulados"] = sum(1 for i in saida["itens"] if i["status"] == "pulado")

    # Mural de resultados
    try:
        Path(args.mural).parent.mkdir(parents=True, exist_ok=True)
        mural = _carregar_mural(args.mural)
        mural.append({
            "id": f"pipeline-{int(time.time())}",
            "nome": args.nome,
            "inicio": saida["inicio"],
            "fim": saida["fim"],
            "comandos": comandos,
            "ok": saida["ok"],
            "erros": saida["erros"],
            "pulados": saida["pulados"],
            "total": saida["total_itens"],
            "itens": [{"comando": i["comando"], "origem": i["origem"],
                       "status": i["status"], "erro": i.get("erro"),
                       "exit_code": i.get("exit_code")} for i in saida["itens"]],
        })
        Path(args.mural).write_text(
            json.dumps(mural, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Falha ao gravar mural: {e}")

    print(f"\n🏁 PIPELINE '{args.nome}' CONCLUÍDO: "
          f"{saida['ok']} ok · {saida['erros']} erros · {saida['pulados']} pulados "
          f"(de {saida['total_itens']})")
    _gravar_progresso({"pct": 100, "fim": True, "timestamp": _agora(),
                       "ok": saida["ok"], "erros": saida["erros"]})
    return 0


def _carregar_mural(caminho: str | Path) -> list[dict]:
    try:
        p = Path(caminho)
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, list) else []
    except Exception:
        pass
    return []


if __name__ == "__main__":
    sys.exit(main())
