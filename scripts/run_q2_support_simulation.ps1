param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$HlsBuild='D:\PLD\retina_fpga\build\q2_support_hls_01',
      [string]$VivadoBin='E:\vivado\Vivado\2017.4\bin',
      [switch]$ResetOnly)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskOut=[System.IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $taskOut){throw 'Choose a new simulation directory'}
New-Item -ItemType Directory -Path $taskOut | Out-Null
& (Join-Path $taskRoot '.venv\Scripts\python.exe') -X utf8 -B (Join-Path $taskRoot 'scripts\prepare_q2_support_vectors.py') $taskOut
if($LASTEXITCODE -ne 0){throw 'Q2 support vector preparation failed'}
Push-Location -LiteralPath $taskOut
try {
    Get-ChildItem -LiteralPath (Join-Path $HlsBuild 'solution1\syn\verilog') -Filter '*.dat' | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $taskOut
    }
    $taskSources=@((Get-ChildItem -LiteralPath (Join-Path $HlsBuild 'solution1\syn\verilog') -Filter '*.v').FullName)
    & (Join-Path $VivadoBin 'xvlog.bat') @taskSources
    if($LASTEXITCODE -ne 0){throw 'Q2 generated RTL compilation failed'}
    & (Join-Path $VivadoBin 'xvlog.bat') -sv (Join-Path $taskRoot 'tests\retina_c2_support_axis_tb.sv')
    if($LASTEXITCODE -ne 0){throw 'Q2 RTL testbench compilation failed'}
    & (Join-Path $VivadoBin 'xelab.bat') retina_c2_support_axis_tb -s c2_support_axis_sim -mt off
    if($LASTEXITCODE -ne 0){throw 'Q2 RTL elaboration failed'}
    $taskSimArgs=@('c2_support_axis_sim','-runall','-onfinish','quit')
    if($ResetOnly){$taskSimArgs+=@('-testplusarg','RESET_ONLY')}
    & (Join-Path $VivadoBin 'xsim.bat') @taskSimArgs
    if($LASTEXITCODE -ne 0){throw 'Q2 RTL simulation failed'}
    $taskLog=Get-Content -LiteralPath xsim.log -Raw
    $taskExpectedPass=if($ResetOnly){'C2_SUPPORT_RESET_FOCUS_PASS:'}else{'C2_SUPPORT_AXIS_SIM_PASS:'}
    if($taskLog -notmatch $taskExpectedPass -or $taskLog -match '(?i)Fatal:|Error:'){throw 'Q2 support RTL PASS gate failed'}
} finally {Pop-Location}
