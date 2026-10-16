param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$HlsBuild='D:\PLD\retina_fpga\build\q4_refined_hls_02',
      [string]$VivadoBin='E:\vivado\Vivado\2017.4\bin')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskOut=[System.IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $taskOut){throw 'Choose a new simulation directory'}
New-Item -ItemType Directory -Path $taskOut | Out-Null
& (Join-Path $taskRoot '.venv\Scripts\python.exe') -X utf8 -B (Join-Path $taskRoot 'scripts\prepare_q4_refined_vectors.py') $taskOut
if($LASTEXITCODE -ne 0){throw 'Vector preparation failed'}
Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\core\retina_refined_guard.v') -Destination $taskOut
Copy-Item -LiteralPath (Join-Path $taskRoot 'tests\retina_q4_refined_axis_tb.sv') -Destination $taskOut
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $taskOut 'run_script_used.ps1')
Push-Location -LiteralPath $taskOut
try {
    Get-ChildItem -LiteralPath (Join-Path $HlsBuild 'solution1\syn\verilog') -Filter '*.dat' | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $taskOut
    }
    $taskSources=@((Join-Path $taskOut 'retina_refined_guard.v')) + @((Get-ChildItem -LiteralPath (Join-Path $HlsBuild 'solution1\syn\verilog') -Filter '*.v').FullName)
    $taskProject = @($taskSources | ForEach-Object { 'verilog work "' + $_.Replace('\','/') + '"' })
    $taskProject | Set-Content -LiteralPath (Join-Path $taskOut 'sources.prj') -Encoding ascii
    & (Join-Path $VivadoBin 'xvlog.bat') -prj sources.prj
    if($LASTEXITCODE -ne 0){throw 'Generated RTL compilation failed'}
    & (Join-Path $VivadoBin 'xvlog.bat') -sv (Join-Path $taskOut 'retina_q4_refined_axis_tb.sv')
    if($LASTEXITCODE -ne 0){throw 'Testbench compilation failed'}
    & (Join-Path $VivadoBin 'xelab.bat') retina_q4_refined_axis_tb -s q4_refined_axis_sim -mt off
    if($LASTEXITCODE -ne 0){throw 'RTL elaboration failed'}
    & (Join-Path $VivadoBin 'xsim.bat') q4_refined_axis_sim -runall -onfinish quit
    if($LASTEXITCODE -ne 0){throw 'RTL simulation failed'}
    $taskLog=Get-Content -LiteralPath xsim.log -Raw
    if($taskLog -notmatch 'Q4_REFINED_AXIS_SIM_PASS:' -or $taskLog -match '(?i)Fatal:|Error:'){throw 'Q2 quality PASS gate failed'}
} finally {Pop-Location}
