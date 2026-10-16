param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$HlsBuild='D:\PLD\retina_fpga\build\a4_hls_02',
      [string]$VivadoBin='E:\vivado\Vivado\2017.4\bin')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskOut=[System.IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $taskOut){throw 'Choose a new simulation directory'}
New-Item -ItemType Directory -Path $taskOut | Out-Null
& (Join-Path $taskRoot '.venv\Scripts\python.exe') (Join-Path $taskRoot 'scripts\prepare_a4_vectors.py') $taskOut
if($LASTEXITCODE -ne 0){throw 'Vector preparation failed'}
Push-Location -LiteralPath $taskOut
try {
    Get-ChildItem -LiteralPath (Join-Path $HlsBuild 'solution1\syn\verilog') -Filter '*.dat' | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $taskOut
    }
    $taskSources=@((Join-Path $taskRoot 'rtl\core\retina_gaussian_guard.v')) + @((Get-ChildItem -LiteralPath (Join-Path $HlsBuild 'solution1\syn\verilog') -Filter '*.v').FullName)
    & (Join-Path $VivadoBin 'xvlog.bat') @taskSources
    if($LASTEXITCODE -ne 0){throw 'Generated RTL compilation failed'}
    & (Join-Path $VivadoBin 'xvlog.bat') -sv (Join-Path $taskRoot 'tests\retina_segmentation_axis_tb.sv')
    if($LASTEXITCODE -ne 0){throw 'Testbench compilation failed'}
    & (Join-Path $VivadoBin 'xelab.bat') retina_segmentation_axis_tb -s segmentation_axis_sim -mt off
    if($LASTEXITCODE -ne 0){throw 'RTL elaboration failed'}
    & (Join-Path $VivadoBin 'xsim.bat') segmentation_axis_sim -runall -onfinish quit
    if($LASTEXITCODE -ne 0){throw 'RTL simulation failed'}
    $taskLog=Get-Content -LiteralPath xsim.log -Raw
    if($taskLog -notmatch 'SEGMENTATION_AXIS_SIM_PASS:' -or $taskLog -match '(?i)Fatal:|Error:'){throw 'Segmentation PASS gate failed'}
} finally {Pop-Location}
