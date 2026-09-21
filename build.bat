@echo off
REM ============================================================
REM  Bulletin Premium — Build pour Windows (One-file .exe)
REM  Usage : build.bat [clean]
REM ============================================================
title Building Bulletin Premium...

echo.
echo 1/4 — Installation des dependances...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERREUR : pip install a echoue.
    pause
    exit /b 1
)

echo.
echo 2/4 — Verification des donnees Windows PyQt6...
REM Copier les DLLs Windows si disponibles
if exist "C:\Python313\PyQt6\Qt6\bin" (
    xcopy "C:\Python313\PyQt6\Qt6\bin\*.dll" "dist\Bulletin\PyQt6\Qt6\bin\" /Y /Q 2>nul
)

echo.
echo 3/4 — Nettoyage des anciens builds...
if /I "%1"=="clean" (
    if exist dist rmdir /s /q dist
    if exist build rmdir /s /q build
)

echo.
echo 4/4 — Compilation avec PyInstaller...
pyinstaller Bulletin.spec

if %errorlevel% neq 0 (
    echo.
    echo ERREUR : PyInstaller a echoue.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  SUCCES ! L'executable se trouve dans :
echo    dist\Bulletin\Bulletin.exe
echo ============================================================
echo.
pause
