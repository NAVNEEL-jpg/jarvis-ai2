@echo off
title Push Termux Server to Phone
echo ========================================================
echo        PUSHING TERMUX SERVER TO YOUR ANDROID PHONE
echo ========================================================
echo.

:: Get ADB location
set ADB_EXE=C:\Users\admin\AppData\Local\Microsoft\WinGet\Packages\Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe\platform-tools\adb.exe
if not exist "%ADB_EXE%" (
    set ADB_EXE=adb
)

:: Verify connection
echo Checking phone connection status...
"%ADB_EXE%" devices | findstr /i "device" >nul
if errorlevel 1 (
    echo [ERROR] No connected Android devices found.
    echo Please make sure your phone is connected via Wireless Debugging first.
    echo run: adb connect ^<phone_ip^>:34067
    pause
    exit /b
)

echo Phone found. Pushing termux_server.py to phone storage...
"%ADB_EXE%" push termux_server.py /sdcard/termux_server.py
if errorlevel 1 (
    echo [ERROR] Failed to push file to phone storage.
    pause
    exit /b
)

echo.
echo [SUCCESS] termux_server.py has been copied to your phone's storage.
echo.
echo ========================================================
echo          HOW TO RUN IT IN TERMUX ON YOUR PHONE
echo ========================================================
echo.
echo 1. Open Termux on your phone and run:
echo    termux-setup-storage
echo.
echo 2. Copy the file from storage to your Termux home directory:
echo    cp /sdcard/termux_server.py ~/
echo.
echo 3. Install Python and Flask in Termux:
echo    pkg update
echo    pkg install python
echo    pip install flask
echo.
echo 4. Run the server:
echo    python termux_server.py
echo.
echo 5. Check your phone's IP address (shown when starting the server).
echo.
echo 6. Open [.env] on PC and set:
echo    PHONE_HTTP_URL=http://^<YOUR_PHONE_IP^>:8765
echo.
echo ========================================================
pause
