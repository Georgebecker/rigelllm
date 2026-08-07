@echo off
setlocal
title Desativar Telemetria do Windows (RigelSLM)
echo ============================================================
echo  Desativando telemetria de compatibilidade do Windows
echo  (CompatTelRunner.exe - consome CPU em rajadas)
echo  Rode como ADMINISTRADOR (botao direito - Executar como adm.)
echo ============================================================
echo.

:: ============================================================================
:: 1) TAREFAS AGENDADAS de telemetria (Application Experience)
::    CompatTelRunner.exe e disparado por estas tarefas.
:: ============================================================================
echo [1/4] Desativando tarefas agendadas de compatibilidade...
for %%T in (
    "\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser"
    "\Microsoft\Windows\Application Experience\ProgramDataUpdater"
    "\Microsoft\Windows\Application Experience\Consolidator"
    "\Microsoft\Windows\Application Experience\KernelCeipTask"
    "\Microsoft\Windows\Application Experience\StartupAppTask"
    "\Microsoft\Windows\Customer Experience Improvement Program\Consolidator"
    "\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip"
    "\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector"
) do (
    schtasks /change /TN "%%~T" /DISABLE >nul 2>&1 && echo    OK desativada: %%~nxT || echo    (nao encontrada ou ja desativada): %%~nxT
)

:: ============================================================================
:: 2) SERVICO DiagTrack (Connected User Experiences and Telemetry)
:: ============================================================================
echo [2/4] Parando e desativando o servico DiagTrack...
sc stop DiagTrack >nul 2>&1
sc config DiagTrack start= disabled >nul 2>&1 && echo    OK DiagTrack desativado || echo    (falha - precisa de Administrador?)

:: ============================================================================
:: 3) dmwappushservice (Device Management WAP Push) - telemetria
:: ============================================================================
echo [3/4] Parando e desativando dmwappushservice...
sc stop dmwappushservice >nul 2>&1
sc config dmwappushservice start= disabled >nul 2>&1 && echo    OK dmwappushservice desativado || echo    (falha - precisa de Administrador?)

:: ============================================================================
:: 4) REGISTRO: AllowTelemetry = 0 (Security / Enterprise)
:: ============================================================================
echo [4/4] Configurando registro AllowTelemetry=0...
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection" /v AllowTelemetry /t REG_DWORD /d 0 /f >nul 2>&1 && echo    OK AllowTelemetry=0 || echo    (falha - precisa de Administrador?)

:: ============================================================================
:: 5) Mata o CompatTelRunner se estiver rodando AGORA
:: ============================================================================
echo [*] Matando CompatTelRunner.exe se estiver rodando...
taskkill /IM CompatTelRunner.exe /F >nul 2>&1 && echo    OK processo encerrado || echo    (nenhum rodando agora)

echo.
echo ============================================================
echo  PRONTO! Telemetria de compatibilidade desativada.
echo  Dica: reinicie o PC quando puder para garantir.
echo ============================================================
pause
