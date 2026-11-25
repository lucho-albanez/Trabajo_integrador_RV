@echo off
title ArcSim VR - Diagnostico del motor
cd /d "%~dp0"
call "%~dp0_buscar_python.bat" || exit /b 1
echo Cerra Godot, el puente y la ventana de la camara antes de seguir.
pause
%PY% tools\diagnostico_motor.py %1
