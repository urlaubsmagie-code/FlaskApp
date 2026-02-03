@echo off
echo ============================================
echo   Urlaubsmagie Bewertungsportal
echo ============================================
echo.
echo Starte Flask Server und Cloudflare Tunnel...
echo.

REM Start Flask in background
start "Flask Server" /min cmd /c "python app.py"

REM Wait for Flask to start
timeout /t 3 /nobreak >nul

echo ============================================
echo   Server gestartet!
echo ============================================
echo.
echo Lokaler Zugriff:
echo   - http://127.0.0.1
echo   - http://192.168.178.36
echo.
echo Externer Zugriff (weltweit):
echo   - https://umteamsbz.com
echo.
echo Druecke Ctrl+C zum Beenden
echo.

REM Start Cloudflare Tunnel
cloudflared tunnel run umteam-flask

REM When tunnel closes, also stop Flask
taskkill /FI "WINDOWTITLE eq Flask Server" /F >nul 2>&1
pause
