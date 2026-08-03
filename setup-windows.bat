@echo off
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  echo Se necesitan permisos de administrador.
  echo Relanzando con UAC...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo.
echo AlejandrISBN - instalacion de Brave, Git y Docker Desktop
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1"
set ERR=%ERRORLEVEL%

echo.
if not "%ERR%"=="0" (
  echo El instalador termino con errores (codigo %ERR%).
) else (
  echo Instalador finalizado.
)
pause
exit /b %ERR%
