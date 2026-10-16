param([ValidateSet('hls','hls-repack','bd')][string]$Stage = 'hls')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$vivadoBin = 'E:\vivado\Vivado\2017.4\bin'
$taskOutput = Join-Path $taskRoot 'results\audit\official_v2.2.1'
New-Item -ItemType Directory -Force -Path $taskOutput | Out-Null
$previousPath = $env:PATH
try {
    $env:PATH = "$vivadoBin;$previousPath"
    & (Join-Path $vivadoBin 'vivado.bat') -mode batch -nojournal -log (Join-Path $taskOutput "$Stage.log") -source (Join-Path $PSScriptRoot 'audit_official_base.tcl') -tclargs $Stage
    if ($LASTEXITCODE -ne 0) { throw "Official $Stage audit failed ($LASTEXITCODE); see $taskOutput" }
} finally {
    $env:PATH = $previousPath
}
