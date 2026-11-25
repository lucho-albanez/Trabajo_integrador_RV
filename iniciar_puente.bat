@echo off
title ArcSim VR - Puente Serial a Godot
cd /d "%~dp0"
call "%~dp0_buscar_python.bat" || exit /b 1

echo =======================================================
echo   ArcSim VR - Iniciando Puente Serial ESP32 - Godot
echo =======================================================
echo.
echo Buscando el ESP32 y reenviando a Godot (UDP 4242)...
echo Presiona Ctrl+C cuando quieras cerrar el puente.
echo.

%PY% simulacion_godot\trabajo-final-rv\tools\serial_bridge.py

pause
