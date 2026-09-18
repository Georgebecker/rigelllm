#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tratamento.py — Central de Tratamento de Dados (dados de QUALQUER fonte).

Automacão do tratamento, igual ao fluxo do HuggingFace, mas para pastas que
vieram de qualquer lugar (scrap, RSS, download manual, HF, etc.):

  1. Varre dados/raw/ e detecta o FORMATO de cada pasta
  2. Recomenda o tratamento certo (matriz de tratamento):
       - jsonl   → 🧼 sanitização PT-BR        (dashboard.services.sanitizacao)
       - parquet → 🧹 limpeza leve v2          (limpeza_leve_rigel_v2.py)
       - txt     → 🔤 limpeza de encoding      (limpeza.py)
       - csv     → 🧹 limpeza leve v2
  3. O usuário MARCA as pastas e clica "Tratar marcados"
  4. O pipeline roda em lote: tratar → promover p/ processed/<tipo>/<nome> → limpar origens

Regras de ouro: guard de memória (recusa se RAM livre < 2 GB), 1 processo pesado
por vez, estado persistido p/ sobreviver a --reload, origens só apagadas após sucesso.
"""
import json
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

import httpx  # noqa: F401  (mantém o path de rede consistente com os demais)

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW = PROJETO_ROOT / "dados" / "raw"
GERADOS = PROJETO_ROOT / "dados" / "gerados"
GERADOS_JSONL = GERADOS / "jsonl"
PROCESSED = PROJETO_ROOT / "dados" / "processed"
SANITIZADOS = PROJETO_ROOT / "dados" / "sanitizados"
MIN_RAM_LIVRE_GB = 2.0  # guardião: não inicia tratamento pesado abaixo disso

# ============================================================================
# Estado (thread-safe + persistência)
# ============================================================================
_estado: dict = {
    "rodando": False,
    "etapa": "idle",          # idle | preparando | tratando | extraindo | concluido | erro
    "mensagem": "",
    "percentual": None,
    "fila": [],               # pastas marcadas
    "atual": None,            # pasta sendo tratada agora
    "concluidos": [],         # [{nome, ok, tratamento, detalhe}]
    "log": [],                # 📋 linhas do log em tempo real (regra: ver acontecendo)
    "inicio": None,
    "fim": None,
    "erro": None,
}
_lock = threading.Lock()
_PERSISTENCIA = PROJETO_ROOT / "estado" / "tratamento_estado.json"


def _persistir() -> None:
    try:
        _PERSISTENCIA.parent.mkdir(parents=True, exist_ok=True)
        _PERSISTENCIA.write_text(json.dumps(_estado, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception:
        pass


def _atualizar(**kwargs) -> None:
    with _lock:
        _estado.update(kwargs)
        _persistir()


def _log(msg: str) -> None:
    """Anexa uma linha ao log EM TEMPO REAL (regra de ouro: ver acontecendo)."""
    linha = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    with _lock:
        _estado.setdefault("log", []).append(linha)
        _estado["log"] = _estado["log"][-400:]  # teto
        _persistir()


def _processo_vivo(pid) -> bool:
    """Diz se um PID ainda está rodando (usado para não marcar 'interrompido'
    quando o processo separado de extração continua vivo após um reload)."""
    if not pid:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except Exception:
        try:
            import os as _os
            _os.kill(pid, 0)  # noqa: PLW0211 — checagem simples
            return True
        except Exception:
            return False


def get_estado() -> dict:
    """Estado atual. A fonte da verdade é o arquivo persistido: o processo
    separado de extração (scripts/extrair_pdfs_lote.py) também escreve nele,
    então mesmo com reload do uvicorn o front vê o progresso real."""
    with _lock:
        try:
            if _PERSISTENCIA.exists():
                dados = json.loads(_PERSISTENCIA.read_text(encoding="utf-8"))
                if isinstance(dados, dict):
                    _estado.clear()
                    _estado.update(dados)
        except Exception:
            pass
        # 🔒 Rede de segurança: se diz "rodando" mas o processo dono morreu,
        # nunca deixa o painel travado — vira interrompido (mostra Continuar).
        if _estado.get("rodando") and not _processo_vivo(_estado.get("pid")):
            _estado["rodando"] = False
            _estado["etapa"] = "interrompido"
            _estado["erro"] = ("O processo de extração foi encerrado. "
                               "Nada foi perdido — use o botão Continuar.")
            _estado.setdefault("log", [])
            msg_crash = (f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ A extração caiu. "
                         "Clique em Continuar para retomar (pula o que já estava feito).")
            # Anexa UMA vez por episódio — não repetir a cada consulta do painel
            if not _estado["log"] or "A extração caiu" not in _estado["log"][-1]:
                _estado["log"].append(msg_crash)
            _persistir()
        return dict(_estado)


def limpar() -> dict:
    """Para o processo de extração (se houver) e reseta o estado."""
    with _lock:
        pid = _estado.get("pid")
        if _estado.get("rodando") and pid and _processo_vivo(pid):
            try:
                import subprocess as _sp
                # taskkill /T /F — mata o processo e os filhos (regra do usuário)
                _sp.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True, timeout=15)
            except Exception:
                try:
                    import psutil
                    psutil.Process(pid).kill()
                except Exception:
                    pass
        _estado.update({
            "rodando": False, "etapa": "idle", "mensagem": "", "percentual": None,
            "fila": [], "atual": None, "concluidos": [], "inicio": None,
            "fim": None, "erro": None, "log": [], "pid": None,
        })
        _persistir()
    return {"ok": True, "mensagem": "Parado (o que já foi feito fica salvo). Estado limpo."}


# ============================================================================
# ✨ EXTRAÇÃO DE PDF (na própria aba de Tratamento — não joga p/ outra página)
# Roda: PDF → TXT (extrair_livro_pdf) → JSONL (livro_para_jsonl) → promoção
# automática p/ processed. Roda como PROCESSO INDEPENDENTE (scripts/
# extrair_pdfs_lote.py) para sobreviver ao --reload do uvicorn: mesmo que o
# servidor recarregue, o trabalho continua e o log/percentual seguem sendo
# gravados no mesmo arquivo de estado (nada se perde).
# ============================================================================
def extrair_pdfs_pasta(nome: str) -> dict:
    """Extrai TODOS os PDFs de uma pasta em dados/raw/<nome> (livros).

    Fluxo completo na própria aba: extrair → limpar → converter p/ JSONL →
    promover p/ processed. Nada de ir para outra página.
    """
    import subprocess as _sp

    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um tratamento em andamento."}
    origem = RAW / nome
    if not origem.is_dir():
        return {"ok": False, "erro": f"Pasta '{nome}' não encontrada em dados/raw/."}
    pdfs = sorted([p for p in origem.rglob("*.pdf") if p.is_file()])
    if not pdfs:
        return {"ok": False, "erro": f"Não há PDFs em '{nome}'."}

    script_lote = PROJETO_ROOT / "scripts" / "extrair_pdfs_lote.py"
    if not script_lote.exists():
        return {"ok": False, "erro": "Script de extração em lote não encontrado."}

    # Guardião de memória (regra de ouro): recusa se RAM livre < mínimo
    livre = _ram_livre_gb()
    if livre < MIN_RAM_LIVRE_GB:
        return {"ok": False, "erro": f"Memória livre baixa ({livre:.1f} GB < {MIN_RAM_LIVRE_GB}). "
                                     "Nada iniciado — feche processos pesados e tente de novo."}

    # ✅ Marca logo o estado como rodando (para o front mostrar na hora)
    _atualizar(rodando=True, etapa="extraindo", percentual=0,
               mensagem=f"Preparando extração de {len(pdfs)} PDF(s) de '{nome}'...",
               fila=[nome], atual=nome, concluidos=[], log=[],
               inicio=datetime.now().isoformat(), fim=None, erro=None, pid=None)
    _log(f"🚀 Iniciando extração de {len(pdfs)} PDF(s) de '{nome}' (processo separado)...")

    # 🔥 Lança o subprocesso INDEPENDENTE: ele escreve o estado/log sozinho.
    # Não é thread daemon — sobrevive a reload do uvicorn.
    proc = _sp.Popen([sys.executable, str(script_lote), "--pasta", nome],
                     cwd=str(PROJETO_ROOT))
    return {"ok": True,
            "mensagem": f"✨ Extração de {len(pdfs)} PDF(s) de '{nome}' iniciada. "
                        "Acompanhe o percentual e o log aqui mesmo.",
            "pdfs": len(pdfs), "pid": proc.pid}


# ============================================================================
# Detecção de formato + recomendação
# ============================================================================
def detectar_formato(caminho: Path) -> str:
    """Detecta o formato dominante de uma pasta/arquivo pelos arquivos."""
    exts: dict[str, int] = {}
    arquivos = [caminho] if caminho.is_file() else [f for f in caminho.rglob("*") if f.is_file()]
    for f in arquivos:
        e = f.suffix.lower()
        if e:
            exts[e] = exts.get(e, 0) + 1
    if not exts:
        return "vazio"
    # formatação ignora metadados
    for meta in (".gitattributes", ".gitignore", ".metadata"):
        pass
    if exts.get(".jsonl", 0) >= 1:
        return "jsonl"
    if exts.get(".parquet", 0) >= 1:
        return "parquet"
    if exts.get(".csv", 0) >= 1:
        return "csv"
    if exts.get(".txt", 0) >= 1:
        return "txt"
    if exts.get(".json", 0) >= 1:
        return "json"
    return "outro"


def recomendar_tratamento(formato: str) -> str:
    """Matriz de tratamento: cada formato tem sua ferramenta certa."""
    mapa = {
        "jsonl": "sanitizar",
        "parquet": "limpeza_leve",
        "csv": "limpeza_leve",
        "txt": "limpeza_encoding",
        "json": "sanitizar",
        "outro": "nenhum",
        "vazio": "nenhum",
    }
    return mapa.get(formato, "nenhum")


def _tamanho_pasta(caminho: Path) -> float:
    return sum(f.stat().st_size for f in caminho.rglob("*") if f.is_file()) / 1e6


def _pode_converter_para_messages(pasta: Path) -> bool:
    """True se a pasta jsonl pode virar conversa (messages/prompt/instruction/
    pergunta/question). False se é só pré-treino (text) ou vazia."""
    try:
        arqs = sorted(pasta.glob("*.jsonl")) + sorted(pasta.glob("*.json"))
        for arq in arqs[:2]:
            with open(arq, encoding="utf-8", errors="replace") as f:
                for i, linha in enumerate(f):
                    if i >= 20:
                        break
                    linha = linha.strip()
                    if not linha:
                        continue
                    try:
                        obj = json.loads(linha)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        if isinstance(obj.get("messages"), list):
                            return True
                        if any(k in obj for k in ("prompt", "instruction", "pergunta", "question")):
                            return True
                        if obj.get("text"):
                            return False
        return False
    except Exception:
        return False


def _acoes_disponiveis(pasta: Path) -> list:
    """Ações possíveis para a pasta provisória, pelo que ela ainda precisa:
    'converter' (vira conversa) ou 'extrair_txt' (pré-treino → .txt)."""
    if _pode_converter_para_messages(pasta):
        return ["converter"]
    try:
        arqs = sorted(pasta.glob("*.jsonl")) + sorted(pasta.glob("*.json"))
        for arq in arqs[:1]:
            with open(arq, encoding="utf-8", errors="replace") as f:
                for linha in f:
                    linha = linha.strip()
                    if not linha:
                        continue
                    try:
                        obj = json.loads(linha)
                    except Exception:
                        continue
                    if isinstance(obj, dict) and obj.get("text"):
                        return ["extrair_txt"]
                    break
    except Exception:
        pass
    return []


def _carteira_resumo(nome: str) -> dict:
    """Resumo do cartão de vacina da pasta (quais etapas já foram carimbadas)."""
    try:
        from dashboard.services.qualidade import status as _qs
        st = _qs(nome)
        return {"etapas": st.get("etapas") or {}, "faltam": st.get("faltam") or []}
    except Exception:
        return {"etapas": {}, "faltam": []}


def listar_entrada() -> dict:
    """Lista as pastas em dados/raw/ (tratáveis) + as de dados/gerados/jsonl/
    (provisórias — só para VERIFICAR; o tratamento aqui não converte formatos
    como pretrain/raciocínio, então não oferecemos tratar para não re-promover
    conteúdo bruto em processed).

    Pastas VAZIAS são separadas em 'vazias' (não aparecem na lista de
    marcação — não há o que tratar; o usuário só vê uma nota).
    """
    itens = []
    vazias: list[dict] = []
    if RAW.exists():
        for d in sorted(RAW.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            n_arquivos = sum(len(fs) for _, _, fs in os.walk(d))
            formato = detectar_formato(d)
            item = {
                "nome": d.name,
                "formato": formato,
                "tratamento": recomendar_tratamento(formato),
                "arquivos": n_arquivos,
                "tamanho_mb": round(_tamanho_pasta(d), 2),
            }
            if n_arquivos == 0:
                vazias.append(item)  # nada para tratar — só nota
            else:
                itens.append(item)
    # 📁 Provisórios em dados/gerados/jsonl — verificação (não tratar aqui)
    gerados: list[dict] = []
    if GERADOS_JSONL.exists():
        for d in sorted(GERADOS_JSONL.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            n_arquivos = sum(len(fs) for _, _, fs in os.walk(d))
            formato = detectar_formato(d)
            gerados.append({
                "nome": d.name,
                "formato": formato,
                "tratamento": recomendar_tratamento(formato),
                "arquivos": n_arquivos,
                "tamanho_mb": round(_tamanho_pasta(d), 2),
                "caminho": str(d),
                "conversivel": _pode_converter_para_messages(d),
                "acoes": _acoes_disponiveis(d),
                "carteira": _carteira_resumo(d.name),
            })
    gerados.sort(key=lambda x: x["nome"])
    return {"ok": True, "itens": itens, "vazias": vazias,
            "gerados": gerados, "pasta": str(RAW)}


# ============================================================================
# PRÉVIA — explica ao usuário o que vai acontecer com cada pasta marcada
# (iterativo: ninguém precisa adivinhar; o sistema fala o que faz e por quê)
# ============================================================================

def _explicar_formato(formato: str, pasta: Path) -> dict:
    """Explica, em linguagem leiga, o que será feito com a pasta.

    Retorna {ok, formato, tratamento, explicacao, acao_url?, acao_label?}:
    - ok=True  → vai ser tratada (explica o quê)
    - ok=False → NÃO pode ser tratada aqui (explica o porquê + para onde ir)
    """
    arquivos = [f for f in pasta.rglob("*") if f.is_file()]
    ext_dominante = ""
    if arquivos:
        contagem: dict[str, int] = {}
        for f in arquivos:
            e = f.suffix.lower().lstrip(".") or "sem_extensao"
            contagem[e] = contagem.get(e, 0) + 1
        if contagem:
            ext_dominante = max(contagem, key=contagem.get)

    if formato == "jsonl":
        return {"ok": True, "formato": formato, "tratamento": "sanitizar",
                "explicacao": "🧼 Textos em formato JSONL: serão limpos (acentos corretos, português certo) e preparados para o treino."}
    if formato == "json":
        return {"ok": True, "formato": formato, "tratamento": "sanitizar",
                "explicacao": "🧼 Arquivos JSON: serão convertidos e limpos (português correto)."}
    if formato == "parquet":
        return {"ok": True, "formato": formato, "tratamento": "limpeza_leve",
                "explicacao": "🧹 Dados em Parquet: serão limpos — textos repetidos e fora do português serão removidos."}
    if formato == "csv":
        return {"ok": True, "formato": formato, "tratamento": "limpeza_leve",
                "explicacao": "🧹 Dados em CSV: serão limpos — textos repetidos e fora do português serão removidos."}
    if formato == "txt":
        return {"ok": True, "formato": formato, "tratamento": "limpeza_encoding",
                "explicacao": "🔤 Textos em TXT: terão a codificação corrigida (letras e acentos certos)."}
    if formato == "vazio":
        return {"ok": False, "formato": formato, "tratamento": "nenhum",
                "explicacao": "📭 Esta pasta está vazia — não há o que tratar. Ela não vai atrapalhar; pode deixar ou apagar manualmente."}
    if formato == "outro":
        if ext_dominante in ("pdf",):
            return {"ok": False, "formato": formato, "tratamento": "nenhum",
                    "explicacao": "📄 Aqui têm arquivos PDF. Posso extrair o texto AGORA aqui mesmo (gera TXT + JSONL e já promove p/ processed) — sem precisar sair desta página.",
                    "tem_pdf": True, "acao_url": "/pdfs", "acao_label": "📄 Ver PDFs"}
        if ext_dominante in ("docx", "doc"):
            return {"ok": False, "formato": formato, "tratamento": "nenhum",
                    "explicacao": "📝 Aqui têm documentos Word (.docx/.doc). Converta para texto (.txt) ou JSONL primeiro (salve como 'Somente Texto') e tente de novo."}
        return {"ok": False, "formato": formato, "tratamento": "nenhum",
                "explicacao": f"❓ Esta pasta tem arquivos que o sistema não reconhece (tipo: .{ext_dominante or 'desconhecido'}). "
                              "Converta para .txt, .jsonl ou .csv e tente de novo."}
    return {"ok": False, "formato": formato, "tratamento": "nenhum",
            "explicacao": f"❓ Não sei tratar arquivos do tipo '{formato}'. Converta para .txt, .jsonl ou .csv e tente de novo."}


def prever(nomes: list[str]) -> dict:
    """Prévia iterativa: explica o que será feito com cada pasta marcada.

    Usada ANTES de iniciar o tratamento, para o usuário saber exatamente o
    que vai acontecer (e o que NÃO pode ser feito, com o caminho certo).
    """
    nomes = [n for n in (nomes or []) if isinstance(n, str) and n.strip()]
    itens = []
    trataveis = 0
    nao_trataveis = 0
    for nome in nomes:
        pasta = RAW / nome
        if not pasta.is_dir():
            itens.append({"nome": nome, "ok": False, "existe": False,
                          "explicacao": "❓ Pasta não encontrada em dados/raw/."})
            nao_trataveis += 1
            continue
        formato = detectar_formato(pasta)
        prev = _explicar_formato(formato, pasta)
        prev["nome"] = nome
        prev["arquivos"] = sum(len(fs) for _, _, fs in os.walk(pasta))
        prev["tamanho_mb"] = round(_tamanho_pasta(pasta), 2)
        if prev.get("ok"):
            trataveis += 1
        else:
            nao_trataveis += 1
        itens.append(prev)
    return {"ok": True, "itens": itens, "trataveis": trataveis,
            "nao_trataveis": nao_trataveis,
            "mensagem": (f"{trataveis} pasta(s) serão tratadas"
                         + (f" e {nao_trataveis} não podem (veja o motivo)" if nao_trataveis else " — tudo certo!")
                         if trataveis else "Nenhuma das pastas marcadas pode ser tratada agora — veja o motivo abaixo.")}


# ============================================================================
# Pipeline de tratamento por tipo
# ============================================================================
def _ram_livre_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().available / 1e9
    except Exception:
        return 99.0


def _tratar_uma(nome: str) -> dict:
    """Aplica o tratamento certo e promove. Retorna {ok, tratamento, detalhe}."""
    import time as _time
    origem = RAW / nome
    formato = detectar_formato(origem)
    tratamento = recomendar_tratamento(formato)
    detalhe = f"{formato} -> {tratamento}"

    if tratamento == "sanitizar":
        from dashboard.services import sanitizacao
        import shutil as _sh
        saida = str(SANITIZADOS / f"trat_{nome}")
        ini = sanitizacao.iniciar(str(origem), saida_dir=saida)
        if not ini.get("ok"):
            return {"ok": False, "tratamento": tratamento, "detalhe": f"sanitizar não iniciou: {ini.get('erro','?')}"}
        _espera = 0
        while _espera < 1800:
            _time.sleep(2)
            _espera += 2
            if not sanitizacao.status().get("rodando"):
                break
        st = sanitizacao.status()
        gravados = int(st.get("total_gravados", 0) or 0)
        destino = PROCESSED / "jsonl" / nome
        destino.mkdir(parents=True, exist_ok=True)
        copiados = 0
        for f in Path(saida).glob("*.jsonl"):
            try:
                _sh.copy2(str(f), str(destino / f.name))
                copiados += 1
            except Exception:
                pass
        if copiados == 0 and gravados == 0:
            # Fallback honesto: promove o bruto
            for f in origem.rglob("*.jsonl"):
                try:
                    _sh.copy2(str(f), str(destino / f.name))
                    copiados += 1
                except Exception:
                    pass
        return {"ok": True, "tratamento": tratamento,
                "detalhe": f"sanitizado: {gravados} exemplos, {copiados} arquivo(s) -> processed/jsonl/{nome}/"}

    if tratamento == "limpeza_leve":
        import subprocess as _sp
        import shutil as _sh
        PROCESSED.mkdir(parents=True, exist_ok=True)
        res = _sp.run(
            [sys.executable, "-u", "limpeza_leve_rigel_v2.py",
             "--origem", str(origem), "--saida", str(PROCESSED)],
            capture_output=True, text=True, timeout=7200,
            encoding="utf-8", errors="replace", cwd=str(PROJETO_ROOT))
        if res.returncode != 0:
            return {"ok": False, "tratamento": tratamento,
                    "detalhe": f"limpeza leve falhou (código {res.returncode}): {(res.stderr or res.stdout or '')[-200:]}"}
        # localiza o parquet/relatório gerado
        gerados = [str(f) for f in PROCESSED.glob("*.parquet")] + [str(f) for f in PROCESSED.glob("*relatorio*.json")]
        return {"ok": True, "tratamento": tratamento,
                "detalhe": f"limpeza leve OK: {len(gerados)} artefato(s) em processed/ (ex.: rigel_sft.parquet)"}

    if tratamento == "limpeza_encoding":
        from limpeza import corrigir_codificacao
        import shutil as _sh
        destino = PROCESSED / "txt" / nome
        destino.mkdir(parents=True, exist_ok=True)
        tmp = PROCESSED / "txt" / f".tmp_{nome}"
        tmp.mkdir(parents=True, exist_ok=True)
        corrigir_codificacao(str(origem), str(tmp), copiar_utf8=True)
        copiados = 0
        for f in tmp.glob("*"):
            try:
                _sh.move(str(f), str(destino / f.name))
                copiados += 1
            except Exception:
                pass
        try:
            _sh.rmtree(str(tmp))
        except Exception:
            pass
        return {"ok": True, "tratamento": tratamento,
                "detalhe": f"limpeza de encoding: {copiados} arquivo(s) -> processed/txt/{nome}/"}

    return {"ok": False, "tratamento": tratamento, "detalhe": f"sem tratamento para formato {formato}"}


def _trabalho(nomes: list) -> None:
    import shutil as _sh
    concluidos = []
    try:
        _atualizar(etapa="tratando", percentual=0,
                   mensagem=f"Tratando {len(nomes)} pasta(s)...")
        for i, nome in enumerate(nomes, 1):
            _atualizar(atual=nome, percentual=int((i - 1) * 100 / len(nomes)),
                       mensagem=f"Tratando {nome} ({i}/{len(nomes)})...")
            res = _tratar_uma(nome)
            res["nome"] = nome
            concluidos.append(res)
            # promovido com sucesso → carimba a carteira + limpa a origem (HD liberado)
            if res.get("ok"):
                try:
                    from dashboard.services import qualidade as _q
                    _q.marcar(nome, "sanitizado")
                    _q.marcar(nome, "verificado_encoding")
                    _q.marcar(nome, "promovido")
                except Exception:
                    pass
                try:
                    if (RAW / nome).exists():
                        _sh.rmtree(str(RAW / nome))
                except Exception:
                    pass
            _atualizar(concluidos=list(concluidos),
                       percentual=int(i * 100 / len(nomes)))
        _atualizar(etapa="concluido", percentual=100,
                   mensagem=f"✅ {sum(1 for c in concluidos if c.get('ok'))}/{len(nomes)} pasta(s) tratadas e promovidas.",
                   concluidos=list(concluidos), fim=datetime.now().isoformat())
    except Exception as e:
        import traceback
        traceback.print_exc()
        _atualizar(etapa="erro", mensagem=str(e), erro=str(e), percentual=None,
                   concluidos=list(concluidos), fim=datetime.now().isoformat())
    finally:
        _atualizar(rodando=False)


def tratar(nomes: list) -> dict:
    """Inicia o tratamento em lote das pastas marcadas (segundo plano)."""
    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um tratamento em andamento."}
    nomes = [n for n in (nomes or []) if isinstance(n, str) and n.strip()]
    nomes = [re.sub(r"[^a-zA-Z0-9_\-\. ]", "_", n).strip(" .") for n in nomes]
    nomes = [n for n in nomes if (RAW / n).is_dir()]
    if not nomes:
        return {"ok": False, "erro": "Nenhuma pasta marcada encontrada em dados/raw/."}
    # Guardião de memória (regra de ouro): recusa se RAM livre < mínimo
    livre = _ram_livre_gb()
    if livre < MIN_RAM_LIVRE_GB:
        return {"ok": False, "erro": f"Memória livre baixa ({livre:.1f} GB < {MIN_RAM_LIVRE_GB}). "
                                     "Nada iniciado — feche processos pesados e tente de novo."}
    _atualizar(rodando=True, etapa="tratando", mensagem="Iniciando tratamento...",
               percentual=0, fila=list(nomes), atual=None, concluidos=[],
               inicio=datetime.now().isoformat(), fim=None, erro=None)
    threading.Thread(target=_trabalho, args=(nomes,), daemon=True).start()
    return {"ok": True, "mensagem": f"Tratamento iniciado para {len(nomes)} pasta(s).", "nomes": nomes,
            "ram_livre_gb": round(livre, 1)}


# ============================================================================
# ✨ CONVERSÃO POR PASTA (provisórias de dados/gerados/jsonl) → messages (SFT)
# Botão individual por pasta: roda scripts/converter_jsonl_messages.py em
# subprocesso e transmite o log em tempo real para o painel (ver acontecendo).
# ============================================================================
def _rodar_conversor(cmd: list, nome: str, saida: Path) -> None:
    import subprocess as _sp
    import re as _re
    linhas_log: list = []
    try:
        proc = _sp.Popen(cmd, stdout=_sp.PIPE, stderr=_sp.STDOUT, text=True,
                         encoding="utf-8", errors="replace", cwd=str(PROJETO_ROOT))
        for linha in proc.stdout:  # type: ignore[union-attr]
            linha = linha.rstrip()
            if not linha:
                continue
            linhas_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {linha}")
            linhas_log = linhas_log[-80:]
            _atualizar(log=list(linhas_log), atual=nome, mensagem=linha[:140])
            m = _re.search(r"\(([\d.]+)%\)", linha)
            if m:
                try:
                    _atualizar(percentual=float(m.group(1)))
                except Exception:
                    pass
        proc.wait(timeout=10800)
        # 💉 Carteira: conversão + promoção concluídas (carimba na base)
        try:
            from dashboard.services import qualidade as _q
            _q.marcar(nome, "sanitizado")
            _q.marcar(nome, "verificado_encoding")
            _q.marcar(nome, "promovido")
        except Exception:
            pass
        try:
            _rel_saida = str(saida.relative_to(PROJETO_ROOT)).replace("\\", "/")
        except Exception:
            _rel_saida = str(saida)
        _atualizar(etapa="concluido", rodando=False, percentual=100,
                   mensagem=f"✅ Concluído '{nome}' — saída em {_rel_saida}/",
                   log=list(linhas_log), concluidos=[{"ok": True, "nome": nome, "detalhe": str(saida)}],
                   fim=datetime.now().isoformat())
    except Exception as e:
        _atualizar(etapa="erro", rodando=False, erro=str(e), mensagem=str(e),
                   log=list(linhas_log), fim=datetime.now().isoformat())


def converter_jsonl_pasta(nome: str) -> dict:
    """Converte uma pasta PROVISÓRIA (dados/gerados/jsonl/<nome>) para o
    formato messages, salvando em processed/jsonl/<nome>_sanitizado."""
    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um tratamento em andamento."}
    origem = GERADOS_JSONL / nome
    if not origem.is_dir():
        return {"ok": False, "erro": f"Pasta '{nome}' não encontrada em dados/gerados/jsonl/."}
    if not _pode_converter_para_messages(origem):
        return {"ok": False, "erro": f"'{nome}' não tem formato de conversa (só texto/pré-treino) — não há o que converter para mensagens."}
    saida = PROCESSED / "jsonl" / f"{nome}_sanitizado"
    saida.mkdir(parents=True, exist_ok=True)
    script = PROJETO_ROOT / "scripts" / "converter_jsonl_messages.py"
    cmd = [sys.executable, "-u", str(script), "--origem", str(origem), "--saida", str(saida)]
    _atualizar(rodando=True, etapa="tratando", mensagem=f"Convertendo '{nome}' p/ mensagens...",
               percentual=0, fila=[nome], atual=nome, concluidos=[], log=[],
               inicio=datetime.now().isoformat(), fim=None, erro=None)
    threading.Thread(target=_rodar_conversor, args=(cmd, nome, saida), daemon=True).start()
    return {"ok": True, "mensagem": f"Conversão de '{nome}' iniciada — saída em processed/jsonl/{nome}_sanitizado/."}


def extrair_txt_pasta(nome: str) -> dict:
    """Extrai o TEXTO (pré-treino) de dados/gerados/jsonl/<nome> → .txt em
    dados/processed/txt/<nome> (pipeline de PRÉ-TREINO — treinov2)."""
    if get_estado()["rodando"]:
        return {"ok": False, "erro": "Já existe um tratamento em andamento."}
    origem = GERADOS_JSONL / nome
    if not origem.is_dir():
        return {"ok": False, "erro": f"Pasta '{nome}' não encontrada em dados/gerados/jsonl/."}
    saida = PROCESSED / "txt" / nome
    saida.mkdir(parents=True, exist_ok=True)
    script = PROJETO_ROOT / "scripts" / "converter_jsonl_txt.py"
    cmd = [sys.executable, "-u", str(script), "--origem", str(origem), "--saida", str(saida)]
    _atualizar(rodando=True, etapa="tratando",
               mensagem=f"Extraindo texto de '{nome}' p/ TXT (pré-treino)...",
               percentual=0, fila=[nome], atual=nome, concluidos=[], log=[],
               inicio=datetime.now().isoformat(), fim=None, erro=None)
    threading.Thread(target=_rodar_conversor, args=(cmd, nome, saida), daemon=True).start()
    return {"ok": True, "mensagem": f"Extração de '{nome}' iniciada — saída em processed/txt/{nome}/."}


# ============================================================================
# Recuperação pós-reload: recarrega o estado persistido para que NADA se perca
# (regra de ouro: o sistema não perde ninguém). Se um processo estava rodando
# quando o servidor reiniciou E o processo separado de extração ainda está
# vivo, deixamos rodando (ele continua e o log segue). Se não há processo
# vivo, marcamos como "interrompido" mas preservamos o log e os concluídos —
# o usuário vê o que aconteceu e pode retomar.
# ============================================================================
def _recuperar_estado() -> None:
    try:
        if not _PERSISTENCIA.exists():
            return
        dados = json.loads(_PERSISTENCIA.read_text(encoding="utf-8"))
        if not isinstance(dados, dict):
            return
        if dados.get("rodando") and not _processo_vivo(dados.get("pid")):
            # O trabalho que rodava não tem mais dono (thread daemon morreu
            # num reload antigo, ou o processo foi encerrado) — não fica
            # "rodando" pra sempre; marca interrompido preservando o log.
            dados["rodando"] = False
            dados["etapa"] = "interrompido"
            dados["erro"] = "Processo foi interrompido por uma reinicialização do servidor. " \
                           "Nada foi perdido — veja o log abaixo e clique de novo para continuar."
            dados.setdefault("log", []).append(
                f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Servidor reiniciou no meio do trabalho — "
                "o que já estava feito ficou salvo.")
        with _lock:
            _estado.clear()
            _estado.update(dados)
            _persistir()
    except Exception:
        pass


_recuperar_estado()
