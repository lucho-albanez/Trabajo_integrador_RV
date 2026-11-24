@echo off
title ArcSim VR - Sistema Integrado (Vision + ESP32 Bridge)
cd /d "%~dp0"

echo ===================================================================
echo     ArcSim VR - Sistema Integrado de Entrenamiento SMAW
echo ===================================================================
echo.
echo 1. Iniciando Seguimiento por Camara (Mesa y Herramienta ArUco)...
start "ArcSim VR - Vision Tracking" cmd /c "c:\Users\MSI\AppData\Local\Programs\Python\Python312\python.exe tools\test_vision_table.py"

timeout /t 1 /nobreak >nul

echo 2. Iniciando Puente Serial ESP32 (IMU + Laser ToF + Haptico)...
start "ArcSim VR - Puente Serial ESP32" cmd /c "c:\Users\MSI\AppData\Local\Programs\Python\Python312\python.exe simulacion_godot\trabajo-final-rv\tools\serial_bridge.py"

echo.
echo ===================================================================
echo   TODO LISTO Y TRANSMITIENDO EN TIEMPO REAL:
echo   - Vision ArUco : UDP 127.0.0.1:4242 [dx, dy en mm]
echo   - ESP32 Serial : UDP 127.0.0.1:4242 [IMU, ToF, Gatillo, Motor]
echo.
echo   Abre Godot o presiona F5 en el editor para iniciar la simulacion.
echo   (Para cerrar todo, simplemente cierra las ventanas de consola)
echo ===================================================================
echo.
pause
