@echo off
echo.
echo  ============================================
echo   ARIA - Build Script for Windows (.exe)
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ from python.org
    echo         Make sure to check "Add Python to PATH" during install!
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
pip install customtkinter pyinstaller --quiet

echo [2/3] Building ARIA.exe (this takes ~60 seconds)...
pyinstaller --onefile --windowed --name ARIA --hidden-import customtkinter --collect-all customtkinter aria.py

echo [3/3] Done!
echo.
if exist dist\ARIA.exe (
    echo  SUCCESS! Your ARIA.exe is ready at:
    echo  %cd%\dist\ARIA.exe
    echo.
    echo  Double-click ARIA.exe to launch — no installation needed!
    explorer dist
) else (
    echo  Build may have failed. Check output above.
)
pause
