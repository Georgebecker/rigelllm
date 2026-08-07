# -*- coding: utf-8 -*-
"""Investiga processos gerar_sanitizados vivos."""
import subprocess, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ps = r"""
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*gerar_sanitizados*' } |
  Select-Object ProcessId, CreationDate, CommandLine |
  Format-List
"""
r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                   capture_output=True, text=True, timeout=30)
print(r.stdout)
print('STDERR:', r.stderr[:300])
