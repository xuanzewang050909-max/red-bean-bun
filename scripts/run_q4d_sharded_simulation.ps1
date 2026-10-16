param([string]$OutputDirectory='D:\PLD\retina_fpga\build\q4d_sharded_rtl_02')
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskOut=[System.IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $taskOut){throw 'Preserve previous simulation'}
New-Item -ItemType Directory -Path $taskOut | Out-Null
$taskCompiled=Join-Path $taskRoot 'build\q4d_shard_compile_01'
$taskVectors=Join-Path $taskRoot 'build\q4d_detector_axis_sim_03'
if((Get-Content (Join-Path $taskCompiled 'elaborate.log') -Raw) -notmatch 'Built simulation snapshot q4d_detector_shard'){throw 'Compiled snapshot missing'}
$taskRanges=@(@(1,3),@(3,5),@(5,7),@(7,9),@(9,11),@(11,13),@(13,15),@(15,18))
$taskProcesses=@()
$taskRuns=@()
for($taskIndex=0;$taskIndex -lt $taskRanges.Count;$taskIndex++){
    $taskRange=$taskRanges[$taskIndex]
    $taskDir=Join-Path $taskOut ('group_{0:d2}' -f ($taskIndex+1))
    New-Item -ItemType Directory -Path $taskDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $taskCompiled 'xsim.dir') -Destination $taskDir -Recurse
    Get-ChildItem -LiteralPath $taskVectors -File | Where-Object {$_.Extension -in @('.dat','.hex') -or $_.Name -eq 'vector_manifest.json'} | Copy-Item -Destination $taskDir
    Copy-Item -LiteralPath (Join-Path $taskCompiled 'retina_q4d_detector_shard_tb.sv') -Destination $taskDir
    $taskRunner=Join-Path $taskDir 'run.ps1'
    # The vendor batch loader splits unquoted '='. Preserve literal quotes.
    $taskText=@'
& 'E:\vivado\Vivado\2017.4\bin\xsim.bat' q4d_detector_shard -runall -onfinish quit -maxdeltaid 50000 -testplusarg '"RANGE_FIRST={0}"' -testplusarg '"RANGE_LAST={1}"' *> session.log
exit $LASTEXITCODE
'@ -f $taskRange[0],$taskRange[1]
    Set-Content -LiteralPath $taskRunner -Value $taskText -Encoding utf8
    $taskProcess=Start-Process -FilePath (Join-Path $PSHOME 'pwsh.exe') -ArgumentList @('-NoProfile','-File',$taskRunner) -WorkingDirectory $taskDir -WindowStyle Hidden -PassThru
    $taskProcesses+=$taskProcess
    $taskRuns+=@{first=$taskRange[0];last=$taskRange[1];directory=$taskDir;process_id=$taskProcess.Id}
}
$taskRuns | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $taskOut 'launch.json') -Encoding utf8
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $taskOut 'launch_script_used.ps1')
Write-Output 'Started eight actual RTL groups. Every adjacent vector pair is retained; seven seed frames are deliberately repeated.'
foreach($taskProcess in $taskProcesses){$taskProcess.WaitForExit();if($taskProcess.ExitCode -ne 0){throw "Group process failed: $($taskProcess.Id)"}}
Write-Output 'Processes completed; independent log/source/vector audit is still required.'
