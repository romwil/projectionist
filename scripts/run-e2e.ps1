# Mocked Playwright e2e from repo root. Default port 8799 (see playwright.config.ts).
# Do NOT use :8788 — it is often an SSH tunnel to production / Docker.
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$PlaywrightArgs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($env:SKIP_FRONTEND_BUILD -ne "1") {
  Push-Location frontend
  npm install
  npm run build
  Pop-Location
}

npm install
npx playwright install chromium
if ($PlaywrightArgs.Count -gt 0) {
  npx playwright test @PlaywrightArgs
} else {
  npm run test:e2e
}
