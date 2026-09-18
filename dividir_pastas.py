import os
import shutil
import math
import argparse
import re
from tqdm import tqdm

# =============================================================================
# CONFIGURAÇÕES (podem ser sobrescritas por argumentos)
# =============================================================================
PASTA_BASE = r"D:\Projetos\rigelllm\dados\processed"
# Limites POR TIPO (regra de ouro 18/08/2026): TXT=1000, JSONL=5000, PARQUET=5000
LIMITES_POR_TIPO = {".txt": 1000, ".jsonl": 5000, ".parquet": 5000}
LIMITE_ARQUIVOS = 5000  # Máximo padrão por pasta (JSONL/PARQUET)

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def formatar_tamanho(bytes_tamanho: int) -> str:
    """Converte bytes para uma string legível (KB, MB, GB)."""
    for unidade in ['B', 'KB', 'MB', 'GB']:
        if bytes_tamanho < 1024.0:
            return f"{bytes_tamanho:.2f} {unidade}"
        bytes_tamanho /= 1024.0
    return f"{bytes_tamanho:.2f} TB"

def ja_foi_dividida(nome_pasta: str) -> bool:
    """
    Verifica se uma pasta já foi dividida (termina com _a, _b, _c, etc.)
    Isso evita reprocessar pastas que já foram divididas.
    """
    return bool(re.search(r'_[a-z]$', nome_pasta))

def contar_arquivos_na_raiz(caminho_pasta: str) -> int:
    """Conta quantos arquivos existem na raiz da pasta (ignora subpastas)."""
    if not os.path.isdir(caminho_pasta):
        return 0
    return len([f for f in os.listdir(caminho_pasta) if os.path.isfile(os.path.join(caminho_pasta, f))])

def _limite_tipo(caminho_pasta: str, limite_default: int) -> int:
    """Limite conforme o TIPO dominante dos arquivos (regra de ouro 18/08).

    TXT → 1000 | JSONL → 5000 | PARQUET → 5000. Se não identificar, usa o
    limite padrão informado."""
    cont = {e: 0 for e in LIMITES_POR_TIPO}
    try:
        for f in os.listdir(caminho_pasta):
            e = os.path.splitext(f)[1].lower()
            if e in cont:
                cont[e] += 1
    except Exception:
        pass
    dom = max(cont, key=lambda k: cont[k])
    if cont[dom] == 0:
        return limite_default
    return LIMITES_POR_TIPO[dom]


def dividir_pasta_recursivamente(caminho_pasta: str, limite: int, dry_run: bool = False) -> None:
    """
    Verifica se a pasta atual tem mais que 'limite' arquivos.
    Se sim, divide os arquivos em subpastas com sufixos _a, _b, ...
    Depois, chama-se recursivamente para cada subpasta (para processar subníveis).

    O limite efetivo é POR TIPO de arquivo (TXT=1000, JSONL/PARQUET=5000).
    """
    # aplica o limite conforme o tipo dominante da pasta
    limite = _limite_tipo(caminho_pasta, limite)
    nome_pasta = os.path.basename(caminho_pasta)

    # Pula pastas que já foram divididas (para não reprocessar)
    if ja_foi_dividida(nome_pasta):
        return

    # Pula se não for um diretório
    if not os.path.isdir(caminho_pasta):
        return

    # Lista apenas arquivos na raiz (não subpastas)
    arquivos = [f for f in os.listdir(caminho_pasta) if os.path.isfile(os.path.join(caminho_pasta, f))]
    total_arquivos = len(arquivos)

    if total_arquivos == 0:
        # Não tem arquivos na raiz, mas pode ter subpastas – vamos processá-las
        for item in os.listdir(caminho_pasta):
            sub_caminho = os.path.join(caminho_pasta, item)
            if os.path.isdir(sub_caminho):
                dividir_pasta_recursivamente(sub_caminho, limite, dry_run)
        return

    if total_arquivos <= limite:
        # Está dentro do limite – mas ainda pode ter subpastas para processar
        for item in os.listdir(caminho_pasta):
            sub_caminho = os.path.join(caminho_pasta, item)
            if os.path.isdir(sub_caminho):
                dividir_pasta_recursivamente(sub_caminho, limite, dry_run)
        return

    # Se chegou aqui, a pasta tem mais arquivos que o limite
    num_partes = math.ceil(total_arquivos / limite)
    print(f"\n📁 Pasta: {caminho_pasta}")
    print(f"   📊 Total de arquivos: {total_arquivos}")
    print(f"   ⚠️ Excede o limite ({limite}). Será dividida em {num_partes} parte(s).")
    if dry_run:
        print("   🔍 DRY-RUN: Nenhum arquivo será movido.")

    # Ordena os arquivos (para manter consistência)
    arquivos.sort()

    # Pasta base para criar as subpastas (usamos o mesmo diretório)
    dir_pai = os.path.dirname(caminho_pasta)

    # As novas pastas terão o nome da pasta atual + sufixo _a, _b, ...
    # A primeira parte (índice 0) fica na pasta original (sem sufixo)
    # As demais vão para pastas com sufixo
    pastas_criadas = {}

    # Barra de progresso
    for i, nome_arquivo in enumerate(tqdm(arquivos, desc=f"   Movendo", unit="arq")):
        idx_parte = (i // limite) + 1  # 1-based

        if idx_parte == 1:
            # Mantém na pasta original
            destino_pasta = caminho_pasta
        else:
            # Cria sufixo: a=2, b=3, c=4, ...
            sufixo = chr(ord('a') + idx_parte - 2)  # a para parte 2, b para parte 3, etc.
            nome_nova_pasta = f"{nome_pasta}_{sufixo}"
            destino_pasta = os.path.join(dir_pai, nome_nova_pasta)

            # Cria a pasta se ainda não foi criada
            if destino_pasta not in pastas_criadas:
                if not dry_run:
                    os.makedirs(destino_pasta, exist_ok=True)
                pastas_criadas[destino_pasta] = True
                print(f"\n   📂 Criando nova pasta: {nome_nova_pasta}")

        src = os.path.join(caminho_pasta, nome_arquivo)
        dst = os.path.join(destino_pasta, nome_arquivo)

        if dry_run:
            # Em dry-run, apenas mostra o que seria feito
            if i % 500 == 0:
                print(f"      [DRY-RUN] Moveria: {nome_arquivo} -> {os.path.basename(destino_pasta)}")
        else:
            try:
                shutil.move(src, dst)
                if i % 500 == 0:
                    print(f"      Movido: {nome_arquivo} -> {os.path.basename(destino_pasta)}")
            except Exception as e:
                print(f"\n   ❌ ERRO ao mover {nome_arquivo}: {e}")

    # Após dividir, processamos as subpastas (que agora podem ter sido criadas)
    # Mas primeiro, vamos processar as subpastas originais (se houver)
    for item in os.listdir(caminho_pasta):
        sub_caminho = os.path.join(caminho_pasta, item)
        if os.path.isdir(sub_caminho):
            # Se a subpasta for uma das que acabamos de criar (com sufixo), processamos também
            dividir_pasta_recursivamente(sub_caminho, limite, dry_run)

    # Também processamos as novas pastas que criamos (se houver)
    for pasta_dest in pastas_criadas.keys():
        dividir_pasta_recursivamente(pasta_dest, limite, dry_run)

# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Divide pastas com muitos arquivos em partes de até 5000 arquivos (recursivo).")
    parser.add_argument("--base", type=str, default=PASTA_BASE, help="Pasta base para processar (padrão: D:\\Projetos\\rigelllm\\dados\\processed)")
    parser.add_argument("--limite", type=int, default=LIMITE_ARQUIVOS, help="Número máximo de arquivos por pasta (padrão: 5000)")
    parser.add_argument("--dry-run", action="store_true", help="Apenas simula, não move arquivos")
    args = parser.parse_args()

    caminho_base = args.base
    limite = args.limite
    dry_run = args.dry_run

    if not os.path.exists(caminho_base):
        print(f"❌ ERRO: Caminho não encontrado: {caminho_base}")
        return

    print("=" * 70)
    print("🚀 DIVISOR DE PASTAS RECURSIVO DO RIGELSLM")
    print(f"📁 Pasta base: {caminho_base}")
    print(f"📊 Limite máximo de arquivos por pasta: {limite}")
    if dry_run:
        print("🔍 MODO DRY-RUN: Nenhum arquivo será movido (apenas simulação).")
    print("=" * 70)

    confirm = input("\n⚠️ ATENÇÃO: Este script vai MOVER os arquivos permanentemente.\n   Pastas com mais de 5000 arquivos serão divididas recursivamente.\n\nDeseja continuar? (s/N): ").strip().lower()

    if confirm != 's':
        print("\n⏹️ Operação cancelada pelo usuário.")
        return

    print("\n🔍 Iniciando varredura recursiva...")
    dividir_pasta_recursivamente(caminho_base, limite, dry_run)

    if dry_run:
        print("\n✅ Simulação concluída. Nenhum arquivo foi movido.")
    else:
        print("\n✅ Processo finalizado com sucesso!")

if __name__ == "__main__":
    main()