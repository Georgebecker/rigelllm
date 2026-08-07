# ============================================================================
# sincronizar.ps1
# Sincroniza pastas de D:\Projetos\rigelllm\dados\gerados para
# D:\Projetos\rigelllm\dados\processed
#
# Regras:
# - Se a pasta de destino NAO existe: copia a pasta inteira (com tudo)
# - Se a pasta de destino JA existe: copia apenas os arquivos que nao existem
#   no destino (ou que sao mais novos)
# ============================================================================

$OrigemBase = "D:\Projetos\rigelllm\dados\gerados"
$DestinoBase = "D:\Projetos\rigelllm\dados\processed"

# Verifica se a origem existe
if (-not (Test-Path $OrigemBase)) {
    Write-Host "[ERRO] Pasta de origem nao encontrada: $OrigemBase" -ForegroundColor Red
    exit 1
}

# Cria o destino se nao existir
if (-not (Test-Path $DestinoBase)) {
    Write-Host "[INFO] Criando pasta de destino: $DestinoBase" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $DestinoBase -Force | Out-Null
}

# Obtem todas as subpastas da origem
$PastasOrigem = Get-ChildItem -Path $OrigemBase -Directory

Write-Host "[INFO] Sincronizando $($PastasOrigem.Count) pastas..." -ForegroundColor Cyan

foreach ($pasta in $PastasOrigem) {
    $nomePasta = $pasta.Name
    $caminhoOrigem = $pasta.FullName
    $caminhoDestino = Join-Path -Path $DestinoBase -ChildPath $nomePasta

    # Verifica se a pasta de destino existe
    if (-not (Test-Path $caminhoDestino)) {
        # Pasta nao existe: copia a pasta inteira
        Write-Host "[CRIAR] Nova pasta: $nomePasta (copia completa)" -ForegroundColor Green
        Copy-Item -Path $caminhoOrigem -Destination $caminhoDestino -Recurse -Force
    } else {
        # Pasta ja existe: copia apenas os arquivos que nao existem no destino
        Write-Host "[ATUALIZAR] Pasta: $nomePasta (copiando apenas arquivos novos)" -ForegroundColor Yellow

        # Lista todos os arquivos da origem (recursivamente)
        $arquivosOrigem = Get-ChildItem -Path $caminhoOrigem -File -Recurse

        foreach ($arq in $arquivosOrigem) {
            # Calcula o caminho relativo para manter a estrutura de subpastas
            $caminhoRelativo = $arq.FullName.Substring($caminhoOrigem.Length + 1)
            $caminhoArquivoDestino = Join-Path -Path $caminhoDestino -ChildPath $caminhoRelativo

            # Verifica se o arquivo ja existe no destino
            if (-not (Test-Path $caminhoArquivoDestino)) {
                # Arquivo nao existe: copia
                Write-Host "   + Copiando: $caminhoRelativo" -ForegroundColor Gray
                # Cria a subpasta se necessario
                $pastaDestinoArquivo = Split-Path -Path $caminhoArquivoDestino -Parent
                if (-not (Test-Path $pastaDestinoArquivo)) {
                    New-Item -ItemType Directory -Path $pastaDestinoArquivo -Force | Out-Null
                }
                Copy-Item -Path $arq.FullName -Destination $caminhoArquivoDestino -Force
            }
        }
    }
}

Write-Host "[SUCESSO] Sincronizacao concluida!" -ForegroundColor Green