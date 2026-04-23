@echo off
setlocal
cd /d "%~dp0"

echo Avvio backend (Flask :5000) e frontend (React) in finestre separate...
start "MetalWorkingPOC - Backend" /D "%~dp0backend" cmd /k python app.py
start "MetalWorkingPOC - Frontend" /D "%~dp0frontend" cmd /k npm start

endlocal
