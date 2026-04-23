@echo off
setlocal
cd /d "%~dp0backend"

echo Training modello ML con ml_model.py ...
python ml_model.py --data "..\dati\Estrazione fattore k (1).xlsx"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo Fatto. Output: backend\ml_model.pkl, backend\ml_metrics.json, backend\ml_charts\
endlocal
