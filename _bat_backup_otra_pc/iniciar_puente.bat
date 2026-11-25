@echo off
title ArcSim VR - Puente Serial a Godot
cd /d "%~dp0"

echo =======================================================
echo   ArcSim VR - Iniciando Puente Serial ESP32 - Godot
echo =======================================================
echo.
echo Conectando con ESP32 en COM4 y reenviando a Godot (UDP 4242)...
echo Presiona Ctrl+C cuando quieras cerrar el puente.
echo.

c:\Users\MSI\AppData\Local\Programs\Python\Python312\python.exe simulacion_godot\trabajo-final-rv\tools\serial_bridge.py

pause
