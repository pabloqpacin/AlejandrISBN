@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se encuentra Docker. Instala Docker Desktop y asegurate de que este en marcha.
  echo Guia: docs\SELFHOSTING.md
  pause
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Desktop no responde. Abre Docker Desktop y espera a que arranque.
  pause
  exit /b 1
)

if not exist ".env" (
  echo Creando .env desde .env.example ...
  copy /Y ".env.example" ".env" >nul
)

echo Arrancando AlejandrISBN (puede tardar la primera vez)...
docker compose up --build -d
if errorlevel 1 (
  echo [ERROR] Fallo al levantar el stack. Prueba: docker compose logs
  pause
  exit /b 1
)

echo.
echo Listo. Abriendo http://localhost:8000
echo Para detener: stop.bat
start "" "http://localhost:8000"
endlocal
