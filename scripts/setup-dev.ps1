# First-time Windows dev setup (PowerShell). Prefer python.org Python 3.12.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$pyCandidates = @(
  (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
  (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
  (Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe")
)
$pyLauncher = $null
foreach ($c in $pyCandidates) {
  if (Test-Path $c) { $pyLauncher = $c; break }
}
if (-not $pyLauncher) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) { $pyLauncher = $cmd.Source }
}
if (-not $pyLauncher) {
  throw "No Python found. Install 3.12: winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements"
}

Write-Host "Using: $pyLauncher"
& $pyLauncher --version

if (-not (Test-Path (Join-Path $Root ".venv\Scripts\python.exe"))) {
  & $pyLauncher -m venv .venv
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip setuptools wheel
& $py -m pip install -e ".[web,dev]"
& $py -c "import numpy; print('numpy ok', numpy.__version__)"

Push-Location (Join-Path $Root "frontend")
npm install
npm run build
Pop-Location

npm install
npx playwright install chromium

Write-Host ""
Write-Host "Done. Activate: .\.venv\Scripts\Activate.ps1"
Write-Host "Dev server: .\scripts\dev-server.ps1"
Write-Host "E2E (port 8799): .\scripts\run-e2e.ps1"
