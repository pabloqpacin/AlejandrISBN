@echo off
setlocal
echo Cierra la ventana de start-desktop.bat con Ctrl+C,
echo o mata el proceso en el puerto 8000:
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
  echo Terminando PID %%p
  taskkill /PID %%p /F >nul 2>&1
)
echo Listo.
pause
endlocal
