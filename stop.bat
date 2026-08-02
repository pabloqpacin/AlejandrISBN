@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se encuentra Docker.
  pause
  exit /b 1
)

echo Deteniendo AlejandrISBN (los datos se conservan)...
docker compose down
if errorlevel 1 (
  echo [ERROR] No se pudo detener el stack.
  pause
  exit /b 1
)

echo Listo. Para volver a arrancar: start.bat
endlocal
