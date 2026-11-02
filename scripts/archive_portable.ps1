param([string]$WslDistribution = 'ep-wsl')

$ErrorActionPreference = 'Stop'
$repository = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$distribution = Join-Path $repository 'dist\portable'
foreach ($role in @('master', 'slave')) {
    $name = "windows-$role"
    $source = Join-Path $distribution $name
    $archive = Join-Path $distribution "$name.zip"
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing package: $source" }
    & tar -a -cf $archive -C $distribution $name
    if ($LASTEXITCODE -ne 0) { throw "Could not archive $name" }
    Get-FileHash -Algorithm SHA256 -LiteralPath $archive | Select-Object Path, Hash
}

$linuxScript = (& wsl -d $WslDistribution -- wslpath -a (Join-Path $repository 'scripts\archive_linux_portable.sh').Replace('\', '/')).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not map archive script into WSL' }
foreach ($role in @('master', 'slave')) {
    $name = "linux-$role"
    $source = (& wsl -d $WslDistribution -- wslpath -a (Join-Path $distribution $name).Replace('\', '/')).Trim()
    $archive = (& wsl -d $WslDistribution -- wslpath -a (Join-Path $distribution "$name.tar.gz").Replace('\', '/')).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not map $name into WSL" }
    & wsl -d $WslDistribution -- bash $linuxScript $source $archive
    if ($LASTEXITCODE -ne 0) { throw "Could not archive $name" }
}

$names = @('windows-master.zip', 'windows-slave.zip',
           'linux-master.tar.gz', 'linux-slave.tar.gz')
$lines = foreach ($name in $names) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $distribution $name)).Hash.ToLowerInvariant()
    "$hash  $name"
}
Set-Content -LiteralPath (Join-Path $distribution 'SHA256SUMS.txt') -Value $lines -Encoding ascii
