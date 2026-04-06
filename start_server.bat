@echo off
echo ============================================
echo   Urlaubsmagie Bewertungsportal
echo ============================================
echo.
echo Starte Flask Server und Cloudflare Tunnel...
echo.

REM Start Flask in background (cmd /k keeps window open on crash so you can see the error)
start "Flask Server" /min cmd /k "python app.py"

REM Wait for Flask to start
timeout /t 3 /nobreak >nul

REM Start Cloudflare Tunnel in background (separate process so it doesn't kill Flask)
start "Cloudflare Tunnel" /min cmd /k "cloudflared tunnel run umteam-flask"

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
echo Beide Fenster (Flask Server + Cloudflare Tunnel) laufen minimiert.
echo Dieses Fenster kann geschlossen werden.
echo.
pause
