param(
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$VivadoBin = 'E:\vivado\Vivado\2017.4\bin'
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOut = [System.IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $taskOut) {throw 'Choose a new simulation directory'}
New-Item -ItemType Directory -Path $taskOut | Out-Null
Push-Location -LiteralPath $taskOut
try {
    & (Join-Path $VivadoBin 'xvlog.bat') -i (Join-Path $taskRoot 'rtl\core') (Join-Path $taskRoot 'rtl\core\retina_point_axis.v')
    if ($LASTEXITCODE -ne 0) {throw 'Verilog-2001 module compilation failed'}
    & (Join-Path $VivadoBin 'xvlog.bat') -sv (Join-Path $taskRoot 'tests\retina_point_axis_tb.sv')
    if ($LASTEXITCODE -ne 0) {throw 'RTL compilation failed'}
    & (Join-Path $VivadoBin 'xelab.bat') retina_point_axis_tb -s point_axis_sim -mt off
    if ($LASTEXITCODE -ne 0) {throw 'RTL elaboration failed'}
    & (Join-Path $VivadoBin 'xsim.bat') point_axis_sim -runall -onfinish quit
    if ($LASTEXITCODE -ne 0) {throw 'RTL simulation failed'}
    $taskLog = Get-Content -LiteralPath 'xsim.log' -Raw
    if ($taskLog -notmatch 'POINT_AXIS_SIM_PASS:' -or $taskLog -match '(?i)Fatal:|Error:') {throw 'Simulation PASS gate failed'}
} finally {Pop-Location}
