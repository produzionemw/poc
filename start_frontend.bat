@echo off
echo Avvio frontend React...
echo.
echo NOTA: il proxy punta a http://localhost:5000 - avvia il backend in un altro terminale:
echo   start_backend.bat
echo.
cd frontend
if not exist node_modules (
    echo Installazione dipendenze...
    call npm install
)
call npm start
