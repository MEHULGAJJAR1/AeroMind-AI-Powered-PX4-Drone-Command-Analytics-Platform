$ErrorActionPreference = 'Stop'
$AppDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location (Join-Path $AppDir 'backend')
$env:PYTHONPATH = (Get-Location).Path
& (Join-Path $AppDir '.venv\Scripts\python.exe') -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
