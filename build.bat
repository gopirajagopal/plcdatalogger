@echo off
echo ============================================
echo   Boiler PLC Monitor - Build Executable
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

:: Install dependencies
echo [1/3] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

:: Build with PyInstaller
echo.
echo [2/3] Building executable with PyInstaller...
pyinstaller --noconfirm --onedir --windowed ^
    --name "BoilerPLCMonitor" ^
    --add-data "plc_client.py;." ^
    --add-data "ui_main.py;." ^
    --hidden-import snap7 ^
    --hidden-import pyqtgraph ^
    --hidden-import numpy ^
    --collect-all pyqtgraph ^
    main.py

if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    pause
    exit /b 1
)

:: Copy snap7 DLL if it exists
echo.
echo [2.5/3] Checking for snap7 DLL...
for /f "tokens=*" %%i in ('python -c "import snap7; import os; print(os.path.dirname(snap7.__file__))" 2^>nul') do (
    if exist "%%i\lib\snap7.dll" (
        echo Copying snap7.dll...
        copy "%%i\lib\snap7.dll" "dist\BoilerPLCMonitor\" >nul 2>&1
    )
)

:: Create ZIP
echo.
echo [3/3] Creating ZIP archive...
powershell -Command "if (Test-Path 'dist\BoilerPLCMonitor.zip') { Remove-Item 'dist\BoilerPLCMonitor.zip' }; Compress-Archive -Path 'dist\BoilerPLCMonitor\*' -DestinationPath 'dist\BoilerPLCMonitor.zip' -Force"

if errorlevel 1 (
    echo WARNING: Failed to create ZIP (non-critical)
) else (
    echo ZIP created: dist\BoilerPLCMonitor.zip
)

echo.
echo ============================================
echo   Build complete!
echo   Executable: dist\BoilerPLCMonitor\BoilerPLCMonitor.exe
echo   ZIP:        dist\BoilerPLCMonitor.zip
echo ============================================
pause
