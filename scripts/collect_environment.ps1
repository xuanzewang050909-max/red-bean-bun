param([string]$VivadoBat = 'E:\vivado\Vivado\2017.4\bin\vivado.bat')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskInfo = [ordered]@{
    captured_at = (Get-Date).ToString('o')
    project = $taskRoot
    os = (Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,OSArchitecture)
    cpu = (Get-CimInstance Win32_Processor | Select-Object Name,AddressWidth,NumberOfCores,NumberOfLogicalProcessors)
    disks = @(Get-PSDrive -PSProvider FileSystem | Select-Object Name,Root,@{Name='free_GiB';Expression={[math]::Round($_.Free/1GB,2)}})
    tools = @(Get-Command git,python,py,ssh -ErrorAction SilentlyContinue | Select-Object Name,Source)
    vivado_executable = $VivadoBat
    vivado_version_output = @(& $VivadoBat -version)
    usb_fpga_devices = @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object { $_.FriendlyName -match 'Xilinx|Digilent|FTDI|PYNQ|USB Serial|USB UART|JTAG' } | Select-Object Status,Class,FriendlyName)
    physical_network_adapters = @(Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Select-Object Name,InterfaceDescription,Status,LinkSpeed)
    board_availability = (Get-Content -LiteralPath (Join-Path $taskRoot 'results\audit\demo_status.json') -Raw | ConvertFrom-Json).board_availability
    board_pcb_revision = $null
    board_pynq_version = $null
}
$taskInfo | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskRoot 'results\audit\environment.json') -Encoding utf8
$taskInfo | ConvertTo-Json -Depth 6
