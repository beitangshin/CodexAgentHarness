$ErrorActionPreference = 'Stop'

$listener = Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    Write-Output 'Master is already stopped.'
    exit 0
}

$masterPid = @($listener)[0].OwningProcess
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$masterPid"
if (-not $process -or $process.CommandLine -notmatch '(?i)(?:^|\s)-m\s+codex_agent_harness\.master(?:\s|$)' `
        -or $process.CommandLine -notmatch '(?:^|\s)--port\s+8000(?:\s|$)') {
    throw "Port 8000 is owned by another process (PID $masterPid)."
}

Stop-Process -Id $masterPid -ErrorAction Stop
Write-Output "Stopped Master PID $masterPid"
