@echo off
title ArcSim VR - Monitor de Camara ArUco
cd /d "%~dp0"

echo =======================================================
echo   ArcSim VR - Iniciando Monitor Optico ArUco
echo =======================================================
echo.
echo Abriendo camara web y detector ArUco (DICT_4X4_50)...
echo Presiona Q en la ventana de video para salir.
echo.

c:\Users\MSI\AppData\Local\Programs\Python\Python312\python.exe tools\test_vision_aruco.py

pause
