@echo off
REM Script para permitir Flask en Firewall
REM DEBE ejecutarse como Administrador

echo.
echo ============================================
echo  FIREWALL - Permitir Puerto 5000
echo ============================================
echo.

REM Verificar permisos de administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Este script DEBE ejecutarse como Administrador
    echo.
    echo Por favor:
    echo 1. Haz clic derecho en este archivo
    echo 2. Selecciona "Ejecutar como Administrador"
    echo.
    pause
    exit /b 1
)

echo Anadiendo regla de firewall para puerto 5000...
echo.

REM Intentar agregar la regla
netsh advfirewall firewall add rule name="Flask Port 5000" dir=in action=allow protocol=tcp localport=5000 program="C:\Users\admin\Server\FlaskApp\app.py" >nul 2>&1

if %errorlevel% equ 0 (
    echo ✓ Regla agregada exitosamente
    echo.
    echo Ahora puedes acceder desde la TV en:
    echo   http://192.168.178.188:5000
) else (
    echo Posible error. Intentando forma alternativa...
    netsh advfirewall firewall add rule name="Flask Port 5000" dir=in action=allow protocol=tcp localport=5000 >nul 2>&1
    
    if %errorlevel% equ 0 (
        echo ✓ Regla agregada exitosamente
        echo.
        echo Ahora puedes acceder desde la TV en:
        echo   http://192.168.178.188:5000
    ) else (
        echo ✗ No se pudo agregar la regla
        echo.
        echo Opcion alternativa: Desactiva temporalmente el firewall
        echo   Configuracion > Firewall y Seguridad
    )
)

echo.
echo Presiona Enter para cerrar...
pause
