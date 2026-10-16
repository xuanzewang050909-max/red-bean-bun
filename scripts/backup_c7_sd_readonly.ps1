$ErrorActionPreference = 'Stop'
$sourceStream = $null
$destinationStream = $null
$backupDir = $null
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script in an Administrator PowerShell window.'
    }
    $cards = @(Get-Disk | Where-Object {
        $_.BusType -eq 'USB' -and $_.Size -eq 15931539456 -and
        $_.SerialNumber.Trim() -eq '000000000819' -and -not $_.IsBoot -and -not $_.IsSystem
    })
    if ($cards.Count -ne 1) { throw 'Expected exactly one matching old 16GB card. Nothing copied.' }
    $card = $cards[0]
    $parts = @(Get-Partition -DiskNumber $card.Number | Sort-Object PartitionNumber)
    if ($parts.Count -ne 2 -or $parts[0].Size -ne 136314880 -or $parts[1].Size -ne 15794176000) {
        throw 'Old card partition sizes differ. Nothing copied.'
    }
    $bootVolume = $parts[0] | Get-Volume
    if ($bootVolume.FileSystemLabel -ne 'PYNQ') { throw 'Missing PYNQ boot volume.' }
    if ((Get-Volume -DriveLetter D).SizeRemaining -lt ($card.Size + 2GB)) { throw 'Insufficient free space on D:.' }
    $sourceStream = [IO.File]::Open(('\\.\PhysicalDrive' + $card.Number), [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    $sector = New-Object byte[] 512
    if ($sourceStream.Read($sector, 0, 512) -ne 512 -or $sector[510] -ne 0x55 -or $sector[511] -ne 0xAA) {
        throw 'Invalid MBR signature.'
    }
    $null = $sourceStream.Seek(0, [IO.SeekOrigin]::Begin)
    $backupDir = Join-Path 'D:\PLD\sd_backups' ('c7_old16_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8))
    $null = New-Item -ItemType Directory -Path $backupDir
    $imagePath = Join-Path $backupDir 'pynq_c7_old16.img'
    $destinationStream = [IO.File]::Open($imagePath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    $buffer = New-Object byte[] (4MB)
    [long]$copied = 0
    [long]$nextProgress = 0
    while ($copied -lt $card.Size) {
        $wanted = [int][Math]::Min([long]$buffer.Length, ([long]$card.Size - $copied))
        $read = $sourceStream.Read($buffer, 0, $wanted)
        if ($read -le 0) { throw ('Unexpected end of card at byte ' + $copied) }
        $destinationStream.Write($buffer, 0, $read)
        $copied += $read
        if ($copied -ge $nextProgress) {
            Write-Host ('Copied {0:N2} / {1:N2} GiB' -f ($copied/1GB), ($card.Size/1GB))
            $nextProgress = $copied + 512MB
        }
    }
    $destinationStream.Flush($true)
    $destinationStream.Dispose(); $destinationStream = $null
    $sourceStream.Dispose(); $sourceStream = $null
    if ((Get-Item -LiteralPath $imagePath).Length -ne $card.Size) { throw 'Backup file size mismatch.' }
    Write-Host 'Computing backup SHA256...'
    $hash = (Get-FileHash -LiteralPath $imagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    [ordered]@{
        status = 'BACKUP_COPY_COMPLETE'; image = $imagePath; bytes = $copied; sha256 = $hash
        sourceDisk = $card.Number; sourceSerial = $card.SerialNumber.Trim(); sourceBus = 'USB'
        createdLocal = (Get-Date -Format o); sourceAccess = 'READ_ONLY'
        note = 'Image length and SHA256 recorded; bootability and independent full source comparison not yet verified.'
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $backupDir 'backup_manifest.json') -Encoding UTF8
    Write-Host ('BACKUP_COPY_COMPLETE: ' + $imagePath) -ForegroundColor Green
} catch {
    if ($backupDir) { $_.Exception.Message | Set-Content -LiteralPath (Join-Path $backupDir 'FAILED.txt') -Encoding UTF8 }
    Write-Host ('BACKUP_FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    throw
} finally {
    if ($destinationStream) { $destinationStream.Dispose() }
    if ($sourceStream) { $sourceStream.Dispose() }
}
