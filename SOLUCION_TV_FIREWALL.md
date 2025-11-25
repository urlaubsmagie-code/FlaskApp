# 🎥 SOLUCIÓN: El Firewall Bloquea la TV

## El Problema
- ✅ Funciona en Smartphone y Laptop
- ❌ NO funciona en TV
- 🔴 **CAUSA: Windows Firewall está bloqueando el puerto 5000 desde la TV**

## La Solución

### Opción 1: Script Automático (Recomendado)

1. **Haz clic derecho en el archivo:**
   ```
   firewall_fix.bat
   ```

2. **Selecciona: "Ejecutar como Administrador"**

3. **Presiona "Sí" cuando Windows pida confirmación**

4. **El script agregará automáticamente una regla al firewall**

5. **Reinicia el servidor Flask:**
   ```cmd
   start_server.bat
   ```

6. **Intenta acceder desde la TV:**
   ```
   http://192.168.178.188:5000
   ```

---

### Opción 2: Manual (Si el script no funciona)

#### En Windows 10/11:

1. **Abre: Panel de Control → Firewall y Seguridad**

2. **Haz clic en: "Permitir una aplicación a través del firewall"**

3. **Haz clic en: "Cambiar configuración"**

4. **Haz clic en: "Permitir otra aplicación"**

5. **Haz clic en: "Examinar..."**

6. **Navega a:** `C:\Users\admin\Server\FlaskApp\app.py`

7. **Selecciona Python (python.exe)**

8. **Haz clic en "Agregar"**

9. **Asegúrate de marcar AMBAS casillas:**
   - ✓ Privada
   - ✓ Pública

10. **Haz clic en "Aceptar"**

---

### Opción 3: Desactivar Firewall (Temporal)

⚠️ **Solo para pruebas, NO recomendado permanentemente**

1. **En Panel de Control:**
   - Firewall y Seguridad
   - Desactiva todos los perfiles (Domain, Private, Public)

2. **Prueba la TV**

3. **Cuando funcione, RE-ACTIVA el firewall:**
   - Vuelve a activar los 3 perfiles

---

## ¿Por Qué La TV Fue Bloqueada?

Algunos televisores aparecen como "dispositivos desconocidos" en Windows Firewall, por lo que pueden ser bloqueados por defecto.

---

## Confirmación

Después de aplicar cualquier solución:

1. El servidor debe estar corriendo:
   ```
   start_server.bat
   ```

2. Accede desde la TV:
   ```
   http://192.168.178.188:5000
   ```

3. ✅ Debería funcionar perfectamente

---

## Si SIGUE sin funcionar

Intenta estas verificaciones:

1. **Verifica que Flask está realmente corriendo:**
   ```powershell
   netstat -ano | findstr :5000
   ```
   Deberías ver `LISTENING` en la salida

2. **Desde la TV, abre el navegador y prueba:**
   ```
   http://192.168.178.188:5000
   http://admin:5000
   ```

3. **Comprueba que la TV está en la MISMA RED que la PC**

4. **Reinicia el router (desconecta 30 segundos)**

5. **Reinicia la TV completamente**

---

**Última actualización:** 2025-11-10
