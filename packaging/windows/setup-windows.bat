@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Solo Windows. Si abres esto desde Linux/WSL path raro, puede fallar.
echo.
echo AlejandrISBN - instalacion de Brave, Git y Docker Desktop
echo Carpeta: %CD%
echo.

net session >nul 2>&1
if errorlevel 1 (
  echo Se necesitan permisos de administrador. Relanzando con UAC...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "Start-Process -FilePath '%ComSpec%' -ArgumentList '/c \"\"%~f0\"\"' -WorkingDirectory '%~dp0' -Verb RunAs"
  exit /b
)

REM Quitar bloqueo de archivo descargado (SmartScreen / "Mark of the Web")
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath '%~dp0' -Filter 'setup-windows.*' | Unblock-File -ErrorAction SilentlyContinue"

echo Ejecutando setup-windows.ps1 ...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1"
set ERR=%ERRORLEVEL%

echo.
if not "%ERR%"=="0" (
  echo El instalador termino con errores ^(codigo %ERR%^).
  echo Si puedes, copia el texto de esta ventana y envialo para depurar.
) else (
  echo Instalador finalizado.
)
echo.
pause
exit /b %ERR%
