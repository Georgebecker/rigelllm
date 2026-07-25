#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
main.py - Ponto de entrada principal do gerador de dados sintéticos RigelSLM.
"""
import argparse
import sys
import time
import random
from datetime import datetime
from typing import Optional

from config import (
    PASTA_DADOS_CURTOS,
    PASTA_DADOS_LONGOS,
    PASTA_DESCARTES,
    PASTA_LOGS,
    ARQUIVO_LOG,
    ARQUIVO_HISTORICO,
    ARQUIVO_METADADOS,
    ARQUIVO_HISTORICO_TOPICOS,
    ARQUIVO_TOPICOS_EXTERNOS,
    MODEL_NAME,
    MAX_COST_USD,
    DELAY_SECONDS,
    client,
    atualizar_config,
    verificar_limite,
    carregar_gastos,
)
from state import StateManager
from generation import gerar_lote, listar_temas
from validation import listar_arquivos_invalidos, limpar_arquivos_invalidos
from utils import (
    salvar_metadados,
    carregar_json,
    salvar_json,
    salvar_texto,
    hash_texto,
    exibir_status_topicos,
)
from categories import SAUDACOES


# ============================================================================
# COMANDOS AUXILIARES
# ============================================================================
def cmd_ver_logs() -> None:
    """Exibe o histórico de execuções."""
    historico = carregar_json(ARQUIVO_HISTORICO, [])
    if not historico:
        print("📭 Nenhum histórico encontrado.")
        return
    print(f"\n📋 Histórico de execuções ({len(historico)} registros):\n")
    for i, entry in enumerate(historico, 1):
        print(
            f"[{i}] {entry['data_hora']} | {entry['modelo']} | "
            f"Gerados: {entry['gerados']} | Gasto: ${entry['gasto_execucao']:.4f} | "
            f"Desc.salvos: {entry.get('descartados_salvos', 0)}"
        )
    print(f"\n📄 Log completo em: {ARQUIVO_LOG}")
    print(f"📄 Histórico JSON em: {ARQUIVO_HISTORICO}")


def cmd_estatisticas(state: StateManager) -> None:
    """Exibe estatísticas resumidas."""
    dados = carregar_json(ARQUIVO_HISTORICO, [])
    if not dados:
        print("📭 Sem dados para estatísticas ainda.")
        return

    total_execucoes = len(dados)
    soma_gerados = sum(item.get("gerados", 0) for item in dados)
    soma_descartados = sum(item.get("descartados", 0) for item in dados)
    soma_gasto = sum(item.get("gasto_execucao", 0.0) for item in dados)

    print("\n📊 ESTATÍSTICAS")
    print(f"   Execuções: {total_execucoes}")
    print(f"   Itens gerados: {soma_gerados}")
    print(f"   Itens descartados: {soma_descartados}")
    print(f"   Gasto total: ${soma_gasto:.4f}")
    print(f"   Gasto atual (sessão): ${state.get_total_gasto():.4f}")
    print(f"   Categorias mais usadas: {state.get_categorias_mais_usadas(5)}")


def cmd_validar(dry_run: bool) -> None:
    """Valida arquivos existentes."""
    print("🔍 Verificando arquivos existentes...")
    limpar_arquivos_invalidos(PASTA_DADOS_CURTOS, dry_run=dry_run)
    limpar_arquivos_invalidos(PASTA_DADOS_LONGOS, dry_run=dry_run)


def cmd_status_topicos() -> None:
    """Exibe o status dos tópicos externos."""
    exibir_status_topicos(ARQUIVO_TOPICOS_EXTERNOS, ARQUIVO_HISTORICO_TOPICOS)


# ============================================================================
# MENU INTERATIVO
# ============================================================================
def menu_interativo() -> None:
    """Exibe o menu interativo para escolha de tipo e parâmetros."""
    print("\n" + "=" * 70)
    print("🤖 GERADOR DE DADOS SINTÉTICOS - RigelSLM (v2.0)")
    print("   Desenvolvido por George Herman Becker")
    print("=" * 70)
    print("\nEscolha o tipo de dado a gerar:")
    print("  1. Dicionário (pergunta + resposta curta)")
    print("  2. Pergunta e Resposta (resposta longa e estruturada)")
    print("  3. Iteração (diálogo de 4-6 turnos)")
    print("  4. Artigo (texto corrido estruturado 400-800 palavras)")
    print("  5. Conto (história curta 300-600 palavras)")
    print("  6. Diálogo Profundo (8-12 turnos)")
    print("  7. Explicação (texto explicativo detalhado 300-500 palavras)")
    print("  8. Resumo (síntese concisa 150-300 palavras)")
    print("  9. Conversa (diálogo entre duas pessoas)")
    print(" 10. Saudação (prontas, sem custo)")
    print(" 11. Modo Automático (balanceia tipos automaticamente)")
    print(" 12. Sair")
    print(" 13. Status dos tópicos externos")

    opcao = input("\nDigite o número da opção (1-13): ").strip()
    if opcao == "13":
        cmd_status_topicos()
        return

    if opcao not in [str(i) for i in range(1, 13)]:
        print("❌ Opção inválida. Tente novamente.")
        return menu_interativo()

    if opcao == "12":
        print("👋 Saindo...")
        sys.exit(0)

    tipos = [
        "dicionario", "pergunta_resposta", "iteracao", "artigo",
        "conto", "dialogo_profundo", "explicacao", "resumo",
        "conversa", "saudacao"
    ]

    if opcao == "11":
        tipo = "auto"
    else:
        tipo = tipos[int(opcao) - 1]

    try:
        quantidade = int(input("Quantos itens deseja gerar? (padrão 500): ") or "500")
    except ValueError:
        print("❌ Valor inválido. Usando 500.")
        quantidade = 500

    if quantidade <= 0:
        print("❌ Quantidade deve ser positiva. Usando 500.")
        quantidade = 500

    # Estima custo
    custo_por_item = {
        "dicionario": 0.0001,
        "pergunta_resposta": 0.0008,
        "iteracao": 0.0005,
        "artigo": 0.0010,
        "conto": 0.0010,
        "dialogo_profundo": 0.0012,
        "explicacao": 0.0010,
        "resumo": 0.0006,
        "conversa": 0.0007,
        "saudacao": 0.0,
    }
    if tipo != "auto":
        custo_estimado = custo_por_item.get(tipo, 0.0005) * quantidade
        print(f"\n💰 Custo estimado: ${custo_estimado:.4f} USD")
    else:
        custo_estimado = (
            (0.0008 * 0.2 + 0.0010 * 0.15 + 0.0012 * 0.15 +
             0.0010 * 0.15 + 0.0006 * 0.1 + 0.0007 * 0.1 +
             0.0001 * 0.1 + 0.0010 * 0.05) * quantidade
        )
        print(f"\n💰 Custo estimado (modo automático): ${custo_estimado:.4f} USD")

    dados_gastos = carregar_gastos()
    gasto_atual = dados_gastos.get("total_gasto", 0.0)
    if gasto_atual + custo_estimado > MAX_COST_USD:
        print(f"⚠️ Atenção: seu limite global é ${MAX_COST_USD:.2f} e você já gastou ${gasto_atual:.4f}.")
        print(f"   Esta execução custaria ${custo_estimado:.4f}, ultrapassando o limite.")
        continuar = input("   Deseja continuar mesmo assim? (s/N): ").strip().lower()
        if continuar != 's':
            print("❌ Operação cancelada.")
            return

    confirm = input("\nContinuar com a geração? (s/N): ").strip().lower()
    if confirm != 's':
        print("❌ Operação cancelada.")
        return

    class Args:
        pass

    args = Args()
    args.tipo = tipo
    args.quantidade = quantidade
    args.prefixo = "dialogo"
    args.delay = DELAY_SECONDS
    args.limite = MAX_COST_USD
    args.tema = None
    args.listar_temas = False
    args.limpar_invalidos = False
    args.validar = False
    args.ver_logs = False
    args.estatisticas = False
    args.status_topicos = False

    executar_geracao(args)


# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================
def executar_geracao(args) -> None:
    """Função principal que orquestra a geração conforme os argumentos."""
    global MAX_COST_USD, DELAY_SECONDS

    if hasattr(args, 'limite') and args.limite is not None:
        MAX_COST_USD = args.limite
    if hasattr(args, 'delay') and args.delay is not None:
        DELAY_SECONDS = args.delay

    state = StateManager()

    # Comandos auxiliares
    if hasattr(args, 'ver_logs') and args.ver_logs:
        cmd_ver_logs()
        return
    if hasattr(args, 'estatisticas') and args.estatisticas:
        cmd_estatisticas(state)
        return
    if hasattr(args, 'validar') and args.validar:
        cmd_validar(dry_run=True)
        return
    if hasattr(args, 'limpar_invalidos') and args.limpar_invalidos:
        cmd_validar(dry_run=False)
        return
    if hasattr(args, 'listar_temas') and args.listar_temas:
        listar_temas()
        return
    if hasattr(args, 'status_topicos') and args.status_topicos:
        cmd_status_topicos()
        return

    if args.tipo == "auto":
        executar_auto(state, args)
    elif args.tipo == "saudacao":
        executar_saudacao(state, args)
    else:
        executar_tipo_especifico(state, args)


# ============================================================================
# MODO AUTO
# ============================================================================
def executar_auto(state: StateManager, args) -> None:
    """Executa o modo automático com distribuição balanceada."""
    # Exibe status dos tópicos antes de começar
    cmd_status_topicos()

    print("=" * 70)
    print("🤖 GERADOR DE DADOS SINTÉTICOS - MODO AUTOMÁTICO (v2.0)")
    print(f"   Modelo: {MODEL_NAME} | Limite: ${MAX_COST_USD:.2f} | Delay: {DELAY_SECONDS}s")
    print(f"   Alvo: {args.quantidade} itens")
    print("=" * 70)

    if not verificar_limite():
        print("⚠️ Limite já foi atingido.")
        return

    distribuicao = {
        "pergunta_resposta": 0.20,
        "dialogo_profundo": 0.20,
        "artigo": 0.15,
        "explicacao": 0.15,
        "conto": 0.10,
        "dicionario": 0.10,
        "resumo": 0.05,
        "conversa": 0.05,
    }

    quantidades = {}
    resto = args.quantidade
    for tipo, prop in distribuicao.items():
        qtd = int(args.quantidade * prop)
        quantidades[tipo] = qtd
        resto -= qtd

    for tipo in ["dialogo_profundo", "pergunta_resposta", "artigo", "explicacao"]:
        if resto <= 0:
            break
        quantidades[tipo] += 1
        resto -= 1

    total_gerados = 0
    total_descartes = 0
    gasto_execucao = 0.0
    inicio = time.time()

    for tipo, qtd in quantidades.items():
        if qtd <= 0:
            continue
        print(f"\n--- Gerando {qtd} itens do tipo '{tipo}' ---")
        gerados, descartes, gasto = gerar_lote(
            tipo=tipo,
            quantidade=qtd,
            prefixo=f"auto_{tipo}",
            state=state,
            delay=DELAY_SECONDS
        )
        total_gerados += gerados
        total_descartes += descartes
        gasto_execucao += gasto

    tempo_total = time.time() - inicio
    registrar_execucao(
        tipo="auto",
        alvo=args.quantidade,
        gerados=total_gerados,
        descartados=total_descartes,
        gasto=gasto_execucao,
        tempo=tempo_total,
        descartados_salvos=0
    )

    print("\n" + "=" * 70)
    print("📊 RESUMO FINAL (MODO AUTOMÁTICO)")
    print("=" * 70)
    print(f"   ✅ Gerados: {total_gerados}")
    print(f"   ❌ Descartados: {total_descartes}")
    print(f"   💰 Gasto execução: ${gasto_execucao:.4f}")
    print(f"   📂 Curtos: {PASTA_DADOS_CURTOS}/")
    print(f"   📂 Longos: {PASTA_DADOS_LONGOS}/")
    print(f"   🗑️  Descartados salvos: {PASTA_DESCARTES}/")
    print(f"   ⏱️ Tempo: {tempo_total:.2f}s")
    print("=" * 70)

    # Exibe status atualizado após a geração
    print("\n📌 Status dos tópicos após esta execução:")
    cmd_status_topicos()


# ============================================================================
# SAUDAÇÃO (CORRIGIDA – GERA TODAS AS QUANTIDADES)
# ============================================================================
def executar_saudacao(state: StateManager, args) -> None:
    """
    Gera saudações:
    - Primeiro tenta usar a lista fixa (sem custo).
    - Se a lista fixa acabar ou for insuficiente, gera novas via API.
    - Fallback garantido para cada saudação, assegurando a quantidade solicitada.
    """
    from utils import salvar_texto, hash_texto
    from config import client, MODEL_NAME

    print("💬 GERANDO SAUDAÇÕES (com fallback para API se necessário)")

    total_gerados = 0
    usadas_na_rodada = set()
    MAX_TENTATIVAS_SEM_API = len(SAUDACOES) * 2

    # Fase 1: lista fixa (sem custo)
    tentativas = 0
    while total_gerados < args.quantidade and tentativas < MAX_TENTATIVAS_SEM_API:
        tentativas += 1

        disponiveis = [s for s in SAUDACOES if s[0] not in usadas_na_rodada]
        if not disponiveis:
            todas_usadas = all(state.resposta_ja_usada(resp) for _, resp in SAUDACOES)
            if todas_usadas:
                print("⚠️ Todas as saudações fixas já foram usadas. Passando para API.")
                break
            usadas_na_rodada.clear()
            continue

        pergunta, resposta = random.choice(disponiveis)
        usadas_na_rodada.add(pergunta)

        if state.resposta_ja_usada(resposta):
            continue

        texto = f"Pergunta: {pergunta}\nResposta: {resposta}"
        salvar_texto(texto, args.prefixo, total_gerados, PASTA_DADOS_CURTOS)

        metadados = {
            "indice": total_gerados,
            "tipo": "saudacao",
            "categoria": "saudacao",
            "assunto": "cumprimento",
            "pergunta": pergunta,
            "modelo": "predefinido",
            "data": datetime.now().isoformat(),
            "arquivo": f"{PASTA_DADOS_CURTOS}/{args.prefixo}_{total_gerados:06d}.txt"
        }
        salvar_metadados(metadados, ARQUIVO_METADADOS)

        state.registrar_item(
            pergunta=pergunta,
            resposta=resposta,
            categoria="saudacao",
            assunto="cumprimento",
            texto_hash=hash_texto(texto),
            custo=0.0
        )

        total_gerados += 1
        if total_gerados % 10 == 0:
            print(f"   ✅ {total_gerados} saudações geradas (fixas)")

    # Fase 2: via API (com validação branda e fallback)
    if total_gerados < args.quantidade:
        restantes = args.quantidade - total_gerados
        print(f"   Gerando {restantes} saudações via API...")

        for i in range(restantes):
            sucesso = False
            for tentativa_api in range(5):
                try:
                    prompt = """Gere uma saudação original em português brasileiro, no formato:

Pergunta: [saudação]
Resposta: [resposta à saudação]

A saudação deve ser criativa, variada e adequada para uma conversa. Evite clichês como "tudo bem?".
Use diferentes estilos: formal, informal, engraçado, afetuoso, etc.
NÃO use Markdown, listas, nem frases genéricas como "é muito relevante".

Exemplo:
Pergunta: Olá, como tem passado?
Resposta: Tenho passado bem, e você? Que bom te ver!

Agora, crie uma saudação diferente:"""

                    response = client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.9,
                        max_tokens=80,
                        top_p=0.9
                    )
                    texto = response.choices[0].message.content or ""
                    if not texto:
                        continue

                    if "Pergunta:" in texto and "Resposta:" in texto:
                        partes = texto.split("Resposta:", 1)
                        if len(partes) > 1:
                            pergunta_extra = texto.split("Pergunta:", 1)[1].split("Resposta:", 1)[0].strip()
                            resposta_extra = partes[1].strip()
                    else:
                        pergunta_extra = "Saudação"
                        resposta_extra = texto.strip()

                    if not pergunta_extra or not resposta_extra:
                        continue

                    if state.resposta_ja_usada(resposta_extra):
                        print(f"   ⏳ Saudação repetida, tentando novamente...")
                        continue

                    texto_final = f"Pergunta: {pergunta_extra}\nResposta: {resposta_extra}"
                    salvar_texto(texto_final, f"{args.prefixo}_api", total_gerados, PASTA_DADOS_CURTOS)

                    metadados = {
                        "indice": total_gerados,
                        "tipo": "saudacao_api",
                        "categoria": "saudacao",
                        "assunto": "cumprimento",
                        "pergunta": pergunta_extra,
                        "modelo": MODEL_NAME,
                        "data": datetime.now().isoformat(),
                        "arquivo": f"{PASTA_DADOS_CURTOS}/{args.prefixo}_api_{total_gerados:06d}.txt"
                    }
                    salvar_metadados(metadados, ARQUIVO_METADADOS)

                    state.registrar_item(
                        pergunta=pergunta_extra,
                        resposta=resposta_extra,
                        categoria="saudacao",
                        assunto="cumprimento",
                        texto_hash=hash_texto(texto_final),
                        custo=0.0001
                    )

                    total_gerados += 1
                    sucesso = True
                    if total_gerados % 10 == 0:
                        print(f"   ✅ {total_gerados} saudações geradas (API)")
                    break

                except Exception as e:
                    print(f"   ⚠️ Erro na tentativa {tentativa_api+1}: {e}")
                    continue

            if not sucesso:
                print(f"   ⚠️ Falha ao gerar saudação via API. Usando fallback fixo.")
                pergunta_fallback = "Olá, como vai?"
                resposta_fallback = "Vou bem, obrigado! E você?"
                texto_fallback = f"Pergunta: {pergunta_fallback}\nResposta: {resposta_fallback}"
                salvar_texto(texto_fallback, f"{args.prefixo}_fallback", total_gerados, PASTA_DADOS_CURTOS)
                state.registrar_item(
                    pergunta=pergunta_fallback,
                    resposta=resposta_fallback,
                    categoria="saudacao",
                    assunto="cumprimento",
                    texto_hash=hash_texto(texto_fallback),
                    custo=0.0
                )
                total_gerados += 1
                if total_gerados % 10 == 0:
                    print(f"   ✅ {total_gerados} saudações geradas (fallback)")

            time.sleep(0.5)

    print(f"\n✅ {total_gerados} saudações salvas em {PASTA_DADOS_CURTOS}/")


# ============================================================================
# TIPO ESPECÍFICO
# ============================================================================
def executar_tipo_especifico(state: StateManager, args) -> None:
    """Executa a geração para um único tipo."""
    print("=" * 70)
    print("🤖 GERADOR DE DADOS SINTÉTICOS - RigelSLM (v2.0)")
    print(f"   Modelo: {MODEL_NAME} | Limite: ${MAX_COST_USD:.2f} | Delay: {DELAY_SECONDS}s")
    print(f"   Alvo: {args.quantidade} itens | Tipo: {args.tipo}")
    print(f"   Saída: {PASTA_DADOS_CURTOS} (curtos) e {PASTA_DADOS_LONGOS} (longos)")
    print("=" * 70)

    if not verificar_limite():
        print("⚠️ Limite já foi atingido.")
        return

    inicio = time.time()
    gerados, descartes, gasto = gerar_lote(
        tipo=args.tipo,
        quantidade=args.quantidade,
        prefixo=args.prefixo,
        state=state,
        delay=DELAY_SECONDS
    )
    tempo_total = time.time() - inicio

    registrar_execucao(
        tipo=args.tipo,
        alvo=args.quantidade,
        gerados=gerados,
        descartados=descartes,
        gasto=gasto,
        tempo=tempo_total,
        descartados_salvos=0
    )

    print("\n" + "=" * 70)
    print("📊 RESUMO FINAL")
    print("=" * 70)
    print(f"   ✅ Gerados: {gerados}")
    print(f"   ❌ Descartados: {descartes}")
    print(f"   💰 Gasto execução: ${gasto:.4f}")
    print(f"   📂 Curtos: {PASTA_DADOS_CURTOS}/")
    print(f"   📂 Longos: {PASTA_DADOS_LONGOS}/")
    print(f"   🗑️  Descartados salvos: {PASTA_DESCARTES}/")
    print(f"   ⏱️ Tempo: {tempo_total:.2f}s")
    print("=" * 70)
    print(f"\n📝 Log salvo em: {ARQUIVO_LOG}")
    print("💡 Para treinar, use: python treino.py --dados dados/gerados")


# ============================================================================
# REGISTRO DE EXECUÇÃO
# ============================================================================
def registrar_execucao(
    tipo: str,
    alvo: int,
    gerados: int,
    descartados: int,
    gasto: float,
    tempo: float,
    descartados_salvos: int = 0
) -> None:
    """Registra uma execução no histórico."""
    dados_gastos = carregar_gastos()
    gasto_acumulado = dados_gastos.get("total_gasto", 0.0)

    execucao = {
        "data_hora": datetime.now().isoformat(),
        "modelo": MODEL_NAME,
        "tipo": tipo,
        "alvo": alvo,
        "gerados": gerados,
        "descartados": descartados,
        "gasto_execucao": round(gasto, 6),
        "gasto_acumulado": round(gasto_acumulado, 6),
        "tempo_segundos": round(tempo, 2),
        "descartados_salvos": descartados_salvos,
    }

    historico = carregar_json(ARQUIVO_HISTORICO, [])
    historico.append(execucao)
    salvar_json(ARQUIVO_HISTORICO, historico)

    with open(ARQUIVO_LOG, 'a', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write(f"📅 {execucao['data_hora']}\n")
        f.write(f"   Modelo: {execucao['modelo']}\n")
        f.write(f"   Tipo: {execucao['tipo']}\n")
        f.write(f"   Alvo: {execucao['alvo']}\n")
        f.write(f"   Gerados: {execucao['gerados']}\n")
        f.write(f"   Descartados: {execucao['descartados']}\n")
        f.write(f"   Gasto: ${execucao['gasto_execucao']:.6f}\n")
        f.write(f"   Gasto acumulado: ${execucao['gasto_acumulado']:.6f}\n")
        f.write(f"   Tempo: {execucao['tempo_segundos']:.2f}s\n")
        f.write("=" * 70 + "\n\n")


# ============================================================================
# PARSER DE ARGUMENTOS
# ============================================================================
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera diálogos sintéticos em PT-BR.")
    parser.add_argument(
        "--tipo",
        type=str,
        choices=[
            "conversa", "pergunta_resposta", "dicionario", "iteracao",
            "saudacao", "artigo", "conto", "dialogo_profundo",
            "explicacao", "resumo", "auto"
        ],
        default="dicionario"
    )
    parser.add_argument("--quantidade", type=int, default=500)
    parser.add_argument("--prefixo", type=str, default="dialogo")
    parser.add_argument("--limite", type=float)
    parser.add_argument("--delay", type=float)
    parser.add_argument("--tema", type=str)
    parser.add_argument("--listar-temas", action="store_true")
    parser.add_argument("--limpar-invalidos", action="store_true")
    parser.add_argument("--validar", action="store_true")
    parser.add_argument("--ver-logs", action="store_true")
    parser.add_argument("--estatisticas", action="store_true")
    parser.add_argument("--status-topicos", action="store_true", help="Exibe o status dos tópicos externos (quantos usados, quantos faltam, próximo)")
    return parser.parse_args()


# ============================================================================
# MAIN
# ============================================================================
def main() -> None:
    if len(sys.argv) > 1:
        args = parse_args()
        atualizar_config(args)
        executar_geracao(args)
    else:
        menu_interativo()


if __name__ == "__main__":
    main()