param([string]$VivadoBin = 'E:\vivado\Vivado\2017.4\bin')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOut = Join-Path $taskRoot 'results\audit\simulation'
New-Item -ItemType Directory -Path $taskOut -Force | Out-Null
Push-Location -LiteralPath $taskOut
try {
    & (Join-Path $VivadoBin 'xvlog.bat') -sv (Join-Path $PSScriptRoot 'environment_probe.sv') (Join-Path $PSScriptRoot 'environment_probe_tb.sv')
    if ($LASTEXITCODE -ne 0) { throw 'xvlog failed' }
    & (Join-Path $VivadoBin 'xelab.bat') environment_probe_tb -s environment_probe_sim -mt off
    if ($LASTEXITCODE -ne 0) { throw 'xelab failed' }
    & (Join-Path $VivadoBin 'xsim.bat') environment_probe_sim -runall -onfinish quit
    if ($LASTEXITCODE -ne 0) { throw 'xsim failed' }
    if (-not (Select-String -LiteralPath 'xsim.log' -Pattern 'ENVIRONMENT_SIM_PASS' -Quiet)) { throw 'Simulation success marker not found' }
} finally { Pop-Location }
