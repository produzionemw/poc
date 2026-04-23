@echo off
echo Avvio backend Flask...
cd backend
if not exist venv (
    echo Creazione ambiente virtuale...
    python -m venv venv
)
call venv\Scripts\activate
if not exist .env (
    echo ATTENZIONE: File .env non trovato!
    echo Crea un file .env nella cartella backend con OPENAI_API_KEY=your_key
    pause
    exit /b 1
)
pip install -r requirements.txt
python app.py
pause
