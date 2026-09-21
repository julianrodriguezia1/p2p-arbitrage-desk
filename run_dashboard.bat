@echo off
cd /d "%~dp0"
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
REM Liberar el puerto 8000 si quedo un server viejo colgado (evita servir codigo viejo).
echo Liberando el puerto 8000 si quedo un server anterior...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }" 2>nul
REM Abrir el navegador recien cuando el server ya levanto (espera 4s en una ventana aparte).
start "" /min cmd /c "timeout /t 4 >nul & start """" http://127.0.0.1:8000"
python -m uvicorn webapp.server:create_app --factory --host 127.0.0.1 --port 8000
echo.
echo El servidor se detuvo. Revisa el mensaje de arriba si fue por error.
pause
