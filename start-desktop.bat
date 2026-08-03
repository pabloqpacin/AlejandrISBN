@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Desktop mode: SQLite in %%LOCALAPPDATA%%\AlejandrISBN — no Docker required.

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] No se encuentra Python. Instala Python 3.11+ desde https://www.python.org/downloads/
    echo         Marca "Add python.exe to PATH" en el instalador.
    pause
    exit /b 1
  )
  set "PY=py -3"
) else (
  set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual .venv ...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] No se pudo crear .venv
    pause
    exit /b 1
  )
)

echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install fallo.
  pause
  exit /b 1
)

set "ALEJANDRISBN_BACKEND=sqlite"
set "DATABASE_URL="

echo.
echo Arrancando AlejandrISBN (SQLite, sin Docker)...
echo Datos: %LOCALAPPDATA%\AlejandrISBN\alejandrisbn.db
echo URL:   http://127.0.0.1:8000
echo.
echo Deja esta ventana abierta. Cierra con Ctrl+C o stop-desktop.bat
echo.

start "" "http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

endlocal
