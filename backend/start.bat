@echo off
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if not exist "venv\Scripts\python.exe" (
    echo [ERRORE] Virtual environment non trovata in "%~dp0venv"
    echo Crea il venv con: python -m venv venv
    echo Poi installa le dipendenze: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Avvio backend Flask su http://127.0.0.1:5000
echo Premi CTRL+C per arrestare il server.
echo.
"venv\Scripts\python.exe" app.py
pause
