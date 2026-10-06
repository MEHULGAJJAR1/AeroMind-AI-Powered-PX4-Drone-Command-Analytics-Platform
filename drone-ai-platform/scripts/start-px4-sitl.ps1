param([string]$Px4Dir = $env:PX4_DIR, [string]$Target = $env:PX4_SITL_TARGET)
$ErrorActionPreference = 'Stop'
if (-not $Px4Dir) { Write-Error 'Set PX4_DIR or pass -Px4Dir to your PX4-Autopilot checkout.'; exit 2 }
$Px4Dir = (Resolve-Path $Px4Dir).Path
if (-not (Test-Path (Join-Path $Px4Dir 'Makefile'))) { Write-Error "No PX4 Makefile found at $Px4Dir"; exit 2 }
if (-not (Get-Command make -ErrorAction SilentlyContinue)) { Write-Error 'GNU make is unavailable. Run PX4 SITL in a supported Linux/WSL2 toolchain, then start the app backend with TELEMETRY_MODE=px4.'; exit 3 }
if (-not $Target) {
  $targets = (make -C $Px4Dir px4_sitl list_vmd_make_targets 2>&1 | Out-String)
  if ($targets -match '(?m)(^|\W)gz_x500($|\W)') { $Target = 'gz_x500' }
  elseif ($targets -match '(?m)(^|\W)gazebo-classic_iris($|\W)') { $Target = 'gazebo-classic_iris' }
  else { Write-Host $targets; Write-Error 'No recognized target detected. Set PX4_SITL_TARGET to one listed above.'; exit 3 }
}
Write-Host "Starting PX4 target '$Target' from $Px4Dir"
make -C $Px4Dir px4_sitl $Target
