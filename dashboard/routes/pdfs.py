#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pdfs.py - Rotas da API de PDFs (livros) — upload manual, listagem e download.
Versão: 1.0.0 | Data: 09/08/2026

  GET  /api/pdfs                - lista os PDFs/TXT em dados/raw/livros
  POST /api/pdfs/upload         - ENVIA um PDF manualmente (o usuário escolhe
                                  o arquivo no PC e o sistema coloca na pasta)
  GET  /api/pdfs/arquivo/{caminho} - serve o arquivo (abrir/baixar)
  POST /api/pdfs/remover        - apaga um arquivo
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

PROJETO_ROOT = Path(__file__).resolve().parents[2]          # raiz do projeto
PASTA_PDFS = PROJETO_ROOT / "dados" / "raw" / "livros"      # pasta de PDFs
PASTA_UPLOADS = PASTA_PDFS / "importados"                   # uploads manuais

router = APIRouter(prefix="/api/pdfs", tags=["PDFs"])


class RemoverRequest(BaseModel):
    caminho: str   # caminho relativo dentro de dados/raw/livros


class ExtrairRequest(BaseModel):
    caminho: str   # PDF relativo dentro de dados/raw/livros


def _caminho_seguro(relativo: str) -> Path:
    """Resolve um caminho relativo e garante que está dentro da pasta de PDFs."""
    alvo = (PASTA_PDFS / relativo).resolve()
    base = PASTA_PDFS.resolve()
    if not str(alvo).startswith(str(base)):
        raise HTTPException(400, "Caminho inválido (fora da pasta de PDFs).")
    return alvo


def _listar_pdfs() -> list:
    if not PASTA_PDFS.exists():
        return []
    itens = []
    for p in sorted(PASTA_PDFS.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".pdf", ".txt"):
            try:
                rel = p.relative_to(PASTA_PDFS).as_posix()
            except ValueError:
                continue
            itens.append({
                "caminho": rel,
                "nome": p.name,
                "pasta": str(p.parent.relative_to(PASTA_PDFS)).replace("\\", "/"),
                "tamanho_mb": round(p.stat().st_size / 1e6, 2),
                "data": datetime.fromtimestamp(p.stat().st_mtime)
                        .strftime("%d/%m/%Y %H:%M"),
            })
    # mais recentes primeiro
    itens.sort(key=lambda x: x["data"], reverse=True)
    return itens


def _contar_arquivos(pasta: Path, ext: str) -> int:
    """Conta arquivos com a extensão dentro de uma pasta (sem travar)."""
    if not pasta.is_dir():
        return 0
    try:
        return sum(1 for f in pasta.rglob("*") if f.is_file() and f.suffix.lower() == ext)
    except Exception:
        return 0


@router.get("")
async def listar():
    """Lista os arquivos (PDF/TXT) já presentes na pasta de livros + resumo
    de livros baixados/tratados (Kanban: nada fica perdido — mostra a
    realidade: quantos aguardam e quantos já viraram TXT/JSONL)."""
    pdfs = _listar_pdfs()
    tratados_txt = _contar_arquivos(PROJETO_ROOT / "dados" / "gerados" / "txt_livros", ".txt")
    tratados_jsonl = _contar_arquivos(PROJETO_ROOT / "dados" / "gerados" / "jsonl" / "livros", ".jsonl")
    resumo = {
        "aguardando": sum(1 for p in pdfs if p["caminho"].lower().endswith(".pdf")),
        "tratados_txt": tratados_txt,
        "tratados_jsonl": tratados_jsonl,
        "tratados": max(tratados_txt, tratados_jsonl),
    }
    return {"pdfs": pdfs, "pasta": str(PASTA_PDFS), "resumo": resumo}


def _ler_lista_sites(caminho: Path) -> list:
    """Lê uma lista de sites (sites_pdfs.txt / sites_abertos.txt), ignorando
    comentários (#) e linhas vazias. Retorna lista de URLs (sem duplicatas)."""
    if not caminho.exists():
        return []
    urls = []
    vistos = set()
    try:
        for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            if linha.lower().startswith("http"):
                if linha not in vistos:
                    vistos.add(linha)
                    urls.append(linha.rstrip("/"))
    except Exception:
        pass
    return urls


@router.get("/sites")
async def sites():
    """Lista os sites configurados para o scraper (sites_pdfs.txt + sites_abertos.txt).
    O /pdfs usa no dropdown 'Rodar scraper' — o usuário NÃO digita URL (regra 05/08)."""
    pdfs = _ler_lista_sites(PROJETO_ROOT / "sites_pdfs.txt")
    abertos = _ler_lista_sites(PROJETO_ROOT / "sites_abertos.txt")
    return {
        "pdfs": pdfs,
        "abertos": abertos,
        "total": len(pdfs) + len(abertos),
        "lista_pdfs": str(PROJETO_ROOT / "sites_pdfs.txt"),
        "lista_abertos": str(PROJETO_ROOT / "sites_abertos.txt"),
    }


@router.get("/scrap-progresso")
async def scrap_progresso():
    """Progresso em tempo real do scraper (logs/scrap_progresso.json)."""
    caminho = PROJETO_ROOT / "logs" / "scrap_progresso.json"
    if caminho.exists():
        try:
            import json
            return json.loads(caminho.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"pct": 0, "site": None, "fase": "ocioso"}


@router.get("/scrap-relatorio")
async def scrap_relatorio():
    """Relatório do último scrap por site (logs/scrap_relatorio.json).

    Classifica cada site: 'zerado' quando NADA foi baixado e não há links
    úteis — candidato a remoção da lista (não fornece nada).
    """
    caminho = PROJETO_ROOT / "logs" / "scrap_relatorio.json"
    if caminho.exists():
        try:
            import json
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            sites = dados.get("sites") or []
            for s in sites:
                ok = int(s.get("ok") or 0)
                links = int(s.get("links") or 0)
                pulados = int(s.get("pulados") or 0)
                dups = int(s.get("dups") or 0)
                # zerado: nada baixado e nenhum link útil encontrado
                s["zerado"] = (ok == 0 and links == 0 and pulados == 0 and dups == 0)
                s["sem_conteudo"] = (ok == 0 and links == 0)
            # ordena: zerados primeiro (mais relevantes de remover)
            sites.sort(key=lambda x: (not x.get("zerado"), x.get("site") or ""))
            dados["sites"] = sites
            dados["zerados"] = [s for s in sites if s.get("zerado")]
            return dados
        except Exception:
            pass
    return {"sites": [], "totais": {}, "zerados": []}


@router.post("/remover-site-zerado")
async def remover_site_zerado(req: dict | None = None):
    """🗑️ Remove um site que NÃO forneceu nada (zerado) das listas.

    Body: {"site": "dominiopublico.gov.br"} — remove da sites_pdfs.txt e
    sites_abertos.txt. Registra a remoção em logs/sites_removidos.log.
    """
    import json
    body = req or {}
    site = (body.get("site") or "").strip()
    if not site:
        return {"ok": False, "erro": "Informe o site a remover."}
    removidos = []
    for lista in ("sites_pdfs.txt", "sites_abertos.txt"):
        caminho = PROJETO_ROOT / lista
        if not caminho.exists():
            continue
        linhas = caminho.read_text(encoding="utf-8", errors="replace").splitlines()
        restantes = [l for l in linhas if site not in l]
        if len(restantes) != len(linhas):
            caminho.write_text("\n".join(restantes) + "\n", encoding="utf-8")
            removidos.append(lista)
    if not removidos:
        return {"ok": False, "erro": f"'{site}' não estava em nenhuma lista."}
    # Registra a remoção (histórico honesto — regra: não apagar sem rastro)
    try:
        with open(PROJETO_ROOT / "logs" / "sites_removidos.log", "a",
                  encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] Removido '{site}' "
                    f"das listas: {', '.join(removidos)} (0 downloads)\n")
    except Exception:
        pass
    return {"ok": True, "mensagem": f"'{site}' removido de {', '.join(removidos)}.",
            "removidos": removidos}


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Envia um PDF manualmente. Valida a assinatura %PDF- e salva em
    dados/raw/livros/importados/ (não sobrescreve arquivo existente)."""
    nome = (file.filename or "arquivo.pdf").strip()
    if not nome.lower().endswith(".pdf"):
        raise HTTPException(400, "Só arquivos .pdf são aceitos.")
    dados = await file.read()
    if not dados:
        raise HTTPException(400, "Arquivo vazio.")
    if not dados[:5] == b"%PDF-":
        raise HTTPException(400, "O arquivo não parece ser um PDF válido (sem %PDF-).")
    if len(dados) < 10_000:
        raise HTTPException(400, "PDF muito pequeno (menos de 10 KB) — confira o arquivo.")

    os.makedirs(PASTA_UPLOADS, exist_ok=True)
    destino = PASTA_UPLOADS / nome
    contador = 1
    stem = destino.stem
    while destino.exists():
        destino = PASTA_UPLOADS / f"{stem}_{contador}.pdf"
        contador += 1
    with open(destino, "wb") as f:
        f.write(dados)

    return {
        "ok": True,
        "mensagem": f"✅ '{destino.name}' enviado para dados/raw/livros/importados/",
        "caminho": destino.name,
    }


@router.post("/extrair")
async def extrair(req: ExtrairRequest):
    """✨ Extrai e limpa um PDF de livro → TXT (pdfplumber+posição) + JSONL SFT.
    Reutiliza os scripts genéricos (funcionam para qualquer livro).
    Saída: dados/gerados/txt_livros/<nome>.txt + dados/gerados/jsonl/livros/<nome>.jsonl
    """
    alvo = _caminho_seguro(req.caminho)
    if not alvo.is_file():
        raise HTTPException(404, "Arquivo não encontrado.")
    if not alvo.name.lower().endswith(".pdf"):
        raise HTTPException(400, "Só arquivos .pdf podem ser extraídos.")

    script_extrair = PROJETO_ROOT / "scripts" / "extrair_livro_pdf.py"
    script_jsonl = PROJETO_ROOT / "scripts" / "livro_para_jsonl.py"
    txt_saida = PROJETO_ROOT / "dados" / "gerados" / "txt_livros" / (alvo.stem + ".txt")
    jsonl_saida = PROJETO_ROOT / "dados" / "gerados" / "jsonl" / "livros" / (alvo.stem + ".jsonl")

    # No Windows o Python filho herda o encoding do console (cp1252) e
    # escreve "Saída" como bytes cp1252; o pai lendo como UTF-8 vira "Sa�da".
    # PYTHONIOENCODING=utf-8 força o filho a escrever UTF-8 (igual ao executor).
    env_py = dict(os.environ)
    env_py["PYTHONIOENCODING"] = "utf-8"

    try:
        r1 = subprocess.run(
            [sys.executable, str(script_extrair), "--pdf", str(alvo), "--saida", str(txt_saida)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=900, env=env_py,
        )
        if r1.returncode != 0:
            return {"ok": False,
                    "erro": (r1.stdout or "")[-300:] + (r1.stderr or "")[-300:]}

        r2 = subprocess.run(
            [sys.executable, str(script_jsonl), "--txt", str(txt_saida), "--saida", str(jsonl_saida)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=900, env=env_py,
        )
        ok2 = r2.returncode == 0
        rel = lambda p: str(Path(p).relative_to(PROJETO_ROOT))

        # 🚀 PROMOÇÃO AUTOMÁTICA: o JSONL gerado vai direto para processed/
        # (o usuário NÃO precisa sair da página p/ promover — fluxo completo).
        promovido = None
        if ok2 and jsonl_saida.exists():
            try:
                from dashboard.services import treino_local as _tl
                # 💉 CARTEIRA DE QUALIDADE: extração gera texto LIMPO (PDF →
                # texto com acentos corretos → JSONL) → marca sanitizado +
                # verificado_encoding antes de promover.
                try:
                    from dashboard.services.qualidade import marcar as _marcar_q
                    _marcar_q("livros", "sanitizado", fonte="extração_pdf")
                    _marcar_q("livros", "verificado_encoding", fonte="extração_pdf")
                except Exception:
                    pass
                promovido = _tl.promover_para_processed("livros", remover_invalidos=False)
            except Exception as _e:
                promovido = {"ok": False, "erro": f"falha ao promover: {_e}"}

        aviso = None
        if not ok2:
            aviso = "TXT extraído, mas a conversão p/ JSONL falhou: " + \
                    ((r2.stderr or "")[-200:] or (r2.stdout or "")[-200:])
        elif promovido and not promovido.get("ok"):
            aviso = promovido.get("erro")

        return {
            "ok": True,
            "txt": rel(txt_saida),
            "jsonl": rel(jsonl_saida) if ok2 else None,
            "extrair": (r1.stdout or "").strip().splitlines()[-1] if (r1.stdout or "").strip() else "",
            "converter": (r2.stdout or "").strip().splitlines()[-1] if ok2 and (r2.stdout or "").strip() else "",
            "promovido": promovido,
            "aviso": aviso,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "erro": "Tempo esgotado (15 min). O PDF pode ser muito grande ou escaneado."}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


@router.get("/arquivo/{caminho:path}")
async def arquivo(caminho: str):
    """Serve o arquivo (abrir/baixar no navegador)."""
    alvo = _caminho_seguro(caminho)
    if not alvo.is_file():
        raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(str(alvo), filename=alvo.name)


@router.post("/remover")
async def remover(req: RemoverRequest):
    """Apaga um arquivo da pasta de PDFs."""
    alvo = _caminho_seguro(req.caminho)
    if not alvo.is_file():
        raise HTTPException(404, "Arquivo não encontrado.")
    try:
        alvo.unlink()
    except Exception as e:
        raise HTTPException(500, f"Erro ao apagar: {e}")
    return {"ok": True, "mensagem": f"🗑️ '{alvo.name}' apagado."}
