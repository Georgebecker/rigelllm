#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
treino_colab.py - Rotas da página "Treino Colab" (preparação do notebook).

O dashboard NÃO controla o Colab diretamente (ambientes separados). O que esta
rota faz: lista os datasets VALIDADOS (processed) e gera uma cópia do
RigelSLM_Colab.ipynb já configurada com o dataset + parâmetros escolhidos —
o usuário abre o notebook gerado no Colab e roda.

  GET  /api/treino_colab/datasets   - datasets processed (para o seletor)
  POST /api/treino_colab/gerar      - gera notebook configurado (colab/*.ipynb)
"""
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from dashboard.services import treino_local

router = APIRouter(prefix="/api/treino_colab", tags=["Treino Colab"])

PROJETO_ROOT = Path(__file__).resolve().parent.parent.parent
NOTEBOOK_BASE = PROJETO_ROOT / "RigelSLM_Colab.ipynb"
PASTA_SAIDA = PROJETO_ROOT / "colab"


class GerarRequest(BaseModel):
    modo: str = "jsonl"            # "texto" | "jsonl" | "parquet"
    dataset: str = ""              # jsonl: dataset validado (processed)
    dados: str = ""                # caminho dos dados (vazio = padrão do modo)
    max_arquivos: int = 5
    epochs: int = 3
    lr: float = 1e-4
    accum: int = 4
    batch_size: int = 16
    save_every: int = 50
    num_workers: int = 2
    precision: str = "amp"
    preload: bool = False
    resume: bool = True
    testar_apos: bool = True
    converter_gguf: bool = False
    drive_path: str = "/content/drive/MyDrive/rigelllm"


def _dados_padrao(req: GerarRequest) -> str:
    """Caminho padrão dos dados por modo (se o usuário não preencheu)."""
    if req.dados and req.dados.strip():
        return req.dados.strip()
    if req.modo == "texto":
        return "dados/processed"
    if req.modo == "parquet":
        return "/content/dados/processed"
    return (f"dados/processed/jsonl/{req.dataset}"
            if req.dataset else "dados/processed/jsonl")


def _comando_treino(req: GerarRequest) -> str:
    """Comando `!...` da célula de treino conforme o modo (texto/jsonl/parquet)."""
    drive = req.drive_path.rstrip("/")
    dados = _dados_padrao(req)
    if req.modo == "texto":
        cmd = (f"!cd {drive} && python treino.py --dados {dados} "
               f"--max-arquivos {req.max_arquivos} "
               f"--batch-size {req.batch_size} --save-every {req.save_every}")
        if req.resume:
            cmd += " --resume"
        return cmd
    if req.modo == "parquet":
        cmd = (f"!cd {drive} && python treino_colab.py --dados {dados} "
               f"--max-arquivos {req.max_arquivos} --preload --no-interactive "
               f"--num-workers {req.num_workers} --precision {req.precision} "
               f"--batch-size {req.batch_size} --save-every {req.save_every}")
        if req.resume:
            cmd += " --resume"
        return cmd
    # jsonl (SFT)
    cmd = (f'!cd {drive} && yes "n" | python treinar_com_jsonl.py '
           f'--dados "{dados}" --max-arquivos {req.max_arquivos} --epochs {req.epochs} '
           f'--origem colab')
    if req.resume:
        cmd += " --resume"
    return cmd


def _celula_params(req: GerarRequest) -> str:
    """Célula 5 (parâmetros) por modo — informativa/ajustável no notebook."""
    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    dados = _dados_padrao(req)
    if req.modo == "texto":
        return (
            "# 5. Configurar parâmetros do treino CAUSAL (texto .txt)\n"
            f"# (gerado pelo dashboard em {data})\n\n"
            f'PASTA_DADOS = "{dados}"   # pasta com .txt\n'
            f"MAX_ARQUIVOS = {req.max_arquivos}   # 0 = todos\n"
            f"BATCH_SIZE = {req.batch_size}\n"
            f"SAVE_EVERY = {req.save_every}\n"
            f"RESUME = {str(req.resume).lower()}\n\n"
            'print("📋 Parâmetros (texto):", PASTA_DADOS, "| max:", MAX_ARQUIVOS, '
            '"| batch:", BATCH_SIZE, "| save:", SAVE_EVERY)'
        )
    if req.modo == "parquet":
        return (
            "# 5. Configurar parâmetros do treino PARQUET\n"
            f"# (gerado pelo dashboard em {data})\n\n"
            f'PASTA_DADOS = "{dados}"   # parquet\n'
            f"MAX_ARQUIVOS = {req.max_arquivos}   # 0 = todos\n"
            f"BATCH_SIZE = {req.batch_size}\n"
            f"SAVE_EVERY = {req.save_every}\n"
            f"NUM_WORKERS = {req.num_workers}\n"
            f'PRECISION = "{req.precision}"\n'
            f"RESUME = {str(req.resume).lower()}\n\n"
            'print("📋 Parâmetros (parquet):", PASTA_DADOS, "| max:", MAX_ARQUIVOS, '
            '"| batch:", BATCH_SIZE, "| workers:", NUM_WORKERS, "| precision:", PRECISION)'
        )
    # jsonl (SFT)
    return (
        "# 5. Configurar parâmetros do treino SFT\n"
        f"# (gerado pelo dashboard em {data})\n\n"
        f'PASTA_DADOS = "{dados}"   # dataset escolhido no dashboard\n'
        f"MAX_ARQUIVOS = {req.max_arquivos}   # 0 = todos (CUIDADO)\n"
        f"EPOCHS = {req.epochs}\n"
        "BATCH_SIZE = 8\n"
        "SEQ_LEN = 512\n"
        f"LR = {req.lr}\n"
        f"ACCUM = {req.accum}\n"
        f"RESUME = {str(req.resume).lower()}\n"
        f"TESTAR_APOS = {str(req.testar_apos).lower()}\n"
        f"CONVERTER_GGUF = {str(req.converter_gguf).lower()}\n\n"
        'print("📋 Parâmetros (gerados pelo dashboard):")\n'
        'print(f"   📁 Dados: {PASTA_DADOS} | max-arquivos: {MAX_ARQUIVOS}")\n'
        'print(f"   🔄 Épocas: {EPOCHS} | batch: {BATCH_SIZE} | seq: {SEQ_LEN}")\n'
        'print(f"   🎯 LR: {LR} | accum: {ACCUM} | resume: {RESUME}")'
    )


def _celula_treino(req: GerarRequest) -> str:
    """Célula 6 (executar treino) — comando por modo."""
    data = datetime.now().strftime("%d/%m/%Y %H:%M")
    rotulo = {"texto": "CAUSAL (texto)", "parquet": "PARQUET",
              "jsonl": "SFT (JSONL)"}.get(req.modo, "SFT (JSONL)")
    return (
        f"# 6. Executar treino {rotulo} — comando gerado pelo dashboard em {data}\n"
        'print("=" * 60)\n'
        f'print("   🧠 INICIANDO TREINO {rotulo}")\n'
        'print("=" * 60)\n'
        f"{_comando_treino(req)}\n"
        'print()\nprint("✅ Treino encerrado. Confira a saída acima.")'
    )


@router.get("/datasets")
async def datasets():
    """Lista datasets VALIDADOS (processed) para treinar no Colab."""
    lista = treino_local.listar_datasets(usar_cache=True)
    if not lista:
        treino_local.iniciar_escaneamento_estrutura()
    return {"datasets": [d for d in lista if d.get("local") == "processed"]}


def _trocar_celula(cells: list, marcador: str, novo: str) -> bool:
    """Substitui o source da 1ª célula que contém `marcador` pelo novo texto."""
    for c in cells:
        src = "".join(c.get("source", []))
        if marcador in src:
            c["source"] = novo.splitlines(keepends=True)
            return True
    return False


@router.post("/gerar")
async def gerar(req: GerarRequest):
    """Gera o notebook configurado com o modo/dataset/parâmetros escolhidos."""
    if not NOTEBOOK_BASE.exists():
        return {"ok": False, "erro": f"Notebook base não encontrado: {NOTEBOOK_BASE.name}"}
    try:
        nb = json.loads(NOTEBOOK_BASE.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "erro": f"Erro ao ler notebook base: {e}"}

    # Célula 5 — parâmetros (por modo)
    params_src = _celula_params(req)

    # Célula 6 — comando de treino (por modo)
    treino_src = _celula_treino(req)

    # Célula 2 — montagem do Drive (atualiza DRIVE_PATH p/ o layout do usuário)
    mount_src = (
        "# 2. Montar Google Drive e ir para a pasta do projeto\n"
        "from google.colab import drive\n"
        "drive.mount('/content/drive')\n\n"
        f'DRIVE_PATH = "{req.drive_path}"\n'
        "os.chdir(DRIVE_PATH)\n\n"
        'print(f"📁 Diretório de trabalho: {os.getcwd()}")\n'
        'print(f"📄 Arquivos: {os.listdir()[:15]}...")\n'
        'print()\n'
        'print("📂 Pastas encontradas:")\n'
        "for item in sorted(os.listdir()):\n"
        "    if os.path.isdir(item):\n"
        "        qtd = len(os.listdir(item)) if os.path.exists(item) else 0\n"
        '        print(f"   📁 {item}/ ({qtd} arquivos)")\n'
        "    else:\n"
        '        print(f"   📄 {item}")'
    )

    cells = nb.get("cells", [])
    ok_params = _trocar_celula(cells, "PASTA_DADOS =", params_src)
    ok_mount = _trocar_celula(cells, "DRIVE_PATH =", mount_src)
    ok_treino = _trocar_celula(cells, "INICIANDO TREINO SFT", treino_src)

    PASTA_SAIDA.mkdir(exist_ok=True)
    saida = PASTA_SAIDA / "RigelSLM_Colab_pronto.ipynb"
    saida.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")

    rotulos = {"texto": "CAUSAL (texto)", "parquet": "PARQUET", "jsonl": "SFT (JSONL)"}
    comando = _comando_treino(req)
    return {
        "ok": True,
        "arquivo": str(saida),
        "dataset": req.dataset,
        "modo": req.modo,
        "rotulo": rotulos.get(req.modo, "SFT (JSONL)"),
        "notebook_atualizado": bool(ok_params and ok_mount and ok_treino),
        "data": datetime.now().isoformat(),
        "drive_path": req.drive_path,
        "comando_colab": (
            "# 1) Montar o Drive (onde estão os dados do projeto):\n"
            "from google.colab import drive\n"
            "drive.mount('/content/drive')\n"
            f"%cd {req.drive_path}\n\n"
            "# 2) Comando de treino (copie e rode):\n"
            f"{comando.lstrip('!').strip()}"
        ),
        "instrucao": (
            "O Colab não recebe comandos do dashboard (são ambientes separados). "
            "Coloque o notebook gerado no Drive (ou use File → Upload notebook) e "
            "abra com o Colab; depois é só executar as células em ordem."
        ),
    }
