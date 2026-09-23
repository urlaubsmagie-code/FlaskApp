@echo off
REM Starts the WhatsApp bridge in its own window so it survives closing other
REM terminals. Reads WHATSAPP_BRIDGE_SECRET from ChatBotAI\.env.
cd /d "%~dp0whatsapp_bridge"

for /f "tokens=1,* delims==" %%a in ('findstr /b "WHATSAPP_BRIDGE_SECRET=" "%~dp0.env"') do set "WHATSAPP_BRIDGE_SECRET=%%b"
set "FLASK_URL=http://127.0.0.1"

if "%WHATSAPP_BRIDGE_SECRET%"=="" (
    echo FEHLER: WHATSAPP_BRIDGE_SECRET fehlt in ChatBotAI\.env
    pause
    exit /b 1
)

echo ============================================
echo   UMI WhatsApp Bridge
echo ============================================
echo Kopplung / Status:
echo   http://127.0.0.1:3001/qr?t=%WHATSAPP_BRIDGE_SECRET%
echo.
echo Dieses Fenster offen lassen - Schliessen stoppt die Spiegelung.
echo.
node index.js
REM Exit 0 = normal stop, or a bridge was already running. Keep the window open
REM only on a crash, so the error stays readable.
if errorlevel 1 pause
