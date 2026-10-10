# Instala dist\RussoTrainer em %LOCALAPPDATA%\RussoTrainer\app e cria o atalho na área de trabalho.
# -SeedFrom copia (uma vez) o progresso e o cache de áudio de uma pasta russotrainer existente.
param(
    [string]$SeedFrom = "",
    [string]$Python = "$env:LOCALAPPDATA\RussoTrainerBuild\venv\Scripts\python.exe"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$install = "$env:LOCALAPPDATA\RussoTrainer\app"
$userData = "$env:APPDATA\RussoTrainer\data"

if (-not (Test-Path "$root\dist\RussoTrainer\RussoTrainer.exe")) { throw "Rode build_windows.ps1 primeiro." }
Get-Process RussoTrainer -ErrorAction SilentlyContinue | Stop-Process -Force
New-Item -ItemType Directory -Force $install, $userData | Out-Null
robocopy "$root\dist\RussoTrainer" $install /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Falha ao copiar os arquivos (robocopy $LASTEXITCODE)" }

if ($SeedFrom) {
    $db = "$userData\progress.sqlite3"
    if ((Test-Path "$SeedFrom\data\progress.sqlite3") -and -not (Test-Path $db)) {
        # A API de backup do SQLite junta o arquivo -wal ao copiar, sem corromper o original.
        & $Python -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()" "$SeedFrom\data\progress.sqlite3" $db
        Write-Host "Progresso copiado."
    }
    # Índice do Лексический минимум: fica fora do release público, então vem da sua pasta local.
    if (Test-Path "$SeedFrom\data\lexical_minimum.sqlite3") {
        Copy-Item "$SeedFrom\data\lexical_minimum.sqlite3" "$userData\lexical_minimum.sqlite3" -Force
        Write-Host "Índice do léxico mínimo copiado."
    }
    if ((Test-Path "$SeedFrom\data\tts_cache") -and -not (Test-Path "$userData\tts_cache")) {
        robocopy "$SeedFrom\data\tts_cache" "$userData\tts_cache" /E /NFL /NDL /NJH /NJS /NP | Out-Null
        Write-Host "Cache de áudio copiado."
    }
}

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Russo Trainer.lnk")
$link.TargetPath = "$install\RussoTrainer.exe"
$link.WorkingDirectory = $install
$link.Description = "Treinador local de russo (TRKI-II)"
$link.Save()
Write-Host "Instalado em $install"
