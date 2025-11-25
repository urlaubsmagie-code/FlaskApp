# 🎥 Solución de Problemas - Acceso desde TV

## Problema
La página de slideshow funciona en smartphone y laptop, pero no en la TV.

## Causas Comunes

### 1. **Conexión de red**
   - [ ] Verifica que la TV esté conectada a la MISMA red WiFi que la computadora
   - [ ] Comprueba que la red es de 2.4GHz (algunas TVs no soportan 5GHz)
   - [ ] Reinicia el router si tienes conexión intermitente

### 2. **URL incorrecta**
   - [ ] Usa la dirección IP completa: `http://192.168.178.188:5000`
   - [ ] NO uses `localhost` o `127.0.0.1` (solo funcionan en la misma máquina)
   - [ ] Asegúrate de incluir el puerto `:5000`
   - [ ] La URL debe ser HTTP (no HTTPS)

### 3. **Servidor Flask no está corriendo**
   - [ ] Ejecuta `start_server.bat` en la carpeta `C:\Users\admin\Server\FlaskApp`
   - [ ] Deberías ver un mensaje: `* Running on http://0.0.0.0:5000`
   - [ ] NO cierres la ventana de terminal

### 4. **Firewall bloqueando la conexión**
   - [ ] Verifica que Windows Firewall permita Flask en puerto 5000
   - [ ] En Windows Defender Firewall: Avanzada → Reglas de entrada → Nueva regla
   - [ ] Crea una regla para permitir Python en puerto 5000

### 5. **El navegador de la TV**
   - [ ] Algunos navegadores de TV tienen limitaciones
   - [ ] Intenta con diferentes navegadores si es posible
   - [ ] Limpia el caché del navegador: Configuración → Privacidad → Limpiar datos

## Pasos para Diagnosticar

### Paso 1: Verificar que el servidor está corriendo
```bash
# En otra terminal, ejecuta:
ping 192.168.178.188
# Deberías ver respuestas (packets recibidos)
```

### Paso 2: Verificar conectividad desde otra máquina
```bash
# En smartphone o laptop, abre el navegador e intenta:
http://192.168.178.188:5000
# Si funciona aquí, el problema es la TV o su navegador
```

### Paso 3: Prueba de acceso directo
- Abre el navegador de la TV
- En la barra de dirección, ingresa manualmente: `192.168.178.188:5000`
- Presiona Enter/OK

### Paso 4: Verificar logs del servidor
- En la ventana del servidor Flask, busca mensajes de error
- Copia cualquier error y verifica qué dice

## Soluciones Rápidas

### Opción A: Reiniciar todo
1. Cierra `start_server.bat`
2. Espera 10 segundos
3. Reinicia el servidor ejecutando `start_server.bat`
4. Intenta acceder desde la TV nuevamente

### Opción B: Cambiar la dirección IP en start_server.bat
Si la IP `192.168.178.188` es incorrecta:

1. Abre PowerShell como administrador
2. Ejecuta: `ipconfig /all`
3. Busca "IPv4-Adresse" en la salida
4. Anota la IP que comience con `192.168.x.x` o `10.0.x.x`
5. En `start_server.bat`, cambia la línea de URL por la IP correcta
6. Guarda y reinicia el servidor

### Opción C: Acceso por nombre de máquina
En lugar de IP, prueba:
```
http://admin:5000
```
(Reemplaza "admin" con el nombre de tu usuario/computadora)

### Opción D: Usar URL de localhost en red local
Si tu TV soporta DNS local, prueba:
```
http://flaskapp.local:5000
```

## Configuración HTTP de Compatibilidad

El servidor ahora incluye headers especiales para mejor compatibilidad:
- ✅ CORS habilitado (acceso desde cualquier origen)
- ✅ Headers de caché deshabilitados (contenido siempre fresco)
- ✅ Compatible con navegadores antiguos (IE=edge)
- ✅ Modo responsivo activado

## Comandos Útiles de PowerShell

```powershell
# Ver dirección IP
ipconfig /all

# Probar conectividad
ping 192.168.178.188

# Ver qué está usando el puerto 5000
netstat -ano | findstr :5000

# Detener proceso en puerto 5000 (si es necesario)
taskkill /PID <PID> /F
```

## Si Nada Funciona

1. **Verifica que el router permite conexiones locales**
   - Algunos routers aislados no permiten comunicación entre dispositivos
   - Accede a la configuración del router y busca "Aislamiento de AP"

2. **Intenta conectar TV con cable Ethernet** (si es posible)
   - Las conexiones por cable son más estables

3. **Comprueba que tienes la TV en la misma subred**
   - Si la IP de PC es 192.168.178.188
   - La TV debe estar en 192.168.178.x (no 192.168.0.x)

4. **Reinicia el router completamente**
   - Desconecta durante 30 segundos
   - Reconecta y espera a que se reinicie completamente

## Información de Diagnóstico Rápida

Ejecuta en PowerShell cuando tengas problemas:
```powershell
Write-Host "=== INFORMACIÓN DE DIAGNÓSTICO ===" -ForegroundColor Cyan
Write-Host "IP del servidor:" -ForegroundColor Yellow
ipconfig /all | Select-String "IPv4"
Write-Host ""
Write-Host "Puerto 5000 en uso:" -ForegroundColor Yellow
netstat -ano | findstr :5000
Write-Host ""
Write-Host "Conectividad:" -ForegroundColor Yellow
ping 192.168.178.188
```

---

**Última actualización:** 2025-11-10
**Versión:** 1.0
