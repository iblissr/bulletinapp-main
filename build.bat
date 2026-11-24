@echo off
REM ============================================================
REM  Bulletin Premium — Build pour Windows
REM  Usage :双击 build.bat  ou  build.bat [clean]
REM ============================================================
title Building Bulletin Premium...

echo.
echo 1/3 — Installation des dépendances…
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERREUR : pip install a echoue.
    pause
    exit /b 1
)

echo.
echo 2/3 — Nettoyage des anciens builds…
if /I "%1"=="clean" (
    if exist dist\Bulletin rmdir /s /q dist\Bulletin
    if exist build\Bulletin rmdir /s /q build\Bulletin
    if exist Bulletin.spec del /q Bulletin.spec
)

echo.
echo 3/3 — Compilation avec PyInstaller…
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
