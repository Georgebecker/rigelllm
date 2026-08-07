#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
log_manager.py - Gerenciamento centralizado de logs
Versão: 1.0.0 | Data: 31/07/2026
Funcionalidades:
  - Logs em JSONL (logs/operacoes.log.json)
  - Análise de erros e resumo diário/semanal
  - Limpeza automática (retenção configurável)
  - Integração com rigel.py e dashboard
"""
import os
import sys
import json
import gzip
import shutil
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================
PROJETO_DIR = Path(__file__).resolve().parent
LOG_DIR = PROJETO_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
OLD_DIR = LOG_DIR / "old"
OLD_DIR.mkdir(exist_ok=True)

ARQUIVO_OPERACOES = LOG_DIR / "operacoes.log.json"
ARQUIVO_ERROS = LOG_DIR / "erros_verificador.log"
ARQUIVO_RESUMO = LOG_DIR / "resumo"

# Padrões de retenção (dias)
RETENCAO_PADRAO = 30
EXCLUSAO_APOS = 60

# ============================================================================
# OPERAÇÕES (JSONL)
# ============================================================================

def _gerar_id() -> str:
    return uuid.uuid4().hex[:12]

def registrar_operacao(
    tipo: str,
    status: str = "iniciado",
    detalhes: Optional[str] = None,
    checkpoint: Optional[str] = None,
    inicio: Optional[str] = None
) -> str:
    """
    Registra uma operação no log JSONL.
    Retorna o ID da operação.
    """
    oper_id = _gerar_id()
    agora = datetime.now().isoformat()
    entrada = {
        "id": oper_id,
        "tipo": tipo,
        "timestamp_inicio": inicio or agora,
        "timestamp_fim": agora if status in ("concluido", "erro") else None,
        "status": status,
        "detalhes": detalhes,
        "checkpoint": checkpoint
    }
    try:
        with open(ARQUIVO_OPERACOES, "a", encoding="utf-8") as f:
            f.write(json.dumps(entrada, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"❌ Erro ao registrar operação: {e}")
    return oper_id

def finalizar_operacao(oper_id: str, status: str = "concluido", detalhes: Optional[str] = None):
    """Atualiza o status de uma operação existente."""
    try:
        linhas = []
        encontrou = False
        if ARQUIVO_OPERACOES.exists():
            with open(ARQUIVO_OPERACOES, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if not linha:
                        continue
                    try:
                        entry = json.loads(linha)
                        if entry.get("id") == oper_id and not encontrou:
                            entry["timestamp_fim"] = datetime.now().isoformat()
                            entry["status"] = status
                            if detalhes:
                                entry["detalhes"] = detalhes
                            encontrou = True
                        linhas.append(json.dumps(entry, ensure_ascii=False))
                    except json.JSONDecodeError:
                        linhas.append(linha)  # mantém linha inválida
        if encontrou:
            with open(ARQUIVO_OPERACOES, "w", encoding="utf-8") as f:
                f.write("\n".join(linhas) + "\n")
    except Exception as e:
        print(f"❌ Erro ao finalizar operação: {e}")

def listar_operacoes(tipo: Optional[str] = None, limite: int = 50) -> List[Dict]:
    """Lista as últimas operações registradas."""
    resultados = []
    if not ARQUIVO_OPERACOES.exists():
        return []
    try:
        with open(ARQUIVO_OPERACOES, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    entry = json.loads(linha)
                    if not tipo or entry.get("tipo") == tipo:
                        resultados.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    return resultados[-limite:]

# ============================================================================
# ANÁLISE DE LOGS
# ============================================================================

def analisar_erros(ultimos_dias: int = 7) -> Dict[str, Any]:
    """Analisa logs de erro e retorna estatísticas."""
    erros = []
    if ARQUIVO_ERROS.exists():
        try:
            with open(ARQUIVO_ERROS, "r", encoding="utf-8") as f:
                for linha in f:
                    if "ERRO" in linha or "ERROR" in linha:
                        erros.append(linha.strip())
        except Exception:
            pass

    # Analisa também operações com erro
    operacoes_erro = [op for op in listar_operacoes(limite=500) if op.get("status") == "erro"]

    # Agrupa por tipo
    tipos_erro = {}
    for op in operacoes_erro:
        t = op.get("tipo", "desconhecido")
        tipos_erro[t] = tipos_erro.get(t, 0) + 1

    return {
        "total_erros_log": len(erros),
        "operacoes_erro": len(operacoes_erro),
        "erros_por_tipo": tipos_erro,
        "ultimo_erro": operacoes_erro[-1] if operacoes_erro else None
    }

def gerar_resumo(data_ref: Optional[str] = None) -> str:
    """Gera um resumo diário/semanal dos logs."""
    data = data_ref or datetime.now().strftime("%Y-%m-%d")
    analise = analisar_erros()

    linhas = []
    linhas.append(f"{'='*60}")
    linhas.append(f"   📊 RESUMO DE LOGS - {data}")
    linhas.append(f"{'='*60}")
    linhas.append(f"")
    linhas.append(f"📈 Operações com erro: {analise['operacoes_erro']}")
    linhas.append(f"⚠️  Total de erros no log: {analise['total_erros_log']}")
    linhas.append(f"")
    if analise['erros_por_tipo']:
        linhas.append(f"🔴 Erros por tipo:")
        for tipo, qtd in sorted(analise['erros_por_tipo'].items(), key=lambda x: -x[1]):
            linhas.append(f"   - {tipo}: {qtd}x")
    linhas.append(f"")
    if analise['ultimo_erro']:
        ult = analise['ultimo_erro']
        linhas.append(f"🕐 Último erro: {ult.get('timestamp_fim', '?')} - {ult.get('detalhes', '?')}")
    linhas.append(f"")
    linhas.append(f"{'='*60}")

    resumo = "\n".join(linhas)

    # Salva em arquivo
    caminho_resumo = ARQUIVO_RESUMO.parent / f"resumo_{data}.txt"
    try:
        caminho_resumo.write_text(resumo, encoding="utf-8")
    except Exception:
        pass

    return resumo

# ============================================================================
# LIMPEZA AUTOMÁTICA
# ============================================================================

def limpar_logs(dias_reter: int = RETENCAO_PADRAO, dias_excluir: int = EXCLUSAO_APOS, confirmar: bool = True):
    """
    Limpa logs antigos:
    - Move logs com mais de `dias_reter` para logs/old/ (compactados .gz)
    - Exclui logs com mais de `dias_excluir`
    """
    agora = datetime.now()
    movidos = 0
    excluidos = 0

    # Arquivos de log a gerenciar
    padroes = ["*.log", "*.json", "*.txt"]
    arquivos = []
    for padrao in padroes:
        arquivos.extend(LOG_DIR.glob(padrao))

    for arquivo in arquivos:
        if arquivo.parent == OLD_DIR:  # já está na pasta old
            continue
        if arquivo.name.startswith("resumo_"):  # não limpa resumos
            continue

        idade = agora - datetime.fromtimestamp(arquivo.stat().st_mtime)

        if idade.days > dias_excluir:
            if confirmar:
                print(f"   🗑️  Excluir {arquivo.name} ({idade.days}d)?")
                resp = input("      Confirmar (S/N/pular todos)? ").strip().lower()
                if resp == "pular todos":
                    confirmar = False
                    continue
                if resp != "s":
                    continue
            try:
                arquivo.unlink()
                excluidos += 1
                print(f"   ✅ Excluído: {arquivo.name}")
            except Exception as e:
                print(f"   ❌ Erro ao excluir {arquivo.name}: {e}")

        elif idade.days > dias_reter:
            destino = OLD_DIR / (arquivo.name + ".gz")
            try:
                with open(arquivo, "rb") as f_orig:
                    with gzip.open(destino, "wb") as f_gz:
                        shutil.copyfileobj(f_orig, f_gz)
                arquivo.unlink()
                movidos += 1
                print(f"   📦 Compactado: {arquivo.name} → {destino.name}")
            except Exception as e:
                print(f"   ❌ Erro ao compactar {arquivo.name}: {e}")

    print(f"\n📊 Resumo: {movidos} compactados, {excluidos} excluídos")
    return movidos, excluidos

# ============================================================================
# INTEGRAÇÃO COM RIGEL.PY
# ============================================================================

def verificar_erros_criticos() -> List[Dict]:
    """Retorna erros críticos recentes para exibir no dashboard."""
    operacoes = listar_operacoes(limite=200)
    return [op for op in operacoes if op.get("status") == "erro"][-10:]

# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gerenciador de Logs RigelSLM")
    parser.add_argument("--acao", choices=["resumo", "limpar", "analisar"], default="resumo")
    parser.add_argument("--dias", type=int, default=RETENCAO_PADRAO, help="Dias de retenção")
    parser.add_argument("--confirmar", action="store_true", help="Confirma limpeza sem perguntar")
    args = parser.parse_args()

    if args.acao == "resumo":
        print(gerar_resumo())
    elif args.acao == "analisar":
        analise = analisar_erros()
        print(json.dumps(analise, indent=2, ensure_ascii=False))
    elif args.acao == "limpar":
        limpar_logs(args.dias, confirmar=not args.confirmar)
