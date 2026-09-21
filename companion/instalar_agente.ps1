# Instala el agente de sync on-demand para que arranque solo, sin ventana, al
# iniciar sesion en Windows. Usa la carpeta de Inicio del usuario (no requiere admin).
$ErrorActionPreference = "Stop"

# 1. Resolver python y derivar pythonw (variante sin consola)
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Write-Host "No encontre Python en el PATH. Instalalo o agregalo al PATH y reintenta." -ForegroundColor Red
    exit 1
}
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (-not (Test-Path $pythonw)) { $pythonw = $python }  # fallback si no hay pythonw

# 2. Raiz del repo = carpeta padre de companion/
$repo = Split-Path $PSScriptRoot -Parent

# 3. Generar un lanzador .vbs en la carpeta de Inicio (ventana oculta, cwd = repo)
$startup = [Environment]::GetFolderPath('Startup')
$vbsPath = Join-Path $startup "ArbitradorAgente.vbs"
$vbs = @"
' Lanza el agente de sync on-demand sin ventana. Generado por instalar_agente.ps1.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "$repo"
sh.Run """$pythonw"" -m companion.agent", 0, False
"@
Set-Content -Path $vbsPath -Value $vbs -Encoding ASCII

# 4. Arrancarlo ya (sin esperar al proximo login)
Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`""

Write-Host "Listo. El actualizador arranca solo al iniciar sesion y ya esta corriendo." -ForegroundColor Green
Write-Host "Vive en:   $vbsPath"
Write-Host "Apagarlo:  powershell -ExecutionPolicy Bypass -File companion\desinstalar_agente.ps1"
