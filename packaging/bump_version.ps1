# Le ou altera APP_VERSION no app.py (usado pelo publicar_alteracoes.bat).
#   -Current         mostra a versao atual
#   -Next            mostra a proxima versao de correcao (1.6.0 -> 1.6.1)
#   -Version 1.7.0   grava a nova versao (precisa ser maior que a atual)
# Mensagens em ASCII de proposito: o PowerShell 5.1 le .ps1 sem BOM como ANSI.
param([string]$Version = "", [switch]$Current, [switch]$Next)
$ErrorActionPreference = "Stop"
$path = Join-Path (Split-Path $PSScriptRoot -Parent) "app.py"
$text = [IO.File]::ReadAllText($path)
$match = [regex]::Match($text, '(?m)^APP_VERSION = "([^"]+)"')
if (-not $match.Success) { throw "APP_VERSION nao encontrado em app.py" }
$cur = $match.Groups[1].Value

if ($Current) { Write-Output $cur; exit 0 }
if ($Next) {
    $parts = $cur.Split(".")
    $parts[-1] = [string]([int]$parts[-1] + 1)
    Write-Output ($parts -join "."); exit 0
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Versao invalida: '$Version'. Use o formato 1.6.1" }
if ([version]$Version -le [version]$cur) { throw "A nova versao ($Version) precisa ser maior que a atual ($cur)." }

$group = $match.Groups[1]
$new = $text.Substring(0, $group.Index) + $Version + $text.Substring($group.Index + $group.Length)
[IO.File]::WriteAllText($path, $new, (New-Object System.Text.UTF8Encoding $false))
Write-Output "Versao alterada: $cur -> $Version"
