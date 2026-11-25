@echo off
title ArcSim VR - Centro de Control y Configuracion
cd /d "%~dp0"
call "%~dp0_buscar_python.bat" || exit /b 1

echo ===================================================================
echo     ArcSim VR - Centro de Control y Configuracion SMAW
echo ===================================================================
echo.
echo Iniciando interfaz grafica de configuracion y lanzador...
echo.

where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 tools\arcsim_gui.py
    exit /b 0
)
%PY% tools\arcsim_gui.py
if errorlevel 1 pause
