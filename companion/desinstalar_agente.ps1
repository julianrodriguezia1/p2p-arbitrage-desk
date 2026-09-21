# Apaga el agente de sync on-demand: lo saca del inicio de Windows y mata el proceso.
$startup = [Environment]::GetFolderPath('Startup')
$vbsPath = Join-Path $startup "ArbitradorAgente.vbs"

if (Test-Path $vbsPath) {
    Remove-Item $vbsPath -Force
    Write-Host "Quitado del inicio de Windows." -ForegroundColor Green
} else {
    Write-Host "No estaba en el inicio."
}

# Matar el proceso del agente (best-effort, por linea de comando)
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "companion.agent" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host "Proceso $($_.ProcessId) detenido." }

Write-Host "Actualizador apagado." -ForegroundColor Green
