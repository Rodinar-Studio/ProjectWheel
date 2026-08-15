@echo off
title ProjectWheel Backend Service
set BASE_DIR=%~dp0
cd /d "%BASE_DIR%"

echo ===================================================
echo   ProjectWheel - Gyro Pedal ^& Wheel Driver Server
echo ===================================================
echo.

:: Check for ADB in common paths or PATH
set ADB_EXE=adb.exe
if exist "%BASE_DIR%adb.exe" (
    set ADB_EXE="%BASE_DIR%adb.exe"
    goto :adb_found
)
if exist "%BASE_DIR%platform-tools\adb.exe" (
    set ADB_EXE="%BASE_DIR%platform-tools\adb.exe"
    goto :adb_found
)
where adb.exe >nul 2>nul
if %errorlevel% equ 0 (
    goto :adb_found
)
if exist "C:\Android\platform-tools\adb.exe" (
    set ADB_EXE="C:\Android\platform-tools\adb.exe"
    goto :adb_found
)
if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
    set ADB_EXE="%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
    goto :adb_found
)

echo [ADB] Uyari: adb.exe sistemde veya varsayilan yollarda bulunamadi.
echo [ADB] USB baglantisi kullanacaksaniz Android SDK platform-tools kurmaniz gerekebilir.
echo.
goto :start_server

:adb_found
echo [ADB] Cihaz taramasi yapiliyor...
%ADB_EXE% devices
echo.
echo [ADB] USB port yonlendirmesi (ADB reverse) kuruluyor...
%ADB_EXE% reverse tcp:8000 tcp:8000
echo.

:start_server
echo [SERVER] FastAPI sunucusu port 8000 uzerinde baslatiliyor...
echo WebUI arayuzune ulasmak icin tarayicinizdan sunu acin:
echo   ==^> http://localhost:8000
echo.

:: Try default python from PATH, fallback to uv python or user path if needed
python "%BASE_DIR%backend_app.py"
if %errorlevel% neq 0 (
    echo.
    echo [HATA] Python sunucusu baslatilamadi! 
    echo Lutfen 'pip install fastapi uvicorn websockets vgamepad' komutuyla paketleri yuklediginizden emin olun.
)
pause
