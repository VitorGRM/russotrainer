# Gera dist\RussoTrainer\ e dist\RussoTrainer-v<versão>-windows.zip (o arquivo que vai no release do GitHub).
param([string]$Python = "$env:LOCALAPPDATA\RussoTrainerBuild\venv\Scripts\python.exe")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$version = (Select-String -Path "$root\app.py" -Pattern '^APP_VERSION = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Compilando RussoTrainer v$version"

Remove-Item "$root\dist", "$root\build" -Recurse -Force -ErrorAction SilentlyContinue
& $Python -m PyInstaller "$PSScriptRoot\RussoTrainer.spec" --noconfirm --distpath "$root\dist" --workpath "$root\build"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou" }

$zip = "$root\dist\RussoTrainer-v$version-windows.zip"
Compress-Archive -Path "$root\dist\RussoTrainer\*" -DestinationPath $zip -CompressionLevel Optimal
Write-Host ("Pronto: {0} ({1:N0} MB)" -f $zip, ((Get-Item $zip).Length / 1MB))
