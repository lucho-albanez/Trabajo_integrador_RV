@echo off
title ArcSim VR - Centro de Control y Configuracion
cd /d "%~dp0"

echo ===================================================================
echo     ArcSim VR - Centro de Control y Configuracion SMAW
echo ===================================================================
echo.
echo Iniciando interfaz grafica de configuracion y lanzador...
echo.

start "" "c:\Users\MSI\AppData\Local\Programs\Python\Python312\pythonw.exe" tools\arcsim_gui.py
if errorlevel 1 (
    c:\Users\MSI\AppData\Local\Programs\Python\Python312\python.exe tools\arcsim_gui.py
    pause
)
