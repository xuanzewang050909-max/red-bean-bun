param([Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$VivadoBin='E:\vivado\Vivado\2017.4\bin')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskOut=[System.IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $taskOut){throw 'Choose a new guard unit simulation directory'}
New-Item -ItemType Directory -Path $taskOut | Out-Null
Copy-Item -LiteralPath (Join-Path $taskRoot 'rtl\core\retina_quality_guard.v') -Destination $taskOut
Copy-Item -LiteralPath (Join-Path $taskRoot 'tests\retina_quality_guard_tb.sv') -Destination $taskOut
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $taskOut 'run_script_used.ps1')
Push-Location -LiteralPath $taskOut
try {
    & (Join-Path $VivadoBin 'xvlog.bat') retina_quality_guard.v
    if($LASTEXITCODE -ne 0){throw 'W2 guard compilation failed'}
    & (Join-Path $VivadoBin 'xvlog.bat') -sv retina_quality_guard_tb.sv
    if($LASTEXITCODE -ne 0){throw 'W2 guard testbench compilation failed'}
    & (Join-Path $VivadoBin 'xelab.bat') retina_quality_guard_tb -s w2_guard_unit -mt off
    if($LASTEXITCODE -ne 0){throw 'W2 guard unit elaboration failed'}
    & (Join-Path $VivadoBin 'xsim.bat') w2_guard_unit -runall -onfinish quit
    if($LASTEXITCODE -ne 0){throw 'W2 guard unit simulation failed'}
    $taskLog=Get-Content -LiteralPath xsim.log -Raw
    if($taskLog -notmatch 'W2_GUARD_UNIT_PASS:' -or $taskLog -match '(?i)Fatal:|Error:'){
        throw 'W2 guard unit PASS gate failed'
    }
} finally {Pop-Location}
