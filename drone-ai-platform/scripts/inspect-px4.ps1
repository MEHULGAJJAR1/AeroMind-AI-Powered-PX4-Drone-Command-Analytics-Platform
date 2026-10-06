param([string]$Px4Dir = $env:PX4_DIR)
$ErrorActionPreference = 'Continue'
if (-not $Px4Dir) { Write-Error 'Set PX4_DIR or pass -Px4Dir to an existing PX4-Autopilot checkout.'; exit 2 }
$Px4Dir = (Resolve-Path $Px4Dir).Path
Write-Host "PX4 checkout: $Px4Dir"
Write-Host -NoNewline 'Revision: '; git -C $Px4Dir describe --tags --always --dirty
Write-Host -NoNewline 'Branch: '; git -C $Px4Dir branch --show-current
@('boards/px4/sitl','Tools/simulation/gz','Tools/simulation/gazebo-classic','src/modules/mavlink','msg') | ForEach-Object { if (Test-Path (Join-Path $Px4Dir $_)) { Write-Host "Present: $_" } else { Write-Host "Absent: $_" } }
if (Test-Path (Join-Path $Px4Dir 'msg')) { Write-Host "Message definitions: $((Get-ChildItem (Join-Path $Px4Dir 'msg') -Filter '*.msg' -Recurse).Count) .msg files" }
if (Get-Command make -ErrorAction SilentlyContinue) { Write-Host "`nTargets reported by PX4:"; make -C $Px4Dir px4_sitl list_vmd_make_targets } else { Write-Host 'GNU make is unavailable. Use the PX4 toolchain in WSL2/Linux to enumerate targets.' }
Write-Host "`nGazebo tools:"; Get-Command gz,gazebo -ErrorAction SilentlyContinue | Select-Object Name,Source
Write-Host 'Inspection is read-only; no PX4 source files are modified.'
