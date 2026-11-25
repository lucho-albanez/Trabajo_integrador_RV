@echo off
cd /d "%~dp0"
call "%~dp0_buscar_python.bat" || exit /b 1
%PY% tools\diagnostico_motor.py --auto
timeout /t 4 >nul
