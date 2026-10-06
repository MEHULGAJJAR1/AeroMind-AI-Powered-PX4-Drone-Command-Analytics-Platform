$ErrorActionPreference = 'Stop'
$AppDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location (Join-Path $AppDir 'frontend')
npm run dev -- --host 0.0.0.0
