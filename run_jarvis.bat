@echo off
title Jarvis Voice Assistant

:: Check for Administrator privileges
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo Requesting Administrative Privileges...
    goto UACPrompt
) else ( goto gotAdmin )

:UACPrompt
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    set params=%*
    echo UAC.ShellExecute "cmd.exe", "/c ""%~s0"" %params%", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    del "%temp%\getadmin.vbs"
    exit /b

:gotAdmin
    pushd "%CD%"
    cd /d "%~dp0"
echo =========================================
echo             STARTING JARVIS
echo =========================================
echo.
if exist "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" (
    "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" showvminfo "Home Assistant" | findstr /i "running" >nul
    if errorlevel 1 (
        echo Starting Home Assistant virtual machine...
        "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe" startvm "Home Assistant" --type headless
    )
)

if not exist ".venv\Scripts\activate.bat" (
    echo Error: Virtual environment [.venv] not found.
    echo Please make sure you run this from the project root directory.
    pause
    exit /b
)

echo [SPOTIFY] Opening Spotify Web Player...
start https://open.spotify.com
timeout /t 3 /nobreak >nul

echo.
echo [TUNNEL] Starting permanent ngrok tunnel...
echo [TUNNEL] Fixed URL: https://probation-tiptoeing-evade.ngrok-free.dev
echo [TUNNEL] Open your Vercel URL on any device - it connects automatically.
echo.
start "Jarvis ngrok Tunnel" cmd /k ".\ngrok.exe http --url=probation-tiptoeing-evade.ngrok-free.dev 5000"

call .venv\Scripts\activate.bat
python -u jarvis.py
echo.
echo Jarvis has stopped. Press any key to close.
pause
