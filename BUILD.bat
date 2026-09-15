@echo off
REM Build script for AIT Generator
REM This script compiles the Python application into an executable

setlocal enabledelayedexpansion

echo.
echo ========================================
echo   AIT Generator - Build Script
echo ========================================
echo.

REM Check if PyInstaller is installed
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install -q tkcalendar reportlab pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
    echo Dependencies installed successfully!
    echo.
)

REM Kill any running instances
echo Closing any running instances...
taskkill /F /IM "UC Immunotherapy.exe" >nul 2>&1

REM Clean build directories
echo Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller
echo.
echo Building executable... This may take a minute or two...
echo.

python -m PyInstaller "UC Immunotherapy.spec" --distpath ./dist --workpath ./build

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

REM Verify the executable exists
if exist "dist\UC Immunotherapy.exe" (
    echo.
    echo ========================================
    echo   BUILD SUCCESSFUL!
    echo ========================================
    echo.
    echo Location: dist\UC Immunotherapy.exe
    for /f %%A in ('powershell -Command "(Get-Item 'dist\UC Immunotherapy.exe').Length / 1MB"') do echo Size: %%A MB
    echo.
    echo Would you like to:
    echo   1) Open the dist folder
    echo   2) Run the application
    echo   3) Exit
    echo.
    set /p choice="Enter choice (1-3): "

    if "!choice!"=="1" (
        explorer dist
    ) else if "!choice!"=="2" (
        start "" "dist\UC Immunotherapy.exe"
    )
) else (
    echo.
    echo ERROR: Executable not found after build!
    pause
    exit /b 1
)

echo.
pause
