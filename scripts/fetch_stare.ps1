param([string]$Destination = 'D:\PLD\retina_fpga\data\raw\stare')
$ErrorActionPreference = 'Stop'
$sourceBase = 'https://cecas.clemson.edu/~ahoover/stare/probing/'
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$manifestPath = Join-Path $Destination 'download_manifest.json'
if (Test-Path -LiteralPath $manifestPath) {
    $previous = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    foreach ($entry in $previous.files) {
        if ($entry.name -notin @('index.html', 'stare-images.tar', 'labels-ah.tar', 'labels-vk.tar')) {throw 'Unknown manifest filename'}
        $existing = Join-Path $Destination $entry.name
        if (-not (Test-Path -LiteralPath $existing)) {throw 'Previously recorded download is missing'}
        if ((Get-FileHash -LiteralPath $existing -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) {throw 'Previously recorded download hash changed'}
    }
    if ($previous.files.Count -ne 4) {throw 'Incomplete previous manifest'}
    Write-Output 'EXISTING_DOWNLOAD_VERIFIED_MANIFEST_PRESERVED'
    return
}
# Use the Windows certificate store; never bypass HTTPS verification.
foreach ($name in @('index.html', 'stare-images.tar', 'labels-ah.tar', 'labels-vk.tar')) {
    $target = Join-Path $Destination $name
    if (Test-Path -LiteralPath $target) {
        Write-Output "PRESERVED_EXISTING: $name"
        continue
    }
    $partial = "$target.partial"
    Invoke-WebRequest -Uri "$sourceBase$name" -OutFile $partial -TimeoutSec 120
    Move-Item -LiteralPath $partial -Destination $target
    Write-Output "DOWNLOADED: $name"
}
$records = foreach ($name in @('index.html', 'stare-images.tar', 'labels-ah.tar', 'labels-vk.tar')) {
    $target = Join-Path $Destination $name
    @{name=$name; url="$sourceBase$name"; bytes=(Get-Item -LiteralPath $target).Length;
      sha256=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()}
}
@{source=$sourceBase; downloaded_host_utc=[DateTime]::UtcNow.ToString('o'); files=@($records);
  license='No explicit license grant inferred from public download. Preserve attribution; see data/README.md.'} |
  ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding utf8
