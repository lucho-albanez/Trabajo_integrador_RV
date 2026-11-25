@echo off
REM Busca Python en esta PC y deja el comando en la variable PY.
REM Lo usan todos los .bat con:  call "%~dp0_buscar_python.bat" || exit /b 1
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
    echo.
    echo ERROR: no se encontro Python en esta PC.
    echo Instalalo desde https://www.python.org/downloads/ y marca "Add python.exe to PATH".
    echo Luego instala las librerias:  pip install opencv-contrib-python numpy pyserial
    echo.
    pause
    exit /b 1
)
%PY% -c "import cv2, numpy" >nul 2>nul
if errorlevel 1 (
    echo.
    echo AVISO: faltan librerias de Python. Instalalas con:
    echo     %PY% -m pip install opencv-contrib-python numpy pyserial
    echo.
)
