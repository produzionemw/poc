@echo off
setlocal
cd /d "%~dp0backend"

echo Training con ore aggiornate dal foglio Elaborato (commesse 25^)...
echo Richiede il file storico Metal+ (dimensioni + commessa), es. dati\Estrazione fattore k (1).xlsx
echo.

python ml_model.py --data "..\dati\Estrazione fattore k (1).xlsx" --merge-commesse-ore --commesse-xlsx "..\ORE PER REPARTO PER COMMESSA commesse 25.xlsm"
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo Fatto. Output: backend\ml_model.pkl, backend\ml_metrics.json, backend\ml_charts\, backend\ml_models\
endlocal
