param(
    [string]$Godot = "$env:USERPROFILE\Downloads\Godot_v4.7-stable_win64.exe\Godot_v4.7-stable_win64.exe",
    [string]$WslDistribution = 'ep-wsl',
    [string]$LinuxBuildVenv = '~/.venvs/pyfatfs',
    [switch]$MasterOnly,
    [switch]$SlaveOnly,
    [switch]$SkipWindowsPython,
    [switch]$SkipLinuxPython
)

$ErrorActionPreference = 'Stop'
if ($MasterOnly -and $SlaveOnly) { throw 'Choose either -MasterOnly or -SlaveOnly' }
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$distribution = Join-Path $repository 'dist\portable'
New-Item -ItemType Directory -Force -Path $distribution | Out-Null

function Build-PythonRole([string]$role, [string]$entry) {
    $target = Join-Path $distribution "windows-$role"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $arguments = @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
        '--name', "codex-agent-harness-$role", '--paths', $repository,
        '--hidden-import', 'codex_agent_harness.managed',
        '--distpath', $target,
        '--workpath', (Join-Path $repository "build\pyinstaller-windows-$role"),
        '--specpath', (Join-Path $repository "build\pyinstaller-spec-windows-$role")
    )
    if ($role -eq 'master') {
        $arguments += @('--hidden-import', 'codex_agent_harness.server', '--collect-data', 'codex_agent_harness')
    } else {
        $arguments += @('--hidden-import', 'codex_agent_harness.gui')
    }
    $arguments += (Join-Path $repository $entry)
    & python @arguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed for Windows $role" }
    $binary = Join-Path $target "codex-agent-harness-$role\codex-agent-harness-$role.exe"
    & $binary --help | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Windows $role binary failed its smoke check" }
}

if (-not $SkipWindowsPython) {
    if (-not $MasterOnly) {
        Build-PythonRole 'slave' 'codex_agent_harness\__main__.py'
    }
    if (-not $SlaveOnly) {
        Build-PythonRole 'master' 'codex_agent_harness\master_entry.py'
    }
}

if (-not $SkipLinuxPython) {
    $linuxRepository = (& wsl -d $WslDistribution -- wslpath -a $repository.Replace('\', '/')).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $linuxRepository) { throw 'Could not map the repository into WSL' }
    $encodedPath = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($linuxRepository))
    $linuxRole = if ($MasterOnly) { 'master' } elseif ($SlaveOnly) { 'slave' } else { 'all' }
    $linuxCommand = 'cd "$(printf %s ' + $encodedPath + ' | base64 -d)" && source ' + $LinuxBuildVenv + '/bin/activate && bash scripts/build_linux_portable.sh dist/portable ' + $linuxRole
    & wsl -d $WslDistribution -- bash -lc $linuxCommand
    if ($LASTEXITCODE -ne 0) { throw 'Linux Python builds failed' }
}

if (-not $SlaveOnly) {
    if (-not (Test-Path -LiteralPath $Godot)) { throw "Godot editor not found: $Godot" }
    $godotLogDirectory = Join-Path $repository 'build\godot-logs'
    New-Item -ItemType Directory -Force -Path $godotLogDirectory | Out-Null
    foreach ($preset in @(@('Windows Desktop', 'windows-master', 'CodexAgentHarness-Master.exe'),
                         @('Linux', 'linux-master', 'CodexAgentHarness-Master.x86_64'))) {
        $target = Join-Path $distribution $preset[1]
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        $output = Join-Path $target $preset[2]
        $stdout = Join-Path $godotLogDirectory "godot-$($preset[1]).out.log"
        $stderr = Join-Path $godotLogDirectory "godot-$($preset[1]).err.log"
        $process = Start-Process -FilePath $Godot -ArgumentList @('--headless', '--path',
            (Join-Path $repository 'godot_master'), '--export-release', ('"' + $preset[0] + '"'), $output) `
            -Wait -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if ($process.ExitCode -ne 0) { throw "Godot export failed for $($preset[0]): $(Get-Content $stderr -Raw)" }
    }

# Keep the exported Godot executable at the package root and the Python backend beside it.
foreach ($platform in @('windows', 'linux')) {
    $root = Join-Path $distribution "$platform-master"
    $backend = Join-Path $root 'backend'
    $source = Join-Path $root 'codex-agent-harness-master'
    $distributionPrefix = [IO.Path]::GetFullPath($distribution).TrimEnd('\') + '\'
    foreach ($candidate in @($root, $backend, $source)) {
        if (-not [IO.Path]::GetFullPath($candidate).StartsWith($distributionPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Build output escaped the distribution directory: $candidate"
        }
    }
    if (Test-Path -LiteralPath $source) {
        if (Test-Path -LiteralPath $backend) {
            Remove-Item -LiteralPath $backend -Recurse -Force
        }
        $moved = $false
        for ($attempt = 1; $attempt -le 5; $attempt++) {
            try {
                Move-Item -LiteralPath $source -Destination $backend -ErrorAction Stop
                $moved = $true
                break
            } catch {
                if ($attempt -eq 5) { throw }
                Start-Sleep -Seconds 2
            }
        }
    } elseif (-not (Test-Path -LiteralPath $backend)) {
        throw "Missing packaged backend: $backend"
    }
}
}

Write-Output "Portable packages: $distribution"
