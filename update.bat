@echo off
setlocal
cd /d "%~dp0"

where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se encuentra Docker. Abre Docker Desktop.
  pause
  exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker Desktop no responde. Abrelo y espera a que arranque.
  pause
  exit /b 1
)

if exist ".git" (
  where git >nul 2>&1
  if not errorlevel 1 (
    echo Actualizando codigo (git pull)...
    git pull
  ) else (
    echo [AVISO] Git no esta instalado; se volverá a implantar el código actual sin actualizar.
  )
) else (
  echo [AVISO] Esta carpeta no es un clon git; no se puede hacer git pull.
  echo Descarga de nuevo el ZIP desde GitHub o clona el repo.
)

if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
)

echo Reconstruyendo e iniciando...
docker compose up --build -d
if errorlevel 1 (
  echo [ERROR] Fallo al actualizar. Prueba: docker compose logs
  pause
  exit /b 1
)

echo.
echo Actualizado. Abriendo http://localhost:8000
start "" "http://localhost:8000"
endlocal
