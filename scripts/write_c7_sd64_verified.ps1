$ErrorActionPreference = 'Stop'
$imagePath = 'D:\PLD\sd_backups\c7_old16_20261016_180536_b2a95fb1\pynq_c7_old16.img'
$expectedHash = 'b6df4dc4d9e562a4c0d2bc497d675dc9b88a5ea1749bb69357447a6273cae154'
[long]$imageBytes = 15931539456
[long]$targetBytes = 63864569856
$sourceStream = $null
$diskStream = $null
$volumeStream = $null
$hash = $null
$logDir = $null
try {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator PowerShell required.' }
    $cards = @(Get-Disk | Where-Object { $_.BusType -eq 'USB' -and $_.Size -eq $targetBytes -and $_.SerialNumber.Trim() -eq '000000000819' -and -not $_.IsBoot -and -not $_.IsSystem })
    if ($cards.Count -ne 1) { throw 'Expected exactly one matching 64GB USB card.' }
    $card = $cards[0]
    $parts = @(Get-Partition -DiskNumber $card.Number)
    if ($parts.Count -ne 1 -or $parts[0].Offset -ne 16777216 -or $parts[0].Size -ne 63847792640 -or -not $parts[0].DriveLetter) {
        throw 'New card layout has changed. Stop and ask for inspection; do not retry automatically.'
    }
    $logDir = Join-Path 'D:\PLD\sd_backups' ('write64_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
    $null = New-Item -ItemType Directory -Path $logDir
    $sourceStream = [IO.File]::Open($imagePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    if ($sourceStream.Length -ne $imageBytes) { throw 'Image size mismatch.' }
    Write-Host 'Checking source image SHA256 before writing...'
    $hash = [Security.Cryptography.SHA256]::Create()
    $sourceHash = ([BitConverter]::ToString($hash.ComputeHash($sourceStream))).Replace('-','').ToLowerInvariant()
    $hash.Dispose(); $hash = $null
    if ($sourceHash -ne $expectedHash) { throw 'Image SHA256 mismatch. Nothing written.' }
    $null = $sourceStream.Seek(0, [IO.SeekOrigin]::Begin)
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class C7VolumeControl {
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool DeviceIoControl(SafeFileHandle h, uint code, IntPtr input, uint inputSize, IntPtr output, uint outputSize, out uint returned, IntPtr overlapped);
}
'@
    $volumePath = '\\.\' + $parts[0].DriveLetter + ':'
    $volumeStream = [IO.File]::Open($volumePath, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    [uint32]$returned = 0
    # Lock and dismount the new card volume before any raw disk writes.
    foreach ($code in @([uint32]0x00090018, [uint32]0x00090020)) {
        if (-not [C7VolumeControl]::DeviceIoControl($volumeStream.SafeFileHandle, $code, [IntPtr]::Zero, 0, [IntPtr]::Zero, 0, [ref]$returned, [IntPtr]::Zero)) {
            throw ('Cannot lock/dismount new card; Windows error ' + [Runtime.InteropServices.Marshal]::GetLastWin32Error() + '. Close Explorer windows using the card and report this error.')
        }
    }
    $fresh = Get-Disk -Number $card.Number
    if ($fresh.Size -ne $targetBytes -or $fresh.BusType -ne 'USB' -or $fresh.IsBoot -or $fresh.IsSystem -or $fresh.SerialNumber.Trim() -ne '000000000819') { throw 'Disk identity changed.' }
    $diskStream = [IO.File]::Open(('\\.\PhysicalDrive' + $card.Number), [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
    $buffer = New-Object byte[] (4MB)
    [long]$copied = 0
    [long]$nextProgress = 0
    Write-Host ('Writing image to 64GB card, disk ' + $card.Number + '. Do not unplug.')
    while ($copied -lt $imageBytes) {
        $wanted = [int][Math]::Min([long]$buffer.Length, ($imageBytes - $copied))
        $read = $sourceStream.Read($buffer, 0, $wanted)
        if ($read -ne $wanted) { throw 'Short image read.' }
        $diskStream.Write($buffer, 0, $read)
        $copied += $read
        if ($copied -ge $nextProgress) {
            Write-Host ('Written {0:N2} / {1:N2} GiB' -f ($copied/1GB), ($imageBytes/1GB))
            $nextProgress = $copied + 512MB
        }
    }
    $diskStream.Flush($true)
    $diskStream.Dispose(); $diskStream = $null
    $sourceStream.Dispose(); $sourceStream = $null
    Write-Host 'Reading back the written image region for SHA256 verification...'
    $diskStream = [IO.File]::Open(('\\.\PhysicalDrive' + $card.Number), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $hash = [Security.Cryptography.SHA256]::Create()
    [long]$verified = 0
    [long]$nextProgress = 0
    while ($verified -lt $imageBytes) {
        $wanted = [int][Math]::Min([long]$buffer.Length, ($imageBytes - $verified))
        $read = $diskStream.Read($buffer, 0, $wanted)
        if ($read -ne $wanted) { throw 'Short card readback.' }
        $null = $hash.TransformBlock($buffer, 0, $read, $buffer, 0)
        $verified += $read
        if ($verified -ge $nextProgress) {
            Write-Host ('Verified {0:N2} / {1:N2} GiB' -f ($verified/1GB), ($imageBytes/1GB))
            $nextProgress = $verified + 1GB
        }
    }
    $null = $hash.TransformFinalBlock((New-Object byte[] 0), 0, 0)
    $readbackHash = ([BitConverter]::ToString($hash.Hash)).Replace('-','').ToLowerInvariant()
    if ($readbackHash -ne $expectedHash) { throw ('Readback SHA256 mismatch: ' + $readbackHash) }
    [ordered]@{status='WRITE_AND_READBACK_PASS';image=$imagePath;imageBytes=$imageBytes;targetBytes=$targetBytes;diskNumber=$card.Number;sha256=$readbackHash;createdLocal=(Get-Date -Format o);pending='Boot test and root partition expansion; old image partitions remain approximately 16GB.'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logDir 'write_manifest.json') -Encoding UTF8
    Write-Host ('WRITE_AND_READBACK_PASS: ' + $logDir) -ForegroundColor Green
} catch {
    if ($logDir) { $_.Exception.Message | Set-Content -LiteralPath (Join-Path $logDir 'FAILED.txt') -Encoding UTF8 }
    Write-Host ('WRITE_FAILED: ' + $_.Exception.Message + ' STOP; do not retry automatically.') -ForegroundColor Red
    throw
} finally {
    if ($hash) { $hash.Dispose() }
    if ($diskStream) { $diskStream.Dispose() }
    if ($sourceStream) { $sourceStream.Dispose() }
    if ($volumeStream) { $volumeStream.Dispose() }
}
