@echo off
title ArcSim VR - Mesa de Soldadura ArUco
cd /d "%~dp0"

echo =======================================================
echo   ArcSim VR - Seguimiento en Mesa de Soldadura A4
echo =======================================================
echo.
echo Detectando marcadores de mesa (1, 2, 3, 4) y herramienta (0)...
echo Presiona Q en la ventana de video para salir.
echo.

c:\Users\MSI\AppData\Local\Programs\Python\Python312\python.exe tools\test_vision_table.py

pause
