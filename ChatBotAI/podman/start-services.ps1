$ErrorActionPreference = 'Stop'
$podmanExe = Join-Path $env:LOCALAPPDATA 'Programs\Podman\podman.exe'
if (-not (Test-Path -LiteralPath $podmanExe)) { throw 'Podman executable not found.' }
# Windows PowerShell treats native stderr as an error under Stop.
# An unavailable engine is expected here before the machine starts.
$ErrorActionPreference = 'Continue'
& $podmanExe info --format '{{.Host.Hostname}}' 2>$null | Out-Null
$engineExitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($engineExitCode -ne 0) {
    & $podmanExe machine start podman-machine-default
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the Podman machine.' }
}
& $podmanExe start umi-n8n umi-waha
if ($LASTEXITCODE -ne 0) { throw 'Could not start one or more UMI containers.' }
$pythonExe = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'
& $pythonExe (Join-Path $PSScriptRoot 'forward_ports.py')
if ($LASTEXITCODE -ne 0) { throw 'Could not refresh Windows port forwarding; run as administrator.' }
