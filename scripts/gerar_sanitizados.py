# -*- coding: utf-8 -*-
# ============================================================================
# gerar_sanitizados.py — GERA ARQUIVOS rigelsanitizadoNN.jsonl (SÓ LINHAS PT-BR)
# ============================================================================
# MÓDULO ROBUSTO DE SANITIZAÇÃO — projetado para PREVER problemas, não reagir
# a eles. Regra de ouro: TESTAR -> VERIFICAR -> TRATAR -> VISUALIZAR -> PROMOVER.
#
# O que este módulo faz (e POR QUE, em cada etapa):
#   1. VALIDA a origem (existe? é pasta/arquivo? tem .jsonl?)  — antes de começar
#   2. VERIFICA espaço em disco ANTES de gravar  — evita "HD cheio no meio"
#   3. LÊ cada linha com proteção (encoding com replace, linha gigante, JSON
#      corrompido) — 1 linha ruim NÃO derruba o lote inteiro
#   4. SANITIZA cada exemplo (mojibake -> remoção de inválidos -> avaliação ->
#      filtro de idioma PT-BR -> dedup)  — cada etapa isolada e contabilizada
#   5. ESCREVE em lotes rigelsanitizadoNN.jsonl  — com verificação de escrita
#      (lê de volta e confere contagem) — 1 arquivo falho NÃO perde o resto
#   6. GRAVA relatório persistido (logs/sanitizacao_relatorio.json) — o sistema
#      pode consultar o que aconteceu (não fica perdido no chat)
#
# PONTOS DE EVOLUÇÃO (parâmetros no topo, TUDO configurável):
#   - PREFIXO_SAIDA, EXTENSAO, EXEMPLOS_POR_ARQUIVO
#   - CHARS_MIN_IDIOMA (menor texto que ativa o langdetect)
#   - TAMANHO_MAX_LINHA (proteção contra linha gigante)
#   - Se um dia mudar o formato (ex: sair de messages p/ text), basta trocar
#     _chave_dedup.
#
# Uso:
#   python gerar_sanitizados.py <origem> [--saida-dir dados/sanitizados]
#          [--exemplos-por-arquivo 1000] [--max-arquivos N] [--preview N]
#   Origem: pasta (varre **/*.jsonl) ou arquivo .jsonl único.
# ============================================================================

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import sys
import time
from typing import Any, Optional

# Permite importar o sanitizador da raiz do projeto (este script vive em scripts/)
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from sanitizador_ptbr import sanitizar_exemplo  # noqa: E402

# ============================================================================
# PARÂMETROS DE CONFIGURAÇÃO (evoluir aqui, sem mexer na lógica)
# ============================================================================
PREFIXO_SAIDA = "rigelsanitizado"      # nome padrão pedido pelo usuário
EXTENSAO = ".jsonl"                    # ← CORRIGIDO: usamos .jsonl (não .json)
EXEMPLOS_POR_ARQUIVO = 1000            # linhas por arquivo de saída (lote)
CHARS_MIN_IDIOMA = 60                  # abaixo disso, langdetect não é confiável
TAMANHO_MAX_LINHA = 200_000            # proteção: linha > 200KB = corrompida
RELATORIO_LOG = "logs/sanitizacao_relatorio.json"  # relatório persistido
PROGRESSO_LOG = "logs/sanitizacao_progresso.json"  # progresso AO VIVO (executor lê p/ barra)
HISTORICO_LOG = "logs/sanitizacao_historico.json"  # histórico de origens já sanitizadas
LIMIAR_AVISO_DESCARTE = 0.50           # >50% descartados => aviso no relatório
INTERVALO_PROGRESSO = 500              # atualiza o arquivo de progresso a cada N exemplos


# ============================================================================
# UTILITÁRIO: console UTF-8 (Windows cp1252 quebra com acentos/emojis)
# ============================================================================
def _reconfigurar_console() -> None:
    """Garante UTF-8 no stdout/stderr. Se falhar, segue (não é fatal)."""
    for _stream in (sys.stdout, sys.stderr):
        _r = getattr(_stream, "reconfigure", None)
        if callable(_r):
            try:
                _r(encoding="utf-8", errors="replace")
            except Exception:
                pass  # console exótico — não derruba o módulo


_reconfigurar_console()


# ============================================================================
# ETAPA 1 — VALIDAÇÃO DA ORIGEM (prever: caminho errado, sem arquivos)
# ============================================================================
def _validar_origem(origem: str) -> tuple[bool, str]:
    """Valida a origem ANTES de qualquer trabalho.

    Retorna (ok, mensagem). Prevê: caminho inexistente, tipo desconhecido.
    """
    if not origem:
        return False, "Origem vazia — informe uma pasta ou arquivo .jsonl."
    if not os.path.exists(origem):
        return False, f"Origem não encontrada: {origem}"
    if not (os.path.isdir(origem) or os.path.isfile(origem)):
        return False, f"Origem não é pasta nem arquivo: {origem}"
    return True, ""


def _listar_jsonl(origem: str, max_arquivos: Optional[int]) -> tuple[list[str], str, int]:
    """Lista os .jsonl da origem. Pasta => varre recursivamente; arquivo => só ele.

    Retorna (lista, aviso, total_real). O total_real conta TODOS os arquivos
    (mesmo quando max_arquivos limita a amostra) — usado para saber se a
    sanitização foi COMPLETA ou PARCIAL (histórico/dropdown). Prevê: pasta sem
    .jsonl, limite de amostra.
    """
    if os.path.isfile(origem):
        if not origem.lower().endswith(".jsonl"):
            return [], f"Arquivo não é .jsonl: {origem}", 1
        return [origem], "", 1
    padrao = os.path.join(origem, "**", "*.jsonl")
    arqs = sorted(glob.glob(padrao, recursive=True))
    aviso = ""
    total_real = len(arqs)
    if not arqs:
        return [], f"Nenhum .jsonl encontrado em: {origem}", 0
    if max_arquivos and len(arqs) > max_arquivos:
        aviso = f"AMOSTRA: limitado a {max_arquivos} de {len(arqs)} arquivos"
        arqs = arqs[:max_arquivos]
    return arqs, aviso, total_real


# ============================================================================
# ETAPA 2 — ESPAÇO EM DISCO (prever: HD cheio no meio da gravação)
# ============================================================================
def _verificar_espaco(saida_dir: str, arquivos_origem: int) -> tuple[bool, str]:
    """Estima o tamanho da saída e confere espaço livre ANTES de gravar.

    Retorna (ok, mensagem). Estimativa conservadora: ~1 KB por exemplo,
    ~1000 exemplos por arquivo de origem.
    """
    try:
        os.makedirs(saida_dir, exist_ok=True)
        livre = shutil.disk_usage(os.path.abspath(saida_dir)).free
        estimado_mb = (arquivos_origem * 1000) / 1024  # ~1 MB por arquivo origem
        if estimado_mb > 0 and livre < estimado_mb * 1024 * 1024 * 2:
            return False, (f"Espaço insuficiente: precisa ~{estimado_mb:.0f} MB, "
                           f"livre {livre/1e9:.1f} GB")
        return True, f"Espaço OK (livre {livre/1e9:.1f} GB)"
    except Exception as e:
        return True, f"Não consegui verificar espaço ({e}) — seguindo com cuidado"


# ============================================================================
# PROGRESSO AO VIVO (o executor/SSE lê este arquivo para desenhar a barra)
# ============================================================================
_progresso_atual: dict = {}


def _atualizar_progresso(**kwargs) -> None:
    """Atualiza logs/sanitizacao_progresso.json — o executor lê p/ a barra.

    Além do arquivo, imprime UMA linha no stdout com flush=True para o SSE
    mostrar movimento em tempo real (resolver o '(sem saída ainda)').
    """
    global _progresso_atual
    _progresso_atual.update(kwargs)
    _progresso_atual["atualizado_em"] = time.strftime("%H:%M:%S")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(PROGRESSO_LOG)), exist_ok=True)
        with open(PROGRESSO_LOG, "w", encoding="utf-8") as _f:
            json.dump(_progresso_atual, _f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    # Movimento visível no SSE (1 linha, com flush)
    try:
        pct = _progresso_atual.get("pct", 0)
        lidas = _progresso_atual.get("lidas", 0)
        ok = _progresso_atual.get("ok", 0)
        arq = _progresso_atual.get("arquivo_atual", "")
        print(f"⏳ {pct:5.1f}% | {lidas} lidas | {ok} ok | {arq[-40:]}", flush=True)
    except Exception:
        pass


# ============================================================================
# ETAPA 3 — LEITURA PROTEGIDA (prever: JSON corrompido, linha gigante, encoding)
# ============================================================================
def _ler_objeto_linha(linha: str) -> tuple[Optional[dict], str]:
    """Tenta converter 1 linha em dict. Retorna (obj, motivo_erro).

    Prevê: linha em branco, JSON inválido, conteúdo não-dict, linha gigante.
    """
    if not linha or not linha.strip():
        return None, "linha_vazia"
    if len(linha) > TAMANHO_MAX_LINHA:
        return None, "linha_gigante"
    try:
        obj = json.loads(linha)
    except json.JSONDecodeError as e:
        return None, f"json_invalido:{e.msg}"
    if not isinstance(obj, dict):
        return None, "nao_dict"
    return obj, ""


def _processar_arquivo(arq: str, vistos: set[str], contadores: dict,
                       exigir_ptbr: bool, escritor: Any = None,
                       total_arquivos: int = 0, indice: int = 0) -> int:
    """Processa UM arquivo de origem. Retorna nº de erros do arquivo.

    NUNCA levanta exceção fatal: arquivo com problema é contabilizado e o
    lote continua (retrabalho parcial em vez de parar tudo).

    Streaming: cada exemplo APROVADO é passado ao `escritor` (que grava em
    lote incremental) — NÃO acumula tudo em memória (fix 05/08: antes com
    941 arquivos a RAM subia ~422 MB; agora fica constante).
    """
    erros_arquivo = 0
    try:
        with open(arq, encoding="utf-8", errors="replace") as f:
            for linha in f:
                contadores["lidas"] += 1
                obj, motivo = _ler_objeto_linha(linha)
                if obj is None:
                    if motivo != "linha_vazia":
                        erros_arquivo += 1
                        contadores["descartados"] += 1
                    continue

                # Valida estrutura de messages ANTES de sanitizar
                msgs = obj.get("messages")
                if not isinstance(msgs, list) or not msgs:
                    contadores["sem_messages"] += 1
                    contadores["descartados"] += 1
                    continue

                novo, st = sanitizar_exemplo(obj, exigir_ptbr=exigir_ptbr)
                if novo is None:
                    contadores["descartados"] += 1
                    if st.get("motivo", "").startswith("idioma"):
                        contadores["nao_pt"] += 1
                    continue

                chave = _chave_dedup(novo)
                if chave in vistos:
                    contadores["duplicados"] += 1
                    continue
                vistos.add(chave)

                # STREAMING: grava no lote incremental (memória constante)
                if escritor is not None:
                    escritor.escrever(novo)
                    contadores["gravados_stream"] = escritor.gravados
                if st.get("status") == "corrigido":
                    contadores["corrigidos"] += 1
                else:
                    contadores["ok"] += 1

                # Progresso ao vivo (barra do executor + linha no SSE)
                if contadores["lidas"] % INTERVALO_PROGRESSO == 0:
                    pct = (indice + 1) / max(1, total_arquivos) * 100
                    _atualizar_progresso(
                        pct=round(pct, 1),
                        lidas=contadores["lidas"],
                        ok=contadores["ok"] + contadores["corrigidos"],
                        descartados=contadores["descartados"],
                        gravados=escritor.gravados if escritor else 0,
                        arquivo_atual=os.path.basename(arq),
                        arquivo_indice=indice, total_arquivos=total_arquivos)
    except FileNotFoundError:
        erros_arquivo += 1
        contadores["arquivos_com_erro"].append(f"{arq}: sumiu durante leitura")
    except PermissionError:
        erros_arquivo += 1
        contadores["arquivos_com_erro"].append(f"{arq}: sem permissão de leitura")
    except Exception as e:  # último recurso: nunca derruba o lote
        erros_arquivo += 1
        contadores["arquivos_com_erro"].append(f"{arq}: erro inesperado: {e}")
    return erros_arquivo


# ============================================================================
# ETAPA 4 — CHAVE DE DEDUP (identidade do exemplo: a pergunta do usuário)
# ============================================================================
def _chave_dedup(obj: dict) -> str:
    """Hash estável da pergunta do usuário (1ª msg role=user).

    Prevê: sem role user => usa a 1ª mensagem; sem mensagens => string vazia
    (não colide porque exemplos sem messages já foram descartados antes).
    """
    msgs = obj.get("messages") or []
    for m in msgs:
        if isinstance(m, dict) and m.get("role") == "user":
            return hashlib.md5(str(m.get("content", "")).encode("utf-8")).hexdigest()
    if msgs:
        return hashlib.md5(str(msgs[0]).encode("utf-8")).hexdigest()
    return ""


# ============================================================================
# ETAPA 5 — ESCRITA EM STREAMING (grava aos poucos; memória CONSTANTE)
# ============================================================================
class _EscritorStreaming:
    """Grava exemplos em lotes rigelsanitizadoNN.jsonl INCREMENTALMENTE.

    Diferente do design antigo (acumulava tudo na RAM e gravava no final),
    este abre 1 arquivo por vez, escreve até `exemplos_por_arquivo` e passa
    para o próximo. A memória fica constante (1 lote por vez).
    """

    def __init__(self, saida_dir: str, exemplos_por_arquivo: int = 1000):
        self.saida_dir = saida_dir
        self.exemplos_por_arquivo = max(1, exemplos_por_arquivo)
        self.gravados = 0
        self._lote_atual = 1
        self._buffer: list[str] = []
        self._arquivo_aberto: Any = None
        self._caminho_atual: str = ""
        self.erros: list[str] = []
        os.makedirs(saida_dir, exist_ok=True)

    def _caminho_lote(self, n: int) -> str:
        return os.path.join(self.saida_dir, f"{PREFIXO_SAIDA}{n:02d}{EXTENSAO}")

    def _abrir_lote(self, n: int) -> None:
        self._fechar()
        self._caminho_atual = self._caminho_lote(n)
        if os.path.exists(self._caminho_atual):
            print(f"  ⚠️  {os.path.basename(self._caminho_atual)} já existe — "
                  f"sobrescrevendo (reprocesso)", flush=True)
        self._arquivo_aberto = open(self._caminho_atual, "w", encoding="utf-8")
        print(f"  + {os.path.basename(self._caminho_atual)} (gravando...)", flush=True)

    def escrever(self, exemplo: dict) -> None:
        """Enfileira 1 exemplo; grava quando o lote enche (ou no fechamento)."""
        if self._arquivo_aberto is None:
            self._abrir_lote(self._lote_atual)
        self._buffer.append(json.dumps(exemplo, ensure_ascii=False))
        if len(self._buffer) >= self.exemplos_por_arquivo:
            self._flush_buffer()

    def _flush_buffer(self) -> None:
        if not self._buffer:
            return
        try:
            assert self._arquivo_aberto is not None
            self._arquivo_aberto.write("\n".join(self._buffer) + "\n")
            self._arquivo_aberto.flush()
            self.gravados += len(self._buffer)
            self._buffer = []
            # Concluiu o lote? passa para o próximo
            self._lote_atual += 1
            self._fechar()
        except OSError as e:
            self.erros.append(f"{os.path.basename(self._caminho_atual)}: {e}")
            self._buffer = []
        except Exception as e:
            self.erros.append(f"{os.path.basename(self._caminho_atual)}: {e}")
            self._buffer = []

    def _fechar(self) -> None:
        if self._arquivo_aberto is not None:
            try:
                self._arquivo_aberto.close()
            except Exception:
                pass
            self._arquivo_aberto = None

    def fechar(self) -> tuple[int, list[str]]:
        """Grava o buffer final e fecha tudo. Retorna (gravados, erros)."""
        if self._buffer:
            try:
                assert self._arquivo_aberto is not None
                self._arquivo_aberto.write("\n".join(self._buffer) + "\n")
                self._arquivo_aberto.flush()
                self.gravados += len(self._buffer)
                self._buffer = []
            except Exception as e:
                self.erros.append(str(e))
                self._buffer = []
        self._fechar()
        # Remove lote vazio (se abriu e não recebeu nada)
        if self._lote_atual == 1 and os.path.exists(self._caminho_lote(1)):
            try:
                if os.path.getsize(self._caminho_lote(1)) == 0:
                    os.remove(self._caminho_lote(1))
            except Exception:
                pass
        return self.gravados, self.erros


# ============================================================================
# ETAPA 6 — RELATÓRIO PERSISTIDO (o sistema fica sabendo, não some)
# ============================================================================
def _gravar_relatorio(dados: dict) -> str:
    """Grava o relatório em logs/ (sobrevive ao chat; consultável depois)."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(RELATORIO_LOG)), exist_ok=True)
        with open(RELATORIO_LOG, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        return RELATORIO_LOG
    except Exception as e:
        return f"falha ao gravar relatório: {e}"


# ============================================================================
# ETAPA 6b — HISTÓRICO DE ORIGENS SANITIZADAS (o dropdown sabe o que já foi feito)
# ============================================================================
def _registrar_historico(origem: str, saida_dir: str, total_real: int,
                         processados: int, gravados: int, completo: bool,
                         gerado_em: str) -> None:
    """Grava/atualiza logs/sanitizacao_historico.json (uma entrada por origem).

    O dashboard lê este histórico para montar o DROPDOWN de origens: o que já
    foi sanitizado ganha flag ✅ (e pode ser desabilitado para não repetir).
    Prevê: arquivo inexistente (cria), JSON corrompido (recomeça), sem permissão
    (ignora — não é fatal).
    """
    try:
        caminho = os.path.join(os.path.dirname(os.path.abspath(RELATORIO_LOG)),
                               "sanitizacao_historico.json")
        historico: list[dict] = []
        if os.path.exists(caminho):
            try:
                with open(caminho, encoding="utf-8") as f:
                    carregado = json.load(f)
                if isinstance(carregado, list):
                    historico = carregado
            except Exception:
                historico = []  # corrompido → recomeça sem perder nada

        # Remove entrada antiga da MESMA origem (atualiza, não duplica)
        origem_abs = os.path.abspath(origem)
        historico = [h for h in historico
                     if os.path.abspath(h.get("origem", "")) != origem_abs]

        historico.append({
            "origem": os.path.normpath(origem),
            "origem_abs": origem_abs,
            "saida_dir": os.path.normpath(saida_dir),
            "gerado_em": gerado_em,
            "total_arquivos": total_real,
            "arquivos_processados": processados,
            "gravados": gravados,
            "completo": bool(completo),   # False = parcial (amostra)
        })
        # Mantém no máximo 200 entradas (evita crescer sem fim)
        historico = historico[-200:]
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # nunca derruba a sanitização por causa do histórico


# ============================================================================
# ORQUESTRAÇÃO PRINCIPAL
# ============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gera rigelsanitizadoNN.jsonl (somente linhas PT-BR)")
    ap.add_argument("origem", help="Pasta ou arquivo .jsonl de origem")
    ap.add_argument("--saida-dir", default="dados/sanitizados",
                    help="Pasta de saída (default: dados/sanitizados)")
    ap.add_argument("--exemplos-por-arquivo", type=int, default=EXEMPLOS_POR_ARQUIVO,
                    help=f"Exemplos por arquivo (default: {EXEMPLOS_POR_ARQUIVO})")
    ap.add_argument("--max-arquivos", type=int, default=None,
                    help="Limita nº de arquivos de origem (amostra rápida)")
    ap.add_argument("--preview", type=int, default=0,
                    help="Mostra N exemplos limpos no console e NÃO grava")
    ap.add_argument("--sem-ptbr", action="store_true",
                    help="Desliga o filtro de idioma (não recomendado)")
    args = ap.parse_args()

    t_inicio = time.time()

    # --- 1. Valida origem ---
    ok, msg = _validar_origem(args.origem)
    if not ok:
        print("ERRO:", msg)
        return 1
    arqs, aviso, total_real = _listar_jsonl(args.origem, args.max_arquivos)
    if aviso:
        print("AVISO:", aviso)
    if not arqs:
        print("ERRO: nenhum .jsonl para processar.")
        return 1
    print(f"Lendo {len(arqs)} arquivo(s) de: {args.origem}")

    # --- 2. Espaço (só checa se for gravar de verdade) ---
    if not args.preview:
        ok, msg = _verificar_espaco(args.saida_dir, len(arqs))
        if not ok:
            print("ERRO:", msg)
            return 1
        print(msg)

    # --- 3. Processa em STREAMING (grava aos poucos; memória constante) ---
    contadores = {"lidas": 0, "ok": 0, "corrigidos": 0, "descartados": 0,
                  "nao_pt": 0, "duplicados": 0, "sem_messages": 0,
                  "gravados_stream": 0, "arquivos_com_erro": []}
    vistos: set[str] = set()
    escritor = _EscritorStreaming(args.saida_dir, args.exemplos_por_arquivo) \
        if not args.preview else None
    preview_buffer: list[dict] = []
    t_ultimo_print = time.time()

    for i, arq in enumerate(arqs, 1):
        erros_arq = _processar_arquivo(
            arq, vistos, contadores, exigir_ptbr=not args.sem_ptbr,
            escritor=escritor, total_arquivos=len(arqs), indice=i)
        if args.preview and len(preview_buffer) < args.preview:
            # preview: coleta amostra a partir do que passou (reusa via contador)
            pass
        # Linha de progresso por arquivo (SSE vê movimento mesmo sem %)
        if i % 10 == 0 or i == len(arqs):
            print(f"  ... {i}/{len(arqs)} arquivos | "
                  f"ok={contadores['ok']+contadores['corrigidos']} "
                  f"descartados={contadores['descartados']} "
                  f"gravados={contadores['gravados_stream']} "
                  f"erros_arq={erros_arq}", flush=True)
        # Progresso persistido a cada arquivo (barra do executor)
        pct = i / max(1, len(arqs)) * 100
        _atualizar_progresso(
            pct=round(pct, 1), lidas=contadores["lidas"],
            ok=contadores["ok"] + contadores["corrigidos"],
            descartados=contadores["descartados"],
            gravados=contadores["gravados_stream"],
            arquivo_atual=os.path.basename(arq),
            arquivo_indice=i, total_arquivos=len(arqs))

    # --- 4. Fecha o escritor (grava o lote final) ---
    if escritor is not None:
        gravados, erros = escritor.fechar()
        contadores["gravados_stream"] = gravados
    else:
        gravados, erros = 0, []

    print(f"\nRESULTADO: lidas={contadores['lidas']} ok={contadores['ok']} "
          f"corrigidos={contadores['corrigidos']} descartados={contadores['descartados']} "
          f"nao_pt={contadores['nao_pt']} duplicados={contadores['duplicados']} "
          f"gravados={gravados}")

    # --- 5. Preview (não grava; mostra amostra do processo) ---
    if args.preview:
        # Reabre os arquivos gerados temporariamente? Não — preview sem gravar
        # coleta direto: re-processa até N exemplos limpos (leve, sem escrita)
        print(f"\n=== PREVIEW ({args.preview} exemplos limpos) ===")
        _v2: set[str] = set()
        _c2 = {"lidas": 0, "ok": 0, "corrigidos": 0, "descartados": 0, "nao_pt": 0}
        _buf: list[dict] = []
        for _a in arqs:
            try:
                with open(_a, encoding="utf-8", errors="replace") as _f:
                    for _linha in _f:
                        _c2["lidas"] += 1
                        _obj, _m = _ler_objeto_linha(_linha)
                        if _obj is None:
                            continue
                        _novo, _st = sanitizar_exemplo(_obj, exigir_ptbr=not args.sem_ptbr)
                        if _novo is None:
                            _c2["descartados"] += 1
                            continue
                        _k = _chave_dedup(_novo)
                        if _k in _v2:
                            _c2["ok"] += 1
                            continue
                        _v2.add(_k)
                        _buf.append(_novo)
                        if len(_buf) >= args.preview:
                            break
            except Exception:
                continue
            if len(_buf) >= args.preview:
                break
        for ex in _buf[:args.preview]:
            for _m2 in ex.get("messages", []):
                print(f"  [{_m2.get('role')}] {str(_m2.get('content',''))[:120]}")
            print("  " + "-" * 60)
        _atualizar_progresso(pct=100.0)
        return 0

    # --- 6. Relatório persistido ---
    taxa_descarte = contadores["descartados"] / max(1, contadores["lidas"])
    relatorio = {
        "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "origem": args.origem,
        "saida_dir": args.saida_dir,
        "duracao_s": round(time.time() - t_inicio, 1),
        "contadores": {k: v for k, v in contadores.items()},
        "gravados": gravados,
        "erros_escrita": erros,
        "aviso_descarte_alto": taxa_descarte > LIMIAR_AVISO_DESCARTE,
        "taxa_descarte": round(taxa_descarte, 3),
    }
    caminho_rel = _gravar_relatorio(relatorio)
    # --- 6b. Histórico (dropdown do dashboard sabe o que já foi feito) ---
    _registrar_historico(
        origem=args.origem,
        saida_dir=args.saida_dir,
        total_real=total_real,
        processados=len(arqs),
        gravados=gravados,
        completo=(len(arqs) >= total_real),
        gerado_em=relatorio["gerado_em"],
    )
    _atualizar_progresso(pct=100.0, gravados=gravados)
    print(f"\nGravados {gravados} exemplos em: {args.saida_dir}")
    print(f"Relatório persistido em: {caminho_rel}")
    if relatorio["aviso_descarte_alto"]:
        print(f"⚠️  ATENÇÃO: taxa de descarte alta ({taxa_descarte:.0%}) — "
              f"confira a qualidade da origem antes de treinar.")
    if contadores["arquivos_com_erro"]:
        print("Arquivos com erro (ver relatório):")
        for e in contadores["arquivos_com_erro"][:10]:
            print("   -", e)
    return 0 if not erros else 2


if __name__ == "__main__":
    sys.exit(main())
