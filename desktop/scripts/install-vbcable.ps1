$ErrorActionPreference = "Stop"

$packageUrl = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip"
$downloadDir = "C:\tmp\vbcable-pack45"
$zipPath = Join-Path $downloadDir "VBCABLE_Driver_Pack45.zip"
$extractDir = Join-Path $downloadDir "extracted"
$installerPath = Join-Path $extractDir "VBCABLE_Setup_x64.exe"

Write-Host "Preparing VB-CABLE installer..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
New-Item -ItemType Directory -Force -Path $extractDir | Out-Null

Write-Host "Downloading official package from $packageUrl" -ForegroundColor Cyan
Invoke-WebRequest -Uri $packageUrl -OutFile $zipPath

Write-Host "Extracting package..." -ForegroundColor Cyan
Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

if (-not (Test-Path $installerPath)) {
    throw "Expected installer not found: $installerPath"
}

Write-Host "Launching VB-CABLE x64 installer as administrator..." -ForegroundColor Yellow
Write-Host "After installation completes, reboot Windows before using the desktop companion privacy route." -ForegroundColor Yellow

Start-Process -FilePath $installerPath -Verb RunAs -Wait

Write-Host ""
Write-Host "Post-install check (device endpoints containing 'CABLE'):" -ForegroundColor Green
Get-PnpDevice -Class AudioEndpoint |
    Where-Object { $_.FriendlyName -like "*CABLE*" } |
    Select-Object Status, FriendlyName, InstanceId

Write-Host ""
Write-Host "If no CABLE endpoints are listed yet, reboot first and run this check again:" -ForegroundColor Yellow
Write-Host 'Get-PnpDevice -Class AudioEndpoint | Where-Object { $_.FriendlyName -like "*CABLE*" } | Select-Object Status, FriendlyName'
