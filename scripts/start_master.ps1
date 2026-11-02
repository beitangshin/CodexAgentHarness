$ErrorActionPreference = 'Stop'

$credentialsPath = Join-Path $HOME '.codex-agent-harness\master-credentials.json'
if (-not (Test-Path -LiteralPath $credentialsPath)) {
    throw "Master credentials file was not found: $credentialsPath"
}

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    throw "Port 8000 is still in use by process $($listener.OwningProcess). Close the old Master before starting this version."
}

$credentials = Get-Content -LiteralPath $credentialsPath -Raw | ConvertFrom-Json
$env:REPORT_TOKEN = $credentials.REPORT_TOKEN
$env:DASHBOARD_USER = $credentials.DASHBOARD_USER
$env:DASHBOARD_PASSWORD = $credentials.DASHBOARD_PASSWORD

$repository = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction Stop).Source
$process = Start-Process -FilePath $python -ArgumentList @('-m', 'codex_agent_harness.master', '--port', '8000') `
    -WorkingDirectory $repository -WindowStyle Hidden -PassThru
Write-Output "Master starting: PID $($process.Id), http://127.0.0.1:8000"
