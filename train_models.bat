@echo off
cd /d "%~dp0"
python train_models.py %*
exit /b %ERRORLEVEL%
