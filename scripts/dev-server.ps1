# Start CuratorX web UI for local dev (PowerShell).
param(
  [string]$DataDir = "",
  [int]$Port = 8788
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

if ([string]::IsNullOrWhiteSpace($DataDir)) {
  $DataDir = Join-Path $Root "config"
}

$dist = Join-Path $Root "frontend\dist"
if (-not (Test-Path $dist)) {
  Write-Host "Building frontend..."
  Push-Location (Join-Path $Root "frontend")
  npm install
  npm run build
  Pop-Location
}

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

$env:DATA_DIR = $DataDir
$env:PORT = "$Port"
Write-Host "CuratorX at http://127.0.0.1:$Port (DATA_DIR=$DataDir)"
& $python -m curatorx.web